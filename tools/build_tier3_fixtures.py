"""PAPER-23 tier-3 composite stress fixtures: hand-authored raw OOXML combining
multiple structural features per document (dataset-landscape-2026-08-25.md's
three-tier plan calls for ~4-6 of these; this delivers a first 3). Same
raw-XML-package technique as tools/build_tier1_fixtures.py -- not product code.

Usage: pixi run python tools/build_tier3_fixtures.py
Writes: E:\\MeridianData\\ooxml-graph-paper\\gold\\tier3\\*.docx
"""
from __future__ import annotations

import zipfile
from pathlib import Path

_OUT = Path(r"E:\MeridianData\ooxml-graph-paper\gold\tier3")
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


def composite_01_report() -> Path:
    """Table + equation + caption (resolved) + bookmark, combined into one
    small "report" -- the realistic combination the paper's product targets."""
    omath = (
        f'<m:oMath xmlns:m="{_M}"><m:f><m:num><m:r><m:t>a</m:t></m:r></m:num>'
        '<m:den><m:r><m:t>b</m:t></m:r></m:den></m:f></m:oMath>'
    )
    body = (
        '<w:p w14:paraId="30000001" w14:textId="40000001">'
        '<w:bookmarkStart w:id="1" w:name="COMPOSITE01_INTRO"/>'
        '<w:r><w:t>Composite fixture 01: a small report combining table, equation, caption, and bookmark.</w:t></w:r>'
        '<w:bookmarkEnd w:id="1"/>'
        "</w:p>"
        '<w:tbl>'
        '<w:tr><w:tc><w:p w14:paraId="30000002" w14:textId="40000002"><w:r><w:t>Metric</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p w14:paraId="30000003" w14:textId="40000003"><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr>'
        '<w:tr><w:tc><w:p w14:paraId="30000004" w14:textId="40000004"><w:r><w:t>a/b</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p w14:paraId="30000005" w14:textId="40000005"><w:r><w:t>see eq. 1</w:t></w:r></w:p></w:tc></w:tr>'
        "</w:tbl>"
        '<w:p w14:paraId="30000006" w14:textId="40000006">'
        '<w:r><w:t xml:space="preserve">Table 1: </w:t></w:r>'
        '<w:fldSimple w:instr="SEQ Table \\* ARABIC"><w:r><w:t>1</w:t></w:r></w:fldSimple>'
        '<w:r><w:t xml:space="preserve"> -- metric definitions.</w:t></w:r>'
        "</w:p>"
        f'<w:p w14:paraId="30000007" w14:textId="40000007">{omath}</w:p>'
    )
    return _write("composite-01-report", _wrap(body))


def composite_02_adversarial() -> Path:
    """Duplicate paraId + equation + caption combined -- stresses that a
    real-shaped document with genuine content can STILL trip the same
    adversarial invariant fixture-03 tests in isolation."""
    omath = f'<m:oMath xmlns:m="{_M}"><m:sSub><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:oMath>'
    body = (
        '<w:p w14:paraId="30000101" w14:textId="40000101"><w:r><w:t>Composite fixture 02: adversarial -- duplicate paraId alongside real content.</w:t></w:r></w:p>'
        f'<w:p w14:paraId="30000102" w14:textId="40000102">{omath}</w:p>'
        '<w:tbl><w:tr><w:tc><w:p w14:paraId="30000102" w14:textId="40000103"><w:r><w:t>Cell reusing paragraph 30000102s paraId (adversarial).</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '<w:p w14:paraId="30000104" w14:textId="40000104">'
        '<w:r><w:t xml:space="preserve">Table 1: </w:t></w:r>'
        '<w:fldSimple w:instr="SEQ Table \\* ARABIC"><w:r><w:t>1</w:t></w:r></w:fldSimple>'
        "</w:p>"
    )
    return _write("composite-02-adversarial", _wrap(body))


def composite_03_multi() -> Path:
    """Multiple tables, multiple equations, multiple captions -- stresses the
    Section 6 nearest-preceding-table caption resolution against more than
    one caption/table pair in the same section."""
    eq1 = (
        f'<m:oMath xmlns:m="{_M}"><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e>'
        '<m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:oMath>'
    )
    eq2 = f'<m:oMath xmlns:m="{_M}"><m:rad><m:deg/><m:e><m:r><m:t>2</m:t></m:r></m:e></m:rad></m:oMath>'
    body = (
        '<w:p w14:paraId="30000201" w14:textId="40000201"><w:r><w:t>Composite fixture 03: two tables, two equations, two captions.</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:p w14:paraId="30000202" w14:textId="40000202"><w:r><w:t>T1</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '<w:p w14:paraId="30000203" w14:textId="40000203">'
        '<w:r><w:t xml:space="preserve">Table 1: </w:t></w:r>'
        '<w:fldSimple w:instr="SEQ Table \\* ARABIC"><w:r><w:t>1</w:t></w:r></w:fldSimple>'
        "</w:p>"
        f'<w:p w14:paraId="30000204" w14:textId="40000204">{eq1}</w:p>'
        '<w:tbl><w:tr><w:tc><w:p w14:paraId="30000205" w14:textId="40000205"><w:r><w:t>T2</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '<w:p w14:paraId="30000206" w14:textId="40000206">'
        '<w:r><w:t xml:space="preserve">Table 2: </w:t></w:r>'
        '<w:fldSimple w:instr="SEQ Table \\* ARABIC"><w:r><w:t>2</w:t></w:r></w:fldSimple>'
        "</w:p>"
        f'<w:p w14:paraId="30000207" w14:textId="40000207">{eq2}</w:p>'
    )
    return _write("composite-03-multi", _wrap(body))


def main() -> int:
    built = [composite_01_report(), composite_02_adversarial(), composite_03_multi()]
    for p in built:
        print(f"built {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
