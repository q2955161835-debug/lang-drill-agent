from __future__ import annotations

import pytest

from langdrill_agent.models import Question
from langdrill_agent.validator import QuestionValidationError, QuestionValidator


def _question(**overrides) -> Question:
    data = {
        "id": "q_validator",
        "session_id": "ses_validator",
        "sequence": 1,
        "type": "multiple_choice",
        "prompt": "Which option best completes the sentence?",
        "options": ["context", "evidence", "method"],
        "answer": {"letter": "B", "correct": "evidence"},
        "explanation": "Evidence fits the sentence.",
        "knowledge_tags": ["vocabulary:evidence"],
        "difficulty": 0.4,
        "source_refs": [],
    }
    data.update(overrides)
    return Question(**data)


def test_validator_accepts_answer_letter_and_matching_text() -> None:
    question = _question(answer={"letter": "B", "correct": "evidence"})

    assert QuestionValidator().validate(question) is question


def test_validator_accepts_answer_text_without_letter() -> None:
    question = _question(answer={"correct": "method"})

    assert QuestionValidator().validate(question) is question


def test_validator_rejects_letter_outside_existing_options() -> None:
    question = _question(options=["context", "evidence"], answer={"letter": "D", "correct": "D"})

    with pytest.raises(QuestionValidationError, match="答案字母必须对应现有选项"):
        QuestionValidator().validate(question)


def test_validator_rejects_inconsistent_letter_and_answer_text() -> None:
    question = _question(answer={"letter": "A", "correct": "evidence"})

    with pytest.raises(QuestionValidationError, match="答案字母与答案文本不一致"):
        QuestionValidator().validate(question)


def test_validator_rejects_missing_knowledge_tags() -> None:
    question = _question(knowledge_tags=[])

    with pytest.raises(QuestionValidationError, match="knowledge_tags"):
        QuestionValidator().validate(question)

