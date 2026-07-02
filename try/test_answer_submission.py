from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.agents import EvaluatorTutorAgent, QuestionAuthorAgent
from langdrill_agent.api import app
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import ChatRequest, Question, TaskType, UserProfile
from langdrill_agent.providers import ModelResult
from langdrill_agent.services import ProfileService, QuestionService, SessionService
from langdrill_agent.task_router import TaskRouter
from langdrill_agent.utils import dumps


class ChineseOptionProvider:
    provider_id = "bad-options"
    model = "bad-options-model"

    def complete(self, pack) -> ModelResult:
        payload = {
            "opening_message": "bad option set",
            "questions": [
                {
                    "type": "cloze",
                    "prompt": "Choose the best word to complete the sentence.\n\nDoctors used a ______ to perform the operation.",
                    "options": ["laser", "robe", "loyalty", "真实联调"],
                    "answer": {"letter": "A", "correct": "laser"},
                    "explanation": "Laser fits the medical context.",
                    "knowledge_tags": ["vocabulary:laser"],
                    "difficulty": 0.35,
                    "source_refs": [{"type": "generated", "boundary": "practice_only"}],
                }
            ],
        }
        return ModelResult(content=dumps(payload), input_tokens=1, output_tokens=1, latency_ms=0, model=self.model)


class CapturePromptProvider:
    provider_id = "capture"
    model = "capture-model"

    def __init__(self) -> None:
        self.packs = []

    def complete(self, pack) -> ModelResult:
        self.packs.append(pack)
        return ModelResult(
            content="判断：正确。\n\n正确答案：A skin。\n\nD 是 waterfall，意思是瀑布，不能和 harm 搭配表示损害皮肤。",
            input_tokens=1,
            output_tokens=1,
            latency_ms=0,
            model=self.model,
        )


def test_selected_option_routes_as_answer_even_with_extra_prompt() -> None:
    request = ChatRequest(
        content="",
        selected_option="B",
        question_id="q_1",
        extra_prompt="顺便讲一下为什么 A 不对",
    )

    task = TaskRouter().route(
        request.content,
        has_active_question=True,
        selected_text=request.selected_text,
        selected_option=request.selected_option,
    )

    assert task is TaskType.answer_question


def test_hint_request_routes_as_explanation_when_question_is_active() -> None:
    task = TaskRouter().route(
        "请给我一点提示，不要直接告诉正确答案。",
        has_active_question=True,
    )

    assert task is TaskType.explanation


def test_chat_answers_question_by_id_without_model_reroute(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "answer.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)

    with transaction(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES ('model.default', ?, CURRENT_TIMESTAMP)
            """,
            (
                dumps(
                    {
                        "provider_id": "mock",
                        "base_url": "",
                        "model": "mock-tutor-v1",
                        "api_format": "mock",
                        "has_api_key": False,
                    }
                ),
            ),
        )
        session_id = SessionService(conn).ensure_session(None, "answer test", force_new=True)
        QuestionService(conn).save_question(
            Question(
                id="q_answer_by_id",
                session_id=session_id,
                sequence=1,
                type="multiple_choice",
                prompt="Which sentence uses affect correctly?",
                options=["A works", "B fails"],
                answer={"letter": "A", "correct": "A works"},
                explanation="A is correct.",
                knowledge_tags=["vocabulary:affect"],
                difficulty=0.3,
                source_refs=[],
            )
        )

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={
            "content": "",
            "session_id": session_id,
            "selected_option": "A",
            "question_id": "q_answer_by_id",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "判断：正确" in payload["message"]["content"]
    assert payload["active_question"] is None
    assert payload["answered_question"]["id"] == "q_answer_by_id"
    assert payload["answered_question"]["selected_option"] == "A"
    assert payload["answered_question"]["selected_answer"] == "A works"
    assert payload["answered_question"]["is_correct"] is True
    assert payload["message"]["payload"]["answered_question"]["id"] == "q_answer_by_id"
    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["messages"][-1]["payload"]["answered_question"]["id"] == "q_answer_by_id"

    with transaction(db_path) as conn:
        calls = conn.execute(
            "SELECT task_type FROM model_calls WHERE agent_name='evaluator_tutor'"
        ).fetchall()

    assert [row["task_type"] for row in calls] == ["answer_evaluation"]


def test_answer_extra_prompt_is_structured_and_profile_usage_is_not_repetitive(tmp_path: Path) -> None:
    db_path = tmp_path / "answer-extra-prompt.db"
    init_db(db_path)
    provider = CapturePromptProvider()

    with transaction(db_path) as conn:
        ProfileService(conn).update(
            UserProfile(
                exam_id="cet4",
                exam_name="大学英语四级",
                learning_goal="四级 600 分",
                learning_background="阅读和长难句偏弱",
                global_user_prompt="讲题时先给结论，再解释易混点。",
            )
        )
        session_id = SessionService(conn).ensure_session(None, "answer extra prompt", force_new=True)
        question = Question(
            id="q_extra_prompt",
            session_id=session_id,
            sequence=1,
            type="cloze",
            prompt="Choose the best word to complete the sentence.\n\nThis cream can protect your ______.",
            options=["skin", "hence", "fierce", "waterfall"],
            answer={"letter": "A", "correct": "skin"},
            explanation="Skin fits the body-part context.",
            knowledge_tags=["vocabulary:skin"],
            difficulty=0.3,
            source_refs=[],
        )
        QuestionService(conn).save_question(question)
        EvaluatorTutorAgent(conn, provider).evaluate(
            session_id,
            QuestionService(conn).active_question(session_id),
            "A",
            extra_prompt="D 不太会",
        )

    pack = provider.packs[0]
    module_text = "\n".join(module["content"] for module in pack.system_modules)

    assert pack.context_pack["user_extra_prompt"] == "D 不太会"
    assert "必须先直接回应用户这个补充提问" in pack.context_pack["answer_feedback_contract"]["extra_prompt_priority"]
    assert "不要输出“下一题已就绪”" in pack.context_pack["answer_feedback_contract"]["progress_footer"]
    assert "用户额外提问：D 不太会" in pack.user_content
    assert "必须在正文前半部分直接回答这个提问" in pack.user_content
    assert "不要写“下一题已就绪”" in pack.user_content
    assert "不要每次显式重复学习目标" in pack.user_content
    assert "profile.saved_user_prompt" in [module["id"] for module in pack.system_modules]
    assert "讲题时先给结论，再解释易混点。" in module_text
    assert "除非用户主动询问学习设置、制定计划" in module_text
    assert "要主动结合这些信息" not in module_text


def test_model_feedback_progress_footer_is_stripped() -> None:
    feedback = (
        "判断：正确。\n\n"
        "正确答案：A skin。\n\n"
        "讲解：skin fits the sentence.\n\n"
        "下一题已就绪：第 7 题 / 共 11 题。"
    )

    assert EvaluatorTutorAgent._strip_drill_progress_footer(feedback) == (
        "判断：正确。\n\n"
        "正确答案：A skin。\n\n"
        "讲解：skin fits the sentence."
    )
    assert EvaluatorTutorAgent._strip_drill_progress_footer("下一题已就绪：第 7 题 / 共 11 题。") == ""


def test_model_feedback_json_is_rendered_as_readable_text() -> None:
    base_feedback = "判断：正确。\n\n正确答案：A answer"

    assert EvaluatorTutorAgent._coerce_model_feedback("{}", base_feedback) == base_feedback
    assert EvaluatorTutorAgent._coerce_model_feedback(
        '{"message": "继续保持，下一题注意搭配语境。"}',
        base_feedback,
    ) == f"{base_feedback}\n\n模型补充：继续保持，下一题注意搭配语境。"


def test_english_question_author_rejects_chinese_options(tmp_path: Path) -> None:
    db_path = tmp_path / "reject_chinese_options.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        profile = ProfileService(conn).get()
        ProfileService(conn).update(profile.model_copy(update={"exam_id": "cet4", "target_language": "英语"}))
        session_id = SessionService(conn).ensure_session(None, "bad options", force_new=True)

        QuestionAuthorAgent(conn, ChineseOptionProvider()).ensure_question_set(
            session_id,
            "laser: 激光\nrobe: 长袍\nloyalty: 忠诚\ncontext: 语境",
            target_count=4,
        )
        active = QuestionService(conn).active_question(session_id)
        calls = conn.execute(
            "SELECT validation_status FROM model_calls WHERE agent_name='question_author'"
        ).fetchall()

    assert active is not None
    assert all("真实联调" not in option for option in active["options"])
    assert all(not any("\u4e00" <= char <= "\u9fff" for char in option) for option in active["options"])
    assert [row["validation_status"] for row in calls] == ["fallback_after_validation_failure"]
