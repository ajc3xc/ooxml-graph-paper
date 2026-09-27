"""PAPER-S7 section 7: pass-rate bootstrap CIs + paired control-vs-treatment
significance, reusing tools/graph_scorer.py's existing bootstrap_ci and
paired_permutation_test UNMODIFIED (confirmed reusable as-is on 0/1 pass/fail
outcomes by PAPER-S7 recon, 2026-08-30 -- see docs/paper-s7-protocol-v1.md
section 7). Computed over validation+primary_holdout slice manifests combined,
per (family, k_pairs), never over a single slice alone.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_scorer import bootstrap_ci, paired_permutation_test, paired_permutation_test_exact  # noqa: E402

# A chain that stopped before finishing, by cause. "blocked" is every such
# chain written before 2026-09-25 (cause not recorded); run_chain now writes
# one status per cause (see run_paper_s7_benchmark's STATUS_BLOCKED_*). By
# default every one of them is treated exactly as "blocked" always was.
BLOCKED_STATUSES = frozenset({
    "blocked", "blocked_timeout", "blocked_forward_failed", "blocked_unreadable_input",
    "blocked_inverse_unresolvable",
})
# Never an outcome under any policy: not applicable, a harness crash, an
# infrastructure failure (run_chain's infra_blocked; infra_excluded once the
# rerun limit is reached) or a chain the sweep's circuit breaker stopped.
_NEVER_SCORED_STATUSES = frozenset({
    "not_applicable", "harness_exception", "infra_blocked", "infra_excluded", "aborted_circuit_open",
})

# How a blocked chain enters the outcome (--blocked-policy; review item 22,
# S25 5.5 / S26 section 5):
#   "exclude" -- (default) no outcome: dropped from both arms' denominators
#                for that pair, the behavior every stored source was computed
#                with, so they regenerate byte-identically.
#   "fail"    -- 0.0 unless the chain carries an infrastructure signature
#                (run_chain would have written infra_blocked; for a legacy
#                "blocked" chain every recorded trial is classified with
#                claude_pair_runner.classify_infra_signature), which stays
#                excluded. A timeout, an unreadable next input or an
#                unresolvable forward output is the arm's own failure.
BLOCKED_POLICIES: tuple[str, ...] = ("exclude", "fail")
DEFAULT_BLOCKED_POLICY = "exclude"


def _check_blocked_policy(blocked_policy: str) -> None:
    if blocked_policy not in BLOCKED_POLICIES:
        raise ValueError(f"unknown blocked_policy {blocked_policy!r}; expected one of {BLOCKED_POLICIES}")


def _blocked_chain_infra_signature(chain: dict[str, Any]) -> dict[str, Any] | None:
    """The first infrastructure signature among a blocked chain's recorded
    trials: the chain-level one run_chain records, else each trial's own
    `infra_signature`, else (legacy runs) a classification of the stored
    trial fields."""
    if chain.get("infra_signature"):
        return chain["infra_signature"]
    from claude_pair_runner import classify_infra_signature  # noqa: PLC0415 -- only needed for this policy

    for pair in chain.get("pairs") or []:
        for direction in ("forward", "inverse"):
            trial = pair.get(direction)
            if not isinstance(trial, dict):
                continue
            signature = trial.get("infra_signature") or classify_infra_signature(trial)
            if signature:
                return {**signature, "trial_id": trial.get("trial_id")}
    return None


def _blocked_outcome(chain: dict[str, Any], blocked_policy: str) -> float | None:
    """None under "exclude"; under "fail", 0.0 unless the chain has an
    infrastructure signature (then None)."""
    if blocked_policy == "exclude":
        return None
    return None if _blocked_chain_infra_signature(chain) else 0.0


def _scored_as_failure(chain: dict[str, Any], score_as_failure: frozenset[str]) -> bool:
    """True when this chain is on the explicit score-as-failure list. Only a
    "blocked" (timed-out) chain may be listed: the override exists for a timeout
    judged to be the arm's own task failure rather than an infrastructure flake
    (paper Appendix Note b), not to rescore chains that have a grading verdict.
    Any status of BLOCKED_STATUSES qualifies."""
    if chain.get("chain_id") not in score_as_failure:
        return False
    if chain.get("status") not in BLOCKED_STATUSES:
        raise ValueError(f"{chain.get('chain_id')}: only a blocked chain can be scored as a failure, "
                         f"this one is {chain.get('status')!r}")
    return True


def _chain_outcome(chain: dict[str, Any], score_as_failure: frozenset[str] = frozenset(),
                   blocked_policy: str = DEFAULT_BLOCKED_POLICY) -> float | None:
    """1.0 if every pair in the chain passed both forward and inverse
    grading, 0.0 if the chain completed but any pair failed, None if the
    chain never executed at all or never finished (not_applicable/blocked/
    harness_exception) -- a None is excluded from BOTH arms' denominators for
    that (document, family, k) pair, per the protocol's own not_applicable
    exclusion rule, rather than scored as a 0.

    "blocked" must be excluded here, not just at not_applicable/
    harness_exception: found live (2026-09-04) on a real K=4 v2-corpus run --
    a chain that hit a genuine 300s subprocess timeout mid-chain still has a
    pair entry recorded for the trial that never actually completed (no
    grading verdict, since there was no valid output to grade), so the old
    "if not pairs: return None" guard never caught it and the loop below fell
    through to scoring an infra timeout as a real 0.0 task failure. The
    harness's own checkpoint/resume logic (_load_checkpoint) already treats
    "blocked" as never trustworthy for exactly this reason; this function
    must agree with that, not silently contradict it.

    A blocked chain named in score_as_failure is scored 0.0 instead.

    2026-09-25: every status of BLOCKED_STATUSES is handled as "blocked"
    (None by default; see BLOCKED_POLICIES for `blocked_policy="fail"`), and
    infra_blocked / infra_excluded / aborted_circuit_open are never scored,
    like harness_exception."""
    _check_blocked_policy(blocked_policy)
    if _scored_as_failure(chain, score_as_failure):
        return 0.0
    status = chain.get("status")
    if status in _NEVER_SCORED_STATUSES:
        return None
    if status in BLOCKED_STATUSES:
        return _blocked_outcome(chain, blocked_policy)
    pairs = chain.get("pairs") or []
    if not pairs:
        return None
    for pair in pairs:
        fwd_verdict = (pair.get("forward") or {}).get("grading", {}).get("verdict")
        if fwd_verdict != "pass":
            return 0.0
        inverse = pair.get("inverse")
        if inverse is None:
            return 0.0
        inv_verdict = inverse.get("grading", {}).get("verdict")
        if inv_verdict != "pass":
            return 0.0
    return 1.0


def _pair_passed(pair: dict[str, Any]) -> bool:
    if (pair.get("forward") or {}).get("grading", {}).get("verdict") != "pass":
        return False
    inverse = pair.get("inverse")
    if inverse is None:
        return False
    return inverse.get("grading", {}).get("verdict") == "pass"


def _chain_steady_state_outcome(chain: dict[str, Any], score_as_failure: frozenset[str] = frozenset(),
                                blocked_policy: str = DEFAULT_BLOCKED_POLICY) -> float | None:
    """For K>1 chains only: pass rate over pairs[1:], excluding the first
    pair. Bibliography's first-ever use on a document always fails the
    strict exact-restoration check (the disclosed References-heading
    residue, symmetric across arms -- see docs/paper-s22-harness-
    verification-v1.md's correction), which would otherwise make EVERY K=4
    bibliography chain register as a flat 0.0 under _chain_outcome and
    obscure whether genuine cumulative drift exists once past that one
    known, one-time side effect. Returns None for k_pairs<2, or for chains
    that never applied/executed at all; 0.0 for a blocked chain named in
    score_as_failure, which never reached its later pairs. Blocked statuses
    follow `blocked_policy` as in _chain_outcome (under "fail" a blocked
    chain never reached its later pairs, so it scores 0.0)."""
    _check_blocked_policy(blocked_policy)
    if chain.get("k_pairs", 1) < 2:
        return None
    if _scored_as_failure(chain, score_as_failure):
        return 0.0
    status = chain.get("status")
    if status in _NEVER_SCORED_STATUSES:
        return None
    if status in BLOCKED_STATUSES:
        return _blocked_outcome(chain, blocked_policy)
    pairs = chain.get("pairs") or []
    steady_state_pairs = pairs[1:]
    if not steady_state_pairs:
        return None
    passed = sum(1 for p in steady_state_pairs if _pair_passed(p))
    return passed / len(steady_state_pairs)


def load_chains(slice_manifest_paths: list[Path]) -> list[dict[str, Any]]:
    chains: list[dict[str, Any]] = []
    for path in slice_manifest_paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        chains.extend(manifest["chains"])
    return chains


def compute_statistics(chains: list[dict[str, Any]],
                       score_as_failure: frozenset[str] = frozenset(),
                       blocked_policy: str = DEFAULT_BLOCKED_POLICY) -> dict[str, Any]:
    _check_blocked_policy(blocked_policy)
    unknown = score_as_failure - {c.get("chain_id") for c in chains}
    if unknown:
        raise ValueError(f"--score-as-failure names chains not in these manifests: {sorted(unknown)}")
    by_group: dict[tuple[str, int], dict[str, dict[str, float]]] = {}
    steady_state_by_group: dict[tuple[str, int], dict[str, dict[str, float]]] = {}
    not_applicable_counts: dict[tuple[str, int], int] = {}

    for chain in chains:
        family = chain["family"]
        k = chain["k_pairs"]
        arm = chain["arm"]
        doc_label = chain["doc_label"]
        key = (family, k)

        outcome = _chain_outcome(chain, score_as_failure, blocked_policy)
        if outcome is None:
            not_applicable_counts[key] = not_applicable_counts.get(key, 0) + 1
        else:
            by_group.setdefault(key, {"control": {}, "treatment": {}})
            by_group[key][arm][doc_label] = outcome

        steady_outcome = _chain_steady_state_outcome(chain, score_as_failure, blocked_policy)
        if steady_outcome is not None:
            steady_state_by_group.setdefault(key, {"control": {}, "treatment": {}})
            steady_state_by_group[key][arm][doc_label] = steady_outcome

    results = []
    for (family, k), arms in sorted(by_group.items()):
        control_by_doc = arms["control"]
        treatment_by_doc = arms["treatment"]

        control_values = list(control_by_doc.values())
        treatment_values = list(treatment_by_doc.values())
        control_ci = bootstrap_ci(control_values) if control_values else None
        treatment_ci = bootstrap_ci(treatment_values) if treatment_values else None

        paired_docs = sorted(set(control_by_doc) & set(treatment_by_doc))
        paired_a = [control_by_doc[d] for d in paired_docs]
        paired_b = [treatment_by_doc[d] for d in paired_docs]
        significance = (
            paired_permutation_test(paired_a, paired_b) if len(paired_docs) >= 2 else None
        )
        # P-K1: the exact-enumeration counterpart the protocol's primary test
        # requires (section 6.1: "the result's `exact` flag must be true").
        # Kept alongside, not instead of, the as-run Monte Carlo field above --
        # that field is what the published p continues from (section 6.3),
        # this one is what k4_replication_verdict.py's confirmatory rule reads.
        significance_exact = (
            paired_permutation_test_exact(paired_a, paired_b) if len(paired_docs) >= 2 else None
        )

        steady_arms = steady_state_by_group.get((family, k), {"control": {}, "treatment": {}})
        steady_control_values = list(steady_arms["control"].values())
        steady_treatment_values = list(steady_arms["treatment"].values())
        steady_state = {
            "note": (
                "Pass rate over pairs[1:] only (excludes the first pair), isolating "
                "whether repeated cycling introduces NEW drift once past any known "
                "one-time first-use side effect (e.g. bibliography's References-heading "
                "residue, which affects both arms equally on pair 0) -- None if k_pairs<2."
            ),
            "control_n": len(steady_control_values),
            "control_pass_rate_ci": bootstrap_ci(steady_control_values) if steady_control_values else None,
            "treatment_n": len(steady_treatment_values),
            "treatment_pass_rate_ci": bootstrap_ci(steady_treatment_values) if steady_treatment_values else None,
        } if k >= 2 else None

        results.append({
            "family": family,
            "k_pairs": k,
            "not_applicable_count": not_applicable_counts.get((family, k), 0),
            "control_n": len(control_values),
            "control_pass_rate_ci": control_ci,
            "treatment_n": len(treatment_values),
            "treatment_pass_rate_ci": treatment_ci,
            "steady_state_pairs_1_plus": steady_state,
            "paired_n": len(paired_docs),
            "paired_control_vs_treatment_significance": significance,
            "paired_control_vs_treatment_significance_exact": significance_exact,
        })

    stats: dict[str, Any] = {
        "schema": "paper-s7-statistics-v1",
        "chain_count": len(chains),
        "groups": results,
    }
    if score_as_failure:
        stats["scored_as_failure"] = sorted(score_as_failure)
    if blocked_policy != DEFAULT_BLOCKED_POLICY:
        # Recorded whenever it is not the default (the default is left out so
        # every stored source regenerates byte-identically).
        blocked = [c for c in chains if c.get("status") in BLOCKED_STATUSES
                   and c.get("chain_id") not in score_as_failure]
        stats["blocked_policy"] = {
            "policy": blocked_policy,
            "rule": "a blocked chain scores 0 unless it has an infrastructure signature, which stays excluded",
            "blocked_scored_as_failure": sorted(
                str(c.get("chain_id")) for c in blocked if _blocked_outcome(c, blocked_policy) == 0.0
            ),
            "blocked_excluded_infrastructure": sorted(
                str(c.get("chain_id")) for c in blocked if _blocked_outcome(c, blocked_policy) is None
            ),
        }
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slice_manifests", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--score-as-failure", action="append", default=[], metavar="CHAIN_ID",
                        help="score this blocked (timed-out) chain as a failure instead of excluding it; repeatable")
    parser.add_argument("--blocked-policy", "--timeout-policy", dest="blocked_policy", choices=BLOCKED_POLICIES,
                        default=DEFAULT_BLOCKED_POLICY,
                        help="how a blocked chain (any blocked* status) is scored: 'exclude' (default, how every "
                             "stored source was computed) or 'fail' (0 unless it has an infrastructure signature). "
                             "A non-default policy is recorded in the output.")
    args = parser.parse_args(argv)

    chains = load_chains(args.slice_manifests)
    stats = compute_statistics(chains, frozenset(args.score_as_failure), args.blocked_policy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
