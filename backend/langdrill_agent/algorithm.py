from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class MasteryInputs:
    correct_rate: float
    days_since_last_attempt: float
    difficulty: float
    answered_after_hint: bool
    answered_in_integrated_item: bool
    wrong_repeat_count: int


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def mastery_score(inputs: MasteryInputs) -> float:
    recency = clamp(1 - min(inputs.days_since_last_attempt, 30) / 30)
    hint_penalty = 0.12 if inputs.answered_after_hint else 0.0
    integrated_bonus = 0.06 if inputs.answered_in_integrated_item else 0.0
    wrong_penalty = min(inputs.wrong_repeat_count * 0.06, 0.24)
    difficulty_adjustment = (0.5 - inputs.difficulty) * 0.16
    raw = (
        inputs.correct_rate * 0.46
        + recency * 0.18
        + difficulty_adjustment
        + integrated_bonus
        - hint_penalty
        - wrong_penalty
        + 0.18
    )
    return round(clamp(raw), 3)


def next_review_at(score: float, from_time: datetime | None = None) -> datetime:
    base = from_time or datetime.now()
    if score < 0.25:
        return base + timedelta(hours=8)
    if score < 0.45:
        return base + timedelta(days=1)
    if score < 0.65:
        return base + timedelta(days=3)
    if score < 0.82:
        return base + timedelta(days=7)
    return base + timedelta(days=14)
