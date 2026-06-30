from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import ChatRequest, TaskType
from langdrill_agent.models import Question
from langdrill_agent.services import QuestionService, SessionService
from langdrill_agent.task_router import TaskRouter


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
    init_db(db_path)

    with transaction(db_path) as conn:
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
