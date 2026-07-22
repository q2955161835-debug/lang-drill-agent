from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.knowledge.embeddings import reciprocal_rank_fusion
from langdrill_agent.knowledge.models import KnowledgeChunkInput
from langdrill_agent.knowledge.repository import KnowledgeRepository
from langdrill_agent.knowledge.retrieval import KnowledgeRetrievalService, RetrievalQuery


def test_reciprocal_rank_fusion_keeps_exact_and_semantic_hits() -> None:
    fused = reciprocal_rank_fusion([["exact", "other"], ["semantic", "exact"]], k=60)

    assert fused[0][0] == "exact"
    assert {item[0] for item in fused[:2]} == {"exact", "semantic"}


def test_missing_embedding_provider_returns_fts_results(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = KnowledgeRepository(conn)
        document = repo.create_document(
            title="Unit 1",
            source_name="unit1.md",
            mime_type="text/markdown",
            content_hash="sha256:abc",
            status="ready",
        )
        repo.upsert_chunks(
            document.id,
            [
                KnowledgeChunkInput(
                    ordinal=0,
                    content="consecutive means following continuously",
                    content_hash="sha256:c1",
                    token_count=10,
                )
            ],
        )

        result = KnowledgeRetrievalService(conn).search_result(
            RetrievalQuery(text="consecutive", top_k=3)
        )

        assert result.mode == "fts"
        assert result.items
