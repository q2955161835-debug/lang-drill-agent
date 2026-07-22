from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import connect, init_db
from langdrill_agent.runtime.models import AgentRunStep
from langdrill_agent.runtime.repository import AgentRunRepository
from langdrill_agent.runtime.settings import CapabilityRuntimeSettingsService


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "agent-runs.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)
    return TestClient(app)


def seed_run(*, status: str = "running", with_event: bool = False) -> str:
    with connect() as conn:
        repo = AgentRunRepository(conn)
        run = repo.create(session_id="s1", task_type="knowledge_index", goal="index file")
        if with_event:
            repo.append_event(run.id, "progress", {"percent": 100})
        repo.set_status(run.id, status)
        return run.id


def test_agent_run_status_and_cancel(client: TestClient) -> None:
    run_id = seed_run()

    status = client.get(f"/api/agent-runs/{run_id}")
    cancelled = client.post(f"/api/agent-runs/{run_id}/cancel")

    assert status.status_code == 200
    assert status.json()["run"]["status"] == "running"
    assert cancelled.status_code == 200
    assert cancelled.json()["run"]["status"] == "cancelled"


def test_missing_run_returns_stable_error(client: TestClient) -> None:
    response = client.get("/api/agent-runs/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "AGENT_RUN_NOT_FOUND",
        "params": {"run_id": "missing"},
    }


def test_pause_resume_cancel_and_plan_lifecycle(client: TestClient) -> None:
    with connect() as conn:
        repo = AgentRunRepository(conn)
        run = repo.create(session_id="s1", task_type="agentic_task", goal="generate report")
        repo.replace_plan(
            run.id,
            [
                AgentRunStep(
                    id="",
                    run_id="",
                    sequence=1,
                    title="Generate report",
                    description="Generate the report safely.",
                    tool_names=["runtime.review"],
                    completion_criteria=["report plan is verified"],
                )
            ],
        )
        repo.set_status(run.id, "running")
        CapabilityRuntimeSettingsService(conn).save(enabled=True)

    paused = client.post(f"/api/agent-runs/{run.id}/pause")
    plan = client.get(f"/api/agent-runs/{run.id}/plan")
    resumed = client.post(f"/api/agent-runs/{run.id}/resume")
    cancelled = client.post(f"/api/agent-runs/{run.id}/cancel")

    assert paused.status_code == 200
    assert paused.json()["run"]["status"] == "paused"
    assert plan.json()["steps"][0]["title"] == "Generate report"
    assert resumed.json()["run"]["status"] == "queued"
    assert cancelled.json()["run"]["status"] == "cancelled"


def test_resume_requires_capability_runtime_to_remain_enabled(client: TestClient) -> None:
    run_id = seed_run(status="paused")

    response = client.post(f"/api/agent-runs/{run_id}/resume")

    assert response.status_code == 409
    assert response.json()["detail"] == "capability runtime is disabled"


def test_agent_run_event_stream_uses_sse_frames(client: TestClient) -> None:
    run_id = seed_run(status="completed", with_event=True)

    response = client.get(f"/api/agent-runs/{run_id}/events?after=0")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    assert 'data: {"percent":100}' in response.text
