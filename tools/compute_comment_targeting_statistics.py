"""PAPER-S24 (docs/paper-s24-targeted-comment-protocol-v0.md, locked
2026-09-24): Tier 1/2/3 aggregation for `comment_targeting` chain and
isolated-baseline results.

Extends, not rewrites, the existing statistics stack (protocol section 5
item 7's own instruction): `_tiered_report`, `_group_by_document`,
`_anchor_level_values`, `_paired_drop`, and `_direct_arm_comparison` are
imported UNMODIFIED from `compute_respec_cascade_statistics.py` rather than
duplicated -- every one of those four helpers is already generic over any
chain shape carrying `doc_label`/`arm` fields, which `comment_targeting`
chains and baselines both do (confirmed by reading `tools/run_comment_
targeting_family.py`'s real `base_result`/baseline `base_result` dicts
directly, not assumed). `bootstrap_ci`/`paired_permutation_test`
(`tools/graph_scorer.py`) and `weighted_mean`/`weighted_bootstrap_ci`/
`weighted_paired_permutation_test`/`estimate_icc_and_effective_n`
(`tools/compute_multianchor_extension_statistics.py`) are themselves
re-imported through that module unmodified, same seed (`20260828`) and
resample count (2000) as the rest of this project's statistics.

-------------------------------------------------------------------------
Why this family's aggregation shape differs from respec_cascade's
-------------------------------------------------------------------------
respec_cascade resolves multiple ANCHOR-SETS per document (up to 4), so
`doc_label` values like `"jcshm-si__anchor2"` give `_group_by_document`
real per-document multiplicity to pool over even before touching K. This
family runs exactly ONE chain per (document, arm) -- `doc_label` is the
bare document name, `usable_k` targets live INSIDE that one chain, not as
separate chains. So:

  - At any FIXED (condition, chain position), the real N is capped at 3
    documents regardless of tier -- there is only one chain per document
    per arm to read that position from. Tier 1/2/3 still differ (Tier 2
    weights by how many *targets* a document actually has via its own
    usable_k -- the manuscript's 4-target chains count for less than the
    SI's/dissertation's 8-target chains -- and Tier 3 pools every
    STEP-level observation, not just a per-document mean), but none of the
    three tiers can turn 3 documents into more than 3 documents' worth of
    genuinely independent per-position information.
  - Pooling ACROSS POSITIONS within one condition (treating each
    (document, chain_position) pair as its own trial, `_pool_across_
    positions` below, structurally the same move `compute_respec_cascade_
    statistics._pool_across_families` already makes for that family's own
    five families) is where this measure's real statistical power lives --
    up to 3 documents x 8 positions = 24 trials per arm per condition,
    non-independent (same document's positions share document-level
    confounds, exactly the multi-anchor extension's own already-disclosed
    reasoning), Tier 3's ICC-corrected effective N carrying that caveat
    forward rather than reporting the naive 24 as if it were real
    independent power.

Usage:
    python compute_comment_targeting_statistics.py \\
        --run-root <primary-sweep-run-root> \\
        --baseline-run-root <baseline-sweep-run-root> \\
        --schedule-json D:/MeridianData/ooxml-graph-paper/runs/paper-s24/comment-targeting-schedule-v1.json \\
        --out <path>/statistics.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from compute_respec_cascade_statistics import (  # noqa: E402 -- reused UNMODIFIED, see module docstring
    _anchor_level_values,
    _direct_arm_comparison,
    _group_by_document,
    _paired_drop,
    _tiered_report,
)
from compute_multianchor_extension_statistics import _RESAMPLES, _SEED  # noqa: E402 -- reused UNMODIFIED
from graph_scorer import paired_permutation_test  # noqa: E402 -- reused UNMODIFIED

_EXCLUDED_STATUSES = frozenset({"not_applicable", "harness_exception", "blocked"})
_CONDITIONS: tuple[str, ...] = ("ambiguous", "unique")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_comment_targeting_chains(run_root: Path) -> list[dict[str, Any]]:
    """Every `chain-result.json` directly under `run_root/<chain_dir>/` --
    matches `tools/run_comment_targeting_family.py::_CHECKPOINT_NAME`
    exactly, one entry per (document, arm) chain (protocol section 2.1: a
    single chain covers ALL `2*usable_k` steps for that document/arm, not
    one chain per step or per family)."""
    if not run_root.is_dir():
        return []
    chains: list[dict[str, Any]] = []
    for chain_dir in sorted(run_root.iterdir()):
        if not chain_dir.is_dir():
            continue
        cr = chain_dir / "chain-result.json"
        if cr.is_file():
            chains.append(json.loads(cr.read_text(encoding="utf-8")))
    return chains


def load_comment_targeting_baselines(baseline_run_root: Path) -> list[dict[str, Any]]:
    """Every `baseline-result.json` directly under
    `baseline_run_root/<baseline_dir>/` -- matches `tools/run_comment_
    targeting_family.py::_BASELINE_CHECKPOINT_NAME`, one entry per
    (document, condition, target_index, arm) isolated single-step trial
    (protocol section 3)."""
    if not baseline_run_root.is_dir():
        return []
    baselines: list[dict[str, Any]] = []
    for b_dir in sorted(baseline_run_root.iterdir()):
        if not b_dir.is_dir():
            continue
        br = b_dir / "baseline-result.json"
        if br.is_file():
            baselines.append(json.loads(br.read_text(encoding="utf-8")))
    return baselines


# ---------------------------------------------------------------------------
# Per-chain-position reconstruction and outcome extraction
# ---------------------------------------------------------------------------

def _condition_positions(chain: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Splits the persisted `chain_grade["per_position"]` list (ordered by
    ABSOLUTE chain step, one entry per step, each carrying `condition` but
    not a condition-relative index) into per-condition sequences, in order
    -- reconstructing `condition_position` (1..usable_k WITHIN each
    condition) from list order rather than trusting an index that was never
    persisted. Safe because `tools/run_comment_targeting_family.py::
    _interleaved_steps` guarantees each condition's own targets appear in
    strict target order within their own condition -- a simple per-condition
    running count recovers the same `condition_position` the orchestrator
    itself used, exactly."""
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in _CONDITIONS}
    per_position = (chain.get("chain_grade") or {}).get("per_position") or []
    for entry in per_position:
        cond = entry.get("condition")
        if cond in out:
            out[cond].append(entry)
    return out


def _position_entry(chain: dict[str, Any], condition: str, position: int) -> dict[str, Any] | None:
    """The (condition, position)'th entry (1-indexed) for this chain, or
    None when the chain never reached it -- either because this document's
    own usable_k is smaller than `position` (protocol section 1.2b: the
    manuscript's real, frozen K=4 while SI/dissertation are K=8 -- asking
    for position 6 on a manuscript chain is not a failure, it is a question
    that document's own frozen schedule never had an answer to) or because
    the chain froze before reaching it (`chain_broken_at_step_*`)."""
    positions = _condition_positions(chain).get(condition, [])
    if position < 1 or position > len(positions):
        return None
    return positions[position - 1]


def make_step_pass_outcome_fn(condition: str, position: int) -> Callable[[dict[str, Any]], float | None]:
    def _fn(chain: dict[str, Any]) -> float | None:
        if chain.get("status") in _EXCLUDED_STATUSES:
            return None
        entry = _position_entry(chain, condition, position)
        if entry is None:
            return None
        return 1.0 if entry.get("step_pass") else 0.0
    return _fn


def make_keep_survival_outcome_fn(condition: str, position: int) -> Callable[[dict[str, Any]], float | None]:
    def _fn(chain: dict[str, Any]) -> float | None:
        if chain.get("status") in _EXCLUDED_STATUSES:
            return None
        entry = _position_entry(chain, condition, position)
        if entry is None:
            return None
        return 1.0 if entry.get("keep_survival_ok") else 0.0
    return _fn


def _chain_composite_outcome(chain: dict[str, Any]) -> float | None:
    """Whole-chain composite: every position's own step_pass, across BOTH
    conditions (protocol section 4: "per-chain pass = every step
    correct_target AND every keep-survival check passed... "). A chain that
    froze before any grading happened (`chain_grade` is None) is scored
    0.0, not excluded -- the same reasoning `compute_respec_cascade_
    statistics._phase3_composite_outcome` already documents: a mid-chain
    freeze is itself a real structural finding about that arm's output, not
    an absence of information."""
    if chain.get("status") in _EXCLUDED_STATUSES:
        return None
    chain_grade = chain.get("chain_grade")
    if chain_grade is None:
        return 0.0
    return 1.0 if chain_grade.get("chain_pass") else 0.0


def _baseline_outcome(baseline: dict[str, Any]) -> float | None:
    if baseline.get("status") in _EXCLUDED_STATUSES:
        return None
    step_grade = baseline.get("step_grade")
    if step_grade is None:
        return 0.0
    return 1.0 if step_grade.get("step_pass") else 0.0


# ---------------------------------------------------------------------------
# Pooling across chain positions within one condition (this family's own
# Tier-3-power move -- see module docstring).
# ---------------------------------------------------------------------------

def _pool_across_positions(
    chains: list[dict[str, Any]], condition: str, max_position: int,
    outcome_fn_factory: Callable[[str, int], Callable[[dict[str, Any]], float | None]],
) -> tuple[dict[str, dict[str, list[float]]], list[dict[str, Any]]]:
    pooled: dict[str, dict[str, list[float]]] = {"control": {}, "treatment": {}}
    excluded: list[dict[str, Any]] = []
    for position in range(1, max_position + 1):
        fn = outcome_fn_factory(condition, position)
        grouped, excl = _group_by_document(chains, fn, f"{condition}_position{position}")
        excluded.extend(excl)
        for arm in ("control", "treatment"):
            for doc, values in grouped[arm].items():
                pooled[arm].setdefault(doc, []).extend(values)
    return pooled, excluded


def _pool_anchor_level_across_positions(
    chains: list[dict[str, Any]], condition: str, max_position: int,
    outcome_fn_factory: Callable[[str, int], Callable[[dict[str, Any]], float | None]],
) -> dict[str, dict[str, float]]:
    """{arm: {"position{p}::{doc_label}": value}} -- the composite-key
    pooling convention `compute_respec_cascade_statistics._pool_across_
    families` already uses for its own family x anchor-set pooling, applied
    here to position x document so a paired test over the pooled set treats
    each (position, document) pair as its own paired observation instead of
    silently overwriting one position's value with another's for the same
    document."""
    out: dict[str, dict[str, float]] = {"control": {}, "treatment": {}}
    for position in range(1, max_position + 1):
        fn = outcome_fn_factory(condition, position)
        al = _anchor_level_values(chains, fn)
        for arm in ("control", "treatment"):
            for doc, value in al[arm].items():
                out[arm][f"position{position}::{doc}"] = value
    return out


# ---------------------------------------------------------------------------
# Top-level aggregation
# ---------------------------------------------------------------------------

def compute_comment_targeting_tiers(
    chains: list[dict[str, Any]], baselines: list[dict[str, Any]], max_position: int = 8,
) -> dict[str, Any]:
    excluded_observations: list[dict[str, Any]] = []

    # ---- (a) Per-(condition, position) step-pass rate, Tier 1 only (real N
    # is capped at 3 documents at any fixed position regardless of tier --
    # module docstring) -- protocol section 4's own primary readout, reported
    # exactly at this granularity, not only pooled.
    per_position_step_pass: dict[str, dict[int, Any]] = {c: {} for c in _CONDITIONS}
    for condition in _CONDITIONS:
        for position in range(1, max_position + 1):
            fn = make_step_pass_outcome_fn(condition, position)
            grouped, excl = _group_by_document(chains, fn, f"step_pass_{condition}_position{position}")
            excluded_observations.extend(excl)
            if not grouped["control"] and not grouped["treatment"]:
                continue  # no document has this position at all (e.g. position 5-8 for the manuscript, K=4) -- skip, not a zero
            per_position_step_pass[condition][position] = _tiered_report(grouped["control"], grouped["treatment"])

    # ---- (b) Pooled-across-positions step-pass rate, per condition (this
    # family's real Tier-3 power -- module docstring).
    pooled_step_pass: dict[str, Any] = {}
    pooled_step_pass_anchor_level: dict[str, dict[str, dict[str, float]]] = {}
    for condition in _CONDITIONS:
        pooled, excl = _pool_across_positions(chains, condition, max_position, make_step_pass_outcome_fn)
        excluded_observations.extend(excl)
        pooled_step_pass[condition] = _tiered_report(pooled["control"], pooled["treatment"])
        pooled_step_pass_anchor_level[condition] = _pool_anchor_level_across_positions(
            chains, condition, max_position, make_step_pass_outcome_fn,
        )

    # ---- (c) Whole-chain composite pass rate.
    composite_grouped, composite_excluded = _group_by_document(chains, _chain_composite_outcome, "chain_composite")
    excluded_observations.extend(composite_excluded)
    composite_tiers = _tiered_report(composite_grouped["control"], composite_grouped["treatment"])
    composite_anchor_level = _anchor_level_values(chains, _chain_composite_outcome)

    # ---- (d) Keep-survival pass rate, pooled across positions, per condition
    # (protocol section 7 confirm criterion 4's own "selective-precision-
    # under-load" measure -- keep_survival_ok specifically, not step_pass,
    # see tools/docx_trial_evaluator.py::grade_comment_targeting_chain's own
    # comment on why these two are not interchangeable).
    pooled_keep_survival: dict[str, Any] = {}
    pooled_keep_survival_anchor_level: dict[str, dict[str, dict[str, float]]] = {}
    for condition in _CONDITIONS:
        pooled, excl = _pool_across_positions(chains, condition, max_position, make_keep_survival_outcome_fn)
        excluded_observations.extend(excl)
        pooled_keep_survival[condition] = _tiered_report(pooled["control"], pooled["treatment"])
        pooled_keep_survival_anchor_level[condition] = _pool_anchor_level_across_positions(
            chains, condition, max_position, make_keep_survival_outcome_fn,
        )

    # ---- (e) Isolated K=1 baseline pass rate, per condition.
    baseline_tiers: dict[str, Any] = {}
    baseline_anchor_level: dict[str, dict[str, float]] = {}
    for condition in _CONDITIONS:
        cond_baselines = [b for b in baselines if b.get("condition") == condition]
        grouped, excl = _group_by_document(cond_baselines, _baseline_outcome, f"baseline_{condition}")
        excluded_observations.extend(excl)
        baseline_tiers[condition] = _tiered_report(grouped["control"], grouped["treatment"])
        baseline_anchor_level[condition] = _anchor_level_values(cond_baselines, _baseline_outcome)["control"]
        baseline_anchor_level[condition + "_treatment"] = _anchor_level_values(cond_baselines, _baseline_outcome)["treatment"]

    # ---- Section 7: the five preregistered confirm/disconfirm comparisons,
    # computed here and returned under their own explicit, labeled keys --
    # never left implicit inside a larger tiered dict, matching every other
    # confirm/disconfirm section in this project's statistics modules.
    position1_step_pass = {c: _anchor_level_values(chains, make_step_pass_outcome_fn(c, 1)) for c in _CONDITIONS}
    position_k_step_pass = {c: _anchor_level_values(chains, make_step_pass_outcome_fn(c, max_position)) for c in _CONDITIONS}
    position_k_keep_survival = {c: _anchor_level_values(chains, make_keep_survival_outcome_fn(c, max_position)) for c in _CONDITIONS}

    def _trend(arm: str, condition: str) -> dict[str, Any]:
        p1 = position1_step_pass[condition][arm]
        pk = position_k_step_pass[condition][arm]
        common = sorted(set(p1) & set(pk))
        if len(common) < 2:
            return {
                "observed_mean_diff": None, "p_value": None, "n_paired_documents": len(common),
                "reason": "fewer than 2 documents with both a position-1 and a position-K outcome for this arm/condition",
            }
        result = paired_permutation_test([p1[d] for d in common], [pk[d] for d in common])
        result["n_paired_documents"] = len(common)
        result["matched_documents"] = common
        result["method"] = f"paired_permutation_test(position 1 step_pass, position {max_position} step_pass), {arm}/{condition}, matched by doc_label"
        return result

    confirm_disconfirm: dict[str, Any] = {
        "control_ambiguous_position1_vs_positionK_trend": _trend("control", "ambiguous"),
        "treatment_ambiguous_position1_vs_positionK_trend": _trend("treatment", "ambiguous"),
        "control_unique_position1_vs_positionK_trend": _trend("control", "unique"),
        "treatment_unique_position1_vs_positionK_trend": _trend("treatment", "unique"),
        "direct_control_vs_treatment_positionK_ambiguous": _direct_arm_comparison(position_k_step_pass["ambiguous"]),
        "direct_control_vs_treatment_positionK_unique": _direct_arm_comparison(position_k_step_pass["unique"]),
    }

    # Ambiguous-vs-unique gap at position K, by arm (confirm criterion 3).
    for arm in ("control", "treatment"):
        amb = position_k_step_pass["ambiguous"][arm]
        uniq = position_k_step_pass["unique"][arm]
        common = sorted(set(amb) & set(uniq))
        if len(common) < 2:
            confirm_disconfirm[f"{arm}_ambiguous_vs_unique_gap_positionK"] = {
                "observed_mean_diff": None, "p_value": None, "n_paired_documents": len(common),
                "reason": "fewer than 2 documents with both an ambiguous and a unique outcome at this position for this arm",
            }
        else:
            result = paired_permutation_test([amb[d] for d in common], [uniq[d] for d in common])
            result["n_paired_documents"] = len(common)
            result["matched_documents"] = common
            result["method"] = f"paired_permutation_test(ambiguous step_pass, unique step_pass) at position {max_position}, {arm}, matched by doc_label"
            confirm_disconfirm[f"{arm}_ambiguous_vs_unique_gap_positionK"] = result

    # Keep-survival at position K, direct control-vs-treatment (criterion 4).
    confirm_disconfirm["keep_survival_positionK_control_vs_treatment"] = {
        c: _direct_arm_comparison(position_k_keep_survival[c]) for c in _CONDITIONS
    }

    # Position-1 vs isolated K=1 baseline, by arm/condition (criterion 5) --
    # reuses _paired_drop directly, matching respec_cascade's own
    # control_drop/treatment_drop shape exactly (protocol section 7 explicitly
    # models this comparison on that precedent).
    position1_vs_baseline: dict[str, Any] = {}
    for condition in _CONDITIONS:
        cascade_al = position1_step_pass[condition]
        baseline_al = {"control": baseline_anchor_level[condition], "treatment": baseline_anchor_level[condition + "_treatment"]}
        position1_vs_baseline[condition] = {
            "control": _paired_drop(cascade_al, baseline_al, "control"),
            "treatment": _paired_drop(cascade_al, baseline_al, "treatment"),
        }
    confirm_disconfirm["position1_vs_isolated_baseline"] = position1_vs_baseline

    return {
        "schema": "paper-s24-comment-targeting-statistics-v1",
        "conditions": list(_CONDITIONS),
        "max_position_computed": max_position,
        "seed": _SEED,
        "n_resamples": _RESAMPLES,
        "outcome_measures": {
            "a_per_position_step_pass_rate": per_position_step_pass,
            "b_pooled_step_pass_rate_by_condition": pooled_step_pass,
            "c_whole_chain_composite_pass_rate": composite_tiers,
            "d_pooled_keep_survival_rate_by_condition": pooled_keep_survival,
            "e_isolated_k1_baseline_pass_rate_by_condition": baseline_tiers,
        },
        "confirm_disconfirm": confirm_disconfirm,
        "excluded_observations": excluded_observations,
        "n_chains_loaded": len(chains),
        "n_baselines_loaded": len(baselines),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--baseline-run-root", required=True, type=Path)
    parser.add_argument("--max-position", type=int, default=8)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    chains = load_comment_targeting_chains(args.run_root)
    baselines = load_comment_targeting_baselines(args.baseline_run_root)

    report = compute_comment_targeting_tiers(chains, baselines, max_position=args.max_position)
    report["run_root"] = str(args.run_root)
    report["baseline_run_root"] = str(args.baseline_run_root)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "n_chains_loaded": report["n_chains_loaded"],
        "n_baselines_loaded": report["n_baselines_loaded"],
        "excluded_observation_count": len(report["excluded_observations"]),
    }, indent=2))

    print("\n=== PAPER-S24 section 7 primary numbers ===")
    cd = report["confirm_disconfirm"]
    print(f"control ambiguous position1->positionK trend:   {cd['control_ambiguous_position1_vs_positionK_trend']}")
    print(f"treatment ambiguous position1->positionK trend: {cd['treatment_ambiguous_position1_vs_positionK_trend']}")
    print(f"direct control-vs-treatment, positionK ambiguous: {cd['direct_control_vs_treatment_positionK_ambiguous']}")
    print(f"keep_survival positionK, control-vs-treatment:    {cd['keep_survival_positionK_control_vs_treatment']}")
    print(f"Full report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
