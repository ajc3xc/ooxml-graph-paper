"""PAPER-S23 (`docs/paper-s23-respec-cascade-protocol-v0.md`, locked 2026-09-20,
five-family contingency per section 1.2a / 2.3): Tier 1/2/3 aggregation for
`respec_cascade` chain results.

Rotation `R' = [bibliography, citation, section_reorder, equation, caption]`
(`table_structural` dropped -- `insert_table`/`remove_table` confirmed absent
from the live `meridian-docs` tool manifest at corpus-build time, section
1.2a item 2).

This module deliberately does NOT reimplement any statistical primitive.
`bootstrap_ci`/`paired_permutation_test` (`tools/graph_scorer.py`) and
`weighted_mean`/`weighted_bootstrap_ci`/`weighted_paired_permutation_test`/
`estimate_icc_and_effective_n` (`tools/compute_multianchor_extension_statistics.py`)
are imported and used UNMODIFIED, exactly as protocol section 5 item 7
requires. The module constants `_SEED`/`_RESAMPLES` (2000 resamples, seed
20260828) are likewise imported from `compute_multianchor_extension_statistics.py`
rather than re-declared, so every tier in this file shares one seed with the
rest of the paper's statistics.

Three separate outcome measures are reported, each with its OWN Tier1/2/3
triplet (protocol section 6-7), per family and pooled across families:

  (a) Phase 3 ("SECOND EXPOSURE") composite pass rate -- the `checkpoint_c`
      component of a chain's overall PASS (section 4), both as a whole-chain
      composite and broken out per family (protocol section 7's primary
      comparison is explicitly "per family and pooled").
  (b) Phase 2 ("RESPEC") keep-survival pass rate -- `score_keep_survival`'s
      own pass/fail on `B`/`E`/`Cap` at Checkpoint B, the design's central,
      novel test (section 4, Checkpoint B item 3).
  (c) A FRESH, ISOLATED K=1 baseline pass rate per arm, PER FAMILY (protocol
      section 3: "run one fresh, isolated K=1 forward+inverse trial at the
      identical anchor used in this chain's Phase 1/3" -- read literally,
      this is a baseline per (document, anchor-set, FAMILY, arm), not one
      pooled baseline number, since each family has its own anchor and its
      own single-edit pass/fail semantics). This baseline comes from a
      SEPARATE, already-existing run of
      `tools/run_paper_s7_benchmark.py::run_chain(k_pairs=1)`, one such run
      per family, never from this family's own cascade chains.

Section 7's three preregistered numbers -- `control_drop`, `treatment_drop`,
and the direct control-vs-treatment Phase-3 comparison -- are computed at
anchor-set granularity (paired by `doc_label`, i.e. by (document, anchor-set),
matching section 7's own "matched by doc_label + anchor-set" wording) and are
written out explicitly, under their own labeled keys, both per family and
pooled -- never left implicit inside a larger tiered dict.

-------------------------------------------------------------------------
SCHEMA THIS FILE READS (reconciled against the REAL orchestrator, 2026-09-20)
-------------------------------------------------------------------------
`tools/run_respec_cascade_family.py` now exists and has been read directly
(not assumed) to reconcile this module's loaders against its ACTUAL
`chain-result.json` shape -- an earlier draft of this file specified a
speculative `checkpoint_a`/`checkpoint_b`/`checkpoint_c` schema written
before that orchestrator existed, which never matched what it actually
produces; that mismatch is fixed, not merely documented, in the outcome
extractors below.

  `--run-root/<chain_dir>/chain-result.json`, one file per (document,
  anchor-set, arm) -- ONE heterogeneous chain spans all five families across
  all three phases, unlike `run_paper_s7_benchmark.py::run_chain`'s
  per-family checkpoint (so, unlike
  `compute_multianchor_extension_statistics.load_family_chains`, there is no
  per-family subdirectory under `run_root` here). Real keys, as written by
  `run_respec_cascade_chain`:

    doc_label            -- anchor-set-scoped label, convention
                             f"{original_doc_label}__anchor{anchor_set_index}"
                             (the SAME convention
                             `run_paper_s7_benchmark.py::run_chain`'s own
                             docstring already documents for multi-anchor
                             callers, reused here rather than inventing a
                             second one).
    original_doc_label   -- base document label (e.g.
                             "masters-dissertation-defense"), used for Tier
                             1/2 per-document grouping. If absent, derived by
                             stripping "__anchor<N>" from doc_label.
    anchor_set_index      -- int.
    arm                   -- "control" | "treatment".
    status                -- "completed" | "completed_with_failure" |
                             "not_applicable" | f"chain_broken_at_step_{id}"
                             (a package-validity gate failure, id e.g. "1.3"
                             or "3.3a") | "render_gate_timeout". PLUS
                             "harness_exception"/"blocked" reserved for
                             future harness-level failure modes, not
                             currently emitted by the orchestrator itself.
    phase1_result         -- None (chain froze before Phase 1 finished) or
                             {"phase1_pass": bool, "families": {family:
                             {"verdict": "pass"|..., ...}, ...}, ...}
    phase2_result          -- None (froze before/during Phase 2) or
                             {"phase2_pass": bool, "citation_absent": bool,
                              "section_at_d2": bool, "keep_survival":
                              {"overall_status": "clean_keep_survival"|...,
                               ...}, ...}
    phase3_result          -- None (froze before/during Phase 3) or
                             {"phase3_pass": bool, "families": {family:
                              {"verdict": "pass"|..., ...}, ...},
                              "final_structure_match": bool, ...}

  `--baseline-run-root/<family>/<chain_id>/chain-result.json` -- this IS the
  existing, unmodified `run_paper_s7_benchmark.py::run_chain(k_pairs=1)`
  checkpoint format, one per-family subtree per
  `compute_multianchor_extension_statistics.load_family_chains`'s own,
  already-validated convention. The `doc_label` passed to each baseline
  `run_chain` call MUST use the identical
  f"{original_doc_label}__anchor{anchor_set_index}" convention as the cascade
  chains, for a given (document, anchor-set) to be matched between the two
  -- this is the load-bearing integration contract for section 3's paired
  comparison and is flagged again in this module's final report as an open
  risk (nothing upstream enforces it yet).

Usage:
    python compute_respec_cascade_statistics.py \
        --run-root D:/MeridianData/ooxml-graph-paper/runs/paper-s23-respec-cascade/runs \
        --baseline-run-root D:/MeridianData/ooxml-graph-paper/runs/paper-s23-respec-cascade/baseline-runs \
        --out D:/MeridianData/ooxml-graph-paper/runs/paper-s23-respec-cascade/statistics.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_multianchor_extension_statistics import (  # noqa: E402 -- reused UNMODIFIED, see module docstring
    _RESAMPLES,
    _SEED,
    estimate_icc_and_effective_n,
    weighted_bootstrap_ci,
    weighted_mean,  # noqa: F401 -- re-exported for callers pattern-matching the multi-anchor module's own surface
    weighted_paired_permutation_test,
)
from compute_s7_statistics import _chain_outcome  # noqa: E402 -- reused UNMODIFIED for baseline pass/fail
from graph_scorer import bootstrap_ci, paired_permutation_test  # noqa: E402 -- reused UNMODIFIED

# Five-family contingency rotation R' (protocol section 2.3 / 1.2a item 2).
# `table_structural` is NOT in this list -- see module docstring.
FAMILIES: list[str] = ["bibliography", "citation", "section_reorder", "equation", "caption"]

# Statuses excluded from every outcome measure's denominator (None, not a
# fabricated 0) -- mirrors compute_s7_statistics._chain_outcome's own
# exclusion set, PLUS "render_gate_timeout", which protocol section 7's
# render-gate/host-contention control requires be reported separately and
# never folded into control_drop/treatment_drop.
_EXCLUDED_STATUSES = frozenset({"not_applicable", "harness_exception", "blocked", "render_gate_timeout"})


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_respec_cascade_chains(run_root: Path) -> list[dict[str, Any]]:
    """Every `chain-result.json` directly under `run_root/<chain_dir>/`. One
    entry = one full three-phase, five-family chain for one (document,
    anchor-set, arm). See the module docstring's SCHEMA section for the
    exact keys this file depends on -- `tools/run_respec_cascade_family.py`
    does not exist yet, so this is a specification, not an observed format."""
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


def load_baseline_chains(baseline_run_root: Path, families: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Baseline is PER FAMILY (protocol section 3), not one pooled number --
    see the module docstring for why. Returns {family: [chain, ...]}, each
    chain the raw, unmodified `run_paper_s7_benchmark.py::run_chain`
    checkpoint dict, read the same way
    `compute_multianchor_extension_statistics.load_family_chains` already
    reads per-family chain trees (`baseline_run_root/<family>/<chain_dir>/
    chain-result.json`), minus that module's own `doc_label_mapping.json`
    indirection -- baseline chains here are expected to carry `doc_label` in
    the f"{original}__anchor{i}" convention directly, matched against the
    same convention on the cascade side, so no separate mapping file is
    needed (see module docstring's SCHEMA note on this being the load-
    bearing integration contract)."""
    families = list(families) if families is not None else list(FAMILIES)
    out: dict[str, list[dict[str, Any]]] = {}
    for family in families:
        family_root = baseline_run_root / family
        chains: list[dict[str, Any]] = []
        if family_root.is_dir():
            for chain_dir in sorted(family_root.iterdir()):
                if not chain_dir.is_dir():
                    continue
                cr = chain_dir / "chain-result.json"
                if cr.is_file():
                    chains.append(json.loads(cr.read_text(encoding="utf-8")))
        out[family] = chains
    return out


# ---------------------------------------------------------------------------
# Outcome extraction -- turns one raw chain dict into a single 1.0/0.0/None
# per outcome measure. None means "excluded from this measure's denominator",
# always with a reason recorded by the caller (section 6: never a silently
# reduced denominator).
# ---------------------------------------------------------------------------

def _original_doc_label(chain: dict[str, Any]) -> str:
    """Base document label for Tier 1/2 per-document grouping. Prefers an
    explicit `original_doc_label` field; falls back to stripping
    "__anchor<N>" from `doc_label` (the same multi-anchor convention
    `run_paper_s7_benchmark.py::run_chain`'s own docstring documents)."""
    explicit = chain.get("original_doc_label")
    if explicit:
        return str(explicit)
    doc_label = str(chain.get("doc_label", ""))
    if "__anchor" in doc_label:
        return doc_label.rsplit("__anchor", 1)[0]
    return doc_label


def _phase3_composite_outcome(chain: dict[str, Any]) -> float | None:
    """Outcome measure (a), whole-chain composite: Phase 1 pass AND Phase 2
    pass AND Phase 3 pass AND no package-validity gate failure anywhere in
    the chain (protocol section 4's "Composite chain PASS" definition).

    Reads the REAL schema `tools/run_respec_cascade_family.py` actually
    writes (`phase1_result`/`phase2_result`/`phase3_result`, each with its
    own `phase{N}_pass` boolean key) -- NOT `checkpoint_a`/`checkpoint_b`/
    `checkpoint_c`/`"pass"`, which this file originally specified
    speculatively before that orchestrator existed and never reconciled
    against its real, landed output."""
    status = chain.get("status")
    if status in _EXCLUDED_STATUSES:
        return None
    phase1 = chain.get("phase1_result")
    phase2 = chain.get("phase2_result")
    phase3 = chain.get("phase3_result")
    if phase1 is None or phase2 is None or phase3 is None:
        # The chain froze at a package-validity gate before all three
        # phases completed (`run_respec_cascade_chain`'s own `_freeze`
        # leaves every not-yet-reached phase's result as `None`) -- scored
        # 0.0, not excluded: the composite requires all three phases to
        # have genuinely passed, and a mid-chain freeze is itself a real
        # structural finding about that arm's output, per protocol section
        # 4/7, not an absence of information.
        return 0.0
    a, b, c = phase1.get("phase1_pass"), phase2.get("phase2_pass"), phase3.get("phase3_pass")
    if a is None or b is None or c is None:
        return None
    return 1.0 if (a and b and c) else 0.0


def _phase3_family_outcome(chain: dict[str, Any], family: str) -> float | None:
    """Outcome measure (a), per-family: this family's own Phase-3
    forward+inverse pass/fail, section 7's primary per-family comparison
    unit. Reads `phase3_result["families"][family]["verdict"] == "pass"`
    (the real per-family grader dicts `_grade_family_inverse` returns, each
    carrying a `"verdict"` key -- the same convention
    `grade_phase1_build`/`grade_phase3_second_exposure` themselves check via
    `r.get("verdict") == "pass"`), NOT `checkpoint_c["per_family"][family]
    ["pass"]`, which never matches anything the real evaluator produces."""
    status = chain.get("status")
    if status in _EXCLUDED_STATUSES:
        return None
    phase3 = chain.get("phase3_result")
    if phase3 is None:
        # Phase 3 never ran (the chain froze during Phase 1 or Phase 2) --
        # this family's own Phase-3 round trip never happened, so there is
        # no real per-family verdict to report. Excluded (None), not the
        # whole-chain composite's 0.0 -- a family-specific outcome that
        # never got a chance to run is a different thing from one that ran
        # and failed.
        return None
    families = phase3.get("families") or {}
    fam = families.get(family)
    if fam is None:
        return None
    verdict = fam.get("verdict")
    if verdict is None:
        return None
    return 1.0 if verdict == "pass" else 0.0


def _phase2_keep_survival_outcome(chain: dict[str, Any]) -> float | None:
    """Outcome measure (b): `score_keep_survival`'s own pass/fail at
    Checkpoint B (protocol section 4, Checkpoint B item 3) -- distinct from
    Checkpoint B's FULL pass (which also folds in citation-absence,
    section-at-D2, and the zero-unintended-diff check). Reads
    `phase2_result["keep_survival"]["overall_status"] == "clean_keep_survival"`
    (a status STRING, per `graph_scorer.score_keep_survival`'s real return
    shape), NOT `checkpoint_b["keep_survival"]["pass"]` (a boolean that
    field never had)."""
    status = chain.get("status")
    if status in _EXCLUDED_STATUSES:
        return None
    phase2 = chain.get("phase2_result")
    if phase2 is None:
        # Phase 2 never ran (the chain froze during Phase 1) -- excluded,
        # same reasoning as the per-family Phase-3 case above.
        return None
    keep_survival = phase2.get("keep_survival") or {}
    overall_status = keep_survival.get("overall_status")
    if overall_status is None:
        return None
    return 1.0 if overall_status == "clean_keep_survival" else 0.0


def _baseline_outcome(chain: dict[str, Any]) -> float | None:
    """Outcome measure (c): reuses `compute_s7_statistics._chain_outcome`
    UNMODIFIED -- baseline chains are exactly `run_chain`'s own K=1
    checkpoint format, so its already-validated pass/fail rule applies as-is."""
    return _chain_outcome(chain)


# ---------------------------------------------------------------------------
# Grouping: arm -> original_doc_label -> [outcome, ...], with exclusions
# recorded (never silently dropped, per section 6).
# ---------------------------------------------------------------------------

def _group_by_document(
    chains: list[dict[str, Any]],
    outcome_fn: Callable[[dict[str, Any]], float | None],
    measure: str,
) -> tuple[dict[str, dict[str, list[float]]], list[dict[str, Any]]]:
    grouped: dict[str, dict[str, list[float]]] = {"control": {}, "treatment": {}}
    excluded: list[dict[str, Any]] = []
    for chain in chains:
        arm = chain.get("arm")
        if arm not in ("control", "treatment"):
            continue
        outcome = outcome_fn(chain)
        if outcome is None:
            excluded.append({
                "measure": measure, "doc_label": chain.get("doc_label"), "arm": arm,
                "reason": chain.get("status") or "outcome_unavailable",
            })
            continue
        grouped[arm].setdefault(_original_doc_label(chain), []).append(outcome)
    return grouped, excluded


def _anchor_level_values(
    chains: list[dict[str, Any]],
    outcome_fn: Callable[[dict[str, Any]], float | None],
) -> dict[str, dict[str, float]]:
    """arm -> doc_label (anchor-set, NOT original document) -> outcome. Used
    for the section-7 paired comparisons, which are matched "by doc_label +
    anchor-set", a finer grain than Tier 1/2's per-document mean."""
    out: dict[str, dict[str, float]] = {"control": {}, "treatment": {}}
    for chain in chains:
        arm = chain.get("arm")
        if arm not in out:
            continue
        outcome = outcome_fn(chain)
        if outcome is None:
            continue
        out[arm][str(chain.get("doc_label"))] = outcome
    return out


# ---------------------------------------------------------------------------
# Tier 1/2/3 report -- pattern-matched to
# compute_multianchor_extension_statistics.compute_family_tiers's own shape,
# adapted to take already-grouped (arm -> doc -> [outcomes]) dicts directly,
# since respec_cascade's outcome measures are derived booleans from a
# heterogeneous chain shape compute_family_tiers's own chain-shaped grouping
# can't parse -- every underlying statistical primitive below is still the
# SAME function, imported and called unmodified.
# ---------------------------------------------------------------------------

def _tiered_report(control_by_doc: dict[str, list[float]], treatment_by_doc: dict[str, list[float]]) -> dict[str, Any]:
    def per_doc_means(by_doc: dict[str, list[float]]) -> dict[str, float]:
        return {doc: sum(vs) / len(vs) for doc, vs in by_doc.items() if vs}

    control_means = per_doc_means(control_by_doc)
    treatment_means = per_doc_means(treatment_by_doc)

    # --- Tier 1: unweighted per-document mean (N=3 documents; demonstration/
    # mechanism-probing strength per protocol section 6, not a powered
    # confirmatory test on its own).
    tier1_control_values = list(control_means.values())
    tier1_treatment_values = list(treatment_means.values())
    paired_docs = sorted(set(control_means) & set(treatment_means))
    tier1 = {
        "note": "Unweighted per-document mean, N=3 documents max -- demonstration/mechanism-probing strength, not a powered confirmatory test on its own (protocol section 6).",
        "control_n_documents": len(tier1_control_values),
        "control_pass_rate_ci": bootstrap_ci(tier1_control_values) if tier1_control_values else None,
        "treatment_n_documents": len(tier1_treatment_values),
        "treatment_pass_rate_ci": bootstrap_ci(tier1_treatment_values) if tier1_treatment_values else None,
        "paired_n_documents": len(paired_docs),
        "paired_significance": (
            paired_permutation_test([control_means[d] for d in paired_docs],
                                     [treatment_means[d] for d in paired_docs])
            if len(paired_docs) >= 2 else None
        ),
    }

    # --- Tier 2: anchor-set-count-weighted per-document mean.
    control_items = [(control_means[d], len(control_by_doc[d])) for d in control_means]
    treatment_items = [(treatment_means[d], len(treatment_by_doc[d])) for d in treatment_means]
    paired_control_items = [(control_means[d], len(control_by_doc[d])) for d in paired_docs]
    paired_treatment_items = [(treatment_means[d], len(treatment_by_doc[d])) for d in paired_docs]
    tier2 = {
        "control": weighted_bootstrap_ci(control_items),
        "treatment": weighted_bootstrap_ci(treatment_items),
        "paired_significance": (
            weighted_paired_permutation_test(paired_control_items, paired_treatment_items)
            if len(paired_docs) >= 2 else None
        ),
    }

    # --- Tier 3: pooled anchor-set-level (naive) + ICC-corrected effective N.
    tier3_control_values = [v for vs in control_by_doc.values() for v in vs]
    tier3_treatment_values = [v for vs in treatment_by_doc.values() for v in vs]
    tier3 = {
        "control_naive_pooled_n": len(tier3_control_values),
        "control_pass_rate_ci_naive": bootstrap_ci(tier3_control_values) if tier3_control_values else None,
        "control_clustering": estimate_icc_and_effective_n(control_by_doc),
        "treatment_naive_pooled_n": len(tier3_treatment_values),
        "treatment_pass_rate_ci_naive": bootstrap_ci(tier3_treatment_values) if tier3_treatment_values else None,
        "treatment_clustering": estimate_icc_and_effective_n(treatment_by_doc),
        "disclosure": (
            "The naive pooled CI above treats every anchor-set (and, for pooled-across-families "
            "measures, every family x anchor-set pair) as an independent observation, which "
            "OVERSTATES precision. The *_clustering fields give the ICC-corrected effective N; "
            "treat that, not the naive pooled N, as the honest sample size for this tier "
            "(protocol section 6)."
        ),
    }

    return {
        "tier1_per_document_unweighted": tier1,
        "tier2_anchor_weighted_document_mean": tier2,
        "tier3_pooled_anchor_level": tier3,
        "n_distinct_documents": {"control": len(control_means), "treatment": len(treatment_means)},
    }


# ---------------------------------------------------------------------------
# Section 7: control_drop / treatment_drop / direct comparison -- anchor-set-
# level PAIRED tests, matched by doc_label, explicitly labeled and returned
# under their own keys (never left implicit inside a tiered dict).
# ---------------------------------------------------------------------------

def _paired_drop(
    cascade_by_arm_doc: dict[str, dict[str, float]],
    baseline_by_arm_doc: dict[str, dict[str, float]],
    arm: str,
) -> dict[str, Any]:
    """paired_permutation_test (graph_scorer.py, UNMODIFIED) between this
    arm's cascade Phase-3 outcome and that SAME arm's fresh isolated
    baseline outcome, matched by doc_label (document + anchor-set), per
    protocol section 7's `control_drop`/`treatment_drop` definition."""
    cascade_docs = cascade_by_arm_doc.get(arm, {})
    baseline_docs = baseline_by_arm_doc.get(arm, {})
    common = sorted(set(cascade_docs) & set(baseline_docs))
    if len(common) < 2:
        return {
            "observed_mean_diff": None, "p_value": None, "n_paired_anchor_sets": len(common),
            "reason": "fewer than 2 anchor-sets with both a cascade Phase-3 outcome and a matching fresh isolated baseline outcome for this arm",
        }
    result = paired_permutation_test([cascade_docs[d] for d in common], [baseline_docs[d] for d in common])
    result["n_paired_anchor_sets"] = len(common)
    result["matched_anchor_sets"] = common
    result["method"] = "paired_permutation_test(cascade Phase-3 outcome, fresh isolated K=1 baseline outcome), matched by doc_label"
    return result


def _direct_arm_comparison(cascade_by_arm_doc: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Direct control-vs-treatment paired_permutation_test on the cascade
    Phase-3 outcome itself, matched by doc_label -- section 7's third
    preregistered number."""
    control_docs = cascade_by_arm_doc.get("control", {})
    treatment_docs = cascade_by_arm_doc.get("treatment", {})
    common = sorted(set(control_docs) & set(treatment_docs))
    if len(common) < 2:
        return {
            "observed_mean_diff": None, "p_value": None, "n_paired_anchor_sets": len(common),
            "reason": "fewer than 2 anchor-sets with a Phase-3 outcome on both arms",
        }
    result = paired_permutation_test([control_docs[d] for d in common], [treatment_docs[d] for d in common])
    result["n_paired_anchor_sets"] = len(common)
    result["matched_anchor_sets"] = common
    result["method"] = "paired_permutation_test(control Phase-3 outcome, treatment Phase-3 outcome), matched by doc_label"
    return result


def _pool_across_families(per_family: dict[str, dict[str, dict[str, float]]]) -> dict[str, dict[str, float]]:
    """Merges {family: {arm: {doc_label: value}}} into {arm: {"family::doc_label": value}}.
    The composite key is required here (unlike _tiered_report's grouping,
    which is safe to leave as plain original_doc_label) because every family
    within one chain shares the SAME doc_label -- without the family prefix,
    pooling would silently overwrite one family's anchor-set outcome with
    another's in the same arm/doc_label slot instead of keeping both as
    distinct paired observations."""
    pooled: dict[str, dict[str, float]] = {"control": {}, "treatment": {}}
    for family, by_arm in per_family.items():
        for arm, by_doc in by_arm.items():
            for doc_label, value in by_doc.items():
                pooled.setdefault(arm, {})[f"{family}::{doc_label}"] = value
    return pooled


# ---------------------------------------------------------------------------
# Top-level aggregation
# ---------------------------------------------------------------------------

def compute_respec_cascade_tiers(
    cascade_chains: list[dict[str, Any]],
    baseline_chains: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    excluded_observations: list[dict[str, Any]] = []
    render_gate_timeouts: list[dict[str, Any]] = [
        {"doc_label": c.get("doc_label"), "arm": c.get("arm"), "chain_broken_at_step": c.get("chain_broken_at_step")}
        for c in cascade_chains if c.get("status") == "render_gate_timeout"
    ]

    # ---- (a) Phase 3 composite pass rate, per arm -- whole-chain.
    composite_grouped, composite_excluded = _group_by_document(cascade_chains, _phase3_composite_outcome, "phase3_composite")
    excluded_observations.extend(composite_excluded)
    phase3_composite_tiers = _tiered_report(composite_grouped["control"], composite_grouped["treatment"])
    phase3_composite_anchor_level = _anchor_level_values(cascade_chains, _phase3_composite_outcome)

    # ---- (a) Phase 3 pass rate, per family.
    per_family_phase3_tiers: dict[str, Any] = {}
    per_family_phase3_anchor_level: dict[str, dict[str, dict[str, float]]] = {}
    for family in FAMILIES:
        def _fn(chain: dict[str, Any], family: str = family) -> float | None:
            return _phase3_family_outcome(chain, family)
        grouped, excluded = _group_by_document(cascade_chains, _fn, f"phase3_{family}")
        excluded_observations.extend(excluded)
        per_family_phase3_tiers[family] = _tiered_report(grouped["control"], grouped["treatment"])
        per_family_phase3_anchor_level[family] = _anchor_level_values(cascade_chains, _fn)

    # ---- (a) pooled across families (family x anchor-set as the observation unit).
    pooled_phase3_grouped: dict[str, dict[str, list[float]]] = {"control": {}, "treatment": {}}
    for family in FAMILIES:
        def _fn2(chain: dict[str, Any], family: str = family) -> float | None:
            return _phase3_family_outcome(chain, family)
        grouped, _excl = _group_by_document(cascade_chains, _fn2, f"phase3_{family}_pooled")
        for arm in ("control", "treatment"):
            for doc, vs in grouped[arm].items():
                pooled_phase3_grouped[arm].setdefault(doc, []).extend(vs)
    pooled_phase3_tiers = _tiered_report(pooled_phase3_grouped["control"], pooled_phase3_grouped["treatment"])
    pooled_phase3_anchor_level = _pool_across_families(per_family_phase3_anchor_level)

    # ---- (b) Phase 2 keep-survival pass rate (chain-level, one bool per anchor-set).
    ks_grouped, ks_excluded = _group_by_document(cascade_chains, _phase2_keep_survival_outcome, "phase2_keep_survival")
    excluded_observations.extend(ks_excluded)
    phase2_keep_survival_tiers = _tiered_report(ks_grouped["control"], ks_grouped["treatment"])
    phase2_keep_survival_anchor_level = _anchor_level_values(cascade_chains, _phase2_keep_survival_outcome)
    keep_survival_direct_comparison = _direct_arm_comparison(phase2_keep_survival_anchor_level)

    # ---- (c) fresh isolated K=1 baseline pass rate, per arm, per family.
    baseline_tiers: dict[str, Any] = {}
    baseline_anchor_level: dict[str, dict[str, dict[str, float]]] = {}
    pooled_baseline_grouped: dict[str, dict[str, list[float]]] = {"control": {}, "treatment": {}}
    for family in FAMILIES:
        chains_f = baseline_chains.get(family, [])
        grouped, excluded = _group_by_document(chains_f, _baseline_outcome, f"baseline_{family}")
        excluded_observations.extend(excluded)
        baseline_tiers[family] = _tiered_report(grouped["control"], grouped["treatment"])
        baseline_anchor_level[family] = _anchor_level_values(chains_f, _baseline_outcome)
        for arm in ("control", "treatment"):
            for doc, vs in grouped[arm].items():
                pooled_baseline_grouped[arm].setdefault(doc, []).extend(vs)
    baseline_tiers["pooled"] = _tiered_report(pooled_baseline_grouped["control"], pooled_baseline_grouped["treatment"])
    pooled_baseline_anchor_level = _pool_across_families(baseline_anchor_level)

    # ---- Section 7: control_drop / treatment_drop / direct comparison, per family and pooled.
    confirm_disconfirm: dict[str, Any] = {}
    for family in FAMILIES:
        cascade_al = per_family_phase3_anchor_level[family]
        baseline_al = baseline_anchor_level[family]
        confirm_disconfirm[family] = {
            "control_drop": _paired_drop(cascade_al, baseline_al, "control"),
            "treatment_drop": _paired_drop(cascade_al, baseline_al, "treatment"),
            "direct_control_vs_treatment_phase3": _direct_arm_comparison(cascade_al),
        }
    confirm_disconfirm["pooled"] = {
        "control_drop": _paired_drop(pooled_phase3_anchor_level, pooled_baseline_anchor_level, "control"),
        "treatment_drop": _paired_drop(pooled_phase3_anchor_level, pooled_baseline_anchor_level, "treatment"),
        "direct_control_vs_treatment_phase3": _direct_arm_comparison(pooled_phase3_anchor_level),
    }
    # NOTE: no "whole_chain_composite" control_drop/treatment_drop entry is
    # computed here deliberately -- section 3's fresh isolated baseline is
    # defined PER FAMILY (one K=1 trial per family, at that family's own
    # anchor), so there is no single matching baseline for the whole-chain,
    # all-5-families-at-once composite outcome. Only the per-family and
    # pooled-across-families (family x anchor-set) drops below have a
    # well-defined baseline to compare against; the whole-chain composite is
    # reported on its own (outcome measure "a_phase3_composite_pass_rate"
    # above) without a drop-vs-baseline number, rather than faking one
    # against a baseline that does not actually match its scope.
    confirm_disconfirm["keep_survival_significance"] = keep_survival_direct_comparison

    return {
        "schema": "paper-s23-respec-cascade-statistics-v1",
        "rotation_order": FAMILIES,
        "seed": _SEED,
        "n_resamples": _RESAMPLES,
        "outcome_measures": {
            "a_phase3_composite_pass_rate": phase3_composite_tiers,
            "a_phase3_pass_rate_per_family": per_family_phase3_tiers,
            "a_phase3_pass_rate_pooled": pooled_phase3_tiers,
            "b_phase2_keep_survival_pass_rate": phase2_keep_survival_tiers,
            "c_fresh_isolated_k1_baseline_pass_rate_per_family": baseline_tiers,
        },
        "confirm_disconfirm": confirm_disconfirm,
        "render_gate_timeouts": render_gate_timeouts,
        "excluded_observations": excluded_observations,
        "n_cascade_chains_loaded": len(cascade_chains),
        "n_baseline_chains_loaded": {family: len(chains) for family, chains in baseline_chains.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--baseline-run-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    cascade_chains = load_respec_cascade_chains(args.run_root)
    baseline_chains = load_baseline_chains(args.baseline_run_root)

    report = compute_respec_cascade_tiers(cascade_chains, baseline_chains)
    report["run_root"] = str(args.run_root)
    report["baseline_run_root"] = str(args.baseline_run_root)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    # Section 7's three primary numbers, explicit and clearly labeled per the
    # protocol's own requirement -- never left implicit in the larger dict above.
    pooled = report["confirm_disconfirm"]["pooled"]
    print("\n=== PAPER-S23 section 7 primary numbers (pooled across families) ===")
    print(f"control_drop   (cascade Phase-3 vs control's own fresh K=1 baseline):   {pooled['control_drop']}")
    print(f"treatment_drop (cascade Phase-3 vs treatment's own fresh K=1 baseline): {pooled['treatment_drop']}")
    print(f"direct control-vs-treatment (cascade Phase-3 composite pass rate):      {pooled['direct_control_vs_treatment_phase3']}")
    print(f"keep_survival_significance (Checkpoint B, control vs treatment):        {report['confirm_disconfirm']['keep_survival_significance']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
