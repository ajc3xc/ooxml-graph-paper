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


# ---------------------------------------------------------------------------
# 2026-09-25: per-cause blocked statuses and --blocked-policy (review blocker 1,
# items 22 and 23). The default must treat every new status exactly as the
# legacy "blocked", so no stored number moves.
# ---------------------------------------------------------------------------

import json  # noqa: E402

import compute_s7_statistics as cs7  # noqa: E402

_NEW_BLOCKED = ("blocked_timeout", "blocked_forward_failed", "blocked_unreadable_input", "blocked_inverse_unresolvable")


def _blocked_by_cause(status: str, chain_id: str = "c1", *, arm: str = "control", doc: str = "d1", trial: dict | None = None,
                   k: int = 4) -> dict:
    forward = trial if trial is not None else {"timed_out": True, "returncode": None, "claude_json_result": None,
                                               "grading": {"verdict": "not_run"}}
    return {"chain_id": chain_id, "doc_label": doc, "family": "section_reorder", "arm": arm, "k_pairs": k,
            "status": status, "pairs": [{"forward": forward}]}


@pytest.mark.parametrize("status", ("blocked", *_NEW_BLOCKED))
def test_every_blocked_status_is_excluded_by_default(status) -> None:
    chain = _blocked_by_cause(status)
    assert _chain_outcome(chain) is None
    assert _chain_steady_state_outcome(chain) is None


@pytest.mark.parametrize("status", ("infra_blocked", "infra_excluded", "aborted_circuit_open", "harness_exception"))
def test_infrastructure_and_aborted_chains_are_never_scored(status) -> None:
    chain = _blocked_by_cause(status, trial={"grading": {"verdict": "pass"}})
    for policy in cs7.BLOCKED_POLICIES:
        assert _chain_outcome(chain, blocked_policy=policy) is None
        assert _chain_steady_state_outcome(chain, blocked_policy=policy) is None


@pytest.mark.parametrize("status", _NEW_BLOCKED)
def test_fail_policy_scores_every_non_infrastructure_blocked_cause_zero(status) -> None:
    chain = _blocked_by_cause(status)
    assert _chain_outcome(chain, blocked_policy="fail") == 0.0
    assert _chain_steady_state_outcome(chain, blocked_policy="fail") == 0.0


def test_fail_policy_classifies_a_legacy_blocked_chain_from_its_trials() -> None:
    timed_out = _blocked_by_cause("blocked")
    assert _chain_outcome(timed_out, blocked_policy="fail") == 0.0
    dll_init_failed = _blocked_by_cause("blocked", trial={"timed_out": False, "returncode": 0xC0000142,
                                                       "claude_json_result": None, "stderr_tail": ""})
    assert _chain_outcome(dll_init_failed, blocked_policy="fail") is None
    rate_limited = _blocked_by_cause("blocked", trial={
        "timed_out": False, "returncode": 1, "stderr_tail": "",
        "claude_json_result": {"subtype": "success", "is_error": True, "api_error_status": 429, "result": "API Error: 429"},
    })
    assert _chain_outcome(rate_limited, blocked_policy="fail") is None
    recorded = {**_blocked_by_cause("blocked_timeout"), "infra_signature": {"kinds": ["foreign_signal"], "scope": "chain"}}
    assert _chain_outcome(recorded, blocked_policy="fail") is None


def test_score_as_failure_accepts_the_new_timeout_status() -> None:
    chain = _blocked_by_cause("blocked_timeout", chain_id="d1-sr-control-k4")
    assert _chain_outcome(chain, frozenset({"d1-sr-control-k4"})) == 0.0


def test_unknown_blocked_policy_is_rejected() -> None:
    with pytest.raises(ValueError):
        _chain_outcome(_passing_chain("d1", "bibliography", "control"), blocked_policy="sometimes")


def test_default_policy_output_is_unchanged_and_fail_policy_is_recorded() -> None:
    chains = [
        {**_passing_chain("d1", "section_reorder", "control", 4), "chain_id": "d1-c"},
        {**_passing_chain("d1", "section_reorder", "treatment", 4), "chain_id": "d1-t"},
        {**_passing_chain("d2", "section_reorder", "treatment", 4), "chain_id": "d2-t"},
        _blocked_by_cause("blocked_timeout", "d2-c", doc="d2"),
        _blocked_by_cause("blocked", "d3-c", doc="d3", trial={"timed_out": False, "returncode": -9,
                                                          "claude_json_result": None, "stderr_tail": ""}),
        {**_passing_chain("d3", "section_reorder", "treatment", 4), "chain_id": "d3-t"},
    ]
    default = compute_statistics(chains)
    assert "blocked_policy" not in default
    assert default == compute_statistics(chains, blocked_policy="exclude")
    [group] = default["groups"]
    assert group["control_n"] == 1 and group["paired_n"] == 1

    failed = compute_statistics(chains, blocked_policy="fail")
    [group] = failed["groups"]
    assert group["control_n"] == 2 and group["paired_n"] == 2
    assert failed["blocked_policy"]["policy"] == "fail"
    assert failed["blocked_policy"]["blocked_scored_as_failure"] == ["d2-c"]
    assert failed["blocked_policy"]["blocked_excluded_infrastructure"] == ["d3-c"]


def test_cli_accepts_blocked_policy_and_its_timeout_policy_alias(tmp_path: Path) -> None:
    manifest = tmp_path / "slice.json"
    manifest.write_text(json.dumps({"chains": [
        {**_passing_chain("d1", "bibliography", "control"), "chain_id": "a"},
        {**_passing_chain("d1", "bibliography", "treatment"), "chain_id": "b"},
        {**_blocked_by_cause("blocked_timeout", "c", doc="d2", k=1), "family": "bibliography"},
        {**_passing_chain("d2", "bibliography", "treatment"), "chain_id": "d"},
    ]}))
    for flag in ("--blocked-policy", "--timeout-policy"):
        out = tmp_path / f"{flag}.json"
        assert cs7.main([str(manifest), "--out", str(out), flag, "fail"]) == 0
        assert json.loads(out.read_text())["blocked_policy"]["blocked_scored_as_failure"] == ["c"]
    out = tmp_path / "default.json"
    assert cs7.main([str(manifest), "--out", str(out)]) == 0
    assert "blocked_policy" not in json.loads(out.read_text())
