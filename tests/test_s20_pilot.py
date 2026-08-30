"""Regression tests for S20 execution-status gating."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from claude_pair_runner import _build_command, _CLAUDE_EXECUTABLE  # noqa: E402
from docx_trial_broker import TrialSpec  # noqa: E402
from run_paper_s20_pilot import classify_trial_execution  # noqa: E402


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
        input_docx=tmp_path / "input.docx",
        anchor_text="anchor",
        insert_text="insert",
        prompt="edit the document",
    )

    command = _build_command(spec, tmp_path, tmp_path / "doc.docx")

    assert command[command.index("--setting-sources") + 1] == "project"
    assert "--safe-mode" not in command
    assert "--bare" not in command


def test_runner_uses_tools_flag_for_actual_arm_boundary(tmp_path: Path) -> None:
    base = dict(
        trial_id="trial",
        doc_label="fixture",
        direction="forward",
        input_docx=tmp_path / "input.docx",
        anchor_text="anchor",
        insert_text="insert",
        prompt="edit the document",
    )

    control = _build_command(TrialSpec(arm="control", **base), tmp_path, tmp_path / "doc.docx")
    treatment = _build_command(TrialSpec(arm="treatment", **base), tmp_path, tmp_path / "doc.docx")

    assert control[control.index("--tools") + 1] == "Read,Write,Edit,Bash"
    assert "--tools" not in treatment
    assert "Edit" in treatment[treatment.index("--disallowedTools") + 1]
    assert treatment[treatment.index("--allowedTools") + 1] == "Read,mcp__meridian-docs-pilot__insert_highlighted_note"


def test_runner_resolves_native_claude_executable() -> None:
    assert Path(_CLAUDE_EXECUTABLE).suffix.lower() == ".exe"
