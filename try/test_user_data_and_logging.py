from __future__ import annotations

import importlib
import logging
from pathlib import Path


def test_default_settings_use_home_dot_directory(tmp_path: Path, monkeypatch) -> None:
    import langdrill_agent.config as config_module

    project_root = tmp_path / "project"
    home_dir = tmp_path / "home"
    project_root.mkdir()
    home_dir.mkdir()
    monkeypatch.setattr(config_module, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("LANGDRILL_USER_DATA_DIR", raising=False)
    monkeypatch.delenv("LANGDRILL_DB_PATH", raising=False)

    settings = config_module.load_settings()

    assert settings.user_data_dir == home_dir / ".langdrill-agent"
    assert settings.db_path == home_dir / ".langdrill-agent" / "data" / "langdrill_agent.db"
    assert settings.log_dir == home_dir / ".langdrill-agent" / "logs"


def test_legacy_project_db_is_not_copied_without_opt_in(tmp_path: Path, monkeypatch) -> None:
    import langdrill_agent.config as config_module
    import langdrill_agent.db as db_module

    project_root = tmp_path / "project"
    home_dir = tmp_path / "home"
    legacy_db = project_root / "data" / "langdrill_agent.db"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_bytes(b"legacy-db")
    home_dir.mkdir()
    monkeypatch.setattr(config_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(db_module, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("LANGDRILL_USER_DATA_DIR", raising=False)
    monkeypatch.setenv("LANGDRILL_DB_PATH", "./data/langdrill_agent.db")
    monkeypatch.delenv("LANGDRILL_MIGRATE_LEGACY_DB", raising=False)

    target = db_module.prepare_user_database_path()

    assert target == home_dir / ".langdrill-agent" / "data" / "langdrill_agent.db"
    assert not target.exists()
    assert legacy_db.exists()


def test_legacy_project_db_is_copied_when_opted_in(tmp_path: Path, monkeypatch) -> None:
    import langdrill_agent.config as config_module
    import langdrill_agent.db as db_module

    project_root = tmp_path / "project"
    home_dir = tmp_path / "home"
    legacy_db = project_root / "data" / "langdrill_agent.db"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_bytes(b"legacy-db")
    home_dir.mkdir()
    monkeypatch.setattr(config_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(db_module, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("LANGDRILL_USER_DATA_DIR", raising=False)
    monkeypatch.setenv("LANGDRILL_DB_PATH", "./data/langdrill_agent.db")
    monkeypatch.setenv("LANGDRILL_MIGRATE_LEGACY_DB", "1")

    target = db_module.prepare_user_database_path()

    assert target == home_dir / ".langdrill-agent" / "data" / "langdrill_agent.db"
    assert target.read_bytes() == b"legacy-db"
    assert legacy_db.exists()


def test_configured_logging_writes_to_user_log_dir(tmp_path: Path, monkeypatch) -> None:
    import langdrill_agent.config as config_module

    project_root = tmp_path / "project"
    home_dir = tmp_path / "home"
    project_root.mkdir()
    home_dir.mkdir()
    monkeypatch.setattr(config_module, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("LANGDRILL_USER_DATA_DIR", raising=False)
    monkeypatch.delenv("LANGDRILL_DB_PATH", raising=False)
    logging_module = importlib.import_module("langdrill_agent.logging_config")

    result = logging_module.configure_logging(force=True)
    logger = logging.getLogger("langdrill_agent.test")
    logger.info("smoke-log-entry")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert result["log_file"] == home_dir / ".langdrill-agent" / "logs" / "langdrill-agent.log"
    assert "smoke-log-entry" in result["log_file"].read_text(encoding="utf-8")
