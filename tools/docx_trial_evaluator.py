"""PAPER-S20: grades a trial's OUTPUT docx against the broker's expected/
forbidden ground truth, entirely outside the agent (the agent never sees
this module or its verdicts). Structural, not semantic -- deliberately
narrow scope for a first commissioning pilot.

Substring matching (not exact-paragraph-equality) is used for the marker
title deliberately: the visible paragraph is a full APA-formatted
citation (e.g. "Marker, P. (2026). Commissioning Pilot Marker Publication
<id>."), not the bare title text, and the exact surrounding formatting is
allowed to differ between the control arm (whatever the agent's generic
edit produced) and the treatment arm (Meridian's own APA formatter).
"""
from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from docx_trial_broker import _paragraph_texts  # noqa: E402
from graph_scorer import score_keep_survival, score_comment_set_survival, _comment_range_precision  # noqa: E402
# PAPER-S24 comment_targeting only: reuses independent_gold_extractor.py's own
# namespace constants and _local_text helper (never duplicating OOXML
# text-extraction logic), the same convention docx_anchor_prober.py's own
# resolve_comment_targeting_clusters already established for this family.
from independent_gold_extractor import _W, _W14, _local_text, _q  # noqa: E402


def _package_is_valid_docx(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, "output file does not exist"
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return False, f"corrupt zip member: {bad}"
            names = set(zf.namelist())
        for required in ("[Content_Types].xml", "_rels/.rels", "word/document.xml"):
            if required not in names:
                return False, f"missing required part: {required}"
        return True, None
    except zipfile.BadZipFile as exc:
        return False, f"not a valid zip/docx: {exc}"


def _paragraphs_containing(paragraphs: list[str], substring: str) -> list[str]:
    return [p for p in paragraphs if substring in p]


def grade_forward_trial(
    output_docx: Path, paragraphs_before: list[str], expected_marker_title: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    matches = _paragraphs_containing(paragraphs_after, expected_marker_title)
    delta = len(paragraphs_after) - len(paragraphs_before)
    missing_originals = [p for p in paragraphs_before if p not in paragraphs_after]

    checks = {
        "output_is_valid_docx": True,
        "marker_title_present_in_exactly_one_paragraph": len(matches) == 1,
        "no_original_paragraphs_removed": not missing_originals,
        "paragraph_count_delta_is_at_least_one": delta >= 1,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_before": len(paragraphs_before),
        "paragraph_count_after": len(paragraphs_after),
        "matching_paragraphs": matches,
        "missing_original_paragraphs": missing_originals,
    }


def grade_inverse_trial(
    output_docx: Path, paragraphs_before_forward: list[str], expected_marker_title: str,
) -> dict[str, Any]:
    """PAPER-S7 correction (2026-08-30): a long-horizon K=4 bibliography chain
    smoke test found this evaluator marking every inverse "pass" while a
    "References" heading paragraph (created once by the FIRST forward call,
    per insert_bibliography_entry's own "locate-or-create the heading" design
    -- remove_bibliography_entry only ever removes the entry, never the
    shared heading) was silently left behind forever after. The original
    checks here (marker gone + no ORIGINAL paragraph lost) are both satisfied
    even with a stray extra paragraph present, because neither checks for an
    UNEXPECTED addition -- only for a removal. Added
    "exact_paragraph_list_restored" as the authoritative check; the two
    original checks are kept for their more specific failure messages, but
    the verdict now requires all three.
    """
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    matches = _paragraphs_containing(paragraphs_after, expected_marker_title)
    missing_originals = [p for p in paragraphs_before_forward if p not in paragraphs_after]
    unexpected_additions = [p for p in paragraphs_after if p not in paragraphs_before_forward]

    checks = {
        "output_is_valid_docx": True,
        "marker_entry_removed": len(matches) == 0,
        "no_pre_forward_paragraph_lost": not missing_originals,
        "exact_paragraph_list_restored": paragraphs_after == paragraphs_before_forward,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_after": len(paragraphs_after),
        "paragraph_count_before_forward": len(paragraphs_before_forward),
        "remaining_matching_paragraphs": matches,
        "missing_pre_forward_paragraphs": missing_originals,
        "unexpected_added_paragraphs": unexpected_additions,
    }


# ---------------------------------------------------------------------------
# inline families (citation): marker text is APPENDED to an EXISTING
# paragraph, not a new one -- grading compares that one paragraph's text
# before/after instead of the whole-document paragraph SET.
# ---------------------------------------------------------------------------

def grade_forward_trial_inline(
    output_docx: Path, paragraphs_before: list[str], anchor_text_before: str, marker_text: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    anchor_matches_after = [p for p in paragraphs_after if p.startswith(anchor_text_before[:40]) and marker_text in p]
    other_before = [p for p in paragraphs_before if p != anchor_text_before]
    missing_others = [p for p in other_before if p not in paragraphs_after]
    unexpected_marker_elsewhere = [
        p for p in paragraphs_after
        if marker_text in p and not p.startswith(anchor_text_before[:40])
    ]

    checks = {
        "output_is_valid_docx": True,
        "anchor_paragraph_now_contains_marker_exactly_once": len(anchor_matches_after) == 1,
        "no_other_paragraph_lost": not missing_others,
        "marker_not_leaked_into_other_paragraphs": not unexpected_marker_elsewhere,
        "paragraph_count_unchanged": len(paragraphs_after) == len(paragraphs_before),
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_before": len(paragraphs_before),
        "paragraph_count_after": len(paragraphs_after),
        "anchor_matches_after": anchor_matches_after,
        "missing_other_paragraphs": missing_others,
        "unexpected_marker_elsewhere": unexpected_marker_elsewhere,
    }


def grade_inverse_trial_inline(
    output_docx: Path, paragraphs_before_forward: list[str], marker_text: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    remaining_marker = [p for p in paragraphs_after if marker_text in p]
    missing_originals = [p for p in paragraphs_before_forward if p not in paragraphs_after]

    checks = {
        "output_is_valid_docx": True,
        "marker_fully_removed": not remaining_marker,
        "exact_pre_forward_paragraph_set_restored": not missing_originals,
        "paragraph_count_restored": len(paragraphs_after) == len(paragraphs_before_forward),
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_after": len(paragraphs_after),
        "paragraph_count_before_forward": len(paragraphs_before_forward),
        "remaining_marker_paragraphs": remaining_marker,
        "missing_pre_forward_paragraphs": missing_originals,
    }


# ---------------------------------------------------------------------------
# section_reorder: no paragraph is added/removed/reworded -- only ORDER
# changes. Grading compares the paragraph LIST (order-sensitive), not a set.
# ---------------------------------------------------------------------------

def grade_forward_trial_reorder(
    output_docx: Path, paragraphs_before: list[str], section_heading_text: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    same_multiset = sorted(paragraphs_after) == sorted(paragraphs_before)
    order_changed = paragraphs_after != paragraphs_before
    # Found live (2026-08-31) grading a real-world document corpus:
    # section_heading_text comes from document_outline's raw run text (not
    # stripped), while paragraphs_after comes from _paragraph_texts (every
    # entry IS stripped) -- any heading with real, incidental leading/
    # trailing whitespace in its OOXML runs (common in organic documents,
    # rare in the curated DocOps benchmark corpus) could never match here
    # even on a byte-perfect round trip. Strip both sides of this specific
    # comparison to match how paragraphs_after was already produced.
    heading_present = section_heading_text.strip() in paragraphs_after

    checks = {
        "output_is_valid_docx": True,
        "no_paragraph_added_or_removed_or_reworded": same_multiset,
        "order_actually_changed": order_changed,
        "moved_heading_still_present": heading_present,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_before": len(paragraphs_before),
        "paragraph_count_after": len(paragraphs_after),
    }


def grade_inverse_trial_reorder(
    output_docx: Path, paragraphs_before_forward: list[str],
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    exact_order_restored = paragraphs_after == paragraphs_before_forward

    checks = {
        "output_is_valid_docx": True,
        "exact_original_order_restored": exact_order_restored,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_after": len(paragraphs_after),
        "paragraph_count_before_forward": len(paragraphs_before_forward),
    }


# ---------------------------------------------------------------------------
# equation (new paragraph, mirrors grade_forward_trial/grade_inverse_trial's
# "new paragraph" shape, but the marker can NEVER be found via
# _paragraph_texts: a pure-equation paragraph's content lives entirely in
# <m:oMath>/<m:t>, a different namespace than the <w:t> runs _paragraph_texts
# reads. Confirmed directly (2026-09-03): inserting a real equation and
# calling parse_docx() on the result shows that paragraph's own "text" field
# as an empty string. Uses parse_docx_equations_local's own flat_text
# (flattened <m:t> content) for the marker check instead; the surrounding
# "did any OTHER paragraph change" checks still use _paragraph_texts since
# that part of the document has nothing to do with OMML.
# ---------------------------------------------------------------------------

def _import_docs_intel():
    from meridian_docs import docs_intel

    return docs_intel


def _equation_flat_texts(output_docx: Path) -> list[str]:
    docs_intel = _import_docs_intel()
    equations = docs_intel.parse_docx_equations_local(str(output_docx))
    return [e.get("flat_text") or "" for e in equations]


def grade_forward_trial_equation(
    output_docx: Path, paragraphs_before: list[str], marker: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    matches = [t for t in _equation_flat_texts(output_docx) if marker in t]
    missing_originals = [p for p in paragraphs_before if p not in paragraphs_after]

    checks = {
        "output_is_valid_docx": True,
        "marker_equation_present_exactly_once": len(matches) == 1,
        "no_original_paragraph_lost": not missing_originals,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_before": len(paragraphs_before),
        "paragraph_count_after": len(paragraphs_after),
        "matching_equation_flat_texts": matches,
        "missing_original_paragraphs": missing_originals,
    }


def grade_inverse_trial_equation(
    output_docx: Path, paragraphs_before_forward: list[str], marker: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    remaining_matches = [t for t in _equation_flat_texts(output_docx) if marker in t]
    missing_originals = [p for p in paragraphs_before_forward if p not in paragraphs_after]

    checks = {
        "output_is_valid_docx": True,
        "marker_equation_removed": len(remaining_matches) == 0,
        "exact_pre_forward_paragraph_list_restored": paragraphs_after == paragraphs_before_forward,
        "no_pre_forward_paragraph_lost": not missing_originals,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_after": len(paragraphs_after),
        "paragraph_count_before_forward": len(paragraphs_before_forward),
        "remaining_matching_equation_flat_texts": remaining_matches,
        "missing_pre_forward_paragraphs": missing_originals,
    }


# ---------------------------------------------------------------------------
# table_structural (new paragraph inside a new table cell -- unlike
# equation, a table cell's own paragraph text IS ordinary <w:t> content, so
# _paragraph_texts (which walks every <w:p> in the whole tree, including
# ones nested inside table cells) already sees the marker directly; no
# special OMML-style extractor is needed the way equation's flat_text is.)
# ---------------------------------------------------------------------------

def grade_forward_trial_table_structural(
    output_docx: Path, paragraphs_before: list[str], marker: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    matches = _paragraphs_containing(paragraphs_after, marker)
    missing_originals = [p for p in paragraphs_before if p not in paragraphs_after]

    checks = {
        "output_is_valid_docx": True,
        "marker_table_cell_present_exactly_once": len(matches) == 1,
        "no_original_paragraph_lost": not missing_originals,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_before": len(paragraphs_before),
        "paragraph_count_after": len(paragraphs_after),
        "matching_paragraphs": matches,
        "missing_original_paragraphs": missing_originals,
    }


def grade_inverse_trial_table_structural(
    output_docx: Path, paragraphs_before_forward: list[str], marker: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    remaining_matches = _paragraphs_containing(paragraphs_after, marker)
    missing_originals = [p for p in paragraphs_before_forward if p not in paragraphs_after]

    checks = {
        "output_is_valid_docx": True,
        "marker_table_removed": len(remaining_matches) == 0,
        "exact_pre_forward_paragraph_list_restored": paragraphs_after == paragraphs_before_forward,
        "no_pre_forward_paragraph_lost": not missing_originals,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_after": len(paragraphs_after),
        "paragraph_count_before_forward": len(paragraphs_before_forward),
        "remaining_matching_paragraphs": remaining_matches,
        "missing_pre_forward_paragraphs": missing_originals,
    }


# ---------------------------------------------------------------------------
# respec_cascade (PAPER-S23) phase orchestration.
#
# Ground-truth note (2026-09-20, written while implementing this section):
# the task brief that specified this section claimed
# `_bibliography_entry_prf1`, `_citation_marker_prf1` (graph_scorer.py) and
# `score_keep_survival` (graph_scorer.py) "do NOT exist yet." Re-reading
# graph_scorer.py directly (this project's own standing rule -- never trust
# a stale ground-truth summary, re-derive from the file) found all three
# already implemented, uncommitted, in this shared repo's working tree
# (`git diff --stat` showed graph_scorer.py, docx_trial_broker.py, and
# docx_anchor_prober.py all modified by a concurrent session; this file,
# docx_trial_evaluator.py, was not). `score_keep_survival`'s real signature
# -- `score_keep_survival(checkpoint_a_items: dict, checkpoint_b_items:
# dict, kept_element_markers: dict[str, str], excluded_paragraph_texts:
# list[str] | None = None) -> dict[str, Any]`, operating on
# `{"paragraphs": [{"text": ...}, ...]}` extractor-shaped "items" dicts, not
# raw `.docx` paths or flat text lists -- is what the three functions below
# actually call, via the small `_items_from_paragraph_texts` adapter below
# (this module has never needed the full extractor-item shape before; every
# existing `grade_*` function above compares flat text lists directly).
# `tools/docx_anchor_prober.py`'s new `resolve_section_redirect_plan` was
# also read directly to confirm `move_section`'s real
# `destination_position: "after"` semantics (verified there, 2026-09-20,
# against the live tool's own docstring) before writing
# `_section_heading_adjacency` below, rather than guessing at the
# destination convention.
# ---------------------------------------------------------------------------

FAMILY_ORDER: tuple[str, ...] = ("bibliography", "citation", "section_reorder", "equation", "caption")
"""R' from docs/paper-s23-respec-cascade-protocol-v0.md section 2.3 -- the
five-family contingency rotation, locked because insert_table/remove_table
are confirmed absent from the live meridian-docs tool manifest (protocol
section 1.2a item 2). table_structural is never part of respec_cascade."""

# meridian_docs.docs_intel.insert_bibliography_entry "Locates (or creates) a
# References heading at the end of the document" -- on any corpus document
# that has NO pre-existing References/Bibliography heading (confirmed live,
# 2026-09-22 primary sweep: jcshm-si.docx has zero such headings, unlike
# jcshm-manuscript.docx/masters-dissertation-defense.docx which both already
# have one), this auto-created heading paragraph (`_build_references_heading`,
# literal text "References") is a SECOND legitimate addition beyond the entry
# paragraph itself -- documented, intended tool behavior, not collateral
# damage. Every bibliography-family collateral/final-structure check below
# must treat it as an expected touch point, or every chain on a
# heading-less document fails Phase 1 (and Phase 3's final-structure check)
# on this alone, regardless of anchor-set -- exactly the uniform
# `completed_with_failure` pattern observed across all 4 jcshm-si treatment
# chains in that sweep. Also never removed by `remove_bibliography_entry`
# (only the entry is), so it persists into Phase 3 and must be accounted for
# there too.
_AUTO_CREATED_REFERENCES_HEADING_TEXT = "References"

_PHASE1_LAST_STEP = "1.5"   # Caption, the final Phase-1 step in R' order
_PHASE2_LAST_STEP = "2.3"   # SectionReorder redirect; five-family Phase 2 has no 2.2 (Table)
_PHASE3_LAST_STEP = "3.5"   # Caption's own insert-then-remove, the final Phase-3 family in R'


def _items_from_paragraph_texts(paragraph_texts: list[str]) -> dict[str, Any]:
    """Adapts this module's own flat paragraph-text-list shape (what
    `_paragraph_texts` returns) into the `{"paragraphs": [{"text": ...},
    ...]}` "items" shape `graph_scorer.score_round_trip_editability` /
    `score_keep_survival` expect (the shape a real extractor's `parse_docx`
    -style output already has). Only `"text"` is populated -- `para_id` is
    left out entirely rather than faked as `None` for every entry, since
    `score_keep_survival` never reads `para_id`."""
    return {"paragraphs": [{"text": t} for t in paragraph_texts]}


def _items_with_equations(docx_path: Path, paragraph_texts: list[str]) -> dict[str, Any]:
    """Like `_items_from_paragraph_texts`, but ALSO folds each equation's
    flat text (`_equation_flat_texts`) into the same `"paragraphs"` list.

    Found live (2026-09-22 RunPod smoke test): `score_keep_survival` only
    ever reads `checkpoint_*_items["paragraphs"]`, which -- being built from
    `_paragraph_texts` -- structurally CANNOT see equation content at all (a
    pure-equation paragraph's `<w:t>` text is empty, confirmed directly
    against the real jcshm-manuscript.docx corpus document; see
    `grade_forward_trial_equation`'s own module comment on this same fact).
    This means `E` (the equation family's own kept target in Phase 2/3) was
    being silently, permanently invisible to every keep-survival check --
    not merely absent from a marker-text mismatch, but structurally
    unverifiable regardless of what text was passed for it. Merging
    equations' flat text into the same comparable-items list (rather than
    inventing a second, parallel "equations" concept `score_keep_survival`
    would need to know about) fixes this with no change to that function at
    all: exact-multiset text matching does not care which XML namespace a
    comparable unit came from, and the unintended-drift remainder check
    gains real equation-collateral-damage detection as a side effect,
    which it also did not have before."""
    return {"paragraphs": [{"text": t} for t in (*paragraph_texts, *_equation_flat_texts(docx_path))]}


def _collateral_diff_outside_touched(
    paragraphs_before: list[str], paragraphs_after: list[str],
    touched_before: list[str], touched_after: list[str],
) -> tuple[bool, dict[str, list[str]]]:
    """Multiset (Counter) diff of `paragraphs_before` vs. `paragraphs_after`,
    after removing exactly the paragraph texts a family's OWN grader already
    identified as ITS intentional touch point (a new marker paragraph for an
    insert, or an existing paragraph's before/after text for citation's
    in-place edit). `section_reorder` and `equation` deliberately contribute
    no touched-text entries: the former only changes paragraph ORDER, never
    paragraph TEXT (`grade_forward_trial_reorder`'s own multiset+order
    checks already cover it), and the latter's marker never appears in
    `_paragraph_texts` at all -- a pure `<m:oMath>` paragraph has no `<w:t>`
    text (see this file's equation-family comment block above). Whatever
    remains unexplained after removing the known touch points is genuine
    collateral drift -- this is the generalization of each individual
    family's own "no_original_paragraph_lost" check across all five targets
    in one pass, per protocol section 4's Checkpoint A requirement."""
    before_ctr = Counter(paragraphs_before)
    after_ctr = Counter(paragraphs_after)
    for t in touched_before:
        before_ctr[t] -= 1
    for t in touched_after:
        after_ctr[t] -= 1
    before_remainder = Counter({k: v for k, v in before_ctr.items() if v > 0})
    after_remainder = Counter({k: v for k, v in after_ctr.items() if v > 0})
    clean = before_remainder == after_remainder
    # 2026-09-22 correction (found live, RunPod smoke test control arm):
    # this previously returned the two FULL remainder multisets side by
    # side (`before_remainder.elements()`/`after_remainder.elements()`),
    # not their actual difference -- so any time `clean` was False, the
    # reported "unexplained_missing"/"unexplained_added" dumped nearly the
    # entire document (every paragraph present in each remainder, whether
    # or not its count actually changed) instead of showing what genuinely
    # differed. `Counter` subtraction (`-`) keeps only positive-count
    # differences, which is what these fields were always meant to report.
    missing_diff = before_remainder - after_remainder
    added_diff = after_remainder - before_remainder
    return clean, {
        "unexplained_missing": sorted(missing_diff.elements()),
        "unexplained_added": sorted(added_diff.elements()),
    }


def _end_of_heading_subtree_index(headings: list[dict[str, Any]], index: int) -> int:
    """Index of the heading immediately after the subtree rooted at
    `headings[index]` -- i.e. skip forward past every descendant (any
    heading with `level` deeper than `headings[index]`'s own), stopping at
    the first same-or-shallower-level heading, or `len(headings)` if none
    remains. Mirrors `move_section`'s own real destination_position="after"
    semantics, `_locate_section_bounds` (`meridian_docs/docs_intel.py`:
    "resolve to after that heading's WHOLE pre-existing content"), applied
    to the flat heading-outline list this module already works with rather
    than the raw paragraph-range that function itself operates on."""
    root_level = headings[index].get("level")
    i = index + 1
    while i < len(headings):
        level = headings[i].get("level")
        if root_level is None or level is None or level <= root_level:
            break
        i += 1
    return i


def _section_heading_adjacency(
    docx_path: Path, section_id: str, d1_heading_para_id: str, d2_heading_para_id: str,
) -> dict[str, Any]:
    """Reads the live heading outline (`docs_intel.document_outline`, via
    this module's own `_import_docs_intel`) and checks whether the section
    identified by `section_id` sits immediately after the END of D1's,
    resp. D2's, own heading SUBTREE -- the structural signature
    `move_section`'s real, verified `destination_position: "after"`
    semantics produce.

    2026-09-22 correction (found live, RunPod smoke test against the real
    jcshm-manuscript.docx corpus document): this previously checked
    `section_index == d2_index + 1` -- "the very next heading after D2's
    OWN heading line" -- which is wrong whenever D2 has child headings.
    `move_section`'s real behavior (confirmed directly against
    `meridian_docs/docs_intel.py::move_section`'s own destination-resolution
    comment, "resolve to after that heading's WHOLE pre-existing content",
    which calls the SAME `_locate_section_bounds` function used to resolve
    the section being moved) places the section after the destination
    heading's ENTIRE subtree, not immediately after its own heading line.
    Confirmed empirically: this run's D2 ("4.1 MIDLINE EVALUATION") has 4
    child subsections (4.1.1-4.1.4); the section landed correctly, right
    before "4.2 WIDTH CORRESPONDENCE AND EVALUATION" (D2's subtree's real
    end), which the old index+1 check misread as "not at D2" -- a false
    failure, not a real one. Fixed via `_end_of_heading_subtree_index`.

    Position -- not text presence alone -- is what distinguishes "still at
    D1" from "moved on to D2": both D1's and D2's own heading text remain in
    the document the whole time (a destination heading is never removed),
    so a presence-only check (`grade_forward_trial_reorder`'s own
    `moved_heading_still_present`) cannot by itself tell D1 from D2.

    D1/D2 are matched by their stable `para_id` (as
    `resolve_section_redirect_plan`/`resolve_multiple_section_reorder_plans`
    already resolve and hand the orchestrator), NOT by heading text: a
    first-match-by-text lookup would silently resolve to the wrong heading
    on any document with a repeated heading title (e.g. two chapters each
    containing an "Introduction" or "Summary" subsection -- plausible on
    the real, dense corpus documents this family runs against, one of which
    has 111 headings) -- exactly the "positional guessing" failure mode
    this whole benchmark family exists to detect, which a text-matching
    grader must not itself reintroduce."""
    docs_intel = _import_docs_intel()
    outline = docs_intel.document_outline(str(docx_path))
    headings = outline.get("headings") or []

    section_index = next((i for i, h in enumerate(headings) if h.get("para_id") == section_id), None)
    d1_index = next((i for i, h in enumerate(headings) if h.get("para_id") == d1_heading_para_id), None)
    d2_index = next((i for i, h in enumerate(headings) if h.get("para_id") == d2_heading_para_id), None)

    d1_subtree_end = _end_of_heading_subtree_index(headings, d1_index) if d1_index is not None else None
    d2_subtree_end = _end_of_heading_subtree_index(headings, d2_index) if d2_index is not None else None

    return {
        "section_found": section_index is not None,
        "d1_found": d1_index is not None,
        "d2_found": d2_index is not None,
        "at_d1": section_index is not None and d1_subtree_end is not None and section_index == d1_subtree_end,
        "at_d2": section_index is not None and d2_subtree_end is not None and section_index == d2_subtree_end,
        "section_heading_text": headings[section_index].get("text") if section_index is not None else None,
    }


def _grade_family_forward(
    family: str, output_docx: Path, paragraphs_before: list[str], target: dict[str, Any],
) -> dict[str, Any]:
    """Local family-dispatch table for respec_cascade's five families,
    mirroring the SHAPE of `run_paper_s7_benchmark.py`'s own `_grade_forward`
    (described here, never imported -- importing it would create a backwards
    dependency, since `run_paper_s7_benchmark.py` imports FROM this file) --
    reduced to exactly the five families in `FAMILY_ORDER`
    (`table_structural` dropped, per the five-family contingency). `caption`
    intentionally reuses `grade_forward_trial`, the SAME function
    `bibliography` uses: both insert a brand-new whole paragraph, and this
    file has never had a separate caption-specific forward grader (see this
    file's own docstring, "used by BOTH bibliography AND caption")."""
    if family == "bibliography":
        return grade_forward_trial(output_docx, paragraphs_before, target["marker_text"])
    if family == "citation":
        return grade_forward_trial_inline(
            output_docx, paragraphs_before, target["anchor_text_before"], target["marker_text"],
        )
    if family == "section_reorder":
        return grade_forward_trial_reorder(output_docx, paragraphs_before, target["section_heading_text"])
    if family == "equation":
        return grade_forward_trial_equation(output_docx, paragraphs_before, target["marker"])
    if family == "caption":
        return grade_forward_trial(output_docx, paragraphs_before, target["marker_text"])
    raise ValueError(f"unknown respec_cascade family: {family!r}")


def _grade_family_inverse(
    family: str, output_docx: Path, paragraphs_before_forward: list[str], target: dict[str, Any],
) -> dict[str, Any]:
    """Inverse-direction sibling of `_grade_family_forward` -- same five-
    family dispatch, same caption/bibliography sharing."""
    if family == "bibliography":
        return grade_inverse_trial(output_docx, paragraphs_before_forward, target["marker_text"])
    if family == "citation":
        return grade_inverse_trial_inline(output_docx, paragraphs_before_forward, target["marker_text"])
    if family == "section_reorder":
        return grade_inverse_trial_reorder(output_docx, paragraphs_before_forward)
    if family == "equation":
        return grade_inverse_trial_equation(output_docx, paragraphs_before_forward, target["marker"])
    if family == "caption":
        return grade_inverse_trial(output_docx, paragraphs_before_forward, target["marker_text"])
    raise ValueError(f"unknown respec_cascade family: {family!r}")


_FAMILY_OWN_TARGET_CHECKS: dict[str, tuple[str, ...]] = {
    # Each family's own forward grader bundles two DIFFERENT questions into
    # one `checks` dict: (a) "did MY OWN edit's target land correctly" and
    # (b) "did nothing ELSE in the whole document change" (e.g.
    # `no_original_paragraphs_removed`, `paragraph_count_unchanged`,
    # `no_paragraph_added_or_removed_or_reworded`). Question (b) is only
    # correct to ask of a SINGLE isolated edit -- these graders were built
    # for the existing single-family K=1 benchmark, where "before the
    # phase" and "before this edit" are the same paragraph list. In
    # respec_cascade's Phase 1, five DIFFERENT families each edit the SAME
    # document in sequence, so by the time grade_phase1_build calls a given
    # family's grader against the PHASE's cumulative final output, the
    # other four families' own legitimate edits are real, expected changes
    # -- but question (b), scoped to "nothing besides MY edit changed",
    # necessarily sees them as violations and always fails. Confirmed
    # empirically (2026-09-22 smoke test, real subprocess trial against
    # jcshm-manuscript.docx): all five families showed verdict="fail" with
    # question-(b) checks naming EACH OTHER's own successful edits as
    # "missing original paragraphs" / "paragraph count changed", while the
    # PHASE-WIDE collateral check below (which correctly accounts for all
    # five targets at once via Counter-based multiset diff, not a single
    # target) reported clean.
    #
    # This dict names only the (a)-type checks -- the ones that verify
    # THIS family's own target, not the whole document -- for
    # grade_phase1_build to gate on. The (b)-type question is answered once,
    # correctly, for all five targets together, by the collateral check.
    "bibliography": ("marker_title_present_in_exactly_one_paragraph", "paragraph_count_delta_is_at_least_one"),
    "citation": ("anchor_paragraph_now_contains_marker_exactly_once", "marker_not_leaked_into_other_paragraphs"),
    "section_reorder": ("order_actually_changed", "moved_heading_still_present"),
    "equation": ("marker_equation_present_exactly_once",),
    "caption": ("marker_title_present_in_exactly_one_paragraph", "paragraph_count_delta_is_at_least_one"),
}


def _family_own_target_ok(family: str, result: dict[str, Any]) -> bool:
    checks = result.get("checks") or {}
    if not checks.get("output_is_valid_docx", False):
        return False
    required = _FAMILY_OWN_TARGET_CHECKS.get(family)
    if required is None:
        raise ValueError(f"unknown respec_cascade family: {family!r}")
    return all(checks.get(name, False) for name in required)


# Phase 3's per-family sibling of _FAMILY_OWN_TARGET_CHECKS above, for the
# INVERSE graders' checks dicts. Same rationale: `grade_inverse_trial*`'s
# broad checks (`exact_pre_forward_paragraph_list_restored`,
# `paragraph_count_restored`, etc.) ask "does the WHOLE document exactly
# match checkpoint B" -- correct when every one of the 5 families' own net
# round trip genuinely completed, but a misattribution risk when a SINGLE
# family's step degrades (e.g. an equation render-gate timeout): the other
# four families' own narrow checks would still correctly show their own
# target is fine, but their broad checks would ALSO flip to "fail" purely
# because the broken family's leftover state changed the whole-document
# comparison. `section_reorder` has no narrower check available -- its own
# net-effect check (`exact_original_order_restored`) inherently requires
# the whole document to match, so it is not included here and keeps using
# its full verdict (the best granularity this family's grader can offer).
_FAMILY_OWN_INVERSE_TARGET_CHECKS: dict[str, tuple[str, ...]] = {
    "bibliography": ("marker_entry_removed",),
    "citation": ("marker_fully_removed",),
    "equation": ("marker_equation_removed",),
    "caption": ("marker_entry_removed",),
}


def _family_own_inverse_target_ok(family: str, result: dict[str, Any]) -> bool:
    checks = result.get("checks") or {}
    if not checks.get("output_is_valid_docx", False):
        return False
    required = _FAMILY_OWN_INVERSE_TARGET_CHECKS.get(family)
    if required is None:
        # section_reorder: no narrower check exists; fall back to the full verdict.
        return result.get("verdict") == "pass"
    return all(checks.get(name, False) for name in required)


def grade_phase1_build(
    output_docx: Path, paragraphs_before: list[str], targets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Checkpoint A (protocol section 4): grades the end of Phase 1 (BUILD,
    5 steps, forward-only, order R') in one pass -- each family's own
    EXISTING forward grader, called with that family's own args from
    `targets`, for its OWN target's narrow presence/correctness checks only
    (see `_family_own_target_ok`/`_FAMILY_OWN_TARGET_CHECKS`) -- plus one
    generalized, phase-wide check: zero paragraph-text diff anywhere outside
    the five targets' own touched paragraphs, against `paragraphs_before`
    (the pristine, pre-Phase-1 paragraph list).

    `targets` must have exactly the five keys in `FAMILY_ORDER`, e.g.:
        {"bibliography": {"marker_text": ...},
         "citation": {"anchor_text_before": ..., "marker_text": ...},
         "section_reorder": {"section_heading_text": ...},
         "equation": {"marker": ...},
         "caption": {"marker_text": ...}}

    `_package_is_valid_docx` is the hard gate, checked first: an invalid
    package short-circuits with `{"package_valid": False, "status":
    "chain_broken_at_step_N"}` and every per-family/collateral check is
    skipped, per protocol section 4's "later steps are never run against a
    document already known to be invalid." (This function only ever sees
    Phase 1's OWN final output docx, so its own gate stands in for the last
    of the per-step gates the protocol requires after every one of the 9-15
    steps in a chain -- the per-step gates for steps 1.1-1.4 are the
    orchestrator's own responsibility, `tools/run_respec_cascade_family.py`,
    out of this function's scope.)
    """
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {
            "package_valid": False,
            "status": f"chain_broken_at_step_{_PHASE1_LAST_STEP}",
            "reason": f"invalid output package: {err}",
            "phase1_pass": False,
        }

    paragraphs_after = _paragraph_texts(output_docx)

    family_results: dict[str, dict[str, Any]] = {}
    touched_before: list[str] = []
    touched_after: list[str] = []
    for family in FAMILY_ORDER:
        if family not in targets:
            raise ValueError(f"grade_phase1_build: targets is missing required family {family!r}")
        target = targets[family]
        result = _grade_family_forward(family, output_docx, paragraphs_before, target)
        family_results[family] = result

        if family in ("bibliography", "caption"):
            touched_after.extend(result.get("matching_paragraphs", []))
            if family == "bibliography" and _AUTO_CREATED_REFERENCES_HEADING_TEXT not in paragraphs_before:
                touched_after.append(_AUTO_CREATED_REFERENCES_HEADING_TEXT)
        elif family == "citation":
            touched_before.append(target["anchor_text_before"])
            touched_after.extend(result.get("anchor_matches_after", []))
        # section_reorder, equation: no `_paragraph_texts` CONTENT touched
        # (order-only, resp. no <w:t> text at all) -- see helper docstring.

    collateral_clean, collateral_detail = _collateral_diff_outside_touched(
        paragraphs_before, paragraphs_after, touched_before, touched_after,
    )

    all_family_pass = all(_family_own_target_ok(f, r) for f, r in family_results.items())
    phase1_pass = bool(all_family_pass and collateral_clean)

    return {
        "package_valid": True,
        "families": family_results,
        "collateral_clean": collateral_clean,
        "collateral_detail": collateral_detail,
        "phase1_pass": phase1_pass,
    }


def grade_phase2_respec(
    checkpoint_a_docx: Path,
    checkpoint_b_docx: Path,
    paragraphs_at_checkpoint_a: list[str],
    citation_marker_text: str,
    citation_anchor_text_before: str,
    section_id: str,
    expected_d1_heading_para_id: str,
    expected_d2_heading_para_id: str,
    kept_markers: dict[str, str],
) -> dict[str, Any]:
    """Checkpoint B (protocol section 4, "the design's central, novel
    test"): grades the end of Phase 2 (RESPEC -- 2.1 Citation inverse, 2.3
    SectionReorder redirect D1->D2; five-family contingency has no 2.2
    Table). `checkpoint_a_docx` is re-read directly (via `_items_with_
    equations`, alongside `checkpoint_b_docx`) to fold each checkpoint's
    OWN equation content into `score_keep_survival`'s comparison -- `E`'s
    survival can only be checked this way, never from `paragraphs_at_
    checkpoint_a`'s flat text alone (see `_items_with_equations`'s own
    docstring for why: a pure-equation paragraph's `<w:t>` text is empty).

    (a) Citation absence is checked directly against `checkpoint_b_docx`'s
    own paragraph texts, NOT by calling `grade_inverse_trial_inline` itself:
    that function's `exact_pre_forward_paragraph_list_restored` check
    requires exact equality to `paragraphs_before_forward`, which would
    spuriously fail here since 2.3's OWN section move and every OTHER
    Phase-1 target (`B`, `D1`-move, `E`, `Cap`) are still legitimately
    present between checkpoints A and B -- this is not the same shape as a
    single family's own isolated forward/inverse round trip.

    (b) Section position uses `_section_heading_adjacency` (matched by
    `para_id`, not heading text -- see that function's own docstring)
    against `checkpoint_b_docx` (not `grade_forward_trial_reorder`'s own
    multiset+order check, which was written for a single isolated move
    against the document's pristine original, not a doubly-moved section
    mid-chain).

    (c) `B`/`E`/`Cap` survival is graded via `graph_scorer.score_keep_survival`
    (checkpoint A -> checkpoint B). `score_keep_survival`'s own remainder
    comparison is Counter-based (order-blind), so 2.3's section relocation
    needs NO explicit exclusion at all -- moving a section's paragraphs
    changes their position, not their text or count, which a multiset diff
    is naturally blind to. Only 2.1's citation removal is a genuine CONTENT
    change (the anchor paragraph's text differs between checkpoints A and
    B), so its two distinct forms -- the actual checkpoint-A paragraph that
    carries `citation_marker_text` (found by searching
    `paragraphs_at_checkpoint_a` directly, not by passing the bare marker
    substring itself, which would never exact-match a whole paragraph's
    normalized text) and `citation_anchor_text_before` (the anchor's
    restored, checkpoint-B form) -- are both passed as
    `excluded_paragraph_texts`.

    `_package_is_valid_docx` gates on `checkpoint_b_docx` first, exactly as
    task 1: an invalid package short-circuits with `{"package_valid": False,
    "status": "chain_broken_at_step_N"}`.
    """
    ok, err = _package_is_valid_docx(checkpoint_b_docx)
    if not ok:
        return {
            "package_valid": False,
            "status": f"chain_broken_at_step_{_PHASE2_LAST_STEP}",
            "reason": f"invalid output package: {err}",
            "phase2_pass": False,
        }

    paragraphs_at_checkpoint_b = _paragraph_texts(checkpoint_b_docx)

    remaining_citation_markers = [p for p in paragraphs_at_checkpoint_b if citation_marker_text in p]
    citation_absent = not remaining_citation_markers

    section_position = _section_heading_adjacency(
        checkpoint_b_docx, section_id, expected_d1_heading_para_id, expected_d2_heading_para_id,
    )
    section_at_d2 = bool(section_position["at_d2"] and not section_position["at_d1"])

    checkpoint_a_citation_paragraphs = [p for p in paragraphs_at_checkpoint_a if citation_marker_text in p]
    excluded_texts = list(checkpoint_a_citation_paragraphs) + [citation_anchor_text_before]
    keep_survival = score_keep_survival(
        _items_with_equations(checkpoint_a_docx, paragraphs_at_checkpoint_a),
        _items_with_equations(checkpoint_b_docx, paragraphs_at_checkpoint_b),
        kept_markers,
        excluded_paragraph_texts=excluded_texts,
    )

    phase2_pass = bool(
        citation_absent and section_at_d2
        and keep_survival.get("overall_status") == "clean_keep_survival"
    )

    return {
        "package_valid": True,
        "citation_absent": citation_absent,
        "remaining_citation_markers": remaining_citation_markers,
        "section_at_d2": section_at_d2,
        "section_position": section_position,
        "keep_survival": keep_survival,
        "phase2_pass": phase2_pass,
    }


def _check_final_structure(output_docx: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """The full-document check against Phase 3's expected end state
    (protocol sections 2.2/2.3's own "expected final structure" paragraph).
    Every check re-derives ground truth directly from the persisted `.docx`
    XML (`_paragraph_texts`, `_equation_flat_texts`, `document_outline`),
    never from either arm's own completion claim, per this project's
    standing rule.

    Required keys in `expected`:
      bibliography_marker_text, equation_marker, caption_marker_text: `B`'s/
        `E`'s/`Cap`'s own Phase-1 marker, each expected present EXACTLY ONCE.
      citation_absent_marker_texts: every citation marker text ever planted
        in this chain (1.2's and 3.2's), expected present ZERO times.
      section_id, expected_d1_heading_para_id, expected_d2_heading_para_id: the
        section's identity plus both destinations' stable para_ids (NOT
        heading text -- see `_section_heading_adjacency`'s own docstring for
        why), to confirm it ends at `D2` (3.3's own D2->D1->D2 excursion
        must net back to `D2`).
      pristine_paragraphs: the full paragraph-text list of the PRISTINE,
        never-edited original document -- "every paragraph outside these
        targets byte-identical to the pristine original" is checked against
        THIS, not checkpoint B, since checkpoint B already carries Phase 1's
        own legitimate edits.
    """
    paragraphs_after = _paragraph_texts(output_docx)

    bib_matches = _paragraphs_containing(paragraphs_after, expected["bibliography_marker_text"])
    caption_matches = _paragraphs_containing(paragraphs_after, expected["caption_marker_text"])
    equation_matches = [t for t in _equation_flat_texts(output_docx) if expected["equation_marker"] in t]
    citation_leftovers = [
        p for p in paragraphs_after
        if any(marker in p for marker in expected["citation_absent_marker_texts"])
    ]

    section_position = _section_heading_adjacency(
        output_docx, expected["section_id"],
        expected["expected_d1_heading_para_id"], expected["expected_d2_heading_para_id"],
    )
    section_at_d2 = bool(section_position["at_d2"] and not section_position["at_d1"])

    final_touched_after = [*bib_matches, *caption_matches]
    if _AUTO_CREATED_REFERENCES_HEADING_TEXT not in expected["pristine_paragraphs"]:
        final_touched_after.append(_AUTO_CREATED_REFERENCES_HEADING_TEXT)
    collateral_clean, collateral_detail = _collateral_diff_outside_touched(
        expected["pristine_paragraphs"], paragraphs_after,
        touched_before=[], touched_after=final_touched_after,
    )

    checks = {
        "bibliography_present_exactly_once": len(bib_matches) == 1,
        "equation_present_exactly_once": len(equation_matches) == 1,
        "caption_present_exactly_once": len(caption_matches) == 1,
        "citation_fully_absent": not citation_leftovers,
        "section_at_d2": section_at_d2,
        "zero_collateral_diff_vs_pristine": collateral_clean,
    }
    return {
        "final_structure_match": all(checks.values()),
        "checks": checks,
        "bibliography_matches": bib_matches,
        "equation_matches": equation_matches,
        "caption_matches": caption_matches,
        "citation_leftovers": citation_leftovers,
        "section_position": section_position,
        "collateral_detail": collateral_detail,
    }


def grade_phase3_second_exposure(
    output_docx: Path,
    paragraphs_at_checkpoint_b: list[str],
    targets: dict[str, dict[str, Any]],
    expected_final_structure: dict[str, Any],
    checkpoint_b_docx: Path | None = None,
) -> dict[str, Any]:
    """Checkpoint C (protocol section 4, "K=4-comparable primary outcome"):
    grades the end of Phase 3 (SECOND EXPOSURE -- 5 families forward+inverse
    = 10 tool-call steps, order R').

    Signature note / open question (flagged for the integration step, see
    final report): this function receives only ONE post-Phase-3 snapshot
    (`output_docx`) plus the pre-Phase-3 baseline (`paragraphs_at_checkpoint_
    b`) -- it does NOT receive an intermediate snapshot between each
    family's own insert sub-step and remove sub-step (there are 5 such
    intermediate points across the phase, one per family). Protocol section
    4 describes reusing "its own existing grading function... one family per
    row" for Phase 3, and each family's own INVERSE grader
    (`grade_inverse_trial*`) is already built for exactly this "insert-then-
    remove nets to the pre-forward state" shape (its own
    `exact_pre_forward_paragraph_list_restored`-style check), so calling
    `_grade_family_inverse` ONCE per family -- with `paragraphs_at_
    checkpoint_b` as the pre-forward baseline and `output_docx` as the
    state to check, and `targets[family]` supplying THAT family's fresh
    Phase-3-only marker (`B2`'s title, a fresh citation/equation/caption
    marker; `section_reorder` needs no marker, only exact order restored) --
    correctly verifies the NET round-trip effect this signature can observe.
    Per-sub-step package-validity gating (protocol section 4: "after EVERY
    step, not just phase ends") for the 10 individual sub-steps is the
    orchestrator's own responsibility (`tools/run_respec_cascade_family.py`,
    out of this function's scope); if per-sub-step *content* grading (not
    just the validity gate) is later found to be necessary here too, this
    signature will need intermediate snapshots threaded in -- not attempted
    here since the task brief's signature does not carry them.

    `targets` must have exactly the five keys in `FAMILY_ORDER`
    (`section_reorder`'s target dict may be empty -- `grade_inverse_trial_
    reorder` takes no family-specific marker).

    `expected_final_structure` is passed straight to `_check_final_structure`
    (see its docstring for the required keys) for the full-document check,
    and its `bibliography_marker_text`/`equation_marker`/`caption_marker_
    text` double as the `kept_markers` for one final `score_keep_survival`
    close-out call (checkpoint B -> this phase's own final state) -- the
    "final collateral-damage close-out" protocol section 4 requires.
    """
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {
            "package_valid": False,
            "status": f"chain_broken_at_step_{_PHASE3_LAST_STEP}",
            "reason": f"invalid output package: {err}",
            "phase3_pass": False,
        }

    family_results: dict[str, dict[str, Any]] = {}
    for family in FAMILY_ORDER:
        if family not in targets:
            raise ValueError(f"grade_phase3_second_exposure: targets is missing required family {family!r}")
        result = _grade_family_inverse(family, output_docx, paragraphs_at_checkpoint_b, targets[family])
        family_results[family] = result
    all_family_pass = all(_family_own_inverse_target_ok(f, r) for f, r in family_results.items())

    final_structure = _check_final_structure(output_docx, expected_final_structure)

    # score_keep_survival needs each kept element's FULL exact text, not the
    # bare marker fragment `expected_final_structure` carries for
    # `_check_final_structure`'s own SUBSTRING checks (`_paragraphs_containing`)
    # -- same bug class as grade_phase2_respec's own kept_markers construction
    # (see that fix's comment for the full story). Resolved the same way:
    # search checkpoint B's own paragraphs/equations for whichever one
    # actually carries the marker fragment, use its full text -- equation
    # needs this too (confirmed live, 2026-09-22 RunPod re-run:
    # generate_equation_forward's own payload is f"x = {marker}", never the
    # bare marker `equation_marker` carries).
    bib_fragment = expected_final_structure["bibliography_marker_text"]
    cap_fragment = expected_final_structure["caption_marker_text"]
    eq_fragment = expected_final_structure["equation_marker"]
    bib_full_text = next((p for p in paragraphs_at_checkpoint_b if bib_fragment in p), bib_fragment)
    cap_full_text = next((p for p in paragraphs_at_checkpoint_b if cap_fragment in p), cap_fragment)
    if checkpoint_b_docx is not None:
        checkpoint_b_items = _items_with_equations(checkpoint_b_docx, paragraphs_at_checkpoint_b)
        checkpoint_c_items = _items_with_equations(output_docx, _paragraph_texts(output_docx))
        eq_full_text = next(
            (t for t in _equation_flat_texts(checkpoint_b_docx) if eq_fragment in t), eq_fragment,
        )
    else:
        # Backward-compatible degraded path (no checkpoint_b_docx given):
        # `E`'s own survival is unverifiable here, same limitation this
        # whole function had before `_items_with_equations` existed -- see
        # that helper's docstring.
        checkpoint_b_items = _items_from_paragraph_texts(paragraphs_at_checkpoint_b)
        checkpoint_c_items = _items_from_paragraph_texts(_paragraph_texts(output_docx))
        eq_full_text = eq_fragment
    kept_markers = {
        "bibliography": bib_full_text,
        "equation": eq_full_text,
        "caption": cap_full_text,
    }
    keep_survival_final = score_keep_survival(
        checkpoint_b_items,
        checkpoint_c_items,
        kept_markers,
    )

    phase3_pass = bool(
        all_family_pass
        and final_structure["final_structure_match"]
        and keep_survival_final.get("overall_status") == "clean_keep_survival"
    )

    return {
        "package_valid": True,
        "families": family_results,
        "final_structure_match": final_structure["final_structure_match"],
        "final_structure_detail": final_structure,
        "keep_survival_final": keep_survival_final,
        "phase3_pass": phase3_pass,
    }


def chain_pass(phase1_result: dict[str, Any], phase2_result: dict[str, Any], phase3_result: dict[str, Any]) -> bool:
    """Composite chain PASS (protocol section 4) = Phase 1 pass AND Phase 2
    pass AND Phase 3 pass AND every intermediate package-validity gate
    passed. Each phase's own `phase{N}_pass` key already folds in that
    phase's own gate (a `package_valid: False` result always carries
    `phase{N}_pass: False`), so this composite does not need to re-check
    `package_valid` itself."""
    return bool(
        phase1_result.get("phase1_pass")
        and phase2_result.get("phase2_pass")
        and phase3_result.get("phase3_pass")
    )


def chain_failure_taxonomy(
    phase1_result: dict[str, Any], phase2_result: dict[str, Any], phase3_result: dict[str, Any],
) -> str | None:
    """The specific failure-attribution string protocol section 4 requires
    ("never collapsed into one opaque pass/fail without knowing where it
    broke") -- `chain_broken_at_step_N` for a package-validity failure,
    `respec_broken_at_2.1`/`2.3` for a Checkpoint-B-specific failure,
    `phase3_broken_at_<family>` (or `phase3_broken_at_final_structure`) for
    a Checkpoint-C-specific failure -- or `None` if the chain passed.
    Checked in chain-execution order (Phase 1 -> Phase 2 -> Phase 3): a
    Phase 1 package-validity failure makes every later phase's own result
    meaningless, since later steps never even ran against an
    already-invalid document (protocol section 4's package-validity gate)."""
    if not phase1_result.get("package_valid", True):
        return phase1_result.get("status", "chain_broken_at_step_unknown")
    if not phase1_result.get("phase1_pass"):
        # package was fine; this is a CONTENT failure, not a validity-gate
        # failure -- must not share chain_broken_at_step_N's string shape,
        # which protocol section 4 reserves for the package-validity gate
        # (and which a downstream string-prefix classifier could otherwise
        # conflate with this). Mirrors phase3_broken_at_<family>'s own
        # per-family attribution below.
        families = phase1_result.get("families", {})
        failed_families = [f for f in FAMILY_ORDER if not _family_own_target_ok(f, families.get(f, {}))]
        if failed_families:
            return f"phase1_broken_at_{failed_families[0]}"
        return "phase1_broken_at_collateral"  # every family passed; collateral_clean was False

    if not phase2_result.get("package_valid", True):
        return phase2_result.get("status", "chain_broken_at_step_unknown")
    if not phase2_result.get("citation_absent"):
        return "respec_broken_at_2.1"
    if not phase2_result.get("section_at_d2"):
        return "respec_broken_at_2.3"
    if not phase2_result.get("phase2_pass"):
        # citation absent and section at D2 both individually held, but
        # score_keep_survival still failed: a kept element (B/E/Cap) was
        # lost/changed/duplicated, or unintended-drift fired outside them.
        # Attribute to whichever of 2.1/2.3 is structurally capable of
        # having caused it, rather than blindly naming 2.1 -- 2.1 (citation
        # removal) can only ever touch the citation anchor paragraph itself,
        # so if score_keep_survival's own failure isn't about a kept
        # element's exact text, 2.3 (the section redirect, which touches an
        # entire section's worth of paragraphs) is the more likely cause.
        keep_status = phase2_result.get("keep_survival", {}).get("overall_status", "")
        if keep_status.startswith("kept_element_"):
            return "respec_broken_at_2.1"
        return "respec_broken_at_2.3"

    if not phase3_result.get("package_valid", True):
        return phase3_result.get("status", "chain_broken_at_step_unknown")
    if not phase3_result.get("phase3_pass"):
        families = phase3_result.get("families", {})
        failed_families = [f for f in FAMILY_ORDER if not _family_own_inverse_target_ok(f, families.get(f, {}))]
        if failed_families:
            return f"phase3_broken_at_{failed_families[0]}"
        return "phase3_broken_at_final_structure"

    return None


# ---------------------------------------------------------------------------
# comment_targeting (PAPER-S24, docs/paper-s24-targeted-comment-protocol-v0.md
# section 4/5 item 3). No phases here -- a chain is K sequential, distinct,
# never-repeated single-step comment placements (protocol section 2.1), so
# grading is per-STEP (grade_comment_targeting_step) plus a simple chain-wide
# composite (grade_comment_targeting_chain), not respec_cascade's three-phase
# shape above. Every check parses word/comments.xml / word/document.xml
# directly via stdlib zipfile/ElementTree, per protocol section 4's own
# standing rule: list_internal_notes is explicitly NOT used as ground truth
# anywhere in this family (it is a sidecar populated by insert_highlighted_
# note itself at insertion time -- confirmed by reading that function's
# source, which upserts index_db_path's sidecar row for mode="comment" too,
# `note_id = f"_MComment{comment_id}"` -- never an independent re-derivation),
# and neither arm's own self-report is trusted either.
# ---------------------------------------------------------------------------

_COMMENTS_PART = "word/comments.xml"
_DOCUMENT_PART = "word/document.xml"


def _read_optional_xml_part(docx_path: Path, part_name: str) -> ET.Element | None:
    """The parsed root of `part_name` inside `docx_path`, or None if the
    part is absent -- e.g. `word/comments.xml` on a document with zero
    comments (protocol section 1.3 found this true of
    masters-dissertation-defense.docx: its first inserted comment in this
    family exercises `_stage_word_comment`'s own "create the part from
    scratch" code path, never the "extend an existing part" path the other
    two documents exercise). Never raises on a MISSING part; a genuinely
    corrupt/unparseable PRESENT part is allowed to raise, since that is real
    evidence for `_package_is_valid_docx`'s own gate to have already caught
    -- this helper is only ever called after that gate passes."""
    with zipfile.ZipFile(docx_path) as zf:
        if part_name not in zf.namelist():
            return None
        return ET.fromstring(zf.read(part_name))


def _comment_texts_by_id(comments_root: ET.Element | None) -> dict[str, dict[str, str]]:
    """`{comment_id: {"author": ..., "text": ...}}` from `word/comments.xml`'s
    own `<w:comment>` elements, read directly."""
    if comments_root is None:
        return {}
    out: dict[str, dict[str, str]] = {}
    for comment in comments_root.findall(_q(_W, "comment")):
        comment_id = comment.get(_q(_W, "id"))
        if comment_id is None:
            continue
        out[comment_id] = {
            "author": comment.get(_q(_W, "author")) or "",
            "text": _local_text(comment).strip(),
        }
    return out


def _walk_all_paragraphs(document_root: ET.Element):
    body = document_root.find(_q(_W, "body"))
    if body is None:
        return
    yield from body.iter(_q(_W, "p"))


def _comment_bracketed_para_ids(document_root: ET.Element) -> dict[str, set[str]]:
    """`{comment_id: {para_id, ...}}` -- for every `commentRangeStart`/
    `commentRangeEnd` found anywhere in `word/document.xml`, the identity of
    the `<w:p>` element that structurally contains it (directly or via a
    nested descendant -- this naturally covers table-cell paragraphs too,
    since `<w:tc>`'s own `<w:p>` children are the ones actually walked here,
    never a `<w:tbl>`/`<w:tr>`/`<w:tc>` ancestor). No OOXML paragraph is ever
    nested inside another, so walking one paragraph's own subtree can never
    misattribute a range marker to the wrong paragraph.

    Identity is the paragraph's native `w14:paraId` when present -- every
    candidate target this family's resolver hands out already has one
    (protocol section 1.1: 100% native `w14:paraId` coverage on all three
    real corpus documents) -- falling back to a positional
    `f"__unindexed_para_{n}"` placeholder for the rare paragraph with none,
    so a malformed control-arm edit that brackets an off-target,
    unindexed paragraph still shows up as "an extra paragraph got touched"
    in `_comment_range_precision` rather than silently vanishing from the
    bracketed set. This fallback is exercised only by a synthetic test
    fixture or a genuine control-arm mistake, never by the real corpus."""
    bracketed: dict[str, set[str]] = {}
    start_tag = _q(_W, "commentRangeStart")
    end_tag = _q(_W, "commentRangeEnd")
    id_attr = _q(_W, "id")
    for index, p in enumerate(_walk_all_paragraphs(document_root)):
        pid = p.get(_q(_W14, "paraId")) or f"__unindexed_para_{index}"
        ids_here: set[str] = set()
        for el in p.iter():
            if el.tag in (start_tag, end_tag):
                cid = el.get(id_attr)
                if cid is not None:
                    ids_here.add(cid)
        for cid in ids_here:
            bracketed.setdefault(cid, set()).add(pid)
    return bracketed


def _extract_comment_items(docx_path: Path) -> list[dict[str, Any]]:
    """Every native Word comment currently present in `docx_path`, read
    directly from `word/comments.xml` + `word/document.xml`'s own range
    markers. Returns one item dict per `<w:comment>`,
    `{"comment_id": str, "author": str, "text": str,
    "anchor_para_ids": tuple[str, ...]}` -- the same shape
    `graph_scorer.score_comment_set_survival` and `_comment_range_precision`
    (via its own `bracketed_para_ids` set argument) expect. `anchor_para_ids`
    is `()` for a comment id whose range markers were not found bracketing
    any paragraph at all (a genuinely malformed edit)."""
    document_root = _read_optional_xml_part(docx_path, _DOCUMENT_PART)
    if document_root is None:
        return []
    comments_root = _read_optional_xml_part(docx_path, _COMMENTS_PART)
    comment_meta = _comment_texts_by_id(comments_root)
    bracketed = _comment_bracketed_para_ids(document_root)

    items: list[dict[str, Any]] = []
    for comment_id, meta in comment_meta.items():
        items.append({
            "comment_id": comment_id,
            "author": meta["author"],
            "text": meta["text"],
            "anchor_para_ids": tuple(sorted(bracketed.get(comment_id, ()))),
        })
    return items


def _safe_paragraph_texts_or_none(docx_path: Path) -> list[str] | None:
    """Mirrors `run_respec_cascade_family.py::_safe_paragraph_texts` (not
    imported -- private to that module, and this file avoids the same
    backwards/sideways private-import coupling the respec_cascade ground
    truth already warned against): a raw zipfile read against the
    immediately-prior checkpoint must never raise and abort grading just
    because an earlier step (either arm) left something unreadable behind.
    That prior checkpoint's OWN package validity was already gated when it
    was produced (every step runs through `_package_is_valid_docx`); this
    is only a defensive re-read, not a second validity gate."""
    try:
        return _paragraph_texts(docx_path)
    except (KeyError, zipfile.BadZipFile, ET.ParseError, FileNotFoundError):
        return None


def grade_comment_targeting_step(
    output_docx: Path,
    input_docx: Path,
    author_tag: str,
    target_para_id: str,
    confusable_sibling_para_ids: list[str],
    kept_comments: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """PAPER-S24 comment_targeting (protocol section 4, "Per-step check: new
    `grade_comment_targeting_step`"). Grades ONE step of a comment_targeting
    chain: `input_docx` is the checkpoint IMMEDIATELY BEFORE this step,
    `output_docx` is this step's own output -- matching every other per-step
    gate's before/after convention in this file.

    `kept_comments` is every comment this step's own survival check must
    verify byte-identical across the two checkpoints -- every comment
    inserted at steps `1..k-1` of this SAME chain plus every pre-existing
    organic comment (protocol section 1.3), keyed exactly the way
    `graph_scorer.score_comment_set_survival` expects (see its docstring):
    a stable key -> `{"author": ..., "text": ..., "anchor_para_ids": ...}`.
    The orchestrator (`tools/run_comment_targeting_family.py`) grows this
    dict by one entry after every successfully-graded step and seeds it with
    the organic comments found in the PRISTINE document before step 1.

    `_package_is_valid_docx` (reused unmodified, protocol section 5 item 3)
    gates first -- a corrupt/missing output short-circuits every other check
    with an `outcome` of `"chain_broken_at_step_k"` (the orchestrator
    supplies the actual step id when it logs this), the same failure-
    taxonomy value `respec_cascade` already introduced.

    Outcome taxonomy (protocol section 4): one of `correct_target` /
    `wrong_target_same_cluster` / `wrong_target_other` / `no_comment_created`
    / `prior_comment_corrupted` / `chain_broken_at_step_k`, chosen by
    priority in that order once the package-validity gate and the "exactly
    one new comment by this author" check both pass -- a step's own target
    precision is diagnosed first (mirroring `docx_trial_evaluator.py`'s own
    respec_cascade `chain_failure_taxonomy`, which likewise checks a step's
    OWN specific-target correctness before falling back to keep-survival
    attribution), and only a step that got its OWN new comment exactly right
    can still be downgraded to `prior_comment_corrupted` if it damaged
    something else (an earlier comment, an organic comment, or unrelated
    paragraph text) in the process. `len(own_new_comments) > 1` (a genuine
    edge case the protocol's six-value taxonomy does not separately name) is
    folded into `no_comment_created`, disclosed here rather than silently
    reusing that label without comment: both cases mean "the intended
    SINGLE new comment was not cleanly created," which is the property this
    check exists to verify.
    """
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {
            "package_valid": False, "outcome": "chain_broken_at_step_k",
            "reason": f"invalid output package: {err}", "step_pass": False,
        }

    paragraphs_before = _safe_paragraph_texts_or_none(input_docx)
    paragraphs_after = _paragraph_texts(output_docx)
    # A real comment insertion never touches run text (confirmed by reading
    # _stage_word_comment: it only splices commentRangeStart/commentRangeEnd/
    # a commentReference run into the paragraph's own child list, never
    # edits or adds a <w:t>) -- so this is a strict, cheap invariant,
    # stricter than bibliography/citation/caption require of themselves
    # since those legitimately mutate text (protocol section 4 item 4).
    zero_text_diff = paragraphs_before is not None and paragraphs_after == paragraphs_before

    comments_before = _extract_comment_items(input_docx)
    comments_after = _extract_comment_items(output_docx)
    own_new_comments = [c for c in comments_after if c["author"] == author_tag]
    exactly_one_new_comment = len(own_new_comments) == 1

    keep_survival = score_comment_set_survival(
        comments_before, comments_after, kept_comments, excluded_authors=[author_tag],
    )
    keep_survival_ok = keep_survival.get("overall_status") == "clean_comment_set_survival"
    prior_state_clean = keep_survival_ok and zero_text_diff

    range_precision: dict[str, Any] | None = None
    if not exactly_one_new_comment:
        outcome = "no_comment_created"
    else:
        range_precision = _comment_range_precision(
            set(own_new_comments[0]["anchor_para_ids"]), target_para_id, confusable_sibling_para_ids,
        )
        status = range_precision["status"]
        if status == "no_range_found":
            # A <w:comment> record exists by this author but its range never
            # actually bracketed any paragraph -- functionally equivalent to
            # never having been created, for this family's own grading
            # purposes (there is no paragraph a reader could ever see it
            # attached to).
            outcome = "no_comment_created"
        elif status in ("wrong_target_same_cluster", "wrong_target_other"):
            outcome = status
        elif not prior_state_clean:
            outcome = "prior_comment_corrupted"
        else:
            outcome = "correct_target"

    step_pass = bool(
        exactly_one_new_comment
        and range_precision is not None
        and range_precision["status"] == "exact_match"
        and prior_state_clean
    )

    return {
        "package_valid": True,
        "outcome": outcome,
        "step_pass": step_pass,
        "exactly_one_new_comment_by_author": exactly_one_new_comment,
        "new_comments_by_author_count": len(own_new_comments),
        # The ACTUAL observed (author, text, anchor_para_ids) of this step's
        # own new comment (or None when zero/multiple were found) -- NOT
        # necessarily what was intended. The orchestrator needs this,
        # regardless of whether this step landed on the correct target, to
        # grow its own running kept_comments dict for LATER steps' survival
        # checks: even a wrongly-targeted comment is now real content in the
        # document that a later step must not additionally corrupt.
        "new_comment_item": own_new_comments[0] if exactly_one_new_comment else None,
        "range_precision": range_precision,
        "keep_survival": keep_survival,
        "keep_survival_ok": keep_survival_ok,
        "zero_paragraph_text_diff": zero_text_diff,
    }


def grade_comment_targeting_chain(
    step_results: list[dict[str, Any]], condition_by_step: list[str],
) -> dict[str, Any]:
    """PAPER-S24 comment_targeting: chain-level composite (protocol section
    4, "Chain-level composite: per-chain pass = every step `correct_target`
    AND every keep-survival check passed AND every package-validity gate
    passed"). Since `grade_comment_targeting_step`'s own `step_pass` already
    folds in all three of those conditions for that one step (see its
    docstring), the chain composite reduces to "every step's own `step_pass`
    is True" -- no separate re-derivation of the three conditions here.

    `step_results` is this chain's own ordered list of
    `grade_comment_targeting_step` results (one per chain position, in
    order -- this function trusts list order, not any embedded index);
    `condition_by_step` is the matching list of `"ambiguous"` | `"unique"`
    condition labels (protocol section 2.1's alternating design), carried
    through into the returned `per_position` breakdown for the primary
    per-chain-position, per-condition readout (protocol section 4's own
    "Primary statistic: per-chain-position pass rate (1..K), by condition")
    -- it does NOT gate the chain PASS/FAIL verdict itself, which is
    unconditional on every step regardless of condition.
    """
    if len(step_results) != len(condition_by_step):
        raise ValueError(
            f"grade_comment_targeting_chain: step_results has {len(step_results)} entries "
            f"but condition_by_step has {len(condition_by_step)} -- must be the same length"
        )

    per_position: list[dict[str, Any]] = []
    for i, (step_result, condition) in enumerate(zip(step_results, condition_by_step), start=1):
        per_position.append({
            "chain_position": i,
            "condition": condition,
            "outcome": step_result.get("outcome"),
            "step_pass": bool(step_result.get("step_pass")),
        })

    first_failed_position = next((p["chain_position"] for p in per_position if not p["step_pass"]), None)
    chain_pass = first_failed_position is None

    return {
        "chain_pass": chain_pass,
        "first_failed_chain_position": first_failed_position,
        "per_position": per_position,
        "step_count": len(step_results),
    }
