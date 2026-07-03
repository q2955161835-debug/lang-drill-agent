from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    user_data_dir: Path
    db_path: Path
    log_dir: Path
    user_name: str
    default_provider: str
    default_model: str
    skill_source: Path


LEGACY_DEFAULT_DB_VALUES = {"./data/langdrill_agent.db", "data/langdrill_agent.db"}


def env_file_path() -> Path:
    raw = os.getenv("LANGDRILL_ENV_FILE", "").strip()
    if raw:
        return Path(os.path.expandvars(raw)).expanduser()
    return PROJECT_ROOT / ".env"


def default_user_data_dir() -> Path:
    raw = os.getenv("LANGDRILL_USER_DATA_DIR", "").strip()
    if raw:
        return Path(os.path.expandvars(raw)).expanduser()
    return Path.home() / ".langdrill-agent"


def _is_legacy_default_db(raw_path: str) -> bool:
    normalized = raw_path.strip().replace("\\", "/")
    return normalized in LEGACY_DEFAULT_DB_VALUES


def _resolve_db_path(raw_path: str, user_data_dir: Path) -> Path:
    if not raw_path or _is_legacy_default_db(raw_path):
        return user_data_dir / "data" / "langdrill_agent.db"
    db_path = Path(os.path.expandvars(raw_path)).expanduser()
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return db_path


def load_settings() -> Settings:
    if load_dotenv:
        load_dotenv(env_file_path())

    user_data_dir = default_user_data_dir()
    db_path = _resolve_db_path(os.getenv("LANGDRILL_DB_PATH", ""), user_data_dir)

    skill_source = Path(
        os.getenv(
            "LANGDRILL_SKILL_SOURCE",
            "D:/1Folder/语言学习-lang-drill/语言学习-lang-drill-skill",
        )
    )

    return Settings(
        user_data_dir=user_data_dir,
        db_path=db_path,
        log_dir=user_data_dir / "logs",
        user_name=os.getenv("LANGDRILL_USER_NAME", "boss"),
        default_provider=os.getenv("LANGDRILL_DEFAULT_PROVIDER", "mimo"),
        default_model=os.getenv("LANGDRILL_DEFAULT_MODEL", "mimo-v2.5-pro"),
        skill_source=skill_source,
    )
