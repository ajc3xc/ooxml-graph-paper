"""Derive the two FINAL-DECISIONS document lists (S25 respec D=8, S26 K4 N=60)
deterministically from the already-reviewed candidate manifests, and write them
as the frozen, lock-time manifests.

This performs NO new seeding and NO new content review: both seeds were
already recorded in the candidate manifests before this script existed
(`manifests/respec_public_review_queue.json`'s seed 20260925002, and
`manifests/k4sr_candidates.json`'s `proposed_seed` 20260925001), and the
FINAL DECISIONS locked in `docs/paper-s25-respec-cascade-rerun-protocol-v1.md`
and `docs/paper-s26-k4-section-reorder-confirmatory-protocol-v1.md` on
2026-09-26 select purely by hash rank under those seeds, not by a fresh
two-reviewer content review (there was no time for one before the deadline;
this is disclosed in both protocols as the lock-time selection method).

Every output document's SHA-256 is *recomputed from the actual local file*
and checked against the value already recorded in the source manifest --
never taken on faith -- so a stale or swapped candidate manifest is caught
here rather than silently propagating into a locked command.

    python tools/select_locked_documents.py respec
        -> manifests/s25-respec-documents-locked.json
           (3 author-owned documents, fixed order, + top 5 by hash rank from
           manifests/respec_public_review_queue.json's existing eligible
           queue, seed 20260925002)

    python tools/select_locked_documents.py k4
        -> manifests/s26-k4-documents-locked.json
           (top 60 by manifests/k4sr_candidates.json's own
           `rank_under_proposed_seed`, seed 20260925001)

Both outputs share the shape {"documents": [{"doc_label", "source", "sha256"}]}.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rerun_selection_common import MANIFESTS_DIR, read_json, write_json  # noqa: E402

REPO_ROOT = MANIFESTS_DIR.parent

RESPEC_CANDIDATES = MANIFESTS_DIR / "respec_public_candidates.json"
RESPEC_QUEUE = MANIFESTS_DIR / "respec_public_review_queue.json"
K4SR_CANDIDATES = MANIFESTS_DIR / "k4sr_candidates.json"

RESPEC_OUT = MANIFESTS_DIR / "s25-respec-documents-locked.json"
K4_OUT = MANIFESTS_DIR / "s26-k4-documents-locked.json"

RESPEC_PUBLIC_QUOTA = 5   # FINAL DECISIONS 2026-09-26: D = 8 = 3 author + 5 public
K4_N = 60                 # FINAL DECISIONS 2026-09-26: N = 60

AUTHOR_DOCS = [
    # (doc_label, local_path, expected sha256 -- from S25 protocol section 1.1, re-verified here)
    ("jcshm-manuscript",
     r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\jcshm-manuscript.docx",
     "ada276d4de9dd346b2f2b6be3cfac9e7637f6eca849e0aa2b516d7b70c294747"),
    ("jcshm-si",
     r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\jcshm-si.docx",
     "8ccdf9dd53a1cb16def8fc6f22044c5902d553c47cd0781fec29677486495cb8"),
    ("masters-dissertation-defense",
     r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\masters-dissertation-defense.docx",
     "b3336b9809dfb0bcac5d73e0f2e94ed4d899a98a93217f01fd6fca648ae0f332"),
]


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_respec(args: argparse.Namespace) -> int:
    queue = read_json(args.queue)
    if queue["seed"] != 20260925002:
        raise SystemExit(f"refusing to re-seed: queue seed is {queue['seed']}, expected 20260925002")
    candidates = {d["sha256"]: d for d in read_json(args.candidates)["documents"]}

    documents = []
    for label, local_path, expected_sha in AUTHOR_DOCS:
        actual = file_sha256(local_path)
        if actual != expected_sha:
            raise SystemExit(f"author document {label} sha256 mismatch: file={actual} protocol={expected_sha}")
        documents.append({
            "doc_label": label,
            "source": f"author-owned, {local_path}",
            "sha256": actual,
            "selection": "S25 section 1.1, fixed (used in the 2026-09-23 run)",
        })

    top = queue["queue"][:args.quota]
    if len(top) < args.quota:
        raise SystemExit(f"review queue has only {len(top)} eligible documents, need {args.quota}")
    for row in top:
        sha = row["sha256"]
        cand = candidates.get(sha)
        if cand is None:
            raise SystemExit(f"rank {row['rank']} sha256 {sha} not found in {args.candidates}")
        actual = file_sha256(cand["local_path"])
        if actual != sha:
            raise SystemExit(f"public document rank {row['rank']} sha256 mismatch: file={actual} manifest={sha}")
        documents.append({
            "doc_label": f"s25pub_{sha[:16]}",
            "source": f"manifests/respec_public_review_queue.json rank {row['rank']} (seed {queue['seed']}); {cand['source']}",
            "sha256": actual,
            "selection": f"hash rank {row['rank']} of {queue['eligible']} eligible, seed {queue['seed']}",
        })

    out = {
        "schema": "s25-respec-documents-locked-v1",
        "decided": "2026-09-26 (FINAL DECISIONS, docs/paper-s25-respec-cascade-rerun-protocol-v1.md D-R1/D-R2)",
        "d": len(documents),
        "selection_method": (
            "3 fixed author-owned documents (section 1.1) plus the top "
            f"{args.quota} documents by existing hash rank from manifests/respec_public_review_queue.json "
            "(seed already recorded there, not re-seeded); selection is by hash rank alone, not a fresh "
            "two-reviewer content review, because of the Sunday 19:00 deadline -- disclosed as a lock-time "
            "deviation from S25 section 1.2's originally drafted two-reviewer process."
        ),
        "documents": documents,
    }
    write_json(args.out, out, indent=1)
    print(f"wrote {len(documents)} documents -> {args.out}")
    return 0


def cmd_k4(args: argparse.Namespace) -> int:
    raw = read_json(args.candidates)
    seed = raw["proposed_seed"]
    docs = raw["documents"]
    ranked = sorted(docs, key=lambda d: d["rank_under_proposed_seed"])
    top = ranked[:args.n]
    if len(top) < args.n:
        raise SystemExit(f"candidate pool has only {len(top)} documents, need {args.n}")

    documents = []
    for d in top:
        actual = file_sha256(d["local_path"])
        if actual != d["sha256"]:
            raise SystemExit(f"K4 doc rank {d['rank_under_proposed_seed']} sha256 mismatch: file={actual} manifest={d['sha256']}")
        label = f"s26k4_{d['sha256'][:16]}"
        documents.append({
            "doc_label": label,
            "source": f"manifests/k4sr_candidates.json rank {d['rank_under_proposed_seed']} (seed {seed}); {d['source']}",
            "sha256": actual,
            "selection": f"hash rank {d['rank_under_proposed_seed']} of 676 eligible, seed {seed}",
        })

    out = {
        "schema": "s26-k4-documents-locked-v1",
        "decided": "2026-09-26 (FINAL DECISIONS, docs/paper-s26-k4-section-reorder-confirmatory-protocol-v1.md D-K1/D-K2)",
        "n": len(documents),
        "selection_method": (
            f"top {args.n} documents by existing hash rank (rank_under_proposed_seed) from "
            "manifests/k4sr_candidates.json (seed already recorded there as proposed_seed, not re-seeded); "
            "selection is by hash rank alone, not a fresh two-reviewer content review, because of the "
            "Sunday 19:00 deadline -- disclosed as a lock-time deviation from S26 section 1.2's originally "
            "drafted two-reviewer process."
        ),
        "documents": documents,
    }
    write_json(args.out, out, indent=1)
    print(f"wrote {len(documents)} documents -> {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("respec", help="write manifests/s25-respec-documents-locked.json")
    p.add_argument("--queue", type=Path, default=RESPEC_QUEUE)
    p.add_argument("--candidates", type=Path, default=RESPEC_CANDIDATES)
    p.add_argument("--quota", type=int, default=RESPEC_PUBLIC_QUOTA)
    p.add_argument("--out", type=Path, default=RESPEC_OUT)
    p.set_defaults(func=cmd_respec)

    p = sub.add_parser("k4", help="write manifests/s26-k4-documents-locked.json")
    p.add_argument("--candidates", type=Path, default=K4SR_CANDIDATES)
    p.add_argument("--n", type=int, default=K4_N)
    p.add_argument("--out", type=Path, default=K4_OUT)
    p.set_defaults(func=cmd_k4)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
