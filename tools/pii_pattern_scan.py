"""Bounded, reproducible regex PII pattern scan, reusing the exact pattern
family PAPER-S13's DocOps audit already established and this project already
accepted as a legitimate (if explicitly non-legal-grade) screening step:
email addresses, US-format phone numbers, SSN-pattern digit groups, and long
digit runs (potential card/account numbers). Operates on a .docx's visible
text (word/document.xml's <w:t> runs), never on raw XML markup, so a
structural artifact (a table cell id, a revision timestamp) cannot masquerade
as a text-level match.

Per PAPER-S13's own explicit framing: this is a bounded, reproducible regex
pass, NOT a substitute for a legal/manual PII review. It only catches
STRUCTURED patterns (a well-formed phone number, a labeled SSN-shaped digit
group), not free-text PII (a name mentioned in an otherwise-fictional
sentence). Findings must be read in that light, not treated as a clearance.
"""
from __future__ import annotations

import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LONG_DIGIT_RUN_RE = re.compile(r"\b\d{13,19}\b")

_PLACEHOLDER_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "example.test"}


_TEXT_BEARING_PART_PREFIXES = ("word/header", "word/footer")
_TEXT_BEARING_PARTS = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml")


def _part_text(xml_bytes: bytes) -> str:
    """Join a part's own <w:t> runs WITHIN each paragraph (correct -- a run
    split mid-word, e.g. for bold, must stay contiguous), but insert a
    newline BETWEEN paragraphs. Found live (2026-08-31): joining every <w:t>
    in the whole part with "" glues adjacent paragraphs (e.g. an address
    block's separate lines) into one unbroken run of characters, which can
    silently swallow a real phone/SSN/email match's trailing `\\b` word
    boundary -- a false NEGATIVE that let real PII patterns escape detection,
    not merely the previously-known false-POSITIVE direction (concatenated
    table cells misread as phone numbers) already documented in
    docs/paper-s6-organic-omml-round2-3-result-v1.md."""
    root = ET.fromstring(xml_bytes)
    paragraphs = []
    for p in root.iter(f"{{{_W_NS}}}p"):
        paragraphs.append("".join(t.text or "" for t in p.iter(f"{{{_W_NS}}}t")))
    return "\n".join(paragraphs)


def _extract_visible_text(docx_path: Path) -> str:
    """Visible text across every part a reader actually sees -- the main
    body, headers/footers, and footnotes/endnotes -- not just
    word/document.xml. A confidentiality notice or contact block living in a
    header/footer (a separate OOXML part) was previously invisible to this
    scanner entirely."""
    with zipfile.ZipFile(docx_path) as zf:
        names = zf.namelist()
        parts = [
            n for n in names
            if n in _TEXT_BEARING_PARTS or n.startswith(_TEXT_BEARING_PART_PREFIXES)
        ]
        texts = [_part_text(zf.read(n)) for n in parts]
    return "\n".join(texts)


def scan_document(docx_path: Path) -> dict[str, Any]:
    text = _extract_visible_text(docx_path)

    emails = _EMAIL_RE.findall(text)
    real_emails = [e for e in emails if e.rsplit("@", 1)[-1].lower() not in _PLACEHOLDER_EMAIL_DOMAINS]
    placeholder_emails = [e for e in emails if e not in real_emails]

    phones = _PHONE_RE.findall(text)
    ssns = _SSN_RE.findall(text)
    long_digit_runs = _LONG_DIGIT_RUN_RE.findall(text)

    return {
        "path": str(docx_path),
        "email_matches_total": len(emails),
        "email_matches_placeholder_rfc2606": len(placeholder_emails),
        "email_matches_real_domain": len(real_emails),
        "real_email_samples": real_emails[:5],
        "phone_matches": len(phones),
        "ssn_pattern_matches": len(ssns),
        "long_digit_run_matches": len(long_digit_runs),
        "long_digit_run_samples": long_digit_runs[:5],
        "clean": not (real_emails or phones or ssns or long_digit_runs),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", action="append", default=[], type=Path, dest="files")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    results = []
    for path in args.files:
        try:
            results.append(scan_document(path))
        except Exception as exc:  # noqa: BLE001
            results.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})

    summary = {
        "schema": "pii-pattern-scan-v1",
        "pattern_families": ["email", "us_phone", "ssn_pattern", "long_digit_run"],
        "caveat": "Bounded, reproducible regex pass over visible text only -- catches structured patterns, not free-text PII. Not a substitute for legal/manual review.",
        "file_count": len(results),
        "clean_count": sum(1 for r in results if r.get("clean")),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    for r in results:
        if not r.get("clean", True):
            print(f"FLAGGED: {r['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
