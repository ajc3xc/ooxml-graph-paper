"""Regression tests for PAPER-S16's family-level split assignment."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build_dev_validation_holdout_split import (  # noqa: E402
    FamilySplitTarget,
    assign_family_splits,
)


def test_fractions_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        FamilySplitTarget(development=0.5, validation=0.5, primary_holdout=0.5)


def test_rejects_empty_family_sizes() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        assign_family_splits({}, seed=1)


def test_rejects_non_positive_family_size() -> None:
    with pytest.raises(ValueError, match="positive"):
        assign_family_splits({"a": 0}, seed=1)


def test_every_family_assigned_to_exactly_one_split() -> None:
    family_sizes = {f"family-{i}": (i % 5) + 1 for i in range(40)}

    result = assign_family_splits(family_sizes, seed=7)

    assert set(result["family_assignment"]) == set(family_sizes)
    assert set(result["family_assignment"].values()) <= {"development", "validation", "primary_holdout"}


def test_deterministic_given_fixed_seed() -> None:
    family_sizes = {f"family-{i}": (i * 3 % 7) + 1 for i in range(30)}

    first = assign_family_splits(family_sizes, seed=42)
    second = assign_family_splits(family_sizes, seed=42)

    assert first["family_assignment"] == second["family_assignment"]
    assert first["achieved_document_counts"] == second["achieved_document_counts"]


def test_different_seeds_can_change_tie_break_order() -> None:
    # All families the same size -- the only thing a seed can affect is tie-break order.
    family_sizes = {f"family-{i}": 1 for i in range(20)}

    a = assign_family_splits(family_sizes, seed=1)
    b = assign_family_splits(family_sizes, seed=2)

    assert a["family_assignment"] != b["family_assignment"]


def test_achieved_fractions_close_to_requested_for_many_small_families() -> None:
    family_sizes = {f"family-{i}": 1 for i in range(300)}

    result = assign_family_splits(family_sizes, seed=11)

    for split, requested in result["requested_fractions"].items():
        assert abs(result["achieved_fractions"][split] - requested) < 0.02


def test_achieved_fractions_can_diverge_and_is_reported_not_hidden() -> None:
    # A single family holding 90% of all documents makes hitting the requested 40/30/30
    # split impossible without breaking the family apart -- confirm the function reports
    # the actual achieved imbalance rather than silently claiming success.
    family_sizes = {"giant-family": 90, "small-a": 5, "small-b": 5}

    result = assign_family_splits(family_sizes, seed=3)

    giant_split = result["family_assignment"]["giant-family"]
    assert result["achieved_fractions"][giant_split] >= 0.9
    assert result["achieved_fractions"][giant_split] != pytest.approx(
        result["requested_fractions"][giant_split], abs=0.05
    )


def test_output_schema_has_expected_top_level_keys() -> None:
    result = assign_family_splits({"a": 2, "b": 3}, seed=5)

    assert result["schema"] == "paper-s16-split-manifest-v1"
    assert result["total_documents"] == 5
    assert result["total_families"] == 2
    assert result["seed"] == 5
