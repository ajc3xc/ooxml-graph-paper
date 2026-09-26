"""Tests for tools/run_respec_cascade_baselines.py (2026-09-25, review items 6
and 21): the baseline sweep reads the primary run's schedule and documents
(public documents included), verifies every hash, adds table_structural for a
six-family run, and fails loudly instead of silently dropping a family.
run_chain is faked; no trial runs.

Run with: pixi run python -m pytest tests/test_run_respec_cascade_baselines.py -v
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import run_respec_cascade_baselines as baselines  # noqa: E402
import run_respec_cascade_sweep as sweep  # noqa: E402


def _anchor(prefix: str, i: int) -> dict:
    return {"found": True, "anchor_para_id": f"{prefix}{i}", "anchor_text_snippet": prefix, "anchor_full_text": prefix}


def _schedule(n: int, usable: bool = True) -> list[dict]:
    return [
        {"anchor_set_index": i, "usable": usable, "reason": None if usable else "no_anchor",
         "citation_anchor": _anchor("C", i), "equation_anchor": _anchor("E", i), "caption_anchor": _anchor("K", i),
         "section_reorder_plan": {"found": True, "section_id": f"S{i}"}}
        for i in range(n)
    ]


@pytest.fixture
def primary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A primary run root with a verified schedule over two public documents."""
    state: dict = {"usable": True, "chains": []}
    monkeypatch.setattr(sweep, "resolve_respec_schedule", lambda path, max_anchor_sets: _schedule(2, state["usable"]))
    monkeypatch.setattr(sweep, "resolve_multiple_body_anchors",
                        lambda path, max_anchors, exclude_para_ids: [_anchor("T", i) for i in range(max_anchors)])

    def fake_run_chain(family, doc_label, docx_path, arm, k, model, run_root, **kwargs):
        state["chains"].append({"family": family, "doc_label": doc_label, "docx_path": Path(docx_path), "arm": arm,
                                "override": kwargs["anchor_or_plan_override"], "run_root": Path(run_root)})
        return {"chain_id": f"{doc_label}-{family}-{arm}-k1", "doc_label": doc_label, "family": family, "arm": arm,
                "status": "completed", "pairs": []}

    monkeypatch.setattr(baselines, "run_chain", fake_run_chain)
    rows = []
    for label in ("pub-a", "pub-b"):
        path = tmp_path / "corpus" / f"{label}.docx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"docx {label}".encode())
        rows.append({"doc_label": label, "docx_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = tmp_path / "documents.json"
    manifest.write_text(json.dumps({"documents": rows}), encoding="utf-8")

    def make(six_family: bool) -> Path:
        run_root = tmp_path / ("six" if six_family else "five")
        sweep.check_primary_sweep(run_root, max_anchor_sets=2, six_family=six_family,
                                  documents=sweep.load_document_manifest(manifest))
        return run_root

    return {"make": make, "state": state, "manifest": manifest, "tmp": tmp_path}


def test_six_family_baselines_add_table_structural_at_the_table_anchor(primary):
    run_root = primary["make"](True)
    out = baselines.run_baseline_sweep(run_root, primary["tmp"] / "baselines", "haiku", max_workers=1)
    assert out["families"] == list(baselines.SIX_FAMILIES) and out["rotation"] == "six_family"
    chains = primary["state"]["chains"]
    assert len(chains) == 2 * 2 * 6 * 2  # documents x anchor-sets x families x arms
    table = [c for c in chains if c["family"] == "table_structural"]
    assert {c["override"]["anchor_para_id"] for c in table} == {"T0", "T1"}
    assert all(c["run_root"].name == "table_structural" for c in table)
    assert {c["docx_path"].name for c in chains} == {"pub-a.docx", "pub-b.docx"}  # public documents, from the meta
    meta = json.loads((run_root / sweep.SCHEDULE_META_NAME).read_text())
    assert out["anchor_schedules_sha256"] == meta["anchor_schedules_sha256"]
    order = out["submission_order"]
    assert all(order[i][:2] == order[i + 1][:2] and {order[i][2], order[i + 1][2]} == {"control", "treatment"}
               for i in range(0, len(order), 2))


def test_five_family_primary_gives_five_family_baselines(primary):
    run_root = primary["make"](False)
    out = baselines.run_baseline_sweep(run_root, primary["tmp"] / "b5", "haiku", max_workers=1)
    assert out["families"] == list(baselines.FIVE_FAMILIES)
    with pytest.raises(sweep.ScheduleMismatchError, match="six-family"):
        baselines.run_baseline_sweep(run_root, primary["tmp"] / "b5x", "haiku", six_family=True)


def test_baselines_require_the_primary_schedule_and_never_re_resolve(primary, monkeypatch):
    monkeypatch.setattr(sweep, "resolve_respec_schedule", lambda *a, **k: pytest.fail("must not resolve"))
    empty_root = primary["tmp"] / "no-primary"
    empty_root.mkdir()
    with pytest.raises(sweep.ScheduleMismatchError, match="does not exist"):
        baselines.run_baseline_sweep(empty_root, primary["tmp"] / "b", "haiku")
    assert baselines.main(["--run-root", str(empty_root), "--baseline-run-root", str(primary["tmp"] / "b")]) == 2
    assert primary["state"]["chains"] == []


def test_baselines_refuse_a_tampered_schedule_or_wrong_expected_hash(primary):
    run_root = primary["make"](True)
    with pytest.raises(sweep.ScheduleMismatchError, match="expected"):
        baselines.run_baseline_sweep(run_root, primary["tmp"] / "b", "haiku", expected_schedule_sha256="0" * 64)
    path = run_root / sweep.SCHEDULE_NAME
    path.write_bytes(path.read_bytes().replace(b'"T0"', b'"T7"'))
    with pytest.raises(sweep.ScheduleMismatchError, match="recorded"):
        baselines.run_baseline_sweep(run_root, primary["tmp"] / "b", "haiku")
    assert primary["state"]["chains"] == []


def test_baselines_refuse_a_changed_document_or_a_disagreeing_manifest(primary):
    run_root = primary["make"](False)
    other = primary["tmp"] / "other.json"
    other.write_text(json.dumps({"documents": [{"doc_label": "pub-a", "docx_path": "x.docx", "sha256": "ab"}]}))
    with pytest.raises(sweep.ScheduleMismatchError, match="disagrees"):
        baselines.run_baseline_sweep(run_root, primary["tmp"] / "b", "haiku", documents_manifest=other)
    out = baselines.run_baseline_sweep(run_root, primary["tmp"] / "b-ok", "haiku",
                                       documents_manifest=primary["manifest"], max_workers=1)
    assert out["chain_count"] == 2 * 2 * 5 * 2
    (primary["tmp"] / "corpus" / "pub-a.docx").write_bytes(b"edited since the primary run")
    with pytest.raises(sweep.ScheduleMismatchError, match="pub-a"):
        baselines.run_baseline_sweep(run_root, primary["tmp"] / "b2", "haiku")


def test_a_family_with_no_baseline_chain_fails_loudly(primary):
    primary["state"]["usable"] = False
    run_root = primary["make"](False)
    with pytest.raises(ValueError, match="no baseline chains"):
        baselines.run_baseline_sweep(run_root, primary["tmp"] / "b", "haiku")
    assert baselines.main(["--run-root", str(run_root), "--baseline-run-root", str(primary["tmp"] / "b")]) == 2


def test_table_structural_override_mapping():
    entry = {"table_anchor": _anchor("T", 3)}
    assert baselines._anchor_override_for_family("table_structural", entry)["anchor_para_id"] == "T3"
    assert baselines.FAMILIES == baselines.FIVE_FAMILIES


def test_baseline_sweep_auto_retries_and_resumes_after_a_usage_cap(primary, monkeypatch):
    """Rate-limit handling (review finding: the baseline sweep was not wired
    into usage_cap at all): a usage_limit trip on one chain pauses the round
    and every other in-flight chain aborts via the fresh per-round
    CircuitBreaker, then the next round retries only those chains and the
    sweep finishes within this one call -- no relaunch, no permanent trip."""
    run_root = primary["make"](False)
    tripped_once = {"done": False}

    def flaky_run_chain(family, doc_label, docx_path, arm, k, model, run_root_arg, **kwargs):
        primary["state"]["chains"].append({"family": family, "doc_label": doc_label, "arm": arm})
        breaker = kwargs["circuit_breaker"]
        pc = kwargs["pause_controller"]
        if breaker.is_open:
            raise baselines.CircuitOpenError("open")
        if not tripped_once["done"]:
            tripped_once["done"] = True
            signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": ["api_error_status 429"]}
            breaker.trip(signature, f"{doc_label}/{family}/{arm}")
            if pc is not None:
                pc.note_trial({"claude_json_result": {"result": "You've hit your usage limit."}}, signature,
                              f"{doc_label}/{family}/{arm}")
            return {"chain_id": f"{doc_label}-{family}-{arm}-k1", "doc_label": doc_label, "family": family,
                    "arm": arm, "status": "infra_blocked", "infra_signature": signature, "pairs": []}
        return {"chain_id": f"{doc_label}-{family}-{arm}-k1", "doc_label": doc_label, "family": family,
                "arm": arm, "status": "completed", "pairs": []}

    monkeypatch.setattr(baselines, "run_chain", flaky_run_chain)
    sleeps: list[float] = []
    pause_controller = baselines.UsagePauseController(sleep=sleeps.append)
    out = baselines.run_baseline_sweep(
        run_root, primary["tmp"] / "b-cap", "haiku", max_workers=1, pause_controller=pause_controller,
    )
    assert len(out["usage_cap_rounds"]) == 2
    assert out["usage_cap_rounds"][0]["usage_cap_round"] is True
    assert out["usage_cap_rounds"][1]["usage_cap_round"] is False
    assert not out["circuit_breaker"]["open"]
    assert all(c["status"] == "completed" for c in out["chains_summary"])
    assert out["chain_count"] == 2 * 2 * 5 * 2  # every chain still present in the final result
    assert sleeps  # the round actually waited via the (faked) backoff, not skipped
    assert pause_controller.is_paused is False


# ---------------------------------------------------------------------------
# --provenance-json (wf4_report.txt section 1.2, gap 2).
# ---------------------------------------------------------------------------

_PROVENANCE_KEYS = {
    "schema", "argv", "command_line", "repo_git_commit", "meridian_docs", "model",
    "documents_manifest_path", "documents_manifest_sha256", "schedule_path", "schedule_sha256",
    "hostname", "python_version", "start_time_utc", "end_time_utc", "exit_status",
}


def test_real_run_writes_provenance_with_the_primary_schedule_sha_before_dispatch(primary, monkeypatch):
    run_root = primary["make"](False)
    prov = primary["tmp"] / "logs" / "provenance-baselines.json"
    seen: dict = {}

    def spying_run_chain(family, doc_label, docx_path, arm, k, model, run_root_arg, **kwargs):
        if not seen:
            seen["exists"] = prov.is_file()
            if prov.is_file():
                seen["record"] = json.loads(prov.read_text(encoding="utf-8"))
        primary["state"]["chains"].append({"family": family, "doc_label": doc_label, "arm": arm})
        return {"chain_id": f"{doc_label}-{family}-{arm}-k1", "doc_label": doc_label, "family": family, "arm": arm,
                "status": "completed", "pairs": []}

    monkeypatch.setattr(baselines, "run_chain", spying_run_chain)
    code = baselines.main([
        "--run-root", str(run_root), "--baseline-run-root", str(primary["tmp"] / "b-prov"),
        "--model", "claude-sonnet-5", "--max-workers", "1", "--documents-manifest", str(primary["manifest"]),
        "--provenance-json", str(prov),
    ])
    assert code == 0
    assert seen["exists"] is True  # written before any baseline chain dispatched
    start_record = seen["record"]
    assert set(start_record) == _PROVENANCE_KEYS
    assert start_record["model"] == "claude-sonnet-5"
    assert start_record["documents_manifest_path"] == str(primary["manifest"])
    assert start_record["documents_manifest_sha256"] == hashlib.sha256(primary["manifest"].read_bytes()).hexdigest()
    meta = json.loads((run_root / sweep.SCHEDULE_META_NAME).read_text())
    assert start_record["schedule_sha256"] == meta["anchor_schedules_sha256"]
    assert start_record["schedule_path"] == str(run_root / sweep.SCHEDULE_NAME)
    assert start_record["end_time_utc"] is None and start_record["exit_status"] is None

    final_record = json.loads(prov.read_text(encoding="utf-8"))
    assert final_record["exit_status"] == 0
    assert final_record["end_time_utc"] is not None


def test_a_refused_baseline_start_writes_no_provenance_when_none_existed(primary):
    """No primary schedule at all: run_baseline_sweep raises before
    load_verified_schedule even returns, so write_provenance_start is never
    reached -- and write_provenance_end is a no-op with nothing to update."""
    empty_root = primary["tmp"] / "no-primary-2"
    empty_root.mkdir()
    prov = primary["tmp"] / "never.json"
    code = baselines.main(["--run-root", str(empty_root), "--baseline-run-root", str(primary["tmp"] / "bx"),
                           "--provenance-json", str(prov)])
    assert code == 2
    assert not prov.exists()
