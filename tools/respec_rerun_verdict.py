"""PAPER-S25 (`docs/paper-s25-respec-cascade-rerun-protocol-v1.md`) section 7:
the decision rule (D1-D3 / C1-C6), applied mechanically (prerequisite P-R5).

Reads the four `compute_respec_cascade_statistics.py` outputs the locked
`s25-statistics` command produces from ``--statistics-dir`` -- one file per
frozen-chain mode (``fail_graded_prefreeze``, ``fail``, ``exclude``,
``package_invalid_only``), named ``*statistics-<mode>.json`` -- applies
section 7's rule under the primary scoring (``fail_graded_prefreeze``,
section 5.2) and reports the freeze-scoring robustness label computed under
``exclude`` (section 5.2's "robust to freeze scoring" / "dependent on freeze
scoring").

Every number the rule needs is read from an explicitly named field; none is
guessed or derived by a shortcut this module does not document. In
particular:

* Section 7's C1-C4 require a **document-level** p-value beside every
  **chain-level** one (protocol section 6.3: "document_level tests beside
  every chain_level entry"). As of this writing `compute_respec_cascade_
  statistics.py` computes `chain_level` but NOT `document_level`
  (prerequisite **P-R4**, not yet implemented) -- so this script will
  raise `VerdictInputError` and exit 2 on today's statistics files. That is
  intentional: do not hand-wave the missing document-level test or fall
  back to the chain-level p-value alone. Finish P-R4, rerun `s25-statistics`,
  then rerun this script.
* C4 needs the difference-in-drops test (protocol section 6.6, output key
  `drop_difference`, also P-R4) and C6 needs the public-documents-only
  analysis (section 6.7, also P-R4). Both are required the same way.
* C5 needs, if it applies, statistics computed under the render-gate adverse
  bound (section 5.7(b)) or under the grader-exception adverse/favourable
  bounds (section 5.5) -- neither is one of the four files the locked
  command produces. This script checks whether the antecedent applies
  (any recorded `render_gate_timeouts`, or a disclosed count of unregradable
  grader-exception stubs) and, if it does, fails loudly rather than assume
  C5 holds.

This module does not reimplement any statistical primitive: every p-value
and point estimate is read as-is from the statistics JSON that
`tools/graph_scorer.py` (via `compute_respec_cascade_statistics.py`)
produced.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Fixed by protocol section 5.2 / 6.9 / 7 -- not options.
# ---------------------------------------------------------------------------
FROZEN_CHAIN_MODES: tuple[str, ...] = ("fail_graded_prefreeze", "fail", "exclude", "package_invalid_only")
PRIMARY_MODE = "fail_graded_prefreeze"          # section 5.2: "the primary scoring"
ROBUSTNESS_ALT_MODE = "exclude"                 # section 5.2: the freeze-scoring robustness comparison
REQUIRED_BLOCKED_POLICY = "fail"                # section 6.9's locked command: --blocked-policy fail, every mode
ALPHA = 0.05                                    # section 7: "significant" means two-sided exact p < 0.05

# Section 6.1 sign conventions: the statistics script reports observed_mean_diff
# as A - B (A = cascade Phase-3 outcome for control_drop/treatment_drop, A =
# control Phase-3 for the direct comparison and for keep_survival). This module
# converts to the protocol's own pp conventions (positive = worse, for the
# drops; positive = favours treatment, for direct/keep_survival) by negating.
_DROP_AND_DIRECT_SIGN = -1.0


class VerdictInputError(RuntimeError):
    """Raised when a field the decision rule needs is missing from the
    statistics input. Callers must not catch this to substitute a guess."""


def _dig(node: Any, keys: tuple[str, ...], ctx: str) -> Any:
    cur = node
    for i, key in enumerate(keys):
        if not isinstance(cur, dict) or key not in cur:
            path = ".".join(str(k) for k in keys[: i + 1])
            raise VerdictInputError(f"{ctx}: missing required field '{path}'")
        cur = cur[key]
    return cur


def _require_p(node: dict[str, Any], ctx: str, label: str) -> dict[str, Any]:
    if not isinstance(node, dict) or node.get("p_value") is None:
        reason = node.get("reason") if isinstance(node, dict) else None
        raise VerdictInputError(f"{ctx}: {label} has no p_value" + (f" ({reason})" if reason else ""))
    return node


# ---------------------------------------------------------------------------
# Loading and cross-checking the four statistics files
# ---------------------------------------------------------------------------

def load_statistics_files(stats_dir: Path) -> dict[str, dict[str, Any]]:
    """One file per FROZEN_CHAIN_MODES entry, matched by filename suffix
    `statistics-<mode>.json` (as `respec-rerun-v1-statistics-$MODE.json` in
    the locked s25-statistics command, section 6.9). Cross-checks each
    file's own recorded `frozen_chain_mode` and `blocked_policy` fields so a
    misnamed or wrong file is caught immediately, not silently used."""
    stats_dir = Path(stats_dir)
    if not stats_dir.is_dir():
        raise VerdictInputError(f"--statistics-dir {stats_dir} is not a directory")
    out: dict[str, dict[str, Any]] = {}
    for mode in FROZEN_CHAIN_MODES:
        matches = sorted(stats_dir.glob(f"*statistics-{mode}.json"))
        if not matches:
            raise VerdictInputError(
                f"no statistics file for frozen-chain-mode {mode!r} found in {stats_dir} "
                f"(expected a filename ending 'statistics-{mode}.json', as the locked "
                "s25-statistics command produces -- section 6.9)"
            )
        if len(matches) > 1:
            raise VerdictInputError(
                f"multiple candidate statistics files for frozen-chain-mode {mode!r} in "
                f"{stats_dir}: {[str(m) for m in matches]} -- expected exactly one"
            )
        path = matches[0]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerdictInputError(f"{path}: could not be read as JSON ({exc})") from exc
        recorded_mode = data.get("frozen_chain_mode")
        if recorded_mode != mode:
            raise VerdictInputError(
                f"{path}: frozen_chain_mode field is {recorded_mode!r}, expected {mode!r} -- "
                "wrong file matched by name"
            )
        recorded_policy = data.get("blocked_policy")
        if recorded_policy != REQUIRED_BLOCKED_POLICY:
            raise VerdictInputError(
                f"{path}: blocked_policy field is {recorded_policy!r}, expected "
                f"{REQUIRED_BLOCKED_POLICY!r} (the locked s25-statistics command's choice, "
                "section 6.9) -- wrong command was used to produce this file"
            )
        out[mode] = data
    return out


# ---------------------------------------------------------------------------
# Extracting the numbers section 7 needs, each from an explicitly named field
# ---------------------------------------------------------------------------

def _pooled_measure_node(stats: dict[str, Any], measure_key: str, ctx: str) -> dict[str, Any]:
    return _dig(stats, ("confirm_disconfirm", "pooled", measure_key), ctx)


def _level(node: dict[str, Any], level: str, measure_key: str, ctx: str) -> dict[str, Any]:
    if level not in node:
        extra = (
            " (prerequisite P-R4 -- document-level tests beside every chain_level entry, "
            "protocol section 6.3 -- is not yet implemented in compute_respec_cascade_statistics.py)"
            if level == "document_level" else ""
        )
        raise VerdictInputError(
            f"{ctx}: confirm_disconfirm.pooled.{measure_key} has no '{level}' entry{extra}"
        )
    return _require_p(node[level], ctx, f"confirm_disconfirm.pooled.{measure_key}.{level}")


def _extract_pooled_measure(stats: dict[str, Any], measure_key: str, ctx: str, pp_sign: float) -> dict[str, Any]:
    node = _pooled_measure_node(stats, measure_key, ctx)
    chain = _level(node, "chain_level", measure_key, ctx)
    document = _level(node, "document_level", measure_key, ctx)
    return {
        "pp": pp_sign * 100.0 * chain["observed_mean_diff"],
        "chain_level_p": chain["p_value"],
        "chain_level_exact": chain.get("exact"),
        "chain_level_observed_mean_diff": chain["observed_mean_diff"],
        "chain_level_n_clusters": chain.get("n_clusters"),
        "document_level_p": document["p_value"],
        "document_level_exact": document.get("exact"),
        "document_level_observed_mean_diff": document.get("observed_mean_diff"),
        "document_level_n_clusters": document.get("n_clusters"),
    }


def _extract_keep_survival(stats: dict[str, Any], ctx: str) -> dict[str, Any]:
    cd = stats.get("confirm_disconfirm")
    if not isinstance(cd, dict):
        raise VerdictInputError(f"{ctx}: missing required field 'confirm_disconfirm'")
    chain_key = "keep_survival_significance_chain_level"
    document_key = "keep_survival_significance_document_level"
    if chain_key not in cd:
        raise VerdictInputError(f"{ctx}: confirm_disconfirm.{chain_key} missing")
    chain = _require_p(cd[chain_key], ctx, f"confirm_disconfirm.{chain_key}")
    if document_key not in cd:
        raise VerdictInputError(
            f"{ctx}: confirm_disconfirm.{document_key} missing (prerequisite P-R4 -- "
            "document-level keep-survival test, protocol section 6.3/7 condition C3 -- "
            "is not yet implemented)"
        )
    document = _require_p(cd[document_key], ctx, f"confirm_disconfirm.{document_key}")
    return {
        "pp": _DROP_AND_DIRECT_SIGN * 100.0 * chain["observed_mean_diff"],
        "chain_level_p": chain["p_value"],
        "chain_level_exact": chain.get("exact"),
        "document_level_p": document["p_value"],
        "document_level_exact": document.get("exact"),
    }


def _extract_drop_difference(stats: dict[str, Any], ctx: str) -> dict[str, Any]:
    """Protocol section 6.6: `d = (control_baseline - control_phase3) -
    (treatment_baseline - treatment_phase3)`, `drop_difference_pp = 100 x
    mean(d)`, output key `drop_difference` (section 6.6, prerequisite P-R4,
    not yet implemented). Assumed built the same way as every other section-7
    test in this codebase (`cluster_paired_sign_flip_test(clusters, a, b)`
    with `a` = each observation's control-arm drop and `b` = its treatment-arm
    drop, so `observed_mean_diff` IS `mean(d)` already -- no sign flip, unlike
    control_drop/treatment_drop/direct, which reverse the cascade-vs-baseline
    or control-vs-treatment order). If a future implementation of P-R4 uses a
    different sign, update this function and its docstring together."""
    node = _dig(stats, ("confirm_disconfirm", "pooled", "drop_difference"), ctx)
    chain = _level(node, "chain_level", "drop_difference", ctx)
    document = _level(node, "document_level", "drop_difference", ctx)
    return {
        "pp": 100.0 * chain["observed_mean_diff"],
        "chain_level_p": chain["p_value"],
        "chain_level_exact": chain.get("exact"),
        "document_level_p": document["p_value"],
        "document_level_exact": document.get("exact"),
    }


def _observed_mean_diff_anywhere(node: dict[str, Any], ctx: str, label: str) -> float:
    """C6 (section 7) needs only the SIGN of a point estimate, at whichever
    level it is reported (section 6.7 does not require significance). Accepts
    either a flat `observed_mean_diff` or one nested under `chain_level`."""
    chain = node.get("chain_level")
    if isinstance(chain, dict) and chain.get("observed_mean_diff") is not None:
        return chain["observed_mean_diff"]
    if node.get("observed_mean_diff") is not None:
        return node["observed_mean_diff"]
    raise VerdictInputError(f"{ctx}: {label} has no observed_mean_diff (flat or chain_level)")


def _extract_public_only(stats: dict[str, Any], ctx: str) -> dict[str, Any]:
    """Protocol section 6.7's public-documents-only analysis, output
    expected beside `confirm_disconfirm.pooled` under
    `confirm_disconfirm.public_documents_only` (prerequisite P-R4, not yet
    implemented). C6 needs only `control_drop_pp > 0` and `direct_pp > 0`."""
    node = _dig(stats, ("confirm_disconfirm", "public_documents_only"), ctx)
    if "control_drop" not in node:
        raise VerdictInputError(f"{ctx}: confirm_disconfirm.public_documents_only.control_drop missing")
    if "direct_control_vs_treatment_phase3" not in node:
        raise VerdictInputError(
            f"{ctx}: confirm_disconfirm.public_documents_only.direct_control_vs_treatment_phase3 missing"
        )
    control_drop_diff = _observed_mean_diff_anywhere(
        node["control_drop"], ctx, "confirm_disconfirm.public_documents_only.control_drop"
    )
    direct_diff = _observed_mean_diff_anywhere(
        node["direct_control_vs_treatment_phase3"], ctx,
        "confirm_disconfirm.public_documents_only.direct_control_vs_treatment_phase3",
    )
    return {
        "control_drop_pp": _DROP_AND_DIRECT_SIGN * 100.0 * control_drop_diff,
        "direct_pp": _DROP_AND_DIRECT_SIGN * 100.0 * direct_diff,
    }


def _evaluate_c5(stats: dict[str, Any], ctx: str) -> dict[str, Any]:
    """Section 7 C5: only a conditional requirement. If no render-gate
    timeout occurred and no grader-exception stub is disclosed as
    unregradable, C5 holds vacuously. If either antecedent applies, this
    script cannot compute the required adverse/favourable-bound comparison
    from the four locked-command statistics files alone, and fails loudly
    instead of assuming C5 holds."""
    if "render_gate_timeouts" not in stats:
        raise VerdictInputError(f"{ctx}: 'render_gate_timeouts' missing from statistics (prerequisite P-R2)")
    render_gate_timeouts = stats["render_gate_timeouts"]
    if render_gate_timeouts:
        raise VerdictInputError(
            f"{ctx}: {len(render_gate_timeouts)} render-gate timeout(s) recorded; condition C5 "
            "requires C1-C4 to also hold under the adverse bound of protocol section 5.7(b), "
            "which needs a statistics run scored under that bound -- not one of the four "
            "frozen-chain-mode files the locked s25-statistics command produces. Compute that "
            "sensitivity run and extend this script before trusting a CONFIRMING verdict; "
            "refusing to guess."
        )
    unregradable = stats.get("unregradable_grader_exception_stubs") or 0
    if unregradable:
        raise VerdictInputError(
            f"{ctx}: statistics disclose {unregradable} grader-exception stub(s) that could not "
            "be re-graded; condition C5 requires the verdict to be identical under the adverse "
            "and favourable bounds of protocol section 5.5, which this script does not yet "
            "compute. Refusing to guess."
        )
    return {
        "held": True,
        "render_gate_timeouts": 0,
        "unregradable_grader_exception_stubs": unregradable,
        "note": "no render-gate timeouts and no disclosed unregradable grader-exception stubs recorded; C5 holds vacuously",
    }


# ---------------------------------------------------------------------------
# The decision rule itself (protocol section 7)
# ---------------------------------------------------------------------------

def evaluate(stats_by_mode: dict[str, dict[str, Any]], mode: str) -> dict[str, Any]:
    stats = stats_by_mode[mode]
    ctx = f"frozen-chain-mode={mode}"

    control_drop = _extract_pooled_measure(stats, "control_drop", ctx, _DROP_AND_DIRECT_SIGN)
    treatment_drop = _extract_pooled_measure(stats, "treatment_drop", ctx, _DROP_AND_DIRECT_SIGN)
    direct = _extract_pooled_measure(stats, "direct_control_vs_treatment_phase3", ctx, _DROP_AND_DIRECT_SIGN)
    keep_survival = _extract_keep_survival(stats, ctx)
    drop_difference = _extract_drop_difference(stats, ctx)
    public_only = _extract_public_only(stats, ctx)
    c5 = _evaluate_c5(stats, ctx)

    d_documents = direct.get("document_level_n_clusters")

    # --- Step 1: DISCONFIRMING (section 7) -----------------------------
    d1 = direct["chain_level_p"] >= ALPHA or direct["pp"] <= 0
    d2 = (
        (control_drop["chain_level_p"] > 0.10 and treatment_drop["chain_level_p"] > 0.10)
        or (control_drop["pp"] < 10 and treatment_drop["pp"] < 10)
    )
    d3 = treatment_drop["pp"] >= control_drop["pp"]
    disconfirming = d1 or d2 or d3

    sub_label = None
    if disconfirming:
        contrary = direct["pp"] <= 0 or control_drop["pp"] <= 0 or d3
        sub_label = "contrary" if contrary else f"not_detected_at_D={d_documents}"

    # --- Step 2: CONFIRMING (only meaningful if not disconfirming, but every
    # condition is computed regardless so the robustness check (which reuses
    # this function under a different mode) always has C1-C6 available). ---
    c1 = control_drop["pp"] >= 10 and control_drop["chain_level_p"] < ALPHA and control_drop["document_level_p"] < ALPHA
    c2 = direct["pp"] > 0 and direct["chain_level_p"] < ALPHA and direct["document_level_p"] < ALPHA
    c3 = keep_survival["pp"] > 0 and keep_survival["chain_level_p"] < ALPHA and keep_survival["document_level_p"] < ALPHA
    c4 = (
        drop_difference["pp"] >= 10
        and drop_difference["chain_level_p"] < ALPHA
        and drop_difference["document_level_p"] < ALPHA
    )
    c5_ok = c5["held"]
    c6 = public_only["control_drop_pp"] > 0 and public_only["direct_pp"] > 0

    confirming = (not disconfirming) and c1 and c2 and c3 and c4 and c5_ok and c6

    if disconfirming:
        verdict = "DISCONFIRMING"
    elif confirming:
        verdict = "CONFIRMING"
    else:
        verdict = "INCONCLUSIVE"

    # Section 6.4: "every primary p is expected to be exact ... a non-exact
    # primary p is reported as a deviation" -- reported, never a hard failure.
    deviations = []
    for name, exact_flag in (
        ("control_drop.chain_level", control_drop["chain_level_exact"]),
        ("control_drop.document_level", control_drop["document_level_exact"]),
        ("treatment_drop.chain_level", treatment_drop["chain_level_exact"]),
        ("treatment_drop.document_level", treatment_drop["document_level_exact"]),
        ("direct.chain_level", direct["chain_level_exact"]),
        ("direct.document_level", direct["document_level_exact"]),
        ("keep_survival.chain_level", keep_survival["chain_level_exact"]),
        ("keep_survival.document_level", keep_survival["document_level_exact"]),
        ("drop_difference.chain_level", drop_difference["chain_level_exact"]),
        ("drop_difference.document_level", drop_difference["document_level_exact"]),
    ):
        if exact_flag is False:
            deviations.append(f"{name} p-value is not exact (Monte Carlo fallback) -- protocol section 6.4 deviation")

    return {
        "verdict": verdict,
        "sub_label": sub_label,
        "conditions": {
            "D1_direct_not_significant_or_non_positive": d1,
            "D2_both_drops_null": d2,
            "D3_treatment_drop_at_least_control_drop": d3,
            "C1_control_drop": c1,
            "C2_direct": c2,
            "C3_keep_survival": c3,
            "C4_drop_difference": c4,
            "C5_grader_and_render_gate_bounds": c5_ok,
            "C6_public_documents_only": c6,
        },
        "numbers": {
            "d_documents_at_document_level": d_documents,
            "control_drop": control_drop,
            "treatment_drop": treatment_drop,
            "direct": direct,
            "keep_survival": keep_survival,
            "drop_difference": drop_difference,
            "public_documents_only": public_only,
            "c5_detail": c5,
        },
        "deviations": deviations,
    }


def robustness_label(stats_by_mode: dict[str, dict[str, Any]], primary_verdict: str) -> tuple[str, dict[str, Any] | None]:
    """Section 5.2: "A CONFIRMING verdict is labelled robust to freeze
    scoring if conditions C1-C4 and C6 of section 7 also hold under
    `exclude`, and dependent on freeze scoring otherwise." Only meaningful
    for a CONFIRMING verdict."""
    if primary_verdict != "CONFIRMING":
        return "not_applicable", None
    alt = evaluate(stats_by_mode, ROBUSTNESS_ALT_MODE)
    conds = alt["conditions"]
    # Section 5.2 names exactly C1-C4 and C6 for this label (not C3's sibling
    # "keep_survival" wording confusion -- C3 IS one of C1-C4 here since the
    # protocol's "C1-C4" is a contiguous numeric range that includes C3).
    robust = (
        conds["C1_control_drop"] and conds["C2_direct"] and conds["C3_keep_survival"]
        and conds["C4_drop_difference"] and conds["C6_public_documents_only"]
    )
    label = "robust_to_freeze_scoring" if robust else "dependent_on_freeze_scoring"
    return label, alt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--statistics-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        stats_by_mode = load_statistics_files(args.statistics_dir)
        primary = evaluate(stats_by_mode, PRIMARY_MODE)
        label, alt = robustness_label(stats_by_mode, primary["verdict"])
    except VerdictInputError as exc:
        print(f"respec_rerun_verdict: cannot compute a verdict -- {exc}", file=sys.stderr)
        return 2

    report = {
        "schema": "paper-s25-respec-cascade-verdict-v1",
        "primary_frozen_chain_mode": PRIMARY_MODE,
        "robustness_alt_frozen_chain_mode": ROBUSTNESS_ALT_MODE,
        "verdict": primary["verdict"],
        "sub_label": primary["sub_label"],
        "freeze_scoring_robustness_label": label,
        "conditions": primary["conditions"],
        "numbers": primary["numbers"],
        "deviations": primary["deviations"],
        "robustness_alt_mode_conditions": alt["conditions"] if alt else None,
        "robustness_alt_mode_numbers": alt["numbers"] if alt else None,
        "statistics_dir": str(args.statistics_dir),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n=== PAPER-S25 section 7 verdict: {report['verdict']} "
          f"(sub-label: {report['sub_label']}, freeze-scoring: {report['freeze_scoring_robustness_label']}) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
