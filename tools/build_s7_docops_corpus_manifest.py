"""PAPER-S7/S16: derive the S9 benchmark's development/validation/primary-holdout
corpus manifest from DocOps' own already-audited, already-preregistered split
(manifests/docops/docops_prereg_split_v1.json, seed 20260830, PAPER-S13/S16).

Reuses that split rather than re-deriving a new one (same rationale S16 itself
would apply: don't re-split what is already properly split, preregistered, and
dated before any of this project's own results existed). The only transformation
here is (a) filtering to tasks with exactly one input .docx -- PAPER-S9's task
templates are single-document edits, so DocOps' 4 multi-document
"cross_doc_docops" tasks are excluded, not silently miscounted as failures, and
(b) remapping DocOps' four named stages onto S9's three-stage terminology per
docs/paper-s9-long-horizon-benchmark-protocol-v0.md section 3:
  development = DocOps "development" + "smoke" (debug the harness itself)
  validation  = DocOps "scale_up"
  primary_holdout = DocOps "final_holdout" (evaluated exactly once)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_DOCOPS_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\external\docops-source")
_SPLIT_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\manifests\docops\docops_prereg_split_v1.json")
_PURE_WORD_MANIFEST_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\manifests\docops\docops_pure_word_manifest.json")

_STAGE_REMAP = {
    "development": "development",
    "smoke": "development",
    "scale_up": "validation",
    "final_holdout": "primary_holdout",
}


def build_manifest() -> dict[str, Any]:
    split = json.loads(_SPLIT_PATH.read_text(encoding="utf-8"))
    pure_word = json.loads(_PURE_WORD_MANIFEST_PATH.read_text(encoding="utf-8"))
    by_task_dir = {entry["task_dir"]: entry for entry in pure_word}

    documents: list[dict[str, Any]] = []
    excluded_multi_file: list[str] = []
    excluded_missing: list[str] = []

    for docops_stage, task_dirs in split["assignment"].items():
        s7_split = _STAGE_REMAP[docops_stage]
        for task_dir in task_dirs:
            entry = by_task_dir.get(task_dir)
            if entry is None:
                excluded_missing.append(task_dir)
                continue
            input_files = entry.get("docx_input_files") or []
            if len(input_files) != 1:
                excluded_multi_file.append(task_dir)
                continue
            file_record = input_files[0]
            docx_path = _DOCOPS_ROOT / "tasks" / task_dir / "environment" / file_record["file"]
            documents.append(
                {
                    "doc_label": task_dir,
                    "docx_path": str(docx_path),
                    "sha256": file_record["sha256"],
                    "s7_split": s7_split,
                    "docops_stage": docops_stage,
                    "difficulty_level": entry.get("difficulty_level"),
                    "source_type": entry.get("source_type"),
                    "structural_scan": file_record.get("structural_scan"),
                }
            )

    split_counts = {}
    for doc in documents:
        split_counts[doc["s7_split"]] = split_counts.get(doc["s7_split"], 0) + 1

    missing_on_disk = [d["doc_label"] for d in documents if not Path(d["docx_path"]).is_file()]

    return {
        "schema": "paper-s7-docops-corpus-manifest-v1",
        "source_split": str(_SPLIT_PATH),
        "source_split_seed": split["seed"],
        "source_pure_word_manifest": str(_PURE_WORD_MANIFEST_PATH),
        "excluded_multi_file_tasks": excluded_multi_file,
        "excluded_missing_from_pure_word_manifest": excluded_missing,
        "missing_on_disk": missing_on_disk,
        "split_counts": split_counts,
        "total_documents": len(documents),
        "documents": documents,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    manifest = build_manifest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: v for k, v in manifest.items() if k != "documents"}, indent=2))
    if manifest["missing_on_disk"]:
        print(f"WARNING: {len(manifest['missing_on_disk'])} documents not found on disk: {manifest['missing_on_disk']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
