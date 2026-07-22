from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import BaseModel

from ..utils import dumps, loads
from .models import MemoryCandidate, MemoryItem
from .providers import (
    BuiltinMemoryProvider,
    MemoryExportRecord,
    MemoryProviderAdapter,
    MemoryProviderRegistry,
    ProviderHealth,
)
from .retrieval import (
    MemoryRetrievalQuery,
    MemoryRetrievalResult,
    RetrievedMemoryItem,
)
from .secrets import scan_memory_secrets

MemoryProviderFactory = Callable[[sqlite3.Connection], MemoryProviderAdapter]
_PROVIDER_FACTORIES: dict[str, MemoryProviderFactory] = {}
_PROVIDER_FACTORY_LOCK = threading.RLock()


def register_memory_provider_factory(
    provider_id: str,
    factory: MemoryProviderFactory,
) -> None:
    clean_id = provider_id.strip()
    if not clean_id or clean_id == "builtin":
        raise ValueError("external memory provider id is invalid")
    with _PROVIDER_FACTORY_LOCK:
        _PROVIDER_FACTORIES[clean_id] = factory


def unregister_memory_provider_factory(provider_id: str) -> None:
    with _PROVIDER_FACTORY_LOCK:
        _PROVIDER_FACTORIES.pop(provider_id, None)


def _provider_factories() -> dict[str, MemoryProviderFactory]:
    with _PROVIDER_FACTORY_LOCK:
        return dict(_PROVIDER_FACTORIES)


class ProviderSwitchResult(BaseModel):
    requested_provider_id: str
    current_primary_id: str
    switched: bool = False
    migration_required: bool = False
    migration_verified: bool = False
    verification_token: str = ""
    source_count: int = 0
    destination_count: int = 0
    detail: str = ""


class MemoryServiceStatus(BaseModel):
    current_primary_id: str
    providers: dict[str, ProviderHealth]
    requested_primary_id: str = ""
    migration_required: bool = False


class MemoryService:
    PRIMARY_KEY = "memory.provider.primary"
    REQUESTED_PRIMARY_KEY = "memory.provider.requested"
    SWITCH_KEY_PREFIX = "memory.provider.switch."

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.registry = MemoryProviderRegistry()
        self.builtin = BuiltinMemoryProvider(conn)
        self.registry.register("builtin", self.builtin, primary=True)
        for provider_id, factory in _provider_factories().items():
            try:
                provider = factory(conn)
                if provider.id != provider_id:
                    continue
                self.registry.register(provider_id, provider)
            except Exception:
                continue

        saved_primary = self._saved_primary_id()
        self.current_primary_id = "builtin"
        if saved_primary != "builtin" and saved_primary in self.registry.providers():
            try:
                if self.registry.get(saved_primary).health().healthy:
                    self.registry.set_primary(saved_primary)
                    self.current_primary_id = saved_primary
            except Exception:
                self.current_primary_id = "builtin"
        if saved_primary != "builtin" and self.current_primary_id == "builtin":
            self._save_primary("builtin")
            self._save_requested_primary(saved_primary)

    @property
    def primary_provider(self) -> MemoryProviderAdapter:
        return self.registry.get(self.current_primary_id)

    def register_provider(self, provider: MemoryProviderAdapter) -> None:
        if provider.id == "builtin":
            raise ValueError("builtin memory provider is already registered")
        self.registry.register(provider.id, provider)

    def status(self) -> MemoryServiceStatus:
        health = {
            provider_id: self._provider_health(provider)
            for provider_id, provider in self.registry.providers().items()
        }
        saved_primary = self._saved_primary_id()
        requested = self._requested_primary_id()
        unresolved = requested or (
            saved_primary if saved_primary != self.current_primary_id else ""
        )
        migration_required = bool(unresolved and unresolved != self.current_primary_id)
        return MemoryServiceStatus(
            current_primary_id=self.current_primary_id,
            providers=health,
            requested_primary_id=unresolved,
            migration_required=migration_required,
        )

    def active_items(self, *, scope: str = "global") -> list[MemoryItem]:
        if self.current_primary_id == "builtin":
            return self.builtin.repository.list_items(statuses=("active",), scope=scope)
        items: list[MemoryItem] = []
        for record in self.export():
            if record.status != "active":
                continue
            if scope == "global" and record.scope != "global":
                continue
            if scope != "global" and record.scope not in {"global", scope}:
                continue
            items.append(_record_to_item(record))
        return items

    def retrieve(self, query: MemoryRetrievalQuery) -> MemoryRetrievalResult:
        result = MemoryRetrievalResult.model_validate(
            self.primary_provider.retrieve(query)
        )
        as_of = _parse_timestamp(query.as_of) if query.as_of else datetime.now(timezone.utc)
        selected: list[RetrievedMemoryItem] = []
        consumed = 0
        for item in result.items:
            if len(selected) >= query.top_k:
                break
            if item.status != "active":
                continue
            if query.categories and item.category not in query.categories:
                continue
            if query.scope == "global" and item.scope != "global":
                continue
            if query.scope != "global" and item.scope not in {"global", query.scope}:
                continue
            if not _valid_at(item, as_of):
                continue
            if scan_memory_secrets(item.content).detected:
                continue
            token_count = _estimate_tokens(item.content)
            if selected and consumed + token_count > query.token_budget:
                continue
            if not selected and token_count > query.token_budget:
                item = item.model_copy(
                    update={
                        "content": item.content[: max(1, query.token_budget * 4)],
                        "token_count": query.token_budget,
                    }
                )
                selected.append(item)
                consumed = query.token_budget
                break
            item = item.model_copy(update={"token_count": token_count})
            selected.append(item)
            consumed += token_count
        return MemoryRetrievalResult(
            mode=result.mode,
            items=selected,
            token_count=consumed,
        )

    def commit_candidate(self, candidate: MemoryCandidate) -> MemoryItem:
        if self.current_primary_id == "builtin":
            return self.builtin.commit_candidate(candidate)
        candidate_id = self.primary_provider.stage_candidate(candidate)
        return self.primary_provider.commit(candidate_id)

    def commit_staged_candidate(self, candidate: MemoryCandidate) -> MemoryItem:
        if not candidate.id:
            raise ValueError("memory candidate must be staged before provider commit")
        if self.current_primary_id == "builtin":
            return self.builtin.commit(candidate.id)
        external_candidate_id = self.primary_provider.stage_candidate(candidate)
        return self.primary_provider.commit(external_candidate_id)

    def update(self, memory_id: str, content: str) -> MemoryItem:
        return self.primary_provider.update(memory_id, content)

    def delete(self, memory_id: str) -> MemoryItem:
        return self.primary_provider.delete(memory_id)

    def export(self) -> list[MemoryExportRecord]:
        return [
            record
            for record in self.primary_provider.export()
            if not scan_memory_secrets(record.content).detected
        ]

    def reindex(self):
        return self.primary_provider.reindex()

    def configure_primary(self, provider_id: str) -> ProviderSwitchResult:
        if provider_id == self.current_primary_id:
            self._save_primary(provider_id)
            self._clear_requested_primary()
            return ProviderSwitchResult(
                requested_provider_id=provider_id,
                current_primary_id=self.current_primary_id,
                detail="provider is already primary",
            )
        try:
            destination = self.registry.get(provider_id)
        except KeyError:
            self._save_requested_primary(provider_id)
            return ProviderSwitchResult(
                requested_provider_id=provider_id,
                current_primary_id=self.current_primary_id,
                migration_required=True,
                detail="provider is not registered",
            )
        health = self._provider_health(destination)
        if not health.healthy:
            self._save_requested_primary(provider_id)
            return ProviderSwitchResult(
                requested_provider_id=provider_id,
                current_primary_id=self.current_primary_id,
                migration_required=True,
                detail=health.detail or "destination provider is unhealthy",
            )

        source = self.primary_provider
        records = list(source.export())
        self._assert_secret_safe(records)
        source_hashes = tuple(sorted(record.content_hash for record in records))
        dry_run = destination.import_dry_run(records)
        destination_hashes = tuple(
            sorted(str(value) for value in dry_run.get("hashes", []))
        )
        destination_count = int(dry_run.get("count", -1))
        if destination_count != len(records) or destination_hashes != source_hashes:
            return ProviderSwitchResult(
                requested_provider_id=provider_id,
                current_primary_id=self.current_primary_id,
                migration_required=True,
                source_count=len(records),
                destination_count=destination_count,
                detail="provider dry run count or hashes did not match",
            )

        token = secrets.token_urlsafe(24)
        payload = {
            "provider_id": provider_id,
            "source_provider_id": self.current_primary_id,
            "count": len(records),
            "hashes": list(source_hashes),
            "token_hash": _token_hash(token),
        }
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (self.SWITCH_KEY_PREFIX + provider_id, dumps(payload)),
        )
        self._save_requested_primary(provider_id)
        return ProviderSwitchResult(
            requested_provider_id=provider_id,
            current_primary_id=self.current_primary_id,
            migration_required=True,
            migration_verified=True,
            verification_token=token,
            source_count=len(records),
            destination_count=destination_count,
            detail="provider migration dry run verified; explicit commit required",
        )

    def commit_provider_switch(
        self,
        provider_id: str,
        verification_token: str,
    ) -> ProviderSwitchResult:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (self.SWITCH_KEY_PREFIX + provider_id,),
        ).fetchone()
        payload = loads(row["value_json"], {}) if row else {}
        if not payload or payload.get("token_hash") != _token_hash(verification_token):
            raise ValueError("provider switch verification token is invalid")
        if payload.get("source_provider_id") != self.current_primary_id:
            raise ValueError("provider switch source changed; run verification again")

        destination = self.registry.get(provider_id)
        health = self._provider_health(destination)
        if not health.healthy:
            raise RuntimeError("destination provider became unhealthy")
        source = self.primary_provider
        records = list(source.export())
        self._assert_secret_safe(records)
        expected_hashes = tuple(sorted(str(value) for value in payload.get("hashes", [])))
        actual_hashes = tuple(sorted(record.content_hash for record in records))
        if len(records) != int(payload.get("count", -1)) or actual_hashes != expected_hashes:
            raise RuntimeError("memory export changed; run provider verification again")
        imported_count = destination.import_records(records)
        destination_export = list(destination.export())
        self._assert_secret_safe(destination_export)
        destination_hashes = tuple(sorted(record.content_hash for record in destination_export))
        if imported_count != len(records) or destination_hashes != expected_hashes:
            raise RuntimeError("destination import verification failed")

        self.registry.set_primary(provider_id)
        self.current_primary_id = provider_id
        self._save_primary(provider_id)
        self._clear_requested_primary()
        self.conn.execute(
            "DELETE FROM app_settings WHERE key=?",
            (self.SWITCH_KEY_PREFIX + provider_id,),
        )
        return ProviderSwitchResult(
            requested_provider_id=provider_id,
            current_primary_id=provider_id,
            switched=True,
            migration_required=False,
            migration_verified=True,
            source_count=len(records),
            destination_count=len(destination_export),
            detail="provider switch committed after count and hash verification",
        )

    @staticmethod
    def _provider_health(provider: MemoryProviderAdapter) -> ProviderHealth:
        try:
            return ProviderHealth.model_validate(provider.health())
        except Exception:
            return ProviderHealth(healthy=False, detail="provider health check failed")

    @staticmethod
    def _assert_secret_safe(records: list[MemoryExportRecord]) -> None:
        if any(scan_memory_secrets(record.content).detected for record in records):
            raise RuntimeError("memory provider export contains rejected secret material")

    def _saved_primary_id(self) -> str:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (self.PRIMARY_KEY,),
        ).fetchone()
        payload = loads(row["value_json"], {}) if row else {}
        return str(payload.get("provider_id") or "builtin")

    def _requested_primary_id(self) -> str:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (self.REQUESTED_PRIMARY_KEY,),
        ).fetchone()
        payload = loads(row["value_json"], {}) if row else {}
        return str(payload.get("provider_id") or "")

    def _save_primary(self, provider_id: str) -> None:
        self._save_provider_setting(self.PRIMARY_KEY, provider_id)

    def _save_requested_primary(self, provider_id: str) -> None:
        self._save_provider_setting(self.REQUESTED_PRIMARY_KEY, provider_id)

    def _save_provider_setting(self, key: str, provider_id: str) -> None:
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (key, dumps({"provider_id": provider_id})),
        )

    def _clear_requested_primary(self) -> None:
        self.conn.execute(
            "DELETE FROM app_settings WHERE key=?",
            (self.REQUESTED_PRIMARY_KEY,),
        )


def _record_to_item(record: MemoryExportRecord) -> MemoryItem:
    return MemoryItem(
        id=record.id,
        category=record.category,
        scope=record.scope,
        content=record.content,
        normalized_key=record.normalized_key,
        confidence=record.confidence,
        importance=record.importance,
        status=record.status,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        expires_at=record.expires_at,
        supersedes_id=record.supersedes_id,
        pinned=record.pinned,
        metadata=record.metadata,
    )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _valid_at(item: RetrievedMemoryItem, as_of: datetime) -> bool:
    try:
        if item.valid_from and _parse_timestamp(item.valid_from) > as_of:
            return False
        if item.valid_to and _parse_timestamp(item.valid_to) <= as_of:
            return False
        if item.expires_at and _parse_timestamp(item.expires_at) <= as_of:
            return False
    except ValueError:
        return False
    return True


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
