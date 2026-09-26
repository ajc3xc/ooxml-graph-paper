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
family of the primary run's rotation, arm), calls run_chain(...,
k_pairs=1, anchor_or_plan_override=<that anchor-set's own resolved anchor/
plan>) UNMODIFIED -- no new grading logic, no reimplementation.

2026-09-25 (re-run preparation, review items 6 and 21):
  - The anchor-sets come ONLY from the primary run's anchor-schedules.json,
    whose sha256 is checked against its anchor-schedules.meta.json (and
    --expected-schedule-sha256 when given). There is no fallback that
    re-resolves: a missing or mismatched schedule refuses the sweep.
  - The documents are the ones the primary run recorded in that meta file
    (public documents included), each re-hashed and checked before any
    trial; --documents-manifest, when given, must name the same documents
    with the same hashes.
  - The families follow the primary run's rotation: a six-family run adds
    table_structural, anchored at each anchor-set's own table_anchor. A
    family with zero baseline chains fails the sweep loudly instead of
    silently dropping out of the pooled drops.
  - Arms of each (document, anchor-set, family) are submitted back to back
    (--arm-order-seed), a circuit breaker stops dispatch at the first global
    infrastructure signature (exit 3), --max-chain-attempts applies the
    rerun limit.

Output layout matches tools/compute_respec_cascade_statistics.py::
load_baseline_chains's own documented convention exactly:
    --baseline-run-root/<family>/<chain_dir>/chain-result.json
doc_label uses the SAME f"{original_doc_label}__anchor{i}" convention the
cascade sweep uses, so the two datasets join correctly on doc_label.

Usage:
    python run_respec_cascade_baselines.py --run-root <cascade-run-root> --baseline-run-root <dir> --model haiku
        [--documents-manifest <json>] [--expected-schedule-sha256 <hex>] [--six-family]
        [--arm-order-seed <int>] [--max-chain-attempts 2]
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
from claude_pair_runner import CircuitBreaker, CircuitOpenError  # noqa: E402
from provenance import build_provenance, write_provenance_end, write_provenance_start  # noqa: E402
from run_respec_cascade_sweep import (  # noqa: E402
    SCHEDULE_NAME,
    ScheduleMismatchError,
    load_document_manifest,
    load_verified_schedule,
    verify_documents,
)
from run_paper_s7_benchmark import STATUS_ABORTED_CIRCUIT_OPEN, arm_order, run_chain  # noqa: E402
from usage_cap import UsagePauseController, run_with_usage_cap_retry  # noqa: E402

# The five-family contingency rotation (protocol section 2.3 / 1.2a item 2)
# and the six-family rotation R (section 2.2), which adds table_structural.
FIVE_FAMILIES: tuple[str, ...] = ("bibliography", "citation", "section_reorder", "equation", "caption")
SIX_FAMILIES: tuple[str, ...] = ("bibliography", "citation", "section_reorder", "equation", "table_structural", "caption")
# Kept for callers of the original module surface: the five-family list.
FAMILIES: tuple[str, ...] = FIVE_FAMILIES


def _anchor_override_for_family(family: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Maps one resolve_respec_schedule anchor-set entry to the exact
    anchor_or_plan_override shape run_paper_s7_benchmark.probe_family_
    applicability expects per family (verified directly against that
    function's own real branches, 2026-09-22): a single anchor dict for
    citation/caption/equation/table_structural (the exact shape
    resolve_multiple_body_anchors's own list elements already are; the
    table anchor is the one run_respec_cascade_sweep.add_table_anchors put on
    the entry), the plan dict (with its extra "redirect" key, harmless --
    consumed by explicit key access, not schema-validated) for
    section_reorder, and None for bibliography (probe_family_applicability's
    bibliography branch never reads the override at all -- it has no anchor
    concept, being document-global)."""
    if family == "bibliography":
        return None
    if family == "citation":
        return entry["citation_anchor"]
    if family == "caption":
        return entry["caption_anchor"]
    if family == "equation":
        return entry["equation_anchor"]
    if family == "table_structural":
        return entry["table_anchor"]
    if family == "section_reorder":
        return entry["section_reorder_plan"]
    raise ValueError(f"unknown respec_cascade baseline family: {family!r}")


def _baseline_documents(
    meta: dict[str, Any], documents_manifest: Path | None,
) -> dict[str, dict[str, Any]]:
    """The primary run's documents ({doc_label: {"docx_path", "sha256"}}) from
    its schedule meta file; with `documents_manifest`, that manifest's rows,
    which must name the same documents with the same hashes."""
    recorded = {
        label: {"docx_path": Path(d["docx_path"]), "sha256": d.get("sha256")}
        for label, d in (meta.get("documents") or {}).items()
    }
    if not recorded:
        raise ScheduleMismatchError("the primary run's schedule meta file records no documents")
    if documents_manifest is None:
        return recorded
    given = load_document_manifest(documents_manifest)
    problems = []
    if set(given) != set(recorded):
        problems.append(f"documents {sorted(given)} != primary run's {sorted(recorded)}")
    for label in set(given) & set(recorded):
        expected = given[label].get("sha256")
        if expected is not None and str(expected).lower() != str(recorded[label]["sha256"]).lower():
            problems.append(f"{label}: manifest sha256 {expected} != primary run's {recorded[label]['sha256']}")
    if problems:
        raise ScheduleMismatchError("--documents-manifest disagrees with the primary run: " + "; ".join(problems))
    return {label: {**given[label], "sha256": recorded[label]["sha256"]} for label in given}


def _baseline_job_key(job: tuple[str, str, str]) -> tuple[str, str, str]:
    return job


def run_baseline_sweep(
    cascade_run_root: Path, baseline_run_root: Path, model: str, *,
    max_anchor_sets: int = 4, max_workers: int = 4, word_receipts_enabled: bool = False,
    six_family: bool | None = None, documents_manifest: Path | None = None,
    expected_schedule_sha256: str | None = None, arm_order_seed: int | None = None,
    max_chain_attempts: int | None = None,
    pause_controller: UsagePauseController | None = None, max_usage_cap_rounds: int | None = None,
    provenance_json: Path | None = None, argv: list[str] | None = None,
) -> dict[str, Any]:
    """`six_family`: None follows the primary run's recorded rotation; True
    or False must agree with it. `max_anchor_sets` is kept for the original
    signature only: the anchor-sets are whatever the primary schedule holds.

    `provenance_json`, when given, is written (build_provenance/
    write_provenance_start) right after the primary run's schedule is loaded
    and verified and this sweep's own documents are verified below -- still
    before any trial dispatches -- with the primary schedule's path/sha256
    and `documents_manifest` (the raw --documents-manifest CLI value, None
    when omitted) and its sha256. The caller (main()) updates the same file
    with the end time/exit status once the run finishes
    (write_provenance_end).

    Rate-limit handling (2026-09-25): dispatched in rounds via
    usage_cap.run_with_usage_cap_retry, the same mechanism
    run_respec_cascade_sweep.run_primary_sweep uses -- see that function's
    docstring for the exact semantics, shared verbatim here. Missing this
    wiring previously meant a usage-cap/rate-limit hit during the (often
    multi-hour) baseline sweep permanently tripped a single CircuitBreaker
    for the whole run, aborting every remaining baseline chain and exiting 3
    for an operator to notice and manually relaunch. `pause_controller`
    defaults to a fresh UsagePauseController writing its heartbeat to
    `<baseline_run_root>/usage-cap-status.json`."""
    schedules, meta, schedule_sha = load_verified_schedule(cascade_run_root, expected_sha256=expected_schedule_sha256)
    primary_six = meta.get("rotation") == "six_family"
    if six_family is not None and six_family != primary_six:
        raise ScheduleMismatchError(
            f"--six-family={six_family} but the primary run's rotation is {meta.get('rotation')!r}",
        )
    families = SIX_FAMILIES if primary_six else FIVE_FAMILIES
    documents = _baseline_documents(meta, documents_manifest)
    document_hashes = verify_documents(documents)
    missing = sorted(set(schedules) - set(documents))
    if missing:
        raise ScheduleMismatchError(f"schedule documents with no document path: {missing}")

    if provenance_json is not None:
        record = build_provenance(
            argv if argv is not None else sys.argv, model=model,
            documents_manifest=documents_manifest,
            schedule_path=cascade_run_root / SCHEDULE_NAME, schedule_sha256=schedule_sha,
        )
        write_provenance_start(provenance_json, record)

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
            for family in families:
                jobs.append((doc_label, entry, family))
    # Review item 6: a family with no baseline chain would silently drop its
    # observations from the pooled drops downstream -- refuse instead.
    empty = [family for family in families if not any(f == family for _, _, f in jobs)]
    if empty:
        raise ValueError(f"no baseline chains for families {empty}: no usable anchor-set in {sorted(schedules)}")

    baseline_run_root.mkdir(parents=True, exist_ok=True)
    if pause_controller is None:
        pause_controller = UsagePauseController(heartbeat_path=baseline_run_root / "usage-cap-status.json")

    all_jobs: list[tuple[str, dict[str, Any], str, str]] = []
    for doc_label, entry, family in jobs:
        scoped_label = f"{doc_label}__anchor{entry['anchor_set_index']}"
        for arm in arm_order(arm_order_seed, f"{scoped_label}:{family}"):
            all_jobs.append((doc_label, entry, family, arm))

    def dispatch_round(
        round_jobs: list[tuple[str, dict[str, Any], str, str]], circuit_breaker: CircuitBreaker,
    ) -> tuple[dict[Any, dict[str, Any]], list[Any]]:
        round_results: dict[Any, dict[str, Any]] = {}
        round_submission: list[Any] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for doc_label, entry, family, arm in round_jobs:
                scoped_label = f"{doc_label}__anchor{entry['anchor_set_index']}"
                family_run_root = baseline_run_root / family
                override = _anchor_override_for_family(family, entry)
                future = pool.submit(
                    run_chain, family, scoped_label, Path(documents[doc_label]["docx_path"]), arm, 1, model,
                    family_run_root, word_receipts_enabled=word_receipts_enabled, anchor_or_plan_override=override,
                    circuit_breaker=circuit_breaker, max_chain_attempts=max_chain_attempts,
                    pause_controller=pause_controller,
                )
                key = _baseline_job_key((scoped_label, family, arm))
                futures[future] = key
                round_submission.append([scoped_label, family, arm])
            for future in concurrent.futures.as_completed(futures):
                scoped_label, family, arm = key = futures[future]
                try:
                    round_results[key] = future.result()
                except CircuitOpenError as exc:
                    round_results[key] = {
                        "chain_id": f"{scoped_label}-{family}-{arm}-k1-ABORTED",
                        "doc_label": scoped_label, "family": family, "arm": arm, "k_pairs": 1,
                        "status": STATUS_ABORTED_CIRCUIT_OPEN, "reason": str(exc), "pairs": [],
                    }
                except Exception as exc:  # noqa: BLE001
                    round_results[key] = {
                        "chain_id": f"{scoped_label}-{family}-{arm}-k1-EXCEPTION",
                        "doc_label": scoped_label, "family": family, "arm": arm, "k_pairs": 1,
                        "status": "harness_exception", "reason": f"{type(exc).__name__}: {exc}",
                        "pairs": [],
                    }
        return round_results, round_submission

    def _job_key(job: tuple[str, dict[str, Any], str, str]) -> tuple[str, str, str]:
        doc_label, entry, family, arm = job
        return (f"{doc_label}__anchor{entry['anchor_set_index']}", family, arm)

    final_results, submission_order, usage_cap_rounds = run_with_usage_cap_retry(
        dispatch_round, all_jobs, pause_controller, job_key=_job_key,
        make_circuit_breaker=CircuitBreaker, max_rounds=max_usage_cap_rounds,
    )
    results = list(final_results.values())
    final_circuit_breaker = usage_cap_rounds[-1]["circuit_breaker"] if usage_cap_rounds else CircuitBreaker().state()

    manifest = {
        "schema": "paper-s23-respec-cascade-baseline-sweep-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": model, "families": list(families),
        "rotation": meta.get("rotation"),
        "anchor_schedules_sha256": schedule_sha, "document_hashes": document_hashes,
        "arm_order_seed": arm_order_seed, "max_chain_attempts": max_chain_attempts,
        "submission_order": submission_order,
        "circuit_breaker": final_circuit_breaker,
        "usage_cap_rounds": usage_cap_rounds,
        "usage_cap_status": pause_controller.state(),
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
    parser.add_argument("--run-root", type=Path, required=True, help="The respec_cascade sweep's own run-root (its anchor-schedules.json is required).")
    parser.add_argument("--baseline-run-root", type=Path, required=True)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-anchor-sets", type=int, default=4, help="Unused: the anchor-sets are the primary schedule's.")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--word-receipts", action="store_true")
    parser.add_argument("--six-family", action="store_true", default=None,
                        help="Assert the primary run used the six-family rotation (the families always follow it).")
    parser.add_argument("--documents-manifest", type=Path, default=None,
                        help="The primary sweep's document manifest; must match the documents it recorded.")
    parser.add_argument("--expected-schedule-sha256", default=None,
                        help="Refuse to start unless the primary anchor-schedules.json has this sha256.")
    parser.add_argument("--arm-order-seed", type=int, default=None)
    parser.add_argument("--max-chain-attempts", type=int, default=None)
    parser.add_argument(
        "--max-usage-cap-rounds", type=int, default=None,
        help="Safety valve: stop auto-retrying after this many usage-cap/rate-limit pause-and-resume rounds "
             "(circuit_breaker stays open, exit 3). Omitted: unlimited -- the sweep resumes on its own for as "
             "long as the account keeps hitting its usage cap or a transient rate limit, with no relaunch needed.",
    )
    parser.add_argument(
        "--usage-cap-base-backoff-seconds", type=float, default=30.0,
        help="Backoff before the first retry after a usage-cap/rate-limit pause when the CLI gave no reset time.",
    )
    parser.add_argument(
        "--usage-cap-max-backoff-seconds", type=float, default=1800.0,
        help="Cap on the exponential backoff between usage-cap/rate-limit retry rounds (default 30 minutes).",
    )
    parser.add_argument(
        "--provenance-json", type=Path, default=None,
        help="Write a provenance record here (argv, this repo's git commit, the installed Meridian Docs "
             "package's commit/version, model, documents-manifest path+sha256, the primary run's anchor "
             "schedule path+sha256, hostname, start/end time, exit status) right after the primary run's "
             "schedule and this sweep's documents are verified -- still before any trial dispatches -- then "
             "update it with the end time and exit status when the run finishes.",
    )
    args = parser.parse_args(argv)

    pause_controller = UsagePauseController(
        heartbeat_path=args.baseline_run_root / "usage-cap-status.json",
        base_backoff_seconds=args.usage_cap_base_backoff_seconds,
        max_backoff_seconds=args.usage_cap_max_backoff_seconds,
    )
    try:
        manifest = run_baseline_sweep(
            args.run_root, args.baseline_run_root, args.model, max_anchor_sets=args.max_anchor_sets,
            max_workers=args.max_workers, word_receipts_enabled=args.word_receipts,
            six_family=args.six_family, documents_manifest=args.documents_manifest,
            expected_schedule_sha256=args.expected_schedule_sha256,
            arm_order_seed=args.arm_order_seed, max_chain_attempts=args.max_chain_attempts,
            pause_controller=pause_controller, max_usage_cap_rounds=args.max_usage_cap_rounds,
            provenance_json=args.provenance_json,
        )
    except (ScheduleMismatchError, ValueError) as exc:
        print(f"REFUSING TO START: {exc}", file=sys.stderr)
        if args.provenance_json is not None:
            write_provenance_end(args.provenance_json, exit_status=2)
        return 2
    print(json.dumps({
        "chain_count": manifest["chain_count"],
        "excluded_anchor_set_count": len(manifest["excluded_anchor_sets"]),
        "status_counts": {
            status: sum(1 for c in manifest["chains_summary"] if c["status"] == status)
            for status in sorted({c["status"] for c in manifest["chains_summary"]})
        },
    }, indent=2))
    print(f"Full manifest: {args.baseline_run_root / 'baseline-sweep-manifest.json'}")
    if manifest["usage_cap_rounds"]:
        print(f"Usage-cap pause/resume rounds: {len(manifest['usage_cap_rounds'])} "
              f"(heartbeat: {args.baseline_run_root / 'usage-cap-status.json'})")
    exit_status = 3 if manifest["circuit_breaker"]["open"] else 0
    if manifest["circuit_breaker"]["open"]:
        print(f"CIRCUIT BREAKER OPEN: {json.dumps(manifest['circuit_breaker'])}", file=sys.stderr)
    if args.provenance_json is not None:
        write_provenance_end(args.provenance_json, exit_status=exit_status)
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
