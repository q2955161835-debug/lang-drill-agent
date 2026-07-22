from pathlib import Path

from langdrill_agent.db import apply_migrations, connect, init_db, iter_migration_files


def test_init_db_records_all_migrations(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"

    init_db(db_path)

    with connect(db_path) as conn:
        versions = [
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]

    assert versions == [path.stem for path in iter_migration_files()]


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"

    init_db(db_path)

    with connect(db_path) as conn:
        assert apply_migrations(conn) == []
