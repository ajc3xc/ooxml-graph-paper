"""Unit tests for tools/run_comment_targeting_sweep.py (PAPER-S24).

No real subprocess or real corpus file is touched: `run_comment_targeting_
chain` (the sweep's own per-(document, arm) unit of work) is monkeypatched,
mirroring the same convention used for run_trial in
tests/test_run_comment_targeting_family.py and
tests/test_run_paper_s7_benchmark.py.

Run with: pixi run python -m pytest tests/test_run_comment_targeting_sweep.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import run_comment_targeting_sweep as rcts  # noqa: E402
from run_comment_targeting_sweep import (  # noqa: E402
    _per_position_summary,
    load_frozen_schedules,
    run_primary_sweep,
)


def test_load_frozen_schedules_extracts_the_documents_dict(tmp_path: Path):
    payload = {
        "schema": "paper-s24-comment-targeting-schedule-v1",
        "documents": {
            "doc-a": {"usable_k": 4},
            "doc-b": {"usable_k": 0},
        },
    }
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    documents = load_frozen_schedules(path)

    assert documents == payload["documents"]


def test_per_position_summary_aggregates_pass_rate_across_chains():
    chain_results = [
        {
            "arm": "treatment",
            "chain_grade": {"per_position": [
                {"condition": "ambiguous", "chain_position": 1, "step_pass": True},
                {"condition": "unique", "chain_position": 1, "step_pass": True},
            ]},
        },
        {
            "arm": "treatment",
            "chain_grade": {"per_position": [
                {"condition": "ambiguous", "chain_position": 1, "step_pass": False},
                {"condition": "unique", "chain_position": 1, "step_pass": True},
            ]},
        },
        {"arm": "control", "chain_grade": None},  # frozen before any step graded -- must not crash
    ]

    summary = _per_position_summary(chain_results)

    assert summary["treatment|ambiguous|position1"]["pass"] == 1
    assert summary["treatment|ambiguous|position1"]["total"] == 2
    assert summary["treatment|ambiguous|position1"]["pass_rate"] == 0.5
    assert summary["treatment|unique|position1"]["pass_rate"] == 1.0
    assert "control|ambiguous|position1" not in summary


def test_run_primary_sweep_excludes_documents_with_zero_usable_k_or_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps({
        "schema": "paper-s24-comment-targeting-schedule-v1",
        "documents": {
            "doc-usable": {"usable_k": 2, "ambiguous_targets": [], "unique_targets": []},
            "doc-empty": {"usable_k": 0},
            "doc-error": {"error": "corpus file not found"},
        },
    }), encoding="utf-8")

    monkeypatch.setattr(rcts, "REAL_DOCUMENTS", {"doc-usable": tmp_path / "doc-usable.docx"})
    calls: list[tuple] = []

    def fake_run_chain(doc_label, docx_path, arm, model, run_root, schedule, *, word_receipts_enabled):
        calls.append((doc_label, arm))
        return {
            "chain_id": f"{doc_label}-comment_targeting-{arm}", "doc_label": doc_label, "arm": arm,
            "status": "completed", "steps_run": 4, "round_trip_count": 4,
            "chain_grade": {"chain_pass": True, "per_position": []},
        }

    monkeypatch.setattr(rcts, "run_comment_targeting_chain", fake_run_chain)

    manifest = run_primary_sweep(tmp_path / "run-root", "sonnet", schedule_path, max_workers=2)

    assert manifest["chain_count"] == 2  # doc-usable x 2 arms
    excluded_labels = {e["doc_label"] for e in manifest["excluded_documents"]}
    assert excluded_labels == {"doc-empty", "doc-error"}
    assert {(c[0], c[1]) for c in calls} == {("doc-usable", "control"), ("doc-usable", "treatment")}
    assert all(c["chain_pass"] is True for c in manifest["chains_summary"])


def test_run_primary_sweep_degrades_a_raised_exception_to_harness_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps({
        "documents": {"doc-a": {"usable_k": 1, "ambiguous_targets": [{}], "unique_targets": [{}]}},
    }), encoding="utf-8")
    monkeypatch.setattr(rcts, "REAL_DOCUMENTS", {"doc-a": tmp_path / "doc-a.docx"})

    def raising_run_chain(*args, **kwargs):
        raise RuntimeError("simulated harness crash")

    monkeypatch.setattr(rcts, "run_comment_targeting_chain", raising_run_chain)

    manifest = run_primary_sweep(tmp_path / "run-root", "sonnet", schedule_path, max_workers=2)

    assert manifest["chain_count"] == 2
    assert all(c["status"] == "harness_exception" for c in manifest["chains_summary"])


def test_run_primary_sweep_writes_manifest_and_schedule_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps({"documents": {}}), encoding="utf-8")
    monkeypatch.setattr(rcts, "REAL_DOCUMENTS", {})

    run_root = tmp_path / "run-root"
    run_primary_sweep(run_root, "sonnet", schedule_path, max_workers=1)

    assert (run_root / "sweep-manifest.json").is_file()
    assert (run_root / "target-schedules.json").is_file()
