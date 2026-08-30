"""PAPER-S9 validator-gap re-probe, post-fix (2026-08-30).

Re-runs the exact two adversarial constructions described in
docs/paper-s9-long-horizon-benchmark-protocol-v0.md section 5/6.2 against
meridian_docs.docs_intel.ooxml_integrity.validate_docx_package, after the fix
applied in the parent repo (extensions/meridian-docs/meridian_docs/ooxml_integrity.py):
removed an early `if not rel_ids: continue` that skipped dangling-reference
checks whenever a part's .rels file was missing/empty, and added an explicit
duplicate-ZIP-part-name check. Imports meridian_docs.docs_intel read-only,
modifies nothing on disk beyond this script's own in-memory fixtures.
"""
from __future__ import annotations

import io
import json
import zipfile

from meridian_docs import docs_intel

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _good_parts() -> dict[str, bytes]:
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>'
        f'<w:p><w:r><w:t>Fixture.</w:t></w:r></w:p><w:sectPr/></w:body></w:document>'
    ).encode("utf-8")
    return {
        "[Content_Types].xml": (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<ct:Types xmlns:ct="{CT}">'
            f'<ct:Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            f'<ct:Default Extension="xml" ContentType="application/xml"/>'
            f'</ct:Types>'
        ).encode("utf-8"),
        "_rels/.rels": (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<pr:Relationships xmlns:pr="{PKG_REL}">'
            f'<pr:Relationship Id="rIdDoc" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            f'</pr:Relationships>'
        ).encode("utf-8"),
        "word/document.xml": document_xml,
    }


def _zip_bytes(parts: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    return stream.getvalue()


def main() -> None:
    good_bytes = _zip_bytes(_good_parts())

    dangling_parts = dict(_good_parts())
    dangling_parts["word/document.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}"><w:body>'
        f'<w:p><w:r><w:drawing><a:blip r:id="rId99"/></w:drawing></w:r></w:p><w:sectPr/></w:body></w:document>'
    ).encode("utf-8")
    # No word/_rels/document.xml.rels part at all -- rId99 is unresolvable.
    dangling_bytes = _zip_bytes(dangling_parts)

    duplicate_parts = dict(_good_parts())
    duplicate_bytes_stream = io.BytesIO()
    with zipfile.ZipFile(duplicate_bytes_stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in duplicate_parts.items():
            archive.writestr(name, payload)
        archive.writestr("word/document.xml", duplicate_parts["word/document.xml"] + b"<!-- second write -->")
    duplicate_bytes = duplicate_bytes_stream.getvalue()

    good_report = docs_intel.ooxml_integrity.validate_docx_package(good_bytes)
    dangling_report = docs_intel.ooxml_integrity.validate_docx_package(dangling_bytes)
    duplicate_report = docs_intel.ooxml_integrity.validate_docx_package(duplicate_bytes)

    result = {
        "good_fixture": {
            "ok": good_report["ok"],
            "verdict": "as_expected" if good_report["ok"] else "unexpected_ok_false_on_good_input",
            "issues": good_report["issues"],
        },
        "adversarial_dangling_relationship_ref": {
            "ok": dangling_report["ok"],
            "verdict": "gap_closed_now_caught" if not dangling_report["ok"] else "unexpected_ok_true_on_adversarial_input",
            "issues": dangling_report["issues"],
        },
        "adversarial_duplicate_zip_part": {
            "ok": duplicate_report["ok"],
            "verdict": "gap_closed_now_caught" if not duplicate_report["ok"] else "unexpected_ok_true_on_adversarial_input",
            "issues": duplicate_report["issues"],
        },
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
