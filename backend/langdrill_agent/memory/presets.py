"""Memory modes, user-facing groups, and security budget resolution.

Plan 3 Task 1: defines the three-tier memory mode preset (economy/standard/deep),
the three user-facing memory groups (about_me/learning_history/usage_habits) that
map onto the internal eight memory categories, and the context-aware budget
resolver that always reserves at least 30% of the available context.

Memory content is derived reference data only; it must never override the
authoritative profile / attempts / questions / mastery tables.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Literal

from pydantic import BaseModel

from ..utils import loads

MemoryMode = Literal["economy", "standard", "deep"]
MemoryGroup = Literal["about_me", "learning_history", "usage_habits"]

#: Configured token ceiling per mode. ``deep`` has no fixed ceiling and is
#: bounded only by the available-context safety budget.
MODE_LIMITS: dict[MemoryMode, int | None] = {
    "economy": 5_000,
    "standard": 10_000,
    "deep": None,
}

#: Mapping from user-facing group to the internal memory categories it covers.
#: Every internal category appears exactly once across all groups so the
#: database/export taxonomy (core/semantic/episodic/procedural/temporal/
#: preference/profile/learning_weakness) is preserved without duplication.
GROUP_CATEGORIES: dict[MemoryGroup, tuple[str, ...]] = {
    "about_me": ("core", "profile", "semantic"),
    "learning_history": ("episodic", "temporal", "learning_weakness"),
    "usage_habits": ("procedural", "preference"),
}

#: Groups in stable expansion order.
_GROUP_ORDER: tuple[MemoryGroup, ...] = ("about_me", "learning_history", "usage_habits")


class MemoryBudget(BaseModel):
    """Resolved memory budget after applying the 30% context safety reserve."""

    mode: MemoryMode
    configured_limit: int | None
    available_context_tokens: int
    reserved_tokens: int
    effective_tokens: int
    constrained_by_context: bool


def resolve_memory_budget(
    mode: MemoryMode, available_context_tokens: int
) -> MemoryBudget:
    """Resolve the effective memory token budget for a given mode.

    Always reserves at least 30% of the available context (rounded up). When
    the resulting "safe memory" is below the mode's configured limit, the
    effective budget is clamped down and ``constrained_by_context`` is set so
    the UI/API can report that a lower-than-configured budget is in effect.
    ``deep`` mode has no configured limit, so it is never marked constrained.
    """
    available = max(0, int(available_context_tokens))
    reserved = math.ceil(available * 0.30)
    safe_memory = max(0, available - reserved)
    configured = MODE_LIMITS[mode]
    if configured is None:
        effective = safe_memory
        constrained = False
    else:
        effective = min(configured, safe_memory)
        constrained = effective < configured
    return MemoryBudget(
        mode=mode,
        configured_limit=configured,
        available_context_tokens=available,
        reserved_tokens=reserved,
        effective_tokens=effective,
        constrained_by_context=constrained,
    )


def categories_for_groups(
    group_enabled: dict[MemoryGroup, bool],
) -> list[str]:
    """Expand only enabled groups into internal categories, in mapping order.

    Groups not present in ``group_enabled`` default to enabled, matching the
    long-standing behaviour where all memory categories are visible unless the
    user explicitly disables a group.
    """
    categories: list[str] = []
    for group in _GROUP_ORDER:
        if group_enabled.get(group, True):
            categories.extend(GROUP_CATEGORIES[group])
    return categories


def read_context_limit(conn: sqlite3.Connection) -> int:
    """Read ``max_tokens`` from ``app_settings['context.settings']``.

    Defaults to 1,000,000 when the key is missing, the payload is not a
    dict, or ``max_tokens`` is absent/non-positive. The floor is 1,000 so a
    misconfigured value can never zero out the memory budget.
    """
    row = conn.execute(
        "SELECT value_json FROM app_settings WHERE key='context.settings'"
    ).fetchone()
    payload = loads(row["value_json"], {}) if row else {}
    if not isinstance(payload, dict):
        return 1_000_000
    configured = payload.get("max_tokens")
    try:
        value = int(configured) if configured is not None else 1_000_000
    except (TypeError, ValueError):
        return 1_000_000
    return max(1_000, value)


def intersect_categories(
    requested: list[str] | None,
    grouped: list[str],
    internal_enabled: dict[str, bool],
) -> list[str]:
    """Intersect requested categories with grouped expansion and internal flags.

    - When ``requested`` is ``None`` the grouped list is used as the requested
      set (i.e. "all groups the caller enabled").
    - ``grouped`` defines both the candidate order and the superset; categories
      not in ``grouped`` are never returned even if explicitly requested.
    - ``internal_enabled`` can disable individual categories (e.g. a future
      per-category opt-out); categories default to enabled when absent.
    """
    requested_set = set(requested) if requested is not None else set(grouped)
    return [
        category
        for category in grouped
        if category in requested_set and internal_enabled.get(category, True)
    ]
