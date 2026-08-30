"""Regression tests for PAPER-S21's orphan-diagnostics wrapper
(tools/word_receipt_watchdog.py), mocking psutil and retained_render_receipt
so these run without a real Word COM install.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import word_receipt_watchdog as wrw  # noqa: E402


def _fake_process(pid: int, name: str = "winword.exe"):
    proc = mock.MagicMock()
    proc.name.return_value = name
    proc.pid = pid
    return proc


def test_no_new_word_process_is_reported_clean(monkeypatch, tmp_path):
    monkeypatch.setattr(wrw, "_current_word_pids", lambda: {111})
    monkeypatch.setattr(wrw, "retained_render_receipt", lambda *a, **k: {"status": "rendered"})
    result = wrw.word_receipt_with_orphan_diagnostics(tmp_path / "a.docx", tmp_path)
    diag = result["orphan_diagnostics"]
    assert diag["owned_pid_status"] == "clean_no_new_word_process"
    assert diag["orphan_pids"] == []
    assert diag["pre_existing_unrelated_pids_untouched"] == [111]


def test_new_orphan_is_detected_and_cleaned_up(monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake_current_pids():
        calls["n"] += 1
        return {111} if calls["n"] == 1 else ({111, 222} if calls["n"] == 2 else {111})

    monkeypatch.setattr(wrw, "_current_word_pids", fake_current_pids)
    monkeypatch.setattr(wrw, "retained_render_receipt", lambda *a, **k: {"status": "rendered"})

    fake_proc = _fake_process(222)
    with mock.patch("psutil.Process", return_value=fake_proc), \
         mock.patch("psutil.pid_exists", return_value=False):
        result = wrw.word_receipt_with_orphan_diagnostics(tmp_path / "a.docx", tmp_path)

    diag = result["orphan_diagnostics"]
    assert diag["owned_pid_status"] == "unattributed_new_process"
    assert diag["orphan_pids"] == [222]
    assert diag["cleanup_complete"] is True
    fake_proc.terminate.assert_called_once()
    assert diag["pre_existing_unrelated_pids_untouched"] == [111]


def test_pre_existing_pid_is_never_terminated_even_if_misclassified(tmp_path):
    """Hard safety invariant: _attempt_owned_orphan_cleanup refuses to touch
    a pid that is a member of pre_existing_pids, regardless of what the
    caller passes as orphan_pids."""
    with mock.patch("psutil.Process") as mock_process_cls:
        result = wrw._attempt_owned_orphan_cleanup([111], pre_existing_pids={111})
    mock_process_cls.assert_not_called()
    assert result["cleanup_attempts"] == [{"pid": 111, "action": "skipped_pre_existing_guard"}]


def test_cleanup_skips_pid_whose_process_name_is_not_word(tmp_path):
    fake_proc = _fake_process(333, name="notepad.exe")
    with mock.patch("psutil.Process", return_value=fake_proc):
        result = wrw._attempt_owned_orphan_cleanup([333], pre_existing_pids=set())
    fake_proc.terminate.assert_not_called()
    assert result["cleanup_attempts"][0]["action"] == "skipped_name_mismatch"


def test_owned_pid_still_running_is_reported_as_orphan(monkeypatch, tmp_path):
    monkeypatch.setattr(wrw, "_current_word_pids", lambda: {111, 999})
    monkeypatch.setattr(
        wrw, "retained_render_receipt", lambda *a, **k: {"status": "timed_out", "owned_pid": 999},
    )
    with mock.patch("psutil.Process", return_value=_fake_process(999)), \
         mock.patch("psutil.pid_exists", return_value=False):
        result = wrw.word_receipt_with_orphan_diagnostics(tmp_path / "a.docx", tmp_path)
    diag = result["orphan_diagnostics"]
    assert diag["owned_pid_status"] == "orphan_still_running"
    assert diag["orphan_pids"] == [999]
