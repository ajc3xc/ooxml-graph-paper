"""Reconstruct the per-observation outcomes of the 2026-09-23 respec_cascade run
(PAPER-S23, `docs/paper-s23-respec-cascade-protocol-v0.md`) from the three files
that survive it.

The raw `chain-result.json` files were lost with the RunPod pod and volume on
2026-09-23. What survives, in paper/sources/:
  respec-cascade-statistics.json             the pipeline's aggregate output
  respec-cascade-primary-sweep-manifest.json  status of each of the 24 cascade chains
  respec-cascade-baseline-sweep-manifest.json status of each of the 120 K=1 baselines

The unknowns are 0/1 cells:
  phase3        one per (family, arm, doc_label) for a chain whose Phase 3 was graded
  baseline      one per (family, arm, doc_label) K=1 baseline chain
  keep_survival one per (arm, doc_label) for a chain whose Phase 2 was graded

What a status fixes (read from tools/run_respec_cascade_family.py at the commit
that ran, tools/docx_trial_evaluator.py and tools/run_paper_s7_benchmark.py):
  - cascade "completed" means chain_pass was True, so phase2_pass (which needs a
    clean keep-survival) and phase3_pass (which needs section_reorder's verdict
    "pass"; the other families use a narrower check than their verdict) were
    True: keep_survival = 1 and phase3[section_reorder] = 1. Every other
    cascade cell is free.
  - cascade chain_broken_at_step_<phase>.<n>: no Phase-3 result (the as-run
    orchestrator discarded it); Phase 1 was graded if phase >= 2 and Phase 2
    if phase >= 3.
  - a graded, non-frozen chain the stored statistics exclude from a measure had
    that phase's grader raise (the orchestrator's `_safe_call` stub).
  - baseline "completed_with_failure" means the inverse failed: 0. "blocked" is
    excluded. "completed" means the inverse passed while the forward grade is
    free (a forward that ran but graded "fail" keeps the chain "completed").

Every remaining assignment is enumerated and kept only if the statistics
pipeline, run on synthetic chains carrying exactly these cells in
`frozen_chain_mode="exclude"` (the as-run scoring), reproduces every field of
respec-cascade-statistics.json. The search is staged (per family and arm,
then per family, then pooled) so it stays small, but every stage compares
fields of the pipeline's own output, and the final stage compares the whole
file; a reconstruction is accepted only there. Chains are passed to the
pipeline in the order it loaded them (sorted chain directory names = chain_id),
because the seeded bootstrap depends on that order.

One stored field cannot be reproduced literally and is compared after a
documented substitution: the stored file predates commit acc33de and records a
chain whose Phase-3 grader raised under its chain status in
`excluded_observations[*].reason`; the current pipeline records
"phase3_grading_raised_exception: ...". See `reason_substitutions` in the result.

Float summation. The run used Python 3.11 or older, whose built-in sum() adds
floats left to right; Python 3.12 sums floats with compensation, which moves
the last bit of some stored values (e.g. an ICC). Every pipeline call made here
runs inside `as_run_summation()`, which gives the pipeline modules the
left-to-right sum on Python >= 3.12, so the reproduction is exact and the
output is identical on either interpreter.

Usage (writes the reconstructions as JSON; tools/reanalyze_respec_cascade.py
is the consumer):
    python tools/reconstruct_respec_observations.py [--out reconstructions.json]
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import importlib
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compute_respec_cascade_statistics as crs  # noqa: E402 -- the pipeline under test, used unmodified

REPO = Path(__file__).resolve().parent.parent
SOURCES = REPO / "paper" / "sources"
STATISTICS = SOURCES / "respec-cascade-statistics.json"
PRIMARY_MANIFEST = SOURCES / "respec-cascade-primary-sweep-manifest.json"
BASELINE_MANIFEST = SOURCES / "respec-cascade-baseline-sweep-manifest.json"

FAMILIES: list[str] = list(crs.FAMILIES)
ARMS = ("control", "treatment")
AS_RUN_MODE = "exclude"

_FROZEN_PREFIX = "chain_broken_at_step_"
_KS_CLEAN = "clean_keep_survival"
_KS_NOT_CLEAN = "not_clean_keep_survival"  # any status other than _KS_CLEAN scores 0
_ALL_PASS = {f: 1 for f in FAMILIES}  # filler for cells a stage does not look at
_STUB_REASON = "not recorded (raw chain-result.json lost with the RunPod volume)"
# Refuse a search stage larger than this rather than run for hours.
_MAX_ASSIGNMENTS = 2 ** 16
_MAX_COMBINATIONS = 2000

# Stored fields that depend on keep-survival cells (checked at stage 4, skipped at stage 3).
_KEEP_SURVIVAL_PATHS = frozenset({
    "/outcome_measures/b_phase2_keep_survival_pass_rate",
    "/confirm_disconfirm/keep_survival_significance",
})
# Written by the CLI from its arguments, not computed.
_PATH_FIELDS = frozenset({"/run_root", "/baseline_run_root"})


class ReconstructionError(RuntimeError):
    """The stored files are inconsistent with every assignment tried."""


# ---------------------------------------------------------------------------
# Float summation as run
# ---------------------------------------------------------------------------

# Modules whose statistics this package reproduces (all reached from crs).
_PIPELINE_MODULES = ("compute_respec_cascade_statistics", "compute_multianchor_extension_statistics",
                     "graph_scorer", "compute_s7_statistics")


def left_to_right_sum(values: Any, start: Any = 0) -> Any:
    """Built-in sum() as Python <= 3.11 computes it for ints and floats."""
    total = start
    for value in values:
        total = total + value
    return total


@contextlib.contextmanager
def as_run_summation() -> Iterator[None]:
    """Run the pipeline modules with the run's float summation (see module
    docstring). A no-op on Python <= 3.11."""
    if sys.version_info < (3, 12):
        yield
        return
    modules = [importlib.import_module(name) for name in _PIPELINE_MODULES]
    saved = [(module, module.__dict__.get("sum")) for module in modules]
    for module in modules:
        module.sum = left_to_right_sum
    try:
        yield
    finally:
        for module, previous in saved:
            if previous is None:
                del module.sum
            else:
                module.sum = previous


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def load_inputs(statistics: Path = STATISTICS, primary_manifest: Path = PRIMARY_MANIFEST,
                baseline_manifest: Path = BASELINE_MANIFEST) -> dict[str, Any]:
    return {name: json.loads(path.read_text(encoding="utf-8")) for name, path in (
        ("statistics", statistics), ("primary_manifest", primary_manifest), ("baseline_manifest", baseline_manifest))}


def _excluded_index(stored: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {(e["measure"], e["doc_label"], e["arm"]) for e in stored.get("excluded_observations", [])}


def phase3_step_family(step: str, rotation: list[str] | None = None) -> str | None:
    """Family whose Phase-3 round trip step `step` (e.g. "3.4-inverse", "3.3a")
    belongs to: step 3.n is rotation[n-1]. The default rotation is FAMILIES,
    the five-family contingency R' (protocol section 2.3) the 2026-09-23 run
    used. Six-family chains number their round trips through their own
    rotation (3.5 is table_structural there, not caption), so pass the chain's
    recorded rotation for them."""
    rotation = FAMILIES if rotation is None else rotation
    match = re.match(r"^3\.(\d)", step)
    return rotation[int(match.group(1)) - 1] if match else None


def cascade_chain_meta(primary_manifest: dict[str, Any], stored: dict[str, Any]) -> list[dict[str, Any]]:
    """One record per cascade chain, in the pipeline's load order, saying which
    phases were graded and, for a chain that froze in Phase 3, which round
    trips had finished before the freeze."""
    excluded = _excluded_index(stored)
    metas: list[dict[str, Any]] = []
    for summary in sorted(primary_manifest["chains_summary"], key=lambda c: c["chain_id"]):
        status, doc_label, arm = summary["status"], summary["doc_label"], summary["arm"]
        meta: dict[str, Any] = {
            "chain_id": summary["chain_id"], "doc_label": doc_label, "arm": arm, "status": status,
            "frozen_at_step": None, "finished_phase3_families": [], "in_progress_phase3_family": None,
        }
        ks_excluded = ("phase2_keep_survival", doc_label, arm) in excluded
        if status.startswith(_FROZEN_PREFIX):
            step = status[len(_FROZEN_PREFIX):]
            phase = int(step.split(".", 1)[0])
            meta["frozen_at_step"] = step
            meta["phase1"] = "graded" if phase >= 2 else "not_reached"
            meta["phase2"] = ("grader_raised" if ks_excluded else "graded") if phase >= 3 else "not_reached"
            meta["phase3"] = "frozen"
            family = phase3_step_family(step)
            if family is not None:
                meta["finished_phase3_families"] = FAMILIES[:FAMILIES.index(family)]
                meta["in_progress_phase3_family"] = family
        elif status in ("completed", "completed_with_failure"):
            p3_excluded = all((f"phase3_{f}", doc_label, arm) in excluded for f in FAMILIES)
            composite_excluded = ("phase3_composite", doc_label, arm) in excluded
            meta["phase3"] = "grader_raised" if p3_excluded else "graded"
            meta["phase2"] = "grader_raised" if ks_excluded else "graded"
            meta["phase1"] = "grader_raised" if composite_excluded and not (p3_excluded or ks_excluded) else "graded"
            if status == "completed" and "grader_raised" in (meta["phase1"], meta["phase2"], meta["phase3"]):
                raise ReconstructionError(f"{doc_label}/{arm}: 'completed' but a grader raised -- impossible")
        else:
            raise ReconstructionError(f"{doc_label}/{arm}: unexpected cascade status {status!r}")
        metas.append(meta)
    return metas


def baseline_chain_meta(baseline_manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for family in FAMILIES:
        chains = [c for c in baseline_manifest["chains_summary"] if c["family"] == family]
        for c in chains:
            if c["status"] not in ("completed", "completed_with_failure", "blocked"):
                raise ReconstructionError(f"{c['chain_id']}: unexpected baseline status {c['status']!r}")
        out[family] = sorted(chains, key=lambda c: c["chain_id"])
    return out


# ---------------------------------------------------------------------------
# Cells: what the statuses fix (0/1) and what is free (None)
# ---------------------------------------------------------------------------

def phase3_cells(metas: list[dict[str, Any]], family: str, arm: str) -> list[tuple[str, int | None]]:
    return [(m["doc_label"], 1 if (m["status"] == "completed" and family == "section_reorder") else None)
            for m in metas if m["arm"] == arm and m["phase3"] == "graded"]


def keep_survival_cells(metas: list[dict[str, Any]], arm: str) -> list[tuple[str, int | None]]:
    return [(m["doc_label"], 1 if m["status"] == "completed" else None)
            for m in metas if m["arm"] == arm and m["phase2"] == "graded"]


def baseline_cells(bmetas: list[dict[str, Any]], arm: str) -> list[tuple[str, int | None]]:
    """Blocked chains carry no cell (excluded by the pipeline)."""
    return [(b["doc_label"], {"completed": None, "completed_with_failure": 0}[b["status"]])
            for b in bmetas if b["arm"] == arm and b["status"] != "blocked"]


def _assignments(cells: list[tuple[str, int | None]]) -> Iterator[dict[str, int]]:
    free = [key for key, fixed in cells if fixed is None]
    if 2 ** len(free) > _MAX_ASSIGNMENTS:
        raise ReconstructionError(f"{len(free)} free cells in one stage -- search too large")
    for bits in itertools.product((0, 1), repeat=len(free)):
        values = dict(zip(free, bits))
        yield {key: (values[key] if fixed is None else fixed) for key, fixed in cells}


# ---------------------------------------------------------------------------
# Synthetic chains in the schema the pipeline reads
# ---------------------------------------------------------------------------

def _stub() -> dict[str, Any]:
    return {"status": "grading_raised_exception", "reason": _STUB_REASON}


def cascade_chain(meta: dict[str, Any], phase3: dict[str, int] | None, keep_survival: int | None) -> dict[str, Any]:
    """A chain-result.json carrying exactly the given cells. `phase*_pass`
    only feeds the whole-chain composite, which the status fixes: all True
    for "completed", and Phase 3 False otherwise."""
    completed = meta["status"] == "completed"
    chain: dict[str, Any] = {
        "chain_id": meta["chain_id"], "doc_label": meta["doc_label"], "arm": meta["arm"], "status": meta["status"],
        "phase1_result": None, "phase2_result": None, "phase3_result": None,
    }
    if meta["phase1"] == "graded":
        chain["phase1_result"] = {"phase1_pass": True}
    elif meta["phase1"] == "grader_raised":
        chain["phase1_result"] = _stub()
    if meta["phase2"] == "graded":
        chain["phase2_result"] = {
            "phase2_pass": completed,
            "keep_survival": {"overall_status": _KS_CLEAN if keep_survival else _KS_NOT_CLEAN},
        }
    elif meta["phase2"] == "grader_raised":
        chain["phase2_result"] = _stub()
    if meta["phase3"] == "graded":
        chain["phase3_result"] = {
            "phase3_pass": completed,
            "families": {f: {"verdict": "pass" if phase3[f] else "fail"} for f in FAMILIES},
        }
    elif meta["phase3"] == "grader_raised":
        chain["phase3_result"] = _stub()
    return chain


def baseline_chain(bmeta: dict[str, Any], outcome: int | None) -> dict[str, Any]:
    """A K=1 run_chain checkpoint whose `_chain_outcome` is `outcome`."""
    chain = {key: bmeta[key] for key in ("chain_id", "doc_label", "family", "arm", "status")}
    if bmeta["status"] == "blocked":
        chain["pairs"] = [{"pair_index": 0, "forward": None}]
    elif bmeta["status"] == "completed_with_failure":
        chain["pairs"] = [{"forward": {"grading": {"verdict": "pass"}}, "inverse": {"grading": {"verdict": "fail"}}}]
    else:
        chain["pairs"] = [{"forward": {"grading": {"verdict": "pass" if outcome else "fail"}},
                           "inverse": {"grading": {"verdict": "pass"}}}]
    return chain


def build_chains(metas: list[dict[str, Any]], bmetas: dict[str, list[dict[str, Any]]],
                 reconstruction: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """(cascade chains, {family: baseline chains}) for one reconstruction, in load order."""
    p3, bl, ks = reconstruction["phase3"], reconstruction["baseline"], reconstruction["keep_survival"]
    chains = []
    for m in metas:
        arm, label = m["arm"], m["doc_label"]
        phase3 = {f: p3[f][arm][label] for f in FAMILIES} if m["phase3"] == "graded" else None
        chains.append(cascade_chain(m, phase3, ks[arm].get(label)))
    bchains = {f: [baseline_chain(b, bl[f][b["arm"]].get(b["doc_label"])) for b in bmetas[f]] for f in FAMILIES}
    return chains, bchains


# ---------------------------------------------------------------------------
# Comparison against the stored file
# ---------------------------------------------------------------------------

def stored_mismatches(stored: Any, computed: Any, path: str = "", skip: frozenset[str] = frozenset(),
                      first_only: bool = False) -> list[str]:
    """Paths of every stored leaf the computed report does not reproduce
    exactly. Keys the computed report has and the stored file lacks (fields
    added to the pipeline after the run) are ignored."""
    if path in skip:
        return []
    if isinstance(stored, dict):
        if not isinstance(computed, dict):
            return [path or "/"]
        out: list[str] = []
        for key in sorted(stored):
            sub = f"{path}/{key}"
            if key not in computed:
                if sub not in skip:
                    out.append(f"{sub} (missing)")
            else:
                out.extend(stored_mismatches(stored[key], computed[key], sub, skip, first_only))
            if out and first_only:
                return out
        return out
    if isinstance(stored, list):
        if not isinstance(computed, list) or len(stored) != len(computed):
            return [path]
        out = []
        for i, (s, c) in enumerate(zip(stored, computed)):
            out.extend(stored_mismatches(s, c, f"{path}[{i}]", skip, first_only))
            if out and first_only:
                return out
        return out
    if type(stored) is bool or type(computed) is bool:
        return [] if stored is computed else [path]
    return [] if stored == computed else [path]


def count_leaves(obj: Any, path: str = "", skip: frozenset[str] = frozenset()) -> int:
    if path in skip:
        return 0
    if isinstance(obj, dict):
        return sum(count_leaves(v, f"{path}/{k}", skip) for k, v in obj.items())
    if isinstance(obj, list):
        return sum(count_leaves(v, f"{path}[{i}]", skip) for i, v in enumerate(obj))
    return 1


def _with_stored_reason_convention(report: dict[str, Any], metas: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The stored file records a grader crash under the chain's status (it
    predates acc33de). Rewrite those reasons to that convention and list every
    rewrite, so the comparison is otherwise exact."""
    stubbed = {(m["doc_label"], m["arm"]): m["status"] for m in metas
               if "grader_raised" in (m["phase1"], m["phase2"], m["phase3"])}
    report = copy.deepcopy(report)
    substitutions = []
    for entry in report.get("excluded_observations", []):
        key = (entry.get("doc_label"), entry.get("arm"))
        if key in stubbed and "grading_raised_exception" in str(entry.get("reason")):
            substitutions.append({"measure": entry["measure"], "doc_label": key[0], "arm": key[1],
                                  "pipeline_reason": entry["reason"], "stored_reason": stubbed[key]})
            entry["reason"] = stubbed[key]
    return report, substitutions


# ---------------------------------------------------------------------------
# Staged search
# ---------------------------------------------------------------------------

def _arm_fields(report: dict[str, Any], arm: str, as_arm: str | None = None) -> dict[str, Any]:
    """The fields of a `_tiered_report` computed from one arm's data alone."""
    src = as_arm or arm
    t1, t2, t3 = (report["tier1_per_document_unweighted"], report["tier2_anchor_weighted_document_mean"],
                  report["tier3_pooled_anchor_level"])
    return {
        "n_documents": t1[f"{src}_n_documents"], "pass_rate_ci": t1[f"{src}_pass_rate_ci"], "tier2": t2[src],
        "naive_pooled_n": t3[f"{src}_naive_pooled_n"], "pass_rate_ci_naive": t3[f"{src}_pass_rate_ci_naive"],
        "clustering": t3[f"{src}_clustering"], "n_distinct_documents": report["n_distinct_documents"][src],
    }


def _arm_candidates(cells: list[tuple[str, int | None]], make_chains: Callable[[dict[str, int]], list[dict[str, Any]]],
                    outcome_fn: Callable[[dict[str, Any]], float | None], arm: str,
                    stored_report: dict[str, Any]) -> list[dict[str, int]]:
    """Stage 1: assignments of one arm's cells whose arm-only fields (Tier 1/2/3
    rates, CIs, ICC) match the stored report. The point estimates and the ICC
    dict are checked first, with the same arithmetic `_tiered_report` uses,
    because they are cheap; the full `_tiered_report` (seeded bootstraps) only
    runs for survivors."""
    target = _arm_fields(stored_report, arm)
    out = []
    for assignment in _assignments(cells):
        grouped, _ = crs._group_by_document(make_chains(assignment), outcome_fn, "stage1")
        by_doc = grouped[arm]
        pooled = [v for vs in by_doc.values() for v in vs]
        doc_means = [left_to_right_sum(vs) / len(vs) for vs in by_doc.values() if vs]
        if (pooled and left_to_right_sum(pooled) / len(pooled) != (target["pass_rate_ci_naive"] or {}).get("mean")) or (
                doc_means and left_to_right_sum(doc_means) / len(doc_means) != (target["pass_rate_ci"] or {}).get("mean")):
            continue
        if crs.estimate_icc_and_effective_n(by_doc) != target["clustering"]:
            continue
        computed = _arm_fields(crs._tiered_report(by_doc, by_doc), arm, as_arm="control")
        if not stored_mismatches(target, computed, first_only=True):
            out.append(assignment)
    return out


def _pair_candidates(control: list[dict[str, int]], treatment: list[dict[str, int]],
                     make_chains: Callable[[dict[str, dict[str, int]]], list[dict[str, Any]]],
                     outcome_fn: Callable[[dict[str, Any]], float | None],
                     stored_report: dict[str, Any], stored_direct: dict[str, Any] | None) -> list[dict[str, dict[str, int]]]:
    """Stage 2: (control, treatment) pairs whose full tiered report (and, for
    cascade measures, direct control-vs-treatment test) match."""
    out = []
    for c, t in itertools.product(control, treatment):
        assignment = {"control": c, "treatment": t}
        if len(out) > _MAX_COMBINATIONS:
            raise ReconstructionError("too many stage-2 candidates")
        chains = make_chains(assignment)
        grouped, _ = crs._group_by_document(chains, outcome_fn, "stage2")
        report = crs._tiered_report(grouped["control"], grouped["treatment"], exact_tests=True)
        if stored_mismatches(stored_report, report, first_only=True):
            continue
        if stored_direct is not None:
            direct = crs._direct_arm_comparison(crs._anchor_level_values(chains, outcome_fn))
            if stored_mismatches(stored_direct, direct, first_only=True):
                continue
        out.append(assignment)
    return out


def _as_float_levels(assignment: dict[str, dict[str, int | None]]) -> dict[str, dict[str, float]]:
    return {arm: {k: float(v) for k, v in vals.items() if v is not None} for arm, vals in assignment.items()}


def reconstruct(inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every assignment of the free cells that reproduces the stored
    statistics. Raises ReconstructionError if there is none."""
    with as_run_summation():
        return _reconstruct(inputs or load_inputs())


def _reconstruct(inputs: dict[str, Any]) -> dict[str, Any]:
    stored = inputs["statistics"]
    metas = cascade_chain_meta(inputs["primary_manifest"], stored)
    bmetas = baseline_chain_meta(inputs["baseline_manifest"])
    om, cd = stored["outcome_measures"], stored["confirm_disconfirm"]
    search: dict[str, Any] = {"per_family": {}}
    ks_placeholder = {arm: {k: (1 if v is None else v) for k, v in keep_survival_cells(metas, arm)} for arm in ARMS}

    # Stage 0: the whole-chain composite has no free cell -- the statuses alone
    # must reproduce it, or the status reading above is wrong.
    p3_ones = {f: {arm: {k: 1 for k, _ in phase3_cells(metas, f, arm)} for arm in ARMS} for f in FAMILIES}
    probe, _ = build_chains(metas, bmetas, {"phase3": p3_ones, "baseline": {f: {a: {} for a in ARMS} for f in FAMILIES},
                                            "keep_survival": ks_placeholder})
    grouped, _ = crs._group_by_document(probe, crs._phase3_composite_outcome, "phase3_composite")
    bad = stored_mismatches(om["a_phase3_composite_pass_rate"],
                            crs._tiered_report(grouped["control"], grouped["treatment"], exact_tests=True))
    if bad:
        raise ReconstructionError(f"the chain statuses do not reproduce the stored composite measure: {bad[:5]}")

    per_family_survivors: dict[str, list[tuple[dict, dict]]] = {}
    for family in FAMILIES:
        def p3_fn(chain: dict[str, Any], family: str = family) -> float | None:
            return crs._phase3_family_outcome(chain, family, AS_RUN_MODE)

        def p3_arm_chains(assignment: dict[str, int], arm: str, family: str = family) -> list[dict[str, Any]]:
            return [cascade_chain(m, {f: assignment[m["doc_label"]] if f == family else 1 for f in FAMILIES}, 1)
                    for m in metas if m["arm"] == arm and m["phase3"] == "graded"]

        def p3_chains(assignment: dict[str, dict[str, int]], family: str = family) -> list[dict[str, Any]]:
            return [cascade_chain(m, {f: assignment[m["arm"]][m["doc_label"]] if f == family else 1 for f in FAMILIES}
                                  if m["phase3"] == "graded" else None, 1) for m in metas]

        def b_arm_chains(assignment: dict[str, int], arm: str, family: str = family) -> list[dict[str, Any]]:
            return [baseline_chain(b, assignment.get(b["doc_label"])) for b in bmetas[family] if b["arm"] == arm]

        def b_chains(assignment: dict[str, dict[str, int]], family: str = family) -> list[dict[str, Any]]:
            return [baseline_chain(b, assignment[b["arm"]].get(b["doc_label"])) for b in bmetas[family]]

        stored_p3 = om["a_phase3_pass_rate_per_family"][family]
        stored_b = om["c_fresh_isolated_k1_baseline_pass_rate_per_family"][family]
        p3_arm = {arm: _arm_candidates(phase3_cells(metas, family, arm), lambda a, arm=arm: p3_arm_chains(a, arm),
                                       p3_fn, arm, stored_p3) for arm in ARMS}
        b_arm = {arm: _arm_candidates(baseline_cells(bmetas[family], arm), lambda a, arm=arm: b_arm_chains(a, arm),
                                      crs._baseline_outcome, arm, stored_b) for arm in ARMS}
        p3_pairs = _pair_candidates(p3_arm["control"], p3_arm["treatment"], p3_chains, p3_fn, stored_p3,
                                    cd[family]["direct_control_vs_treatment_phase3"])
        b_pairs = _pair_candidates(b_arm["control"], b_arm["treatment"], b_chains, crs._baseline_outcome, stored_b, None)
        survivors = []
        for p3, bl in itertools.product(p3_pairs, b_pairs):
            p3_levels, b_levels = _as_float_levels(p3), _as_float_levels(bl)
            if all(not stored_mismatches(cd[family][f"{arm}_drop"], crs._paired_drop(p3_levels, b_levels, arm), first_only=True)
                   for arm in ARMS):
                survivors.append((p3, bl))
        search["per_family"][family] = {
            "phase3_candidates_per_arm": {arm: len(p3_arm[arm]) for arm in ARMS},
            "baseline_candidates_per_arm": {arm: len(b_arm[arm]) for arm in ARMS},
            "phase3_pairs": len(p3_pairs), "baseline_pairs": len(b_pairs),
            "consistent_with_family_drops": len(survivors),
        }
        if not survivors:
            raise ReconstructionError(f"no {family} assignment reproduces that family's stored statistics")
        per_family_survivors[family] = survivors

    # Stage 3: pooled across families -- the full pipeline, keep-survival held fixed.
    n_combos = 1
    for family in FAMILIES:
        n_combos *= len(per_family_survivors[family])
    if n_combos > _MAX_COMBINATIONS:
        raise ReconstructionError(f"{n_combos} pooled combinations -- search too large")
    pooled: list[dict[str, Any]] = []
    for combo in itertools.product(*(per_family_survivors[f] for f in FAMILIES)):
        candidate = {"phase3": {f: c[0] for f, c in zip(FAMILIES, combo)},
                     "baseline": {f: c[1] for f, c in zip(FAMILIES, combo)}, "keep_survival": ks_placeholder}
        chains, bchains = build_chains(metas, bmetas, candidate)
        report, _ = _with_stored_reason_convention(
            crs.compute_respec_cascade_tiers(chains, bchains, frozen_chain_mode=AS_RUN_MODE), metas)
        if not stored_mismatches(stored, report, skip=_KEEP_SURVIVAL_PATHS | _PATH_FIELDS, first_only=True):
            pooled.append(candidate)
    search["pooled_combinations_checked"] = n_combos
    search["pooled_consistent"] = len(pooled)
    if not pooled:
        raise ReconstructionError("no phase3/baseline assignment reproduces the pooled statistics")

    # Stage 4: keep-survival (independent of every other cell).
    def ks_fn(chain: dict[str, Any]) -> float | None:
        return crs._phase2_keep_survival_outcome(chain, AS_RUN_MODE)

    def ks_arm_chains(assignment: dict[str, int], arm: str) -> list[dict[str, Any]]:
        return [cascade_chain(m, _ALL_PASS, assignment[m["doc_label"]])
                for m in metas if m["arm"] == arm and m["phase2"] == "graded"]

    def ks_chains(assignment: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        return [cascade_chain(m, _ALL_PASS, assignment[m["arm"]].get(m["doc_label"])) for m in metas]

    stored_ks = om["b_phase2_keep_survival_pass_rate"]
    ks_arm = {arm: _arm_candidates(keep_survival_cells(metas, arm), lambda a, arm=arm: ks_arm_chains(a, arm),
                                   ks_fn, arm, stored_ks) for arm in ARMS}
    ks_pairs = _pair_candidates(ks_arm["control"], ks_arm["treatment"], ks_chains, ks_fn, stored_ks,
                                cd["keep_survival_significance"])
    search["keep_survival"] = {"candidates_per_arm": {arm: len(ks_arm[arm]) for arm in ARMS}, "pairs": len(ks_pairs)}
    if not ks_pairs:
        raise ReconstructionError("no keep-survival assignment reproduces the stored keep-survival statistics")

    # Stage 5: the whole stored file, with the unmodified top-level function.
    accepted: list[dict[str, Any]] = []
    substitutions: list[dict[str, Any]] = []
    for base, ks in itertools.product(pooled, ks_pairs):
        candidate = {"phase3": base["phase3"], "baseline": base["baseline"], "keep_survival": ks}
        chains, bchains = build_chains(metas, bmetas, candidate)
        report, substitutions = _with_stored_reason_convention(
            crs.compute_respec_cascade_tiers(chains, bchains, frozen_chain_mode=AS_RUN_MODE), metas)
        if not stored_mismatches(stored, report, skip=_PATH_FIELDS):
            accepted.append(candidate)
    search["full_file_checked"] = len(pooled) * len(ks_pairs)
    if not accepted:
        raise ReconstructionError("no assignment reproduces the complete stored statistics file")
    return {
        "reconstructions": accepted,
        "cascade_meta": metas,
        "baseline_meta": bmetas,
        "search": search,
        "reason_substitutions": substitutions,
        "stored_leaves_compared": count_leaves(stored, skip=_PATH_FIELDS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--statistics", type=Path, default=STATISTICS)
    parser.add_argument("--primary-manifest", type=Path, default=PRIMARY_MANIFEST)
    parser.add_argument("--baseline-manifest", type=Path, default=BASELINE_MANIFEST)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = reconstruct(load_inputs(args.statistics, args.primary_manifest, args.baseline_manifest))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(json.dumps({"n_consistent_reconstructions": len(result["reconstructions"]), "search": result["search"]},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
