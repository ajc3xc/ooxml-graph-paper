"""PAPER-S23 (`docs/paper-s23-respec-cascade-protocol-v0.md`, locked 2026-09-20,
five-family contingency per section 1.2a / 2.3): Tier 1/2/3 aggregation for
`respec_cascade` chain results.

Rotation `R' = [bibliography, citation, section_reorder, equation, caption]`
(`table_structural` dropped because `insert_table`/`remove_table` were missing
from the `meridian-docs` tool manifest checked at corpus-build time, section
1.2a item 2 -- that manifest later turned out to be a stale, separately
installed build of the server; the harness's own server exposes both tools).

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

2026-09-25 corrections (independent audit of the 2026-09-23 run):
  - Frozen chains. The as-run code EXCLUDED a chain that froze from the
    per-family Phase-3 and keep-survival measures. `--frozen-chain-mode fail`
    (default) scores it 0 at every checkpoint it did not reach;
    `--frozen-chain-mode exclude` reproduces the stored statistics. The mode
    used is written to the output. `fail` is one interpretation, not the
    protocol's literal rule: protocol section 4 defines a freeze only for a
    package-validity failure, so `fail` is exact only for a package-invalid
    freeze. The orchestrator also freezes when it cannot re-resolve its own
    anchor marker, and a family the chain never ran has no outcome at all; for
    both, the 0 is an imputation (see FROZEN_CHAIN_MODES).
  - Additional tests. Each section-7 entry now also carries `chain_level` (an
    exact cluster sign-flip test in which all observations of one
    (document, anchor-set) chain flip together, since the five family
    outcomes of one chain are not independent) and `observation_level_exact`
    (the as-run test with an exact p). The flat as-run fields are unchanged in
    meaning. Tier 1 gains `paired_significance_exact`. These tests, and the
    whole-chain composite direct comparison, were chosen after the
    2026-09-23 results were known: for that run they are post hoc (output
    `analysis_status`), not the test protocol section 7 names. They can be
    primary only for a run whose protocol names them before any data exists
    (the S25 re-run protocol).

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
                             Since 2026-09-25 a frozen chain also carries
                             freeze_cause ("package_invalid" |
                             "anchor_reresolution_failed" | "other"),
                             freeze_detail and frozen_at_step; the same
                             status string is written for every cause.
    phase1_result         -- None (chain froze before Phase 1 finished) or
                             {"phase1_pass": bool, "families": {family:
                             {"verdict": "pass"|..., ...}, ...}, ...}
    phase2_result          -- None (froze before/during Phase 2) or
                             {"phase2_pass": bool, "citation_absent": bool,
                              "section_at_d2": bool, "keep_survival":
                              {"overall_status": "clean_keep_survival"|...,
                               ...}, ...}
    phase3_result          -- None (froze before Phase 3; before 2026-09-25
                             also on a Phase-3 freeze) or
                             {"phase3_pass": bool, "families": {family:
                              {"verdict": "pass"|..., ...}, ...},
                              "final_structure_match": bool, ...}. On a
                             Phase-3 freeze since 2026-09-25:
                             {"status": "frozen_before_checkpoint_c",
                              "phase3_pass": False, "families": {finished
                              round trips' own verdicts, the rest
                              "not_completed"/"not_run"}} -- diagnostics,
                             never read as Checkpoint-C outcomes.

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
        --out D:/MeridianData/ooxml-graph-paper/runs/paper-s23-respec-cascade/statistics.json \
        [--frozen-chain-mode fail|exclude] [--six-family]
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
from compute_s7_statistics import (  # noqa: E402 -- reused UNMODIFIED for baseline pass/fail
    BLOCKED_POLICIES,
    DEFAULT_BLOCKED_POLICY,
    _chain_outcome,
    _check_blocked_policy,
)
from graph_scorer import (  # noqa: E402 -- reused UNMODIFIED
    bootstrap_ci,
    cluster_paired_sign_flip_test,
    paired_permutation_test,
    paired_permutation_test_exact,
)

# Five-family contingency rotation R' (protocol section 2.3 / 1.2a item 2).
# `table_structural` is NOT in this list -- see module docstring. The
# six-family rotation R (protocol section 2.2) is SIX_FAMILIES, selected
# explicitly with --families; five-family results are never merged with it.
FAMILIES: list[str] = ["bibliography", "citation", "section_reorder", "equation", "caption"]
SIX_FAMILIES: list[str] = ["bibliography", "citation", "section_reorder", "equation", "table_structural", "caption"]

# Statuses excluded from every outcome measure's denominator (None, not a
# fabricated 0) -- mirrors compute_s7_statistics._chain_outcome's own
# exclusion set, PLUS "render_gate_timeout", which protocol section 7's
# render-gate/host-contention control requires be reported separately and
# never folded into control_drop/treatment_drop.
#
# 2026-09-26 fix (M1): "infra_blocked", "infra_excluded" and
# "aborted_circuit_open" were missing here. Without them, a chain still
# infra_blocked (or exhausted to infra_excluded, or stopped by the sweep-wide
# circuit breaker) had phase1_result/phase2_result/phase3_result == None but
# was NOT in this set, so _phase3_composite_outcome fell through to its
# "froze or missing phase result" branch and scored it a hard 0.0 -- an
# infrastructure non-outcome counted as an observed task failure. Probed
# directly against all three outcome functions before this fix (see
# tests/test_compute_respec_cascade_statistics.py); each of these three
# statuses must be None (excluded), never 0.0, from every measure.
_EXCLUDED_STATUSES = frozenset({
    "not_applicable", "harness_exception", "blocked", "render_gate_timeout",
    "infra_blocked", "infra_excluded", "aborted_circuit_open",
})

# How a chain that froze at a package-validity gate or a marker re-resolution
# (status "chain_broken_at_step_*") enters the per-family Phase-3 measure and
# the Phase-2 keep-survival measure:
#   "fail"    -- a chain that froze passes no checkpoint it did not reach; it
#                scores 0.0 there. Default for every new run. Exact only for
#                a package-invalid freeze, the one freeze protocol section 4
#                defines (composite PASS needs every package-validity gate).
#                For a freeze on a failed anchor/marker re-resolution (the
#                harness not finding its own marker in the arm's output;
#                protocol section 4 does not define it as a freeze) and for
#                every family the chain never ran, the 0 is an imputation,
#                not an observed outcome. The orchestrator records
#                `freeze_cause` since 2026-09-25; chains from the 2026-09-23
#                run carry none (all 5 of its control freezes were at steps
#                with a re-resolution check, cause unknown).
#   "exclude" -- the as-run behavior of the 2026-09-23 primary sweep: a
#                frozen chain has no outcome for a checkpoint it did not reach
#                and drops out of that measure's denominator. Kept so
#                paper/sources/respec-cascade-statistics.json stays
#                reproducible.
# The whole-chain composite (measure a) scores a frozen chain 0.0 in both
# modes, as it always has. A checkpoint the chain DID reach before freezing
# (e.g. Checkpoint B for a chain that froze in Phase 3) keeps its real
# graded outcome in both modes.
#   "fail_graded_prefreeze" -- S25 protocol section 5.2's PRIMARY scoring
#                (prerequisite P-R1). Per family: a round trip that finished
#                grading before the freeze keeps that real verdict (pass/fail);
#                a family not reached (in progress when it froze, or later in
#                the rotation) scores 0, same as "fail". Keep-survival and the
#                whole-chain composite score exactly as "fail" (keep-survival
#                has no partial-credit notion below Checkpoint B; the
#                composite fails on any freeze regardless of mode).
#   "package_invalid_only" -- a sensitivity split of "fail_graded_prefreeze"
#                by freeze_cause (S25 section 6.8 item 4): a freeze whose
#                freeze_cause is "package_invalid" (protocol section 4's one
#                defined freeze) is scored exactly as "fail_graded_prefreeze";
#                any other cause (anchor/marker re-resolution, "other", or
#                "not_recorded" on a pre-2026-09-25 chain) is EXCLUDED
#                (None) from every checkpoint that chain did not reach,
#                instead of imputed.
FROZEN_CHAIN_MODES: tuple[str, ...] = ("fail", "exclude", "fail_graded_prefreeze", "package_invalid_only")
DEFAULT_FROZEN_CHAIN_MODE = "fail"
FROZEN_CHAIN_MODE_NOTES: dict[str, str] = {
    "fail": (
        "A frozen chain scores 0 at every checkpoint it did not reach. Exact only for a package-invalid "
        "freeze (protocol section 4); for an anchor/marker re-resolution freeze and for families the chain "
        "never ran, the 0 is an imputation. See frozen_chains[*].freeze_cause."
    ),
    "exclude": (
        "A frozen chain drops out of every measure whose checkpoint it did not reach (the as-run scoring "
        "of the 2026-09-23 sweep)."
    ),
    "fail_graded_prefreeze": (
        "S25 protocol section 5.2's primary scoring. Per family, a Phase-3 round trip already graded "
        "before the freeze keeps its real verdict; a family not reached scores 0, like 'fail'. "
        "Keep-survival and the whole-chain composite score exactly as 'fail'."
    ),
    "package_invalid_only": (
        "'fail_graded_prefreeze' scoring restricted to freezes with freeze_cause == 'package_invalid' "
        "(protocol section 4's one defined freeze); every other freeze cause is excluded (None) from the "
        "checkpoints it did not reach, rather than imputed (S25 section 6.8 item 4)."
    ),
}

# Tests added on 2026-09-25, after the 2026-09-23 results were known. For that
# run they are post hoc; a later run may call them primary only if its own
# protocol names them before any data exists (S25 does).
POST_HOC_LABEL = "post_hoc_for_2026-09-23_run"
ANALYSIS_STATUS: dict[str, str] = {
    "confirm_disconfirm.*.chain_level": POST_HOC_LABEL,
    "confirm_disconfirm.*.observation_level_exact": POST_HOC_LABEL,
    "confirm_disconfirm.whole_chain_composite_direct": POST_HOC_LABEL,
    "confirm_disconfirm.keep_survival_significance_chain_level": POST_HOC_LABEL,
    "confirm_disconfirm.keep_survival_significance_observation_level_exact": POST_HOC_LABEL,
    "outcome_measures.*.tier1_per_document_unweighted.paired_significance_exact": POST_HOC_LABEL,
    "frozen_chain_mode=fail": POST_HOC_LABEL,
}


def _is_frozen(chain: dict[str, Any]) -> bool:
    return str(chain.get("status") or "").startswith("chain_broken_at_step_")


def _check_frozen_chain_mode(frozen_chain_mode: str) -> None:
    if frozen_chain_mode not in FROZEN_CHAIN_MODES:
        raise ValueError(f"frozen_chain_mode must be one of {FROZEN_CHAIN_MODES}, got {frozen_chain_mode!r}")


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
    if _is_frozen(chain) or phase1 is None or phase2 is None or phase3 is None:
        # The chain froze at a package-validity gate before all three
        # phases completed (`run_respec_cascade_chain`'s own `_freeze`
        # leaves every not-yet-reached phase's result as `None`) -- scored
        # 0.0, not excluded: the composite requires all three phases to
        # have genuinely passed, and a mid-chain freeze is itself a real
        # structural finding about that arm's output, per protocol section
        # 4/7, not an absence of information. `_is_frozen` covers chains from
        # the current orchestrator, whose `phase3_result` on a Phase-3 freeze
        # holds the verdicts of the round trips that finished before it.
        return 0.0
    a, b, c = phase1.get("phase1_pass"), phase2.get("phase2_pass"), phase3.get("phase3_pass")
    if a is None or b is None or c is None:
        return None
    return 1.0 if (a and b and c) else 0.0


def _frozen_not_reached_outcome(chain: dict[str, Any], frozen_chain_mode: str) -> float | None:
    """0.0 or None for a measure this frozen chain never reached at all
    (never graded before or during the freeze), depending on
    frozen_chain_mode: "fail"/"fail_graded_prefreeze" impute 0.0; "exclude"
    always excludes (None); "package_invalid_only" imputes 0.0 only when this
    chain's freeze_cause is "package_invalid" (the one freeze protocol
    section 4 defines), else excludes -- see FROZEN_CHAIN_MODES."""
    if frozen_chain_mode == "exclude":
        return None
    if frozen_chain_mode == "package_invalid_only":
        return 0.0 if chain.get("freeze_cause") == "package_invalid" else None
    return 0.0  # "fail", "fail_graded_prefreeze"


def _phase3_family_outcome(
    chain: dict[str, Any], family: str, frozen_chain_mode: str = DEFAULT_FROZEN_CHAIN_MODE,
) -> float | None:
    """Outcome measure (a), per-family: this family's own Phase-3
    forward+inverse pass/fail, section 7's primary per-family comparison
    unit. Reads `phase3_result["families"][family]["verdict"] == "pass"`
    (the real per-family grader dicts `_grade_family_inverse` returns, each
    carrying a `"verdict"` key -- the same convention
    `grade_phase1_build`/`grade_phase3_second_exposure` themselves check via
    `r.get("verdict") == "pass"`), NOT `checkpoint_c["per_family"][family]
    ["pass"]`, which never matches anything the real evaluator produces.

    A frozen chain never reached Checkpoint C, so it has no Checkpoint-C
    verdict for any family: 0.0 under frozen_chain_mode="fail", None under
    "exclude" (see FROZEN_CHAIN_MODES). Verdicts the orchestrator recorded
    for round trips that finished before a Phase-3 freeze are diagnostics
    (reported under `frozen_chains`), not Checkpoint-C outcomes -- EXCEPT
    under "fail_graded_prefreeze" (S25 section 5.2's primary scoring) and,
    when this chain's freeze_cause is "package_invalid", under
    "package_invalid_only": both then use that pre-freeze verdict as this
    family's real outcome, exactly like a chain that did not freeze at all,
    falling back to _frozen_not_reached_outcome (0.0/None) only for a family
    the chain never reached (in progress when it froze, or later in the
    rotation)."""
    _check_frozen_chain_mode(frozen_chain_mode)
    status = chain.get("status")
    if status in _EXCLUDED_STATUSES:
        return None
    if _is_frozen(chain):
        use_graded_prefreeze = frozen_chain_mode == "fail_graded_prefreeze" or (
            frozen_chain_mode == "package_invalid_only" and chain.get("freeze_cause") == "package_invalid"
        )
        if use_graded_prefreeze:
            phase3 = chain.get("phase3_result")
            fam = ((phase3 or {}).get("families") or {}).get(family) or {}
            verdict = fam.get("verdict")
            if verdict is not None:
                return 1.0 if verdict == "pass" else 0.0
            # Not graded before the freeze (not_completed/not_run, or no
            # phase3_result at all): never reached.
            return _frozen_not_reached_outcome(chain, frozen_chain_mode)
        return _frozen_not_reached_outcome(chain, frozen_chain_mode)
    phase3 = chain.get("phase3_result")
    if phase3 is None:
        # No Phase-3 result on a chain that did not freeze: nothing graded.
        return None
    families = phase3.get("families") or {}
    fam = families.get(family)
    if fam is None:
        return None
    verdict = fam.get("verdict")
    if verdict is None:
        return None
    return 1.0 if verdict == "pass" else 0.0


def _phase2_keep_survival_outcome(
    chain: dict[str, Any], frozen_chain_mode: str = DEFAULT_FROZEN_CHAIN_MODE,
) -> float | None:
    """Outcome measure (b): `score_keep_survival`'s own pass/fail at
    Checkpoint B (protocol section 4, Checkpoint B item 3) -- distinct from
    Checkpoint B's FULL pass (which also folds in citation-absence,
    section-at-D2, and the zero-unintended-diff check). Reads
    `phase2_result["keep_survival"]["overall_status"] == "clean_keep_survival"`
    (a status STRING, per `graph_scorer.score_keep_survival`'s real return
    shape), NOT `checkpoint_b["keep_survival"]["pass"]` (a boolean that
    field never had).

    A chain that froze before Checkpoint B (no `phase2_result`) scores 0.0
    under frozen_chain_mode="fail"/"fail_graded_prefreeze" (there is no
    partial-credit notion below Checkpoint B, so "fail_graded_prefreeze"
    scores exactly as "fail" here), is excluded under "exclude", and under
    "package_invalid_only" follows freeze_cause via _frozen_not_reached_outcome;
    a chain that froze later keeps its real Checkpoint-B outcome in every mode."""
    _check_frozen_chain_mode(frozen_chain_mode)
    status = chain.get("status")
    if status in _EXCLUDED_STATUSES:
        return None
    phase2 = chain.get("phase2_result")
    if phase2 is None:
        if _is_frozen(chain):
            return _frozen_not_reached_outcome(chain, frozen_chain_mode)
        return None
    keep_survival = phase2.get("keep_survival") or {}
    overall_status = keep_survival.get("overall_status")
    if overall_status is None:
        return None
    return 1.0 if overall_status == "clean_keep_survival" else 0.0


def _baseline_outcome(chain: dict[str, Any], blocked_policy: str = DEFAULT_BLOCKED_POLICY) -> float | None:
    """Outcome measure (c): reuses `compute_s7_statistics._chain_outcome`
    UNMODIFIED -- baseline chains are exactly `run_chain`'s own K=1
    checkpoint format, so its already-validated pass/fail rule applies as-is.

    2026-09-26 fix (M2/P-R1): `blocked_policy` was previously never threaded
    through, so `_chain_outcome` always ran with its default ("exclude") no
    matter what a caller wanted -- a `blocked_*` baseline chain (a K=1 trial
    that timed out, failed to exit cleanly, or hit an unreadable/unresolvable
    input) silently dropped out of the baseline denominator instead of
    scoring 0 under `--blocked-policy fail`, the S25 protocol's locked
    default for baselines (section 5.6)."""
    return _chain_outcome(chain, blocked_policy=blocked_policy)


# ---------------------------------------------------------------------------
# Grouping: arm -> original_doc_label -> [outcome, ...], with exclusions
# recorded (never silently dropped, per section 6).
# ---------------------------------------------------------------------------

def _exclusion_reason(chain: dict[str, Any]) -> str:
    """Why a chain has no outcome for a measure. A phase grader that raised
    leaves a `_safe_call` stub ({"status": "grading_raised_exception"}) and makes
    the orchestrator mark the whole chain `completed_with_failure`, so the chain
    status alone would misreport a grader crash as a task failure."""
    for phase in ("phase1_result", "phase2_result", "phase3_result"):
        result = chain.get(phase)
        if isinstance(result, dict) and result.get("status") == "grading_raised_exception":
            return f"{phase.split('_')[0]}_grading_raised_exception: {result.get('reason', '')}".rstrip(": ")
    return chain.get("status") or "outcome_unavailable"


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
                "reason": _exclusion_reason(chain),
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

def _tiered_report(
    control_by_doc: dict[str, list[float]], treatment_by_doc: dict[str, list[float]], *, exact_tests: bool = False,
) -> dict[str, Any]:
    """`exact_tests=True` adds Tier 1's `paired_significance_exact` (exact
    sign-flip enumeration over the paired documents; with 3 documents no p
    below 0.25 is possible, which the Monte Carlo `paired_significance` can
    undershoot). Off by default so other callers' output is unchanged."""
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
    if exact_tests:
        tier1["paired_significance_exact"] = (
            paired_permutation_test_exact([control_means[d] for d in paired_docs],
                                          [treatment_means[d] for d in paired_docs])
            if len(paired_docs) >= 2 else None
        )

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
# Section 7, additional tests (post hoc for the 2026-09-23 run, see
# ANALYSIS_STATUS). The flat `control_drop`/`treatment_drop`/
# `direct_control_vs_treatment_phase3`/`keep_survival_significance` fields
# above are the as-run observation-level Monte Carlo paired_permutation_test
# and keep that meaning. Pooled across families they treat the five family
# outcomes of ONE chain as five independent pairs, which they are not. The
# chain-level test below flips all observations of one (document,
# anchor-set) chain together, and the exact observation-level test is the
# same test as the flat fields with an exact p-value.
# ---------------------------------------------------------------------------

def _chain_of(key: str) -> str:
    """(document, anchor-set) chain a section-7 observation key belongs to:
    per-family keys are the doc_label itself, pooled keys are
    "family::doc_label" (see _pool_across_families)."""
    return key.split("::", 1)[-1]


def _strip_anchor_suffix(doc_or_chain_label: str) -> str:
    """"<original_doc_label>__anchor<N>" -> "<original_doc_label>", the same
    convention _original_doc_label reads directly off a chain dict (see its
    docstring); unchanged if there is no "__anchor" suffix to strip."""
    return doc_or_chain_label.rsplit("__anchor", 1)[0] if "__anchor" in doc_or_chain_label else doc_or_chain_label


def _document_of(key: str) -> str:
    """Original document a section-7 observation key belongs to (P-R4,
    protocol section 6.3's document-level cluster: every anchor-set AND every
    family of one document pools into one cluster) -- the (document,
    anchor-set) chain from `_chain_of`, with its anchor-set suffix stripped."""
    return _strip_anchor_suffix(_chain_of(key))


def _section7_tests(a_by_key: dict[str, float], b_by_key: dict[str, float], label: str) -> dict[str, Any]:
    common = sorted(set(a_by_key) & set(b_by_key))
    a_values = [a_by_key[k] for k in common]
    b_values = [b_by_key[k] for k in common]
    chain_level = cluster_paired_sign_flip_test([_chain_of(k) for k in common], a_values, b_values)
    chain_level["method"] = f"{chain_level.get('method', 'cluster-level paired sign-flip test')}: {label}, clustered by (document, anchor-set) chain"
    document_level = cluster_paired_sign_flip_test([_document_of(k) for k in common], a_values, b_values)
    document_level["method"] = f"{document_level.get('method', 'cluster-level paired sign-flip test')}: {label}, clustered by original document (P-R4, protocol section 6.3)"
    observation_exact = paired_permutation_test_exact(a_values, b_values)
    observation_exact["method"] = f"{observation_exact.get('method', 'paired sign-flip permutation test')}: {label}, every observation its own unit"
    for result in (chain_level, document_level, observation_exact):
        result["n_paired_observations"] = len(common)
        result["matched_observations"] = common
    return {"chain_level": chain_level, "document_level": document_level, "observation_level_exact": observation_exact}


def _section7_primary_tests(
    cascade_by_arm_doc: dict[str, dict[str, float]],
    baseline_by_arm_doc: dict[str, dict[str, float]] | None,
) -> dict[str, dict[str, Any]]:
    """{"chain_level": {...}, "observation_level_exact": {...}}, each holding
    control_drop / treatment_drop / direct_control_vs_treatment_phase3 with
    the same pairing as `_paired_drop`/`_direct_arm_comparison`. With
    `baseline_by_arm_doc=None` only the direct comparison is computed (used
    for keep-survival, which has no baseline)."""
    out: dict[str, dict[str, Any]] = {"chain_level": {}, "document_level": {}, "observation_level_exact": {}}
    tests: dict[str, dict[str, Any]] = {}
    if baseline_by_arm_doc is not None:
        for arm in ("control", "treatment"):
            tests[f"{arm}_drop"] = _section7_tests(
                cascade_by_arm_doc.get(arm, {}), baseline_by_arm_doc.get(arm, {}),
                f"{arm} cascade Phase-3 outcome vs {arm} fresh isolated K=1 baseline outcome",
            )
    tests["direct_control_vs_treatment_phase3"] = _section7_tests(
        cascade_by_arm_doc.get("control", {}), cascade_by_arm_doc.get("treatment", {}),
        "control vs treatment cascade outcome",
    )
    return _flatten_section7_tests(out, tests)


def _flatten_section7_tests(out: dict[str, dict[str, Any]], tests: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    for name, result in tests.items():
        for level in out:
            out[level][name] = result[level]
    return out


def _difference_in_drops(
    cascade_by_family_arm_doc: dict[str, dict[str, dict[str, float]]],
    baseline_by_family_arm_doc: dict[str, dict[str, dict[str, float]]],
    families: list[str],
    *, doc_filter: set[str] | None = None,
) -> dict[str, Any]:
    """P-R4, protocol section 6.6 (the cascade-specific claim): for every
    matched (document, anchor-set, family) with a control Phase-3, control
    baseline, treatment Phase-3 and treatment baseline observation,
    d = (control_baseline - control_phase3) - (treatment_baseline -
    treatment_phase3), d in {-2..2} for 0/1 outcomes -- positive means
    control dropped more than treatment. Tested against a null of zero via
    cluster_paired_sign_flip_test(d, 0*d), at chain level (cluster =
    (document, anchor-set)) and document level (cluster = original
    document). `drop_difference_pp = 100 * mean(d)`, matching protocol
    section 6.1's `drop_difference_pp = control_drop_pp - treatment_drop_pp`
    exactly (same per-unit quantity, opposite of the two drops' own A-B sign
    convention cancels out). Observations missing any of the four values are
    left out of the test and counted. `doc_filter`, when given, restricts to
    doc_labels whose original document is in the set (section 6.7)."""
    d_by_key: dict[str, float] = {}
    n_candidates = 0
    n_missing = 0
    for family in families:
        cascade_f = cascade_by_family_arm_doc.get(family, {})
        baseline_f = baseline_by_family_arm_doc.get(family, {})
        control_cascade = cascade_f.get("control", {})
        control_baseline = baseline_f.get("control", {})
        treatment_cascade = cascade_f.get("treatment", {})
        treatment_baseline = baseline_f.get("treatment", {})
        doc_labels = set(control_cascade) | set(control_baseline) | set(treatment_cascade) | set(treatment_baseline)
        for doc_label in doc_labels:
            if doc_filter is not None and _strip_anchor_suffix(doc_label) not in doc_filter:
                continue
            n_candidates += 1
            if (doc_label not in control_cascade or doc_label not in control_baseline
                    or doc_label not in treatment_cascade or doc_label not in treatment_baseline):
                n_missing += 1
                continue
            d = (control_baseline[doc_label] - control_cascade[doc_label]) - (treatment_baseline[doc_label] - treatment_cascade[doc_label])
            d_by_key[f"{family}::{doc_label}"] = d

    keys = sorted(d_by_key)
    d_values = [d_by_key[k] for k in keys]
    zeros = [0.0] * len(d_values)
    chain_level = cluster_paired_sign_flip_test([_chain_of(k) for k in keys], d_values, zeros)
    chain_level["method"] = "cluster-level paired sign-flip test: difference-in-drops d vs 0, clustered by (document, anchor-set) chain"
    document_level = cluster_paired_sign_flip_test([_document_of(k) for k in keys], d_values, zeros)
    document_level["method"] = "cluster-level paired sign-flip test: difference-in-drops d vs 0, clustered by original document (P-R4)"
    for result in (chain_level, document_level):
        result["n_paired_observations"] = len(keys)
        result["matched_observations"] = keys
    return {
        "chain_level": chain_level,
        "document_level": document_level,
        "drop_difference_pp": 100.0 * (sum(d_values) / len(d_values)) if d_values else None,
        "n_candidates": n_candidates,
        "n_missing_any_of_four_values": n_missing,
    }


def _filter_to_documents(by_arm_doc: dict[str, dict[str, float]], allowed_documents: set[str]) -> dict[str, dict[str, float]]:
    """Restrict a {arm: {key: value}} anchor-level dict to keys whose
    original document is in `allowed_documents` (protocol section 6.7's
    public-documents-only subset, P-R4)."""
    return {
        arm: {k: v for k, v in by_doc.items() if _document_of(k) in allowed_documents}
        for arm, by_doc in by_arm_doc.items()
    }


def _per_document_breakdown(
    pooled_phase3_anchor_level: dict[str, dict[str, float]],
    pooled_baseline_anchor_level: dict[str, dict[str, float]],
    phase2_keep_survival_anchor_level: dict[str, dict[str, float]],
    per_family_phase3_anchor_level: dict[str, dict[str, dict[str, float]]],
    baseline_anchor_level: dict[str, dict[str, dict[str, float]]],
    families: list[str],
) -> dict[str, Any]:
    """Exploratory (protocol section 8: no verdict weight, not part of the
    section 7 decision rule): P1 (control_drop), P2 (treatment_drop), P3
    (direct), P4 (keep_survival) and the difference-in-drops test, ONE
    DOCUMENT AT A TIME instead of pooled across all D documents -- lets a
    reader see whether a pooled effect is broad-based or driven by a subset
    of documents. Chain-level only (cluster = anchor-set): restricted to a
    single document, there is nothing left to cluster further at the
    document level (see docs/paper-s25-respec-cascade-rerun-protocol-v1.md
    section 6.7 for the analogous, protocol-named public-documents-only
    slice this generalizes; found live, 2026-09-27, when the single public
    document in the D=4 rerun showed a null effect while the pooled result,
    driven by the 3 author-owned documents, was strongly significant)."""
    all_documents = sorted({
        _document_of(k) for k in (
            list(pooled_phase3_anchor_level.get("control", {}))
            + list(pooled_phase3_anchor_level.get("treatment", {}))
        )
    })
    out: dict[str, Any] = {}
    for doc in all_documents:
        doc_filter = {doc}
        doc_phase3 = _filter_to_documents(pooled_phase3_anchor_level, doc_filter)
        doc_baseline = _filter_to_documents(pooled_baseline_anchor_level, doc_filter)
        doc_keep_survival = _filter_to_documents(phase2_keep_survival_anchor_level, doc_filter)
        out[doc] = {
            "control_drop": _paired_drop(doc_phase3, doc_baseline, "control"),
            "treatment_drop": _paired_drop(doc_phase3, doc_baseline, "treatment"),
            "direct_control_vs_treatment_phase3": _direct_arm_comparison(doc_phase3),
            "keep_survival_significance": _direct_arm_comparison(doc_keep_survival),
            "difference_in_drops": _difference_in_drops(
                per_family_phase3_anchor_level, baseline_anchor_level, families, doc_filter=doc_filter,
            ),
        }
    return out


def _frozen_chain_disclosure(cascade_chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every frozen chain with where and why it froze (`freeze_cause`, only
    recorded by the orchestrator since 2026-09-25 -- "not_recorded" for older
    chains) and the verdicts of any Phase-3 round trips that finished before
    the freeze. Diagnostic only: under either frozen_chain_mode these
    verdicts are not Checkpoint-C outcomes."""
    out: list[dict[str, Any]] = []
    for chain in cascade_chains:
        if not _is_frozen(chain):
            continue
        phase3 = chain.get("phase3_result") or {}
        families = phase3.get("families") or {}
        out.append({
            "doc_label": chain.get("doc_label"), "arm": chain.get("arm"), "status": chain.get("status"),
            "freeze_cause": chain.get("freeze_cause", "not_recorded"),
            "freeze_detail": chain.get("freeze_detail", chain.get("reason")),
            "phase3_verdicts_before_freeze": {
                family: (result or {}).get("verdict", (result or {}).get("status")) for family, result in families.items()
            },
        })
    return out


# ---------------------------------------------------------------------------
# Top-level aggregation
# ---------------------------------------------------------------------------

def compute_respec_cascade_tiers(
    cascade_chains: list[dict[str, Any]],
    baseline_chains: dict[str, list[dict[str, Any]]],
    *,
    frozen_chain_mode: str = DEFAULT_FROZEN_CHAIN_MODE,
    families: list[str] | None = None,
    blocked_policy: str = DEFAULT_BLOCKED_POLICY,
    public_doc_labels: set[str] | None = None,
) -> dict[str, Any]:
    """`frozen_chain_mode`: see FROZEN_CHAIN_MODES ("exclude" reproduces the
    stored 2026-09-23 statistics; "fail" scores a frozen chain 0 at every
    checkpoint it did not reach, exact only for package-invalid freezes;
    "fail_graded_prefreeze" and "package_invalid_only" are the S25 protocol's
    primary and per-cause-sensitivity modes, section 5.2).
    `families`: the rotation to aggregate, FAMILIES (default, five-family
    contingency) or SIX_FAMILIES.
    `blocked_policy`: passed through to `_baseline_outcome` /
    `compute_s7_statistics._chain_outcome` for the fresh isolated K=1
    baselines (compute_s7_statistics.BLOCKED_POLICIES; "exclude" default
    reproduces the stored 2026-09-23 statistics, "fail" is the S25 locked
    command's choice for baselines, section 5.6/6.8 item 8).

    Raises ValueError if a family in `families` has no baseline chain: its
    per-family drops would be empty and the pooled drops would silently leave
    out every one of its observations while the direct comparison kept them."""
    _check_frozen_chain_mode(frozen_chain_mode)
    _check_blocked_policy(blocked_policy)
    families = list(families) if families is not None else list(FAMILIES)
    no_baseline = [family for family in families if not baseline_chains.get(family)]
    if no_baseline:
        raise ValueError(
            f"no fresh isolated K=1 baseline chains for {no_baseline}: control_drop/treatment_drop would silently "
            "drop these families' observations. Run the baselines for every family in the rotation."
        )
    excluded_observations: list[dict[str, Any]] = []
    render_gate_timeouts: list[dict[str, Any]] = [
        {"doc_label": c.get("doc_label"), "arm": c.get("arm"), "chain_broken_at_step": c.get("chain_broken_at_step")}
        for c in cascade_chains if c.get("status") == "render_gate_timeout"
    ]

    def _keep_survival(chain: dict[str, Any]) -> float | None:
        return _phase2_keep_survival_outcome(chain, frozen_chain_mode)

    # ---- (a) Phase 3 composite pass rate, per arm -- whole-chain.
    composite_grouped, composite_excluded = _group_by_document(cascade_chains, _phase3_composite_outcome, "phase3_composite")
    excluded_observations.extend(composite_excluded)
    phase3_composite_tiers = _tiered_report(composite_grouped["control"], composite_grouped["treatment"], exact_tests=True)
    phase3_composite_anchor_level = _anchor_level_values(cascade_chains, _phase3_composite_outcome)

    # ---- (a) Phase 3 pass rate, per family.
    per_family_phase3_tiers: dict[str, Any] = {}
    per_family_phase3_anchor_level: dict[str, dict[str, dict[str, float]]] = {}
    for family in families:
        def _fn(chain: dict[str, Any], family: str = family) -> float | None:
            return _phase3_family_outcome(chain, family, frozen_chain_mode)
        grouped, excluded = _group_by_document(cascade_chains, _fn, f"phase3_{family}")
        excluded_observations.extend(excluded)
        per_family_phase3_tiers[family] = _tiered_report(grouped["control"], grouped["treatment"], exact_tests=True)
        per_family_phase3_anchor_level[family] = _anchor_level_values(cascade_chains, _fn)

    # ---- (a) pooled across families (family x anchor-set as the observation unit).
    pooled_phase3_grouped: dict[str, dict[str, list[float]]] = {"control": {}, "treatment": {}}
    for family in families:
        def _fn2(chain: dict[str, Any], family: str = family) -> float | None:
            return _phase3_family_outcome(chain, family, frozen_chain_mode)
        grouped, _excl = _group_by_document(cascade_chains, _fn2, f"phase3_{family}_pooled")
        for arm in ("control", "treatment"):
            for doc, vs in grouped[arm].items():
                pooled_phase3_grouped[arm].setdefault(doc, []).extend(vs)
    pooled_phase3_tiers = _tiered_report(pooled_phase3_grouped["control"], pooled_phase3_grouped["treatment"], exact_tests=True)
    pooled_phase3_anchor_level = _pool_across_families(per_family_phase3_anchor_level)

    # ---- (b) Phase 2 keep-survival pass rate (chain-level, one bool per anchor-set).
    ks_grouped, ks_excluded = _group_by_document(cascade_chains, _keep_survival, "phase2_keep_survival")
    excluded_observations.extend(ks_excluded)
    phase2_keep_survival_tiers = _tiered_report(ks_grouped["control"], ks_grouped["treatment"], exact_tests=True)
    phase2_keep_survival_anchor_level = _anchor_level_values(cascade_chains, _keep_survival)
    keep_survival_direct_comparison = _direct_arm_comparison(phase2_keep_survival_anchor_level)

    # ---- (c) fresh isolated K=1 baseline pass rate, per arm, per family.
    baseline_tiers: dict[str, Any] = {}
    baseline_anchor_level: dict[str, dict[str, dict[str, float]]] = {}
    pooled_baseline_grouped: dict[str, dict[str, list[float]]] = {"control": {}, "treatment": {}}
    def _baseline_fn(chain: dict[str, Any]) -> float | None:
        return _baseline_outcome(chain, blocked_policy)

    for family in families:
        chains_f = baseline_chains.get(family, [])
        grouped, excluded = _group_by_document(chains_f, _baseline_fn, f"baseline_{family}")
        excluded_observations.extend(excluded)
        baseline_tiers[family] = _tiered_report(grouped["control"], grouped["treatment"], exact_tests=True)
        baseline_anchor_level[family] = _anchor_level_values(chains_f, _baseline_fn)
        for arm in ("control", "treatment"):
            for doc, vs in grouped[arm].items():
                pooled_baseline_grouped[arm].setdefault(doc, []).extend(vs)
    baseline_tiers["pooled"] = _tiered_report(pooled_baseline_grouped["control"], pooled_baseline_grouped["treatment"], exact_tests=True)
    pooled_baseline_anchor_level = _pool_across_families(baseline_anchor_level)

    # ---- Section 7: control_drop / treatment_drop / direct comparison, per family and pooled.
    # The flat fields are the as-run observation-level Monte Carlo tests;
    # `chain_level` and `observation_level_exact` (post hoc for the
    # 2026-09-23 run) sit beside them -- see _section7_primary_tests.
    confirm_disconfirm: dict[str, Any] = {}
    for family in families:
        cascade_al = per_family_phase3_anchor_level[family]
        baseline_al = baseline_anchor_level[family]
        confirm_disconfirm[family] = {
            "control_drop": _paired_drop(cascade_al, baseline_al, "control"),
            "treatment_drop": _paired_drop(cascade_al, baseline_al, "treatment"),
            "direct_control_vs_treatment_phase3": _direct_arm_comparison(cascade_al),
            **_section7_primary_tests(cascade_al, baseline_al),
        }
    confirm_disconfirm["pooled"] = {
        "control_drop": _paired_drop(pooled_phase3_anchor_level, pooled_baseline_anchor_level, "control"),
        "treatment_drop": _paired_drop(pooled_phase3_anchor_level, pooled_baseline_anchor_level, "treatment"),
        "direct_control_vs_treatment_phase3": _direct_arm_comparison(pooled_phase3_anchor_level),
        **_section7_primary_tests(pooled_phase3_anchor_level, pooled_baseline_anchor_level),
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
    # against a baseline that does not actually match its scope. Its direct
    # control-vs-treatment comparison (section 7 names the composite pass
    # rate for that test) needs no baseline and is reported below.
    confirm_disconfirm["whole_chain_composite_direct"] = _section7_primary_tests(phase3_composite_anchor_level, None)
    confirm_disconfirm["keep_survival_significance"] = keep_survival_direct_comparison
    keep_survival_primary = _section7_primary_tests(phase2_keep_survival_anchor_level, None)
    confirm_disconfirm["keep_survival_significance_chain_level"] = keep_survival_primary["chain_level"]["direct_control_vs_treatment_phase3"]
    confirm_disconfirm["keep_survival_significance_document_level"] = keep_survival_primary["document_level"]["direct_control_vs_treatment_phase3"]
    confirm_disconfirm["keep_survival_significance_observation_level_exact"] = (
        keep_survival_primary["observation_level_exact"]["direct_control_vs_treatment_phase3"]
    )

    # ---- P-R4: the difference-in-drops test (section 6.6, the cascade-
    # specific claim -- C4) and the public-documents-only analysis (section
    # 6.7 -- C6), pooled across families.
    confirm_disconfirm["difference_in_drops"] = _difference_in_drops(
        per_family_phase3_anchor_level, baseline_anchor_level, families,
    )
    confirm_disconfirm["per_document"] = _per_document_breakdown(
        pooled_phase3_anchor_level, pooled_baseline_anchor_level, phase2_keep_survival_anchor_level,
        per_family_phase3_anchor_level, baseline_anchor_level, families,
    )
    if public_doc_labels:
        pub_phase3 = _filter_to_documents(pooled_phase3_anchor_level, public_doc_labels)
        pub_baseline = _filter_to_documents(pooled_baseline_anchor_level, public_doc_labels)
        pub_keep_survival = _filter_to_documents(phase2_keep_survival_anchor_level, public_doc_labels)
        pub_primary = _section7_primary_tests(pub_phase3, pub_baseline)
        pub_keep_survival_primary = _section7_primary_tests(pub_keep_survival, None)
        confirm_disconfirm["public_documents_only"] = {
            "note": (
                "protocol section 6.7: P1 (control_drop), P3 (direct), P4 (keep_survival) and the "
                "difference in drops, at chain and document level, over the public documents only. "
                "Condition C6 requires the same sign as the pooled analysis; significance is not required."
            ),
            "public_documents": sorted(public_doc_labels),
            "n_public_documents": len(public_doc_labels),
            "control_drop": _paired_drop(pub_phase3, pub_baseline, "control"),
            "direct_control_vs_treatment_phase3": _direct_arm_comparison(pub_phase3),
            "keep_survival_significance": _direct_arm_comparison(pub_keep_survival),
            "chain_level": {
                "control_drop": pub_primary["chain_level"]["control_drop"],
                "direct_control_vs_treatment_phase3": pub_primary["chain_level"]["direct_control_vs_treatment_phase3"],
                "keep_survival_significance": pub_keep_survival_primary["chain_level"]["direct_control_vs_treatment_phase3"],
            },
            "document_level": {
                "control_drop": pub_primary["document_level"]["control_drop"],
                "direct_control_vs_treatment_phase3": pub_primary["document_level"]["direct_control_vs_treatment_phase3"],
                "keep_survival_significance": pub_keep_survival_primary["document_level"]["direct_control_vs_treatment_phase3"],
            },
            "difference_in_drops": _difference_in_drops(
                per_family_phase3_anchor_level, baseline_anchor_level, families, doc_filter=public_doc_labels,
            ),
        }

    return {
        "schema": "paper-s23-respec-cascade-statistics-v1",
        "rotation_order": families,
        "seed": _SEED,
        "n_resamples": _RESAMPLES,
        "frozen_chain_mode": frozen_chain_mode,
        "frozen_chain_mode_note": FROZEN_CHAIN_MODE_NOTES[frozen_chain_mode],
        "blocked_policy": blocked_policy,
        "section7_tests_note": (
            "chain_level: exact cluster-level paired sign-flip test, every observation of one (document, "
            "anchor-set) chain flips together (each result's `exact` says whether the p-value was enumerated "
            "exactly or, for a null distribution too large to enumerate, estimated by Monte Carlo). The flat control_drop/"
            "treatment_drop/direct_control_vs_treatment_phase3/keep_survival_significance fields are the "
            "as-run observation-level Monte Carlo paired_permutation_test, kept for continuity; "
            "observation_level_exact is that test with an exact p-value. chain_level, observation_level_exact, "
            "whole_chain_composite_direct and Tier 1 paired_significance_exact were added after the 2026-09-23 "
            f"results were known: for that run they are {POST_HOC_LABEL} (see analysis_status), and they are "
            "primary tests only for a run whose protocol names them in advance (S25)."
        ),
        "analysis_status": dict(ANALYSIS_STATUS),
        "outcome_measures": {
            "a_phase3_composite_pass_rate": phase3_composite_tiers,
            "a_phase3_pass_rate_per_family": per_family_phase3_tiers,
            "a_phase3_pass_rate_pooled": pooled_phase3_tiers,
            "b_phase2_keep_survival_pass_rate": phase2_keep_survival_tiers,
            "c_fresh_isolated_k1_baseline_pass_rate_per_family": baseline_tiers,
        },
        "confirm_disconfirm": confirm_disconfirm,
        "render_gate_timeouts": render_gate_timeouts,
        "frozen_chains": _frozen_chain_disclosure(cascade_chains),
        "excluded_observations": excluded_observations,
        "n_cascade_chains_loaded": len(cascade_chains),
        "n_baseline_chains_loaded": {family: len(chains) for family, chains in baseline_chains.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--baseline-run-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--frozen-chain-mode", choices=FROZEN_CHAIN_MODES, default=DEFAULT_FROZEN_CHAIN_MODE,
        help=(
            "How a chain that froze (status chain_broken_at_step_*) enters the per-family Phase-3 and "
            "keep-survival measures: 'fail' (default) scores it 0 at every checkpoint it did not reach -- exact "
            "for a package-invalid freeze, an imputation for a marker re-resolution freeze and for families "
            "never run; 'exclude' drops it, the as-run behavior of the 2026-09-23 sweep, needed to reproduce "
            "paper/sources/respec-cascade-statistics.json. Recorded in the output as frozen_chain_mode."
        ),
    )
    parser.add_argument(
        "--six-family", action="store_true",
        help="Aggregate the six-family rotation R (protocol section 2.2, adds table_structural) instead of the five-family contingency R'.",
    )
    parser.add_argument(
        "--blocked-policy", choices=BLOCKED_POLICIES, default=DEFAULT_BLOCKED_POLICY,
        help=(
            "How a blocked_* fresh isolated K=1 baseline chain (timed out, non-zero exit, unreadable/"
            "unresolvable input) enters outcome measure (c): 'exclude' (default) drops it, reproducing "
            "paper/sources/respec-cascade-statistics.json; 'fail' scores it 0 unless it carries an "
            "infrastructure signature (compute_s7_statistics.BLOCKED_POLICIES, passed to _baseline_outcome). "
            "The S25 locked s25-statistics command passes 'fail'. Recorded in the output as blocked_policy."
        ),
    )
    parser.add_argument(
        "--documents-manifest", type=Path, default=None,
        help=(
            "P-R4, protocol section 6.7: the locked documents manifest (e.g. "
            "manifests/s25-respec-documents-locked-v2.json), read only to find which doc_labels are public "
            "(a 'source' field containing 'public') for the public-documents-only analysis. Omit to skip "
            "section 6.7 entirely (confirm_disconfirm.public_documents_only absent from the output)."
        ),
    )
    args = parser.parse_args(argv)

    families = SIX_FAMILIES if args.six_family else FAMILIES
    cascade_chains = load_respec_cascade_chains(args.run_root)
    baseline_chains = load_baseline_chains(args.baseline_run_root, families)

    public_doc_labels: set[str] | None = None
    if args.documents_manifest is not None:
        manifest = json.loads(args.documents_manifest.read_text(encoding="utf-8"))
        public_doc_labels = {
            d["doc_label"] for d in manifest.get("documents", [])
            if "public" in str(d.get("source", "")).lower()
        }

    report = compute_respec_cascade_tiers(
        cascade_chains, baseline_chains, frozen_chain_mode=args.frozen_chain_mode, families=families,
        blocked_policy=args.blocked_policy, public_doc_labels=public_doc_labels,
    )
    report["run_root"] = str(args.run_root)
    report["baseline_run_root"] = str(args.baseline_run_root)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    # Section 7's three preregistered numbers, explicit and clearly labeled per
    # the protocol's own requirement -- never left implicit in the larger dict above.
    pooled = report["confirm_disconfirm"]["pooled"]
    chain_level = pooled["chain_level"]
    print(f"\n=== PAPER-S23 section 7 numbers (pooled across families; frozen_chain_mode={args.frozen_chain_mode}) ===")
    print(f"--- chain-level exact tests ({POST_HOC_LABEL}; primary only under a protocol naming them in advance) ---")
    print(f"control_drop   (cascade Phase-3 vs control's own fresh K=1 baseline), chain-level:   {chain_level['control_drop']}")
    print(f"treatment_drop (cascade Phase-3 vs treatment's own fresh K=1 baseline), chain-level: {chain_level['treatment_drop']}")
    print(f"direct control-vs-treatment (cascade Phase-3 per-family outcome), chain-level:      {chain_level['direct_control_vs_treatment_phase3']}")
    print(f"keep_survival_significance (Checkpoint B, control vs treatment), chain-level:       {report['confirm_disconfirm']['keep_survival_significance_chain_level']}")
    print("--- document_level exact tests (P-R4; co-requirement for CONFIRMING, protocol section 6.3) ---")
    document_level = pooled["document_level"]
    print(f"control_drop   document-level: {document_level['control_drop']}")
    print(f"treatment_drop document-level: {document_level['treatment_drop']}")
    print(f"direct         document-level: {document_level['direct_control_vs_treatment_phase3']}")
    print(f"keep_survival_significance document-level: {report['confirm_disconfirm']['keep_survival_significance_document_level']}")
    print("--- difference-in-drops (P-R4; the cascade-specific claim, C4, protocol section 6.6) ---")
    dd = report["confirm_disconfirm"]["difference_in_drops"]
    print(f"drop_difference_pp={dd['drop_difference_pp']}  chain_level={dd['chain_level']}  document_level={dd['document_level']}")
    print("--- per-document breakdown (P-R4; exploratory, no verdict weight -- protocol section 8) ---")
    for doc, per_doc in report["confirm_disconfirm"]["per_document"].items():
        cd, di = per_doc["control_drop"], per_doc["direct_control_vs_treatment_phase3"]
        dd_doc = per_doc["difference_in_drops"]
        cd_pp = -100 * cd["observed_mean_diff"] if cd.get("observed_mean_diff") is not None else None
        di_pp = -100 * di["observed_mean_diff"] if di.get("observed_mean_diff") is not None else None
        print(f"{doc}: control_drop_pp={cd_pp} (p={cd.get('p_value')})  direct_pp={di_pp} (p={di.get('p_value')})  "
              f"drop_difference_pp={dd_doc.get('drop_difference_pp')} (chain p={dd_doc['chain_level'].get('p_value')})")
    if "public_documents_only" in report["confirm_disconfirm"]:
        pub = report["confirm_disconfirm"]["public_documents_only"]
        print(f"--- public-documents-only (P-R4; C6, protocol section 6.7; n={pub['n_public_documents']}) ---")
        print(f"control_drop_pp/direct_pp signs: control_drop={pub['control_drop']}  direct={pub['direct_control_vs_treatment_phase3']}")
        print(f"chain_level={pub['chain_level']}")
        print(f"document_level={pub['document_level']}")
        print(f"difference_in_drops={pub['difference_in_drops']}")
    print("--- as-run observation-level Monte Carlo tests (continuity) ---")
    print(f"control_drop:   {pooled['control_drop']}")
    print(f"treatment_drop: {pooled['treatment_drop']}")
    print(f"direct:         {pooled['direct_control_vs_treatment_phase3']}")
    print(f"keep_survival:  {report['confirm_disconfirm']['keep_survival_significance']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
