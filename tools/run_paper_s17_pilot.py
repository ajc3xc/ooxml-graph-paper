"""PAPER-S17 PILOT: bounded structural/native-parser evidence + Claude A/B
availability probe, produced while S6 (organic-OMML holdout) remains closed.

This script does NOT construct new gold, does NOT touch the clean-holdout
gate, and does NOT run any confirmatory benchmark. It only:

1. Cites the two structural/native-parser scorer reports already produced
   this session by the existing, already-verified `run_paper30_graph_eval.py`
   harness (PAPER-30/PAPER-S5) against the staged D0/127 gold corpus --
   one full `--slice all` (127/127 documents) run, and one `--slice smoke`
   run with a 2-document real Word-COM round-trip sample -- by path + SHA-256,
   so results are traceable to an actual re-run, not re-typed by hand.

2. Runs that SAME harness's own extraction functions
   (`extract_native_meridian_items`, `extract_python_docx_items`, imported
   directly, not reimplemented) against the already-built, already-verified
   `thesis-p30` development/regression fixture
   (E:\\MeridianData\\ooxml-graph-paper\\fixtures\\thesis-p30\\, built and
   Word-verified in a prior session, see docs/thesis-p30-fixture-v0.md and
   that fixture's own manifest.json) as this run's "development/regression
   material" pass. Before extracting, each fixture file's SHA-256 is
   recomputed and compared against the hash already on record in that
   fixture's manifest.json -- a real drift check, not an assumption the
   fixture is untouched. No fixture text is re-quoted here; only structural
   counts (paragraphs/tables/equations/captions) and timings are recorded,
   since the underlying document is the user's real personal thesis draft.

3. Re-probes whether the PAPER-S20 paired Claude control/treatment harness
   (tools/docx_trial_broker.py, tools/claude_pair_runner.py,
   tools/docx_trial_evaluator.py, tools/run_paper_s20_pilot.py -- all already
   committed) can actually execute right now, with a minimal, bounded,
   non-interactive `claude -p` call using an empty --strict-mcp-config (the
   control arm's own isolation mechanism). Records the exact stdout/stderr
   and exit code -- never a fabricated pilot number if this fails.

Usage:
  pixi run python tools/run_paper_s17_pilot.py
"""
from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

PAPER_ROOT = Path(r"C:\Users\13144\Documents\Meridian\ooxml-graph-paper")
DATA_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper")
FIXTURE_DIR = DATA_ROOT / "fixtures" / "thesis-p30"
OUT_DIR = DATA_ROOT / "runs" / "paper-s17-pilot"

sys.path.insert(0, str(PAPER_ROOT / "tools"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _structural_scorer_citations() -> dict:
    """Cite the two run_paper30_graph_eval.py reports produced this session
    (see this session's own tool-call log for the exact commands/timings:
    `--slice all` and `--slice smoke --round-trip-check --round-trip-sample 2`)."""
    manifests_dir = DATA_ROOT / "manifests"
    all_reports = sorted(manifests_dir.glob("paper30-graph-eval-all-*.json"))
    smoke_rt_reports = sorted(manifests_dir.glob("paper30-graph-eval-smoke-*.json"))
    out = {}
    if all_reports:
        p = all_reports[-1]
        d = json.loads(p.read_text(encoding="utf-8"))
        out["d0_127_full_slice"] = {
            "report_path": str(p),
            "report_sha256": _sha256_file(p),
            "document_count": d["document_count"],
            "scored_count": d["scored_count"],
            "corpus_run_manifest_sha256": d.get("corpus_run_manifest_sha256"),
            "aggregate_bootstrap_ci": d["aggregate_bootstrap_ci"],
        }
    else:
        out["d0_127_full_slice"] = {"status": "not_run", "reason": "no paper30-graph-eval-all-*.json found"}

    # pick the smoke report that actually carries a round-trip result
    rt_report = None
    for p in reversed(smoke_rt_reports):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("round_trip_check", {}).get("results"):
            rt_report = (p, d)
            break
    if rt_report:
        p, d = rt_report
        out["word_round_trip_sample"] = {
            "report_path": str(p),
            "report_sha256": _sha256_file(p),
            "sample_size_requested": d["round_trip_check"]["sample_size_requested"],
            "results": d["round_trip_check"]["results"],
        }
    else:
        out["word_round_trip_sample"] = {"status": "not_run", "reason": "no smoke report with round_trip_check results found"}
    return out


def _thesis_p30_structural_pass() -> dict:
    """Structural/native-parser pass over the already-built thesis-p30
    development/regression fixture. Reports counts and timings only -- no
    text content, since the source is the user's real personal thesis."""
    manifest_path = FIXTURE_DIR / "manifest.json"
    if not manifest_path.is_file():
        return {"status": "not_run", "reason": f"fixture manifest not found at {manifest_path}"}
    fixture_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    from run_paper30_graph_eval import extract_native_meridian_items, extract_python_docx_items  # noqa: E402

    variants = {
        "base": (FIXTURE_DIR / "thesis-p30-base.docx", fixture_manifest.get("base_sha256")),
        "forward": (FIXTURE_DIR / "thesis-p30-forward.docx", fixture_manifest.get("forward_sha256")),
        "inverse": (FIXTURE_DIR / "thesis-p30-inverse.docx", fixture_manifest.get("inverse_sha256")),
    }
    results = {}
    for name, (path, expected_hash) in variants.items():
        if not path.is_file():
            results[name] = {"status": "not_run", "reason": f"missing file {path}"}
            continue
        actual_hash = _sha256_file(path)
        row = {
            "path": str(path),
            "expected_sha256_from_fixture_manifest": expected_hash,
            "actual_sha256": actual_hash,
            "hash_matches_fixture_manifest": (actual_hash == expected_hash),
        }
        for extractor_name, fn in (("native_meridian", extract_native_meridian_items),
                                    ("python_docx", extract_python_docx_items)):
            t0 = time.monotonic()
            try:
                items = fn(path)
                elapsed = time.monotonic() - t0
                row[extractor_name] = {
                    "status": "ok",
                    "elapsed_seconds": round(elapsed, 3),
                    "paragraph_count": len(items["paragraphs"]),
                    "table_count": len(items["tables"]),
                    "equation_count": len(items["equations"]),
                    "caption_count": len(items["captions"]),
                }
            except Exception as exc:  # noqa: BLE001
                elapsed = time.monotonic() - t0
                row[extractor_name] = {
                    "status": "crashed",
                    "elapsed_seconds": round(elapsed, 3),
                    "error": f"{type(exc).__name__}: {exc}",
                }
        results[name] = row

    # cross-variant regression check: forward vs base, inverse vs base --
    # counts only (never text), consistent with the fixture's own
    # already-verified "exactly one paragraph changed" result.
    def _counts(variant_row: dict, extractor: str) -> dict | None:
        node = variant_row.get(extractor)
        if not isinstance(node, dict) or node.get("status") != "ok":
            return None
        return {k: node[k] for k in ("paragraph_count", "table_count", "equation_count", "caption_count")}

    comparisons = {}
    for extractor in ("native_meridian", "python_docx"):
        base_counts = _counts(results.get("base", {}), extractor)
        forward_counts = _counts(results.get("forward", {}), extractor)
        inverse_counts = _counts(results.get("inverse", {}), extractor)
        comparisons[extractor] = {
            "base_counts": base_counts,
            "forward_counts": forward_counts,
            "inverse_counts": inverse_counts,
            "forward_structural_counts_match_base": (forward_counts == base_counts) if (base_counts and forward_counts) else None,
            "inverse_structural_counts_match_base": (inverse_counts == base_counts) if (base_counts and inverse_counts) else None,
        }

    return {
        "status": "ran",
        "fixture_manifest_path": str(manifest_path),
        "fixture_manifest_overall_pass": fixture_manifest.get("overall_pass"),
        "per_variant": results,
        "structural_count_comparisons": comparisons,
        "note": (
            "This is a structural-count sanity pass (paragraph/table/equation/"
            "caption counts + crash/timing), reusing the same extractor "
            "functions as the D0/127 structural scorer. It is NOT a graph_scorer "
            "precision/recall/F1 run: there is no independent gold record for "
            "this fixture (and none should be built -- it is real personal "
            "thesis content, development/regression material only, never "
            "primary holdout, per this item's own instructions and PAPER-S16)."
        ),
    }


def _claude_ab_availability_probe() -> dict:
    """Re-probe (does not assume) whether the PAPER-S20 harness can actually
    execute a live trial right now. Records the exact command and output."""
    harness_files = [
        "docx_trial_broker.py",
        "claude_pair_runner.py",
        "docx_trial_evaluator.py",
        "run_paper_s20_pilot.py",
    ]
    present = {f: (PAPER_ROOT / "tools" / f).is_file() for f in harness_files}

    cmd = ["claude", "-p", "reply with exactly: PING_OK",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=str(PAPER_ROOT), capture_output=True, text=True,
                               timeout=45, shell=True)
        elapsed = time.monotonic() - t0
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        authenticated = "Failed to authenticate" not in stdout and "Failed to authenticate" not in stderr
        probe = {
            "command": " ".join(cmd),
            "elapsed_seconds": round(elapsed, 3),
            "returncode": proc.returncode,
            "stdout": stdout[:2000],
            "stderr": stderr[:2000],
            "authenticated": authenticated,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        probe = {"command": " ".join(cmd), "elapsed_seconds": round(elapsed, 3),
                  "status": "timed_out", "authenticated": False}
    except Exception as exc:  # noqa: BLE001
        probe = {"command": " ".join(cmd), "status": "error",
                  "error": f"{type(exc).__name__}: {exc}", "authenticated": False}

    pilot_executable = bool(probe.get("authenticated"))
    return {
        "harness_code_present": present,
        "harness_code_all_present": all(present.values()),
        "commissioning_doc": "docs/paper-s20-paired-runner-v1.md",
        "live_probe": probe,
        "pilot_executable_now": pilot_executable,
        "status": "not_run" if not pilot_executable else "available_but_not_executed_this_run",
        "reason": (
            None if pilot_executable else
            "Non-interactive `claude -p` subprocess authentication is blocked "
            "in this environment (see live_probe.stdout/stderr for the exact "
            "error). This is the same blocker PAPER-S20 recorded at 2026-08-30 "
            "02:27 (docs/paper-s20-paired-runner-v1.md); re-confirmed live by "
            "this script, not assumed from that earlier document. No API key "
            "or credential was fabricated or sourced to work around this."
        ),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    report = {
        "run_id": f"paper-s17-pilot-{ts}",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "label": "PILOT / NON-CONFIRMATORY -- must not be pooled with S7/S8 final evidence",
        "sprint_item": "d5a64f3c-5001-4ee8-9d35-35cc6ba3b774 (PAPER-S17 PILOT)",
        "structural_scorer_on_d0_127": _structural_scorer_citations(),
        "structural_scorer_on_development_regression_material": {
            "thesis_p30_fixture": _thesis_p30_structural_pass(),
        },
        "claude_ab_pilot": _claude_ab_availability_probe(),
    }

    out_path = OUT_DIR / f"paper-s17-pilot-{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Report: {out_path}")
    print(json.dumps({
        "d0_127_scored_count": report["structural_scorer_on_d0_127"].get("d0_127_full_slice", {}).get("scored_count"),
        "thesis_p30_status": report["structural_scorer_on_development_regression_material"]["thesis_p30_fixture"].get("status"),
        "claude_ab_pilot_executable_now": report["claude_ab_pilot"]["pilot_executable_now"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
