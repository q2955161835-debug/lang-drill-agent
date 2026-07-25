from __future__ import annotations

import os
from pathlib import Path

import pytest

from langdrill_agent.config import env_file_path
from langdrill_agent.db import connect, init_db
from langdrill_agent.embeddings.models import (
    EmbeddingIdentity,
    EmbeddingSettingsPatch,
)
from langdrill_agent.embeddings.settings import EmbeddingSettingsService
from langdrill_agent.utils import dumps


@pytest.fixture
def conn(tmp_path: Path):
    db_path = tmp_path / "embeddings.db"
    init_db(db_path)
    with connect(db_path) as connection:
        yield connection


@pytest.fixture(autouse=True)
def _isolate_embedding_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGDRILL_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path))
    yield
    for key in (
        "LANGDRILL_EMBEDDING_HF_TOKEN",
        "LANGDRILL_EMBEDDING_CLOUD_API_KEY",
    ):
        os.environ.pop(key, None)


def test_embedding_settings_default_to_off(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path))
    settings = EmbeddingSettingsService(conn).get()
    assert settings.mode == "off"
    assert settings.model_id == ""
    assert settings.model_dir == str(tmp_path / "models" / "embeddings")
    assert settings.api_key_configured is False


def test_identity_changes_with_revision_or_dimensions():
    first = EmbeddingIdentity(
        provider="local",
        model_id="Qwen/Qwen3-Embedding-0.6B",
        revision="abc",
        dimensions=1024,
    )
    second = first.model_copy(update={"revision": "def"})
    third = first.model_copy(update={"dimensions": 768})
    assert len({first.key, second.key, third.key}) == 3


def test_save_writes_secret_only_to_env(conn, tmp_path, monkeypatch):
    saved = EmbeddingSettingsService(conn).save(
        EmbeddingSettingsPatch(
            mode="huggingface_cloud",
            model_id="sentence-transformers/all-MiniLM-L6-v2",
            api_key="hf_secret_value",
        )
    )
    assert saved.api_key_configured is True
    assert "hf_secret_value" not in dumps(saved.model_dump())
    assert "hf_secret_value" in env_file_path().read_text(encoding="utf-8")
