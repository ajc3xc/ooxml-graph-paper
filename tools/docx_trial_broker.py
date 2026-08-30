"""PAPER-S20: symmetric trial schema + task/inverse generator for the paired
Claude-without-vs-with-Meridian DOCX editing study.

Both arms (control, treatment) are given the SAME logical task in plain
English and differ only in which tools they're allowed to use to accomplish
it -- control gets generic file-editing tools and no Meridian MCP access at
all; treatment gets exactly one bounded Meridian Docs MCP write primitive.
Neither arm is told "use python-docx" or "use insert_highlighted_note"
explicitly by name for the forward task's own wording (the CLI-level tool
restriction is what actually enforces the arm difference, not the prompt);
the prompt states the document-level outcome, not the implementation.

This module owns:
  - TrialSpec: the symmetric per-trial descriptor both arms share.
  - generate_task_pair(): builds a (forward, inverse) TrialSpec pair for one
    frozen DOCX + one anchor choice.
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
    anchor_text: str
    insert_text: str
    prompt: str


def _paragraph_texts(docx_path: Path) -> list[str]:
    """Read-only: extract paragraph text via plain w:t concatenation (no tab/br
    handling needed for this purpose -- only used to pick a real, present
    anchor phrase from the frozen fixture, not to grade anything)."""
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

    Forward: insert one new paragraph containing a unique, opaque marker
    string immediately after a real, existing anchor paragraph.
    Inverse: remove that exact paragraph (identified by its unique marker
    text, not by position -- position could have shifted).

    The marker is opaque (a random token, not semantically meaningful) so a
    correct completion is unambiguous to grade and cannot be confused with
    any content that was already in the frozen document.
    """
    paragraphs = _paragraph_texts(input_docx)
    if not paragraphs:
        raise ValueError(f"{input_docx} has no non-empty paragraphs to anchor on")
    anchor_text = paragraphs[0]
    marker = f"PILOT-S20-MARKER-{uuid.uuid4().hex[:12]}"
    insert_text = f"Commissioning pilot inserted paragraph {marker}."

    trial_base = f"{doc_label}-{marker}"

    forward = TrialSpec(
        trial_id=f"{trial_base}-forward",
        doc_label=doc_label,
        arm="",  # filled in by the caller per-arm
        direction="forward",
        input_docx=input_docx,
        anchor_text=anchor_text,
        insert_text=insert_text,
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Find the paragraph whose text is exactly:\n\n{anchor_text!r}\n\n"
            f"Insert exactly one NEW paragraph immediately after it, containing "
            f"exactly this text and nothing else:\n\n{insert_text!r}\n\n"
            f"Do not change, remove, reorder, or reformat any other paragraph. "
            f"Save the document in place at the same path. When finished, "
            f"reply with a single line: DONE."
        ),
    )
    inverse = TrialSpec(
        trial_id=f"{trial_base}-inverse",
        doc_label=doc_label,
        arm="",
        direction="inverse",
        input_docx=input_docx,  # the FORWARD arm's own output; wired up by the runner
        anchor_text=anchor_text,
        insert_text=insert_text,
        prompt=(
            f"You are editing a Word document at the path given to you. "
            f"Find the paragraph whose text is exactly:\n\n{insert_text!r}\n\n"
            f"Remove exactly that one paragraph. "
            f"Do not change, remove, reorder, or reformat any other paragraph. "
            f"Save the document in place at the same path. When finished, "
            f"reply with a single line: DONE."
        ),
    )
    return forward, inverse


def expected_forward_state(paragraphs_before: list[str], spec: TrialSpec) -> dict:
    """Ground truth for grading a forward trial's output against its input."""
    return {
        "expected_new_paragraph": spec.insert_text,
        "expected_paragraph_count_delta": 1,
        "forbidden_paragraph_removed": paragraphs_before,
        "anchor_must_still_be_present": spec.anchor_text,
    }


def expected_inverse_state(paragraphs_before_forward: list[str], spec: TrialSpec) -> dict:
    """Ground truth for grading an inverse trial's output: it should exactly
    reconstruct the document as it was BEFORE the forward trial ran."""
    return {
        "expected_paragraph_removed": spec.insert_text,
        "expected_paragraph_count_delta": -1,
        "expected_final_paragraphs": paragraphs_before_forward,
    }
