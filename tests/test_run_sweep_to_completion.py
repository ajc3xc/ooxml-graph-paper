import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import run_sweep_to_completion as w  # noqa: E402


def _write_ledger(run_root: Path, chain_id: str, n_attempts: int) -> None:
    ledger_dir = run_root / w.ATTEMPTS_DIR_NAME
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / f"{chain_id}.json").write_text(
        json.dumps({"chain_id": chain_id, "attempts": [{"attempt": i + 1} for i in range(n_attempts)]}),
        encoding="utf-8",
    )


def _write_chain_result(run_root: Path, chain_id: str, cost_usd: float) -> None:
    chain_dir = run_root / chain_id
    chain_dir.mkdir(parents=True, exist_ok=True)
    (chain_dir / "chain-result.json").write_text(
        json.dumps({"chain_id": chain_id, "step_log": [{"claude_json_result": {"total_cost_usd": cost_usd}}]}),
        encoding="utf-8",
    )


def test_count_attempts_sums_ledgers_across_multiple_run_roots(tmp_path):
    primary, baselines = tmp_path / "primary", tmp_path / "baselines"
    _write_ledger(primary, "a", 2)
    _write_ledger(primary, "b", 1)
    _write_ledger(baselines, "c", 3)
    assert w.count_attempts([primary, baselines]) == 6
    assert w.count_attempts([primary]) == 3
    assert w.count_attempts([tmp_path / "missing"]) == 0


def test_total_cost_usd_walks_nested_chain_results(tmp_path):
    run_root = tmp_path / "primary"
    _write_chain_result(run_root, "a", 0.05)
    _write_chain_result(run_root, "b", 0.10)
    # nested under a per-family subdirectory, like the baseline tree
    (run_root / "bibliography" / "c").mkdir(parents=True)
    (run_root / "bibliography" / "c" / "chain-result.json").write_text(
        json.dumps({"pairs": [{"forward": {"claude_json_result": {"total_cost_usd": 0.02}},
                                "inverse": {"claude_json_result": {"total_cost_usd": 0.03}}}]}),
        encoding="utf-8",
    )
    assert w.total_cost_usd([run_root]) == 0.20


def test_total_cost_usd_ignores_missing_or_corrupt_fields(tmp_path):
    run_root = tmp_path / "primary"
    chain_dir = run_root / "a"
    chain_dir.mkdir(parents=True)
    (chain_dir / "chain-result.json").write_text(json.dumps({"claude_json_result": {}}), encoding="utf-8")
    (chain_dir / "not-a-chain-result.json").write_text("not json at all {{{", encoding="utf-8")
    assert w.total_cost_usd([run_root]) == 0.0


def test_fixed_point_reached_relaunches_until_zero_new_attempts_then_runs_verdict(tmp_path):
    run_root = tmp_path / "primary"
    calls = []

    def fake_run(cmd):
        calls.append(list(cmd))
        if cmd[0] == "sweep":
            n_before = w.count_attempts([run_root])
            if n_before < 2:
                _write_ledger(run_root, "chain-a", n_before + 1)
            return 0
        assert cmd[0] == "verdict"
        return 0

    rc = w.run_to_completion(
        [run_root], ["sweep"], ["verdict"], run_fn=fake_run, log=lambda _msg: None,
    )
    assert rc == 0
    # two launches started a new attempt, the third started none and ran the verdict command
    sweep_calls = [c for c in calls if c[0] == "sweep"]
    verdict_calls = [c for c in calls if c[0] == "verdict"]
    assert len(sweep_calls) == 3 and len(verdict_calls) == 1
    state = json.loads((run_root / "sweep-to-completion-state.json").read_text(encoding="utf-8"))
    assert state["outcome"] == "fixed_point_reached"
    assert [entry["new_attempts"] for entry in state["launches"]] == [1, 1, 0]
    assert state["verdict_exit_code"] == 0


def test_nonzero_exit_stops_without_relaunching_or_running_verdict(tmp_path):
    run_root = tmp_path / "primary"
    calls = []

    def fake_run(cmd):
        calls.append(list(cmd))
        return 3  # e.g. circuit_breaker open

    rc = w.run_to_completion([run_root], ["sweep"], ["verdict"], run_fn=fake_run, log=lambda _msg: None)
    assert rc == 3
    assert calls == [["sweep"]]  # never relaunched, verdict never run
    state = json.loads((run_root / "sweep-to-completion-state.json").read_text(encoding="utf-8"))
    assert state["outcome"] == "sweep_nonzero_exit"


def test_cost_circuit_breaker_trips_and_halts_before_verdict(tmp_path):
    run_root = tmp_path / "primary"
    calls = []

    def fake_run(cmd):
        calls.append(list(cmd))
        if cmd[0] == "sweep":
            # Still making real progress (a new attempt every launch), so
            # only the cost ceiling -- not the fixed-point check -- can stop
            # this loop.
            _write_ledger(run_root, "chain-a", len(calls))
            _write_chain_result(run_root, f"chain-{len(calls)}", 1_000.0)
            return 0
        raise AssertionError("verdict command must never run once the cost breaker trips")

    rc = w.run_to_completion(
        [run_root], ["sweep"], ["verdict"], cost_ceiling_usd=1_350.0, run_fn=fake_run, log=lambda _msg: None,
    )
    assert rc == 4
    assert len(calls) == 2  # trips on the second launch once cumulative cost exceeds the ceiling
    breaker = json.loads((run_root / "cost-circuit-breaker.json").read_text(encoding="utf-8"))
    assert breaker["tripped"] is True and breaker["total_cost_usd"] == 2_000.0
    state = json.loads((run_root / "sweep-to-completion-state.json").read_text(encoding="utf-8"))
    assert state["outcome"] == "cost_circuit_breaker_tripped"


def test_max_relaunches_exceeded_gives_up(tmp_path):
    run_root = tmp_path / "primary"

    def fake_run(cmd):
        # every launch starts exactly one new attempt, forever
        n = w.count_attempts([run_root])
        _write_ledger(run_root, "chain-a", n + 1)
        return 0

    rc = w.run_to_completion(
        [run_root], ["sweep"], ["verdict"], max_relaunches=3, run_fn=fake_run, log=lambda _msg: None,
    )
    assert rc == 5
    state = json.loads((run_root / "sweep-to-completion-state.json").read_text(encoding="utf-8"))
    assert state["outcome"] == "max_relaunches_exceeded"
    assert len(state["launches"]) == 3


def test_main_requires_a_double_dash_separator(capsys):
    rc = w.main(["--run-root", "x", "--verdict-cmd", "[]"])
    assert rc == 2
    assert "--" in capsys.readouterr().err


def test_main_rejects_invalid_verdict_cmd_json(tmp_path, capsys):
    rc = w.main(["--run-root", str(tmp_path), "--verdict-cmd", "not json", "--", "true"])
    assert rc == 2
    assert "JSON" in capsys.readouterr().err


def test_main_parses_run_roots_and_verdict_cmd_and_invokes_the_loop(tmp_path, monkeypatch):
    captured = {}

    def fake_run_to_completion(run_roots, sweep_cmd, verdict_cmd, **kwargs):
        captured["run_roots"] = run_roots
        captured["sweep_cmd"] = sweep_cmd
        captured["verdict_cmd"] = verdict_cmd
        captured["kwargs"] = kwargs
        return 0

    monkeypatch.setattr(w, "run_to_completion", fake_run_to_completion)
    rc = w.main([
        "--run-root", str(tmp_path / "primary"), "--run-root", str(tmp_path / "baselines"),
        "--verdict-cmd", json.dumps(["python", "verdict.py"]), "--cost-ceiling-usd", "999",
        "--", "python", "sweep.py", "--run-root", str(tmp_path / "primary"),
    ])
    assert rc == 0
    assert captured["run_roots"] == [tmp_path / "primary", tmp_path / "baselines"]
    assert captured["sweep_cmd"] == ["python", "sweep.py", "--run-root", str(tmp_path / "primary")]
    assert captured["verdict_cmd"] == ["python", "verdict.py"]
    assert captured["kwargs"]["cost_ceiling_usd"] == 999.0
