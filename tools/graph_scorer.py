"""PAPER-30: graph-aware scorer for all comparator outputs.

Upgrades `run_paper15_smoke.py`'s simplified count/overlap proxy with real
node-level correspondence, precision/recall/F1 by node kind, a genuine
(non-tautological) reading-order metric, equation semantic-class accuracy
re-derived independently rather than trusted from the system under test,
bootstrap confidence intervals, and paired document-level significance
tests -- all without any dependency beyond the standard library.

## Common schema (declared explicitly, per PAPER-27/30)

Every system's output is normalized to:

    {
        "paragraphs": [{"text": str, "para_id": str | None}],   # document order
        "tables": [{"row_count": int, "col_count": int}],       # document order
        "equations": [{"omml_raw": str | None}],                # document order
        "full_text": str,
    }

`para_id` is None when the system cannot mint/preserve one (python-docx,
Docling). `omml_raw` is None when the system does not expose OMML (python-docx,
Docling) -- equation *count* can still be compared, but equation semantic-class
accuracy is `not_applicable` wherever `omml_raw` is None for every equation.

## What is and is not covered (PAPER-S5 update)

Per `graph-gold-schema-v0.md`, the full node vocabulary also includes
`package_part`, `run`, `caption`, `anchor`, `reference`, `source_binding`,
`revision`, and `render_receipt`. As of PAPER-S5, `caption` and `anchor` are
REAL, scored node kinds (`caption_node_prf1` / `anchor_node_prf1` below) --
`independent_gold_extractor.py` already produces gold `caption` nodes
(SEQ-field paragraphs), gold `anchor` nodes (`w:bookmarkStart` names), and a
resolved `caption_for` edge (nearest preceding top-level table), so these are
not a fabricated gold-vs-nothing comparison. Candidate-side support is real
but uneven, honestly reported per system:

- `caption`: native Meridian extraction (`document_content_tree`'s own
  per-paragraph `fields` list, which already parses SEQ/REF/PAGEREF/NOTEREF
  field instructions) can identify a SEQ-field paragraph as a caption, so
  this is `scored` for native Meridian. python-docx and Docling expose no
  field-instruction API at all, so this remains `not_applicable:
  no_candidate_adapter` for those two -- a real capability gap, not an
  oversight.
- `anchor`: none of the three current candidate adapters (native Meridian's
  `document_content_tree`, python-docx, Docling) expose a bookmark/anchor
  listing API, so this is `not_applicable: no_candidate_adapter` for all
  three today. The scoring function itself is real and tested
  (exact bookmark-name multiset precision/recall/F1), ready for a future
  candidate adapter that does extract bookmarks.
- `caption_for` (edge): gold resolves this edge; no candidate adapter
  computes an equivalent caption-to-table target resolution yet, so this
  remains `not_applicable: no_candidate_adapter` -- named remaining scope.
- `reference`, `source_binding`, `revision` (nodes) and `references`,
  `revises`, `clones`, `conflicts_with` (edges): **`independent_gold_extractor.py`
  itself does not produce this data yet** -- there is no gold ground truth to
  score against at all, for any system. This is reported as
  `not_applicable: no_gold_ground_truth`, a distinct and more precise reason
  than "no candidate adapter" (which would wrongly imply gold has the data
  and only the candidates are missing it).

Edge-level scoring beyond `caption_for` is limited to `contains` (via node
correspondence) and order (via the reading-order metric); `references`,
`revises`, `clones`, `conflicts_with` are not yet separate scored edges,
named here as explicit remaining scope, not hidden.

PAPER-S5 also adds `score_round_trip_editability`: a genuine Word-COM
open(ReadOnly=False) -> edit -> Save() -> Close() round-trip check (see
`run_paper30_graph_eval.py`'s `_word_open_edit_save_round_trip`), comparing a
candidate's own extraction of a document before vs. after the round trip
(not against gold) to detect unintended structural drift, plus a
render-equivalence check (before/after retained Word render receipts,
comparing page counts).
"""
from __future__ import annotations

import difflib
import random
import re
import xml.etree.ElementTree as ET
from typing import Any

_BOOTSTRAP_SEED = 20260828  # distinct from, but analogous to, _split.json's own seed=20260826
_BOOTSTRAP_RESAMPLES = 2000
_PERMUTATION_RESAMPLES = 2000

NOT_APPLICABLE_NO_ADAPTER = "not_applicable: no_candidate_adapter"
# Distinct from NOT_APPLICABLE_NO_ADAPTER: this reason means the GOLD
# extractor itself (independent_gold_extractor.py) does not produce this
# node/edge kind yet, so there is no ground truth for ANY candidate to be
# scored against -- never conflate the two ("candidates lack an adapter for
# data gold already has" vs. "gold has no data for this at all yet").
NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH = "not_applicable: no_gold_ground_truth"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


# ---------------------------------------------------------------------------
# Node correspondence
# ---------------------------------------------------------------------------

def _lcs_correspondence(gold_texts: list[str], cand_texts: list[str]) -> list[tuple[int, int]]:
    """Order-preserving text correspondence via LCS alignment (difflib).

    Good for precision/recall/F1 (a real text match is a real match
    regardless of exact position), but by construction NEVER reveals
    reordering -- matched pairs are always monotonic in both sequences. Do
    not use this for a reading-order metric; see `_reading_order_accuracy`.

    Deliberately does NOT special-case empty-string paragraphs: a document
    that is legitimately all-blank (e.g. an image-only body with one empty
    placeholder paragraph) must still be able to score a correct 1:1 match
    on that blank paragraph's existence and position. Excluding empty-empty
    pairs from matching (an earlier version of this function did) tanks
    precision/recall to 0 on such a document even though the extraction was
    structurally perfect -- a real, found-by-testing bug, not a hypothetical
    one (`tier2-omegause-010-roadmap-diagram`, the corpus's single-blank-
    paragraph flowchart-image document). SequenceMatcher's own alignment
    still only pairs two blanks together when doing so is consistent with
    the surrounding non-blank anchors' order, so this does not risk crediting
    unrelated blank paragraphs as if they were the same content.
    """
    gold_norm = [_normalize(t) for t in gold_texts]
    cand_norm = [_normalize(t) for t in cand_texts]
    matcher = difflib.SequenceMatcher(a=gold_norm, b=cand_norm, autojunk=False)
    pairs: list[tuple[int, int]] = []
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            gi, ci = block.a + k, block.b + k
            pairs.append((gi, ci))
    return pairs


def _prf1(matched: int, gold_total: int, cand_total: int) -> dict[str, float | None]:
    precision = matched / cand_total if cand_total else (1.0 if gold_total == 0 else 0.0)
    recall = matched / gold_total if gold_total else None  # undefined, not zero -- no instances to find
    f1 = None
    if recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    elif recall is None:
        f1 = None
    return {"precision": precision, "recall": recall, "f1": f1, "matched": matched,
            "gold_total": gold_total, "cand_total": cand_total}


_READING_ORDER_MATCH_THRESHOLD = 0.6


def _reading_order_accuracy(gold_texts: list[str], cand_texts: list[str]) -> dict[str, Any]:
    """A genuine reading-order signal, independent of the LCS correspondence.

    For each candidate item, finds its single best-matching gold item by text
    similarity alone (no order constraint), then counts *inversions*: pairs of
    matches where the gold order and candidate order disagree. An LCS-based
    correspondence is unsuitable here because SequenceMatcher's matching
    blocks are monotonic by construction -- they would report perfect
    reading-order "accuracy" even on a document whose paragraphs were fully
    shuffled, which would be a tautology, not a measurement.

    Naively comparing every candidate item against every unused gold item
    with `SequenceMatcher.ratio()` is O(n*m) *expensive* comparisons (full
    Ratcliff/Obershelp matching per pair) -- measured as multi-minute stalls
    on real corpus documents with hundreds of paragraphs. Two real
    optimizations, not a shortcut on correctness: (1) an exact-normalized-text
    bucket pass resolves the (common -- headers, boilerplate, short lines)
    exact-duplicate case in O(n+m) with no fuzzy comparison at all; (2) for
    the remaining candidates, `SequenceMatcher.real_quick_ratio()` /
    `quick_ratio()` -- both O(min(n,m)) upper-bound estimates documented by
    the stdlib specifically for this pre-filtering use -- are checked before
    ever calling the expensive O(n*m) `ratio()`, so a pair that cannot
    possibly clear the match threshold never pays for full alignment.
    """
    gold_norm = [_normalize(t) for t in gold_texts]
    cand_norm = [_normalize(t) for t in cand_texts]
    if not gold_norm or not cand_norm:
        return {"accuracy": None, "matched_pairs": 0, "reason": "empty sequence on one or both sides"}

    used_gold: set[int] = set()
    matches: list[tuple[int, int]] = []  # (gold_index, cand_index)

    # Pass 1: exact-normalized-text matches, cheapest possible resolution.
    gold_by_text: dict[str, list[int]] = {}
    for gi, gtext in enumerate(gold_norm):
        if gtext:
            gold_by_text.setdefault(gtext, []).append(gi)
    remaining_cand: list[int] = []
    for ci, ctext in enumerate(cand_norm):
        if not ctext:
            continue
        bucket = gold_by_text.get(ctext)
        gi = next((g for g in bucket if g not in used_gold), None) if bucket else None
        if gi is not None:
            matches.append((gi, ci))
            used_gold.add(gi)
        else:
            remaining_cand.append(ci)

    # Pass 2: fuzzy matching, only for what pass 1 couldn't resolve, with a
    # cheap quick-ratio pre-filter before any full ratio() call. Hard circuit
    # breaker: even with the pre-filter, a document made of many near-
    # identical short lines (e.g. a repetitive price catalog) can still
    # approach worst-case O(n*m) full ratio() calls -- rather than risk an
    # unbounded stall on one pathological document during a multi-document
    # corpus run, skip the fuzzy pass and report it explicitly instead of
    # hanging silently.
    _MAX_FUZZY_PAIR_BUDGET = 400_000
    remaining_gold = [gi for gi in range(len(gold_norm)) if gi not in used_gold and gold_norm[gi]]
    fuzzy_pass_skipped = False
    if len(remaining_cand) * len(remaining_gold) > _MAX_FUZZY_PAIR_BUDGET:
        if len(matches) < 2:
            return {"accuracy": None, "matched_pairs": len(matches),
                    "reason": (f"fuzzy-match search space ({len(remaining_cand)}x{len(remaining_gold)}) "
                               f"exceeds the {_MAX_FUZZY_PAIR_BUDGET}-pair budget and exact matches alone "
                               "gave fewer than 2 pairs -- skipped rather than risking an unbounded stall")}
        fuzzy_pass_skipped = True
        remaining_cand = []  # keep pass-1 exact matches, skip the expensive fuzzy pass
    for ci in remaining_cand:
        ctext = cand_norm[ci]
        matcher = difflib.SequenceMatcher(autojunk=False)
        matcher.set_seq2(ctext)
        best_gi, best_ratio = None, _READING_ORDER_MATCH_THRESHOLD
        for gi in remaining_gold:
            if gi in used_gold:
                continue
            matcher.set_seq1(gold_norm[gi])
            if matcher.real_quick_ratio() < best_ratio or matcher.quick_ratio() < best_ratio:
                continue  # cheap upper bound already below threshold -- skip the expensive ratio()
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio, best_gi = ratio, gi
        if best_gi is not None:
            matches.append((best_gi, ci))
            used_gold.add(best_gi)

    if len(matches) < 2:
        return {"accuracy": None, "matched_pairs": len(matches), "reason": "fewer than 2 matched pairs -- order is undefined"}

    # Concordant/discordant pair counts = Kendall-tau's own definition. A
    # naive double loop is O(k^2) in the number of matched pairs, which can
    # itself run to the thousands on a large real-world document -- counted
    # instead via merge-sort inversion counting (O(k log k), exact, no
    # arbitrary cutoff needed) by sorting matches on gold order and counting
    # candidate-order inversions.
    total_pairs = len(matches) * (len(matches) - 1) // 2
    discordant = _count_inversions([ci for _, ci in sorted(matches, key=lambda pair: pair[0])])
    concordant = total_pairs - discordant
    accuracy = concordant / total_pairs if total_pairs else None
    return {"accuracy": accuracy, "matched_pairs": len(matches), "concordant_pairs": concordant,
            "discordant_pairs": discordant, "fuzzy_pass_skipped": fuzzy_pass_skipped}


def _count_inversions(sequence: list[int]) -> int:
    """Count inversions in `sequence` via merge sort. O(k log k)."""
    if len(sequence) <= 1:
        return 0
    mid = len(sequence) // 2
    left, right = sequence[:mid], sequence[mid:]
    inversions = _count_inversions(left) + _count_inversions(right)
    merged, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1
            inversions += len(left) - i  # everything remaining in `left` inverts with right[j]
    merged.extend(left[i:])
    merged.extend(right[j:])
    sequence[:] = merged
    return inversions


# ---------------------------------------------------------------------------
# Equation semantic-class accuracy (re-derived independently, not trusted)
# ---------------------------------------------------------------------------

def _reclassify_omml(omml_raw: str) -> tuple[str, str] | None:
    """Apply independent_gold_extractor.py's OWN classifier to a candidate's
    claimed OMML, rather than trusting any label the candidate itself might
    report. Returns None if the string does not even parse as XML (itself a
    reportable candidate defect, surfaced by the caller as a mismatch)."""
    import sys
    from pathlib import Path

    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from independent_gold_extractor import _classify_equation  # noqa: PLC0415

    try:
        element = ET.fromstring(omml_raw)
    except ET.ParseError:
        return None
    return _classify_equation(element)


def _equation_semantic_accuracy(gold_equations: list[dict], cand_equations: list[dict]) -> dict[str, Any]:
    """Three distinct null states, not one conflated "nothing to report":

    - Both sides have zero equations: this document simply has none --
      `undefined`, a content characteristic, not a capability gap.
    - Candidate found zero equations (or found some but none carry OMML)
      while gold has at least one: the candidate system cannot expose OMML
      at all here -- `not_applicable: no_candidate_adapter`. In the current
      caller (`score_document_graph`), this path is reachable only when
      `candidate_has_omml=True` was passed yet this specific document's
      candidate list still came back OMML-less (e.g. the system's equation
      detector missed a real equation) -- callers with
      `candidate_has_omml=False` never reach this function at all.
    - Otherwise: an ordinary scored comparison.
    """
    if not gold_equations and not cand_equations:
        return {"accuracy": None, "status": "undefined", "reason": "no equations on either side for this document"}
    if not any(eq.get("omml_raw") for eq in cand_equations):
        return {
            "accuracy": None,
            "status": NOT_APPLICABLE_NO_ADAPTER,
            "reason": "candidate does not expose OMML for any equation (no semantic class is derivable from text/pixels alone)",
        }
    n = min(len(gold_equations), len(cand_equations))
    if n == 0:
        return {"accuracy": None, "status": "undefined",
                "reason": "equation count mismatch (one side has equations, the other has none) -- not a capability gap"}
    correct = 0
    mismatches = []
    for i in range(n):
        gold_label = gold_equations[i].get("attrs", {}).get("semantic_label")
        cand_omml = cand_equations[i].get("omml_raw")
        cand_label = _reclassify_omml(cand_omml)[0] if cand_omml else None
        if gold_label is not None and cand_label == gold_label:
            correct += 1
        elif gold_label is not None:
            mismatches.append({"index": i, "gold_label": gold_label, "candidate_reclassified_label": cand_label})
    return {
        "accuracy": correct / n,
        "status": "scored",
        "compared_count": n,
        "mismatches": mismatches,
    }


# ---------------------------------------------------------------------------
# caption / anchor node scoring (PAPER-S5)
# ---------------------------------------------------------------------------

def _caption_node_accuracy(gold_captions: list[dict], cand_captions: list[dict],
                            candidate_has_caption_detection: bool) -> dict[str, Any]:
    """Real precision/recall/F1 for whether a candidate can identify WHICH
    paragraphs are captions (SEQ-field paragraphs, per
    `independent_gold_extractor.py`'s `_is_seq_field` heuristic), reusing the
    same LCS text correspondence as paragraph-node scoring. Explicitly
    `not_applicable: no_candidate_adapter` (never a fabricated 0) when the
    candidate's own extraction library exposes no field/SEQ-instruction data
    -- true today for python-docx and Docling, per this module's docstring."""
    if not candidate_has_caption_detection:
        return {"precision": None, "recall": None, "f1": None, "matched": 0,
                "gold_total": len(gold_captions), "cand_total": len(cand_captions),
                "status": NOT_APPLICABLE_NO_ADAPTER,
                "reason": "candidate system's extraction API does not expose field/SEQ-instruction "
                          "data needed to identify which paragraphs are captions"}
    gold_texts = [c.get("text", "") for c in gold_captions]
    cand_texts = [c.get("text", "") for c in cand_captions]
    pairs = _lcs_correspondence(gold_texts, cand_texts)
    result = _prf1(len(pairs), len(gold_texts), len(cand_texts))
    result["status"] = "scored"
    return result


def _anchor_node_accuracy(gold_anchors: list[dict], cand_anchors: list[dict],
                           candidate_has_anchor_detection: bool) -> dict[str, Any]:
    """Exact bookmark-NAME multiset precision/recall/F1 (bookmark names are
    stable identifiers, not free text -- see
    docs/word-roundtrip-preservation-contract-v0.md Section 2, "Preserved by
    name" -- so this deliberately does not use fuzzy text correspondence).
    `not_applicable: no_candidate_adapter` for every candidate adapter as of
    PAPER-S5 (none expose a bookmark-listing API yet) -- a real, named
    capability gap, not a fabricated comparison. The function itself is real
    and tested so a future candidate adapter that does extract bookmarks
    gets scored automatically."""
    if not candidate_has_anchor_detection:
        return {"precision": None, "recall": None, "f1": None, "matched": 0,
                "gold_total": len(gold_anchors), "cand_total": len(cand_anchors),
                "status": NOT_APPLICABLE_NO_ADAPTER,
                "reason": "candidate system's extraction API exposes no bookmark/anchor listing capability"}
    from collections import Counter

    gold_names = [a.get("name") for a in gold_anchors if a.get("name")]
    cand_names = [a.get("name") for a in cand_anchors if a.get("name")]
    gold_counter, cand_counter = Counter(gold_names), Counter(cand_names)
    matched = sum((gold_counter & cand_counter).values())
    result = _prf1(matched, len(gold_names), len(cand_names))
    result["status"] = "scored"
    return result


# ---------------------------------------------------------------------------
# Word round-trip editability / render-equivalence (PAPER-S5)
# ---------------------------------------------------------------------------

def score_round_trip_editability(pre_items: dict, post_items: dict, marker_text: str) -> dict[str, Any]:
    """Compares a candidate's OWN extraction of a document before vs. after a
    real Word-COM open(ReadOnly=False) -> edit -> Save() -> Close() round
    trip (see `run_paper30_graph_eval.py`'s `_word_open_edit_save_round_trip`).
    This is deliberately NOT a gold-vs-candidate score -- both `pre_items`
    and `post_items` come from the SAME extractor -- so it measures whether
    the round trip itself introduced unintended structural drift,
    independent of that extractor's own accuracy against gold.

    `marker_text` is the exact paragraph the round trip intentionally
    appended. It is normalized-text-matched and removed from `post_items`'s
    paragraphs before comparing the remainder against `pre_items` via the
    same LCS correspondence used for gold scoring, so the intended, expected
    addition never counts against "unintended drift".

    Per docs/word-roundtrip-preservation-contract-v0.md Section 4, raw
    equation OMML content fingerprints are a KNOWN false-positive source --
    they drift across a genuine Word save even when semantics do not (Word
    adds `m:*Pr`/`m:ctrlPr`/`m:rFonts` property wrappers). So equation
    stability here re-derives each equation's independent semantic label via
    `_reclassify_omml` and compares LABELS, never raw OMML bytes.
    """
    pre_para_texts = [p["text"] for p in pre_items["paragraphs"]]
    post_para_texts_all = [p["text"] for p in post_items["paragraphs"]]

    marker_norm = _normalize(marker_text)
    remainder: list[str] = []
    marker_found = False
    for text in reversed(post_para_texts_all):
        if not marker_found and _normalize(text) == marker_norm:
            marker_found = True
            continue
        remainder.append(text)
    remainder.reverse()

    para_pairs = _lcs_correspondence(pre_para_texts, remainder)
    unintended_drift_prf1 = _prf1(len(para_pairs), len(pre_para_texts), len(remainder))

    pre_tables, post_tables = pre_items["tables"], post_items["tables"]
    table_count_stable = len(pre_tables) == len(post_tables)
    table_row_counts_stable = table_count_stable and all(
        pre_tables[i].get("row_count") == post_tables[i].get("row_count") for i in range(len(pre_tables))
    )

    pre_equations, post_equations = pre_items["equations"], post_items["equations"]
    equation_count_stable = len(pre_equations) == len(post_equations)
    n_eq = min(len(pre_equations), len(post_equations))
    equation_label_mismatches = []
    for i in range(n_eq):
        pre_omml = pre_equations[i].get("omml_raw")
        post_omml = post_equations[i].get("omml_raw")
        pre_label = _reclassify_omml(pre_omml)[0] if pre_omml else None
        post_label = _reclassify_omml(post_omml)[0] if post_omml else None
        if pre_label != post_label:
            equation_label_mismatches.append({"index": i, "pre_label": pre_label, "post_label": post_label})
    equation_semantic_stable = equation_count_stable and not equation_label_mismatches

    if not marker_found:
        overall_status = "marker_paragraph_missing_after_round_trip"
    elif unintended_drift_prf1["f1"] != 1.0:
        overall_status = "unintended_paragraph_drift_detected"
    elif not table_count_stable:
        overall_status = "table_count_drift_detected"
    elif not table_row_counts_stable:
        overall_status = "table_row_count_drift_detected"
    elif not equation_semantic_stable:
        overall_status = "equation_semantic_drift_detected"
    else:
        overall_status = "clean_round_trip"

    return {
        "marker_paragraph_round_tripped": marker_found,
        "unintended_paragraph_drift_prf1": unintended_drift_prf1,
        "table_count_stable": table_count_stable,
        "table_row_counts_stable": table_row_counts_stable if table_count_stable else None,
        "equation_count_stable": equation_count_stable,
        "equation_semantic_labels_stable": equation_semantic_stable,
        "equation_label_mismatches": equation_label_mismatches,
        "overall_status": overall_status,
    }


# ---------------------------------------------------------------------------
# Bootstrap CIs and paired significance tests
# ---------------------------------------------------------------------------

def bootstrap_ci(values: list[float], n_resamples: int = _BOOTSTRAP_RESAMPLES, alpha: float = 0.05,
                  seed: int = _BOOTSTRAP_SEED) -> dict[str, Any]:
    """Percentile bootstrap CI for the mean of `values`. Pure stdlib (`random`)."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return {"mean": (clean[0] if clean else None), "ci_low": None, "ci_high": None,
                "n": len(clean), "reason": "fewer than 2 non-null values -- CI undefined"}
    rng = random.Random(seed)
    n = len(clean)
    means = []
    for _ in range(n_resamples):
        resample = [clean[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    return {
        "mean": sum(clean) / n,
        "ci_low": means[lo_idx],
        "ci_high": means[min(hi_idx, n_resamples - 1)],
        "n": n,
        "confidence_level": 1 - alpha,
        "n_resamples": n_resamples,
    }


def paired_permutation_test(values_a: list[float | None], values_b: list[float | None],
                             n_permutations: int = _PERMUTATION_RESAMPLES,
                             seed: int = _BOOTSTRAP_SEED) -> dict[str, Any]:
    """Paired sign-flip permutation test on per-document differences (A - B).

    Under the null hypothesis of no systematic difference between the two
    systems, each document's (A-B) difference is equally likely to have been
    (B-A) -- so randomly flipping signs and recomputing the mean gives an
    exact empirical null distribution without assuming normality.
    """
    diffs = [a - b for a, b in zip(values_a, values_b) if a is not None and b is not None]
    if len(diffs) < 2:
        return {"observed_mean_diff": None, "p_value": None, "n_paired_documents": len(diffs),
                "reason": "fewer than 2 paired documents with values on both sides"}
    observed = sum(diffs) / len(diffs)
    rng = random.Random(seed)
    extreme_count = 0
    for _ in range(n_permutations):
        flipped = [d if rng.random() < 0.5 else -d for d in diffs]
        if abs(sum(flipped) / len(flipped)) >= abs(observed):
            extreme_count += 1
    p_value = extreme_count / n_permutations
    return {
        "observed_mean_diff": observed,
        "p_value": p_value,
        "n_paired_documents": len(diffs),
        "n_permutations": n_permutations,
        "method": "paired sign-flip permutation test",
    }


# ---------------------------------------------------------------------------
# Per-document scoring entry point
# ---------------------------------------------------------------------------

def score_document_graph(gold: dict, candidate: dict, candidate_has_para_id: bool,
                          candidate_has_omml: bool, candidate_has_caption_detection: bool = False,
                          candidate_has_anchor_detection: bool = False) -> dict[str, Any]:
    """Full graph-aware score for one (gold, candidate) document pair.

    `gold` and `candidate` are both in the common schema described in this
    module's docstring, PLUS gold also carries the raw `nodes` list (needed
    for `attrs.semantic_label` on equation nodes), plus (PAPER-S5)
    `captions: [{"text": str}]` and `anchors: [{"name": str}]` -- optional on
    `candidate` too (defaults to empty, scored `not_applicable` unless the
    corresponding `candidate_has_*_detection` flag is set).
    """
    gold_para_texts = [p["text"] for p in gold["paragraphs"]]
    cand_para_texts = [p["text"] for p in candidate["paragraphs"]]
    para_pairs = _lcs_correspondence(gold_para_texts, cand_para_texts)
    paragraph_prf1 = _prf1(len(para_pairs), len(gold_para_texts), len(cand_para_texts))
    reading_order = _reading_order_accuracy(gold_para_texts, cand_para_texts)

    gold_tables = gold["tables"]
    cand_tables = candidate["tables"]
    matched_tables = min(len(gold_tables), len(cand_tables))
    table_prf1 = _prf1(matched_tables, len(gold_tables), len(cand_tables))
    table_row_exact_matches = sum(
        1 for i in range(matched_tables) if gold_tables[i]["row_count"] == cand_tables[i].get("row_count")
    )
    table_row_exact_match_rate = (table_row_exact_matches / matched_tables) if matched_tables else None

    gold_equations = gold["equations"]
    cand_equations = candidate["equations"]
    matched_equations = min(len(gold_equations), len(cand_equations))
    equation_prf1 = _prf1(matched_equations, len(gold_equations), len(cand_equations))
    equation_nodes_for_labels = gold.get("equation_nodes", [])
    if candidate_has_omml:
        equation_semantic = _equation_semantic_accuracy(equation_nodes_for_labels, cand_equations)
    else:
        equation_semantic = {"accuracy": None, "status": NOT_APPLICABLE_NO_ADAPTER,
                              "reason": "candidate system does not expose OMML"}

    para_id_status: dict[str, Any]
    if not candidate_has_para_id:
        para_id_status = {"preservation_rate": None, "status": "not_applicable",
                           "reason": "candidate system cannot mint/preserve native paragraph identity"}
    else:
        gold_ids = [p.get("para_id") for p in gold["paragraphs"]]
        cand_ids = [p.get("para_id") for p in candidate["paragraphs"]]
        expected = [i for i, v in enumerate(gold_ids) if v]
        if not expected:
            para_id_status = {"preservation_rate": None, "status": "undefined", "reason": "gold has no native paragraph IDs for this document"}
        else:
            preserved = sum(i < len(cand_ids) and cand_ids[i] == gold_ids[i] for i in expected)
            para_id_status = {"preservation_rate": preserved / len(expected), "status": "scored", "evaluable_paragraphs": len(expected)}

    caption_node_prf1 = _caption_node_accuracy(
        gold.get("captions", []), candidate.get("captions", []), candidate_has_caption_detection,
    )
    anchor_node_prf1 = _anchor_node_accuracy(
        gold.get("anchors", []), candidate.get("anchors", []), candidate_has_anchor_detection,
    )

    # reference/source_binding/revision: independent_gold_extractor.py itself
    # produces no ground truth for these node kinds yet -- distinct from (and
    # a stronger statement than) "no candidate adapter", see module docstring.
    unsupported_kinds = {
        kind: NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH for kind in ("reference", "source_binding", "revision")
    }
    unsupported_edge_kinds = {
        # gold DOES resolve caption_for; no candidate adapter computes an
        # equivalent target resolution yet -- real, named remaining scope.
        "caption_for": NOT_APPLICABLE_NO_ADAPTER,
        # gold itself has no ground truth for these edge kinds yet.
        "references": NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH,
        "revises": NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH,
        "clones": NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH,
        "conflicts_with": NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH,
    }

    return {
        "paragraph_node_prf1": paragraph_prf1,
        "reading_order": reading_order,
        "table_node_prf1": table_prf1,
        "table_row_exact_match_rate": table_row_exact_match_rate,
        "equation_node_prf1": equation_prf1,
        "equation_semantic_class_accuracy": equation_semantic,
        "para_id": para_id_status,
        "caption_node_prf1": caption_node_prf1,
        "anchor_node_prf1": anchor_node_prf1,
        "unsupported_node_kinds": unsupported_kinds,
        "unsupported_edge_kinds": unsupported_edge_kinds,
    }
