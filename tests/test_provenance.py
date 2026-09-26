"""Unit tests for tools/provenance.py: the shared --provenance-json record
builder/writer used by run_respec_cascade_sweep.py,
run_respec_cascade_baselines.py and run_paper_s7_benchmark.py (wf4_report.txt
section 1.2, gap 2 -- the missing --provenance-json CLI support).

Run with: pixi run python -m pytest tests/test_provenance.py -v
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import provenance  # noqa: E402


def _init_git_repo(root: Path) -> str:
    """A throwaway git repo so _repo_git_commit/_meridian_docs_provenance's
    checkout fallback can be exercised without touching the real repo."""
    has_content = any(p.name != ".git" for p in root.iterdir())
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(root), check=True)
    if not has_content:
        (root / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(root), check=True)
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_sha256_file_matches_hashlib_and_is_none_when_missing(tmp_path: Path):
    path = tmp_path / "x.json"
    path.write_bytes(b"hello world")
    assert provenance._sha256_file(path) == hashlib.sha256(b"hello world").hexdigest()
    assert provenance._sha256_file(tmp_path / "missing.json") is None


def test_repo_git_commit_reads_head_of_a_real_checkout(tmp_path: Path):
    commit = _init_git_repo(tmp_path)
    assert provenance._repo_git_commit(tmp_path) == commit


def test_repo_git_commit_is_none_outside_a_git_repo(tmp_path: Path):
    assert provenance._repo_git_commit(tmp_path) is None


def test_find_git_root_walks_up_to_the_dot_git_directory(tmp_path: Path):
    _init_git_repo(tmp_path)
    nested = tmp_path / "pkg" / "sub"
    nested.mkdir(parents=True)
    assert provenance._find_git_root(nested / "mod.py") == tmp_path


def test_find_git_root_is_none_when_no_ancestor_has_dot_git(tmp_path: Path):
    nested = tmp_path / "pkg"
    nested.mkdir()
    assert provenance._find_git_root(nested / "mod.py") is None


def test_meridian_docs_provenance_falls_back_to_the_checkout_git_head(tmp_path: Path, monkeypatch):
    """No dist-info at all (this paper's actual environment: a plain
    sys.path.insert against a live checkout, confirmed live 2026-09-26) --
    the commit must come from reading that checkout's own HEAD, read-only,
    not from a hardcoded pin."""
    pkg_dir = tmp_path / "meridian_docs"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("__version__ = None\n", encoding="utf-8")
    commit = _init_git_repo(tmp_path)  # commits everything present, including pkg_dir, so the checkout is clean

    import types

    fake_module = types.ModuleType("meridian_docs")
    fake_module.__file__ = str(pkg_dir / "__init__.py")
    monkeypatch.setitem(sys.modules, "meridian_docs", fake_module)

    def _raise_not_found(name):
        raise provenance.importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(provenance.importlib_metadata, "distribution", _raise_not_found)

    info = provenance._meridian_docs_provenance()
    assert info["importable"] is True
    assert info["direct_url_commit"] is None
    assert info["checkout_git_commit"] == commit
    assert info["checkout_git_dirty"] is False
    assert info["checkout_git_root"] == str(tmp_path.resolve())


def test_meridian_docs_provenance_detects_dirty_checkout(tmp_path: Path, monkeypatch):
    _init_git_repo(tmp_path)
    (tmp_path / "b.txt").write_text("uncommitted", encoding="utf-8")
    pkg_dir = tmp_path / "meridian_docs"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    import types

    fake_module = types.ModuleType("meridian_docs")
    fake_module.__file__ = str(pkg_dir / "__init__.py")
    monkeypatch.setitem(sys.modules, "meridian_docs", fake_module)

    def _raise_not_found(name):
        raise provenance.importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(provenance.importlib_metadata, "distribution", _raise_not_found)

    info = provenance._meridian_docs_provenance()
    assert info["checkout_git_dirty"] is True


def test_meridian_docs_provenance_records_import_error_without_raising(monkeypatch):
    monkeypatch.delitem(sys.modules, "meridian_docs", raising=False)

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "meridian_docs":
            raise ModuleNotFoundError("no module named meridian_docs")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    info = provenance._meridian_docs_provenance()
    assert info["importable"] is False
    assert "ModuleNotFoundError" in info["import_error"]


def test_build_provenance_has_the_required_fields_and_hashes_the_manifest(tmp_path: Path):
    manifest = tmp_path / "documents.json"
    manifest.write_text(json.dumps({"documents": []}), encoding="utf-8")
    record = provenance.build_provenance(
        ["run_x.py", "--run-root", "r"], model="claude-sonnet-5", documents_manifest=manifest,
    )
    for key in (
        "schema", "argv", "command_line", "repo_git_commit", "meridian_docs", "model",
        "documents_manifest_path", "documents_manifest_sha256", "schedule_path", "schedule_sha256",
        "hostname", "python_version", "start_time_utc", "end_time_utc", "exit_status",
    ):
        assert key in record, key
    assert record["argv"] == ["run_x.py", "--run-root", "r"]
    assert record["model"] == "claude-sonnet-5"
    assert record["documents_manifest_path"] == str(manifest)
    assert record["documents_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert record["schedule_path"] is None and record["schedule_sha256"] is None
    assert record["end_time_utc"] is None and record["exit_status"] is None


def test_build_provenance_prefers_a_given_schedule_sha_over_hashing_the_file(tmp_path: Path):
    schedule = tmp_path / "anchor-schedules.json"
    schedule.write_bytes(b"{}")
    record = provenance.build_provenance(
        ["x"], schedule_path=schedule, schedule_sha256="deadbeef" * 8,
    )
    assert record["schedule_sha256"] == "deadbeef" * 8
    assert record["schedule_path"] == str(schedule)


def test_build_provenance_hashes_the_schedule_file_when_no_sha_given(tmp_path: Path):
    schedule = tmp_path / "anchor-schedules.json"
    schedule.write_bytes(b"schedule bytes")
    record = provenance.build_provenance(["x"], schedule_path=schedule)
    assert record["schedule_sha256"] == hashlib.sha256(b"schedule bytes").hexdigest()


def test_write_provenance_start_then_end_updates_in_place(tmp_path: Path):
    path = tmp_path / "out" / "provenance.json"
    record = provenance.build_provenance(["x", "--flag"], model="haiku")
    provenance.write_provenance_start(path, record)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["argv"] == ["x", "--flag"]
    assert on_disk["end_time_utc"] is None and on_disk["exit_status"] is None

    provenance.write_provenance_end(path, exit_status=3)
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["exit_status"] == 3
    assert updated["end_time_utc"] is not None
    # everything from the start write is preserved
    assert updated["argv"] == ["x", "--flag"] and updated["model"] == "haiku"


def test_write_provenance_end_is_a_no_op_when_the_start_file_was_never_written(tmp_path: Path):
    path = tmp_path / "never-written.json"
    provenance.write_provenance_end(path, exit_status=2)
    assert not path.exists()
