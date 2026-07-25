"""Identity-bound embedding runtime and hybrid retrieval fallback tests.

Covers Plan 2 Task 3 Step 1 & Step 2:

* Local providers must never enable ``trust_remote_code``.
* Retrieval must ignore vectors stored under a previous identity revision and
  fall back to FTS when the current identity no longer matches.
* Provider failures must not break search; results come from FTS5.
* ``EmbeddingIndexCoordinator.reindex`` requires explicit confirmation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from langdrill_agent.db import connect, init_db
from langdrill_agent.embeddings.indexing import EmbeddingIndexCoordinator
from langdrill_agent.embeddings.models import EmbeddingIdentity
from langdrill_agent.embeddings.providers import LocalSentenceTransformerProvider
from langdrill_agent.knowledge.embeddings import EmbeddingConfig, EmbeddingProvider
from langdrill_agent.knowledge.models import KnowledgeChunkInput
from langdrill_agent.knowledge.repository import KnowledgeRepository
from langdrill_agent.knowledge.retrieval import KnowledgeRetrievalService, RetrievalQuery
from langdrill_agent.utils import dumps


def test_local_provider_never_enables_remote_code() -> None:
    captured: dict[str, Any] = {}

    def factory(*args: Any, **kwargs: Any) -> Any:
        captured["args"] = args
        captured["kwargs"] = kwargs

        class _Stub:
            def encode(
                self, texts: list[str], *, normalize_embeddings: bool = False
            ) -> list[list[float]]:
                return [[1.0] for _ in texts]

        return _Stub()

    provider = LocalSentenceTransformerProvider(
        model_path=Path("model"),
        identity=EmbeddingIdentity(
            provider="local",
            model_id="org/model",
            revision="abc",
            dimensions=384,
        ),
        factory=factory,
    )

    provider.embed(["hello"])

    assert captured["args"] == (str(Path("model")),)
    assert captured["kwargs"] == {
        "trust_remote_code": False,
        "local_files_only": True,
    }


class FailingProvider:
    @property
    def identity(self) -> EmbeddingIdentity:
        return EmbeddingIdentity(
            provider="openai_compatible",
            model_id="embed-v1",
            revision="r1",
            dimensions=2,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("provider unavailable")


class _StaticProvider:
    def __init__(self, identity: EmbeddingIdentity, vector: list[float]) -> None:
        self.identity = identity
        self._vector = vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(self._vector) for _ in texts]


def _create_chunk(repo: KnowledgeRepository) -> Any:
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
    return chunks[0]


def _insert_embedding(
    conn: Any,
    chunk: Any,
    *,
    identity: EmbeddingIdentity,
    vector: list[float],
) -> None:
    conn.execute(
        """
        INSERT INTO knowledge_embeddings
        (chunk_id, provider, model, dimensions, vector_json, content_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id, provider, model) DO UPDATE SET
          dimensions=excluded.dimensions,
          vector_json=excluded.vector_json,
          content_hash=excluded.content_hash
        """,
        (
            chunk.id,
            identity.key,
            identity.model_id,
            identity.dimensions,
            dumps(vector),
            chunk.content_hash,
        ),
    )


def test_retrieval_ignores_vectors_from_previous_revision(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = KnowledgeRepository(conn)
        chunk = _create_chunk(repo)
        old = EmbeddingIdentity(
            provider="local",
            model_id="org/model",
            revision="old",
            dimensions=3,
        )
        current = old.model_copy(update={"revision": "new"})
        _insert_embedding(conn, chunk, identity=old, vector=[1.0, 0.0, 0.0])

        result = KnowledgeRetrievalService(
            conn,
            embedding_provider=_StaticProvider(current, [1.0, 0.0, 0.0]),
            embedding_config=EmbeddingConfig.from_identity(current),
        ).search_result(
            RetrievalQuery(text="semantic only", top_k=5, token_budget=500)
        )

        assert result.mode == "fts"


def test_provider_error_returns_fts_results(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = KnowledgeRepository(conn)
        _create_chunk(repo)

        result = KnowledgeRetrievalService(
            conn,
            embedding_provider=FailingProvider(),
            embedding_config=EmbeddingConfig(enabled=True),
        ).search_result(
            RetrievalQuery(text="following continuously", top_k=5, token_budget=500)
        )

        assert result.mode == "fts"
        assert result.items


class _FakeRuntime:
    def current(self) -> tuple[Any, EmbeddingProvider | None]:
        return None, None


def test_reindex_requires_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        coordinator = EmbeddingIndexCoordinator(conn, runtime=_FakeRuntime())
        with pytest.raises(ValueError, match="EMBEDDING_REINDEX_CONFIRMATION_REQUIRED"):
            coordinator.reindex(["knowledge"], confirmed=False)
