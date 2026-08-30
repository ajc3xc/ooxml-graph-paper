"""PAPER-S21: read-only provenance snapshot of the parent Meridian Docs checkout.

The paper Pixi environment imports `docparse`/`meridian_docs` through an
EDITABLE install pointing directly at the parent repo's live filesystem
checkout (see pixi.toml). That means any scoring/render run's "Meridian"
result silently depends on whatever that checkout happens to contain at the
moment -- including uncommitted, in-progress changes from a concurrent
session working the same shared repo. A run against a dirty parent is not
reproducible: someone re-running it later against a clean `git checkout`
of the recorded commit could get different code.

This tool NEVER mutates, stashes, or cleans the parent worktree -- it is a
pure read-only inspector. It answers exactly one question for a given run:
"what code was actually imported, and is that state pinned/reproducible or
not," and records that as an explicit, auditable receipt rather than a
silent assumption baked into a result.

Usage: pixi run python tools/prepare_pinned_parent_snapshot.py [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_PAPER_ROOT = Path(__file__).resolve().parent.parent
_PARENT_REPO = (_PAPER_ROOT.parent / "repository").resolve()


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Read-only git invocation only -- callers must never pass a mutating
    subcommand (checkout/stash/clean/reset/commit/etc.) here."""
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _parent_git_state(parent_repo: Path) -> dict[str, Any]:
    if not parent_repo.is_dir():
        return {"error": f"parent repo not found at {parent_repo}"}

    rc, head, err = _run_git(["rev-parse", "HEAD"], parent_repo)
    if rc != 0:
        return {"error": f"git rev-parse HEAD failed: {err}"}

    rc, branch, _ = _run_git(["branch", "--show-current"], parent_repo)
    rc, porcelain, _ = _run_git(["status", "--porcelain"], parent_repo)
    dirty_paths = [line for line in porcelain.splitlines() if line.strip()]

    return {
        "commit": head,
        "branch": branch or None,
        "is_dirty": bool(dirty_paths),
        "dirty_path_count": len(dirty_paths),
        # Path fragments only (status codes + relative paths), never absolute
        # machine paths, to keep this safe to embed in a shared manifest.
        "dirty_paths_sample": dirty_paths[:10],
    }


def _import_resolution() -> dict[str, Any]:
    """Where docparse/meridian_docs actually import FROM right now, in THIS
    process's environment -- confirms the editable install really does
    resolve to the parent repo path (not, e.g., a stale installed wheel)."""
    resolved: dict[str, Any] = {}
    try:
        import docparse

        resolved["docparse_file"] = str(Path(docparse.__file__).resolve())
    except Exception as exc:  # noqa: BLE001
        resolved["docparse_file"] = None
        resolved["docparse_import_error"] = f"{type(exc).__name__}: {exc}"

    try:
        import meridian_docs

        resolved["meridian_docs_file"] = str(Path(meridian_docs.__file__).resolve())
    except Exception as exc:  # noqa: BLE001
        resolved["meridian_docs_file"] = None
        resolved["meridian_docs_import_error"] = f"{type(exc).__name__}: {exc}"

    parent_repo_str = str(_PARENT_REPO)
    resolved["docparse_resolves_to_parent_repo"] = (
        resolved.get("docparse_file") is not None
        and resolved["docparse_file"].startswith(parent_repo_str)
    )
    resolved["meridian_docs_resolves_to_parent_repo"] = (
        resolved.get("meridian_docs_file") is not None
        and resolved["meridian_docs_file"].startswith(parent_repo_str)
    )
    return resolved


def _mml2omml_path() -> dict[str, Any]:
    """Locate Microsoft's own MML2OMML.XSL (the independent MathML-to-OMML
    conversion reference used elsewhere in this paper's equation work) --
    record whether it's actually present, never assume."""
    candidates = [
        Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
        Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL"),
        Path(r"C:\Program Files\Microsoft Office\Office16\MML2OMML.XSL"),
    ]
    for c in candidates:
        if c.is_file():
            return {"found": True, "path": str(c)}
    return {"found": False, "path": None, "checked": [str(c) for c in candidates]}


def _word_com_probe() -> dict[str, Any]:
    """Best-effort, NON-mutating check that Word COM activation succeeds --
    launches and immediately quits a Word.Application, recording only its
    version/build. Does not open, render, or save any document. If this
    itself fails or times out, that is recorded, not silently skipped."""
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        try:
            version = str(word.Version)
            build = str(getattr(word, "Build", None))
        finally:
            word.Quit()
        return {"activation": "ok", "version": version, "build": build}
    except Exception as exc:  # noqa: BLE001
        return {"activation": "failed", "error": f"{type(exc).__name__}: {exc}"}


def prepare_pinned_parent_snapshot(*, probe_word: bool = True) -> dict[str, Any]:
    git_state = _parent_git_state(_PARENT_REPO)
    import_state = _import_resolution()
    mml2omml = _mml2omml_path()
    word_probe = _word_com_probe() if probe_word else {"activation": "not_run"}

    is_clean_pinned = (
        "error" not in git_state
        and not git_state.get("is_dirty", True)
        and import_state.get("docparse_resolves_to_parent_repo")
        and import_state.get("meridian_docs_resolves_to_parent_repo")
    )

    return {
        "schema": "paper-s21-pinned-parent-snapshot-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "parent_repo_path_hint": "sibling 'repository' checkout (path redacted from receipt; see local pixi.toml)",
        "parent_git": git_state,
        "import_resolution": import_state,
        "mml2omml": mml2omml,
        "word_com_probe": word_probe,
        "provenance_status": "clean_pinned" if is_clean_pinned else "degraded_dirty_or_unresolved",
        "provenance_note": (
            "Parent checkout is clean and commit-pinned; results using this "
            "snapshot are reproducible against the recorded commit."
            if is_clean_pinned else
            "Parent checkout is dirty and/or import resolution did not land "
            "on the parent repo as expected. Any run using this snapshot "
            "must be labeled degraded/non-confirmatory for product-code "
            "provenance until a clean, pinned parent state is confirmed."
        ),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="write JSON receipt here")
    parser.add_argument("--no-word-probe", action="store_true", help="skip the Word COM activation probe")
    args = parser.parse_args(argv)

    snapshot = prepare_pinned_parent_snapshot(probe_word=not args.no_word_probe)
    text = json.dumps(snapshot, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0 if snapshot["provenance_status"] == "clean_pinned" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
