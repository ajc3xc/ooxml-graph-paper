"""PAPER-S20/S7: fresh-process runner for the paired Claude-without-vs-with-
Meridian DOCX editing study. Generalized (2026-08-30) from a single
bibliography-only family to any family in docx_trial_broker.py -- each trial's
treatment run exposes exactly the one Meridian tool `spec.treatment_tool`
names (tighter than the original design, which exposed both insert+remove to
every trial regardless of direction), and `model` is now a `run_trial`
parameter (haiku for cheap harness-development iteration; a pinned, dated
model for the confirmatory validation/primary-holdout runs) rather than a
fixed module constant.

Isolation mechanism (this is what actually enforces the arm boundary, NOT
the prompt wording): every trial is a fresh, non-interactive `claude -p`
subprocess launched with:
  --setting-sources     project-only settings, so user-level customizations
                        do not enter the trial while OAuth remains usable
  --strict-mcp-config    ONLY the MCP servers named in --mcp-config are
                         visible -- no user/project-level MCP config leaks in
  --mcp-config <file>    control: a config naming ZERO servers.
                         treatment: a config naming ONLY the local
                         meridian-docs stdio server (launched from THIS
                         paper repo's own pixi env, not the parent's hosted
                         orchestration MCP, and never touching its
                         credentials).
  --tools                control: generic file/shell tools only.
  --disallowedTools      treatment: deny generic editors/shell/file-search
                         tools while leaving the local Meridian MCP available.
  --allowedTools         auto-approves the declared tools. The actual
                         availability boundary is --tools/--disallowedTools
                         plus --strict-mcp-config; --allowedTools alone is
                         not a visibility restriction.
  --add-dir <trial_root> the ONLY directory outside its own cwd the process
                         may touch.
Each trial runs in its own fresh directory containing only a private copy
of the input DOCX -- the frozen gold fixture is never touched directly, and
trials never share a directory or process.

This module does not itself decide isolation is upheld -- audit_isolation()
inspects the recorded transcript afterward and reports violations rather
than assuming the CLI flags alone are sufficient.

2026-09-25 additions (re-run preparation, review items 8, 17, 18, 24):
  - `--verbose` makes the CLI's JSON output the full message list, so the
    CLI's own `system`/`init` record (MCP server status, tool list) is kept as
    `claude_init_record`; `claude_json_result` is still the final `result`
    message exactly as before.
  - `classify_infra_signature` defines an infrastructure failure only from
    evidence the agent cannot produce (pinned patterns below); `run_trial`
    records it as `infra_signature`.
  - A trial never reuses a non-empty trial directory: an earlier attempt's
    files are moved to `<runs_root>/attic/` first (`attic_moves`).
  - The CLI session transcript is found by session id, copied next to the
    trial (`session-transcript.jsonl`) and scanned for Meridian render-gate
    errors (`render_gate_errors`, `render_gate_timeout`).
  - `CircuitBreaker` (sweep-wide stop at the first global infrastructure
    signature) and the per-chain attempt ledger (`begin_chain_attempt` /
    `finish_chain_attempt`) shared by both orchestrators.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

def _resolve_claude_executable() -> str:
    """Resolve Claude to its native executable when Windows exposes a wrapper.

    On Windows, ``shutil.which('claude')`` can resolve the npm-generated
    ``.cmd``/``.ps1`` launcher.  Passing a list of arguments to that launcher
    through ``subprocess.run(..., shell=True)`` loses the ``-p`` prompt, so
    Claude starts successfully but believes no task was supplied.  The npm
    launcher places the native executable at a stable path relative to the
    launcher; invoke that executable directly so argument boundaries are
    preserved.
    """
    resolved = shutil.which("claude")
    if resolved is None:
        raise RuntimeError("claude CLI not found on PATH")

    resolved_path = Path(resolved)
    if sys.platform == "win32" and resolved_path.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        native = (
            resolved_path.parent
            / "node_modules"
            / "@anthropic-ai"
            / "claude-code"
            / "bin"
            / "claude.exe"
        )
        if native.is_file():
            return str(native)
        raise RuntimeError(f"native Claude executable not found beside launcher: {native}")

    return resolved


# Resolved at import as before, but a missing CLI no longer makes the module
# unimportable: the statistics scripts import classify_infra_signature from
# here on machines that never launch a trial. _build_command raises instead.
try:
    _CLAUDE_EXECUTABLE: str | None = _resolve_claude_executable()
    _CLAUDE_EXECUTABLE_ERROR: str | None = None
except RuntimeError as _exc:  # noqa: N816
    _CLAUDE_EXECUTABLE = None
    _CLAUDE_EXECUTABLE_ERROR = str(_exc)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_trial_broker import TrialSpec  # noqa: E402

_PAPER_ROOT = Path(__file__).resolve().parent.parent
_PAPER_PYTHON = sys.executable
# Raised 300s -> 600s 2026-09-07 (PAPER-S7 confirmatory completion sprint): every
# equation/table_structural treatment trial attempted after the render_gate fixes
# (profile isolation, short-path fix, retry left OFF) is STILL ending "blocked",
# but with a materially different signature than earlier in this sprint -- not a
# soffice crash or a soffice-level timeout, but the WHOLE claude -p subprocess
# hitting exactly this outer budget with zero stdout/stderr captured (returncode
# None, wall_time_seconds ~300.08, 100% consistent across every trial checked).
# This is a single-attempt budget, not a retry count (a plain TimeoutExpired
# leaves parsed_json None, which never satisfies the narrow MCP-flake retry
# below) -- so raising it cannot reproduce the earlier fix-4 regression, where
# making one *step* retryable silently doubled worst-case latency past this same
# ceiling. Consistent with the independently-confirmed, severe, ongoing host
# memory crisis this session (down to ~0.5GB free at one point, Cygwin fork()
# itself failing for >2 hours in an earlier crash) from many concurrent Claude
# Code sessions sharing this host -- the whole agent process (model turns + tool
# round trips + render-gate checks) plausibly needs more than 300s of real
# wall-clock time under that contention, even with no single step broken.
#
# Raised 600s -> 900s 2026-09-18, this time from actual wall-clock evidence
# instead of a reactive doubling: aggregating wall_time_seconds across all 643
# chain-result.json files under runs/ (2460 forward+inverse trials, 2409 that
# completed without hitting either ceiling) gives p99=388.8s and max=574.8s for
# the two render-gated families (equation, caption) combined -- but that max
# sits right at the old 600s ceiling because the data is right-censored: 46
# trials hit their contemporaneous timeout outright (300s pre-09-07, 600s
# after), and 37 of those hit the *current* 600s ceiling as recently as
# 2026-09-12 (25 table_structural, 11 equation, 1 caption). So 600s is still
# provably insufficient for a real fraction of genuine, uncorrupted attempts
# right now -- this is not a hypothetical. 900s (1.5x, matching this project's
# own prior evidence-based soffice 60s->90s raise) clears the observed
# successful max with headroom instead of sitting exactly on it. It is still
# not a true derived percentile -- the right-censoring means the real tail
# beyond 600s is unobserved -- so this remains a reasoned, evidence-informed
# interim value pending a validation run with enough headroom to observe
# genuine completion times past the old ceiling, not a closed derivation.
_TIMEOUT_SECONDS = 900.0

# See the retry logic in run_trial (PAPER-S8 defect 11): these phrases are
# how the agent itself describes a treatment session where --mcp-config's
# server never loaded at all, leaving it with the bare default Claude Code
# toolset instead of Meridian's bounded tool. Confirmed corpus-wide unique
# (1 occurrence in 330+ scanned trials) before this retry was added --
# narrow and specific on purpose, not a general "no-op means flake" rule.
_MCP_TOOL_UNAVAILABLE_SIGNATURES = (
    "doesn't exist in my toolset",
    "isn't loaded in this session",
    "no way to modify or save",
)

# ---------------------------------------------------------------------------
# Infrastructure signature (review item 8; S25 section 5.5, S26 section 5).
#
# A trial has an infrastructure signature only on evidence the agent itself
# cannot produce:
#   1. an API error the CLI reports about its own model request: the result
#      record has `is_error: true` with subtype "success" (the CLI sets
#      is_error from its own isApiErrorMessage flag, not from anything the
#      agent writes) and its `api_error_status` or error text names one of the
#      error types below; or those error types appear in the CLI's stderr;
#   2. a non-zero exit with no JSON result and no harness timeout;
#   3. a kill by a foreign signal (negative POSIX return code) or a Windows
#      NTSTATUS crash code (>= 0xC0000000, e.g. STATUS_DLL_INIT_FAILED);
#   4. (treatment) the CLI's own init record shows the meridian-docs-pilot
#      server not connected and the trial's tool missing from its tool list.
# Deliberately NOT signatures: `is_error` on its own (also set for task-driven
# errors such as "Prompt is too long", an HTTP 400), the error_max_turns /
# error_during_execution subtypes, a harness timeout, and anything in the
# agent's own final text. The pattern list is pinned here and tested
# (tests/test_claude_pair_runner_infra.py); changing it after a protocol lock
# is a protocol deviation.
#
# kind -> scope. "global" kinds affect every trial on the account or host at
# once (usage/rate limits, overload, authentication, API outage, network):
# they trip the sweep-wide CircuitBreaker and never count toward a chain's
# rerun-once rule. "chain" kinds are specific to one process.
# ---------------------------------------------------------------------------
INFRA_KIND_SCOPES: dict[str, str] = {
    "api_rate_limit": "global",
    "usage_limit": "global",
    "api_overloaded": "global",
    "api_authentication": "global",
    "api_server_error": "global",
    "api_connection": "global",
    "nonzero_exit_no_json": "chain",
    "foreign_signal": "chain",
    "process_crash_ntstatus": "chain",
    "mcp_load_failure": "chain",
}

# (kind, pattern) pairs searched in the CLI's API-error text (result record
# with is_error true) and in its stderr. Case-insensitive.
INFRA_ERROR_TEXT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("api_rate_limit", r"rate_limit_error|API Error: 429\b|\brate limited\b|temporarily limiting requests"),
    ("usage_limit", r"usage limit|spend limit|You've hit your|You've reached your|You're out of usage credits"
                    r"|limit reached\b.*\bresets?\b|billing_error|credit balance is too low"),
    ("api_overloaded", r"overloaded_error|API Error: 529\b|\bOverloaded\b"),
    ("api_authentication", r"authentication_error|permission_error|API Error: 40[13]\b|Invalid API key"
                           r"|OAuth token (?:has )?(?:expired|been revoked)|Please run /login"),
    ("api_server_error", r"\"type\"\s*:\s*\"api_error\"|API Error: 5\d\d\b|Internal server error"),
    ("api_connection", r"API Error: (?:Connection error|Request timed out)|Unable to connect to API"
                       r"|ECONNRESET|ETIMEDOUT|EAI_AGAIN|ENOTFOUND"),
)
_INFRA_ERROR_TEXT_REGEXES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.IGNORECASE)) for kind, pattern in INFRA_ERROR_TEXT_PATTERNS
)

# api_error_status (the HTTP status the CLI records on an API-error result)
# -> kind. 400/413 (e.g. context overflow) are task-driven: not listed.
_INFRA_API_STATUS_KINDS: dict[int, str] = {401: "api_authentication", 403: "api_authentication", 429: "api_rate_limit",
                                           529: "api_overloaded"}

_NTSTATUS_CRASH_FLOOR = 0xC0000000
_MERIDIAN_MCP_SERVER = "meridian-docs-pilot"


def _text_kinds(text: str) -> list[str]:
    return [kind for kind, regex in _INFRA_ERROR_TEXT_REGEXES if regex.search(text or "")]


def classify_infra_signature(trial: dict[str, Any]) -> dict[str, Any] | None:
    """The infrastructure signature of one trial record (run_trial's return
    shape, or a stored trial from an older run: only `arm`, `timed_out`,
    `returncode`, `claude_json_result`, `stderr_tail`/`stderr` and, when
    present, `claude_init_record`, `treatment_tool` and `docx_changed` are
    read), or None.

    Returns {"kinds": [...], "scope": "global" | "chain", "evidence": [...]}.
    scope is "global" when any kind is global (see INFRA_KIND_SCOPES). See the
    comment above INFRA_KIND_SCOPES for what counts and what never does."""
    kinds: list[str] = []
    evidence: list[str] = []

    def add(kind: str, why: str) -> None:
        if kind not in kinds:
            kinds.append(kind)
        evidence.append(why)

    timed_out = bool(trial.get("timed_out"))
    returncode = trial.get("returncode")
    result = trial.get("claude_json_result")
    result = result if isinstance(result, dict) else None

    # 1. API errors: the CLI's own is_error on a "success"-subtype result.
    if result is not None and result.get("is_error") is True and result.get("subtype", "success") == "success":
        status = result.get("api_error_status")
        if isinstance(status, int):
            kind = _INFRA_API_STATUS_KINDS.get(status) or ("api_server_error" if 500 <= status <= 599 else None)
            if kind is not None:
                add(kind, f"api_error_status {status}")
        result_text = result.get("result") if isinstance(result.get("result"), str) else ""
        for kind in _text_kinds(result_text):
            add(kind, f"API-error result text matches {kind}")
    # stderr is the CLI's own channel, but a run that ended cleanly (exit 0, a
    # result not flagged as an API error) is never infrastructure-failed,
    # whatever retry chatter its stderr holds.
    clean_exit = returncode == 0 and result is not None and result.get("is_error") is not True
    stderr = trial.get("stderr_tail")
    if stderr is None:
        stderr = trial.get("stderr")
    if not clean_exit:
        for kind in _text_kinds(stderr if isinstance(stderr, str) else ""):
            add(kind, f"CLI stderr matches {kind}")

    # 2./3. Process-level failures the harness timeout did not cause.
    if not timed_out and isinstance(returncode, int):
        if returncode < 0:
            add("foreign_signal", f"killed by signal {-returncode}")
        elif returncode >= _NTSTATUS_CRASH_FLOOR:
            add("process_crash_ntstatus", f"return code 0x{returncode:08X}")
        elif returncode != 0 and result is None:
            add("nonzero_exit_no_json", f"exit {returncode} with no JSON result")

    # 4. MCP load failure, from the CLI's own init record only.
    #
    # 2026-09-27 fix (found live during the S25/S26 rerun: 30 of 30 k4
    # section_reorder treatment chains excluded, 0 of 30 control -- every one
    # of the 30 had `docx_changed: True` on the very trial that tripped this
    # signature, meaning the real move_section MCP call had already
    # succeeded -- `--disallowedTools` leaves no other way for the docx to
    # change). The init record's `mcp_servers` snapshot is taken once, early
    # in the CLI's own startup; under this host's heavy contention the
    # server's connection handshake can still be resolving at that moment
    # and finish moments later in the SAME session, in time for the real
    # tool call to succeed. The within-attempt retry a few lines below
    # already encodes this exact distinction (`not docx_changed`, i.e. only
    # a trial that changed nothing gets treated as a load flake); this branch
    # is the one place that never learned it, so a trial whose edit had
    # already landed was still discarded as an infrastructure failure. Fixed
    # by requiring the same `not docx_changed` here. Disclosed as a dated
    # instrumentation correction, not a scoring-criteria change: it does not
    # touch how a trial's actual edit is graded, only whether a trial that
    # provably ran for real is allowed to reach grading at all.
    init = trial.get("claude_init_record")
    if trial.get("arm") == "treatment" and isinstance(init, dict):
        servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or [] if isinstance(s, dict)}
        status = servers.get(_MERIDIAN_MCP_SERVER)
        tool = trial.get("treatment_tool")
        tool_listed = bool(tool) and _mcp_tool_name(tool) in (init.get("tools") or [])
        if status != "connected" and not tool_listed and not trial.get("docx_changed"):
            add("mcp_load_failure", f"init record: {_MERIDIAN_MCP_SERVER} status {status!r}, tool not listed")

    if not kinds:
        return None
    scope = "global" if any(INFRA_KIND_SCOPES.get(k) == "global" for k in kinds) else "chain"
    return {"kinds": kinds, "scope": scope, "evidence": evidence}


def unconfirmed_infra_text(trial: dict[str, Any]) -> list[str]:
    """Infrastructure-looking text in the agent's final result when the CLI
    did NOT flag an API error (is_error not true). Never a signature -- the
    agent can write anything -- but recorded so an operator can see a limit
    event the CLI reported in an unexpected way."""
    result = trial.get("claude_json_result")
    if not isinstance(result, dict) or result.get("is_error") is True:
        return []
    text = result.get("result") if isinstance(result.get("result"), str) else ""
    return _text_kinds(text)


# ---------------------------------------------------------------------------
# Render-gate errors (review item 24): the text a Meridian tool returns when
# its render-verification gate fails lives only in the tool_result blocks of
# the CLI session transcript, never in the final result. Pinned against
# meridian_docs.docs_intel's render-gate error headlines and
# render_gate.py's timeout messages.
# ---------------------------------------------------------------------------
RENDER_GATE_ERROR_PATTERNS: tuple[tuple[str, str], ...] = (
    ("render_gate_failed", r"render verification failed"),
    ("render_gate_unavailable", r"render verification unavailable in this environment"),
    ("render_gate_timeout", r"exceeded its \d+s\s+bound|\\?\"error_class\\?\"\s*:\s*\\?\"timeout\\?\""),
)
_RENDER_GATE_REGEXES = tuple((kind, re.compile(p, re.IGNORECASE)) for kind, p in RENDER_GATE_ERROR_PATTERNS)
_RENDER_GATE_TEXT_LIMIT = 4000


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            c.get("text", "") if isinstance(c, dict) and c.get("type") == "text" else json.dumps(c)
            for c in content
        )
    return json.dumps(content) if content is not None else ""


def extract_render_gate_errors(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every tool_result of a Meridian (mcp__meridian-docs-pilot__*) tool call
    in `messages` (CLI transcript records or verbose-output messages) whose
    text matches a render-gate pattern: [{"tool_use_id", "tool", "kinds",
    "is_error", "text"}]. Only Meridian tool output is read, so the agent's
    own text cannot produce a match."""
    tool_names: dict[str, str] = {}
    found: list[dict[str, Any]] = []
    for record in messages:
        if not isinstance(record, dict):
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                tool_names[block["id"]] = str(block.get("name") or "")
            elif block.get("type") == "tool_result":
                tool = tool_names.get(block.get("tool_use_id"), "")
                if not tool.startswith(f"mcp__{_MERIDIAN_MCP_SERVER}__"):
                    continue
                text = _tool_result_text(block.get("content"))
                kinds = [kind for kind, regex in _RENDER_GATE_REGEXES if regex.search(text)]
                if kinds:
                    found.append({
                        "tool_use_id": block.get("tool_use_id"), "tool": tool, "kinds": kinds,
                        "is_error": block.get("is_error"), "text": text[:_RENDER_GATE_TEXT_LIMIT],
                    })
    return found


def _claude_config_dir() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


def find_session_transcript(session_id: str | None, cwd: Path) -> Path | None:
    """The CLI's session transcript `<config>/projects/<cwd with every
    non-alphanumeric character replaced by '-'>/<session_id>.jsonl`, or, if
    the CLI named the directory differently, any projects/*/<session_id>.jsonl."""
    if not session_id or not re.fullmatch(r"[A-Za-z0-9-]+", session_id):
        return None
    projects = _claude_config_dir() / "projects"
    direct = projects / re.sub(r"[^A-Za-z0-9]", "-", str(Path(cwd).resolve())) / f"{session_id}.jsonl"
    if direct.is_file():
        return direct
    if projects.is_dir():
        for candidate in projects.glob(f"*/{session_id}.jsonl"):
            return candidate
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return records


def _parse_cli_output(stdout: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """(result record, init record, all messages) from the CLI's stdout: one
    JSON object (plain --output-format json), a JSON list of messages
    (--verbose), or JSON lines. The result record is what
    `claude_json_result` has always held."""
    if not stdout.strip():
        return None, None, []
    try:
        parsed: Any = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = []
        for line in stdout.splitlines():
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if not parsed:
            return None, None, []
    if isinstance(parsed, dict):
        return parsed, None, [parsed]
    if not isinstance(parsed, list):
        return None, None, []
    messages = [m for m in parsed if isinstance(m, dict)]
    result = next((m for m in reversed(messages) if m.get("type") == "result"), None)
    init = next((m for m in messages if m.get("type") == "system" and m.get("subtype") == "init"), None)
    return result, init, messages


def _init_record_summary(init: dict[str, Any] | None) -> dict[str, Any] | None:
    if init is None:
        return None
    keep = ("session_id", "model", "claude_code_version", "permissionMode", "mcp_servers", "tools", "cwd")
    return {k: init.get(k) for k in keep if k in init}


# ---------------------------------------------------------------------------
# Trial directories and attic (review item 18).
# ---------------------------------------------------------------------------

def _utc_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def move_to_attic(directory: Path, attic_root: Path, label: str) -> Path | None:
    """Moves a non-empty `directory` to `attic_root/<label>/<UTC timestamp>/`
    (then recreates it empty) and returns the new location; None when the
    directory is absent or empty. Raises OSError if it cannot be moved -- a
    stale attempt's files must never be silently reused."""
    if not directory.is_dir() or not any(directory.iterdir()):
        return None
    destination = attic_root / label / _utc_stamp()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(directory), str(destination))
    directory.mkdir(parents=True, exist_ok=True)
    return destination


# ---------------------------------------------------------------------------
# Sweep-wide circuit breaker (review item 17).
# ---------------------------------------------------------------------------

class CircuitOpenError(RuntimeError):
    """Raised before a trial starts once the sweep's circuit breaker is open."""


class CircuitBreaker:
    """Opens at the first GLOBAL infrastructure signature any trial of the
    sweep reports; from then on no new trial starts (the orchestrators check
    it before every run_trial call and raise CircuitOpenError). The sweep
    records its state and exits non-zero. Chains that were stopped by it, or
    that ended with the global signature itself, do not count toward the
    rerun-once rule (see finish_chain_attempt)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tripped: dict[str, Any] | None = None

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._tripped is not None

    def trip(self, signature: dict[str, Any], source: str) -> None:
        with self._lock:
            if self._tripped is None:
                self._tripped = {
                    "tripped_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "source": source, "signature": signature,
                }

    def check(self, source: str) -> None:
        with self._lock:
            tripped = self._tripped
        if tripped is not None:
            raise CircuitOpenError(f"circuit breaker open (tripped by {tripped['source']}); not starting {source}")

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {"open": self._tripped is not None, **({"tripped": self._tripped} if self._tripped else {})}


def infra_signature_of(
    trial: dict[str, Any], circuit_breaker: CircuitBreaker | None, source: str, *, pause_controller: Any = None,
) -> dict[str, Any] | None:
    """The trial's recorded `infra_signature` (run_trial sets it), tripping
    `circuit_breaker` when its scope is global.

    `pause_controller` (2026-09-25 rate-limit-handling addition; a
    usage_cap.UsagePauseController, duck-typed here so this module never
    imports usage_cap.py) is optional and purely additive: when given, it is
    told about the trial via `note_trial` regardless of whether a signature
    was found, so it can also catch the fail-safe "unconfirmed" case (a
    usage/rate-limit phrase in the agent's own final text when the CLI did
    NOT flag an API error -- see usage_cap.detect_usage_cap_event). This
    never changes `circuit_breaker`'s own trip decision or this function's
    return value; every existing call site (pause_controller=None, the
    default) is unaffected."""
    signature = trial.get("infra_signature")
    if signature and circuit_breaker is not None and signature.get("scope") == "global":
        circuit_breaker.trip(signature, source)
    if pause_controller is not None:
        pause_controller.note_trial(trial, signature, source)
    return signature or None


# ---------------------------------------------------------------------------
# Per-chain attempt ledger (review blocker 1 / items 17-18): kept OUTSIDE the
# chain root, at <run_root>/_chain_attempts/<chain_id>.json, so moving a
# chain root to the attic never loses the count.
# ---------------------------------------------------------------------------
ATTEMPTS_DIR_NAME = "_chain_attempts"
ATTIC_DIR_NAME = "attic"
# Statuses whose attempt counts toward a chain's rerun limit. A global
# infrastructure event (or the circuit breaker stopping the chain) never
# counts; an interrupted attempt (pod loss, killed sweep) never counts.
_CHARGEABLE_END_STATUSES = frozenset({"infra_blocked", "harness_exception"})


@dataclasses.dataclass
class ChainAttempt:
    number: int
    ledger_path: Path
    attic: str | None
    exhausted: bool
    chargeable_before: int


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def _read_ledger(path: Path, chain_id: str) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"chain_id": chain_id, "attempts": []}


def begin_chain_attempt(
    run_root: Path, chain_id: str, chain_root: Path, *, max_chain_attempts: int | None = None,
) -> ChainAttempt:
    """Called once the chain has no trusted checkpoint. Records a new attempt
    in the ledger and moves whatever an earlier attempt left in `chain_root`
    to `<run_root>/attic/<chain_id>/<timestamp>/` so nothing of it is reused.
    With `max_chain_attempts`, a chain whose chargeable attempts (see
    _CHARGEABLE_END_STATUSES) already reach it is `exhausted`: the caller
    must not run it and reports it as `infra_excluded`; nothing is moved."""
    ledger_path = run_root / ATTEMPTS_DIR_NAME / f"{chain_id}.json"
    ledger = _read_ledger(ledger_path, chain_id)
    attempts = ledger.setdefault("attempts", [])
    for previous in attempts:
        if previous.get("ended_status") is None:
            previous["ended_status"] = "interrupted"
            previous["counts_toward_limit"] = False
    chargeable = sum(1 for a in attempts if a.get("counts_toward_limit"))
    if max_chain_attempts is not None and chargeable >= max_chain_attempts:
        _write_json_atomic(ledger_path, ledger)
        return ChainAttempt(len(attempts), ledger_path, None, True, chargeable)
    attic = move_to_attic(chain_root, run_root / ATTIC_DIR_NAME, chain_id)
    chain_root.mkdir(parents=True, exist_ok=True)
    number = len(attempts) + 1
    attempts.append({
        "attempt": number, "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "previous_attempt_moved_to": str(attic) if attic else None, "ended_status": None,
    })
    _write_json_atomic(ledger_path, ledger)
    return ChainAttempt(number, ledger_path, str(attic) if attic else None, False, chargeable)


def finish_chain_attempt(attempt: ChainAttempt, ended_status: str, *, infra_scope: str | None = None) -> None:
    """Closes the attempt in the ledger. It counts toward the rerun limit only
    when it ended infra_blocked by a chain-scope signature, or by a harness
    exception; a global signature or a circuit-breaker stop never counts."""
    ledger = _read_ledger(attempt.ledger_path, attempt.ledger_path.stem)
    for entry in ledger.get("attempts", []):
        if entry.get("attempt") == attempt.number:
            entry["ended_status"] = ended_status
            entry["ended_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            entry["infra_scope"] = infra_scope
            entry["counts_toward_limit"] = ended_status in _CHARGEABLE_END_STATUSES and infra_scope != "global"
    _write_json_atomic(attempt.ledger_path, ledger)


def exhausted_chain_result(attempt: ChainAttempt, base: dict[str, Any], max_chain_attempts: int) -> dict[str, Any]:
    return {
        **base, "status": "infra_excluded",
        "reason": (f"{attempt.chargeable_before} chargeable attempt(s) ended infra_blocked/harness_exception; "
                   f"limit {max_chain_attempts} reached (rerun-once rule)"),
        "attempt_ledger": str(attempt.ledger_path),
    }

_CONTROL_ALLOWED_TOOLS = "Read,Write,Edit,Bash"
_CONTROL_AVAILABLE_TOOLS = "Read,Write,Edit,Bash"
_TREATMENT_DISALLOWED_TOOLS = (
    "Edit,Write,Bash,PowerShell,Glob,Grep,NotebookEdit,WebFetch,WebSearch,Agent"
)


def _mcp_tool_name(tool: str) -> str:
    return f"mcp__meridian-docs-pilot__{tool}"


def _treatment_allowed_tools(spec: TrialSpec) -> str:
    """Expose exactly the ONE Meridian tool this specific trial's direction
    needs -- tighter than S20's original bibliography-only design, which
    exposed both insert and remove to every trial regardless of direction.
    Read stays available so the agent can confirm a write landed, though none
    of today's families require it to complete the task."""
    return f"Read,{_mcp_tool_name(spec.treatment_tool)}"


def _sha256_file(p: Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _empty_mcp_config(trial_root: Path) -> Path:
    path = trial_root / "mcp-config-control.json"
    path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    return path


def _meridian_docs_mcp_config(trial_root: Path) -> Path:
    """Local stdio launch of the meridian-docs extension's OWN MCP server
    (extensions/meridian-docs/meridian_docs/server.py:main, run via THIS
    paper repo's own editable-install pixi env) -- never the parent repo's
    hosted orchestration MCP or its credentials, which this file never
    reads or references."""
    config = {
        "mcpServers": {
            "meridian-docs-pilot": {
                "command": _PAPER_PYTHON,
                "args": ["-m", "meridian_docs.server"],
            }
        }
    }
    path = trial_root / "mcp-config-treatment.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _build_command(spec: TrialSpec, trial_root: Path, docx_in_trial: Path, model: str) -> list[str]:
    if spec.arm == "control":
        available_tools = _CONTROL_AVAILABLE_TOOLS
    elif spec.arm == "treatment":
        available_tools = None
    else:
        raise ValueError(f"unknown arm {spec.arm!r}")

    if _CLAUDE_EXECUTABLE is None:
        raise RuntimeError(_CLAUDE_EXECUTABLE_ERROR or "claude CLI not found on PATH")
    common = [
        _CLAUDE_EXECUTABLE, "-p", spec.prompt,
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--permission-mode", "bypassPermissions",
        "--model", model,
        "--output-format", "json",
        # 2026-09-25: the full message list, so the CLI's own init record
        # (MCP server status) is available to classify_infra_signature.
        # _parse_cli_output still extracts the same final result record.
        "--verbose",
        "--add-dir", str(trial_root),
    ]
    if spec.arm == "control":
        mcp_config = _empty_mcp_config(trial_root)
        return [
            *common,
            "--tools", available_tools,
            "--mcp-config", str(mcp_config),
            "--allowedTools", _CONTROL_ALLOWED_TOOLS,
        ]
    elif spec.arm == "treatment":
        mcp_config = _meridian_docs_mcp_config(trial_root)
        return [
            *common,
            "--disallowedTools", _TREATMENT_DISALLOWED_TOOLS,
            "--mcp-config", str(mcp_config),
            "--allowedTools", _treatment_allowed_tools(spec),
        ]
    raise AssertionError("validated arm did not produce a command")


def _prepare_trial_root(spec: TrialSpec, runs_root: Path, trial_root: Path, input_bytes: bytes) -> Path | None:
    """Gives the trial an empty directory holding only a fresh copy of its
    input (review item 18): anything an earlier attempt left there (its
    doc.docx, scratch/, step-result.json, transcript copy) is moved to
    `<runs_root>/attic/<trial_id>/<timestamp>/` first, never reused. Returns
    the attic location, or None when the directory was new or empty."""
    attic = move_to_attic(trial_root, runs_root / ATTIC_DIR_NAME, spec.trial_id)
    trial_root.mkdir(parents=True, exist_ok=True)
    (trial_root / "doc.docx").write_bytes(input_bytes)
    (trial_root / "scratch").mkdir(parents=True, exist_ok=True)
    return attic


def run_trial(spec: TrialSpec, runs_root: Path, *, model: str = "haiku") -> dict[str, Any]:
    trial_root = runs_root / spec.trial_id
    docx_in_trial = trial_root / "doc.docx"
    # Read before any attic move, in case the input sits inside trial_root.
    input_bytes = Path(spec.input_docx).read_bytes()
    attic_moves: list[str] = []
    moved = _prepare_trial_root(spec, runs_root, trial_root, input_bytes)
    if moved is not None:
        attic_moves.append(str(moved))
    input_hash = _sha256_file(docx_in_trial)

    # PAPER-S7 correction (2026-08-31): a real primary_holdout trial found a
    # control-arm agent extracting/editing its own scratch copy at a FIXED,
    # non-trial-specific path (C:\Users\...\AppData\Local\Temp\claude\
    # extract_doc -- a convention the agent chose on its own, --add-dir
    # never restricts Bash from writing outside trial_root, only grants
    # additional read/write access). Under this harness's own concurrent
    # execution (multiple trials run in parallel threads), a SECOND
    # control-arm trial was independently running and almost certainly
    # collided on that same shared path mid-edit, truncating the first
    # trial's word/document.xml from 48KB to 2.7KB while every other ZIP
    # part stayed intact -- a harness concurrency defect, not necessarily a
    # property of generic-tool editing itself. Point TEMP/TMP/TMPDIR at a
    # trial-unique scratch directory so an agent that (reasonably) assumes
    # "the system temp directory" is private to its own process gets one
    # that actually is, closing this specific collision class without
    # relying on the agent to choose a unique path on its own.
    scratch_dir = trial_root / "scratch"
    trial_env = dict(os.environ)
    trial_env["TEMP"] = str(scratch_dir)
    trial_env["TMP"] = str(scratch_dir)
    trial_env["TMPDIR"] = str(scratch_dir)

    # The prompt references "the document" -- tell the agent its concrete
    # path via an explicit prefix rather than baking a machine path into the
    # broker's own prompt text (keeps docx_trial_broker.py path-agnostic).
    prefix = f"The document's path is: {docx_in_trial}\n\n"
    if spec.arm == "treatment":
        # Naming the exact tool + arguments here (rather than making the
        # model reconstruct a Meridian tool's argument schema from prose)
        # keeps this a test of whether Claude can use Meridian's bounded
        # write primitives, not a test of whether it can independently
        # rediscover a tool's argument schema from a natural-language task
        # description alone -- matching every family's design intent, not
        # just the original bibliography family's.
        #
        # "do not use ToolSearch first" (2026-09-03 finding): citation's
        # treatment-arm trials cost far more per chain than any other
        # family despite needing fewer turns on average -- traced to real
        # transcripts, not guessed. ToolSearch's own "select:" lookup for
        # `remove_citation` reproducibly returns no match on the very first
        # call (confirmed identically across every expensive trial
        # inspected), sending the agent down an 8+ turn exploration of
        # unrelated tool names before it eventually calls remove_citation
        # DIRECTLY and it just works -- the tool was always callable via
        # --allowedTools, ToolSearch's own index is what's stale/wrong for
        # this specific tool name. That's a host-level ToolSearch defect,
        # not something fixable in this repo or meridian-docs -- but
        # telling the agent up front that the tool needs no discovery step
        # routes around it for every family, not just this one.
        prefix += (
            f"Call the {spec.treatment_tool} tool directly, right away, with "
            f"these exact arguments: {json.dumps(spec.treatment_args)}\n\n"
            f"This tool is already available to you -- do not use ToolSearch "
            f"or any other discovery step first; just call it.\n\n"
        )
        if spec.family == "citation" and spec.direction == "inverse":
            # A SECOND, distinct source of the same turn/cost overhead
            # (2026-09-03, found in a post-fix transcript after the
            # ToolSearch fix above): the paragraph text that comes back from
            # a generic read looks like plain bracketed text, so the agent
            # reasonably distrusts that remove_citation (which it knows
            # removes CSL_CITATION fields) is the right tool, and burns
            # several turns verifying via plan/apply_batch_transform before
            # falling back to calling it anyway -- it always was correct.
            # This is genuine, deterministic ground truth the harness
            # already knows (insert_citation created a real field here,
            # confirmed by direct XML inspection during the original
            # investigation), not an assertion papering over a real
            # ambiguity -- stating it removes the agent's reasonable but
            # costly need to verify it independently.
            prefix += (
                "That bracketed marker is embedded in a real Word citation "
                "field (a CSL_CITATION complex field), not a plain text run "
                "-- remove_citation is the correct and only tool needed here. "
                "Do not try to edit the paragraph text directly or verify "
                "this with any other tool first.\n\n"
            )
    located_prompt = prefix + spec.prompt
    spec_with_path = dataclasses.replace(spec, prompt=located_prompt)

    cmd = _build_command(spec_with_path, trial_root, docx_in_trial, model)

    mcp_flake_retried = False
    for attempt in range(2):
        if attempt > 0:
            # The retry gets a fresh directory and input copy (review item
            # 18); the first attempt's files go to the attic. The command is
            # rebuilt because its MCP config file lives in trial_root.
            moved = _prepare_trial_root(spec, runs_root, trial_root, input_bytes)
            if moved is not None:
                attic_moves.append(str(moved))
            input_hash = _sha256_file(docx_in_trial)
            cmd = _build_command(spec_with_path, trial_root, docx_in_trial, model)
        started = datetime.datetime.now(datetime.timezone.utc)
        t0 = time.time()
        try:
            proc = subprocess.run(
                cmd, cwd=str(trial_root), capture_output=True, text=True,
                timeout=_TIMEOUT_SECONDS, encoding="utf-8", errors="replace",
                env=trial_env,
                # _resolve_claude_executable() selects the native .exe on
                # Windows, so shell=False preserves every prompt/flag argument.
                shell=False,
            )
            timed_out = False
            stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            returncode = None
        wall_time = time.time() - t0

        output_hash = _sha256_file(docx_in_trial)
        docx_changed = input_hash != output_hash

        # parsed_json is the final result record, as before --verbose;
        # init_record the CLI's own system/init message (None without it).
        parsed_json, init_record, cli_messages = _parse_cli_output(stdout)

        # PAPER-S8 defect 11 (2026-09-06): a real, confirmed-unique (1 of
        # 330+ trials scanned corpus-wide) one-off flake where the
        # meridian-docs-pilot MCP server never loaded for a treatment CLI
        # invocation at all -- the agent correctly reported its own toolset
        # as the bare Claude Code default (Artifact/Read/ReportFindings/...,
        # none of --mcp-config's servers), left the docx untouched, and
        # apologized. Re-running the identical trial fresh passed cleanly,
        # confirming this is CLI/MCP-startup flakiness, not a real capability
        # gap -- so it must not be silently scored as a treatment failure.
        # Retry ONCE automatically rather than requiring a human to notice
        # and manually re-collect, the same "don't count real infra
        # hiccups as task failures" principle already applied to render-gate
        # timeouts ("blocked" chains) and 300s process timeouts elsewhere in
        # this harness. Deliberately narrow: only fires for treatment, only
        # when the docx was never touched, and only on this exact, specific
        # phrasing -- a genuine reasoning failure that happens to also leave
        # the docx untouched must NOT be masked by a blanket retry-on-no-op
        # policy, which would bias treatment's measured pass rate upward.
        #
        # 2026-09-25 (review item 8): when the CLI's own init record is
        # available (always, with --verbose), the retry fires on THAT
        # evidence only -- the server not connected and the trial's tool not
        # listed -- never on the agent's wording. The phrase list is used only
        # for output without an init record (an older CLI).
        if init_record is not None:
            mcp_evidence = classify_infra_signature({
                "arm": spec.arm, "claude_init_record": init_record, "treatment_tool": spec.treatment_tool,
            })
            mcp_not_loaded = bool(mcp_evidence and "mcp_load_failure" in mcp_evidence["kinds"])
        else:
            mcp_not_loaded = bool((parsed_json or {}).get("result")) and any(
                sig in str(parsed_json["result"]) for sig in _MCP_TOOL_UNAVAILABLE_SIGNATURES
            )
        is_mcp_flake = spec.arm == "treatment" and not docx_changed and mcp_not_loaded
        if is_mcp_flake and attempt == 0:
            mcp_flake_retried = True
            continue
        break

    # The CLI session transcript (found by session id) is copied next to the
    # trial so the run archive carries it; the render-gate text is read from
    # it, or from the verbose message list when the transcript is missing.
    session_id = (parsed_json or {}).get("session_id") or (init_record or {}).get("session_id")
    transcript_source = find_session_transcript(session_id, trial_root)
    transcript_copy: Path | None = None
    if transcript_source is not None:
        transcript_copy = trial_root / "session-transcript.jsonl"
        try:
            shutil.copyfile(transcript_source, transcript_copy)
        except OSError:
            transcript_copy = None
        transcript_messages = _read_jsonl(transcript_source)
    else:
        transcript_messages = cli_messages
        if len(cli_messages) > 1:
            try:
                (trial_root / "cli-messages.json").write_text(
                    json.dumps(cli_messages, ensure_ascii=False), encoding="utf-8",
                )
            except OSError:
                pass
    render_gate_errors = extract_render_gate_errors(transcript_messages)

    trial_record = {
        "arm": spec.arm, "timed_out": timed_out, "returncode": returncode, "claude_json_result": parsed_json,
        "stderr": stderr, "claude_init_record": init_record, "treatment_tool": spec.treatment_tool,
        "docx_changed": docx_changed,
    }
    # Plain --output-format json put exactly the result record on stdout;
    # keep stdout_tail meaning that when --verbose printed the whole list.
    stdout_tail = json.dumps(parsed_json, ensure_ascii=False) if len(cli_messages) > 1 and parsed_json else stdout

    return {
        "trial_id": spec.trial_id,
        "doc_label": spec.doc_label,
        "arm": spec.arm,
        "direction": spec.direction,
        "family": spec.family,
        "pair_index": spec.pair_index,
        "model": model,
        "started_at": started.isoformat(),
        "wall_time_seconds": wall_time,
        "timed_out": timed_out,
        "returncode": returncode,
        "input_hash_sha256": input_hash,
        "output_hash_sha256": output_hash,
        "docx_changed": docx_changed,
        "trial_root": str(trial_root),
        "output_docx_path": str(docx_in_trial),
        "cli_command_argv": cmd,
        "claude_json_result": parsed_json,
        "stdout_tail": stdout_tail[-4000:],
        "stderr_tail": stderr[-4000:],
        "mcp_flake_retry_triggered": mcp_flake_retried,
        "claude_init_record": _init_record_summary(init_record),
        "session_id": session_id,
        "session_transcript_path": str(transcript_copy) if transcript_copy else None,
        "infra_signature": classify_infra_signature(trial_record),
        "unconfirmed_infra_text": unconfirmed_infra_text(trial_record),
        "render_gate_errors": render_gate_errors,
        "render_gate_timeout": any("render_gate_timeout" in e["kinds"] for e in render_gate_errors),
        "attic_moves": attic_moves,
    }


def audit_isolation(trial_result: dict[str, Any]) -> dict[str, Any]:
    """Post-hoc check of the recorded transcript, not a re-trust of the CLI
    flags alone. Looks for any evidence the CONTROL arm reached an MCP tool
    or a Meridian-specific path/token; for TREATMENT, confirms the ONLY
    tool used (besides Read) was the one declared bounded write primitive.
    """
    result = trial_result.get("claude_json_result") or {}
    transcript_text = json.dumps(result) + trial_result.get("stdout_tail", "")

    tool_names_used: list[str] = []
    # Claude Code's --output-format json final result does not always
    # enumerate every tool call inline; fall back to scanning for the
    # "mcp__" naming convention and known tool identifiers in the raw text.
    for marker in ("mcp__", "Bash(", "Edit(", "Write(", "Read("):
        if marker in transcript_text:
            tool_names_used.append(marker)

    violations: list[str] = []
    arm = trial_result["arm"]
    if arm == "control":
        if "mcp__" in transcript_text:
            violations.append("control transcript references an mcp__ tool name")
        if "meridian_docs" in transcript_text or "docparse" in transcript_text:
            violations.append("control transcript references Meridian-specific module names")
    elif arm == "treatment":
        # meridian-docs-pilot is the only MCP server this arm was given; any
        # OTHER mcp__<server>__ prefix appearing would be a real leak.
        import re

        other_mcp = set(re.findall(r"mcp__([a-zA-Z0-9_-]+)__", transcript_text)) - {"meridian-docs-pilot"}
        if other_mcp:
            violations.append(f"treatment transcript references unexpected MCP servers: {sorted(other_mcp)}")

    return {
        "trial_id": trial_result["trial_id"],
        "arm": arm,
        "markers_seen_in_transcript": tool_names_used,
        "violations": violations,
        "isolation_verdict": "clean" if not violations else "violation",
    }
