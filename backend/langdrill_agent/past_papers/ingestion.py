from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from ..paper_assets import extract_text_from_file, write_paper_v2_assets
from ..runtime.models import AgentRunRecord, RunStatus
from ..runtime.repository import AgentRunRepository
from ..utils import new_id
from .models import PaperDocumentInput, PaperQuestionInput, PaperSourceInput
from .repository import PastPaperRepository
from .sources import DownloadReceipt, PastPaperSourceAdapter


class Downloader(Protocol):
    def download(self, source_url: str, destination: Path) -> DownloadReceipt: ...


@dataclass(frozen=True, slots=True)
class PaperSyncResult:
    run: AgentRunRecord
    source_id: str
    document_id: str
    downloaded: bool


class PastPaperIngestionService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        papers_root: Path,
        downloader: Downloader,
        source_adapter: PastPaperSourceAdapter | None = None,
        extractor: Callable[..., tuple[str, str]] | None = None,
    ) -> None:
        self.conn = conn
        self.papers_root = papers_root
        self.downloader = downloader
        self.source_adapter = source_adapter
        self.extractor = extractor or extract_text_from_file

    def sync(self, exam_id: str, max_documents: int = 3) -> AgentRunRecord:
        if self.source_adapter is None:
            raise RuntimeError("past paper source adapter is not configured")
        run_repo = AgentRunRepository(self.conn)
        run = run_repo.create(
            session_id=None,
            task_type="past_paper_sync",
            goal=f"Sync real past papers for {exam_id}",
            completion_criteria=["catalog_discovered", "documents_downloaded"],
        )
        run_repo.set_status(run.id, RunStatus.running)
        try:
            sources = self.source_adapter.discover(exam_id)
            run_repo.append_event(
                run.id,
                "progress",
                {"stage": "catalog_discovered", "source_count": len(sources)},
            )
            completed = 0
            for source in sources[: max(0, max_documents)]:
                result = self.sync_one(source)
                completed += int(result.run.status == RunStatus.completed)
            run_repo.append_event(
                run.id,
                "progress",
                {"stage": "documents_downloaded", "document_count": completed},
            )
            return run_repo.set_status(run.id, RunStatus.completed)
        except Exception as exc:
            run_repo.append_event(
                run.id,
                "failed",
                {"stage": "sync_failed", "detail": str(exc)[:300]},
            )
            return run_repo.set_status(
                run.id,
                RunStatus.failed,
                error_code="PAST_PAPER_SYNC_FAILED",
            )

    def sync_one(self, source: PaperSourceInput) -> PaperSyncResult:
        paper_repo = PastPaperRepository(self.conn)
        run_repo = AgentRunRepository(self.conn)
        paper_repo.upsert_source(source)
        run = run_repo.create(
            session_id=None,
            task_type="past_paper_import",
            goal=f"Import real past paper {source.id}",
            completion_criteria=["catalogued", "downloaded", "document_ready"],
        )
        run_repo.set_status(run.id, RunStatus.running)

        existing = self._ready_document_for_source(source.id)
        if existing is not None:
            run_repo.append_event(
                run.id,
                "progress",
                {"stage": "document_reused", "document_id": existing["id"]},
            )
            completed_run = run_repo.set_status(run.id, RunStatus.completed)
            return PaperSyncResult(
                run=completed_run,
                source_id=source.id,
                document_id=existing["id"],
                downloaded=False,
            )

        job_id = new_id("paperjob")
        self.conn.execute(
            """
            INSERT INTO past_paper_import_jobs
            (id, source_id, run_id, status, stage)
            VALUES (?, ?, ?, 'running', 'catalogued')
            """,
            (job_id, source.id, run.id),
        )
        run_repo.append_event(run.id, "progress", {"stage": "catalogued", "job_id": job_id})

        suffix = Path(urlparse(source.source_url).path).suffix.lower() or ".bin"
        raw_dir = self.papers_root / source.exam_id / "raw"
        destination = raw_dir / f"{source.id}{suffix}"
        try:
            receipt = self.downloader.download(source.source_url, destination)
            self._update_job(
                job_id,
                status="running",
                stage="downloaded",
                partial_path=str(receipt.path),
                content_hash=receipt.content_hash,
                bytes_downloaded=receipt.bytes_downloaded,
            )
            run_repo.append_event(
                run.id,
                "progress",
                {
                    "stage": "downloaded",
                    "content_hash": receipt.content_hash,
                    "bytes_downloaded": receipt.bytes_downloaded,
                },
            )
            document = paper_repo.find_document_by_source_hash(
                exam_id=source.exam_id,
                source_url=receipt.source_url,
                content_hash=receipt.content_hash,
            )
            downloaded = document is None
            if document is None:
                document = paper_repo.create_document(
                    PaperDocumentInput(
                        source_id=source.id,
                        exam_id=source.exam_id,
                        title=source.title,
                        year=source.year,
                        session=source.session,
                        set_number=source.set_number,
                        source_url=receipt.source_url,
                        raw_path=str(receipt.path),
                        content_hash=receipt.content_hash,
                        status="downloaded",
                    )
                )
            elif Path(document.raw_path) != receipt.path:
                receipt.path.unlink(missing_ok=True)
            markdown_path = self.papers_root / source.exam_id / "parsed" / f"{document.id}.md"
            structured_path = (
                self.papers_root / source.exam_id / "structured" / f"{document.id}.json"
            )
            extracted_text, parser = self.extractor(Path(document.raw_path), language="ch")
            parsed = write_paper_v2_assets(
                extracted_text,
                exam_id=source.exam_id,
                title=source.title,
                year=source.year,
                source_url=receipt.source_url,
                markdown_path=markdown_path,
                structured_path=structured_path,
            )
            paper_repo.replace_questions(
                document.id,
                [
                    PaperQuestionInput(
                        question_number=question.question_number,
                        question_type=question.question_type,
                        prompt=question.prompt,
                        options=question.options,
                        answer=question.answer,
                        explanation=question.explanation,
                        knowledge_tags=question.knowledge_tags,
                        difficulty=question.difficulty,
                        source_page=question.source_page,
                        answer_confidence=question.answer_confidence,
                        verification_status=question.verification_status,
                    )
                    for question in parsed.questions
                ],
            )
            document = paper_repo.update_document_state(
                document.id,
                status="ready",
                markdown_path=str(markdown_path),
                structured_path=str(structured_path),
                parser=parser,
                parser_version="2",
                error_code="",
            )
            self._update_job(job_id, status="completed", stage="document_ready")
            run_repo.append_event(
                run.id,
                "progress",
                {"stage": "document_ready", "document_id": document.id},
            )
            completed_run = run_repo.set_status(run.id, RunStatus.completed)
            return PaperSyncResult(
                run=completed_run,
                source_id=source.id,
                document_id=document.id,
                downloaded=downloaded,
            )
        except Exception as exc:
            self._update_job(
                job_id,
                status="failed",
                stage="failed",
                error_code="PAST_PAPER_IMPORT_FAILED",
            )
            run_repo.append_event(
                run.id,
                "failed",
                {"stage": "failed", "detail": str(exc)[:300]},
            )
            failed_run = run_repo.set_status(
                run.id,
                RunStatus.failed,
                error_code="PAST_PAPER_IMPORT_FAILED",
            )
            raise PastPaperImportError(failed_run, str(exc)) from exc

    def _ready_document_for_source(self, source_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT id, raw_path FROM past_paper_documents
            WHERE source_id=? AND status='ready'
            ORDER BY created_at DESC LIMIT 1
            """,
            (source_id,),
        ).fetchone()

    def _update_job(
        self,
        job_id: str,
        *,
        status: str,
        stage: str,
        partial_path: str | None = None,
        content_hash: str | None = None,
        bytes_downloaded: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE past_paper_import_jobs
            SET status=?, stage=?,
                partial_path=COALESCE(?, partial_path),
                content_hash=COALESCE(?, content_hash),
                bytes_downloaded=COALESCE(?, bytes_downloaded),
                error_code=COALESCE(?, error_code),
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                status,
                stage,
                partial_path,
                content_hash,
                bytes_downloaded,
                error_code,
                job_id,
            ),
        )


class PastPaperImportError(RuntimeError):
    def __init__(self, run: AgentRunRecord, detail: str) -> None:
        super().__init__(detail)
        self.run = run
