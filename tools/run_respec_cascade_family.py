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
"""
from __future__ import annotations

import dataclasses
import datetime
import json
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
    new_marker,
)
from docx_trial_evaluator import (  # noqa: E402
    _package_is_valid_docx,
    chain_pass,
    grade_phase1_build,
    grade_phase2_respec,
    grade_phase3_second_exposure,
)
from claude_pair_runner import audit_isolation, run_trial  # noqa: E402
from word_receipt_watchdog import word_receipt_with_orphan_diagnostics  # noqa: E402

_WORD_RECEIPT_TIMEOUT_SECONDS = 90.0
_FAMILY = "respec_cascade"

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
    # checkpoint. "chain_broken_at_step_*" is ALSO trusted here (unlike
    # run_chain's own "blocked", which is deliberately never trusted): a
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
    result = run_trial(step_spec, chain_root, model=model)
    result["isolation_audit"] = audit_isolation(result)
    result["step_id"] = step_id
    output_path = Path(result["output_docx_path"])
    valid, reason = _package_is_valid_docx(output_path)
    result["package_valid"] = valid
    result["package_invalid_reason"] = reason
    return result


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


def run_respec_cascade_chain(
    doc_label: str, docx_path: Path, arm: str, model: str, run_root: Path, anchor_set: dict[str, Any],
    *, word_receipts_enabled: bool = True,
) -> dict[str, Any]:
    """Runs one full 17-tool-call, 3-phase respec_cascade chain for one
    (document, anchor-set, arm) combination. See this module's docstring for
    the sibling-file contract this is written against, and protocol section
    2.3 for the exact five-family step sequence.
    """
    short_doc_label = doc_label[:32]
    chain_id = f"{short_doc_label}-{_FAMILY}-{arm}"
    chain_root = run_root / chain_id
    chain_root.mkdir(parents=True, exist_ok=True)

    checkpoint = _load_checkpoint(chain_root)
    if checkpoint is not None:
        return checkpoint

    base_result = {
        "chain_id": chain_id, "doc_label": doc_label, "family": _FAMILY, "arm": arm,
        "anchor_set_index": anchor_set.get("anchor_set_index"), "model": model,
    }

    if not anchor_set.get("usable", False):
        result = {
            **base_result, "status": "not_applicable", "reason": anchor_set.get("reason"),
            "phase1_result": None, "phase2_result": None, "phase3_result": None,
            "steps_run": 0, "word_com_receipts": [],
        }
        _write_checkpoint(chain_root, result)
        return result

    citation_anchor = anchor_set["citation_anchor"]
    equation_anchor = anchor_set["equation_anchor"]
    caption_anchor = anchor_set["caption_anchor"]
    plan = anchor_set["section_reorder_plan"]

    original_paragraphs = _paragraph_texts(docx_path)
    receipts: list[dict[str, Any]] = []
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(docx_path, chain_root / "receipts" / "chain-start", milestone="chain_start"))

    current_input = docx_path
    steps_run = 0

    def _freeze(step_id: str, step_result: dict[str, Any] | None, extra_reason: str | None = None) -> dict[str, Any]:
        reason = extra_reason if extra_reason is not None else (step_result or {}).get("package_invalid_reason")
        result = {
            **base_result, "status": f"chain_broken_at_step_{step_id}", "reason": reason,
            "phase1_result": None, "phase2_result": None, "phase3_result": None,
            "steps_run": steps_run, "word_com_receipts": receipts,
            "frozen_step_result": step_result,
        }
        _write_checkpoint(chain_root, result)
        return result

    # -------------------------------------------------------------------
    # PHASE 1 -- BUILD (5 steps, forward-only, order R')
    # -------------------------------------------------------------------

    marker_b = new_marker(f"respec-{short_doc_label}-bib-B")
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

    marker_c = new_marker(f"respec-{short_doc_label}-cit-C")
    cit_forward = generate_citation_forward(
        doc_label, current_input, marker_c, citation_anchor["anchor_para_id"], citation_anchor["anchor_text_snippet"],
    )
    step = _run_step(cit_forward, chain_root, model, arm, "1.2-citation-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("1.2", step)
    current_input = Path(step["output_docx_path"])

    marker_sec = new_marker(f"respec-{short_doc_label}-sec")
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

    marker_e = new_marker(f"respec-{short_doc_label}-eq")
    eq_forward = generate_equation_forward(
        doc_label, current_input, marker_e, equation_anchor["anchor_para_id"], equation_anchor["anchor_text_snippet"],
    )
    step = _run_step(eq_forward, chain_root, model, arm, "1.4-equation-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("1.4", step)
    current_input = Path(step["output_docx_path"])

    marker_cap = new_marker(f"respec-{short_doc_label}-cap")
    cap_forward = generate_caption_forward(
        doc_label, current_input, marker_cap, caption_anchor["anchor_para_id"], caption_anchor["anchor_text_snippet"],
    )
    step = _run_step(cap_forward, chain_root, model, arm, "1.5-caption-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("1.5", step)
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
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(checkpoint_a_docx, chain_root / "receipts" / "after-phase1", milestone="after_phase1"))

    # -------------------------------------------------------------------
    # PHASE 2 -- RESPEC (2 steps: citation inverse, section redirect)
    # -------------------------------------------------------------------

    resolved_cit = _resolve_or_none(resolve_para_id_by_marker_text, current_input, cit_forward.marker_text)
    if not resolved_cit.get("found"):
        return _freeze("2.1", None, f"citation anchor re-resolution failed: {resolved_cit.get('reason')}")
    cit_inverse = generate_citation_inverse(
        doc_label, current_input, marker_c, cit_forward.marker_text, resolved_cit["para_id"],
    )
    step = _run_step(cit_inverse, chain_root, model, arm, "2.1-citation-inverse", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("2.1", step)
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
    kept_markers = {
        "bibliography": bib_forward.marker_text, "equation": eq_forward.marker_text, "caption": cap_forward.marker_text,
    }
    phase2_result = _safe_call(
        grade_phase2_respec, checkpoint_a_docx, checkpoint_b_docx, paragraphs_at_checkpoint_a,
        cit_forward.marker_text, citation_anchor["anchor_full_text"], plan["section_id"],
        plan["destination_heading_para_id"], d2_heading_para_id, kept_markers,
    )
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(checkpoint_b_docx, chain_root / "receipts" / "after-phase2", milestone="after_phase2"))

    # -------------------------------------------------------------------
    # PHASE 3 -- SECOND EXPOSURE (10 steps: 4 families insert-then-remove
    # a FRESH element at the same anchor, section_reorder makes two more
    # moves D2 -> D1 -> D2)
    # -------------------------------------------------------------------
    phase3_targets: dict[str, Any] = {}

    paragraphs_before_3_1 = _safe_paragraph_texts(current_input)
    marker_b2 = new_marker(f"respec-{short_doc_label}-bib-B2")
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
    marker_c2 = new_marker(f"respec-{short_doc_label}-cit-C2")
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
        return _freeze("3.2-inverse", None, f"citation (second exposure) re-resolution failed: {resolved_cit2.get('reason')}")
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
    marker_sec2 = new_marker(f"respec-{short_doc_label}-sec2")
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
    marker_e2 = new_marker(f"respec-{short_doc_label}-eq2")
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
        return _freeze("3.4-inverse", None, f"equation (second exposure) re-resolution failed: {resolved_eq2.get('reason')}")
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

    paragraphs_before_3_5 = _safe_paragraph_texts(current_input)
    marker_cap2 = new_marker(f"respec-{short_doc_label}-cap2")
    cap2_forward = generate_caption_forward(
        doc_label, current_input, marker_cap2, caption_anchor["anchor_para_id"], caption_anchor["anchor_text_snippet"],
    )
    step = _run_step(cap2_forward, chain_root, model, arm, "3.5-caption-forward", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.5-forward", step)
    cap2_forward_output = Path(step["output_docx_path"])
    current_input = cap2_forward_output
    resolved_cap2 = _resolve_or_none(resolve_para_id_by_marker_text, current_input, cap2_forward.marker_text)
    if not resolved_cap2.get("found"):
        return _freeze("3.5-inverse", None, f"caption (second exposure) re-resolution failed: {resolved_cap2.get('reason')}")
    cap2_inverse = generate_caption_inverse(
        doc_label, current_input, marker_cap2, cap2_forward.marker_text, resolved_cap2["para_id"],
    )
    step = _run_step(cap2_inverse, chain_root, model, arm, "3.5-caption-inverse", current_input)
    steps_run += 1
    if not step["package_valid"]:
        return _freeze("3.5-inverse", step)
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
    )
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(checkpoint_c_docx, chain_root / "receipts" / "after-phase3", milestone="after_phase3"))

    chain_ok = _safe_call(lambda: {"pass": chain_pass(phase1_result, phase2_result, phase3_result)}).get("pass", False)
    status = "completed" if chain_ok else "completed_with_failure"

    result = {
        **base_result, "status": status,
        "phase1_result": phase1_result, "phase2_result": phase2_result, "phase3_result": phase3_result,
        "steps_run": steps_run, "word_com_receipts": receipts,
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
        anchor_set = schedule[args.anchor_set_index]

    result = run_respec_cascade_chain(
        args.doc_label, args.docx_path, args.arm, args.model, args.run_root, anchor_set,
        word_receipts_enabled=not args.no_word_receipts,
    )

    print(json.dumps({
        "chain_id": result["chain_id"], "status": result["status"], "steps_run": result["steps_run"],
    }, indent=2))
    print(f"Full result: {args.run_root / result['chain_id'] / _CHECKPOINT_NAME}")
    return 0 if result["status"] in ("completed", "not_applicable") else 1


if __name__ == "__main__":
    raise SystemExit(main())
