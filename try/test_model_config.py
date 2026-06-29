import sqlite3

import langdrill_agent.services as services_module
from langdrill_agent.services import ModelConfigService


def test_reset_defaults_preserves_existing_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    monkeypatch.setenv("LANGDRILL_PROVIDER_BASE_URL", "https://stale.example.com")
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)

    env_path = tmp_path / ".env"
    env_path.write_text(
        "LANGDRILL_DEFAULT_PROVIDER=deepseek\n"
        "LANGDRILL_DEFAULT_MODEL=deepseek-chat\n"
        "LANGDRILL_PROVIDER_BASE_URL=https://api.deepseek.com\n"
        "LANGDRILL_PROVIDER_API_KEY=keep-existing-key\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)

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

    config = ModelConfigService(conn).reset_defaults()

    assert config["provider_id"] == "mimo"
    assert config["model"] == "mimo-v2.5-pro"
    env_text = env_path.read_text(encoding="utf-8")
    assert "LANGDRILL_DEFAULT_PROVIDER=mimo" in env_text
    assert "LANGDRILL_PROVIDER_API_KEY=keep-existing-key" in env_text


def test_mock_config_does_not_inherit_real_provider_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    monkeypatch.setenv("LANGDRILL_PROVIDER_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LANGDRILL_PROVIDER_API_KEY", "real-provider-key")
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)

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

    service = ModelConfigService(conn)
    config = service.current()
    secret_config = service.current_with_secret()

    assert config["provider_id"] == "mock"
    assert config["base_url"] == ""
    assert config["model"] == "mock-tutor-v1"
    assert config["thinking_level"] == "auto"
    assert config["thinking_level_options"][0]["id"] == "auto"
    assert config["has_api_key"] is False
    assert secret_config["api_key"] == ""


def test_model_config_saves_thinking_level(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGDRILL_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("LANGDRILL_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)

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

    service = ModelConfigService(conn)
    config = service.save(
        "mimo",
        "https://api.xiaomimimo.com/v1",
        "mimo-v2.5-pro",
        thinking_level="high",
    )

    assert config["thinking_level"] == "high"
    assert {item["id"] for item in config["thinking_level_options"]} == {"auto", "low", "medium", "high"}
