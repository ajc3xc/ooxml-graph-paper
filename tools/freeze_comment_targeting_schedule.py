"""PAPER-S24 comment_targeting only: freezes resolve_comment_targeting_clusters's
output for the three real corpus documents into one hash-pinned JSON file,
run once at corpus-build time -- the same convention resolve_respec_schedule's
own callers already follow for respec_cascade (protocol section 2.2 item 4).

Usage:
    python freeze_comment_targeting_schedule.py --out <path> [--max-k 8] [--min-group-size 3]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from docx_anchor_prober import resolve_comment_targeting_clusters

REAL_DOCUMENTS: dict[str, Path] = {
    "jcshm-manuscript": Path(r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\jcshm-manuscript.docx"),
    "jcshm-si": Path(r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\jcshm-si.docx"),
    "masters-dissertation-defense": Path(r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\masters-dissertation-defense.docx"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-k", type=int, default=8)
    parser.add_argument("--min-group-size", type=int, default=3)
    args = parser.parse_args(argv)

    schedules: dict[str, Any] = {}
    for label, path in REAL_DOCUMENTS.items():
        if not path.is_file():
            schedules[label] = {"error": f"corpus file not found: {path}"}
            continue
        result = resolve_comment_targeting_clusters(path, max_k=args.max_k, min_group_size=args.min_group_size)
        result["source_sha256"] = _sha256(path)
        schedules[label] = result

    out = {
        "schema": "paper-s24-comment-targeting-schedule-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "max_k": args.max_k,
        "min_group_size": args.min_group_size,
        "resolver_self_sha256": _sha256(Path(__file__).with_name("docx_anchor_prober.py")),
        "documents": schedules,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    for label, sched in schedules.items():
        if "error" in sched:
            print(f"{label}: ERROR {sched['error']}")
            continue
        print(
            f"{label}: usable_k={sched['usable_k']} "
            f"regime1={sched['regime1_cluster_count']} regime2={sched['regime2_cluster_count']} "
            f"duplicate_para_ids={sched['duplicate_para_id_count']} "
            f"excluded={len(sched['excluded_candidates'])}"
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
