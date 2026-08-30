"""PAPER-S18 PREFLIGHT: independent, source-agnostic DOCX ZIP/XML scanner and
rights/privacy adjudication-ledger builder for candidate documents that might
carry *organic* (real-world, non-hand-authored) OMML equations.

Why this exists
----------------
The D0 gold corpus (127 documents) and the raw/external pools behind it
(155 raw + 152 docops-source, 434 packages total as of 2026-08-30) contain
exactly 7 native-OMML packages / 8 <m:oMath> containers, and every one of
them is a hand-authored tier1/tier3 fixture
(fixture-02-equation, fixture-06-equation-radical, fixture-07-equation-empty-child,
fixture-08-equation-fallback, composite-01-report, composite-02-adversarial,
composite-03-multi). Zero real-world documents in any locally available pool
contain a native OMML equation. S6 (the equation-writer benchmark) is
blocked on assembling >=24 clean *organic* OMML units from >=8 independent
source groups and >=6 task families, plus human rights/exposure approval.
This script is the reusable, independent screening tool required before any
new candidate can be considered for that pool.

What it does
------------
For each .docx file under one or more --root directories (or explicit
--file paths):
  1. Reads the raw bytes and computes a whole-package SHA-256 (identity/dedup
     across byte-identical copies).
  2. Opens it as a zip, validates member integrity (zf.testzip()), confirms
     [Content_Types].xml and word/document.xml are present, and parses every
     word/*.xml part as XML -- this is a lightweight, self-contained integrity
     check, independent of and narrower in scope than the product's own
     ooxml_integrity.validate_docx_package (that deeper check remains the
     authority used by tools/build_gold_manifests.py for anything actually
     promoted to gold).
  3. Walks every parsed word/*.xml part (document, headers, footers,
     footnotes, endnotes, comments, glossary) for elements in the OOXML Math
     namespace, counts <m:oMath> containers, and classifies child elements
     into the same 8 feature-family buckets already used in
     docs/native-docx-corpus-candidate-manifest-v1.json (fraction, radical,
     subscript, superscript, nary, matrix_or_array, accent_or_limit,
     multi_script) so results are directly comparable to that D1 audit.
  4. Computes a content-level SHA-256 (over the sorted word/*.xml part names
     and bytes) so byte-different-but-content-identical repackagings can be
     deduplicated separately from whole-file dedup.
  5. Emits one adjudication-ledger record per file with every field this
     project's rights/privacy policy requires: source URL/timestamp,
     source-group key, task-family key, license/redistribution status,
     privacy/PII review, exposure review, independent-gold-extraction status,
     and Word receipt -- every field that has no real answer yet is recorded
     as an explicit "not_assessed" / "unknown_pending_review" / "not_run"
     value, never silently omitted or guessed.

What it does NOT do
--------------------
- It does not download anything. It only reads files already present on
  local disk. Acquiring new public candidates (e.g. the ~18,680 filtered-but-
  unreviewed docx-corpus URLs recorded in
  raw/docx-corpus/filtered_candidates.json) requires fetching third-party
  content from an external host, which is outside this script's scope and,
  per this project's standing operating policy, requires an explicit human
  go-ahead before any such fetch -- not a decision an autonomous preflight
  script makes for itself. See docs/paper-s18-organic-omml-preflight-v1.md.
- It does not relabel, promote, or mutate any existing D0 gold document. It
  is read-only over whatever roots it is pointed at.
- It does not import Meridian's product parser (docs_intel.py) to decide
  whether a file has OMML -- that determination is made entirely from raw
  ZIP/XML inspection, independent of the product.

Usage
-----
  pixi run python tools/screen_organic_omml_candidates.py \
      --root "E:/MeridianData/ooxml-graph-paper/raw" \
      --root "E:/MeridianData/ooxml-graph-paper/external/docops-source" \
      --root "E:/MeridianData/ooxml-graph-paper/gold" \
      --out "E:/MeridianData/ooxml-graph-paper/manifests/s18-omml-screen-<ts>.json"

With no --root/--file given, it defaults to scanning the three pools named
above (the full set of locally available DOCX pools as of 2026-08-30).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT_VERSION = "s18-organic-omml-scanner-v1"

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# Same 8 buckets as docs/native-docx-corpus-candidate-manifest-v1.json's
# `equation_classes`, keyed by OMML local tag name (namespace already
# constrained to M_NS by the caller).
FEATURE_FAMILIES: dict[str, set[str]] = {
    "fraction": {"f"},
    "radical": {"rad"},
    "subscript": {"sSub"},
    "superscript": {"sSup"},
    "nary": {"nary"},
    "matrix_or_array": {"m", "eqArr"},
    "accent_or_limit": {"acc", "bar", "box", "borderBox", "groupChr", "d", "limLow", "limUpp"},
    "multi_script": {"sSubSup", "sPre", "sPost"},
}

DEFAULT_ROOTS = [
    Path("E:/MeridianData/ooxml-graph-paper/raw"),
    Path("E:/MeridianData/ooxml-graph-paper/external/docops-source"),
    Path("E:/MeridianData/ooxml-graph-paper/gold"),
]

# Doc-id/filename prefixes this project already uses exclusively for
# hand-authored, non-organic fixtures. Used only to annotate results for
# readability -- never to silently drop a record from the ledger.
HAND_AUTHORED_PREFIXES = ("fixture-", "composite-")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_docx(path: Path) -> dict:
    """Read-only ZIP/XML scan of one .docx. Never raises for a malformed
    file -- integrity failures are recorded in the result, not thrown."""
    entry: dict = {
        "path": str(path),
        "filename": path.name,
        "sha256": None,
        "size_bytes": None,
        "content_sha256_for_dedup": None,
        "package_integrity": {"ok": False, "errors": [], "xml_parts_checked": []},
        "has_native_omath": False,
        "omath_container_count": 0,
        "feature_families": {},
        "looks_hand_authored_by_name": path.stem.startswith(HAND_AUTHORED_PREFIXES),
    }

    try:
        raw = path.read_bytes()
    except OSError as exc:
        entry["package_integrity"]["errors"].append(f"unreadable: {exc}")
        return entry

    entry["sha256"] = _sha256_bytes(raw)
    entry["size_bytes"] = len(raw)

    try:
        with zipfile.ZipFile(path) as zf:
            errors: list[str] = []
            bad_member = zf.testzip()
            if bad_member:
                errors.append(f"corrupt member: {bad_member}")

            names = zf.namelist()
            if "[Content_Types].xml" not in names:
                errors.append("missing [Content_Types].xml")
            if "word/document.xml" not in names:
                errors.append("missing word/document.xml")

            xml_parts = sorted(n for n in names if n.startswith("word/") and n.endswith(".xml"))
            parsed_roots = []
            for name in xml_parts:
                data = zf.read(name)
                try:
                    parsed_roots.append(ET.fromstring(data))
                except ET.ParseError as exc:
                    errors.append(f"unparsable XML part {name}: {exc}")

            entry["package_integrity"] = {
                "ok": not errors,
                "errors": errors,
                "xml_parts_checked": xml_parts,
            }

            families: dict[str, int] = {}
            omath_containers = 0
            for root in parsed_roots:
                for el in root.iter():
                    tag = el.tag
                    if not tag.startswith("{"):
                        continue
                    ns, _, local = tag[1:].partition("}")
                    if ns != M_NS:
                        continue
                    if local == "oMath":
                        omath_containers += 1
                        continue
                    if local == "oMathPara":
                        continue
                    for family, tags in FEATURE_FAMILIES.items():
                        if local in tags:
                            families[family] = families.get(family, 0) + 1

            entry["has_native_omath"] = omath_containers > 0
            entry["omath_container_count"] = omath_containers
            entry["feature_families"] = families

            content_hasher = hashlib.sha256()
            for name in xml_parts:
                content_hasher.update(name.encode("utf-8"))
                content_hasher.update(zf.read(name))
            entry["content_sha256_for_dedup"] = content_hasher.hexdigest()
    except zipfile.BadZipFile as exc:
        entry["package_integrity"] = {
            "ok": False,
            "errors": [f"not a valid zip: {exc}"],
            "xml_parts_checked": [],
        }

    return entry


def build_ledger_record(scan: dict, metadata: dict | None = None) -> dict:
    """Wrap a raw scan result with every field this project's S18 rights/
    privacy policy requires. Any field with no real answer yet is set to an
    explicit sentinel, never omitted or guessed."""
    metadata = metadata or {}
    candidate_id = scan["sha256"][:16] if scan["sha256"] else "unhashable"
    return {
        "candidate_id": candidate_id,
        "path": scan["path"],
        "filename": scan["filename"],
        "sha256": scan["sha256"],
        "size_bytes": scan["size_bytes"],
        "content_sha256_for_dedup": scan["content_sha256_for_dedup"],
        "package_integrity": scan["package_integrity"],
        "has_native_omath": scan["has_native_omath"],
        "omath_container_count": scan["omath_container_count"],
        "feature_families": scan["feature_families"],
        "looks_hand_authored_by_name": scan["looks_hand_authored_by_name"],
        "source_url": metadata.get("source_url"),
        "source_retrieved_at": metadata.get("source_retrieved_at"),
        "source_group": metadata.get("source_group", "unassigned"),
        "task_family": metadata.get("task_family", "unassigned"),
        "license_or_redistribution": metadata.get("license_or_redistribution", "unknown_pending_review"),
        "privacy_pii_review": metadata.get("privacy_pii_review", "not_assessed"),
        "exposure_review": metadata.get("exposure_review", "not_assessed"),
        "independent_gold_extracted": metadata.get("independent_gold_extracted", False),
        "word_receipt": metadata.get("word_receipt", "not_run"),
        "admission_decision": metadata.get("admission_decision", "not_admitted"),
        "admission_reason": metadata.get("admission_reason"),
    }


def iter_docx_paths(roots: list[Path], files: list[Path]) -> list[Path]:
    found: list[Path] = list(files)
    for root in roots:
        if not root.exists():
            continue
        found.extend(sorted(root.rglob("*.docx")))
    # stable de-dup by resolved path, preserving first-seen order
    seen: set[str] = set()
    ordered: list[Path] = []
    for p in found:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            ordered.append(p)
    return ordered


def summarize(records: list[dict]) -> dict:
    by_sha: dict[str, list[str]] = {}
    by_content_sha: dict[str, list[str]] = {}
    content_sha_whole_shas: dict[str, set[str]] = {}
    family_totals: dict[str, int] = {}
    omath_records = []
    integrity_failures = []

    for r in records:
        if r["sha256"]:
            by_sha.setdefault(r["sha256"], []).append(r["path"])
        if r["content_sha256_for_dedup"]:
            by_content_sha.setdefault(r["content_sha256_for_dedup"], []).append(r["path"])
            content_sha_whole_shas.setdefault(r["content_sha256_for_dedup"], set()).add(r["sha256"])
        for family, count in r["feature_families"].items():
            family_totals[family] = family_totals.get(family, 0) + count
        if r["has_native_omath"]:
            omath_records.append(r["path"])
        if not r["package_integrity"]["ok"]:
            integrity_failures.append({"path": r["path"], "errors": r["package_integrity"]["errors"]})

    organic_omath_records = [
        r["path"] for r in records if r["has_native_omath"] and not r["looks_hand_authored_by_name"]
    ]
    hand_authored_omath_records = [
        r["path"] for r in records if r["has_native_omath"] and r["looks_hand_authored_by_name"]
    ]

    return {
        "total_scanned": len(records),
        "package_integrity_failures": len(integrity_failures),
        "package_integrity_failure_detail": integrity_failures,
        "documents_with_native_omath": len(omath_records),
        "documents_with_native_omath_paths": omath_records,
        "documents_with_native_omath_hand_authored_by_name": len(hand_authored_omath_records),
        "documents_with_native_omath_not_hand_authored_by_name": len(organic_omath_records),
        "organic_candidate_paths": organic_omath_records,
        "omath_container_total": sum(r["omath_container_count"] for r in records),
        "feature_family_totals": family_totals,
        "whole_file_duplicate_groups": {k: v for k, v in by_sha.items() if len(v) > 1},
        # Same rendered/logical XML content packaged under genuinely different
        # bytes (e.g. re-zipped, different compression, metadata timestamp
        # changed) -- distinct from whole_file_duplicate_groups above, which
        # only catches byte-identical copies.
        "content_duplicate_groups_across_different_bytes": {
            k: v
            for k, v in by_content_sha.items()
            if len(v) > 1 and len(content_sha_whole_shas[k]) > 1
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", action="append", default=[], type=Path,
                         help="Directory to recursively scan for *.docx (repeatable).")
    parser.add_argument("--file", action="append", default=[], type=Path,
                         help="Explicit .docx file to scan (repeatable).")
    parser.add_argument("--metadata", type=Path, default=None,
                         help="Optional JSON file mapping absolute path -> ledger metadata overrides.")
    parser.add_argument("--out", type=Path, required=True,
                         help="Path to write the JSON scan+ledger result to.")
    args = parser.parse_args(argv)

    roots = args.root or (list(DEFAULT_ROOTS) if not args.file else [])
    files = args.file

    metadata_by_path: dict[str, dict] = {}
    if args.metadata and args.metadata.exists():
        metadata_by_path = json.loads(args.metadata.read_text(encoding="utf-8"))

    paths = iter_docx_paths(roots, files)
    records = []
    for p in paths:
        scan = scan_docx(p)
        record = build_ledger_record(scan, metadata_by_path.get(str(p.resolve())))
        records.append(record)

    summary = summarize(records)
    output = {
        "schema": "s18-organic-omml-screen-v1",
        "scanner_version": SCRIPT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots_scanned": [str(r) for r in roots],
        "explicit_files_scanned": [str(f) for f in files],
        "summary": summary,
        "records": records,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"wrote {args.out}")
    print(f"total_scanned={summary['total_scanned']}")
    print(f"documents_with_native_omath={summary['documents_with_native_omath']}")
    print(f"  hand_authored_by_name={summary['documents_with_native_omath_hand_authored_by_name']}")
    print(f"  NOT_hand_authored_by_name (organic candidates)={summary['documents_with_native_omath_not_hand_authored_by_name']}")
    print(f"package_integrity_failures={summary['package_integrity_failures']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
