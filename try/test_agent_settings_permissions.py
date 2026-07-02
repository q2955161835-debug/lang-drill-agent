from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.db import init_db
from langdrill_agent.services import AgentSettingsPermissionService, SkillRegistryService


DEFAULT_ENABLED_PERMISSION_IDS = [
    "screenshot_import",
    "learning_database",
    "past_paper_import",
    "web_search_import",
    "profile_exam",
    "context_settings",
]


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


def test_agent_settings_permissions_default_enables_non_sensitive_and_save() -> None:
    conn = _settings_conn()
    service = AgentSettingsPermissionService(conn)

    status = service.status()
    assert status["enabled_feature_ids"] == DEFAULT_ENABLED_PERMISSION_IDS
    assert all(feature["enabled"] is True for feature in status["features"] if feature["default_enabled"])
    assert all(feature["id"] != "skills" for feature in status["features"])
    custom_models = next(feature for feature in status["features"] if feature["id"] == "custom_models")
    assert custom_models["enabled"] is False
    assert custom_models["sensitive"] is True
    assert all(
        feature["enabled"] is False
        for feature in status["features"]
        if feature["sensitive"]
    )
    assert [group["id"] for group in status["groups"]] == ["default_enabled", "sensitive"]

    updated = service.save(["past_paper_import", "unknown", "model_config", "past_paper_import"])
    assert updated["enabled_feature_ids"] == ["past_paper_import", "model_config"]
    assert service.is_enabled("past_paper_import") is True
    assert service.is_enabled("screenshot_import") is False
    assert service.is_enabled("unknown") is False


def test_agent_permissions_legacy_rows_merge_new_defaults_and_drop_skills() -> None:
    conn = _settings_conn()
    conn.execute(
        """
        INSERT INTO app_settings (key, value_json)
        VALUES ('agent.settings.permissions', '{"enabled_feature_ids":["skills"]}')
        """
    )
    service = AgentSettingsPermissionService(conn)

    assert service.status()["enabled_feature_ids"] == DEFAULT_ENABLED_PERMISSION_IDS
    assert service.is_enabled("skills") is False


def test_agent_permissions_current_rows_drop_removed_skills_feature() -> None:
    conn = _settings_conn()
    conn.execute(
        """
        INSERT INTO app_settings (key, value_json)
        VALUES ('agent.settings.permissions', '{"version":2,"enabled_feature_ids":["skills","model_config"]}')
        """
    )
    service = AgentSettingsPermissionService(conn)

    assert service.status()["enabled_feature_ids"] == ["model_config"]
    assert service.is_enabled("skills") is False


def test_skill_registry_selects_no_key_web_search_skill(tmp_path: Path) -> None:
    conn = _settings_conn()
    skill_dir = tmp_path / "multi-search-engine"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: multi-search-engine
description: Build auditable search URLs with no API keys.
---

# Multi Search Engine

This skill does not require API keys.
""",
        encoding="utf-8",
    )

    service = SkillRegistryService([tmp_path], conn=conn)
    status = service.status()

    assert status["installed_count"] == 1
    assert status["builtin_web_search"]["id"] == "builtin-web-search"
    assert status["builtin_web_search"]["enabled"] is True
    assert status["builtin_web_search"]["always_enabled"] is True
    assert status["builtin_web_search"]["locked"] is True
    assert status["builtin_web_search"]["permission_enabled"] is True
    assert status["builtin_web_search"]["requires_api_key"] is False
    assert status["builtin_web_search"]["requires_token"] is False
    assert status["web_search_skill"]["id"] == "multi-search-engine"
    assert status["web_search_skill"]["installed"] is True
    assert status["web_search_skill"]["enabled"] is False
    assert status["web_search_skill"]["requires_api_key"] is False
    assert "multi-search-engine" in status["no_key_skill_ids"]

    enabled = service.save_enabled("multi-search-engine", True)
    assert enabled["enabled_skill_ids"] == ["multi-search-engine"]
    assert enabled["builtin_web_search"]["enabled"] is True
    assert enabled["web_search_skill"]["enabled"] is True

    disabled = service.save_enabled("multi-search-engine", False)
    assert disabled["enabled_skill_ids"] == []
    assert disabled["builtin_web_search"]["enabled"] is True

    AgentSettingsPermissionService(conn).save([])
    permission_blocked = service.status()
    assert permission_blocked["builtin_web_search"]["enabled"] is True
    assert permission_blocked["builtin_web_search"]["always_enabled"] is True
    assert permission_blocked["builtin_web_search"]["permission_enabled"] is False
    assert permission_blocked["web_search_skill"]["enabled"] is False


def test_agent_permissions_api_round_trip(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "permissions.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)
    client = TestClient(_api_app())

    default_response = client.get("/api/settings/agent-permissions")
    assert default_response.status_code == 200
    assert default_response.json()["agent_permissions"]["enabled_feature_ids"] == DEFAULT_ENABLED_PERMISSION_IDS

    save_response = client.post(
        "/api/settings/agent-permissions",
        json={"enabled_feature_ids": ["past_paper_import", "context_settings"]},
    )
    assert save_response.status_code == 200
    assert save_response.json()["agent_permissions"]["enabled_feature_ids"] == ["past_paper_import", "context_settings"]


def test_skills_status_api_reports_recommended_no_key_skill(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "skills-api.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)
    client = TestClient(_api_app())

    response = client.get("/api/skills")

    assert response.status_code == 200
    status = response.json()["skills_status"]
    assert status["builtin_web_search"]["id"] == "builtin-web-search"
    assert status["builtin_web_search"]["enabled"] is True
    assert status["builtin_web_search"]["always_enabled"] is True
    assert status["builtin_web_search"]["locked"] is True
    assert status["builtin_web_search"]["permission_enabled"] is True
    assert status["builtin_web_search"]["requires_api_key"] is False
    assert status["builtin_web_search"]["requires_token"] is False
    assert status["web_search_skill"]["id"] == "multi-search-engine"
    assert status["web_search_skill"]["requires_api_key"] is False
    assert status["web_search_skill"]["requires_token"] is False
    assert status["web_search_skill"]["enabled"] is False


def test_skill_toggle_api_saves_enabled_state(tmp_path: Path, monkeypatch) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "multi-search-engine"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: multi-search-engine\ndescription: No API keys.\n---\nThis skill does not require API keys.\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "skill-toggle.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_SKILLS_ROOTS", str(skills_root))
    init_db(db_path)
    client = TestClient(_api_app())

    enabled = client.post("/api/skills/enabled", json={"skill_id": "multi-search-engine", "enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["skills_status"]["enabled_skill_ids"] == ["multi-search-engine"]
    assert enabled.json()["skills_status"]["builtin_web_search"]["enabled"] is True

    disabled = client.post("/api/skills/enabled", json={"skill_id": "multi-search-engine", "enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["skills_status"]["enabled_skill_ids"] == []
    assert disabled.json()["skills_status"]["builtin_web_search"]["enabled"] is True


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
    client.post("/api/settings/agent-permissions", json={"enabled_feature_ids": []})
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


def test_custom_model_settings_action_requires_permission(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "custom-model-permission.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    client = TestClient(_api_app())
    client.post("/api/settings/agent-permissions", json={"enabled_feature_ids": []})
    content = "请添加自定义模型 model: mimo-v2.5-ultra，显示名称：MiMo Ultra，上下文 100万，支持图片"

    blocked = client.post("/api/chat", json={"content": content})
    assert blocked.status_code == 200
    assert "还没有授权" in blocked.json()["message"]["content"]
    assert "settings_action" not in blocked.json()["message"]["payload"]

    client.post("/api/settings/agent-permissions", json={"enabled_feature_ids": ["custom_models"]})
    allowed = client.post("/api/chat", json={"content": content, "force_new_session": True})

    assert allowed.status_code == 200
    payload = allowed.json()["message"]["payload"]
    action = payload["settings_action"]
    assert action["type"] == "custom_model_draft"
    assert action["feature_id"] == "custom_models"
    assert action["confirmation_required"] is True
    assert action["draft"]["model"] == "mimo-v2.5-ultra"
    assert action["draft"]["label"] == "MiMo Ultra"
    assert action["draft"]["context_tokens"] == 1000000
    assert action["draft"]["vision"] is True


def test_screenshot_import_permission_can_block_inline_database_write(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "screenshot-permission.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    client = TestClient(_api_app())
    client.post("/api/settings/agent-permissions", json={"enabled_feature_ids": []})

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
                ]
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "权限已关闭" in payload["message"]["content"]
    assert payload["active_question"] is None


def test_search_import_requires_online_permission(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "search-import-permission.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "papers"))
    init_db(db_path)
    client = TestClient(_api_app())
    client.post("/api/settings/agent-permissions", json={"enabled_feature_ids": []})

    blocked = client.post(
        "/api/past-papers/search-import",
        json={"exam_id": "cet4", "source_website": "https://example.test/cet4"},
    )
    assert blocked.status_code == 403

    client.post("/api/settings/agent-permissions", json={"enabled_feature_ids": ["web_search_import"]})
    allowed = client.post(
        "/api/past-papers/search-import",
        json={"exam_id": "cet4", "source_website": "https://example.test/cet4"},
    )

    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["skill"]["id"] == "multi-search-engine"
    assert payload["selected_paper_ids"][:3] == ["paper_cet4_2025", "paper_cet4_2024", "paper_cet4_2023"]
