"""PAPER-23: a standalone, RETAINED Word-COM render receipt.

Deliberately a from-scratch script in the paper subproject, not a change to
the parent repo's render_gate.py (that file is shared, actively used by other
concurrent sessions this sprint, and out of scope for this paper item). The
watchdog/cleanup/COM-apartment pattern below is copied faithfully from
render_gate.py's own `_word_com_render_thread` (read directly, line for line,
before writing this) because that pattern is already validated this sprint --
only the output directory changes, from a `tempfile.TemporaryDirectory()` that
self-deletes before the caller ever sees the PDF (confirmed root cause of the
"render receipt not retained" gap in docs/gold-corpus-status-v0.md) to a
persistent, caller-chosen directory so the PDF and its hash genuinely survive.

Usage: pixi run python tools/retained_render_receipt.py <docx_path> <out_dir> [--timeout SECONDS]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any

_WORD_COM_TIMEOUT_SECONDS = 90.0
_WORD_COM_CLEANUP_JOIN_SECONDS = 5.0
_WD_FORMAT_PDF = 17


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _word_application_pid(word: Any) -> int | None:
    """Mirrors render_gate.py's own `_word_application_pid` (read directly
    before writing this) -- resolve the Word.Application's OS pid via its
    main window handle, never raising."""
    try:
        import win32process

        hwnd = word.Hwnd
        _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
        return int(process_id)
    except Exception:
        return None


def _terminate_owned_process(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def retained_render_receipt(docx_path: Path, out_dir: Path, timeout: float = _WORD_COM_TIMEOUT_SECONDS) -> dict:
    import win32com.client

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / (docx_path.stem + ".pdf")
    outcome: dict[str, Any] = {}
    owned: dict[str, int | None] = {"pid": None}
    timeout_requested = threading.Event()
    facts: dict[str, Any] = {}

    def _worker() -> None:
        word = None
        doc = None
        try:
            import pythoncom

            pythoncom.CoInitialize()
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            owned["pid"] = _word_application_pid(word)
            facts["word_version"] = str(word.Version)
            facts["word_build"] = str(getattr(word, "Build", None))
            doc = word.Documents.Open(
                str(docx_path.resolve()),
                ConfirmConversions=False,
                ReadOnly=True,
                AddToRecentFiles=False,
                Revert=False,
                OpenAndRepair=False,
                NoEncodingDialog=True,
            )
            try:
                facts["page_count"] = int(doc.ComputeStatistics(2))  # wdStatisticPages = 2
            except Exception:
                facts["page_count"] = None
            doc.SaveAs(str(pdf_path), FileFormat=_WD_FORMAT_PDF)
        except Exception as exc:  # noqa: BLE001
            outcome["exc"] = exc
        finally:
            if not timeout_requested.is_set():
                try:
                    if doc is not None:
                        doc.Close(False)
                except Exception:
                    pass
                try:
                    if word is not None:
                        word.Quit()
                except Exception:
                    pass

    worker_thread = threading.Thread(target=_worker, daemon=True)
    started_at = datetime.datetime.now(datetime.timezone.utc)
    worker_thread.start()
    worker_thread.join(timeout)

    receipt: dict[str, Any] = {
        "renderer": "word-com",
        "input_path": str(docx_path),
        "input_hash_sha256": _sha256_file(docx_path) if docx_path.exists() else None,
        "started_at": started_at.isoformat(),
        "timeout_seconds": timeout,
        "word_version": facts.get("word_version"),
        "word_build": facts.get("word_build"),
        "page_count": facts.get("page_count"),
    }

    if worker_thread.is_alive():
        timeout_requested.set()
        pid = owned.get("pid")
        terminated = _terminate_owned_process(pid) if pid is not None else False
        worker_thread.join(_WORD_COM_CLEANUP_JOIN_SECONDS)
        receipt.update({
            "status": "timed_out",
            "exit_status": "timeout",
            "owned_pid": pid,
            "terminated": terminated,
            "cleanup_pending": worker_thread.is_alive(),
            "retained_pdf_path": None,
            "output_hash_sha256": None,
        })
        return receipt

    if "exc" in outcome:
        receipt.update({
            "status": "failed",
            "exit_status": f"exception: {type(outcome['exc']).__name__}: {outcome['exc']}",
            "retained_pdf_path": None,
            "output_hash_sha256": None,
        })
        return receipt

    if not pdf_path.exists():
        receipt.update({
            "status": "failed",
            "exit_status": "Word COM reported success but no PDF was written to disk",
            "retained_pdf_path": None,
            "output_hash_sha256": None,
        })
        return receipt

    receipt.update({
        "status": "rendered",
        "exit_status": "ok",
        "retained_pdf_path": str(pdf_path),
        "output_hash_sha256": _sha256_file(pdf_path),
        "output_size_bytes": pdf_path.stat().st_size,
        "cleanup_status": "clean" if not worker_thread.is_alive() else "worker_still_alive",
    })
    return receipt


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx_path", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--timeout", type=float, default=_WORD_COM_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    receipt = retained_render_receipt(args.docx_path, args.out_dir, args.timeout)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt["status"] == "rendered" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
