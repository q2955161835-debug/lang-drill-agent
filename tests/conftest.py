from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from langdrill_agent.db import connect, init_db


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Fresh in-memory-ish SQLite connection with migrations applied."""
    db_path = tmp_path / "memory.db"
    init_db(db_path)
    connection = connect(db_path)
    try:
        yield connection
    finally:
        connection.close()
