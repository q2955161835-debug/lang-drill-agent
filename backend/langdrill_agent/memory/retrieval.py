from __future__ import annotations

import math
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field

from ..knowledge.embeddings import (
    EmbeddingConfig,
    EmbeddingProvider,
    cosine_similarity,
    maximal_marginal_relevance,
    reciprocal_rank_fusion,
)
from ..utils import loads
from .models import MemoryItem
from .repository import MemoryRepository

_QUERY_TOKEN = re.compile(r"[\w\u3400-\u9fff]+", re.UNICODE)


class MemoryRetrievalQuery(BaseModel):
    text: str = Field(default="", max_length=2000)
    categories: list[str] = Field(default_factory=list)
    scope: str = "global"
    top_k: int = Field(default=8, ge=1, le=50)
    token_budget: int = Field(default=1000, ge=1, le=7_000_000)
    as_of: str = ""


class RetrievedMemoryItem(MemoryItem):
    score: float = 0
    token_count: int = 1
    evidence_ids: list[str] = Field(default_factory=list)


class MemoryRetrievalResult(BaseModel):
    mode: Literal["fts", "hybrid", "core"] = "fts"
    items: list[RetrievedMemoryItem] = Field(default_factory=list)
    token_count: int = 0


class MemoryRetrievalService:
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

    def retrieve(self, query: MemoryRetrievalQuery) -> MemoryRetrievalResult:
        clean_text = query.text.strip()
        if not clean_text:
            return MemoryRetrievalResult(items=[])
        fts_items = self._fts_candidates(query)
        mode: Literal["fts", "hybrid"] = "fts"
        ranked = fts_items
        if self.embedding_config.enabled and self.embedding_provider is not None:
            try:
                vectors = self.embedding_provider.embed([clean_text])
                semantic = self._semantic_candidates(query, vectors[0]) if len(vectors) == 1 else []
            except Exception:
                semantic = []
            if semantic:
                fused = reciprocal_rank_fusion(
                    [[item.id for item in fts_items], [item.id for item in semantic]]
                )
                by_id = {item.id: item for item in [*fts_items, *semantic]}
                ranked = [
                    by_id[item_id].model_copy(
                        update={"score": score + _quality_score(by_id[item_id])}
                    )
                    for item_id, score in fused
                    if item_id in by_id
                ]
                mode = "hybrid"
        items = _apply_budget(ranked, query.top_k, query.token_budget)
        return MemoryRetrievalResult(
            mode=mode,
            items=items,
            token_count=sum(item.token_count for item in items),
        )

    def build_core(
        self,
        *,
        scope: str = "global",
        token_budget: int = 400,
        as_of: str = "",
        categories: list[str] | None = None,
    ) -> MemoryRetrievalResult:
        filters, params = _validity_filters(
            categories=categories or ["core", "profile", "preference"],
            scope=scope,
            as_of=as_of,
        )
        rows = self.conn.execute(
            f"""
            SELECT m.*
            FROM memory_items m
            WHERE {' AND '.join(filters)}
            ORDER BY m.pinned DESC, m.confidence DESC, m.importance DESC,
                     m.updated_at DESC, m.id
            """,
            params,
        ).fetchall()
        ranked = [
            self._row_to_item(
                row,
                base_score=(
                    2.0 * int(bool(row["pinned"]))
                    + float(row["confidence"])
                    + float(row["importance"])
                ),
            )
            for row in rows
        ]
        items = _apply_budget(ranked, len(ranked), token_budget)
        return MemoryRetrievalResult(
            mode="core",
            items=items,
            token_count=sum(item.token_count for item in items),
        )

    def _fts_candidates(self, query: MemoryRetrievalQuery) -> list[RetrievedMemoryItem]:
        expression = _fts_match_expression(query.text)
        if not expression:
            return []
        filters, params = _validity_filters(
            categories=query.categories,
            scope=query.scope,
            as_of=query.as_of,
        )
        filters.insert(0, "memory_item_fts MATCH ?")
        params.insert(0, expression)
        params.append(max(query.top_k * 3, query.top_k))
        rows = self.conn.execute(
            f"""
            SELECT m.*, bm25(memory_item_fts) AS rank
            FROM memory_item_fts
            JOIN memory_items m ON m.id=memory_item_fts.memory_id
            WHERE {' AND '.join(filters)}
            ORDER BY rank, m.pinned DESC, m.importance DESC, m.updated_at DESC, m.id
            LIMIT ?
            """,
            params,
        ).fetchall()
        return sorted(
            [
                self._row_to_item(
                    row,
                    base_score=1 / (1 + math.fabs(float(row["rank"] or 0))),
                )
                for row in rows
            ],
            key=lambda item: (-item.score, item.id),
        )

    def _semantic_candidates(
        self,
        query: MemoryRetrievalQuery,
        query_vector: list[float],
    ) -> list[RetrievedMemoryItem]:
        identity = self.embedding_provider.identity
        filters, params = _validity_filters(
            categories=query.categories,
            scope=query.scope,
            as_of=query.as_of,
        )
        filters.extend(
            [
                "e.provider=?",
                "e.model=?",
                "e.dimensions=?",
                "e.content_hash=printf('%s', e.content_hash)",
            ]
        )
        params.extend([identity.key, identity.model_id, identity.dimensions])
        rows = self.conn.execute(
            f"""
            SELECT m.*, e.vector_json
            FROM memory_embeddings e
            JOIN memory_items m ON m.id=e.memory_id
            WHERE {' AND '.join(filters)}
            """,
            params,
        ).fetchall()
        candidates: dict[str, RetrievedMemoryItem] = {}
        vectors: dict[str, list[float]] = {}
        for row in rows:
            vector = loads(row["vector_json"], [])
            similarity = cosine_similarity(query_vector, vector)
            if similarity <= 0:
                continue
            item = self._row_to_item(row, base_score=similarity)
            candidates[item.id] = item
            vectors[item.id] = vector
        selected_ids = maximal_marginal_relevance(
            query_vector=query_vector,
            candidates=vectors,
            limit=query.top_k,
        )
        return [candidates[item_id] for item_id in selected_ids]

    def _row_to_item(self, row: sqlite3.Row, *, base_score: float) -> RetrievedMemoryItem:
        item = MemoryRepository._item_from_row(row)
        evidence_ids = [
            evidence.evidence_ref for evidence in MemoryRepository(self.conn).evidence(item.id)
        ]
        retrieved = RetrievedMemoryItem(
            **item.model_dump(),
            score=base_score,
            token_count=_estimate_tokens(item.content),
            evidence_ids=evidence_ids,
        )
        return retrieved.model_copy(update={"score": base_score + _quality_score(retrieved)})


def _validity_filters(
    *,
    categories: list[str],
    scope: str,
    as_of: str,
) -> tuple[list[str], list[object]]:
    filters = ["m.status='active'"]
    params: list[object] = []
    if categories:
        placeholders = ",".join("?" for _ in categories)
        filters.append(f"m.category IN ({placeholders})")
        params.extend(categories)
    if scope and scope != "global":
        filters.append("m.scope IN ('global', ?)")
        params.append(scope)
    else:
        filters.append("m.scope='global'")
    if as_of:
        filters.extend(
            [
                "(m.valid_from IS NULL OR m.valid_from='' OR m.valid_from<=?)",
                "(m.valid_to IS NULL OR m.valid_to='' OR m.valid_to>?)",
                "(m.expires_at IS NULL OR m.expires_at='' OR m.expires_at>?)",
            ]
        )
        params.extend([as_of, as_of, as_of])
    else:
        filters.append(
            "(m.expires_at IS NULL OR m.expires_at='' OR m.expires_at>CURRENT_TIMESTAMP)"
        )
    return filters, params


def _quality_score(item: MemoryItem) -> float:
    return (
        0.35 * float(item.confidence)
        + 0.25 * float(item.importance)
        + 0.2 * int(bool(item.pinned))
    )


def _apply_budget(
    ranked: list[RetrievedMemoryItem],
    top_k: int,
    token_budget: int,
) -> list[RetrievedMemoryItem]:
    selected: list[RetrievedMemoryItem] = []
    consumed = 0
    for item in ranked:
        if len(selected) >= top_k:
            break
        if selected and consumed + item.token_count > token_budget:
            continue
        if not selected and item.token_count > token_budget:
            truncated = item.model_copy(
                update={
                    "content": item.content[: max(1, token_budget * 4)],
                    "token_count": token_budget,
                }
            )
            selected.append(truncated)
            break
        selected.append(item)
        consumed += item.token_count
    return selected


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _fts_match_expression(text: str) -> str:
    tokens = _QUERY_TOKEN.findall(text)
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
