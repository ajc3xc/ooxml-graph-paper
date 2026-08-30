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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_trial_broker import (  # noqa: E402
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
            fwd_result["isolation_audit"] = audit_isolation(fwd_result)
            fwd_result["grading"] = grade_forward_trial(
                Path(fwd_result["output_docx_path"]),
                paragraphs_before,
                forward_spec.insert_text,
                forward_spec.anchor_text,
            )
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
            inv_result = run_trial(inv_spec, run_root)
            inv_result["isolation_audit"] = audit_isolation(inv_result)
            inv_result["grading"] = grade_inverse_trial(
                Path(inv_result["output_docx_path"]),
                paragraphs_before,
                forward_spec.insert_text,
            )
            all_results.append(inv_result)
            print(json.dumps({k: inv_result[k] for k in ("trial_id", "returncode", "timed_out", "docx_changed")}))
            print(json.dumps(inv_result["grading"]))

    manifest = {
        "schema": "paper-s20-commissioning-pilot-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "confirmatory": False,
        "note": "8-process (or fewer, if a frozen doc was missing) commissioning pilot -- proves the harness works end to end, not a benchmark result.",
        "trial_count": len(all_results),
        "trials": all_results,
    }
    manifest_path = run_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nManifest: {manifest_path}")

    n_pass = sum(1 for r in all_results if r.get("grading", {}).get("verdict") == "pass")
    n_isolation_clean = sum(1 for r in all_results if r.get("isolation_audit", {}).get("isolation_verdict") == "clean")
    print(f"Grading: {n_pass}/{len(all_results)} passed. Isolation: {n_isolation_clean}/{len(all_results)} clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
