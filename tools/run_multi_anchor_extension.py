"""PAPER-S7 follow-up: multi-anchor-per-document extension.

Grows N for the body-anchor families (equation, caption, table_structural,
citation) and section_reorder using two sources, neither requiring new
corpus acquisition or licensing review:

1. Extra anchors/plans from documents ALREADY in the confirmatory corpus,
   via docx_anchor_prober.resolve_multiple_body_anchors /
   resolve_multiple_section_reorder_plans -- these functions were built
   specifically so their first returned anchor/plan is identical to what
   the single-anchor corpus run already used (see their docstrings), so
   this script always skips index 0 for already-run documents and only
   adds anchors[1:]/plans[1:] as genuinely new trial points.
2. Full anchor/plan discovery (including index 0) against three new,
   author-owned documents never previously used in this benchmark --
   see D:\\MeridianData\\ooxml-graph-paper\\raw\\author-owned-personal\\PROVENANCE.md
   for their rights/provenance/overlap disclosure.

Reuses run_chain from run_paper_s7_benchmark.py completely unmodified in
its own trial/grading/checkpoint logic -- only passes it an
anchor_or_plan_override and a doc_label suffixed per-anchor so each extra
anchor is tracked (and paired control-vs-treatment) as its own
independent trial point, never conflated with the document's original
single-anchor trial.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_anchor_prober import (  # noqa: E402
    resolve_multiple_body_anchors,
    resolve_multiple_section_reorder_plans,
)
from run_paper_s7_benchmark import run_chain  # noqa: E402

_BODY_ANCHOR_FAMILIES = ("citation", "caption", "equation", "table_structural")

_PERSONAL_DOCS = [
    {
        "doc_label": "author_owned__jcshm_manuscript",
        "docx_path": r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\jcshm-manuscript.docx",
    },
    {
        "doc_label": "author_owned__jcshm_si",
        "docx_path": r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\jcshm-si.docx",
    },
    {
        "doc_label": "author_owned__masters_dissertation",
        "docx_path": r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\masters-dissertation-defense.docx",
    },
]


def _existing_corpus_documents(corpus_manifest_path: Path, split: str) -> list[dict[str, Any]]:
    manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    return [d for d in manifest["documents"] if d["s7_split"] == split]


def _short_unique_doc_label(original_doc_label: str, anchor_index: int) -> str:
    """run_chain (run_paper_s7_benchmark.py) truncates doc_label to its first
    32 characters to build chain_id/chain_root (a real, deliberate Windows
    MAX_PATH guard on the original single-anchor corpus, where that first-32
    prefix already happened to be unique per document). A naive
    f"{original_doc_label}__anchor{i}" suffix defeats that: for any
    original_doc_label longer than ~22 characters the anchor-distinguishing
    suffix falls entirely outside the 32-char window truncation keeps, so
    every anchor of the same document collides onto the identical chain_id
    -- confirmed live, 2026-09-19: 372 expected chains collapsed to 146
    actual directories on a real remote run, because _load_checkpoint then
    silently returned anchor 0's already-completed result for every later
    anchor's supposedly-independent trial, rather than running them.

    Fixed by putting the uniqueness-bearing parts FIRST and keeping the
    whole label <=32 chars outright, so run_chain's truncation becomes a
    no-op: a short human-readable prefix (<=12 chars) + an 8-hex-char
    sha256 of the FULL original label (collision probability negligible at
    this trial-count scale) + the anchor index. Callers must keep their own
    mapping from this synthetic label back to the real document identity
    (see plan_extra_trials's returned "original_doc_label" field) since the
    synthetic label alone is not human-identifiable."""
    prefix = original_doc_label[:12]
    digest = hashlib.sha256(original_doc_label.encode("utf-8")).hexdigest()[:8]
    label = f"{prefix}_{digest}_a{anchor_index}"
    assert len(label) <= 32, f"synthetic doc_label still too long: {label!r} ({len(label)} chars)"
    return label


def plan_extra_trials(
    family: str,
    *,
    corpus_manifest_path: Path | None,
    splits: tuple[str, ...],
    include_existing_corpus: bool,
    include_personal_docs: bool,
    max_extra_per_doc: int,
) -> list[dict[str, Any]]:
    """Returns a list of {doc_label, docx_path, anchor_or_plan_override,
    source} dicts -- one per NEW trial point this extension would add,
    without running anything. Always excludes index 0 for
    include_existing_corpus documents (already covered by the standard
    corpus run); always includes index 0 for personal docs (never
    previously run)."""
    jobs: list[dict[str, Any]] = []

    def _resolve_all(docx_path: Path) -> list[dict[str, Any]]:
        if family == "section_reorder":
            return resolve_multiple_section_reorder_plans(docx_path, max_plans=max_extra_per_doc + 1)
        if family in _BODY_ANCHOR_FAMILIES:
            return resolve_multiple_body_anchors(docx_path, max_anchors=max_extra_per_doc + 1)
        raise ValueError(f"family {family!r} has no anchor/plan concept (bibliography needs none)")

    if include_existing_corpus:
        assert corpus_manifest_path is not None
        for split in splits:
            for doc in _existing_corpus_documents(corpus_manifest_path, split):
                docx_path = Path(doc["docx_path"])
                if not docx_path.is_file():
                    continue
                resolved = _resolve_all(docx_path)
                for i, item in enumerate(resolved[1:], start=1):  # skip index 0: already run
                    jobs.append({
                        "doc_label": _short_unique_doc_label(doc["doc_label"], i),
                        "original_doc_label": doc["doc_label"],
                        "anchor_index": i,
                        "docx_path": str(docx_path),
                        "anchor_or_plan_override": item,
                        "source": f"existing_corpus:{split}",
                    })

    if include_personal_docs:
        for doc in _PERSONAL_DOCS:
            docx_path = Path(doc["docx_path"])
            if not docx_path.is_file():
                continue
            resolved = _resolve_all(docx_path)
            for i, item in enumerate(resolved):  # include index 0: never run before
                jobs.append({
                    "doc_label": _short_unique_doc_label(doc["doc_label"], i),
                    "original_doc_label": doc["doc_label"],
                    "anchor_index": i,
                    "docx_path": str(docx_path),
                    "anchor_or_plan_override": item,
                    "source": "author_owned_personal",
                })

    return jobs


def run_extra_trials(
    family: str, jobs: list[dict[str, Any]], *, arms: tuple[str, ...], model: str, run_root: Path,
    word_receipts_enabled: bool = True, max_workers: int = 4,
) -> list[dict[str, Any]]:
    run_root.mkdir(parents=True, exist_ok=True)

    # Hard pre-flight check: every job's doc_label must be unique, and must
    # SURVIVE run_chain's own doc_label[:32] truncation unique -- this is
    # the exact invariant _short_unique_doc_label exists to guarantee.
    # Checked here too (not just trusted from the caller) so any future
    # regression fails loudly before spending real trial cost, instead of
    # silently collapsing chains the way the 2026-09-19 bug did.
    seen_labels = [job["doc_label"] for job in jobs]
    seen_truncated = [label[:32] for label in seen_labels]
    if len(set(seen_truncated)) != len(seen_truncated):
        dupes = {l for l in seen_truncated if seen_truncated.count(l) > 1}
        raise AssertionError(
            f"doc_label collision after run_chain's 32-char truncation: {dupes} -- "
            f"refusing to run, this would silently duplicate/skip chains."
        )

    # Persist the synthetic-label -> real-document mapping so results remain
    # attributable after the fact (chain-result.json itself only stores the
    # short synthetic doc_label, not the original document identity).
    mapping = [
        {"doc_label": job["doc_label"], "original_doc_label": job.get("original_doc_label"),
         "anchor_index": job.get("anchor_index"), "source": job["source"], "docx_path": job["docx_path"]}
        for job in jobs
    ]
    (run_root / "doc_label_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                run_chain, family, job["doc_label"], Path(job["docx_path"]), arm, 1, model, run_root,
                word_receipts_enabled=word_receipts_enabled,
                anchor_or_plan_override=job["anchor_or_plan_override"],
            ): job
            for job in jobs
            for arm in arms
        }
        done = 0
        for future in concurrent.futures.as_completed(futures):
            job = futures[future]
            done += 1
            try:
                result = future.result()
                result["_source"] = job["source"]
                results.append(result)
                print(f"  [{done}/{len(futures)}] {job['doc_label']} -> status={result.get('status')}", flush=True)
            except Exception as exc:  # noqa: BLE001 -- one chain's crash must not abort the whole batch
                print(f"  [{done}/{len(futures)}] {job['doc_label']} -> EXCEPTION {type(exc).__name__}: {exc}", flush=True)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True, choices=list(_BODY_ANCHOR_FAMILIES) + ["section_reorder"])
    parser.add_argument("--corpus-manifest", type=Path, default=Path(r"D:\MeridianData\ooxml-graph-paper\manifests\paper-s7-corpus-manifest-v1.json"))
    parser.add_argument("--splits", nargs="+", default=["validation", "primary_holdout"])
    parser.add_argument("--include-existing-corpus", action="store_true")
    parser.add_argument("--include-personal-docs", action="store_true")
    parser.add_argument("--max-extra-per-doc", type=int, default=3)
    parser.add_argument("--plan-only", action="store_true", help="print the job list and exit, run nothing")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--arms", nargs="+", default=["control", "treatment"])
    parser.add_argument("--run-root", type=Path, required=False)
    parser.add_argument("--no-word-receipts", action="store_true")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args(argv)

    jobs = plan_extra_trials(
        args.family,
        corpus_manifest_path=args.corpus_manifest,
        splits=tuple(args.splits),
        include_existing_corpus=args.include_existing_corpus,
        include_personal_docs=args.include_personal_docs,
        max_extra_per_doc=args.max_extra_per_doc,
    )
    print(f"{len(jobs)} new trial point(s) planned for family={args.family} "
          f"({len(jobs) * len(args.arms)} chains across {args.arms}):")
    by_source: dict[str, int] = {}
    for j in jobs:
        by_source[j["source"]] = by_source.get(j["source"], 0) + 1
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")

    if args.plan_only:
        return 0

    if not args.run_root:
        print("ERROR: --run-root required when not --plan-only", file=sys.stderr)
        return 2

    results = run_extra_trials(
        args.family, jobs, arms=tuple(args.arms), model=args.model, run_root=args.run_root,
        word_receipts_enabled=not args.no_word_receipts, max_workers=args.max_workers,
    )
    passed = sum(1 for r in results if r.get("status") == "completed" and r.get("cumulative_fidelity_after_k_cycles"))
    print(f"\n{passed}/{len(results)} chains completed with cumulative fidelity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
