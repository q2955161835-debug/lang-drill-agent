from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import connect, init_db
from langdrill_agent.memory.models import MemoryCandidate
from langdrill_agent.memory.repository import MemoryRepository


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "memory-api.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)
    return TestClient(app)


def seed_item(*, content: str = "User prefers concise examples") -> str:
    with connect() as conn:
        repository = MemoryRepository(conn)
        item = repository.commit(
            repository.stage(
                MemoryCandidate(
                    category="preference",
                    content=content,
                    normalized_key="preference:examples",
                    confidence=0.95,
                    importance=0.8,
                    evidence_ids=["message:1"],
                )
            )
        )
        return item.id


def seed_candidate() -> str:
    with connect() as conn:
        candidate = MemoryRepository(conn).stage(
            MemoryCandidate(
                category="learning_weakness",
                content="User repeatedly struggles with conditionals",
                normalized_key="weakness:conditionals",
                confidence=0.9,
                importance=0.8,
                reason="approval_required",
                evidence_ids=[
                    "attempt:session-1:q-1:conditionals",
                    "attempt:session-2:q-2:conditionals",
                    "attempt:session-3:q-3:conditionals",
                ],
            )
        )
        return candidate.id


@pytest.fixture
def seeded_memories() -> None:
    """Seed one active memory item per internal category across all groups."""
    categories = [
        ("core", "core:identity", "User identity anchor"),
        ("profile", "profile:background", "User background summary"),
        ("semantic", "semantic:fact", "User studies French"),
        ("episodic", "episodic:session-1", "Completed reading practice"),
        ("temporal", "temporal:exam-date", "Exam deadline 2026-12-01"),
        ("learning_weakness", "weakness:conditionals", "Struggles with conditionals"),
        ("procedural", "procedural:flow", "User prefers spaced repetition"),
        ("preference", "preference:examples", "User prefers concise examples"),
    ]
    with connect() as conn:
        repository = MemoryRepository(conn)
        for category, normalized_key, content in categories:
            repository.commit(
                repository.stage(
                    MemoryCandidate(
                        category=category,
                        content=content,
                        normalized_key=normalized_key,
                        confidence=0.9,
                        importance=0.7,
                        evidence_ids=[f"message:{category}"],
                    )
                )
            )


def test_disabling_memory_keeps_items(client: TestClient) -> None:
    item_id = seed_item()

    saved = client.post(
        "/api/memory/settings",
        json={"enabled": False, "capture_enabled": False, "recall_enabled": False},
    )
    items = client.get("/api/memory/items")

    assert saved.status_code == 200
    assert saved.json()["settings"]["enabled"] is False
    assert items.status_code == 200
    assert items.json()["items"][0]["id"] == item_id


def test_candidate_review_exposes_evidence_and_approves(client: TestClient) -> None:
    candidate_id = seed_candidate()

    pending = client.get("/api/memory/candidates")
    approved = client.post(
        f"/api/memory/candidates/{candidate_id}/review",
        json={"action": "approve"},
    )

    assert pending.status_code == 200
    assert pending.json()["candidates"][0]["evidence_count"] == 3
    assert approved.status_code == 200
    assert approved.json()["item"]["category"] == "learning_weakness"
    assert approved.json()["candidate"]["status"] == "committed"


def test_approving_conflicting_candidate_supersedes_existing_item(client: TestClient) -> None:
    existing_id = seed_item(content="User prefers concise examples")
    with connect() as conn:
        candidate = MemoryRepository(conn).stage(
            MemoryCandidate(
                category="preference",
                content="User prefers detailed worked examples",
                normalized_key="preference:examples",
                confidence=0.95,
                importance=0.9,
                reason="approval_required",
                evidence_ids=["message:conflict"],
            )
        )

    response = client.post(
        f"/api/memory/candidates/{candidate.id}/review",
        json={"action": "approve"},
    )

    assert response.status_code == 200
    replacement_id = response.json()["item"]["id"]
    with connect() as conn:
        repository = MemoryRepository(conn)
        assert repository.get(existing_id).status == "superseded"
        assert repository.get(replacement_id).supersedes_id == existing_id


def test_item_lifecycle_keeps_evidence_and_revisions(client: TestClient) -> None:
    item_id = seed_item()

    updated = client.post(
        f"/api/memory/items/{item_id}",
        json={"content": "User prefers concise worked examples", "pinned": True},
    )
    archived = client.post(
        f"/api/memory/items/{item_id}/action",
        json={"action": "archive"},
    )
    restored = client.post(
        f"/api/memory/items/{item_id}/action",
        json={"action": "restore"},
    )
    detail = client.get(f"/api/memory/items/{item_id}")

    assert updated.json()["item"]["pinned"] is True
    assert archived.json()["item"]["status"] == "archived"
    assert restored.json()["item"]["status"] == "active"
    assert detail.json()["evidence"][0]["evidence_ref"] == "message:1"
    assert [row["operation"] for row in detail.json()["revisions"]] == [
        "ADD",
        "UPDATE",
        "ARCHIVE",
        "RESTORE",
    ]


def test_export_reindex_and_secret_safe_import(client: TestClient) -> None:
    item_id = seed_item()

    exported = client.get("/api/memory/export")
    reindexed = client.post("/api/memory/reindex", json={})
    rejected = client.post(
        "/api/memory/import",
        json={
            "records": [
                {
                    "category": "profile",
                    "scope": "global",
                    "content": "OPENAI_API_KEY=sk-super-secret-value",
                    "normalized_key": "profile:unsafe",
                    "confidence": 1,
                    "importance": 1,
                }
            ]
        },
    )

    assert exported.status_code == 200
    assert exported.json()["schema_version"] == 1
    assert exported.json()["records"][0]["id"] == item_id
    assert reindexed.json()["indexed_count"] == 1
    assert rejected.status_code == 422
    with connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_items WHERE normalized_key='profile:unsafe'"
        ).fetchone()[0] == 0


def test_import_preserves_superseded_status(client: TestClient) -> None:
    response = client.post(
        "/api/memory/import",
        json={
            "records": [
                {
                    "category": "profile",
                    "scope": "global",
                    "content": "Previous exam target was CET-4",
                    "normalized_key": "profile:previous-exam",
                    "confidence": 0.9,
                    "importance": 0.7,
                    "status": "superseded",
                }
            ]
        },
    )
    items = client.get("/api/memory/items?status=superseded")

    assert response.status_code == 200
    assert items.json()["items"][0]["status"] == "superseded"


def test_approving_polluted_candidate_rejects_secret_without_echo(client: TestClient) -> None:
    with connect() as conn:
        candidate = MemoryRepository(conn).stage(
            MemoryCandidate(
                category="profile",
                content="OPENAI_API_KEY=sk-secret-candidate-value",
                normalized_key="profile:polluted",
                confidence=1,
                importance=1,
            )
        )

    response = client.post(
        f"/api/memory/candidates/{candidate.id}/review",
        json={"action": "approve"},
    )

    assert response.status_code == 422
    assert "sk-secret-candidate-value" not in response.text
    with connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_items WHERE normalized_key='profile:polluted'"
        ).fetchone()[0] == 0


def test_unknown_provider_cannot_replace_builtin_primary(client: TestClient) -> None:
    item_id = seed_item()

    prepared = client.post(
        "/api/memory/provider/prepare",
        json={"provider_id": "missing-provider"},
    )
    status = client.get("/api/memory/status")

    assert prepared.status_code == 200
    assert prepared.json()["result"]["switched"] is False
    assert prepared.json()["result"]["migration_required"] is True
    assert status.json()["provider"]["current_primary_id"] == "builtin"
    with connect() as conn:
        assert MemoryRepository(conn).get(item_id).status == "active"


def test_status_exposes_mode_groups_and_effective_budget(client: TestClient) -> None:
    payload = client.get("/api/memory/status").json()

    assert payload["settings"]["mode"] == "standard"
    assert payload["settings"]["group_enabled"]["about_me"] is True
    assert payload["effective_budget"]["configured_limit"] == 10_000
    assert payload["group_counts"].keys() == {
        "about_me",
        "learning_history",
        "usage_habits",
    }


def test_group_clear_requires_confirmation(client: TestClient) -> None:
    response = client.post(
        "/api/memory/groups/learning_history/clear",
        json={"confirmed": False},
    )

    assert response.status_code == 400


def test_group_clear_archives_only_mapped_categories(
    client: TestClient,
    seeded_memories: None,
) -> None:
    response = client.post(
        "/api/memory/groups/learning_history/clear",
        json={"confirmed": True},
    )

    assert response.status_code == 200
    assert set(response.json()["categories"]) == {
        "episodic",
        "temporal",
        "learning_weakness",
    }
    with connect() as conn:
        archived_categories = {
            row["category"]
            for row in conn.execute(
                "SELECT category FROM memory_items WHERE status='archived'"
            ).fetchall()
        }
        assert archived_categories == {
            "episodic",
            "temporal",
            "learning_weakness",
        }
        active_categories = {
            row["category"]
            for row in conn.execute(
                "SELECT category FROM memory_items WHERE status='active'"
            ).fetchall()
        }
        assert active_categories == {
            "core",
            "profile",
            "semantic",
            "procedural",
            "preference",
        }
