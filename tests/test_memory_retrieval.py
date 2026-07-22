from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.memory.context import MemoryContextAssembler
from langdrill_agent.memory.models import MemoryCandidate
from langdrill_agent.memory.repository import MemoryRepository
from langdrill_agent.memory.retrieval import MemoryRetrievalQuery, MemoryRetrievalService


def _add(
    repo: MemoryRepository,
    *,
    content: str,
    category: str = "semantic",
    scope: str = "global",
    confidence: float = 0.9,
    importance: float = 0.8,
    pinned: bool = False,
    expires_at: str | None = None,
):
    return repo.commit(
        repo.stage(
            MemoryCandidate(
                category=category,
                scope=scope,
                content=content,
                normalized_key=f"{category}:{content[:20]}",
                confidence=confidence,
                importance=importance,
                pinned=pinned,
                expires_at=expires_at,
                evidence_ids=["message:1"],
            )
        )
    )


def test_expired_temporal_memory_is_not_recalled(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = MemoryRepository(conn)
        expired = _add(
            repo,
            content="Exam deadline reminder for September",
            category="temporal",
            expires_at="2026-07-21T12:00:00",
        )
        active = _add(
            repo,
            content="Exam deadline reminder for October",
            category="temporal",
            expires_at="2026-10-01T00:00:00",
        )
        result = MemoryRetrievalService(conn).retrieve(
            MemoryRetrievalQuery(
                text="exam deadline reminder",
                as_of="2026-07-22T12:00:00",
            )
        )

        ids = {item.id for item in result.items}
        assert expired.id not in ids
        assert active.id in ids


def test_scope_filter_excludes_other_exam(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = MemoryRepository(conn)
        cet4 = _add(repo, content="Reading strategy for main ideas", scope="exam:cet4")
        cet6 = _add(repo, content="Reading strategy for main ideas", scope="exam:cet6")
        result = MemoryRetrievalService(conn).retrieve(
            MemoryRetrievalQuery(
                text="reading strategy main ideas",
                scope="exam:cet4",
            )
        )

        assert [item.id for item in result.items] == [cet4.id]
        assert cet6.id not in {item.id for item in result.items}


def test_core_budget_prefers_pinned_high_confidence(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = MemoryRepository(conn)
        pinned = _add(
            repo,
            content="User explicitly prefers concise explanations with examples",
            category="core",
            pinned=True,
            confidence=1,
            importance=1,
        )
        for index in range(8):
            _add(
                repo,
                content=f"Lower priority profile observation number {index} with extra details",
                category="core",
                confidence=0.71,
                importance=0.2,
            )
        context = MemoryContextAssembler(conn).build_core(token_budget=24)

        assert context.token_count <= 24
        assert pinned.id in {item.id for item in context.items}
        assert any(item.pinned for item in context.items)


def test_recall_context_is_structured_derived_memory(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = MemoryRepository(conn)
        item = _add(
            repo,
            content="User prefers vocabulary examples from technology articles",
            category="preference",
        )
        context = MemoryContextAssembler(conn).build(
            MemoryRetrievalQuery(text="vocabulary examples technology")
        )

        assert context.trust == "derived_memory"
        assert context.items[0].id == item.id
        assert context.items[0].evidence_ids == ["message:1"]
        assert context.rules
