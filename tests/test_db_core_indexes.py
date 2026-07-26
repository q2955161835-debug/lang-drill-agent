"""批次 A 回归测试：核心索引、连接 PRAGMA、init_db 一次性守卫。

对应改动：`backend/langdrill_agent/db.py`
- `001_initial.sql` 的 20 张核心表原先没有任何二级索引。
- `connect()` 原先缺 `synchronous` 和 `busy_timeout`。
- `init_db()` 原先被 102 个调用点无条件重跑完整迁移 + 播种周期。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from langdrill_agent import db as dbmod
from langdrill_agent.db import connect, init_db

CORE_INDEXES = {
    "idx_messages_session_created",
    "idx_questions_session_status_sequence",
    "idx_attempts_session_created",
    "idx_attempts_question_session_created",
    "idx_knowledge_items_exam_term_scope",
    "idx_knowledge_items_term",
    "idx_study_sessions_exam_date_status",
    "idx_branch_messages_branch_created",
    "idx_branch_conversations_session",
    "idx_generation_jobs_session",
    "idx_exam_assets_exam_type",
}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}


def test_core_indexes_exist_after_init(tmp_path: Path) -> None:
    db_path = tmp_path / "indexes.db"
    init_db(db_path)

    with connect(db_path) as conn:
        assert CORE_INDEXES <= _index_names(conn)


@pytest.mark.parametrize(
    ("pragma", "expected"),
    [
        ("journal_mode", "wal"),
        ("synchronous", 1),  # NORMAL
        ("busy_timeout", 5000),
        ("foreign_keys", 1),
    ],
)
def test_connection_pragmas(tmp_path: Path, pragma: str, expected: object) -> None:
    db_path = tmp_path / "pragmas.db"
    init_db(db_path)

    with connect(db_path) as conn:
        value = conn.execute(f"PRAGMA {pragma}").fetchone()[0]

    assert (value.lower() if isinstance(value, str) else value) == expected


@pytest.mark.parametrize(
    ("sql", "index_name"),
    [
        (
            "SELECT * FROM questions WHERE session_id='s' AND status='ready' ORDER BY sequence ASC",
            "idx_questions_session_status_sequence",
        ),
        (
            "SELECT * FROM messages WHERE session_id='s' ORDER BY created_at ASC",
            "idx_messages_session_created",
        ),
        (
            "SELECT * FROM attempts WHERE session_id='s' ORDER BY created_at DESC",
            "idx_attempts_session_created",
        ),
        (
            "SELECT id FROM knowledge_items WHERE term='skin' AND exam_id='cet4'"
            " AND source_scope='screenshot_import'",
            "idx_knowledge_items_exam_term_scope",
        ),
        (
            "SELECT * FROM study_sessions WHERE folder_date='2026-07-26' AND exam_id='cet4'"
            " AND status!='deleted'",
            "idx_study_sessions_exam_date_status",
        ),
        (
            "SELECT * FROM branch_messages WHERE branch_id='b' ORDER BY created_at DESC",
            "idx_branch_messages_branch_created",
        ),
    ],
)
def test_hot_queries_use_an_index(tmp_path: Path, sql: str, index_name: str) -> None:
    db_path = tmp_path / "plans.db"
    init_db(db_path)

    with connect(db_path) as conn:
        plan = " ".join(str(row[3]) for row in conn.execute("EXPLAIN QUERY PLAN " + sql))

    assert index_name in plan, plan


def test_session_cascade_delete_does_not_scan_child_tables(tmp_path: Path) -> None:
    """PRAGMA foreign_keys=ON 下删除会话要查 5 张子表，缺索引时每张都是全表扫描。"""
    db_path = tmp_path / "cascade.db"
    init_db(db_path)

    with connect(db_path) as conn:
        plan = " ".join(
            str(row[3])
            for row in conn.execute("EXPLAIN QUERY PLAN DELETE FROM study_sessions WHERE id='s'")
        )

    assert "SCAN" not in plan.upper(), plan


def test_init_db_is_idempotent_per_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "guard.db"
    init_db(db_path)

    calls: list[int] = []
    real_seed = dbmod.seed_prompt_modules
    monkeypatch.setattr(
        dbmod,
        "seed_prompt_modules",
        lambda conn: (calls.append(1), real_seed(conn))[1],
    )

    init_db(db_path)
    init_db(db_path)
    init_db(db_path)

    assert calls == []


def test_init_db_reinitialises_new_path_and_deleted_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real_seed = dbmod.seed_prompt_modules
    monkeypatch.setattr(
        dbmod,
        "seed_prompt_modules",
        lambda conn: (calls.append(1), real_seed(conn))[1],
    )

    db_path = tmp_path / "fresh-path.db"
    init_db(db_path)
    assert len(calls) == 1, "数据目录迁移会传入新路径，必须重新初始化"

    db_path.unlink()
    init_db(db_path)
    assert len(calls) == 2, "数据库文件被删除后必须重新初始化"

    init_db(db_path, force=True)
    assert len(calls) == 3, "force=True 必须强制重跑"


def test_indexes_apply_to_legacy_db_missing_exam_id(tmp_path: Path) -> None:
    """老库回归：study_sessions 缺 exam_id 时，索引仍须建立成功。

    这是索引没有写成 .sql 迁移的原因：`apply_migrations` 跑在 `ensure_schema_columns`
    之前，迁移脚本引用 exam_id 会在这些老库上抛 `no such column: exam_id`。
    """
    db_path = tmp_path / "legacy.db"
    init_db(db_path)

    raw = sqlite3.connect(db_path, isolation_level=None)
    raw.execute("DROP INDEX idx_study_sessions_exam_date_status")
    raw.execute("ALTER TABLE study_sessions DROP COLUMN exam_id")
    columns = {row[1] for row in raw.execute("PRAGMA table_info(study_sessions)")}
    assert "exam_id" not in columns

    # 反证：在补列之前建索引确实会失败。
    with pytest.raises(sqlite3.OperationalError, match="exam_id"):
        raw.execute("CREATE INDEX probe ON study_sessions(folder_date, exam_id, status)")
    raw.close()

    init_db(db_path, force=True)

    with connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(study_sessions)")}
        assert "exam_id" in columns
        assert CORE_INDEXES <= _index_names(conn)
