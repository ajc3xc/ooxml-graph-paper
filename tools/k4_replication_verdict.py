"""PAPER-S26 (`docs/paper-s26-k4-section-reorder-confirmatory-protocol-v1.md`)
section 7: the REPLICATED / REVERSED / NOT REPLICATED decision rule, applied
mechanically (prerequisite P-K6).

Reads the two `compute_s7_statistics.py` outputs the locked `s26-statistics`
command produces: `--statistics` (scored `--blocked-policy fail`, the
primary/fail-scoring file) and `--statistics-timeouts-excluded` (scored
`--blocked-policy exclude`, the timeout-scoring-robustness file), for the
(family=section_reorder, k_pairs=4) group, and applies section 7's rule with
the timeout-scoring robustness label (section 7's last paragraph).

The primary test is `graph_scorer.paired_permutation_test_exact` (protocol
section 6.1: "the result's `exact` flag must be true"). As of this writing
`compute_s7_statistics.py` computes only the as-run Monte Carlo
`paired_control_vs_treatment_significance` field, not the exact one
(prerequisite **P-K1**: field `paired_control_vs_treatment_significance_exact`,
not yet implemented). This script REQUIRES that field and raises
`VerdictInputError` (exit 2) when it is absent -- it never falls back to the
Monte Carlo field for a confirmatory verdict; do that only to "just get a
number" is exactly the shortcut the protocol and the review process forbid.

Section 5's grader-exception adverse/favourable-bound check ("if the
verdicts differ, the verdict is NOT REPLICATED, flagged") is likewise only
evaluated when a statistics file discloses unregradable stubs; if it does,
this script fails loudly rather than guess, since resolving it needs
statistics runs this script does not have.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

FAMILY = "section_reorder"      # locked command: --families section_reorder
K_PAIRS = 4                     # locked command: --k-values 4
ALPHA = 0.05                    # section 6.1: "Two-sided, alpha = 0.05."
EXACT_FIELD = "paired_control_vs_treatment_significance_exact"   # P-K1
MONTE_CARLO_FIELD = "paired_control_vs_treatment_significance"   # as-run, never used for the verdict


class VerdictInputError(RuntimeError):
    """Raised when a field the decision rule needs is missing from the
    statistics input. Callers must not catch this to substitute a guess."""


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerdictInputError(f"{path}: could not be read as JSON ({exc})") from exc


def _find_group(stats: dict[str, Any], family: str, k_pairs: int, ctx: str) -> dict[str, Any]:
    groups = stats.get("groups")
    if groups is None:
        raise VerdictInputError(f"{ctx}: 'groups' missing from statistics")
    matches = [g for g in groups if g.get("family") == family and g.get("k_pairs") == k_pairs]
    if not matches:
        raise VerdictInputError(f"{ctx}: no group with family={family!r} k_pairs={k_pairs} in 'groups'")
    if len(matches) > 1:
        raise VerdictInputError(f"{ctx}: multiple groups with family={family!r} k_pairs={k_pairs} in 'groups'")
    return matches[0]


def _check_blocked_policy(stats: dict[str, Any], expected_policy: str, ctx: str) -> None:
    """compute_s7_statistics.py's `blocked_policy` field is present only when
    it is not the default ('exclude'), so an 'exclude'-scoring file normally
    has no such field at all -- both cases are accepted for 'exclude'."""
    tag = stats.get("blocked_policy")
    if expected_policy == "fail":
        if not tag or tag.get("policy") != "fail":
            raise VerdictInputError(
                f"{ctx}: expected statistics scored --blocked-policy fail (blocked_policy.policy=='fail'); "
                f"got blocked_policy={tag!r} -- wrong file passed as --statistics?"
            )
    else:
        if tag is not None and tag.get("policy") != "exclude":
            raise VerdictInputError(
                f"{ctx}: expected statistics scored --blocked-policy exclude; got blocked_policy={tag!r} -- "
                "wrong file passed as --statistics-timeouts-excluded?"
            )


def _exact_result(group: dict[str, Any], ctx: str) -> dict[str, Any]:
    node = group.get(EXACT_FIELD)
    if node is None:
        raise VerdictInputError(
            f"{ctx}: '{EXACT_FIELD}' missing from statistics group (family/k_pairs matched) -- "
            "prerequisite P-K1 (compute_s7_statistics.py does not yet compute the exact test) "
            f"is not implemented. Refusing to fall back to the Monte Carlo '{MONTE_CARLO_FIELD}' "
            "field for a confirmatory verdict."
        )
    if node.get("p_value") is None or node.get("observed_mean_diff") is None:
        reason = node.get("reason")
        raise VerdictInputError(
            f"{ctx}: '{EXACT_FIELD}' has no p_value/observed_mean_diff" + (f" ({reason})" if reason else "")
        )
    if node.get("exact") is not True:
        raise VerdictInputError(
            f"{ctx}: '{EXACT_FIELD}'.exact is {node.get('exact')!r}; protocol section 6.1 requires it true"
        )
    return node


def _grader_exception_check(stats: dict[str, Any], ctx: str) -> int:
    unregradable = stats.get("unregradable_grader_exception_stubs") or 0
    if unregradable:
        raise VerdictInputError(
            f"{ctx}: statistics disclose {unregradable} grader-exception stub(s) that could not "
            "be re-graded; protocol section 5 requires the verdict to be checked under the "
            "adverse and favourable bounds (verdict becomes NOT REPLICATED, flagged, if they "
            "differ), which this script does not yet compute. Refusing to guess."
        )
    return unregradable


def evaluate(stats: dict[str, Any], ctx: str, *, family: str = FAMILY, k_pairs: int = K_PAIRS,
             expected_blocked_policy: str) -> dict[str, Any]:
    _check_blocked_policy(stats, expected_blocked_policy, ctx)
    group = _find_group(stats, family, k_pairs, ctx)
    exact = _exact_result(group, ctx)
    unregradable = _grader_exception_check(stats, ctx)

    # Section 7: "Let diff = treatment rate - control rate". The exact field
    # is assumed built the same way as the existing Monte Carlo field
    # (compute_s7_statistics.compute_statistics: paired_a = control values,
    # paired_b = treatment values), so observed_mean_diff = mean(control -
    # treatment) and diff is its negation. If P-K1 is implemented with the
    # arguments swapped, update this line and this comment together.
    diff = -1.0 * exact["observed_mean_diff"]
    p_value = exact["p_value"]

    replicated = diff > 0 and p_value < ALPHA
    reversed_ = diff < 0 and p_value < ALPHA
    if replicated:
        verdict = "REPLICATED"
    elif reversed_:
        verdict = "REVERSED"
    else:
        verdict = "NOT REPLICATED"

    return {
        "verdict": verdict,
        "diff": diff,
        "p_value": p_value,
        "exact": exact.get("exact"),
        "n_paired_documents": exact.get("n_paired_documents"),
        "unregradable_grader_exception_stubs": unregradable,
        "control_n": group.get("control_n"),
        "treatment_n": group.get("treatment_n"),
        "control_pass_rate_ci": group.get("control_pass_rate_ci"),
        "treatment_pass_rate_ci": group.get("treatment_pass_rate_ci"),
        "monte_carlo_significance_for_reference_only": group.get(MONTE_CARLO_FIELD),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--statistics", required=True, type=Path,
                        help="compute_s7_statistics.py output scored --blocked-policy fail (primary).")
    parser.add_argument("--statistics-timeouts-excluded", required=True, type=Path,
                        help="compute_s7_statistics.py output scored --blocked-policy exclude (timeout-scoring robustness).")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--family", default=FAMILY)
    parser.add_argument("--k-pairs", default=K_PAIRS, type=int)
    args = parser.parse_args(argv)

    try:
        fail_stats = _load(args.statistics)
        exclude_stats = _load(args.statistics_timeouts_excluded)
        primary = evaluate(
            fail_stats, f"{args.statistics} (fail-scoring, primary)",
            family=args.family, k_pairs=args.k_pairs, expected_blocked_policy="fail",
        )
        label = "not_applicable"
        alt = None
        if primary["verdict"] == "REPLICATED":
            alt = evaluate(
                exclude_stats, f"{args.statistics_timeouts_excluded} (exclude-scoring, timeout-robustness)",
                family=args.family, k_pairs=args.k_pairs, expected_blocked_policy="exclude",
            )
            robust = alt["diff"] > 0 and alt["p_value"] < ALPHA
            label = "robust_to_timeout_scoring" if robust else "dependent_on_timeout_scoring"
    except VerdictInputError as exc:
        print(f"k4_replication_verdict: cannot compute a verdict -- {exc}", file=sys.stderr)
        return 2

    report = {
        "schema": "paper-s26-k4-replication-verdict-v1",
        "family": args.family,
        "k_pairs": args.k_pairs,
        "verdict": primary["verdict"],
        "timeout_scoring_robustness_label": label,
        "primary_fail_scoring": primary,
        "timeout_excluded_scoring": alt,
        "statistics_path": str(args.statistics),
        "statistics_timeouts_excluded_path": str(args.statistics_timeouts_excluded),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n=== PAPER-S26 section 7 verdict: {report['verdict']} "
          f"(timeout-scoring: {report['timeout_scoring_robustness_label']}) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
