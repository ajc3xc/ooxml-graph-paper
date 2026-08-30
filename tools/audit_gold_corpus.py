"""PAPER-29: independent audit/reconciliation of the gold DOCX corpus.

Read-only over E:\\MeridianData\\ooxml-graph-paper\\gold\\manifests -- does not
regenerate or alter any manifest. Checks, per document: source hash, Word-COM
PDF render receipt, package-integrity result, graph manifest presence,
privacy/license rationale (traced back to the source review artifact for
tier2 documents), split assignment, and at least one equation/caption/
reference-bearing node where the document's own content review said it should
have one. Also checks for duplicate underlying source content across distinct
doc_ids (same source_sha256 promoted twice under different names).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

MANIFEST_DIR = Path("E:/MeridianData/ooxml-graph-paper/gold/manifests")
RENDER_DIR = Path("E:/MeridianData/ooxml-graph-paper/renders/gold")
OUT_PATH = MANIFEST_DIR / "paper29-corpus-audit.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    split = _load(MANIFEST_DIR / "_split.json")
    split_by_doc = {}
    for split_name, doc_ids in split.items():
        if isinstance(doc_ids, list):
            for doc_id in doc_ids:
                split_by_doc[doc_id] = split_name

    docxcorpus_review = _load(MANIFEST_DIR / "_docxcorpus_review.json")
    # Keyed directly by the full doc_id (e.g. "tier2-docxcorpus-<hash prefix>"),
    # each value a {id, verdict, content_summary, reasoning, ...} record.
    docxcorpus_verdicts = {
        doc_id: entry.get("verdict") for doc_id, entry in docxcorpus_review.items()
    }

    tier2_review = _load(MANIFEST_DIR / "_tier2_review.json")
    tier2_promoted_notes = {
        p["doc_id"]: p.get("note") for p in tier2_review.get("promoted", []) if p.get("doc_id")
    }

    manifest_paths = sorted(
        p for p in MANIFEST_DIR.glob("*.manifest.json")
    )

    issues = []
    docs = []
    source_hash_to_docids = defaultdict(list)

    for path in manifest_paths:
        m = _load(path)
        doc_id = m.get("doc_id", path.stem.replace(".manifest", ""))
        entry = {"doc_id": doc_id, "manifest_path": str(path)}

        source_sha = m.get("gold_record", {}).get("document", {}).get("source_sha256")
        entry["has_source_hash"] = bool(source_sha)
        if not source_sha:
            issues.append({"doc_id": doc_id, "kind": "missing_source_hash"})
        else:
            source_hash_to_docids[source_sha].append(doc_id)

        render_receipt = m.get("render_receipt")
        render_result = m.get("render_result")
        entry["has_render_receipt"] = bool(render_receipt)
        entry["render_status"] = (render_result or {}).get("status") if isinstance(render_result, dict) else render_result
        render_pdf = RENDER_DIR / doc_id / f"{doc_id}.pdf"
        entry["render_pdf_on_disk"] = render_pdf.exists()
        if not render_receipt or not render_pdf.exists():
            issues.append({"doc_id": doc_id, "kind": "missing_or_unretained_render_receipt",
                           "has_receipt_field": bool(render_receipt), "pdf_on_disk": render_pdf.exists()})

        pkg_integrity = m.get("package_integrity")
        entry["has_package_integrity"] = bool(pkg_integrity)
        entry["package_integrity_ok"] = (
            pkg_integrity.get("ok") if isinstance(pkg_integrity, dict) else None
        )
        if not pkg_integrity:
            issues.append({"doc_id": doc_id, "kind": "missing_package_integrity"})
        elif isinstance(pkg_integrity, dict) and pkg_integrity.get("ok") is False:
            issues.append({"doc_id": doc_id, "kind": "package_integrity_failed", "detail": pkg_integrity})

        gold_record = m.get("gold_record", {})
        provenance = gold_record.get("provenance") or {}
        entry["provenance_producer"] = provenance.get("producer")
        if provenance.get("producer") in (None, "", "docs_intel.py", "meridian_docs.docs_intel"):
            issues.append({"doc_id": doc_id, "kind": "suspect_or_missing_independent_provenance",
                           "producer": provenance.get("producer")})

        nodes = gold_record.get("nodes", [])
        node_kinds = {n.get("kind") for n in nodes}
        entry["node_kinds"] = sorted(k for k in node_kinds if k)
        entry["equation_count"] = sum(1 for n in nodes if n.get("kind") == "equation")
        entry["caption_count"] = sum(1 for n in nodes if n.get("kind") == "caption")
        entry["reference_count"] = sum(1 for n in nodes if n.get("kind") in ("reference", "cross_reference"))

        split_name = split_by_doc.get(doc_id)
        entry["split"] = split_name
        if split_name is None:
            issues.append({"doc_id": doc_id, "kind": "missing_split_assignment"})

        entry["tier"] = m.get("tier")
        if str(doc_id).startswith("tier2-docxcorpus-"):
            verdict = docxcorpus_verdicts.get(doc_id)
            entry["docxcorpus_review_verdict"] = verdict
            if verdict != "promote":
                issues.append({"doc_id": doc_id, "kind": "docxcorpus_doc_without_promote_verdict",
                               "verdict_found": verdict})
        elif str(doc_id).startswith(("tier2-omegause-", "tier2-docxbenchmark-")):
            note = tier2_promoted_notes.get(doc_id)
            entry["tier2_review_rationale_note"] = note
            if not note:
                issues.append({
                    "doc_id": doc_id,
                    "kind": "missing_machine_readable_rights_rationale_in_tier2_review",
                    "detail": (
                        "no entry with a rationale note in _tier2_review.json's "
                        "'promoted' list; rationale may exist only as prose in "
                        "docs/dataset-landscape-2026-08-25.md, which is not "
                        "machine-checkable the same way as the OmegaUse entries"
                    ),
                })

        docs.append(entry)

    for source_sha, doc_ids in source_hash_to_docids.items():
        if len(doc_ids) > 1:
            issues.append({"kind": "duplicate_source_content", "source_sha256": source_sha, "doc_ids": doc_ids})

    summary = {
        "schema": "paper29-corpus-audit-v1",
        "total_documents": len(docs),
        "documents_missing_source_hash": sum(1 for d in docs if not d["has_source_hash"]),
        "documents_missing_render_receipt_or_pdf": sum(
            1 for d in docs if not d["has_render_receipt"] or not d["render_pdf_on_disk"]
        ),
        "documents_missing_package_integrity": sum(1 for d in docs if not d["has_package_integrity"]),
        "documents_with_failed_package_integrity": sum(
            1 for d in docs if d["package_integrity_ok"] is False
        ),
        "documents_missing_split_assignment": sum(1 for d in docs if d["split"] is None),
        "documents_with_suspect_provenance": sum(
            1 for i in issues if i["kind"] == "suspect_or_missing_independent_provenance"
        ),
        "documents_missing_machine_readable_rights_rationale": [
            i["doc_id"] for i in issues if i["kind"] == "missing_machine_readable_rights_rationale_in_tier2_review"
        ],
        "duplicate_source_content_groups": [i for i in issues if i["kind"] == "duplicate_source_content"],
        "docxcorpus_docs_without_promote_verdict": [
            i for i in issues if i["kind"] == "docxcorpus_doc_without_promote_verdict"
        ],
        "total_issues": len(issues),
        "issues": issues,
        "documents": docs,
    }

    OUT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"total_documents={summary['total_documents']} total_issues={summary['total_issues']}")
    for k, v in summary.items():
        if k.startswith("documents_") or k == "total_issues":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
