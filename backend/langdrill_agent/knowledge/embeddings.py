from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..utils import dumps, normalize_api_key, validate_http_header_value
from .models import KnowledgeChunk


class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    provider: str = ""
    model: str = ""
    dimensions: int = 0
    enabled: bool = False


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def identity(self) -> str:
        return f"{self.base_url}::{self.model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise RuntimeError("embedding provider returned an invalid data length")
        ordered = sorted(rows, key=lambda row: int(row.get("index", 0)))
        vectors = [row.get("embedding") for row in ordered]
        if any(not isinstance(vector, list) or not vector for vector in vectors):
            raise RuntimeError("embedding provider returned an invalid vector")
        return [[float(value) for value in vector] for vector in vectors]


def embedding_runtime_from_env() -> tuple[EmbeddingConfig, EmbeddingProvider | None]:
    enabled = os.getenv("LANGDRILL_KNOWLEDGE_EMBEDDING_ENABLED", "").strip() == "1"
    base_url = os.getenv("LANGDRILL_KNOWLEDGE_EMBEDDING_BASE_URL", "").strip()
    api_key = normalize_api_key(os.getenv("LANGDRILL_KNOWLEDGE_EMBEDDING_API_KEY", ""))
    model = os.getenv("LANGDRILL_KNOWLEDGE_EMBEDDING_MODEL", "").strip()
    try:
        dimensions = int(os.getenv("LANGDRILL_KNOWLEDGE_EMBEDDING_DIMENSIONS", "0") or 0)
    except ValueError:
        dimensions = 0
    config = EmbeddingConfig(
        provider=base_url,
        model=model,
        dimensions=max(dimensions, 0),
        enabled=enabled,
    )
    if not enabled or not base_url or not model or not api_key:
        return config, None
    validate_http_header_value(api_key, "Knowledge Embedding API Key")
    return config, OpenAICompatibleEmbeddingProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


class EmbeddingIndexService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def index_chunks(
        self,
        provider: EmbeddingProvider,
        chunks: list[KnowledgeChunk],
        config: EmbeddingConfig | None = None,
    ) -> int:
        if not chunks:
            return 0
        vectors = provider.embed([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
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
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.conn.execute(
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
                    provider.identity,
                    active_config.model or provider.identity,
                    dimensions,
                    dumps(vector),
                    chunk.content_hash,
                ),
            )
        return len(chunks)


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    if k < 1:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(item_id, len(first_seen))
    return sorted(
        scores.items(),
        key=lambda item: (-item[1], first_seen[item[0]]),
    )


def maximal_marginal_relevance(
    *,
    query_vector: list[float],
    candidates: dict[str, list[float]],
    limit: int,
    lambda_mult: float = 0.7,
) -> list[str]:
    if limit <= 0 or not candidates:
        return []
    if not 0 <= lambda_mult <= 1:
        raise ValueError("lambda_mult must be between 0 and 1")
    remaining = dict(candidates)
    selected: list[str] = []
    while remaining and len(selected) < limit:
        best_id = max(
            remaining,
            key=lambda item_id: (
                lambda_mult * cosine_similarity(query_vector, remaining[item_id])
                - (1 - lambda_mult)
                * max(
                    (
                        cosine_similarity(remaining[item_id], candidates[selected_id])
                        for selected_id in selected
                    ),
                    default=0.0,
                ),
                item_id,
            ),
        )
        selected.append(best_id)
        remaining.pop(best_id)
    return selected


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
