from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import connect, init_db
from langdrill_agent.past_papers.models import (
    PaperDocumentInput,
    PaperQuestionInput,
    PaperSourceInput,
)
from langdrill_agent.past_papers.repository import PastPaperRepository


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "past-papers-api.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path / "user-data"))
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "papers"))
    init_db(db_path)
    return TestClient(app)


def test_catalog_does_not_report_remote_as_installed(client: TestClient) -> None:
    with connect() as conn:
        PastPaperRepository(conn).upsert_source(
            PaperSourceInput(
                id="cet4-2025-06-1",
                exam_id="cet4",
                title="CET-4 2025 June Set 1",
                source_url="https://source.test/2025-06-set1.pdf",
                year=2025,
                session="june",
                set_number=1,
            )
        )

    response = client.get("/api/past-papers/catalog?exam_id=cet4")

    assert response.status_code == 200
    payload = response.json()
    assert payload["remote_count"] == 1
    assert payload["installed_count"] == 0
    assert payload["sources"][0]["installed"] is False
    assert payload["documents"] == []


def test_reparse_uses_user_edited_markdown(client: TestClient, tmp_path: Path) -> None:
    raw_path = tmp_path / "paper.txt"
    markdown_path = tmp_path / "paper.md"
    structured_path = tmp_path / "paper.json"
    raw_path.write_text("1. Old raw question?\nA. Old\nB. Other\n", encoding="utf-8")
    markdown_path.write_text(
        """---
schema_version: 2
exam_id: cet4
title: Edited Paper
---
# Paper

## Section: Reading

#### Question 1
Which statement reflects the user's reviewed version?

- [A] Reviewed answer
- [B] Other answer

```paper-question
{"question_type":"reading","answer":{"letter":"A"},"knowledge_tags":["reviewed"],"answer_confidence":1,"verification_status":"verified"}
```
""",
        encoding="utf-8",
    )
    with connect() as conn:
        repo = PastPaperRepository(conn)
        document = repo.create_document(
            PaperDocumentInput(
                exam_id="cet4",
                title="Edited Paper",
                source_url="https://source.test/edited.pdf",
                raw_path=str(raw_path),
                markdown_path=str(markdown_path),
                structured_path=str(structured_path),
                content_hash="sha256:edited",
                status="ready",
            )
        )
        repo.replace_questions(
            document.id,
            [
                PaperQuestionInput(
                    question_number="1",
                    question_type="reading",
                    prompt="Old indexed prompt?",
                )
            ],
        )

    response = client.post(
        "/api/past-papers/reparse",
        json={"document_id": document.id},
    )

    assert response.status_code == 202
    with connect() as conn:
        question = PastPaperRepository(conn).list_questions(document.id)[0]
    assert question.prompt == "Which statement reflects the user's reviewed version?"
    assert question.verification_status == "verified"


def test_reindex_restores_fts_rows(client: TestClient, tmp_path: Path) -> None:
    raw_path = tmp_path / "indexed.txt"
    raw_path.write_text("paper", encoding="utf-8")
    with connect() as conn:
        repo = PastPaperRepository(conn)
        document = repo.create_document(
            PaperDocumentInput(
                exam_id="cet4",
                title="Indexed Paper",
                source_url="https://source.test/indexed.pdf",
                raw_path=str(raw_path),
                content_hash="sha256:indexed",
                status="ready",
            )
        )
        repo.replace_questions(
            document.id,
            [
                PaperQuestionInput(
                    question_number="1",
                    question_type="reading",
                    prompt="Which renewable energy source is discussed?",
                )
            ],
        )
        conn.execute(
            "DELETE FROM past_paper_question_fts WHERE document_id=?",
            (document.id,),
        )

    response = client.post(
        "/api/past-papers/reindex",
        json={"document_id": document.id},
    )
    search = client.post(
        "/api/past-papers/search",
        json={"exam_id": "cet4", "query": "renewable energy"},
    )

    assert response.status_code == 202
    assert response.json()["question_count"] == 1
    assert search.status_code == 200
    assert search.json()["items"][0]["id"]


def test_settings_round_trip_keeps_safety_bounds(client: TestClient) -> None:
    response = client.post(
        "/api/past-papers/settings",
        json={
            "exam_id": "cet4",
            "auto_sync": True,
            "sync_cadence_hours": 12,
            "recent_count": 5,
            "allowed_sources": ["https://source.test/exams"],
            "parser": "auto",
            "auto_distill": True,
            "verified_answers_only": True,
            "long_tail_min_ratio": 0.15,
            "max_question_type_ratio": 0.4,
            "coverage_window": 30,
        },
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["auto_sync"] is True
    assert settings["recent_count"] == 5
    assert settings["verified_answers_only"] is True
    assert settings["long_tail_min_ratio"] == 0.15
