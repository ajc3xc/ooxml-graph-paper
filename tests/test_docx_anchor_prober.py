"""Regression tests for tools/docx_anchor_prober.py's harness-side resolvers."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from docx_anchor_prober import resolve_equation_para_id_by_marker  # noqa: E402

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
