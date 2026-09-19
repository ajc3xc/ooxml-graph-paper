#!/usr/bin/env python3
"""Integrity audit for the multi-anchor extension runs: for every chain
graded completed/completed_with_failure, check whether its working doc.docx
still plausibly belongs to the document the chain claims to be about, by
comparing early paragraph text against the real corpus source file's early
paragraph text.

Found live (2026-09-19): a handful of control-arm chains' trial-local
doc.docx ended up holding a DIFFERENT, real corpus document's content
instead of their assigned source -- see the "Control-arm-only
document-identity contamination bug" finding. Every instance found so far
was correctly graded as a failure by the grader (not a false positive), but
it still inflates control-arm's failure count for a harness reason rather
than genuine model incapability, biasing the control-vs-treatment
comparison unless caught and re-run clean.

Cheap heuristic, not a full diff: if none of the source's first N non-empty
paragraphs appear (even substring-fuzzy) anywhere in the trial copy's first
M paragraphs, flag it as a likely identity mismatch.

Usage:
    python3 audit_doc_identity.py <family> --run-root <path> --manifest <path>
    python3 audit_doc_identity.py <family> --run-root <path> --manifest <path> --reset

--reset deletes the whole chain_dir for every flagged mismatch (not just
chain-result.json) so checkpoint-resume treats it as unattempted and a
re-run of the same harness command re-executes ONLY those chains cleanly --
everything else already has a trusted checkpoint and is skipped instantly.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import docx


def build_label_to_path(manifest: dict) -> dict[str, str]:
    """original_doc_label -> real source docx path, from the corpus manifest.

    Defensive about key names (doc_label/label/name, docx_path/path) since
    this is meant to work against any of this project's manifest shapes,
    not just remote_corpus_manifest.json's specific one.
    """
    label_to_path: dict[str, str] = {}

    def walk(obj):
        if isinstance(obj, dict):
            keys = set(obj.keys())
            if {"docx_path"} & keys or {"path"} & keys:
                lbl = obj.get("doc_label") or obj.get("label") or obj.get("name")
                p = obj.get("docx_path") or obj.get("path")
                if lbl and p:
                    label_to_path[lbl] = p
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(manifest)
    return label_to_path


def first_paras(path_str: str, n: int = 5) -> tuple[list[str] | None, str | None]:
    try:
        d = docx.Document(path_str)
    except Exception as exc:  # noqa: BLE001 -- report, don't crash the audit
        return None, f"UNREADABLE: {exc}"
    texts = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    return texts[:n], None


def audit(family: str, run_root: Path, manifest_path: Path) -> tuple[dict, list[dict]]:
    mapping_path = run_root / "doc_label_mapping.json"
    mapping = {m["doc_label"]: m for m in json.loads(mapping_path.read_text(encoding="utf-8"))}
    label_to_path = build_label_to_path(json.loads(manifest_path.read_text(encoding="utf-8")))

    results = {"ok": 0, "mismatch": 0, "unreadable": 0, "no_source": 0, "skipped_no_trial": 0}
    mismatches = []

    for chain_dir in sorted(run_root.iterdir()):
        if not chain_dir.is_dir():
            continue
        cr = chain_dir / "chain-result.json"
        if not cr.is_file():
            continue
        try:
            result = json.loads(cr.read_text(encoding="utf-8"))
        except Exception:
            continue
        if result.get("status") not in ("completed", "completed_with_failure"):
            continue
        doc_label = result.get("doc_label")
        m = mapping.get(doc_label)
        if m is None:
            results["no_source"] += 1
            continue
        orig_label = m["original_doc_label"]
        src_path = label_to_path.get(orig_label)
        if not src_path:
            results["no_source"] += 1
            continue

        candidates = sorted(chain_dir.glob("**/doc.docx"))
        if not candidates:
            results["skipped_no_trial"] += 1
            continue
        trial_docx = candidates[-1]

        src_texts, src_err = first_paras(src_path, n=5)
        trial_texts, trial_err = first_paras(str(trial_docx), n=40)
        if trial_err:
            # The chain's own FINAL artifact can't even be parsed (e.g. a
            # broken OOXML package missing a referenced media part) --
            # that's a reset-worthy integrity problem regardless of status,
            # not a benign "skip and move on" case: a "completed" grade on
            # an unopenable package can't be trusted either.
            results["unreadable"] += 1
            mismatches.append({
                "doc_label": doc_label,
                "chain_dir": chain_dir.name,
                "expected_source": orig_label,
                "expected_first_line": src_texts[0][:80] if src_texts else None,
                "trial_first_lines": None,
                "reason": f"trial doc unreadable: {trial_err}",
            })
            continue
        if src_err:
            results["unreadable"] += 1
            continue
        if not src_texts:
            results["no_source"] += 1
            continue

        trial_blob = "\n".join(trial_texts).lower()
        hit = any(t.lower()[:40] in trial_blob for t in src_texts if len(t) >= 15)
        if hit:
            results["ok"] += 1
        else:
            results["mismatch"] += 1
            mismatches.append({
                "doc_label": doc_label,
                "chain_dir": chain_dir.name,
                "expected_source": orig_label,
                "expected_first_line": src_texts[0][:80] if src_texts else None,
                "trial_first_lines": trial_texts[:3],
            })

    return results, mismatches


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("family")
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--reset", action="store_true",
                         help="Delete every flagged chain_dir so a re-run of the harness re-executes it clean.")
    args = parser.parse_args()

    results, mismatches = audit(args.family, args.run_root, args.manifest)

    print(f"=== {args.family} identity audit ===")
    print(json.dumps(results, indent=2))
    if not mismatches:
        print("\nNo identity mismatches found.")
        return

    print(f"\n{len(mismatches)} MISMATCH(ES):")
    for mm in mismatches:
        print(json.dumps(mm, indent=2))

    if args.reset:
        print(f"\n--reset: deleting {len(mismatches)} flagged chain director{'y' if len(mismatches) == 1 else 'ies'}...")
        for mm in mismatches:
            chain_dir = args.run_root / mm["chain_dir"]
            if chain_dir.is_dir():
                shutil.rmtree(chain_dir)
                print(f"  removed {chain_dir}")
        print("Re-run the same harness command for this family -- everything else has a "
              "trusted checkpoint and will be skipped instantly; only the reset chains re-execute.")
    else:
        print("\n(dry run -- pass --reset to delete these chain directories so a re-run re-executes them clean)")


if __name__ == "__main__":
    main()
