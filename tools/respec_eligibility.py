"""Respec-cascade eligibility for .docx files, using the repo's own resolvers
exactly as tools/run_respec_cascade_sweep.py uses them.

Five-family (protocol 2.3, what the locked run used): resolve_respec_schedule
unmodified; usable anchor-set count = entries with usable=True.

Six-family (protocol 2.2): same schedule, plus a FOURTH disjoint body-anchor pool
for the table step, resolved the same way resolve_respec_schedule resolves its
three pools (resolve_multiple_body_anchors, excluding every para_id already
claimed by citation/equation/caption). The table pool is resolved LAST so the
five-family anchors stay identical to what the locked resolver returns; an
anchor-set index is six-family usable iff it is five-family usable AND the table
pool has an entry at that index. Bibliography/equation/caption/table need no
further per-document applicability condition in the harness (bibliography is
document-global and creates a References heading if absent; equation, caption and
table insert after any eligible body paragraph).

Diagnostics that are NOT harness eligibility conditions (reported only):
- ambiguous_snippet: the control arm is told "the paragraph that starts with the
  exact text <anchor_text_snippet>" (80 chars); count anchors whose snippet is a
  prefix of more than one parse_docx paragraph.
- duplicate_heading_text: a section plan's chosen/preceding/D1/D2 heading text
  appears on more than one heading.

Usage (from the repo root):

    pixi run python tools/respec_eligibility.py paths <paths.json> <out.json>
        paths.json = [{"label":..., "path":..., ...extra passthrough fields}].
        Full per-anchor-set detail, INCLUDING section heading text: write it
        outside the repo (e.g. for author-owned documents), never to manifests/.
    pixi run python tools/respec_eligibility.py organic [--data-root D]
        The S6 organic-OMML adjudicated candidates -> manifests/organic_respec_eligibility.json
    pixi run python tools/respec_eligibility.py fresh [--workers 12]
        Every fresh, plan-found, PII-pattern-clean document of
        manifests/fresh_pool_structure_pii_scan.json (no heading band; respec has
        none) -> manifests/fresh_pool_respec_eligibility.json

The organic and fresh outputs are per-document summaries: no anchor_sets
(which carry heading text) and no timing, so they are content-free and
deterministic for a fixed Meridian Docs build.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import zipfile
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_anchor_prober import (  # noqa: E402
    _import_docs_intel,
    resolve_multiple_body_anchors,
    resolve_respec_schedule,
    resolve_section_reorder_plan,
)
from rerun_selection_common import DEFAULT_DATA_ROOT, MANIFESTS_DIR, file_sha256, read_json, write_json  # noqa: E402

POOL_INDEX = MANIFESTS_DIR / "docx_corpus_pool_index.json"
FRESH_SCAN = MANIFESTS_DIR / "fresh_pool_structure_pii_scan.json"
FRESH_OUT = MANIFESTS_DIR / "fresh_pool_respec_eligibility.json"
ORGANIC_OUT = MANIFESTS_DIR / "organic_respec_eligibility.json"
# Relative to <data-root>.
ORGANIC_ADJUDICATION = os.path.join("manifests", "s6-organic-candidates-adjudication-v1.json")
ORGANIC_COMBINED = os.path.join("manifests", "s6-combined-organic-omml-v1.json")
ORGANIC_LICENSE_STATUS = ("unknown_pending_review (per-file); dataset-level claim ODC-BY "
                          "(s6-organic-candidates-adjudication-v1.json summary.note)")
SUMMARY_DROP = ("anchor_sets", "seconds")


def _xml_counts(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    return {"omath": xml.count(b"<m:oMath>") + xml.count(b"<m:oMath "), "tbl": xml.count(b"<w:tbl>") + xml.count(b"<w:tbl ")}


def analyze(path: Path, max_anchor_sets: int = 4) -> dict:
    t0 = time.time()
    docs_intel = _import_docs_intel()
    paragraphs = docs_intel.parse_docx(str(path))
    outline = docs_intel.document_outline(str(path))
    headings = outline.get("headings") or []
    texts = [(p.get("text") or "").strip() for p in paragraphs]

    schedule = resolve_respec_schedule(path, max_anchor_sets=max_anchor_sets)

    citation = resolve_multiple_body_anchors(path, max_anchors=max_anchor_sets)
    claimed = {a["anchor_para_id"] for a in citation if a.get("found")}
    equation = resolve_multiple_body_anchors(path, max_anchors=max_anchor_sets, exclude_para_ids=claimed)
    claimed |= {a["anchor_para_id"] for a in equation if a.get("found")}
    caption = resolve_multiple_body_anchors(path, max_anchors=max_anchor_sets, exclude_para_ids=claimed)
    claimed |= {a["anchor_para_id"] for a in caption if a.get("found")}
    table = resolve_multiple_body_anchors(path, max_anchors=max_anchor_sets, exclude_para_ids=claimed)

    heading_text_counts: dict[str, int] = {}
    for h in headings:
        t = (h.get("text") or "").strip()
        heading_text_counts[t] = heading_text_counts.get(t, 0) + 1

    def _ambiguous(snippet: str) -> bool:
        return sum(1 for t in texts if t.startswith(snippet)) > 1

    entries = []
    for e in schedule:
        i = e["anchor_set_index"]
        six_usable = bool(e["usable"]) and i < len(table) and table[i].get("found", False)
        diag = {}
        if e["usable"]:
            anchors = [e["citation_anchor"], e["equation_anchor"], e["caption_anchor"]] + ([table[i]] if i < len(table) else [])
            diag["ambiguous_snippet_count"] = sum(1 for a in anchors if _ambiguous(a["anchor_text_snippet"]))
            plan = e["section_reorder_plan"]
            htexts = [plan.get("section_heading_text"), plan.get("original_preceding_heading_text"),
                      plan.get("destination_heading_text"), (plan.get("redirect") or {}).get("redirect_destination_heading_text")]
            diag["duplicate_heading_text_count"] = sum(1 for t in htexts if heading_text_counts.get((t or "").strip(), 0) > 1)
        entries.append({
            "anchor_set_index": i, "five_family_usable": bool(e["usable"]), "six_family_usable": six_usable,
            "reason": e["reason"] if not e["usable"] else (None if six_usable else "missing_table_anchor"),
            "section_id": (e.get("section_reorder_plan") or {}).get("section_id"),
            "section_heading_text": (e.get("section_reorder_plan") or {}).get("section_heading_text"),
            "redirect_found": ((e.get("section_reorder_plan") or {}).get("redirect") or {}).get("found"),
            **diag,
        })

    single = resolve_section_reorder_plan(path)
    return {
        "sha256": file_sha256(path),
        "size": path.stat().st_size,
        "paragraphs": len(paragraphs),
        "headings": len(headings),
        **_xml_counts(path),
        "pool_sizes": {"citation": len(citation), "equation": len(equation), "caption": len(caption), "table": len(table)},
        "attempted_anchor_sets": len(schedule),
        "five_family_usable": sum(1 for e in entries if e["five_family_usable"]),
        "six_family_usable": sum(1 for e in entries if e["six_family_usable"]),
        "anchor_sets": entries,
        "single_section_reorder_plan_found": bool(single.get("found")),
        "single_section_reorder_reason": single.get("reason"),
        "seconds": round(time.time() - t0, 1),
    }


def _summary(a: dict) -> dict:
    return {k: v for k, v in a.items() if k not in SUMMARY_DROP}


def cmd_paths(args: argparse.Namespace) -> int:
    items = read_json(args.paths)
    results = []
    for item in items:
        p = Path(item["path"])
        try:
            r = analyze(p)
        except Exception as exc:  # noqa: BLE001
            r = {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-1500:]}
        results.append({**item, **r})
        print(item["label"], r.get("headings"), r.get("five_family_usable"), r.get("six_family_usable"), r.get("error"), r.get("seconds"), flush=True)
        args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def organic_items(pool: list[dict], data_root: str) -> list[dict]:
    """The S6 organic-OMML adjudicated candidates, matched to the pool by id or
    sha256 prefix, in adjudication-manifest order."""
    adj = read_json(os.path.join(data_root, ORGANIC_ADJUDICATION))
    feat = {c["candidate_id"]: c for c in read_json(os.path.join(data_root, ORGANIC_COMBINED))["all_hits"]}
    items = []
    for c in adj["candidates"]:
        cid = c["candidate_id"]
        m = [d for d in pool if d["id"].startswith(cid) or d["sha256"].startswith(cid)]
        if len(m) != 1:
            raise SystemExit(f"organic candidate {cid} matches {len(m)} pool documents, expected 1")
        d = m[0]
        items.append({"label": "organic_" + cid, "path": d["path"], "candidate_id": cid, "docxcorpus_id": d["id"], "sha256": d["sha256"],
                      "matched_on": ("id" if d["id"].startswith(cid) else "sha256"), "batch": d["batch"],
                      "topic": c.get("topic"), "type": c.get("type"), "pii_scan": c.get("pii_scan"), "adjudication": c.get("adjudication"),
                      "cleared": c.get("adjudication", "").startswith("cleared"), "omml_containers": feat.get(cid, {}).get("containers"),
                      "license_status": ORGANIC_LICENSE_STATUS})
    return items


def cmd_organic(args: argparse.Namespace) -> int:
    items = organic_items(read_json(args.pool), args.data_root)
    out = []
    for item in items:
        try:
            a = _summary(analyze(Path(item["path"])))
        except Exception as exc:  # noqa: BLE001
            a = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        out.append({**item, **a})
        print(item["label"], a.get("headings"), a.get("five_family_usable"), a.get("six_family_usable"), a.get("error"), flush=True)
    write_json(args.out, out, indent=1, ensure_ascii=False)
    print(len(out), "organic candidates,", sum(i["cleared"] for i in out), "cleared ->", args.out)
    return 0


def _fresh_work(r: dict) -> dict:
    try:
        a = _summary(analyze(Path(r["path"])))
    except Exception as exc:  # noqa: BLE001
        a = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return {"id": r["id"], "sha256": r["sha256"], "batch": r["batch"], "path": r["path"], **a}


def cmd_fresh(args: argparse.Namespace) -> int:
    items = [r for r in read_json(args.scan) if r.get("plan_found") and r.get("pii_clean")]
    with Pool(args.workers) as pp:
        out = list(pp.imap_unordered(_fresh_work, items, chunksize=4))
    out.sort(key=lambda r: r["id"])
    write_json(args.out, out, indent=0, ensure_ascii=False)
    print("done", len(out), "->", args.out)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("paths", help="full detail for an explicit list of documents (includes heading text)")
    p.add_argument("paths", type=Path)
    p.add_argument("out", type=Path)
    p.set_defaults(func=cmd_paths)

    p = sub.add_parser("organic", help="S6 organic-OMML adjudicated candidates (summary)")
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--pool", type=Path, default=POOL_INDEX)
    p.add_argument("--out", type=Path, default=ORGANIC_OUT)
    p.set_defaults(func=cmd_organic)

    p = sub.add_parser("fresh", help="fresh plan-found PII-clean pool documents (summary)")
    p.add_argument("--scan", type=Path, default=FRESH_SCAN)
    p.add_argument("--out", type=Path, default=FRESH_OUT)
    p.add_argument("--workers", type=int, default=12)
    p.set_defaults(func=cmd_fresh)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
