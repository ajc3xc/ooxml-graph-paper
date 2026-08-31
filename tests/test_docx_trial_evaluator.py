"""Regression tests for tools/docx_trial_evaluator.py's structural grading."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from docx_trial_evaluator import grade_forward_trial_reorder  # noqa: E402

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx(tmp_path: Path, name: str, paragraphs: list[str]) -> Path:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>'
    ).encode("utf-8")
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("_rels/.rels", "<Relationships/>")
        zf.writestr("word/document.xml", document_xml)
    return path


def test_reorder_forward_passes_when_heading_has_no_incidental_whitespace(tmp_path: Path) -> None:
    before = ["Heading A", "Body A", "Heading B", "Body B"]
    after = ["Heading B", "Body B", "Heading A", "Body A"]
    output = _make_docx(tmp_path, "clean.docx", after)

    result = grade_forward_trial_reorder(output, before, "Heading B")

    assert result["verdict"] == "pass"
    assert result["checks"]["moved_heading_still_present"] is True


def test_reorder_forward_passes_when_plans_heading_text_has_trailing_whitespace(tmp_path: Path) -> None:
    """Found live (2026-08-31) grading real-world documents: document_outline
    returns raw, unstripped run text for a heading (real OOXML runs commonly
    carry incidental trailing whitespace), while the grader's own paragraph
    extraction strips every paragraph. A byte-perfect round trip on such a
    document was being graded 'fail' purely from this whitespace mismatch --
    not a real capability gap, but it disproportionately penalized organic
    documents (rare in the curated benchmark corpus, common in real-world
    scraped documents) on BOTH arms equally, masking the true pass rate."""
    # paragraphs_before is itself always produced by _paragraph_texts (already
    # stripped) in the real harness -- only document_outline's heading text is
    # ever unstripped, so that's the only side of this fixture that carries it.
    before = ["Heading A", "Body A", "Heading B", "Body B"]
    after = ["Heading B", "Body B", "Heading A", "Body A"]
    output = _make_docx(tmp_path, "whitespace.docx", after)

    # section_heading_text as document_outline would actually return it: unstripped.
    result = grade_forward_trial_reorder(output, before, "Heading B ")

    assert result["verdict"] == "pass"
    assert result["checks"]["moved_heading_still_present"] is True


def test_reorder_forward_fails_when_heading_genuinely_missing(tmp_path: Path) -> None:
    before = ["Heading A", "Body A", "Heading B", "Body B"]
    after = ["Body B", "Heading A", "Body A"]  # heading B genuinely dropped
    output = _make_docx(tmp_path, "missing.docx", after)

    result = grade_forward_trial_reorder(output, before, "Heading B")

    assert result["verdict"] == "fail"
    assert result["checks"]["moved_heading_still_present"] is False
