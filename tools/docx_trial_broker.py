"""PAPER-S7/S20: symmetric trial schema + task/inverse generator for the paired
Claude-without-vs-with-Meridian DOCX editing study.

Both arms (control, treatment) are given the SAME logical task in plain English
and differ only in which tools they're allowed to use -- control gets generic
file-editing tools and no Meridian MCP access at all; treatment gets exactly one
Meridian bounded write-primitive pair per family. The prompt states the
document-level outcome, never an implementation, so the CLI-level tool
restriction is what actually enforces the arm difference.

FAMILIES (per PAPER-S7 recon, 2026-08-30 -- see docs/paper-s15-skill-matrix-v1.md
for the full verdict table):
  - bibliography: insert_bibliography_entry / remove_bibliography_entry.
    Keyed purely by citation_key; no anchor at all. The original S20 family.
  - citation: insert_citation / remove_citation. Keyed by the SAME
    anchor_para_id for both directions (resolved once, harness-side, by
    docx_anchor_prober.resolve_body_anchor -- never by either agent).
  - caption: insert_caption / remove_caption. insert never returns the new
    caption paragraph's own id, so the RUNNER resolves it between the forward
    and inverse trial via docx_anchor_prober.resolve_caption_para_id (a
    structured locate_anchor query, not a text search) and injects it into the
    inverse trial the same way citation_key is injected for bibliography.
  - section_reorder: move_section, called twice (there and back). Self-
    inverting because it moves (never copies) the live elements -- every
    paragraph/bookmark keeps its id. Requires >=3 headings
    (docx_anchor_prober.resolve_section_reorder_plan); not every document
    qualifies, and that is recorded as not_applicable, not forced or hidden.
  - equation: insert_equation / remove_equation. insert_equation DOES return
    the new paragraph's own id directly (unlike caption), but that id is only
    reachable by the treatment arm through the tool's own result -- the
    control arm's output has no such metadata, so post-forward resolution is
    still needed for both arms uniformly, via
    docx_anchor_prober.resolve_equation_para_id_by_marker. That resolver is
    NOT the marker-text one citation/caption use: a pure-equation paragraph's
    content lives in <m:oMath>/<m:t>, not the <w:t> runs parse_docx() reads,
    so its plain "text" field comes back empty -- confirmed directly,
    2026-09-03, by inserting a real equation and checking. The prompt asks
    for a REAL native OOXML equation (not plain text that merely looks like
    math) deliberately: this is the one family whose grading can only pass
    if genuine <m:oMath> structure exists, making it a direct test of the
    same native-format-under-generic-tools question this whole project asks
    elsewhere, not just "can the text appear in the right place." Shares
    insert_caption's Word-COM render-verification gate (_enforce_render_
    verification, ~60s per call) and its sensitivity to shared-host resource
    contention -- run at low concurrency, same mitigation as the K=4 depth
    study's own resource-contention findings.

Deliberately NOT implemented this pass: cross_reference (insert_cross_reference
requires an EXISTING caption to target, and zero of the 38 corpus documents
have one -- creating one via insert_caption first would inherit exactly the
render-gate fragility that already excluded caption below; needs caption's
render-timeout handling fixed first, not merely a removal primitive -- that
part, remove_cross_reference, already exists) and table/tracked-change
families (no clean whole-table or accept/reject primitive exists at all --
see the recon findings folded into docs/paper-s15-skill-matrix-v1.md).
"""
from __future__ import annotations

import dataclasses
import uuid
import zipfile
from pathlib import Path
from typing import Any


@dataclasses.dataclass(frozen=True)
class TrialSpec:
    trial_id: str
    doc_label: str
    arm: str  # "control" | "treatment"
    direction: str  # "forward" | "inverse"
    family: str  # "bibliography" | "citation" | "caption" | "section_reorder" | "equation"
    input_docx: Path
    prompt: str
    marker_text: str
    treatment_tool: str
    treatment_args: dict[str, Any]
    pair_index: int = 0


def _paragraph_texts(docx_path: Path) -> list[str]:
    """Read-only: extract paragraph text via plain w:t concatenation (no tab/br
    handling needed for this purpose -- only used for pre/post structural
    comparison, not to grade exact fidelity)."""
    import xml.etree.ElementTree as ET

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(docx_path) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    texts = []
    for p in root.iter(f"{{{W}}}p"):
        text = "".join(t.text or "" for t in p.iter(f"{{{W}}}t"))
        if text.strip():
            texts.append(text.strip())
    return texts


def new_marker(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# bibliography (unchanged from S20)
# ---------------------------------------------------------------------------

def generate_bibliography_pair(doc_label: str, input_docx: Path, marker: str) -> tuple[TrialSpec, TrialSpec]:
    citation_key = f"pilot-s7-{marker}"
    marker_title = f"Commissioning Pilot Marker Publication {marker}"
    trial_base = f"{doc_label}-bibliography-{marker}"

    forward = TrialSpec(
        trial_id=f"{trial_base}-forward",
        doc_label=doc_label, arm="", direction="forward", family="bibliography",
        input_docx=input_docx,
        marker_text=marker_title,
        treatment_tool="insert_bibliography_entry",
        treatment_args={
            "citation_key": citation_key,
            "csl_item": {
                "type": "article-journal", "title": marker_title,
                "author": [{"family": "Marker", "given": "Pilot"}],
                "issued": {"date-parts": [[2026]]},
            },
        },
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Add ONE new reference/bibliography entry to the document's "
            f"reference list, formatted in APA 7th-edition style (create a "
            f"'References' section at the end of the document first if one "
            f"does not already exist). The new entry is for a journal "
            f"article with exactly these details:\n\n"
            f"  Author: Marker, Pilot\n  Year: 2026\n"
            f"  Title: {marker_title!r}\n\n"
            f"The new entry must appear as its own paragraph, and its "
            f"title text must appear verbatim somewhere in that paragraph. "
            f"Do not change, remove, reorder, or reformat any other "
            f"paragraph in the document. Save the document in place at the "
            f"same path. When finished, reply with a single line: DONE."
        ),
    )
    inverse = TrialSpec(
        trial_id=f"{trial_base}-inverse",
        doc_label=doc_label, arm="", direction="inverse", family="bibliography",
        input_docx=input_docx,
        marker_text=marker_title,
        treatment_tool="remove_bibliography_entry",
        # PAPER-S7 correction: the forward call locate-or-CREATES a
        # References heading the first time it runs on a document without
        # one; remove_bibliography_entry never removed it, so a genuine
        # insert+remove cycle could never return a virgin document to its
        # exact original state -- both arms failed the strict round-trip
        # bar 100% of the time for this reason alone (see
        # docs/paper-s22-harness-verification-v1.md's correction section).
        # remove_heading_if_empty=True (parent repo commit d65cea2f) closes
        # this for the treatment arm; the prompt below asks the SAME
        # complete round trip of the control arm using generic tools, so
        # both arms are held to the identical, now-achievable bar.
        treatment_args={"citation_key": citation_key, "remove_heading_if_empty": True},
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"It contains a reference/bibliography entry whose title is "
            f"exactly:\n\n{marker_title!r}\n\n"
            f"Remove that entire reference entry (its whole paragraph) from "
            f"the document. If that was the ONLY entry under the "
            f"References/Bibliography heading, also remove that now-empty "
            f"heading paragraph, so the document is restored to EXACTLY "
            f"its state before the entry was ever added. Do not change, "
            f"remove, reorder, or reformat any other paragraph. Save the "
            f"document in place at the same path. When finished, reply "
            f"with a single line: DONE."
        ),
    )
    return forward, inverse


# ---------------------------------------------------------------------------
# citation (inline text appended to an existing anchor paragraph)
#
# PAPER-S7 correction: anchor_para_id for this family was originally resolved
# ONCE from the PRISTINE document and reused for both forward and inverse.
# Meridian's synthetic para_id (`sp<hash>`) is content-derived -- forward's
# own edit (appending the citation marker) changes that same paragraph's
# text, which changes its own synthetic id. A real treatment-arm trial
# (validation slice, docops_v2_l3_009) hit exactly this: the agent correctly
# self-detected the stale id via locate_anchor, found the right one, but
# stopped short of acting rather than risk mutating the wrong paragraph --
# a reasonable, cautious response to a genuinely broken instruction, not an
# agent failure. Control never had this problem: its instructions are
# always a fresh text search, never a cached id. Generalizing caption's
# already-correct pattern (resolve the id AFTER forward, from forward's own
# output) closes this for citation too.
# ---------------------------------------------------------------------------

def generate_citation_forward(
    doc_label: str, input_docx: Path, marker: str, anchor_para_id: str, anchor_text_snippet: str,
) -> TrialSpec:
    marker_text = f"[PILOT-S7-CITATION-{marker}]"
    citation_key = f"pilot-s7-cite-{marker}"
    trial_base = f"{doc_label}-citation-{marker}"

    return TrialSpec(
        trial_id=f"{trial_base}-forward",
        doc_label=doc_label, arm="", direction="forward", family="citation",
        input_docx=input_docx,
        marker_text=marker_text,
        treatment_tool="insert_citation",
        treatment_args={
            "anchor_para_id": anchor_para_id,
            "citation_keys": [citation_key],
            "formatted_text": marker_text,
        },
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Find the paragraph that starts with the exact text: "
            f"{anchor_text_snippet!r}\n\n"
            f"Append this exact bracketed text to the END of that "
            f"paragraph, as a citation marker, with a single leading space: "
            f"{marker_text!r}\n\n"
            f"Do not change, remove, reorder, or reformat any other part of "
            f"that paragraph, and do not touch any other paragraph. Save "
            f"the document in place at the same path. When finished, reply "
            f"with a single line: DONE."
        ),
    )


def generate_citation_inverse(
    doc_label: str, input_docx: Path, marker: str, marker_text: str, anchor_para_id: str,
) -> TrialSpec:
    """``anchor_para_id`` here MUST be re-resolved from the forward trial's
    own OUTPUT document (e.g. via docx_anchor_prober.resolve_para_id_by_marker_text),
    never reused from the pristine pre-forward document -- see this module's
    docstring above for why.

    ``match_display_text=marker_text`` is passed explicitly (2026-09-05):
    found live via a hand-authored fixture that a paragraph can hold more
    than one CSL_CITATION field (e.g. a pre-existing citation the forward
    trial's own insert landed alongside), in which case remove_citation now
    refuses to guess which one to remove unless told. The harness already
    knows exactly which marker text identifies ITS OWN inserted field --
    passing it costs nothing when the paragraph has only one field (the
    parameter is ignored in that case) and is required whenever it has
    more than one."""
    trial_base = f"{doc_label}-citation-{marker}"

    return TrialSpec(
        trial_id=f"{trial_base}-inverse",
        doc_label=doc_label, arm="", direction="inverse", family="citation",
        input_docx=input_docx,
        marker_text=marker_text,
        treatment_tool="remove_citation",
        treatment_args={"anchor_para_id": anchor_para_id, "match_display_text": marker_text},
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Find the paragraph that contains this exact bracketed text: "
            f"{marker_text!r}\n\n"
            f"Remove exactly that bracketed text (and the single leading "
            f"space immediately before it) from the paragraph, restoring "
            f"the paragraph's original text exactly. Do not change any "
            f"other part of that paragraph or any other paragraph. Save "
            f"the document in place at the same path. When finished, reply "
            f"with a single line: DONE."
        ),
    )


# ---------------------------------------------------------------------------
# caption (new paragraph; inverse args resolved post-forward by the runner)
# ---------------------------------------------------------------------------

def generate_caption_forward(
    doc_label: str, input_docx: Path, marker: str, anchor_para_id: str, anchor_text_snippet: str,
) -> TrialSpec:
    label_text = f"Pilot S7 Caption Marker {marker}"
    trial_base = f"{doc_label}-caption-{marker}"
    return TrialSpec(
        trial_id=f"{trial_base}-forward",
        doc_label=doc_label, arm="", direction="forward", family="caption",
        input_docx=input_docx,
        marker_text=label_text,
        treatment_tool="insert_caption",
        treatment_args={
            "anchor_para_id": anchor_para_id, "kind": "Figure",
            "label_text": label_text, "position": "after",
        },
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Find the paragraph that starts with the exact text: "
            f"{anchor_text_snippet!r}\n\n"
            f"Insert a new caption paragraph immediately AFTER that "
            f"paragraph, in the style Word uses for figure captions "
            f"(e.g. 'Figure 1: ...'), with this exact label text somewhere "
            f"in it: {label_text!r}\n\n"
            f"Do not change, remove, reorder, or reformat any other "
            f"paragraph. Save the document in place at the same path. When "
            f"finished, reply with a single line: DONE."
        ),
    )


def generate_caption_inverse(
    doc_label: str, input_docx: Path, marker: str, label_text: str, caption_para_id: str,
) -> TrialSpec:
    trial_base = f"{doc_label}-caption-{marker}"
    return TrialSpec(
        trial_id=f"{trial_base}-inverse",
        doc_label=doc_label, arm="", direction="inverse", family="caption",
        input_docx=input_docx,
        marker_text=label_text,
        treatment_tool="remove_caption",
        treatment_args={"caption_para_id": caption_para_id},
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"It contains a figure caption paragraph with this exact label "
            f"text: {label_text!r}\n\n"
            f"Remove that entire caption paragraph from the document. Do "
            f"not change, remove, reorder, or reformat any other "
            f"paragraph. Save the document in place at the same path. When "
            f"finished, reply with a single line: DONE."
        ),
    )


def generate_table_structural_forward(
    doc_label: str, input_docx: Path, marker_prefix: str, anchor_para_id: str, anchor_text_snippet: str,
) -> TrialSpec:
    marker = new_marker("PILOT-S7-TABLE")
    trial_base = f"{doc_label}-table_structural-{marker_prefix}"
    return TrialSpec(
        trial_id=f"{trial_base}-forward",
        doc_label=doc_label, arm="", direction="forward", family="table_structural",
        input_docx=input_docx,
        marker_text=marker,
        treatment_tool="insert_table",
        treatment_args={
            "anchor_para_id": anchor_para_id, "rows": 1, "cols": 1,
            "position": "after", "cell_texts": [[marker]],
        },
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Find the paragraph that starts with the exact text: "
            f"{anchor_text_snippet!r}\n\n"
            f"Insert a new, real Word table (a genuine table object with "
            f"rows and columns, not plain text formatted to look like one) "
            f"immediately AFTER that paragraph. The table should have "
            f"exactly 1 row and 1 column, and that single cell must "
            f"contain exactly this text: {marker}\n\n"
            f"Do not change, remove, reorder, or reformat any other "
            f"paragraph. Save the document in place at the same path. When "
            f"finished, reply with a single line: DONE."
        ),
    )


def generate_table_structural_inverse(
    doc_label: str, input_docx: Path, marker_prefix: str, marker: str, table_index: int,
) -> TrialSpec:
    """``table_index`` here MUST be re-resolved from the forward trial's own
    OUTPUT document via docx_anchor_prober.resolve_table_index_by_marker
    (never reused from a pristine document -- there is nothing to reuse,
    the table did not exist before forward ran), same post-forward pattern
    as caption/citation/equation."""
    trial_base = f"{doc_label}-table_structural-{marker_prefix}"
    return TrialSpec(
        trial_id=f"{trial_base}-inverse",
        doc_label=doc_label, arm="", direction="inverse", family="table_structural",
        input_docx=input_docx,
        marker_text=marker,
        treatment_tool="remove_table",
        treatment_args={"table_index": table_index},
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"It contains a real Word table whose single cell has exactly "
            f"this text: {marker}\n\n"
            f"Remove that entire table from the document. Do not change, "
            f"remove, reorder, or reformat any other paragraph. Save the "
            f"document in place at the same path. When finished, reply "
            f"with a single line: DONE."
        ),
    )


# ---------------------------------------------------------------------------
# section_reorder (move_section is its own inverse)
# ---------------------------------------------------------------------------

def generate_section_reorder_pair(
    doc_label: str, input_docx: Path, marker: str, section_id: str, section_heading_text: str,
    original_preceding_heading_para_id: str, original_preceding_heading_text: str,
    destination_heading_para_id: str, destination_heading_text: str,
) -> tuple[TrialSpec, TrialSpec]:
    trial_base = f"{doc_label}-section_reorder-{marker}"

    forward = TrialSpec(
        trial_id=f"{trial_base}-forward",
        doc_label=doc_label, arm="", direction="forward", family="section_reorder",
        input_docx=input_docx,
        marker_text=section_heading_text,
        treatment_tool="move_section",
        treatment_args={
            "section_id": section_id,
            "destination_anchor_para_id": destination_heading_para_id,
            "destination_position": "after",
        },
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"It has a section heading with the exact text: "
            f"{section_heading_text!r}\n\n"
            f"Move that ENTIRE section (its heading and all of its body "
            f"content, up to but not including the next heading) so it "
            f"appears immediately AFTER the section whose heading is the "
            f"exact text: {destination_heading_text!r}\n\n"
            f"Do not change the text of any paragraph, and do not change "
            f"the relative order of any OTHER section. Save the document "
            f"in place at the same path. When finished, reply with a "
            f"single line: DONE."
        ),
    )
    inverse = TrialSpec(
        trial_id=f"{trial_base}-inverse",
        doc_label=doc_label, arm="", direction="inverse", family="section_reorder",
        input_docx=input_docx,
        marker_text=section_heading_text,
        treatment_tool="move_section",
        treatment_args={
            "section_id": section_id,
            "destination_anchor_para_id": original_preceding_heading_para_id,
            "destination_position": "after",
        },
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"It has a section heading with the exact text: "
            f"{section_heading_text!r}\n\n"
            f"That section was just moved. Move it back so it appears "
            f"immediately AFTER the section whose heading is the exact "
            f"text: {original_preceding_heading_text!r}\n\n"
            f"This restores the document's section order to exactly what "
            f"it was before the earlier move. Do not change the text of "
            f"any paragraph. Save the document in place at the same path. "
            f"When finished, reply with a single line: DONE."
        ),
    )
    return forward, inverse


# ---------------------------------------------------------------------------
# equation (new display-mode paragraph; inverse args resolved post-forward by
# the runner via docx_anchor_prober.resolve_equation_para_id_by_marker, NOT
# resolve_para_id_by_marker_text -- see this module's docstring above)
# ---------------------------------------------------------------------------

def _new_numeric_marker() -> str:
    """A purely-digit marker, not new_marker()'s hex output: it goes straight
    into a LaTeX expression converted to OMML, and stays easy to eyeball as
    deliberately planted (no real equation in these documents is going to
    coincidentally contain a random 10-digit number)."""
    return str(uuid.uuid4().int)[:10]


def generate_equation_forward(
    doc_label: str, input_docx: Path, marker_prefix: str, anchor_para_id: str, anchor_text_snippet: str,
) -> TrialSpec:
    marker = _new_numeric_marker()
    trial_base = f"{doc_label}-equation-{marker_prefix}"
    return TrialSpec(
        trial_id=f"{trial_base}-forward",
        doc_label=doc_label, arm="", direction="forward", family="equation",
        input_docx=input_docx,
        marker_text=marker,
        treatment_tool="insert_equation",
        treatment_args={
            "anchor_para_id": anchor_para_id, "payload": f"x = {marker}", "position": "after",
        },
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Find the paragraph that starts with the exact text: "
            f"{anchor_text_snippet!r}\n\n"
            f"Insert a new paragraph immediately AFTER that paragraph "
            f"containing a REAL native Word equation -- an OOXML math "
            f"object (<m:oMath>), not plain text that merely looks like an "
            f"equation -- with exactly this content: x = {marker}\n\n"
            f"Do not change, remove, reorder, or reformat any other "
            f"paragraph. Save the document in place at the same path. When "
            f"finished, reply with a single line: DONE."
        ),
    )


def generate_equation_inverse(
    doc_label: str, input_docx: Path, marker_prefix: str, marker: str, equation_para_id: str,
) -> TrialSpec:
    """``equation_para_id`` here MUST be re-resolved from the forward trial's
    own OUTPUT document via docx_anchor_prober.resolve_equation_para_id_by_marker
    (never reused from a pristine document -- there is nothing to reuse,
    the equation did not exist before forward ran), same post-forward
    pattern as caption and citation."""
    trial_base = f"{doc_label}-equation-{marker_prefix}"
    return TrialSpec(
        trial_id=f"{trial_base}-inverse",
        doc_label=doc_label, arm="", direction="inverse", family="equation",
        input_docx=input_docx,
        marker_text=marker,
        treatment_tool="remove_equation",
        treatment_args={"equation_para_id": equation_para_id},
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"It contains a paragraph with a real native Word equation "
            f"(an OOXML math object, <m:oMath>) with exactly this content: "
            f"x = {marker}\n\n"
            f"Remove that entire equation paragraph from the document. Do "
            f"not change, remove, reorder, or reformat any other "
            f"paragraph. Save the document in place at the same path. When "
            f"finished, reply with a single line: DONE."
        ),
    )
