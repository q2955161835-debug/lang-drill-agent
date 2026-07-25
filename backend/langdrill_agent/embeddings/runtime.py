"""Lazy-loaded embedding runtime bound to the current EmbeddingIdentity.

The runtime caches a single local provider instance. When the enabled identity
changes (provider/model/revision/dimensions), the cached provider is unloaded
and ``gc.collect()`` runs so the previous model releases its memory before the
new one loads. Cloud providers are cheap to construct and are not cached.
"""

from __future__ import annotations

import gc
import math
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..knowledge.embeddings import EmbeddingConfig, EmbeddingProvider
from .downloads import safe_model_dir
from .models import EmbeddingIdentity, EmbeddingSettings
from .providers import (
    HuggingFaceInferenceEmbeddingProvider,
    LocalSentenceTransformerProvider,
)
from .settings import (
    CLOUD_API_KEY_ENV,
    HF_TOKEN_ENV,
    EmbeddingSettingsService,
)

HEALTH_PROBE_TEXT = "Lang Drill embedding health probe"
HEALTH_PROBE_FAILED = "EMBEDDING_HEALTH_PROBE_FAILED"


def _config_from_settings(settings: EmbeddingSettings) -> EmbeddingConfig:
    """Build an ``EmbeddingConfig`` from the persisted ``EmbeddingSettings``.

    When no identity is enabled the config is disabled so callers safely fall
    back to FTS-only retrieval.
    """

    identity = settings.enabled_identity
    if settings.mode == "off" or identity is None:
        return EmbeddingConfig(enabled=False)
    return EmbeddingConfig(
        provider=identity.key,
        model=identity.model_id,
        dimensions=identity.dimensions,
        enabled=True,
    )


class EmbeddingRuntime:
    """Lazy-loaded embedding provider bound to the current EmbeddingIdentity."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        clock: type[datetime] | None = None,
    ) -> None:
        self.conn = conn
        self._lock = threading.Lock()
        self._cached_provider: EmbeddingProvider | None = None
        self._cached_identity: EmbeddingIdentity | None = None
        self._clock = clock or datetime

    def current(self) -> tuple[EmbeddingConfig, EmbeddingProvider | None]:
        """Return ``(EmbeddingConfig, provider)`` for the current identity.

        When embeddings are off or no identity is enabled, returns an
        ``EmbeddingConfig(enabled=False)`` and ``None`` provider so callers
        safely fall back to FTS-only retrieval.
        """

        settings = EmbeddingSettingsService(self.conn).get()
        config = _config_from_settings(settings)
        if settings.mode == "off" or settings.enabled_identity is None:
            return config, None
        with self._lock:
            current_key = settings.enabled_identity.key
            if (
                self._cached_identity is None
                or self._cached_identity.key != current_key
            ):
                self._unload_locked()
                provider = self._build_provider(settings)
                if provider is not None:
                    self._cached_provider = provider
                    self._cached_identity = settings.enabled_identity
            return config, self._cached_provider

    def settings(self) -> EmbeddingSettings:
        """Return the current EmbeddingSettings (persistence layer view)."""

        return EmbeddingSettingsService(self.conn).get()

    def health_probe(self, settings: EmbeddingSettings) -> EmbeddingIdentity:
        """Embed a probe text and return an identity with measured dimensions.

        Raises ``ValueError("EMBEDDING_HEALTH_PROBE_FAILED")`` if the provider
        cannot return a non-empty finite vector.
        """

        provider = self._build_provider(settings)
        if provider is None:
            raise ValueError(HEALTH_PROBE_FAILED)
        try:
            vectors = provider.embed([HEALTH_PROBE_TEXT])
        except Exception as exc:
            raise ValueError(HEALTH_PROBE_FAILED) from exc
        if len(vectors) != 1:
            raise ValueError(HEALTH_PROBE_FAILED)
        vector = vectors[0]
        if not vector or any(not _is_finite(value) for value in vector):
            raise ValueError(HEALTH_PROBE_FAILED)
        base_identity = settings.enabled_identity or EmbeddingIdentity(
            provider=settings.mode,
            model_id=settings.model_id,
            revision=settings.revision,
            dimensions=len(vector),
        )
        return base_identity.model_copy(update={"dimensions": len(vector)})

    def status(self) -> dict[str, Any]:
        settings = EmbeddingSettingsService(self.conn).get()
        enabled_key = (
            settings.enabled_identity.key if settings.enabled_identity else ""
        )
        loaded = bool(
            self._cached_identity is not None
            and self._cached_identity.key == enabled_key
        )
        return {
            "mode": settings.mode,
            "loaded": loaded,
            "healthy": loaded and self._cached_provider is not None,
            "identity": (
                self._cached_identity.model_dump(mode="json")
                if self._cached_identity
                else None
            ),
        }

    def _build_provider(
        self, settings: EmbeddingSettings
    ) -> EmbeddingProvider | None:
        identity = settings.enabled_identity
        if identity is None:
            return None
        if settings.mode == "local":
            if not settings.model_dir or not settings.model_id or not settings.revision:
                return None
            model_path = (
                Path(settings.model_dir)
                / safe_model_dir(settings.model_id)
                / settings.revision
            )
            return LocalSentenceTransformerProvider(
                model_path=model_path,
                identity=identity,
            )
        if settings.mode == "huggingface_cloud":
            token = os.getenv(HF_TOKEN_ENV, "").strip()
            if not token:
                return None
            return HuggingFaceInferenceEmbeddingProvider(
                identity=identity,
                token=token,
            )
        if settings.mode == "openai_compatible":
            api_key = os.getenv(CLOUD_API_KEY_ENV, "").strip()
            if not api_key or not settings.base_url:
                return None
            from ..knowledge.embeddings import OpenAICompatibleEmbeddingProvider

            return OpenAICompatibleEmbeddingProvider(
                identity=identity,
                base_url=settings.base_url,
                api_key=api_key,
            )
        return None

    def _unload_locked(self) -> None:
        self._cached_provider = None
        self._cached_identity = None
        gc.collect()


def _is_finite(value: float) -> bool:
    return isinstance(value, int | float) and not math.isnan(value) and not math.isinf(value)
