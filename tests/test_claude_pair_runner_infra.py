"""Tests for claude_pair_runner's infrastructure signature, render-gate
capture, trial-directory attic, circuit breaker and per-chain attempt ledger
(2026-09-25, re-run preparation review items 8, 17, 18, 24 and blocker 1).

No real `claude -p` subprocess is started: subprocess.run is faked.

Run with: pixi run python -m pytest tests/test_claude_pair_runner_infra.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import claude_pair_runner as cpr  # noqa: E402
from docx_trial_broker import TrialSpec  # noqa: E402


# ---------------------------------------------------------------------------
# classify_infra_signature: the pinned list
# ---------------------------------------------------------------------------

def test_infra_kinds_and_scopes_are_pinned():
    """Changing the signature list after a protocol lock is a deviation: this
    test pins it."""
    assert cpr.INFRA_KIND_SCOPES == {
        "api_rate_limit": "global", "usage_limit": "global", "api_overloaded": "global",
        "api_authentication": "global", "api_server_error": "global", "api_connection": "global",
        "nonzero_exit_no_json": "chain", "foreign_signal": "chain", "process_crash_ntstatus": "chain",
        "mcp_load_failure": "chain",
    }
    assert [kind for kind, _ in cpr.INFRA_ERROR_TEXT_PATTERNS] == [
        "api_rate_limit", "usage_limit", "api_overloaded", "api_authentication", "api_server_error", "api_connection",
    ]
    assert [kind for kind, _ in cpr.RENDER_GATE_ERROR_PATTERNS] == [
        "render_gate_failed", "render_gate_unavailable", "render_gate_timeout",
    ]


def _trial(**kw) -> dict:
    base = {"arm": "control", "timed_out": False, "returncode": 0, "claude_json_result": {
        "type": "result", "subtype": "success", "is_error": False, "result": "Done."}, "stderr_tail": ""}
    base.update(kw)
    return base


def _api_error(text: str, status: int | None = None) -> dict:
    return {"type": "result", "subtype": "success", "is_error": True, "result": text, "api_error_status": status}


@pytest.mark.parametrize(("result", "kind"), [
    (_api_error("API Error: 429 {\"type\":\"error\",\"error\":{\"type\":\"rate_limit_error\"}}", 429), "api_rate_limit"),
    (_api_error("API Error: 529 {\"type\":\"error\",\"error\":{\"type\":\"overloaded_error\"}}", 529), "api_overloaded"),
    (_api_error("API Error: 401 Invalid API key · Please run /login", 401), "api_authentication"),
    (_api_error("API Error: 500 {\"type\":\"error\",\"error\":{\"type\":\"api_error\"}}", 500), "api_server_error"),
    (_api_error("You've hit your limit · resets 3pm"), "usage_limit"),
    (_api_error("API Error: Connection error."), "api_connection"),
])
def test_cli_api_errors_are_global_infrastructure(result, kind):
    signature = cpr.classify_infra_signature(_trial(returncode=1, claude_json_result=result))
    assert signature is not None and kind in signature["kinds"] and signature["scope"] == "global"


@pytest.mark.parametrize("result", [
    _api_error("Prompt is too long", 400),  # context overflow: task-driven
    _api_error("API Error: 400 due to tool use concurrency issues.", 400),
    {"type": "result", "subtype": "error_max_turns", "is_error": True},
    {"type": "result", "subtype": "error_during_execution", "is_error": True},
])
def test_task_driven_cli_errors_are_not_infrastructure(result):
    assert cpr.classify_infra_signature(_trial(returncode=1, claude_json_result=result)) is None


def test_agent_text_that_looks_like_a_limit_is_never_a_signature_but_is_recorded():
    trial = _trial(claude_json_result={"type": "result", "subtype": "success", "is_error": False,
                                       "result": "API Error: 529 overloaded_error -- You've hit your limit"})
    assert cpr.classify_infra_signature(trial) is None
    assert set(cpr.unconfirmed_infra_text(trial)) >= {"api_overloaded", "usage_limit"}


def test_harness_timeout_is_not_infrastructure():
    assert cpr.classify_infra_signature(_trial(timed_out=True, returncode=None, claude_json_result=None)) is None


def test_process_level_failures():
    no_json = cpr.classify_infra_signature(_trial(returncode=1, claude_json_result=None))
    assert no_json["kinds"] == ["nonzero_exit_no_json"] and no_json["scope"] == "chain"
    assert cpr.classify_infra_signature(_trial(returncode=-9, claude_json_result=None))["kinds"][0] == "foreign_signal"
    dll = cpr.classify_infra_signature(_trial(returncode=0xC0000142, claude_json_result=None))
    assert dll["kinds"] == ["process_crash_ntstatus"]
    # a non-zero exit WITH a JSON result that is not an API error is the agent's
    assert cpr.classify_infra_signature(_trial(returncode=1)) is None


def test_stderr_is_read_only_when_the_run_did_not_end_cleanly():
    chatter = "Connection error, retrying... ECONNRESET"
    assert cpr.classify_infra_signature(_trial(stderr_tail=chatter)) is None
    failed = cpr.classify_infra_signature(_trial(returncode=1, claude_json_result=None, stderr_tail="rate_limit_error"))
    assert set(failed["kinds"]) == {"api_rate_limit", "nonzero_exit_no_json"} and failed["scope"] == "global"


def _init(status: str | None, tools: list[str]) -> dict:
    servers = [] if status is None else [{"name": "meridian-docs-pilot", "status": status}]
    return {"type": "system", "subtype": "init", "mcp_servers": servers, "tools": tools}


def test_mcp_load_failure_comes_only_from_the_init_record():
    tool = "mcp__meridian-docs-pilot__move_section"
    failed = _trial(arm="treatment", treatment_tool="move_section", claude_init_record=_init("failed", ["Read"]))
    assert cpr.classify_infra_signature(failed)["kinds"] == ["mcp_load_failure"]
    missing = _trial(arm="treatment", treatment_tool="move_section", claude_init_record=_init(None, ["Read"]))
    assert cpr.classify_infra_signature(missing)["kinds"] == ["mcp_load_failure"]
    ok = _trial(arm="treatment", treatment_tool="move_section", claude_init_record=_init("connected", ["Read", tool]))
    assert cpr.classify_infra_signature(ok) is None
    # the agent saying its tool is missing is not evidence
    claims = _trial(arm="treatment", treatment_tool="move_section", claude_init_record=_init("connected", ["Read", tool]),
                    claude_json_result={"type": "result", "subtype": "success", "is_error": False,
                                        "result": "The tool doesn't exist in my toolset"})
    assert cpr.classify_infra_signature(claims) is None
    # control has no MCP server to load
    assert cpr.classify_infra_signature(_trial(claude_init_record=_init(None, ["Read"]))) is None


# ---------------------------------------------------------------------------
# run_trial with a faked CLI
# ---------------------------------------------------------------------------

def _spec(tmp_path: Path, arm: str = "treatment", tool: str = "insert_table") -> TrialSpec:
    input_docx = tmp_path / "input.docx"
    input_docx.write_bytes(b"fake-docx-bytes")
    return TrialSpec(
        trial_id="t1", doc_label="doc", arm=arm, direction="forward", family="table_structural",
        input_docx=input_docx, marker_text="marker", treatment_tool=tool, treatment_args={}, prompt="do it",
    )


def _verbose_stdout(init: dict, result: dict, extra: list[dict] | None = None) -> str:
    return json.dumps([init, *(extra or []), result])


def test_verbose_output_keeps_the_result_record_and_the_init_record(tmp_path, monkeypatch):
    spec = _spec(tmp_path)
    result = {"type": "result", "subtype": "success", "is_error": False, "result": "Done.", "session_id": "s1"}
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        (tmp_path / "runs" / "t1" / "doc.docx").write_bytes(b"edited")
        init = _init("connected", ["Read", "mcp__meridian-docs-pilot__insert_table"])
        return subprocess.CompletedProcess(cmd, 0, stdout=_verbose_stdout(init, result), stderr="")

    monkeypatch.setattr(cpr.subprocess, "run", fake_run)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-config"))
    out = cpr.run_trial(spec, tmp_path / "runs")
    assert "--verbose" in captured["cmd"]
    assert out["claude_json_result"] == result
    assert out["claude_init_record"]["mcp_servers"] == [{"name": "meridian-docs-pilot", "status": "connected"}]
    assert out["infra_signature"] is None and out["mcp_flake_retry_triggered"] is False
    assert json.loads(out["stdout_tail"]) == result  # same meaning as before --verbose
    assert out["session_id"] == "s1" and out["session_transcript_path"] is None
    assert (tmp_path / "runs" / "t1" / "cli-messages.json").is_file()  # fallback archive of the messages


def test_mcp_retry_fires_on_init_record_evidence_and_uses_a_fresh_directory(tmp_path, monkeypatch):
    spec = _spec(tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(1)
        trial_root = Path(kwargs["cwd"])
        (trial_root / "scratch" / "leftover.txt").write_text(f"attempt {len(calls)}")
        if len(calls) == 1:
            init = _init("failed", ["Read"])
        else:
            init = _init("connected", ["Read", "mcp__meridian-docs-pilot__insert_table"])
            (trial_root / "doc.docx").write_bytes(b"edited")
        result = {"type": "result", "subtype": "success", "is_error": False, "result": "ok"}
        return subprocess.CompletedProcess(cmd, 0, stdout=_verbose_stdout(init, result), stderr="")

    monkeypatch.setattr(cpr.subprocess, "run", fake_run)
    out = cpr.run_trial(spec, tmp_path / "runs")
    assert len(calls) == 2 and out["mcp_flake_retry_triggered"] is True
    assert out["docx_changed"] is True and out["infra_signature"] is None
    assert len(out["attic_moves"]) == 1
    attic = Path(out["attic_moves"][0])
    assert (attic / "scratch" / "leftover.txt").read_text() == "attempt 1"
    assert (tmp_path / "runs" / "t1" / "scratch" / "leftover.txt").read_text() == "attempt 2"


def test_no_mcp_retry_when_the_init_record_shows_the_server_connected(tmp_path, monkeypatch):
    """With the init record available, the agent's own wording never triggers
    the retry (review item 8)."""
    spec = _spec(tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(1)
        init = _init("connected", ["Read", "mcp__meridian-docs-pilot__insert_table"])
        result = {"type": "result", "subtype": "success", "is_error": False,
                  "result": "That tool doesn't exist in my toolset; no way to modify or save."}
        return subprocess.CompletedProcess(cmd, 0, stdout=_verbose_stdout(init, result), stderr="")

    monkeypatch.setattr(cpr.subprocess, "run", fake_run)
    out = cpr.run_trial(spec, tmp_path / "runs")
    assert len(calls) == 1 and out["mcp_flake_retry_triggered"] is False and out["infra_signature"] is None


def test_persistent_mcp_load_failure_is_an_infrastructure_signature(tmp_path, monkeypatch):
    spec = _spec(tmp_path)

    def fake_run(cmd, **kwargs):
        result = {"type": "result", "subtype": "success", "is_error": False, "result": "no tool"}
        return subprocess.CompletedProcess(cmd, 0, stdout=_verbose_stdout(_init("failed", ["Read"]), result), stderr="")

    monkeypatch.setattr(cpr.subprocess, "run", fake_run)
    out = cpr.run_trial(spec, tmp_path / "runs")
    assert out["mcp_flake_retry_triggered"] is True
    assert out["infra_signature"]["kinds"] == ["mcp_load_failure"]


def test_a_rerun_never_reuses_a_non_empty_trial_directory(tmp_path, monkeypatch):
    """Review item 18: a relaunch's trial must not see the previous attempt's
    files; they are moved to <runs_root>/attic/<trial_id>/<timestamp>/."""
    spec = _spec(tmp_path, arm="control")
    stale = tmp_path / "runs" / "t1"
    (stale / "scratch").mkdir(parents=True)
    (stale / "scratch" / "old-extract.xml").write_text("stale")
    (stale / "step-result.json").write_text("{}")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["files"] = sorted(p.name for p in Path(kwargs["cwd"]).rglob("*"))
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    monkeypatch.setattr(cpr.subprocess, "run", fake_run)
    out = cpr.run_trial(spec, tmp_path / "runs")
    assert "old-extract.xml" not in seen["files"] and "step-result.json" not in seen["files"]
    attic = Path(out["attic_moves"][0])
    assert attic.parent == tmp_path / "runs" / "attic" / "t1"
    assert (attic / "scratch" / "old-extract.xml").read_text() == "stale"


def _transcript_lines(tool_name: str, text: str) -> list[dict]:
    return [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": tool_name, "input": {}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_1", "is_error": True,
                                                  "content": [{"type": "text", "text": text}]}]}},
    ]


_RENDER_TIMEOUT_TEXT = json.dumps({
    "error": "render verification failed: soffice --convert-to pdf exceeded its 90s bound and was terminated",
    "render_status": "failed", "file_restored": True,
})


def test_render_gate_error_text_is_captured_from_the_session_transcript(tmp_path, monkeypatch):
    """Review item 24: the render-gate error lives only in the CLI session
    transcript; it is found by session id, copied beside the trial, and its
    Meridian tool results scanned."""
    spec = _spec(tmp_path)
    config = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    trial_root = tmp_path / "runs" / "t1"
    import re as _re

    transcript_dir = config / "projects" / _re.sub(r"[^A-Za-z0-9]", "-", str(trial_root))
    transcript_dir.mkdir(parents=True)
    lines = _transcript_lines("mcp__meridian-docs-pilot__insert_table", _RENDER_TIMEOUT_TEXT)
    (transcript_dir / "sess-123.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

    def fake_run(cmd, **kwargs):
        result = {"type": "result", "subtype": "success", "is_error": False, "result": "failed", "session_id": "sess-123"}
        init = _init("connected", ["Read", "mcp__meridian-docs-pilot__insert_table"])
        return subprocess.CompletedProcess(cmd, 0, stdout=_verbose_stdout(init, result), stderr="")

    monkeypatch.setattr(cpr.subprocess, "run", fake_run)
    out = cpr.run_trial(spec, tmp_path / "runs")
    assert out["render_gate_timeout"] is True
    [error] = out["render_gate_errors"]
    assert error["tool"] == "mcp__meridian-docs-pilot__insert_table"
    assert set(error["kinds"]) == {"render_gate_failed", "render_gate_timeout"}
    assert "exceeded its 90s bound" in error["text"]
    assert Path(out["session_transcript_path"]).read_text(encoding="utf-8").count("toolu_1") == 2


def test_render_gate_text_outside_a_meridian_tool_result_is_ignored():
    """A control agent's own Bash output (or any non-Meridian tool) cannot
    produce a render-gate record."""
    assert cpr.extract_render_gate_errors(_transcript_lines("Bash", _RENDER_TIMEOUT_TEXT)) == []
    found = cpr.extract_render_gate_errors(_transcript_lines(
        "mcp__meridian-docs-pilot__insert_equation",
        "render verification unavailable in this environment (no backend) -- failing closed",
    ))
    assert found[0]["kinds"] == ["render_gate_unavailable"]


def test_render_gate_errors_fall_back_to_verbose_messages_when_no_transcript(tmp_path, monkeypatch):
    spec = _spec(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty-config"))

    def fake_run(cmd, **kwargs):
        result = {"type": "result", "subtype": "success", "is_error": False, "result": "x", "session_id": "nope"}
        init = _init("connected", ["Read", "mcp__meridian-docs-pilot__insert_table"])
        extra = _transcript_lines("mcp__meridian-docs-pilot__insert_table", _RENDER_TIMEOUT_TEXT)
        return subprocess.CompletedProcess(cmd, 0, stdout=_verbose_stdout(init, result, extra), stderr="")

    monkeypatch.setattr(cpr.subprocess, "run", fake_run)
    out = cpr.run_trial(spec, tmp_path / "runs")
    assert out["render_gate_timeout"] is True and out["session_transcript_path"] is None


# ---------------------------------------------------------------------------
# Circuit breaker and attempt ledger
# ---------------------------------------------------------------------------

def test_circuit_breaker_trips_only_on_global_signatures():
    breaker = cpr.CircuitBreaker()
    local = {"infra_signature": {"kinds": ["foreign_signal"], "scope": "chain", "evidence": []}}
    assert cpr.infra_signature_of(local, breaker, "a") is not None
    assert breaker.is_open is False
    breaker.check("next")  # no raise
    global_ = {"infra_signature": {"kinds": ["usage_limit"], "scope": "global", "evidence": []}}
    cpr.infra_signature_of(global_, breaker, "chain-x/p0-forward")
    assert breaker.is_open is True
    assert breaker.state()["tripped"]["source"] == "chain-x/p0-forward"
    with pytest.raises(cpr.CircuitOpenError):
        breaker.check("chain-y/p0-forward")


def test_attempt_ledger_lives_outside_the_chain_root_and_moves_stale_attempts(tmp_path):
    run_root = tmp_path / "runs"
    chain_root = run_root / "chain-a"
    chain_root.mkdir(parents=True)
    first = cpr.begin_chain_attempt(run_root, "chain-a", chain_root)
    assert first.number == 1 and first.attic is None
    (chain_root / "p0-forward").mkdir()
    (chain_root / "chain-result.json").write_text('{"status": "infra_blocked"}')
    cpr.finish_chain_attempt(first, "infra_blocked", infra_scope="chain")

    second = cpr.begin_chain_attempt(run_root, "chain-a", chain_root)
    assert second.number == 2 and second.chargeable_before == 1
    assert not any(chain_root.iterdir())
    assert (Path(second.attic) / "chain-result.json").is_file()
    ledger = json.loads((run_root / "_chain_attempts" / "chain-a.json").read_text(encoding="utf-8"))
    assert [a["attempt"] for a in ledger["attempts"]] == [1, 2]
    assert ledger["attempts"][0]["counts_toward_limit"] is True


def test_global_and_interrupted_attempts_do_not_count_toward_the_limit(tmp_path):
    run_root, chain_root = tmp_path / "runs", tmp_path / "runs" / "c"
    chain_root.mkdir(parents=True)
    a1 = cpr.begin_chain_attempt(run_root, "c", chain_root, max_chain_attempts=1)
    cpr.finish_chain_attempt(a1, "infra_blocked", infra_scope="global")
    a2 = cpr.begin_chain_attempt(run_root, "c", chain_root, max_chain_attempts=1)
    cpr.finish_chain_attempt(a2, "aborted_circuit_open")
    cpr.begin_chain_attempt(run_root, "c", chain_root, max_chain_attempts=1)  # never finished (pod lost)
    a4 = cpr.begin_chain_attempt(run_root, "c", chain_root, max_chain_attempts=1)
    assert not a4.exhausted and a4.number == 4
    cpr.finish_chain_attempt(a4, "harness_exception")
    a5 = cpr.begin_chain_attempt(run_root, "c", chain_root, max_chain_attempts=1)
    assert a5.exhausted
    ledger = json.loads((run_root / "_chain_attempts" / "c.json").read_text(encoding="utf-8"))
    assert [a["ended_status"] for a in ledger["attempts"]] == [
        "infra_blocked", "aborted_circuit_open", "interrupted", "harness_exception",
    ]
