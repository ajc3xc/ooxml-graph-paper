"""Seeded, outcome-blind review orders for the S25/S26 re-runs (stdlib only).

Every order is ascending sha256(f"{seed}:{doc_sha256}") -- no PRNG, so it is
identical on any Python version/OS. Assignment and ordering use only resolver
output, never an outcome.

    python tools/select_rerun_documents.py respec-queue [--seed 20260925002]
        S25: the respec_public_candidates.json documents with all 4 six-family
        anchor-sets, in review order -> manifests/respec_public_review_queue.json.

    python tools/select_rerun_documents.py k4sr --seed <locked seed>
            [--respec-quota Q] [--respec-min-sets 4] [--family five|six] [--out PATH]
        S26: walks k4sr_candidates.json (the 676 fresh, band-3..25,
        PII-pattern-clean, plan-applicable documents) in seeded order once and
        assigns each document to exactly one study, so the respec public slice
        and the K=4 replication never share a document: while the respec quota
        is unfilled, a document with at least --respec-min-sets usable
        anchor-sets (for --family) goes to respec; every other document goes to
        the K=4 queue. The default quota 0 sends every document to K=4.

Reviewers walk each queue top-down (two independent content reviews per
document: free-text PII + suitability, the follow-up protocol's step-4
criteria), record every verdict, and stop the moment the preregistered number
of promotable documents is reached (S25: D, S26: N -- both pending author
decisions). Rejected documents are recorded with a reason and never
revisited; no document is ever dropped after a trial has run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rerun_selection_common import MANIFESTS_DIR, rank_key, read_json, write_json  # noqa: E402

K4SR_CANDIDATES = MANIFESTS_DIR / "k4sr_candidates.json"
RESPEC_CANDIDATES = MANIFESTS_DIR / "respec_public_candidates.json"
RESPEC_QUEUE = MANIFESTS_DIR / "respec_public_review_queue.json"
DEFAULT_RESPEC_SEED = 20260925002  # S25 protocol v1 section 1.3


def order(docs: list[dict], seed: int) -> list[dict]:
    return sorted(docs, key=lambda d: rank_key(seed, d["sha256"]))


def cmd_k4sr(args: argparse.Namespace) -> int:
    docs = read_json(args.candidates)["documents"]
    respec, k4 = [], []
    for d in order(docs, args.seed):
        sets = (d["respec_usable_anchor_sets"] or {}).get(f"{args.family}_family") or 0
        if len(respec) < args.respec_quota and sets >= args.respec_min_sets:
            respec.append(d)
        else:
            k4.append(d)
    result = {
        "seed": args.seed, "family": args.family, "respec_quota": args.respec_quota,
        "respec_queue": [{"sha256": d["sha256"], "docxcorpus_id": d["docxcorpus_id"]} for d in respec],
        "k4sr_queue": [{"sha256": d["sha256"], "docxcorpus_id": d["docxcorpus_id"], "heading_count": d["heading_count"]} for d in k4],
    }
    if args.out:
        write_json(args.out, result, indent=1)
    else:
        print(json.dumps(result, indent=1))
    print(f"respec queue {len(respec)}, k4sr queue {len(k4)}", file=sys.stderr)
    return 0


def cmd_respec_queue(args: argparse.Namespace) -> int:
    docs = read_json(args.candidates)["documents"]
    elig = order([d for d in docs if d.get("six_family_usable") == 4], args.seed)
    queue = [{"rank": i + 1, "sha256": d["sha256"], "headings": d["headings"], "omath": d["omath"], "tbl": d["tbl"],
              "source": d["source"], "pii_status": d["pii_status"]} for i, d in enumerate(elig)]
    write_json(args.out, {"seed": args.seed, "eligible": len(elig), "queue": queue}, indent=1)
    print(len(elig), "eligible ->", args.out)
    for r in queue[:15]:
        print(r["rank"], r["sha256"], r["headings"], r["omath"], r["tbl"], r["source"][:40], "|", r["pii_status"][:30])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("k4sr", help="S26 review order (optionally routing a respec slice first)")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--respec-quota", type=int, default=0)
    p.add_argument("--respec-min-sets", type=int, default=4)
    p.add_argument("--family", choices=("five", "six"), default="five")
    p.add_argument("--candidates", type=Path, default=K4SR_CANDIDATES)
    p.add_argument("--out", type=Path, default=None, help="write JSON here instead of stdout")
    p.set_defaults(func=cmd_k4sr)

    p = sub.add_parser("respec-queue", help="S25 public-document review order")
    p.add_argument("--seed", type=int, default=DEFAULT_RESPEC_SEED)
    p.add_argument("--candidates", type=Path, default=RESPEC_CANDIDATES)
    p.add_argument("--out", type=Path, default=RESPEC_QUEUE)
    p.set_defaults(func=cmd_respec_queue)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
