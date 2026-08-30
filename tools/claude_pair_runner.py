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
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
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


_CLAUDE_EXECUTABLE = _resolve_claude_executable()

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_trial_broker import TrialSpec  # noqa: E402

_PAPER_ROOT = Path(__file__).resolve().parent.parent
_PAPER_PYTHON = sys.executable
_TIMEOUT_SECONDS = 300.0

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

    common = [
        _CLAUDE_EXECUTABLE, "-p", spec.prompt,
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--permission-mode", "bypassPermissions",
        "--model", model,
        "--output-format", "json",
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


def run_trial(spec: TrialSpec, runs_root: Path, *, model: str = "haiku") -> dict[str, Any]:
    trial_root = runs_root / spec.trial_id
    trial_root.mkdir(parents=True, exist_ok=True)
    docx_in_trial = trial_root / "doc.docx"
    shutil.copyfile(spec.input_docx, docx_in_trial)
    input_hash = _sha256_file(docx_in_trial)

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
        prefix += (
            f"Use the {spec.treatment_tool} tool with these exact "
            f"arguments: {json.dumps(spec.treatment_args)}\n\n"
        )
    located_prompt = prefix + spec.prompt
    spec_with_path = dataclasses.replace(spec, prompt=located_prompt)

    cmd = _build_command(spec_with_path, trial_root, docx_in_trial, model)
    started = datetime.datetime.now(datetime.timezone.utc)
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=str(trial_root), capture_output=True, text=True,
            timeout=_TIMEOUT_SECONDS, encoding="utf-8", errors="replace",
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

    parsed_json: dict[str, Any] | None = None
    if stdout.strip():
        try:
            parsed_json = json.loads(stdout)
        except json.JSONDecodeError:
            parsed_json = None

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
        "docx_changed": input_hash != output_hash,
        "trial_root": str(trial_root),
        "output_docx_path": str(docx_in_trial),
        "cli_command_argv": cmd,
        "claude_json_result": parsed_json,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
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
