from __future__ import annotations

import sqlite3
from pathlib import Path

from langdrill_agent.config import env_file_path, load_settings
from langdrill_agent.services import ModelConfigService


def test_langdrill_env_file_overrides_project_env(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / "desktop.env"
    user_data = tmp_path / "desktop-user-data"
    db_path = user_data / "data" / "langdrill_agent.db"
    env_path.write_text(
        "\n".join(
            [
                f"LANGDRILL_USER_DATA_DIR={user_data.as_posix()}",
                f"LANGDRILL_DB_PATH={db_path.as_posix()}",
                "LANGDRILL_DEFAULT_PROVIDER=mock",
                "LANGDRILL_DEFAULT_MODEL=mock-tutor-v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("LANGDRILL_ENV_FILE", str(env_path))
    monkeypatch.delenv("LANGDRILL_USER_DATA_DIR", raising=False)
    monkeypatch.delenv("LANGDRILL_DB_PATH", raising=False)
    monkeypatch.delenv("LANGDRILL_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("LANGDRILL_DEFAULT_MODEL", raising=False)

    settings = load_settings()

    assert env_file_path() == env_path
    assert settings.user_data_dir == user_data
    assert settings.db_path == db_path
    assert settings.default_provider == "mock"
    assert settings.default_model == "mock-tutor-v1"


def test_model_config_service_writes_to_langdrill_env_file(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / "desktop.env"
    project_env = tmp_path / "project.env"
    project_env.write_text("LANGDRILL_DEFAULT_PROVIDER=project\n", encoding="utf-8")
    monkeypatch.setenv("LANGDRILL_ENV_FILE", str(env_path))
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", "")
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "")
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", "")

    conn = sqlite3.connect(":memory:")
    service = ModelConfigService(conn)
    service._write_env(
        {
            "LANGDRILL_USER_DATA_DIR": (tmp_path / "data").as_posix(),
            "LANGDRILL_DEFAULT_PROVIDER": "mimo",
            "LANGDRILL_PAPER_ROOT": (tmp_path / "papers").as_posix(),
        }
    )

    written = env_path.read_text(encoding="utf-8")
    assert "LANGDRILL_DEFAULT_PROVIDER=mimo" in written
    assert "LANGDRILL_PAPER_ROOT=" in written
    assert "LANGDRILL_USER_DATA_DIR=" in written
    assert "LANGDRILL_DEFAULT_PROVIDER=project" in project_env.read_text(encoding="utf-8")
