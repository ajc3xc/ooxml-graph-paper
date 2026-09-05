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
from pathlib import Path
from typing import Any

from docx_trial_broker import _paragraph_texts  # noqa: E402


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
