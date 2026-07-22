from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.creative.repository import CreativeRepository
from langdrill_agent.db import connect, init_db
from langdrill_agent.providers import ModelProvider


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "creative-routing.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "langdrill_agent.api._current_model_provider",
        lambda _conn: ModelProvider("mock", "mock-creative"),
    )
    init_db(db_path)
    return TestClient(app)


def enable_creative_mode(*, runtime_state: str = "ready") -> None:
    with connect() as conn:
        repo = CreativeRepository(conn)
        repo.save_runtime_status(
            state="ready",
            version="0.80.10",
        )
        repo.save_settings(enabled=True, permission_profile="smart_approval")
        if runtime_state != "ready":
            repo.save_runtime_status(
                state=runtime_state,
                version=None,
                error_code="runtime_broken",
            )


def test_creative_action_uses_pi_backend(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_creative_mode()
    dispatched: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "langdrill_agent.api._queue_creative_run",
        lambda run_id, prompt, _provider: dispatched.append((run_id, prompt)),
    )

    response = client.post(
        "/api/chat",
        json={"content": "帮我整理这个目录并生成报告"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_run"]["status"] in {"queued", "running"}
    assert payload["creative_runtime"] == {
        "state": "queued",
        "backend": "pi",
        "repair_required": False,
    }
    assert dispatched == [
        (payload["agent_run"]["id"], "帮我整理这个目录并生成报告")
    ]


def test_learning_request_stays_on_existing_route(client: TestClient) -> None:
    enable_creative_mode()

    response = client.post(
        "/api/chat",
        json={"content": "练习这十个单词，每个词出一道题"},
    )

    assert response.status_code == 200
    assert response.json().get("agent_run") is None
    assert response.json().get("creative_runtime") is None


def test_unavailable_pi_returns_repair_state_without_fake_run(client: TestClient) -> None:
    enable_creative_mode(runtime_state="install_failed")

    response = client.post(
        "/api/chat",
        json={"content": "帮我整理这个目录并生成报告"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("agent_run") is None
    assert payload["creative_runtime"] == {
        "state": "install_failed",
        "backend": "pi",
        "repair_required": True,
        "error_code": "runtime_broken",
    }
    assert "运行时修复" in payload["message"]["content"]
