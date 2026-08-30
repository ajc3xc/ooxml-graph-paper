"""Regression tests for PAPER-S7's multi-family dispatch logic (pure functions
only -- no real Claude CLI or Meridian import needed for these)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_paper_s7_benchmark import _build_pair_specs, _grade_forward, _grade_inverse  # noqa: E402


def test_build_pair_specs_bibliography_needs_no_applicability_info(tmp_path: Path) -> None:
    forward, inverse = _build_pair_specs(
        "bibliography", "doc-a", tmp_path / "in.docx", "marker1", {"applicable": True},
    )

    assert forward.family == "bibliography"
    assert forward.treatment_tool == "insert_bibliography_entry"
    assert inverse is not None
    assert inverse.treatment_tool == "remove_bibliography_entry"
    assert forward.treatment_args["citation_key"] == inverse.treatment_args["citation_key"]


def test_build_pair_specs_citation_uses_resolved_anchor(tmp_path: Path) -> None:
    applicability = {
        "applicable": True,
        "anchor": {"anchor_para_id": "p42", "anchor_text_snippet": "Hello", "anchor_full_text": "Hello world"},
    }

    forward, inverse = _build_pair_specs("citation", "doc-a", tmp_path / "in.docx", "marker1", applicability)

    assert forward.treatment_args["anchor_para_id"] == "p42"
    assert inverse.treatment_args["anchor_para_id"] == "p42"
    assert forward.marker_text == inverse.marker_text


def test_build_pair_specs_caption_returns_none_inverse(tmp_path: Path) -> None:
    applicability = {
        "applicable": True,
        "anchor": {"anchor_para_id": "p1", "anchor_text_snippet": "Snip", "anchor_full_text": "Snip text"},
    }

    forward, inverse = _build_pair_specs("caption", "doc-a", tmp_path / "in.docx", "marker1", applicability)

    assert forward.treatment_tool == "insert_caption"
    assert inverse is None  # resolved post-forward by the runner, not upfront


def test_build_pair_specs_section_reorder_uses_plan(tmp_path: Path) -> None:
    applicability = {
        "applicable": True,
        "plan": {
            "section_id": "h2", "section_heading_text": "Section Two",
            "original_preceding_heading_para_id": "h1", "original_preceding_heading_text": "Section One",
            "destination_heading_para_id": "h3", "destination_heading_text": "Section Three",
        },
    }

    forward, inverse = _build_pair_specs("section_reorder", "doc-a", tmp_path / "in.docx", "marker1", applicability)

    assert forward.treatment_args["destination_anchor_para_id"] == "h3"
    assert inverse.treatment_args["destination_anchor_para_id"] == "h1"
    assert forward.treatment_args["section_id"] == inverse.treatment_args["section_id"] == "h2"


def test_build_pair_specs_rejects_unknown_family(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown family"):
        _build_pair_specs("nonexistent", "doc-a", tmp_path / "in.docx", "m", {})


def test_grade_dispatch_rejects_unknown_family(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown family"):
        _grade_forward("nonexistent", tmp_path / "out.docx", [], None, {})
    with pytest.raises(ValueError, match="unknown family"):
        _grade_inverse("nonexistent", tmp_path / "out.docx", [], None)
