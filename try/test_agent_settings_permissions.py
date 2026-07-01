from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.db import init_db
from langdrill_agent.services import AgentSettingsPermissionService


def _api_app():
    return __import__("langdrill_agent.api", fromlist=["app"]).app


def _settings_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE app_settings (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def test_agent_settings_permissions_default_closed_and_save() -> None:
    conn = _settings_conn()
    service = AgentSettingsPermissionService(conn)

    status = service.status()
    assert status["enabled_feature_ids"] == []
    assert all(feature["enabled"] is False for feature in status["features"])

    updated = service.save(["past_paper_import", "unknown", "model_config", "past_paper_import"])
    assert updated["enabled_feature_ids"] == ["past_paper_import", "model_config"]
    assert service.is_enabled("past_paper_import") is True
    assert service.is_enabled("unknown") is False


def test_agent_permissions_api_round_trip(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "permissions.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)
    client = TestClient(_api_app())

    default_response = client.get("/api/settings/agent-permissions")
    assert default_response.status_code == 200
    assert default_response.json()["agent_permissions"]["enabled_feature_ids"] == []

    save_response = client.post(
        "/api/settings/agent-permissions",
        json={"enabled_feature_ids": ["past_paper_import", "context_settings"]},
    )
    assert save_response.status_code == 200
    assert save_response.json()["agent_permissions"]["enabled_feature_ids"] == ["past_paper_import", "context_settings"]


def test_chat_settings_requires_permission_then_returns_action(tmp_path: Path, monkeypatch) -> None:
    import langdrill_agent.api as api_module

    db_path = tmp_path / "chat-permission.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setattr(
        api_module,
        "_past_paper_model_hint",
        lambda *args, **kwargs: {
            "title": "2025 年 6 月英语四级真题",
            "year": 2025,
            "question_types": ["writing", "listening", "reading", "translation"],
            "summary": "含写作、听力、阅读和翻译。",
        },
    )
    init_db(db_path)
    client = TestClient(_api_app())
    content = (
        "请把这份真题导入设置。\n"
        "# 2025 年 6 月英语四级真题\n"
        "Part I Writing\nPart II Listening\nPart III Reading\nPart IV Translation"
    )

    blocked = client.post("/api/chat", json={"content": content})
    assert blocked.status_code == 200
    assert "还没有授权" in blocked.json()["message"]["content"]
    assert "settings_action" not in blocked.json()["message"]["payload"]

    client.post("/api/settings/agent-permissions", json={"enabled_feature_ids": ["past_paper_import"]})
    allowed = client.post("/api/chat", json={"content": content, "force_new_session": True})

    assert allowed.status_code == 200
    payload = allowed.json()["message"]["payload"]
    action = payload["settings_action"]
    assert action["type"] == "past_paper_import_draft"
    assert action["confirmation_required"] is True
    assert action["draft"]["title"] == "2025 年 6 月英语四级真题"
    assert action["draft"]["year"] == 2025
    assert {"writing", "listening", "reading", "translation"} <= set(action["draft"]["question_types"])
