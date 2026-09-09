"""Regression tests for PAPER-S7's multi-family dispatch logic (pure functions
only -- no real Claude CLI or Meridian import needed for these)."""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import run_paper_s7_benchmark  # noqa: E402
from run_paper_s7_benchmark import (  # noqa: E402
    _build_pair_specs,
    _grade_forward,
    _grade_inverse,
    _load_checkpoint,
    _safe_grade,
    _safe_paragraph_texts,
    _write_checkpoint,
    run_chain,
)


def test_build_pair_specs_bibliography_needs_no_applicability_info(tmp_path: Path) -> None:
    forward, inverse = _build_pair_specs(
        "bibliography", "doc-a", tmp_path / "in.docx", "marker1", {"applicable": True},
    )

    assert forward.family == "bibliography"
    assert forward.treatment_tool == "insert_bibliography_entry"
    assert inverse is not None
    assert inverse.treatment_tool == "remove_bibliography_entry"
    assert forward.treatment_args["citation_key"] == inverse.treatment_args["citation_key"]


def test_build_pair_specs_citation_uses_resolved_anchor_for_forward(tmp_path: Path) -> None:
    applicability = {
        "applicable": True,
        "anchor": {"anchor_para_id": "p42", "anchor_text_snippet": "Hello", "anchor_full_text": "Hello world"},
    }

    forward, inverse = _build_pair_specs("citation", "doc-a", tmp_path / "in.docx", "marker1", applicability)

    assert forward.treatment_args["anchor_para_id"] == "p42"
    # PAPER-S7 correction: citation's anchor paragraph is itself modified by
    # forward (the marker text is appended into it), so its Meridian
    # synthetic id changes -- reusing the pristine-document id for inverse
    # would be stale. inverse must be resolved from forward's own OUTPUT,
    # same as caption, so it comes back None here (see run_chain).
    assert inverse is None


def test_generate_citation_inverse_uses_the_resolved_post_forward_id() -> None:
    from docx_trial_broker import generate_citation_inverse

    spec = generate_citation_inverse(
        "doc-a", Path("/tmp/forward-output.docx"), "marker1",
        "[PILOT-S7-CITATION-marker1]", "sp_post_forward_id",
    )

    assert spec.treatment_tool == "remove_citation"
    assert spec.treatment_args["anchor_para_id"] == "sp_post_forward_id"
    assert spec.marker_text == "[PILOT-S7-CITATION-marker1]"
    # 2026-09-05: passed explicitly so remove_citation can disambiguate when
    # the anchor paragraph holds more than one CSL_CITATION field.
    assert spec.treatment_args["match_display_text"] == "[PILOT-S7-CITATION-marker1]"


def test_build_pair_specs_caption_returns_none_inverse(tmp_path: Path) -> None:
    applicability = {
        "applicable": True,
        "anchor": {"anchor_para_id": "p1", "anchor_text_snippet": "Snip", "anchor_full_text": "Snip text"},
    }

    forward, inverse = _build_pair_specs("caption", "doc-a", tmp_path / "in.docx", "marker1", applicability)

    assert forward.treatment_tool == "insert_caption"
    assert inverse is None  # resolved post-forward by the runner, not upfront


def test_build_pair_specs_equation_returns_none_inverse(tmp_path: Path) -> None:
    applicability = {
        "applicable": True,
        "anchor": {"anchor_para_id": "p1", "anchor_text_snippet": "Snip", "anchor_full_text": "Snip text"},
    }

    forward, inverse = _build_pair_specs("equation", "doc-a", tmp_path / "in.docx", "marker1", applicability)

    assert forward.treatment_tool == "insert_equation"
    assert forward.treatment_args["anchor_para_id"] == "p1"
    assert inverse is None  # resolved post-forward, same as caption/citation -- see docx_anchor_prober.resolve_equation_para_id_by_marker


def test_generate_equation_inverse_uses_the_resolved_post_forward_id() -> None:
    from docx_trial_broker import generate_equation_inverse

    spec = generate_equation_inverse(
        "doc-a", Path("/tmp/forward-output.docx"), "marker1", "9876543210", "sp_post_forward_id",
    )

    assert spec.treatment_tool == "remove_equation"
    assert spec.treatment_args["equation_para_id"] == "sp_post_forward_id"
    assert spec.marker_text == "9876543210"


def test_build_pair_specs_table_structural_returns_none_inverse(tmp_path: Path) -> None:
    applicability = {
        "applicable": True,
        "anchor": {"anchor_para_id": "p1", "anchor_text_snippet": "Snip", "anchor_full_text": "Snip text"},
    }

    forward, inverse = _build_pair_specs("table_structural", "doc-a", tmp_path / "in.docx", "marker1", applicability)

    assert forward.treatment_tool == "insert_table"
    assert forward.treatment_args["anchor_para_id"] == "p1"
    assert forward.treatment_args["rows"] == 1
    assert forward.treatment_args["cols"] == 1
    assert inverse is None  # resolved post-forward, same as caption/citation/equation


def test_generate_table_structural_inverse_uses_the_resolved_post_forward_index() -> None:
    from docx_trial_broker import generate_table_structural_inverse

    spec = generate_table_structural_inverse(
        "doc-a", Path("/tmp/forward-output.docx"), "marker1", "PILOT-S7-TABLE-abc123", 3,
    )

    assert spec.treatment_tool == "remove_table"
    assert spec.treatment_args["table_index"] == 3
    assert spec.marker_text == "PILOT-S7-TABLE-abc123"


def test_build_pair_specs_section_reorder_uses_plan(tmp_path: Path) -> None:
    applicability = {
        "applicable": True,
        "plan": {
            "section_id": "h2", "section_heading_text": "Section Two",
            "original_preceding_heading_para_id": "h1", "original_preceding_heading_text": "Section One",
            "destination_heading_para_id": "h3", "destination_heading_text": "Section Three",
        },
    }

    forward, inverse = _build_pair_specs("section_reorder", "doc-a", tmp_path / "in.docx", "marker1", applicability)

    assert forward.treatment_args["destination_anchor_para_id"] == "h3"
    assert inverse.treatment_args["destination_anchor_para_id"] == "h1"
    assert forward.treatment_args["section_id"] == inverse.treatment_args["section_id"] == "h2"


def test_build_pair_specs_rejects_unknown_family(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown family"):
        _build_pair_specs("nonexistent", "doc-a", tmp_path / "in.docx", "m", {})


def test_grade_dispatch_rejects_unknown_family(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown family"):
        _grade_forward("nonexistent", tmp_path / "out.docx", [], None, {})
    with pytest.raises(ValueError, match="unknown family"):
        _grade_inverse("nonexistent", tmp_path / "out.docx", [], None)


def test_safe_paragraph_texts_returns_none_on_corrupt_zip_instead_of_raising(tmp_path: Path) -> None:
    """Found live in a real development-slice run (2026-08-30): a control
    arm's own edit corrupted its output package badly enough that even a raw
    word/document.xml zip read raised KeyError, crashing the whole chain as
    an unhandled harness_exception rather than a graded failure."""
    corrupt = tmp_path / "corrupt.docx"
    import zipfile

    with zipfile.ZipFile(corrupt, "w") as zf:
        zf.writestr("not-the-right-part.xml", "<x/>")

    assert _safe_paragraph_texts(corrupt) is None


def test_safe_paragraph_texts_returns_none_on_non_zip_bytes(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "not-a-docx.docx"
    not_a_zip.write_bytes(b"this is not a zip file at all")

    assert _safe_paragraph_texts(not_a_zip) is None


def test_safe_paragraph_texts_returns_none_on_missing_file(tmp_path: Path) -> None:
    """Found live (2026-09-04) via the equation family's harder control-arm
    task: a control trial that never wrote its output file at all raised an
    unhandled FileNotFoundError here, the same failure mode the original
    three exceptions were added to close."""
    assert _safe_paragraph_texts(tmp_path / "does-not-exist.docx") is None


def test_safe_grade_converts_a_raised_exception_into_a_graded_fail() -> None:
    """grade_forward_trial_equation and friends do a raw ET.fromstring parse
    after _package_is_valid_docx's own check, which only validates ZIP
    structure and required-part presence -- never that the XML content
    itself is well-formed. Found live (2026-09-04): a genuinely malformed
    word/document.xml (structurally valid ZIP, invalid XML content) raised
    ParseError here uncaught, crashing the whole chain as an uninformative
    harness_exception instead of a graded, informative fail."""
    def _always_raises(*args, **kwargs):
        raise ValueError("simulated malformed-XML parse failure")

    result = _safe_grade(_always_raises, "arg1", kwarg="x")

    assert result["verdict"] == "fail"
    assert "ValueError" in result["reason"]


def test_safe_grade_passes_through_a_real_grading_result() -> None:
    def _echoes(x):
        return {"verdict": "pass", "checks": {"ok": True}}

    result = _safe_grade(_echoes, "anything")

    assert result == {"verdict": "pass", "checks": {"ok": True}}


def test_checkpoint_round_trip_for_a_trusted_status(tmp_path: Path) -> None:
    result = {"chain_id": "x", "status": "completed", "pairs": []}
    _write_checkpoint(tmp_path, result)

    loaded = _load_checkpoint(tmp_path)

    assert loaded == result


def test_checkpoint_not_trusted_for_blocked_status(tmp_path: Path) -> None:
    """Found live (2026-09-02): a Windows STATUS_DLL_INIT_FAILED process-
    launch failure under shared-host resource contention produces a
    "blocked" chain result indistinguishable, without deeper inspection,
    from a genuine forward-call timeout. A resume must always retry a
    blocked chain rather than risk silently trusting an infra hiccup as
    real experimental data."""
    _write_checkpoint(tmp_path, {"chain_id": "x", "status": "blocked", "pairs": []})

    assert _load_checkpoint(tmp_path) is None


def test_checkpoint_missing_file_returns_none(tmp_path: Path) -> None:
    assert _load_checkpoint(tmp_path) is None


def test_checkpoint_corrupt_json_returns_none(tmp_path: Path) -> None:
    (tmp_path / "chain-result.json").write_text("{not valid json", encoding="utf-8")

    assert _load_checkpoint(tmp_path) is None


def test_run_chain_is_resumable_for_a_not_applicable_combo(tmp_path: Path) -> None:
    """End-to-end test of the actual resume mechanism using a real
    not_applicable outcome (no Claude CLI subprocess involved, so this can
    run without mocking): a second run_chain call for the identical
    (doc, family, arm, k) combo must land on the SAME deterministic
    chain_root and reuse the checkpoint rather than recomputing."""
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>No headings here.</w:t></w:r></w:p></w:body></w:document>'
    ).encode("utf-8")
    docx_path = tmp_path / "in.docx"
    with zipfile.ZipFile(docx_path, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    run_root = tmp_path / "run-root"

    first = run_chain("section_reorder", "doc-a", docx_path, "control", 1, "sonnet", run_root)
    assert first["status"] == "not_applicable"

    second = run_chain("section_reorder", "doc-a", docx_path, "control", 1, "sonnet", run_root)

    assert second == first
    assert first["chain_id"] == second["chain_id"]


def _write_minimal_docx(path: Path, text: str = "No headings here.") -> None:
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'
    ).encode("utf-8")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)


def _fake_trial_result(spec, chain_root: Path, *, timed_out: bool, returncode: int | None, docx_changed: bool, source_docx: Path) -> dict:
    """Mirrors claude_pair_runner.run_trial's real return shape closely
    enough to drive run_chain's control flow and audit_isolation, without
    spawning a real `claude -p` subprocess."""
    trial_root = chain_root / spec.trial_id
    trial_root.mkdir(parents=True, exist_ok=True)
    docx_in_trial = trial_root / "doc.docx"
    shutil.copyfile(source_docx, docx_in_trial)
    return {
        "trial_id": spec.trial_id, "doc_label": spec.doc_label, "arm": spec.arm,
        "direction": spec.direction, "family": spec.family, "pair_index": spec.pair_index,
        "model": "sonnet", "started_at": "2026-09-09T00:00:00", "wall_time_seconds": 1.0,
        "timed_out": timed_out, "returncode": returncode,
        "input_hash_sha256": "input-hash",
        "output_hash_sha256": "output-hash" if docx_changed else "input-hash",
        "docx_changed": docx_changed, "trial_root": str(trial_root),
        "output_docx_path": str(docx_in_trial), "cli_command_argv": [],
        "claude_json_result": None, "stdout_tail": "", "stderr_tail": "",
        "mcp_flake_retry_triggered": False,
    }


def test_run_chain_recovers_forward_trial_killed_by_outer_timeout_when_docx_changed_and_grades_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """d1c4f7e2: found live (2026-09-09) that a real chain's forward CLI
    process was killed by the harness's own outer subprocess timeout yet
    left a genuinely correct, render-verified write on disk (docx_changed
    was true, and the file itself graded as a real pass on direct
    inspection). run_chain must recover this case instead of discarding it
    as "blocked" just because the wrapping process never reported DONE."""
    docx_path = tmp_path / "in.docx"
    _write_minimal_docx(docx_path)
    forward_output = tmp_path / "forward-output.docx"
    _write_minimal_docx(forward_output)
    inverse_output = tmp_path / "inverse-output.docx"
    _write_minimal_docx(inverse_output)

    def fake_run_trial(spec, chain_root, *, model):
        if spec.direction == "forward":
            return _fake_trial_result(spec, chain_root, timed_out=True, returncode=None, docx_changed=True, source_docx=forward_output)
        return _fake_trial_result(spec, chain_root, timed_out=False, returncode=0, docx_changed=True, source_docx=inverse_output)

    monkeypatch.setattr(run_paper_s7_benchmark, "run_trial", fake_run_trial)
    monkeypatch.setattr(run_paper_s7_benchmark, "_grade_forward", lambda *a, **k: {"verdict": "pass", "checks": {}})
    monkeypatch.setattr(run_paper_s7_benchmark, "_grade_inverse", lambda *a, **k: {"verdict": "pass", "checks": {}})

    result = run_chain("bibliography", "doc-a", docx_path, "treatment", 1, "sonnet", tmp_path / "run-root", word_receipts_enabled=False)

    assert result["status"] == "completed"
    fwd_result = result["pairs"][0]["forward"]
    assert fwd_result["recovered_from_outer_timeout"] is True
    assert fwd_result["grading"]["verdict"] == "pass"


def test_run_chain_does_not_recover_forward_trial_when_docx_changed_but_grading_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative case for the same recovery path: a changed docx is only
    evidence worth grading, not a free pass. If the file that was actually
    left on disk genuinely fails grading, the chain must still end up
    blocked -- this does not weaken the existing grading check."""
    docx_path = tmp_path / "in.docx"
    _write_minimal_docx(docx_path)
    forward_output = tmp_path / "forward-output.docx"
    _write_minimal_docx(forward_output)

    def fake_run_trial(spec, chain_root, *, model):
        assert spec.direction == "forward", "inverse must never run once the forward pair is blocked"
        return _fake_trial_result(spec, chain_root, timed_out=True, returncode=None, docx_changed=True, source_docx=forward_output)

    monkeypatch.setattr(run_paper_s7_benchmark, "run_trial", fake_run_trial)
    monkeypatch.setattr(run_paper_s7_benchmark, "_grade_forward", lambda *a, **k: {"verdict": "fail", "reason": "simulated genuine grading failure"})

    result = run_chain("bibliography", "doc-a", docx_path, "treatment", 1, "sonnet", tmp_path / "run-root", word_receipts_enabled=False)

    assert result["status"] == "blocked"
    fwd_result = result["pairs"][0]["forward"]
    assert "recovered_from_outer_timeout" not in fwd_result


def test_run_chain_recovers_inverse_trial_killed_by_outer_timeout_when_docx_changed_and_grades_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors the forward-trial recovery test above for the inverse trial,
    which needs the identical treatment (see d1c4f7e2 in run_chain)."""
    docx_path = tmp_path / "in.docx"
    _write_minimal_docx(docx_path)
    forward_output = tmp_path / "forward-output.docx"
    _write_minimal_docx(forward_output)
    inverse_output = tmp_path / "inverse-output.docx"
    _write_minimal_docx(inverse_output)

    def fake_run_trial(spec, chain_root, *, model):
        if spec.direction == "forward":
            return _fake_trial_result(spec, chain_root, timed_out=False, returncode=0, docx_changed=True, source_docx=forward_output)
        return _fake_trial_result(spec, chain_root, timed_out=True, returncode=None, docx_changed=True, source_docx=inverse_output)

    monkeypatch.setattr(run_paper_s7_benchmark, "run_trial", fake_run_trial)
    monkeypatch.setattr(run_paper_s7_benchmark, "_grade_forward", lambda *a, **k: {"verdict": "pass", "checks": {}})
    monkeypatch.setattr(run_paper_s7_benchmark, "_grade_inverse", lambda *a, **k: {"verdict": "pass", "checks": {}})

    result = run_chain("bibliography", "doc-a", docx_path, "treatment", 1, "sonnet", tmp_path / "run-root", word_receipts_enabled=False)

    assert result["status"] == "completed"
    inv_result = result["pairs"][0]["inverse"]
    assert inv_result["recovered_from_outer_timeout"] is True
    assert inv_result["grading"]["verdict"] == "pass"
