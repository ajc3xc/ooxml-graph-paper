"""PAPER-S7: harness-side (never agent-side) anchor resolution.

Every S20/S7 task family needs a body-paragraph anchor to attach an edit to. The
anchor-resolution bug that caused PAPER-S20's original 300s treatment timeout
(insert_highlighted_note's anchor_para_id had no discovery tool reachable to the
treatment arm) is avoided structurally here: this module runs ONCE, ahead of time,
in the trial-generation/runner process itself -- never handed to either arm as a
tool -- using Meridian's own stateless `parse_docx` to pick a safe anchor and a
matching human-readable text description. The treatment arm receives the resolved
id directly (like citation_key/marker_title already are for the bibliography
family); the control arm receives the text description and locates it itself with
its own generic tools, exactly mirroring the existing bibliography-family split.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HEADING_STYLE_RE = re.compile(r"heading\s*\d|title|subtitle", re.IGNORECASE)


def _import_docs_intel():
    from meridian_docs import docs_intel

    return docs_intel


def resolve_body_anchor(docx_path: Path) -> dict[str, Any]:
    """Pick a safe, non-heading, non-empty body paragraph to use as an edit
    anchor, plus a short verbatim text snippet the control arm can locate the
    same paragraph by. Prefers a paragraph roughly 70-90% of the way through
    the document body (leaves room for genuine end-of-document material like a
    References section without picking the literal last paragraph, which is
    sometimes a section break marker with no real text)."""
    docs_intel = _import_docs_intel()
    paragraphs = docs_intel.parse_docx(str(docx_path))
    candidates = [
        p for p in paragraphs
        if (p.get("text") or "").strip()
        and len((p.get("text") or "").strip()) >= 8
        and not _HEADING_STYLE_RE.search(p.get("style") or "")
    ]
    if not candidates:
        return {"found": False, "reason": "no eligible non-heading body paragraph with text found"}

    target_index = int(len(candidates) * 0.8)
    target_index = min(target_index, len(candidates) - 1)
    chosen = candidates[target_index]
    text = chosen["text"].strip()
    snippet = text[:80]

    return {
        "found": True,
        "anchor_para_id": chosen["para_id"],
        "anchor_text_snippet": snippet,
        "anchor_full_text": text,
        "candidate_pool_size": len(candidates),
        "chosen_rank": target_index,
    }


def resolve_anchor_or_raise(docx_path: Path) -> dict[str, Any]:
    result = resolve_body_anchor(docx_path)
    if not result["found"]:
        raise ValueError(f"{docx_path}: {result['reason']}")
    return result


def resolve_para_id_by_marker_text(docx_path: Path, marker_text: str) -> dict[str, Any]:
    """Post-forward resolution for any family whose forward trial creates a
    NEW paragraph identified only by a unique marker string the harness
    itself minted (caption's insert_caption never returns the new caption
    paragraph's own id -- see PAPER-S7 recon). Re-parses the OUTPUT docx with
    the same stateless parse_docx() every mutation primitive resolves ids
    against, and returns whichever paragraph's text contains the marker --
    the same id remove_caption/edit_caption would need, without having to
    replicate insert_caption's internal seq-number counting logic. Called by
    the runner between the forward and inverse trial, never by either agent;
    works identically regardless of which arm produced the paragraph."""
    docs_intel = _import_docs_intel()
    paragraphs = docs_intel.parse_docx(str(docx_path))
    matches = [p for p in paragraphs if marker_text in (p.get("text") or "")]
    if not matches:
        return {"found": False, "reason": f"no paragraph contains marker text {marker_text!r}"}
    if len(matches) > 1:
        return {
            "found": False,
            "reason": f"marker text {marker_text!r} found in {len(matches)} paragraphs, expected exactly 1",
        }
    return {"found": True, "para_id": matches[0]["para_id"]}


def resolve_equation_para_id_by_marker(docx_path: Path, marker: str) -> dict[str, Any]:
    """Post-forward resolution for the equation family, analogous to
    resolve_para_id_by_marker_text above but NOT built on it: a paragraph
    containing only an <m:oMath> has empty parse_docx() text (that field is
    <w:t>-only; OMML's own text lives in <m:t>, a different namespace
    entirely -- confirmed directly, 2026-09-03, inserting a real equation
    and finding its parse_docx() "text" field empty). Uses
    parse_docx_equations_local's own flat_text (flattened <m:t> content)
    instead, which exists specifically to cover this gap. Works for either
    arm's output identically, same as the marker-text version."""
    docs_intel = _import_docs_intel()
    equations = docs_intel.parse_docx_equations_local(str(docx_path))
    matches = [e for e in equations if marker in (e.get("flat_text") or "")]
    if not matches:
        return {"found": False, "reason": f"no equation contains marker {marker!r}"}
    if len(matches) > 1:
        return {
            "found": False,
            "reason": f"marker {marker!r} found in {len(matches)} equations, expected exactly 1",
        }
    return {"found": True, "para_id": matches[0]["para_id"]}


def resolve_section_reorder_plan(docx_path: Path) -> dict[str, Any]:
    """Pick a real heading (not the first, so it has a preceding neighbor to
    restore position against; not the last, so there is room to move it
    forward) plus the destination anchors needed for both directions of a
    move_section round trip -- entirely harness-side, mirroring
    resolve_body_anchor's role for the other families.

    Found live (2026-09-03), via a hand-authored adversarial fixture, then
    confirmed against the real corpus: the original version picked
    headings[mid-1]/headings[mid]/headings[mid+1] from a FLAT heading list
    with no awareness of heading LEVEL. On any document with nested
    headings (a Heading1 section containing its own Heading2 subheadings),
    the immediately-following heading in document order is very often a
    CHILD of the just-chosen section, not an independent sibling -- e.g.
    chosen="Application Process" (level 1), "following" picked as "Guidance
    on Completing a CV Application" (level 2, a subheading OF Application
    Process itself). The resulting plan is logically incoherent: "move this
    section to appear after a heading that is part of the section being
    moved." move_section correctly (and defensibly) treats this as a no-op
    -- the destination is already inside the source range -- while a
    control-arm agent given the same instruction in prose often produces
    SOME reordering that happens to satisfy the grader's loose checks
    (same multiset, order changed, heading still present) despite the
    underlying instruction being nonsensical. This does not measure either
    arm's real section-reordering capability; it spuriously penalizes
    treatment specifically, since move_section's no-op is graded as
    order_actually_changed=False while control's arbitrary response often
    isn't. Confirmed present in 4 of 48 documents in the v2 section_reorder
    follow-up corpus (docs/paper-s7-section-reorder-followup-result-v1.md's
    own correction section has the full audit and re-run).

    Fixed by requiring `following` to be at the SAME level as `chosen` (a
    genuine sibling section boundary), scanning forward past any deeper
    (child) headings rather than blindly taking the next one in document
    order. `preceding` is left as-is (headings[mid-1]): it is always
    RESTORED TO, never moved into, so an incoherent preceding pick cannot
    make the forward move itself incoherent the way an incoherent
    following pick does -- see the correction doc for why only the
    following side needed this."""
    docs_intel = _import_docs_intel()
    outline = docs_intel.document_outline(str(docx_path))
    headings = outline.get("headings") or []
    if len(headings) < 3:
        return {"found": False, "reason": f"only {len(headings)} heading(s); need at least 3 to pick a safely-bounded middle section"}

    paragraphs = docs_intel.parse_docx(str(docx_path))
    para_id_to_index = {p["para_id"]: p["index"] for p in paragraphs}

    mid = len(headings) // 2
    chosen = headings[mid]
    preceding = headings[mid - 1]
    chosen_level = chosen.get("level")

    following = None
    for candidate in headings[mid + 1:]:
        candidate_level = candidate.get("level")
        if chosen_level is None or candidate_level is None or candidate_level <= chosen_level:
            following = candidate
            break
    if following is None:
        return {"found": False, "reason": "no sibling-level heading available after the chosen section to move into"}

    return {
        "found": True,
        "section_id": chosen["para_id"],
        "section_heading_text": chosen.get("text"),
        "original_preceding_heading_para_id": preceding["para_id"],
        "original_preceding_heading_text": preceding.get("text"),
        "destination_heading_para_id": following["para_id"],
        "destination_heading_text": following.get("text"),
        "heading_count": len(headings),
    }
