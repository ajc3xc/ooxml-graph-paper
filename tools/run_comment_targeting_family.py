"""PAPER-S24: comment_targeting family orchestrator
(docs/paper-s24-targeted-comment-protocol-v0.md).

Structurally copied from tools/run_respec_cascade_family.py's own
fresh-agent-per-step pattern -- chain_id/chain_root, crash-resume via a
trusted checkpoint file, current_input chaining between steps,
claude_pair_runner.run_trial reuse for real subprocess isolation, the same
doc-label-hash-suffix fix that file's own history documents (a plain
`doc_label[:N]` truncation silently collides for any two labels sharing a
long common prefix -- found live in that family's own primary sweep) --
REUSED directly, never rebuilt from scratch, per this build's own discipline
requirement. Adapted, not copied verbatim, for a family with:

  - No inverse (protocol section 0.2): every step is a single forward
    `insert_highlighted_note(mode="comment")` call (treatment) or an
    equivalent hand-authored `word/comments.xml` edit (control) -- there is
    no companion "undo" call anywhere in a chain, unlike every other family
    this paper's harness runs.
  - No fixed phase structure: `run_respec_cascade_family.py`'s own chain is
    a hand-written, 17-step sequence across 5 named families. This family's
    chain length is DATA, not code -- `2 * usable_k` steps, `usable_k` read
    from the frozen resolver schedule (different per document; protocol
    section 6: manuscript 4, SI 8, dissertation 8) -- so step construction
    here is a loop over the schedule's own `ambiguous_targets`/
    `unique_targets` lists, alternating condition each step (protocol
    section 2.1), rather than a sequence of named calls.
  - A GROWING keep-survival set (protocol section 4 item 3): each step's own
    grading needs every EARLIER step's own inserted comment, plus every
    pre-existing organic comment (protocol section 1.3), to check for
    corruption -- `kept_comments` accumulates by one entry per successful
    step, seeded once before step 1 from the pristine document's own real
    `word/comments.xml`.
  - Tool-grant swap: NO change needed to `claude_pair_runner.py` at all.
    That module's own `_treatment_allowed_tools` already grants exactly
    `Read,mcp__meridian-docs-pilot__<spec.treatment_tool>` for whichever
    tool a TrialSpec names -- `generate_comment_targeting_step` sets
    `treatment_tool="insert_highlighted_note"`, so the existing,
    unmodified runner already produces exactly `Read` +
    `insert_highlighted_note` for every treatment step, and its own prompt
    prefix already states `mode="comment"` verbatim as part of
    `treatment_args` (protocol section 2.3's own "never mode=inline"
    requirement is enforced by the ARGUMENT VALUE baked into
    `generate_comment_targeting_step`, not by any runner-level change).
    Control gets `Read`/`Write`/`Edit`/`Bash`, also unchanged, per
    `claude_pair_runner._CONTROL_ALLOWED_TOOLS`.

Also implements protocol section 3's isolated single-step baseline trial
runner (`run_comment_targeting_isolated_baseline`): the SAME per-step
machinery, invoked exactly once per (document, target, condition, arm),
against a fresh copy of the same pristine document, outside any chain.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_trial_broker import generate_comment_targeting_step  # noqa: E402
from docx_trial_evaluator import (  # noqa: E402
    _extract_comment_items,
    _package_is_valid_docx,
    grade_comment_targeting_chain,
    grade_comment_targeting_step,
)
from claude_pair_runner import audit_isolation, run_trial  # noqa: E402
from word_receipt_watchdog import word_receipt_with_orphan_diagnostics  # noqa: E402

_WORD_RECEIPT_TIMEOUT_SECONDS = 90.0
_FAMILY = "comment_targeting"
_CHECKPOINT_NAME = "chain-result.json"
_BASELINE_CHECKPOINT_NAME = "baseline-result.json"


def _doc_tag(doc_label: str) -> str:
    """8-hex-char hash of the full doc_label -- reused verbatim from
    `run_respec_cascade_family.py`'s own 2026-09-22 correction: a plain
    `doc_label[:N]` truncation silently collides for two labels sharing a
    long common prefix (that file's own docstring has the full, real
    incident this fixes: 3 of 4 anchor-set chains for one document silently
    overwrote each other's checkpoints under the old scheme). Used both for
    directory-naming (`short_doc_label`, no length ceiling there) and for
    every MARKER minted into document content (`new_marker`'s own callers),
    where Word's ~40-char bookmark-name truncation makes a long, doc-label-
    derived prefix a real collision risk -- this family doesn't mint
    bookmark-keyed content the way bibliography/citation do, but the same
    short, collision-resistant tag is used throughout regardless, for
    consistency with the rest of this paper's harness."""
    return hashlib.sha256(doc_label.encode("utf-8")).hexdigest()[:8]


def _short_doc_label(doc_label: str) -> str:
    return f"{doc_label[:24]}-{_doc_tag(doc_label)}"


def _milestone_word_receipt(docx_path: Path, out_dir: Path, *, milestone: str) -> dict[str, Any]:
    if not docx_path.is_file():
        return {"milestone": milestone, "status": "not_run", "reason": "input docx does not exist"}
    try:
        result = word_receipt_with_orphan_diagnostics(docx_path, out_dir, timeout=_WORD_RECEIPT_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 -- a receipt failure must never abort a real chain
        return {"milestone": milestone, "status": "not_run", "reason": f"{type(exc).__name__}: {exc}"}
    result["milestone"] = milestone
    result["status"] = result.get("render_receipt", {}).get("status", "unknown")
    return result


def _load_checkpoint(root: Path, name: str = _CHECKPOINT_NAME) -> dict[str, Any] | None:
    path = root / name
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    status = result.get("status", "")
    # Mirrors run_respec_cascade_family.py's own trust rule exactly: a
    # deterministic terminal outcome (including a package-validity gate
    # failure, a real structural finding about that step's own output) is
    # trusted on resume; anything else is re-run rather than risk trusting a
    # partial/interrupted write.
    trusted = status in ("completed", "completed_with_failure", "not_applicable") or status.startswith(
        "chain_broken_at_step"
    )
    if not trusted:
        return None
    return result


def _write_checkpoint(root: Path, result: dict[str, Any], name: str = _CHECKPOINT_NAME) -> None:
    tmp_path = root / f"{name}.tmp"
    tmp_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(root / name)


def _safe_call(fn, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """grade_comment_targeting_step/grade_comment_targeting_chain are
    first-use code (this build's own disclosed-risk convention, matching
    run_respec_cascade_family.py::_safe_call's identical rationale): a
    raised exception here must degrade to a graded, inspectable failure
    dict, never an unhandled crash that discards an otherwise-completed
    chain's worth of real subprocess work. Deliberately does NOT pre-guess
    which keys a caller will later `.get()` off this fallback dict (neither
    `grade_comment_targeting_step`'s `step_pass` nor
    `grade_comment_targeting_chain`'s `chain_pass`) -- every caller in this
    module reads those via `.get(...)`, which returns None (falsy) for a
    missing key, so a single generic fallback shape is safe for both call
    sites, exactly mirroring the respec_cascade precedent's own generic
    `{"status": "grading_raised_exception", "reason": ...}` shape."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 -- must never propagate, see docstring
        return {
            "status": "grading_raised_exception",
            "reason": f"{type(exc).__name__}: {exc}",
        }


def _seed_organic_kept_comments(pristine_docx_path: Path) -> dict[str, dict[str, Any]]:
    """Protocol section 1.3: two of the three real corpus documents have
    pre-existing ORGANIC comments (`jcshm-manuscript.docx`: 1, author "Adam
    Camerer"; `jcshm-si.docx`: 6, mostly "Claude (review flag)") that every
    step's own keep-survival check must verify survive untouched, exactly
    like every harness-inserted comment. Seeded once, before step 1, directly
    from the PRISTINE document's own real `word/comments.xml` (never assumed
    empty, never hand-listed for these two specific documents -- this reads
    whatever is actually there, so it also works unmodified on
    `masters-dissertation-defense.docx`, which has zero organic comments and
    no `word/comments.xml` part at all)."""
    organic = _extract_comment_items(pristine_docx_path)
    return {f"organic:{i}": item for i, item in enumerate(organic)}


def _run_step(
    spec, chain_root: Path, model: str, arm: str, step_id: str, current_input: Path,
) -> dict[str, Any]:
    """Executes exactly one step. Mirrors
    `run_respec_cascade_family.py::_run_step` exactly -- see that function's
    own docstring for why the `dataclasses.replace(spec, arm=..., trial_id=
    ..., input_docx=...)` override always happens immediately before running
    a spec, regardless of what its generator already set: this family's own
    chain advances `current_input` after every one of its `2*usable_k`
    steps, so a spec built even one step earlier would otherwise carry a
    stale `input_docx`."""
    step_spec = dataclasses.replace(spec, arm=arm, trial_id=step_id, input_docx=current_input)
    result = run_trial(step_spec, chain_root, model=model)
    result["isolation_audit"] = audit_isolation(result)
    result["step_id"] = step_id
    output_path = Path(result["output_docx_path"])
    valid, reason = _package_is_valid_docx(output_path)
    result["package_valid"] = valid
    result["package_invalid_reason"] = reason
    return result


def _interleaved_steps(schedule: dict[str, Any]) -> list[tuple[str, int, dict[str, Any]]]:
    """Protocol section 2.1's own alternating design, made explicit: returns
    `[(condition, condition_position, target), ...]`, length `2 *
    usable_k`, alternating `("ambiguous", i, ambiguous_targets[i-1])` /
    `("unique", i, unique_targets[i-1])` for `i` in `1..usable_k`.
    `condition_position` (1-indexed WITHIN its own condition's own
    sub-sequence) is distinct from this list's own absolute index -- it is
    what protocol section 4's "primary statistic: per-chain-position pass
    rate (1..K), by condition" actually means by chain position, since a
    document's frozen `usable_k` targets in EACH of `ambiguous_targets`/
    `unique_targets` are both fully used (protocol section 1.2b's own K
    table -- manuscript K=4 means 4 ambiguous AND 4 unique targets, 8 total
    physical steps -- not 4 total split across both conditions; confirmed by
    reading the hash-pinned schedule JSON directly, where both lists always
    have exactly `usable_k` entries each, not `usable_k // 2`)."""
    usable_k = int(schedule.get("usable_k") or 0)
    ambiguous_targets = schedule.get("ambiguous_targets") or []
    unique_targets = schedule.get("unique_targets") or []
    steps: list[tuple[str, int, dict[str, Any]]] = []
    for i in range(usable_k):
        steps.append(("ambiguous", i + 1, ambiguous_targets[i]))
        steps.append(("unique", i + 1, unique_targets[i]))
    return steps


def run_comment_targeting_chain(
    doc_label: str, docx_path: Path, arm: str, model: str, run_root: Path, schedule: dict[str, Any],
    *, word_receipts_enabled: bool = True,
) -> dict[str, Any]:
    """Runs one full comment_targeting chain (`2 * usable_k` single-step
    tool calls, protocol section 2.1) for one (document, arm) combination.
    `schedule` is one document's own entry from `resolve_comment_targeting_
    clusters`'s output (equivalently, one value of the hash-pinned
    `comment-targeting-schedule-v1.json`'s own `"documents"` dict) -- read
    directly, never re-derived or guessed, per this build's own discipline.
    """
    chain_id = f"{_short_doc_label(doc_label)}-{_FAMILY}-{arm}"
    chain_root = run_root / chain_id
    chain_root.mkdir(parents=True, exist_ok=True)

    checkpoint = _load_checkpoint(chain_root)
    if checkpoint is not None:
        return checkpoint

    base_result = {
        "chain_id": chain_id, "doc_label": doc_label, "family": _FAMILY, "arm": arm, "model": model,
    }

    usable_k = int(schedule.get("usable_k") or 0)
    ambiguous_targets = schedule.get("ambiguous_targets") or []
    unique_targets = schedule.get("unique_targets") or []
    if usable_k <= 0 or len(ambiguous_targets) < usable_k or len(unique_targets) < usable_k:
        result = {
            **base_result, "status": "not_applicable",
            "reason": (
                f"usable_k={usable_k} -- this document's own resolved schedule has no usable "
                f"interleaved ambiguous/unique target pool (protocol section 2.1's own K, capped "
                f"by the weaker of the two pools)"
            ),
            "chain_grade": None, "steps_run": 0, "round_trip_count": 0,
            "word_com_receipts": [], "organic_comment_count": None,
        }
        _write_checkpoint(chain_root, result)
        return result

    kept_comments = _seed_organic_kept_comments(docx_path)
    organic_count = len(kept_comments)

    receipts: list[dict[str, Any]] = []
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(docx_path, chain_root / "receipts" / "chain-start", milestone="chain_start"))

    current_input = docx_path
    steps_run = 0
    round_trip_count = 0  # explicit per-arm round-trip-count logging, protocol section 5 item 5
    step_results: list[dict[str, Any]] = []
    condition_by_step: list[str] = []
    condition_positions: list[int] = []

    def _freeze(step_id: str, step_result: dict[str, Any] | None, extra_reason: str | None = None) -> dict[str, Any]:
        reason = extra_reason if extra_reason is not None else (step_result or {}).get("package_invalid_reason")
        partial_grade = (
            _safe_call(grade_comment_targeting_chain, step_results, condition_by_step) if step_results else None
        )
        result = {
            **base_result, "status": f"chain_broken_at_step_{step_id}", "reason": reason,
            "chain_grade": partial_grade,
            "steps_run": steps_run, "round_trip_count": round_trip_count, "word_com_receipts": receipts,
            "organic_comment_count": organic_count, "condition_positions_completed": condition_positions,
            "frozen_step_result": step_result,
        }
        _write_checkpoint(chain_root, result)
        return result

    for condition, condition_position, target in _interleaved_steps(schedule):
        step_num = len(step_results) + 1
        step_id = f"step{step_num}-{condition}{condition_position}"
        trial_id = f"{chain_id}-{step_id}"
        # Distinct per-trial author tag (protocol section 4 item 1) -- the
        # SAME string is stated verbatim in the shared prompt (both arms
        # are told to use it) and passed as insert_highlighted_note's own
        # `author` argument for treatment, so grading's "exactly one new
        # <w:comment> by this author" check is meaningful for either arm.
        author_tag = f"MeridianBench-{trial_id}"

        spec = generate_comment_targeting_step(
            doc_label, current_input, chain_id, condition_position, condition, target, author_tag,
        )
        checkpoint_before = current_input
        step = _run_step(spec, chain_root, model, arm, step_id, current_input)
        steps_run += 1
        round_trip_count += 1
        if not step["package_valid"]:
            return _freeze(step_id, step)
        output_path = Path(step["output_docx_path"])

        confusable_siblings = target.get("confusable_sibling_para_ids", []) if condition == "ambiguous" else []
        step_grade = _safe_call(
            grade_comment_targeting_step, output_path, checkpoint_before, author_tag,
            target["para_id"], confusable_siblings, kept_comments,
        )
        step_results.append(step_grade)
        condition_by_step.append(condition)
        condition_positions.append(condition_position)

        new_comment_item = step_grade.get("new_comment_item")
        if new_comment_item is not None:
            # Tracks the ACTUAL observed comment (author/text/anchor), not
            # what was intended -- even a wrongly-targeted comment is now
            # real content in the document a LATER step must not further
            # corrupt (see grade_comment_targeting_step's own docstring on
            # this same field).
            kept_comments[author_tag] = new_comment_item

        current_input = output_path

    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(current_input, chain_root / "receipts" / "chain-end", milestone="chain_end"))

    chain_grade = _safe_call(grade_comment_targeting_chain, step_results, condition_by_step)
    status = "completed" if chain_grade.get("chain_pass") else "completed_with_failure"

    result = {
        **base_result, "status": status, "chain_grade": chain_grade,
        "steps_run": steps_run, "round_trip_count": round_trip_count,
        "word_com_receipts": receipts, "organic_comment_count": organic_count,
        "condition_positions_completed": condition_positions,
    }
    _write_checkpoint(chain_root, result)
    return result


def run_comment_targeting_isolated_baseline(
    doc_label: str, docx_path: Path, arm: str, model: str, run_root: Path,
    condition: str, target_index: int, target: dict[str, Any],
    *, word_receipts_enabled: bool = True,
) -> dict[str, Any]:
    """Protocol section 3's isolated single-step baseline: "for every
    (document, target, arm), run one isolated, single-step trial at the
    identical target and anchor used in the chain, against a fresh copy of
    the same pristine document snapshot" -- the SAME per-step machinery
    (`generate_comment_targeting_step`, `run_trial`,
    `grade_comment_targeting_step`) this chain runner already needs,
    invoked exactly ONCE, outside any chain: no prior chain steps of any
    kind, no accumulated kept-comments beyond this document's own organic
    pre-existing ones (protocol section 1.3's organic-comment hazard
    applies at position 1 too, isolated or not).

    `target_index` is this target's own 0-based position in whichever of
    `schedule["ambiguous_targets"]`/`schedule["unique_targets"]` it came
    from -- used only for a stable, human-legible baseline_id, never for any
    grading logic (grading only ever needs `target` itself).
    """
    trial_scoped_label = f"{_short_doc_label(doc_label)}-baseline-{condition}{target_index}"
    baseline_id = f"{trial_scoped_label}-{_FAMILY}-{arm}"
    baseline_root = run_root / baseline_id
    baseline_root.mkdir(parents=True, exist_ok=True)

    checkpoint = _load_checkpoint(baseline_root, name=_BASELINE_CHECKPOINT_NAME)
    if checkpoint is not None:
        return checkpoint

    base_result = {
        "baseline_id": baseline_id, "doc_label": doc_label, "family": _FAMILY, "arm": arm, "model": model,
        "condition": condition, "target_index": target_index,
    }

    receipts: list[dict[str, Any]] = []
    if word_receipts_enabled:
        receipts.append(
            _milestone_word_receipt(docx_path, baseline_root / "receipts" / "baseline-start", milestone="baseline_start")
        )

    trial_id = f"{baseline_id}-step1"
    author_tag = f"MeridianBench-{trial_id}"
    spec = generate_comment_targeting_step(doc_label, docx_path, baseline_id, 1, condition, target, author_tag)
    # docx_path itself (the pristine snapshot) is always the input -- never
    # a chain-mutated document, per protocol section 3. run_trial already
    # copies it into a fresh, trial-private directory before touching it
    # (claude_pair_runner.run_trial's own docstring), so no extra copy step
    # is needed here.
    step = _run_step(spec, baseline_root, model, arm, "baseline-step1", docx_path)

    if not step["package_valid"]:
        result = {
            **base_result, "status": "chain_broken_at_step_baseline",
            "reason": step.get("package_invalid_reason"), "step_grade": None,
            "round_trip_count": 1, "word_com_receipts": receipts,
        }
        _write_checkpoint(baseline_root, result, name=_BASELINE_CHECKPOINT_NAME)
        return result

    output_path = Path(step["output_docx_path"])
    kept_comments = _seed_organic_kept_comments(docx_path)
    confusable_siblings = target.get("confusable_sibling_para_ids", []) if condition == "ambiguous" else []
    step_grade = _safe_call(
        grade_comment_targeting_step, output_path, docx_path, author_tag,
        target["para_id"], confusable_siblings, kept_comments,
    )
    if word_receipts_enabled:
        receipts.append(
            _milestone_word_receipt(output_path, baseline_root / "receipts" / "baseline-end", milestone="baseline_end")
        )

    status = "completed" if step_grade.get("step_pass") else "completed_with_failure"
    result = {
        **base_result, "status": status, "step_grade": step_grade,
        "round_trip_count": 1, "word_com_receipts": receipts,
    }
    _write_checkpoint(baseline_root, result, name=_BASELINE_CHECKPOINT_NAME)
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--doc-label", required=True)
    parser.add_argument("--docx-path", type=Path, required=True)
    parser.add_argument("--arm", required=True, choices=["control", "treatment"])
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--no-word-receipts", action="store_true")
    parser.add_argument(
        "--schedule-json", type=Path, required=True,
        help=(
            "Path to a JSON file holding ONE document's own resolve_comment_targeting_clusters "
            "output (equivalently, one value of the hash-pinned comment-targeting-schedule-v1.json's "
            "own 'documents' dict) -- the frozen, already-hash-pinned schedule, never re-resolved "
            "live per trial (protocol section 2.2 item 4's own freeze-once discipline)."
        ),
    )
    baseline_group = parser.add_argument_group("isolated single-step baseline (protocol section 3)")
    baseline_group.add_argument(
        "--baseline", action="store_true",
        help="Run ONE isolated single-step baseline trial instead of a full chain.",
    )
    baseline_group.add_argument("--baseline-condition", choices=["ambiguous", "unique"])
    baseline_group.add_argument("--baseline-target-index", type=int)
    args = parser.parse_args(argv)

    schedule = json.loads(args.schedule_json.read_text(encoding="utf-8"))

    if args.baseline:
        if args.baseline_condition is None or args.baseline_target_index is None:
            print("--baseline requires --baseline-condition and --baseline-target-index", file=sys.stderr)
            return 1
        targets = schedule.get(
            "ambiguous_targets" if args.baseline_condition == "ambiguous" else "unique_targets", [],
        )
        if args.baseline_target_index >= len(targets):
            print(
                f"--baseline-target-index {args.baseline_target_index} out of range: only "
                f"{len(targets)} {args.baseline_condition} target(s) resolved for {args.docx_path}",
                file=sys.stderr,
            )
            return 1
        result = run_comment_targeting_isolated_baseline(
            args.doc_label, args.docx_path, args.arm, args.model, args.run_root,
            args.baseline_condition, args.baseline_target_index, targets[args.baseline_target_index],
            word_receipts_enabled=not args.no_word_receipts,
        )
        print(json.dumps({
            "baseline_id": result["baseline_id"], "status": result["status"],
        }, indent=2))
        return 0 if result["status"] in ("completed", "not_applicable") else 1

    result = run_comment_targeting_chain(
        args.doc_label, args.docx_path, args.arm, args.model, args.run_root, schedule,
        word_receipts_enabled=not args.no_word_receipts,
    )
    print(json.dumps({
        "chain_id": result["chain_id"], "status": result["status"], "steps_run": result["steps_run"],
        "round_trip_count": result["round_trip_count"],
    }, indent=2))
    print(f"Full result: {args.run_root / result['chain_id'] / _CHECKPOINT_NAME}")
    return 0 if result["status"] in ("completed", "not_applicable") else 1


if __name__ == "__main__":
    raise SystemExit(main())
