"""Regression tests for S20 execution-status gating."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from claude_pair_runner import _build_command, _CLAUDE_EXECUTABLE  # noqa: E402
from docx_trial_broker import TrialSpec  # noqa: E402
from run_paper_s20_pilot import _milestone_word_receipt, classify_trial_execution  # noqa: E402


def test_authentication_failure_is_not_a_completed_trial() -> None:
    status, reason = classify_trial_execution(
        {
            "returncode": 1,
            "timed_out": False,
            "claude_json_result": {
                "is_error": True,
                "result": "Failed to authenticate: OAuth session expired and could not be refreshed",
            },
        }
    )

    assert status == "not_run"
    assert "authenticate" in (reason or "").lower()


def test_plaintext_authentication_failure_is_not_run() -> None:
    status, reason = classify_trial_execution(
        {
            "returncode": 1,
            "timed_out": False,
            "claude_json_result": None,
            "stdout_tail": "Failed to authenticate: OAuth session expired and could not be refreshed",
        }
    )

    assert status == "not_run"
    assert "oauth session expired" in (reason or "").lower()


def test_successful_claude_result_is_executable() -> None:
    status, reason = classify_trial_execution(
        {
            "returncode": 0,
            "timed_out": False,
            "claude_json_result": {
                "is_error": False,
                "subtype": "success",
                "result": "DONE",
            },
        }
    )

    assert status == "completed"
    assert reason is None


def test_nonzero_process_exit_cannot_be_graded_from_unchanged_docx() -> None:
    status, reason = classify_trial_execution(
        {
            "returncode": 1,
            "timed_out": False,
            "claude_json_result": None,
            "docx_changed": False,
        }
    )

    assert status == "not_run"
    assert "return code 1" in (reason or "")


def test_runner_uses_safe_mode_so_oauth_login_remains_available(tmp_path: Path) -> None:
    spec = TrialSpec(
        trial_id="trial-control",
        doc_label="fixture",
        arm="control",
        direction="forward",
        family="bibliography",
        input_docx=tmp_path / "input.docx",
        marker_text="Commissioning Pilot Marker Publication abc123",
        treatment_tool="insert_bibliography_entry",
        treatment_args={"citation_key": "pilot-s20-abc123", "csl_item": {}},
        prompt="edit the document",
    )

    command = _build_command(spec, tmp_path, tmp_path / "doc.docx", "haiku")

    assert command[command.index("--setting-sources") + 1] == "project"
    assert "--safe-mode" not in command
    assert "--bare" not in command
    assert command[command.index("--model") + 1] == "haiku"


def test_runner_uses_tools_flag_for_actual_arm_boundary(tmp_path: Path) -> None:
    base = dict(
        trial_id="trial",
        doc_label="fixture",
        direction="forward",
        family="bibliography",
        input_docx=tmp_path / "input.docx",
        marker_text="Commissioning Pilot Marker Publication abc123",
        treatment_tool="insert_bibliography_entry",
        treatment_args={"citation_key": "pilot-s20-abc123", "csl_item": {}},
        prompt="edit the document",
    )

    control = _build_command(TrialSpec(arm="control", **base), tmp_path, tmp_path / "doc.docx", "haiku")
    treatment = _build_command(TrialSpec(arm="treatment", **base), tmp_path, tmp_path / "doc.docx", "haiku")

    assert control[control.index("--tools") + 1] == "Read,Write,Edit,Bash"
    assert "--tools" not in treatment
    assert "Edit" in treatment[treatment.index("--disallowedTools") + 1]
    # Generalized (PAPER-S7): each trial exposes exactly the ONE Meridian
    # tool its own direction needs (spec.treatment_tool), tighter than S20's
    # original design which exposed both insert+remove to every trial.
    assert treatment[treatment.index("--allowedTools") + 1] == (
        "Read,mcp__meridian-docs-pilot__insert_bibliography_entry"
    )


def test_runner_exposes_only_the_inverse_tool_for_an_inverse_trial(tmp_path: Path) -> None:
    spec = TrialSpec(
        trial_id="trial",
        doc_label="fixture",
        arm="treatment",
        direction="inverse",
        family="bibliography",
        input_docx=tmp_path / "input.docx",
        marker_text="Commissioning Pilot Marker Publication abc123",
        treatment_tool="remove_bibliography_entry",
        treatment_args={"citation_key": "pilot-s20-abc123"},
        prompt="edit the document",
    )

    command = _build_command(spec, tmp_path, tmp_path / "doc.docx", "haiku")

    assert command[command.index("--allowedTools") + 1] == (
        "Read,mcp__meridian-docs-pilot__remove_bibliography_entry"
    )


def test_runner_resolves_native_claude_executable() -> None:
    assert Path(_CLAUDE_EXECUTABLE).suffix.lower() == ".exe"


def test_milestone_word_receipt_reports_not_run_on_missing_input(tmp_path: Path) -> None:
    receipt = _milestone_word_receipt(
        tmp_path / "does-not-exist.docx", tmp_path / "out", milestone="trial_start",
    )

    assert receipt["milestone"] == "trial_start"
    assert receipt["status"] == "not_run"
    assert "does not exist" in receipt["reason"]


def test_run_trial_gives_each_trial_a_unique_scratch_temp_dir(tmp_path: Path, monkeypatch) -> None:
    """PAPER-S7 correction (2026-08-31): a real primary_holdout trial showed a
    control-arm agent extracting/editing at a fixed, shared temp path; a
    concurrently-running second control-arm trial almost certainly collided
    on the same path, truncating the first trial's document.xml from 48KB to
    2.7KB. run_trial must point TEMP/TMP/TMPDIR at a trial-unique directory
    so two concurrent trials cannot collide on an agent-chosen "system temp
    directory" path."""
    import claude_pair_runner
    import subprocess as subprocess_module

    input_docx = tmp_path / "input.docx"
    input_docx.write_bytes(b"fake-docx-bytes")
    spec = TrialSpec(
        trial_id="trial-a", doc_label="doc", arm="control", direction="forward",
        family="bibliography", input_docx=input_docx, marker_text="marker",
        treatment_tool="insert_bibliography_entry", treatment_args={},
        prompt="edit the document",
    )

    captured_env = {}

    def _fake_run(*args, **kwargs):
        captured_env.update(kwargs.get("env") or {})
        return subprocess_module.CompletedProcess(args=args, returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(claude_pair_runner.subprocess, "run", _fake_run)

    claude_pair_runner.run_trial(spec, tmp_path / "runs")

    expected_scratch = str(tmp_path / "runs" / "trial-a" / "scratch")
    assert captured_env["TEMP"] == expected_scratch
    assert captured_env["TMP"] == expected_scratch
    assert captured_env["TMPDIR"] == expected_scratch
    assert (tmp_path / "runs" / "trial-a" / "scratch").is_dir()


def test_milestone_word_receipt_never_raises_on_render_failure(tmp_path: Path, monkeypatch) -> None:
    import run_paper_s20_pilot

    docx_path = tmp_path / "input.docx"
    docx_path.write_bytes(b"not-a-real-docx")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated Word COM failure")

    monkeypatch.setattr(run_paper_s20_pilot, "word_receipt_with_orphan_diagnostics", _boom)

    receipt = _milestone_word_receipt(docx_path, tmp_path / "out", milestone="after_forward_pair")

    assert receipt["status"] == "not_run"
    assert "simulated Word COM failure" in receipt["reason"]
