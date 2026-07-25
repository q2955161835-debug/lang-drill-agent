from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from langdrill_agent.db import connect, init_db
from langdrill_agent.embeddings.downloads import EmbeddingDownloadService
from langdrill_agent.embeddings.runtime_install import (
    EmbeddingRuntimeInstallService,
)


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
def conn(tmp_path: Path):
    db_path = tmp_path / "embeddings.db"
    init_db(db_path)
    with connect(db_path) as connection:
        yield connection


@pytest.fixture
def fake_hf_client() -> Mock:
    client = Mock()
    client.model_info.return_value = model_info()
    client.list_models.return_value = []
    client.hf_hub_download = Mock(return_value=Path("/cache/file.bin"))
    return client


@pytest.fixture
def fake_runner() -> Mock:
    runner = Mock()
    runner.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
    return runner


def test_download_reuses_cached_files(
    conn, tmp_path: Path, fake_hf_client: Mock
) -> None:
    service = EmbeddingDownloadService(conn, hub=fake_hf_client)
    job = service.create(
        "Qwen/Qwen3-Embedding-0.6B", "rev123", tmp_path, confirmed=True
    )
    service.run(job.id)
    assert service.status(job.id).status == "completed"
    assert fake_hf_client.hf_hub_download.call_count == 3


def test_cancel_is_checked_between_files(
    conn, tmp_path: Path, fake_hf_client: Mock
) -> None:
    service = EmbeddingDownloadService(conn, hub=fake_hf_client)
    job = service.create("org/model", "rev123", tmp_path, confirmed=True)
    service.cancel(job.id)
    service.run(job.id)
    assert service.status(job.id).status == "cancelled"
    fake_hf_client.hf_hub_download.assert_not_called()


def test_runtime_install_requires_confirmation(conn) -> None:
    service = EmbeddingRuntimeInstallService(conn, runner=Mock())
    with pytest.raises(
        ValueError, match="EMBEDDING_RUNTIME_INSTALL_CONFIRMATION_REQUIRED"
    ):
        service.create(confirmed=False)


def test_runtime_install_uses_fixed_packages_only(
    conn, fake_runner: Mock
) -> None:
    service = EmbeddingRuntimeInstallService(conn, runner=fake_runner)
    job = service.create(confirmed=True)
    service.run(job.id)
    assert service.status(job.id).status == "completed"
    command = fake_runner.call_args.args[0]
    assert command == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "sentence-transformers>=5.0,<6",
        "safetensors>=0.5,<1",
    ]
