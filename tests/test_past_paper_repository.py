from pathlib import Path

import pytest

from langdrill_agent.db import connect, init_db
from langdrill_agent.past_papers.models import (
    PaperDocumentInput,
    PaperQuestionInput,
    PaperSourceInput,
)
from langdrill_agent.past_papers.repository import PastPaperRepository


def test_remote_source_is_not_counted_as_local_paper(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = PastPaperRepository(conn)
        repo.upsert_source(
            PaperSourceInput(
                id="cet4-2025-06-1",
                exam_id="cet4",
                title="CET-4 2025-06 Set 1",
                source_url="https://example.test/paper.pdf",
                year=2025,
                session="june",
                set_number=1,
            )
        )

        assert repo.list_sources("cet4")
        assert repo.list_documents("cet4") == []


def test_replace_questions_keeps_last_verified_version_on_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = PastPaperRepository(conn)
        document = repo.create_document(
            PaperDocumentInput(
                exam_id="cet4",
                title="CET-4 2025 June Set 1",
                year=2025,
                raw_path="raw/paper.pdf",
                content_hash="sha256:paper",
                status="ready",
            )
        )
        repo.replace_questions(
            document.id,
            [
                PaperQuestionInput(
                    question_number="1",
                    question_type="reading",
                    prompt="What is the main idea?",
                    answer={"letter": "A"},
                    answer_confidence=1.0,
                    verification_status="verified",
                )
            ],
        )

        with pytest.raises(ValueError, match="duplicate question number"):
            repo.replace_questions(
                document.id,
                [
                    PaperQuestionInput(
                        question_number="2",
                        question_type="reading",
                        prompt="First replacement?",
                    ),
                    PaperQuestionInput(
                        question_number="2",
                        question_type="reading",
                        prompt="Duplicate replacement?",
                    ),
                ],
            )

        questions = repo.list_questions(document.id)
        assert [question.question_number for question in questions] == ["1"]
        assert questions[0].verification_status == "verified"
