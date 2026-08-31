"""Regression tests for the bounded PII pattern scanner."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pii_pattern_scan import scan_document  # noqa: E402

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx(tmp_path: Path, text: str) -> Path:
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}"><w:body>'
        f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
        f'</w:body></w:document>'
    ).encode("utf-8")
    path = tmp_path / "doc.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return path


def test_clean_document_reports_clean(tmp_path: Path) -> None:
    path = _make_docx(tmp_path, "This is a perfectly ordinary paragraph with no sensitive data.")

    result = scan_document(path)

    assert result["clean"] is True
    assert result["email_matches_total"] == 0
    assert result["phone_matches"] == 0


def test_placeholder_email_does_not_flag(tmp_path: Path) -> None:
    path = _make_docx(tmp_path, "Contact us at community@example.test for more information.")

    result = scan_document(path)

    assert result["clean"] is True
    assert result["email_matches_placeholder_rfc2606"] == 1
    assert result["email_matches_real_domain"] == 0


def test_real_email_domain_flags(tmp_path: Path) -> None:
    path = _make_docx(tmp_path, "Reach the project manager at elena.park@realcompany.com anytime.")

    result = scan_document(path)

    assert result["clean"] is False
    assert result["email_matches_real_domain"] == 1
    assert "elena.park@realcompany.com" in result["real_email_samples"]


def test_us_phone_number_flags(tmp_path: Path) -> None:
    path = _make_docx(tmp_path, "Call the office at 555-234-6789 during business hours.")

    result = scan_document(path)

    assert result["clean"] is False
    assert result["phone_matches"] == 1


def test_ssn_pattern_flags(tmp_path: Path) -> None:
    path = _make_docx(tmp_path, "Employee record on file: 123-45-6789.")

    result = scan_document(path)

    assert result["clean"] is False
    assert result["ssn_pattern_matches"] == 1


def test_long_digit_run_flags(tmp_path: Path) -> None:
    path = _make_docx(tmp_path, "Account number 4111111111111111 was charged.")

    result = scan_document(path)

    assert result["clean"] is False
    assert result["long_digit_run_matches"] == 1
