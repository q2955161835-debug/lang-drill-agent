from __future__ import annotations

import math
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field

from ..utils import dumps, loads, new_id
from .embeddings import (
    EmbeddingConfig,
    EmbeddingProvider,
    cosine_similarity,
    maximal_marginal_relevance,
    reciprocal_rank_fusion,
)

_QUERY_TOKEN = re.compile(r"[\w\u3400-\u9fff]+", re.UNICODE)


class RetrievalQuery(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=50)
    token_budget: int = Field(default=2000, ge=1, le=20_000)
    trace_id: str = ""


class KnowledgeCitation(BaseModel):
    document_id: str
    document_title: str
    source_name: str
    heading: str = ""
    page_start: int | None = None
    page_end: int | None = None
    content_hash: str


class RetrievedChunk(BaseModel):
    id: str
    document_id: str
    content: str
    content_hash: str
    token_count: int
    score: float
    citation: KnowledgeCitation


class RetrievalResult(BaseModel):
    mode: Literal["fts", "hybrid"] = "fts"
    items: list[RetrievedChunk] = Field(default_factory=list)


class KnowledgeRetrievalService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_config: EmbeddingConfig | None = None,
    ) -> None:
        self.conn = conn
        self.embedding_provider = embedding_provider
        self.embedding_config = embedding_config or EmbeddingConfig()

    def search(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        match_expression = _fts_match_expression(query.text)
        if not match_expression:
            self._record_event(query, [], [])
            return []

        filters = ["knowledge_chunk_fts MATCH ?", "d.status = 'ready'"]
        params: list[object] = [match_expression]
        if query.document_ids:
            placeholders = ",".join("?" for _ in query.document_ids)
            filters.append(f"c.document_id IN ({placeholders})")
            params.extend(query.document_ids)
        params.append(query.top_k)
        rows = self.conn.execute(
            f"""
            SELECT
              c.id,
              c.document_id,
              c.heading,
              c.page_start,
              c.page_end,
              c.content,
              c.content_hash,
              c.token_count,
              d.title AS document_title,
              d.source_name,
              bm25(knowledge_chunk_fts) AS rank
            FROM knowledge_chunk_fts
            JOIN knowledge_chunks c ON c.id = knowledge_chunk_fts.chunk_id
            JOIN knowledge_documents d ON d.id = c.document_id
            WHERE {' AND '.join(filters)}
            ORDER BY rank, c.ordinal, c.id
            LIMIT ?
            """,
            params,
        ).fetchall()

        ranked = [self._row_to_result(row) for row in rows]
        injected: list[RetrievedChunk] = []
        consumed_tokens = 0
        for item in ranked:
            if injected and consumed_tokens + item.token_count > query.token_budget:
                continue
            injected.append(item)
            consumed_tokens += item.token_count
        self._record_event(query, ranked, injected)
        return injected

    def search_result(self, query: RetrievalQuery) -> RetrievalResult:
        fts_items = self.search(query)
        if not self.embedding_config.enabled or self.embedding_provider is None:
            return RetrievalResult(mode="fts", items=fts_items)
        try:
            query_vectors = self.embedding_provider.embed([query.text])
        except Exception:
            return RetrievalResult(mode="fts", items=fts_items)
        if len(query_vectors) != 1:
            return RetrievalResult(mode="fts", items=fts_items)
        semantic_items = self._semantic_candidates(query, query_vectors[0])
        if not semantic_items:
            return RetrievalResult(mode="fts", items=fts_items)
        fused = reciprocal_rank_fusion(
            [
                [item.id for item in fts_items],
                [item.id for item in semantic_items],
            ]
        )
        by_id = {item.id: item for item in [*fts_items, *semantic_items]}
        ranked = [
            by_id[item_id].model_copy(update={"score": score})
            for item_id, score in fused
            if item_id in by_id
        ]
        injected = self._apply_token_budget(ranked, query.token_budget)
        self._record_event(query, ranked, injected)
        return RetrievalResult(mode="hybrid", items=injected)

    def _semantic_candidates(
        self,
        query: RetrievalQuery,
        query_vector: list[float],
    ) -> list[RetrievedChunk]:
        filters = ["e.provider = ?", "d.status = 'ready'", "e.content_hash = c.content_hash"]
        params: list[object] = [self.embedding_provider.identity]
        if query.document_ids:
            placeholders = ",".join("?" for _ in query.document_ids)
            filters.append(f"c.document_id IN ({placeholders})")
            params.extend(query.document_ids)
        rows = self.conn.execute(
            f"""
            SELECT
              c.id, c.document_id, c.heading, c.page_start, c.page_end,
              c.content, c.content_hash, c.token_count,
              d.title AS document_title, d.source_name,
              e.vector_json
            FROM knowledge_embeddings e
            JOIN knowledge_chunks c ON c.id = e.chunk_id
            JOIN knowledge_documents d ON d.id = c.document_id
            WHERE {' AND '.join(filters)}
            """,
            params,
        ).fetchall()
        candidates: dict[str, RetrievedChunk] = {}
        vectors: dict[str, list[float]] = {}
        for row in rows:
            vector = loads(row["vector_json"], [])
            score = cosine_similarity(query_vector, vector)
            if score <= 0:
                continue
            candidates[row["id"]] = self._row_to_result(row, score=score)
            vectors[row["id"]] = vector
        selected_ids = maximal_marginal_relevance(
            query_vector=query_vector,
            candidates=vectors,
            limit=query.top_k,
        )
        return [candidates[item_id] for item_id in selected_ids]

    @staticmethod
    def _apply_token_budget(
        ranked: list[RetrievedChunk],
        token_budget: int,
    ) -> list[RetrievedChunk]:
        injected: list[RetrievedChunk] = []
        consumed_tokens = 0
        for item in ranked:
            if injected and consumed_tokens + item.token_count > token_budget:
                continue
            injected.append(item)
            consumed_tokens += item.token_count
        return injected

    def _row_to_result(self, row: sqlite3.Row, *, score: float | None = None) -> RetrievedChunk:
        if score is None:
            rank = float(row["rank"] or 0.0)
            score = 1.0 / (1.0 + math.fabs(rank))
        return RetrievedChunk(
            id=row["id"],
            document_id=row["document_id"],
            content=row["content"],
            content_hash=row["content_hash"],
            token_count=max(int(row["token_count"] or 0), 1),
            score=score,
            citation=KnowledgeCitation(
                document_id=row["document_id"],
                document_title=row["document_title"],
                source_name=row["source_name"],
                heading=row["heading"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                content_hash=row["content_hash"],
            ),
        )

    def _record_event(
        self,
        query: RetrievalQuery,
        ranked: list[RetrievedChunk],
        injected: list[RetrievedChunk],
    ) -> None:
        result_payload = [
            {"id": item.id, "score": item.score, "document_id": item.document_id}
            for item in ranked
        ]
        injected_payload = [item.id for item in injected]
        self.conn.execute(
            """
            INSERT INTO retrieval_events
            (id, trace_id, query, filters_json, result_json, injected_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("retrieval"),
                query.trace_id,
                query.text,
                dumps({"document_ids": query.document_ids}),
                dumps(result_payload),
                dumps(injected_payload),
            ),
        )


def _fts_match_expression(text: str) -> str:
    tokens = _QUERY_TOKEN.findall(text)
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
