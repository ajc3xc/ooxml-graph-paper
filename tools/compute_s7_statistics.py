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
from graph_scorer import bootstrap_ci, paired_permutation_test  # noqa: E402


def _chain_outcome(chain: dict[str, Any]) -> float | None:
    """1.0 if every pair in the chain passed both forward and inverse
    grading, 0.0 if the chain completed but any pair failed, None if the
    chain never executed at all (not_applicable/blocked-before-any-pair-ran/
    harness_exception) -- a None is excluded from BOTH arms' denominators for
    that (document, family, k) pair, per the protocol's own not_applicable
    exclusion rule, rather than scored as a 0."""
    status = chain.get("status")
    if status == "not_applicable":
        return None
    if status == "harness_exception":
        return None
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


def _chain_steady_state_outcome(chain: dict[str, Any]) -> float | None:
    """For K>1 chains only: pass rate over pairs[1:], excluding the first
    pair. Bibliography's first-ever use on a document always fails the
    strict exact-restoration check (the disclosed References-heading
    residue, symmetric across arms -- see docs/paper-s22-harness-
    verification-v1.md's correction), which would otherwise make EVERY K=4
    bibliography chain register as a flat 0.0 under _chain_outcome and
    obscure whether genuine cumulative drift exists once past that one
    known, one-time side effect. Returns None for k_pairs<2, or for chains
    that never applied/executed at all."""
    if chain.get("k_pairs", 1) < 2:
        return None
    status = chain.get("status")
    if status in ("not_applicable", "harness_exception"):
        return None
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


def compute_statistics(chains: list[dict[str, Any]]) -> dict[str, Any]:
    by_group: dict[tuple[str, int], dict[str, dict[str, float]]] = {}
    steady_state_by_group: dict[tuple[str, int], dict[str, dict[str, float]]] = {}
    not_applicable_counts: dict[tuple[str, int], int] = {}

    for chain in chains:
        family = chain["family"]
        k = chain["k_pairs"]
        arm = chain["arm"]
        doc_label = chain["doc_label"]
        key = (family, k)

        outcome = _chain_outcome(chain)
        if outcome is None:
            not_applicable_counts[key] = not_applicable_counts.get(key, 0) + 1
        else:
            by_group.setdefault(key, {"control": {}, "treatment": {}})
            by_group[key][arm][doc_label] = outcome

        steady_outcome = _chain_steady_state_outcome(chain)
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
        })

    return {
        "schema": "paper-s7-statistics-v1",
        "chain_count": len(chains),
        "groups": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slice_manifests", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    chains = load_chains(args.slice_manifests)
    stats = compute_statistics(chains)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
