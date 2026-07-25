from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import load_settings
from ..knowledge.chunking import chunk_markdown
from ..knowledge.ingestion import KnowledgeIngestionService
from ..knowledge.repository import KnowledgeRepository
from ..paper_assets import IMAGE_SUFFIXES, extract_text_from_file, paper_root
from ..past_papers.ingestion import PastPaperIngestionService
from ..past_papers.parser import PaperParseResult, ParsedPaperQuestion, parse_extracted_paper_text
from ..utils import new_id
from .models import ImportTarget, ResourceImportPreview, ResourceImportRecord
from .repository import ResourceImportRepository

ALLOWED_SUFFIXES: set[str] = {".pdf", ".docx", ".txt", ".md", ".markdown", *IMAGE_SUFFIXES}
DEFAULT_MAX_BYTES = 50 * 1024 * 1024

Extractor = Callable[..., tuple[str, str]]


class ResourceImportError(RuntimeError):
    """Staging or preview failure carrying a stable error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ResourceImportService:
    """Validates, stages, parses and cleans up imported resource files.

    Parsing is preview-only: it never writes formal knowledge or past-paper
    rows. Formal writes happen only through domain confirmation callers that
    consume the extracted text produced here.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        user_data_dir: Path | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        extractor: Extractor | None = None,
    ) -> None:
        self.conn = conn
        self.user_data_dir = user_data_dir or load_settings().user_data_dir
        self.max_bytes = max_bytes
        self.extractor = extractor or extract_text_from_file
        self.repository = ResourceImportRepository(conn)

    def stage_bytes(
        self,
        *,
        target: ImportTarget,
        filename: str,
        mime_type: str,
        data: bytes,
    ) -> ResourceImportRecord:
        safe_name = Path(filename.replace("\\", "/")).name
        suffix = Path(safe_name).suffix.lower()
        if not safe_name or suffix not in ALLOWED_SUFFIXES:
            raise ResourceImportError("RESOURCE_IMPORT_TYPE_UNSUPPORTED")
        if not data:
            raise ResourceImportError("RESOURCE_IMPORT_EMPTY")
        if len(data) > self.max_bytes:
            raise ResourceImportError("RESOURCE_IMPORT_TOO_LARGE")

        import_id = new_id("import")
        target_dir = self.user_data_dir / "staging" / "resource-imports" / import_id
        target_dir.mkdir(parents=True, exist_ok=False)
        path = target_dir / safe_name
        path.write_bytes(data)
        return self.repository.create(
            target=target,
            filename=safe_name,
            mime_type=mime_type,
            size_bytes=len(data),
            staged_path=str(path),
            record_id=import_id,
        )

    def parse(
        self,
        import_id: str,
        *,
        metadata: dict[str, object],
    ) -> ResourceImportRecord:
        record = self.repository.get(import_id)
        self.repository.update(
            import_id,
            status="parsing",
            error_code="",
            error_detail="",
        )
        try:
            text, parser = self.extractor(
                Path(record.staged_path),
                language=str(metadata.get("language") or "ch"),
                preferred_parser=str(metadata.get("parser") or "auto"),
            )
            extracted_path = Path(record.staged_path).parent / "extracted.txt"
            extracted_path.write_text(text, encoding="utf-8")

            if record.target == "knowledge":
                chunks = chunk_markdown(text)
                preview = ResourceImportPreview(
                    title=str(metadata.get("title") or Path(record.filename).stem),
                    language=str(metadata.get("language") or ""),
                    parser=parser,
                    text_preview=text[:1200],
                    characters=len(text),
                    chunk_count=len(chunks),
                )
            else:
                parsed = parse_extracted_paper_text(
                    text,
                    exam_id=str(metadata.get("exam_id") or "custom"),
                    title=str(metadata.get("title") or Path(record.filename).stem),
                    year=_optional_year(metadata.get("year")),
                    source_url=str(metadata.get("source_url") or ""),
                )
                preview = ResourceImportPreview(
                    title=parsed.title,
                    year=_optional_year(metadata.get("year")),
                    parser=parser,
                    text_preview=text[:1200],
                    characters=len(text),
                    question_count=len(parsed.questions),
                    question_types=sorted({q.question_type for q in parsed.questions}),
                    answer_confidence=_mean_confidence(parsed.questions),
                    warnings=_paper_warnings(parsed),
                )
            return self.repository.update(
                import_id,
                status="preview_ready",
                parser=parser,
                extracted_path=str(extracted_path),
                preview=preview,
            )
        except Exception as exc:
            return self.repository.update(
                import_id,
                status="failed",
                error_code="RESOURCE_IMPORT_PARSE_FAILED",
                error_detail=str(exc)[:300],
            )

    def cancel(self, import_id: str) -> ResourceImportRecord:
        record = self.repository.get(import_id)
        staging_dir = Path(record.staged_path).parent
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        return self.repository.update(import_id, status="cancelled")

    def confirm(
        self,
        import_id: str,
        *,
        metadata: dict[str, object],
    ) -> dict[str, Any]:
        """Persist a previewed staging record into its formal domain.

        Dispatches to ``KnowledgeIngestionService.import_preparsed`` for
        knowledge targets or ``PastPaperIngestionService.import_local_file``
        for past-paper targets. The staging directory is removed only after
        the domain write succeeds.
        """
        record = self.repository.get(import_id)
        if record.status != "preview_ready" or not record.extracted_path:
            raise ResourceImportError("RESOURCE_IMPORT_PREVIEW_REQUIRED")
        if record.preview is None:
            raise ResourceImportError("RESOURCE_IMPORT_PREVIEW_REQUIRED")

        source = Path(record.staged_path)
        extracted_text = Path(record.extracted_path).read_text(encoding="utf-8")

        if record.target == "knowledge":
            run = KnowledgeIngestionService(self.conn).import_preparsed(
                source,
                extracted_text=extracted_text,
                parser=record.parser,
                title=str(metadata.get("title") or record.preview.title),
                language=str(metadata.get("language") or record.preview.language),
            )
            documents = KnowledgeRepository(self.conn).list_documents()
            if not documents:
                raise ResourceImportError("RESOURCE_IMPORT_CONFIRM_FAILED")
            result: dict[str, Any] = {
                "run": run.model_dump(mode="json"),
                "document": documents[-1].model_dump(mode="json"),
            }
        else:
            document = PastPaperIngestionService(
                self.conn,
                papers_root=paper_root(),
            ).import_local_file(
                source,
                extracted_text=extracted_text,
                parser=record.parser,
                exam_id=str(metadata.get("exam_id") or "custom"),
                title=str(metadata.get("title") or record.preview.title),
                year=_optional_year(metadata.get("year")),
                source_url=str(metadata.get("source_url") or ""),
            )
            result = {"document": document.model_dump(mode="json")}

        self.repository.update(import_id, status="confirmed")
        shutil.rmtree(source.parent, ignore_errors=True)
        return result

    def cleanup_expired(self) -> int:
        expired = self.repository.list_expired()
        for record in expired:
            staging_dir = Path(record.staged_path).parent
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            try:
                self.repository.delete(record.id)
            except KeyError:
                continue
        return len(expired)


def _optional_year(value: object) -> int | None:
    clean = str(value or "").strip()
    if not clean.isdigit():
        return None
    year = int(clean)
    if 1900 <= year <= 2200:
        return year
    return None


def _mean_confidence(questions: list[ParsedPaperQuestion]) -> float:
    if not questions:
        return 0.0
    return round(sum(item.answer_confidence for item in questions) / len(questions), 4)


def _paper_warnings(parsed: PaperParseResult) -> list[str]:
    warnings: list[str] = []
    if not parsed.questions:
        warnings.append("未识别到结构化题目，请检查抽取文本。")
    if parsed.questions and all(not item.answer for item in parsed.questions):
        warnings.append("未识别到可核验答案，入库后仅作为风格证据。")
    return warnings
