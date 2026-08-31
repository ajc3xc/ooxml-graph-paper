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


def _make_multi_paragraph_docx(tmp_path: Path, paragraphs: list[str]) -> Path:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>'
    ).encode("utf-8")
    path = tmp_path / "doc.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return path


def test_phone_number_across_a_paragraph_boundary_still_flags(tmp_path: Path) -> None:
    """Found live (2026-08-31) screening real acquired documents: an address
    block written as separate paragraphs ('202 E Earll Dr.', 'Phoenix, AZ
    85012', 'Phone: (602) 759-1905', 'www.example.com') was joined with NO
    separator, fusing the phone number's trailing digits directly onto the
    next paragraph's text and breaking the phone regex's trailing \\b word
    boundary -- a real phone number silently reported as clean."""
    path = _make_multi_paragraph_docx(
        tmp_path,
        ["202 E Earll Dr. Ste 110", "Phoenix, AZ 85012", "Phone: (602) 759-1905", "www.njbsoft.com"],
    )

    result = scan_document(path)

    assert result["clean"] is False
    assert result["phone_matches"] == 1


def test_pii_in_a_footer_part_is_detected(tmp_path: Path) -> None:
    """Headers/footers live in separate OOXML parts (word/footer1.xml, etc.),
    never inline in word/document.xml -- a confidentiality notice or contact
    block placed there was previously invisible to this scanner entirely."""
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}"><w:body>'
        f'<w:p><w:r><w:t>This is an ordinary body paragraph.</w:t></w:r></w:p>'
        f'</w:body></w:document>'
    ).encode("utf-8")
    footer_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:ftr xmlns:w="{_W}">'
        f'<w:p><w:r><w:t>Questions? Email elena.park@realcompany.com</w:t></w:r></w:p>'
        f'</w:ftr>'
    ).encode("utf-8")
    path = tmp_path / "doc.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/footer1.xml", footer_xml)

    result = scan_document(path)

    assert result["clean"] is False
    assert result["email_matches_real_domain"] == 1
