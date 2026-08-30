"""Focused tests for tools/extract_docx_convention_profile.py (PAPER-S19).

Builds a minimal, wholly synthetic DOCX package in-memory (stdlib zipfile
only) rather than reading any gold-corpus or development-corpus fixture, so
these tests exercise the extractor's parsing logic without depending on --
or risking any appearance of tuning against -- either the primary 127-document
benchmark holdout or the PAPER-S19 development corpus.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import extract_docx_convention_profile as profiler  # noqa: E402

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:bookmarkStart w:id="0" w:name="MyAnchor"/>
      <w:r><w:t>Hello</w:t></w:r>
      <w:bookmarkEnd w:id="0"/>
    </w:p>
    <w:p><w:r><w:instrText>SEQ Figure \\* ARABIC</w:instrText></w:r></w:p>
    <w:tbl>
      <w:tblPr><w:tblStyle w:val="TableGrid"/></w:tblPr>
      <w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid>
      <w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:bottom="1440" w:left="1440" w:right="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""

_STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
  </w:docDefaults>
  <w:latentStyles w:count="1" w:defLockedState="0"/>
  <w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/></w:style>
</w:styles>"""

_CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Synthetic Test Document</dc:title>
  <dc:creator>PAPER-S19 test</dc:creator>
  <dc:language>en-US</dc:language>
</cp:coreProperties>"""


def _build_synthetic_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", _DOCUMENT_XML)
        z.writestr("word/styles.xml", _STYLES_XML)
        z.writestr("docProps/core.xml", _CORE_XML)


@pytest.fixture()
def synthetic_docx(tmp_path: Path) -> Path:
    p = tmp_path / "synthetic.docx"
    _build_synthetic_docx(p)
    return p


def test_determinism_same_hash_across_two_runs(synthetic_docx: Path) -> None:
    p1 = profiler.extract_document_profile(synthetic_docx)
    p2 = profiler.extract_document_profile(synthetic_docx)
    assert p1["profile_hash"] == p2["profile_hash"]
    assert p1["profile_hash"] != ""


def test_all_twelve_categories_present_in_evidence(synthetic_docx: Path) -> None:
    prof = profiler.extract_document_profile(synthetic_docx)
    cats = {e["category"] for e in prof["evidence"]}
    expected = set(profiler._CATEGORY_FUNCS.keys())
    assert cats == expected, f"missing categories: {expected - cats}"


def test_single_document_abstains_without_template_registry(synthetic_docx: Path) -> None:
    prof = profiler.extract_document_profile(synthetic_docx)
    assert prof["resolution"]["level"] == "abstain"


def test_no_numbering_part_records_unknown_not_guessed(synthetic_docx: Path) -> None:
    prof = profiler.extract_document_profile(synthetic_docx)
    numbering_ev = [e for e in prof["evidence"] if e["category"] == "numbering"]
    uses = next(e for e in numbering_ev if e["node"] == "uses_numbering")
    assert uses["observed_value"] is False
    assert uses["authority"] == "inferred"


def test_bookmark_and_caption_and_table_signals_observed(synthetic_docx: Path) -> None:
    prof = profiler.extract_document_profile(synthetic_docx)
    by_node = {(e["category"], e["node"]): e for e in prof["evidence"]}
    assert by_node[("anchors", "user_named_bookmark_count")]["observed_value"] == 1
    seq = by_node[("captions", "SEQ_field_label_usage")]["observed_value"]
    assert seq.get("Figure") == 1
    assert by_node[("tables", "tbl_count")]["observed_value"] == 1
    assert by_node[("tables", "tbl_with_tblGrid_count")]["observed_value"] == 1


def test_sections_page_geometry_resolved_single_value(synthetic_docx: Path) -> None:
    prof = profiler.extract_document_profile(synthetic_docx)
    by_node = {e["node"]: e for e in prof["evidence"] if e["category"] == "sections"}
    pgsz = by_node["pgSz_w_h_twips"]
    assert pgsz["status"] == "resolved"
    assert pgsz["observed_value"] == ["12240", "15840"]
    assert by_node["pgSz_inferred_paper_label"]["observed_value"] == "Letter"
    assert by_node["pgSz_inferred_paper_label"]["authority"] == "inferred"


def test_mixed_page_geometry_across_sections_flagged_not_hidden(tmp_path: Path) -> None:
    doc_xml = _DOCUMENT_XML.replace(
        "</w:body>",
        "<w:p><w:pPr><w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:bottom="1440" w:left="1440" w:right="1440" w:header="720" w:footer="720" w:gutter="0"/>'
        "</w:sectPr></w:pPr></w:p></w:body>",
    )
    p = tmp_path / "mixed.docx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", doc_xml)
        z.writestr("word/styles.xml", _STYLES_XML)
        z.writestr("docProps/core.xml", _CORE_XML)
    prof = profiler.extract_document_profile(p)
    by_node = {e["node"]: e for e in prof["evidence"] if e["category"] == "sections"}
    assert by_node["sectPr_count"]["observed_value"] == 2
    pgsz = by_node["pgSz_w_h_twips"]
    assert pgsz["status"] == "mixed"
    assert len(pgsz["conflicts"]) == 1


def test_aggregate_domain_profile_abstains_below_threshold() -> None:
    fake_profiles = [
        {"doc_id": "a", "source_sha256": "x", "evidence": [
            {"category": "fonts_language", "node": "n", "part": "p", "observed_value": "Calibri",
             "confidence": 1.0, "authority": "observed", "status": "resolved", "conflicts": []}]},
        {"doc_id": "b", "source_sha256": "y", "evidence": [
            {"category": "fonts_language", "node": "n", "part": "p", "observed_value": "Arial",
             "confidence": 1.0, "authority": "observed", "status": "resolved", "conflicts": []}]},
    ]
    agg = profiler.aggregate_domain_profile(fake_profiles, "toy-domain", 0.6)
    assert agg["resolution"]["level"] == "abstain"  # only 2 docs, below the n>=3 floor


def test_aggregate_domain_profile_reaches_domain_family_above_threshold() -> None:
    fake_profiles = [
        {"doc_id": f"d{i}", "source_sha256": f"h{i}", "evidence": [
            {"category": "fonts_language", "node": "n", "part": "p", "observed_value": "Calibri",
             "confidence": 1.0, "authority": "observed", "status": "resolved", "conflicts": []}]}
        for i in range(4)
    ] + [
        {"doc_id": "d_minority", "source_sha256": "hm", "evidence": [
            {"category": "fonts_language", "node": "n", "part": "p", "observed_value": "Arial",
             "confidence": 1.0, "authority": "observed", "status": "resolved", "conflicts": []}]},
    ]
    agg = profiler.aggregate_domain_profile(fake_profiles, "toy-domain", 0.6)
    assert agg["resolution"]["level"] == "domain_family"
    node_ev = next(e for e in agg["evidence"] if e["node"] == "n")
    assert node_ev["observed_value"] == "Calibri"
    assert node_ev["authority"] == "domain_default"
    assert node_ev["conflicts"] == ["Arial"]


def test_aggregate_hash_stable_for_same_evidence_regardless_of_input_order() -> None:
    ev_a = {"category": "fonts_language", "node": "n", "part": "p", "observed_value": "Calibri",
            "confidence": 1.0, "authority": "observed", "status": "resolved", "conflicts": []}
    ev_b = {"category": "fonts_language", "node": "n", "part": "p", "observed_value": "Calibri",
            "confidence": 1.0, "authority": "observed", "status": "resolved", "conflicts": []}
    ev_c = {"category": "fonts_language", "node": "n", "part": "p", "observed_value": "Calibri",
            "confidence": 1.0, "authority": "observed", "status": "resolved", "conflicts": []}
    profs_in_order = [
        {"doc_id": "d0", "source_sha256": "h0", "evidence": [ev_a]},
        {"doc_id": "d1", "source_sha256": "h1", "evidence": [ev_b]},
        {"doc_id": "d2", "source_sha256": "h2", "evidence": [ev_c]},
    ]
    profs_reversed = list(reversed(profs_in_order))
    agg1 = profiler.aggregate_domain_profile(profs_in_order, "toy-domain", 0.6)
    agg2 = profiler.aggregate_domain_profile(profs_reversed, "toy-domain", 0.6)
    assert agg1["profile_hash"] == agg2["profile_hash"]
