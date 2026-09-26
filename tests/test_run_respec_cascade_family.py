"""Unit tests for tools/run_respec_cascade_family.py's freeze handling,
grader-exception bookkeeping and six-family option (2026-09-25).

Same convention as tests/test_run_comment_targeting_family.py: no real
`claude -p` subprocess is ever invoked. A fake `run_trial` copies the step's
input .docx to the step's own doc.docx (and, for table_structural, really
inserts/removes a one-cell table carrying the step's marker, so the real
table resolver and table graders run). The five-family phase graders are
stubbed; what is under test is the orchestrator's own bookkeeping.

Run with: pixi run python -m pytest tests/test_run_respec_cascade_family.py -v
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import run_respec_cascade_family as rrcf  # noqa: E402
from docx_trial_evaluator import _FAMILY_OWN_TARGET_CHECKS  # noqa: E402

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_FIVE = ("bibliography", "citation", "section_reorder", "equation", "caption")


def _para(para_id: str, text: str) -> str:
    return f'<w:p w14:paraId="{para_id}"><w:r><w:t>{text}</w:t></w:r></w:p>'


def _write_docx(path: Path, body_xml: str) -> None:
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}" xmlns:w14="{_W14}"><w:body>{body_xml}</w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("_rels/.rels", "<Relationships/>")
        zf.writestr("word/document.xml", document_xml)


def _body(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    return xml.split("<w:body>", 1)[1].rsplit("</w:body>", 1)[0]


def _pristine(tmp_path: Path) -> Path:
    path = tmp_path / "pristine.docx"
    _write_docx(path, "".join(_para(f"P{i:07d}", f"Body paragraph number {i} with text.") for i in range(8)))
    return path


def _anchor(i: int) -> dict:
    return {"found": True, "anchor_para_id": f"P{i:07d}", "anchor_text_snippet": f"Body paragraph number {i}",
            "anchor_full_text": f"Body paragraph number {i} with text."}


def _anchor_set(with_table: bool = False) -> dict:
    entry = {
        "anchor_set_index": 0, "usable": True,
        "citation_anchor": _anchor(1), "equation_anchor": _anchor(2), "caption_anchor": _anchor(3),
        "section_reorder_plan": {
            "found": True, "section_id": "H1", "section_heading_text": "Section",
            "original_preceding_heading_para_id": "H0", "original_preceding_heading_text": "Before",
            "destination_heading_para_id": "HD1", "destination_heading_text": "D1",
            "redirect": {"found": True, "redirect_destination_heading_para_id": "HD2",
                         "redirect_destination_heading_text": "D2"},
        },
    }
    if with_table:
        entry["table_anchor"] = _anchor(4)
    return entry


def _make_fake_run_trial(calls: list[str], invalid_steps: frozenset[str] = frozenset()):
    def fake_run_trial(spec, chain_root, model):
        calls.append(spec.trial_id)
        trial_root = Path(chain_root) / spec.trial_id
        trial_root.mkdir(parents=True, exist_ok=True)
        out = trial_root / "doc.docx"
        if spec.trial_id in invalid_steps:
            out.write_bytes(b"not a zip")
        elif spec.family == "table_structural" and spec.direction == "forward":
            table = f"<w:tbl><w:tr><w:tc>{_para('T0000001', spec.marker_text)}</w:tc></w:tr></w:tbl>"
            _write_docx(out, _body(spec.input_docx) + table)
        elif spec.family == "table_structural":
            body = re.sub(r"<w:tbl>.*?</w:tbl>", "", _body(spec.input_docx), flags=re.S)
            _write_docx(out, body)
        else:
            shutil.copyfile(spec.input_docx, out)
        return {"trial_id": spec.trial_id, "trial_root": str(trial_root), "output_docx_path": str(out)}
    return fake_run_trial


def _passing_family() -> dict:
    return {"verdict": "pass", "checks": {"output_is_valid_docx": True}}


def _phase1_pass(*_args, **_kwargs):
    families = {
        f: {"verdict": "pass", "checks": {"output_is_valid_docx": True, **{c: True for c in _FAMILY_OWN_TARGET_CHECKS[f]}}}
        for f in _FIVE
    }
    # The fake run_trial leaves the citation anchor unedited, so its "after"
    # text is its "before" text.
    families["citation"]["anchor_matches_after"] = [_anchor(1)["anchor_full_text"]]
    return {"package_valid": True, "families": families, "collateral_clean": True, "phase1_pass": True}


def _phase2_pass(*_args, **_kwargs):
    return {"package_valid": True, "citation_absent": True, "section_at_d2": True,
            "keep_survival": {"overall_status": "clean_keep_survival"}, "phase2_pass": True}


def _phase3_pass(*_args, **_kwargs):
    return {"package_valid": True, "families": {f: _passing_family() for f in _FIVE},
            "final_structure_match": True, "phase3_pass": True}


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    graded_round_trips: list[tuple[str, str]] = []
    monkeypatch.setattr(rrcf, "run_trial", _make_fake_run_trial(calls))
    monkeypatch.setattr(rrcf, "audit_isolation", lambda result: {"violations": []})
    monkeypatch.setattr(rrcf, "_equation_flat_texts", lambda path: [])
    monkeypatch.setattr(rrcf, "resolve_para_id_by_marker_text", lambda path, marker: {"found": True, "para_id": "PX"})
    monkeypatch.setattr(rrcf, "resolve_equation_para_id_by_marker", lambda path, marker: {"found": True, "para_id": "PE"})
    monkeypatch.setattr(rrcf, "grade_phase1_build", _phase1_pass)
    monkeypatch.setattr(rrcf, "grade_phase2_respec", _phase2_pass)
    monkeypatch.setattr(rrcf, "grade_phase3_second_exposure", _phase3_pass)

    def fake_grade_family_inverse(family, output_docx, paragraphs_before_forward, target):
        graded_round_trips.append((family, Path(output_docx).parent.name))
        return {"verdict": "pass", "checks": {"output_is_valid_docx": True}}

    monkeypatch.setattr(rrcf, "_grade_family_inverse", fake_grade_family_inverse)
    return {"calls": calls, "graded_round_trips": graded_round_trips, "monkeypatch": monkeypatch}


def _run(tmp_path: Path, **kwargs) -> dict:
    return rrcf.run_respec_cascade_chain(
        "doc__anchor0", _pristine(tmp_path), "control", "haiku", tmp_path / "runs",
        kwargs.pop("anchor_set", _anchor_set()), word_receipts_enabled=False, **kwargs,
    )


def test_completed_chain_records_final_docx_and_no_grading_exceptions(tmp_path, stubbed):
    result = _run(tmp_path)
    assert result["status"] == "completed"
    assert result["steps_run"] == 17
    assert result["grading_exceptions"] == []
    assert result["rotation"] == list(rrcf.FIVE_FAMILY_ROTATION)
    assert Path(result["final_output_docx"]).parent.name == "3.5-caption-inverse"
    step_result = json.loads((Path(result["final_output_docx"]).parent / "step-result.json").read_text(encoding="utf-8"))
    assert step_result["step_id"] == "3.5-caption-inverse" and step_result["package_valid"] is True


def test_phase3_freeze_grades_finished_round_trips_and_marks_the_rest(tmp_path, stubbed):
    stubbed["monkeypatch"].setattr(
        rrcf, "resolve_equation_para_id_by_marker", lambda path, marker: {"found": False, "reason": "gone"},
    )
    result = _run(tmp_path)
    assert result["status"] == "chain_broken_at_step_3.4-inverse"  # unchanged status string
    assert result["freeze_cause"] == rrcf.FREEZE_CAUSE_ANCHOR_RERESOLUTION
    assert result["frozen_at_step"] == "3.4-inverse"
    assert "gone" in result["freeze_detail"]
    phase3 = result["phase3_result"]
    assert phase3["status"] == "frozen_before_checkpoint_c" and phase3["phase3_pass"] is False
    families = phase3["families"]
    assert [families[f]["verdict"] for f in _FIVE] == ["pass", "pass", "pass", "not_completed", "not_run"]
    # each finished round trip is graded on its own inverse output
    assert stubbed["graded_round_trips"] == [
        ("bibliography", "3.1-bibliography-inverse"),
        ("citation", "3.2-citation-inverse"),
        ("section_reorder", "3.3-section_reorder-inverse-d1-to-d2"),
    ]
    assert result["phase2_result"]["phase2_pass"] is True  # earlier checkpoint kept
    assert Path(result["final_output_docx"]).parent.name == "3.4-equation-forward"


def test_package_invalid_freeze_is_recorded_as_such_and_has_no_phase3(tmp_path, stubbed):
    stubbed["monkeypatch"].setattr(
        rrcf, "run_trial", _make_fake_run_trial(stubbed["calls"], frozenset({"1.3-section_reorder-forward"})),
    )
    result = _run(tmp_path)
    assert result["status"] == "chain_broken_at_step_1.3"
    assert result["freeze_cause"] == rrcf.FREEZE_CAUSE_PACKAGE_INVALID
    assert result["freeze_detail"] == result["reason"] and result["reason"]
    assert result["phase1_result"] is None and result["phase3_result"] is None


def test_frozen_chain_is_trusted_on_resume(tmp_path, stubbed):
    stubbed["monkeypatch"].setattr(
        rrcf, "run_trial", _make_fake_run_trial(stubbed["calls"], frozenset({"1.1-bibliography-forward"})),
    )
    first = _run(tmp_path)
    n_calls = len(stubbed["calls"])
    assert _run(tmp_path) == first and len(stubbed["calls"]) == n_calls


def test_grader_exception_reasons_are_kept_in_the_chain_result(tmp_path, stubbed):
    def boom(*_args, **_kwargs):
        raise KeyError("expected_d2_heading_para_id")

    stubbed["monkeypatch"].setattr(rrcf, "grade_phase3_second_exposure", boom)
    stubbed["monkeypatch"].setattr(rrcf, "chain_pass", boom)
    result = _run(tmp_path)
    assert result["status"] == "completed_with_failure"
    assert result["phase3_result"] == {"status": "grading_raised_exception", "reason": "KeyError: 'expected_d2_heading_para_id'"}
    assert result["grading_exceptions"] == [
        {"grader": "phase3_result", "reason": "KeyError: 'expected_d2_heading_para_id'"},
        {"grader": "chain_pass", "reason": "KeyError: 'expected_d2_heading_para_id'"},
    ]


def test_six_family_runs_table_steps_and_grades_the_table(tmp_path, stubbed):
    excluded_seen: list[list[str]] = []

    def fake_keep_survival(a_items, b_items, kept, excluded_paragraph_texts=None):
        excluded_seen.append(list(excluded_paragraph_texts or []))
        return {"overall_status": "clean_keep_survival"}

    stubbed["monkeypatch"].setattr(rrcf, "score_keep_survival", fake_keep_survival)
    stubbed["monkeypatch"].setattr(rrcf, "_items_with_equations", lambda path, paragraphs: {"paragraphs": []})
    result = _run(tmp_path, anchor_set=_anchor_set(with_table=True), six_family=True)
    assert result["status"] == "completed", result
    assert result["steps_run"] == 21
    assert "-six-" in result["chain_id"] and result["rotation"] == list(rrcf.SIX_FAMILY_ROTATION)
    for step in ("1.5-table_structural-forward", "1.6-caption-forward", "2.2-table_structural-inverse",
                 "3.5-table_structural-forward", "3.5-table_structural-inverse", "3.6-caption-inverse"):
        assert step in stubbed["calls"]
    phase1, phase2, phase3 = result["phase1_result"], result["phase2_result"], result["phase3_result"]
    assert phase1["families"]["table_structural"]["verdict"] == "pass"
    assert phase1["collateral_clean"] is True and phase1["phase1_pass"] is True
    assert phase2["table_absent"] is True and phase2["phase2_pass"] is True
    assert any("PILOT-S7-TABLE" in t for t in excluded_seen[0])  # reverted table excluded from keep-survival
    assert phase3["families"]["table_structural"]["verdict"] == "pass"
    assert phase3["table_leftovers"] == [] and phase3["phase3_pass"] is True


def test_six_family_table_left_behind_fails_checkpoint_b(tmp_path, stubbed):
    calls = stubbed["calls"]
    real_fake = _make_fake_run_trial(calls)

    def lazy_table_revert(spec, chain_root, model):
        if spec.trial_id == "2.2-table_structural-inverse":  # "succeeds" but leaves the table in place
            calls.append(spec.trial_id)
            trial_root = Path(chain_root) / spec.trial_id
            trial_root.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(spec.input_docx, trial_root / "doc.docx")
            return {"trial_id": spec.trial_id, "trial_root": str(trial_root), "output_docx_path": str(trial_root / "doc.docx")}
        return real_fake(spec, chain_root, model)

    stubbed["monkeypatch"].setattr(rrcf, "run_trial", lazy_table_revert)
    stubbed["monkeypatch"].setattr(rrcf, "score_keep_survival", lambda *a, **k: {"overall_status": "clean_keep_survival"})
    stubbed["monkeypatch"].setattr(rrcf, "_items_with_equations", lambda path, paragraphs: {"paragraphs": []})
    result = _run(tmp_path, anchor_set=_anchor_set(with_table=True), six_family=True)
    assert result["phase2_result"]["table_absent"] is False
    assert result["phase2_result"]["phase2_pass"] is False
    assert result["status"] == "completed_with_failure"


def test_six_family_without_table_anchor_is_not_applicable(tmp_path, stubbed):
    result = _run(tmp_path, six_family=True)
    assert result["status"] == "not_applicable" and result["reason"] == "missing_table_anchor"
    assert stubbed["calls"] == []


# ---------------------------------------------------------------------------
# 2026-09-25 (re-run preparation): the three freeze paths the review found
# untested, forward-step evidence on re-resolution freezes, step -> family
# through the recorded rotation, infrastructure stop, circuit breaker, ledger.
# ---------------------------------------------------------------------------

from claude_pair_runner import CircuitBreaker, CircuitOpenError  # noqa: E402

_SIX = ("bibliography", "citation", "section_reorder", "equation", "table_structural", "caption")


def test_step_family_maps_through_the_recorded_rotation():
    five, six = rrcf.FIVE_FAMILY_ROTATION, rrcf.SIX_FAMILY_ROTATION
    assert rrcf.step_family("3.5-inverse", five) == "caption"
    assert rrcf.step_family("3.5-inverse", six) == "table_structural"
    assert rrcf.step_family("3.6-forward", six) == "caption"
    assert rrcf.step_family("1.6-caption-forward", six) == "caption"
    assert rrcf.step_family("3.3a", five) == "section_reorder"
    assert rrcf.step_family("2.1", five) == "citation"
    assert rrcf.step_family("2.2", six) == "table_structural"
    assert rrcf.step_family("2.3", five) == "section_reorder"
    assert rrcf.step_family("3.7-forward", six) is None and rrcf.step_family("junk", five) is None


def test_phase2_freeze_has_no_phase3_targets_and_names_the_forward_step(tmp_path, stubbed):
    """Freeze path 1: a Phase-2 re-resolution freeze. Phase 1's graded result
    is kept, Phase 3 never started (phase3_result None), and the forward step
    that inserted the missing citation marker (1.2) is recorded."""
    stubbed["monkeypatch"].setattr(rrcf, "resolve_para_id_by_marker_text", lambda path, marker: {"found": False, "reason": "gone"})
    result = _run(tmp_path)
    assert result["status"] == "chain_broken_at_step_2.1"
    assert result["freeze_cause"] == rrcf.FREEZE_CAUSE_ANCHOR_RERESOLUTION
    assert result["frozen_family"] == "citation"
    assert result["phase1_result"]["phase1_pass"] is True
    assert result["phase2_result"] is None and result["phase3_result"] is None
    assert result["freeze_forward_step"]["step_id"] == "1.2-citation-forward"
    assert result["frozen_step_result"]["step_id"] == "1.2-citation-forward"
    assert set(result["freeze_forward_step"]) >= {"timed_out", "returncode", "package_valid"}
    assert result["steps_run"] == 5


def test_six_family_phase3_freeze_grades_the_table_round_trip_first(tmp_path, stubbed):
    """Freeze path 2: a six-family chain freezing at the caption's Phase-3
    re-resolution (3.6-inverse). The table round trip (3.5) finished and is
    graded with the real table grader; caption is the in-progress family."""
    stubbed["monkeypatch"].setattr(rrcf, "score_keep_survival", lambda *a, **k: {"overall_status": "clean_keep_survival"})
    stubbed["monkeypatch"].setattr(rrcf, "_items_with_equations", lambda path, paragraphs: {"paragraphs": []})
    stubbed["monkeypatch"].setattr(
        rrcf, "resolve_para_id_by_marker_text",
        lambda path, marker: ({"found": False, "reason": "caption marker gone"} if Path(path).parent.name == "3.6-caption-forward"
                              else {"found": True, "para_id": "PX"}),
    )
    result = _run(tmp_path, anchor_set=_anchor_set(with_table=True), six_family=True)
    assert result["status"] == "chain_broken_at_step_3.6-inverse"
    assert result["frozen_family"] == "caption"
    assert result["freeze_forward_step"]["step_id"] == "3.6-caption-forward"
    families = result["phase3_result"]["families"]
    assert [families[f]["verdict"] for f in _SIX] == ["pass", "pass", "pass", "pass", "pass", "not_completed"]
    assert families["table_structural"]["checks"]["marker_table_removed"] is True  # real table grader
    assert ("table_structural", "3.5-table_structural-inverse") not in stubbed["graded_round_trips"]
    assert len(stubbed["graded_round_trips"]) == 4


def test_phase3_package_invalid_freeze_marks_the_in_progress_family(tmp_path, stubbed):
    """Freeze path 3: a Phase-3 package-validity freeze. The cause is
    package_invalid, the round trip under way is not_completed, later ones
    not_run, and the earlier finished round trip is graded."""
    stubbed["monkeypatch"].setattr(
        rrcf, "run_trial", _make_fake_run_trial(stubbed["calls"], frozenset({"3.2-citation-forward"})),
    )
    result = _run(tmp_path)
    assert result["status"] == "chain_broken_at_step_3.2-forward"
    assert result["freeze_cause"] == rrcf.FREEZE_CAUSE_PACKAGE_INVALID
    assert result["frozen_family"] == "citation"
    assert result["freeze_forward_step"] is None
    assert result["frozen_step_result"]["step_id"] == "3.2-citation-forward"
    families = result["phase3_result"]["families"]
    assert [families[f]["verdict"] for f in _FIVE] == ["pass", "not_completed", "not_run", "not_run", "not_run"]
    assert result["phase2_result"]["phase2_pass"] is True


def test_completed_chain_has_a_step_log(tmp_path, stubbed):
    result = _run(tmp_path)
    assert [s["step_id"] for s in result["step_log"]][:2] == ["1.1-bibliography-forward", "1.2-citation-forward"]
    assert len(result["step_log"]) == 17 and result["render_gate_timeout_steps"] == []
    assert result["attempt"] == 1


def test_infrastructure_signature_stops_the_chain_and_it_is_re_run(tmp_path, stubbed):
    calls = stubbed["calls"]
    inner = _make_fake_run_trial(calls)
    flaky = {"n": 0}

    def fake(spec, chain_root, model):
        result = inner(spec, chain_root, model)
        if spec.trial_id == "2.3-section_reorder-redirect" and flaky["n"] == 0:
            flaky["n"] += 1
            result["infra_signature"] = {"kinds": ["nonzero_exit_no_json"], "scope": "chain", "evidence": []}
        return result

    stubbed["monkeypatch"].setattr(rrcf, "run_trial", fake)
    first = _run(tmp_path)
    assert first["status"] == rrcf.STATUS_INFRA_BLOCKED
    assert first["infra_signature"]["step_id"] == "2.3-section_reorder-redirect"
    assert calls[-1] == "2.3-section_reorder-redirect"
    second = _run(tmp_path)
    assert second["status"] == "completed" and second["attempt"] == 2
    assert calls.count("1.1-bibliography-forward") == 2
    runs = tmp_path / "runs"
    assert (runs / "attic" / first["chain_id"]).is_dir()
    ledger = json.loads((runs / "_chain_attempts" / f"{first['chain_id']}.json").read_text(encoding="utf-8"))
    assert [a["ended_status"] for a in ledger["attempts"]] == ["infra_blocked", "completed"]


def test_open_circuit_breaker_stops_the_chain_before_any_step(tmp_path, stubbed):
    breaker = CircuitBreaker()
    breaker.trip({"kinds": ["usage_limit"], "scope": "global"}, "elsewhere")
    with pytest.raises(CircuitOpenError):
        _run(tmp_path, circuit_breaker=breaker)
    assert stubbed["calls"] == []
    [ledger_path] = (tmp_path / "runs" / "_chain_attempts").iterdir()
    assert json.loads(ledger_path.read_text(encoding="utf-8"))["attempts"][0]["ended_status"] == "aborted_circuit_open"


def test_exhausted_chain_writes_its_infra_excluded_result_as_the_checkpoint(tmp_path, stubbed):
    """M1 fix (2026-09-26): before the fix, `exhausted_chain_result` was
    returned without ever calling `_write_checkpoint`, so `chain_root` kept
    whatever the LAST chargeable attempt wrote (here, an `infra_blocked`
    chain-result.json) even though the sweep manifest and this return value
    both say `infra_excluded` -- the on-disk file disagreed with the record
    of what actually happened."""
    calls = stubbed["calls"]
    inner = _make_fake_run_trial(calls)

    def always_infra_blocked(spec, chain_root, model):
        result = inner(spec, chain_root, model)
        if spec.trial_id == "1.1-bibliography-forward":
            result["infra_signature"] = {"kinds": ["nonzero_exit_no_json"], "scope": "chain", "evidence": []}
        return result

    stubbed["monkeypatch"].setattr(rrcf, "run_trial", always_infra_blocked)

    first = _run(tmp_path, max_chain_attempts=1)
    assert first["status"] == rrcf.STATUS_INFRA_BLOCKED

    second = _run(tmp_path, max_chain_attempts=1)
    assert second["status"] == "infra_excluded"

    chain_root = tmp_path / "runs" / first["chain_id"]
    on_disk = json.loads((chain_root / "chain-result.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "infra_excluded"
    assert on_disk == second

    # infra_excluded is deliberately never trusted on resume: a third launch
    # must still recognize the chain as exhausted from the ledger (not the
    # checkpoint) and must NOT start a new attempt (B1's "0 new attempts" fixed
    # point requires this).
    ledger_path = tmp_path / "runs" / "_chain_attempts" / f"{first['chain_id']}.json"
    attempts_before = len(json.loads(ledger_path.read_text(encoding="utf-8"))["attempts"])
    third = _run(tmp_path, max_chain_attempts=1)
    assert third["status"] == "infra_excluded"
    attempts_after = len(json.loads(ledger_path.read_text(encoding="utf-8"))["attempts"])
    assert attempts_after == attempts_before
