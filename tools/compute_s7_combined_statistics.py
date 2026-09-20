"""Merges the multi-anchor extension's new trial points into the already-
published original-corpus per-document outcomes, then reports the same
3-tier aggregation (tools/compute_multianchor_extension_statistics.py) over
the COMBINED per-document data -- the integration deliberately deferred when
that module was first written, now done with the canonical original-corpus
source identified and verified.

Canonical original-corpus source (verified, not guessed): for equation and
caption, `D:/MeridianData/ooxml-graph-paper/runs/paper-s7-clean-rerun-runpod/
runs/paper-s7-clean-rerun/{primary_holdout,validation}/slice-manifest.json`
-- confirmed by loading `s7-final-statistics-runpod.json` from that same run
and checking its numbers match paper/main.tex's Table~\ref{tab:render-gate-clean}
EXACTLY (equation 100%/100% N=26/26 p=1.0, caption 100%/100% N=26/26 p=1.0,
both confirmatory/dedicated-host, the paper's own stated load-bearing table
for these families -- see Section~\ref{sec:limitations}, second factor).
Each manifest chain's `doc_label` field is the FULL, untruncated original
document label (only the on-disk directory name was truncated for Windows
path-length reasons) -- directly matches the extension's own
`original_doc_label` field with no further normalization needed, verified
directly against a real entry before trusting this as the join key.

table_structural has no multi-anchor extension (never run for that family),
so it is intentionally excluded here -- nothing to merge for it.

section_reorder is NOT handled by this script: its currently-published
"combined" number is itself already a two-corpus merge (11-document original
+ 48-document independently-preregistered follow-up, with an asymmetric
N=55 control / N=56 treatment from one further disclosed exclusion --
Table~\ref{tab:single-edit}), a materially more complex provenance question
than equation/caption's single clean confirmatory-rerun manifest. Handled
separately once that source is verified with the same rigor, not guessed
here just to produce a number.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_s7_statistics import _chain_outcome, load_chains  # noqa: E402
from compute_multianchor_extension_statistics import (  # noqa: E402
    load_family_chains, weighted_bootstrap_ci, weighted_paired_permutation_test,
    estimate_icc_and_effective_n,
)
from graph_scorer import bootstrap_ci, paired_permutation_test  # noqa: E402


def original_corpus_by_doc(manifest_paths: list[Path], family: str) -> dict[str, dict[str, float]]:
    """arm -> doc_label -> outcome, for one family, from the ORIGINAL corpus's
    own already-validated chain data (single K=1 anchor per document)."""
    chains = load_chains(manifest_paths)
    by_arm: dict[str, dict[str, float]] = {"control": {}, "treatment": {}}
    for chain in chains:
        if chain["family"] != family or chain["k_pairs"] != 1:
            continue
        outcome = _chain_outcome(chain)
        if outcome is None:
            continue
        by_arm[chain["arm"]][chain["doc_label"]] = outcome
    return by_arm


def combine(
    original_by_arm: dict[str, dict[str, float]],
    extension_by_arm: dict[str, dict[str, list[float]]],
) -> dict[str, dict[str, list[float]]]:
    """Concatenates each document's original single outcome (if any) with its
    extension anchors (if any) into one combined per-document outcome list,
    per arm. A document present in only one source still gets a valid list
    from that source alone."""
    combined: dict[str, dict[str, list[float]]] = {"control": {}, "treatment": {}}
    for arm in ("control", "treatment"):
        docs = set(original_by_arm[arm]) | set(extension_by_arm[arm])
        for doc in docs:
            values: list[float] = []
            if doc in original_by_arm[arm]:
                values.append(original_by_arm[arm][doc])
            if doc in extension_by_arm[arm]:
                values.extend(extension_by_arm[arm][doc])
            combined[arm][doc] = values
    return combined


def compute_combined_tiers(combined_by_arm: dict[str, dict[str, list[float]]]) -> dict[str, Any]:
    control_by_doc, treatment_by_doc = combined_by_arm["control"], combined_by_arm["treatment"]

    def per_doc_means(by_doc: dict[str, list[float]]) -> dict[str, float]:
        return {doc: sum(vs) / len(vs) for doc, vs in by_doc.items()}

    control_means = per_doc_means(control_by_doc)
    treatment_means = per_doc_means(treatment_by_doc)

    tier1_control_values = list(control_means.values())
    tier1_treatment_values = list(treatment_means.values())
    paired_docs = sorted(set(control_means) & set(treatment_means))
    tier1 = {
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
            "The naive pooled CI above treats every anchor (original single anchor plus every "
            "extension anchor) as an independent observation, which OVERSTATES precision -- "
            "anchors from the same document share document-level confounds. The *_clustering "
            "fields give the ICC-corrected effective N; treat that, not the naive pooled N, as "
            "the honest sample size for this tier."
        ),
    }

    return {
        "tier1_per_document_unweighted": tier1,
        "tier2_anchor_weighted_document_mean": tier2,
        "tier3_pooled_anchor_level": tier3,
        "n_distinct_documents": {"control": len(control_means), "treatment": len(treatment_means)},
        "anchors_per_document_distribution": {
            "control": {doc: len(vs) for doc, vs in control_by_doc.items()},
            "treatment": {doc: len(vs) for doc, vs in treatment_by_doc.items()},
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--original-manifests", nargs="+", required=True, type=Path)
    parser.add_argument("--extension-run-root", required=True, type=Path)
    parser.add_argument("--families", nargs="+", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    report = {
        "schema": "paper-s7-combined-statistics-v1",
        "scope": (
            "Original corpus (confirmatory dedicated-host re-run) merged with the multi-anchor "
            "extension's new trial points, per document. table_structural and section_reorder "
            "are not included -- see module docstring for why."
        ),
        "families": {},
    }
    for family in args.families:
        original_by_arm = original_corpus_by_doc(args.original_manifests, family)
        ext_chains, ext_mapping = load_family_chains(args.extension_run_root, family)
        from compute_multianchor_extension_statistics import group_by_original_document
        extension_by_arm = group_by_original_document(ext_chains, ext_mapping)
        combined = combine(original_by_arm, extension_by_arm)
        report["families"][family] = compute_combined_tiers(combined)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
