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
# bibliography / citation node scoring (PAPER-S23 respec_cascade)
# ---------------------------------------------------------------------------

def _bibliography_entry_prf1(gold_entries: list[dict], cand_entries: list[dict],
                              candidate_has_bibliography_detection: bool) -> dict[str, Any]:
    """Exact-multiset PRF1 on a bibliography entry's citation KEY -- pattern-
    matched to `_anchor_node_accuracy` rather than `_caption_node_accuracy`,
    since a citation key is a stable minted identifier (like a bookmark
    name), not free text that benefits from LCS's fuzzy/reordering
    tolerance. `not_applicable: no_candidate_adapter` (never a fabricated 0,
    per this module's docstring) when the candidate's own extraction API does
    not expose bibliography/reference-list entry data at all."""
    if not candidate_has_bibliography_detection:
        return {"precision": None, "recall": None, "f1": None, "matched": 0,
                "gold_total": len(gold_entries), "cand_total": len(cand_entries),
                "status": NOT_APPLICABLE_NO_ADAPTER,
                "reason": "candidate system's extraction API does not expose bibliography/"
                          "reference-list entry data"}
    from collections import Counter

    gold_keys = [e.get("key") for e in gold_entries if e.get("key")]
    cand_keys = [e.get("key") for e in cand_entries if e.get("key")]
    gold_counter, cand_counter = Counter(gold_keys), Counter(cand_keys)
    matched = sum((gold_counter & cand_counter).values())
    result = _prf1(matched, len(gold_keys), len(cand_keys))
    result["status"] = "scored"
    return result


def _citation_marker_prf1(gold_citations: list[dict], cand_citations: list[dict],
                           candidate_has_citation_detection: bool) -> dict[str, Any]:
    """Exact-multiset PRF1 on a citation marker's KEY -- the bibliography
    entry it cites, a stable identifier, not the citation's rendered/
    formatted display text (which varies by style and is not what this
    benchmark's grading cares about: `docx_trial_evaluator.py`'s citation
    graders check the field code/key, not prose, per this project's own
    "never trust the system under test's own self-report" rule). Same
    `_anchor_node_accuracy`-style exact-multiset pattern and the same
    `not_applicable: no_candidate_adapter` convention as
    `_bibliography_entry_prf1` above."""
    if not candidate_has_citation_detection:
        return {"precision": None, "recall": None, "f1": None, "matched": 0,
                "gold_total": len(gold_citations), "cand_total": len(cand_citations),
                "status": NOT_APPLICABLE_NO_ADAPTER,
                "reason": "candidate system's extraction API does not expose citation "
                          "marker/field-code data needed to identify which entry a citation cites"}
    from collections import Counter

    gold_keys = [c.get("key") for c in gold_citations if c.get("key")]
    cand_keys = [c.get("key") for c in cand_citations if c.get("key")]
    gold_counter, cand_counter = Counter(gold_keys), Counter(cand_keys)
    matched = sum((gold_counter & cand_counter).values())
    result = _prf1(matched, len(gold_keys), len(cand_keys))
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
# Keep-survival differ (PAPER-S23 respec_cascade, Checkpoint B)
# ---------------------------------------------------------------------------

def score_keep_survival(checkpoint_a_items: dict, checkpoint_b_items: dict,
                         kept_element_markers: dict[str, str],
                         excluded_paragraph_texts: list[str] | None = None) -> dict[str, Any]:
    """Generalizes `score_round_trip_editability`'s before/after diff pattern
    from one Word-COM round trip's single marker to two ARBITRARY named
    checkpoints (not specifically a Word-COM round trip) and MULTIPLE named
    elements at once -- this is the respec_cascade design's Checkpoint B
    "selective revert" test (`docs/paper-s23-respec-cascade-protocol-v0.md`
    section 4): can an arm touch exactly the elements named for reversal/
    redirection while leaving every other, untouched sibling from the same
    chain completely alone.

    `kept_element_markers` maps an element's name to its exact, expected
    (whitespace-insensitive, via `_normalize` -- same convention
    `score_round_trip_editability` uses for its own marker check) text, e.g.
    a bibliography entry's rendered text or a caption's text. For each
    element this counts how many paragraphs in each checkpoint normalize to
    exactly that text:

    - zero occurrences in `checkpoint_b_items` -> the element was lost
      somewhere between the two checkpoints (`kept_element_missing`).
    - more than one occurrence in `checkpoint_b_items` -> the element was
      unintentionally duplicated (`kept_element_duplicated`).
    - exactly one occurrence in `checkpoint_b_items` but not exactly one in
      `checkpoint_a_items` -> the element's own checkpoint-A form was not
      stably present under this exact text (already missing, duplicated, or
      textually different there), so checkpoint-B's apparent survival cannot
      be credited as "unchanged" (`kept_element_changed`). This is a
      deliberately conservative exact-text-multiset check, the same kind
      `_anchor_node_accuracy` uses for bookmark names, not a positional
      diff -- it can only say a kept element's exact expected text failed to
      appear exactly once on both sides, not pinpoint how it changed.

    `excluded_paragraph_texts` names paragraphs BOTH checkpoints are allowed
    to differ on for a reason other than a kept element -- e.g. the citation
    anchor paragraph's own two different forms (with the marker at
    checkpoint A, restored without it at checkpoint B) -- so a caller-named,
    intentional respec-phase CONTENT change is never silently absorbed into
    "unintended drift" and never silently ignored either.

    Every paragraph in `checkpoint_b_items` not attributable to a kept
    element or an excluded paragraph is compared against its
    `checkpoint_a_items` counterpart via exact-multiset (`Counter`)
    matching, NOT `_lcs_correspondence` -- deliberately, unlike
    `score_round_trip_editability`'s own remainder check. `_lcs_correspondence`'s
    own docstring says it "by construction NEVER reveals reordering... do
    not use this for a reading-order metric," but this function's whole
    purpose (protocol section 4's Checkpoint B, "the design's central,
    novel test") is to grade a checkpoint pair where a REAL, INTENTIONAL
    reorder happens in between -- step 2.3 relocates an entire section
    (heading + every body paragraph) to a new position, changing none of
    those paragraphs' text, only their position. A Counter-based multiset
    diff is naturally blind to pure reordering (same texts, same counts,
    different order -> zero apparent drift) without needing the caller to
    enumerate every one of a moved section's body paragraphs as excluded --
    only a genuine CONTENT change (added/removed/edited text, like the
    citation marker) shows up as drift, which is exactly what this check
    should catch.
    """
    from collections import Counter

    excluded_norms = {_normalize(t) for t in (excluded_paragraph_texts or [])}

    a_para_texts = [p["text"] for p in checkpoint_a_items["paragraphs"]]
    b_para_texts = [p["text"] for p in checkpoint_b_items["paragraphs"]]
    a_norms = [_normalize(t) for t in a_para_texts]
    b_norms = [_normalize(t) for t in b_para_texts]

    element_results: dict[str, dict[str, Any]] = {}
    kept_norms: set[str] = set()
    for name, marker_text in kept_element_markers.items():
        marker_norm = _normalize(marker_text)
        kept_norms.add(marker_norm)
        count_a = sum(1 for n in a_norms if n == marker_norm)
        count_b = sum(1 for n in b_norms if n == marker_norm)
        element_results[name] = {
            "present": count_b >= 1,
            "unchanged": count_a == 1 and count_b == 1,
            "occurrences": count_b,
        }

    a_remainder = [text for text, n in zip(a_para_texts, a_norms) if n not in kept_norms and n not in excluded_norms]
    b_remainder = [text for text, n in zip(b_para_texts, b_norms) if n not in kept_norms and n not in excluded_norms]
    a_remainder_ctr = Counter(_normalize(t) for t in a_remainder)
    b_remainder_ctr = Counter(_normalize(t) for t in b_remainder)
    matched = sum((a_remainder_ctr & b_remainder_ctr).values())
    unintended_drift_prf1 = _prf1(matched, len(a_remainder), len(b_remainder))

    overall_status = "clean_keep_survival"
    for name in kept_element_markers:
        result = element_results[name]
        if not result["present"]:
            overall_status = f"kept_element_missing:{name}"
            break
        if result["occurrences"] > 1:
            overall_status = f"kept_element_duplicated:{name}"
            break
        if not result["unchanged"]:
            overall_status = f"kept_element_changed:{name}"
            break
    else:
        if unintended_drift_prf1["f1"] != 1.0:
            overall_status = "unintended_paragraph_drift_detected"

    return {
        **element_results,
        "unintended_drift_prf1": unintended_drift_prf1,
        "overall_status": overall_status,
    }


# ---------------------------------------------------------------------------
# comment_targeting precision + set-survival scorers (PAPER-S24,
# docs/paper-s24-targeted-comment-protocol-v0.md section 4/5)
# ---------------------------------------------------------------------------

def _comment_range_precision(
    bracketed_para_ids: set[str],
    target_para_id: str,
    confusable_sibling_para_ids: list[str] | set[str],
) -> dict[str, Any]:
    """PAPER-S24 comment_targeting only (protocol section 4 item 2): the
    presence-AND-absence check for one already-inserted comment's own range
    -- does it bracket EXACTLY the intended target paragraph, and NO other
    paragraph in that target's frozen confusable-sibling set (the specific
    precision failure -- `wrong_target_same_cluster` -- this whole family
    exists to measure), and no other paragraph at all.

    Pattern-matched to `_bibliography_entry_prf1`/`_citation_marker_prf1`'s
    exact-match-on-a-stable-identifier style (a native `w14:paraId`, never
    fuzzy text), but deliberately NOT the same `(gold_entries, cand_entries,
    candidate_has_X_detection)` corpus-level PRF1 signature those two share:
    this grades a single structural fact about ONE already-resolved comment
    (protocol section 4's `grade_comment_targeting_step` is a one-step
    check, not an aggregate precision/recall over many candidate comments),
    so there is no corpus here to average over. The caller
    (`docx_trial_evaluator.py::grade_comment_targeting_step`) is responsible
    for deriving `bracketed_para_ids` directly from raw `word/document.xml`
    (never from `list_internal_notes` -- protocol section 4's own standing
    rule) -- this function only does the presence/absence comparison
    against the frozen ground truth, the same narrow scope every other
    `_*_prf1` helper in this module keeps for itself.

    `bracketed_para_ids` is deliberately a SET of every paragraph id whose
    own `<w:p>` element structurally contains (directly or via a nested
    descendant) a `commentRangeStart` or `commentRangeEnd` tagged with this
    comment's id -- NOT a document-order interpolation of every paragraph
    physically BETWEEN a start and an end landing in two different
    paragraphs. A native insertion via `_stage_word_comment` never produces
    more than one such paragraph (protocol section 0.1, confirmed by reading
    that function directly), so this distinction only matters for a
    malformed control-arm hand-edit that puts the two markers in different
    paragraphs -- and for that case, `bracketed_para_ids` already contains
    more than one id, which fails `exact_single_paragraph_match` regardless
    of which paragraphs a document-order interpolation would additionally
    include. This simpler, tag-container definition is sufficient for every
    distinction this check needs to make and avoids a full document-order
    walk of the whole body+table tree just to resolve one malformed edge
    case that changes no downstream verdict.
    """
    siblings = set(confusable_sibling_para_ids)
    target_present = target_para_id in bracketed_para_ids
    bracketed_siblings = bracketed_para_ids & siblings
    bracketed_other = bracketed_para_ids - siblings - {target_para_id}
    exact_single_paragraph_match = bracketed_para_ids == {target_para_id}

    if not bracketed_para_ids:
        status = "no_range_found"
    elif exact_single_paragraph_match:
        status = "exact_match"
    elif bracketed_siblings:
        status = "wrong_target_same_cluster"
    else:
        status = "wrong_target_other"

    return {
        "target_present": target_present,
        "confusable_siblings_absent": not bracketed_siblings,
        "bracketed_confusable_siblings": sorted(bracketed_siblings),
        "bracketed_other_paragraphs": sorted(bracketed_other),
        "bracketed_para_ids": sorted(bracketed_para_ids),
        "exact_single_paragraph_match": exact_single_paragraph_match,
        "status": status,
        "pass": status == "exact_match",
    }


def score_comment_set_survival(
    checkpoint_a_comments: list[dict[str, Any]],
    checkpoint_b_comments: list[dict[str, Any]],
    kept_comments: dict[str, dict[str, Any]],
    excluded_authors: list[str] | None = None,
) -> dict[str, Any]:
    """PAPER-S24 comment_targeting only (protocol section 4 item 3):
    generalizes `score_keep_survival`'s before/after checkpoint-pair diff
    (see that function's own docstring for the full design this adapts)
    from a small, FIXED set of named elements (respec_cascade's
    `bibliography`/`equation`/`caption`, three keys chosen once per chain at
    design time) to an arbitrary, GROWING per-chain set: every comment
    inserted at steps `1..k-1` of THIS chain, plus every pre-existing
    organic comment (protocol section 1.3), checked at chain position `k`.

    `checkpoint_{a,b}_comments` are lists of comment "item" dicts,
    `{"author": str, "text": str, "anchor_para_ids": tuple[str, ...]}`,
    extracted by the CALLER directly from raw `word/comments.xml` +
    `word/document.xml` range markers (never from `list_internal_notes`,
    the same standing rule `_comment_range_precision` and every grader in
    this module follows) -- this function never touches a `.docx` path
    itself, exactly like `score_keep_survival`'s own items-dict convention.
    `anchor_para_ids` is a tuple (not a single id) for the same reason
    `_comment_range_precision` uses a set: a malformed comment can bracket
    zero, one, or more than one paragraph structurally, and this function
    needs to be able to tell "unchanged" from "silently re-anchored"
    without assuming exactly one.

    `kept_comments` maps a STABLE identifying key to that comment's own
    EXPECTED `(author, text, anchor_para_ids)` triple -- each earlier step's
    own per-trial author tag (protocol section 4 item 1: "a distinct
    per-trial author tag" is this family's own harness-minted stable
    identifier, playing the role `score_keep_survival`'s three fixed
    element NAMES play for respec_cascade) for harness-inserted comments,
    or a synthesized key (e.g. `f"organic:{index}"`) for each pre-existing
    organic comment.

    Matching is by the FULL `(author, text, anchor_para_ids)` triple, never
    by author alone: protocol section 1.3's own real corpus data confirms
    author is NOT a unique key across a document's comments in general
    (`jcshm-si.docx` has 6 organic comments, 5 of them all authored "Claude
    (review flag)") -- only a HARNESS-MINTED per-trial author tag is
    guaranteed unique (protocol section 4 item 1's own per-step "exactly one
    new `<w:comment>` by this author" check enforces that at insertion
    time), and this function must grade organic comments correctly too, so
    it cannot assume author uniqueness in general. A full-tuple match
    is checked in BOTH checkpoints -- not just checkpoint B alone --
    mirroring `score_keep_survival`'s own "checkpoint A's own form must
    ALSO be exactly one occurrence" discipline: an element already
    missing/duplicated/wrong at checkpoint A cannot be credited as
    "surviving" merely because checkpoint B shows the identical wrong state.
    A comment that survives under the same author but drifts to a different
    TEXT or ANCHOR_PARA_IDS is reported as `present=False` (it no longer
    matches its own expected record) exactly like a comment that vanished
    outright -- both collapse to `kept_comment_missing` at the `overall_
    status` level, the same granularity `score_keep_survival` itself uses
    for its own three named elements (this function does not attempt a
    finer "moved" vs. "deleted" distinction at the top level, though the
    per-key `occurrences_checkpoint_{a,b}_by_author` fields below retain
    enough raw detail for a caller that wants to investigate further).

    `excluded_authors` names the author tag(s) legitimately NEW at
    checkpoint B and absent at checkpoint A -- THIS step's own freshly
    inserted comment, whose own correctness is graded separately by
    `_comment_range_precision` and the per-step "exactly one new comment"
    check, never by this function -- the same role `score_keep_survival`'s
    own `excluded_paragraph_texts` plays for citation's anchor-paragraph
    text change.

    Deliberate, disclosed deviation from a byte-for-byte copy of
    `score_keep_survival`'s own remainder-drift check: that function flags
    drift whenever its Counter-based remainder PRF1's `f1 != 1.0`, which is
    safe there because respec_cascade's remainder is "every OTHER paragraph
    in a real, hundreds-of-paragraphs document" -- essentially never empty
    on either side, so `_prf1`'s `recall=None` (undefined-when-gold-empty)
    edge case never actually arises in that caller. Here, once the kept set
    and this step's own excluded new comment are removed, the remainder is
    typically EMPTY on BOTH sides in the normal, clean case (a document's
    comments are, absent a defect, entirely accounted for by kept +
    this-step's-own-new). `_prf1(0, 0, 0)` returns `f1=None` (recall is
    undefined when `gold_total=0`), and `None != 1.0` is True -- so a blind
    copy of `score_keep_survival`'s own check would flag EVERY clean step as
    drift-detected, a real bug class this function was caught making before
    it shipped (the same level of care
    `docx_trial_evaluator.py`'s own `_AUTO_CREATED_REFERENCES_HEADING_TEXT`
    fix was applied with elsewhere in this codebase, cited in this family's
    own build brief as the precedent to match). Fixed here by treating "both
    remainders empty" as its own explicit clean case rather than routing it
    through the ambiguous f1-vs-1.0 comparison.
    """
    from collections import Counter

    def _tuple_of(item: dict[str, Any]) -> tuple[Any, Any, Any]:
        return (item.get("author"), item.get("text"), tuple(item.get("anchor_para_ids") or ()))

    def _by_author(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            grouped.setdefault(item.get("author"), []).append(item)
        return grouped

    a_by_author = _by_author(checkpoint_a_comments)
    b_by_author = _by_author(checkpoint_b_comments)

    element_results: dict[str, dict[str, Any]] = {}
    for key, expected in kept_comments.items():
        expected_tuple = (
            expected.get("author"), expected.get("text"), tuple(expected.get("anchor_para_ids") or ()),
        )
        author = expected.get("author")
        a_author_comments = a_by_author.get(author, [])
        b_author_comments = b_by_author.get(author, [])
        a_exact = [c for c in a_author_comments if _tuple_of(c) == expected_tuple]
        b_exact = [c for c in b_author_comments if _tuple_of(c) == expected_tuple]
        # present/duplicated/unchanged are all keyed on the FULL exact
        # tuple, never on author alone -- see docstring for why (organic
        # comments are not author-unique in the real corpus). The
        # by-author counts are kept only as extra diagnostic detail.
        element_results[key] = {
            "present": len(b_exact) >= 1,
            "duplicated": len(b_exact) > 1,
            "unchanged": len(a_exact) == 1 and len(b_exact) == 1,
            "occurrences_checkpoint_a_by_author": len(a_author_comments),
            "occurrences_checkpoint_b_by_author": len(b_author_comments),
            "exact_matches_checkpoint_a": len(a_exact),
            "exact_matches_checkpoint_b": len(b_exact),
        }

    # Remainder = every comment NOT accounted for by kept_comments/excluded_
    # authors, used for the generic drift check below. Excluded authors are
    # removed by AUTHOR membership (safe: an excluded author is always this
    # step's own harness-minted, guaranteed-unique tag, never shared with
    # any other real comment). Kept comments are removed by exact-TUPLE
    # multiset subtraction (one occurrence per kept_comments entry), never
    # by author membership -- author-based removal would be WRONG here: if
    # two organic comments share an author (real, confirmed on
    # jcshm-si.docx per protocol section 1.3) and only one is a genuine
    # "kept" match, author-based filtering would silently exempt the OTHER
    # one from drift-checking too, even if it were a totally unrelated,
    # unaccounted-for comment that merely happens to share that author
    # string.
    excluded = set(excluded_authors or ())
    kept_tuples = Counter(
        (expected.get("author"), expected.get("text"), tuple(expected.get("anchor_para_ids") or ()))
        for expected in kept_comments.values()
    )

    def _remainder(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = [c for c in items if c.get("author") not in excluded]
        remaining = Counter(kept_tuples)
        result: list[dict[str, Any]] = []
        for c in filtered:
            t = _tuple_of(c)
            if remaining.get(t, 0) > 0:
                remaining[t] -= 1
                continue
            result.append(c)
        return result

    a_remainder = _remainder(checkpoint_a_comments)
    b_remainder = _remainder(checkpoint_b_comments)
    a_ctr = Counter(_tuple_of(c) for c in a_remainder)
    b_ctr = Counter(_tuple_of(c) for c in b_remainder)
    matched = sum((a_ctr & b_ctr).values())
    unintended_drift_prf1 = _prf1(matched, len(a_remainder), len(b_remainder))
    if not a_remainder and not b_remainder:
        drift_detected = False  # see docstring -- both-empty is this function's own explicit clean case
    else:
        drift_detected = unintended_drift_prf1["f1"] != 1.0

    overall_status = "clean_comment_set_survival"
    for key in kept_comments:
        result = element_results[key]
        if not result["present"]:
            overall_status = f"kept_comment_missing:{key}"
            break
        if result["duplicated"]:
            overall_status = f"kept_comment_duplicated:{key}"
            break
        if not result["unchanged"]:
            overall_status = f"kept_comment_changed:{key}"
            break
    else:
        if drift_detected:
            overall_status = "unintended_comment_drift_detected"

    return {
        **element_results,
        "unintended_drift_prf1": unintended_drift_prf1,
        "unintended_drift_detected": drift_detected,
        "overall_status": overall_status,
    }


# ---------------------------------------------------------------------------
# Bootstrap CIs and paired significance tests
# ---------------------------------------------------------------------------

def _clopper_pearson_boundary_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact Clopper-Pearson CI for the two proportions the percentile bootstrap
    below cannot express at all: every trial passed, or every trial failed. Those
    are the only two observed proportions where every possible bootstrap resample
    is identical to the original sample (nothing else could be drawn), so the
    resampled-mean distribution has zero variance and the percentile interval
    collapses to a single point -- reporting no uncertainty rather than a real
    one. Closed-form here because Beta(n, 1) and Beta(1, n) have elementary CDFs
    (x**n and 1-(1-x)**n respectively), so no numerical Beta-inverse is needed.
    """
    if successes == n:
        return (alpha / 2) ** (1.0 / n), 1.0
    if successes == 0:
        return 0.0, 1.0 - (alpha / 2) ** (1.0 / n)
    raise ValueError("_clopper_pearson_boundary_ci is only valid at 0 or n successes")


def bootstrap_ci(values: list[float], n_resamples: int = _BOOTSTRAP_RESAMPLES, alpha: float = 0.05,
                  seed: int = _BOOTSTRAP_SEED) -> dict[str, Any]:
    """Percentile bootstrap CI for the mean of `values`. Pure stdlib (`random`).

    Falls back to the exact Clopper-Pearson binomial CI when `values` is binary
    (0/1) and every value is identical -- see `_clopper_pearson_boundary_ci` for
    why the percentile bootstrap itself cannot produce a meaningful interval in
    exactly that one situation.
    """
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
    ci_low = means[lo_idx]
    ci_high = means[min(hi_idx, n_resamples - 1)]
    mean = sum(clean) / n
    method = "percentile_bootstrap"
    if ci_low == ci_high and set(clean) <= {0.0, 1.0}:
        successes = int(round(mean * n))
        ci_low, ci_high = _clopper_pearson_boundary_ci(successes, n, alpha)
        method = "clopper_pearson_exact_fallback"
    return {
        "mean": mean,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "n": n,
        "confidence_level": 1 - alpha,
        "n_resamples": n_resamples,
        "method": method,
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


# Exact sign-flip enumeration is always used while 2**units <= 2**_EXACT_SIGN_FLIP_MAX_UNITS,
# and beyond that while the null distribution has at most that many distinct values
# (always true for 0/1 outcomes); otherwise the tests below use a seeded Monte Carlo draw.
_EXACT_SIGN_FLIP_MAX_UNITS = 20


def _sign_flip_p_value(unit_sums: list[float], n_permutations: int, seed: int,
                       max_exact_units: int) -> dict[str, Any]:
    """Two-sided sign-flip p-value for the statistic |sum_u s_u * D_u|, where
    D_u is one exchangeable unit's summed paired difference and every s_u is
    flipped independently. The observed statistic is the all-(+1) pattern.

    Exact: the null distribution of the flipped sum over all 2**units sign
    patterns is built one unit at a time as {sum: number of patterns} (a unit
    whose sum is 0 leaves the statistic unchanged under both signs, so it is
    skipped), and p is the exact share of patterns at least as extreme as
    observed. This is always done when units <= max_exact_units (the table
    then has at most 2**max_exact_units entries) and is kept for more units as
    long as the table stays that small -- as it does for 0/1 outcomes, whose
    sums are small integers. Otherwise a Monte Carlo estimate over
    n_permutations seeded draws, with the usual (extreme + 1) /
    (n_permutations + 1) correction so it is never 0."""
    observed = abs(sum(unit_sums))
    tol = 1e-8 * max(1.0, observed)
    n_units = len(unit_sums)
    max_table = 2 ** max_exact_units
    dist: dict[float, int] | None = {0.0: 1}
    nonzero = [d for d in unit_sums if d != 0]
    for d in nonzero:
        nxt: dict[float, int] = {}
        for s, count in dist.items():
            for v in (round(s + d, 10), round(s - d, 10)):
                nxt[v] = nxt.get(v, 0) + count
        dist = nxt
        if len(dist) > max_table:
            dist = None
            break
    if dist is not None:
        extreme = sum(count for s, count in dist.items() if abs(s) >= observed - tol)
        return {"p_value": extreme / 2 ** len(nonzero), "exact": True, "n_sign_patterns": 2 ** n_units}
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_permutations):
        if abs(sum(d if rng.random() < 0.5 else -d for d in unit_sums)) >= observed - tol:
            extreme += 1
    return {"p_value": (extreme + 1) / (n_permutations + 1), "exact": False, "n_permutations": n_permutations}


def paired_permutation_test_exact(values_a: list[float | None], values_b: list[float | None],
                                  n_permutations: int = _PERMUTATION_RESAMPLES,
                                  seed: int = _BOOTSTRAP_SEED,
                                  max_exact_n: int = _EXACT_SIGN_FLIP_MAX_UNITS) -> dict[str, Any]:
    """Same paired sign-flip test and statistic as `paired_permutation_test`
    (every pair is its own exchangeable unit), but with the p-value computed
    exactly over all 2**n sign patterns (always while n <= max_exact_n; for
    larger n while the null distribution stays small -- see
    `_sign_flip_p_value`), and a corrected Monte Carlo estimate otherwise;
    `exact` in the result says which. `paired_permutation_test`
    itself is left unchanged because reported statistics depend on it; its
    uncorrected Monte Carlo p can fall below the exact floor 2/2**n or be 0.

    `p_value_floor` is the smallest two-sided p any data with this many pairs
    could produce (2/2**n) -- e.g. 0.25 with 3 pairs."""
    diffs = [a - b for a, b in zip(values_a, values_b) if a is not None and b is not None]
    if len(diffs) < 2:
        return {"observed_mean_diff": None, "p_value": None, "n_paired_documents": len(diffs),
                "reason": "fewer than 2 paired documents with values on both sides"}
    result = {
        "observed_mean_diff": sum(diffs) / len(diffs),
        **_sign_flip_p_value(diffs, n_permutations, seed, max_exact_n),
        "p_value_floor": 2 / 2 ** len(diffs),
        "n_paired_documents": len(diffs),
    }
    result["method"] = ("paired sign-flip permutation test, exact enumeration" if result["exact"]
                        else "paired sign-flip permutation test, Monte Carlo (null distribution too large to enumerate)")
    return result


def cluster_paired_sign_flip_test(cluster_ids: list[str], values_a: list[float | None],
                                  values_b: list[float | None],
                                  n_permutations: int = _PERMUTATION_RESAMPLES,
                                  seed: int = _BOOTSTRAP_SEED,
                                  max_exact_clusters: int = _EXACT_SIGN_FLIP_MAX_UNITS) -> dict[str, Any]:
    """Cluster-level paired sign-flip test. Observation i is the pair
    (values_a[i], values_b[i]) and belongs to cluster cluster_ids[i]; under the
    null, the A/B labels are exchangeable per CLUSTER, not per observation, so
    every observation of one cluster flips sign together. Use it when several
    paired observations come from one unit that is not independent inside --
    e.g. the five family outcomes of one respec_cascade chain.

    The statistic is the same mean paired difference (A - B) over all
    observations that `paired_permutation_test` reports, so `observed_mean_diff`
    is comparable between the two; only the null distribution differs. Exact
    over the 2**clusters sign patterns (always while clusters <=
    max_exact_clusters; for more clusters while the null distribution stays
    small), a corrected Monte Carlo estimate otherwise (see
    `_sign_flip_p_value`); `exact` in the result says which.
    `p_value_floor` = 2/2**clusters."""
    cluster_diffs: dict[str, list[float]] = {}
    for cluster, a, b in zip(cluster_ids, values_a, values_b):
        if a is None or b is None:
            continue
        cluster_diffs.setdefault(cluster, []).append(a - b)
    n_obs = sum(len(ds) for ds in cluster_diffs.values())
    if len(cluster_diffs) < 2:
        return {"observed_mean_diff": None, "p_value": None, "n_clusters": len(cluster_diffs),
                "n_paired_observations": n_obs,
                "reason": "fewer than 2 clusters with paired values on both sides"}
    unit_sums = [sum(ds) for ds in cluster_diffs.values()]
    result = {
        "observed_mean_diff": sum(unit_sums) / n_obs,
        **_sign_flip_p_value(unit_sums, n_permutations, seed, max_exact_clusters),
        "p_value_floor": 2 / 2 ** len(unit_sums),
        "n_clusters": len(unit_sums),
        "n_paired_observations": n_obs,
    }
    result["method"] = ("cluster-level paired sign-flip test, exact enumeration" if result["exact"]
                        else "cluster-level paired sign-flip test, Monte Carlo (null distribution too large to enumerate)")
    return result


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
