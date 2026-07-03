from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import Question, TaskType, UserProfile
from langdrill_agent.providers import ModelProvider, ModelResult
from langdrill_agent.services import ProfileService, QuestionService, SessionService
from langdrill_agent.task_router import TaskRouter


def test_greeting_routes_as_general_chat() -> None:
    router = TaskRouter()

    assert router.route("你好", has_active_question=False) is TaskType.general_chat
    assert router.route("你好", has_active_question=True) is TaskType.general_chat


def test_advice_question_does_not_start_drill() -> None:
    task = TaskRouter().route("我应该怎么安排四级复习计划？", has_active_question=False)
    practice_advice = TaskRouter().route("怎么练四级听力？", has_active_question=False)

    assert task is TaskType.general_chat
    assert practice_advice is TaskType.general_chat


def test_saved_settings_questions_route_as_general_chat() -> None:
    router = TaskRouter()

    assert (
        router.route(
            "请直接依据我的学习设置回答：我的目标是什么、学习背景是什么？另外列出当前已开启权限中你能使用的学习工具说明。",
            has_active_question=False,
        )
        is TaskType.general_chat
    )
    assert router.route("当前模型和已开启权限是什么？", has_active_question=False) is TaskType.general_chat


def test_settings_mutations_still_route_to_settings() -> None:
    router = TaskRouter()

    assert router.route("请把学习目标改成四级600分", has_active_question=False) is TaskType.settings
    assert router.route("帮我配置一个自定义模型 mimo-v2.5", has_active_question=False) is TaskType.settings
    assert router.route("请开启联网功能权限", has_active_question=False) is TaskType.settings
    assert router.route("导入 2025 年四级真题并解析", has_active_question=False) is TaskType.settings


def test_explicit_drill_requests_still_start_drill() -> None:
    router = TaskRouter()

    assert router.route("请给我出 12 道四级词汇题", has_active_question=False) is TaskType.daily_drill
    assert router.route("今天练 CET-4 高频词汇", has_active_question=False) is TaskType.daily_drill
    assert router.route("collision: 碰撞；冲突", has_active_question=False) is TaskType.daily_drill
    assert router.route("再来点题", has_active_question=False) is TaskType.daily_drill
    assert router.route("再来2题吧", has_active_question=False) is TaskType.daily_drill
    assert router.route("再来 2 题吧", has_active_question=False) is TaskType.daily_drill
    assert router.route("在来点题", has_active_question=False) is TaskType.daily_drill
    assert router.route("给我来两道阅读题", has_active_question=False) is TaskType.daily_drill
    assert router.route("再来一组翻译判断题", has_active_question=False) is TaskType.daily_drill
    assert router.route("接着练练", has_active_question=False) is TaskType.daily_drill


def test_vague_extra_drill_request_asks_for_preferences() -> None:
    router = TaskRouter()

    assert router.route("再来几题", has_active_question=False) is TaskType.extra_drill_setup
    assert router.route("再来几道题吧", has_active_question=False) is TaskType.extra_drill_setup
    assert router.route("继续几题", has_active_question=False) is TaskType.extra_drill_setup


def test_greeting_chat_calls_model_without_generating_questions(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "greeting.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)

    client = TestClient(app)
    response = client.post("/api/chat", json={"content": "你好", "force_new_session": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["active_question"] is None
    assert "已根据当前学习目标整理好下一步" in payload["message"]["content"]
    assert payload["daily_panel"]["questions_total"] == 0
    assert payload["daily_panel"]["knowledge_total"] == 0

    with transaction(db_path) as conn:
        question_count = conn.execute("SELECT COUNT(*) AS total FROM questions").fetchone()["total"]
        model_call_count = conn.execute("SELECT COUNT(*) AS total FROM model_calls").fetchone()["total"]
        messages = conn.execute(
            "SELECT role, content, payload_json FROM messages WHERE session_id=? ORDER BY created_at ASC",
            (payload["session_id"],),
        ).fetchall()

    assert question_count == 0
    assert model_call_count == 1
    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_general_chat_prompt_includes_runtime_context(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "general-context.db"
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "multi-search-engine"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: multi-search-engine\n"
        "description: Generate auditable search URLs without API keys.\n"
        "---\n"
        "This skill does not require API keys.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    monkeypatch.setenv("LANGDRILL_SKILLS_ROOTS", str(skills_root))
    init_db(db_path)
    with transaction(db_path) as conn:
        ProfileService(conn).update(
            UserProfile(
                learning_goal="四级 550 分",
                learning_background="高中英语基础，阅读弱",
                deadline="2026-12-12T09:00",
                global_user_prompt="回答先给结论。",
            )
        )

    captured = {}

    def fake_complete(self, pack):
        captured["pack"] = pack
        return ModelResult(content="模型回复", input_tokens=10, output_tokens=4, latency_ms=1, model=self.model)

    monkeypatch.setattr(ModelProvider, "complete", fake_complete)
    client = TestClient(app)
    response = client.post("/api/chat", json={"content": "你好", "force_new_session": True})

    assert response.status_code == 200
    assert response.json()["message"]["content"] == "模型回复"
    pack = captured["pack"]
    module_ids = [module["id"] for module in pack.system_modules]
    assert "core.safety" in module_ids
    assert "core.product_capabilities" in module_ids
    assert "task.general_chat" in module_ids
    assert "persona.professional" in module_ids
    assert "profile.saved_user_prompt" in module_ids
    assert "runtime.profile_context_contract" in module_ids
    assert "runtime.tool_usage_contract" in module_ids
    assert pack.context_pack["profile"]["learning_goal"] == "四级 550 分"
    assert pack.context_pack["profile"]["learning_background"] == "高中英语基础，阅读弱"
    assert pack.context_pack["profile"]["deadline"] == "2026-12-12T09:00"
    permissions = pack.context_pack["agent_permissions"]
    assert "profile_exam" in permissions["enabled_feature_ids"]
    assert any(item["feature_id"] == "profile_exam" for item in permissions["enabled_tool_guidance"])
    assert any(item["feature_id"] == "web_search_import" for item in permissions["enabled_tool_guidance"])
    skills = pack.context_pack["skills"]
    assert skills["builtin_web_search"]["behavior"]
    assert skills["web_search_skill"]["behavior"]
    assert skills["enabled_skill_guidance"]


def test_saved_settings_question_calls_model_with_runtime_context(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "settings-question-context.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    with transaction(db_path) as conn:
        ProfileService(conn).update(
            UserProfile(
                learning_goal="四级600分",
                learning_background="高中英语，阅读和长难句偏弱",
                deadline="2026-07-14T09:00",
            )
        )

    captured = {}

    def fake_complete(self, pack):
        captured["pack"] = pack
        return ModelResult(content="已读取学习设置上下文", input_tokens=10, output_tokens=4, latency_ms=1, model=self.model)

    monkeypatch.setattr(ModelProvider, "complete", fake_complete)
    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={
            "content": "请直接依据我的学习设置回答：我的目标是什么、学习背景是什么？另外列出当前已开启权限中你能使用的学习工具说明。",
            "force_new_session": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"]["content"] == "已读取学习设置上下文"
    pack = captured["pack"]
    assert pack.context_pack["task_type"] == "general_chat"
    assert pack.context_pack["profile"]["learning_goal"] == "四级600分"
    assert pack.context_pack["profile"]["learning_background"] == "高中英语，阅读和长难句偏弱"
    assert any(
        item["feature_id"] == "profile_exam"
        for item in pack.context_pack["agent_permissions"]["enabled_tool_guidance"]
    )


def test_question_explanation_prompt_uses_runtime_context(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "question-explanation-context.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    with transaction(db_path) as conn:
        ProfileService(conn).update(
            UserProfile(
                learning_goal="四级 600 分",
                learning_background="高中英语，语法薄弱",
                deadline="2026-12-12T09:00",
            )
        )
        session_id = SessionService(conn).ensure_session(None, "题目追问", force_new=True)
        QuestionService(conn).save_question(
            Question(
                id="q_explain_runtime",
                session_id=session_id,
                sequence=1,
                type="multiple_choice",
                prompt="Which option best completes the sentence: She ____ the deadline by one day.",
                options=["extended", "extensive", "extension", "extent"],
                answer={"letter": "A", "correct": "extended"},
                explanation="extended means made longer in time.",
                knowledge_tags=["vocabulary:extend"],
                difficulty=0.4,
            )
        )

    captured = {}

    def fake_complete(self, pack):
        captured["pack"] = pack
        return ModelResult(content="提示回复", input_tokens=10, output_tokens=4, latency_ms=1, model=self.model)

    monkeypatch.setattr(ModelProvider, "complete", fake_complete)
    client = TestClient(app)
    response = client.post("/api/chat", json={"session_id": session_id, "content": "给点提示，不要告诉答案"})

    assert response.status_code == 200
    pack = captured["pack"]
    module_ids = [module["id"] for module in pack.system_modules]
    assert "task.evaluator" in module_ids
    assert "runtime.profile_context_contract" in module_ids
    assert "runtime.tool_usage_contract" in module_ids
    assert pack.context_pack["task_type"] == "explanation"
    assert pack.context_pack["profile"]["learning_goal"] == "四级 600 分"
    assert pack.context_pack["profile"]["learning_background"] == "高中英语，语法薄弱"
    assert pack.context_pack["active_question"]["options"] == ["extended", "extensive", "extension", "extent"]
    assert any(item["feature_id"] == "learning_database" for item in pack.context_pack["agent_permissions"]["enabled_tool_guidance"])


def test_branch_create_and_message_call_model(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "branch-model.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    with transaction(db_path) as conn:
        ProfileService(conn).update(
            UserProfile(
                learning_goal="四级 600 分",
                learning_background="高中英语，阅读弱",
                deadline="2026-12-12T09:00",
            )
        )
        session_id = SessionService(conn).ensure_session(None, "分支源会话", force_new=True)
        QuestionService(conn).save_question(
            Question(
                id="q_branch_runtime",
                session_id=session_id,
                sequence=1,
                type="multiple_choice",
                prompt="Choose the word closest in meaning to altogether in this sentence.",
                options=["completely", "rarely", "separately", "briefly"],
                answer={"letter": "A", "correct": "completely"},
                explanation="altogether can mean completely.",
                knowledge_tags=["vocabulary:altogether"],
                difficulty=0.3,
            )
        )

    captured_packs = []

    def fake_complete(self, pack):
        captured_packs.append(pack)
        return ModelResult(content="分支模型回复", input_tokens=12, output_tokens=5, latency_ms=1, model=self.model)

    monkeypatch.setattr(ModelProvider, "complete", fake_complete)
    client = TestClient(app)
    create_response = client.post(
        "/api/branch",
        json={"session_id": session_id, "selected_text": "altogether", "message": "解释这个词"},
    )

    assert create_response.status_code == 200
    branch_id = create_response.json()["branch_id"]
    assert create_response.json()["message"] == "分支模型回复"

    message_response = client.post(f"/api/branch/{branch_id}/messages", json={"message": "再给一个例句"})
    assert message_response.status_code == 200
    assert message_response.json()["message"] == "分支模型回复"
    assert len(captured_packs) == 2
    assert captured_packs[0].context_pack["selected_text"] == "altogether"
    branch_module_ids = [module["id"] for module in captured_packs[0].system_modules]
    assert "task.branch_chat" in branch_module_ids
    assert "runtime.profile_context_contract" in branch_module_ids
    assert "runtime.tool_usage_contract" in branch_module_ids
    assert "runtime.branch_context_contract" in branch_module_ids
    assert captured_packs[0].context_pack["profile"]["learning_goal"] == "四级 600 分"
    assert captured_packs[0].context_pack["profile"]["deadline"] == "2026-12-12T09:00"
    assert captured_packs[0].context_pack["active_question"]["prompt"].startswith("Choose the word")
    assert captured_packs[0].context_pack["active_question"]["options"] == ["completely", "rarely", "separately", "briefly"]
    assert any(
        item["feature_id"] == "profile_exam"
        for item in captured_packs[0].context_pack["agent_permissions"]["enabled_tool_guidance"]
    )

    with transaction(db_path) as conn:
        model_call_count = conn.execute("SELECT COUNT(*) AS total FROM model_calls WHERE task_type='branch_chat'").fetchone()["total"]

    assert model_call_count == 2


def test_branch_without_selected_text_uses_main_session_context(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "branch-main-context.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    with transaction(db_path) as conn:
        session_service = SessionService(conn)
        session_id = session_service.ensure_session(None, "主会话背景", force_new=True)
        session_service.add_message(session_id, "user", "silence: n. 寂静；沉默")
        session_service.add_message(session_id, "assistant", "silence 常用于 in silence 和 keep silence。")

    captured = {}

    def fake_complete(self, pack):
        captured["pack"] = pack
        return ModelResult(content="基于主会话背景的分支回复", input_tokens=15, output_tokens=8, latency_ms=1, model=self.model)

    monkeypatch.setattr(ModelProvider, "complete", fake_complete)
    client = TestClient(app)
    response = client.post(
        "/api/branch",
        json={"session_id": session_id, "selected_text": "", "message": "帮我继续解释 silence 的用法"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "基于主会话背景的分支回复"
    pack = captured["pack"]
    assert pack.context_pack["selected_text"] == ""
    assert pack.context_pack["branch_source"] == "main_session_context"
    messages = pack.context_pack["main_session_context"]["messages"]
    assert [message["content"] for message in messages] == [
        "silence: n. 寂静；沉默",
        "silence 常用于 in silence 和 keep silence。",
    ]

    with transaction(db_path) as conn:
        branch = conn.execute("SELECT selected_text, title FROM branch_conversations").fetchone()

    assert branch["selected_text"] == ""
    assert branch["title"].startswith("帮我继续解释")
