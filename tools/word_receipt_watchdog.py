"""PAPER-S21: orphan-diagnostics wrapper around tools/retained_render_receipt.py.

Motivation: this sprint's own S21 preflight found that a prior probe left a
Word automation process behind. `retained_render_receipt.py`'s existing
timeout/cleanup logic (validated, copied faithfully from the parent repo's
render_gate.py) only tracks and terminates the ONE PID it itself spawned --
correct behavior, but it never confirms, after the fact, whether that
termination actually succeeded, nor does it distinguish "our process leaked"
from "some unrelated WINWORD.EXE was already running before we started."

This wrapper adds that missing diagnostic layer without changing the render
logic itself:
  1. Snapshot WINWORD.EXE PIDs that exist BEFORE the render starts.
  2. Run the existing, already-validated retained_render_receipt().
  3. Snapshot WINWORD.EXE PIDs again AFTER it returns.
  4. Classify every post-render WINWORD.EXE PID as pre_existing_unrelated
     (do not touch), owned_and_clean (was ours, gone now), or
     owned_orphan (was ours, still running -- a real leak to report).

This module NEVER terminates a process itself -- it only classifies and
reports. Termination of the OWNED pid, if needed, remains
retained_render_receipt.py's own responsibility (the one component that
actually knows it spawned that process).

Usage: pixi run python tools/word_receipt_watchdog.py <docx_path> <out_dir> [--timeout SECONDS]
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retained_render_receipt import retained_render_receipt  # noqa: E402

_WORD_PROCESS_NAME = "winword.exe"


def _current_word_pids() -> set[int]:
    import psutil

    pids: set[int] = set()
    for proc in psutil.process_iter(attrs=["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
        except Exception:  # noqa: BLE001
            continue
        if name == _WORD_PROCESS_NAME:
            pids.add(proc.info["pid"])
    return pids


def _attempt_owned_orphan_cleanup(orphan_pids: list[int], pre_existing_pids: set[int]) -> dict[str, Any]:
    """Best-effort termination of PIDs already PROVEN new-since-our-own-launch
    (never a member of pre_existing_pids -- checked again here as a hard
    safety invariant, not just trusted from the caller). Never touches
    anything else. Records exactly what was attempted and its outcome so an
    incomplete cleanup is visible, never silently swallowed."""
    import time

    import psutil

    attempts: list[dict[str, Any]] = []
    for pid in orphan_pids:
        if pid in pre_existing_pids:
            # Hard invariant violation guard -- should be unreachable given
            # how callers compute orphan_pids, but this function must never
            # terminate a pre-existing process even if a caller's bookkeeping
            # were wrong.
            attempts.append({"pid": pid, "action": "skipped_pre_existing_guard"})
            continue
        try:
            proc = psutil.Process(pid)
            if proc.name().lower() != _WORD_PROCESS_NAME:
                attempts.append({"pid": pid, "action": "skipped_name_mismatch", "actual_name": proc.name()})
                continue
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
                attempts.append({"pid": pid, "action": "terminated", "confirmed_exited": True})
            except psutil.TimeoutExpired:
                time.sleep(0)
                attempts.append({
                    "pid": pid, "action": "terminated",
                    "confirmed_exited": not psutil.pid_exists(pid),
                })
        except psutil.NoSuchProcess:
            attempts.append({"pid": pid, "action": "already_gone"})
        except Exception as exc:  # noqa: BLE001
            attempts.append({"pid": pid, "action": "error", "error": f"{type(exc).__name__}: {exc}"})
    return {"cleanup_attempts": attempts}


def word_receipt_with_orphan_diagnostics(
    docx_path: Path, out_dir: Path, timeout: float | None = None, *, cleanup_orphans: bool = True,
) -> dict[str, Any]:
    pre_existing_pids = _current_word_pids()

    kwargs: dict[str, Any] = {}
    if timeout is not None:
        kwargs["timeout"] = timeout
    receipt = retained_render_receipt(docx_path, out_dir, **kwargs)

    post_pids = _current_word_pids()
    owned_pid = receipt.get("owned_pid")  # only set on the timeout path today

    diagnostics: dict[str, Any] = {
        "pre_existing_word_pids": sorted(pre_existing_pids),
        "post_render_word_pids": sorted(post_pids),
        "new_word_pids_since_start": sorted(post_pids - pre_existing_pids),
    }

    new_pids = post_pids - pre_existing_pids
    if owned_pid is not None and owned_pid in post_pids:
        diagnostics["owned_pid_status"] = "orphan_still_running"
        diagnostics["orphan_pids"] = [owned_pid]
    elif new_pids:
        # A WINWORD.EXE that wasn't there before and isn't the one
        # render_receipt told us it owned (e.g. the success path never
        # populates owned_pid at all) -- report it explicitly rather than
        # silently attributing it to "pre-existing."
        diagnostics["owned_pid_status"] = "unattributed_new_process"
        diagnostics["orphan_pids"] = sorted(new_pids)
    else:
        diagnostics["owned_pid_status"] = "clean_no_new_word_process"
        diagnostics["orphan_pids"] = []

    diagnostics["pre_existing_unrelated_pids_untouched"] = sorted(
        pre_existing_pids & post_pids
    )

    if cleanup_orphans and diagnostics["orphan_pids"]:
        cleanup = _attempt_owned_orphan_cleanup(diagnostics["orphan_pids"], pre_existing_pids)
        diagnostics.update(cleanup)
        diagnostics["post_cleanup_word_pids"] = sorted(_current_word_pids())
        diagnostics["cleanup_complete"] = pre_existing_pids >= _current_word_pids()

    return {
        "schema": "paper-s21-word-receipt-watchdog-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "render_receipt": receipt,
        "orphan_diagnostics": diagnostics,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx_path", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument(
        "--no-cleanup-orphans", action="store_true",
        help="diagnose only, never terminate a provably-new orphaned WINWORD.EXE",
    )
    args = parser.parse_args(argv)

    result = word_receipt_with_orphan_diagnostics(
        args.docx_path, args.out_dir, args.timeout,
        cleanup_orphans=not args.no_cleanup_orphans,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    status = result["render_receipt"]["status"]
    diag = result["orphan_diagnostics"]
    unresolved_orphan = bool(diag.get("orphan_pids")) and not diag.get("cleanup_complete", False)
    return 0 if (status == "rendered" and not unresolved_orphan) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
