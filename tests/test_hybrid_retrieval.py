from pathlib import Path

from langdrill_agent.db import connect, init_db
import httpx

from langdrill_agent.knowledge.embeddings import (
    EmbeddingConfig,
    EmbeddingIndexService,
    OpenAICompatibleEmbeddingProvider,
    maximal_marginal_relevance,
    reciprocal_rank_fusion,
)
from langdrill_agent.knowledge.models import KnowledgeChunkInput
from langdrill_agent.knowledge.repository import KnowledgeRepository
from langdrill_agent.knowledge.retrieval import KnowledgeRetrievalService, RetrievalQuery


class FakeEmbeddingProvider:
    def __init__(self, identity: str = "fake:v1") -> None:
        self.identity = identity

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "consecutive" in lowered or "continuous" in lowered:
                vectors.append([1.0, 0.0])
            elif "budget" in lowered or "finance" in lowered:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.0, 0.0])
        return vectors


def test_reciprocal_rank_fusion_keeps_exact_and_semantic_hits() -> None:
    fused = reciprocal_rank_fusion([["exact", "other"], ["semantic", "exact"]], k=60)

    assert fused[0][0] == "exact"
    assert {item[0] for item in fused[:2]} == {"exact", "semantic"}


def test_mmr_prefers_relevant_but_diverse_vectors() -> None:
    selected = maximal_marginal_relevance(
        query_vector=[1.0, 0.0],
        candidates={
            "exact": [1.0, 0.0],
            "duplicate": [0.99, 0.01],
            "diverse": [0.7, 0.7],
        },
        limit=2,
        lambda_mult=0.45,
    )

    assert selected == ["exact", "diverse"]


def test_openai_compatible_embedding_provider_parses_indexed_vectors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="embed-v1",
        client=client,
    )

    assert provider.embed(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert provider.identity == "https://example.test/v1::embed-v1"


def test_hybrid_retrieval_keeps_semantic_hit_and_persists_identity(tmp_path: Path) -> None:
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
        chunks = repo.upsert_chunks(
            document.id,
            [
                KnowledgeChunkInput(
                    ordinal=0,
                    content="following continuously",
                    content_hash="sha256:c1",
                    token_count=10,
                ),
                KnowledgeChunkInput(
                    ordinal=1,
                    content="finance planning and budget evidence",
                    content_hash="sha256:c2",
                    token_count=10,
                ),
            ],
        )
        provider = FakeEmbeddingProvider()
        indexed = EmbeddingIndexService(conn).index_chunks(provider, chunks)
        result = KnowledgeRetrievalService(
            conn,
            embedding_provider=provider,
            embedding_config=EmbeddingConfig(provider="fake", model="v1", dimensions=2, enabled=True),
        ).search_result(RetrievalQuery(text="consecutive", top_k=5, token_budget=500))

        assert indexed == 2
        assert result.mode == "hybrid"
        assert result.items[0].content == "following continuously"
        assert conn.execute("SELECT COUNT(*) FROM knowledge_embeddings").fetchone()[0] == 2


def test_changed_embedding_identity_falls_back_to_fts(tmp_path: Path) -> None:
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
        chunks = repo.upsert_chunks(
            document.id,
            [
                KnowledgeChunkInput(
                    ordinal=0,
                    content="following continuously",
                    content_hash="sha256:c1",
                    token_count=10,
                )
            ],
        )
        EmbeddingIndexService(conn).index_chunks(FakeEmbeddingProvider("fake:v1"), chunks)
        result = KnowledgeRetrievalService(
            conn,
            embedding_provider=FakeEmbeddingProvider("fake:v2"),
            embedding_config=EmbeddingConfig(provider="fake", model="v2", dimensions=2, enabled=True),
        ).search_result(RetrievalQuery(text="consecutive", top_k=5, token_budget=500))

        assert result.mode == "fts"
        assert result.items == []


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
