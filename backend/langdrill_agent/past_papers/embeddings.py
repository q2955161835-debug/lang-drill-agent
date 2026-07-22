from __future__ import annotations

import sqlite3

from ..knowledge.embeddings import EmbeddingConfig, EmbeddingProvider
from ..utils import dumps
from .models import PaperQuestion


class PastPaperEmbeddingIndexService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def index_questions(
        self,
        provider: EmbeddingProvider,
        questions: list[PaperQuestion],
        config: EmbeddingConfig | None = None,
    ) -> int:
        if not questions:
            return 0
        texts = [_embedding_text(question) for question in questions]
        vectors = provider.embed(texts)
        if len(vectors) != len(questions):
            raise RuntimeError("embedding provider returned an invalid vector count")
        dimensions = len(vectors[0])
        if dimensions < 1 or any(len(vector) != dimensions for vector in vectors):
            raise RuntimeError("embedding vectors have inconsistent dimensions")
        active_config = config or EmbeddingConfig(
            provider=provider.identity,
            model=provider.identity,
            dimensions=dimensions,
            enabled=True,
        )
        if active_config.dimensions and active_config.dimensions != dimensions:
            raise RuntimeError("embedding dimensions do not match configuration")
        for question, vector in zip(questions, vectors, strict=True):
            self.conn.execute(
                """
                INSERT INTO past_paper_embeddings
                (question_id, provider, model, dimensions, vector_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(question_id, provider, model) DO UPDATE SET
                  dimensions=excluded.dimensions,
                  vector_json=excluded.vector_json,
                  content_hash=excluded.content_hash
                """,
                (
                    question.id,
                    provider.identity,
                    active_config.model or provider.identity,
                    dimensions,
                    dumps(vector),
                    question.content_hash,
                ),
            )
        return len(questions)

    def clear_document(self, document_id: str) -> int:
        question_ids = [
            row[0]
            for row in self.conn.execute(
                "SELECT id FROM past_paper_questions WHERE document_id=?",
                (document_id,),
            )
        ]
        if not question_ids:
            return 0
        placeholders = ",".join("?" for _ in question_ids)
        cursor = self.conn.execute(
            f"DELETE FROM past_paper_embeddings WHERE question_id IN ({placeholders})",
            question_ids,
        )
        return cursor.rowcount


def _embedding_text(question: PaperQuestion) -> str:
    return "\n".join(
        part
        for part in (
            question.question_type,
            question.prompt,
            "\n".join(question.options),
            question.explanation if question.verification_status == "verified" else "",
            " ".join(question.knowledge_tags),
        )
        if part
    )
