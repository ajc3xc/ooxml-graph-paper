"""PAPER-39: merge the standalone crash/timeout-retry outputs for the final
graph-aware scoring run into a durable addendum manifest, matching the
PAPER-36 pattern -- reported separately, never silently folded into the main
run's own aggregate/paired-test numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

SCRATCH = Path(r"C:\Users\13144\AppData\Local\Temp\claude\C--Users-13144-Documents-Meridian-ooxml-graph-paper\b425ba47-4f00-4009-b058-0371b1939e57\scratchpad")
OUT_PATH = Path("E:/MeridianData/ooxml-graph-paper/manifests/paper39-docling-retry-addendum.json")

RETRIED = {
    "tier2-omegause-039-thesis-template": "timed_out (300s)",
    "tier2-docxcorpus-d4b0f603137ef5d1": "crashed (0xC0000005)",
    "tier2-docxcorpus-4b9e8251787b5cd3": "crashed (0xC0000005)",
    "tier2-docxcorpus-31b78fbf950f9a3d": "crashed (0xC0000005)",
    "tier2-omegause-031-pinyin-worksheet": "timed_out (300s)",
    "tier2-omegause-059-project-proposal": "crashed (0xC0000005)",
    "tier2-omegause-025-business-plan": "crashed (0xC0000005)",
}


def main() -> None:
    entries = []
    for doc_id, original in RETRIED.items():
        path = SCRATCH / f"retry39_{doc_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries.append({
            "doc_id": doc_id,
            "original_status": original,
            "retry_status": payload.get("conversion_status"),
            "retry_wall_time_seconds": payload.get("wall_time_seconds"),
            "retry_page_count": payload.get("page_count"),
            "retry_text_item_count": payload.get("text_item_count"),
            "retry_table_count": payload.get("table_count"),
        })

    out = {
        "schema": "paper39-docling-retry-addendum-v1",
        "note": (
            "5 crashed + 2 non-price-catalog timeouts from the PAPER-39 full "
            "127-doc final graph-aware scoring run, retried individually via "
            "tools/docling_convert_one.py after the main run finished. This "
            "failure set was entirely DIFFERENT from PAPER-36's own crash/"
            "timeout set on the same documents/configuration -- further "
            "evidence these are transient, host-load-driven failures, not "
            "deterministic per-document defects. Reported separately, not "
            "folded into paper30-graph-eval-all-20260828T161244Z.json's own "
            "aggregate/paired-test numbers."
        ),
        "all_seven_succeeded_on_retry": all(e["retry_status"] == "ConversionStatus.SUCCESS" for e in entries),
        "notable": [
            (
                "tier2-omegause-031-pinyin-worksheet (a tiny 1-page, 573-character "
                "document) originally timed out at 300s -- flagged for scrutiny as "
                "a potential real anomaly rather than assumed transient. Retried "
                "in isolation: completed in 19.8 seconds with real content (1 "
                "page, 34 text items, 1 table detected) -- confirms this was "
                "genuinely a resource-contention artifact even for a trivially "
                "small document, not a per-document defect."
            ),
            (
                "tier2-omegause-025-business-plan is a genuine borderline case, not "
                "a clean confirmation of transience: it originally CRASHED (access "
                "violation, not a timeout), but its clean, isolated retry still took "
                "398.4 seconds -- longer than the standard 300-second timeout every "
                "other document in this corpus is scored against. This means a "
                "future clean run of this specific document under the standard "
                "300s configuration could legitimately time out on its own merits "
                "(a real, large/complex document near or over the pipeline's "
                "practical per-document budget), independent of any resource "
                "contention. Not assumed resolved; flagged as a real, standing "
                "capacity-boundary risk for this one document specifically."
            ),
        ],
        "entries": entries,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"all_seven_succeeded_on_retry: {out['all_seven_succeeded_on_retry']}")
    for e in entries:
        print(f"  {e['doc_id']}: {e['original_status']} -> {e['retry_status']} ({e['retry_wall_time_seconds']:.1f}s)")


if __name__ == "__main__":
    main()
