from langdrill_agent.memory.models import MemoryCandidate, MemoryItem
from langdrill_agent.memory.policy import (
    MemoryPolicy,
    MemoryPolicyConfig,
    MemoryPolicyEvidence,
)


def candidate(
    content: str,
    *,
    category: str = "preference",
    normalized_key: str = "preference:general",
    confidence: float = 0.9,
    explicit: bool = False,
) -> MemoryCandidate:
    return MemoryCandidate(
        category=category,
        content=content,
        normalized_key=normalized_key,
        confidence=confidence,
        metadata={"explicit": explicit},
    )


def existing(content: str, *, normalized_key: str) -> MemoryItem:
    return MemoryItem(
        id="memory_existing",
        category="profile",
        content=content,
        normalized_key=normalized_key,
        confidence=0.9,
    )


def test_small_talk_is_noop() -> None:
    decision = MemoryPolicy().evaluate(candidate("Thanks"), [], [])

    assert decision.operation == "NOOP"
    assert decision.reason == "low_future_utility"


def test_one_wrong_answer_does_not_create_weakness() -> None:
    weakness = candidate(
        "User struggles with conditionals",
        category="learning_weakness",
        normalized_key="weakness:conditionals",
    )
    evidence = [
        MemoryPolicyEvidence(
            id="attempt:1",
            kind="wrong_attempt",
            session_id="session-1",
            knowledge_key="conditionals",
        )
    ]

    decision = MemoryPolicy().evaluate(weakness, [], evidence)

    assert decision.operation == "STAGE"
    assert decision.reason == "insufficient_learning_evidence"


def test_three_independent_errors_can_create_weakness() -> None:
    weakness = candidate(
        "User repeatedly struggles with conditionals",
        category="learning_weakness",
        normalized_key="weakness:conditionals",
    )
    evidence = [
        MemoryPolicyEvidence(
            id=f"attempt:{index}",
            kind="wrong_attempt",
            session_id=f"session-{index}",
            knowledge_key="conditionals",
        )
        for index in range(3)
    ]

    decision = MemoryPolicy().evaluate(weakness, [], evidence)

    assert decision.operation == "ADD"
    assert decision.evidence_ids == ["attempt:0", "attempt:1", "attempt:2"]


def test_api_key_value_is_never_stored() -> None:
    decision = MemoryPolicy().evaluate(
        candidate(
            "Remember OPENAI_API_KEY=sk-test-secret-value",
            explicit=True,
        ),
        [],
        [],
    )

    assert decision.operation == "NOOP"
    assert decision.reason == "secret_detected"
    assert "sk-test-secret-value" not in decision.sanitized_content


def test_duplicate_is_noop_and_material_conflict_supersedes() -> None:
    memory = existing(
        "Exam deadline is 2026-09-01",
        normalized_key="profile:exam_deadline",
    )
    policy = MemoryPolicy(MemoryPolicyConfig(write_mode="proactive"))

    duplicate = policy.evaluate(
        candidate(
            "Exam deadline is 2026-09-01",
            category="profile",
            normalized_key="profile:exam_deadline",
        ),
        [memory],
        [],
    )
    conflict = policy.evaluate(
        candidate(
            "Exam deadline is 2026-10-01",
            category="profile",
            normalized_key="profile:exam_deadline",
        ),
        [memory],
        [],
    )

    assert duplicate.operation == "NOOP"
    assert duplicate.reason == "duplicate_memory"
    assert conflict.operation == "SUPERSEDE"
    assert conflict.target_memory_id == memory.id
