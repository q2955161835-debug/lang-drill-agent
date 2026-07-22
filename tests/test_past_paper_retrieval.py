from pathlib import Path

import pytest

from langdrill_agent.db import connect, init_db
from langdrill_agent.models import Question
from langdrill_agent.past_papers.models import PaperDocumentInput, PaperQuestionInput
from langdrill_agent.past_papers.repository import PastPaperRepository
from langdrill_agent.past_papers.retrieval import PastPaperQuery, PastPaperRetrievalService
from langdrill_agent.validator import QuestionValidationError, QuestionValidator


def _add_question(
    repo: PastPaperRepository,
    *,
    exam_id: str,
    title: str,
    question_type: str,
    prompt: str,
    verification_status: str = "verified",
) -> str:
    document = repo.create_document(
        PaperDocumentInput(
            exam_id=exam_id,
            title=title,
            year=2025,
            source_url=f"https://source.test/{exam_id}/{title}.pdf",
            raw_path=f"raw/{title}.pdf",
            content_hash=f"sha256:{exam_id}-{title}",
            status="ready",
        )
    )
    return repo.replace_questions(
        document.id,
        [
            PaperQuestionInput(
                question_number="1",
                question_type=question_type,
                prompt=prompt,
                answer={"letter": "A"},
                answer_confidence=1 if verification_status == "verified" else 0.4,
                verification_status=verification_status,
            )
        ],
    )[0].id


def test_retrieval_filters_exam_and_type(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = PastPaperRepository(conn)
        expected_id = _add_question(
            repo,
            exam_id="cet4",
            title="cet4-reading",
            question_type="reading",
            prompt="What is the main idea of the passage?",
        )
        _add_question(
            repo,
            exam_id="cet4",
            title="cet4-translation",
            question_type="translation",
            prompt="Translate the main idea into English.",
        )
        _add_question(
            repo,
            exam_id="cet6",
            title="cet6-reading",
            question_type="reading",
            prompt="What is the main idea of this advanced passage?",
        )

        result = PastPaperRetrievalService(conn).search(
            PastPaperQuery(
                exam_id="cet4",
                text="main idea",
                question_types=["reading"],
                top_k=5,
            )
        )

        assert [item.id for item in result.items] == [expected_id]
        assert all(
            item.exam_id == "cet4" and item.question_type == "reading"
            for item in result.items
        )


def test_unverified_answer_is_style_only_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = PastPaperRepository(conn)
        _add_question(
            repo,
            exam_id="cet4",
            title="unverified",
            question_type="reading",
            prompt="Choose the best title for the passage.",
            verification_status="unverified",
        )

        item = PastPaperRetrievalService(conn).search(
            PastPaperQuery(exam_id="cet4", text="best title", top_k=1)
        ).items[0]

        assert item.style_evidence is True
        assert item.correctness_evidence is False
        assert item.answer == {}


def test_validator_rejects_unknown_or_original_paper_claim() -> None:
    question = Question(
        id="q1",
        session_id="s1",
        sequence=1,
        type="multiple_choice",
        prompt="Which option best completes this sentence?",
        options=["First option", "Second option"],
        answer={"letter": "A", "correct": "First option"},
        explanation="The first option matches the sentence context.",
        knowledge_tags=["context"],
        source_refs=[
            {
                "type": "past_paper_evidence",
                "question_id": "unknown",
                "claim": "original_paper_question",
            }
        ],
    )

    with pytest.raises(QuestionValidationError):
        QuestionValidator().validate_source_refs(question, {"known"})
