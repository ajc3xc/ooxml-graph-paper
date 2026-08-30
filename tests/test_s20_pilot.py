"""Regression tests for S20 execution-status gating."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

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
