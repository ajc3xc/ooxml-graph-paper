"""PAPER-S23: fresh, contemporaneous isolated K=1 baseline sweep (protocol
section 3), resolving the section-reorder historical-baseline provenance
problem for THIS family by never depending on any other run's historical
numbers.

Per protocol section 3: "run one fresh, isolated K=1 forward+inverse trial
at the identical anchor used in this chain's Phase 1/3, against a fresh
copy of the same pristine document snapshot, on the same day and host as
the cascade chain -- reusing tools/run_paper_s7_benchmark.py::run_chain
completely unmodified, K=1."

This script does exactly that: for every (document, usable anchor-set,
family in the five-family contingency, arm), calls run_chain(...,
k_pairs=1, anchor_or_plan_override=<that anchor-set's own resolved anchor/
plan>) UNMODIFIED -- no new grading logic, no reimplementation. Anchor-sets
are read from the SAME anchor-schedules.json run_respec_cascade_sweep.py
already wrote (or re-resolved identically if absent), so both sweeps see
the identical frozen anchors per protocol section 2.1.

Output layout matches tools/compute_respec_cascade_statistics.py::
load_baseline_chains's own documented convention exactly:
    --baseline-run-root/<family>/<chain_dir>/chain-result.json
doc_label uses the SAME f"{original_doc_label}__anchor{i}" convention the
cascade sweep uses, so the two datasets join correctly on doc_label.

Usage:
    python run_respec_cascade_baselines.py --run-root <cascade-run-root> --baseline-run-root <dir> --model haiku
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
from run_respec_cascade_sweep import REAL_DOCUMENTS, resolve_all_schedules  # noqa: E402
from run_paper_s7_benchmark import run_chain  # noqa: E402

# The five-family contingency rotation (protocol section 2.3 / 1.2a item 2).
# table_structural is never part of respec_cascade.
FAMILIES: tuple[str, ...] = ("bibliography", "citation", "section_reorder", "equation", "caption")


def _anchor_override_for_family(family: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Maps one resolve_respec_schedule anchor-set entry to the exact
    anchor_or_plan_override shape run_paper_s7_benchmark.probe_family_
    applicability expects per family (verified directly against that
    function's own real branches, 2026-09-22): a single anchor dict for
    citation/caption/equation (the exact shape resolve_multiple_body_
    anchors's own list elements already are), the plan dict (with its
    extra "redirect" key, harmless -- consumed by explicit key access, not
    schema-validated) for section_reorder, and None for bibliography
    (probe_family_applicability's bibliography branch never reads the
    override at all -- it has no anchor concept, being document-global)."""
    if family == "bibliography":
        return None
    if family == "citation":
        return entry["citation_anchor"]
    if family == "caption":
        return entry["caption_anchor"]
    if family == "equation":
        return entry["equation_anchor"]
    if family == "section_reorder":
        return entry["section_reorder_plan"]
    raise ValueError(f"unknown respec_cascade baseline family: {family!r}")


def run_baseline_sweep(
    cascade_run_root: Path, baseline_run_root: Path, model: str, *,
    max_anchor_sets: int = 4, max_workers: int = 4, word_receipts_enabled: bool = False,
) -> dict[str, Any]:
    schedule_path = cascade_run_root / "anchor-schedules.json"
    if schedule_path.is_file():
        schedules: dict[str, list[dict[str, Any]]] = json.loads(schedule_path.read_text(encoding="utf-8"))
    else:
        # Cascade sweep hasn't run yet in this run_root -- resolve fresh.
        # Still the IDENTICAL deterministic resolver, so the anchors match
        # regardless of which sweep runs first.
        schedules = resolve_all_schedules(max_anchor_sets)

    baseline_run_root.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[str, dict[str, Any], str]] = []
    excluded: list[dict[str, Any]] = []
    for doc_label, schedule in schedules.items():
        for entry in schedule:
            if not entry["usable"]:
                excluded.append({
                    "doc_label": doc_label, "anchor_set_index": entry["anchor_set_index"],
                    "reason": entry["reason"],
                })
                continue
            for family in FAMILIES:
                jobs.append((doc_label, entry, family))

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for doc_label, entry, family in jobs:
            scoped_label = f"{doc_label}__anchor{entry['anchor_set_index']}"
            family_run_root = baseline_run_root / family
            override = _anchor_override_for_family(family, entry)
            for arm in ("control", "treatment"):
                future = pool.submit(
                    run_chain, family, scoped_label, REAL_DOCUMENTS[doc_label], arm, 1, model, family_run_root,
                    word_receipts_enabled=word_receipts_enabled, anchor_or_plan_override=override,
                )
                futures[future] = (family, scoped_label, arm)
        for future in concurrent.futures.as_completed(futures):
            family, scoped_label, arm = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                results.append({
                    "chain_id": f"{scoped_label}-{family}-{arm}-k1-EXCEPTION",
                    "doc_label": scoped_label, "family": family, "arm": arm, "k_pairs": 1,
                    "status": "harness_exception", "reason": f"{type(exc).__name__}: {exc}",
                    "pairs": [],
                })

    manifest = {
        "schema": "paper-s23-respec-cascade-baseline-sweep-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": model, "families": list(FAMILIES),
        "chain_count": len(results),
        "excluded_anchor_sets": excluded,
        "chains_summary": [
            {"chain_id": r.get("chain_id"), "doc_label": r.get("doc_label"), "family": r.get("family"), "arm": r.get("arm"), "status": r.get("status")}
            for r in results
        ],
    }
    (baseline_run_root / "baseline-sweep-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", type=Path, required=True, help="The respec_cascade sweep's own run-root (read anchor-schedules.json from here if present).")
    parser.add_argument("--baseline-run-root", type=Path, required=True)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-anchor-sets", type=int, default=4)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--word-receipts", action="store_true")
    args = parser.parse_args(argv)

    manifest = run_baseline_sweep(
        args.run_root, args.baseline_run_root, args.model, max_anchor_sets=args.max_anchor_sets,
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
    print(f"Full manifest: {args.baseline_run_root / 'baseline-sweep-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
