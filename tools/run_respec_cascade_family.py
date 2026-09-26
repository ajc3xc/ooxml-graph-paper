"""PAPER-S23: heterogeneous cross-family cascade orchestrator for the
`respec_cascade` task family (docs/paper-s23-respec-cascade-protocol-v0.md).

Generalizes tools/run_paper_s7_benchmark.py::run_chain's structure --
deterministic chain_id/chain_root, crash-resume via a trusted checkpoint
file, current_input chaining between steps, Word-COM milestone receipts,
run_trial reuse for real subprocess isolation -- from run_chain's
homogeneous "K forward+inverse pairs of the SAME family" shape to this
design's heterogeneous, mixed-length step sequence: 5 build steps, 2 respec
steps, 10 second-exposure steps, all sharing one evolving .docx lineage
(protocol section 2.3, the five-family contingency R' = [Bibliography,
Citation, SectionReorder, Equation, Caption], locked 2026-09-20 because
insert_table/remove_table are confirmed absent from this session's live
meridian-docs tool manifest -- see protocol section 1.2a item 2).

This module is written against a CONTRACT for four sibling files another
session may be writing in parallel (protocol section 5 items 1-2, 5-6):
  - docx_anchor_prober.resolve_respec_schedule (new)
  - docx_trial_broker.generate_section_redirect_trial,
    generate_second_exposure_reorder_pair (new)
  - docx_trial_evaluator.grade_phase1_build, grade_phase2_respec,
    grade_phase3_second_exposure, chain_pass (new)
Everything else imported below already exists on disk as of this file's
own writing (2026-09-20) -- see this module's own docstring notes below
for the two places where the sibling contract underspecifies an exact
dict-key shape and this file had to make an explicit, documented judgment
call (search for "JUDGMENT CALL").

Package-validity gate scope (protocol section 4): deliberately narrow, the
same scope tools/docx_trial_evaluator.py::_package_is_valid_docx already
has -- ZIP structural integrity and required-part presence, NEVER whether
a given step's edit semantically succeeded. A step whose underlying task
failed (wrong text, tool declined, timed out) but that still left a
structurally valid .docx on disk passes this gate and the chain continues;
that step's semantic outcome is instead caught by the diagnostic
grade_phase1_build/grade_phase2_respec/grade_phase3_second_exposure calls,
never by the gate itself. This mirrors the protocol's own text precisely
("A failure freezes the chain at that exact step" -- freezing is for
package corruption, not task failure) and keeps this file from silently
re-defining a gate the protocol already specified elsewhere.

2026-09-25 additions (after the 2026-09-23 run's raw results were lost and
audited): a frozen chain records `freeze_cause` (package_invalid |
anchor_reresolution_failed | other), `freeze_detail` and `frozen_at_step`
beside the unchanged `chain_broken_at_step_<id>` status; a Phase-3 freeze
grades the round trips that had finished instead of discarding them
(`_phase3_result_before_freeze`); `grading_exceptions` lists every grader
crash's reason; `final_output_docx` names the chain's last valid document;
each step's full result is written to `<step dir>/step-result.json`; and
`six_family=True` runs protocol section 2.2's six-family rotation.

Later on 2026-09-25 (re-run preparation): a marker re-resolution freeze
records the forward step that inserted the missing marker
(`frozen_step_result`, summarized as `freeze_forward_step`: its timed_out,
returncode, package validity), every freeze records `frozen_family` mapped
through the chain's own rotation (`step_family`); a step with an
infrastructure signature stops the chain as `infra_blocked` (never trusted
on resume); a sweep's CircuitBreaker is checked before every step; and every
attempt is counted in a ledger outside the chain root, with an earlier
attempt's files moved to `<run_root>/attic/` (claude_pair_runner).
"""
from __future__ import annotations

import contextvars
import dataclasses
import datetime
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_anchor_prober import (  # noqa: E402
    resolve_equation_para_id_by_marker,
    resolve_para_id_by_marker_text,
    resolve_respec_schedule,
    resolve_table_index_by_marker,
)
from docx_trial_broker import (  # noqa: E402
    TrialSpec,
    _paragraph_texts,
    generate_bibliography_pair,
    generate_caption_forward,
    generate_caption_inverse,
    generate_citation_forward,
    generate_citation_inverse,
    generate_equation_forward,
    generate_equation_inverse,
    generate_second_exposure_reorder_pair,
    generate_section_redirect_trial,
    generate_section_reorder_pair,
    generate_table_structural_forward,
    generate_table_structural_inverse,
    new_marker,
)
from docx_trial_evaluator import (  # noqa: E402
    _AUTO_CREATED_REFERENCES_HEADING_TEXT,
    _collateral_diff_outside_touched,
    _equation_flat_texts,
    _family_own_target_ok,
    _grade_family_inverse,
    _items_with_equations,
    _package_is_valid_docx,
    chain_pass,
    grade_forward_trial_table_structural,
    grade_inverse_trial_table_structural,
    grade_phase1_build,
    grade_phase2_respec,
    grade_phase3_second_exposure,
)
from graph_scorer import score_keep_survival  # noqa: E402
from claude_pair_runner import (  # noqa: E402
    CircuitBreaker,
    CircuitOpenError,
    audit_isolation,
    begin_chain_attempt,
    exhausted_chain_result,
    finish_chain_attempt,
    infra_signature_of,
    run_trial,
)
from usage_cap import UsagePauseController  # noqa: E402
from word_receipt_watchdog import word_receipt_with_orphan_diagnostics  # noqa: E402

_WORD_RECEIPT_TIMEOUT_SECONDS = 90.0
_FAMILY = "respec_cascade"

# Protocol section 2.3's five-family contingency R' (the default, and the only
# rotation the 2026-09-23 run used) and section 2.2's six-family rotation R,
# which adds table_structural (1.5 insert, 2.2 revert, 3.5 insert+remove;
# caption moves to 1.6/3.6). The six-family rotation needs insert_table/
# remove_table, which the harness's own meridian-docs server (the one
# claude_pair_runner launches) registers; section 1.2a dropped them only
# because a stale, separately installed build lacked them. Six-family runs are
# opt-in (`six_family=True` / --six-family) and are never merged with
# five-family results.
FIVE_FAMILY_ROTATION: tuple[str, ...] = ("bibliography", "citation", "section_reorder", "equation", "caption")
SIX_FAMILY_ROTATION: tuple[str, ...] = (
    "bibliography", "citation", "section_reorder", "equation", "table_structural", "caption",
)

# Why a chain froze (`freeze_cause` in a frozen chain's result; the status
# string stays chain_broken_at_step_<id> for compatibility and is the same
# for every cause).
FREEZE_CAUSE_PACKAGE_INVALID = "package_invalid"
FREEZE_CAUSE_ANCHOR_RERESOLUTION = "anchor_reresolution_failed"
FREEZE_CAUSE_OTHER = "other"

# A chain with a step whose trial has an infrastructure signature
# (claude_pair_runner.classify_infra_signature). Never trusted on resume.
STATUS_INFRA_BLOCKED = "infra_blocked"
STATUS_ABORTED_CIRCUIT_OPEN = "aborted_circuit_open"

_STEP_RESULT_NAME = "step-result.json"

# Phase-2 steps name their family explicitly; Phase-1 and Phase-3 steps are
# numbered by position in the chain's rotation (3.5 is caption in the
# five-family rotation but table_structural in the six-family one).
_PHASE2_STEP_FAMILIES = {"2.1": "citation", "2.2": "table_structural", "2.3": "section_reorder"}


def step_family(step_id: str, rotation: tuple[str, ...] | list[str]) -> str | None:
    """The family a step id (a freeze id such as "3.5-inverse" or "3.3a", or a
    trial id such as "1.6-caption-forward") belongs to, mapped through the
    chain's recorded `rotation` rather than a fixed family list. None when the
    id does not name a step."""
    match = re.match(r"^([123])\.(\d+)", step_id or "")
    if not match:
        return None
    phase, index = match.group(1), int(match.group(2))
    if phase == "2":
        return _PHASE2_STEP_FAMILIES.get(f"2.{index}")
    return rotation[index - 1] if 1 <= index <= len(rotation) else None


# The sweep's CircuitBreaker for the chain running in this thread (set by
# run_respec_cascade_chain around its attempt, read by _run_step).
_ACTIVE_CIRCUIT_BREAKER: contextvars.ContextVar[CircuitBreaker | None] = contextvars.ContextVar(
    "respec_cascade_circuit_breaker", default=None,
)
# The sweep's usage_cap.UsagePauseController (rate-limit handling), set and
# read the same way. Optional and purely additive -- see infra_signature_of's
# own docstring for what a non-None value does.
_ACTIVE_PAUSE_CONTROLLER: contextvars.ContextVar[UsagePauseController | None] = contextvars.ContextVar(
    "respec_cascade_pause_controller", default=None,
)
# One compact record per step run in this attempt (written to the chain
# result as `step_log`), so a chain's timeouts, render-gate errors and cost are
# readable from chain-result.json without opening every step-result.json.
_ACTIVE_STEP_LOG: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "respec_cascade_step_log", default=None,
)


def _step_log_entry(result: dict[str, Any]) -> dict[str, Any]:
    cli = result.get("claude_json_result") if isinstance(result.get("claude_json_result"), dict) else {}
    return {
        "step_id": result.get("step_id"), "timed_out": result.get("timed_out"),
        "returncode": result.get("returncode"), "docx_changed": result.get("docx_changed"),
        "package_valid": result.get("package_valid"), "wall_time_seconds": result.get("wall_time_seconds"),
        "total_cost_usd": cli.get("total_cost_usd"),
        "render_gate_timeout": result.get("render_gate_timeout"),
        "render_gate_error_kinds": sorted({k for e in result.get("render_gate_errors") or [] for k in e.get("kinds", [])}),
        "infra_signature": result.get("infra_signature"),
    }


class _InfraSignatureStop(Exception):
    """Raised by _run_step when a step's trial has an infrastructure signature;
    run_respec_cascade_chain turns it into an infra_blocked result."""

    def __init__(self, step: dict[str, Any], signature: dict[str, Any]) -> None:
        super().__init__(f"infrastructure signature at step {step.get('step_id')}: {signature.get('kinds')}")
        self.step = step
        self.signature = signature

# Confirmed against the real, now-landed tools/docx_anchor_prober.py
# (resolve_respec_schedule/resolve_section_redirect_plan appeared on disk,
# written by a concurrent session, partway through this file's own
# development -- re-read directly rather than left as a guess): each
# anchor-set's "section_reorder_plan" dict merges the D1 plan's existing
# keys with a nested "redirect" dict holding "found",
# "redirect_destination_heading_para_id", "redirect_destination_heading_text"
# (plus its own section_id/section_heading_text, redundant with the outer
# plan's). These two accessors centralize that nesting so only they need
# to change if the sibling implementation's shape moves again.
def _d2_heading_para_id(plan: dict[str, Any]) -> str:
    return plan["redirect"]["redirect_destination_heading_para_id"]


def _d2_heading_text(plan: dict[str, Any]) -> str:
    return plan["redirect"]["redirect_destination_heading_text"]

_CHECKPOINT_NAME = "chain-result.json"


def _safe_paragraph_texts(docx_path: Path) -> list[str] | None:
    """Mirrors run_paper_s7_benchmark.py::_safe_paragraph_texts exactly (not
    imported -- that function is private to its own module and this file
    avoids the backwards/sideways private-import coupling the ground-truth
    brief warned against for _grade_forward/_grade_inverse): a raw zipfile
    read against a step's own output must never crash the whole chain as an
    unhandled harness_exception just because a PRIOR step (either arm) left
    a corrupted or unwritten package behind. Returns None (never raises) on
    any corruption/absence; callers treat None as "cannot continue from
    this document," never as an empty-but-valid paragraph list."""
    try:
        return _paragraph_texts(docx_path)
    except (KeyError, zipfile.BadZipFile, ET.ParseError, FileNotFoundError):
        return None


def _safe_call(fn, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """grade_phase1_build/grade_phase2_respec/grade_phase3_second_exposure/
    chain_pass are first-use code (protocol section 8's own disclosed risk:
    "New grading code is first-use code ... have never run before"). A raised
    exception here must degrade to a graded, inspectable failure dict, never
    an unhandled crash that discards an otherwise-completed 17-step chain's
    worth of real subprocess work -- the same principle
    run_paper_s7_benchmark.py::_safe_grade already applies to the six
    existing families' own grading functions."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 -- must never propagate, see docstring
        return {
            "status": "grading_raised_exception",
            "reason": f"{type(exc).__name__}: {exc}",
        }


def _grading_exceptions(graded: dict[str, Any]) -> list[dict[str, Any]]:
    """Every `_safe_call` stub among `graded` ({name: grader result}), plus
    any stub inside a phase result's own per-family dict, as
    [{"grader": name, "reason": ...}] -- written to the chain result as
    `grading_exceptions`, so a grader crash's reason is never lost behind a
    plain completed_with_failure status (e.g. when chain_pass itself raises,
    whose stub is otherwise only read for its missing "pass" key)."""
    found: list[dict[str, Any]] = []
    for name, result in graded.items():
        if not isinstance(result, dict):
            continue
        if result.get("status") == "grading_raised_exception":
            found.append({"grader": name, "reason": result.get("reason")})
        for family, family_result in (result.get("families") or {}).items():
            if isinstance(family_result, dict) and family_result.get("status") == "grading_raised_exception":
                found.append({"grader": f"{name}:{family}", "reason": family_result.get("reason")})
    return found


def _milestone_word_receipt(docx_path: Path, out_dir: Path, *, milestone: str) -> dict[str, Any]:
    if not docx_path.is_file():
        return {"milestone": milestone, "status": "not_run", "reason": "input docx does not exist"}
    try:
        result = word_receipt_with_orphan_diagnostics(docx_path, out_dir, timeout=_WORD_RECEIPT_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        return {"milestone": milestone, "status": "not_run", "reason": f"{type(exc).__name__}: {exc}"}
    result["milestone"] = milestone
    result["status"] = result.get("render_receipt", {}).get("status", "unknown")
    return result


def _load_checkpoint(chain_root: Path) -> dict[str, Any] | None:
    path = chain_root / _CHECKPOINT_NAME
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    status = result.get("status", "")
    # "completed"/"completed_with_failure"/"not_applicable" are genuine,
    # deterministic outcomes, trusted on resume exactly like run_chain's own
    # checkpoint. "infra_blocked" is never trusted (the chain is re-run).
    # "chain_broken_at_step_*" is ALSO trusted here (unlike
    # run_chain's legacy "blocked", which is deliberately never trusted): a
    # package-validity gate failure recorded by THIS module is, by the
    # protocol's own design, a real structural finding about that step's
    # output ("A failure freezes the chain at that exact step" -- section 4),
    # not an infra hiccup like a Windows process-launch flake -- so re-running
    # it blind on resume would not produce different ground truth, only cost.
    trusted = status in ("completed", "completed_with_failure", "not_applicable") or status.startswith(
        "chain_broken_at_step_"
    )
    if not trusted:
        return None
    return result


def _write_checkpoint(chain_root: Path, result: dict[str, Any]) -> None:
    # Atomic write, exactly mirroring run_chain's own mechanism: a crash
    # mid-write must never leave a checkpoint _load_checkpoint could
    # half-parse and wrongly trust.
    tmp_path = chain_root / f"{_CHECKPOINT_NAME}.tmp"
    tmp_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(chain_root / _CHECKPOINT_NAME)


def _run_step(
    spec: TrialSpec, chain_root: Path, model: str, arm: str, step_id: str, current_input: Path,
) -> dict[str, Any]:
    """Executes exactly one of the chain's 17 tool-call steps.

    Overrides arm/trial_id/input_docx on ``spec`` immediately before running
    it -- this reproduces, for every step regardless of which generator
    built the spec, the exact override run_chain itself performs
    unconditionally right before every run_trial call (run_chain lines
    ~454-457: ``dataclasses.replace(inverse_spec, arm=arm, pair_index=...,
    trial_id=..., input_docx=Path(fwd_result["output_docx_path"]))`` -- note
    this happens for EVERY inverse spec there, including one already fully
    formed by generate_bibliography_pair/generate_section_reorder_pair, not
    only ones synthesized post-resolution). The respec_cascade chain needs
    this even more than a K-pair chain does: a step's ``spec.input_docx`` as
    originally built by its generator reflects whatever document snapshot
    was current AT GENERATION TIME, but by the time a step actually runs,
    zero or more OTHER families' steps may have advanced the real on-disk
    lineage further (Phase 1's 1.3/1.4/1.5 run between 1.2's own generation
    and 2.1's citation-inverse execution, for instance) -- so this override
    is the one place that keeps every step honestly attached to the chain's
    actual current state rather than a stale generation-time snapshot.

    Runs via claude_pair_runner.run_trial (the real subprocess-isolation
    primitive -- reused directly, never reimplemented), audits isolation,
    and applies the package-validity gate. Never raises: a run_trial-level
    exception is not expected (run_trial itself does not raise on a killed
    subprocess or a bad exit -- see its own docstring), but the validity
    check is always performed against whatever ``output_docx_path`` comes
    back, structurally-invalid or not.
    """
    step_spec = dataclasses.replace(spec, arm=arm, trial_id=step_id, input_docx=current_input)
    circuit_breaker = _ACTIVE_CIRCUIT_BREAKER.get()
    if circuit_breaker is not None:
        circuit_breaker.check(f"{chain_root.name}/{step_id}")
    result = run_trial(step_spec, chain_root, model=model)
    result["isolation_audit"] = audit_isolation(result)
    result["step_id"] = step_id
    output_path = Path(result["output_docx_path"])
    valid, reason = _package_is_valid_docx(output_path)
    result["package_valid"] = valid
    result["package_invalid_reason"] = reason
    # The step's full result (agent transcript tail, timing, hashes) was
    # previously only held in memory; persisted next to its doc.docx so the
    # run archive (run_respec_cascade_sweep.py --archive) carries it.
    try:
        (Path(result["trial_root"]) / _STEP_RESULT_NAME).write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8",
        )
    except OSError:
        pass
    step_log = _ACTIVE_STEP_LOG.get()
    if step_log is not None:
        step_log.append(_step_log_entry(result))
    signature = infra_signature_of(
        result, circuit_breaker, f"{chain_root.name}/{step_id}", pause_controller=_ACTIVE_PAUSE_CONTROLLER.get(),
    )
    if signature is not None:
        raise _InfraSignatureStop(result, signature)
    return result


def _forward_step_summary(step: dict[str, Any] | None) -> dict[str, Any] | None:
    """The fields of the forward step behind a missing marker that tell a
    harness timeout apart from the arm deleting (or never inserting) it."""
    if step is None:
        return None
    return {
        key: step.get(key)
        for key in ("step_id", "timed_out", "returncode", "docx_changed", "package_valid",
                    "package_invalid_reason", "wall_time_seconds", "render_gate_timeout")
    }


def _resolve_or_none(resolver, docx_path: Path, marker_text: str) -> dict[str, Any]:
    """Wraps a docx_anchor_prober post-forward resolver
    (resolve_para_id_by_marker_text / resolve_equation_para_id_by_marker) the
    same way run_chain's own inverse-resolution block does (see its comment
    at the try/except around its ``resolver(...)`` call): a malformed/
    corrupted forward output must degrade to a normal ``{"found": False,
    "reason": ...}`` result this file already knows how to freeze the chain
    on, never an unhandled exception that discards an otherwise-completed
    step."""
    try:
        return resolver(docx_path, marker_text)
    except Exception as exc:  # noqa: BLE001 -- see docstring
        return {"found": False, "reason": f"resolver raised {type(exc).__name__}: {exc}"}


def _grade_phase3_round_trip(family: str, target: dict[str, Any]) -> dict[str, Any]:
    """One finished Phase-3 insert-then-remove round trip, graded on its own:
    the family's existing inverse grader applied to that round trip's own
    inverse output against the paragraphs before its own forward step."""
    if family == "table_structural":
        return grade_inverse_trial_table_structural(
            target["inverse_output_docx"], target["paragraphs_before_forward"], target["marker_text"],
        )
    return _grade_family_inverse(family, target["inverse_output_docx"], target["paragraphs_before_forward"], target)


def _phase3_result_before_freeze(
    rotation: tuple[str, ...], phase3_targets: dict[str, Any], frozen_step_id: str,
) -> dict[str, Any]:
    """`phase3_result` for a chain that froze during Phase 3. Checkpoint C was
    never reached, so `phase3_pass` is False; but every family whose round
    trip FINISHED before the freeze is graded (`_grade_phase3_round_trip`)
    instead of being discarded, the family whose round trip was under way is
    marked `not_completed`, and every later family `not_run` -- all because
    of the freeze. (Before 2026-09-25 this was simply None, losing the
    verdicts of round trips that had actually run.) These per-family
    verdicts are diagnostics; compute_respec_cascade_statistics does not
    count them as Checkpoint-C outcomes."""
    families: dict[str, Any] = {}
    in_progress_marked = False
    for family in rotation:
        target = phase3_targets.get(family)
        if target is not None:
            families[family] = _safe_call(_grade_phase3_round_trip, family, target)
        elif not in_progress_marked:
            families[family] = {
                "verdict": "not_completed",
                "reason": f"chain froze at step {frozen_step_id} during this family's Phase-3 round trip",
            }
            in_progress_marked = True
        else:
            families[family] = {
                "verdict": "not_run",
                "reason": f"chain froze at step {frozen_step_id} before this family's Phase-3 round trip",
            }
    return {
        "status": "frozen_before_checkpoint_c",
        "frozen_at_step": frozen_step_id,
        "phase3_pass": False,
        "grading_scope": (
            "per round trip: each finished family's inverse output against the paragraphs before its own "
            "forward step; no final-structure or keep-survival check (Checkpoint C was never reached)"
        ),
        "families": families,
    }


# ---------------------------------------------------------------------------
# Six-family grading. docx_trial_evaluator's phase graders cover exactly the
# five families of R'; for the six-family rotation these wrappers grade
# table_structural with that module's existing table graders and fold the
# table into each checkpoint's own pass, so the table's legitimate edits are
# not read as collateral damage by the five-family checks. (The touched-text
# bookkeeping below repeats grade_phase1_build's; it belongs in the evaluator
# and should move there.)
# ---------------------------------------------------------------------------

def _grade_phase1_six_family(
    phase1_result: dict[str, Any], checkpoint_a_docx: Path, paragraphs_before: list[str],
    phase1_targets: dict[str, Any], table_marker: str,
) -> dict[str, Any]:
    """Checkpoint A with the table: grade_phase1_build's five-family result
    plus the table's own forward check, and the phase-wide collateral check
    re-run with the table cell's paragraph counted as an intended touch."""
    if not phase1_result.get("package_valid", False):
        return phase1_result
    table = grade_forward_trial_table_structural(checkpoint_a_docx, paragraphs_before, table_marker)
    families = phase1_result["families"]
    touched_before = [phase1_targets["citation"]["anchor_text_before"]]
    touched_after = [
        *families["bibliography"].get("matching_paragraphs", []),
        *families["caption"].get("matching_paragraphs", []),
        *families["citation"].get("anchor_matches_after", []),
        *table.get("matching_paragraphs", []),
    ]
    if _AUTO_CREATED_REFERENCES_HEADING_TEXT not in paragraphs_before:
        touched_after.append(_AUTO_CREATED_REFERENCES_HEADING_TEXT)
    collateral_clean, collateral_detail = _collateral_diff_outside_touched(
        paragraphs_before, _paragraph_texts(checkpoint_a_docx), touched_before, touched_after,
    )
    table_checks = table.get("checks") or {}
    table_ok = bool(table_checks.get("output_is_valid_docx") and table_checks.get("marker_table_cell_present_exactly_once"))
    five_ok = all(_family_own_target_ok(f, families[f]) for f in FIVE_FAMILY_ROTATION)
    return {
        **phase1_result,
        "families": {**families, "table_structural": table},
        "collateral_clean_five_family_view": phase1_result.get("collateral_clean"),
        "collateral_clean": collateral_clean,
        "collateral_detail": collateral_detail,
        "phase1_pass": bool(five_ok and table_ok and collateral_clean),
    }


def _grade_phase2_six_family(
    phase2_result: dict[str, Any], checkpoint_a_docx: Path, checkpoint_b_docx: Path,
    paragraphs_at_checkpoint_a: list[str], citation_marker_text: str, citation_anchor_text_before: str,
    kept_markers: dict[str, str], table_marker: str,
) -> dict[str, Any]:
    """Checkpoint B with the table (protocol section 4 item 1: citation AND
    table absent): the table must be gone, and keep-survival is re-scored
    with the reverted table's paragraph excluded like the reverted
    citation's (grade_phase2_respec excludes only the citation)."""
    if not phase2_result.get("package_valid", False):
        return phase2_result
    paragraphs_at_checkpoint_b = _paragraph_texts(checkpoint_b_docx)
    remaining_table_markers = [p for p in paragraphs_at_checkpoint_b if table_marker in p]
    excluded_texts = [
        *(p for p in paragraphs_at_checkpoint_a if citation_marker_text in p),
        citation_anchor_text_before,
        *(p for p in paragraphs_at_checkpoint_a if table_marker in p),
    ]
    keep_survival = score_keep_survival(
        _items_with_equations(checkpoint_a_docx, paragraphs_at_checkpoint_a),
        _items_with_equations(checkpoint_b_docx, paragraphs_at_checkpoint_b),
        kept_markers,
        excluded_paragraph_texts=excluded_texts,
    )
    table_absent = not remaining_table_markers
    return {
        **phase2_result,
        "table_absent": table_absent,
        "remaining_table_markers": remaining_table_markers,
        "keep_survival_five_family_view": phase2_result.get("keep_survival"),
        "keep_survival": keep_survival,
        "phase2_pass": bool(
            phase2_result.get("citation_absent") and table_absent and phase2_result.get("section_at_d2")
            and keep_survival.get("overall_status") == "clean_keep_survival"
        ),
    }


def _grade_phase3_six_family(
    phase3_result: dict[str, Any], checkpoint_c_docx: Path, paragraphs_at_checkpoint_b: list[str],
    table_markers: list[str], second_exposure_table_marker: str,
) -> dict[str, Any]:
    """Checkpoint C with the table: the table's own Phase-3 round trip (its
    existing inverse grader, same net-effect framing as the other families
    in grade_phase3_second_exposure) and both table markers (1.5's and
    3.5's) absent from the final document."""
    if not phase3_result.get("package_valid", False):
        return phase3_result
    table = grade_inverse_trial_table_structural(checkpoint_c_docx, paragraphs_at_checkpoint_b, second_exposure_table_marker)
    table_leftovers = [p for p in _paragraph_texts(checkpoint_c_docx) if any(m in p for m in table_markers)]
    table_checks = table.get("checks") or {}
    table_ok = bool(table_checks.get("output_is_valid_docx") and table_checks.get("marker_table_removed"))
    final_structure_match = bool(phase3_result.get("final_structure_match") and not table_leftovers)
    return {
        **phase3_result,
        "families": {**(phase3_result.get("families") or {}), "table_structural": table},
        "final_structure_match_five_family_view": phase3_result.get("final_structure_match"),
        "final_structure_match": final_structure_match,
        "table_leftovers": table_leftovers,
        "phase3_pass": bool(phase3_result.get("phase3_pass") and table_ok and final_structure_match),
    }


def run_respec_cascade_chain(
    doc_label: str, docx_path: Path, arm: str, model: str, run_root: Path, anchor_set: dict[str, Any],
    *, word_receipts_enabled: bool = True, six_family: bool = False,
    circuit_breaker: CircuitBreaker | None = None, max_chain_attempts: int | None = None,
    pause_controller: UsagePauseController | None = None,
) -> dict[str, Any]:
    """Runs one full 17-tool-call, 3-phase respec_cascade chain for one
    (document, anchor-set, arm) combination. See this module's docstring for
    the sibling-file contract this is written against, and protocol section
    2.3 for the exact five-family step sequence.

    `six_family=True` runs protocol section 2.2's six-family rotation instead
    (21 tool calls: table_structural at 1.5, 2.2 and 3.5; caption at 1.6 and
    3.6). It needs `anchor_set["table_anchor"]` (see
    run_respec_cascade_sweep.add_table_anchors) and writes to its own
    chain_id, so it can never resume from or overwrite a five-family chain.

    `circuit_breaker` (the sweep's claude_pair_runner.CircuitBreaker) is
    checked before every step; CircuitOpenError propagates to the sweep.
    `max_chain_attempts` limits chargeable attempts (see
    claude_pair_runner.begin_chain_attempt); None means no limit.
    `pause_controller` (usage_cap.UsagePauseController; rate-limit handling)
    is told about every step's trial so a usage-cap/rate-limit signal pauses
    and later auto-resumes the sweep; purely additive, None reproduces the
    exact prior behavior.
    """
    rotation = SIX_FAMILY_ROTATION if six_family else FIVE_FAMILY_ROTATION
    # 2026-09-22 correction (found live, RunPod primary sweep, all 24
    # chains): a plain `doc_label[:32]` truncation silently COLLIDES for any
    # doc_label sharing the same first-32-characters prefix -- confirmed
    # concretely: "masters-dissertation-defense__anchor0" through
    # "...anchor3" (the real f"{original}__anchor{i}" convention
    # tools/run_respec_cascade_sweep.py uses) all truncate to the IDENTICAL
    # "masters-dissertation-defense__an", since the distinguishing digit
    # falls at position 37, past the cutoff. This made all 4 of that
    # document's anchor-set chains (per arm) share one chain_id/chain_root,
    # silently overwriting each other's checkpoints -- real corrupted data,
    # not a cosmetic naming issue: 3 of the 4 anchor-sets' real results were
    # lost for that document in that run. Fixed by keeping the truncation
    # short (for filesystem path-length headroom) but appending a short
    # hash of the FULL doc_label, so two labels sharing a long common
    # prefix can never collide.
    doc_label_hash = hashlib.sha256(doc_label.encode("utf-8")).hexdigest()[:8]
    short_doc_label = f"{doc_label[:24]}-{doc_label_hash}"
    chain_id = f"{short_doc_label}-{_FAMILY}-six-{arm}" if six_family else f"{short_doc_label}-{_FAMILY}-{arm}"
    chain_root = run_root / chain_id
    chain_root.mkdir(parents=True, exist_ok=True)

    # 2026-09-22 correction #2 (found live, RunPod primary sweep, EVERY
    # treatment chain): `short_doc_label` (above) is fine for chain_id/
    # directory naming (no length constraint there) but is still far too
    # long to use inside a MARKER passed to new_marker() -- confirmed
    # concretely: insert_bibliography_entry's own duplicate-detection is by
    # BOOKMARK NAME, sanitized then truncated to 40 chars
    # (meridian_docs/docs_intel.py::_find_bibliography_entry,
    # `safe_key = safe_key[:40]`, Word's classic bookmark-name limit). With
    # doc_label now `f"{original}__anchor{i}"`-suffixed (tools/
    # run_respec_cascade_sweep.py) plus this file's own "pilot-s7-" /
    # "respec-" prefixing, B's and B2's citation keys shared an IDENTICAL
    # 40-char truncated bookmark name ('pilot_s7_respec_jcshm_manuscript__
    # anchor', verified by direct reproduction) -- Phase 1's B and Phase 3's
    # B2 were never two entries at all; insert_bibliography_entry correctly
    # refused the second insert as a duplicate, the agent recovered via
    # update_bibliography_entry exactly as instructed, and that update
    # OVERWROTE B's own entry with B2's content, silently discarding B --
    # a real, 100%-reproducible defect in EVERY treatment chain, not a
    # rare flake. `doc_tag` (pure 8-hex-char hash, no doc_label text at
    # all) replaces `short_doc_label` in every marker prefix below so the
    # distinguishing role token (B vs B2, C vs C2, ...) plus new_marker's
    # own 12-hex-char uniqueness suffix both comfortably survive ANY
    # plausible truncation limit, regardless of how long doc_label is.
    doc_tag = doc_label_hash

    checkpoint = _load_checkpoint(chain_root)
    if checkpoint is not None:
        return checkpoint

    base_result = {
        "chain_id": chain_id, "doc_label": doc_label, "family": _FAMILY, "arm": arm,
        "anchor_set_index": anchor_set.get("anchor_set_index"), "model": model,
        "rotation": list(rotation),
    }

    # No trusted checkpoint: a new attempt, counted in the ledger outside the
    # chain root; an earlier attempt's files go to <run_root>/attic/.
    attempt = begin_chain_attempt(run_root, chain_id, chain_root, max_chain_attempts=max_chain_attempts)
    if attempt.exhausted:
        # 2026-09-26 fix (M1): this chain's rerun-once budget is exhausted, so
        # `begin_chain_attempt` deliberately left `chain_root` untouched
        # (nothing is moved -- see its own docstring): whatever a prior
        # attempt wrote there (typically an `infra_blocked` chain-result.json)
        # is still on disk. Without writing the infra_excluded result here,
        # that stale file disagreed with the sweep manifest, which does
        # record this chain as infra_excluded. `_load_checkpoint` does not
        # trust status "infra_excluded" (see its own trusted-status set), so
        # writing it does NOT make a future relaunch skip re-checking this
        # chain's ledger -- the chain is correctly recognized as exhausted
        # again from `_chain_attempts/`, not from this checkpoint, and no new
        # attempt is started either way.
        result = exhausted_chain_result(attempt, base_result, max_chain_attempts)
        _write_checkpoint(chain_root, result)
        return result
    base_result["attempt"] = attempt.number
    token = _ACTIVE_CIRCUIT_BREAKER.set(circuit_breaker)
    pause_token = _ACTIVE_PAUSE_CONTROLLER.set(pause_controller)
    step_log: list[dict[str, Any]] = []
    log_token = _ACTIVE_STEP_LOG.set(step_log)
    try:
        result = _run_respec_cascade_attempt(
            doc_label, docx_path, arm, model, anchor_set, chain_root=chain_root, rotation=rotation,
            doc_tag=doc_tag, base_result=base_result, word_receipts_enabled=word_receipts_enabled,
            six_family=six_family,
        )
    except _InfraSignatureStop as stop:
        # Review item 23 / S25 5.5: a step with an infrastructure signature
        # makes the chain infra_blocked; it stops there and is re-run.
        result = {
            **base_result, "status": STATUS_INFRA_BLOCKED, "reason": str(stop),
            "infra_signature": {**stop.signature, "step_id": stop.step.get("step_id")},
            "infra_step_result": stop.step,
            "phase1_result": None, "phase2_result": None, "phase3_result": None,
        }
        _write_checkpoint(chain_root, result)
    except CircuitOpenError:
        finish_chain_attempt(attempt, STATUS_ABORTED_CIRCUIT_OPEN)
        raise
    except Exception:
        finish_chain_attempt(attempt, "harness_exception")
        raise
    finally:
        _ACTIVE_CIRCUIT_BREAKER.reset(token)
        _ACTIVE_PAUSE_CONTROLLER.reset(pause_token)
        _ACTIVE_STEP_LOG.reset(log_token)
    result["step_log"] = step_log
    result["render_gate_timeout_steps"] = [s["step_id"] for s in step_log if s.get("render_gate_timeout")]
    _write_checkpoint(chain_root, result)
    finish_chain_attempt(attempt, result["status"], infra_scope=(result.get("infra_signature") or {}).get("scope"))
    return result


def _run_respec_cascade_attempt(
    doc_label: str, docx_path: Path, arm: str, model: str, anchor_set: dict[str, Any], *,
    chain_root: Path, rotation: tuple[str, ...], doc_tag: str, base_result: dict[str, Any],
    word_receipts_enabled: bool, six_family: bool,
) -> dict[str, Any]:
    """One attempt of run_respec_cascade_chain (everything after the
    checkpoint and attempt bookkeeping); writes the chain's checkpoint."""
    not_applicable_reason = None
    if not anchor_set.get("usable", False):
        not_applicable_reason = anchor_set.get("reason")
    elif six_family and not (anchor_set.get("table_anchor") or {}).get("found"):
        not_applicable_reason = "missing_table_anchor"
    if not_applicable_reason is not None or not anchor_set.get("usable", False):
        result = {
            **base_result, "status": "not_applicable", "reason": not_applicable_reason,
            "phase1_result": None, "phase2_result": None, "phase3_result": None,
            "steps_run": 0, "word_com_receipts": [],
        }
        _write_checkpoint(chain_root, result)
        return result

    citation_anchor = anchor_set["citation_anchor"]
    equation_anchor = anchor_set["equation_anchor"]
    caption_anchor = anchor_set["caption_anchor"]
    table_anchor = anchor_set.get("table_anchor") if six_family else None
    plan = anchor_set["section_reorder_plan"]
    # Caption is the 5th family of R' but the 6th of R.
    caption_n = "6" if six_family else "5"

    original_paragraphs = _paragraph_texts(docx_path)
    receipts: list[dict[str, Any]] = []
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(docx_path, chain_root / "receipts" / "chain-start", milestone="chain_start"))

    current_input = docx_path
    steps_run = 0
    # Populated once Phase 1/2's own diagnostic grading actually runs (after
    # step 1.5, resp. 2.3) -- _freeze reads whatever is here AT THE TIME it's
    # called, so a freeze during Phase 2 or Phase 3 still preserves an
    # earlier phase's already-computed result instead of discarding it.
    # Previously this was unconditionally hardcoded to None in every freeze,
    # which silently threw away real diagnostic signal (e.g. whether Phase
    # 1's own per-family content grading actually passed) for any chain that
    # froze partway through Phase 2/3 -- exactly the case that most needs it,
    # since that's when something has already gone wrong and the "did the
    # earlier phases even semantically succeed" question matters most.
    phase1_result: dict[str, Any] | None = None
    phase2_result: dict[str, Any] | None = None
    # None until Phase 3 starts; then {family: round-trip target}, one entry
    # added as each family's Phase-3 round trip finishes (read by _freeze).
    phase3_targets: dict[str, Any] | None = None

    def _freeze(
        step_id: str, step_result: dict[str, Any] | None, extra_reason: str | None = None, *,
        cause: str | None = None, forward_step: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # forward_step: for a marker re-resolution freeze (no step of its own
        # ran), the forward step that inserted the missing marker -- its
        # timed_out/returncode distinguish a harness timeout that left the
        # document unchanged from the arm deleting or never inserting it.
        reason = extra_reason if extra_reason is not None else (step_result or {}).get("package_invalid_reason")
        # The status string is the same for every cause (kept for
        # compatibility); freeze_cause says which gate actually stopped it.
        if cause is None:
            cause = (
                FREEZE_CAUSE_PACKAGE_INVALID if step_result is not None and not step_result.get("package_valid", True)
                else FREEZE_CAUSE_OTHER
            )
        phase3_result = (
            _phase3_result_before_freeze(rotation, phase3_targets, step_id) if phase3_targets is not None else None
        )
        result = {
            **base_result, "status": f"chain_broken_at_step_{step_id}", "reason": reason,
            "freeze_cause": cause, "freeze_detail": reason, "frozen_at_step": step_id,
            "frozen_family": step_family(step_id, rotation),
            "phase1_result": phase1_result, "phase2_result": phase2_result, "phase3_result": phase3_result,
            "steps_run": steps_run, "word_com_receipts": receipts,
            "frozen_step_result": step_result if step_result is not None else forward_step,
            "freeze_forward_step": _forward_step_summary(forward_step),
            "final_output_docx": str(current_input),
            "grading_exceptions": _grading_exceptions(
                {"phase1_result": phase1_result, "phase2_result": phase2_result, "phase3_result": phase3_result},
            ),
        }
        _write_checkpoint(chain_root, result)
        return result

    # -------------------------------------------------------------------
    # PHASE 1 -- BUILD (5 steps, forward-only, order R')
    # -------------------------------------------------------------------

    marker_b = new_marker(f"{doc_tag}-bib-B")
    bib_forward, _bib_inverse_unused = generate_bibliography_pair(doc_label, current_input, marker_b)
    # B is never removed anywhere in this chain (Phase 1 inserts it, Phase 2
    # leaves it untouched by design, Phase 3 inserts+removes a DISTINCT B2
    # instead -- protocol section 2.3) -- the inverse spec generate_bibliography_pair
    # always returns alongside the forward one is simply not used for B.
    step = _run_step(bib_forward, chain_root, model, arm, "1.1-bibliography-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("1.1", step)
    current_input = Path(step["output_docx_path"])

    marker_c = new_marker(f"{doc_tag}-cit-C")
    cit_forward = generate_citation_forward(
        doc_label, current_input, marker_c, citation_anchor["anchor_para_id"], citation_anchor["anchor_text_snippet"],
    )
    step = _run_step(cit_forward, chain_root, model, arm, "1.2-citation-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("1.2", step)
    current_input = Path(step["output_docx_path"])
    cit_forward_step = step

    marker_sec = new_marker(f"{doc_tag}-sec")
    sec_forward, _sec_inverse_unused = generate_section_reorder_pair(
        doc_label, current_input, marker_sec,
        plan["section_id"], plan["section_heading_text"],
        plan["original_preceding_heading_para_id"], plan["original_preceding_heading_text"],
        plan["destination_heading_para_id"], plan["destination_heading_text"],  # O -> D1
    )
    # The pair's own inverse (D1 -> O) is deliberately unused: Phase 2 step
    # 2.3 redirects D1 -> D2 instead of undoing back to O -- the protocol's
    # own "genuine redirect, not an undo" requirement (section 2.2 row 2.3).
    step = _run_step(sec_forward, chain_root, model, arm, "1.3-section_reorder-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("1.3", step)
    current_input = Path(step["output_docx_path"])

    marker_e = new_marker(f"{doc_tag}-eq")
    eq_forward = generate_equation_forward(
        doc_label, current_input, marker_e, equation_anchor["anchor_para_id"], equation_anchor["anchor_text_snippet"],
    )
    step = _run_step(eq_forward, chain_root, model, arm, "1.4-equation-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("1.4", step)
    current_input = Path(step["output_docx_path"])

    tbl_forward: TrialSpec | None = None
    tbl_forward_step: dict[str, Any] | None = None
    if six_family:
        # generate_table_structural_forward mints its own marker; the prefix
        # only names the trial.
        tbl_forward = generate_table_structural_forward(
            doc_label, current_input, f"{doc_tag}-tbl", table_anchor["anchor_para_id"], table_anchor["anchor_text_snippet"],
        )
        step = _run_step(tbl_forward, chain_root, model, arm, "1.5-table_structural-forward", current_input)
        steps_run += 1
        if not step["package_valid"]:
            return _freeze("1.5", step)
        current_input = Path(step["output_docx_path"])
        tbl_forward_step = step

    marker_cap = new_marker(f"{doc_tag}-cap")
    cap_forward = generate_caption_forward(
        doc_label, current_input, marker_cap, caption_anchor["anchor_para_id"], caption_anchor["anchor_text_snippet"],
    )
    step = _run_step(cap_forward, chain_root, model, arm, f"1.{caption_n}-caption-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze(f"1.{caption_n}", step)
    current_input = Path(step["output_docx_path"])

    checkpoint_a_docx = current_input
    paragraphs_at_checkpoint_a = _safe_paragraph_texts(checkpoint_a_docx)

    phase1_targets = {
        "bibliography": {"marker_text": bib_forward.marker_text, "citation_key": bib_forward.treatment_args["citation_key"]},
        # grade_forward_trial_inline needs "anchor_text_before" (the anchor's
        # own pre-citation full text), NOT the anchor's para_id -- it grades
        # by re-reading the persisted docx's actual paragraph text, never by
        # id lookup (docx_trial_evaluator.py has no id-based paragraph
        # accessor at all).
        "citation": {"marker_text": cit_forward.marker_text, "anchor_text_before": citation_anchor["anchor_full_text"]},
        "section_reorder": {
            "section_id": plan["section_id"], "section_heading_text": plan["section_heading_text"],
            "destination_heading_text_d1": plan["destination_heading_text"],
        },
        # grade_forward_trial_equation's parameter is named "marker", not
        # "marker_text" -- distinct key name from every other family here,
        # confirmed against the real function signature.
        "equation": {"marker": eq_forward.marker_text},
        "caption": {"marker_text": cap_forward.marker_text},
    }
    phase1_result = _safe_call(grade_phase1_build, checkpoint_a_docx, original_paragraphs, phase1_targets)
    if six_family and phase1_result.get("status") != "grading_raised_exception":
        phase1_result = _safe_call(
            _grade_phase1_six_family, phase1_result, checkpoint_a_docx, original_paragraphs, phase1_targets,
            tbl_forward.marker_text,
        )
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(checkpoint_a_docx, chain_root / "receipts" / "after-phase1", milestone="after_phase1"))

    # -------------------------------------------------------------------
    # PHASE 2 -- RESPEC (2 steps: citation inverse, section redirect)
    # -------------------------------------------------------------------

    resolved_cit = _resolve_or_none(resolve_para_id_by_marker_text, current_input, cit_forward.marker_text)
    if not resolved_cit.get("found"):
        return _freeze(
            "2.1", None, f"citation anchor re-resolution failed: {resolved_cit.get('reason')}",
            cause=FREEZE_CAUSE_ANCHOR_RERESOLUTION, forward_step=cit_forward_step,
        )
    cit_inverse = generate_citation_inverse(
        doc_label, current_input, marker_c, cit_forward.marker_text, resolved_cit["para_id"],
    )
    step = _run_step(cit_inverse, chain_root, model, arm, "2.1-citation-inverse", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("2.1", step)
    current_input = Path(step["output_docx_path"])

    if six_family:
        resolved_tbl = _resolve_or_none(resolve_table_index_by_marker, current_input, tbl_forward.marker_text)
        if not resolved_tbl.get("found"):
            return _freeze(
                "2.2", None, f"table re-resolution failed: {resolved_tbl.get('reason')}",
                cause=FREEZE_CAUSE_ANCHOR_RERESOLUTION, forward_step=tbl_forward_step,
            )
        tbl_inverse = generate_table_structural_inverse(
            doc_label, current_input, f"{doc_tag}-tbl", tbl_forward.marker_text, resolved_tbl["table_index"],
        )
        step = _run_step(tbl_inverse, chain_root, model, arm, "2.2-table_structural-inverse", current_input)
        steps_run += 1
        if not step["package_valid"]:
            return _freeze("2.2", step)
        current_input = Path(step["output_docx_path"])

    d2_heading_para_id = _d2_heading_para_id(plan)
    d2_heading_text = _d2_heading_text(plan)
    sec_redirect = generate_section_redirect_trial(
        doc_label, current_input, marker_sec, plan["section_id"], plan["section_heading_text"],
        plan["destination_heading_para_id"], plan["destination_heading_text"],  # D1 (current position)
        d2_heading_para_id, d2_heading_text,  # D2 (genuine redirect target)
    )
    step = _run_step(sec_redirect, chain_root, model, arm, "2.3-section_reorder-redirect", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("2.3", step)
    current_input = Path(step["output_docx_path"])

    checkpoint_b_docx = current_input
    # score_keep_survival matches by EXACT normalized paragraph/equation
    # text, not substring -- bib_forward.marker_text/cap_forward.marker_text
    # are just the short UUID-suffixed fragments handed to insert_bibliography_
    # entry/insert_caption, never the full rendered text those tools actually
    # produce (e.g. "Marker, P. (2026). Commissioning Pilot Marker
    # Publication <fragment>."). Found live (2026-09-22 RunPod smoke test):
    # passing the raw fragment here means score_keep_survival can never find
    # a match, silently reporting a real, correctly-surviving bibliography
    # entry as "missing" on every single chain. Fixed by searching checkpoint
    # A's own paragraphs for whichever one actually carries the marker
    # fragment and using ITS full text -- the same technique already used
    # for citation's own excluded_texts a few lines below. Equation is
    # unaffected (its flat text IS just the bare marker, confirmed against
    # grade_forward_trial_equation's own substring-match convention), so
    # eq_forward.marker_text needs no such resolution.
    # equation is the SAME bug class: generate_equation_forward's own
    # treatment_args payload is f"x = {marker}" (docx_trial_broker.py) --
    # eq_forward.marker_text is only the bare numeric fragment, never the
    # equation's actual flat text ("x=<marker>", post-OMML-round-trip
    # formatting), confirmed live (2026-09-22 RunPod re-run: keep_survival
    # reported "equation": {"present": false, ...} despite the equation
    # genuinely, correctly surviving -- the SAME false-negative shape
    # bibliography/caption had before their own fix above, just for
    # equation flat-text instead of paragraph text).
    bib_full_text = next((p for p in paragraphs_at_checkpoint_a if bib_forward.marker_text in p), bib_forward.marker_text)
    cap_full_text = next((p for p in paragraphs_at_checkpoint_a if cap_forward.marker_text in p), cap_forward.marker_text)
    eq_full_text = next(
        (t for t in _equation_flat_texts(checkpoint_a_docx) if eq_forward.marker_text in t), eq_forward.marker_text,
    )
    kept_markers = {
        "bibliography": bib_full_text, "equation": eq_full_text, "caption": cap_full_text,
    }
    phase2_result = _safe_call(
        grade_phase2_respec, checkpoint_a_docx, checkpoint_b_docx, paragraphs_at_checkpoint_a,
        cit_forward.marker_text, citation_anchor["anchor_full_text"], plan["section_id"],
        plan["destination_heading_para_id"], d2_heading_para_id, kept_markers,
    )
    if six_family and phase2_result.get("status") != "grading_raised_exception":
        phase2_result = _safe_call(
            _grade_phase2_six_family, phase2_result, checkpoint_a_docx, checkpoint_b_docx, paragraphs_at_checkpoint_a,
            cit_forward.marker_text, citation_anchor["anchor_full_text"], kept_markers, tbl_forward.marker_text,
        )
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(checkpoint_b_docx, chain_root / "receipts" / "after-phase2", milestone="after_phase2"))

    # -------------------------------------------------------------------
    # PHASE 3 -- SECOND EXPOSURE (10 steps: 4 families insert-then-remove
    # a FRESH element at the same anchor, section_reorder makes two more
    # moves D2 -> D1 -> D2)
    # -------------------------------------------------------------------
    phase3_targets = {}

    paragraphs_before_3_1 = _safe_paragraph_texts(current_input)
    marker_b2 = new_marker(f"{doc_tag}-bib-B2")
    b2_forward, b2_inverse = generate_bibliography_pair(doc_label, current_input, marker_b2)
    step = _run_step(b2_forward, chain_root, model, arm, "3.1-bibliography-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.1-forward", step)
    b2_forward_output = Path(step["output_docx_path"])
    current_input = b2_forward_output
    step = _run_step(b2_inverse, chain_root, model, arm, "3.1-bibliography-inverse", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.1-inverse", step)
    current_input = Path(step["output_docx_path"])
    phase3_targets["bibliography"] = {
        "forward_spec": b2_forward, "forward_output_docx": b2_forward_output,
        "paragraphs_before_forward": paragraphs_before_3_1,
        "inverse_spec": b2_inverse, "inverse_output_docx": current_input,
        # grade_inverse_trial needs "marker_text": B2's own marker (the
        # element this net round trip must leave ABSENT from the final
        # output) -- not B's Phase-1 marker, which must stay present.
        "marker_text": b2_forward.marker_text,
    }

    paragraphs_before_3_2 = _safe_paragraph_texts(current_input)
    marker_c2 = new_marker(f"{doc_tag}-cit-C2")
    cit2_forward = generate_citation_forward(
        doc_label, current_input, marker_c2, citation_anchor["anchor_para_id"], citation_anchor["anchor_text_snippet"],
    )
    step = _run_step(cit2_forward, chain_root, model, arm, "3.2-citation-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.2-forward", step)
    cit2_forward_output = Path(step["output_docx_path"])
    current_input = cit2_forward_output
    resolved_cit2 = _resolve_or_none(resolve_para_id_by_marker_text, current_input, cit2_forward.marker_text)
    if not resolved_cit2.get("found"):
        return _freeze(
            "3.2-inverse", None, f"citation (second exposure) re-resolution failed: {resolved_cit2.get('reason')}",
            cause=FREEZE_CAUSE_ANCHOR_RERESOLUTION, forward_step=step,
        )
    cit2_inverse = generate_citation_inverse(
        doc_label, current_input, marker_c2, cit2_forward.marker_text, resolved_cit2["para_id"],
    )
    step = _run_step(cit2_inverse, chain_root, model, arm, "3.2-citation-inverse", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.2-inverse", step)
    current_input = Path(step["output_docx_path"])
    phase3_targets["citation"] = {
        "forward_spec": cit2_forward, "forward_output_docx": cit2_forward_output,
        "paragraphs_before_forward": paragraphs_before_3_2, "anchor_full_text_before": citation_anchor["anchor_full_text"],
        "inverse_spec": cit2_inverse, "inverse_output_docx": current_input,
        # grade_inverse_trial_inline needs "marker_text": C2's own marker.
        "marker_text": cit2_forward.marker_text,
    }

    paragraphs_before_3_3 = _safe_paragraph_texts(current_input)
    marker_sec2 = new_marker(f"{doc_tag}-sec2")
    sec2_forward, sec2_inverse = generate_second_exposure_reorder_pair(
        doc_label, current_input, marker_sec2, plan["section_id"], plan["section_heading_text"],
        d2_heading_para_id, d2_heading_text,  # current position, D2
        plan["destination_heading_para_id"], plan["destination_heading_text"],  # D1
    )
    step = _run_step(sec2_forward, chain_root, model, arm, "3.3-section_reorder-forward-d2-to-d1", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.3a", step)
    sec2_forward_output = Path(step["output_docx_path"])
    current_input = sec2_forward_output
    step = _run_step(sec2_inverse, chain_root, model, arm, "3.3-section_reorder-inverse-d1-to-d2", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.3b", step)
    current_input = Path(step["output_docx_path"])
    phase3_targets["section_reorder"] = {
        "forward_spec": sec2_forward, "forward_output_docx": sec2_forward_output,
        "paragraphs_before_forward": paragraphs_before_3_3, "section_heading_text": plan["section_heading_text"],
        "inverse_spec": sec2_inverse, "inverse_output_docx": current_input,
    }

    paragraphs_before_3_4 = _safe_paragraph_texts(current_input)
    marker_e2 = new_marker(f"{doc_tag}-eq2")
    eq2_forward = generate_equation_forward(
        doc_label, current_input, marker_e2, equation_anchor["anchor_para_id"], equation_anchor["anchor_text_snippet"],
    )
    step = _run_step(eq2_forward, chain_root, model, arm, "3.4-equation-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.4-forward", step)
    eq2_forward_output = Path(step["output_docx_path"])
    current_input = eq2_forward_output
    resolved_eq2 = _resolve_or_none(resolve_equation_para_id_by_marker, current_input, eq2_forward.marker_text)
    if not resolved_eq2.get("found"):
        return _freeze(
            "3.4-inverse", None, f"equation (second exposure) re-resolution failed: {resolved_eq2.get('reason')}",
            cause=FREEZE_CAUSE_ANCHOR_RERESOLUTION, forward_step=step,
        )
    eq2_inverse = generate_equation_inverse(
        doc_label, current_input, marker_e2, eq2_forward.marker_text, resolved_eq2["para_id"],
    )
    step = _run_step(eq2_inverse, chain_root, model, arm, "3.4-equation-inverse", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.4-inverse", step)
    current_input = Path(step["output_docx_path"])
    phase3_targets["equation"] = {
        "forward_spec": eq2_forward, "forward_output_docx": eq2_forward_output,
        "paragraphs_before_forward": paragraphs_before_3_4,
        "inverse_spec": eq2_inverse, "inverse_output_docx": current_input,
        # grade_inverse_trial_equation's parameter is named "marker" (like
        # its Phase-1 forward counterpart), not "marker_text".
        "marker": eq2_forward.marker_text,
    }

    tbl2_forward: TrialSpec | None = None
    if six_family:
        paragraphs_before_tbl2 = _safe_paragraph_texts(current_input)
        tbl2_forward = generate_table_structural_forward(
            doc_label, current_input, f"{doc_tag}-tbl2", table_anchor["anchor_para_id"], table_anchor["anchor_text_snippet"],
        )
        step = _run_step(tbl2_forward, chain_root, model, arm, "3.5-table_structural-forward", current_input)
        steps_run += 1
        if not step["package_valid"]:
            return _freeze("3.5-forward", step)
        tbl2_forward_output = Path(step["output_docx_path"])
        current_input = tbl2_forward_output
        resolved_tbl2 = _resolve_or_none(resolve_table_index_by_marker, current_input, tbl2_forward.marker_text)
        if not resolved_tbl2.get("found"):
            return _freeze(
                "3.5-inverse", None, f"table (second exposure) re-resolution failed: {resolved_tbl2.get('reason')}",
                cause=FREEZE_CAUSE_ANCHOR_RERESOLUTION, forward_step=step,
            )
        tbl2_inverse = generate_table_structural_inverse(
            doc_label, current_input, f"{doc_tag}-tbl2", tbl2_forward.marker_text, resolved_tbl2["table_index"],
        )
        step = _run_step(tbl2_inverse, chain_root, model, arm, "3.5-table_structural-inverse", current_input)
        steps_run += 1
        if not step["package_valid"]:
            return _freeze("3.5-inverse", step)
        current_input = Path(step["output_docx_path"])
        phase3_targets["table_structural"] = {
            "forward_spec": tbl2_forward, "forward_output_docx": tbl2_forward_output,
            "paragraphs_before_forward": paragraphs_before_tbl2,
            "inverse_spec": tbl2_inverse, "inverse_output_docx": current_input,
            "marker_text": tbl2_forward.marker_text,
        }

    paragraphs_before_3_5 = _safe_paragraph_texts(current_input)
    marker_cap2 = new_marker(f"{doc_tag}-cap2")
    cap2_forward = generate_caption_forward(
        doc_label, current_input, marker_cap2, caption_anchor["anchor_para_id"], caption_anchor["anchor_text_snippet"],
    )
    step = _run_step(cap2_forward, chain_root, model, arm, f"3.{caption_n}-caption-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze(f"3.{caption_n}-forward", step)
    cap2_forward_output = Path(step["output_docx_path"])
    current_input = cap2_forward_output
    resolved_cap2 = _resolve_or_none(resolve_para_id_by_marker_text, current_input, cap2_forward.marker_text)
    if not resolved_cap2.get("found"):
        return _freeze(
            f"3.{caption_n}-inverse", None, f"caption (second exposure) re-resolution failed: {resolved_cap2.get('reason')}",
            cause=FREEZE_CAUSE_ANCHOR_RERESOLUTION, forward_step=step,
        )
    cap2_inverse = generate_caption_inverse(
        doc_label, current_input, marker_cap2, cap2_forward.marker_text, resolved_cap2["para_id"],
    )
    step = _run_step(cap2_inverse, chain_root, model, arm, f"3.{caption_n}-caption-inverse", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze(f"3.{caption_n}-inverse", step)
    current_input = Path(step["output_docx_path"])
    phase3_targets["caption"] = {
        "forward_spec": cap2_forward, "forward_output_docx": cap2_forward_output,
        "paragraphs_before_forward": paragraphs_before_3_5,
        "inverse_spec": cap2_inverse, "inverse_output_docx": current_input,
        # grade_inverse_trial needs "marker_text": Cap2's own marker.
        "marker_text": cap2_forward.marker_text,
    }

    checkpoint_c_docx = current_input
    paragraphs_at_checkpoint_b = _safe_paragraph_texts(checkpoint_b_docx)
    expected_final_structure = {
        "bibliography_marker_text": bib_forward.marker_text,
        # _check_final_structure's own required key is "equation_marker",
        # not "equation_marker_text" -- confirmed against its real body
        # (`expected["equation_marker"]`).
        "equation_marker": eq_forward.marker_text,
        "caption_marker_text": cap_forward.marker_text,
        "citation_absent_marker_texts": [cit_forward.marker_text, cit2_forward.marker_text],
        "section_id": plan["section_id"],
        # _section_heading_adjacency (called inside _check_final_structure)
        # now matches D1/D2 by para_id, not heading text.
        "expected_d1_heading_para_id": plan["destination_heading_para_id"],
        "expected_d2_heading_para_id": d2_heading_para_id,
        # _check_final_structure's collateral-diff check needs the FULL
        # pristine (pre-Phase-1) paragraph list -- this key was missing
        # entirely before this fix, which would have raised a KeyError on
        # every chain that reached this point.
        "pristine_paragraphs": original_paragraphs,
    }
    phase3_result = _safe_call(
        grade_phase3_second_exposure, checkpoint_c_docx, paragraphs_at_checkpoint_b, phase3_targets, expected_final_structure,
        checkpoint_b_docx,
    )
    if six_family and phase3_result.get("status") != "grading_raised_exception":
        phase3_result = _safe_call(
            _grade_phase3_six_family, phase3_result, checkpoint_c_docx, paragraphs_at_checkpoint_b,
            [tbl_forward.marker_text, tbl2_forward.marker_text], tbl2_forward.marker_text,
        )
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(checkpoint_c_docx, chain_root / "receipts" / "after-phase3", milestone="after_phase3"))

    chain_pass_result = _safe_call(lambda: {"pass": chain_pass(phase1_result, phase2_result, phase3_result)})
    chain_ok = chain_pass_result.get("pass", False)
    status = "completed" if chain_ok else "completed_with_failure"

    result = {
        **base_result, "status": status,
        "phase1_result": phase1_result, "phase2_result": phase2_result, "phase3_result": phase3_result,
        "steps_run": steps_run, "word_com_receipts": receipts,
        "final_output_docx": str(checkpoint_c_docx),
        # Reasons of any grader that raised (its _safe_call stub), including
        # chain_pass itself, whose stub is otherwise reduced to a failed pass.
        "grading_exceptions": _grading_exceptions({
            "phase1_result": phase1_result, "phase2_result": phase2_result, "phase3_result": phase3_result,
            "chain_pass": chain_pass_result,
        }),
    }
    _write_checkpoint(chain_root, result)
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doc-label", required=True)
    parser.add_argument("--docx-path", type=Path, required=True)
    parser.add_argument("--arm", required=True, choices=["control", "treatment"])
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--no-word-receipts", action="store_true")
    parser.add_argument(
        "--six-family", action="store_true",
        help=(
            "Run the protocol's six-family rotation R (section 2.2, adds table_structural) instead of the "
            "five-family contingency R'. The anchor-set must carry a table_anchor (with --anchor-set-index "
            "one is resolved here, the same way run_respec_cascade_sweep.py --six-family does)."
        ),
    )
    anchor_group = parser.add_mutually_exclusive_group(required=True)
    anchor_group.add_argument("--anchor-set-index", type=int)
    anchor_group.add_argument(
        "--anchor-set-json", type=Path,
        help=(
            "Path to a single pre-resolved anchor-set dict (one element of "
            "resolve_respec_schedule's own return list), already hash-recorded. "
            "Preferred mode: the protocol (section 2.1) requires both arms of "
            "the same chain to use the IDENTICAL, frozen anchor-set rather than "
            "each re-deriving it independently -- pass the SAME file for the "
            "control and treatment runs of one (document, anchor-set) pair."
        ),
    )
    args = parser.parse_args(argv)

    if args.anchor_set_json is not None:
        anchor_set = json.loads(args.anchor_set_json.read_text(encoding="utf-8"))
    else:
        schedule = resolve_respec_schedule(args.docx_path, max_anchor_sets=max(4, args.anchor_set_index + 1))
        if args.anchor_set_index >= len(schedule):
            print(
                f"anchor-set-index {args.anchor_set_index} out of range: only "
                f"{len(schedule)} anchor-set(s) resolved for {args.docx_path}",
                file=sys.stderr,
            )
            return 1
        if args.six_family:
            from run_respec_cascade_sweep import add_table_anchors  # noqa: E402 -- sibling module, imports this one

            schedule = add_table_anchors(args.docx_path, schedule, max_anchor_sets=max(4, args.anchor_set_index + 1))
        anchor_set = schedule[args.anchor_set_index]

    result = run_respec_cascade_chain(
        args.doc_label, args.docx_path, args.arm, args.model, args.run_root, anchor_set,
        word_receipts_enabled=not args.no_word_receipts, six_family=args.six_family,
    )

    print(json.dumps({
        "chain_id": result["chain_id"], "status": result["status"], "steps_run": result.get("steps_run"),
    }, indent=2))
    print(f"Full result: {args.run_root / result['chain_id'] / _CHECKPOINT_NAME}")
    return 0 if result["status"] in ("completed", "not_applicable") else 1


if __name__ == "__main__":
    raise SystemExit(main())
