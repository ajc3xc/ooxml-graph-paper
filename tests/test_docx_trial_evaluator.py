"""Regression tests for tools/docx_trial_evaluator.py's structural grading."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from docx_trial_evaluator import (  # noqa: E402
    grade_forward_trial_equation,
    grade_forward_trial_reorder,
    grade_forward_trial_table_structural,
    grade_inverse_trial_equation,
    grade_inverse_trial_table_structural,
)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


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


def _equation_paragraph_xml(marker: str) -> str:
    return (
        f'<w:p><m:oMath xmlns:m="{_M}">'
        f'<m:r><m:t>x = {marker}</m:t></m:r>'
        f'</m:oMath></w:p>'
    )


def _make_docx_raw_body(tmp_path: Path, name: str, body_xml: str) -> Path:
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}"><w:body>{body_xml}</w:body></w:document>'
    ).encode("utf-8")
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("_rels/.rels", "<Relationships/>")
        zf.writestr("word/document.xml", document_xml)
    return path


def _table_paragraph_xml(marker: str) -> str:
    return (
        "<w:tbl><w:tblGrid><w:gridCol w:w=\"1000\"/></w:tblGrid>"
        f"<w:tr><w:tc><w:p><w:r><w:t>{marker}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )


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


def test_equation_forward_passes_when_marker_equation_present(tmp_path: Path) -> None:
    """A pure-equation paragraph's parse_docx() text field comes back empty
    (confirmed directly, 2026-09-03): its content lives in <m:oMath>/<m:t>,
    not the <w:t> runs that field reads. grade_forward_trial_equation must
    use the equation-specific parser (parse_docx_equations_local's
    flat_text), not a plain paragraph-text search, or it could never pass."""
    before = ["Anchor paragraph."]
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _equation_paragraph_xml("1234567890")
    output = _make_docx_raw_body(tmp_path, "eq_forward.docx", body)

    result = grade_forward_trial_equation(output, before, "1234567890")

    assert result["verdict"] == "pass"
    assert result["checks"]["marker_equation_present_exactly_once"] is True


def test_equation_forward_fails_when_only_plain_text_inserted(tmp_path: Path) -> None:
    """The whole point of this family: a control-arm agent that inserts
    plain text reading "x = 1234567890" instead of a real <m:oMath> must
    fail, not pass on a text-substring technicality -- this is a genuine
    test of native OOXML math structure, not just visible text."""
    before = ["Anchor paragraph."]
    body = (
        "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>x = 1234567890</w:t></w:r></w:p>"
    )
    output = _make_docx_raw_body(tmp_path, "eq_plaintext.docx", body)

    result = grade_forward_trial_equation(output, before, "1234567890")

    assert result["verdict"] == "fail"
    assert result["checks"]["marker_equation_present_exactly_once"] is False


def test_equation_inverse_passes_when_equation_removed_and_paragraphs_restored(tmp_path: Path) -> None:
    before_forward = ["Anchor paragraph."]
    output = _make_docx(tmp_path, "eq_inverse_ok.docx", before_forward)

    result = grade_inverse_trial_equation(output, before_forward, "1234567890")

    assert result["verdict"] == "pass"
    assert result["checks"]["marker_equation_removed"] is True


def test_equation_inverse_fails_when_equation_still_present(tmp_path: Path) -> None:
    before_forward = ["Anchor paragraph."]
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _equation_paragraph_xml("1234567890")
    output = _make_docx_raw_body(tmp_path, "eq_inverse_fail.docx", body)

    result = grade_inverse_trial_equation(output, before_forward, "1234567890")

    assert result["verdict"] == "fail"
    assert result["checks"]["marker_equation_removed"] is False


def test_table_structural_forward_passes_when_marker_table_cell_present(tmp_path: Path) -> None:
    before = ["Anchor paragraph."]
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _table_paragraph_xml("PILOT-S7-TABLE-abc123")
    output = _make_docx_raw_body(tmp_path, "table_forward.docx", body)

    result = grade_forward_trial_table_structural(output, before, "PILOT-S7-TABLE-abc123")

    assert result["verdict"] == "pass"
    assert result["checks"]["marker_table_cell_present_exactly_once"] is True
    assert result["checks"]["no_original_paragraph_lost"] is True


def test_table_structural_forward_fails_when_original_paragraph_lost(tmp_path: Path) -> None:
    before = ["Anchor paragraph.", "A second original paragraph."]
    # "A second original paragraph." is missing from the output.
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _table_paragraph_xml("PILOT-S7-TABLE-abc123")
    output = _make_docx_raw_body(tmp_path, "table_forward_lost.docx", body)

    result = grade_forward_trial_table_structural(output, before, "PILOT-S7-TABLE-abc123")

    assert result["verdict"] == "fail"
    assert result["checks"]["no_original_paragraph_lost"] is False


def test_table_structural_inverse_passes_when_table_removed_and_paragraphs_restored(tmp_path: Path) -> None:
    before_forward = ["Anchor paragraph."]
    output = _make_docx(tmp_path, "table_inverse_ok.docx", before_forward)

    result = grade_inverse_trial_table_structural(output, before_forward, "PILOT-S7-TABLE-abc123")

    assert result["verdict"] == "pass"
    assert result["checks"]["marker_table_removed"] is True


def test_table_structural_inverse_fails_when_table_still_present(tmp_path: Path) -> None:
    before_forward = ["Anchor paragraph."]
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _table_paragraph_xml("PILOT-S7-TABLE-abc123")
    output = _make_docx_raw_body(tmp_path, "table_inverse_fail.docx", body)

    result = grade_inverse_trial_table_structural(output, before_forward, "PILOT-S7-TABLE-abc123")

    assert result["verdict"] == "fail"
    assert result["checks"]["marker_table_removed"] is False
