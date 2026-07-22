from pathlib import Path

import pytest

from langdrill_agent.db import connect, init_db
from langdrill_agent.memory.models import MemoryCandidate
from langdrill_agent.memory.providers import (
    BuiltinMemoryProvider,
    MemoryProviderConflict,
    MemoryProviderRegistry,
    ProviderHealth,
)
from langdrill_agent.memory.service import MemoryService


class FakeProvider:
    def __init__(self, provider_id: str, *, healthy: bool, records=None) -> None:
        self.id = provider_id
        self._healthy = healthy
        self._records = list(records or [])

    def health(self) -> ProviderHealth:
        return ProviderHealth(healthy=self._healthy, detail="test provider")

    def retrieve(self, query):
        return []

    def stage_candidate(self, candidate):
        return candidate.id or "candidate"

    def commit(self, candidate_id):
        raise NotImplementedError

    def update(self, memory_id, content):
        raise NotImplementedError

    def delete(self, memory_id):
        raise NotImplementedError

    def export(self):
        return iter(self._records)

    def import_dry_run(self, records):
        records = list(records)
        return {"count": len(records), "hashes": [record.content_hash for record in records]}

    def import_records(self, records):
        self._records = list(records)
        return len(self._records)

    def reindex(self):
        return None


def test_only_one_provider_can_be_primary(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        registry = MemoryProviderRegistry()
        registry.register("builtin", BuiltinMemoryProvider(conn), primary=True)

        with pytest.raises(MemoryProviderConflict):
            registry.register("other", FakeProvider("other", healthy=True), primary=True)


def test_unhealthy_external_provider_does_not_delete_local_memory(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        service = MemoryService(conn)
        local = service.builtin.commit_candidate(
            MemoryCandidate(
                category="preference",
                content="User prefers concise answers",
                normalized_key="preference:answers",
                confidence=0.9,
            )
        )
        service.register_provider(FakeProvider("external-unhealthy", healthy=False))
        result = service.configure_primary("external-unhealthy")

        assert result.migration_required is True
        assert result.switched is False
        assert service.current_primary_id == "builtin"
        assert service.builtin.repository.get(local.id).content == "User prefers concise answers"


def test_switch_requires_verified_dry_run_and_explicit_commit(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        service = MemoryService(conn)
        service.builtin.commit_candidate(
            MemoryCandidate(
                category="profile",
                content="Exam is CET-4",
                normalized_key="profile:exam",
                confidence=1,
            )
        )
        external = FakeProvider("external", healthy=True)
        service.register_provider(external)

        prepared = service.configure_primary("external")
        assert prepared.switched is False
        assert prepared.migration_verified is True
        assert service.current_primary_id == "builtin"

        committed = service.commit_provider_switch("external", prepared.verification_token)
        assert committed.switched is True
        assert service.current_primary_id == "external"
        assert len(list(external.export())) == 1
