from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db, transaction
from langdrill_agent.providers import ModelProvider
from langdrill_agent.utils import dumps


def test_chat_keeps_session_visible_when_model_request_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "model_error.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
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
                        "provider_id": "mimo",
                        "base_url": "https://api.xiaomimimo.com/anthropic",
                        "model": "mimo-v2.5",
                        "api_format": "anthropic-messages",
                        "has_api_key": True,
                    }
                ),
            ),
        )

    def fail_complete(self: ModelProvider, pack) -> object:
        raise RuntimeError("模型 API 请求失败 (404): upstream not found")

    monkeypatch.setattr(ModelProvider, "complete", fail_complete)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/chat", json={"content": "你好"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert "模型 API 请求失败" in payload["message"]["content"]

    sessions_response = client.get("/api/sessions")
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()["sessions"]
    assert [item["id"] for item in sessions] == [payload["session_id"]]

    with transaction(db_path) as conn:
        messages = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY created_at ASC",
            (payload["session_id"],),
        ).fetchall()

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "你好"
