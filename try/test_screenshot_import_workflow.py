from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.agents import EvaluatorTutorAgent, QuestionAuthorAgent
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import UserProfile
from langdrill_agent.providers import ModelProvider
from langdrill_agent.screenshot_import import ScreenshotImportService
from langdrill_agent.services import ProfileService, QuestionService, SessionService
from langdrill_agent.utils import dumps


REAL_SCREENSHOT_TEXT = """
单词列表
cultivate
v. 培养，发展；耕作，种植，栽培
material
n. 材料，原料； adj. 物质的，客观存在的
research
n. 研究，调查； v. 研究，调查
course
n. 课程；过程；一道菜；进程； adv. 当然
blood
n. 血（液）；血统
executive
n. 经理；行政人员； adj. 执行的
adequate
adj. 足够的，充分的
process
n. 步骤，过程； v. 加工；处理
bow
vi. 鞠躬，弯腰
laser
n. 激光
robe
n. 长袍，礼服
loyalty
n. 忠诚，忠心
"""


NOISY_MOBILE_WORD_LIST_TEXT = """
截图导入文本：
15:29
88
单词列表
共4440词
按词书默认排序
skin
n.皮，皮肤，肤色；兽皮，毛皮
hence
adv.因此
vigorous
adj.强有力的，有活力的
waterfall
n.瀑布
fierce
adj.凶猛的，凶狠的；激烈的
contrary
adj.对立的，相反的；叛逆的
discard
V.丢掉
evident
adj.显然的，明显的，明白的
fall
vi.下降，减弱；落下；跌倒，突然倒下
class
n.课，上
等级制度
abc
altoge.
速听
单词选义
速刷
拼写
听写
adv.完全
forever
"""


def _use_mock_provider(db_path: Path) -> None:
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
                        "has_api_key": False,
                    }
                ),
            ),
        )


def test_parse_real_word_list_text_from_user_screenshot() -> None:
    parsed = ScreenshotImportService().parse_text(REAL_SCREENSHOT_TEXT)

    assert parsed["confidence"] == "vocabulary_list"
    assert [item["term"] for item in parsed["words"][:5]] == [
        "cultivate",
        "material",
        "research",
        "course",
        "blood",
    ]
    assert parsed["words"][0]["meaning"].startswith("v. 培养")


def test_parse_noisy_mobile_word_list_skips_navigation_and_repairs_clipped_terms() -> None:
    parsed = ScreenshotImportService().parse_text(NOISY_MOBILE_WORD_LIST_TEXT)

    terms = [item["term"] for item in parsed["words"]]
    meanings = {item["term"]: item["meaning"] for item in parsed["words"]}

    assert parsed["confidence"] == "vocabulary_list"
    assert terms == [
        "skin",
        "hence",
        "vigorous",
        "waterfall",
        "fierce",
        "contrary",
        "discard",
        "evident",
        "fall",
        "class",
        "altogether",
    ]
    assert meanings["class"] == "n.课，上 等级制度"
    assert "速听" not in meanings["class"]
    assert meanings["altogether"] == "adv.完全"
    assert "forever" not in terms
    assert parsed["diagnostics"]["repaired_terms"][0]["term"] == "altogether"
    assert parsed["diagnostics"]["skipped_lines"][0]["text"] == "forever"


def test_parse_inline_vocabulary_formats_from_chat_or_ocr() -> None:
    parsed = ScreenshotImportService().parse_text(
        "\n".join(
            [
                "collision n. 碰撞；冲突",
                "reservation: 预订；保留",
                "maintain v. 维持；维护",
                "approximately：大约",
            ]
        )
    )

    assert parsed["confidence"] == "vocabulary_list"
    assert [item["term"] for item in parsed["words"]] == [
        "collision",
        "reservation",
        "maintain",
        "approximately",
    ]
    assert parsed["words"][0]["meaning"] == "n. 碰撞；冲突"
    assert parsed["words"][1]["meaning"] == "预订；保留"


def test_screenshot_import_persists_words_and_updates_daily_panel(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "import.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    _use_mock_provider(db_path)

    with transaction(db_path) as conn:
        ProfileService(conn).update(UserProfile(exam_id="cet4", exam_name="大学英语四级"))
        session_id = SessionService(conn).ensure_session(None, "screenshot import", force_new=True)
        conn.execute(
            """
            INSERT INTO knowledge_items
            (id, kind, term, meaning, notes, exam_id, source_scope, mastery_score)
            VALUES ('kn_stale_auto_test', 'word', 'legacy', '旧会话污染项', '{}', 'cet4', 'chat_input', 0.1)
            """
        )

    client = TestClient(__import__("langdrill_agent.api", fromlist=["app"]).app)
    response = client.post(
        "/api/screenshot/parse",
        json={
            "text": REAL_SCREENSHOT_TEXT,
            "session_id": session_id,
            "import_to_session": True,
            "auto_start_drill": True,
            "force_new_session": True,
            "source_image_path": "D:/29551/QQ_Files/Tencent Files/2955161835/nt_qq/nt_data/Pic/2026-06/Ori/1f9a9f2e2274ac8f269ad438356fb1c5.png",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["imported_count"] >= 10
    assert payload["auto_started"] is True
    assert payload["words"][0]["term"] == "cultivate"
    assert payload["session_id"] != session_id
    assert payload["active_question"]["sequence"] == 1
    assert payload["active_question"]["set_total"] >= 4
    assert "Choose the best word to complete the sentence" in payload["active_question"]["prompt"]
    assert "最合适的理解" not in payload["active_question"]["prompt"]
    assert "cultivate" in payload["active_question"]["options"]
    assert "legacy" not in payload["active_question"]["options"]
    assert len(payload["messages"]) == 2
    with transaction(db_path) as conn:
        rows = conn.execute(
            """
            SELECT term, meaning, exam_id, source_scope
            FROM knowledge_items
            WHERE source_scope='screenshot_import'
            ORDER BY created_at ASC
            """
        ).fetchall()
        panel = SessionService(conn).daily_panel(payload["session_id"])

    assert rows[0]["term"] == "cultivate"
    assert rows[0]["exam_id"] == "cet4"
    assert rows[0]["source_scope"] == "screenshot_import"
    assert panel["knowledge_total"] >= 10


def test_imported_vocabulary_can_seed_fallback_question_and_mastery_update(tmp_path: Path) -> None:
    db_path = tmp_path / "question.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        ProfileService(conn).update(UserProfile(exam_id="cet4", exam_name="大学英语四级"))
        sessions = SessionService(conn)
        session_id = sessions.ensure_session(None, "imported words", force_new=True)
        parsed = ScreenshotImportService().parse_text(REAL_SCREENSHOT_TEXT)
        imported = ScreenshotImportService().import_words(
            conn,
            session_id=session_id,
            parsed=parsed,
            exam_id="cet4",
            source_image_path="user-screenshot.png",
        )
        question = QuestionAuthorAgent(conn, ModelProvider("mock", "mock-tutor-v1")).ensure_first_question(session_id)
        result = EvaluatorTutorAgent(conn, ModelProvider("mock", "mock-tutor-v1")).evaluate(
            session_id,
            question.model_dump(),
            "A",
        )
        row = conn.execute(
            "SELECT mastery_score, due_at FROM knowledge_items WHERE term='cultivate' AND exam_id='cet4'"
        ).fetchone()
        active = QuestionService(conn).active_question(session_id)

    assert imported >= 10
    assert question.type == "cloze"
    assert "Choose the best word to complete the sentence" in question.prompt
    assert "______" in question.prompt
    assert "cultivate" in question.options
    assert "最贴近的中文释义" not in question.prompt
    assert question.knowledge_tags == ["vocabulary:cultivate"]
    assert result.is_correct is True
    assert row["mastery_score"] > 0.2
    assert row["due_at"]
    assert active is not None
    assert active["sequence"] == 2
