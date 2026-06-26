from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.agents import EvaluatorTutorAgent, QuestionAuthorAgent
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import UserProfile
from langdrill_agent.providers import ModelProvider
from langdrill_agent.screenshot_import import ScreenshotImportService
from langdrill_agent.services import ProfileService, QuestionService, SessionService


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


def test_screenshot_import_persists_words_and_updates_daily_panel(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "import.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)

    with transaction(db_path) as conn:
        ProfileService(conn).update(UserProfile(exam_id="cet4", exam_name="大学英语四级"))
        session_id = SessionService(conn).ensure_session(None, "screenshot import", force_new=True)

    client = TestClient(__import__("langdrill_agent.api", fromlist=["app"]).app)
    response = client.post(
        "/api/screenshot/parse",
        json={
            "text": REAL_SCREENSHOT_TEXT,
            "session_id": session_id,
            "import_to_session": True,
            "source_image_path": "D:/29551/QQ_Files/Tencent Files/2955161835/nt_qq/nt_data/Pic/2026-06/Ori/1f9a9f2e2274ac8f269ad438356fb1c5.png",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["imported_count"] >= 10
    assert payload["words"][0]["term"] == "cultivate"
    with transaction(db_path) as conn:
        rows = conn.execute(
            "SELECT term, meaning, exam_id, source_scope FROM knowledge_items ORDER BY created_at ASC"
        ).fetchall()
        panel = SessionService(conn).daily_panel(session_id)

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
    assert "cultivate" in question.prompt
    assert question.knowledge_tags == ["vocabulary:cultivate"]
    assert result.is_correct is True
    assert row["mastery_score"] > 0.2
    assert row["due_at"]
    assert active is None
