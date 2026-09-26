"""Resume, infrastructure and circuit-breaker behavior of
tools/run_paper_s7_benchmark.py (2026-09-25, re-run preparation review
blocker 1 and items 17, 18, 19, 23, and the arm-interleaving minor).

A fake run_trial stands in for the CLI (same convention as
tests/test_run_paper_s7_benchmark.py); grading is stubbed.

Run with: pixi run python -m pytest tests/test_run_paper_s7_benchmark_resume.py -v
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import run_paper_s7_benchmark as s7  # noqa: E402
import usage_cap  # noqa: E402
from claude_pair_runner import CircuitBreaker, CircuitOpenError  # noqa: E402


def _docx(path: Path, text: str = "Body text.") -> Path:
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    return path


_GLOBAL = {"kinds": ["usage_limit"], "scope": "global", "evidence": ["api_error_status 429"]}
# A HARD global kind (never usage_limit/api_rate_limit): the 2026-09-25
# rate-limit handling addition (usage_cap.py) auto-retries only usage_limit/
# api_rate_limit trips; every other global kind keeps the exact prior
# permanent-trip-and-exit-3 behavior, which this constant's tests cover.
_HARD_GLOBAL = {"kinds": ["api_authentication"], "scope": "global", "evidence": ["api_error_status 401"]}
_LOCAL = {"kinds": ["foreign_signal"], "scope": "chain", "evidence": ["killed by signal 9"]}


class FakeCLI:
    """run_trial stand-in. behaviors: {trial_id: dict of result overrides},
    applied on the first `times` calls for that trial id (default: always)."""

    def __init__(self, source: Path, behaviors: dict[str, dict] | None = None, times: int | None = None):
        self.source = source
        self.behaviors = behaviors or {}
        self.times = times
        self.calls: list[str] = []

    def __call__(self, spec, chain_root, *, model):
        self.calls.append(spec.trial_id)
        trial_root = Path(chain_root) / spec.trial_id
        assert not trial_root.exists() or not any(trial_root.iterdir()), "trial directory reused"
        trial_root.mkdir(parents=True, exist_ok=True)
        out = trial_root / "doc.docx"
        shutil.copyfile(self.source, out)
        result = {
            "trial_id": spec.trial_id, "doc_label": spec.doc_label, "arm": spec.arm, "direction": spec.direction,
            "family": spec.family, "pair_index": spec.pair_index, "timed_out": False, "returncode": 0,
            "docx_changed": True, "trial_root": str(trial_root), "output_docx_path": str(out),
            "claude_json_result": {"result": "done"}, "stdout_tail": "", "stderr_tail": "", "infra_signature": None,
        }
        n_seen = self.calls.count(spec.trial_id)
        if spec.trial_id in self.behaviors and (self.times is None or n_seen <= self.times):
            result.update(self.behaviors[spec.trial_id])
        return result


@pytest.fixture
def graded(monkeypatch):
    monkeypatch.setattr(s7, "_grade_forward", lambda *a, **k: {"verdict": "pass", "checks": {}})
    monkeypatch.setattr(s7, "_grade_inverse", lambda *a, **k: {"verdict": "pass", "checks": {}})
    return monkeypatch


def _run(tmp_path: Path, **kw) -> dict:
    return s7.run_chain("bibliography", "doc-a", tmp_path / "in.docx", "control", kw.pop("k", 2), "sonnet",
                        tmp_path / "run-root", word_receipts_enabled=False, **kw)


def test_resume_returns_a_timed_out_chain_unchanged_and_runs_nothing(tmp_path, graded):
    """Blocker 1: a relaunch (pod-loss recovery, runbook resume) must never
    re-run a timed-out chain -- that would give the arm a second attempt."""
    _docx(tmp_path / "in.docx")
    cli = FakeCLI(tmp_path / "in.docx", {"p1-forward": {"timed_out": True, "returncode": None, "docx_changed": False}})
    graded.setattr(s7, "run_trial", cli)
    first = _run(tmp_path)
    assert first["status"] == s7.STATUS_BLOCKED_TIMEOUT
    n_calls = len(cli.calls)
    second = _run(tmp_path)
    assert second == first and len(cli.calls) == n_calls
    ledger = json.loads((tmp_path / "run-root" / "_chain_attempts" / f"{first['chain_id']}.json").read_text())
    assert len(ledger["attempts"]) == 1 and ledger["attempts"][0]["ended_status"] == "blocked_timeout"


def test_forward_cli_error_without_signature_is_its_own_trusted_status(tmp_path, graded):
    _docx(tmp_path / "in.docx")
    cli = FakeCLI(tmp_path / "in.docx", {"p0-forward": {"returncode": 1, "docx_changed": False,
                                                        "claude_json_result": {"subtype": "error_max_turns", "is_error": True}}})
    graded.setattr(s7, "run_trial", cli)
    first = _run(tmp_path, k=1)
    assert first["status"] == s7.STATUS_BLOCKED_FORWARD_FAILED
    assert _run(tmp_path, k=1) == first and cli.calls == ["p0-forward"]


def test_unreadable_next_input_is_trusted_on_resume(tmp_path, graded):
    _docx(tmp_path / "in.docx")
    corrupt = tmp_path / "corrupt.docx"
    corrupt.write_bytes(b"not a zip")

    class CorruptInverse(FakeCLI):
        def __call__(self, spec, chain_root, *, model):
            result = super().__call__(spec, chain_root, model=model)
            if spec.trial_id == "p0-inverse":
                shutil.copyfile(corrupt, result["output_docx_path"])
            return result

    cli = CorruptInverse(tmp_path / "in.docx")
    graded.setattr(s7, "run_trial", cli)
    first = _run(tmp_path)
    assert first["status"] == s7.STATUS_BLOCKED_UNREADABLE_INPUT
    assert "corrupted/unreadable" in first["pairs"][-1]["blocked_reason"]
    assert _run(tmp_path) == first and cli.calls == ["p0-forward", "p0-inverse"]


def test_unresolvable_forward_marker_is_its_own_trusted_status(tmp_path, graded):
    _docx(tmp_path / "in.docx")
    cli = FakeCLI(tmp_path / "in.docx")
    graded.setattr(s7, "run_trial", cli)
    graded.setattr(s7, "resolve_para_id_by_marker_text", lambda path, marker: {"found": False, "reason": "gone"})
    anchor = {"anchor_para_id": "P1", "anchor_text_snippet": "Body", "anchor_full_text": "Body text."}
    first = s7.run_chain("caption", "doc-a", tmp_path / "in.docx", "control", 1, "sonnet", tmp_path / "run-root",
                         word_receipts_enabled=False, anchor_or_plan_override=anchor)
    assert first["status"] == s7.STATUS_BLOCKED_INVERSE_UNRESOLVABLE


def test_infrastructure_signature_makes_the_chain_infra_blocked_and_it_is_re_run(tmp_path, graded):
    """Items 18 and 23: the chain stops at the signature, is not trusted, and
    the re-run starts from an empty chain root (old one in the attic)."""
    _docx(tmp_path / "in.docx")
    cli = FakeCLI(tmp_path / "in.docx", {"p0-inverse": {"infra_signature": _LOCAL}}, times=1)
    graded.setattr(s7, "run_trial", cli)
    first = _run(tmp_path)
    assert first["status"] == s7.STATUS_INFRA_BLOCKED
    assert first["infra_signature"]["trial_id"] == "p0-inverse" and first["infra_signature"]["scope"] == "chain"
    assert cli.calls == ["p0-forward", "p0-inverse"]  # stopped at the signature

    second = _run(tmp_path)
    assert second["status"] == "completed" and second["attempt"] == 2
    assert cli.calls[2:] == ["p0-forward", "p0-inverse", "p1-forward", "p1-inverse"]
    attic = tmp_path / "run-root" / "attic" / first["chain_id"]
    [moved] = list(attic.iterdir())
    assert json.loads((moved / "chain-result.json").read_text())["status"] == s7.STATUS_INFRA_BLOCKED


def test_signature_on_a_trial_that_otherwise_passed_still_blocks(tmp_path, graded):
    """Item 23: whatever the trial's own outcome."""
    _docx(tmp_path / "in.docx")
    graded.setattr(s7, "run_trial", FakeCLI(tmp_path / "in.docx", {"p0-forward": {"infra_signature": _LOCAL}}))
    assert _run(tmp_path, k=1)["status"] == s7.STATUS_INFRA_BLOCKED


def test_rerun_limit_excludes_after_two_chain_scope_infra_attempts(tmp_path, graded):
    _docx(tmp_path / "in.docx")
    cli = FakeCLI(tmp_path / "in.docx", {"p0-forward": {"infra_signature": _LOCAL}})
    graded.setattr(s7, "run_trial", cli)
    assert _run(tmp_path, max_chain_attempts=2)["status"] == s7.STATUS_INFRA_BLOCKED
    assert _run(tmp_path, max_chain_attempts=2)["status"] == s7.STATUS_INFRA_BLOCKED
    third = _run(tmp_path, max_chain_attempts=2)
    assert third["status"] == s7.STATUS_INFRA_EXCLUDED and len(cli.calls) == 2


def test_legacy_blocked_checkpoint_is_not_trusted(tmp_path, graded):
    """A "blocked" chain written before 2026-09-25 has no recorded cause, so
    it is re-run as before (moved to the attic first)."""
    _docx(tmp_path / "in.docx")
    cli = FakeCLI(tmp_path / "in.docx")
    graded.setattr(s7, "run_trial", cli)
    chain_root = tmp_path / "run-root" / "doc-a-bibliography-control-k1"
    chain_root.mkdir(parents=True)
    (chain_root / "chain-result.json").write_text(json.dumps({"status": "blocked", "pairs": []}))
    assert _run(tmp_path, k=1)["status"] == "completed"
    assert (tmp_path / "run-root" / "attic" / "doc-a-bibliography-control-k1").is_dir()


def test_global_signature_trips_the_breaker_and_stops_other_chains(tmp_path, graded):
    """Item 17: the first global signature opens the sweep-wide breaker; no
    new trial starts; neither attempt counts toward the rerun limit."""
    _docx(tmp_path / "in.docx")
    cli = FakeCLI(tmp_path / "in.docx", {"p0-forward": {"infra_signature": _GLOBAL}})
    graded.setattr(s7, "run_trial", cli)
    breaker = CircuitBreaker()
    first = _run(tmp_path, k=1, circuit_breaker=breaker)
    assert first["status"] == s7.STATUS_INFRA_BLOCKED and breaker.is_open
    with pytest.raises(CircuitOpenError):
        s7.run_chain("bibliography", "doc-b", tmp_path / "in.docx", "control", 1, "sonnet", tmp_path / "run-root",
                     word_receipts_enabled=False, circuit_breaker=breaker)
    assert cli.calls == ["p0-forward"]
    run_root = tmp_path / "run-root"
    for chain_id in ("doc-a-bibliography-control-k1", "doc-b-bibliography-control-k1"):
        ledger = json.loads((run_root / "_chain_attempts" / f"{chain_id}.json").read_text())
        assert ledger["attempts"][-1]["counts_toward_limit"] is False


def _manifest(tmp_path: Path, docs: list[str]) -> Path:
    rows = []
    for label in docs:
        path = _docx(tmp_path / f"{label}.docx", f"Text of {label}.")
        rows.append({"doc_label": label, "docx_path": str(path), "s7_split": "primary_holdout",
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"documents": rows}))
    return manifest


def test_corpus_slice_interleaves_arms_per_document_and_records_a_hard_breaker_trip(tmp_path, graded):
    """A HARD global kind (api_authentication) still trips the breaker
    permanently and stops the slice -- unchanged by the rate-limit handling
    addition. See test_corpus_slice_auto_retries_and_resumes_after_a_usage_cap
    below for the NEW usage_limit/api_rate_limit auto-retry behavior."""
    manifest = _manifest(tmp_path, ["d1", "d2", "d3"])
    source = tmp_path / "d1.docx"
    graded.setattr(s7, "run_trial", FakeCLI(source, {"p0-forward": {"infra_signature": _HARD_GLOBAL}}, times=1))
    out = s7.run_corpus_slice(manifest, "primary_holdout", ("bibliography",), (1,), "sonnet", tmp_path / "rr",
                              max_workers=1, word_receipts_enabled=False, arm_order_seed=7)
    order = out["submission_order"]
    assert [row[0] for row in order] == ["d1", "d1", "d2", "d2", "d3", "d3"]
    assert all({order[i][3], order[i + 1][3]} == {"control", "treatment"} for i in range(0, 6, 2))
    assert out["circuit_breaker"]["open"] is True
    assert len(out["usage_cap_rounds"]) == 1 and out["usage_cap_rounds"][0]["usage_cap_round"] is False
    statuses = sorted(c["status"] for c in out["chains"])
    assert statuses.count(s7.STATUS_INFRA_BLOCKED) == 1
    assert statuses.count(s7.STATUS_ABORTED_CIRCUIT_OPEN) == 5
    assert json.loads((tmp_path / "rr" / "slice-manifest.json").read_text())["arm_order_seed"] == 7


def test_corpus_slice_auto_retries_and_resumes_after_a_usage_cap(tmp_path, graded):
    """Rate-limit handling (2026-09-25): a usage_limit trip pauses new
    dispatch, then resumes automatically within this one call to
    run_corpus_slice -- no relaunch needed, unlike the hard-kind case above.
    `times=1` on the FakeCLI behavior means only the very first "p0-forward"
    call across the whole slice sees the cap, simulating a transient,
    one-shot rate-limit/usage-cap event that clears by the retry round.
    Uses a fake, injected clock/sleep (task item 5: no real sleeping)."""
    manifest = _manifest(tmp_path, ["d1", "d2", "d3"])
    source = tmp_path / "d1.docx"
    graded.setattr(s7, "run_trial", FakeCLI(source, {"p0-forward": {"infra_signature": _GLOBAL}}, times=1))
    sleeps: list[float] = []
    pause_controller = s7.UsagePauseController(sleep=sleeps.append)
    out = s7.run_corpus_slice(manifest, "primary_holdout", ("bibliography",), (1,), "sonnet", tmp_path / "rr",
                              max_workers=1, word_receipts_enabled=False, arm_order_seed=7,
                              pause_controller=pause_controller)
    assert len(out["usage_cap_rounds"]) == 2
    assert out["usage_cap_rounds"][0]["usage_cap_round"] is True and out["usage_cap_rounds"][0]["retried"] == 6
    assert out["usage_cap_rounds"][1]["usage_cap_round"] is False
    assert out["circuit_breaker"]["open"] is False
    statuses = sorted(c["status"] for c in out["chains"])
    assert statuses.count("completed") == 6
    assert sleeps  # waited via the injected sleep, never a real one
    assert pause_controller.state()["resume_count"] == 1
    assert out["usage_cap_status"]["pause_episodes"] == 0  # reset by mark_success after the clean round


def test_arm_order_is_seeded_and_reproducible():
    assert s7.arm_order(None, "x") == ("control", "treatment")
    orders = {s7.arm_order(20260925, f"doc{i}") for i in range(40)}
    assert orders == {("control", "treatment"), ("treatment", "control")}
    assert all(s7.arm_order(1, f"k{i}") == s7.arm_order(1, f"k{i}") for i in range(10))


def test_main_exits_3_when_the_breaker_opened(tmp_path, graded):
    """_HARD_GLOBAL, not _GLOBAL: this behavior has no `times` limit (every
    "p0-forward" call is overridden), so a usage_limit/api_rate_limit kind
    here would retry forever (by design -- see usage_cap.py's module
    docstring); a hard kind still exits 3 on the first trip, as before."""
    manifest = _manifest(tmp_path, ["d1"])
    graded.setattr(s7, "run_trial", FakeCLI(tmp_path / "d1.docx", {"p0-forward": {"infra_signature": _HARD_GLOBAL}}))
    code = s7.main(["--corpus-manifest", str(manifest), "--split", "primary_holdout", "--families", "bibliography",
                    "--run-root", str(tmp_path / "rr"), "--no-word-receipts", "--max-workers", "1"])
    assert code == 3


def test_main_bounds_usage_cap_retries_and_still_exits_3_if_never_resolved(tmp_path, graded, monkeypatch):
    """A persistent usage_limit (never clears) must not hang main() forever:
    --max-usage-cap-rounds bounds it, and it still exits 3 with the last
    round's breaker left open, so the operator sees the same signal a hard
    trip gives. The default (no flag) is unbounded, matching the task's
    "resumes automatically, no relaunch needed" -- this test only exercises
    the bound, and stubs out real sleeping so it cannot hang."""
    manifest = _manifest(tmp_path, ["d1"])
    graded.setattr(s7, "run_trial", FakeCLI(tmp_path / "d1.docx", {"p0-forward": {"infra_signature": _GLOBAL}}))
    monkeypatch.setattr(usage_cap.time, "sleep", lambda seconds: None)
    code = s7.main(["--corpus-manifest", str(manifest), "--split", "primary_holdout", "--families", "bibliography",
                    "--run-root", str(tmp_path / "rr"), "--no-word-receipts", "--max-workers", "1",
                    "--max-usage-cap-rounds", "2"])
    assert code == 3
    manifest_out = json.loads((tmp_path / "rr" / "slice-manifest.json").read_text())
    assert len(manifest_out["usage_cap_rounds"]) == 2
    assert all(r["usage_cap_round"] for r in manifest_out["usage_cap_rounds"])


def test_check_only_verifies_hashes_and_plans_without_trials(tmp_path, graded):
    manifest = _manifest(tmp_path, ["d1", "d2"])
    cli = FakeCLI(tmp_path / "d1.docx")
    graded.setattr(s7, "run_trial", cli)
    code = s7.main(["--corpus-manifest", str(manifest), "--split", "primary_holdout", "--families", "bibliography",
                    "--run-root", str(tmp_path / "rr"), "--check-only"])
    assert code == 0 and cli.calls == []
    report = json.loads((tmp_path / "rr" / "check-report.json").read_text())
    assert report["ok"] is True and all(r["sha256_ok"] for r in report["documents"])
    assert (tmp_path / "rr" / "check-report.json.sha256").is_file()

    (tmp_path / "d2.docx").write_bytes(b"changed")
    code = s7.main(["--corpus-manifest", str(manifest), "--split", "primary_holdout", "--families", "bibliography",
                    "--run-root", str(tmp_path / "rr"), "--check-only"])
    assert code == 2 and cli.calls == []
    # an inapplicable family also fails the check
    code = s7.main(["--corpus-manifest", str(manifest), "--split", "primary_holdout", "--families", "section_reorder",
                    "--run-root", str(tmp_path / "rr2"), "--check-only"])
    assert code == 2


# ---------------------------------------------------------------------------
# --provenance-json (wf4_report.txt section 1.2, gap 2). This script has no
# schedule concept (that's the two respec_cascade scripts only), so
# schedule_path/schedule_sha256 stay None here.
# ---------------------------------------------------------------------------

_PROVENANCE_KEYS = {
    "schema", "argv", "command_line", "repo_git_commit", "meridian_docs", "model",
    "documents_manifest_path", "documents_manifest_sha256", "schedule_path", "schedule_sha256",
    "hostname", "python_version", "start_time_utc", "end_time_utc", "exit_status",
}


def test_check_only_never_writes_provenance(tmp_path, graded):
    manifest = _manifest(tmp_path, ["d1"])
    graded.setattr(s7, "run_trial", FakeCLI(tmp_path / "d1.docx"))
    prov = tmp_path / "provenance.json"
    code = s7.main(["--corpus-manifest", str(manifest), "--split", "primary_holdout", "--families", "bibliography",
                    "--run-root", str(tmp_path / "rr"), "--check-only", "--provenance-json", str(prov)])
    assert code == 0
    assert not prov.exists()


def test_real_run_writes_provenance_before_any_trial_and_updates_it_at_the_end(tmp_path, graded):
    manifest = _manifest(tmp_path, ["d1", "d2"])
    prov = tmp_path / "logs" / "provenance-s7.json"
    seen: dict = {}

    class SpyingCLI(FakeCLI):
        def __call__(self, spec, chain_root, *, model):
            if not seen:
                seen["exists"] = prov.is_file()
                if prov.is_file():
                    seen["record"] = json.loads(prov.read_text(encoding="utf-8"))
            return super().__call__(spec, chain_root, model=model)

    cli = SpyingCLI(tmp_path / "d1.docx")
    graded.setattr(s7, "run_trial", cli)
    code = s7.main(["--corpus-manifest", str(manifest), "--split", "primary_holdout", "--families", "bibliography",
                    "--run-root", str(tmp_path / "rr"), "--no-word-receipts", "--max-workers", "1",
                    "--model", "claude-sonnet-5", "--provenance-json", str(prov)])
    assert code == 0

    assert seen["exists"] is True  # written before the first trial dispatched
    start_record = seen["record"]
    assert set(start_record) == _PROVENANCE_KEYS
    assert start_record["model"] == "claude-sonnet-5"
    assert start_record["documents_manifest_path"] == str(manifest)
    assert start_record["documents_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert start_record["schedule_path"] is None and start_record["schedule_sha256"] is None  # no schedule concept here
    assert start_record["repo_git_commit"]
    assert start_record["end_time_utc"] is None and start_record["exit_status"] is None

    final_record = json.loads(prov.read_text(encoding="utf-8"))
    assert final_record["exit_status"] == 0
    assert final_record["end_time_utc"] is not None
    assert final_record["argv"] == start_record["argv"]  # unchanged by the end update


def test_main_exits_3_updates_provenance_with_that_exit_status(tmp_path, graded):
    manifest = _manifest(tmp_path, ["d1"])
    graded.setattr(s7, "run_trial", FakeCLI(tmp_path / "d1.docx", {"p0-forward": {"infra_signature": _HARD_GLOBAL}}))
    prov = tmp_path / "provenance.json"
    code = s7.main(["--corpus-manifest", str(manifest), "--split", "primary_holdout", "--families", "bibliography",
                    "--run-root", str(tmp_path / "rr"), "--no-word-receipts", "--max-workers", "1",
                    "--provenance-json", str(prov)])
    assert code == 3
    record = json.loads(prov.read_text(encoding="utf-8"))
    assert record["exit_status"] == 3 and record["end_time_utc"] is not None
