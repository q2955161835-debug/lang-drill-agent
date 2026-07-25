"""Coordinate embedding reindex across knowledge, past_papers, and memory.

``reindex`` requires explicit confirmation (``confirmed=True``). Each target is
marked ``rebuilding`` before work begins. On success the identity key and
indexed count are recorded; on failure the status becomes ``failed`` but FTS5
rows are never deleted, so retrieval always has a fallback.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..knowledge.embeddings import (
    EmbeddingConfig,
    EmbeddingIndexService,
    EmbeddingProvider,
)
from ..knowledge.repository import KnowledgeRepository
from ..past_papers.embeddings import PastPaperEmbeddingIndexService
from ..past_papers.repository import PastPaperRepository
from ..utils import dumps
from .models import EmbeddingIdentity
from .runtime import EmbeddingRuntime

CONFIRMATION_ERROR = "EMBEDDING_REINDEX_CONFIRMATION_REQUIRED"
RUNTIME_NOT_READY_ERROR = "EMBEDDING_RUNTIME_NOT_READY"
UNKNOWN_TARGET_ERROR = "EMBEDDING_REINDEX_UNKNOWN_TARGET"
REINDEX_FAILED_ERROR = "EMBEDDING_REINDEX_FAILED"
ERROR_DETAIL_MAX_LENGTH = 300

SUPPORTED_TARGETS = ("knowledge", "past_papers", "memory")


class EmbeddingIndexCoordinator:
    """Coordinate embedding reindex across knowledge, past_papers, and memory."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        runtime: EmbeddingRuntime | Any | None = None,
    ) -> None:
        self.conn = conn
        self.runtime = runtime or EmbeddingRuntime(conn)

    def status(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT target, identity_key, status, indexed_count, error_code, updated_at
            FROM embedding_index_state
            ORDER BY target
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_stale_all(self) -> None:
        """Mark every supported target as ``stale`` without touching vectors.

        Called after the user switches embedding settings so retrieval keeps
        using FTS5 until an explicit, confirmed reindex is requested. The
        ``identity_key`` and ``indexed_count`` columns are preserved so the UI
        can show that a previous index existed; only ``status`` becomes
        ``stale`` and ``error_code`` is cleared.
        """

        for target in SUPPORTED_TARGETS:
            self.conn.execute(
                """
                INSERT INTO embedding_index_state
                  (target, identity_key, status, indexed_count, error_code, updated_at)
                VALUES (?, '', 'stale', 0, '', CURRENT_TIMESTAMP)
                ON CONFLICT(target) DO UPDATE SET
                  status='stale',
                  error_code='',
                  updated_at=CURRENT_TIMESTAMP
                """,
                (target,),
            )

    def reindex(
        self,
        targets: list[str],
        *,
        confirmed: bool,
    ) -> dict[str, dict[str, Any]]:
        if not confirmed:
            raise ValueError(CONFIRMATION_ERROR)
        _config, provider = self.runtime.current()
        if provider is None:
            raise ValueError(RUNTIME_NOT_READY_ERROR)
        identity = provider.identity
        results: dict[str, dict[str, Any]] = {}
        for target in targets:
            if target not in SUPPORTED_TARGETS:
                raise ValueError(f"{UNKNOWN_TARGET_ERROR}:{target}")
            self._set_status(target, "rebuilding")
            try:
                if target == "knowledge":
                    count = self._reindex_knowledge(provider, identity)
                elif target == "past_papers":
                    count = self._reindex_past_papers(provider, identity)
                else:
                    count = self._reindex_memory(provider, identity)
                self._set_status(
                    target,
                    "indexed",
                    identity_key=identity.key,
                    indexed_count=count,
                )
                results[target] = {"status": "indexed", "indexed_count": count}
            except Exception as exc:  # noqa: BLE001 - isolate each index target
                detail = str(exc)[:ERROR_DETAIL_MAX_LENGTH]
                self._set_status(
                    target,
                    "failed",
                    error_code=REINDEX_FAILED_ERROR,
                )
                results[target] = {"status": "failed", "error": detail}
        return results

    def _set_status(
        self,
        target: str,
        status: str,
        *,
        identity_key: str = "",
        indexed_count: int = 0,
        error_code: str = "",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO embedding_index_state
              (target, identity_key, status, indexed_count, error_code, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(target) DO UPDATE SET
              identity_key=excluded.identity_key,
              status=excluded.status,
              indexed_count=excluded.indexed_count,
              error_code=excluded.error_code,
              updated_at=CURRENT_TIMESTAMP
            """,
            (target, identity_key, status, indexed_count, error_code),
        )

    def _reindex_knowledge(
        self,
        provider: EmbeddingProvider,
        identity: EmbeddingIdentity,
    ) -> int:
        repo = KnowledgeRepository(self.conn)
        config = EmbeddingConfig.from_identity(identity)
        total = 0
        for document in repo.list_documents():
            if document.status != "ready":
                continue
            chunks = repo.list_chunks(document.id)
            if not chunks:
                continue
            total += EmbeddingIndexService(self.conn).index_chunks(
                provider, chunks, config
            )
        return total

    def _reindex_past_papers(
        self,
        provider: EmbeddingProvider,
        identity: EmbeddingIdentity,
    ) -> int:
        repo = PastPaperRepository(self.conn)
        config = EmbeddingConfig.from_identity(identity)
        rows = self.conn.execute(
            "SELECT id FROM past_paper_documents WHERE status='ready' ORDER BY id"
        ).fetchall()
        total = 0
        for row in rows:
            questions = repo.list_questions(row["id"])
            if not questions:
                continue
            total += PastPaperEmbeddingIndexService(self.conn).index_questions(
                provider, questions, config
            )
        return total

    def _reindex_memory(
        self,
        provider: EmbeddingProvider,
        identity: EmbeddingIdentity,
    ) -> int:
        rows = self.conn.execute(
            "SELECT id, content FROM memory_items WHERE status='active' ORDER BY id"
        ).fetchall()
        if not rows:
            return 0
        texts = [row["content"] for row in rows]
        vectors = provider.embed(texts)
        if len(vectors) != len(rows):
            raise RuntimeError("embedding provider returned an invalid vector count")
        dimensions = len(vectors[0])
        if dimensions < 1 or any(len(vector) != dimensions for vector in vectors):
            raise RuntimeError("embedding vectors have inconsistent dimensions")
        for row, vector in zip(rows, vectors, strict=True):
            self.conn.execute(
                """
                INSERT INTO memory_embeddings
                  (memory_id, provider, model, dimensions, vector_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id, provider, model) DO UPDATE SET
                  dimensions=excluded.dimensions,
                  vector_json=excluded.vector_json,
                  content_hash=excluded.content_hash
                """,
                (
                    row["id"],
                    identity.key,
                    identity.model_id,
                    dimensions,
                    dumps(vector),
                    "",
                ),
            )
        return len(rows)
