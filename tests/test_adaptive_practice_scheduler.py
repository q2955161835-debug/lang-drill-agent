from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.past_papers.models import CoverageLedger
from langdrill_agent.past_papers.scheduler import (
    AdaptivePracticeScheduler,
    LearningTargetCandidate,
    SchedulingConfig,
)


def candidate(
    target_id: str,
    *,
    source: str,
    question_type: str = "reading",
    exam_frequency: float = 0.2,
    mastery_gap: float = 0.5,
    due: bool = False,
) -> LearningTargetCandidate:
    return LearningTargetCandidate(
        target_id=target_id,
        source=source,
        question_type=question_type,
        label=target_id,
        exam_frequency=exam_frequency,
        mastery_gap=mastery_gap,
        due=due,
    )


def test_current_import_beats_hot_exam_topic(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        result = AdaptivePracticeScheduler(conn).schedule(
            candidates=[
                candidate("consecutive", source="current_import", exam_frequency=0.01),
                candidate("common-main-idea", source="distillation", exam_frequency=0.9),
            ],
            exam_id="cet4",
            count=1,
        )

        assert result.items[0].target_id == "consecutive"


def test_hot_type_does_not_exceed_default_cap(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)
    candidates = [
        candidate(f"reading-{index}", source="distillation", exam_frequency=0.9)
        for index in range(20)
    ] + [
        candidate(f"translation-{index}", source="personal_review", question_type="translation")
        for index in range(20)
    ] + [
        candidate(f"writing-{index}", source="long_tail", question_type="writing")
        for index in range(20)
    ]

    with connect(db_path) as conn:
        result = AdaptivePracticeScheduler(conn).schedule(
            candidates=candidates,
            exam_id="cet4",
            count=20,
        )

        assert sum(item.question_type == "reading" for item in result.items) <= 7


def test_cold_enabled_type_receives_rolling_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)
    ledger = [
        CoverageLedger(
            exam_id="cet4",
            question_type="translation",
            rolling_seen=20,
            rolling_selected=0,
            coverage_debt=2,
        )
    ]
    candidates = [
        candidate(f"reading-{index}", source="distillation", exam_frequency=0.9)
        for index in range(12)
    ] + [
        candidate("cold-translation", source="long_tail", question_type="translation")
    ]

    with connect(db_path) as conn:
        result = AdaptivePracticeScheduler(conn).schedule(
            candidates=candidates,
            exam_id="cet4",
            count=10,
            ledger=ledger,
        )

        assert any(item.question_type == "translation" for item in result.items)


def test_schedule_event_keeps_scores_and_rejections(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        result = AdaptivePracticeScheduler(conn).schedule(
            candidates=[
                candidate("imported", source="current_import", question_type="reading"),
                candidate("listen", source="long_tail", question_type="listening"),
            ],
            exam_id="cet4",
            count=1,
        )
        row = conn.execute(
            "SELECT candidate_json, rejected_json, selected_json FROM practice_schedule_events WHERE id=?",
            (result.event_id,),
        ).fetchone()

        assert '"score"' in row["candidate_json"]
        assert "unsupported_or_disabled_type" in row["rejected_json"]
        assert "current_import_priority" in row["selected_json"]


def test_disabled_listening_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with connect(db_path) as conn:
        result = AdaptivePracticeScheduler(conn).schedule(
            candidates=[
                candidate("listen", source="current_import", question_type="listening"),
                candidate("read", source="personal_review", question_type="reading"),
            ],
            exam_id="cet4",
            count=1,
            config=SchedulingConfig(enabled_question_types=frozenset({"reading", "listening"})),
        )

        assert [item.target_id for item in result.items] == ["read"]
        assert result.rejected[0]["reason"] == "unsupported_or_disabled_type"
