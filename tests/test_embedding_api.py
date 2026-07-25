"""Plan 2 Task 4 Step 1: embedding management API tests.

Covers four required scenarios:

* GET /api/embeddings/status returns defaults (mode="off", effective="fts").
* POST /api/embeddings/downloads requires confirmed=True.
* POST /api/embeddings/runtime/install requires confirmed=True.
* Switching settings marks indexes "stale" without reindexing vectors.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "embeddings-api.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path / "user-data"))
    monkeypatch.setenv("LANGDRILL_ENV_FILE", str(tmp_path / ".env"))
    for key in (
        "LANGDRILL_EMBEDDING_HF_TOKEN",
        "LANGDRILL_EMBEDDING_CLOUD_API_KEY",
    ):
        os.environ.pop(key, None)
    init_db(db_path)
    return TestClient(app)


def test_status_defaults_to_fts_only(client: TestClient) -> None:
    response = client.get("/api/embeddings/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["settings"]["mode"] == "off"
    assert payload["effective_mode"] == "fts"
    assert payload["runtime"]["loaded"] is False


def test_download_requires_confirmation(client: TestClient) -> None:
    response = client.post(
        "/api/embeddings/downloads",
        json={
            "model_id": "Qwen/Qwen3-Embedding-0.6B",
            "revision": "main",
            "confirmed": False,
        },
    )

    assert response.status_code == 400
    detail = response.json().get("detail", {})
    assert isinstance(detail, dict)
    assert detail.get("code") == "EMBEDDING_DOWNLOAD_CONFIRMATION_REQUIRED"


def test_runtime_install_requires_confirmation(client: TestClient) -> None:
    response = client.post(
        "/api/embeddings/runtime/install",
        json={"confirmed": False},
    )

    assert response.status_code == 400
    detail = response.json().get("detail", {})
    assert isinstance(detail, dict)
    assert detail.get("code") == "EMBEDDING_RUNTIME_INSTALL_CONFIRMATION_REQUIRED"


def test_switch_marks_indexes_stale_without_reindex(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Switching to local mode without activate=True must persist the new mode
    # but never store an enabled_identity. All existing indexes must become
    # "stale" so retrieval keeps using FTS until the user explicitly reindexes.
    def _fake_health_probe(self: Any, settings: Any) -> Any:
        raise AssertionError("health probe must not run without activate=True")

    monkeypatch.setattr(
        "langdrill_agent.embeddings.runtime.EmbeddingRuntime.health_probe",
        _fake_health_probe,
    )

    response = client.post(
        "/api/embeddings/settings",
        json={
            "mode": "local",
            "model_id": "Qwen/Qwen3-Embedding-0.6B",
            "revision": "main",
            "activate": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["settings"]["mode"] == "local"
    assert payload["settings"]["enabled_identity"] is None
    assert payload["effective_mode"] == "fts"
    assert payload["indexes"], "indexes should be seeded after migration 009"
    assert all(
        index["status"] == "stale" for index in payload["indexes"]
    ), payload["indexes"]
