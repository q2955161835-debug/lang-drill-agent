from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.past_papers.distillation import PastPaperDistillationService
from langdrill_agent.past_papers.models import PaperDocumentInput, PaperQuestionInput
from langdrill_agent.past_papers.repository import PastPaperRepository


def _add_document_with_questions(
    repo: PastPaperRepository,
    *,
    title: str,
    year: int,
    question_types: list[str],
) -> str:
    document = repo.create_document(
        PaperDocumentInput(
            exam_id="cet4",
            title=title,
            year=year,
            source_url=f"https://source.test/{title}.pdf",
            raw_path=f"raw/{title}.pdf",
            content_hash=f"sha256:{title}",
            status="ready",
        )
    )
    repo.replace_questions(
        document.id,
        [
            PaperQuestionInput(
                question_number=str(index),
                question_type=question_type,
                prompt=f"Verified {question_type} question {index} in {title}?",
                answer={"letter": "A"},
                verification_status="verified",
                answer_confidence=1,
                knowledge_tags=[question_type, "common-skill"],
                difficulty=0.5,
            )
            for index, question_type in enumerate(question_types, start=1)
        ],
    )
    return document.id


def test_distillation_refuses_single_paper_claim(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        document_id = _add_document_with_questions(
            PastPaperRepository(conn),
            title="one-paper",
            year=2025,
            question_types=["reading", "reading", "reading"],
        )
        result = PastPaperDistillationService(conn).distill("cet4", [document_id])

        assert result.status == "insufficient_evidence"
        assert result.findings == []


def test_finding_keeps_evidence_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = PastPaperRepository(conn)
        document_ids = [
            _add_document_with_questions(
                repo,
                title="paper-2024",
                year=2024,
                question_types=["reading", "reading", "translation"],
            ),
            _add_document_with_questions(
                repo,
                title="paper-2025",
                year=2025,
                question_types=["reading", "reading", "writing"],
            ),
        ]
        result = PastPaperDistillationService(conn).distill("cet4", document_ids)

        assert result.status == "ready"
        finding = next(item for item in result.findings if item.label == "reading")
        assert finding.evidence_count >= 3
        assert finding.paper_count == 2
        assert len(finding.evidence_question_ids) == finding.evidence_count
        assert set(finding.years) == {2024, 2025}
