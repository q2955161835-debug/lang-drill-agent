from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db, transaction
from langdrill_agent.services import SessionService
from langdrill_agent.utils import dumps


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
                        "api_format": "mock",
                        "has_api_key": False,
                    }
                ),
            ),
        )


def test_main_chat_vocabulary_screenshot_reuses_import_workflow(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "inline_screenshot.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    _use_mock_provider(db_path)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={
            "content": "\n".join(
                [
                    "collision",
                    "n. 碰撞；冲突",
                    "snowstorm",
                    "n. 暴风雪",
                    "cultivate",
                    "v. 培养；耕作",
                    "evident",
                    "adj. 明显的",
                ]
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["active_question"]["sequence"] == 1
    assert payload["daily_panel"]["knowledge_total"] >= 4
    assert "截图" in payload["message"]["content"] or "先生成并入库" in payload["message"]["content"]

    with transaction(db_path) as conn:
        session = conn.execute(
            "SELECT title FROM study_sessions WHERE id=?",
            (payload["session_id"],),
        ).fetchone()
        messages = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY created_at ASC",
            (payload["session_id"],),
        ).fetchall()
        questions = conn.execute(
            "SELECT COUNT(*) AS count FROM questions WHERE session_id=?",
            (payload["session_id"],),
        ).fetchone()

    assert session["title"].startswith("截图词表练习")
    assert messages[0]["role"] == "user"
    assert messages[0]["content"].startswith("截图导入文本")
    assert questions["count"] >= 4


def test_context_settings_and_manual_compression(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "context.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)
    with transaction(db_path) as conn:
        session_id = SessionService(conn).ensure_session(None, "context test", force_new=True)
        for index in range(8):
            SessionService(conn).add_message(
                session_id,
                "user" if index % 2 == 0 else "assistant",
                f"第 {index} 条上下文消息，包含学习目标、错误原因和复习建议。",
            )

    client = TestClient(app)
    settings_response = client.post(
        "/api/context/settings",
        json={"max_tokens": 123456, "session_id": session_id},
    )
    assert settings_response.status_code == 200
    settings_payload = settings_response.json()
    assert settings_payload["settings"]["max_tokens"] == 123456
    assert settings_payload["token_usage"]["context_limit"] == 123456

    compress_response = client.post("/api/context/compress", json={"session_id": session_id})
    assert compress_response.status_code == 200
    compress_payload = compress_response.json()
    assert compress_payload["compressed_tokens"] > 0
    assert compress_payload["token_usage"]["compressed_context_tokens"] > 0
    assert compress_payload["method"] in {"extractive_fallback", "llmlingua"}

    with transaction(db_path) as conn:
        row = conn.execute("SELECT summary FROM study_sessions WHERE id=?", (session_id,)).fetchone()

    assert row["summary"]


def test_chat_response_reports_current_session_context(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "chat_context.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    _use_mock_provider(db_path)

    client = TestClient(app)
    response = client.post("/api/chat", json={"content": "你好", "force_new_session": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["token_usage"]["context_messages"] == 2
    assert payload["token_usage"]["estimated_current_context"] > 0
