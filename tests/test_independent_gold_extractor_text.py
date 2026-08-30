"""Regression test for PAPER-30/38's tab/break text-fidelity fix in
tools/independent_gold_extractor.py's _local_text.

Found via PAPER-30: gold's paragraph text previously dropped <w:tab/> and
<w:br/> entirely (only <w:t> was concatenated), causing a real, measurable
mismatch against python-docx's own .text property (which does include tabs)
on tab-heavy documents like tier2-docxbenchmark-investment-agreement-executed.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from independent_gold_extractor import _W, _local_text  # noqa: E402


def _q(tag: str) -> str:
    return f"{{{_W}}}{tag}"


def _build_paragraph(*run_specs: list[tuple[str, str]]) -> ET.Element:
    """run_specs: each run is a list of (kind, value) pairs, kind in
    ("t", "tab", "br", "cr"); value is the text for "t", ignored otherwise."""
    p = ET.Element(_q("p"))
    for spec in run_specs:
        r = ET.SubElement(p, _q("r"))
        for kind, value in spec:
            if kind == "t":
                el = ET.SubElement(r, _q("t"))
                el.text = value
            else:
                ET.SubElement(r, _q(kind))
    return p


def test_local_text_converts_tab_to_literal_tab_character():
    p = _build_paragraph([("t", "(a)"), ("tab", ""), ("t", "there is text")])
    assert _local_text(p) == "(a)\tthere is text"


def test_local_text_converts_br_and_cr_to_newline():
    p = _build_paragraph([("t", "line one"), ("br", ""), ("t", "line two"), ("cr", ""), ("t", "line three")])
    assert _local_text(p) == "line one\nline two\nline three"


def test_local_text_preserves_plain_text_with_no_tab_or_break():
    p = _build_paragraph([("t", "Hello "), ("t", "world")])
    assert _local_text(p) == "Hello world"


def test_local_text_handles_multiple_runs_with_mixed_content():
    p = _build_paragraph(
        [("t", "(a)"), ("tab", "")],
        [("t", "clause text"), ("br", ""), ("t", "continued")],
    )
    assert _local_text(p) == "(a)\tclause text\ncontinued"


def test_local_text_empty_paragraph_is_empty_string():
    p = ET.Element(_q("p"))
    assert _local_text(p) == ""
