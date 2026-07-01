from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import TaskType
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


def test_explicit_drill_requests_still_start_drill() -> None:
    router = TaskRouter()

    assert router.route("请给我出 12 道四级词汇题", has_active_question=False) is TaskType.daily_drill
    assert router.route("今天练 CET-4 高频词汇", has_active_question=False) is TaskType.daily_drill
    assert router.route("collision: 碰撞；冲突", has_active_question=False) is TaskType.daily_drill


def test_greeting_chat_does_not_generate_questions(tmp_path: Path, monkeypatch) -> None:
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
    assert "你好" in payload["message"]["content"]
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
    assert model_call_count == 0
    assert [message["role"] for message in messages] == ["user", "assistant"]
