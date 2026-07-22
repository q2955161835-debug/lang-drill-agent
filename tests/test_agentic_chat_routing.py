from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import connect, init_db
from langdrill_agent.providers import ModelProvider
from langdrill_agent.runtime.settings import CapabilityRuntimeSettingsService
from langdrill_agent.services import SessionService
from langdrill_agent.utils import dumps, new_id


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "agentic-chat.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "langdrill_agent.api._current_model_provider",
        lambda _conn: ModelProvider("mock", "mock-agentic"),
    )
    init_db(db_path)
    return TestClient(app)


def seed_active_question() -> tuple[str, str]:
    with connect() as conn:
        session_id = SessionService(conn).ensure_session(None, "active question")
        question_id = new_id("q")
        conn.execute(
            """
            INSERT INTO questions
            (id, session_id, sequence, type, prompt, options_json, answer_json,
             explanation, knowledge_tags_json, difficulty, status, source_refs_json)
            VALUES (?, ?, 1, 'multiple_choice', ?, ?, ?, ?, ?, 0.5, 'ready', '[]')
            """,
            (
                question_id,
                session_id,
                "Choose the option that best completes this verified sentence.",
                dumps(["A", "B", "C", "D"]),
                dumps({"correct": "A"}),
                "A is correct for this acceptance fixture.",
                dumps(["fixture"]),
            ),
        )
        return session_id, question_id


def test_agentic_action_starts_run_without_losing_active_question(
    client: TestClient,
) -> None:
    session_id, question_id = seed_active_question()
    with connect() as conn:
        CapabilityRuntimeSettingsService(conn).save(enabled=True)

    response = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "content": "帮我整理这个目录并生成报告",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_run"]["status"] in {"queued", "running"}
    assert payload["active_question"]["id"] == question_id
    run_id = payload["agent_run"]["id"]
    plan = client.get(f"/api/agent-runs/{run_id}/plan")
    assert plan.status_code == 200
    assert plan.json()["steps"][0]["completion_criteria"]
    assert plan.json()["workflow_skill_ids"] == []


def test_action_without_capability_mode_remains_chat(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={"content": "帮我整理这个目录并生成报告"},
    )

    assert response.status_code == 200
    assert response.json().get("agent_run") is None
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0


def test_learning_route_never_starts_agent_run(client: TestClient) -> None:
    with connect() as conn:
        CapabilityRuntimeSettingsService(conn).save(enabled=True)

    response = client.post(
        "/api/chat",
        json={"content": "给我出两道四级阅读题"},
    )

    assert response.status_code == 200
    assert response.json().get("agent_run") is None
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0
