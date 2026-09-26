"""Shared --provenance-json support for the paper's real-trial launcher
scripts (run_respec_cascade_sweep.py, run_respec_cascade_baselines.py,
run_paper_s7_benchmark.py).

Gap closed (wf4_report.txt section 1.2): none of the three locked real-trial
commands had a `--provenance-json` flag, so a real rerun could start with no
recorded, auditable trail of what was actually launched -- and skipping
provenance recording under deadline pressure "to just get it running" was
flagged as the real corruption risk (the missing flag itself just fails fast
and loud at argparse).

The record is written to `--provenance-json PATH` ONCE, at the start of the
run -- before any trial dispatches, so a crash mid-run still leaves useful
provenance -- via `write_provenance_start`. `write_provenance_end` then
rewrites the SAME file in place with the end time and final exit status once
the run finishes; it reads the start-of-run content back off disk rather
than needing it threaded through the caller, and a crash before it runs
leaves the start-of-run file exactly as written (its guarantees are
unaffected). Neither call is used on a `--check-only` (or archive-only)
invocation -- there is no real run to record.

Content (everything needed to reproduce or audit a run later):
- argv: the exact resolved command line (sys.argv).
- repo_git_commit: this repo's (ooxml-graph-paper) git commit.
- meridian_docs: the installed Meridian Docs package's commit/version, READ
  from the running environment (never hardcoded), so a mismatch against a
  documented pin is detectable. Tries, in order: an importable
  `__version__`, a `direct_url.json` VCS record on its installed
  distribution (pip install from a git URL, editable or not), and -- when
  neither exists but the import resolves straight into a live git checkout,
  which is how this paper's own editable install against the sibling
  `repository` checkout actually works -- that checkout's own
  `git rev-parse HEAD` / `git status --porcelain`, read-only, the same check
  tools/prepare_pinned_parent_snapshot.py's `_parent_git_state` already
  makes for exactly this reason.
- model, documents_manifest_path/_sha256, schedule_path/_sha256 (the two
  respec_cascade scripts only; None where a script has no schedule concept).
- hostname, start_time_utc / end_time_utc, exit_status.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

_THIS_REPO = Path(__file__).resolve().parent.parent


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Read-only git invocation only -- never a mutating subcommand."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _repo_git_commit(repo: Path) -> str | None:
    rc, out, _ = _run_git(["rev-parse", "HEAD"], repo)
    return out if rc == 0 and out else None


def _find_git_root(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _meridian_docs_provenance() -> dict[str, Any]:
    """Best-effort identification of the installed Meridian Docs package's
    commit/version, read from THIS process's environment -- never
    hardcoded, so a mismatch against a documented pin (e.g. the S25/S26
    rerun protocols' pinned commit) is detectable by comparing this field
    against that pin after the fact."""
    info: dict[str, Any] = {
        "importable": False, "module_file": None, "version": None,
        "direct_url_commit": None, "direct_url_vcs_url": None,
        "checkout_git_root": None, "checkout_git_commit": None, "checkout_git_dirty": None,
        "import_error": None,
    }
    try:
        import meridian_docs
    except Exception as exc:  # noqa: BLE001 -- any import failure is recorded, never fatal to provenance
        info["import_error"] = f"{type(exc).__name__}: {exc}"
        return info

    info["importable"] = True
    module_file = getattr(meridian_docs, "__file__", None)
    module_path = Path(module_file).resolve() if module_file else None
    if module_path is not None:
        info["module_file"] = str(module_path)
    info["version"] = getattr(meridian_docs, "__version__", None)

    dist = None
    for dist_name in ("meridian-docs", "meridian_docs"):
        try:
            dist = importlib_metadata.distribution(dist_name)
            break
        except importlib_metadata.PackageNotFoundError:
            continue
        except Exception:  # noqa: BLE001
            continue

    if dist is not None:
        if info["version"] is None:
            info["version"] = dist.version
        try:
            raw = dist.read_text("direct_url.json")
        except Exception:  # noqa: BLE001
            raw = None
        if raw:
            try:
                direct_url = json.loads(raw)
            except json.JSONDecodeError:
                direct_url = {}
            vcs_info = direct_url.get("vcs_info") or {}
            info["direct_url_commit"] = vcs_info.get("commit_id")
            info["direct_url_vcs_url"] = direct_url.get("url")

    # No dist-info VCS record (e.g. a plain sys.path.insert against a live
    # checkout, as this paper's own pixi environment actually does): fall
    # back to reading that checkout's own git HEAD directly, read-only.
    if info["direct_url_commit"] is None and module_path is not None:
        checkout = _find_git_root(module_path)
        if checkout is not None:
            info["checkout_git_root"] = str(checkout)
            commit = _repo_git_commit(checkout)
            info["checkout_git_commit"] = commit
            if commit is not None:
                rc, out, _ = _run_git(["status", "--porcelain"], checkout)
                info["checkout_git_dirty"] = bool(out.strip()) if rc == 0 else None

    return info


def build_provenance(
    argv: list[str], *, model: str | None = None,
    documents_manifest: Path | str | None = None,
    schedule_path: Path | str | None = None, schedule_sha256: str | None = None,
) -> dict[str, Any]:
    """The start-of-run provenance record. `schedule_sha256`, when the
    caller already has it (e.g. run_respec_cascade_sweep.py's
    prepare_schedules already returns one), is used as-is instead of
    re-hashing `schedule_path`; a script with no schedule concept
    (run_paper_s7_benchmark.py) leaves both schedule fields None."""
    documents_manifest = Path(documents_manifest) if documents_manifest is not None else None
    schedule_path = Path(schedule_path) if schedule_path is not None else None
    if schedule_sha256 is None and schedule_path is not None:
        schedule_sha256 = _sha256_file(schedule_path)

    return {
        "schema": "paper-provenance-v1",
        "argv": list(argv),
        "command_line": " ".join([sys.executable, *argv]),
        "repo_git_commit": _repo_git_commit(_THIS_REPO),
        "meridian_docs": _meridian_docs_provenance(),
        "model": model,
        "documents_manifest_path": str(documents_manifest) if documents_manifest is not None else None,
        "documents_manifest_sha256": _sha256_file(documents_manifest) if documents_manifest is not None else None,
        "schedule_path": str(schedule_path) if schedule_path is not None else None,
        "schedule_sha256": schedule_sha256,
        "hostname": platform.node(),
        "python_version": sys.version,
        "start_time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "end_time_utc": None,
        "exit_status": None,
    }


def write_provenance_start(path: Path, record: dict[str, Any]) -> None:
    """Writes `record` to `path` immediately -- before any trial launches --
    so a crash mid-run still leaves useful provenance on disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def write_provenance_end(path: Path, *, exit_status: int) -> None:
    """Rewrites `path` (already written by write_provenance_start) with
    `end_time_utc`/`exit_status` filled in. Reads the existing content back
    off disk rather than requiring the caller to keep the in-memory record
    around. A missing file (the start write never happened, e.g. because
    the run refused to start before reaching it) is a no-op: there is
    nothing to update, and the start write's own guarantees are untouched
    either way."""
    path = Path(path)
    if not path.is_file():
        return
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    record["end_time_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record["exit_status"] = exit_status
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
