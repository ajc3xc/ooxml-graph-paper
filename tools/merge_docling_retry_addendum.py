"""PAPER-36: merge the standalone crash-retry outputs into a durable, labeled
addendum manifest -- NOT silently folded back into the main run's aggregate
statistics (matching the PAPER-15 equation-addendum pattern: targeted retries
are reported separately and explicitly, never used to quietly improve a
headline number).
"""
from __future__ import annotations

import json
from pathlib import Path

SCRATCH = Path(r"C:\Users\13144\AppData\Local\Temp\claude\C--Users-13144-Documents-Meridian-ooxml-graph-paper\b425ba47-4f00-4009-b058-0371b1939e57\scratchpad")
OUT_PATH = Path("E:/MeridianData/ooxml-graph-paper/manifests/paper36-docling-crash-retry-addendum.json")

RETRIED_DOC_IDS = [
    "tier2-docxcorpus-fcf0d7bdf71d9756",
    "tier2-docxcorpus-392c7d7c263d52db",
    "tier2-omegause-009-ch3-results",
    "tier2-docxcorpus-bfb35496a7d01232",
    "tier2-docxcorpus-e63dc39fa8b54d6a",
    "tier2-omegause-088-product-spec-2",
]


def main() -> None:
    entries = []
    for doc_id in RETRIED_DOC_IDS:
        path = SCRATCH / f"retry_{doc_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries.append({
            "doc_id": doc_id,
            "original_run_status": "crashed",
            "original_run_error": "Windows STATUS_ACCESS_VIOLATION (0xC0000005), exit code 3221225477",
            "retry_status": payload.get("conversion_status"),
            "retry_wall_time_seconds": payload.get("wall_time_seconds"),
            "retry_page_count": payload.get("page_count"),
            "retry_text_item_count": payload.get("text_item_count"),
            "retry_table_count": payload.get("table_count"),
            "retry_equation_count": payload.get("equation_count"),
        })

    out = {
        "schema": "paper36-docling-crash-retry-addendum-v1",
        "note": (
            "6 documents crashed with an identical native access violation during "
            "the main PAPER-36 run, which overlapped with PAPER-38's concurrent "
            "hardening workflow on this shared host. All 6 were retried in "
            "isolation, individually, via tools/docling_convert_one.py, after both "
            "concurrent background jobs had finished. This addendum is reported "
            "separately, not folded into paper15-smoke-run-20260828T154212Z.json's "
            "own aggregate macro-averages -- that report's 120/127 scored, 6 "
            "crashed, 1 timed_out figures remain the honest record of the actual "
            "run as executed. This addendum documents what happened on retry."
        ),
        "all_six_succeeded_on_retry": all(e["retry_status"] == "ConversionStatus.SUCCESS" for e in entries),
        "entries": entries,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"all_six_succeeded_on_retry: {out['all_six_succeeded_on_retry']}")
    for e in entries:
        print(f"  {e['doc_id']}: {e['retry_status']}, {e['retry_page_count']} pages, {e['retry_wall_time_seconds']:.1f}s")


if __name__ == "__main__":
    main()
