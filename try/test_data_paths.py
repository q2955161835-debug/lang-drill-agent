from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def _patch_project(monkeypatch, tmp_path: Path):
    import langdrill_agent.config as config_module
    import langdrill_agent.data_paths as data_paths_module
    import langdrill_agent.db as db_module
    import langdrill_agent.paper_assets as paper_assets_module

    project_root = tmp_path / "project"
    home_dir = tmp_path / "home"
    project_root.mkdir()
    home_dir.mkdir()
    monkeypatch.setattr(config_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(db_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(data_paths_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(paper_assets_module, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("LANGDRILL_USER_DATA_DIR", raising=False)
    monkeypatch.delenv("LANGDRILL_DB_PATH", raising=False)
    monkeypatch.delenv("LANGDRILL_MIGRATE_LEGACY_DB", raising=False)
    return project_root, home_dir


def test_question_database_folder_migrates_current_db(tmp_path: Path, monkeypatch) -> None:
    from langdrill_agent.data_paths import DataPathService
    from langdrill_agent.db import init_db

    project_root, _home_dir = _patch_project(monkeypatch, tmp_path)
    source_db = init_db()
    with sqlite3.connect(source_db) as conn:
        conn.execute(
            """
            INSERT INTO study_sessions (id, title, folder_date, exam_id)
            VALUES ('ses_existing', '旧测试会话', '2026-07-01', 'cet4')
            """
        )
        conn.commit()

    target_root = project_root / "custom-user-data"
    result = DataPathService().configure_question_database_folder(str(target_root), migrate=True)
    target_db = target_root / "data" / "langdrill_agent.db"

    assert Path(result["db_path"]) == target_db
    assert os.environ["LANGDRILL_USER_DATA_DIR"] == str(target_root).replace("\\", "/")
    assert os.environ["LANGDRILL_DB_PATH"] == str(target_db).replace("\\", "/")
    with sqlite3.connect(target_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM syllabus_sources").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM exam_assets").fetchone()[0] == 27
    env_text = (project_root / ".env").read_text(encoding="utf-8")
    assert "LANGDRILL_USER_DATA_DIR=" in env_text
    assert "LANGDRILL_DB_PATH=" in env_text


def test_question_database_folder_can_initialize_empty_db(tmp_path: Path, monkeypatch) -> None:
    from langdrill_agent.data_paths import DataPathService
    from langdrill_agent.db import init_db

    project_root, _home_dir = _patch_project(monkeypatch, tmp_path)
    source_db = init_db()
    with sqlite3.connect(source_db) as conn:
        conn.execute(
            """
            INSERT INTO study_sessions (id, title, folder_date, exam_id)
            VALUES ('ses_existing', '旧测试会话', '2026-07-01', 'cet4')
            """
        )
        conn.commit()

    target_root = project_root / "clean-user-data"
    result = DataPathService().configure_question_database_folder(str(target_root), migrate=False)
    target_db = target_root / "data" / "langdrill_agent.db"

    assert Path(result["db_path"]) == target_db
    with sqlite3.connect(target_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM syllabus_sources").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM exam_assets").fetchone()[0] == 27
