"""Rebuild paper/sources/: the small statistics files that every value in
paper/numbers.json is traced to.

Three of them had no stored output before (the combined-corpus section-reorder
statistics at K=1 and K=4, and the multi-anchor combined statistics); they are
regenerated here with this repo's own statistics code from the raw run
manifests. The rest are copied from the run tree. SOURCES.json records, for
each file, where it came from, how it was produced, and its sha256.

Run data lives outside the repo (default D:/MeridianData/ooxml-graph-paper/runs,
override with --runs); this script reads it and writes only paper/sources/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
OUT = REPO / "paper" / "sources"


# Timed-out ("blocked") chains are excluded from both arms' denominators as
# infrastructure failures, except these, which are the arm's own task failure and
# are scored 0 (paper Appendix Note b): on this 2.7MB document the control agent
# never finished within the 300s timeout in six attempts, at K=1 and at K=4,
# while treatment finished in under 20s.
SCORED_AS_FAILURE = {
    1: ["s7v2_sr_402d26ad8605a5ee-section_reorder-control-k1"],
    4: ["s7v2_sr_402d26ad8605a5ee-section_reorder-control-k4"],
}


def _score_as_failure_args(k: int) -> list[str]:
    return [arg for chain_id in SCORED_AS_FAILURE[k] for arg in ("--score-as-failure", chain_id)]


def plan(runs: Path) -> list[dict]:
    v1, v2 = runs / "paper-s7", runs / "paper-s7-v2-section-reorder"
    rerun = runs / "paper-s7-clean-rerun-runpod" / "runs" / "paper-s7-clean-rerun"
    # Order matters: the bootstrap resamples in chain-load order with a fixed seed.
    secreorder_k1 = [TOOLS / "compute_s7_statistics.py",
                     v1 / "validation-k1-fixrerun-20260831T145852Z-bib-flake-corrected-20260906.json",
                     v1 / "holdout-k1-fixrerun-20260831T145852Z" / "slice-manifest.json",
                     v2 / "validation-k1-20260831T172118Z" / "slice-manifest-corrected2-20260904.json",
                     v2 / "holdout-k1-20260831T172118Z" / "slice-manifest-corrected2-20260904.json"]
    secreorder_k4 = [TOOLS / "compute_s7_statistics.py",
                     v1 / "validation-k4-fixrerun-20260902T111600Z" / "slice-manifest.json",
                     v1 / "holdout-k4-fixrerun-20260902T111600Z" / "slice-manifest.json",
                     v2 / "holdout-k4-20260904T090807Z" / "slice-manifest-corrected-20260904.json",
                     v2 / "validation-k4-20260904T132025Z" / "slice-manifest-corrected-20260904.json"]
    return [
        {"name": "secreorder-combined-k1-statistics.json", "cmd": [*secreorder_k1, *_score_as_failure_args(1)]},
        {"name": "secreorder-combined-k4-statistics.json", "cmd": [*secreorder_k4, *_score_as_failure_args(4)]},
        # The same statistics with the Note b chain excluded (the harness's default for every
        # timeout), reported beside the scored-as-failure numbers because that scoring was
        # decided after the results were known.
        {"name": "secreorder-combined-k1-statistics-noteb-excluded.json", "cmd": secreorder_k1},
        {"name": "secreorder-combined-k4-statistics-noteb-excluded.json", "cmd": secreorder_k4},
        {"name": "multianchor-combined-statistics.json",
         "cmd": [TOOLS / "compute_s7_combined_statistics.py",
                 "--original-manifests", rerun / "primary_holdout" / "slice-manifest.json",
                 rerun / "validation" / "slice-manifest.json",
                 "--extension-run-root", runs / "paper-s7-multi-anchor-extension" / "runs",
                 "--families", "equation", "caption"]},
        {"name": "respec-cascade-statistics.json", "copy": runs / "paper-s23-final" / "statistics.json"},
        {"name": "respec-cascade-primary-sweep-manifest.json", "copy": runs / "paper-s23-final" / "primary-sweep-manifest.json"},
        {"name": "respec-cascade-baseline-sweep-manifest.json", "copy": runs / "paper-s23-final" / "baseline-sweep-manifest.json"},
        {"name": "rerun-runpod-statistics.json", "copy": rerun / "s7-final-statistics-runpod.json"},
        {"name": "single-edit-k1-fixrerun-statistics.json", "copy": v1 / "k1-fixrerun-statistics-20260831T145852Z.json"},
    ]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("D:/MeridianData/ooxml-graph-paper/runs"))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    record = {}
    for item in plan(args.runs):
        dest = OUT / item["name"]
        if "copy" in item:
            shutil.copyfile(item["copy"], dest)
            record[item["name"]] = {"copied_from": str(item["copy"]), "sha256_of_origin": sha256(item["copy"])}
        else:
            cmd = [sys.executable] + [str(c) for c in item["cmd"]] + ["--out", str(dest)]
            subprocess.run(cmd, check=True, cwd=REPO)
            inputs = [c for c in item["cmd"][1:] if isinstance(c, Path) and c.suffix == ".json" and c.is_file()]
            record[item["name"]] = {
                "generated_by": " ".join(str(c.relative_to(REPO)) if isinstance(c, Path) and REPO in c.parents
                                         else str(c) for c in item["cmd"]),
                "inputs": {str(p): sha256(p) for p in inputs},
            }
        record[item["name"]]["sha256"] = sha256(dest)
        print(f"wrote {dest.relative_to(REPO)}")
    (OUT / "SOURCES.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
