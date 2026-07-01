import sqlite3

from fastapi.testclient import TestClient

import langdrill_agent.services as services_module
from langdrill_agent.api import app
from langdrill_agent.services import ModelConfigService


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

    conn = _settings_conn()

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

    conn = _settings_conn()

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


def test_default_model_providers_are_configurable_without_custom_template(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGDRILL_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("LANGDRILL_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)

    providers = ModelConfigService(_settings_conn()).providers()
    provider_ids = [item["id"] for item in providers]

    assert provider_ids[:4] == ["openai", "claude", "deepseek", "mimo"]
    assert [item["label"] for item in providers[:4]] == ["OpenAI GPT", "Claude", "DeepSeek", "Xiaomi MiMo"]
    assert providers[-1]["label"] == "Mock Provider"
    assert all("（" not in item["label"] and "）" not in item["label"] for item in providers)
    assert "custom" not in provider_ids
    assert all("api_format" in item for item in providers)
    assert all("enabled" in item for item in providers)


def test_custom_provider_label_uses_raw_name_without_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)
    service = ModelConfigService(_settings_conn())

    created = service.add_custom_provider("MyProvider", "https://example.test/v1", "my-model")

    custom_provider = next(item for item in service.providers() if item["id"].startswith("custom_"))
    assert created["id"] == custom_provider["id"]
    assert created["model"] == "my-model"
    assert created["model_options"][0]["id"] == "my-model"
    assert created["model_options"][0]["label"] == "my-model"
    assert custom_provider["label"] == "MyProvider"
    assert custom_provider["base_url"] == "https://example.test/v1"
    assert "（" not in custom_provider["label"]


def test_add_custom_provider_api_returns_provider_and_refreshed_list(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path / "user"))
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(tmp_path / "user" / "data" / "langdrill_agent.db"))
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/api/config/providers/custom",
        json={
            "name": "ApiProvider",
            "base_url": "https://api.example.test/v1",
            "default_model": "api-model",
        },
    )

    assert response.status_code == 200
    data = response.json()
    provider = data["provider"]
    providers = data["providers"]
    assert provider["label"] == "ApiProvider"
    assert provider["base_url"] == "https://api.example.test/v1"
    assert provider["model"] == "api-model"
    assert any(item["id"] == provider["id"] for item in providers)


def test_default_model_config_api_saves_selected_model(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path / "user"))
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(tmp_path / "user" / "data" / "langdrill_agent.db"))
    monkeypatch.delenv("LANGDRILL_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("LANGDRILL_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY_DEEPSEEK", raising=False)
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/api/model-config/default",
        json={
            "provider_id": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "api_key": "deepseek-key",
            "thinking_level": "off",
            "thinking_level_options": [
                {"id": "off", "label": "关闭", "api_value": ""},
                {"id": "max", "label": "最高", "api_value": "max"},
            ],
            "api_format": "openai-chat-completions",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["model_config"]["provider_id"] == "deepseek"
    assert data["model_config"]["model"] == "deepseek-chat"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LANGDRILL_DEFAULT_PROVIDER=deepseek" in env_text
    assert "LANGDRILL_DEFAULT_MODEL=deepseek-chat" in env_text
    assert "LANGDRILL_PROVIDER_API_KEY_DEEPSEEK=deepseek-key" in env_text


def test_provider_visibility_requires_configured_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY_OPENAI", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY_DEEPSEEK", raising=False)

    env_path = tmp_path / ".env"
    env_path.write_text(
        "LANGDRILL_DEFAULT_PROVIDER=openai\n"
        "LANGDRILL_DEFAULT_MODEL=gpt-5.5\n"
        "LANGDRILL_PROVIDER_BASE_URL=https://api.openai.com/v1\n"
        "LANGDRILL_PROVIDER_API_KEY_DEEPSEEK=deepseek-key\n",
        encoding="utf-8",
    )

    providers = ModelConfigService(_settings_conn()).providers()
    by_id = {item["id"]: item for item in providers}

    assert by_id["openai"]["has_api_key"] is False
    assert by_id["openai"]["visible_in_picker"] is False
    assert by_id["deepseek"]["has_api_key"] is True
    assert by_id["deepseek"]["visible_in_picker"] is True


def test_api_key_paste_label_is_cleaned_from_env(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("LANGDRILL_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("LANGDRILL_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY_DEEPSEEK", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY_MIMO", raising=False)

    env_path = tmp_path / ".env"
    env_path.write_text(
        "LANGDRILL_DEFAULT_PROVIDER=mimo\n"
        "LANGDRILL_DEFAULT_MODEL=mimo-v2.5\n"
        "LANGDRILL_PROVIDER_BASE_URL=https://api.xiaomimimo.com/anthropic\n"
        "LANGDRILL_PROVIDER_API_KEY=Bearer：generic-key\n"
        "LANGDRILL_PROVIDER_API_KEY_MIMO=apikey：mimo-key\n",
        encoding="utf-8",
    )

    service = ModelConfigService(_settings_conn())
    config = service.current_with_secret()
    providers = {item["id"]: item for item in service.providers()}

    assert config["api_key"] == "mimo-key"
    assert providers["mimo"]["has_api_key"] is True


def test_saving_api_key_strips_paste_label(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY_MIMO", raising=False)

    service = ModelConfigService(_settings_conn())
    service.save(
        "mimo",
        "https://api.xiaomimimo.com/anthropic",
        "mimo-v2.5",
        "apikey：mimo-key",
        thinking_level="enabled",
    )

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LANGDRILL_PROVIDER_API_KEY=mimo-key" in env_text
    assert "LANGDRILL_PROVIDER_API_KEY_MIMO=mimo-key" in env_text
    assert "apikey：" not in env_text


def test_env_model_config_overrides_stale_database_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("LANGDRILL_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("LANGDRILL_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)

    env_path = tmp_path / ".env"
    env_path.write_text(
        "LANGDRILL_DEFAULT_PROVIDER=mimo\n"
        "LANGDRILL_DEFAULT_MODEL=mimo-v2.5\n"
        "LANGDRILL_PROVIDER_BASE_URL=https://api.xiaomimimo.com/anthropic\n"
        "LANGDRILL_PROVIDER_API_KEY_MIMO=mimo-key\n",
        encoding="utf-8",
    )
    conn = _settings_conn()
    conn.execute(
        "INSERT INTO app_settings (key, value_json) VALUES ('model.default', ?)",
        (
            '{"provider_id":"mimo","base_url":"https://api.xiaomimimo.com/v1",'
            '"model":"mimo-v2.5","thinking_level":"enabled","api_format":"anthropic-messages"}',
        ),
    )
    conn.execute(
        "INSERT INTO app_settings (key, value_json) VALUES ('model.provider_overrides', ?)",
        (
            '{"mimo":{"base_url":"https://api.xiaomimimo.com/v1","api_format":"anthropic-messages",'
            '"model_reasoning_overrides":{"mimo-v2.5":{"default_level":"enabled",'
            '"parameter":"anthropic_thinking_switch","levels":['
            '{"id":"off","label":"밑균","api_value":""},'
            '{"id":"enabled","label":"역폘","api_value":"enabled"}]}}}}',
        ),
    )

    service = ModelConfigService(conn)
    config = service.current()
    providers = {item["id"]: item for item in service.providers()}

    assert config["base_url"] == "https://api.xiaomimimo.com/anthropic"
    assert providers["mimo"]["base_url"] == "https://api.xiaomimimo.com/anthropic"
    assert config["thinking_level_options"] == [
        {"id": "off", "label": "关闭", "api_value": ""},
        {"id": "enabled", "label": "开启", "api_value": "enabled"},
    ]


def test_thinking_options_follow_selected_model_native_levels(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGDRILL_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("LANGDRILL_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)

    service = ModelConfigService(_settings_conn())

    deepseek_config = service.save(
        "deepseek",
        "https://api.deepseek.com",
        "deepseek-v4-pro",
        thinking_level="max",
    )
    mimo_config = service.save(
        "mimo",
        "https://api.xiaomimimo.com/anthropic",
        "mimo-v2.5-pro",
        thinking_level="enabled",
    )
    openai_config = service.save(
        "openai",
        "https://api.openai.com/v1",
        "gpt-5.5",
        thinking_level="xhigh",
    )

    assert deepseek_config["thinking_level"] == "max"
    assert [item["id"] for item in deepseek_config["thinking_level_options"]] == ["off", "high", "max"]
    assert mimo_config["thinking_level"] == "enabled"
    assert [item["id"] for item in mimo_config["thinking_level_options"]] == ["off", "enabled"]
    assert openai_config["thinking_level"] == "xhigh"
    assert [item["id"] for item in openai_config["thinking_level_options"]] == [
        "auto",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
    ]


def test_custom_reasoning_level_is_saved_for_current_model(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "PROJECT_ROOT", tmp_path)
    service = ModelConfigService(_settings_conn())

    config = service.save(
        "openai",
        "https://api.openai.com/v1",
        "gpt-5.5",
        thinking_level="extreme",
        thinking_level_options=[
            {"id": "auto", "label": "自动", "api_value": ""},
            {"id": "extreme", "label": "极限", "api_value": "xhigh"},
        ],
    )

    assert config["thinking_level"] == "extreme"
    assert config["thinking_level_options"][-1] == {"id": "extreme", "label": "极限", "api_value": "xhigh"}
