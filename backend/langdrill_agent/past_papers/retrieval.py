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
from ..utils import dumps, loads, new_id

_QUERY_TOKEN = re.compile(r"[\w\u3400-\u9fff]+", re.UNICODE)


class PastPaperQuery(BaseModel):
    exam_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)
    question_types: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    knowledge_tags: list[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=50)
    verified_answers_only: bool = False


class RetrievedPaperQuestion(BaseModel):
    id: str
    document_id: str
    exam_id: str
    document_title: str
    year: int | None = None
    source_url: str = ""
    question_number: str = ""
    question_type: str
    prompt: str
    options: list[str] = Field(default_factory=list)
    answer: dict[str, object] = Field(default_factory=dict)
    explanation: str = ""
    knowledge_tags: list[str] = Field(default_factory=list)
    source_page: int | None = None
    verification_status: str
    answer_confidence: float = 0
    style_evidence: bool = True
    correctness_evidence: bool = False
    score: float = 0
    boundary: str = "short_style_reference"


class PastPaperRetrievalResult(BaseModel):
    mode: Literal["fts", "hybrid"] = "fts"
    items: list[RetrievedPaperQuestion] = Field(default_factory=list)


class PastPaperRetrievalService:
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

    def search(self, query: PastPaperQuery) -> PastPaperRetrievalResult:
        fts_items = self._fts_candidates(query)
        mode: Literal["fts", "hybrid"] = "fts"
        items = fts_items
        if self.embedding_config.enabled and self.embedding_provider is not None:
            try:
                vectors = self.embedding_provider.embed([query.text])
                semantic_items = self._semantic_candidates(query, vectors[0]) if len(vectors) == 1 else []
            except Exception:
                semantic_items = []
            if semantic_items:
                fused = reciprocal_rank_fusion(
                    [[item.id for item in fts_items], [item.id for item in semantic_items]]
                )
                by_id = {item.id: item for item in [*fts_items, *semantic_items]}
                items = [
                    by_id[item_id].model_copy(update={"score": score})
                    for item_id, score in fused
                    if item_id in by_id
                ][: query.top_k]
                mode = "hybrid"
        self._record_event(query, mode, items)
        return PastPaperRetrievalResult(mode=mode, items=items[: query.top_k])

    def _fts_candidates(self, query: PastPaperQuery) -> list[RetrievedPaperQuestion]:
        expression = _fts_match_expression(query.text)
        if not expression:
            return []
        filters = [
            "past_paper_question_fts MATCH ?",
            "d.exam_id=?",
            "d.status='ready'",
        ]
        params: list[object] = [expression, query.exam_id]
        _append_filters(filters, params, query)
        params.append(max(query.top_k * 3, query.top_k))
        rows = self.conn.execute(
            f"""
            SELECT q.*, d.exam_id, d.title AS document_title, d.year, d.source_url,
                   bm25(past_paper_question_fts) AS rank
            FROM past_paper_question_fts
            JOIN past_paper_questions q ON q.id=past_paper_question_fts.question_id
            JOIN past_paper_documents d ON d.id=q.document_id
            WHERE {' AND '.join(filters)}
            ORDER BY rank, q.answer_confidence DESC, q.id
            LIMIT ?
            """,
            params,
        ).fetchall()
        ranked = [self._row_to_item(row) for row in rows]
        return sorted(
            ranked,
            key=lambda item: (
                -item.score,
                -int(item.correctness_evidence),
                item.id,
            ),
        )[: query.top_k]

    def _semantic_candidates(
        self,
        query: PastPaperQuery,
        query_vector: list[float],
    ) -> list[RetrievedPaperQuestion]:
        identity = self.embedding_provider.identity
        filters = [
            "e.provider=?",
            "e.model=?",
            "e.dimensions=?",
            "d.exam_id=?",
            "d.status='ready'",
            "e.content_hash=q.content_hash",
        ]
        params: list[object] = [
            identity.key,
            identity.model_id,
            identity.dimensions,
            query.exam_id,
        ]
        _append_filters(filters, params, query)
        rows = self.conn.execute(
            f"""
            SELECT q.*, d.exam_id, d.title AS document_title, d.year, d.source_url,
                   e.vector_json, 0.0 AS rank
            FROM past_paper_embeddings e
            JOIN past_paper_questions q ON q.id=e.question_id
            JOIN past_paper_documents d ON d.id=q.document_id
            WHERE {' AND '.join(filters)}
            """,
            params,
        ).fetchall()
        candidates: dict[str, RetrievedPaperQuestion] = {}
        vectors: dict[str, list[float]] = {}
        for row in rows:
            vector = loads(row["vector_json"], [])
            similarity = cosine_similarity(query_vector, vector)
            if similarity <= 0:
                continue
            item = self._row_to_item(row, base_score=similarity)
            candidates[item.id] = item
            vectors[item.id] = vector
        selected = maximal_marginal_relevance(
            query_vector=query_vector,
            candidates=vectors,
            limit=query.top_k,
        )
        return [candidates[item_id] for item_id in selected]

    @staticmethod
    def _row_to_item(
        row: sqlite3.Row,
        *,
        base_score: float | None = None,
    ) -> RetrievedPaperQuestion:
        verified = row["verification_status"] == "verified"
        if base_score is None:
            rank = float(row["rank"] or 0)
            base_score = 1 / (1 + math.fabs(rank))
        type_bonus = 0.08 if row["question_type"] else 0
        verification_bonus = 0.12 if verified else 0
        return RetrievedPaperQuestion(
            id=row["id"],
            document_id=row["document_id"],
            exam_id=row["exam_id"],
            document_title=row["document_title"],
            year=row["year"],
            source_url=row["source_url"],
            question_number=row["question_number"],
            question_type=row["question_type"],
            prompt=row["prompt"],
            options=loads(row["options_json"], []),
            answer=loads(row["answer_json"], {}) if verified else {},
            explanation=row["explanation"] if verified else "",
            knowledge_tags=loads(row["knowledge_tags_json"], []),
            source_page=row["source_page"],
            verification_status=row["verification_status"],
            answer_confidence=row["answer_confidence"],
            correctness_evidence=verified,
            score=base_score + type_bonus + verification_bonus,
            boundary=(
                "short_verified_reference" if verified else "short_style_reference_unverified_answer"
            ),
        )

    def _record_event(
        self,
        query: PastPaperQuery,
        mode: str,
        items: list[RetrievedPaperQuestion],
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO past_paper_retrieval_events
            (id, exam_id, query, filters_json, result_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                new_id("paperretrieval"),
                query.exam_id,
                query.text,
                dumps(
                    {
                        "question_types": query.question_types,
                        "years": query.years,
                        "knowledge_tags": query.knowledge_tags,
                        "verified_answers_only": query.verified_answers_only,
                        "mode": mode,
                    }
                ),
                dumps([{"id": item.id, "score": item.score} for item in items]),
            ),
        )


def _append_filters(
    filters: list[str],
    params: list[object],
    query: PastPaperQuery,
) -> None:
    if query.question_types:
        placeholders = ",".join("?" for _ in query.question_types)
        filters.append(f"q.question_type IN ({placeholders})")
        params.extend(query.question_types)
    if query.years:
        placeholders = ",".join("?" for _ in query.years)
        filters.append(f"d.year IN ({placeholders})")
        params.extend(query.years)
    if query.knowledge_tags:
        tag_filters = []
        for tag in query.knowledge_tags:
            tag_filters.append("q.knowledge_tags_json LIKE ?")
            params.append(f'%"{tag}"%')
        filters.append("(" + " OR ".join(tag_filters) + ")")
    if query.verified_answers_only:
        filters.append("q.verification_status='verified'")


def _fts_match_expression(text: str) -> str:
    tokens = _QUERY_TOKEN.findall(text)
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
