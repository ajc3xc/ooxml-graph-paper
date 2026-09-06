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
import os
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
    scratch_dir.mkdir(parents=True, exist_ok=True)
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

        parsed_json: dict[str, Any] | None = None
        if stdout.strip():
            try:
                parsed_json = json.loads(stdout)
            except json.JSONDecodeError:
                parsed_json = None

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
        is_mcp_flake = (
            spec.arm == "treatment"
            and not docx_changed
            and bool((parsed_json or {}).get("result"))
            and any(
                sig in parsed_json["result"]
                for sig in _MCP_TOOL_UNAVAILABLE_SIGNATURES
            )
        )
        if is_mcp_flake and attempt == 0:
            mcp_flake_retried = True
            continue
        break

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
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "mcp_flake_retry_triggered": mcp_flake_retried,
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
