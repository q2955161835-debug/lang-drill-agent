from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ..db import init_db, transaction
from ..embeddings.runtime import EmbeddingRuntime
from ..paper_assets import extract_text_from_file, paper_root, write_paper_v2_assets
from ..past_papers.markdown import parse_paper_markdown
from ..past_papers.distillation import PastPaperDistillationService
from ..past_papers.embeddings import PastPaperEmbeddingIndexService
from ..past_papers.ingestion import PastPaperIngestionService
from ..past_papers.models import PaperQuestionInput
from ..past_papers.repository import PastPaperRepository
from ..past_papers.retrieval import PastPaperQuery, PastPaperRetrievalService
from ..past_papers.sources import (
    CompositePastPaperSourceAdapter,
    DownloadPolicy,
    HtmlPaperSourceAdapter,
    PaperDownloader,
    PaperSourcePolicyError,
)
from ..utils import dumps, loads

router = APIRouter(prefix="/api/past-papers", tags=["past-papers"])


class PastPaperSettings(BaseModel):
    exam_id: str = Field(min_length=1, max_length=120)
    auto_sync: bool = False
    sync_cadence_hours: int = Field(default=24, ge=1, le=720)
    recent_count: int = Field(default=3, ge=1, le=20)
    allowed_sources: list[str] = Field(default_factory=list, max_length=20)
    parser: Literal["auto", "mineru", "rapidocr", "text"] = "auto"
    auto_distill: bool = False
    verified_answers_only: bool = True
    long_tail_min_ratio: float = Field(default=0.10, ge=0, le=0.5)
    max_question_type_ratio: float = Field(default=0.35, ge=0.1, le=1)
    coverage_window: int = Field(default=20, ge=5, le=200)

    @field_validator("allowed_sources")
    @classmethod
    def validate_allowed_sources(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            clean = value.strip()
            parsed = urlparse(clean)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("真题来源必须使用有效 HTTPS 地址。")
            if clean not in normalized:
                normalized.append(clean)
        return normalized


class PastPaperSearchRequest(BaseModel):
    exam_id: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=2000)
    question_types: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    knowledge_tags: list[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=50)
    verified_answers_only: bool = False


class PastPaperSyncRequest(BaseModel):
    exam_id: str = Field(min_length=1, max_length=120)
    max_documents: int | None = Field(default=None, ge=1, le=20)
    force: bool = True


class PastPaperDistillRequest(BaseModel):
    exam_id: str = Field(min_length=1, max_length=120)
    document_ids: list[str] = Field(default_factory=list)


class PastPaperReparseRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=240)


def _settings_key(exam_id: str) -> str:
    return f"past_papers.library_settings.{exam_id}"


def _load_settings(conn, exam_id: str) -> PastPaperSettings:
    row = conn.execute(
        "SELECT value_json FROM app_settings WHERE key=?",
        (_settings_key(exam_id),),
    ).fetchone()
    payload = loads(row["value_json"], {}) if row else {}
    return PastPaperSettings(exam_id=exam_id, **{key: value for key, value in payload.items() if key != "exam_id"})


@router.get("/catalog")
def catalog(exam_id: str) -> dict:
    init_db()
    with transaction() as conn:
        repo = PastPaperRepository(conn)
        sources = repo.list_sources(exam_id)
        documents = repo.list_documents(exam_id)
        installed_source_ids = {document.source_id for document in documents if document.source_id}
        source_payload = [
            {
                **source.model_dump(mode="json"),
                "installed": source.id in installed_source_ids,
            }
            for source in sources
        ]
        imports = _list_imports(conn, exam_id)
        settings = _load_settings(conn, exam_id)
    return {
        "exam_id": exam_id,
        "remote_count": len(sources),
        "installed_count": len(documents),
        "sources": source_payload,
        "documents": [document.model_dump(mode="json") for document in documents],
        "imports": imports,
        "settings": settings.model_dump(mode="json"),
    }


@router.get("/imports")
def imports(exam_id: str) -> dict:
    init_db()
    with transaction() as conn:
        items = _list_imports(conn, exam_id)
    return {"exam_id": exam_id, "imports": items}


@router.get("/settings")
def get_settings(exam_id: str) -> dict:
    init_db()
    with transaction() as conn:
        settings = _load_settings(conn, exam_id)
    return {"settings": settings.model_dump(mode="json")}


@router.post("/settings")
def save_settings(request: PastPaperSettings) -> dict:
    init_db()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (_settings_key(request.exam_id), dumps(request.model_dump(mode="json"))),
        )
    return {"settings": request.model_dump(mode="json")}


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def sync(request: PastPaperSyncRequest) -> dict:
    init_db()
    with transaction() as conn:
        settings = _load_settings(conn, request.exam_id)
        if not settings.allowed_sources:
            raise HTTPException(
                status_code=409,
                detail={"code": "PAST_PAPER_SOURCE_NOT_CONFIGURED", "params": {}},
            )
        if not request.force and not _auto_sync_due(conn, request.exam_id, settings):
            return {"skipped": True, "reason": "sync_cadence_not_due"}
        allowed_hosts = {
            host
            for source_url in settings.allowed_sources
            if (host := (urlparse(source_url).hostname or "").lower())
        }
        client = httpx.Client(follow_redirects=False, timeout=60)
        adapter = CompositePastPaperSourceAdapter(
            [
                HtmlPaperSourceAdapter(
                    client,
                    catalog_urls={request.exam_id: source_url},
                    allowed_hosts=allowed_hosts,
                )
                for source_url in settings.allowed_sources
            ]
        )
        downloader = PaperDownloader(
            policy=DownloadPolicy(allowed_hosts=frozenset(allowed_hosts)),
            client=client,
        )
        try:
            run = PastPaperIngestionService(
                conn,
                papers_root=paper_root(),
                downloader=downloader,
                source_adapter=adapter,
                preferred_parser=settings.parser,
            ).sync(
                request.exam_id,
                max_documents=request.max_documents or settings.recent_count,
            )
        except PaperSourcePolicyError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "PAST_PAPER_SOURCE_REJECTED", "params": {}},
            ) from exc
        finally:
            client.close()
        distillation = None
        if run.status == "completed":
            conn.execute(
                """
                INSERT INTO app_settings (key, value_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                  value_json=excluded.value_json,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    f"past_papers.last_sync.{request.exam_id}",
                    dumps({"completed_at": datetime.now().isoformat(timespec="seconds")}),
                ),
            )
        if settings.auto_distill and run.status == "completed":
            ready_document_ids = [
                document.id
                for document in PastPaperRepository(conn).list_documents(request.exam_id)
                if document.status == "ready"
            ]
            distillation = PastPaperDistillationService(conn).distill(
                request.exam_id,
                ready_document_ids,
            ).model_dump(mode="json")
    return {
        "run_id": run.id,
        "run": run.model_dump(mode="json"),
        "distillation": distillation,
    }


@router.post("/search")
def search(request: PastPaperSearchRequest) -> dict:
    init_db()
    with transaction() as conn:
        embedding_config, embedding_provider = EmbeddingRuntime(conn).current()
        result = PastPaperRetrievalService(
            conn,
            embedding_provider=embedding_provider,
            embedding_config=embedding_config,
        ).search(
            PastPaperQuery(
                exam_id=request.exam_id,
                text=request.query,
                question_types=request.question_types,
                years=request.years,
                knowledge_tags=request.knowledge_tags,
                top_k=request.top_k,
                verified_answers_only=request.verified_answers_only,
            )
        )
    return result.model_dump(mode="json")


@router.post("/distill")
def distill(request: PastPaperDistillRequest) -> dict:
    init_db()
    with transaction() as conn:
        repo = PastPaperRepository(conn)
        document_ids = request.document_ids or [
            document.id for document in repo.list_documents(request.exam_id) if document.status == "ready"
        ]
        result = PastPaperDistillationService(conn).distill(
            request.exam_id,
            document_ids,
        )
    return result.model_dump(mode="json")


@router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex(request: PastPaperReparseRequest) -> dict:
    init_db()
    with transaction() as conn:
        repo = PastPaperRepository(conn)
        try:
            document = repo.get_document(request.document_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "PAST_PAPER_DOCUMENT_NOT_FOUND", "params": {}},
            ) from exc
        repo.rebuild_question_fts(document.id)
        questions = repo.list_questions(document.id)
        embedding_index = PastPaperEmbeddingIndexService(conn)
        embedding_index.clear_document(document.id)
        mode = "fts"
        embedding_count = 0
        try:
            embedding_config, embedding_provider = EmbeddingRuntime(conn).current()
            if embedding_config.enabled and embedding_provider is not None:
                embedding_count = embedding_index.index_questions(
                    embedding_provider,
                    questions,
                    embedding_config,
                )
                mode = "hybrid"
        except Exception:
            mode = "fts_fallback"
    return {
        "document_id": document.id,
        "question_count": len(questions),
        "embedding_count": embedding_count,
        "mode": mode,
    }


@router.post("/reparse", status_code=status.HTTP_202_ACCEPTED)
def reparse(request: PastPaperReparseRequest) -> dict:
    init_db()
    with transaction() as conn:
        repo = PastPaperRepository(conn)
        try:
            document = repo.get_document(request.document_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "PAST_PAPER_DOCUMENT_NOT_FOUND", "params": {}},
            ) from exc
        raw_path = Path(document.raw_path)
        if not raw_path.is_file():
            raise HTTPException(
                status_code=409,
                detail={"code": "PAST_PAPER_SOURCE_MISSING", "params": {}},
            )
        root = paper_root() / document.exam_id
        markdown_path = (
            Path(document.markdown_path)
            if document.markdown_path
            else root / "parsed" / f"{document.id}.md"
        )
        structured_path = (
            Path(document.structured_path)
            if document.structured_path
            else root / "structured" / f"{document.id}.json"
        )
        if markdown_path.is_file():
            parsed = parse_paper_markdown(markdown_path.read_text(encoding="utf-8"))
            structured_path.parent.mkdir(parents=True, exist_ok=True)
            structured_staging = structured_path.with_name(structured_path.name + ".staging")
            structured_staging.write_text(
                dumps(parsed.model_dump(mode="json")),
                encoding="utf-8",
            )
            structured_staging.replace(structured_path)
            parser = "user_edited_markdown"
        else:
            extracted_text, parser = extract_text_from_file(raw_path, language="ch")
            parsed = write_paper_v2_assets(
                extracted_text,
                exam_id=document.exam_id,
                title=document.title,
                year=document.year,
                source_url=document.source_url,
                markdown_path=markdown_path,
                structured_path=structured_path,
            )
        repo.replace_questions(
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
        updated = repo.update_document_state(
            document.id,
            status="ready",
            markdown_path=str(markdown_path),
            structured_path=str(structured_path),
            parser=parser,
            parser_version="2",
            error_code="",
        )
    return {"document": updated.model_dump(mode="json")}


def _auto_sync_due(conn, exam_id: str, settings: PastPaperSettings) -> bool:
    if not settings.auto_sync:
        return False
    row = conn.execute(
        "SELECT value_json FROM app_settings WHERE key=?",
        (f"past_papers.last_sync.{exam_id}",),
    ).fetchone()
    payload = loads(row["value_json"], {}) if row else {}
    completed_at = str(payload.get("completed_at") or "")
    if not completed_at:
        return True
    try:
        last_sync = datetime.fromisoformat(completed_at)
    except ValueError:
        return True
    return datetime.now() - last_sync >= timedelta(hours=settings.sync_cadence_hours)


def _list_imports(conn, exam_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT j.*, s.exam_id, s.title
        FROM past_paper_import_jobs j
        JOIN past_paper_sources s ON s.id=j.source_id
        WHERE s.exam_id=?
        ORDER BY j.created_at DESC, j.id DESC
        LIMIT 50
        """,
        (exam_id,),
    ).fetchall()
    return [dict(row) for row in rows]
