from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from langdrill_agent.embeddings.catalog import EmbeddingModelCatalog


def model_info(
    *,
    model_id: str = "org/model",
    sha: str = "abc123",
    pipeline_tag: str = "feature-extraction",
    library_name: str = "sentence-transformers",
    license: str = "apache-2.0",
    siblings: list[str] | None = None,
    downloads: int = 0,
    likes: int = 0,
) -> SimpleNamespace:
    """Build a Hugging Face ``ModelInfo``-shaped object for tests."""

    if siblings is None:
        siblings = ["config.json", "model.safetensors", "tokenizer.json"]
    return SimpleNamespace(
        model_id=model_id,
        sha=sha,
        pipeline_tag=pipeline_tag,
        library_name=library_name,
        card_data=SimpleNamespace(license=license) if license else None,
        siblings=[
            SimpleNamespace(rfilename=name, size=None) for name in siblings
        ],
        downloads=downloads,
        likes=likes,
    )


@pytest.fixture
def fake_hf_client() -> Mock:
    client = Mock()
    client.model_info.return_value = model_info()
    client.list_models.return_value = []
    return client


def test_recommendations_start_with_qwen(fake_hf_client: Mock) -> None:
    catalog = EmbeddingModelCatalog(client=fake_hf_client)
    recommendations = catalog.recommendations()
    assert recommendations
    assert recommendations[0].model_id == "Qwen/Qwen3-Embedding-0.6B"
    assert recommendations[0].recommended is True


def test_remote_code_only_model_cannot_be_enabled(fake_hf_client: Mock) -> None:
    fake_hf_client.model_info.return_value = model_info(
        model_id="unsafe/model",
        pipeline_tag="feature-extraction",
        siblings=["config.json", "modeling_custom.py"],
        library_name="transformers",
        license="apache-2.0",
    )
    detail = EmbeddingModelCatalog(client=fake_hf_client).detail("unsafe/model")
    assert detail.compatible is False
    assert "remote_code" in detail.blockers


def test_search_is_not_limited_to_recommendations(fake_hf_client: Mock) -> None:
    fake_hf_client.list_models.return_value = [
        model_info(model_id="org/custom-embed")
    ]
    items = EmbeddingModelCatalog(client=fake_hf_client).search("custom")
    assert items
    assert items[0].model_id == "org/custom-embed"
