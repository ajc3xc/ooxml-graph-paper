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
    ok, err = _package_is_valid_docx(output_docx)
    if not ok:
        return {"verdict": "fail", "reason": f"invalid output package: {err}"}

    paragraphs_after = _paragraph_texts(output_docx)
    matches = _paragraphs_containing(paragraphs_after, expected_marker_title)
    missing_originals = [p for p in paragraphs_before_forward if p not in paragraphs_after]

    checks = {
        "output_is_valid_docx": True,
        "marker_entry_removed": len(matches) == 0,
        "no_pre_forward_paragraph_lost": not missing_originals,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "paragraph_count_after": len(paragraphs_after),
        "paragraph_count_before_forward": len(paragraphs_before_forward),
        "remaining_matching_paragraphs": matches,
        "missing_pre_forward_paragraphs": missing_originals,
    }
