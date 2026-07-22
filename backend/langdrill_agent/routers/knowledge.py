from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from ..db import init_db, transaction
from ..knowledge.embeddings import embedding_runtime_from_env
from ..knowledge.ingestion import KnowledgeIngestionService
from ..knowledge.repository import KnowledgeRepository
from ..knowledge.retrieval import KnowledgeRetrievalService, RetrievalQuery
from ..models import KnowledgeImportRequest, KnowledgeReindexRequest, KnowledgeSearchRequest

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _document_not_found(document_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "KNOWLEDGE_DOCUMENT_NOT_FOUND", "params": {"document_id": document_id}},
    )


@router.get("/documents")
def list_documents() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repo = KnowledgeRepository(conn)
        documents = []
        for document in repo.list_documents():
            payload = document.model_dump(mode="json")
            payload["chunk_count"] = len(repo.list_chunks(document.id))
            documents.append(payload)
    return {"documents": documents}


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
def import_document(request: KnowledgeImportRequest) -> dict[str, Any]:
    source = Path(request.local_path).expanduser()
    if not source.is_file():
        raise HTTPException(
            status_code=400,
            detail={"code": "KNOWLEDGE_SOURCE_NOT_FOUND", "params": {}},
        )
    init_db()
    with transaction() as conn:
        run = KnowledgeIngestionService(conn).import_file(
            source,
            title=request.title or source.stem,
            language=request.language,
        )
        documents = KnowledgeRepository(conn).list_documents()
        document = documents[-1]
    return {
        "run_id": run.id,
        "run": run.model_dump(mode="json"),
        "document": document.model_dump(mode="json"),
    }


@router.post("/import-file", status_code=status.HTTP_202_ACCEPTED)
async def import_uploaded_document(
    request: Request,
    filename: str,
    title: str = "",
    language: str = "",
) -> dict[str, Any]:
    data = await request.body()
    if not data:
        raise HTTPException(
            status_code=400,
            detail={"code": "KNOWLEDGE_UPLOAD_EMPTY", "params": {}},
        )
    safe_name = Path(filename.replace("\\", "/")).name or "knowledge.txt"
    with tempfile.TemporaryDirectory(prefix="langdrill-knowledge-") as temp_dir:
        source = Path(temp_dir) / safe_name
        source.write_bytes(data)
        init_db()
        with transaction() as conn:
            run = KnowledgeIngestionService(conn).import_file(
                source,
                title=title or source.stem,
                language=language,
            )
            document = KnowledgeRepository(conn).list_documents()[-1]
    return {
        "run_id": run.id,
        "run": run.model_dump(mode="json"),
        "document": document.model_dump(mode="json"),
    }


@router.post("/search")
def search_knowledge(request: KnowledgeSearchRequest) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        embedding_config, embedding_provider = embedding_runtime_from_env()
        result = KnowledgeRetrievalService(
            conn,
            embedding_provider=embedding_provider,
            embedding_config=embedding_config,
        ).search_result(
            RetrievalQuery(
                text=request.query,
                document_ids=request.document_ids,
                top_k=request.top_k,
                token_budget=request.token_budget,
                trace_id=request.trace_id,
            )
        )
    return result.model_dump(mode="json")


@router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex_document(request: KnowledgeReindexRequest) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repo = KnowledgeRepository(conn)
        try:
            document = repo.get_document(request.document_id)
        except KeyError as exc:
            raise _document_not_found(request.document_id) from exc
        source = Path(document.raw_path)
        if not source.is_file():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "KNOWLEDGE_SOURCE_MISSING",
                    "params": {"document_id": request.document_id},
                },
            )
        run = KnowledgeIngestionService(conn).import_file(
            source,
            title=document.title,
            language=document.language,
            document_id=document.id,
        )
        replacement = repo.get_document(document.id)
    return {
        "run_id": run.id,
        "run": run.model_dump(mode="json"),
        "document": replacement.model_dump(mode="json"),
        "replaced_document_id": request.document_id,
    }


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, response: Response) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repo = KnowledgeRepository(conn)
        try:
            document = repo.get_document(document_id)
        except KeyError as exc:
            raise _document_not_found(document_id) from exc
        paths = [Path(path) for path in (document.raw_path, document.parsed_path) if path]
        repo.delete_document(document_id)
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                response.headers.append("Warning", '199 - "knowledge file cleanup failed"')
    return {"deleted": True, "document_id": document_id}
