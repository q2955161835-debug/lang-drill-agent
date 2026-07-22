from __future__ import annotations

import hashlib
import secrets
import sqlite3

from pydantic import BaseModel

from ..utils import dumps, loads
from .providers import (
    BuiltinMemoryProvider,
    MemoryProviderAdapter,
    MemoryProviderRegistry,
    ProviderHealth,
)


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
    migration_required: bool = False


class MemoryService:
    PRIMARY_KEY = "memory.provider.primary"
    SWITCH_KEY_PREFIX = "memory.provider.switch."

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.registry = MemoryProviderRegistry()
        self.builtin = BuiltinMemoryProvider(conn)
        self.registry.register("builtin", self.builtin, primary=True)
        saved_primary = self._saved_primary_id()
        self.current_primary_id = saved_primary if saved_primary == "builtin" else "builtin"

    def register_provider(self, provider: MemoryProviderAdapter) -> None:
        if provider.id == "builtin":
            raise ValueError("builtin memory provider is already registered")
        self.registry.register(provider.id, provider)

    def status(self) -> MemoryServiceStatus:
        health = {
            provider_id: provider.health()
            for provider_id, provider in self.registry.providers().items()
        }
        requested = self._saved_primary_id()
        migration_required = bool(
            requested
            and requested != self.current_primary_id
            and (
                requested not in health
                or not health[requested].healthy
            )
        )
        return MemoryServiceStatus(
            current_primary_id=self.current_primary_id,
            providers=health,
            migration_required=migration_required,
        )

    def configure_primary(self, provider_id: str) -> ProviderSwitchResult:
        if provider_id == self.current_primary_id:
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
        health = destination.health()
        if not health.healthy:
            self._save_requested_primary(provider_id)
            return ProviderSwitchResult(
                requested_provider_id=provider_id,
                current_primary_id=self.current_primary_id,
                migration_required=True,
                detail=health.detail or "destination provider is unhealthy",
            )

        source = self.registry.get(self.current_primary_id)
        records = list(source.export())
        source_hashes = tuple(record.content_hash for record in records)
        dry_run = destination.import_dry_run(records)
        destination_hashes = tuple(str(value) for value in dry_run.get("hashes", []))
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
        health = destination.health()
        if not health.healthy:
            raise RuntimeError("destination provider became unhealthy")
        source = self.registry.get(self.current_primary_id)
        records = list(source.export())
        expected_hashes = tuple(str(value) for value in payload.get("hashes", []))
        actual_hashes = tuple(record.content_hash for record in records)
        if len(records) != int(payload.get("count", -1)) or actual_hashes != expected_hashes:
            raise RuntimeError("memory export changed; run provider verification again")
        imported_count = destination.import_records(records)
        destination_export = list(destination.export())
        destination_hashes = tuple(record.content_hash for record in destination_export)
        if imported_count != len(records) or destination_hashes != expected_hashes:
            raise RuntimeError("destination import verification failed")

        self.registry.set_primary(provider_id)
        self.current_primary_id = provider_id
        self._save_requested_primary(provider_id)
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

    def _saved_primary_id(self) -> str:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (self.PRIMARY_KEY,),
        ).fetchone()
        payload = loads(row["value_json"], {}) if row else {}
        return str(payload.get("provider_id") or "builtin")

    def _save_requested_primary(self, provider_id: str) -> None:
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (self.PRIMARY_KEY, dumps({"provider_id": provider_id})),
        )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
