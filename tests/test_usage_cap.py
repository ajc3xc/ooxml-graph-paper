"""Tests for tools/usage_cap.py (2026-09-25 rate-limit handling addition):
detection (confirmed and fail-safe/unconfirmed), reset-time parsing, the
sweep-wide pause controller's backoff/resume/heartbeat, and the sweep-level
retry loop. No real `claude -p` subprocess is started and no test sleeps for
a real backoff duration -- every clock/sleep is injected.

Run with: pixi run python -m pytest tests/test_usage_cap.py -v
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import claude_pair_runner as cpr  # noqa: E402
import usage_cap as ucap  # noqa: E402

_NOW = datetime.datetime(2026, 9, 25, 12, 0, 0, tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------------------
# parse_reset_time
# ---------------------------------------------------------------------------

def test_parse_reset_time_returns_none_on_ordinary_text():
    assert ucap.parse_reset_time(None, now=_NOW) is None
    assert ucap.parse_reset_time("", now=_NOW) is None
    assert ucap.parse_reset_time("You've hit your limit.", now=_NOW) is None


def test_parse_reset_time_labeled_iso8601():
    assert ucap.parse_reset_time("You've hit your limit, resets at 2026-09-25T18:30:00Z", now=_NOW) == \
        datetime.datetime(2026, 9, 25, 18, 30, 0, tzinfo=datetime.timezone.utc)


def test_parse_reset_time_json_field_iso_and_epoch():
    assert ucap.parse_reset_time('{"error":{"resetsAt":"2026-09-26T00:00:00+00:00"}}', now=_NOW) == \
        datetime.datetime(2026, 9, 26, 0, 0, 0, tzinfo=datetime.timezone.utc)
    epoch = int(datetime.datetime(2026, 9, 25, 13, 0, 0, tzinfo=datetime.timezone.utc).timestamp())
    assert ucap.parse_reset_time(f'{{"reset_at": {epoch}}}', now=_NOW) == \
        datetime.datetime(2026, 9, 25, 13, 0, 0, tzinfo=datetime.timezone.utc)
    epoch_ms = epoch * 1000
    assert ucap.parse_reset_time(f'{{"resetAt": {epoch_ms}}}', now=_NOW) == \
        datetime.datetime(2026, 9, 25, 13, 0, 0, tzinfo=datetime.timezone.utc)


def test_parse_reset_time_relative_phrases():
    assert ucap.parse_reset_time("try again in 5 minutes", now=_NOW) == _NOW + datetime.timedelta(minutes=5)
    assert ucap.parse_reset_time("Retry-After: 120", now=_NOW) == _NOW + datetime.timedelta(seconds=120)


# ---------------------------------------------------------------------------
# detect_usage_cap_event
# ---------------------------------------------------------------------------

def _api_error(text: str, status: int | None = None) -> dict:
    return {"type": "result", "subtype": "success", "is_error": True, "result": text, "api_error_status": status}


def test_confirmed_usage_limit_signal_is_detected_and_kept_distinct_from_overloaded():
    trial = {"claude_json_result": _api_error("You've hit your limit · resets 2026-09-25T20:00:00Z")}
    signature = cpr.classify_infra_signature({**trial, "arm": "control", "timed_out": False, "returncode": 1})
    event = ucap.detect_usage_cap_event(trial, signature, "chain-a/p0-forward", now=_NOW)
    assert event is not None and event.kind == "usage_limit" and event.confirmed is True
    assert event.reset_at == datetime.datetime(2026, 9, 25, 20, 0, 0, tzinfo=datetime.timezone.utc)

    overloaded_trial = {"claude_json_result": _api_error("API Error: 529 overloaded_error", 529)}
    overloaded_sig = cpr.classify_infra_signature({**overloaded_trial, "arm": "control", "timed_out": False, "returncode": 1})
    assert ucap.detect_usage_cap_event(overloaded_trial, overloaded_sig, "x", now=_NOW) is None


def test_confirmed_rate_limit_signal_is_detected():
    trial = {"claude_json_result": _api_error("API Error: 429", 429)}
    signature = cpr.classify_infra_signature({**trial, "arm": "control", "timed_out": False, "returncode": 1})
    event = ucap.detect_usage_cap_event(trial, signature, "x", now=_NOW)
    assert event is not None and event.kind == "api_rate_limit" and event.confirmed is True


def test_ordinary_timeout_and_clean_success_produce_no_event():
    timeout_trial = {"claude_json_result": None, "timed_out": True, "returncode": None, "arm": "control"}
    assert ucap.detect_usage_cap_event(timeout_trial, None, "x", now=_NOW) is None

    clean = {"claude_json_result": {"is_error": False, "result": "Done."}, "unconfirmed_infra_text": []}
    assert ucap.detect_usage_cap_event(clean, None, "x", now=_NOW) is None


def test_unconfirmed_usage_text_is_a_fail_safe_event_but_never_a_signature():
    """Review item (wf3 report, minor): usage-limit text in a result the CLI
    did not flag as an API error must still pause the sweep (fail-safe),
    without ever being classify_infra_signature's own signature."""
    trial = {
        "claude_json_result": {"is_error": False, "result": "API Error: 529 overloaded_error -- You've hit your limit"},
    }
    signature = cpr.classify_infra_signature({**trial, "arm": "control", "timed_out": False, "returncode": 0})
    assert signature is None  # never a confirmed signature (see claude_pair_runner tests)
    unconfirmed = cpr.unconfirmed_infra_text(trial)
    trial["unconfirmed_infra_text"] = unconfirmed
    event = ucap.detect_usage_cap_event(trial, signature, "x", now=_NOW)
    assert event is not None and event.confirmed is False
    assert event.kind in ("usage_limit", "api_rate_limit", "api_overloaded")


def test_unrecognized_but_clearly_not_normal_text_with_no_pattern_match_is_not_forced_into_a_cap_event():
    """Fail-safe means "pause on an unrecognized cap-like condition", not
    "invent a cap event from any odd text" -- ordinary task-driven text
    produces nothing."""
    trial = {"claude_json_result": {"is_error": False, "result": "I could not find that heading."},
             "unconfirmed_infra_text": []}
    assert ucap.detect_usage_cap_event(trial, None, "x", now=_NOW) is None


# ---------------------------------------------------------------------------
# is_usage_cap_result / breaker_tripped_on_usage_cap
# ---------------------------------------------------------------------------

def test_is_usage_cap_result():
    assert ucap.is_usage_cap_result({"status": "aborted_circuit_open"}) is True
    assert ucap.is_usage_cap_result({"status": "infra_blocked", "infra_signature": {"kinds": ["usage_limit"]}}) is True
    assert ucap.is_usage_cap_result({"status": "infra_blocked", "infra_signature": {"kinds": ["api_rate_limit"]}}) is True
    assert ucap.is_usage_cap_result({"status": "infra_blocked", "infra_signature": {"kinds": ["mcp_load_failure"]}}) is False
    assert ucap.is_usage_cap_result({"status": "infra_blocked", "infra_signature": {"kinds": ["api_authentication"]}}) is False
    assert ucap.is_usage_cap_result({"status": "completed"}) is False
    assert ucap.is_usage_cap_result({"status": "harness_exception"}) is False


def test_breaker_tripped_on_usage_cap():
    breaker = cpr.CircuitBreaker()
    assert ucap.breaker_tripped_on_usage_cap(breaker) is False
    breaker.trip({"kinds": ["usage_limit"], "scope": "global"}, "src")
    assert ucap.breaker_tripped_on_usage_cap(breaker) is True

    hard_breaker = cpr.CircuitBreaker()
    hard_breaker.trip({"kinds": ["api_authentication"], "scope": "global"}, "src")
    assert ucap.breaker_tripped_on_usage_cap(hard_breaker) is False


# ---------------------------------------------------------------------------
# UsagePauseController
# ---------------------------------------------------------------------------

def _controller(**kw) -> ucap.UsagePauseController:
    now_box = {"t": _NOW}
    kw.setdefault("now_fn", lambda: now_box["t"])
    kw.setdefault("sleep", lambda seconds: None)
    return ucap.UsagePauseController(**kw)


def test_note_trial_pauses_and_wait_for_resume_uses_backoff_when_no_reset_time():
    sleeps: list[float] = []
    controller = _controller(sleep=sleeps.append, base_backoff_seconds=10.0, poll_interval_seconds=4.0)
    assert controller.is_paused is False
    trial = {"claude_json_result": _api_error("API Error: 429", 429)}
    signature = {"kinds": ["api_rate_limit"], "scope": "global", "evidence": []}
    event = controller.note_trial(trial, signature, "chain-a/p0-forward")
    assert event is not None and controller.is_paused is True
    controller.wait_for_resume()
    assert controller.is_paused is False
    assert sum(sleeps) == pytest.approx(10.0)  # polled in <= poll_interval steps, total = backoff
    assert all(s <= 4.0 for s in sleeps)
    assert controller.state()["resume_count"] == 1


def test_wait_for_resume_is_a_no_op_when_not_paused():
    sleeps: list[float] = []
    controller = _controller(sleep=sleeps.append)
    controller.wait_for_resume()
    assert sleeps == [] and controller.state()["resume_count"] == 0


def test_note_trial_prefers_a_known_reset_time_over_backoff():
    now_box = {"t": _NOW}
    sleeps: list[float] = []
    controller = ucap.UsagePauseController(now_fn=lambda: now_box["t"], sleep=sleeps.append,
                                           base_backoff_seconds=999.0, poll_interval_seconds=30.0)
    trial = {"claude_json_result": _api_error("You've hit your limit · resets at 2026-09-25T12:02:00Z")}
    signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": []}
    controller.note_trial(trial, signature, "x")
    assert controller.state()["reset_at"] == "2026-09-25T12:02:00+00:00"
    controller.wait_for_resume()
    assert sum(sleeps) == pytest.approx(120.0)  # 2 minutes to the parsed reset time, not the 999s backoff


def test_backoff_grows_across_pause_episodes_and_mark_success_resets_it():
    controller = _controller(base_backoff_seconds=10.0, max_backoff_seconds=1000.0)
    signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": []}
    trial = {"claude_json_result": _api_error("usage limit")}

    controller.note_trial(trial, signature, "a")
    assert controller.state()["backoff_seconds"] == 10.0
    controller.wait_for_resume()

    controller.note_trial(trial, signature, "b")  # a fresh episode, no mark_success in between
    assert controller.state()["backoff_seconds"] == 20.0
    controller.wait_for_resume()

    controller.mark_success()
    controller.note_trial(trial, signature, "c")
    assert controller.state()["backoff_seconds"] == 10.0  # back to base


def test_backoff_is_capped_at_max_backoff_seconds():
    controller = _controller(base_backoff_seconds=1000.0, max_backoff_seconds=1500.0)
    signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": []}
    trial = {"claude_json_result": _api_error("usage limit")}
    for _ in range(4):
        controller.note_trial(trial, signature, "x")
        controller.wait_for_resume()
    assert controller.state()["backoff_seconds"] == 1500.0


def test_heartbeat_file_shows_paused_since_and_waiting_trials(tmp_path):
    path = tmp_path / "usage-cap-status.json"
    controller = _controller(heartbeat_path=path)
    signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": ["api_error_status 429"]}
    trial = {"claude_json_result": _api_error("You've hit your limit")}
    controller.note_trial(trial, signature, "chain-a/p0-forward")
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["paused"] is True and written["paused_since"] is not None
    assert written["last_event"]["kind"] == "usage_limit" and written["last_event"]["source"] == "chain-a/p0-forward"
    controller.wait_for_resume()
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["paused"] is False and after["resume_count"] == 1


def test_unconfirmed_event_pauses_but_note_trial_never_raises_or_returns_a_status():
    """The caller decides chain status; note_trial only ever returns the
    event (or None) and writes state -- it has no way to change a status."""
    controller = _controller()
    trial = {"claude_json_result": {"is_error": False, "result": "You've hit your limit, sorry!"},
             "unconfirmed_infra_text": ["usage_limit"]}
    event = controller.note_trial(trial, None, "x")
    assert event is not None and event.confirmed is False
    assert controller.is_paused is True


def test_mark_success_clears_a_lingering_pause_defensively():
    """Regression: mark_success used to reset only the backoff bookkeeping,
    leaving is_paused (and the heartbeat) stuck reporting 'paused: true'
    forever if it was ever called without an intervening wait_for_resume."""
    controller = _controller()
    trial = {"claude_json_result": _api_error("usage limit")}
    signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": []}
    controller.note_trial(trial, signature, "x")
    assert controller.is_paused is True
    controller.mark_success()
    assert controller.is_paused is False


def test_wait_for_resume_clamps_an_implausible_parsed_reset_time():
    """Regression: a misparsed (or genuinely absurd) reset_at must not sleep
    an unbounded duration in an unattended run -- it is clamped to
    max_reset_wait_seconds, distinct from (and larger than) the ordinary
    exponential-backoff ceiling, and the clamp is recorded in state()."""
    now_box = {"t": _NOW}
    sleeps: list[float] = []
    controller = ucap.UsagePauseController(
        now_fn=lambda: now_box["t"], sleep=sleeps.append,
        base_backoff_seconds=10.0, max_backoff_seconds=1800.0,
        max_reset_wait_seconds=3600.0, poll_interval_seconds=600.0,
    )
    trial = {"claude_json_result": _api_error("resets at 2026-12-25T00:00:00Z")}  # ~3 months away
    signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": []}
    controller.note_trial(trial, signature, "x")
    controller.wait_for_resume()
    assert sum(sleeps) == pytest.approx(3600.0)  # clamped, not the multi-month gap
    assert controller.state()["last_wait_clamped"] is True


def test_wait_for_resume_does_not_clamp_a_reset_time_within_the_ceiling():
    now_box = {"t": _NOW}
    sleeps: list[float] = []
    controller = ucap.UsagePauseController(
        now_fn=lambda: now_box["t"], sleep=sleeps.append,
        base_backoff_seconds=10.0, max_reset_wait_seconds=7 * 86400.0, poll_interval_seconds=600.0,
    )
    trial = {"claude_json_result": _api_error("resets at 2026-09-25T13:00:00Z")}  # 1 hour away
    signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": []}
    controller.note_trial(trial, signature, "x")
    controller.wait_for_resume()
    assert sum(sleeps) == pytest.approx(3600.0)
    assert controller.state()["last_wait_clamped"] is False


# ---------------------------------------------------------------------------
# run_with_usage_cap_retry
# ---------------------------------------------------------------------------

def test_run_with_usage_cap_retry_retries_only_usage_cap_rounds_and_stops_on_hard_trip():
    controller = _controller()
    calls: list[list[str]] = []

    def dispatch_round(jobs, breaker):
        calls.append(list(jobs))
        breaker.trip({"kinds": ["api_authentication"], "scope": "global"}, "hard")
        return {j: {"status": "aborted_circuit_open" if j != jobs[0] else "infra_blocked",
                     "infra_signature": {"kinds": ["api_authentication"]}} for j in jobs}, list(jobs)

    final, order, rounds = ucap.run_with_usage_cap_retry(
        dispatch_round, ["a", "b", "c"], controller, job_key=lambda j: j, make_circuit_breaker=cpr.CircuitBreaker,
    )
    assert len(calls) == 1  # a hard trip is never auto-retried
    assert len(rounds) == 1 and rounds[0]["usage_cap_round"] is False
    assert set(final) == {"a", "b", "c"}


def test_run_with_usage_cap_retry_retries_a_usage_cap_round_until_it_clears():
    controller = _controller()
    attempts = {"n": 0}

    def dispatch_round(jobs, breaker):
        attempts["n"] += 1
        if attempts["n"] == 1:
            breaker.trip({"kinds": ["usage_limit"], "scope": "global"}, "cap")
            return (
                {jobs[0]: {"status": "infra_blocked", "infra_signature": {"kinds": ["usage_limit"]}},
                 jobs[1]: {"status": "aborted_circuit_open"}},
                list(jobs),
            )
        return {j: {"status": "completed"} for j in jobs}, list(jobs)

    final, order, rounds = ucap.run_with_usage_cap_retry(
        dispatch_round, ["a", "b"], controller, job_key=lambda j: j, make_circuit_breaker=cpr.CircuitBreaker,
    )
    assert attempts["n"] == 2
    assert len(rounds) == 2 and rounds[0]["usage_cap_round"] is True and rounds[1]["usage_cap_round"] is False
    assert final == {"a": {"status": "completed"}, "b": {"status": "completed"}}
    assert controller.state()["pause_episodes"] == 0  # mark_success after the clean round


def test_run_with_usage_cap_retry_pauses_for_an_all_unconfirmed_round():
    """Regression (major finding): a round where every usage-cap signal is
    'unconfirmed' (no signature ever trips that round's breaker, so
    breaker_tripped_on_usage_cap is False and retry_keys stays empty) must
    still actually pause via wait_for_resume before the loop takes its
    'nothing to retry' exit -- not just record is_paused and move on."""
    sleeps: list[float] = []
    controller = _controller(sleep=sleeps.append, base_backoff_seconds=15.0)

    def dispatch_round(jobs, breaker):
        # Simulate the unconfirmed fail-safe path: a trial's own text names a
        # usage limit but the CLI result was never flagged as an API error,
        # so no confirmed signature is ever produced and the breaker never
        # trips on it.
        trial = {"claude_json_result": {"is_error": False, "result": "You've hit your limit."},
                 "unconfirmed_infra_text": ["usage_limit"]}
        controller.note_trial(trial, None, jobs[0])
        return {j: {"status": "completed"} for j in jobs}, list(jobs)

    final, order, rounds = ucap.run_with_usage_cap_retry(
        dispatch_round, ["a"], controller, job_key=lambda j: j, make_circuit_breaker=cpr.CircuitBreaker,
    )
    assert len(rounds) == 1  # nothing to retry -- one dispatch round is enough
    assert final == {"a": {"status": "completed"}}
    assert sum(sleeps) == pytest.approx(15.0)  # but the pause was still honored before returning
    assert controller.is_paused is False


def test_run_with_usage_cap_retry_respects_max_rounds():
    controller = _controller()

    def always_caps(jobs, breaker):
        breaker.trip({"kinds": ["api_rate_limit"], "scope": "global"}, "cap")
        return {j: {"status": "aborted_circuit_open"} for j in jobs}, list(jobs)

    final, order, rounds = ucap.run_with_usage_cap_retry(
        always_caps, ["a"], controller, job_key=lambda j: j, make_circuit_breaker=cpr.CircuitBreaker, max_rounds=3,
    )
    assert len(rounds) == 3 and all(r["usage_cap_round"] for r in rounds)


# ---------------------------------------------------------------------------
# Task item 5: a usage-cap-hit chain's attempt counter is unchanged and its
# status stays "not yet attempted" -- exercised through the real
# claude_pair_runner ledger (begin_chain_attempt/finish_chain_attempt), the
# same primitive run_chain/run_respec_cascade_chain use, distinguishing it
# from an ordinary chain-scope infra failure (which DOES count).
# ---------------------------------------------------------------------------

def test_usage_cap_attempt_does_not_consume_the_chain_attempt_budget(tmp_path):
    run_root, chain_root = tmp_path / "run", tmp_path / "run" / "chain-a"
    chain_root.mkdir(parents=True)
    controller = _controller()

    attempt = cpr.begin_chain_attempt(run_root, "chain-a", chain_root, max_chain_attempts=1)
    trial = {"claude_json_result": _api_error("You've hit your limit", None), "arm": "control",
             "timed_out": False, "returncode": 1}
    # infra_signature_of reads a PRE-COMPUTED "infra_signature" key (exactly
    # what run_trial itself sets via classify_infra_signature on its own
    # result) -- it never classifies the trial itself.
    trial["infra_signature"] = cpr.classify_infra_signature(trial)
    signature = cpr.infra_signature_of(trial, None, "chain-a/p0-forward", pause_controller=controller)
    assert signature is not None and "usage_limit" in signature["kinds"] and signature["scope"] == "global"
    assert controller.is_paused is True  # the sweep is told to pause

    cpr.finish_chain_attempt(attempt, "infra_blocked", infra_scope=signature["scope"])
    ledger = json.loads((run_root / "_chain_attempts" / "chain-a.json").read_text(encoding="utf-8"))
    assert ledger["attempts"][0]["counts_toward_limit"] is False  # a global (usage-cap) event never counts

    # With max_chain_attempts=1, a chain whose ONE chargeable attempt was
    # already used would now be exhausted -- but this attempt never charged,
    # so the chain is still runnable: "not yet attempted", not excluded.
    second = cpr.begin_chain_attempt(run_root, "chain-a", chain_root, max_chain_attempts=1)
    assert second.exhausted is False and second.chargeable_before == 0


def test_ordinary_chain_scope_infra_failure_still_counts_for_contrast(tmp_path):
    """The exact opposite of the test above: a chain-scope (non-global) kind
    like mcp_load_failure DOES count, same as before this module existed --
    confirming the usage-cap carve-out is specific to global kinds, not a
    general loosening of the attempt-ledger rule."""
    run_root, chain_root = tmp_path / "run", tmp_path / "run" / "chain-b"
    chain_root.mkdir(parents=True)
    controller = _controller()

    attempt = cpr.begin_chain_attempt(run_root, "chain-b", chain_root, max_chain_attempts=1)
    trial = {
        "arm": "treatment", "timed_out": False, "returncode": 0,
        "claude_json_result": {"type": "result", "subtype": "success", "is_error": False, "result": "no tool"},
        "claude_init_record": {"mcp_servers": [], "tools": []}, "treatment_tool": "move_section",
    }
    trial["infra_signature"] = cpr.classify_infra_signature(trial)
    signature = cpr.infra_signature_of(trial, None, "chain-b/p0-forward", pause_controller=controller)
    assert signature is not None and signature["kinds"] == ["mcp_load_failure"] and signature["scope"] == "chain"
    assert controller.is_paused is False  # not a usage-cap/rate-limit kind: never pauses the sweep

    cpr.finish_chain_attempt(attempt, "infra_blocked", infra_scope=signature["scope"])
    ledger = json.loads((run_root / "_chain_attempts" / "chain-b.json").read_text(encoding="utf-8"))
    assert ledger["attempts"][0]["counts_toward_limit"] is True

    second = cpr.begin_chain_attempt(run_root, "chain-b", chain_root, max_chain_attempts=1)
    assert second.exhausted is True  # the one chargeable attempt was used
