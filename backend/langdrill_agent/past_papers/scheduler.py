from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from ..utils import dumps, new_id
from .models import CoverageLedger

CandidateSource = Literal[
    "current_import",
    "personal_review",
    "distillation",
    "long_tail",
]


@dataclass(frozen=True, slots=True)
class SchedulingConfig:
    import_min_ratio: float = 0.40
    personal_review_ratio: float = 0.25
    exam_pattern_ratio: float = 0.20
    long_tail_min_ratio: float = 0.10
    max_question_type_ratio: float = 0.35
    rolling_question_window: int = 20
    enabled_question_types: frozenset[str] = field(default_factory=frozenset)
    specialist_only: bool = False


class LearningTargetCandidate(BaseModel):
    target_id: str
    source: CandidateSource
    question_type: str
    label: str
    mastery_gap: float = Field(default=0.5, ge=0, le=1)
    due: bool = False
    uncertainty: float = Field(default=0.5, ge=0, le=1)
    coverage_debt: float = Field(default=0, ge=0)
    exam_frequency: float = Field(default=0, ge=0, le=1)
    repetition_penalty: float = Field(default=0, ge=0, le=1)
    payload: dict[str, object] = Field(default_factory=dict)


class ScheduledTarget(BaseModel):
    target_id: str
    source: CandidateSource
    question_type: str
    label: str
    score: float
    reason: str
    payload: dict[str, object] = Field(default_factory=dict)


class ScheduleDecision(BaseModel):
    event_id: str
    exam_id: str
    items: list[ScheduledTarget] = Field(default_factory=list)
    rejected: list[dict[str, object]] = Field(default_factory=list)
    allocation: dict[str, int] = Field(default_factory=dict)


class AdaptivePracticeScheduler:
    SUPPORTED_TYPES = frozenset(
        {
            "reading",
            "translation",
            "writing",
            "writing_task1",
            "writing_task2",
            "speaking",
            "cloze",
            "grammar",
            "grammar_vocabulary",
            "vocabulary",
            "context_vocabulary",
            "grammar_fill",
        }
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def schedule(
        self,
        *,
        candidates: list[LearningTargetCandidate],
        exam_id: str,
        count: int,
        config: SchedulingConfig | None = None,
        ledger: list[CoverageLedger] | None = None,
        session_id: str = "",
    ) -> ScheduleDecision:
        active_config = config or SchedulingConfig()
        requested_count = max(0, count)
        enabled_types = (
            active_config.enabled_question_types or self.SUPPORTED_TYPES
        ) & self.SUPPORTED_TYPES
        rejected: list[dict[str, object]] = []
        eligible: list[LearningTargetCandidate] = []
        seen_ids: set[str] = set()
        ledger_by_type = {
            item.question_type: item
            for item in (ledger if ledger is not None else self._load_ledger(exam_id))
        }
        for candidate in candidates:
            if candidate.target_id in seen_ids:
                rejected.append(
                    {"target_id": candidate.target_id, "reason": "duplicate_target"}
                )
                continue
            seen_ids.add(candidate.target_id)
            if candidate.question_type not in enabled_types:
                rejected.append(
                    {
                        "target_id": candidate.target_id,
                        "reason": "unsupported_or_disabled_type",
                    }
                )
                continue
            debt = ledger_by_type.get(candidate.question_type)
            eligible.append(
                candidate.model_copy(
                    update={
                        "coverage_debt": max(
                            candidate.coverage_debt,
                            debt.coverage_debt if debt else 0,
                        )
                    }
                )
            )

        type_cap = max(1, math.floor(requested_count * active_config.max_question_type_ratio))
        selected: list[LearningTargetCandidate] = []
        selected_ids: set[str] = set()
        type_counts: dict[str, int] = {}

        def select(candidate: LearningTargetCandidate) -> bool:
            if len(selected) >= requested_count or candidate.target_id in selected_ids:
                return False
            if type_counts.get(candidate.question_type, 0) >= type_cap:
                return False
            selected.append(candidate)
            selected_ids.add(candidate.target_id)
            type_counts[candidate.question_type] = type_counts.get(candidate.question_type, 0) + 1
            return True

        if not active_config.specialist_only:
            debt_types = sorted(
                {
                    item.question_type
                    for item in eligible
                    if item.coverage_debt > 0
                },
                key=lambda question_type: (
                    -max(
                        item.coverage_debt
                        for item in eligible
                        if item.question_type == question_type
                    ),
                    question_type,
                ),
            )
            long_tail_floor = math.ceil(requested_count * active_config.long_tail_min_ratio)
            for question_type in debt_types[:long_tail_floor]:
                options = [
                    item
                    for item in eligible
                    if item.question_type == question_type and item.target_id not in selected_ids
                ]
                if options:
                    select(max(options, key=self._score_key))

        quotas = {
            "current_import": math.ceil(requested_count * active_config.import_min_ratio),
            "personal_review": math.ceil(
                requested_count * active_config.personal_review_ratio
            ),
            "distillation": math.ceil(requested_count * active_config.exam_pattern_ratio),
            "long_tail": math.ceil(requested_count * active_config.long_tail_min_ratio),
        }
        for source in ("current_import", "personal_review", "distillation", "long_tail"):
            source_selected = sum(item.source == source for item in selected)
            needed = max(0, quotas[source] - source_selected)
            options = sorted(
                (
                    item
                    for item in eligible
                    if item.source == source and item.target_id not in selected_ids
                ),
                key=self._score_key,
                reverse=True,
            )
            for item in options:
                if needed <= 0:
                    break
                if select(item):
                    needed -= 1

        for item in sorted(eligible, key=self._score_key, reverse=True):
            if len(selected) >= requested_count:
                break
            select(item)

        for item in eligible:
            if item.target_id in selected_ids:
                continue
            reason = (
                "question_type_cap"
                if type_counts.get(item.question_type, 0) >= type_cap
                else "lower_score_or_capacity"
            )
            rejected.append({"target_id": item.target_id, "reason": reason})

        scheduled = [
            ScheduledTarget(
                target_id=item.target_id,
                source=item.source,
                question_type=item.question_type,
                label=item.label,
                score=self._score(item),
                reason=self._reason(item),
                payload=item.payload,
            )
            for item in selected
        ]
        allocation: dict[str, int] = {}
        for item in scheduled:
            allocation[item.source] = allocation.get(item.source, 0) + 1
        event_id = new_id("schedule")
        self.conn.execute(
            """
            INSERT INTO practice_schedule_events
            (id, session_id, exam_id, candidate_json, rejected_json,
             allocation_json, selected_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session_id,
                exam_id,
                dumps(
                    [
                        {
                            **item.model_dump(mode="json"),
                            "score": self._score(item),
                        }
                        for item in eligible
                    ]
                ),
                dumps(rejected),
                dumps(allocation),
                dumps([item.model_dump(mode="json") for item in scheduled]),
            ),
        )
        self._update_ledger(
            exam_id,
            enabled_types,
            type_counts,
            requested_count,
            active_config,
            ledger_by_type,
        )
        return ScheduleDecision(
            event_id=event_id,
            exam_id=exam_id,
            items=scheduled,
            rejected=rejected,
            allocation=allocation,
        )

    @staticmethod
    def _score(candidate: LearningTargetCandidate) -> float:
        source_bonus = {
            "current_import": 2.0,
            "personal_review": 1.2,
            "distillation": 0.7,
            "long_tail": 0.5,
        }[candidate.source]
        return round(
            source_bonus
            + 1.4 * candidate.mastery_gap
            + (0.8 if candidate.due else 0)
            + 0.5 * candidate.uncertainty
            + 0.7 * candidate.coverage_debt
            + 0.4 * candidate.exam_frequency
            - 0.8 * candidate.repetition_penalty,
            6,
        )

    @classmethod
    def _score_key(cls, candidate: LearningTargetCandidate) -> tuple[float, str]:
        return cls._score(candidate), candidate.target_id

    @staticmethod
    def _reason(candidate: LearningTargetCandidate) -> str:
        if candidate.source == "current_import":
            return "current_import_priority"
        if candidate.coverage_debt > 0:
            return "rolling_coverage_debt"
        if candidate.due:
            return "due_personal_review"
        if candidate.source == "distillation":
            return "evidence_backed_exam_pattern"
        return "balanced_learning_target"

    def _load_ledger(self, exam_id: str) -> list[CoverageLedger]:
        rows = self.conn.execute(
            "SELECT * FROM practice_coverage_ledger WHERE exam_id=?",
            (exam_id,),
        ).fetchall()
        return [
            CoverageLedger(
                exam_id=row["exam_id"],
                question_type=row["question_type"],
                enabled=bool(row["enabled"]),
                rolling_seen=row["rolling_seen"],
                rolling_selected=row["rolling_selected"],
                coverage_debt=row["coverage_debt"],
            )
            for row in rows
        ]

    def _update_ledger(
        self,
        exam_id: str,
        enabled_types: frozenset[str],
        type_counts: dict[str, int],
        requested_count: int,
        config: SchedulingConfig,
        existing: dict[str, CoverageLedger],
    ) -> None:
        expected_floor = requested_count * config.long_tail_min_ratio
        for question_type in sorted(enabled_types):
            previous = existing.get(
                question_type,
                CoverageLedger(exam_id=exam_id, question_type=question_type),
            )
            selected_count = type_counts.get(question_type, 0)
            rolling_seen = min(
                config.rolling_question_window,
                previous.rolling_seen + requested_count,
            )
            rolling_selected = min(
                config.rolling_question_window,
                previous.rolling_selected + selected_count,
            )
            debt = max(
                0,
                previous.coverage_debt
                + expected_floor
                - selected_count,
            )
            self.conn.execute(
                """
                INSERT INTO practice_coverage_ledger
                (exam_id, question_type, enabled, rolling_seen,
                 rolling_selected, coverage_debt, updated_at)
                VALUES (?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(exam_id, question_type) DO UPDATE SET
                  enabled=1,
                  rolling_seen=excluded.rolling_seen,
                  rolling_selected=excluded.rolling_selected,
                  coverage_debt=excluded.coverage_debt,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    exam_id,
                    question_type,
                    rolling_seen,
                    rolling_selected,
                    debt,
                ),
            )
