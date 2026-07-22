from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.memory.models import MemoryCandidate
from langdrill_agent.memory.repository import MemoryRepository


def candidate(content: str, *, normalized_key: str = "preference:explanation") -> MemoryCandidate:
    return MemoryCandidate(
        category="preference",
        scope="global",
        content=content,
        normalized_key=normalized_key,
        confidence=0.9,
        importance=0.8,
        evidence_ids=["message:1"],
    )


def test_update_preserves_memory_history(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = MemoryRepository(conn)
        item = repo.commit(repo.stage(candidate("User prefers concise explanations")))
        updated = repo.update(item.id, "User prefers concise explanations with examples")
        revisions = repo.revisions(item.id)

        assert updated.content.endswith("with examples")
        assert [revision.operation for revision in revisions] == ["ADD", "UPDATE"]
        assert revisions[0].content == "User prefers concise explanations"


def test_supersede_keeps_old_memory(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = MemoryRepository(conn)
        old = repo.commit(
            repo.stage(
                candidate(
                    "Exam deadline is 2026-09-01",
                    normalized_key="profile:exam_deadline",
                )
            )
        )
        new = repo.supersede(
            old.id,
            candidate(
                "Exam deadline is 2026-10-01",
                normalized_key="profile:exam_deadline",
            ),
        )

        assert repo.get(old.id).status == "superseded"
        assert new.supersedes_id == old.id
        assert [revision.operation for revision in repo.revisions(old.id)] == [
            "ADD",
            "SUPERSEDE",
        ]


def test_soft_delete_and_restore_refresh_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = MemoryRepository(conn)
        item = repo.commit(repo.stage(candidate("User prefers worked examples")))
        repo.delete(item.id)

        assert repo.get(item.id).status == "deleted"
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_item_fts WHERE memory_id=?",
            (item.id,),
        ).fetchone()[0] == 0

        restored = repo.restore(item.id)
        assert restored.status == "active"
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_item_fts WHERE memory_id=?",
            (item.id,),
        ).fetchone()[0] == 1
        assert [revision.operation for revision in repo.revisions(item.id)] == [
            "ADD",
            "DELETE",
            "RESTORE",
        ]
