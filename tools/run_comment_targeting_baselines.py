"""PAPER-S24: fresh, isolated K=1 baseline sweep for the comment_targeting
task family (docs/paper-s24-targeted-comment-protocol-v0.md section 3),
analogous to tools/run_respec_cascade_baselines.py -- read directly before
writing this, per this build's own discipline requirement; it is short and
a direct structural template, reused here rather than built from scratch.

Protocol section 3: "for every (document, target, arm), run one isolated,
single-step trial at the identical target and anchor used in the chain,
against a fresh copy of the same pristine document snapshot" -- this
resolves the one real, disclosed question the interleaved chain design
alone cannot answer (protocol section 7's own confirm criterion 5):
whether position-1 chain accuracy already differs from this same target's
accuracy in complete positional isolation.

Reads the ALREADY-frozen, hash-pinned per-document schedules (the SAME
file tools/run_comment_targeting_sweep.py itself reads), calling
tools/run_comment_targeting_family.py::run_comment_targeting_isolated_
baseline UNMODIFIED for every (document, condition, target_index, arm)
combination its own ambiguous_targets/unique_targets lists contain --
never re-resolving resolve_comment_targeting_clusters live, exactly the
"literal targets are frozen, not re-derived per trial" discipline this
project's other sweep drivers already commit to.

Usage:
    python run_comment_targeting_baselines.py --run-root <dir> --model haiku \\
        [--schedule-json D:/MeridianData/ooxml-graph-paper/runs/paper-s24/comment-targeting-schedule-v1.json]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_comment_targeting_family import run_comment_targeting_isolated_baseline  # noqa: E402
from run_comment_targeting_sweep import (  # noqa: E402
    REAL_DOCUMENTS,
    _DEFAULT_SCHEDULE_JSON,
    load_frozen_schedules,
)


def run_baseline_sweep(
    run_root: Path, model: str, schedule_json_path: Path = _DEFAULT_SCHEDULE_JSON,
    *, max_workers: int = 4, word_receipts_enabled: bool = False,
) -> dict[str, Any]:
    schedules = load_frozen_schedules(schedule_json_path)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "target-schedules.json").write_text(
        json.dumps(schedules, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    # (doc_label, docx_path, condition, target_index, target) per usable
    # target -- both ambiguous_targets AND unique_targets, each already
    # exactly usable_k long (protocol section 1.2b's own K table), not a
    # combined/halved pool -- mirrors _interleaved_steps's own reasoning in
    # tools/run_comment_targeting_family.py.
    jobs: list[tuple[str, Path, str, int, dict[str, Any]]] = []
    excluded_documents: list[dict[str, Any]] = []
    for doc_label, schedule in schedules.items():
        if "error" in schedule:
            excluded_documents.append({"doc_label": doc_label, "reason": schedule["error"]})
            continue
        usable_k = int(schedule.get("usable_k") or 0)
        if not usable_k:
            excluded_documents.append({
                "doc_label": doc_label,
                "reason": f"usable_k={usable_k} -- no usable interleaved target schedule",
            })
            continue
        docx_path = REAL_DOCUMENTS.get(doc_label)
        if docx_path is None:
            excluded_documents.append({
                "doc_label": doc_label, "reason": f"no corpus path registered for doc_label {doc_label!r}",
            })
            continue
        for i in range(usable_k):
            jobs.append((doc_label, docx_path, "ambiguous", i + 1, schedule["ambiguous_targets"][i]))
            jobs.append((doc_label, docx_path, "unique", i + 1, schedule["unique_targets"][i]))

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for doc_label, docx_path, condition, target_index, target in jobs:
            for arm in ("control", "treatment"):
                future = pool.submit(
                    run_comment_targeting_isolated_baseline,
                    doc_label, docx_path, arm, model, run_root, condition, target_index, target,
                    word_receipts_enabled=word_receipts_enabled,
                )
                futures[future] = (doc_label, condition, target_index, arm)
        for future in concurrent.futures.as_completed(futures):
            doc_label, condition, target_index, arm = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 -- one job's crash must not lose the others
                results.append({
                    "baseline_id": f"{doc_label}-baseline-{condition}{target_index}-comment_targeting-{arm}-EXCEPTION",
                    "doc_label": doc_label, "family": "comment_targeting", "arm": arm,
                    "condition": condition, "target_index": target_index,
                    "status": "harness_exception", "reason": f"{type(exc).__name__}: {exc}",
                    "step_grade": None, "round_trip_count": 0,
                })

    manifest = {
        "schema": "paper-s24-comment-targeting-baseline-sweep-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": model, "schedule_json": str(schedule_json_path),
        "chain_count": len(results),
        "excluded_documents": excluded_documents,
        "chains_summary": [
            {
                "baseline_id": r.get("baseline_id"), "doc_label": r.get("doc_label"), "arm": r.get("arm"),
                "condition": r.get("condition"), "target_index": r.get("target_index"),
                "status": r.get("status"),
                "step_pass": (r.get("step_grade") or {}).get("step_pass"),
            }
            for r in results
        ],
    }
    (run_root / "baseline-sweep-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--schedule-json", type=Path, default=_DEFAULT_SCHEDULE_JSON)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--word-receipts", action="store_true",
        help="Enable Word-COM milestone receipts (Windows only; off by default for RunPod/Linux runs).",
    )
    args = parser.parse_args(argv)

    manifest = run_baseline_sweep(
        args.run_root, args.model, args.schedule_json,
        max_workers=args.max_workers, word_receipts_enabled=args.word_receipts,
    )
    print(json.dumps({
        "chain_count": manifest["chain_count"],
        "excluded_document_count": len(manifest["excluded_documents"]),
        "status_counts": {
            status: sum(1 for c in manifest["chains_summary"] if c["status"] == status)
            for status in sorted({c["status"] for c in manifest["chains_summary"]})
        },
    }, indent=2))
    print(f"Full manifest: {args.run_root / 'baseline-sweep-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
