"""PAPER-S24: primary-run sweep driver for the comment_targeting task family
(docs/paper-s24-targeted-comment-protocol-v0.md), analogous to
tools/run_respec_cascade_sweep.py -- read directly before writing this, per
this build's own discipline requirement; it is short and a direct structural
template, reused here rather than built from scratch.

Drives `run_comment_targeting_family.run_comment_targeting_chain` across all
three real documents (protocol section 1.1) and both arms via
`ThreadPoolExecutor` -- mirrors `run_respec_cascade_sweep.py::run_primary_
sweep`'s own concurrency pattern exactly (same primitive, same
as-completed collection, same `harness_exception` degrade-on-raise).

Reads the ALREADY-frozen, hash-pinned per-document schedules (protocol
section 2.2 item 4 / section 1.2b's own addendum:
`D:\\MeridianData\\ooxml-graph-paper\\runs\\paper-s24\\comment-targeting-schedule-v1.json`,
produced once by `tools/freeze_comment_targeting_schedule.py`) -- NEVER
re-resolves `resolve_comment_targeting_clusters` live per sweep run, exactly
the "literal targets are frozen, not re-derived per trial" discipline
`run_respec_cascade_sweep.py`'s own docstring states for its own anchor-sets.

Every document is recorded -- usable or not -- per this project's standing
N-disclosure rule (protocol section 6); a document whose `usable_k` is 0 (or
whose schedule entry carries an `"error"` key, e.g. a missing corpus file)
is excluded from the job grid but still listed in the manifest's own
`excluded_documents`, never silently dropped.

Deliberately does NOT also drive protocol section 3's isolated single-step
baseline trials across every target -- `run_comment_targeting_family.py`'s
own `run_comment_targeting_isolated_baseline` (plus its `--baseline` CLI
flag) is exactly that machinery, ready for a caller to invoke, but sweeping
it across every (document, target, arm) combination is left to a dedicated
baseline-sweep driver, matching `respec_cascade`'s own precedent exactly:
that family's baseline sweep lives in a SEPARATE script
(`tools/run_respec_cascade_baselines.py`), not inside `run_respec_cascade_
sweep.py` itself, and this build's own task list (protocol section 5 items
2-7) names only `run_comment_targeting_sweep.py` for the chain sweep, not a
second baseline-sweep script.

Usage:
    python run_comment_targeting_sweep.py --run-root <dir> --model haiku \\
        [--schedule-json D:/MeridianData/ooxml-graph-paper/runs/paper-s24/comment-targeting-schedule-v1.json]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_comment_targeting_family import run_comment_targeting_chain  # noqa: E402

# The three real author-owned documents (docs/paper-s24-targeted-comment-protocol-v0.md
# section 1.1, the SAME hash-pinned files respec_cascade/multi-anchor already
# use, per raw/author-owned-personal/PROVENANCE.md). Base directory
# overridable via COMMENT_TARGETING_CORPUS_DIR, mirroring
# run_respec_cascade_sweep.py's own RESPEC_CASCADE_CORPUS_DIR precedent
# (needed on a non-Windows host, e.g. a Linux RunPod pod, where the local
# Windows raw/author-owned-personal path does not exist).
_CORPUS_DIR = Path(os.environ.get(
    "COMMENT_TARGETING_CORPUS_DIR",
    r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal",
))
REAL_DOCUMENTS: dict[str, Path] = {
    "jcshm-manuscript": _CORPUS_DIR / "jcshm-manuscript.docx",
    "jcshm-si": _CORPUS_DIR / "jcshm-si.docx",
    "masters-dissertation-defense": _CORPUS_DIR / "masters-dissertation-defense.docx",
}

_DEFAULT_SCHEDULE_JSON = Path(
    r"D:\MeridianData\ooxml-graph-paper\runs\paper-s24\comment-targeting-schedule-v1.json"
)


def load_frozen_schedules(schedule_json_path: Path) -> dict[str, dict[str, Any]]:
    """Reads `tools/freeze_comment_targeting_schedule.py`'s own hash-pinned
    output -- `{"schema": ..., "documents": {doc_label: <resolve_comment_
    targeting_clusters output, plus source_sha256>, ...}}` -- and returns
    just the inner `"documents"` dict, one entry per real corpus document."""
    payload = json.loads(schedule_json_path.read_text(encoding="utf-8"))
    return payload.get("documents", {})


def _per_position_summary(chain_results: list[dict[str, Any]]) -> dict[str, Any]:
    """A quick, lightweight sanity readout -- NOT this family's real
    statistics (protocol section 5 item 7's own Tier1/2/3/ICC-corrected
    machinery lives in the statistics module, not here): per (arm,
    condition, chain_position), the raw pass/total count across every chain
    this sweep just ran, pooled across all three documents with no
    weighting, ICC correction, or significance testing at all. Exists so a
    sweep run's own console/manifest output gives an immediate, honest
    "did this look reasonable" signal without waiting on a separate
    statistics pass."""
    counts: dict[tuple[str, str, int], dict[str, int]] = {}
    for chain in chain_results:
        arm = chain.get("arm")
        chain_grade = chain.get("chain_grade")
        if not chain_grade:
            continue
        for position in chain_grade.get("per_position", []):
            key = (arm, position["condition"], position["chain_position"])
            bucket = counts.setdefault(key, {"pass": 0, "total": 0})
            bucket["total"] += 1
            if position["step_pass"]:
                bucket["pass"] += 1
    return {
        f"{arm}|{condition}|position{position}": {
            **bucket, "pass_rate": (bucket["pass"] / bucket["total"]) if bucket["total"] else None,
        }
        for (arm, condition, position), bucket in sorted(counts.items())
    }


def run_primary_sweep(
    run_root: Path, model: str, schedule_json_path: Path = _DEFAULT_SCHEDULE_JSON,
    *, max_workers: int = 4, word_receipts_enabled: bool = False,
) -> dict[str, Any]:
    run_root.mkdir(parents=True, exist_ok=True)
    schedules = load_frozen_schedules(schedule_json_path)
    (run_root / "target-schedules.json").write_text(
        json.dumps(schedules, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    jobs: list[str] = []
    excluded_documents: list[dict[str, Any]] = []
    for doc_label, schedule in schedules.items():
        if "error" in schedule:
            excluded_documents.append({"doc_label": doc_label, "reason": schedule["error"]})
            continue
        if not schedule.get("usable_k"):
            excluded_documents.append({
                "doc_label": doc_label,
                "reason": f"usable_k={schedule.get('usable_k')} -- no usable interleaved target schedule",
            })
            continue
        if doc_label not in REAL_DOCUMENTS:
            excluded_documents.append({
                "doc_label": doc_label, "reason": f"no corpus path registered for doc_label {doc_label!r}",
            })
            continue
        jobs.append(doc_label)

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for doc_label in jobs:
            for arm in ("control", "treatment"):
                future = pool.submit(
                    run_comment_targeting_chain,
                    doc_label, REAL_DOCUMENTS[doc_label], arm, model, run_root, schedules[doc_label],
                    word_receipts_enabled=word_receipts_enabled,
                )
                futures[future] = (doc_label, arm)
        for future in concurrent.futures.as_completed(futures):
            doc_label, arm = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 -- one job's crash must not lose the others
                results.append({
                    "chain_id": f"{doc_label}-comment_targeting-{arm}-EXCEPTION",
                    "doc_label": doc_label, "family": "comment_targeting", "arm": arm,
                    "status": "harness_exception", "reason": f"{type(exc).__name__}: {exc}",
                    "chain_grade": None, "steps_run": 0, "round_trip_count": 0,
                })

    manifest = {
        "schema": "paper-s24-comment-targeting-primary-sweep-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": model, "schedule_json": str(schedule_json_path),
        "chain_count": len(results),
        "excluded_documents": excluded_documents,
        "chains_summary": [
            {
                "chain_id": r.get("chain_id"), "doc_label": r.get("doc_label"), "arm": r.get("arm"),
                "status": r.get("status"), "steps_run": r.get("steps_run"),
                "round_trip_count": r.get("round_trip_count"),
                "chain_pass": (r.get("chain_grade") or {}).get("chain_pass"),
            }
            for r in results
        ],
        "per_position_summary": _per_position_summary(results),
    }
    (run_root / "sweep-manifest.json").write_text(
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

    manifest = run_primary_sweep(
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
    print(f"Full manifest: {args.run_root / 'sweep-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
