"""Regression tests for PAPER-S7's statistics aggregation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from compute_s7_statistics import _chain_outcome, _chain_steady_state_outcome, compute_statistics  # noqa: E402


def _passing_chain(doc_label: str, family: str, arm: str, k: int = 1) -> dict:
    return {
        "doc_label": doc_label, "family": family, "arm": arm, "k_pairs": k,
        "status": "completed",
        "pairs": [{"forward": {"grading": {"verdict": "pass"}}, "inverse": {"grading": {"verdict": "pass"}}}],
    }


def _failing_chain(doc_label: str, family: str, arm: str, k: int = 1) -> dict:
    return {
        "doc_label": doc_label, "family": family, "arm": arm, "k_pairs": k,
        "status": "completed_with_failure",
        "pairs": [{"forward": {"grading": {"verdict": "pass"}}, "inverse": {"grading": {"verdict": "fail"}}}],
    }


def _not_applicable_chain(doc_label: str, family: str, arm: str, k: int = 1) -> dict:
    return {"doc_label": doc_label, "family": family, "arm": arm, "k_pairs": k, "status": "not_applicable", "pairs": []}


def test_chain_outcome_pass() -> None:
    assert _chain_outcome(_passing_chain("d1", "bibliography", "control")) == 1.0


def test_chain_outcome_fail_on_inverse() -> None:
    assert _chain_outcome(_failing_chain("d1", "bibliography", "control")) == 0.0


def test_chain_outcome_fail_when_forward_fails() -> None:
    chain = {
        "doc_label": "d1", "family": "bibliography", "arm": "control", "k_pairs": 1,
        "status": "completed_with_failure",
        "pairs": [{"forward": {"grading": {"verdict": "fail"}}, "inverse": None}],
    }
    assert _chain_outcome(chain) == 0.0


def test_chain_outcome_not_applicable_is_none() -> None:
    assert _chain_outcome(_not_applicable_chain("d1", "section_reorder", "control")) is None


def test_chain_outcome_blocked_with_no_pairs_is_none() -> None:
    chain = {"doc_label": "d1", "family": "section_reorder", "arm": "control", "k_pairs": 4, "status": "blocked", "pairs": []}
    assert _chain_outcome(chain) is None


def test_chain_outcome_blocked_with_a_partial_pair_is_none_not_a_fail() -> None:
    """Found live (2026-09-04) on a real K=4 v2-corpus run: a chain that hit
    a genuine 300s subprocess timeout mid-chain still has a pair entry for
    the trial that never actually completed -- no grading verdict at all,
    since there was no valid output to grade. Before this fix, "if not
    pairs: return None" never caught this (the pairs list is non-empty), so
    the loop fell through and scored a pure infra timeout as a real 0.0 task
    failure. _load_checkpoint already refuses to trust "blocked" for exactly
    this reason; _chain_outcome must agree, not silently contradict it."""
    chain = {
        "doc_label": "d1", "family": "section_reorder", "arm": "control", "k_pairs": 4,
        "status": "blocked",
        "pairs": [{"forward": {"returncode": None, "timed_out": True}}],  # no "grading" key at all
    }
    assert _chain_outcome(chain) is None


def test_steady_state_outcome_is_none_for_blocked() -> None:
    chain = {
        "doc_label": "d1", "family": "section_reorder", "arm": "control", "k_pairs": 4,
        "status": "blocked",
        "pairs": [{"forward": {"returncode": None, "timed_out": True}}],
    }
    assert _chain_steady_state_outcome(chain) is None


def _blocked_chain(chain_id: str, doc_label: str, arm: str, k: int = 1) -> dict:
    return {
        "chain_id": chain_id, "doc_label": doc_label, "family": "section_reorder", "arm": arm, "k_pairs": k,
        "status": "blocked",
        "pairs": [{"forward": {"returncode": None, "timed_out": True, "grading": {"verdict": "not_run"}}}],
    }


def test_blocked_chain_named_in_score_as_failure_is_a_fail() -> None:
    """Appendix Note b: a timeout judged to be the arm's own task failure is
    scored 0.0 (and 0.0 steady-state at K>1), not excluded."""
    chain = _blocked_chain("d1-sr-control-k4", "d1", "control", k=4)
    assert _chain_outcome(chain, frozenset({"d1-sr-control-k4"})) == 0.0
    assert _chain_steady_state_outcome(chain, frozenset({"d1-sr-control-k4"})) == 0.0
    assert _chain_outcome(chain) is None


def test_score_as_failure_refuses_a_chain_that_has_a_verdict() -> None:
    chain = dict(_passing_chain("d1", "section_reorder", "control"), chain_id="d1-sr-control-k1")
    with pytest.raises(ValueError, match="only a blocked chain"):
        _chain_outcome(chain, frozenset({"d1-sr-control-k1"}))


def test_compute_statistics_scores_named_blocked_chain_and_records_it() -> None:
    chains = [
        _blocked_chain("d1-c", "d1", "control"),
        dict(_passing_chain("d1", "section_reorder", "treatment"), chain_id="d1-t"),
        dict(_passing_chain("d2", "section_reorder", "control"), chain_id="d2-c"),
        dict(_passing_chain("d2", "section_reorder", "treatment"), chain_id="d2-t"),
    ]
    excluded = compute_statistics(chains)
    assert excluded["groups"][0]["control_n"] == 1 and "scored_as_failure" not in excluded
    scored = compute_statistics(chains, frozenset({"d1-c"}))
    group = scored["groups"][0]
    assert group["control_n"] == 2 and group["paired_n"] == 2
    assert group["control_pass_rate_ci"]["mean"] == 0.5
    assert scored["scored_as_failure"] == ["d1-c"]
    with pytest.raises(ValueError, match="not in these manifests"):
        compute_statistics(chains, frozenset({"missing"}))


def test_chain_outcome_multi_pair_requires_all_pairs_pass() -> None:
    chain = {
        "doc_label": "d1", "family": "bibliography", "arm": "treatment", "k_pairs": 2,
        "status": "completed",
        "pairs": [
            {"forward": {"grading": {"verdict": "pass"}}, "inverse": {"grading": {"verdict": "pass"}}},
            {"forward": {"grading": {"verdict": "pass"}}, "inverse": {"grading": {"verdict": "fail"}}},
        ],
    }
    assert _chain_outcome(chain) == 0.0


def test_compute_statistics_groups_by_family_and_k() -> None:
    chains = [
        _passing_chain("d1", "bibliography", "control"),
        _passing_chain("d1", "bibliography", "treatment"),
        _failing_chain("d2", "bibliography", "control"),
        _passing_chain("d2", "bibliography", "treatment"),
        _not_applicable_chain("d3", "bibliography", "control"),
    ]

    stats = compute_statistics(chains)

    assert stats["chain_count"] == 5
    group = stats["groups"][0]
    assert group["family"] == "bibliography"
    assert group["k_pairs"] == 1
    assert group["not_applicable_count"] == 1
    assert group["control_n"] == 2
    assert group["treatment_n"] == 2
    assert group["paired_n"] == 2
    assert group["control_pass_rate_ci"]["mean"] == 0.5
    assert group["treatment_pass_rate_ci"]["mean"] == 1.0


def test_compute_statistics_separates_different_k_values() -> None:
    chains = [
        _passing_chain("d1", "bibliography", "control", k=1),
        _passing_chain("d1", "bibliography", "treatment", k=1),
        _passing_chain("d1", "bibliography", "control", k=4),
        _passing_chain("d1", "bibliography", "treatment", k=4),
    ]

    stats = compute_statistics(chains)

    assert len(stats["groups"]) == 2
    assert {g["k_pairs"] for g in stats["groups"]} == {1, 4}


def test_compute_statistics_skips_significance_test_below_two_paired_docs() -> None:
    chains = [_passing_chain("d1", "bibliography", "control"), _passing_chain("d1", "bibliography", "treatment")]

    stats = compute_statistics(chains)

    assert stats["groups"][0]["paired_control_vs_treatment_significance"] is None


def _k4_chain_first_pair_fails_rest_pass(doc_label: str, arm: str) -> dict:
    pass_pair = {"forward": {"grading": {"verdict": "pass"}}, "inverse": {"grading": {"verdict": "pass"}}}
    fail_pair = {"forward": {"grading": {"verdict": "pass"}}, "inverse": {"grading": {"verdict": "fail"}}}
    return {
        "doc_label": doc_label, "family": "bibliography", "arm": arm, "k_pairs": 4,
        "status": "completed_with_failure",
        "pairs": [fail_pair, pass_pair, pass_pair, pass_pair],
    }


def test_steady_state_outcome_excludes_first_pair() -> None:
    chain = _k4_chain_first_pair_fails_rest_pass("d1", "control")

    assert _chain_outcome(chain) == 0.0  # strict: any failing pair fails the whole chain
    assert _chain_steady_state_outcome(chain) == 1.0  # pairs[1:] all passed


def test_steady_state_outcome_is_none_for_k1() -> None:
    assert _chain_steady_state_outcome(_passing_chain("d1", "bibliography", "control", k=1)) is None


def test_steady_state_outcome_is_none_for_not_applicable() -> None:
    chain = {"doc_label": "d1", "family": "x", "arm": "control", "k_pairs": 4, "status": "not_applicable", "pairs": []}
    assert _chain_steady_state_outcome(chain) is None


def test_compute_statistics_reports_steady_state_for_k4_but_not_k1() -> None:
    k1_chains = [_passing_chain("d1", "bibliography", "control", k=1), _passing_chain("d1", "bibliography", "treatment", k=1)]
    k4_chains = [
        _k4_chain_first_pair_fails_rest_pass("d1", "control"),
        _k4_chain_first_pair_fails_rest_pass("d1", "treatment"),
    ]

    stats = compute_statistics(k1_chains + k4_chains)

    by_k = {g["k_pairs"]: g for g in stats["groups"]}
    assert by_k[1]["steady_state_pairs_1_plus"] is None
    assert by_k[4]["steady_state_pairs_1_plus"]["control_pass_rate_ci"]["mean"] == 1.0
    assert by_k[4]["steady_state_pairs_1_plus"]["treatment_pass_rate_ci"]["mean"] == 1.0
    # Strict, whole-chain outcome still correctly shows 0.0 for both arms.
    assert by_k[4]["control_pass_rate_ci"]["mean"] == 0.0
    assert by_k[4]["treatment_pass_rate_ci"]["mean"] == 0.0
