from datetime import datetime, timedelta
from pathlib import Path

import pytest

from langdrill_agent.db import connect, init_db
from langdrill_agent.resource_imports.models import ResourceImportPreview
from langdrill_agent.resource_imports.repository import ResourceImportRepository
from langdrill_agent.resource_imports.service import (
    ResourceImportError,
    ResourceImportService,
)


def _db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "staging.db"
    init_db(db_path)
    return db_path


def test_staging_record_round_trip(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)

    with connect(db_path) as db_conn:
        repo = ResourceImportRepository(db_conn)
        record = repo.create(
            target="knowledge",
            filename="notes.md",
            mime_type="text/markdown",
            size_bytes=12,
            staged_path=str(tmp_path / "notes.md"),
        )

        stored = repo.update(
            record.id,
            status="preview_ready",
            preview=ResourceImportPreview(
                title="Notes",
                parser="text",
                text_preview="consecutive",
                characters=11,
                chunk_count=1,
            ),
        )

        assert stored.status == "preview_ready"
        assert stored.preview is not None
        assert stored.preview.model_dump() == {
            "title": "Notes",
            "language": "",
            "year": None,
            "parser": "text",
            "text_preview": "consecutive",
            "characters": 11,
            "pages": None,
            "chunk_count": 1,
            "question_count": 0,
            "question_types": [],
            "answer_confidence": 0,
            "warnings": [],
        }


def test_expired_records_are_listed(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)

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


def test_staging_expiry_is_24_hours_after_creation(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)

    with connect(db_path) as db_conn:
        record = ResourceImportRepository(db_conn).create(
            target="knowledge",
            filename="notes.md",
            mime_type="text/markdown",
            size_bytes=12,
            staged_path=str(tmp_path / "notes.md"),
        )

        created_at = datetime.fromisoformat(record.created_at)
        expires_at = datetime.fromisoformat(record.expires_at)
        assert expires_at - created_at == timedelta(hours=24)


def test_staging_record_can_be_updated_and_deleted(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)

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
        with pytest.raises(KeyError, match=record.id):
            repo.get(record.id)


def test_parse_preview_does_not_create_formal_rows(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)

    with connect(db_path) as db_conn:
        service = ResourceImportService(db_conn, user_data_dir=tmp_path)
        record = service.stage_bytes(
            target="knowledge",
            filename="notes.md",
            mime_type="text/markdown",
            data=b"# Notes\nconsecutive",
        )

        previewed = service.parse(record.id, metadata={"language": "en"})

        assert previewed.status == "preview_ready"
        assert previewed.preview is not None
        assert previewed.preview.chunk_count == 1
        assert db_conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0] == 0


def test_rejects_oversized_and_unsupported_files(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)

    with connect(db_path) as db_conn:
        service = ResourceImportService(db_conn, user_data_dir=tmp_path, max_bytes=4)

        with pytest.raises(ResourceImportError, match="RESOURCE_IMPORT_TOO_LARGE"):
            service.stage_bytes(
                target="knowledge",
                filename="notes.md",
                mime_type="text/markdown",
                data=b"12345",
            )
        with pytest.raises(ResourceImportError, match="RESOURCE_IMPORT_TYPE_UNSUPPORTED"):
            service.stage_bytes(
                target="knowledge",
                filename="../bad.exe",
                mime_type="application/octet-stream",
                data=b"x",
            )


def test_cancel_removes_only_its_staging_directory(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)

    with connect(db_path) as db_conn:
        service = ResourceImportService(db_conn, user_data_dir=tmp_path)
        cancelled = service.stage_bytes(
            target="knowledge", filename="cancel.md", mime_type="text/markdown", data=b"one"
        )
        kept = service.stage_bytes(
            target="knowledge", filename="keep.md", mime_type="text/markdown", data=b"two"
        )

        result = service.cancel(cancelled.id)

        assert result.status == "cancelled"
        assert not Path(cancelled.staged_path).parent.exists()
        assert Path(kept.staged_path).exists()


def test_failed_parse_does_not_change_other_staged_record(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)

    def fail_for_bad_file(path: Path, **_: object) -> tuple[str, str]:
        if path.name == "bad.md":
            raise RuntimeError("cannot parse bad file")
        return "# Good\ncontent", "fake"

    with connect(db_path) as db_conn:
        service = ResourceImportService(
            db_conn, user_data_dir=tmp_path, extractor=fail_for_bad_file
        )
        bad = service.stage_bytes(
            target="knowledge", filename="bad.md", mime_type="text/markdown", data=b"bad"
        )
        good = service.stage_bytes(
            target="knowledge", filename="good.md", mime_type="text/markdown", data=b"good"
        )

        failed = service.parse(bad.id, metadata={})
        ready = service.parse(good.id, metadata={})

        assert failed.status == "failed"
        assert failed.error_code == "RESOURCE_IMPORT_PARSE_FAILED"
        assert ready.status == "preview_ready"
