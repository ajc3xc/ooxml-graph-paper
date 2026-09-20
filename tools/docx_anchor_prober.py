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

# Percentile fractions resolve_multiple_body_anchors walks, in priority order.
# The first 9 are the original, already-used-in-published-results set (every
# historical caller passed max_anchors<=9, most <=4) -- left untouched, same
# order, so no existing call site's output changes. The remaining 9 are pure
# additions (never returned to a caller requesting max_anchors<=9) needed by
# PAPER-S23's resolve_respec_schedule, which must resolve THREE disjoint
# per-family anchor pools (citation/equation/caption) from one document in one
# pass -- 3 families x up to 4 anchor-sets = up to 12 distinct positions,
# which the original 9-fraction list could never supply regardless of how
# large the candidate pool was (a resolver capacity ceiling, not a
# per-document content limit).
_BODY_ANCHOR_FRACTIONS = [
    0.8, 0.2, 0.4, 0.6, 0.5, 0.1, 0.3, 0.7, 0.9,
    0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95,
]


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


def resolve_multiple_body_anchors(
    docx_path: Path, max_anchors: int = 4, exclude_para_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Generalizes resolve_body_anchor to return up to max_anchors distinct
    anchors from the same eligible-candidate pool that function already
    computes, instead of discarding every candidate but one. Reuses the
    identical eligibility filter (non-heading, non-empty, >=8 chars) so
    anything resolve_body_anchor would refuse, this refuses too.

    Anchors are spread across evenly-spaced percentile positions in the
    candidate list (e.g. 20/40/60/80% for max_anchors=4) rather than
    clustered, on the same reasoning resolve_body_anchor's own 80% choice
    documents: different regions of a real document differ in local
    structure (references/appendix material near the end, body prose in
    the middle), so spreading anchors samples that variation instead of
    re-testing the same neighborhood four times. resolve_body_anchor's own
    80%-position anchor is always included (index 0 of the returned list)
    so a multi-anchor caller's first anchor is identical to what the
    existing single-anchor corpus run already used for this document --
    callers adding EXTRA anchors on top of an already-run single-anchor
    corpus should skip index 0 and use only anchors[1:], not re-run it.

    exclude_para_ids (PAPER-S23 respec_cascade addition): para_ids to treat
    as already claimed by a SIBLING family's anchor pool within the same
    document, so multiple resolve_multiple_body_anchors calls against one
    document can be composed into disjoint per-family anchor sets (see
    resolve_respec_schedule, which needs three non-overlapping pools --
    citation/equation/caption -- from one document, since all three land an
    edit in the same chain and must not target the same paragraph). Walks
    the FULL _BODY_ANCHOR_FRACTIONS list (not just the first max_anchors of
    it) so a heavily-excluded call still has enough fallback positions to
    fill max_anchors results -- for any existing call with no exclusions
    this is behavior-identical to the old truncated-slice walk, since the
    loop already stops as soon as max_anchors results are found.

    Deduplicates by para_id (two percentile targets can land on the same
    candidate in a short document, or on an excluded one); returns fewer
    than max_anchors if the candidate pool (minus exclusions) is too small
    to support that many distinct positions."""
    docs_intel = _import_docs_intel()
    paragraphs = docs_intel.parse_docx(str(docx_path))
    candidates = [
        p for p in paragraphs
        if (p.get("text") or "").strip()
        and len((p.get("text") or "").strip()) >= 8
        and not _HEADING_STYLE_RE.search(p.get("style") or "")
    ]
    if not candidates:
        return []

    fractions = _BODY_ANCHOR_FRACTIONS
    seen_para_ids: set[str] = set(exclude_para_ids or ())
    results: list[dict[str, Any]] = []
    for frac in fractions:
        if len(results) >= max_anchors:
            break
        idx = min(int(len(candidates) * frac), len(candidates) - 1)
        chosen = candidates[idx]
        if chosen["para_id"] in seen_para_ids:
            continue
        seen_para_ids.add(chosen["para_id"])
        text = chosen["text"].strip()
        results.append({
            "found": True,
            "anchor_para_id": chosen["para_id"],
            "anchor_text_snippet": text[:80],
            "anchor_full_text": text,
            "candidate_pool_size": len(candidates),
            "chosen_rank": idx,
        })
    return results


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


def resolve_table_index_by_marker(docx_path: Path, marker: str) -> dict[str, Any]:
    """Post-forward resolution for the table_structural family, analogous to
    resolve_equation_para_id_by_marker: insert_table's own new table has no
    id the harness can predict ahead of time (its body-child position
    depends on how many body children preceded the anchor, which the
    control arm's own prose interpretation can shift too), so this
    re-parses the OUTPUT document fresh and finds which table (by its
    0-based body-child ``table_index``, the same addressing
    insert_table/remove_table/relocate_table use) has the marker text in
    one of its cells. Works for either arm's output identically.

    Direct raw-XML parse (mirrors ``docx_trial_broker._paragraph_texts``'s
    own style) rather than going through a meridian_docs table-listing
    helper, since all that's needed is "does any cell paragraph in this
    table contain the marker," not a full structural table model."""
    import xml.etree.ElementTree as ET
    import zipfile

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(docx_path) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    body = root.find(f"{{{W}}}body")
    if body is None:
        return {"found": False, "reason": "document has no <w:body> element"}

    matches: list[int] = []
    for idx, child in enumerate(body):
        if child.tag != f"{{{W}}}tbl":
            continue
        cell_text = "".join(t.text or "" for t in child.iter(f"{{{W}}}t"))
        if marker in cell_text:
            matches.append(idx)

    if not matches:
        return {"found": False, "reason": f"no table contains marker {marker!r}"}
    if len(matches) > 1:
        return {
            "found": False,
            "reason": f"marker {marker!r} found in {len(matches)} tables, expected exactly 1",
        }
    return {"found": True, "table_index": matches[0]}


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
    following side needed this.

    A third, distinct defect found live (2026-09-04) on a real 1.7MB
    real-world document in the v2 follow-up corpus: `headings[mid]` was
    picked purely by position, with no check that it actually HAS text.
    Some real-world documents have a heading-styled paragraph with no
    extractable text at all (e.g. an image-only or field-only "heading").
    grade_forward_trial_reorder's `moved_heading_still_present` check is
    `section_heading_text.strip() in paragraphs_after` -- when that text is
    `""`, this check can never pass, since `_paragraph_texts` never yields a
    literal empty-string entry (confirmed directly against this document:
    262 paragraphs, zero empty), no matter how correctly move_section
    performed the move. Fixed by requiring the chosen section's own heading
    to have non-blank text, scanning outward from `mid` (checking `mid`
    itself, then progressively further indices on both sides) for the
    nearest heading that has one, rather than blindly trusting position."""
    docs_intel = _import_docs_intel()
    outline = docs_intel.document_outline(str(docx_path))
    headings = outline.get("headings") or []
    if len(headings) < 3:
        return {"found": False, "reason": f"only {len(headings)} heading(s); need at least 3 to pick a safely-bounded middle section"}

    paragraphs = docs_intel.parse_docx(str(docx_path))
    para_id_to_index = {p["para_id"]: p["index"] for p in paragraphs}

    mid = len(headings) // 2
    mid_index = None
    for offset in range(len(headings)):
        candidates = {mid - offset, mid + offset}
        for candidate_index in sorted(candidates):
            if candidate_index <= 0 or candidate_index >= len(headings) - 1:
                continue
            if (headings[candidate_index].get("text") or "").strip():
                mid_index = candidate_index
                break
        if mid_index is not None:
            break
    if mid_index is None:
        return {"found": False, "reason": "no heading with non-blank text is available in a safely-bounded middle position"}

    chosen = headings[mid_index]
    preceding = headings[mid_index - 1]
    chosen_level = chosen.get("level")

    following = None
    for candidate in headings[mid_index + 1:]:
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


def _try_section_plan_at(headings: list[dict[str, Any]], start_index: int, exclude_para_ids: set[str]) -> dict[str, Any] | None:
    """Shared candidate-validation core for resolve_multiple_section_reorder_plans,
    applying the exact same two safety rules resolve_section_reorder_plan's own
    docstring documents finding live and fixing: the chosen heading must have
    non-blank text (scanned outward from start_index exactly like the single-plan
    version), and `following` must be a same-level sibling of `chosen`, found by
    scanning forward past any deeper child headings -- never a flat next-in-order
    pick. Also refuses any chosen/preceding/following heading whose para_id is in
    exclude_para_ids, so multiple plans from the same document don't overlap.
    Returns None (not found) rather than raising, exactly like the functions it
    mirrors -- callers try the next candidate start_index on None."""
    n = len(headings)
    mid_index = None
    for offset in range(n):
        for candidate_index in sorted({start_index - offset, start_index + offset}):
            if candidate_index <= 0 or candidate_index >= n - 1:
                continue
            if not (headings[candidate_index].get("text") or "").strip():
                continue
            if headings[candidate_index]["para_id"] in exclude_para_ids:
                continue
            mid_index = candidate_index
            break
        if mid_index is not None:
            break
    if mid_index is None:
        return None

    chosen = headings[mid_index]
    preceding = headings[mid_index - 1]
    if preceding["para_id"] in exclude_para_ids:
        return None
    chosen_level = chosen.get("level")

    following = None
    for candidate in headings[mid_index + 1:]:
        if candidate["para_id"] in exclude_para_ids:
            continue
        candidate_level = candidate.get("level")
        if chosen_level is None or candidate_level is None or candidate_level <= chosen_level:
            following = candidate
            break
    if following is None:
        return None

    return {
        "found": True,
        "section_id": chosen["para_id"],
        "section_heading_text": chosen.get("text"),
        "original_preceding_heading_para_id": preceding["para_id"],
        "original_preceding_heading_text": preceding.get("text"),
        "destination_heading_para_id": following["para_id"],
        "destination_heading_text": following.get("text"),
        "heading_count": n,
    }


def resolve_multiple_section_reorder_plans(docx_path: Path, max_plans: int = 4) -> list[dict[str, Any]]:
    """Generalizes resolve_section_reorder_plan to return up to max_plans
    distinct, non-overlapping move-section plans from the same document
    instead of the single middle-ish one. Applies the identical two safety
    rules that function's own docstring documents finding and fixing live
    (non-blank chosen-heading text; `following` must be a same-level
    sibling of `chosen`, not just the next heading in document order) via
    _try_section_plan_at, so nothing this generalizes over is weakened.

    Tries several starting positions spread across the heading list (not
    clustered at the center) so returned plans sample different regions of
    the document, and excludes any heading already used by an
    already-returned plan so plans don't overlap (a heading cannot be
    "chosen" in one plan and "following"/"preceding" in another). The
    single-plan resolve_section_reorder_plan's own choice (built from
    len(headings)//2) is always the first candidate tried, so a caller
    adding EXTRA plans on top of an already-run single-plan corpus should
    skip index 0 (plans[1:]) rather than re-run it. Returns fewer than
    max_plans if the document's heading structure can't support that many
    non-overlapping, validly-bounded sections."""
    docs_intel = _import_docs_intel()
    outline = docs_intel.document_outline(str(docx_path))
    headings = outline.get("headings") or []
    if len(headings) < 3:
        return []

    n = len(headings)
    mid = n // 2
    start_fractions = [0.5, 0.2, 0.8, 0.35, 0.65, 0.15, 0.85][: max(max_plans, 4) + 3]
    start_indices = [mid] + [
        min(max(int(n * f), 1), n - 2) for f in start_fractions
    ]

    exclude: set[str] = set()
    results: list[dict[str, Any]] = []
    for start_index in start_indices:
        if len(results) >= max_plans:
            break
        plan = _try_section_plan_at(headings, start_index, exclude)
        if plan is None:
            continue
        results.append(plan)
        exclude.add(plan["section_id"])
        exclude.add(plan["original_preceding_heading_para_id"])
        exclude.add(plan["destination_heading_para_id"])
    return results


def resolve_section_redirect_plan(
    docx_path: Path,
    section_id: str,
    original_preceding_heading_para_id: str,
    destination_heading_para_id: str,
) -> dict[str, Any]:
    """PAPER-S23 respec_cascade only: resolve a SECOND, distinct destination
    `D2` for a section whose forward move (`O` -> `D1`) was already resolved
    by resolve_section_reorder_plan/resolve_multiple_section_reorder_plans,
    for the mid-chain "redirect, don't undo" respec step (protocol section
    2.1/2.3: move the section from `D1` to `D2`, never back to `O`).

    `chosen` (the section itself, identified by section_id) and `preceding`
    (identified by original_preceding_heading_para_id) are taken as FIXED
    inputs here, never re-derived from a fresh _try_section_plan_at scan,
    because D2 must be relative to the SAME section D1 was resolved for --
    re-choosing "the middle-ish heading" independently could land on a
    different section entirely, silently decoupling the redirect from the
    section the chain actually moved. This is also why this function does
    NOT simply call _try_section_plan_at(headings, ..., exclude_para_ids=
    {section_id, ...}): excluding section_id from consideration would make
    it ineligible to be re-selected as `chosen` (wrong -- it must stay
    `chosen`), and separately, passing original_preceding_heading_para_id as
    excluded while still expecting it to validate as `preceding` would
    always fail, since _try_section_plan_at's own preceding-validation
    checks `preceding["para_id"] in exclude_para_ids` and returns None when
    true. Both anchors are simply reused verbatim instead.

    Only the `following`/redirect side is freshly resolved -- scanning
    forward from the section's own position in the outline for the nearest
    same-level sibling heading that is not `section_id`,
    original_preceding_heading_para_id, or destination_heading_para_id (D1
    itself, so the "redirect" is genuinely a second destination, not an
    accidental re-pick of the first one). This mirrors the same
    same-level-sibling safety rule resolve_section_reorder_plan and
    _try_section_plan_at already establish for the `following` side, since a
    child (deeper-level) heading immediately after `chosen` is not a valid
    move destination (see resolve_section_reorder_plan's docstring for the
    full incoherent-destination story this rule was fixed for).

    Returns {"found": False, "reason": "no_redirect_target"} (the exact
    status string the protocol's anchor-set usability reporting expects,
    never a silently fabricated destination) when section_id can't be found
    in the current outline, or no eligible same-level sibling heading exists
    after it once section_id/original_preceding_heading_para_id/
    destination_heading_para_id are excluded."""
    docs_intel = _import_docs_intel()
    outline = docs_intel.document_outline(str(docx_path))
    headings = outline.get("headings") or []
    section_index = next((i for i, h in enumerate(headings) if h["para_id"] == section_id), None)
    if section_index is None:
        return {"found": False, "reason": "no_redirect_target"}

    chosen = headings[section_index]
    chosen_level = chosen.get("level")
    exclude = {section_id, original_preceding_heading_para_id, destination_heading_para_id}

    redirect = None
    for candidate in headings[section_index + 1:]:
        if candidate["para_id"] in exclude:
            continue
        candidate_level = candidate.get("level")
        if chosen_level is None or candidate_level is None or candidate_level <= chosen_level:
            redirect = candidate
            break
    if redirect is None:
        return {"found": False, "reason": "no_redirect_target"}

    return {
        "found": True,
        "section_id": section_id,
        "section_heading_text": chosen.get("text"),
        "redirect_destination_heading_para_id": redirect["para_id"],
        "redirect_destination_heading_text": redirect.get("text"),
    }


def resolve_respec_schedule(docx_path: Path, max_anchor_sets: int = 4) -> list[dict[str, Any]]:
    """PAPER-S23 respec_cascade only: resolve up to max_anchor_sets full
    respec_cascade anchor-sets for one document in a single pass, bundling
    everything one chain at anchor-set index i needs -- the i-th citation,
    equation, and caption body anchor, the i-th section-reorder plan
    (O -> D1), and that same plan's own D2 redirect (D1 -> D2) -- so a
    caller doesn't have to re-derive the index-i correspondence across five
    separate resolver calls itself. Bibliography needs no per-anchor-set
    entry: protocol section 2.1 is explicit that it is document-global (same
    end-of-reference-list insertion point for every anchor-set), exactly as
    the existing bibliography family already treats it in
    docx_trial_broker.generate_bibliography_pair.

    Each of citation/equation/caption is resolved with its own call to
    resolve_multiple_body_anchors(docx_path, max_anchors=max_anchor_sets,
    exclude_para_ids=...), chained so each later family excludes every
    para_id already claimed by an earlier one in this same schedule --
    NOT three identical calls. resolve_multiple_body_anchors is a pure
    function of (docx_path, max_anchors) with no concept of "family": three
    unexcluded calls with the same arguments return the SAME list three
    times, which would point citation/equation/caption at the identical
    paragraph within one anchor-set. That is wrong here specifically
    because, unlike tools/run_multi_anchor_extension.py::plan_extra_trials
    (which resolves ONE family at a time, in separate script invocations,
    each into its own independent extension run -- collisions across
    families are never possible there since no single document run ever
    edits two families' anchors together), a respec_cascade chain inserts
    citation, equation, AND caption into the SAME live document within one
    continuous chain, so two families landing on the same paragraph would
    corrupt each other's edit and break the later family's text-based
    (control-arm) anchor resolution the moment the earlier family's edit
    changes that paragraph's text.

    An anchor-set index i is only usable if ALL of the following resolved:
    citation/equation/caption each returned a result at index i (any of the
    three resolve_multiple_body_anchors calls may return fewer than
    max_anchor_sets results if the document's candidate pool is too small --
    the smallest of the three lengths, and the section-reorder plan count,
    bounds how many indices are even attempted), the section-reorder plan at
    index i exists, and that plan's own D2 redirect resolved (found=True).
    Every attempted index up to that smallest available count is recorded
    in the return value with an explicit reason when unusable -- never
    silently dropped -- per this project's standing N-disclosure rule
    (see docs/paper-s23-respec-cascade-protocol-v0.md section 6)."""
    citation_anchors = resolve_multiple_body_anchors(docx_path, max_anchors=max_anchor_sets)
    claimed = {a["anchor_para_id"] for a in citation_anchors if a.get("found")}
    equation_anchors = resolve_multiple_body_anchors(
        docx_path, max_anchors=max_anchor_sets, exclude_para_ids=claimed,
    )
    claimed = claimed | {a["anchor_para_id"] for a in equation_anchors if a.get("found")}
    caption_anchors = resolve_multiple_body_anchors(
        docx_path, max_anchors=max_anchor_sets, exclude_para_ids=claimed,
    )
    section_plans = resolve_multiple_section_reorder_plans(docx_path, max_plans=max_anchor_sets)

    attempt_count = min(
        len(citation_anchors),
        len(equation_anchors),
        len(caption_anchors),
        len(section_plans),
    )

    schedule: list[dict[str, Any]] = []
    for i in range(attempt_count):
        citation_anchor = citation_anchors[i]
        equation_anchor = equation_anchors[i]
        caption_anchor = caption_anchors[i]
        plan = section_plans[i]

        if not citation_anchor.get("found"):
            schedule.append({
                "anchor_set_index": i,
                "usable": False,
                "reason": "missing_citation_anchor",
                "citation_anchor": citation_anchor,
                "equation_anchor": equation_anchor,
                "caption_anchor": caption_anchor,
                "section_reorder_plan": plan,
            })
            continue
        if not equation_anchor.get("found"):
            schedule.append({
                "anchor_set_index": i,
                "usable": False,
                "reason": "missing_equation_anchor",
                "citation_anchor": citation_anchor,
                "equation_anchor": equation_anchor,
                "caption_anchor": caption_anchor,
                "section_reorder_plan": plan,
            })
            continue
        if not caption_anchor.get("found"):
            schedule.append({
                "anchor_set_index": i,
                "usable": False,
                "reason": "missing_caption_anchor",
                "citation_anchor": citation_anchor,
                "equation_anchor": equation_anchor,
                "caption_anchor": caption_anchor,
                "section_reorder_plan": plan,
            })
            continue
        if not plan or not plan.get("found"):
            schedule.append({
                "anchor_set_index": i,
                "usable": False,
                "reason": "missing_section_reorder_plan",
                "citation_anchor": citation_anchor,
                "equation_anchor": equation_anchor,
                "caption_anchor": caption_anchor,
                "section_reorder_plan": plan,
            })
            continue

        redirect = resolve_section_redirect_plan(
            docx_path,
            plan["section_id"],
            plan["original_preceding_heading_para_id"],
            plan["destination_heading_para_id"],
        )
        plan_with_redirect = dict(plan)
        plan_with_redirect["redirect"] = redirect

        if not redirect.get("found"):
            schedule.append({
                "anchor_set_index": i,
                "usable": False,
                "reason": redirect.get("reason", "no_redirect_target"),
                "citation_anchor": citation_anchor,
                "equation_anchor": equation_anchor,
                "caption_anchor": caption_anchor,
                "section_reorder_plan": plan_with_redirect,
            })
            continue

        schedule.append({
            "anchor_set_index": i,
            "usable": True,
            "reason": None,
            "citation_anchor": citation_anchor,
            "equation_anchor": equation_anchor,
            "caption_anchor": caption_anchor,
            "section_reorder_plan": plan_with_redirect,
        })

    return schedule
