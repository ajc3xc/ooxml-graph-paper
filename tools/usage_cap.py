"""Usage-cap / rate-limit handling for the respec_cascade and K=4 rerun
harnesses (2026-09-25 rate-limit-handling addition), distinct from the
ordinary infrastructure-failure handling `claude_pair_runner.CircuitBreaker`
already provides.

Why this is a separate mechanism, not a `CircuitBreaker` extension:
`claude_pair_runner.classify_infra_signature` already tags a global
infrastructure signature with a `kind` -- `usage_limit` and `api_rate_limit`
are already distinguished from `api_overloaded`/`api_authentication`/
`api_server_error`/`api_connection` there (see its INFRA_KIND_SCOPES and
INFRA_ERROR_TEXT_PATTERNS), and a global signature already never counts
toward a chain's rerun-once budget (claude_pair_runner._CHARGEABLE_END_STATUSES
excludes `infra_scope == "global"`). What is MISSING is what happens at the
sweep level once one is seen: today `CircuitBreaker` trips once and stays
tripped forever -- every other in-flight or queued chain aborts
(`aborted_circuit_open`), the sweep exits code 3, and nothing resumes it
short of an operator relaunching the whole command by hand (exactly the
"operator decides whether to relaunch" problem the prior rerun-preparation
rounds flagged as blocker B1).

That permanent-trip behavior is still correct and is left completely alone
for the "hard" global kinds (`api_overloaded`, `api_authentication`,
`api_server_error`, `api_connection`): those usually need a human to look at
what happened. `usage_limit` (the weekly subscription cap) and
`api_rate_limit` (a transient 429) are different in kind -- they are
EXPECTED, recoverable, and resolve themselves given enough wait -- so this
module adds a second, resumable mechanism (`UsagePauseController`) reserved
for exactly those two kinds (`USAGE_CAP_KINDS`) plus the fail-safe
"unconfirmed" case described below. It is threaded through
`claude_pair_runner.infra_signature_of` as an optional, purely additive
parameter -- passing `None` (every existing call site that does not opt in)
reproduces today's behavior exactly.

Sweep-level integration (`run_with_usage_cap_retry`): a sweep dispatches one
"round" of jobs against a FRESH `claude_pair_runner.CircuitBreaker` (so a
resolved usage-cap episode never leaves a permanently-tripped breaker
poisoning the next round). If that round's breaker tripped on a kind in
USAGE_CAP_KINDS, every chain the round could not finish because of it
(`aborted_circuit_open`, or `infra_blocked` with a usage-cap signature of its
own) goes back into the queue for the next round; anything else (a genuine
task outcome, a chain-scope infra failure, or a HARD global trip) is left as
this launch's final result, exactly as before. Between rounds the sweep
waits via `UsagePauseController.wait_for_resume` -- until a parsed reset
time if the CLI's error text gave one, otherwise an exponential backoff
capped at `max_backoff_seconds` (default 30 minutes, per the task's "sane
max"). No relaunch is needed: the retry loop lives inside one call to
`run_corpus_slice`/`run_primary_sweep`, so the operator's single launch
command runs it to completion (or to a genuinely hard failure) on its own.

Reset-time parsing is honestly best-effort. NO CONFIRMED EXAMPLE of the
`claude` CLI's actual usage-limit/rate-limit JSON error shape was available
when this was written -- searching this repository and its
`claude_pair_runner.py` (INFRA_ERROR_TEXT_PATTERNS, added 2026-09-25 for the
respec re-run preparation) turned up only free-text phrase patterns
("You've hit your limit", "resets 3pm", "rate_limit_error"), never a
captured raw JSON payload with a machine-readable reset field. `parse_reset_time`
below tries several plausible shapes (a labeled ISO8601 timestamp, a
`resetsAt`/`reset_at` JSON field as an ISO string or epoch seconds/
milliseconds, a "try again in N minutes" phrase, a bare `Retry-After`
seconds value) but this is a heuristic over speculative shapes, not a parser
for a confirmed format. When nothing matches it returns None, and every
caller in this module treats that as "reset time unknown", falling back to
exponential backoff -- never as "no cap is in effect" and never as a reason
to skip the pause.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

# The claude_pair_runner.classify_infra_signature kinds this module treats as
# recoverable-by-waiting rather than a hard infrastructure failure. Deliberately
# narrow: api_overloaded/api_authentication/api_server_error/api_connection keep
# the OLD permanent-circuit-breaker-trip behavior (see module docstring).
USAGE_CAP_KINDS: frozenset[str] = frozenset({"usage_limit", "api_rate_limit"})

_ISO_TOKEN = r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
_RESET_JSON_FIELD_RE = re.compile(r"\"reset(?:s)?_?[Aa]t\"\s*:\s*\"?(\d{10,13}|" + _ISO_TOKEN + r")\"?")
_RESET_LABELED_RE = re.compile(
    r"(?:resets?|reset[_ ]?at|available again|try again after)\D{0,16}(" + _ISO_TOKEN + r")",
    re.IGNORECASE,
)
_RETRY_AFTER_RELATIVE_RE = re.compile(r"try again in\s+(\d+)\s*(second|minute|hour|day)s?", re.IGNORECASE)
_RETRY_AFTER_HEADER_RE = re.compile(r"retry-after\s*:?\s*(\d+)", re.IGNORECASE)
_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def _parse_timestamp_token(token: str, *, now: datetime.datetime) -> datetime.datetime | None:
    token = token.strip()
    if token.isdigit():
        try:
            value = int(token)
            seconds = value / 1000.0 if value > 10**12 else float(value)
            return datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    normalized = token[:-1] + "+00:00" if token.endswith("Z") else token
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=datetime.timezone.utc)


def parse_reset_time(text: str | None, *, now: datetime.datetime) -> datetime.datetime | None:
    """Best-effort reset/retry time from free CLI error text (see module
    docstring: no confirmed real example of the CLI's own shape was
    available). Returns None -- "unknown", never "no cap" -- when nothing
    matches. Tries, in order: a `resetsAt`/`reset_at`-shaped JSON field (ISO
    string or epoch seconds/milliseconds), a labeled ISO8601 timestamp near
    a word like "resets", a "try again in N <unit>" phrase, and a bare
    Retry-After seconds value."""
    if not text:
        return None
    for regex in (_RESET_JSON_FIELD_RE, _RESET_LABELED_RE):
        match = regex.search(text)
        if match:
            parsed = _parse_timestamp_token(match.group(1), now=now)
            if parsed is not None:
                return parsed
    match = _RETRY_AFTER_RELATIVE_RE.search(text)
    if match:
        seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2).lower()]
        return now + datetime.timedelta(seconds=seconds)
    match = _RETRY_AFTER_HEADER_RE.search(text)
    if match:
        return now + datetime.timedelta(seconds=int(match.group(1)))
    return None


def _trial_error_text(trial: dict[str, Any]) -> str:
    result = trial.get("claude_json_result")
    parts = []
    if isinstance(result, dict) and isinstance(result.get("result"), str):
        parts.append(result["result"])
    stderr = trial.get("stderr_tail")
    if stderr is None:
        stderr = trial.get("stderr")
    if isinstance(stderr, str):
        parts.append(stderr)
    return "\n".join(parts)


@dataclasses.dataclass(frozen=True)
class UsageCapEvent:
    """One detected usage-cap/rate-limit signal. `confirmed=False` is the
    fail-safe path (task item 6): the CLI's result was NOT flagged as an API
    error (`is_error` not true -- classify_infra_signature would never call
    this a signature), but its own text still names a usage/rate limit
    (`claude_pair_runner.unconfirmed_infra_text`). Per the prior review that
    flagged this gap (a limit event the CLI reports in an unexpected way
    must not silently fail every later trial as the arm's own outcome): it
    still pauses the sweep, but the caller MUST NOT let it change any
    chain's status -- see `note_trial`'s docstring."""

    kind: str
    confirmed: bool
    detected_at: datetime.datetime
    source: str
    reset_at: datetime.datetime | None = None
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "confirmed": self.confirmed, "detected_at": self.detected_at.isoformat(),
            "source": self.source, "reset_at": self.reset_at.isoformat() if self.reset_at else None,
            "evidence": list(self.evidence),
        }


def detect_usage_cap_event(
    trial: dict[str, Any], signature: dict[str, Any] | None, source: str, *, now: datetime.datetime,
) -> UsageCapEvent | None:
    """A `UsageCapEvent` from one trial (claude_pair_runner.run_trial's
    result dict) and its already-computed `signature`
    (classify_infra_signature's return, or None), or None when neither a
    confirmed nor an unconfirmed usage-cap/rate-limit signal is present.
    Never raises."""
    confirmed_kinds = USAGE_CAP_KINDS.intersection((signature or {}).get("kinds") or [])
    if confirmed_kinds:
        kind = "usage_limit" if "usage_limit" in confirmed_kinds else "api_rate_limit"
        text = _trial_error_text(trial)
        return UsageCapEvent(
            kind=kind, confirmed=True, detected_at=now, source=source,
            reset_at=parse_reset_time(text, now=now),
            evidence=tuple((signature or {}).get("evidence") or ()),
        )
    unconfirmed_kinds = USAGE_CAP_KINDS.intersection(trial.get("unconfirmed_infra_text") or [])
    if unconfirmed_kinds:
        kind = "usage_limit" if "usage_limit" in unconfirmed_kinds else "api_rate_limit"
        text = _trial_error_text(trial)
        return UsageCapEvent(
            kind=kind, confirmed=False, detected_at=now, source=source,
            reset_at=parse_reset_time(text, now=now),
            evidence=(f"unconfirmed_infra_text: {sorted(unconfirmed_kinds)}",),
        )
    return None


def is_usage_cap_result(result: dict[str, Any]) -> bool:
    """True when a chain result (run_chain's / run_respec_cascade_chain's
    return shape, or the synthetic ABORTED/EXCEPTION dict a sweep's executor
    loop builds) stopped only because of a usage-cap/rate-limit episode, and
    should therefore be retried automatically in the next round rather than
    kept as this launch's final result. `aborted_circuit_open` is counted
    unconditionally here -- callers gate that on the round's breaker having
    actually tripped on a USAGE_CAP_KINDS signature first
    (`breaker_tripped_on_usage_cap`), so every `aborted_circuit_open` chain
    in such a round is, by `CircuitBreaker`'s own single-trip semantics,
    downstream of that one signature."""
    status = result.get("status")
    if status == "aborted_circuit_open":
        return True
    if status == "infra_blocked":
        kinds = (result.get("infra_signature") or {}).get("kinds") or []
        return bool(USAGE_CAP_KINDS.intersection(kinds))
    return False


def breaker_tripped_on_usage_cap(circuit_breaker: Any) -> bool:
    """True when `circuit_breaker` (a claude_pair_runner.CircuitBreaker) is
    open and the signature that tripped it is a usage-cap/rate-limit kind."""
    state = circuit_breaker.state()
    tripped = state.get("tripped")
    if not tripped:
        return False
    kinds = (tripped.get("signature") or {}).get("kinds") or []
    return bool(USAGE_CAP_KINDS.intersection(kinds))


# ---------------------------------------------------------------------------
# Sweep-wide pause controller
# ---------------------------------------------------------------------------

_HEARTBEAT_SCHEMA = "usage-cap-status-v1"


class UsagePauseController:
    """Sweep-wide pause/backoff state for usage-cap/rate-limit events,
    shared by every thread of one sweep (analogous to, and used alongside,
    claude_pair_runner.CircuitBreaker -- see the module docstring for why
    these are two separate mechanisms).

    `note_trial` is called (via claude_pair_runner.infra_signature_of, given
    `pause_controller=`) as soon as a trial's usage-cap signal is known; it
    only ever records state and writes the heartbeat -- it never sleeps and
    never raises, so it is always safe to call from a worker thread.
    `wait_for_resume` is the blocking half, called between dispatch rounds by
    the sweep's own (single) coordinating thread -- see
    `run_with_usage_cap_retry`. Tests inject `clock`/`sleep`/`now_fn` so no
    test needs to sleep for a real backoff duration.
    """

    def __init__(
        self, *, heartbeat_path: Path | None = None, base_backoff_seconds: float = 30.0,
        max_backoff_seconds: float = 1800.0, poll_interval_seconds: float = 30.0,
        max_reset_wait_seconds: float = 7 * 86400.0,
        sleep: Callable[[float], None] | None = None,
        now_fn: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._heartbeat_path = heartbeat_path
        self._base_backoff_seconds = base_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._poll_interval_seconds = poll_interval_seconds
        # A separate, much larger ceiling than max_backoff_seconds for the
        # "we parsed a reset time" path: a real weekly subscription cap can
        # legitimately be days away, so clamping it to max_backoff_seconds
        # (default 30 minutes) would make the parsed-reset-time path useless.
        # This ceiling exists only to bound a MISPARSE (parse_reset_time is a
        # heuristic over speculative shapes -- see module docstring) so an
        # autonomous, unattended run can never sleep an unbounded/absurd
        # duration on a garbled timestamp.
        self._max_reset_wait_seconds = max_reset_wait_seconds
        self._last_wait_clamped = False
        # Looked up on `time`/`datetime` here, at construction, rather than
        # bound as a literal default parameter value -- so a test that
        # monkeypatches usage_cap.time.sleep (or .datetime) before
        # constructing a controller (including one main() builds internally)
        # can still replace it, with no real sleep anywhere in the test suite.
        self._sleep = sleep if sleep is not None else time.sleep
        self._now_fn = now_fn if now_fn is not None else (lambda: datetime.datetime.now(datetime.timezone.utc))
        self._lock = threading.Lock()
        self._paused_since: datetime.datetime | None = None
        self._reset_at: datetime.datetime | None = None
        self._backoff_seconds = base_backoff_seconds
        self._pause_episodes = 0
        self._waiting = 0
        self._resume_count = 0
        self._last_event: UsageCapEvent | None = None
        self._events: list[UsageCapEvent] = []

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused_since is not None

    def note_trial(self, trial: dict[str, Any], signature: dict[str, Any] | None, source: str) -> UsageCapEvent | None:
        """Inspects one trial for a usage-cap/rate-limit signal and, if
        found, enters (or extends) a pause episode. NEVER changes the
        caller's chain/trial outcome -- in particular the unconfirmed case
        (see UsageCapEvent) pauses the sweep but must not, and does not,
        mark anything as failed; callers that already decided a chain's
        status (confirmed infra_blocked, or a clean pass) keep that
        decision regardless of this call's return value."""
        event = detect_usage_cap_event(trial, signature, source, now=self._now_fn())
        if event is None:
            return None
        with self._lock:
            if self._paused_since is None:
                self._pause_episodes += 1
                self._backoff_seconds = min(
                    self._base_backoff_seconds * (2 ** (self._pause_episodes - 1)), self._max_backoff_seconds,
                )
                self._paused_since = event.detected_at
            if event.reset_at is not None and (self._reset_at is None or event.reset_at > self._reset_at):
                self._reset_at = event.reset_at
            self._last_event = event
            self._events.append(event)
            if len(self._events) > 50:
                self._events = self._events[-50:]
        self._write_heartbeat()
        return event

    def mark_success(self) -> None:
        """Resets exponential backoff to the base value. Called by
        `run_with_usage_cap_retry` after a round that needed no retry, so a
        LATER, unrelated cap episode starts from the base backoff rather than
        continuing to grow from an earlier, already-resolved one. Also
        defensively clears any lingering pause state: the normal path always
        calls `wait_for_resume` first (which already clears it), but this
        guards against `is_paused`/the heartbeat being left stuck on `True`
        forever if that ordering is ever skipped -- see the "unconfirmed
        event with no confirmed trip" fail-safe path in
        `run_with_usage_cap_retry`."""
        with self._lock:
            self._pause_episodes = 0
            self._backoff_seconds = self._base_backoff_seconds
            self._paused_since = None
            self._reset_at = None
        self._write_heartbeat()

    def wait_for_resume(self, *, source: str = "sweep") -> dict[str, Any]:
        """Blocks the calling thread while paused: until the known reset
        time, or for the current exponential-backoff duration (capped at
        `max_backoff_seconds`) when no reset time was parsed -- polled in
        `poll_interval_seconds` increments so the heartbeat file (and an
        injected fake clock in tests) stays responsive rather than one long
        sleep. A no-op, returning immediately, when not paused. Always
        clears the pause before returning (a later `note_trial` re-enters
        one, growing the backoff further if the cap is hit again right
        away)."""
        with self._lock:
            not_paused = self._paused_since is None
            if not not_paused:
                reset_at = self._reset_at
                backoff = self._backoff_seconds
                self._waiting += 1
        if not_paused:
            # `state()` acquires `self._lock` itself -- it must never be
            # called while this method still holds it (threading.Lock is not
            # reentrant; doing so deadlocks the calling thread forever, found
            # live via a hung test run: exactly the no-op "not paused" case).
            return self.state()
        self._write_heartbeat()
        try:
            if reset_at is not None:
                remaining = max((reset_at - self._now_fn()).total_seconds(), 0.0)
                clamped = remaining > self._max_reset_wait_seconds
                if clamped:
                    remaining = self._max_reset_wait_seconds
            else:
                remaining = backoff
                clamped = False
            with self._lock:
                self._last_wait_clamped = clamped
            while remaining > 0:
                step = min(remaining, self._poll_interval_seconds)
                self._sleep(step)
                remaining -= step
        finally:
            with self._lock:
                self._waiting = max(0, self._waiting - 1)
                self._paused_since = None
                self._reset_at = None
                self._resume_count += 1
            self._write_heartbeat()
        return self.state()

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema": _HEARTBEAT_SCHEMA,
                "paused": self._paused_since is not None,
                "paused_since": self._paused_since.isoformat() if self._paused_since else None,
                "reset_at": self._reset_at.isoformat() if self._reset_at else None,
                "reset_at_known": self._reset_at is not None,
                "backoff_seconds": self._backoff_seconds,
                "pause_episodes": self._pause_episodes,
                "waiting_trials": self._waiting,
                "resume_count": self._resume_count,
                "last_wait_clamped": self._last_wait_clamped,
                "last_event": self._last_event.to_dict() if self._last_event else None,
                "recent_events": [e.to_dict() for e in self._events[-10:]],
                "updated_at": self._now_fn().isoformat(),
            }

    def _write_heartbeat(self) -> None:
        if self._heartbeat_path is None:
            return
        try:
            self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._heartbeat_path.with_name(self._heartbeat_path.name + ".tmp")
            tmp.write_text(json.dumps(self.state(), indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._heartbeat_path)
        except OSError:
            pass  # the heartbeat is diagnostic only; never let it fail a trial


# ---------------------------------------------------------------------------
# Sweep-level retry loop
# ---------------------------------------------------------------------------

def run_with_usage_cap_retry(
    dispatch_round: Callable[[list[Any], Any], tuple[dict[Any, dict[str, Any]], list[Any]]],
    initial_jobs: list[Any],
    pause_controller: UsagePauseController,
    *, job_key: Callable[[Any], Any], make_circuit_breaker: Callable[[], Any], max_rounds: int | None = None,
) -> tuple[dict[Any, dict[str, Any]], list[Any], list[dict[str, Any]]]:
    """Runs `dispatch_round(jobs, circuit_breaker)` -> (key -> chain result,
    submission-order entries) repeatedly, with a FRESH `circuit_breaker`
    (from `make_circuit_breaker`) each round, retrying only the jobs whose
    result `is_usage_cap_result` when that round's breaker
    `breaker_tripped_on_usage_cap`. Waits between rounds via
    `pause_controller.wait_for_resume`. A round that needs no retry ends the
    loop (and resets backoff via `mark_success`); a round whose breaker
    tripped on a HARD (non-usage-cap) global kind also ends the loop, its
    result kept as-is -- unchanged from before this module existed.
    `max_rounds` (None = unlimited, matching "resumes automatically, no
    relaunch needed") is a safety valve mainly for tests and callers that
    want a bound.

    Returns (key -> final result for every job ever dispatched, the
    submission-order entries from every round concatenated in order, one
    summary dict per round)."""
    remaining = list(initial_jobs)
    final: dict[Any, dict[str, Any]] = {}
    submission_order: list[Any] = []
    rounds: list[dict[str, Any]] = []
    round_number = 0
    while remaining:
        round_number += 1
        breaker = make_circuit_breaker()
        round_results, round_submission = dispatch_round(remaining, breaker)
        submission_order.extend(round_submission)
        final.update(round_results)
        usage_cap_round = breaker_tripped_on_usage_cap(breaker)
        retry_keys = {k for k, r in round_results.items() if is_usage_cap_result(r)} if usage_cap_round else set()
        rounds.append({
            "round": round_number, "jobs_dispatched": len(remaining), "usage_cap_round": usage_cap_round,
            "retried": len(retry_keys), "circuit_breaker": breaker.state(),
        })
        if not retry_keys:
            # A round can end with nothing to retry even though the
            # controller is still paused: an "unconfirmed" usage-cap signal
            # (a trial's own text names a limit but the CLI result was never
            # flagged as an API error, so no signature ever trips this
            # round's breaker -- see UsageCapEvent.confirmed) sets
            # `is_paused` via `note_trial` without ever making
            # `breaker_tripped_on_usage_cap` true. That fail-safe path exists
            # specifically to still throttle the sweep, so it must still
            # block here exactly like a confirmed round does -- otherwise the
            # pause is promised by the module docstring but never honored,
            # and `is_paused`/the heartbeat are left reporting "paused: true"
            # forever once `mark_success` below resets bookkeeping without
            # ever having waited.
            if pause_controller.is_paused:
                pause_controller.wait_for_resume(source=f"round-{round_number}-unconfirmed")
            pause_controller.mark_success()
            break
        if max_rounds is not None and round_number >= max_rounds:
            break
        pause_controller.wait_for_resume(source=f"round-{round_number}")
        remaining = [job for job in remaining if job_key(job) in retry_keys]
    return final, submission_order, rounds
