"""PAPER-S7: the confirmatory paired Claude-without-vs-with-Meridian DOCX
editing benchmark. Generalizes PAPER-S20's commissioning harness (single
family, 2 fixtures, haiku) to the full design locked in
docs/paper-s7-protocol-v1.md: multiple task families, the real DocOps
development/validation/primary-holdout corpus
(manifests/paper-s7-corpus-manifest-v1.json), a long-horizon K-pair sweep, and
a confirmatory model.

A "chain" is the actual long-horizon unit per docs/paper-s9-long-horizon-
benchmark-protocol-v0.md section 4: K forward+inverse pairs of the SAME
family, run against the SAME document and arm, each pair its own fresh
process (so process/session round trips = K for BOTH arms symmetrically,
by construction -- see that section's confound warning), with pair i+1
starting from pair i's own inverse output. After the full chain, the final
document is compared against the ORIGINAL pristine paragraphs -- the
strongest available test of whether repeated insert+remove cycles introduce
cumulative drift even when each cycle nominally undoes itself.

Word-COM milestones (two-tier verification, protocol section 5): once at
chain start (the pristine input), then once after every pair -- never after
every raw tool call.

2026-09-25 (re-run preparation): a chain that stops early records its cause
as its status (blocked_timeout, blocked_forward_failed,
blocked_unreadable_input, blocked_inverse_unresolvable -- all trusted on
resume, so a relaunch never re-runs a timeout -- or infra_blocked, the only
one re-run); every attempt is counted in <run-root>/_chain_attempts/ and an
earlier attempt's files move to <run-root>/attic/; a sweep-wide circuit
breaker stops dispatch at the first global infrastructure signature (exit 3);
--check-only verifies hashes and plans without running a trial; both arms of
a pair are submitted back to back (--arm-order-seed).
"""
from __future__ import annotations

import concurrent.futures
import dataclasses
import datetime
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_anchor_prober import (  # noqa: E402
    resolve_body_anchor,
    resolve_equation_para_id_by_marker,
    resolve_para_id_by_marker_text,
    resolve_section_reorder_plan,
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
    generate_section_reorder_pair,
    generate_table_structural_forward,
    generate_table_structural_inverse,
    new_marker,
)
from docx_trial_evaluator import (  # noqa: E402
    grade_forward_trial,
    grade_forward_trial_equation,
    grade_forward_trial_inline,
    grade_forward_trial_reorder,
    grade_forward_trial_table_structural,
    grade_inverse_trial,
    grade_inverse_trial_equation,
    grade_inverse_trial_inline,
    grade_inverse_trial_reorder,
    grade_inverse_trial_table_structural,
)
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
from provenance import build_provenance, write_provenance_end, write_provenance_start  # noqa: E402
from usage_cap import UsagePauseController, run_with_usage_cap_retry  # noqa: E402
from word_receipt_watchdog import word_receipt_with_orphan_diagnostics  # noqa: E402

_WORD_RECEIPT_TIMEOUT_SECONDS = 90.0
_FAMILIES = ("bibliography", "citation", "caption", "section_reorder", "equation", "table_structural")


def _safe_paragraph_texts(docx_path: Path) -> list[str] | None:
    """_paragraph_texts() does a raw zipfile read with no corruption guard --
    fine when the caller already knows the package is valid, but a real
    KeyError/BadZipFile crash waiting to happen against a PRIOR pair's own
    (possibly corrupted) output in a long-horizon chain, or a control arm's
    output docx generically. Found via a real development-slice run
    (2026-08-30): two control-arm trials corrupted their output packages
    badly enough that even a raw word/document.xml read raised, crashing the
    whole chain as an unhandled harness_exception instead of a graded fail.
    Returns None (never raises) on any corruption; callers treat None as
    "this document cannot be graded/continued from," not as an empty
    paragraph list (which would be indistinguishable from a genuinely empty
    document).

    FileNotFoundError added 2026-09-04: found live via the equation family's
    harder control-arm task (hand-constructing OMML) surfacing a pre-existing
    gap -- a control trial that never wrote its output file at all raised
    unhandled here too, the same "harness_exception instead of a graded
    fail" failure mode the original three exceptions were added to close."""
    try:
        return _paragraph_texts(docx_path)
    except (KeyError, zipfile.BadZipFile, ET.ParseError, FileNotFoundError):
        return None


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


def probe_family_applicability(
    family: str, docx_path: Path, *, anchor_or_plan_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Determine, harness-side, whether this document supports this family at
    all -- an inapplicable family is reported as not_applicable, never forced
    or silently dropped (PAPER-S9 protocol's own corpus-heterogeneity design:
    not every document need support every template).

    anchor_or_plan_override (added for the multi-anchor-per-document
    extension, PAPER-S7 follow-up): when given, skips the single-candidate
    resolve_body_anchor/resolve_section_reorder_plan call entirely and uses
    this already-resolved anchor/plan dict directly -- the same shape
    resolve_multiple_body_anchors/resolve_multiple_section_reorder_plans
    each element of their returned list already is. None (the default)
    preserves the exact original single-anchor behavior for every existing
    caller; this parameter only exists so run_chain can be driven with one
    of several anchors discovered from the same document without
    duplicating any of this function's own logic."""
    if anchor_or_plan_override is not None:
        if family in ("citation", "caption", "equation", "table_structural"):
            return {"applicable": True, "anchor": anchor_or_plan_override}
        if family == "section_reorder":
            return {"applicable": True, "plan": anchor_or_plan_override}
        raise ValueError(f"anchor_or_plan_override not supported for family {family!r}")
    if family in ("bibliography",):
        return {"applicable": True}
    if family in ("citation", "caption", "equation", "table_structural"):
        anchor = resolve_body_anchor(docx_path)
        if not anchor["found"]:
            return {"applicable": False, "reason": anchor["reason"]}
        return {"applicable": True, "anchor": anchor}
    if family == "section_reorder":
        plan = resolve_section_reorder_plan(docx_path)
        if not plan["found"]:
            return {"applicable": False, "reason": plan["reason"]}
        return {"applicable": True, "plan": plan}
    raise ValueError(f"unknown family {family!r}")


def _build_pair_specs(
    family: str, doc_label: str, docx_path: Path, marker: str, applicability: dict[str, Any],
) -> tuple[TrialSpec, TrialSpec | None]:
    """Returns (forward, inverse-or-None). inverse is None for citation,
    caption, equation, and table_structural: all four need the forward
    trial's own OUTPUT inspected before the inverse's anchor can be resolved
    (citation's anchor paragraph's own synthetic id changes once forward
    edits its text; caption's, equation's, and table_structural's new
    content never gets an id/index back to the CONTROL arm's output at all,
    and even reading treatment's own tool result would only cover treatment,
    not control uniformly) -- see resolve_para_id_by_marker_text /
    resolve_equation_para_id_by_marker / resolve_table_index_by_marker and
    docx_trial_broker.py's citation/equation/table_structural section
    docstrings for why reusing the pristine-document id is wrong."""
    if family == "bibliography":
        return generate_bibliography_pair(doc_label, docx_path, marker)
    if family == "citation":
        anchor = applicability["anchor"]
        forward = generate_citation_forward(
            doc_label, docx_path, marker, anchor["anchor_para_id"], anchor["anchor_text_snippet"],
        )
        return forward, None
    if family == "caption":
        anchor = applicability["anchor"]
        forward = generate_caption_forward(
            doc_label, docx_path, marker, anchor["anchor_para_id"], anchor["anchor_text_snippet"],
        )
        return forward, None
    if family == "equation":
        anchor = applicability["anchor"]
        forward = generate_equation_forward(
            doc_label, docx_path, marker, anchor["anchor_para_id"], anchor["anchor_text_snippet"],
        )
        return forward, None
    if family == "table_structural":
        anchor = applicability["anchor"]
        forward = generate_table_structural_forward(
            doc_label, docx_path, marker, anchor["anchor_para_id"], anchor["anchor_text_snippet"],
        )
        return forward, None
    if family == "section_reorder":
        plan = applicability["plan"]
        return generate_section_reorder_pair(
            doc_label, docx_path, marker,
            plan["section_id"], plan["section_heading_text"],
            plan["original_preceding_heading_para_id"], plan["original_preceding_heading_text"],
            plan["destination_heading_para_id"], plan["destination_heading_text"],
        )
    raise ValueError(f"unknown family {family!r}")


def _grade_forward(family: str, output_docx: Path, paragraphs_before: list[str], spec: TrialSpec, applicability: dict[str, Any]) -> dict[str, Any]:
    if family in ("bibliography", "caption"):
        return grade_forward_trial(output_docx, paragraphs_before, spec.marker_text)
    if family == "citation":
        return grade_forward_trial_inline(
            output_docx, paragraphs_before, applicability["anchor"]["anchor_full_text"], spec.marker_text,
        )
    if family == "section_reorder":
        return grade_forward_trial_reorder(output_docx, paragraphs_before, spec.marker_text)
    if family == "equation":
        return grade_forward_trial_equation(output_docx, paragraphs_before, spec.marker_text)
    if family == "table_structural":
        return grade_forward_trial_table_structural(output_docx, paragraphs_before, spec.marker_text)
    raise ValueError(f"unknown family {family!r}")


def _grade_inverse(family: str, output_docx: Path, paragraphs_before_forward: list[str], spec: TrialSpec) -> dict[str, Any]:
    if family in ("bibliography", "caption"):
        return grade_inverse_trial(output_docx, paragraphs_before_forward, spec.marker_text)
    if family == "citation":
        return grade_inverse_trial_inline(output_docx, paragraphs_before_forward, spec.marker_text)
    if family == "section_reorder":
        return grade_inverse_trial_reorder(output_docx, paragraphs_before_forward)
    if family == "equation":
        return grade_inverse_trial_equation(output_docx, paragraphs_before_forward, spec.marker_text)
    if family == "table_structural":
        return grade_inverse_trial_table_structural(output_docx, paragraphs_before_forward, spec.marker_text)
    raise ValueError(f"unknown family {family!r}")


def _safe_grade(grade_fn, *args, **kwargs) -> dict[str, Any]:
    """_grade_forward/_grade_inverse's own grading functions do a raw
    _package_is_valid_docx check first, but that only validates the ZIP
    structure and required-part PRESENCE -- never that word/document.xml's
    actual bytes parse as well-formed XML. A structurally-valid ZIP holding
    genuinely malformed XML content (found live, 2026-09-04, via the
    equation family's harder control-arm task: hand-constructing OMML is
    hard enough that a haiku control trial produced exactly this) makes the
    grading function's own ET.fromstring call raise uncaught, which used to
    crash the whole chain as an uninformative harness_exception -- the same
    "should be a graded fail, not a lost pair" failure mode
    _safe_paragraph_texts already exists to close for the inter-pair read.
    This closes it for the grading call itself, for every family uniformly."""
    try:
        return grade_fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 -- see docstring: must never propagate
        return {"verdict": "fail", "reason": f"grading raised {type(exc).__name__}: {exc}"}


_CHECKPOINT_NAME = "chain-result.json"

# Why a chain stopped early (2026-09-25, review blocker 1). Before this date
# every such chain was plain "blocked", which could not be trusted on resume
# because a Windows STATUS_DLL_INIT_FAILED process-launch failure (found live
# 2026-09-02) also produced it -- so every relaunch re-ran every timed-out
# chain, contradicting "timeouts are never re-run". Each cause now has its own
# status; the infrastructure case is identified from evidence
# (claude_pair_runner.classify_infra_signature) and is the only one re-run:
#   blocked_timeout             a forward trial hit the harness timeout
#                               (no infrastructure signature, output not
#                               recovered) -- the arm's own outcome
#   blocked_forward_failed      a forward CLI process exited non-zero with a
#                               JSON result and no infrastructure signature
#   blocked_unreadable_input    the prior pair's inverse output is unreadable
#   blocked_inverse_unresolvable the forward output has no resolvable marker
#   infra_blocked               some trial has an infrastructure signature,
#                               whatever else happened (review item 23)
# compute_s7_statistics treats every blocked_* status exactly as it treats
# the legacy "blocked" (see its BLOCKED_STATUSES and --blocked-policy).
STATUS_BLOCKED_TIMEOUT = "blocked_timeout"
STATUS_BLOCKED_FORWARD_FAILED = "blocked_forward_failed"
STATUS_BLOCKED_UNREADABLE_INPUT = "blocked_unreadable_input"
STATUS_BLOCKED_INVERSE_UNRESOLVABLE = "blocked_inverse_unresolvable"
STATUS_INFRA_BLOCKED = "infra_blocked"
STATUS_INFRA_EXCLUDED = "infra_excluded"
STATUS_ABORTED_CIRCUIT_OPEN = "aborted_circuit_open"

# Statuses of a chain whose attempt genuinely finished (its outcome may itself
# be a failure) -- trusted and skipped on resume. Untrusted, so re-run: the
# legacy "blocked" (cause unknown), infra_blocked, and harness_exception /
# aborted_circuit_open (never written as a checkpoint).
_CHECKPOINT_TRUSTED_STATUSES = frozenset({
    "not_applicable", "completed", "completed_with_failure",
    STATUS_BLOCKED_TIMEOUT, STATUS_BLOCKED_FORWARD_FAILED,
    STATUS_BLOCKED_UNREADABLE_INPUT, STATUS_BLOCKED_INVERSE_UNRESOLVABLE,
})


def _load_checkpoint(chain_root: Path) -> dict[str, Any] | None:
    path = chain_root / _CHECKPOINT_NAME
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if result.get("status") not in _CHECKPOINT_TRUSTED_STATUSES:
        return None
    return result


def _write_checkpoint(chain_root: Path, result: dict[str, Any]) -> None:
    # Atomic write: a crash mid-write must never leave a checkpoint that
    # _load_checkpoint could half-parse and trust.
    tmp_path = chain_root / f"{_CHECKPOINT_NAME}.tmp"
    tmp_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(chain_root / _CHECKPOINT_NAME)


def run_chain(
    family: str, doc_label: str, docx_path: Path, arm: str, k_pairs: int, model: str,
    run_root: Path, *, word_receipts_enabled: bool = True,
    anchor_or_plan_override: dict[str, Any] | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    max_chain_attempts: int | None = None,
    pause_controller: UsagePauseController | None = None,
) -> dict[str, Any]:
    # circuit_breaker (review item 17): checked before every trial; a trial
    # with a global infrastructure signature opens it. max_chain_attempts:
    # the rerun limit counted in the per-chain attempt ledger kept outside
    # the chain root (claude_pair_runner.begin_chain_attempt); None = no limit.
    # pause_controller (rate-limit handling): forwarded to infra_signature_of
    # so a usage-cap/rate-limit trial pauses the sweep (see usage_cap.py);
    # purely additive, None reproduces the exact prior behavior.
    # anchor_or_plan_override: multi-anchor-per-document extension. The
    # CALLER is responsible for passing a doc_label that is already unique
    # per anchor (e.g. f"{base_label}__anchor2") when using this -- doc_label
    # is what compute_s7_statistics.py pairs control against treatment by,
    # so two different anchors sharing one doc_label would silently
    # conflate two independent trial points into one paired slot instead of
    # two. chain_id/chain_root below are derived from doc_label, so a
    # distinct doc_label already gives each anchor its own checkpoint
    # directory -- PROVIDED it survives the truncation below intact (see
    # that correction).
    # Windows MAX_PATH (260 chars) is a real constraint here: chain_root
    # nests trial directories several levels deep under a long E: run root,
    # and DocOps doc_labels can be 60+ chars on their own -- truncate rather
    # than let a long label silently produce a WinError 267 deep in
    # subprocess creation.
    #
    # 2026-09-23 correction (found live, PAPER-S23 respec_cascade baseline
    # sweep): plain `doc_label[:32]` silently COLLIDES whenever two distinct
    # doc_labels share the same first 32 characters -- exactly what
    # f"{base_label}__anchor{i}" produces once base_label alone is >=32
    # chars (confirmed directly: "masters-dissertation-defense__anchor0..3"
    # all truncate to the identical "masters-dissertation-defense__a",
    # so every anchor's job raced on/silently reused ONE shared chain_root
    # across all 5 families -- the exact same class of bug already fixed in
    # run_respec_cascade_family.py's own chain_id, commit 0cd9eb8). Only
    # truncate+disambiguate when the label actually exceeds the budget, so
    # every existing doc_label under 32 chars keeps its EXACT prior
    # chain_id/chain_root (preserves checkpoint-resume compatibility with
    # any already-running or historical PAPER-S7 sweep).
    if len(doc_label) > 32:
        doc_label_hash = hashlib.sha256(doc_label.encode("utf-8")).hexdigest()[:8]
        short_doc_label = f"{doc_label[:23]}-{doc_label_hash}"
    else:
        short_doc_label = doc_label
    chain_id = f"{short_doc_label}-{family}-{arm}-k{k_pairs}"
    chain_root = run_root / chain_id
    chain_root.mkdir(parents=True, exist_ok=True)

    checkpoint = _load_checkpoint(chain_root)
    if checkpoint is not None:
        return checkpoint

    # No trusted checkpoint: a new attempt. Whatever an earlier, untrusted
    # attempt left in chain_root is moved to <run_root>/attic/ first (review
    # item 18) and the attempt is counted in the ledger (blocker 1).
    attempt = begin_chain_attempt(run_root, chain_id, chain_root, max_chain_attempts=max_chain_attempts)
    if attempt.exhausted:
        return exhausted_chain_result(attempt, {
            "chain_id": chain_id, "doc_label": doc_label, "family": family, "arm": arm,
            "k_pairs": k_pairs, "model": model, "pairs": [],
        }, max_chain_attempts)
    try:
        result = _run_chain_attempt(
            family, doc_label, docx_path, arm, k_pairs, model, chain_id, chain_root,
            word_receipts_enabled=word_receipts_enabled, anchor_or_plan_override=anchor_or_plan_override,
            circuit_breaker=circuit_breaker, attempt_number=attempt.number, pause_controller=pause_controller,
        )
    except CircuitOpenError:
        finish_chain_attempt(attempt, STATUS_ABORTED_CIRCUIT_OPEN)
        raise
    except Exception:
        finish_chain_attempt(attempt, "harness_exception")
        raise
    finish_chain_attempt(attempt, result["status"], infra_scope=(result.get("infra_signature") or {}).get("scope"))
    return result


def _check_circuit(circuit_breaker: CircuitBreaker | None, source: str) -> None:
    if circuit_breaker is not None:
        circuit_breaker.check(source)


def _run_chain_attempt(
    family: str, doc_label: str, docx_path: Path, arm: str, k_pairs: int, model: str,
    chain_id: str, chain_root: Path, *, word_receipts_enabled: bool,
    anchor_or_plan_override: dict[str, Any] | None, circuit_breaker: CircuitBreaker | None,
    attempt_number: int, pause_controller: UsagePauseController | None = None,
) -> dict[str, Any]:
    """One attempt of run_chain (everything after the checkpoint and attempt
    bookkeeping); writes the chain's checkpoint."""
    applicability = probe_family_applicability(family, docx_path, anchor_or_plan_override=anchor_or_plan_override)
    if not applicability["applicable"]:
        result = {
            "chain_id": chain_id, "doc_label": doc_label, "family": family, "arm": arm,
            "k_pairs": k_pairs, "model": model, "status": "not_applicable",
            "reason": applicability["reason"], "pairs": [], "attempt": attempt_number,
        }
        _write_checkpoint(chain_root, result)
        return result

    original_paragraphs = _paragraph_texts(docx_path)
    receipts: list[dict[str, Any]] = []
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(docx_path, chain_root / "receipts" / "chain-start", milestone="chain_start"))

    current_input = docx_path
    pairs: list[dict[str, Any]] = []
    chain_status = "completed"
    infra_signature: dict[str, Any] | None = None

    for pair_index in range(k_pairs):
        paragraphs_before_this_pair = _safe_paragraph_texts(current_input)
        if paragraphs_before_this_pair is None:
            # The PRIOR pair's own inverse output was corrupted badly enough
            # that even a raw paragraph read fails -- a real, on-thesis
            # finding in its own right (found live during development-slice
            # testing, 2026-08-30), not a reason to crash the whole slice.
            chain_status = STATUS_BLOCKED_UNREADABLE_INPUT
            pairs.append({
                "pair_index": pair_index,
                "forward": None,
                "blocked_reason": f"input docx from the prior pair's inverse output is corrupted/unreadable: {current_input}",
            })
            break
        marker = new_marker(f"s7-{family}")
        forward_spec, inverse_spec = _build_pair_specs(family, doc_label, current_input, marker, applicability)
        forward_spec = dataclasses.replace(forward_spec, arm=arm, pair_index=pair_index, trial_id=f"p{pair_index}-forward")

        _check_circuit(circuit_breaker, f"{chain_id}/{forward_spec.trial_id}")
        fwd_result = run_trial(forward_spec, chain_root, model=model)
        fwd_result["isolation_audit"] = audit_isolation(fwd_result)
        infra_signature = infra_signature_of(
            fwd_result, circuit_breaker, f"{chain_id}/{forward_spec.trial_id}", pause_controller=pause_controller,
        )
        if infra_signature is not None:
            # Review item 23: an infrastructure signature makes the chain
            # infra_blocked whatever the trial's outcome; the chain stops here
            # (it will be re-run) rather than spending more trials.
            chain_status = STATUS_INFRA_BLOCKED
            infra_signature = {**infra_signature, "trial_id": forward_spec.trial_id}
            pairs.append({"pair_index": pair_index, "forward": fwd_result})
            break
        fwd_execution_ok = fwd_result.get("returncode") == 0 and not fwd_result.get("timed_out")
        fwd_docx_changed = bool(fwd_result.get("docx_changed"))
        if fwd_execution_ok:
            fwd_grading = _safe_grade(_grade_forward, family, Path(fwd_result["output_docx_path"]), paragraphs_before_this_pair, forward_spec, applicability)
        elif fwd_docx_changed:
            # d1c4f7e2 -- a killed/non-zero-exit CLI process does not by
            # itself mean the underlying render-verified write failed:
            # found live, 2026-09-09, a real chain whose forward process
            # was killed by the harness's OWN outer subprocess timeout
            # (the agent never got to report "DONE") nonetheless left a
            # genuinely correct, render-verified table insert on disk --
            # confirmed directly, the exact expected marker text inside a
            # real <w:tbl> element. insert_table/insert_equation/
            # insert_caption's own render-verification gate is atomic: it
            # restores the file from backup on ANY failure and only ever
            # persists a change after a real backend successfully
            # rendered it, so a changed docx is real, positive evidence
            # the underlying task genuinely completed -- independent of
            # whether the wrapping CLI process itself finished reporting
            # before an outer timeout killed it. Grade it for real via
            # the SAME exception-safe _safe_grade used for a clean exit;
            # a genuinely corrupt/incomplete file still correctly fails
            # grading on its own merits (see _safe_grade's own docstring)
            # -- this does not skip or weaken that check, it only stops
            # discarding a result that would otherwise never even be
            # looked at.
            fwd_grading = _safe_grade(_grade_forward, family, Path(fwd_result["output_docx_path"]), paragraphs_before_this_pair, forward_spec, applicability)
        else:
            fwd_grading = {"verdict": "not_run", "reason": "forward process did not complete"}
        fwd_result["grading"] = fwd_grading
        fwd_task_completed = fwd_execution_ok or (fwd_docx_changed and fwd_grading.get("verdict") == "pass")
        if not fwd_execution_ok and fwd_task_completed:
            # Disclose the recovery explicitly -- a reader auditing raw
            # results later must be able to tell a cleanly-reported
            # success apart from one recovered this way, not just see
            # "completed" with no trace of the outer timeout.
            fwd_result["recovered_from_outer_timeout"] = True
        if word_receipts_enabled and fwd_task_completed:
            receipts.append(_milestone_word_receipt(Path(fwd_result["output_docx_path"]), chain_root / "receipts" / f"p{pair_index}-forward", milestone="after_pair_forward"))

        pair_record: dict[str, Any] = {"pair_index": pair_index, "forward": fwd_result}

        if not fwd_task_completed:
            chain_status = STATUS_BLOCKED_TIMEOUT if fwd_result.get("timed_out") else STATUS_BLOCKED_FORWARD_FAILED
            pairs.append(pair_record)
            break

        if inverse_spec is None:
            # equation's own paragraph text comes back empty from parse_docx()
            # (its content lives in <m:oMath>/<m:t>, not the <w:t> runs that
            # function reads -- confirmed directly, 2026-09-03), so it needs
            # its own resolver, not the marker-text one citation/caption share.
            # table_structural needs a THIRD resolver: the new table has no
            # paragraph id of its own at all (it's addressed by body-child
            # table_index, same scheme as insert_table/remove_table).
            if family == "equation":
                resolver = resolve_equation_para_id_by_marker
            elif family == "table_structural":
                resolver = resolve_table_index_by_marker
            else:
                resolver = resolve_para_id_by_marker_text
            try:
                resolved = resolver(Path(fwd_result["output_docx_path"]), forward_spec.marker_text)
            except Exception as exc:  # noqa: BLE001 -- a malformed/corrupted forward output must
                # degrade to a graded "blocked" outcome, never an unhandled harness_exception
                # that discards this pair's already-completed forward result. Found live
                # (2026-09-04) via the equation family's harder control-arm task: a genuinely
                # malformed word/document.xml (structurally valid ZIP, invalid XML content --
                # _package_is_valid_docx does not parse XML, only checks required parts exist)
                # raised ParseError here uncaught.
                resolved = {"found": False, "reason": f"resolver raised {type(exc).__name__}: {exc}"}
            if not resolved["found"]:
                pair_record["inverse"] = None
                pair_record["inverse_resolution_error"] = resolved["reason"]
                chain_status = STATUS_BLOCKED_INVERSE_UNRESOLVABLE
                pairs.append(pair_record)
                break
            if family == "caption":
                inverse_spec = generate_caption_inverse(
                    doc_label, Path(fwd_result["output_docx_path"]), forward_spec.trial_id, forward_spec.marker_text, resolved["para_id"],
                )
            elif family == "citation":
                inverse_spec = generate_citation_inverse(
                    doc_label, Path(fwd_result["output_docx_path"]), forward_spec.trial_id, forward_spec.marker_text, resolved["para_id"],
                )
            elif family == "equation":
                inverse_spec = generate_equation_inverse(
                    doc_label, Path(fwd_result["output_docx_path"]), forward_spec.trial_id, forward_spec.marker_text, resolved["para_id"],
                )
            elif family == "table_structural":
                inverse_spec = generate_table_structural_inverse(
                    doc_label, Path(fwd_result["output_docx_path"]), forward_spec.trial_id, forward_spec.marker_text, resolved["table_index"],
                )
            else:
                raise AssertionError(f"family {family!r} returned inverse=None but has no post-forward resolver wired up")

        inverse_spec = dataclasses.replace(
            inverse_spec, arm=arm, pair_index=pair_index, trial_id=f"p{pair_index}-inverse",
            input_docx=Path(fwd_result["output_docx_path"]),
        )
        _check_circuit(circuit_breaker, f"{chain_id}/{inverse_spec.trial_id}")
        inv_result = run_trial(inverse_spec, chain_root, model=model)
        inv_result["isolation_audit"] = audit_isolation(inv_result)
        infra_signature = infra_signature_of(
            inv_result, circuit_breaker, f"{chain_id}/{inverse_spec.trial_id}", pause_controller=pause_controller,
        )
        if infra_signature is not None:
            chain_status = STATUS_INFRA_BLOCKED
            infra_signature = {**infra_signature, "trial_id": inverse_spec.trial_id}
            pair_record["inverse"] = inv_result
            pairs.append(pair_record)
            break
        inv_execution_ok = inv_result.get("returncode") == 0 and not inv_result.get("timed_out")
        inv_docx_changed = bool(inv_result.get("docx_changed"))
        if inv_execution_ok:
            inv_grading = _safe_grade(_grade_inverse, family, Path(inv_result["output_docx_path"]), paragraphs_before_this_pair, inverse_spec)
        elif inv_docx_changed:
            # d1c4f7e2 -- same recovery as the forward trial above (see its
            # comment for the full account): a killed outer process does
            # not mean the render-verified write itself failed, and a
            # changed docx is real positive evidence worth actually
            # grading rather than discarding unseen.
            inv_grading = _safe_grade(_grade_inverse, family, Path(inv_result["output_docx_path"]), paragraphs_before_this_pair, inverse_spec)
        else:
            inv_grading = {"verdict": "not_run", "reason": "inverse process did not complete"}
        inv_result["grading"] = inv_grading
        inv_task_completed = inv_execution_ok or (inv_docx_changed and inv_grading.get("verdict") == "pass")
        if not inv_execution_ok and inv_task_completed:
            inv_result["recovered_from_outer_timeout"] = True
        if word_receipts_enabled and inv_task_completed:
            receipts.append(_milestone_word_receipt(Path(inv_result["output_docx_path"]), chain_root / "receipts" / f"p{pair_index}-inverse", milestone="after_pair_inverse"))

        pair_record["inverse"] = inv_result
        pairs.append(pair_record)

        if not inv_task_completed or inv_grading.get("verdict") != "pass":
            chain_status = "completed_with_failure"
            current_input = Path(inv_result["output_docx_path"]) if inv_task_completed else current_input
            continue

        current_input = Path(inv_result["output_docx_path"])

    final_paragraphs = _safe_paragraph_texts(current_input) if current_input.is_file() else None
    cumulative_fidelity = final_paragraphs == original_paragraphs if final_paragraphs is not None else False

    result = {
        "chain_id": chain_id, "doc_label": doc_label, "family": family, "arm": arm,
        "k_pairs": k_pairs, "model": model, "status": chain_status,
        "pairs_completed": len(pairs), "cumulative_fidelity_after_k_cycles": cumulative_fidelity,
        "pairs": pairs, "word_com_receipts": receipts, "attempt": attempt_number,
    }
    if infra_signature is not None:
        result["infra_signature"] = infra_signature
    # Written for every status so the attempt is on record, but
    # _load_checkpoint trusts only _CHECKPOINT_TRUSTED_STATUSES: an
    # infra_blocked chain is re-run (after its root moves to the attic).
    _write_checkpoint(chain_root, result)
    return result


_ARMS = ("control", "treatment")


def arm_order(seed: int | None, key: str) -> tuple[str, str]:
    """The order a matched (control, treatment) pair of chains is submitted
    in. Both arms of one pair are always submitted together, back to back
    (review minor: arms interleaved per document in run order, so host load
    and time of day are not confounded with arm). With `seed` None: control
    first, the historical order. With a seed: a fixed pseudo-random order per
    pair, from sha256(f"{seed}:{key}") -- no PRNG state, reproducible."""
    if seed is None:
        return _ARMS
    flip = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).digest()[0] & 1
    return (_ARMS[1], _ARMS[0]) if flip else _ARMS


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_corpus_slice(
    corpus_manifest_path: Path, split: str, families: tuple[str, ...], run_root: Path,
) -> dict[str, Any]:
    """--check-only (review item 19, S26 section 1.2 item 5): verifies every
    document's SHA-256 against the manifest (when it records one) and resolves
    each family's anchor/plan exactly as run_chain would, without starting any
    trial. Writes <run_root>/check-report.json (and its sha256 beside it);
    `ok` is True only when every hash matches and every (document, family)
    is applicable."""
    manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    documents = [d for d in manifest["documents"] if d["s7_split"] == split]
    rows: list[dict[str, Any]] = []
    ok = True
    for doc in documents:
        docx_path = Path(doc["docx_path"])
        row: dict[str, Any] = {"doc_label": doc["doc_label"], "docx_path": str(docx_path)}
        if not docx_path.is_file():
            row.update({"sha256": None, "sha256_ok": False, "error": "docx_path does not exist"})
            ok = False
            rows.append(row)
            continue
        actual = _sha256_path(docx_path)
        expected = doc.get("sha256")
        row["sha256"] = actual
        row["sha256_ok"] = expected is None or actual.lower() == str(expected).lower()
        if expected is None:
            row["sha256_note"] = "manifest records no sha256"
        ok = ok and row["sha256_ok"]
        row["families"] = {}
        if not row["sha256_ok"]:
            rows.append(row)
            continue
        for family in families:
            try:
                probe = probe_family_applicability(family, docx_path)
            except Exception as exc:  # noqa: BLE001 -- a check must report, not crash
                probe = {"applicable": False, "reason": f"resolver raised {type(exc).__name__}: {exc}"}
            row["families"][family] = probe
            ok = ok and bool(probe.get("applicable"))
        rows.append(row)
    report = {
        "schema": "paper-s7-check-only-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "corpus_manifest": str(corpus_manifest_path), "split": split, "families": list(families),
        "document_count": len(documents), "ok": ok, "documents": rows,
    }
    run_root.mkdir(parents=True, exist_ok=True)
    out = run_root / "check-report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_root / "check-report.json.sha256").write_text(f"{_sha256_path(out)}  check-report.json\n", encoding="utf-8")
    return report


def _corpus_chain_key(job: dict[str, Any]) -> tuple[str, str, str, int]:
    return (job["doc"]["doc_label"], job["family"], job["arm"], job["k"])


def run_corpus_slice(
    corpus_manifest_path: Path, split: str, families: tuple[str, ...], k_values: tuple[int, ...],
    model: str, run_root: Path, *, max_workers: int = 4, word_receipts_enabled: bool = True,
    arm_order_seed: int | None = None, max_chain_attempts: int | None = None,
    pause_controller: UsagePauseController | None = None, max_usage_cap_rounds: int | None = None,
) -> dict[str, Any]:
    """Rate-limit handling (2026-09-25): dispatches in rounds via
    usage_cap.run_with_usage_cap_retry. A round whose fresh CircuitBreaker
    trips on usage_limit/api_rate_limit is automatically retried after
    `pause_controller` waits (a parsed reset time, or exponential backoff) --
    no relaunch of this function/command is needed. A round that trips on
    any OTHER global kind (a hard infrastructure failure) is left exactly as
    before: those chains end aborted_circuit_open/infra_blocked, the final
    circuit_breaker in the manifest is open, and the caller (main()) exits 3.
    `pause_controller` defaults to a fresh UsagePauseController that writes
    its heartbeat to `<run_root>/usage-cap-status.json`.
    """
    manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    documents = [d for d in manifest["documents"] if d["s7_split"] == split]

    run_root.mkdir(parents=True, exist_ok=True)
    if pause_controller is None:
        pause_controller = UsagePauseController(heartbeat_path=run_root / "usage-cap-status.json")

    # Both arms of each (document, family, k) are one job each so a usage-cap
    # retry round can re-dispatch exactly the chains it needs to, not
    # necessarily both arms of a pair.
    all_jobs: list[dict[str, Any]] = [
        {"doc": doc, "family": family, "k": k, "arm": arm}
        for doc in documents
        for family in families
        for k in k_values
        for arm in arm_order(arm_order_seed, f"{doc['doc_label']}:{family}:{k}")
    ]

    def dispatch_round(jobs: list[dict[str, Any]], circuit_breaker: CircuitBreaker) -> tuple[dict[Any, dict[str, Any]], list[Any]]:
        round_results: dict[Any, dict[str, Any]] = {}
        round_submission: list[Any] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for job in jobs:
                doc, family, k, arm = job["doc"], job["family"], job["k"], job["arm"]
                future = pool.submit(
                    run_chain, family, doc["doc_label"], Path(doc["docx_path"]), arm, k, model, run_root,
                    word_receipts_enabled=word_receipts_enabled,
                    circuit_breaker=circuit_breaker, max_chain_attempts=max_chain_attempts,
                    pause_controller=pause_controller,
                )
                key = _corpus_chain_key(job)
                futures[future] = key
                round_submission.append([doc["doc_label"], family, k, arm])
            for future in concurrent.futures.as_completed(futures):
                doc_label, family, arm, k = key = futures[future]
                try:
                    round_results[key] = future.result()
                except CircuitOpenError as exc:
                    round_results[key] = {
                        "chain_id": f"{doc_label}-{family}-{arm}-k{k}-ABORTED",
                        "doc_label": doc_label, "family": family, "arm": arm, "k_pairs": k,
                        "status": STATUS_ABORTED_CIRCUIT_OPEN, "reason": str(exc), "pairs": [],
                    }
                except Exception as exc:  # noqa: BLE001
                    round_results[key] = {
                        "chain_id": f"{doc_label}-{family}-{arm}-k{k}-EXCEPTION",
                        "doc_label": doc_label, "family": family, "arm": arm, "k_pairs": k,
                        "status": "harness_exception", "reason": f"{type(exc).__name__}: {exc}",
                        "pairs": [],
                    }
        return round_results, round_submission

    final_results, submission_order, usage_cap_rounds = run_with_usage_cap_retry(
        dispatch_round, all_jobs, pause_controller, job_key=_corpus_chain_key,
        make_circuit_breaker=CircuitBreaker, max_rounds=max_usage_cap_rounds,
    )
    results = list(final_results.values())
    final_circuit_breaker = usage_cap_rounds[-1]["circuit_breaker"] if usage_cap_rounds else CircuitBreaker().state()

    manifest_out = {
        "schema": "paper-s7-benchmark-slice-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "split": split, "families": list(families), "k_values": list(k_values), "model": model,
        "document_count": len(documents), "chain_count": len(results),
        "arm_order_seed": arm_order_seed, "max_chain_attempts": max_chain_attempts,
        "submission_order": submission_order,
        "circuit_breaker": final_circuit_breaker,
        "usage_cap_rounds": usage_cap_rounds,
        "usage_cap_status": pause_controller.state(),
        "chains": results,
    }
    out_path = run_root / "slice-manifest.json"
    out_path.write_text(json.dumps(manifest_out, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-manifest", type=Path, default=Path(r"E:\MeridianData\ooxml-graph-paper\manifests\paper-s7-corpus-manifest-v1.json"))
    parser.add_argument("--split", required=True, choices=["development", "validation", "primary_holdout"])
    parser.add_argument("--families", nargs="+", default=list(_FAMILIES))
    parser.add_argument("--k-values", nargs="+", type=int, default=[1])
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--no-word-receipts", action="store_true")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument(
        "--check-only", action="store_true",
        help="Verify every document's SHA-256 and resolve every family's plan/anchor, write "
             "<run-root>/check-report.json, and exit (non-zero unless all pass). No trial is started.",
    )
    parser.add_argument(
        "--arm-order-seed", type=int, default=None,
        help="Seed for the order in which each matched pair's two arms are submitted (both are always "
             "submitted together). Omitted: control first.",
    )
    parser.add_argument(
        "--max-chain-attempts", type=int, default=None,
        help="Rerun limit per chain, counted in <run-root>/_chain_attempts/ (attempts ended by a global "
             "infrastructure event or the circuit breaker do not count). Omitted: no limit.",
    )
    parser.add_argument(
        "--max-usage-cap-rounds", type=int, default=None,
        help="Safety valve: stop auto-retrying after this many usage-cap/rate-limit pause-and-resume rounds "
             "(circuit_breaker stays open, exit 3). Omitted: unlimited -- the sweep resumes on its own for as "
             "long as the account keeps hitting its usage cap or a transient rate limit, with no relaunch needed.",
    )
    parser.add_argument(
        "--usage-cap-base-backoff-seconds", type=float, default=30.0,
        help="Backoff before the first retry after a usage-cap/rate-limit pause when the CLI gave no reset time.",
    )
    parser.add_argument(
        "--usage-cap-max-backoff-seconds", type=float, default=1800.0,
        help="Cap on the exponential backoff between usage-cap/rate-limit retry rounds (default 30 minutes).",
    )
    parser.add_argument(
        "--provenance-json", type=Path, default=None,
        help="Write a provenance record here (argv, this repo's git commit, the installed Meridian Docs "
             "package's commit/version, model, corpus manifest path+sha256, hostname, start/end time, exit "
             "status) at the start of a real run (not --check-only), then update it with the end time and "
             "exit status when the run finishes.",
    )
    args = parser.parse_args(argv)

    if args.check_only:
        report = check_corpus_slice(args.corpus_manifest, args.split, tuple(args.families), args.run_root)
        print(json.dumps({"ok": report["ok"], "document_count": report["document_count"]}, indent=2))
        print(f"Check report: {args.run_root / 'check-report.json'}")
        return 0 if report["ok"] else 2

    args.run_root.mkdir(parents=True, exist_ok=True)
    if args.provenance_json is not None:
        # No schedule concept in this script (that's the two respec_cascade
        # scripts only): schedule_path/_sha256 stay None.
        record = build_provenance(
            sys.argv, model=args.model, documents_manifest=args.corpus_manifest,
        )
        write_provenance_start(args.provenance_json, record)
    pause_controller = UsagePauseController(
        heartbeat_path=args.run_root / "usage-cap-status.json",
        base_backoff_seconds=args.usage_cap_base_backoff_seconds,
        max_backoff_seconds=args.usage_cap_max_backoff_seconds,
    )
    manifest = run_corpus_slice(
        args.corpus_manifest, args.split, tuple(args.families), tuple(args.k_values),
        args.model, args.run_root, max_workers=args.max_workers,
        word_receipts_enabled=not args.no_word_receipts,
        arm_order_seed=args.arm_order_seed, max_chain_attempts=args.max_chain_attempts,
        pause_controller=pause_controller, max_usage_cap_rounds=args.max_usage_cap_rounds,
    )

    counts: dict[str, int] = {}
    for chain in manifest["chains"]:
        status = chain.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps(counts, indent=2))
    print(f"Slice manifest: {args.run_root / 'slice-manifest.json'}")
    if manifest["usage_cap_rounds"]:
        print(f"Usage-cap pause/resume rounds: {len(manifest['usage_cap_rounds'])} "
              f"(heartbeat: {args.run_root / 'usage-cap-status.json'})")
    exit_status = 3 if manifest["circuit_breaker"]["open"] else 0
    if manifest["circuit_breaker"]["open"]:
        print(f"CIRCUIT BREAKER OPEN: {json.dumps(manifest['circuit_breaker'])}", file=sys.stderr)
    if args.provenance_json is not None:
        write_provenance_end(args.provenance_json, exit_status=exit_status)
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
