"""PAPER-S20: grades a trial's OUTPUT docx against the broker's expected/
forbidden ground truth, entirely outside the agent (the agent never sees
this module or its verdicts). Structural, not semantic -- deliberately
narrow scope for a first commissioning pilot.
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


def grade_forward_trial(
    output_docx: Path, paragraphs_before: list[str], expected_new_paragraph: str, anchor_text: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)

    has_new = expected_new_paragraph in paragraphs_after
    anchor_present = anchor_text in paragraphs_after
    delta = len(paragraphs_after) - len(paragraphs_before)
    missing_originals = [p for p in paragraphs_before if p not in paragraphs_after]
    # Position check: the new paragraph should sit immediately after the anchor.
    correct_position = False
    if has_new and anchor_present:
        try:
            anchor_idx = paragraphs_after.index(anchor_text)
            correct_position = (
                anchor_idx + 1 < len(paragraphs_after)
                and paragraphs_after[anchor_idx + 1] == expected_new_paragraph
            )
        except ValueError:
            correct_position = False

    checks = {
        "output_is_valid_docx": True,
        "new_paragraph_present": has_new,
        "new_paragraph_correctly_positioned": correct_position,
        "anchor_paragraph_preserved": anchor_present,
        "no_original_paragraphs_removed": not missing_originals,
        "paragraph_count_delta_is_exactly_one": delta == 1,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_before": len(paragraphs_before),
        "paragraph_count_after": len(paragraphs_after),
        "missing_original_paragraphs": missing_originals,
    }


def grade_inverse_trial(
    output_docx: Path, expected_final_paragraphs: list[str], expected_removed_paragraph: str,
) -> dict[str, Any]:
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    removed = expected_removed_paragraph not in paragraphs_after
    reconstructs_original = paragraphs_after == expected_final_paragraphs

    checks = {
        "output_is_valid_docx": True,
        "inserted_paragraph_removed": removed,
        "exact_reconstruction_of_pre_forward_state": reconstructs_original,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_after": len(paragraphs_after),
        "expected_paragraph_count": len(expected_final_paragraphs),
    }
