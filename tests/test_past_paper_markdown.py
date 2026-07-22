from langdrill_agent.past_papers.markdown import (
    parse_paper_markdown,
    render_paper_markdown,
)
from langdrill_agent.past_papers.parser import (
    PaperParseResult,
    ParsedPaperQuestion,
    ParsedPaperSection,
)


def test_markdown_round_trip_preserves_question_source() -> None:
    original = PaperParseResult(
        exam_id="cet4",
        title="CET-4 2025 June Set 1",
        year=2025,
        source_url="https://source.test/paper.pdf",
        sections=[ParsedPaperSection(title="Reading", question_type="reading")],
        questions=[
            ParsedPaperQuestion(
                question_number="1",
                section_title="Reading",
                question_type="reading",
                prompt="What is the main idea?",
                options=["A option", "B option", "C option"],
                answer={"letter": "B"},
                source_page=7,
                answer_confidence=1.0,
                verification_status="verified",
                knowledge_tags=["main-idea"],
            )
        ],
    )

    parsed = parse_paper_markdown(render_paper_markdown(original))

    assert parsed.schema_version == 2
    assert parsed.questions[0].source_page == 7
    assert parsed.questions[0].options[1] == "B option"
    assert parsed.questions[0].answer == {"letter": "B"}


def test_missing_answer_remains_unverified() -> None:
    parsed = parse_paper_markdown(
        """---
schema_version: 2
exam_id: cet4
title: Paper
---
# Paper

## Section: Reading

#### Question 1
Prompt?
"""
    )

    assert parsed.questions[0].answer == {}
    assert parsed.questions[0].verification_status == "unverified"
    assert parsed.questions[0].answer_confidence == 0
