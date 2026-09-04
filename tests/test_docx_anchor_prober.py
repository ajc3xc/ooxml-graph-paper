"""Regression tests for tools/docx_anchor_prober.py's harness-side resolvers."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from docx_anchor_prober import (  # noqa: E402
    resolve_equation_para_id_by_marker,
    resolve_section_reorder_plan,
)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


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


def _equation_paragraph_xml(marker: str, para_id: str | None = None) -> str:
    id_attr = f' w14:paraId="{para_id}" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"' if para_id else ""
    return (
        f'<w:p{id_attr}><m:oMath xmlns:m="{_M}">'
        f'<m:r><m:t>x = {marker}</m:t></m:r>'
        f'</m:oMath></w:p>'
    )


def test_resolve_equation_para_id_by_marker_finds_the_right_equation(tmp_path: Path) -> None:
    """A pure-equation paragraph's parse_docx() "text" field is empty (its
    content lives in <m:oMath>/<m:t>, a different namespace than the <w:t>
    runs that field reads -- confirmed directly, 2026-09-03), so this
    resolver deliberately does NOT build on resolve_para_id_by_marker_text;
    it uses parse_docx_equations_local's own flat_text instead."""
    body = (
        "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>"
        + _equation_paragraph_xml("1111111111", para_id="AAAAAAAA")
        + _equation_paragraph_xml("2222222222", para_id="BBBBBBBB")
    )
    path = _make_docx_raw_body(tmp_path, "two_equations.docx", body)

    result = resolve_equation_para_id_by_marker(path, "2222222222")

    assert result["found"] is True
    assert result["para_id"] == "BBBBBBBB"


def test_resolve_equation_para_id_by_marker_not_found(tmp_path: Path) -> None:
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _equation_paragraph_xml("1111111111")
    path = _make_docx_raw_body(tmp_path, "one_equation.docx", body)

    result = resolve_equation_para_id_by_marker(path, "9999999999")

    assert result["found"] is False


def test_resolve_equation_para_id_by_marker_rejects_ambiguous_match(tmp_path: Path) -> None:
    """Same discipline as resolve_para_id_by_marker_text: a marker that
    matches more than one equation is reported as not found with a reason,
    never silently resolved to the first match."""
    body = (
        _equation_paragraph_xml("55551111", para_id="AAAAAAAA")
        + _equation_paragraph_xml("55552222", para_id="BBBBBBBB")
    )
    path = _make_docx_raw_body(tmp_path, "ambiguous.docx", body)

    result = resolve_equation_para_id_by_marker(path, "5555")

    assert result["found"] is False
    assert "2 equations" in result["reason"]


def _heading(text: str, para_id: str, level: int) -> str:
    style = f"Heading{level}"
    return (
        f'<w:p w14:paraId="{para_id}" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
        f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'
    )


def _body_text(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def test_section_reorder_plan_skips_a_child_heading_for_the_destination(tmp_path: Path) -> None:
    """Found live (2026-09-03), via a hand-authored adversarial fixture, then
    confirmed present in 4 of 48 real v2 follow-up corpus documents: picking
    the destination as simply the next heading in document order (with no
    level awareness) can land on a Heading2 that is a CHILD of the section
    just chosen -- "move this section to appear after a heading that is
    part of itself" is logically incoherent. move_section correctly no-ops
    on it (destination already inside the source range), which grades as a
    spurious treatment failure, not a real capability gap. The destination
    must be a heading at the SAME level as the chosen section (a genuine
    sibling), skipping over any deeper child headings in between."""
    body = "".join([
        _heading("Introduction", "H0000001", 1),
        _body_text("Intro body."),
        _heading("Module A", "H0000002", 1),
        _heading("Overview", "H0000003", 2),  # Module A's own child
        _body_text("Module A body."),
        _heading("Module B", "H0000004", 1),  # the section that gets chosen (mid)
        _heading("Overview", "H0000005", 2),  # Module B's OWN child -- must be skipped
        _body_text("Module B body."),
        _heading("Appendix", "H0000006", 1),  # the real, coherent sibling destination
        _body_text("Appendix body."),
    ])
    path = _make_docx_raw_body(tmp_path, "nested_headings.docx", body)

    plan = resolve_section_reorder_plan(path)

    assert plan["found"] is True
    assert plan["section_id"] == "H0000004"
    assert plan["destination_heading_para_id"] == "H0000006"  # Appendix, NOT Module B's own child Overview


def test_section_reorder_plan_skips_a_blank_heading_at_the_middle_position(tmp_path: Path) -> None:
    """Found live (2026-09-04) on a real 1.7MB document in the v2 follow-up
    corpus: headings[mid] was picked purely by position, with no check that
    it actually has text. Some real-world documents have a heading-styled
    paragraph with no extractable text at all (an image-only or field-only
    "heading"). grade_forward_trial_reorder's moved_heading_still_present
    check is `section_heading_text.strip() in paragraphs_after` -- when
    that text is "", this can never pass (confirmed: _paragraph_texts never
    yields a literal empty-string entry), no matter how correctly
    move_section performed the move. The chosen section must have
    non-blank text; a blank heading[mid] is skipped in favor of the
    nearest heading (scanning outward) that has one."""
    body = "".join([
        _heading("Introduction", "H0000001", 1),
        _heading("", "H0000002", 1),  # blank -- must be skipped
        _heading("", "H0000003", 1),  # mid of 5 headings, ALSO blank -- must be skipped
        _heading("Module C", "H0000004", 1),  # nearest non-blank heading -- must be chosen instead
        _heading("Appendix", "H0000005", 1),
    ])
    path = _make_docx_raw_body(tmp_path, "blank_middle_heading.docx", body)

    plan = resolve_section_reorder_plan(path)

    assert plan["found"] is True
    assert plan["section_id"] == "H0000004"
    assert plan["section_heading_text"] == "Module C"
    assert plan["destination_heading_para_id"] == "H0000005"


def test_section_reorder_plan_not_applicable_when_every_candidate_heading_is_blank(tmp_path: Path) -> None:
    body = "".join([
        _heading("", "H0000001", 1),
        _heading("", "H0000002", 1),
        _heading("", "H0000003", 1),
        _heading("", "H0000004", 1),
        _heading("", "H0000005", 1),
    ])
    path = _make_docx_raw_body(tmp_path, "all_blank_headings.docx", body)

    plan = resolve_section_reorder_plan(path)

    assert plan["found"] is False
    assert "non-blank" in plan["reason"]


def test_section_reorder_plan_not_applicable_when_no_sibling_destination_exists(tmp_path: Path) -> None:
    """If every heading after the chosen section is a deeper child (no
    sibling-level heading to move into), this must be reported as a clean
    not_applicable, never a silently-incoherent plan."""
    body = "".join([
        _heading("Introduction", "H0000001", 1),
        _body_text("Intro body."),
        _heading("Module A", "H0000002", 1),
        _body_text("Module A body."),
        _heading("Module B", "H0000003", 1),  # chosen (mid of 4 headings)
        _heading("Overview", "H0000004", 2),  # only remaining heading is a child -- no sibling exists
        _body_text("Module B body."),
    ])
    path = _make_docx_raw_body(tmp_path, "no_sibling.docx", body)

    plan = resolve_section_reorder_plan(path)

    assert plan["found"] is False
    assert "sibling" in plan["reason"]
