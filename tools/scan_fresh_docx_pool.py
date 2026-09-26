"""Structural + PII-pattern scan of the fresh (never-touched) docx-corpus pool
for the S25/S26 re-run document selection, mirroring
docs/paper-s7-section-reorder-followup-protocol-v1.md steps 1-2:
docx_anchor_prober.resolve_section_reorder_plan (the harness's own
applicability gate) and pii_pattern_scan.scan_document (post-2026-08-31 fix),
both unmodified.

    pixi run python tools/scan_fresh_docx_pool.py [--workers 12] [--limit N]

Inputs: manifests/docx_corpus_pool_index.json and manifests/touched_union.json
(fresh_indices). Output: manifests/fresh_pool_structure_pii_scan.json, one
record per fresh document sorted by docx-corpus id. The record keeps the
plan's section_id and heading_count but never heading text, and no timing,
so the output is content-free and deterministic for a fixed resolver build.
The resolvers import meridian_docs, so results depend on the installed
Meridian Docs build; record its commit alongside any re-run.
"""
from __future__ import annotations

import argparse
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rerun_selection_common import MANIFESTS_DIR, read_json, write_json  # noqa: E402

POOL_INDEX = MANIFESTS_DIR / "docx_corpus_pool_index.json"
TOUCHED_UNION = MANIFESTS_DIR / "touched_union.json"
SCAN_OUT = MANIFESTS_DIR / "fresh_pool_structure_pii_scan.json"
PLAN_FIELDS = ("section_id", "heading_count")  # no heading text in the manifest


def scan_one(item: dict) -> dict:
    from docx_anchor_prober import _import_docs_intel, resolve_section_reorder_plan
    from pii_pattern_scan import scan_document

    p = Path(item["path"])
    r = {"id": item["id"], "sha256": item["sha256"], "batch": item["batch"], "path": item["path"], "size": item["size"]}
    try:
        outline = _import_docs_intel().document_outline(str(p))
        r["outline_heading_count"] = len(outline.get("headings") or [])
        plan = resolve_section_reorder_plan(p)
        r["plan_found"] = bool(plan.get("found"))
        r["plan_reason"] = plan.get("reason")
        if plan.get("found"):
            r["plan"] = {k: plan[k] for k in PLAN_FIELDS}
    except Exception as exc:  # noqa: BLE001
        r["error"] = f"{type(exc).__name__}: {exc}"[:300]
    try:
        pii = scan_document(p)
        r["pii_clean"] = pii["clean"]
        r["pii_counts"] = {k: pii[k] for k in ("email_matches_real_domain", "phone_matches", "ssn_pattern_matches", "long_digit_run_matches")}
    except Exception as exc:  # noqa: BLE001
        r["pii_error"] = f"{type(exc).__name__}: {exc}"[:300]
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", type=Path, default=POOL_INDEX)
    ap.add_argument("--touched-union", type=Path, default=TOUCHED_UNION)
    ap.add_argument("--out", type=Path, default=SCAN_OUT)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=None, help="scan only the first N fresh documents (smoke test)")
    args = ap.parse_args(argv)

    pool = read_json(args.pool)
    items = [pool[i] for i in read_json(args.touched_union)["fresh_indices"]]
    if args.limit is not None:
        items = items[: args.limit]
    out = []
    with Pool(args.workers) as pp:
        for n, r in enumerate(pp.imap_unordered(scan_one, items, chunksize=4), 1):
            out.append(r)
            if n % 250 == 0:
                print(n, flush=True)
    out.sort(key=lambda r: r["id"])
    write_json(args.out, out, indent=0, ensure_ascii=False)
    print("done", len(out), "->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
