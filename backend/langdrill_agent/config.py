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
    db_path: Path
    user_name: str
    default_provider: str
    default_model: str
    skill_source: Path


def load_settings() -> Settings:
    if load_dotenv:
        load_dotenv(PROJECT_ROOT / ".env")

    db_path = Path(os.getenv("LANGDRILL_DB_PATH", "./data/langdrill_agent.db"))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    skill_source = Path(
        os.getenv(
            "LANGDRILL_SKILL_SOURCE",
            "D:/1Folder/语言学习-lang-drill/语言学习-lang-drill-skill",
        )
    )

    return Settings(
        db_path=db_path,
        user_name=os.getenv("LANGDRILL_USER_NAME", "boss"),
        default_provider=os.getenv("LANGDRILL_DEFAULT_PROVIDER", "mimo"),
        default_model=os.getenv("LANGDRILL_DEFAULT_MODEL", "mimo-v2.5-pro"),
        skill_source=skill_source,
    )
