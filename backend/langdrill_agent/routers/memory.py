from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import init_db, transaction
from ..memory.hooks import MemorySettings, MemorySettingsService
from ..memory.models import MemoryCandidate
from ..memory.presets import (
    GROUP_CATEGORIES,
    MemoryGroup,
    MemoryMode,
    read_context_limit,
    resolve_memory_budget,
)
from ..memory.repository import MemoryRepository
from ..memory.secrets import scan_memory_secrets
from ..memory.service import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])
_ALL_STATUSES = ("active", "archived", "superseded", "deleted")


class MemorySettingsPatch(BaseModel):
    enabled: bool | None = None
    capture_enabled: bool | None = None
    recall_enabled: bool | None = None
    mode: MemoryMode | None = None
    group_enabled: dict[MemoryGroup, bool] | None = None
    category_enabled: dict[str, bool] | None = None
    write_mode: Literal["explicit", "approval", "balanced", "proactive"] | None = None
    learning_evidence_min: int | None = Field(default=None, ge=2, le=20)
    confidence_min: float | None = Field(default=None, ge=0, le=1)
    default_ttl_days: int | None = Field(default=None, ge=1, le=3650)
    core_token_budget: int | None = Field(default=None, ge=50, le=20_000)
    recall_top_k: int | None = Field(default=None, ge=1, le=50)
    recall_token_budget: int | None = Field(default=None, ge=100, le=20_000)
    embeddings_enabled: bool | None = None
    compaction_flush_enabled: bool | None = None


class CandidateReviewRequest(BaseModel):
    action: Literal["approve", "reject"]


class MemoryItemUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=20_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    importance: float | None = Field(default=None, ge=0, le=1)
    pinned: bool | None = None
    metadata: dict[str, Any] | None = None


class MemoryItemActionRequest(BaseModel):
    action: Literal["archive", "restore", "delete", "purge", "pin", "unpin"]
    confirmed: bool = False


class MemoryGroupClearRequest(BaseModel):
    confirmed: bool = False


class MemoryImportRecord(BaseModel):
    category: str
    scope: str = "global"
    content: str = Field(min_length=1, max_length=20_000)
    normalized_key: str = ""
    confidence: float = Field(default=0.7, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    status: Literal["active", "archived", "superseded", "deleted"] = "active"
    valid_from: str | None = None
    valid_to: str | None = None
    expires_at: str | None = None
    pinned: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryImportRequest(BaseModel):
    records: list[MemoryImportRecord] = Field(max_length=10_000)


class ProviderPrepareRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=100)


class ProviderCommitRequest(ProviderPrepareRequest):
    verification_token: str = Field(min_length=1, max_length=500)


def _not_found(resource: str, resource_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "MEMORY_NOT_FOUND", "params": {"resource": resource, "id": resource_id}},
    )


def _status_counts(conn, service: MemoryService) -> dict[str, int]:
    counts = {status: 0 for status in _ALL_STATUSES}
    for record in service.export():
        counts[record.status] = counts.get(record.status, 0) + 1
    counts["candidates"] = int(
        conn.execute(
            "SELECT COUNT(*) FROM memory_candidates WHERE status='staged'"
        ).fetchone()[0]
    )
    return counts


def _candidate_payload(candidate: MemoryCandidate) -> dict[str, Any]:
    payload = candidate.model_dump(mode="json")
    payload["evidence_count"] = len(candidate.evidence_ids)
    return payload


@router.get("/status")
def memory_status() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        settings = MemorySettingsService(conn).get()
        service = MemoryService(conn)
        provider = service.status()
        counts = _status_counts(conn, service)
        available_context = read_context_limit(conn)
        budget = resolve_memory_budget(settings.mode, available_context)
        category_counts = MemoryRepository(conn).count_active_by_category()
        group_counts = {
            group: sum(category_counts.get(category, 0) for category in categories)
            for group, categories in GROUP_CATEGORIES.items()
        }
    return {
        "settings": settings.model_dump(mode="json"),
        "provider": provider.model_dump(mode="json"),
        "counts": counts,
        "effective_budget": budget.model_dump(mode="json"),
        "group_counts": group_counts,
    }


@router.post("/groups/{group}/clear")
def clear_memory_group(
    group: MemoryGroup,
    request: MemoryGroupClearRequest,
) -> dict[str, Any]:
    init_db()
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail={"code": "MEMORY_GROUP_CLEAR_CONFIRMATION_REQUIRED", "params": {}},
        )
    categories = list(GROUP_CATEGORIES[group])
    with transaction() as conn:
        archived_count = MemoryRepository(conn).archive_categories(categories)
    return {
        "group": group,
        "categories": categories,
        "archived_count": archived_count,
    }


@router.get("/items")
def list_memory_items(
    query: str = "",
    status: str = Query(default="all"),
    category: str = "",
) -> dict[str, Any]:
    init_db()
    statuses = _ALL_STATUSES if status == "all" else (status,)
    with transaction() as conn:
        records = MemoryService(conn).export()
    clean_query = query.strip().casefold()
    items = [
        record
        for record in records
        if record.status in statuses
        and (not category or record.category == category)
        and (
            not clean_query
            or clean_query in record.content.casefold()
            or clean_query in record.normalized_key.casefold()
        )
    ]
    return {"items": [item.model_dump(mode="json") for item in items]}


@router.get("/items/{memory_id}")
def memory_item_detail(memory_id: str) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repository = MemoryRepository(conn)
        service = MemoryService(conn)
        if service.current_primary_id == "builtin":
            try:
                item = repository.get(memory_id)
            except KeyError as exc:
                raise _not_found("item", memory_id) from exc
            evidence = [row.model_dump(mode="json") for row in repository.evidence(memory_id)]
            revisions = [row.model_dump(mode="json") for row in repository.revisions(memory_id)]
        else:
            try:
                item = next(record for record in service.export() if record.id == memory_id)
            except StopIteration as exc:
                raise _not_found("item", memory_id) from exc
            audit_candidate = next(
                (
                    candidate
                    for candidate in repository.list_candidates(status="committed")
                    if candidate.metadata.get("external_memory_id") == memory_id
                ),
                None,
            )
            evidence = [
                {
                    "id": f"external-evidence-{index}",
                    "candidate_id": audit_candidate.id,
                    "memory_id": memory_id,
                    "evidence_type": "reference",
                    "evidence_ref": reference,
                    "payload": {"provider_id": service.current_primary_id},
                    "created_at": audit_candidate.created_at,
                }
                for index, reference in enumerate(audit_candidate.evidence_ids)
            ] if audit_candidate else []
            revisions = []
    return {
        "item": item.model_dump(mode="json"),
        "evidence": evidence,
        "revisions": revisions,
    }


@router.post("/items/{memory_id}")
def update_memory_item(memory_id: str, request: MemoryItemUpdateRequest) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repository = MemoryRepository(conn)
        service = MemoryService(conn)
        try:
            current = next(
                item for item in service.export() if item.id == memory_id
            )
        except StopIteration as exc:
            raise _not_found("item", memory_id) from exc
        content = request.content.strip() if request.content is not None else current.content
        secret_scan = scan_memory_secrets(content)
        if secret_scan.detected:
            raise HTTPException(
                status_code=422,
                detail={"code": "MEMORY_SECRET_REJECTED", "params": {}},
            )
        if service.current_primary_id == "builtin":
            item = repository.update(
                memory_id,
                content,
                confidence=request.confidence,
                importance=request.importance,
                pinned=request.pinned,
                metadata=request.metadata,
            )
        else:
            if any(
                value is not None
                for value in (
                    request.confidence,
                    request.importance,
                    request.pinned,
                    request.metadata,
                )
            ):
                raise HTTPException(
                    status_code=409,
                    detail="external provider only supports content updates",
                )
            item = service.update(memory_id, content)
    return {"item": item.model_dump(mode="json")}


@router.post("/items/{memory_id}/action")
def act_on_memory_item(memory_id: str, request: MemoryItemActionRequest) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repository = MemoryRepository(conn)
        service = MemoryService(conn)
        if service.current_primary_id != "builtin":
            if request.action != "delete":
                raise HTTPException(
                    status_code=409,
                    detail="external provider does not support this lifecycle action",
                )
            try:
                item = service.delete(memory_id)
            except KeyError as exc:
                raise _not_found("item", memory_id) from exc
            return {"item": item.model_dump(mode="json")}
        try:
            current = repository.get(memory_id)
            if request.action == "archive":
                item = repository.archive(memory_id)
            elif request.action == "restore":
                item = repository.restore(memory_id)
            elif request.action == "delete":
                item = repository.delete(memory_id)
            elif request.action == "pin":
                item = repository.update(memory_id, current.content, pinned=True)
            elif request.action == "unpin":
                item = repository.update(memory_id, current.content, pinned=False)
            else:
                repository.purge(memory_id, confirmed=request.confirmed)
                return {"purged": True, "memory_id": memory_id}
        except KeyError as exc:
            raise _not_found("item", memory_id) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"item": item.model_dump(mode="json")}


@router.get("/candidates")
def list_memory_candidates(status: str = "staged") -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        candidates = MemoryRepository(conn).list_candidates(status=status or None)
    return {"candidates": [_candidate_payload(item) for item in candidates]}


@router.post("/candidates/{candidate_id}/review")
def review_memory_candidate(
    candidate_id: str,
    request: CandidateReviewRequest,
) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repository = MemoryRepository(conn)
        try:
            candidate = repository.get_candidate(candidate_id)
        except KeyError as exc:
            raise _not_found("candidate", candidate_id) from exc
        if candidate.status != "staged":
            raise HTTPException(status_code=409, detail="memory candidate is no longer pending")
        if scan_memory_secrets(candidate.content).detected:
            raise HTTPException(
                status_code=422,
                detail={"code": "MEMORY_SECRET_REJECTED", "params": {}},
            )
        if request.action == "reject":
            rejected = repository.discard_candidate(candidate_id, reason="user_rejected")
            return {"candidate": _candidate_payload(rejected), "item": None}
        service = MemoryService(conn)
        same_key = [
            item
            for item in service.active_items(scope=candidate.scope)
            if item.normalized_key == candidate.normalized_key
        ]
        duplicate = next(
            (
                item
                for item in same_key
                if " ".join(item.content.split()).casefold()
                == " ".join(candidate.content.split()).casefold()
            ),
            None,
        )
        if duplicate is not None:
            item = duplicate
            if service.current_primary_id == "builtin":
                repository.mark_candidate_committed_existing(
                    candidate.id,
                    memory_id=item.id,
                )
            else:
                repository.mark_candidate_committed_external(
                    candidate.id,
                    provider_id=service.current_primary_id,
                    external_memory_id=item.id,
                )
        elif same_key:
            if service.current_primary_id == "builtin":
                item = repository.supersede(same_key[0].id, candidate)
            else:
                item = service.update(same_key[0].id, candidate.content)
                repository.mark_candidate_committed_external(
                    candidate.id,
                    provider_id=service.current_primary_id,
                    external_memory_id=item.id,
                )
        else:
            item = service.commit_staged_candidate(candidate)
            if service.current_primary_id != "builtin":
                repository.mark_candidate_committed_external(
                    candidate.id,
                    provider_id=service.current_primary_id,
                    external_memory_id=item.id,
                )
        approved = repository.get_candidate(candidate_id)
    return {
        "candidate": _candidate_payload(approved),
        "item": item.model_dump(mode="json"),
    }


@router.post("/settings")
def save_memory_settings(request: MemorySettingsPatch) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        service = MemorySettingsService(conn)
        current = service.get().model_dump()
        patch = request.model_dump(exclude_none=True)
        if "group_enabled" in patch:
            patch["group_enabled"] = {
                **current["group_enabled"],
                **patch["group_enabled"],
            }
        if "category_enabled" in patch:
            patch["category_enabled"] = {
                **current["category_enabled"],
                **patch["category_enabled"],
            }
        settings = service.save(MemorySettings(**{**current, **patch}))
    return {"settings": settings.model_dump(mode="json")}


@router.get("/export")
def export_memory() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        records = MemoryService(conn).export()
        settings = MemorySettingsService(conn).get()
    return {
        "schema_version": 1,
        "settings": settings.model_dump(mode="json"),
        "records": [record.model_dump(mode="json") for record in records],
    }


@router.post("/import")
def import_memory(request: MemoryImportRequest) -> dict[str, Any]:
    for record in request.records:
        if scan_memory_secrets(record.content).detected:
            raise HTTPException(
                status_code=422,
                detail={"code": "MEMORY_SECRET_REJECTED", "params": {}},
            )
    init_db()
    imported = 0
    skipped = 0
    with transaction() as conn:
        repository = MemoryRepository(conn)
        service = MemoryService(conn)
        existing = {
            (item.normalized_key, item.content.casefold())
            for item in service.export()
        }
        if service.current_primary_id != "builtin" and any(
            record.status != "active" for record in request.records
        ):
            raise HTTPException(
                status_code=409,
                detail="external provider imports only support active records",
            )
        for record in request.records:
            key = (record.normalized_key, record.content.casefold())
            if key in existing:
                skipped += 1
                continue
            try:
                candidate = MemoryCandidate(
                    category=record.category,
                    scope=record.scope,
                    content=record.content,
                    normalized_key=record.normalized_key,
                    confidence=record.confidence,
                    importance=record.importance,
                    valid_from=record.valid_from,
                    valid_to=record.valid_to,
                    expires_at=record.expires_at,
                    pinned=record.pinned,
                    evidence_ids=record.evidence_ids,
                    metadata={**record.metadata, "source": "memory_import"},
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            staged = repository.stage(candidate)
            item = service.commit_staged_candidate(staged)
            if service.current_primary_id != "builtin":
                repository.mark_candidate_committed_external(
                    staged.id,
                    provider_id=service.current_primary_id,
                    external_memory_id=item.id,
                )
            elif record.status == "archived":
                repository.archive(item.id)
            elif record.status == "superseded":
                repository.mark_superseded_from_import(item.id)
            elif record.status == "deleted":
                repository.delete(item.id)
            existing.add(key)
            imported += 1
    return {"imported_count": imported, "skipped_count": skipped}


@router.post("/reindex")
def reindex_memory() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        result = MemoryService(conn).reindex()
    indexed_count = int(result) if isinstance(result, int) else 0
    return {"indexed_count": indexed_count}


@router.post("/provider/prepare")
def prepare_provider_switch(request: ProviderPrepareRequest) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        result = MemoryService(conn).configure_primary(request.provider_id)
    return {"result": result.model_dump(mode="json")}


@router.post("/provider/commit")
def commit_provider_switch(request: ProviderCommitRequest) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        try:
            result = MemoryService(conn).commit_provider_switch(
                request.provider_id,
                request.verification_token,
            )
        except (KeyError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"result": result.model_dump(mode="json")}
