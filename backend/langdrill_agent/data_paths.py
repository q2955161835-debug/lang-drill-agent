from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, env_file_path, load_settings
from .db import init_db, transaction
from .paper_assets import BUILTIN_PAPER_EXAM_IDS
from .services import PastPaperService, SourceService
from .utils import dumps


def _data_env_file_path() -> Path:
    if os.getenv("LANGDRILL_ENV_FILE", "").strip():
        return env_file_path()
    return PROJECT_ROOT / ".env"


class DataPathService:
    DB_FILENAME = "langdrill_agent.db"

    def status(self) -> dict[str, Any]:
        settings = load_settings()
        db_path = settings.db_path
        return {
            "user_data_dir": str(settings.user_data_dir),
            "question_database_dir": str(db_path.parent),
            "db_path": str(db_path),
            "log_dir": str(settings.log_dir),
            "project_data_dir": str(PROJECT_ROOT / "data"),
            "test_data_dir": str(PROJECT_ROOT / "测试数据"),
            "db_exists": db_path.exists(),
            "db_size": db_path.stat().st_size if db_path.exists() else 0,
            "counts": self._database_counts(db_path),
        }

    def configure_question_database_folder(
        self,
        folder: str,
        *,
        migrate: bool = True,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        target_root = self._resolve_folder(folder)
        target_db = target_root / "data" / self.DB_FILENAME
        target_log_dir = target_root / "logs"
        settings = load_settings()
        source_db = settings.db_path

        same_database = self._same_path(source_db, target_db)
        target_db.parent.mkdir(parents=True, exist_ok=True)
        target_log_dir.mkdir(parents=True, exist_ok=True)

        if same_database and not target_db.exists():
            self._initialize_default_database(target_db)
        elif not same_database:
            if target_db.exists() and not overwrite:
                raise ValueError(f"目标数据库已存在：{target_db}")
            if migrate and source_db.exists():
                self._backup_sqlite_database(source_db, target_db, overwrite=overwrite)
            else:
                self._initialize_default_database(target_db)
            self._ensure_default_reference_data(target_db)

        self._write_env(
            {
                "LANGDRILL_USER_DATA_DIR": self._display_path(target_root),
                "LANGDRILL_DB_PATH": self._display_path(target_db),
            }
        )
        os.environ["LANGDRILL_USER_DATA_DIR"] = self._display_path(target_root)
        os.environ["LANGDRILL_DB_PATH"] = self._display_path(target_db)

        status = self.status()
        status.update(
            {
                "previous_db_path": str(source_db),
                "migrated": bool(migrate and source_db.exists() and not same_database),
                "message": "题目数据库目录已更新。",
            }
        )
        return status

    def choose_question_database_folder(
        self,
        *,
        initial_folder: str = "",
        title: str = "选择题目数据库文件夹",
    ) -> dict[str, Any]:
        initial = self._initial_dialog_folder(initial_folder)
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as exc:
            return {
                "selected": False,
                "folder": "",
                "message": f"无法打开本机文件夹选择器：{exc}",
            }

        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title=title or "选择题目数据库文件夹", initialdir=str(initial))
        except Exception as exc:
            return {
                "selected": False,
                "folder": "",
                "message": f"无法打开本机文件夹选择器：{exc}",
            }
        finally:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass

        if not selected:
            return {"selected": False, "folder": "", "message": "未选择文件夹。"}
        folder = Path(selected).resolve()
        return {
            "selected": True,
            "folder": self._display_path(folder),
            "message": "已选择题目数据库文件夹，请确认迁移方式后保存。",
        }

    def _resolve_folder(self, raw_folder: str) -> Path:
        clean = (raw_folder or "").strip().strip('"')
        if not clean:
            raise ValueError("请填写题目数据库文件夹。")
        folder = Path(os.path.expandvars(clean)).expanduser()
        if not folder.is_absolute():
            folder = PROJECT_ROOT / folder
        if folder.exists() and not folder.is_dir():
            raise ValueError("题目数据库位置必须是文件夹。")
        return folder.resolve()

    def _initial_dialog_folder(self, raw_folder: str) -> Path:
        clean = (raw_folder or "").strip().strip('"')
        if clean:
            folder = Path(os.path.expandvars(clean)).expanduser()
            if not folder.is_absolute():
                folder = PROJECT_ROOT / folder
            if folder.exists() and folder.is_dir():
                return folder.resolve()
        return load_settings().user_data_dir

    def _initialize_default_database(self, db_path: Path) -> None:
        init_db(db_path)
        self._ensure_default_reference_data(db_path)

    def _ensure_default_reference_data(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            SourceService(conn).seed_common_sources()
            service = PastPaperService(conn)
            for exam_id in BUILTIN_PAPER_EXAM_IDS:
                service.seed_default_papers(exam_id)
                selected = [f"paper_{exam_id}_{year}" for year in PastPaperService.DEFAULT_RECENT_YEARS]
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value_json, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    """,
                    (f"past_papers.selected.{exam_id}", dumps({"paper_ids": selected})),
                )

    def _backup_sqlite_database(self, source_db: Path, target_db: Path, *, overwrite: bool) -> None:
        if target_db.exists() and not overwrite:
            raise ValueError(f"目标数据库已存在：{target_db}")
        if target_db.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = target_db.with_name(f"{target_db.stem}.pre-migration-{stamp}{target_db.suffix}")
            target_db.replace(backup)
        with sqlite3.connect(source_db) as source_conn:
            with sqlite3.connect(target_db) as target_conn:
                source_conn.backup(target_conn)

    def _database_counts(self, db_path: Path) -> dict[str, int]:
        tables = [
            "study_sessions",
            "messages",
            "questions",
            "attempts",
            "knowledge_items",
            "branch_conversations",
            "branch_messages",
            "model_calls",
            "syllabus_sources",
            "exam_assets",
        ]
        counts = {table: 0 for table in tables}
        if not db_path.exists():
            return counts
        try:
            conn = sqlite3.connect(db_path)
            existing = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            for table in tables:
                if table in existing:
                    counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            conn.close()
        except sqlite3.Error:
            return counts
        return counts

    def _write_env(self, updates: dict[str, str]) -> None:
        env_path = _data_env_file_path()
        env_path.parent.mkdir(parents=True, exist_ok=True)
        values: dict[str, str] = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if not line or line.lstrip().startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        values.update(updates)
        ordered_keys = [
            "LANGDRILL_USER_DATA_DIR",
            "LANGDRILL_DB_PATH",
            "LANGDRILL_MIGRATE_LEGACY_DB",
            "LANGDRILL_LOG_LEVEL",
            "LANGDRILL_USER_NAME",
            "LANGDRILL_ENABLE_LLMLINGUA",
            "LANGDRILL_DEFAULT_PROVIDER",
            "LANGDRILL_DEFAULT_MODEL",
            "LANGDRILL_PROVIDER_BASE_URL",
            "LANGDRILL_PROVIDER_API_KEY",
            "LANGDRILL_PROVIDER_API_KEY_OPENAI",
            "LANGDRILL_PROVIDER_API_KEY_CLAUDE",
            "LANGDRILL_PROVIDER_API_KEY_DEEPSEEK",
            "LANGDRILL_PROVIDER_API_KEY_MIMO",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "LOCAL_LLM_BASE_URL",
            "LOCAL_LLM_API_KEY",
            "LOCAL_LLM_MODEL",
            "LANGDRILL_SKILL_SOURCE",
            "LANGDRILL_PAPER_ROOT",
        ]
        lines = [f"{key}={values[key]}" for key in ordered_keys if key in values]
        lines.extend(f"{key}={values[key]}" for key in sorted(set(values) - set(ordered_keys)))
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _display_path(self, path: Path) -> str:
        return str(path).replace("\\", "/")

    def _same_path(self, first: Path, second: Path) -> bool:
        try:
            return first.resolve() == second.resolve()
        except OSError:
            return first.absolute() == second.absolute()
