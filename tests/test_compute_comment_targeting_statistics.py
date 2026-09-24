"""Regression tests for tools/compute_comment_targeting_statistics.py.

Built against the REAL, exact return shapes of tools/run_comment_targeting_
family.py::run_comment_targeting_chain and run_comment_targeting_isolated_
baseline, and tools/docx_trial_evaluator.py::grade_comment_targeting_chain's
own per_position dicts -- read directly (not guessed) before writing these
fixtures, per this project's own standing discipline.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from compute_comment_targeting_statistics import (  # noqa: E402
    _baseline_outcome,
    _chain_composite_outcome,
    _condition_positions,
    compute_comment_targeting_tiers,
    make_keep_survival_outcome_fn,
    make_step_pass_outcome_fn,
)


def _position(condition: str, chain_position: int, step_pass: bool, keep_survival_ok: bool = True, outcome: str = "correct_target"):
    return {
        "chain_position": chain_position, "condition": condition,
        "outcome": outcome, "step_pass": step_pass, "keep_survival_ok": keep_survival_ok,
    }


def _chain(doc_label: str, arm: str, per_position: list[dict], status: str = "completed", chain_pass: bool | None = None):
    if chain_pass is None:
        chain_pass = all(p["step_pass"] for p in per_position) if per_position else False
    return {
        "chain_id": f"{doc_label}-comment_targeting-{arm}", "doc_label": doc_label,
        "family": "comment_targeting", "arm": arm, "model": "haiku", "status": status,
        "chain_grade": {
            "chain_pass": chain_pass,
            "first_failed_chain_position": next((p["chain_position"] for p in per_position if not p["step_pass"]), None),
            "per_position": per_position, "step_count": len(per_position),
        } if per_position or status == "completed" else None,
        "steps_run": len(per_position), "round_trip_count": len(per_position),
    }


def _baseline(doc_label: str, arm: str, condition: str, target_index: int, step_pass: bool, status: str = "completed"):
    return {
        "baseline_id": f"{doc_label}-baseline-{condition}{target_index}-comment_targeting-{arm}",
        "doc_label": doc_label, "family": "comment_targeting", "arm": arm,
        "condition": condition, "target_index": target_index, "model": "haiku", "status": status,
        "step_grade": {"step_pass": step_pass, "outcome": "correct_target" if step_pass else "wrong_target_same_cluster"},
    }


def test_condition_positions_splits_interleaved_list_preserving_order():
    # Interleaved: ambiguous1, unique1, ambiguous2, unique2 (K=2), matching
    # _interleaved_steps's own real alternating construction.
    per_position = [
        _position("ambiguous", 1, True),
        _position("unique", 2, True),
        _position("ambiguous", 3, False),
        _position("unique", 4, True),
    ]
    chain = _chain("doc-a", "treatment", per_position)

    split = _condition_positions(chain)

    assert [p["step_pass"] for p in split["ambiguous"]] == [True, False]
    assert [p["step_pass"] for p in split["unique"]] == [True, True]


def test_step_pass_outcome_fn_none_past_this_documents_own_k():
    # A K=1 document (manuscript-shaped: only 1 ambiguous + 1 unique step) --
    # asking for position 2 must be None (not 0.0), since this document's own
    # frozen schedule never had a position 2 to answer (protocol section
    # 1.2b's real per-document K asymmetry), distinct from a chain that
    # reached position 2 and genuinely failed it.
    per_position = [_position("ambiguous", 1, True), _position("unique", 2, True)]
    chain = _chain("thin-doc", "treatment", per_position)

    fn_pos1 = make_step_pass_outcome_fn("ambiguous", 1)
    fn_pos2 = make_step_pass_outcome_fn("ambiguous", 2)

    assert fn_pos1(chain) == 1.0
    assert fn_pos2(chain) is None


def test_step_pass_outcome_fn_excludes_not_applicable_status():
    chain = _chain("doc-a", "control", [], status="not_applicable", chain_pass=False)
    fn = make_step_pass_outcome_fn("ambiguous", 1)
    assert fn(chain) is None


def test_keep_survival_outcome_fn_distinct_from_step_pass():
    """A step that mistargeted (step_pass False) but never corrupted prior
    state (keep_survival_ok True) must report these as two DIFFERENT
    outcomes -- exactly the distinction docx_trial_evaluator.py::grade_
    comment_targeting_chain's own keep_survival_ok field comment explains
    step_pass alone cannot make."""
    per_position = [_position("ambiguous", 1, step_pass=False, keep_survival_ok=True, outcome="wrong_target_other")]
    chain = _chain("doc-a", "control", per_position, chain_pass=False)

    step_pass_fn = make_step_pass_outcome_fn("ambiguous", 1)
    keep_survival_fn = make_keep_survival_outcome_fn("ambiguous", 1)

    assert step_pass_fn(chain) == 0.0
    assert keep_survival_fn(chain) == 1.0


def test_chain_composite_outcome_scores_frozen_chain_as_zero_not_excluded():
    """A chain that froze before any grading happened (chain_grade is None)
    is a real structural finding, scored 0.0 -- not excluded, mirroring
    compute_respec_cascade_statistics's own _phase3_composite_outcome."""
    chain = {
        "chain_id": "x", "doc_label": "doc-a", "arm": "control",
        "status": "chain_broken_at_step_step1-ambiguous1", "chain_grade": None,
    }
    assert _chain_composite_outcome(chain) == 0.0


def test_chain_composite_outcome_excludes_not_applicable():
    chain = {"chain_id": "x", "doc_label": "doc-a", "arm": "control", "status": "not_applicable", "chain_grade": None}
    assert _chain_composite_outcome(chain) is None


def test_baseline_outcome_basic():
    assert _baseline_outcome(_baseline("doc-a", "treatment", "ambiguous", 1, step_pass=True)) == 1.0
    assert _baseline_outcome(_baseline("doc-a", "control", "ambiguous", 1, step_pass=False)) == 0.0


def test_compute_comment_targeting_tiers_end_to_end_real_gap_is_visible():
    """A small, realistic synthetic dataset (3 documents, K=2 each, control
    failing every ambiguous step, treatment passing every one) end to end --
    verifies the full aggregation pipeline runs without crashing on the REAL
    chain/baseline shapes and that the resulting pooled numbers actually
    show the gap the fixture was built to contain, not just that no
    exception was raised."""
    chains = []
    baselines = []
    for doc in ("doc-a", "doc-b", "doc-c"):
        control_positions = [
            _position("ambiguous", 1, step_pass=False, outcome="wrong_target_same_cluster"),
            _position("unique", 2, step_pass=True),
            _position("ambiguous", 3, step_pass=False, outcome="wrong_target_same_cluster"),
            _position("unique", 4, step_pass=True),
        ]
        treatment_positions = [
            _position("ambiguous", 1, step_pass=True),
            _position("unique", 2, step_pass=True),
            _position("ambiguous", 3, step_pass=True),
            _position("unique", 4, step_pass=True),
        ]
        chains.append(_chain(doc, "control", control_positions))
        chains.append(_chain(doc, "treatment", treatment_positions))
        for i in (1, 2):
            baselines.append(_baseline(doc, "control", "ambiguous", i, step_pass=True))
            baselines.append(_baseline(doc, "treatment", "ambiguous", i, step_pass=True))
            baselines.append(_baseline(doc, "control", "unique", i, step_pass=True))
            baselines.append(_baseline(doc, "treatment", "unique", i, step_pass=True))

    report = compute_comment_targeting_tiers(chains, baselines, max_position=2)

    assert report["n_chains_loaded"] == 6
    assert report["n_baselines_loaded"] == 24

    pooled_ambiguous = report["outcome_measures"]["b_pooled_step_pass_rate_by_condition"]["ambiguous"]
    control_mean = pooled_ambiguous["tier1_per_document_unweighted"]["control_pass_rate_ci"]["mean"]
    treatment_mean = pooled_ambiguous["tier1_per_document_unweighted"]["treatment_pass_rate_ci"]["mean"]
    assert control_mean == 0.0
    assert treatment_mean == 1.0

    # Unique condition (both arms clean in this fixture) should show no gap.
    pooled_unique = report["outcome_measures"]["b_pooled_step_pass_rate_by_condition"]["unique"]
    assert pooled_unique["tier1_per_document_unweighted"]["control_pass_rate_ci"]["mean"] == 1.0

    cd = report["confirm_disconfirm"]
    assert cd["direct_control_vs_treatment_positionK_ambiguous"]["p_value"] is not None
