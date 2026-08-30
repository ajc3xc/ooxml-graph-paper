"""Unit tests for tools/screen_organic_omml_candidates.py's core ZIP/XML
scanning logic, built against small synthetic .docx packages (no dependency
on the real corpus under E:\\MeridianData) so these run anywhere.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from screen_organic_omml_candidates import (  # noqa: E402
    build_ledger_record,
    scan_docx,
    summarize,
)

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)

_DOC_XML_NO_MATH = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>hello world</w:t></w:r></w:p></w:body>"
    "</w:document>"
)

_DOC_XML_WITH_FRACTION_AND_NARY = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
    "<w:body><w:p><m:oMathPara><m:oMath>"
    "<m:f><m:num><m:r><m:t>1</m:t></m:r></m:num><m:den><m:r><m:t>2</m:t></m:r></m:den></m:f>"
    "</m:oMath></m:oMathPara></w:p>"
    "<w:p><m:oMath><m:nary><m:e><m:r><m:t>x</m:t></m:r></m:e></m:nary></m:oMath></w:p>"
    "</w:body></w:document>"
)


def _write_docx(path: Path, document_xml: str) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("word/document.xml", document_xml)


def test_scan_docx_no_math_reports_zero_omath(tmp_path: Path):
    p = tmp_path / "plain.docx"
    _write_docx(p, _DOC_XML_NO_MATH)
    result = scan_docx(p)
    assert result["package_integrity"]["ok"] is True
    assert result["has_native_omath"] is False
    assert result["omath_container_count"] == 0
    assert result["feature_families"] == {}


def test_scan_docx_detects_fraction_and_nary_families(tmp_path: Path):
    p = tmp_path / "fixture-equation.docx"
    _write_docx(p, _DOC_XML_WITH_FRACTION_AND_NARY)
    result = scan_docx(p)
    assert result["package_integrity"]["ok"] is True
    assert result["has_native_omath"] is True
    assert result["omath_container_count"] == 2
    assert result["feature_families"] == {"fraction": 1, "nary": 1}
    # Filename starts with "fixture-" -> flagged as hand-authored by name.
    assert result["looks_hand_authored_by_name"] is True


def test_scan_docx_organic_sounding_name_not_flagged_hand_authored(tmp_path: Path):
    p = tmp_path / "0308bc29-real-world-report.docx"
    _write_docx(p, _DOC_XML_WITH_FRACTION_AND_NARY)
    result = scan_docx(p)
    assert result["looks_hand_authored_by_name"] is False


def test_scan_docx_missing_content_types_is_integrity_failure(tmp_path: Path):
    p = tmp_path / "broken.docx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", _DOC_XML_NO_MATH)
    result = scan_docx(p)
    assert result["package_integrity"]["ok"] is False
    assert any("Content_Types" in e for e in result["package_integrity"]["errors"])


def test_scan_docx_unparsable_xml_part_is_integrity_failure(tmp_path: Path):
    p = tmp_path / "corrupt-xml.docx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("word/document.xml", "<w:document><unclosed>")
    result = scan_docx(p)
    assert result["package_integrity"]["ok"] is False
    assert any("unparsable" in e for e in result["package_integrity"]["errors"])


def test_scan_docx_not_a_zip_is_integrity_failure(tmp_path: Path):
    p = tmp_path / "notazip.docx"
    p.write_bytes(b"this is not a zip file at all")
    result = scan_docx(p)
    assert result["package_integrity"]["ok"] is False
    assert result["sha256"] is not None  # hashing still succeeds on unreadable-as-zip bytes


def test_build_ledger_record_defaults_every_required_field_explicitly(tmp_path: Path):
    p = tmp_path / "plain.docx"
    _write_docx(p, _DOC_XML_NO_MATH)
    record = build_ledger_record(scan_docx(p))
    assert record["source_url"] is None
    assert record["source_group"] == "unassigned"
    assert record["task_family"] == "unassigned"
    assert record["license_or_redistribution"] == "unknown_pending_review"
    assert record["privacy_pii_review"] == "not_assessed"
    assert record["exposure_review"] == "not_assessed"
    assert record["word_receipt"] == "not_run"
    assert record["admission_decision"] == "not_admitted"


def test_build_ledger_record_honors_supplied_metadata(tmp_path: Path):
    p = tmp_path / "plain.docx"
    _write_docx(p, _DOC_XML_NO_MATH)
    record = build_ledger_record(
        scan_docx(p),
        metadata={
            "source_url": "https://example.org/doc.docx",
            "source_group": "example-org",
            "task_family": "policy-memo",
            "license_or_redistribution": "cc0",
        },
    )
    assert record["source_url"] == "https://example.org/doc.docx"
    assert record["source_group"] == "example-org"
    assert record["task_family"] == "policy-memo"
    assert record["license_or_redistribution"] == "cc0"
    # Fields not supplied still get an explicit default.
    assert record["privacy_pii_review"] == "not_assessed"


def test_summarize_separates_hand_authored_from_organic_omath(tmp_path: Path):
    fixture = tmp_path / "fixture-equation.docx"
    _write_docx(fixture, _DOC_XML_WITH_FRACTION_AND_NARY)
    organic = tmp_path / "abcd1234-real-report.docx"
    _write_docx(organic, _DOC_XML_WITH_FRACTION_AND_NARY)
    plain = tmp_path / "plain.docx"
    _write_docx(plain, _DOC_XML_NO_MATH)

    records = [
        build_ledger_record(scan_docx(fixture)),
        build_ledger_record(scan_docx(organic)),
        build_ledger_record(scan_docx(plain)),
    ]
    summary = summarize(records)
    assert summary["total_scanned"] == 3
    assert summary["documents_with_native_omath"] == 2
    assert summary["documents_with_native_omath_hand_authored_by_name"] == 1
    assert summary["documents_with_native_omath_not_hand_authored_by_name"] == 1
    assert str(organic) in summary["organic_candidate_paths"]
    assert summary["feature_family_totals"] == {"fraction": 2, "nary": 2}


def test_summarize_detects_whole_file_duplicates(tmp_path: Path):
    a = tmp_path / "a.docx"
    b = tmp_path / "b.docx"
    _write_docx(a, _DOC_XML_NO_MATH)
    # Identical content bytes for the document part; whole-file zip bytes
    # will differ trivially in the general case, so instead copy the exact
    # bytes to guarantee a whole-file duplicate.
    b.write_bytes(a.read_bytes())

    records = [build_ledger_record(scan_docx(a)), build_ledger_record(scan_docx(b))]
    summary = summarize(records)
    dup_groups = summary["whole_file_duplicate_groups"]
    assert len(dup_groups) == 1
    (paths,) = dup_groups.values()
    assert sorted(paths) == sorted([str(a), str(b)])
