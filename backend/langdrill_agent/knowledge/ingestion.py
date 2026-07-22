from __future__ import annotations

import hashlib
import mimetypes
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

from ..config import load_settings
from ..paper_assets import extract_text_from_file
from ..runtime.models import AgentRunRecord, RunStatus
from ..runtime.repository import AgentRunRepository
from .chunking import ChunkingConfig, chunk_markdown
from .embeddings import EmbeddingIndexService, embedding_runtime_from_env
from .models import DocumentStatus
from .repository import KnowledgeRepository

Extractor = Callable[..., tuple[str, str]]


class KnowledgeIngestionService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        user_data_dir: Path | None = None,
        extractor: Extractor | None = None,
        chunking_config: ChunkingConfig | None = None,
    ) -> None:
        self.conn = conn
        self.user_data_dir = user_data_dir or load_settings().user_data_dir
        self.extractor = extractor or extract_text_from_file
        self.chunking_config = chunking_config or ChunkingConfig()

    def import_file(
        self,
        path: Path,
        *,
        title: str,
        language: str = "",
        document_id: str | None = None,
    ) -> AgentRunRecord:
        source = path.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)

        content_hash = _file_hash(source)
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        knowledge_repo = KnowledgeRepository(self.conn)
        run_repo = AgentRunRepository(self.conn)
        previous_document = knowledge_repo.get_document(document_id) if document_id else None
        if previous_document:
            document = knowledge_repo.set_document_status(
                previous_document.id,
                DocumentStatus.importing,
                content_hash=content_hash,
                error_code="",
            )
        else:
            document = knowledge_repo.create_document(
                title=title.strip() or source.stem,
                source_name=source.name,
                mime_type=mime_type,
                content_hash=content_hash,
                language=language,
                status=DocumentStatus.importing,
            )
        run = run_repo.create(
            session_id=None,
            task_type="knowledge_import",
            goal=f"Import knowledge document {document.id}",
            completion_criteria=["source_saved", "text_extracted", "chunks_indexed"],
        )
        run_repo.set_status(run.id, RunStatus.running)

        raw_dir, parsed_dir = self._ensure_directories()
        suffix = source.suffix.lower() or ".bin"
        raw_path = raw_dir / f"{document.id}{suffix}"
        raw_staging = raw_dir / f"{document.id}{suffix}.staging"
        parsed_path = parsed_dir / f"{document.id}.md"
        parsed_staging = parsed_dir / f"{document.id}.md.staging"

        try:
            shutil.copy2(source, raw_staging)
            run_repo.append_event(run.id, "progress", {"percent": 10, "document_id": document.id})

            extracted_text, parser = self.extractor(source, language=language or "ch")
            normalized = _normalize_markdown(extracted_text, title=title.strip() or source.stem)
            run_repo.append_event(run.id, "progress", {"percent": 35, "parser": parser})

            parsed_staging.write_text(normalized, encoding="utf-8")
            run_repo.append_event(run.id, "progress", {"percent": 60})

            chunks = chunk_markdown(normalized, self.chunking_config)
            indexed_chunks = knowledge_repo.upsert_chunks(document.id, chunks)
            embedding_mode = "fts"
            embedding_count = 0
            try:
                embedding_config, embedding_provider = embedding_runtime_from_env()
                if embedding_config.enabled and embedding_provider is not None:
                    embedding_count = EmbeddingIndexService(self.conn).index_chunks(
                        embedding_provider,
                        indexed_chunks,
                        embedding_config,
                    )
                    embedding_mode = "hybrid"
            except Exception:
                embedding_mode = "fts_fallback"
            run_repo.append_event(
                run.id,
                "progress",
                {
                    "percent": 90,
                    "chunk_count": len(chunks),
                    "embedding_count": embedding_count,
                    "search_mode": embedding_mode,
                },
            )

            raw_staging.replace(raw_path)
            parsed_staging.replace(parsed_path)
            knowledge_repo.set_document_status(
                document.id,
                DocumentStatus.ready,
                raw_path=str(raw_path),
                parsed_path=str(parsed_path),
                content_hash=content_hash,
                parser=parser,
                parser_version="1",
                error_code="",
            )
            run_repo.append_event(run.id, "progress", {"percent": 100})
            return run_repo.set_status(run.id, RunStatus.completed)
        except Exception as exc:
            _remove_if_exists(raw_staging)
            _remove_if_exists(parsed_staging)
            error_code = "KNOWLEDGE_EXTRACTION_FAILED"
            if previous_document:
                knowledge_repo.set_document_status(
                    document.id,
                    previous_document.status,
                    raw_path=previous_document.raw_path,
                    parsed_path=previous_document.parsed_path,
                    content_hash=previous_document.content_hash,
                    parser=previous_document.parser,
                    parser_version=previous_document.parser_version,
                    error_code=error_code,
                )
            else:
                _remove_if_exists(raw_path)
                _remove_if_exists(parsed_path)
                knowledge_repo.set_document_status(
                    document.id,
                    DocumentStatus.failed,
                    error_code=error_code,
                )
            run_repo.append_event(
                run.id,
                "failed",
                {"code": error_code, "detail": str(exc)[:300]},
            )
            return run_repo.set_status(run.id, RunStatus.failed, error_code=error_code)

    def _ensure_directories(self) -> tuple[Path, Path]:
        root = self.user_data_dir / "knowledge"
        raw_dir = root / "raw"
        parsed_dir = root / "parsed"
        raw_dir.mkdir(parents=True, exist_ok=True)
        parsed_dir.mkdir(parents=True, exist_ok=True)
        return raw_dir, parsed_dir


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _normalize_markdown(text: str, *, title: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise RuntimeError("document extractor returned no text")
    if normalized.lstrip().startswith("#"):
        return normalized + "\n"
    return f"# {title}\n\n{normalized}\n"


def _remove_if_exists(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
