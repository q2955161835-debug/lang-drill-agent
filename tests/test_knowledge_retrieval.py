from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.knowledge.models import KnowledgeChunkInput
from langdrill_agent.knowledge.repository import KnowledgeRepository
from langdrill_agent.knowledge.retrieval import (
    KnowledgeRetrievalService,
    RetrievalQuery,
)


def _create_document(repo: KnowledgeRepository, title: str, content: str) -> str:
    document = repo.create_document(
        title=title,
        source_name=f"{title.lower()}.md",
        mime_type="text/markdown",
        content_hash=f"sha256:{title.lower()}",
        status="ready",
    )
    repo.upsert_chunks(
        document.id,
        [
            KnowledgeChunkInput(
                ordinal=0,
                heading="Vocabulary",
                page_start=2,
                page_end=2,
                content=content,
                content_hash=f"sha256:{title.lower()}-chunk",
                token_count=20,
            )
        ],
    )
    return document.id


def test_fts_finds_exact_term_and_returns_page(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = KnowledgeRepository(conn)
        _create_document(repo, "Unit 1", "consecutive means following continuously")

        results = KnowledgeRetrievalService(conn).search(
            RetrievalQuery(text="consecutive", top_k=5, token_budget=500)
        )

        assert results[0].citation.page_start == 2
        assert results[0].citation.document_title == "Unit 1"
        assert "consecutive" in results[0].content.lower()
        assert results[0].content_hash.startswith("sha256:")


def test_document_filter_prevents_cross_document_results(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = KnowledgeRepository(conn)
        first_id = _create_document(repo, "First", "shared alpha material")
        _create_document(repo, "Second", "shared beta material")

        results = KnowledgeRetrievalService(conn).search(
            RetrievalQuery(text="shared", document_ids=[first_id], top_k=10)
        )

        assert {item.document_id for item in results} == {first_id}


def test_retrieval_records_ranked_and_injected_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = KnowledgeRepository(conn)
        _create_document(repo, "Budget", "budget evidence first")

        results = KnowledgeRetrievalService(conn).search(
            RetrievalQuery(text="budget", top_k=5, token_budget=1, trace_id="trace-1")
        )
        event = conn.execute("SELECT * FROM retrieval_events").fetchone()

        assert len(results) == 1
        assert event["trace_id"] == "trace-1"
        assert results[0].id in event["result_json"]
        assert results[0].id in event["injected_json"]
