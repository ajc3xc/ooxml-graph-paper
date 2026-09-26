"""Re-analysis of the 2026-09-23 respec_cascade run (PAPER-S23) under the
chain-level test and the protocol's frozen-chain scoring, from the files that
survive the lost raw data.

tools/reconstruct_respec_observations.py finds every per-observation
reconstruction consistent with paper/sources/respec-cascade-statistics.json.
For each one this script recomputes, with the statistics pipeline's own
functions (tools/compute_respec_cascade_statistics.py, tools/graph_scorer.py,
tools/compute_multianchor_extension_statistics.py):

Frozen chains. `frozen_chain_mode="fail"` scores a frozen chain 0 at every
checkpoint it did not reach. That is exact only for a package-invalid freeze,
the one freeze protocol section 4 defines. All 5 control freezes of this run
were at steps that also check marker re-resolution (2.1, 3.2-inverse,
3.4-inverse x3) and their cause was not recorded; for them, and for families a
chain never ran, the 0 is an imputation. The scenarios and `bounds` below show
how much the result depends on it.

Scenarios (every one excludes the grader-crash chain, below)
  as_run      frozen chains excluded from the per-family Phase-3 and
              keep-survival measures (`frozen_chain_mode="exclude"`), as the
              stored statistics were computed.
  protocol    every frozen-chain cell scored 0 (`frozen_chain_mode="fail"`):
              finished-but-ungraded round trips, the round trip in progress,
              families never run, and keep-survival for a chain that froze
              before Checkpoint B. The all-fail end of `bounds`, not the
              protocol's literal rule (see above).
  protocol_finished_round_trips_pass
              as `protocol`, but the Phase-3 round trips that finished before
              a freeze (never graded; verdicts lost) scored as passes: the
              all-pass end of `bounds`.
  protocol_finished_round_trips_excluded
              as `protocol`, but those round trips excluded: an intermediate
              point inside `bounds`, not one of its ends.
  protocol_not_run_families_excluded
              as `protocol`, but the Phase-3 families a frozen chain never ran
              excluded instead of imputed 0; the round trip in progress at the
              freeze scores 0, finished round trips score 0.
  protocol_not_run_families_excluded_finished_round_trips_pass
              the same with finished round trips scored as passes.

Unknown cells
  bounds      all 1,024 0/1 assignments of the 10 finished-but-ungraded round
              trips, under protocol scoring and with never-run families
              excluded: ranges of each pooled measure's chain-level effect and
              p, and the section-7 verdict counts.
  grader_crash_chain_sensitivity (per scenario)
              the control chain jcshm-si__anchor3, whose Phase-3 grader raised,
              has no Phase-3 verdicts and no composite and is excluded from
              those measures in every scenario; this gives the ranges over all
              32 assignments of its 5 Phase-3 cells and both values of its
              composite.

Measures (A - B is the reported difference; a negative drop is a loss)
  whole_chain_composite_direct  composite chain PASS, control (A) vs treatment (B)
  keep_survival_direct          Checkpoint-B keep-survival, control (A) vs treatment (B)
  pooled_control_drop           per-family Phase-3 outcome (A) vs fresh K=1 baseline (B), control
  pooled_treatment_drop         the same for treatment
  pooled_direct                 per-family Phase-3 outcome, control (A) vs treatment (B)
  per_family.<family>.*         the last three for one family

Tests
  chain_level               exact cluster sign-flip, all observations of one
                            (document, anchor-set) chain flip together
  observation_level_as_run  the pipeline's Monte Carlo paired_permutation_test,
                            every observation its own unit (as reported)
  observation_level_exact   the same statistic with an exact p
  document_level_exact      exact cluster sign-flip by original document (3
                            documents: no p below 0.25 is attainable); the
                            exact form of Tier 1's per-document test

Only observation_level_as_run and the as_run scenario are what the run
reported. The other tests, the whole-chain composite direct comparison and
every frozen-chain scoring other than as_run were chosen after the results
were known: they are labelled post_hoc_for_2026-09-23_run (`analysis_status`)
and may be called primary only in the S25 re-run protocol, which names them
before any data exists.

Each test also gives a 95% bootstrap CI of the mean difference at its own
unit, and each scenario/test the protocol section 7 decision-rule flags.

Every value is reported once when all reconstructions agree; otherwise as
{"min", "max", "by_reconstruction"} (reconstruction order as listed under
`reconstruction`).

Usage:
    python tools/reanalyze_respec_cascade.py [--out paper/sources/respec-cascade-reanalysis.json]
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compute_respec_cascade_statistics as crs  # noqa: E402 -- statistical primitives used unmodified
import reconstruct_respec_observations as rro  # noqa: E402

REPO = rro.REPO
OUT = rro.SOURCES / "respec-cascade-reanalysis.json"
FAMILIES = rro.FAMILIES
ARMS = rro.ARMS

# (name, frozen_chain_mode, finished Phase-3 round trips before a freeze, Phase-3 families never run);
# None = as the mode scores them.
SCENARIOS: tuple[tuple[str, str, str | None, str | None], ...] = (
    ("as_run", "exclude", None, None),
    ("protocol", "fail", None, None),
    ("protocol_finished_round_trips_pass", "fail", "pass", None),
    ("protocol_finished_round_trips_excluded", "fail", "exclude", None),
    ("protocol_not_run_families_excluded", "fail", None, "exclude"),
    ("protocol_not_run_families_excluded_finished_round_trips_pass", "fail", "pass", "exclude"),
)
_FAIL_MODE_NOTE = (
    "frozen_chain_mode='fail' is exact only for a package-invalid freeze (protocol section 4); all 5 control "
    "freezes of this run were at steps that also check marker re-resolution (2.1, 3.2-inverse, 3.4-inverse x3) "
    "with the cause unrecorded, so for them, and for families never run, the 0 is an imputation."
)
SCENARIO_DESCRIPTIONS = {
    "as_run": "Frozen chains excluded from the per-family Phase-3 and keep-survival measures, as the stored statistics were computed.",
    "protocol": (
        "Every frozen-chain cell scored 0: the Phase-3 round trips that finished before the freeze (never graded), "
        "the round trip in progress, the families never run, and keep-survival for the chain that froze before "
        f"Checkpoint B. {_FAIL_MODE_NOTE} This is the all-fail end of `bounds`, not the protocol's literal rule."
    ),
    "protocol_finished_round_trips_pass": (
        "As protocol, but each Phase-3 round trip that finished before its chain froze (never graded; verdict "
        "unknown) scored as a pass: the all-pass end of `bounds`."
    ),
    "protocol_finished_round_trips_excluded": (
        "As protocol, but each Phase-3 round trip that finished before its chain froze (never graded; verdict "
        "unknown) excluded: an intermediate point inside `bounds`, not one of its ends."
    ),
    "protocol_not_run_families_excluded": (
        "As protocol, but the Phase-3 families a frozen chain never ran (all five for the chain that froze in "
        "Phase 2) are excluded instead of imputed 0. The round trip in progress at the freeze scores 0, each round "
        "trip that finished before the freeze scores 0, and keep-survival is scored as in protocol."
    ),
    "protocol_not_run_families_excluded_finished_round_trips_pass": (
        "As protocol_not_run_families_excluded, but each Phase-3 round trip that finished before its chain froze "
        "scored as a pass."
    ),
}
# Steps at which the orchestrator that ran (tools/run_respec_cascade_family.py at c75184f) freezes on a
# failed marker re-resolution as well as on a package-invalid output, under the same status string.
_RE_RESOLUTION_FREEZE_STEPS = frozenset({"2.1", "3.2-inverse", "3.4-inverse", "3.5-inverse"})
TESTS = ("chain_level", "observation_level_as_run", "observation_level_exact", "document_level_exact")
POST_HOC = crs.POST_HOC_LABEL
ANALYSIS_STATUS = {
    "observation_level_as_run": "as_run_reported",
    "chain_level": POST_HOC,
    "observation_level_exact": POST_HOC,
    "document_level_exact": POST_HOC,
    "whole_chain_composite_direct": POST_HOC,
    "scenario:as_run": "as_run_reported",
    "scenario:every_other": POST_HOC,
    "bounds": POST_HOC,
    "grader_crash_chain_sensitivity": POST_HOC,
}
ALPHA, DROP_THRESHOLD_PP, NULL_P = 0.05, 10.0, 0.10
_TOL = 1e-9
_VERDICT_KEYS = ("verdict", "verdict_with_whole_chain_composite_direct")


class ReanalysisError(RuntimeError):
    """A consistency check between scenarios, bounds and the pipeline failed."""


# ---------------------------------------------------------------------------
# Observations per scenario
# ---------------------------------------------------------------------------

def not_run_families(meta: dict[str, Any]) -> list[str]:
    """Phase-3 families a frozen chain never started (all of them for a chain
    that froze before Phase 3)."""
    if meta["frozen_at_step"] is None:
        return []
    in_progress = meta["in_progress_phase3_family"]
    return FAMILIES[FAMILIES.index(in_progress) + 1:] if in_progress else list(FAMILIES)


def scenario_levels(metas: list[dict[str, Any]], chains: list[dict[str, Any]],
                    bchains: dict[str, list[dict[str, Any]]], mode: str, finished: str | None,
                    not_run: str | None = None) -> dict[str, Any]:
    """{arm: {doc_label: outcome}} per measure, built with the pipeline's own
    outcome functions, then the overrides for finished-before-freeze round
    trips (`finished`: "pass" or "exclude") and never-run families
    (`not_run`: "exclude")."""
    per_family = {}
    for family in FAMILIES:
        def fn(chain: dict[str, Any], family: str = family) -> float | None:
            return crs._phase3_family_outcome(chain, family, mode)
        per_family[family] = crs._anchor_level_values(chains, fn)
    if finished is not None:
        for meta in metas:
            for family in meta["finished_phase3_families"]:
                cell = per_family[family][meta["arm"]]
                if finished == "pass":
                    cell[meta["doc_label"]] = 1.0
                else:
                    cell.pop(meta["doc_label"], None)
    if not_run == "exclude":
        for meta in metas:
            for family in not_run_families(meta):
                per_family[family][meta["arm"]].pop(meta["doc_label"], None)
    return {
        "per_family": per_family,
        "baseline": {f: crs._anchor_level_values(bchains[f], crs._baseline_outcome) for f in FAMILIES},
        "keep_survival": crs._anchor_level_values(chains, lambda c: crs._phase2_keep_survival_outcome(c, mode)),
        "composite": crs._anchor_level_values(chains, crs._phase3_composite_outcome),
    }


def _document_of(key: str) -> str:
    return crs._original_doc_label({"doc_label": crs._chain_of(key)})


def _unit_ci(units: list[str], diffs: list[float]) -> dict[str, Any]:
    """95% cluster bootstrap CI of the pooled mean difference: whole units
    resampled, each weighted by its number of observations."""
    by_unit: dict[str, list[float]] = {}
    for unit, d in zip(units, diffs):
        by_unit.setdefault(unit, []).append(d)
    return crs.weighted_bootstrap_ci([(rro.left_to_right_sum(ds) / len(ds), len(ds)) for ds in by_unit.values()])


def _summary(result: dict[str, Any], ci: dict[str, Any], unit: str, n_units: int) -> dict[str, Any]:
    diff = result.get("observed_mean_diff")
    return {
        "observed_mean_diff": diff,
        "effect_pp": None if diff is None else diff * 100,
        "p_value": result.get("p_value"),
        "exact": result.get("exact", False),
        "p_value_floor": result.get("p_value_floor"),
        "unit": unit,
        "n_units": n_units,
        "ci95_of_mean_diff": {"low": ci.get("ci_low"), "high": ci.get("ci_high"), "method": ci.get("method")},
    }


def run_tests(a_by_key: dict[str, float], b_by_key: dict[str, float]) -> dict[str, Any]:
    """The four tests on observations matched by key (A - B)."""
    common = sorted(set(a_by_key) & set(b_by_key))
    a_values = [a_by_key[k] for k in common]
    b_values = [b_by_key[k] for k in common]
    diffs = [a - b for a, b in zip(a_values, b_values)]
    chains = [crs._chain_of(k) for k in common]
    documents = [_document_of(k) for k in common]
    n = len(common)
    tests = {
        "chain_level": _summary(crs.cluster_paired_sign_flip_test(chains, a_values, b_values),
                                _unit_ci(chains, diffs), "chain (document, anchor-set)", len(set(chains))),
        "observation_level_as_run": _summary(crs.paired_permutation_test(a_values, b_values),
                                             crs.bootstrap_ci(diffs), "observation", n),
        "observation_level_exact": _summary(crs.paired_permutation_test_exact(a_values, b_values),
                                            crs.bootstrap_ci(diffs), "observation", n),
        "document_level_exact": _summary(crs.cluster_paired_sign_flip_test(documents, a_values, b_values),
                                         _unit_ci(documents, diffs), "document", len(set(documents))),
    }
    return {
        "n_paired_observations": n,
        "n_chains": len(set(chains)),
        "n_documents": len(set(documents)),
        "rate_a": rro.left_to_right_sum(a_values) / n if n else None,
        "rate_b": rro.left_to_right_sum(b_values) / n if n else None,
        "tests": tests,
    }


def scenario_measures(levels: dict[str, Any]) -> dict[str, Any]:
    cascade = crs._pool_across_families(levels["per_family"])
    baseline = crs._pool_across_families(levels["baseline"])
    out: dict[str, Any] = {
        "whole_chain_composite_direct": run_tests(levels["composite"]["control"], levels["composite"]["treatment"]),
        "keep_survival_direct": run_tests(levels["keep_survival"]["control"], levels["keep_survival"]["treatment"]),
        "pooled_control_drop": run_tests(cascade["control"], baseline["control"]),
        "pooled_treatment_drop": run_tests(cascade["treatment"], baseline["treatment"]),
        "pooled_direct": run_tests(cascade["control"], cascade["treatment"]),
        "per_family": {},
    }
    for family in FAMILIES:
        c, b = levels["per_family"][family], levels["baseline"][family]
        out["per_family"][family] = {
            "control_drop": run_tests(c["control"], b["control"]),
            "treatment_drop": run_tests(c["treatment"], b["treatment"]),
            "direct": run_tests(c["control"], c["treatment"]),
        }
    return out


def _check_against_pipeline(measures: dict[str, Any], report: dict[str, Any]) -> None:
    """The chain-level and as-run tests computed here must equal the ones
    compute_respec_cascade_tiers itself writes for the same scoring mode."""
    cd = report["confirm_disconfirm"]
    pairs = [
        ("pooled_control_drop", cd["pooled"]["chain_level"]["control_drop"], cd["pooled"]["control_drop"]),
        ("pooled_treatment_drop", cd["pooled"]["chain_level"]["treatment_drop"], cd["pooled"]["treatment_drop"]),
        ("pooled_direct", cd["pooled"]["chain_level"]["direct_control_vs_treatment_phase3"],
         cd["pooled"]["direct_control_vs_treatment_phase3"]),
        ("keep_survival_direct", cd["keep_survival_significance_chain_level"], cd["keep_survival_significance"]),
        ("whole_chain_composite_direct", cd["whole_chain_composite_direct"]["chain_level"]["direct_control_vs_treatment_phase3"],
         None),
    ]
    for name, chain_level, as_run in pairs:
        mine = measures[name]["tests"]
        if (mine["chain_level"]["p_value"], mine["chain_level"]["observed_mean_diff"]) != (
                chain_level.get("p_value"), chain_level.get("observed_mean_diff")):
            raise rro.ReconstructionError(f"{name}: chain-level test differs from the pipeline's own")
        if as_run is not None and (mine["observation_level_as_run"]["p_value"], mine["observation_level_as_run"]["n_units"]) != (
                as_run.get("p_value"), as_run.get("n_paired_anchor_sets")):
            raise rro.ReconstructionError(f"{name}: as-run test differs from the pipeline's own")


# ---------------------------------------------------------------------------
# Protocol section 7 decision rule
# ---------------------------------------------------------------------------

def section7_flags(measures: dict[str, Any], test: str) -> dict[str, Any]:
    """Protocol section 7, applied to the pooled measures with one test.
    `control_drop`/`treatment_drop` are the pooled per-family drops (the only
    measure with a matching baseline); the direct comparison is the pooled
    per-family one the pipeline reports, and the verdict with the whole-chain
    composite direct comparison (section 7's literal wording) is given beside
    it. The Tier-1 clause (significant at Tier 3 but not Tier 1 is
    inconclusive) is checked with the document-level exact test.
    "significant" means two-sided p < `alpha` (0.05); drops are in
    percentage points, positive = worse after the cascade."""
    def res(name: str, which: str = test) -> dict[str, Any]:
        return measures[name]["tests"][which]

    def p(r: dict[str, Any]) -> float:
        return r["p_value"] if r["p_value"] is not None else 1.0

    control, treatment, ks = res("pooled_control_drop"), res("pooled_treatment_drop"), res("keep_survival_direct")
    drop_c, drop_t = -control["effect_pp"], -treatment["effect_pp"]
    tier1 = (p(res("pooled_control_drop", "document_level_exact")) < ALPHA
             and p(res("pooled_direct", "document_level_exact")) < ALPHA)
    ci = treatment["ci95_of_mean_diff"]
    flags: dict[str, Any] = {
        "alpha": ALPHA,
        "control_drop_pp": drop_c,
        "treatment_drop_pp": drop_t,
        "control_drop_significant_and_at_least_10pp": p(control) < ALPHA and drop_c >= DROP_THRESHOLD_PP - _TOL,
        "treatment_drop_ci95_overlaps_zero": ci["low"] is not None and ci["low"] <= 0 <= ci["high"],
        "keep_survival_treatment_higher_significant": ks["effect_pp"] < 0 and p(ks) < ALPHA,
        "disconfirm_both_drops_null": (p(control) > NULL_P and p(treatment) > NULL_P)
                                      or (drop_c < DROP_THRESHOLD_PP and drop_t < DROP_THRESHOLD_PP),
        "disconfirm_treatment_drop_ge_control_drop": drop_t >= drop_c - _TOL,
        "tier1_document_level_control_drop_and_direct_significant": tier1,
        "tier1_min_attainable_p": res("pooled_control_drop", "document_level_exact")["p_value_floor"],
    }
    for label, direct_name in (("", "pooled_direct"), ("_with_whole_chain_composite_direct", "whole_chain_composite_direct")):
        direct = res(direct_name)
        smaller = drop_c - drop_t >= DROP_THRESHOLD_PP - _TOL and p(direct) < ALPHA
        confirm = (flags["control_drop_significant_and_at_least_10pp"]
                   and (flags["treatment_drop_ci95_overlaps_zero"] or smaller)
                   and flags["keep_survival_treatment_higher_significant"])
        not_different = p(direct) > ALPHA
        disconfirm = flags["disconfirm_both_drops_null"] or not_different or flags["disconfirm_treatment_drop_ge_control_drop"]
        flags[f"treatment_drop_at_least_10pp_smaller_with_direct_significant{label}"] = smaller
        flags[f"disconfirm_direct_not_significant{label}"] = not_different
        flags[f"confirming_conditions_met{label}"] = confirm
        flags[f"verdict{label}"] = (
            "DISCONFIRMING" if disconfirm else "CONFIRMING" if confirm and tier1
            else "INCONCLUSIVE (confirming conditions met, but not at Tier 1)" if confirm else "INCONCLUSIVE"
        )
    return flags


# ---------------------------------------------------------------------------
# Unknown cells: finished-before-freeze round trips and the grader-crash chain
# ---------------------------------------------------------------------------

_POOLED_MEASURES = ("pooled_control_drop", "pooled_treatment_drop", "pooled_direct",
                    "keep_survival_direct", "whole_chain_composite_direct")


def _light_tests(a_by_key: dict[str, float], b_by_key: dict[str, float]) -> dict[str, Any]:
    """The chain-level and document-level exact tests of `run_tests`, without
    CIs: all an enumeration needs for its ranges and the chain-level section-7
    verdict (whose one CI, treatment_drop's, never comes from here)."""
    common = sorted(set(a_by_key) & set(b_by_key))
    a_values = [a_by_key[k] for k in common]
    b_values = [b_by_key[k] for k in common]
    chains = [crs._chain_of(k) for k in common]
    documents = [_document_of(k) for k in common]
    return {
        "n_paired_observations": len(common),
        "tests": {
            "chain_level": _summary(crs.cluster_paired_sign_flip_test(chains, a_values, b_values), {},
                                    "chain (document, anchor-set)", len(set(chains))),
            "document_level_exact": _summary(crs.cluster_paired_sign_flip_test(documents, a_values, b_values), {},
                                             "document", len(set(documents))),
        },
    }


def _variant_measures(levels: dict[str, Any], base: dict[str, Any], phase3: dict[tuple[str, str, str], int],
                      composite: dict[tuple[str, str], int]) -> dict[str, Any]:
    """The pooled measures with some cells set: `phase3` {(family, arm,
    doc_label): 0/1}, `composite` {(arm, doc_label): 0/1}. Measures no set
    cell touches are taken from `base` (the scenario's full measures)."""
    measures = {name: base[name] for name in _POOLED_MEASURES}
    if phase3:
        per_family = {f: {arm: dict(cells) for arm, cells in by_arm.items()} for f, by_arm in levels["per_family"].items()}
        for (family, arm, label), value in phase3.items():
            per_family[family][arm][label] = float(value)
        cascade = crs._pool_across_families(per_family)
        baseline = crs._pool_across_families(levels["baseline"])
        arms = {arm for _, arm, _ in phase3}
        if "control" in arms:
            measures["pooled_control_drop"] = _light_tests(cascade["control"], baseline["control"])
        if "treatment" in arms:
            # Full tests: the verdict reads treatment_drop's CI.
            measures["pooled_treatment_drop"] = run_tests(cascade["treatment"], baseline["treatment"])
        measures["pooled_direct"] = _light_tests(cascade["control"], cascade["treatment"])
    if composite:
        cells = {arm: dict(by_doc) for arm, by_doc in levels["composite"].items()}
        for (arm, label), value in composite.items():
            cells[arm][label] = float(value)
        measures["whole_chain_composite_direct"] = _light_tests(cells["control"], cells["treatment"])
    return measures


def _chain_level_point(measure: dict[str, Any]) -> dict[str, Any]:
    t = measure["tests"]["chain_level"]
    return {"effect_pp": t["effect_pp"], "p_value": t["p_value"], "n_paired_observations": measure["n_paired_observations"]}


def _ranges(points: list[dict[str, Any]]) -> dict[str, Any]:
    return {key: {"min": min(p[key] for p in points), "max": max(p[key] for p in points)}
            for key in ("effect_pp", "p_value", "n_paired_observations")}


def _enumerate(levels: dict[str, Any], base: dict[str, Any], phase3_cells: list[tuple[str, str, str]],
               composite_cells: list[tuple[str, str]]) -> dict[str, Any]:
    """Every 0/1 assignment of `phase3_cells` and, independently, of
    `composite_cells`: chain-level ranges of each pooled measure, its all-0 and
    all-1 points, and the chain-level section-7 verdict counts ("verdict" over
    the Phase-3 assignments, the composite variant over both kinds)."""
    points: dict[str, list[dict[str, Any]]] = {name: [] for name in _POOLED_MEASURES}
    ends: dict[str, dict[str, Any]] = {}
    verdicts: dict[str, dict[str, int]] = {key: {} for key in _VERDICT_KEYS}
    # One empty variant when there is no composite cell: the scenario's own composite.
    composite_variants = [dict(zip(composite_cells, bits))
                          for bits in itertools.product((0, 1), repeat=len(composite_cells))]
    for composite in composite_variants:
        points["whole_chain_composite_direct"].append(
            _chain_level_point(_variant_measures(levels, base, {}, composite)["whole_chain_composite_direct"]))
    for bits in itertools.product((0, 1), repeat=len(phase3_cells)):
        measures = _variant_measures(levels, base, dict(zip(phase3_cells, bits)), {})
        for name in ("pooled_control_drop", "pooled_treatment_drop", "pooled_direct", "keep_survival_direct"):
            points[name].append(_chain_level_point(measures[name]))
        # "verdict" reads the pooled per-family direct comparison, not the composite.
        v = section7_flags(measures, "chain_level")["verdict"]
        verdicts["verdict"][v] = verdicts["verdict"].get(v, 0) + 1
        if len(set(bits)) == 1:
            ends["all_1" if bits[0] else "all_0"] = {
                name: _chain_level_point(measures[name]) for name in ("pooled_control_drop", "pooled_direct")}
        for composite in composite_variants:
            with_composite = _variant_measures(levels, measures, {}, composite)
            v = section7_flags(with_composite, "chain_level")["verdict_with_whole_chain_composite_direct"]
            counts = verdicts["verdict_with_whole_chain_composite_direct"]
            counts[v] = counts.get(v, 0) + 1
    return {
        "n_phase3_assignments": 2 ** len(phase3_cells),
        "n_composite_assignments": 2 ** len(composite_cells),
        "chain_level_ranges": {name: _ranges(ps) for name, ps in points.items()},
        "ends": ends,
        "section7_chain_level_verdict_counts": verdicts,
    }


def _cell_label(cell: tuple[str, ...]) -> str:
    return " / ".join(cell)


def finished_round_trip_bounds(metas: list[dict[str, Any]], levels: dict[str, Any], base: dict[str, Any],
                               scenarios: dict[str, Any], all_fail: str, all_pass: str,
                               intermediate: tuple[str, ...] = ()) -> dict[str, Any]:
    """All 2**10 assignments of the Phase-3 round trips that finished before a
    freeze, other cells as in `levels` (the `all_fail` scenario's). Checks that
    the all-0 and all-1 assignments are the named scenarios and that each
    `intermediate` scenario falls inside the ranges."""
    cells = sorted((family, m["arm"], m["doc_label"]) for m in metas for family in m["finished_phase3_families"])
    result = _enumerate(levels, base, cells, [])
    ranges = result["chain_level_ranges"]
    for end, scenario in (("all_0", all_fail), ("all_1", all_pass)):
        for name in ("pooled_control_drop", "pooled_direct"):
            if result["ends"][end][name] != _chain_level_point(scenarios[scenario]["measures"][name]):
                raise ReanalysisError(f"bounds: the {end} assignment's {name} is not scenario {scenario}'s")
    points = {}
    for scenario in intermediate:
        points[scenario] = {}
        for name in ("pooled_control_drop", "pooled_direct"):
            point = _chain_level_point(scenarios[scenario]["measures"][name])
            inside = all(ranges[name][k]["min"] <= point[k] <= ranges[name][k]["max"] for k in ("effect_pp", "p_value"))
            points[scenario][name] = {**point, "inside_the_ranges": inside}
    return {
        "unknown_cells": [_cell_label(c) for c in cells],
        "all_fail_assignment_is_scenario": all_fail,
        "all_pass_assignment_is_scenario": all_pass,
        "intermediate_scenarios": points,
        "measures_affected": ["pooled_control_drop", "pooled_direct"],
        **result,
    }


def crash_chain_sensitivity(metas: list[dict[str, Any]], levels: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Every assignment of the Phase-3 cells and composite of the chains whose
    Phase-3 grader raised (excluded in every scenario), the rest of the
    scenario unchanged. Cells vary independently of each other, a superset of
    the assignments consistent with the chains' status."""
    crashed = [m for m in metas if m["phase3"] == "grader_raised"]
    cells = [(family, m["arm"], m["doc_label"]) for m in crashed for family in FAMILIES]
    composite_cells = [(m["arm"], m["doc_label"]) for m in crashed]
    result = _enumerate(levels, base, cells, composite_cells)
    return {
        "chains": [_cell_label((m["arm"], m["doc_label"])) for m in crashed],
        "measures_affected": ["pooled_control_drop", "pooled_treatment_drop", "pooled_direct", "whole_chain_composite_direct"]
        if any(m["arm"] == "treatment" for m in crashed) else ["pooled_control_drop", "pooled_direct", "whole_chain_composite_direct"],
        **result,
    }


# ---------------------------------------------------------------------------
# Merge across reconstructions
# ---------------------------------------------------------------------------

def merge(values: list[Any]) -> Any:
    """One value if every reconstruction agrees, else min/max (numbers) and
    the per-reconstruction values."""
    first = values[0]
    if all(v == first and type(v) is type(first) for v in values):
        return first
    if all(isinstance(v, dict) for v in values) and all(v.keys() == first.keys() for v in values):
        return {k: merge([v[k] for v in values]) for k in first}
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return {"min": min(values), "max": max(values), "by_reconstruction": values}
    return {"by_reconstruction": values}


# ---------------------------------------------------------------------------
# Cells table
# ---------------------------------------------------------------------------

def cells_table(recon: dict[str, Any]) -> list[dict[str, Any]]:
    metas, bmetas, reconstructions = recon["cascade_meta"], recon["baseline_meta"], recon["reconstructions"]
    rows: list[dict[str, Any]] = []

    def row(kind: str, family: str | None, arm: str, doc_label: str, status: str,
            fixed: int | None, getter: Any, not_graded: str | None) -> dict[str, Any]:
        entry: dict[str, Any] = {"kind": kind, "family": family, "arm": arm, "doc_label": doc_label, "chain_status": status}
        if not_graded is not None:
            entry.update(value=None, determined_by=not_graded)
            return entry
        values = [getter(r) for r in reconstructions]
        if fixed is not None:
            entry.update(value=fixed, determined_by="chain status")
        elif all(v == values[0] for v in values):
            entry.update(value=values[0], determined_by="stored statistics")
        else:
            entry.update(value=None, determined_by="ambiguous", values_by_reconstruction=values)
        return entry

    for m in metas:
        arm, label, status = m["arm"], m["doc_label"], m["status"]
        for family in FAMILIES:
            fixed = dict(rro.phase3_cells(metas, family, arm)).get(label) if m["phase3"] == "graded" else None
            if m["phase3"] == "frozen":
                note = (f"not graded: chain froze at step {m['frozen_at_step']}; this round trip finished before the freeze"
                        if family in m["finished_phase3_families"]
                        else f"not graded: chain froze at step {m['frozen_at_step']} before this round trip finished")
            elif m["phase3"] == "grader_raised":
                note = "not graded: the Phase-3 grader raised"
            else:
                note = None
            rows.append(row("phase3", family, arm, label, status, fixed,
                            lambda r, f=family, a=arm, d=label: r["phase3"][f][a][d], note))
        ks_note = {"graded": None, "not_reached": f"not graded: chain froze at step {m['frozen_at_step']} before Checkpoint B",
                   "grader_raised": "not graded: the Phase-2 grader raised"}[m["phase2"]]
        fixed = dict(rro.keep_survival_cells(metas, arm)).get(label) if m["phase2"] == "graded" else None
        rows.append(row("keep_survival", None, arm, label, status, fixed,
                        lambda r, a=arm, d=label: r["keep_survival"][a][d], ks_note))
    for family in FAMILIES:
        for b in bmetas[family]:
            arm, label, status = b["arm"], b["doc_label"], b["status"]
            note = "excluded: baseline chain blocked" if status == "blocked" else None
            fixed = 0 if status == "completed_with_failure" else None
            rows.append(row("baseline", family, arm, label, status, fixed,
                            lambda r, f=family, a=arm, d=label: r["baseline"][f][a][d], note))
    return sorted(rows, key=lambda e: (e["kind"], e["family"] or "", e["doc_label"], e["arm"]))


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def _relative(path: Path) -> str:
    path = path.resolve()
    return path.relative_to(REPO).as_posix() if REPO in path.parents else path.as_posix()


def build_output(inputs: dict[str, Any] | None = None, recon: dict[str, Any] | None = None,
                 input_paths: dict[str, Path] | None = None) -> dict[str, Any]:
    inputs = inputs or rro.load_inputs()
    recon = recon or rro.reconstruct(inputs)
    input_paths = input_paths or {"statistics": rro.STATISTICS, "primary_manifest": rro.PRIMARY_MANIFEST,
                                  "baseline_manifest": rro.BASELINE_MANIFEST}
    metas, bmetas = recon["cascade_meta"], recon["baseline_meta"]
    crashed = [f"{m['arm']} / {m['doc_label']}" for m in metas if m["phase3"] == "grader_raised"]
    crash_note = (f" The chain(s) whose Phase-3 grader raised ({', '.join(crashed)}) have no Phase-3 verdicts and no "
                  "composite and are excluded from those measures, as in every scenario; see "
                  "grader_crash_chain_sensitivity." if crashed else "")
    per_recon: list[dict[str, Any]] = []
    with rro.as_run_summation():
        for reconstruction in recon["reconstructions"]:
            chains, bchains = rro.build_chains(metas, bmetas, reconstruction)
            reports = {mode: crs.compute_respec_cascade_tiers(chains, bchains, frozen_chain_mode=mode)
                       for mode in crs.FROZEN_CHAIN_MODES}
            scenarios, levels_of = {}, {}
            for name, mode, finished, not_run in SCENARIOS:
                levels = scenario_levels(metas, chains, bchains, mode, finished, not_run)
                measures = scenario_measures(levels)
                if finished is None and not_run is None:
                    _check_against_pipeline(measures, reports[mode])
                as_mode = "excluded" if mode == "exclude" else "scored as failures"
                levels_of[name] = levels
                scenarios[name] = {
                    "description": SCENARIO_DESCRIPTIONS[name] + crash_note,
                    "analysis_status": "as_run_reported" if name == "as_run" else POST_HOC,
                    "frozen_chain_mode": mode,
                    "finished_round_trips_before_freeze": {"pass": "scored as passes", "exclude": "excluded"}.get(finished, as_mode),
                    "phase3_round_trip_in_progress_at_freeze": as_mode,
                    "phase3_families_never_run": "excluded" if not_run == "exclude" else as_mode,
                    "measures": measures,
                    "section7": {test: section7_flags(measures, test) for test in TESTS},
                    "grader_crash_chain_sensitivity": crash_chain_sensitivity(metas, levels, measures),
                }
            bounds = {
                "under_protocol_scoring": finished_round_trip_bounds(
                    metas, levels_of["protocol"], scenarios["protocol"]["measures"], scenarios,
                    "protocol", "protocol_finished_round_trips_pass", ("protocol_finished_round_trips_excluded",)),
                "with_not_run_families_excluded": finished_round_trip_bounds(
                    metas, levels_of["protocol_not_run_families_excluded"],
                    scenarios["protocol_not_run_families_excluded"]["measures"], scenarios,
                    "protocol_not_run_families_excluded", "protocol_not_run_families_excluded_finished_round_trips_pass"),
            }
            per_recon.append({"scenarios": scenarios, "bounds": bounds})
    merged = merge(per_recon)

    frozen = []
    for m in metas:
        if m["frozen_at_step"] is None:
            continue
        frozen.append({
            "doc_label": m["doc_label"], "arm": m["arm"], "status": m["status"], "frozen_at_step": m["frozen_at_step"],
            "checkpoint_b_graded": m["phase2"] == "graded",
            "phase3_round_trips_finished_before_freeze": m["finished_phase3_families"],
            "phase3_family_in_progress": m["in_progress_phase3_family"],
            "phase3_families_not_run": not_run_families(m),
            "freeze_cause": "not recorded (package-invalid and marker re-resolution failures share one status string)",
            "freeze_step_checks_marker_re_resolution": m["frozen_at_step"] in _RE_RESOLUTION_FREEZE_STEPS,
        })
    n_finished = sum(len(f["phase3_round_trips_finished_before_freeze"]) for f in frozen)
    return {
        "schema": "paper-s23-respec-cascade-reanalysis-v1",
        "description": __doc__.split("\n\n")[0].replace("\n", " "),
        "inputs": {name: {"path": _relative(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for name, path in sorted(input_paths.items())},
        "seed": crs._SEED,
        "n_resamples": crs._RESAMPLES,
        "analysis_status": dict(ANALYSIS_STATUS),
        "analysis_status_note": (
            "Only the as_run scenario's observation_level_as_run test is what the 2026-09-23 run reported. "
            f"Everything labelled {POST_HOC} was chosen after its results were known (document_level_exact is the "
            "exact form of Tier 1's paired_significance_exact); it may be called primary only in the S25 re-run "
            "protocol, which names these tests before any data exists."
        ),
        "frozen_chain_scoring_note": _FAIL_MODE_NOTE,
        "tests": {
            "chain_level": f"Exact cluster sign-flip test; all observations of one (document, anchor-set) chain flip together. {POST_HOC}.",
            "observation_level_as_run": "The pipeline's Monte Carlo paired_permutation_test (2000 draws, seed 20260828, no +1 correction), every observation its own unit -- the test behind the reported p-values.",
            "observation_level_exact": f"The as-run statistic with an exact sign-flip p, every observation its own unit. {POST_HOC}.",
            "document_level_exact": f"Exact cluster sign-flip test by original document (the exact Tier-1 test); with 3 documents no p below 0.25 is attainable. {POST_HOC}.",
        },
        "bounds_description": (
            "All 2**10 = 1,024 0/1 assignments of the 10 Phase-3 round trips that finished before a freeze and were "
            "never graded, every other cell as in the named base scenario; chain-level exact test. Under protocol "
            "scoring the all-fail assignment is the `protocol` scenario (one end) and the all-pass assignment "
            "`protocol_finished_round_trips_pass` (the other end); excluding the 10 round trips "
            "(`protocol_finished_round_trips_excluded`) is an intermediate point inside the ranges, not a bound. "
            "p-value extremes need not sit at the all-fail/all-pass ends, hence the full enumeration. Only the "
            "control Phase-3 measures depend on these cells: composite scores a frozen chain 0 in every scoring, "
            "keep-survival is graded at Checkpoint B before Phase 3, and treatment never froze. The grader-crash "
            "chain stays excluded here (see each scenario's grader_crash_chain_sensitivity), so these ranges do not "
            "cover it."
        ),
        "grader_crash_chain_sensitivity_description": (
            "Per scenario: every 0/1 assignment of the 5 Phase-3 cells of the chain(s) whose Phase-3 grader raised "
            "(32) and, independently, of their whole-chain composite (2), the rest of the scenario unchanged; "
            "chain-level exact test. Cells vary independently, a superset of the assignments consistent with the "
            "chain status. `verdict` counts are over the 32 Phase-3 assignments, the composite variant over all 64."
        ),
        "sign_convention": "observed_mean_diff = mean(A - B) over matched observations; effect_pp = 100 * observed_mean_diff. Drops: A = cascade Phase-3 outcome, B = fresh K=1 baseline, negative = worse after the cascade. Direct comparisons: A = control, B = treatment, negative = treatment better.",
        "reconstruction": {
            "n_consistent_reconstructions": len(recon["reconstructions"]),
            "reproduces_stored_statistics": True,
            "stored_leaves_compared": recon["stored_leaves_compared"],
            "stored_fields_not_compared": ["run_root", "baseline_run_root"],
            "reason_substitutions": recon["reason_substitutions"],
            "search": recon["search"],
            "cells": cells_table(recon),
        },
        "frozen_chains": frozen,
        "n_phase3_round_trips_finished_before_freeze": n_finished,
        "scenarios": merged["scenarios"],
        "bounds": merged["bounds"],
    }


def serialize(output: dict[str, Any]) -> str:
    return json.dumps(output, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--statistics", type=Path, default=rro.STATISTICS)
    parser.add_argument("--primary-manifest", type=Path, default=rro.PRIMARY_MANIFEST)
    parser.add_argument("--baseline-manifest", type=Path, default=rro.BASELINE_MANIFEST)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    paths = {"statistics": args.statistics, "primary_manifest": args.primary_manifest,
             "baseline_manifest": args.baseline_manifest}
    output = build_output(rro.load_inputs(**paths), input_paths=paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialize(output), encoding="utf-8", newline="\n")
    print(f"wrote {args.out}: {output['reconstruction']['n_consistent_reconstructions']} consistent reconstruction(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
