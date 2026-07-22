from pathlib import Path

from langdrill_agent.db import connect, init_db
import pytest

from langdrill_agent.past_papers.ingestion import (
    PastPaperImportError,
    PastPaperIngestionService,
)
from langdrill_agent.past_papers.markdown import parse_paper_markdown
from langdrill_agent.past_papers.models import PaperSourceInput
from langdrill_agent.past_papers.repository import PastPaperRepository
from langdrill_agent.past_papers.sources import DownloadReceipt
from langdrill_agent.runtime.repository import AgentRunRepository


class StubDownloader:
    def __init__(self, content: bytes = b"%PDF-1.7\nreal paper") -> None:
        self.content = content
        self.calls = 0

    def download(self, source_url: str, destination: Path) -> DownloadReceipt:
        self.calls += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.content)
        return DownloadReceipt(
            path=destination,
            source_url=source_url,
            content_hash="sha256:fixed-paper",
            bytes_downloaded=len(self.content),
            mime_type="application/pdf",
        )


def _extractor(_path: Path, **_kwargs) -> tuple[str, str]:
    return (
        "# Reading\n1. What is the main idea?\nA. First\nB. Second\nAnswer: B\n",
        "test-parser",
    )


def _source() -> PaperSourceInput:
    return PaperSourceInput(
        id="cet4-2025-06-1",
        exam_id="cet4",
        title="CET-4 2025 June Set 1",
        source_url="https://source.test/2025-06-set1.pdf",
        year=2025,
        session="june",
        set_number=1,
    )


def test_sync_does_not_redownload_same_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)
    downloader = StubDownloader()

    with connect(db_path) as conn:
        service = PastPaperIngestionService(
            conn,
            papers_root=tmp_path / "library",
            downloader=downloader,
            extractor=_extractor,
        )
        first = service.sync_one(_source())
        second = service.sync_one(_source())

        assert first.document_id == second.document_id
        assert first.downloaded is True
        assert second.downloaded is False
        assert downloader.calls == 1


def test_sync_records_resumable_job_stages(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        service = PastPaperIngestionService(
            conn,
            papers_root=tmp_path / "library",
            downloader=StubDownloader(),
            extractor=_extractor,
        )
        result = service.sync_one(_source())
        events = AgentRunRepository(conn).events_after(result.run.id, 0)
        stages = [event.payload.get("stage") for event in events]

        assert result.run.status == "completed"
        assert stages == ["catalogued", "downloaded", "document_ready"]
        job = conn.execute(
            "SELECT status, stage FROM past_paper_import_jobs WHERE source_id=?",
            (_source().id,),
        ).fetchone()
        assert tuple(job) == ("completed", "document_ready")


def test_retry_reuses_downloaded_file_after_parse_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)
    downloader = StubDownloader()

    def fail_extract(_path: Path, **_kwargs) -> tuple[str, str]:
        raise RuntimeError("parser interrupted")

    with connect(db_path) as conn:
        failing = PastPaperIngestionService(
            conn,
            papers_root=tmp_path / "library",
            downloader=downloader,
            extractor=fail_extract,
        )
        with pytest.raises(PastPaperImportError):
            failing.sync_one(_source())

        resumed = PastPaperIngestionService(
            conn,
            papers_root=tmp_path / "library",
            downloader=downloader,
            extractor=_extractor,
        ).sync_one(_source())

        assert resumed.run.status == "completed"
        assert resumed.downloaded is False
        assert downloader.calls == 1
        assert PastPaperRepository(conn).get_document(resumed.document_id).status == "ready"


def test_sync_writes_reviewable_markdown_and_structured_questions(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        result = PastPaperIngestionService(
            conn,
            papers_root=tmp_path / "library",
            downloader=StubDownloader(),
            extractor=_extractor,
        ).sync_one(_source())
        repo = PastPaperRepository(conn)
        document = repo.get_document(result.document_id)
        questions = repo.list_questions(document.id)

        assert document.status == "ready"
        assert document.parser == "test-parser"
        assert Path(document.markdown_path).is_file()
        assert Path(document.structured_path).is_file()
        assert parse_paper_markdown(Path(document.markdown_path).read_text(encoding="utf-8")).questions
        assert questions[0].answer == {"letter": "B"}
        assert questions[0].verification_status == "unverified"
