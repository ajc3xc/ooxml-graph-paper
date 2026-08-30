"""PAPER-38: targeted regeneration of gold_record text fields only, after the
tab/br fix to independent_gold_extractor.py's _local_text (PAPER-30/38).

Deliberately does NOT re-run Word-COM rendering (retained_render_receipt) or
package-integrity checks -- those are unaffected by a text-reconstruction fix
and re-rendering all 127 documents would be slow and risks new transient
Word-COM failures on documents that already have a good, verified receipt.
Re-runs only `independent_gold_extractor.extract()` per document and replaces
the `gold_record` field in the existing manifest, preserving render_receipt/
package_integrity/doc_id/tier/source_path untouched. Reports exactly how many
documents' gold text actually changed, not just that the script ran.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from independent_gold_extractor import extract  # noqa: E402

MANIFEST_DIR = Path("E:/MeridianData/ooxml-graph-paper/gold/manifests")


def main() -> None:
    changed = []
    unchanged = 0
    errors = []
    for path in sorted(MANIFEST_DIR.glob("*.manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        docx_path = Path(manifest["source_path"])
        if not docx_path.is_file():
            errors.append({"doc_id": manifest.get("doc_id"), "reason": f"source docx not found: {docx_path}"})
            continue
        old_text = manifest["gold_record"]["facts"]["text"]
        try:
            new_gold_record = extract(docx_path)
        except Exception as exc:  # noqa: BLE001
            errors.append({"doc_id": manifest.get("doc_id"), "reason": f"{type(exc).__name__}: {exc}"})
            continue
        new_text = new_gold_record["facts"]["text"]
        if new_text != old_text:
            changed.append({
                "doc_id": manifest.get("doc_id"),
                "old_text_len": len(old_text),
                "new_text_len": len(new_text),
            })
        else:
            unchanged += 1
        manifest["gold_record"] = new_gold_record
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"changed: {len(changed)}")
    print(f"unchanged: {unchanged}")
    print(f"errors: {len(errors)}")
    for c in changed:
        print(f"  CHANGED {c['doc_id']}: {c['old_text_len']} -> {c['new_text_len']} chars")
    for e in errors:
        print(f"  ERROR {e['doc_id']}: {e['reason']}")


if __name__ == "__main__":
    main()
