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
from collections import Counter
from pathlib import Path
from typing import Any

from docx_trial_broker import _paragraph_texts  # noqa: E402
from graph_scorer import score_keep_survival  # noqa: E402


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
    return clean, {
        "unexplained_missing": sorted(before_remainder.elements()),
        "unexplained_added": sorted(after_remainder.elements()),
    }


def _section_heading_adjacency(
    docx_path: Path, section_id: str, d1_heading_para_id: str, d2_heading_para_id: str,
) -> dict[str, Any]:
    """Reads the live heading outline (`docs_intel.document_outline`, via
    this module's own `_import_docs_intel`) and checks whether the section
    identified by `section_id` is the heading immediately following D1's,
    resp. D2's, own heading -- the structural signature `move_section`'s
    real, verified `destination_position: "after"` semantics produce (see
    `tools/docx_trial_broker.py`'s respec_cascade `generate_section_
    redirect_trial`/`generate_second_exposure_reorder_pair` docstrings,
    which confirm this directly against the live tool, 2026-09-20). Position
    -- not text presence alone -- is what distinguishes "still at D1" from
    "moved on to D2": both D1's and D2's own heading text remain in the
    document the whole time (a destination heading is never removed), so a
    presence-only check (`grade_forward_trial_reorder`'s own
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

    return {
        "section_found": section_index is not None,
        "d1_found": d1_index is not None,
        "d2_found": d2_index is not None,
        "at_d1": section_index is not None and d1_index is not None and section_index == d1_index + 1,
        "at_d2": section_index is not None and d2_index is not None and section_index == d2_index + 1,
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


def grade_phase1_build(
    output_docx: Path, paragraphs_before: list[str], targets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Checkpoint A (protocol section 4): grades the end of Phase 1 (BUILD,
    5 steps, forward-only, order R') in one pass -- each family's own
    EXISTING forward grader, called with that family's own args from
    `targets`, plus one new generalized check: zero paragraph-text diff
    anywhere outside the five targets' own touched paragraphs, against
    `paragraphs_before` (the pristine, pre-Phase-1 paragraph list).

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
        elif family == "citation":
            touched_before.append(target["anchor_text_before"])
            touched_after.extend(result.get("anchor_matches_after", []))
        # section_reorder, equation: no `_paragraph_texts` CONTENT touched
        # (order-only, resp. no <w:t> text at all) -- see helper docstring.

    collateral_clean, collateral_detail = _collateral_diff_outside_touched(
        paragraphs_before, paragraphs_after, touched_before, touched_after,
    )

    all_family_pass = all(r.get("verdict") == "pass" for r in family_results.values())
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
    Table). `checkpoint_a_docx` is accepted for symmetry with the other two
    grade_phase* functions and to make the checkpoint pairing explicit in
    every call site, even though only `paragraphs_at_checkpoint_a` (not a
    fresh re-read of the file) is actually used below.

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
        _items_from_paragraph_texts(paragraphs_at_checkpoint_a),
        _items_from_paragraph_texts(paragraphs_at_checkpoint_b),
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

    collateral_clean, collateral_detail = _collateral_diff_outside_touched(
        expected["pristine_paragraphs"], paragraphs_after,
        touched_before=[], touched_after=[*bib_matches, *caption_matches],
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
    all_family_pass = all(r.get("verdict") == "pass" for r in family_results.values())

    final_structure = _check_final_structure(output_docx, expected_final_structure)

    kept_markers = {
        "bibliography": expected_final_structure["bibliography_marker_text"],
        "equation": expected_final_structure["equation_marker"],
        "caption": expected_final_structure["caption_marker_text"],
    }
    keep_survival_final = score_keep_survival(
        _items_from_paragraph_texts(paragraphs_at_checkpoint_b),
        _items_from_paragraph_texts(_paragraph_texts(output_docx)),
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
        failed_families = [f for f in FAMILY_ORDER if families.get(f, {}).get("verdict") != "pass"]
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
        failed_families = [f for f in FAMILY_ORDER if families.get(f, {}).get("verdict") != "pass"]
        if failed_families:
            return f"phase3_broken_at_{failed_families[0]}"
        return "phase3_broken_at_final_structure"

    return None
