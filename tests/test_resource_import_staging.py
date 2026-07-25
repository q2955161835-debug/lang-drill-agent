from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.resource_imports.repository import ResourceImportRepository


def test_staging_record_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "staging.db"
    init_db(db_path)

    with connect(db_path) as db_conn:
        repo = ResourceImportRepository(db_conn)
        record = repo.create(
            target="knowledge",
            filename="notes.md",
            mime_type="text/markdown",
            size_bytes=12,
            staged_path=str(tmp_path / "notes.md"),
        )

        assert repo.get(record.id).status == "staged"
        assert repo.get(record.id).expires_at


def test_expired_records_are_listed(tmp_path: Path) -> None:
    db_path = tmp_path / "staging.db"
    init_db(db_path)

    with connect(db_path) as db_conn:
        repo = ResourceImportRepository(db_conn)
        record = repo.create(
            target="past_paper",
            filename="paper.pdf",
            mime_type="application/pdf",
            size_bytes=12,
            staged_path=str(tmp_path / "paper.pdf"),
        )
        db_conn.execute(
            "UPDATE resource_import_staging SET expires_at='2000-01-01T00:00:00' WHERE id=?",
            (record.id,),
        )

        assert [item.id for item in repo.list_expired()] == [record.id]


def test_staging_record_can_be_updated_and_deleted(tmp_path: Path) -> None:
    db_path = tmp_path / "staging.db"
    init_db(db_path)

    with connect(db_path) as db_conn:
        repo = ResourceImportRepository(db_conn)
        record = repo.create(
            target="knowledge",
            filename="notes.md",
            mime_type="text/markdown",
            size_bytes=12,
            staged_path=str(tmp_path / "notes.md"),
        )

        updated = repo.update(
            record.id,
            status="preview_ready",
            parser="markdown",
        )
        repo.delete(record.id)

        assert updated.status == "preview_ready"
        assert updated.parser == "markdown"
        try:
            repo.get(record.id)
        except KeyError:
            pass
        else:
            raise AssertionError("deleted staging record should not be retrievable")
