"""B1 fix (2026-09-26; see the fix-blockers-fast task and the prior review's
blocker: "No completion or relaunch rule", S25 5.6/10.6/11, S26 5/10.4/11,
runbook 9/14): mechanically relaunches a locked sweep command until a launch
starts zero new chain attempts, then runs the verdict/statistics command --
so "keep relaunching to a fixed point, then compute the verdict" is a
mechanical property of one wrapper invocation, never an operator's (or an
unattended relaunch loop's) judgment call about partial outcomes.

Works UNMODIFIED for both sweep entry points, because both already share the
same per-chain attempt ledger mechanism (`claude_pair_runner.begin_chain_attempt`
/ `ATTEMPTS_DIR_NAME = "_chain_attempts"`, written under `<run-root>/_chain_attempts/
<chain_id>.json`):
  - `tools/run_respec_cascade_sweep.py` (the respec cascade primary/baseline sweep)
  - `tools/run_paper_s7_benchmark.py` (the K=4 confirmatory benchmark path)

Completion rule: after any exit 0 from the sweep command, the correct next
action is to relaunch the IDENTICAL locked command immediately, and keep
relaunching until a launch starts zero new attempts. At that fixed point
every chain is trusted, `infra_excluded` or `not_applicable` -- nothing is
`infra_blocked`, `harness_exception`, or aborted -- and only then is the data
"complete" enough to compute a verdict. "New attempts started" is counted
mechanically from every `<run-root>/_chain_attempts/*.json` ledger (summing
`len(ledger["attempts"])`) before and after each launch: a relaunch that
starts genuinely nothing new leaves that sum unchanged, regardless of which
sweep script wrote it. A launch that exits NONZERO stops the loop immediately
WITHOUT relaunching (the "relaunch immediately" rule only ever applies after
an exit 0; a nonzero exit means the sweep itself detected something a blind
relaunch would not fix, e.g. a schedule-hash mismatch or a missing document
manifest) and WITHOUT running the verdict command.

Runaway-cost circuit breaker (FINAL DECISIONS, 2026-09-26): distinct from
`claude_pair_runner.CircuitBreaker` (infrastructure) and
`usage_cap.UsagePauseController` (rate limits/usage caps). Checked BETWEEN
relaunch rounds (after every launch that exited 0, before deciding whether to
relaunch again): sums `claude_json_result.total_cost_usd` over every
`chain-result.json` found anywhere under every `--run-root` given. The
$150-450 expected total for the S25/S26 rerun (three real measured trials
today: $0.0608/$0.0453/$0.0417 per single forward bibliography-family trial,
haiku) sets a hard abort at 3x its top ($1,350, `DEFAULT_COST_CEILING_USD`).
If the running total ever exceeds the ceiling, the loop halts immediately --
no further relaunch, no verdict command -- and writes a clear reason to
`<first run-root>/cost-circuit-breaker.json`.

Every launch (and the final outcome) is also recorded in
`<first run-root>/sweep-to-completion-state.json` for audit.

Usage:
    python run_sweep_to_completion.py \\
        --run-root <run-root> [--run-root <baseline-run-root> ...] \\
        --verdict-cmd '["pixi", "run", "python", "tools/respec_rerun_verdict.py", "--statistics-dir", "..."]' \\
        [--cost-ceiling-usd 1350] [--max-relaunches 200] \\
        -- <the exact locked sweep command and its argv, e.g.> \\
        pixi run python tools/run_respec_cascade_sweep.py --run-root <run-root> --model sonnet ...

Exit codes: 0 (fixed point reached; exits with the verdict command's own exit
code, which is not necessarily 0), the sweep command's own nonzero exit code
(stopped without relaunching), 4 (cost circuit breaker tripped), 5 (gave up
after --max-relaunches without reaching a fixed point).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ATTEMPTS_DIR_NAME = "_chain_attempts"

# 3x the top of the $150-450 expected-total budget range for the S25/S26
# rerun (FINAL DECISIONS, 2026-09-26), grounded in three real measured
# trials ($0.0608/$0.0453/$0.0417 per single forward bibliography-family
# trial, haiku, on a moderate and a large document) -- the true average
# across all six families and both directions is unmeasured and could run
# higher, which is why the ceiling is a multiple of the expected range, not
# the range itself.
DEFAULT_COST_CEILING_USD = 1_350.0
DEFAULT_MAX_RELAUNCHES = 200

RunFn = Callable[[list[str]], int]


def count_attempts(run_roots: list[Path]) -> int:
    """Total number of attempts recorded across every `_chain_attempts/*.json`
    ledger under every run root -- the mechanical "how many attempts has this
    launch started, cumulatively" signal, shared by both sweep entry points
    because both write ledgers through the same `claude_pair_runner.
    begin_chain_attempt`."""
    total = 0
    for root in run_roots:
        ledger_dir = root / ATTEMPTS_DIR_NAME
        if not ledger_dir.is_dir():
            continue
        for ledger_path in sorted(ledger_dir.glob("*.json")):
            try:
                ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            total += len(ledger.get("attempts") or [])
    return total


def _accumulate_cost(node: Any, acc: list[float]) -> None:
    if isinstance(node, dict):
        cli_result = node.get("claude_json_result")
        if isinstance(cli_result, dict):
            cost = cli_result.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                acc[0] += float(cost)
        for value in node.values():
            _accumulate_cost(value, acc)
    elif isinstance(node, list):
        for value in node:
            _accumulate_cost(value, acc)


def total_cost_usd(run_roots: list[Path]) -> float:
    """Running total of `claude_json_result.total_cost_usd`, summed over
    every trial found anywhere inside every `chain-result.json` under every
    run root (a respec_cascade chain result nests one such record per step
    across up to three phases; a K=4/S7 chain result nests one per pair
    direction) -- walked generically rather than pattern-matched to one
    schema, so it costs nothing extra to keep working if either orchestrator's
    nesting changes shape."""
    acc = [0.0]
    for root in run_roots:
        if not root.is_dir():
            continue
        for chain_result_path in root.rglob("chain-result.json"):
            try:
                data = json.loads(chain_result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            _accumulate_cost(data, acc)
    return acc[0]


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def _default_run_fn(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode  # noqa: S603 -- the exact locked command the caller passed in


def run_to_completion(
    run_roots: list[Path], sweep_cmd: list[str], verdict_cmd: list[str], *,
    cost_ceiling_usd: float = DEFAULT_COST_CEILING_USD, max_relaunches: int = DEFAULT_MAX_RELAUNCHES,
    run_fn: RunFn | None = None, log: Callable[[str], None] = print,
) -> int:
    """The relaunch-to-fixed-point loop. `run_fn(cmd) -> exit_code` defaults
    to a real subprocess; tests inject a fake. Every launch is appended to
    `<run_roots[0]>/sweep-to-completion-state.json` as it happens (not only at
    the end), so a killed wrapper still leaves an audit trail of what it did."""
    if not run_roots:
        raise ValueError("run_to_completion requires at least one run root")
    run_fn = run_fn if run_fn is not None else _default_run_fn
    state_path = run_roots[0] / "sweep-to-completion-state.json"
    launches: list[dict[str, Any]] = []

    def _write_state(*, outcome: str, reason: str | None, verdict_exit_code: int | None = None) -> None:
        _write_json_atomic(state_path, {
            "schema": "sweep-to-completion-state-v1",
            "run_roots": [str(root) for root in run_roots],
            "sweep_cmd": sweep_cmd,
            "verdict_cmd": verdict_cmd,
            "cost_ceiling_usd": cost_ceiling_usd,
            "max_relaunches": max_relaunches,
            "launches": launches,
            "outcome": outcome,
            "reason": reason,
            "verdict_exit_code": verdict_exit_code,
        })

    for launch_number in range(1, max_relaunches + 1):
        attempts_before = count_attempts(run_roots)
        log(f"[run_sweep_to_completion] launch {launch_number}: relaunching the locked sweep command "
            f"(cumulative attempts before this launch: {attempts_before})")
        exit_code = run_fn(sweep_cmd)
        attempts_after = count_attempts(run_roots)
        new_attempts = attempts_after - attempts_before
        entry: dict[str, Any] = {
            "launch": launch_number, "exit_code": exit_code,
            "attempts_before": attempts_before, "attempts_after": attempts_after, "new_attempts": new_attempts,
        }
        launches.append(entry)

        if exit_code != 0:
            reason = (
                f"sweep command exited {exit_code} on launch {launch_number}; the relaunch rule only relaunches "
                "after an exit 0 (B1) -- stopping without relaunching and without running the verdict command."
            )
            log(f"[run_sweep_to_completion] {reason}")
            _write_state(outcome="sweep_nonzero_exit", reason=reason)
            return exit_code

        cost_so_far = total_cost_usd(run_roots)
        entry["total_cost_usd_after_launch"] = cost_so_far
        if cost_so_far > cost_ceiling_usd:
            reason = (
                f"runaway-cost circuit breaker tripped after launch {launch_number}: running total "
                f"${cost_so_far:.2f} exceeds the ${cost_ceiling_usd:.2f} hard-abort ceiling (3x the top of the "
                "$150-450 expected-total budget range, FINAL DECISIONS 2026-09-26). Halting before any further "
                "relaunch and without running the verdict command."
            )
            log(f"[run_sweep_to_completion] {reason}")
            _write_state(outcome="cost_circuit_breaker_tripped", reason=reason)
            _write_json_atomic(run_roots[0] / "cost-circuit-breaker.json", {
                "schema": "cost-circuit-breaker-v1",
                "tripped": True,
                "total_cost_usd": cost_so_far,
                "cost_ceiling_usd": cost_ceiling_usd,
                "launch": launch_number,
                "reason": reason,
            })
            return 4

        if new_attempts == 0:
            reason = (
                f"fixed point reached after launch {launch_number}: 0 new attempts started; every chain is "
                "trusted, infra_excluded or not_applicable. Running the verdict command."
            )
            log(f"[run_sweep_to_completion] {reason}")
            verdict_exit_code = run_fn(verdict_cmd)
            _write_state(outcome="fixed_point_reached", reason=reason, verdict_exit_code=verdict_exit_code)
            return verdict_exit_code

        log(f"[run_sweep_to_completion] launch {launch_number} started {new_attempts} new attempt(s); relaunching.")

    reason = f"gave up after {max_relaunches} relaunch(es) without reaching a fixed point of 0 new attempts."
    log(f"[run_sweep_to_completion] {reason}")
    _write_state(outcome="max_relaunches_exceeded", reason=reason)
    return 5


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if "--" not in argv:
        print(
            "error: pass the exact locked sweep command after a literal '--' separator, "
            "e.g. run_sweep_to_completion.py --run-root R --verdict-cmd '[...]' -- pixi run python "
            "tools/run_respec_cascade_sweep.py --run-root R ...",
            file=sys.stderr,
        )
        return 2
    split = argv.index("--")
    own_argv, sweep_cmd = argv[:split], argv[split + 1:]
    if not sweep_cmd:
        print("error: no sweep command given after '--'", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--run-root", action="append", required=True, type=Path, dest="run_roots",
        help="A run root to watch for new chain attempts and cost (repeatable -- pass both the primary and "
             "the baseline run root when the sweep command writes to both).",
    )
    parser.add_argument(
        "--verdict-cmd", required=True,
        help="The verdict/statistics command to run once the fixed point is reached, as a JSON list of argv "
             "tokens (e.g. '[\"pixi\", \"run\", \"python\", \"tools/respec_rerun_verdict.py\", ...]').",
    )
    parser.add_argument("--cost-ceiling-usd", type=float, default=DEFAULT_COST_CEILING_USD)
    parser.add_argument("--max-relaunches", type=int, default=DEFAULT_MAX_RELAUNCHES)
    args = parser.parse_args(own_argv)

    try:
        verdict_cmd = json.loads(args.verdict_cmd)
    except json.JSONDecodeError as exc:
        print(f"error: --verdict-cmd is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(verdict_cmd, list) or not all(isinstance(tok, str) for tok in verdict_cmd):
        print("error: --verdict-cmd must be a JSON list of strings", file=sys.stderr)
        return 2

    return run_to_completion(
        args.run_roots, sweep_cmd, verdict_cmd,
        cost_ceiling_usd=args.cost_ceiling_usd, max_relaunches=args.max_relaunches,
    )


if __name__ == "__main__":
    raise SystemExit(main())
