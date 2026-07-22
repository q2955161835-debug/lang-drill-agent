from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Iterable, Protocol

from pydantic import BaseModel

from .models import MemoryCandidate, MemoryItem
from .repository import MemoryRepository
from .retrieval import MemoryRetrievalQuery, MemoryRetrievalResult, MemoryRetrievalService


class MemoryProviderConflict(RuntimeError):
    pass


class ProviderHealth(BaseModel):
    healthy: bool
    detail: str = ""


class MemoryExportRecord(BaseModel):
    id: str
    category: str
    scope: str
    content: str
    normalized_key: str
    confidence: float
    importance: float
    status: str
    valid_from: str | None = None
    valid_to: str | None = None
    expires_at: str | None = None
    supersedes_id: str | None = None
    pinned: bool = False
    evidence_ids: list[str] = []
    metadata: dict = {}
    content_hash: str


class MemoryProviderAdapter(Protocol):
    id: str

    def health(self) -> ProviderHealth: ...

    def retrieve(self, query: MemoryRetrievalQuery) -> MemoryRetrievalResult | list: ...

    def stage_candidate(self, candidate: MemoryCandidate) -> str: ...

    def commit(self, candidate_id: str) -> MemoryItem: ...

    def update(self, memory_id: str, content: str) -> MemoryItem: ...

    def delete(self, memory_id: str) -> MemoryItem: ...

    def export(self) -> Iterable[MemoryExportRecord]: ...

    def import_dry_run(self, records: Iterable[MemoryExportRecord]) -> dict: ...

    def import_records(self, records: Iterable[MemoryExportRecord]) -> int: ...

    def reindex(self): ...


class MemoryProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, MemoryProviderAdapter] = {}
        self._primary_id = ""

    @property
    def primary_id(self) -> str:
        return self._primary_id

    def register(
        self,
        provider_id: str,
        provider: MemoryProviderAdapter,
        *,
        primary: bool = False,
    ) -> None:
        if primary and self._primary_id and self._primary_id != provider_id:
            raise MemoryProviderConflict("only one memory provider can be primary")
        self._providers[provider_id] = provider
        if primary:
            self._primary_id = provider_id

    def get(self, provider_id: str) -> MemoryProviderAdapter:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"memory provider not registered: {provider_id}") from exc

    def set_primary(self, provider_id: str) -> None:
        self.get(provider_id)
        self._primary_id = provider_id

    def providers(self) -> dict[str, MemoryProviderAdapter]:
        return dict(self._providers)


class BuiltinMemoryProvider:
    id = "builtin"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repository = MemoryRepository(conn)

    def health(self) -> ProviderHealth:
        try:
            self.conn.execute("SELECT 1 FROM memory_items LIMIT 1").fetchone()
        except sqlite3.Error as exc:
            return ProviderHealth(healthy=False, detail=str(exc))
        return ProviderHealth(healthy=True, detail="builtin SQLite memory is available")

    def retrieve(self, query: MemoryRetrievalQuery) -> MemoryRetrievalResult:
        return MemoryRetrievalService(self.conn).retrieve(query)

    def stage_candidate(self, candidate: MemoryCandidate) -> str:
        return self.repository.stage(candidate).id

    def commit(self, candidate_id: str) -> MemoryItem:
        return self.repository.commit(self.repository.get_candidate(candidate_id))

    def commit_candidate(self, candidate: MemoryCandidate) -> MemoryItem:
        return self.repository.commit(self.repository.stage(candidate))

    def update(self, memory_id: str, content: str) -> MemoryItem:
        return self.repository.update(memory_id, content)

    def delete(self, memory_id: str) -> MemoryItem:
        return self.repository.delete(memory_id)

    def export(self) -> Iterable[MemoryExportRecord]:
        items = self.repository.list_items(
            statuses=("active", "archived", "superseded", "deleted")
        )
        for item in items:
            evidence_ids = [
                evidence.evidence_ref for evidence in self.repository.evidence(item.id)
            ]
            yield _export_record(item, evidence_ids)

    def import_dry_run(self, records: Iterable[MemoryExportRecord]) -> dict:
        normalized = list(records)
        return {
            "count": len(normalized),
            "hashes": [record.content_hash for record in normalized],
        }

    def import_records(self, records: Iterable[MemoryExportRecord]) -> int:
        imported = 0
        for record in records:
            existing = self.conn.execute(
                "SELECT id FROM memory_items WHERE id=?",
                (record.id,),
            ).fetchone()
            if existing:
                continue
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
                metadata={**record.metadata, "imported_from_id": record.id},
            )
            self.commit_candidate(candidate)
            imported += 1
        return imported

    def reindex(self) -> int:
        items = self.repository.list_items(
            statuses=("active", "archived", "superseded", "deleted")
        )
        for item in items:
            self.repository._refresh_fts(item)
        return len(items)


def _export_record(item: MemoryItem, evidence_ids: list[str]) -> MemoryExportRecord:
    payload = "\n".join(
        [item.category, item.scope, item.normalized_key, item.content, item.status]
    )
    content_hash = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return MemoryExportRecord(
        **item.model_dump(),
        evidence_ids=evidence_ids,
        content_hash=content_hash,
    )


@dataclass(frozen=True, slots=True)
class ProviderVerification:
    count: int
    hashes: tuple[str, ...]
