from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import connect, init_db
from langdrill_agent.knowledge.models import KnowledgeChunkInput
from langdrill_agent.knowledge.repository import KnowledgeRepository


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "knowledge-api.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path / "user-data"))
    init_db(db_path)
    return TestClient(app)


def test_import_returns_run_id(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Notes\nconsecutive means following continuously", encoding="utf-8")

    response = client.post(
        "/api/knowledge/import",
        json={"local_path": str(path), "title": "Notes", "language": "en"},
    )

    assert response.status_code == 202
    assert response.json()["run_id"].startswith("run_")
    assert response.json()["document"]["status"] == "ready"


def test_uploaded_file_import_returns_run_id(client: TestClient) -> None:
    response = client.post(
        "/api/knowledge/import-file?filename=notes.md&title=Notes&language=en",
        content=b"# Notes\nconsecutive means following continuously",
        headers={"Content-Type": "text/markdown"},
    )

    assert response.status_code == 202
    assert response.json()["run_id"].startswith("run_")
    assert response.json()["document"]["status"] == "ready"


def test_search_returns_citations(client: TestClient) -> None:
    with connect() as conn:
        repo = KnowledgeRepository(conn)
        document = repo.create_document(
            title="Notes",
            source_name="notes.md",
            mime_type="text/markdown",
            content_hash="sha256:notes",
            status="ready",
        )
        repo.upsert_chunks(
            document.id,
            [
                KnowledgeChunkInput(
                    ordinal=0,
                    heading="Vocabulary",
                    page_start=2,
                    content="consecutive means following continuously",
                    content_hash="sha256:chunk",
                    token_count=10,
                )
            ],
        )

    response = client.post("/api/knowledge/search", json={"query": "consecutive"})

    assert response.status_code == 200
    assert response.json()["mode"] == "fts"
    assert response.json()["items"][0]["citation"]["document_id"] == document.id
    assert response.json()["items"][0]["citation"]["page_start"] == 2


def test_reindex_and_delete_document(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Notes\nconsecutive means following continuously", encoding="utf-8")
    imported = client.post(
        "/api/knowledge/import",
        json={"local_path": str(path), "title": "Notes", "language": "en"},
    ).json()
    document_id = imported["document"]["id"]

    reindexed = client.post(
        "/api/knowledge/reindex",
        json={"document_id": document_id},
    )
    deleted = client.delete(f"/api/knowledge/documents/{document_id}")

    assert reindexed.status_code == 202
    assert reindexed.json()["run_id"].startswith("run_")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "document_id": document_id}


def test_failed_reindex_keeps_last_good_files(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Notes\nconsecutive means following continuously", encoding="utf-8")
    imported = client.post(
        "/api/knowledge/import",
        json={"local_path": str(path), "title": "Notes", "language": "en"},
    ).json()
    document_id = imported["document"]["id"]
    with connect() as conn:
        document = KnowledgeRepository(conn).get_document(document_id)
        raw_path = Path(document.raw_path)
        parsed_path = Path(document.parsed_path)

    from langdrill_agent.knowledge import ingestion

    def fail_extract(path: Path, *, language: str) -> tuple[str, str]:
        raise RuntimeError("refresh failed")

    monkeypatch.setattr(ingestion, "extract_text_from_file", fail_extract)
    response = client.post("/api/knowledge/reindex", json={"document_id": document_id})

    assert response.status_code == 202
    assert raw_path.exists()
    assert parsed_path.exists()
