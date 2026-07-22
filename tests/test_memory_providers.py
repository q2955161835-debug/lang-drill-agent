import hashlib
from pathlib import Path

import pytest

from langdrill_agent.db import connect, init_db
from langdrill_agent.memory.hooks import MemoryHooks
from langdrill_agent.memory.models import MemoryCandidate, MemoryItem
from langdrill_agent.memory.providers import (
    BuiltinMemoryProvider,
    MemoryExportRecord,
    MemoryProviderConflict,
    MemoryProviderRegistry,
    ProviderHealth,
)
from langdrill_agent.memory.retrieval import (
    MemoryRetrievalResult,
    RetrievedMemoryItem,
)
from langdrill_agent.memory.service import (
    MemoryService,
    register_memory_provider_factory,
    unregister_memory_provider_factory,
)
from langdrill_agent.utils import new_id


class FakeProvider:
    def __init__(
        self,
        provider_id: str,
        *,
        healthy: bool,
        records=None,
        retrieval_result: MemoryRetrievalResult | None = None,
    ) -> None:
        self.id = provider_id
        self._healthy = healthy
        self._records = list(records or [])
        self._retrieval_result = retrieval_result or MemoryRetrievalResult(items=[])
        self.retrieve_calls = 0

    def health(self) -> ProviderHealth:
        return ProviderHealth(healthy=self._healthy, detail="test provider")

    def retrieve(self, query):
        self.retrieve_calls += 1
        return self._retrieval_result

    def stage_candidate(self, candidate):
        candidate_id = candidate.id or new_id("external-candidate")
        if not hasattr(self, "_candidates"):
            self._candidates = {}
        self._candidates[candidate_id] = candidate
        return candidate_id

    def commit(self, candidate_id):
        candidate = self._candidates[candidate_id]
        item = MemoryItem(
            id=new_id("external-memory"),
            category=candidate.category,
            scope=candidate.scope,
            content=candidate.content,
            normalized_key=candidate.normalized_key,
            confidence=candidate.confidence,
            importance=candidate.importance,
            pinned=candidate.pinned,
            metadata=candidate.metadata,
        )
        payload = "\n".join(
            [item.category, item.scope, item.normalized_key, item.content, item.status]
        )
        self._records.append(
            MemoryExportRecord(
                **item.model_dump(),
                evidence_ids=candidate.evidence_ids,
                content_hash="sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            )
        )
        return item

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


def test_memory_hooks_write_only_to_committed_external_primary(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)
    external = FakeProvider("external-hooks", healthy=True)
    register_memory_provider_factory("external-hooks", lambda _conn: external)

    try:
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
            prepared = service.configure_primary("external-hooks")
            service.commit_provider_switch(
                "external-hooks",
                prepared.verification_token,
            )

            result = MemoryHooks(conn).on_turn_end(
                user="Remember that I prefer concise explanations",
                assistant="Understood.",
            )

            assert result is not None
            recalled = MemoryHooks(conn).recall("CET-4", scope="global")
            assert recalled.items == []
            assert external.retrieve_calls == 1
            assert len(list(external.export())) == 2
            assert len(service.builtin.repository.list_items()) == 1
    finally:
        unregister_memory_provider_factory("external-hooks")


def test_external_recall_is_revalidated_against_scope_category_secret_and_budget(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)
    items = [
        RetrievedMemoryItem(
            id="allowed",
            category="profile",
            scope="global",
            content="User has a durable exam preference that exceeds the tiny budget",
            token_count=999,
        ),
        RetrievedMemoryItem(
            id="wrong-category",
            category="procedural",
            scope="global",
            content="Unrelated process memory",
        ),
        RetrievedMemoryItem(
            id="wrong-scope",
            category="profile",
            scope="exam:CET-6",
            content="Other exam profile",
        ),
        RetrievedMemoryItem(
            id="expired",
            category="profile",
            scope="global",
            content="Expired exam profile",
            expires_at="2020-01-01T00:00:00Z",
        ),
        RetrievedMemoryItem(
            id="secret",
            category="profile",
            scope="global",
            content="OPENAI_API_KEY=sk-external-secret-value",
        ),
    ]
    external = FakeProvider(
        "external-boundary",
        healthy=True,
        retrieval_result=MemoryRetrievalResult(mode="hybrid", items=items, token_count=9999),
    )
    register_memory_provider_factory("external-boundary", lambda _conn: external)

    try:
        with connect(db_path) as conn:
            service = MemoryService(conn)
            prepared = service.configure_primary("external-boundary")
            service.commit_provider_switch(
                "external-boundary",
                prepared.verification_token,
            )

            recalled = MemoryHooks(conn).recall(
                "exam",
                scope="exam:CET-4",
                categories=["profile"],
                token_budget=5,
            )

            assert [item.id for item in recalled.items] == ["allowed"]
            assert recalled.token_count <= 5
            assert recalled.items[0].token_count <= 5
            assert len(recalled.items[0].content) <= 20
            assert "secret" not in recalled.items[0].content.casefold()
    finally:
        unregister_memory_provider_factory("external-boundary")


def test_provider_switch_can_round_trip_back_to_builtin(tmp_path: Path) -> None:
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
        external = FakeProvider("external-round-trip", healthy=True)
        service.register_provider(external)
        prepared_external = service.configure_primary("external-round-trip")
        service.commit_provider_switch(
            "external-round-trip",
            prepared_external.verification_token,
        )
        service.commit_candidate(
            MemoryCandidate(
                category="preference",
                content="User prefers concise examples",
                normalized_key="preference:examples",
                confidence=0.9,
            )
        )

        prepared_builtin = service.configure_primary("builtin")
        committed_builtin = service.commit_provider_switch(
            "builtin",
            prepared_builtin.verification_token,
        )

        assert committed_builtin.switched is True
        assert service.current_primary_id == "builtin"
        assert len(service.builtin.repository.list_items()) == 2


def test_unhealthy_committed_provider_requires_reverification_before_reactivation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)
    external = FakeProvider("external-fallback", healthy=True)
    register_memory_provider_factory("external-fallback", lambda _conn: external)

    try:
        with connect(db_path) as conn:
            service = MemoryService(conn)
            prepared = service.configure_primary("external-fallback")
            service.commit_provider_switch(
                "external-fallback",
                prepared.verification_token,
            )
            assert service.current_primary_id == "external-fallback"

            external._healthy = False
            fallback = MemoryService(conn)
            assert fallback.current_primary_id == "builtin"
            assert fallback.status().migration_required is True

            external._healthy = True
            recovered = MemoryService(conn)
            assert recovered.current_primary_id == "builtin"
            assert recovered.status().requested_primary_id == "external-fallback"
    finally:
        unregister_memory_provider_factory("external-fallback")
