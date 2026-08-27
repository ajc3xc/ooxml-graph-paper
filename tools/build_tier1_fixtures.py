"""PAPER-22 tier-1 gold fixtures: hand-authored raw OOXML, never produced by
meridian_docs/docs_intel.py, each targeting one named graph-gold-schema-v0.md
invariant. Mirrors the raw-XML-package technique already used for other test
fixtures in this sprint (e.g. test_paper14_converter_bakeoff_demo.py) rather
than any part of the product under test.

Usage: pixi run python tools/build_tier1_fixtures.py
Writes: E:\\MeridianData\\ooxml-graph-paper\\gold\\tier1\\*.docx
"""
from __future__ import annotations

import zipfile
from pathlib import Path

_OUT = Path(r"E:\MeridianData\ooxml-graph-paper\gold\tier1")
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
_PACKAGE_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)


def _wrap(body: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{_W}" xmlns:w14="{_W14}" xmlns:m="{_M}">'
        f"<w:body>{body}</w:body></w:document>"
    )


def _write(name: str, document_xml: str) -> Path:
    _OUT.mkdir(parents=True, exist_ok=True)
    out_path = _OUT / f"{name}.docx"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _PACKAGE_RELS)
        zf.writestr("word/document.xml", document_xml)
    return out_path


def fixture_baseline() -> Path:
    """Invariant target: clean paragraph + table, unique w14:paraId, deterministic order."""
    body = (
        '<w:p w14:paraId="10000001" w14:textId="20000001"><w:r><w:t>Gold fixture 01: baseline paragraph and table.</w:t></w:r></w:p>'
        '<w:p w14:paraId="10000002" w14:textId="20000002"><w:r><w:t>A second, distinct paragraph.</w:t></w:r></w:p>'
        '<w:tbl>'
        '<w:tr><w:tc><w:p w14:paraId="10000003" w14:textId="20000003"><w:r><w:t>A1</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p w14:paraId="10000004" w14:textId="20000004"><w:r><w:t>B1</w:t></w:r></w:p></w:tc></w:tr>'
        '<w:tr><w:tc><w:p w14:paraId="10000005" w14:textId="20000005"><w:r><w:t>A2</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p w14:paraId="10000006" w14:textId="20000006"><w:r><w:t>B2</w:t></w:r></w:p></w:tc></w:tr>'
        "</w:tbl>"
    )
    return _write("fixture-01-baseline", _wrap(body))


def fixture_equation() -> Path:
    """Invariant target: a real, non-empty <m:oMath> equation node (fraction)."""
    omath = (
        f'<m:oMath xmlns:m="{_M}"><m:f>'
        '<m:fPr><m:type m:val="bar"/></m:fPr>'
        '<m:num><m:r><m:t>1</m:t></m:r></m:num>'
        '<m:den><m:r><m:t>2</m:t></m:r></m:den>'
        "</m:f></m:oMath>"
    )
    body = (
        '<w:p w14:paraId="10000101" w14:textId="20000101"><w:r><w:t>Gold fixture 02: equation node.</w:t></w:r></w:p>'
        f'<w:p w14:paraId="10000102" w14:textId="20000102">{omath}</w:p>'
    )
    return _write("fixture-02-equation", _wrap(body))


def fixture_duplicate_paraid() -> Path:
    """Invariant target: schema invariant 4 -- a document that MUST be flagged
    ambiguous for duplicate w14:paraId, never silently accepted as unique."""
    body = (
        '<w:p w14:paraId="10000201" w14:textId="20000201"><w:r><w:t>Gold fixture 03: first paragraph with paraId 10000201.</w:t></w:r></w:p>'
        '<w:p w14:paraId="10000201" w14:textId="20000202"><w:r><w:t>Second, DIFFERENT paragraph reusing the same paraId 10000201 (adversarial).</w:t></w:r></w:p>'
    )
    return _write("fixture-03-duplicate-paraid", _wrap(body))


def fixture_caption() -> Path:
    """Invariant target: caption node detection via a SEQ field, paired with the table it captions."""
    body = (
        '<w:tbl>'
        '<w:tr><w:tc><w:p w14:paraId="10000301" w14:textId="20000301"><w:r><w:t>X</w:t></w:r></w:p></w:tc></w:tr>'
        "</w:tbl>"
        '<w:p w14:paraId="10000302" w14:textId="20000302">'
        '<w:r><w:t xml:space="preserve">Table 1: </w:t></w:r>'
        '<w:fldSimple w:instr="SEQ Table \\* ARABIC"><w:r><w:t>1</w:t></w:r></w:fldSimple>'
        '<w:r><w:t xml:space="preserve"> -- Gold fixture 04 caption.</w:t></w:r>'
        "</w:p>"
    )
    return _write("fixture-04-caption", _wrap(body))


def fixture_equation_radical() -> Path:
    """Invariant target: a second, structurally-different correct equation
    (radical, not fraction) -- more than one example of the 'correct' semantic
    label class, not just one."""
    omath = (
        f'<m:oMath xmlns:m="{_M}"><m:rad>'
        '<m:radPr><m:degHide m:val="1"/></m:radPr>'
        '<m:deg/>'
        '<m:e><m:r><m:t>x</m:t></m:r></m:e>'
        "</m:rad></m:oMath>"
    )
    body = (
        '<w:p w14:paraId="10000501" w14:textId="20000501"><w:r><w:t>Gold fixture 06: radical equation (correct).</w:t></w:r></w:p>'
        f'<w:p w14:paraId="10000502" w14:textId="20000502">{omath}</w:p>'
    )
    return _write("fixture-06-equation-radical", _wrap(body))


def fixture_equation_empty_required_child() -> Path:
    """Invariant target: empty_required_child label -- an <m:num> present but
    with no visible text or nested structure, mirroring the real converter's
    documented \\frac{}{} defect (omml-builder-audit-v0.md Section 6)."""
    omath = (
        f'<m:oMath xmlns:m="{_M}"><m:f>'
        "<m:num/>"
        '<m:den><m:r><m:t>2</m:t></m:r></m:den>'
        "</m:f></m:oMath>"
    )
    body = (
        '<w:p w14:paraId="10000601" w14:textId="20000601"><w:r><w:t>Gold fixture 07: empty numerator (empty_required_child).</w:t></w:r></w:p>'
        f'<w:p w14:paraId="10000602" w14:textId="20000602">{omath}</w:p>'
    )
    return _write("fixture-07-equation-empty-child", _wrap(body))


def fixture_equation_fallback_forbidden() -> Path:
    """Invariant target: fallback_forbidden label -- flattened text describing
    an equation instead of real OMML structure, mirroring the real converter's
    documented flattened-fallback defect."""
    omath = f'<m:oMath xmlns:m="{_M}"><m:r><m:t>fraction one over two</m:t></m:r></m:oMath>'
    body = (
        '<w:p w14:paraId="10000701" w14:textId="20000701"><w:r><w:t>Gold fixture 08: flattened fallback text (fallback_forbidden).</w:t></w:r></w:p>'
        f'<w:p w14:paraId="10000702" w14:textId="20000702">{omath}</w:p>'
    )
    return _write("fixture-08-equation-fallback", _wrap(body))


def fixture_bookmark() -> Path:
    """Invariant target: anchor node from a named bookmark, distinct from paraId identity."""
    body = (
        '<w:p w14:paraId="10000401" w14:textId="20000401">'
        '<w:bookmarkStart w:id="1" w:name="GOLD_FIXTURE_05_ANCHOR"/>'
        '<w:r><w:t>Gold fixture 05: bookmarked paragraph.</w:t></w:r>'
        '<w:bookmarkEnd w:id="1"/>'
        "</w:p>"
    )
    return _write("fixture-05-bookmark", _wrap(body))


def main() -> int:
    built = [
        fixture_baseline(),
        fixture_equation(),
        fixture_duplicate_paraid(),
        fixture_caption(),
        fixture_bookmark(),
        fixture_equation_radical(),
        fixture_equation_empty_required_child(),
        fixture_equation_fallback_forbidden(),
    ]
    for p in built:
        print(f"built {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
