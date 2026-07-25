"""Embedding providers bound to an :class:`EmbeddingIdentity`.

All providers expose ``identity`` as an :class:`EmbeddingIdentity` instance so
that retrieval filters can pin results to the exact provider/model/revision
that produced them. Local providers never enable ``trust_remote_code``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from .models import EmbeddingIdentity


class LocalSentenceTransformerProvider:
    """Local sentence-transformer model loaded with trust_remote_code disabled."""

    def __init__(
        self,
        *,
        model_path: Path,
        identity: EmbeddingIdentity,
        factory: Callable[..., Any] | None = None,
    ) -> None:
        self.model_path = model_path
        self.identity = identity
        self._factory = factory
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            factory = self._factory
            if factory is None:
                from sentence_transformers import SentenceTransformer

                factory = SentenceTransformer
            self._model = factory(
                str(self.model_path),
                trust_remote_code=False,
                local_files_only=True,
            )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        rows = self._load().encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in rows]


class HuggingFaceInferenceEmbeddingProvider:
    """Hugging Face Inference API feature-extraction provider."""

    BASE_URL = "https://api-inference.huggingface.co"

    def __init__(
        self,
        *,
        identity: EmbeddingIdentity,
        token: str,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise ValueError("EMBEDDING_HF_TOKEN_MISSING")
        self.identity = identity
        self.token = token
        self._client = client or httpx.Client(timeout=timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.post(
            f"{self.BASE_URL}/models/{self.identity.model_id}",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"inputs": texts, "options": {"wait_for_model": True}},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) != len(texts):
            raise RuntimeError("embedding provider returned an invalid data length")
        vectors: list[list[float]] = []
        for row in payload:
            if not isinstance(row, list) or not row:
                raise RuntimeError("embedding provider returned an invalid vector")
            vectors.append([float(value) for value in row])
        return vectors
