"""Hugging Face model discovery with explicit compatibility rules."""

from __future__ import annotations

from typing import Any

from .models import EmbeddingModelDetail, EmbeddingModelSummary

SUPPORTED_WEIGHT_SUFFIXES = {".safetensors"}
SUPPORTED_LIBRARIES = {"sentence-transformers", "transformers"}
SUPPORTED_PIPELINE_TAGS = {"feature-extraction", "sentence-similarity"}

TOKENIZER_FILENAMES = {
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "vocab.json",
    "merges.txt",
    "special_tokens_map.json",
    "spiece.model",
}

RECOMMENDED_MODEL_IDS = [
    "Qwen/Qwen3-Embedding-0.6B",
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
]

MODEL_LIBRARY_SENTENCE_TRANSFORMERS = "sentence-transformers"
MODEL_PIPELINE_FEATURE_EXTRACTION = "feature-extraction"


class EmbeddingModelCatalog:
    """Discover Hugging Face embedding models and assess compatibility.

    ``trust_remote_code`` is never enabled. Recommendations are a hardcoded,
    vetted list and do not perform any cloud call. ``search`` and ``detail``
    are explicit user-triggered cloud calls.
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _resolve_client(self) -> Any:
        if self._client is None:
            from huggingface_hub import HfApi

            self._client = HfApi()
        return self._client

    def recommendations(self) -> list[EmbeddingModelSummary]:
        """Return the curated, vetted recommendation list (no cloud call)."""

        return [
            EmbeddingModelSummary(
                model_id=model_id,
                revision="",
                license="",
                library=MODEL_LIBRARY_SENTENCE_TRANSFORMERS,
                pipeline_tag=MODEL_PIPELINE_FEATURE_EXTRACTION,
                downloads=0,
                likes=0,
                size_bytes=0,
                compatible=True,
                blockers=[],
                recommended=True,
            )
            for model_id in RECOMMENDED_MODEL_IDS
        ]

    def search(self, query: str) -> list[EmbeddingModelSummary]:
        """Search Hugging Face for feature-extraction models (cloud call)."""

        client = self._resolve_client()
        items = client.list_models(
            search=query,
            pipeline_tag=MODEL_PIPELINE_FEATURE_EXTRACTION,
            sort="downloads",
            direction=-1,
            limit=20,
            full=True,
        )
        return [self._summarize(item, recommended=False) for item in items]

    def detail(
        self, model_id: str, revision: str | None = None
    ) -> EmbeddingModelDetail:
        """Fetch full model metadata and assess compatibility (cloud call)."""

        client = self._resolve_client()
        info = client.model_info(model_id, revision=revision)
        summary = self._summarize(
            info, recommended=model_id in RECOMMENDED_MODEL_IDS
        )
        download_files = self._collect_download_files(info)
        return EmbeddingModelDetail(
            **summary.model_dump(),
            download_files=download_files,
        )

    def _summarize(
        self, info: Any, *, recommended: bool
    ) -> EmbeddingModelSummary:
        siblings = list(info.siblings or []) if info.siblings is not None else []
        sibling_names = [getattr(sibling, "rfilename", "") for sibling in siblings]
        license_name = self._extract_license(info)
        size_bytes = sum(
            (getattr(sibling, "size", None) or 0) for sibling in siblings
        )

        blockers: list[str] = []
        if (info.pipeline_tag or "") not in SUPPORTED_PIPELINE_TAGS:
            blockers.append("unsupported_pipeline")
        if (info.library_name or "") not in SUPPORTED_LIBRARIES:
            blockers.append("unsupported_library")
        if not license_name:
            blockers.append("missing_license")
        if not any(
            name.endswith(suffix) for name in sibling_names
            for suffix in SUPPORTED_WEIGHT_SUFFIXES
        ):
            blockers.append("missing_safetensors")
        if any(
            name.endswith(".py") and "modeling_" in name for name in sibling_names
        ):
            blockers.append("remote_code")

        return EmbeddingModelSummary(
            model_id=info.model_id,
            revision=getattr(info, "sha", "") or "",
            license=license_name,
            library=info.library_name or "",
            pipeline_tag=info.pipeline_tag or "",
            downloads=getattr(info, "downloads", 0) or 0,
            likes=getattr(info, "likes", 0) or 0,
            size_bytes=size_bytes,
            compatible=not blockers,
            blockers=blockers,
            recommended=recommended,
        )

    @staticmethod
    def _extract_license(info: Any) -> str:
        card = getattr(info, "card_data", None)
        if card is not None:
            license_name = getattr(card, "license", None)
            if license_name:
                return license_name
        return getattr(info, "license", "") or ""

    @staticmethod
    def _collect_download_files(info: Any) -> list[str]:
        siblings = list(info.siblings or []) if info.siblings is not None else []
        download_files: list[str] = []
        for sibling in siblings:
            name = getattr(sibling, "rfilename", "")
            if not name or name.endswith(".py"):
                continue
            if name.endswith(".safetensors"):
                download_files.append(name)
            elif name == "config.json":
                download_files.append(name)
            elif name in TOKENIZER_FILENAMES:
                download_files.append(name)
        return download_files
