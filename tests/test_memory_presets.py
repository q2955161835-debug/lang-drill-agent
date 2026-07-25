import math
import sqlite3

import pytest

from langdrill_agent.memory.presets import (
    GROUP_CATEGORIES,
    MemoryBudget,
    categories_for_groups,
    intersect_categories,
    read_context_limit,
    resolve_memory_budget,
)
from langdrill_agent.utils import dumps


@pytest.mark.parametrize(
    ("mode", "available", "expected"),
    [
        ("economy", 100_000, 5_000),
        ("standard", 100_000, 10_000),
        ("deep", 100_000, 70_000),
        ("deep", 8_000, 5_600),
        ("standard", 6_000, 4_200),
    ],
)
def test_resolve_memory_budget(mode, available, expected):
    budget = resolve_memory_budget(mode, available)
    assert budget.effective_tokens == expected
    assert budget.reserved_tokens >= math.ceil(available * 0.30)


def test_group_mapping_covers_internal_categories_once():
    flattened = [category for values in GROUP_CATEGORIES.values() for category in values]
    assert sorted(flattened) == sorted({
        "core", "semantic", "episodic", "procedural", "temporal",
        "preference", "profile", "learning_weakness",
    })
    assert len(flattened) == len(set(flattened))


def test_categories_for_groups_only_includes_enabled():
    result = categories_for_groups({
        "about_me": True,
        "learning_history": False,
        "usage_habits": True,
    })
    assert result == ["core", "profile", "semantic", "procedural", "preference"]


def test_read_context_limit_defaults_to_one_million(conn: sqlite3.Connection):
    # app_settings 无 context.settings 键时返回 1_000_000
    assert read_context_limit(conn) == 1_000_000


def test_read_context_limit_reads_max_tokens(conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO app_settings(key,value_json) VALUES ('context.settings', ?)",
        (dumps({"max_tokens": 200_000}),),
    )
    assert read_context_limit(conn) == 200_000


def test_intersect_categories_respects_internal_enabled():
    result = intersect_categories(
        requested=None,
        grouped=["core", "profile", "semantic"],
        internal_enabled={"core": True, "profile": False, "semantic": True},
    )
    assert result == ["core", "semantic"]


def test_deep_mode_constrained_by_context_when_safe_memory_below_configured():
    # deep 模式无 configured_limit，所以 constrained_by_context 永远为 False
    budget = resolve_memory_budget("deep", 8_000)
    assert budget.constrained_by_context is False


def test_standard_mode_marks_constrained_when_safe_memory_below_configured():
    budget = resolve_memory_budget("standard", 6_000)
    # safe_memory = 6000 - 1800 = 4200 < 10000
    assert budget.constrained_by_context is True
    assert budget.effective_tokens == 4_200


def test_resolve_memory_budget_clamps_negative_available_context():
    budget = resolve_memory_budget("standard", -100)
    assert budget.available_context_tokens == 0
    assert budget.reserved_tokens == 0
    assert budget.effective_tokens == 0
    assert budget.constrained_by_context is True


def test_categories_for_groups_defaults_to_all_enabled():
    result = categories_for_groups({})
    assert result == [
        "core", "profile", "semantic",
        "episodic", "temporal", "learning_weakness",
        "procedural", "preference",
    ]


def test_intersect_categories_with_explicit_requested_subset():
    result = intersect_categories(
        requested=["core", "temporal"],
        grouped=["core", "profile", "semantic", "episodic", "temporal"],
        internal_enabled={"core": True, "profile": True, "semantic": True,
                          "episodic": True, "temporal": True},
    )
    assert result == ["core", "temporal"]


def test_memory_budget_model_fields_complete():
    budget = resolve_memory_budget("economy", 50_000)
    assert isinstance(budget, MemoryBudget)
    assert budget.mode == "economy"
    assert budget.configured_limit == 5_000
    assert budget.available_context_tokens == 50_000
    assert budget.reserved_tokens == math.ceil(50_000 * 0.30)
    assert budget.effective_tokens == 5_000
    assert budget.constrained_by_context is False
