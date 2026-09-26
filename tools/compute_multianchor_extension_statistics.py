"""Multi-anchor extension statistics: per-document, anchor-weighted, and pooled
tiers, computed over the NEW extension trial points only (NOT yet merged with
the already-published original single-anchor corpus -- see the module-level
note at the bottom of this file for why that merge is deliberately deferred).

Three reporting tiers, directly adapted from the precedent already used and
validated in the user's own MS dissertation (Appendix A, "Reporting
aggregation families" -- per-image mean / length-weighted mean / pooled
pointwise, kept as three separate, distinctly-labeled tiers rather than
conflated even when built from the same underlying observations):

  Tier 1 (per-document mean, unweighted): one summary value per ORIGINAL
    document (the mean outcome across however many extension anchors that
    document got), then every document counts equally regardless of how many
    anchors it contributed. Most conservative; N = document count. Uses
    graph_scorer.bootstrap_ci / paired_permutation_test UNMODIFIED -- this is
    exactly the same shape of input those functions already validate against
    (one float per document), just built from extension-anchor means instead
    of single-anchor outcomes.

  Tier 2 (anchor-count-weighted document mean): same one-value-per-document
    summaries as Tier 1, but each document's outer weight in the combined
    mean is how many extension anchors it actually contributed -- documents
    with more real trials get proportionally more say, without treating each
    anchor as a fully independent sample. New weighted-bootstrap/weighted-
    permutation code (below), kept clearly separate from graph_scorer.py's
    own validated, UNMODIFIED functions used for the original corpus.

  Tier 3 (pooled, anchor-level): every (document, anchor) pair as its own
    observation -- what you get if you naively feed this data through the
    existing per-document machinery unchanged, since doc_label is already
    anchor-unique for the extension. Narrowest naive CI, most exposed to
    within-document clustering (anchors from the same document are not fully
    independent). Reported alongside a design-effect-corrected EFFECTIVE N
    (one-way random-effects ICC via Fleiss's unbalanced-design ANOVA
    correction), so the naive pooled N is never presented without the
    clustering-aware number beside it.

Usage:
    python compute_multianchor_extension_statistics.py \
        --run-root D:/MeridianData/ooxml-graph-paper/runs/paper-s7-multi-anchor-extension/runs \
        --families section_reorder equation caption \
        --out D:/MeridianData/ooxml-graph-paper/runs/paper-s7-multi-anchor-extension/statistics.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_s7_statistics import _chain_outcome  # noqa: E402 -- reuse the exact, already-validated outcome rule
from graph_scorer import bootstrap_ci, paired_permutation_test  # noqa: E402 -- reused UNMODIFIED for tiers 1 and 3

_SEED = 20260828  # same seed graph_scorer.py uses, for consistency across tiers
_RESAMPLES = 2000


def load_family_chains(run_root: Path, family: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Returns (chain_results, doc_label -> mapping entry) for one family."""
    family_root = run_root / family
    mapping = {
        m["doc_label"]: m
        for m in json.loads((family_root / "doc_label_mapping.json").read_text(encoding="utf-8"))
    }
    chains = []
    for chain_dir in sorted(family_root.iterdir()):
        cr = chain_dir / "chain-result.json"
        if cr.is_file():
            chains.append(json.loads(cr.read_text(encoding="utf-8")))
    return chains, mapping


def group_by_original_document(
    chains: list[dict[str, Any]], mapping: dict[str, dict[str, Any]],
) -> dict[str, dict[str, list[float]]]:
    """arm -> original_doc_label -> [outcome, outcome, ...] (one per extension anchor)."""
    grouped: dict[str, dict[str, list[float]]] = {"control": {}, "treatment": {}}
    for chain in chains:
        outcome = _chain_outcome(chain)
        if outcome is None:
            continue
        arm = chain["arm"]
        doc_label = chain["doc_label"]
        m = mapping.get(doc_label)
        if m is None:
            continue  # not part of this extension's own mapping -- skip rather than guess
        orig = m["original_doc_label"]
        grouped[arm].setdefault(orig, []).append(outcome)
    return grouped


# ---------------------------------------------------------------------------
# Tier 2: anchor-count-weighted per-document mean -- new code, kept separate
# from graph_scorer.py's own validated, unmodified functions.
# ---------------------------------------------------------------------------

def weighted_mean(items: list[tuple[float, float]]) -> float | None:
    """items: [(value, weight), ...]. None if total weight is 0."""
    total_w = sum(w for _, w in items)
    if total_w == 0:
        return None
    return sum(v * w for v, w in items) / total_w


def weighted_bootstrap_ci(
    items: list[tuple[float, float]], n_resamples: int = _RESAMPLES, alpha: float = 0.05, seed: int = _SEED,
) -> dict[str, Any]:
    """Cluster bootstrap: resample DOCUMENTS (not anchors) with replacement --
    each resample redraws whole (per-document mean, weight) pairs, so between-
    document variability is what drives the interval, matching the actual
    unit of (quasi-)independence -- then reports the WEIGHTED mean of each
    resample, using the documents' own natural anchor-count weights. This is
    the standard cluster-bootstrap-for-a-weighted-statistic construction, not
    a naive unweighted percentile bootstrap over anchors.

    Deliberately does NOT special-case the zero-variance boundary the way
    graph_scorer.bootstrap_ci does (that correction is specific to a binary
    0/1 UNWEIGHTED proportion -- see that function's own docstring); a
    weighted mean of continuous per-document rates only degenerates in the
    same way if literally every document is uniformly all-pass or all-fail,
    an edge case not handled specially here.
    """
    clean = [it for it in items if it[0] is not None]
    if len(clean) < 2:
        point = weighted_mean(clean) if clean else None
        return {"mean": point, "ci_low": None, "ci_high": None, "n_documents": len(clean),
                "reason": "fewer than 2 documents -- CI undefined"}
    rng = random.Random(seed)
    n = len(clean)
    means = []
    for _ in range(n_resamples):
        resample = [clean[rng.randrange(n)] for _ in range(n)]
        m = weighted_mean(resample)
        if m is not None:
            means.append(m)
    means.sort()
    lo_idx = int((alpha / 2) * len(means))
    hi_idx = int((1 - alpha / 2) * len(means)) - 1
    point = weighted_mean(clean)
    return {
        "mean": point,
        "ci_low": means[lo_idx] if means else None,
        "ci_high": means[min(hi_idx, len(means) - 1)] if means else None,
        "n_documents": n,
        "total_weight": sum(w for _, w in clean),
        "confidence_level": 1 - alpha,
        "n_resamples": n_resamples,
        "method": "weighted_cluster_bootstrap",
    }


def weighted_paired_permutation_test(
    control_items: list[tuple[float, float]], treatment_items: list[tuple[float, float]],
    n_permutations: int = _RESAMPLES, seed: int = _SEED,
) -> dict[str, Any]:
    """Weighted generalization of graph_scorer.paired_permutation_test's own
    sign-flip logic: each paired document contributes weight*(control-
    treatment) to the observed statistic; under the null, each document's
    sign is independently flip-able (same assumption the unweighted test
    already makes), so the permutation null distribution is built the same
    way, just weighted. control_items/treatment_items are already aligned by
    caller (same document order, same weights on both sides -- weight is a
    property of the document, not the arm)."""
    # Known issue, left as is because reported statistics depend on it: the
    # weight used for both arms is CONTROL's (`w`); treatment's own weight
    # (`_w2`) is discarded. The docstring's "same weights on both sides" holds
    # only when both arms kept the same number of observations per document.
    # When they differ (e.g. chains excluded on one arm only), both the
    # observed weighted mean diff and, in general, the p-value are weighted
    # by control's counts. Checked 2026-09-25 against the stored
    # respec_cascade statistics: only observed_weighted_mean_diff moves, no
    # p-value does, and no number the paper reports changes.
    diffs_weights = [
        (c - t, w) for (c, w), (t, _w2) in zip(control_items, treatment_items)
        if c is not None and t is not None
    ]
    if len(diffs_weights) < 2:
        return {"observed_weighted_mean_diff": None, "p_value": None,
                "n_paired_documents": len(diffs_weights),
                "reason": "fewer than 2 paired documents with values on both sides"}
    total_w = sum(w for _, w in diffs_weights)
    observed = sum(d * w for d, w in diffs_weights) / total_w
    rng = random.Random(seed)
    extreme_count = 0
    for _ in range(n_permutations):
        flipped_sum = sum((d if rng.random() < 0.5 else -d) * w for d, w in diffs_weights)
        if abs(flipped_sum / total_w) >= abs(observed):
            extreme_count += 1
    p_value = extreme_count / n_permutations
    return {
        "observed_weighted_mean_diff": observed,
        "p_value": p_value,
        "n_paired_documents": len(diffs_weights),
        "n_permutations": n_permutations,
        "method": "weighted paired sign-flip permutation test",
    }


# ---------------------------------------------------------------------------
# Tier 3 diagnostic: one-way random-effects ICC (Fleiss unbalanced-design
# correction) -> design effect -> effective N, alongside the naive pooled CI.
# ---------------------------------------------------------------------------

def estimate_icc_and_effective_n(values_by_doc: dict[str, list[float]]) -> dict[str, Any]:
    """One-way random-effects intraclass correlation from real cluster data
    (Shrout & Fleiss ICC(1) via one-way ANOVA), with Fleiss's (1986) k0
    correction for unequal cluster sizes (documents don't all have the same
    number of extension anchors) used in the ICC estimate itself. The design
    effect does NOT use k0: design_effect = 1 + (m-1)*ICC with m the simple
    mean cluster size, naive_pooled_n / k_clusters (the Kish design effect
    for a clustered mean, as coded below); effective_n = naive_pooled_n /
    design_effect. k0 is also returned (`k0_unbalanced_avg_cluster_size`),
    and equals m when every cluster has the same size; with unequal sizes
    k0 < m, so using m gives a slightly larger design effect (smaller
    effective_n) than k0 would. A negative ICC estimate (can happen with
    small/noisy samples) is clamped to 0 -- a negative "within-cluster
    similarity" isn't interpretable as inflating variance and would produce a
    design effect below 1, understating uncertainty; 0 means "no detectable
    clustering," the conservative reading.
    """
    clusters = [vs for vs in values_by_doc.values() if vs]
    k = len(clusters)  # number of clusters (documents)
    n_total = sum(len(vs) for vs in clusters)
    if k < 2 or n_total <= k:
        return {"icc": None, "design_effect": None, "naive_pooled_n": n_total,
                "effective_n": n_total, "k_clusters": k,
                "reason": "fewer than 2 documents, or no within-document replication -- ICC undefined"}

    grand_mean = sum(v for vs in clusters for v in vs) / n_total
    ss_between = sum(len(vs) * (sum(vs) / len(vs) - grand_mean) ** 2 for vs in clusters)
    ss_within = sum((v - sum(vs) / len(vs)) ** 2 for vs in clusters for v in vs)
    df_between = k - 1
    df_within = n_total - k
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within if df_within > 0 else 0.0

    # Fleiss (1986) unbalanced-design average cluster size.
    n_i_sq_sum = sum(len(vs) ** 2 for vs in clusters)
    k0 = (n_total - n_i_sq_sum / n_total) / df_between

    if ms_between + (k0 - 1) * ms_within == 0:
        icc = 0.0
    else:
        icc = (ms_between - ms_within) / (ms_between + (k0 - 1) * ms_within)
    icc = max(0.0, icc)

    avg_cluster_size = n_total / k
    design_effect = 1 + (avg_cluster_size - 1) * icc
    effective_n = n_total / design_effect if design_effect > 0 else n_total

    return {
        "icc": icc,
        "k0_unbalanced_avg_cluster_size": k0,
        "avg_cluster_size": avg_cluster_size,
        "design_effect": design_effect,
        "naive_pooled_n": n_total,
        "effective_n": effective_n,
        "k_clusters": k,
        "method": "one-way random-effects ICC (Shrout-Fleiss ICC(1)), Fleiss (1986) unbalanced-design correction",
    }


# ---------------------------------------------------------------------------
# Top-level per-family tiered report
# ---------------------------------------------------------------------------

def compute_family_tiers(chains: list[dict[str, Any]], mapping: dict[str, dict[str, Any]]) -> dict[str, Any]:
    grouped = group_by_original_document(chains, mapping)
    control_by_doc, treatment_by_doc = grouped["control"], grouped["treatment"]

    def per_doc_means(by_doc: dict[str, list[float]]) -> dict[str, float]:
        return {doc: sum(vs) / len(vs) for doc, vs in by_doc.items()}

    control_means = per_doc_means(control_by_doc)
    treatment_means = per_doc_means(treatment_by_doc)

    # --- Tier 1: unweighted per-document mean, existing functions unmodified.
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

    # --- Tier 2: anchor-count-weighted per-document mean.
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

    # --- Tier 3: pooled anchor-level (naive, existing functions unmodified) + ICC-corrected effective N.
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
            "The naive pooled CI above treats every anchor as an independent observation, which "
            "OVERSTATES precision -- anchors from the same document share document-level confounds "
            "(formatting, author style, content). The *_clustering fields give the ICC-corrected "
            "effective N; treat that, not the naive pooled N, as the honest sample size for this tier."
        ),
    }

    return {
        "tier1_per_document_unweighted": tier1,
        "tier2_anchor_weighted_document_mean": tier2,
        "tier3_pooled_anchor_level": tier3,
        "n_distinct_documents": {"control": len(control_means), "treatment": len(treatment_means)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--families", nargs="+", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    report = {
        "schema": "paper-s7-multianchor-extension-statistics-v1",
        "scope": (
            "EXTENSION trial points only (the new multi-anchor additions), NOT merged with the "
            "already-published original single-anchor corpus. For existing-corpus documents this "
            "means anchors 1-3 only (anchor 0's result lives in the separately-published original "
            "corpus data); for the 3 newly-added personal documents this means anchors 0-3, since "
            "they were never in the original corpus at all."
        ),
        "families": {},
    }
    for family in args.families:
        chains, mapping = load_family_chains(args.run_root, family)
        report["families"][family] = compute_family_tiers(chains, mapping)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
