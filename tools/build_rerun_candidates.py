"""Build the two candidate pools for the S25 respec_cascade re-run and the S26
K=4 section-reorder replication (stdlib only; no document is opened).

    python tools/build_rerun_candidates.py k4sr   [--generated-at ISO] [--data-root D] [--meridian-repo R]
    python tools/build_rerun_candidates.py respec [--data-root D]

k4sr -> manifests/k4sr_candidates.json: every fresh document of
  manifests/fresh_pool_structure_pii_scan.json with a section-reorder plan, a
  clean PII pattern scan and 3-25 plan headings, sorted by file sha256, with
  its rank under the proposed seed. --generated-at is recorded verbatim (omit
  it to leave the field out); the saved manifest used 2026-09-25T19:19:11+00:00.

respec -> manifests/respec_public_candidates.json: (a) the cleared S6
  organic-OMML candidates with >=1 five-family anchor-set, in adjudication
  order, then (b) the fresh plan-found PII-clean documents with >25 outline
  headings (outside the K=4 band, so disjoint from k4sr by construction) and
  >=1 five-family anchor-set, in docx-corpus id order.

Both read <data-root>/raw/docx-corpus/filtered_candidates.json for the
docx-corpus metadata (url, type, topic, language, word_count).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rerun_selection_common import (  # noqa: E402
    DEFAULT_DATA_ROOT,
    DEFAULT_MERIDIAN_REPO,
    MANIFESTS_DIR,
    PAPER_ROOT,
    rank_key,
    read_json,
    write_json,
)

POOL_INDEX = MANIFESTS_DIR / "docx_corpus_pool_index.json"
TOUCHED_UNION = MANIFESTS_DIR / "touched_union.json"
FRESH_SCAN = MANIFESTS_DIR / "fresh_pool_structure_pii_scan.json"
FRESH_RESPEC = MANIFESTS_DIR / "fresh_pool_respec_eligibility.json"
ORGANIC_RESPEC = MANIFESTS_DIR / "organic_respec_eligibility.json"
K4SR_OUT = MANIFESTS_DIR / "k4sr_candidates.json"
RESPEC_OUT = MANIFESTS_DIR / "respec_public_candidates.json"
CORPUS_METADATA = os.path.join("raw", "docx-corpus", "filtered_candidates.json")  # relative to <data-root>

PROPOSED_K4SR_SEED = 20260925001  # placeholder; the S26 preregistration locks the real seed
K4SR_BAND = (3, 25)
# Measured once over ALL 6,433 batch documents (fresh + touched) with the same
# resolver and scanner as scan_fresh_docx_pool.py; it reproduces the follow-up
# protocol's own counts, which is the evidence that the resolver is unchanged.
REPRODUCTION_CHECK_ALL_BATCH_DOCS = {">=3_outline_headings": 1310, ">=3_headings_and_pii_clean": 883,
                                     "note": "matches docs/paper-s7-section-reorder-followup-protocol-v1.md (e813cd7) 1310 / 883 exactly"}
EXCLUSION_METHOD = (
    "Every text file (.json/.jsonl/.md/.txt/.csv/.tsv/.py/.log/.yaml/.html/.tex/.xml) and every file/dir NAME under "
    "D:/MeridianData/ooxml-graph-paper (except the raw DocBank/ReadingBank/model-cache trees and the docx files themselves) "
    "and under the ooxml-graph-paper repo working tree was scanned for hex runs of 12-64 chars; a pool document is 'touched' "
    "if any run equals a >=12-char prefix of its docx-corpus id OR of its file sha256. Seven pool-wide acquisition/screening "
    "listings that enumerate whole batches were not counted as use (filtered_candidates.json, docxcorpus-batch-{500,2,3}-v1.json, "
    "s6-batch-{500,2,3}-omml-screen-v1.json). All 90 raw/docx-corpus/files/ documents are excluded (gold/paper15/paper30 corpus). "
    "See touched_union.json."
)
ORGANIC_PRIOR_USE = ("S6/S18 organic-OMML screening, s6-independent-gold, s6-word-receipts; "
                     "never in any respec_cascade or section_reorder run")
FRESH_PII_STATUS = "tools/pii_pattern_scan clean (pattern scan only; no free-text review yet)"
FRESH_LICENSE_STATUS = "unknown_pending_review per file; dataset-level ODC-BY claim (same as S6 adjudication note)"


def _git(repo: str | Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def _corpus_metadata(data_root: str) -> dict[str, dict]:
    return {m["id"]: m for m in read_json(os.path.join(data_root, CORPUS_METADATA))}


def cmd_k4sr(args: argparse.Namespace) -> int:
    scan = read_json(args.scan)
    resp = {r["sha256"]: r for r in read_json(args.fresh_respec)}
    meta = _corpus_metadata(args.data_root)
    pool = read_json(args.pool)
    tu = read_json(args.touched_union)
    lo, hi = K4SR_BAND

    elig = [r for r in scan if r.get("plan_found") and r.get("pii_clean") and lo <= r["plan"]["heading_count"] <= hi]
    elig.sort(key=lambda r: r["sha256"])
    order = sorted(elig, key=lambda r: rank_key(args.seed, r["sha256"]))
    rank = {r["sha256"]: i + 1 for i, r in enumerate(order)}
    docs = []
    for r in elig:
        m = meta.get(r["id"], {})
        rr = resp.get(r["sha256"], {})
        docs.append({
            "sha256": r["sha256"], "docxcorpus_id": r["id"], "source": "docx-corpus (docxcorp.us), " + r["batch"],
            "source_url": m.get("url", f"https://docxcorp.us/documents/{r['id']}.docx"),
            "local_path": r["path"], "size": r["size"],
            "corpus_metadata": {k: m.get(k) for k in ("type", "topic", "language", "word_count")},
            "heading_count": r["plan"]["heading_count"],
            "section_reorder_plan_section_id": r["plan"]["section_id"],
            "pii_pattern_scan": {"clean": True, **r["pii_counts"]},
            "respec_usable_anchor_sets": {"five_family": rr.get("five_family_usable"), "six_family": rr.get("six_family_usable")},
            "rank_under_proposed_seed": rank[r["sha256"]],
        })
    paper_commit = args.paper_commit or _git(PAPER_ROOT, "rev-parse", "--short=7", "HEAD")
    meridian_commit = args.meridian_commit or _git(args.meridian_repo, "rev-parse", "HEAD")
    out: dict = {"schema": "k4sr-replication-candidates-v0"}
    if args.generated_at:
        out["generated_at"] = args.generated_at
    out.update({
        "status": "candidate pool only -- NOT a locked corpus; no document here has been content-reviewed for this study",
        "resolver": (f"tools/docx_anchor_prober.resolve_section_reorder_plan (repo HEAD {paper_commit}), meridian_docs editable install from "
                     f"{Path(args.meridian_repo).as_posix()} at {meridian_commit} (working tree, unpinned)"),
        "pii_scanner": "tools/pii_pattern_scan.scan_document (post-2026-08-31 fix), unmodified",
        "funnel": {
            "downloaded_batches_500_2_3": sum(1 for d in pool if d["batch"] != "files"),
            "reproduction_check_all_6433": REPRODUCTION_CHECK_ALL_BATCH_DOCS,
            "excluded_as_touched": sum(1 for t in tu["touched"].values() if t["batch"] != "files"),
            "fresh": len(scan),
            "fresh_parse_error": sum(1 for r in scan if r.get("error")),
            "fresh_>=3_outline_headings": sum(1 for r in scan if (r.get("outline_heading_count") or 0) >= 3),
            "fresh_plan_found": sum(1 for r in scan if r.get("plan_found")),
            "fresh_plan_found_and_pii_clean": sum(1 for r in scan if r.get("plan_found") and r.get("pii_clean")),
            "fresh_eligible_in_band_3_25": len(elig),
        },
        "exclusion_method": EXCLUSION_METHOD,
        "proposed_seed": args.seed,
        "ordering_rule": ("rank = ascending sha256(f'{seed}:{doc_sha256}') hex digest; version-independent (no PRNG). "
                          "Recompute with k4sr_select.py for the seed the preregistration actually locks."),
        "documents": docs,
    })
    write_json(args.out, out, indent=1, ensure_ascii=False)
    print(len(docs), out["funnel"], "->", args.out)
    return 0


def cmd_respec(args: argparse.Namespace) -> int:
    meta = _corpus_metadata(args.data_root)
    docs = []
    for o in read_json(args.organic):
        if not o.get("cleared") or (o.get("five_family_usable") or 0) < 1:
            continue
        docs.append({
            "sha256": o["sha256"],
            "source": f"docx-corpus {o['batch']} (S6 organic-OMML cleared candidate {o['candidate_id']})",
            "local_path": o["path"],
            "headings": o["headings"], "omath": o["omath"], "tbl": o["tbl"],
            "five_family_usable": o["five_family_usable"], "six_family_usable": o["six_family_usable"],
            "pii_status": f"{o['adjudication']} ({o['pii_scan']})",
            "license_status": o["license_status"],
            "prior_use": ORGANIC_PRIOR_USE,
        })
    for r in read_json(args.fresh_respec):
        if r.get("error") or r["headings"] <= K4SR_BAND[1] or r["five_family_usable"] < 1:
            continue
        m = meta.get(r["id"], {})
        docs.append({
            "sha256": r["sha256"],
            "source": f"docx-corpus {r['batch']} (fresh, never touched; >25 headings so outside the K=4 band)",
            "local_path": r["path"],
            "source_url": m.get("url", f"https://docxcorp.us/documents/{r['id']}.docx"),
            "corpus_metadata": {k: m.get(k) for k in ("type", "topic", "word_count")},
            "headings": r["headings"], "omath": r["omath"], "tbl": r["tbl"],
            "five_family_usable": r["five_family_usable"], "six_family_usable": r["six_family_usable"],
            "pii_status": FRESH_PII_STATUS,
            "license_status": FRESH_LICENSE_STATUS,
            "prior_use": "none found",
        })
    out = {
        "schema": "respec-public-candidates-v0",
        "note": ("Disjoint from k4sr_candidates.json by construction (organic docs are touched/excluded from K4SR; "
                 "fresh docs here have >25 headings, outside the K4SR band)."),
        "documents": docs,
    }
    write_json(args.out, out, indent=1)
    print(len(docs), "respec public candidates,", sum(1 for d in docs if d["six_family_usable"] == 4), "with 4 six-family sets ->", args.out)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("k4sr", help="K=4 section-reorder replication candidate pool")
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--meridian-repo", default=DEFAULT_MERIDIAN_REPO, help="Meridian repo whose meridian_docs the resolvers imported")
    p.add_argument("--meridian-commit", default=None, help="record this commit instead of reading --meridian-repo's HEAD")
    p.add_argument("--paper-commit", default=None, help="record this paper-repo commit instead of HEAD (7 hex)")
    p.add_argument("--generated-at", default=None, help="timestamp to record verbatim; omitted when not given")
    p.add_argument("--seed", type=int, default=PROPOSED_K4SR_SEED)
    p.add_argument("--scan", type=Path, default=FRESH_SCAN)
    p.add_argument("--fresh-respec", type=Path, default=FRESH_RESPEC)
    p.add_argument("--pool", type=Path, default=POOL_INDEX)
    p.add_argument("--touched-union", type=Path, default=TOUCHED_UNION)
    p.add_argument("--out", type=Path, default=K4SR_OUT)
    p.set_defaults(func=cmd_k4sr)

    p = sub.add_parser("respec", help="respec_cascade re-run public candidate pool")
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--organic", type=Path, default=ORGANIC_RESPEC)
    p.add_argument("--fresh-respec", type=Path, default=FRESH_RESPEC)
    p.add_argument("--out", type=Path, default=RESPEC_OUT)
    p.set_defaults(func=cmd_respec)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
