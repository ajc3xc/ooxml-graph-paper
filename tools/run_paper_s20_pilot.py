"""PAPER-S20: the 8-process commissioning pilot driver.

2 frozen docs x 2 arms (control, treatment) x 2 task-instances (forward,
inverse) = 8 trials. The inverse trial for a given (doc, arm) pair operates
on THAT SAME ARM's own forward-trial output, not the pristine frozen
fixture and not the other arm's output -- each arm's forward+inverse pair
is a self-contained round trip.

NON-CONFIRMATORY. This is a first commissioning pilot per PAPER-S20's own
acceptance criteria, not a scientific benchmark: one task type, two frozen
documents, a cheap/fast model. It exists to prove the harness (broker,
runner, isolation audit, evaluator) actually works end to end against a
real `claude` CLI, not to support a superiority claim.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_trial_broker import (  # noqa: E402
    TrialSpec,
    _paragraph_texts,
    expected_forward_state,
    expected_inverse_state,
    generate_task_pair,
)
from docx_trial_evaluator import grade_forward_trial, grade_inverse_trial  # noqa: E402
from claude_pair_runner import audit_isolation, run_trial  # noqa: E402

_GOLD_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\gold")
_RUNS_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\runs\paper-s20")
_FROZEN_DOCS = [
    ("fixture-01-baseline", _GOLD_ROOT / "tier1" / "fixture-01-baseline.docx"),
    ("fixture-02-equation", _GOLD_ROOT / "tier1" / "fixture-02-equation.docx"),
]
_ARMS = ["control", "treatment"]


def classify_trial_execution(trial_result: dict[str, Any]) -> tuple[str, str | None]:
    """Classify whether Claude actually executed a trial.

    A structurally unchanged DOCX is not evidence that an inverse succeeded:
    the forward trial may have failed before producing the required input.  In
    particular, Claude's JSON error result can coexist with a copied, valid
    input DOCX.  Keep process/API failures separate from evaluator failures so
    the pilot cannot turn an authentication failure into a document pass.
    """
    existing_status = trial_result.get("execution_status")
    if existing_status == "not_run":
        return "not_run", trial_result.get("execution_failure_reason") or "trial was not run"

    if trial_result.get("timed_out"):
        return "not_run", "Claude trial timed out before a completed result was recorded"

    returncode = trial_result.get("returncode")
    result = trial_result.get("claude_json_result")
    result_text = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else ""
    raw_text = "\n".join(
        part for part in (result_text, trial_result.get("stdout_tail", ""), trial_result.get("stderr_tail", "")) if part
    )
    if "failed to authenticate" in raw_text.lower():
        for line in raw_text.splitlines():
            if "failed to authenticate" in line.lower():
                return "not_run", line.strip()
        return "not_run", "Claude authentication failed"

    if returncode != 0:
        details = ""
        if isinstance(result, dict):
            details = str(result.get("result") or result.get("terminal_reason") or "").strip()
        if not details:
            details = str(trial_result.get("stdout_tail") or trial_result.get("stderr_tail") or "").strip()
        suffix = f": {details}" if details else ""
        return "not_run", f"Claude process exited with return code {returncode}{suffix}"

    if not isinstance(result, dict):
        return "not_run", "Claude did not return a parseable JSON result"

    if result.get("is_error") is True:
        details = str(result.get("result") or result.get("terminal_reason") or "Claude returned an API error").strip()
        return "not_run", details

    return "completed", None


def _not_run_trial(spec: TrialSpec, reason: str) -> dict[str, Any]:
    """Create a manifest row for an ineligible dependent trial."""
    return {
        "trial_id": spec.trial_id,
        "doc_label": spec.doc_label,
        "arm": spec.arm,
        "direction": spec.direction,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "wall_time_seconds": 0.0,
        "timed_out": False,
        "returncode": None,
        "input_hash_sha256": None,
        "output_hash_sha256": None,
        "docx_changed": False,
        "trial_root": None,
        "output_docx_path": None,
        "cli_command_argv": [],
        "claude_json_result": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "execution_status": "not_run",
        "execution_failure_reason": reason,
        "isolation_audit": {
            "trial_id": spec.trial_id,
            "arm": spec.arm,
            "markers_seen_in_transcript": [],
            "violations": [],
            "isolation_verdict": "not_run",
            "reason": reason,
        },
        "grading": {"verdict": "not_run", "reason": reason},
    }


def _annotate_trial(trial_result: dict[str, Any], grading: dict[str, Any]) -> str:
    """Attach execution status before any document grading is counted."""
    status, reason = classify_trial_execution(trial_result)
    trial_result["execution_status"] = status
    if status != "completed":
        trial_result["execution_failure_reason"] = reason
        trial_result["isolation_audit"] = {
            "trial_id": trial_result["trial_id"],
            "arm": trial_result["arm"],
            "markers_seen_in_transcript": [],
            "violations": [],
            "isolation_verdict": "not_run",
            "reason": reason,
        }
        trial_result["grading"] = {"verdict": "not_run", "reason": reason}
        return status

    trial_result["isolation_audit"] = audit_isolation(trial_result)
    trial_result["grading"] = grading
    return status


def main() -> int:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = _RUNS_ROOT / ts
    run_root.mkdir(parents=True, exist_ok=True)

    all_results = []
    for doc_label, docx_path in _FROZEN_DOCS:
        if not docx_path.is_file():
            print(f"SKIP {doc_label}: frozen fixture not found at {docx_path}", file=sys.stderr)
            continue
        paragraphs_before = _paragraph_texts(docx_path)
        forward_spec, inverse_spec_template = generate_task_pair(doc_label, docx_path)

        for arm in _ARMS:
            print(f"=== {doc_label} / {arm} / forward ===", flush=True)
            fwd_spec = dataclasses.replace(forward_spec, arm=arm, trial_id=f"{forward_spec.trial_id}-{arm}")
            fwd_result = run_trial(fwd_spec, run_root)
            fwd_status = _annotate_trial(fwd_result, grade_forward_trial(
                Path(fwd_result["output_docx_path"]),
                paragraphs_before,
                forward_spec.insert_text,
                forward_spec.anchor_text,
            ))
            all_results.append(fwd_result)
            print(json.dumps({k: fwd_result[k] for k in ("trial_id", "returncode", "timed_out", "docx_changed")}))
            print(json.dumps(fwd_result["grading"]))

            print(f"=== {doc_label} / {arm} / inverse ===", flush=True)
            # The inverse operates on THIS arm's own forward output.
            inv_spec = dataclasses.replace(
                inverse_spec_template,
                arm=arm,
                trial_id=f"{inverse_spec_template.trial_id}-{arm}",
                input_docx=Path(fwd_result["output_docx_path"]),
            )
            if fwd_status != "completed":
                inv_result = _not_run_trial(
                    inv_spec,
                    "inverse skipped because its arm's forward trial did not complete",
                )
            else:
                inv_result = run_trial(inv_spec, run_root)
                _annotate_trial(inv_result, grade_inverse_trial(
                    Path(inv_result["output_docx_path"]),
                    paragraphs_before,
                    forward_spec.insert_text,
                ))
            all_results.append(inv_result)
            print(json.dumps({k: inv_result[k] for k in ("trial_id", "returncode", "timed_out", "docx_changed")}))
            print(json.dumps(inv_result["grading"]))

    execution_counts = {}
    for result in all_results:
        status = result.get("execution_status", "unknown")
        execution_counts[status] = execution_counts.get(status, 0) + 1
    n_executed = execution_counts.get("completed", 0)
    pilot_status = "complete" if n_executed == len(all_results) and len(all_results) == 8 else "blocked"
    manifest = {
        "schema": "paper-s20-commissioning-pilot-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "confirmatory": False,
        "note": "8-process (or fewer, if a frozen doc was missing) commissioning pilot -- proves the harness works end to end, not a benchmark result.",
        "status": pilot_status,
        "execution_status_counts": execution_counts,
        "trial_count": len(all_results),
        "trials": all_results,
    }
    manifest_path = run_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nManifest: {manifest_path}")

    n_pass = sum(1 for r in all_results if r.get("execution_status") == "completed" and r.get("grading", {}).get("verdict") == "pass")
    n_isolation_clean = sum(1 for r in all_results if r.get("execution_status") == "completed" and r.get("isolation_audit", {}).get("isolation_verdict") == "clean")
    print(f"Execution: {n_executed}/{len(all_results)} completed ({pilot_status}).")
    print(f"Grading: {n_pass}/{len(all_results)} passed. Isolation: {n_isolation_clean}/{len(all_results)} clean.")
    return 0 if pilot_status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
