"""PAPER-S23: primary-run sweep driver for the respec_cascade task family
(docs/paper-s23-respec-cascade-protocol-v0.md, locked, five-family
contingency). Resolves anchor-sets for all 3 real author-owned documents
(protocol section 1.1), then runs one run_respec_cascade_chain per
(document, anchor_set_index, arm) via ThreadPoolExecutor -- mirrors
tools/run_paper_s7_benchmark.py::run_corpus_slice's own concurrency pattern
exactly (same primitive, same as-completed collection, same
harness_exception degrade-on-raise), generalized from that function's
(family, k) job grid to this family's (document, anchor_set_index) grid.

doc_label uses the f"{original_doc_label}__anchor{i}" convention
tools/compute_respec_cascade_statistics.py's loaders already document and
expect (see that module's SCHEMA section) -- this is the load-bearing
integration contract for section 7's paired comparison.

Every anchor-set resolved -- usable or not -- is recorded (never silently
dropped), per protocol section 6's N-disclosure discipline.

Usage:
    python run_respec_cascade_sweep.py --run-root <dir> --model haiku [--max-anchor-sets 4] [--max-workers 4]
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
from docx_anchor_prober import resolve_respec_schedule  # noqa: E402
from run_respec_cascade_family import run_respec_cascade_chain  # noqa: E402

# The three real author-owned documents (docs/paper-s23-respec-cascade-protocol-v0.md
# section 1.1, hash-pinned 2026-09-20 in raw/author-owned-personal/PROVENANCE.md).
REAL_DOCUMENTS: dict[str, Path] = {
    "jcshm-manuscript": Path(r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\jcshm-manuscript.docx"),
    "jcshm-si": Path(r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\jcshm-si.docx"),
    "masters-dissertation-defense": Path(r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\masters-dissertation-defense.docx"),
}


def resolve_all_schedules(max_anchor_sets: int = 4) -> dict[str, list[dict[str, Any]]]:
    """One resolve_respec_schedule call per real document. Returned dict is
    also the single source of truth the baseline sweep (run_respec_cascade_
    baselines.py) re-derives its own per-family anchor overrides from --
    both sweeps must see the IDENTICAL frozen anchor-sets, per protocol
    section 2.1's "literal targets are frozen, not re-derived per trial."""
    return {label: resolve_respec_schedule(path, max_anchor_sets=max_anchor_sets) for label, path in REAL_DOCUMENTS.items()}


def run_primary_sweep(
    run_root: Path, model: str, *, max_anchor_sets: int = 4, max_workers: int = 4,
    word_receipts_enabled: bool = False,
) -> dict[str, Any]:
    run_root.mkdir(parents=True, exist_ok=True)
    schedules = resolve_all_schedules(max_anchor_sets)
    (run_root / "anchor-schedules.json").write_text(
        json.dumps(schedules, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    jobs: list[tuple[str, dict[str, Any]]] = []
    excluded: list[dict[str, Any]] = []
    for doc_label, schedule in schedules.items():
        for entry in schedule:
            if not entry["usable"]:
                excluded.append({
                    "doc_label": doc_label, "anchor_set_index": entry["anchor_set_index"],
                    "reason": entry["reason"],
                })
                continue
            jobs.append((doc_label, entry))

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for doc_label, entry in jobs:
            scoped_label = f"{doc_label}__anchor{entry['anchor_set_index']}"
            for arm in ("control", "treatment"):
                future = pool.submit(
                    run_respec_cascade_chain,
                    scoped_label, REAL_DOCUMENTS[doc_label], arm, model, run_root, entry,
                    word_receipts_enabled=word_receipts_enabled,
                )
                futures[future] = (scoped_label, arm)
        for future in concurrent.futures.as_completed(futures):
            scoped_label, arm = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 -- one job's crash must not lose the others
                results.append({
                    "chain_id": f"{scoped_label}-respec_cascade-{arm}-EXCEPTION",
                    "doc_label": scoped_label, "family": "respec_cascade", "arm": arm,
                    "status": "harness_exception", "reason": f"{type(exc).__name__}: {exc}",
                    "phase1_result": None, "phase2_result": None, "phase3_result": None,
                })

    manifest = {
        "schema": "paper-s23-respec-cascade-primary-sweep-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": model, "max_anchor_sets": max_anchor_sets,
        "chain_count": len(results),
        "excluded_anchor_sets": excluded,
        "chains_summary": [
            {"chain_id": r.get("chain_id"), "doc_label": r.get("doc_label"), "arm": r.get("arm"), "status": r.get("status")}
            for r in results
        ],
    }
    (run_root / "sweep-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-anchor-sets", type=int, default=4)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--word-receipts", action="store_true", help="Enable Word-COM milestone receipts (Windows only; off by default for RunPod/Linux runs).")
    args = parser.parse_args(argv)

    manifest = run_primary_sweep(
        args.run_root, args.model, max_anchor_sets=args.max_anchor_sets,
        max_workers=args.max_workers, word_receipts_enabled=args.word_receipts,
    )
    print(json.dumps({
        "chain_count": manifest["chain_count"],
        "excluded_anchor_set_count": len(manifest["excluded_anchor_sets"]),
        "status_counts": {
            status: sum(1 for c in manifest["chains_summary"] if c["status"] == status)
            for status in sorted({c["status"] for c in manifest["chains_summary"]})
        },
    }, indent=2))
    print(f"Full manifest: {args.run_root / 'sweep-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
