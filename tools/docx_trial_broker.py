"""PAPER-S20: symmetric trial schema + task/inverse generator for the paired
Claude-without-vs-with-Meridian DOCX editing study.

Both arms (control, treatment) are given the SAME logical task in plain
English and differ only in which tools they're allowed to use to accomplish
it -- control gets generic file-editing tools and no Meridian MCP access at
all; treatment gets exactly Meridian's bounded bibliography-entry write pair
(insert_bibliography_entry / remove_bibliography_entry). The prompt states
the document-level outcome (add/remove a reference entry, identified by its
unique title), never an implementation, so the CLI-level tool restriction is
what actually enforces the arm difference.

REVISION (commissioning run #1 root cause): the original task design
(insert a plain paragraph immediately after a named anchor paragraph, via
insert_highlighted_note) required the treatment arm to resolve "the
paragraph containing this text" into a Meridian anchor_para_id -- but the
treatment arm's tool allowlist had no read/discovery tool capable of that
(Read cannot parse a binary .docx; Grep/Glob/Bash are deliberately denied
to keep the arm boundary bounded to Meridian's own interface). Both
treatment forward trials in run #1 timed out with Claude repeatedly
attempting and failing to locate the anchor. Meridian's
insert_bibliography_entry/remove_bibliography_entry pair needs no anchor
resolution at all -- both directions are keyed purely by an opaque
citation_key the trial itself mints, so this redesign eliminates the
structural gap rather than working around it with a read-tool allowance
that would have changed what's being measured.

This module owns:
  - TrialSpec: the symmetric per-trial descriptor both arms share.
  - generate_task_pair(): builds a (forward, inverse) TrialSpec pair for one
    frozen DOCX.
  - expected/forbidden change predicates the evaluator (docx_trial_evaluator.py)
    checks the OUTPUT docx against -- defined here so the same ground truth
    is used regardless of which arm produced the file.
"""
from __future__ import annotations

import dataclasses
import uuid
import zipfile
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class TrialSpec:
    trial_id: str
    doc_label: str
    arm: str  # "control" | "treatment"
    direction: str  # "forward" | "inverse"
    input_docx: Path
    citation_key: str
    marker_title: str
    prompt: str


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


def generate_task_pair(doc_label: str, input_docx: Path) -> tuple[TrialSpec, TrialSpec]:
    """One forward + one semantic-inverse TrialSpec for a single frozen DOCX.

    Forward: add a new APA-style reference/bibliography entry (creating a
    References section at the end if one doesn't already exist) for a work
    with a unique, opaque marker title -- unambiguous to grade and never
    confusable with content already in the frozen document.
    Inverse: remove that exact entry, identified by its title (not by
    citation_key, which is Meridian-internal and never stated in the
    control arm's prompt -- the control arm has no concept of a
    citation_key at all, only the visible title text).
    """
    marker = uuid.uuid4().hex[:12]
    citation_key = f"pilot-s20-{marker}"
    marker_title = f"Commissioning Pilot Marker Publication {marker}"

    trial_base = f"{doc_label}-{marker}"

    forward = TrialSpec(
        trial_id=f"{trial_base}-forward",
        doc_label=doc_label,
        arm="",  # filled in by the caller per-arm
        direction="forward",
        input_docx=input_docx,
        citation_key=citation_key,
        marker_title=marker_title,
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Add ONE new reference/bibliography entry to the document's "
            f"reference list, formatted in APA 7th-edition style (create a "
            f"'References' section at the end of the document first if one "
            f"does not already exist). The new entry is for a journal "
            f"article with exactly these details:\n\n"
            f"  Author: Marker, Pilot\n"
            f"  Year: 2026\n"
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
        doc_label=doc_label,
        arm="",
        direction="inverse",
        input_docx=input_docx,  # the FORWARD arm's own output; wired up by the runner
        citation_key=citation_key,
        marker_title=marker_title,
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"It contains a reference/bibliography entry whose title is "
            f"exactly:\n\n{marker_title!r}\n\n"
            f"Remove that entire reference entry (its whole paragraph) from "
            f"the document. Do not change, remove, reorder, or reformat any "
            f"other paragraph. Save the document in place at the same "
            f"path. When finished, reply with a single line: DONE."
        ),
    )
    return forward, inverse


def treatment_csl_item(spec: TrialSpec) -> dict:
    """The CSL-JSON item a treatment-arm agent should pass to
    insert_bibliography_entry for this trial -- exposed here (not just left
    to the prompt) so the runner/tests can construct the identical item
    independently for a canary check."""
    return {
        "type": "article-journal",
        "title": spec.marker_title,
        "author": [{"family": "Marker", "given": "Pilot"}],
        "issued": {"date-parts": [[2026]]},
    }


def expected_forward_state(paragraphs_before: list[str], spec: TrialSpec) -> dict:
    """Ground truth for grading a forward trial's output against its input."""
    return {
        "expected_marker_title": spec.marker_title,
        "expected_paragraph_count_delta": 1,
        "forbidden_paragraphs_removed": paragraphs_before,
    }


def expected_inverse_state(paragraphs_before_forward: list[str], spec: TrialSpec) -> dict:
    """Ground truth for grading an inverse trial's output: it should exactly
    reconstruct the document as it was BEFORE the forward trial ran."""
    return {
        "expected_marker_title_removed": spec.marker_title,
        "expected_paragraph_count_delta": -1,
        "expected_final_paragraphs": paragraphs_before_forward,
    }
