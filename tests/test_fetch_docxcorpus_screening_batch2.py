"""Regression tests for PAPER-S6 round-2 acquisition batch selection."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import fetch_docxcorpus_screening_batch2 as batch2  # noqa: E402


def test_select_batch_excludes_already_sampled_and_batch500(tmp_path: Path, monkeypatch) -> None:
    candidates = [
        {"id": f"tech-{i}", "topic": "technology", "type": "technical", "url": f"https://x/{i}"}
        for i in range(5)
    ] + [
        {"id": f"edu-{i}", "topic": "education", "type": "policies", "url": f"https://x/e{i}"}
        for i in range(5)
    ]
    sample90 = [{"id": "tech-0"}]
    batch500 = {"entries": [{"id": "tech-1"}, {"id": "edu-0"}]}

    candidates_path = tmp_path / "candidates.json"
    sample90_path = tmp_path / "sample90.json"
    batch500_path = tmp_path / "batch500.json"
    candidates_path.write_text(json.dumps(candidates))
    sample90_path.write_text(json.dumps(sample90))
    batch500_path.write_text(json.dumps(batch500))

    monkeypatch.setattr(batch2, "_CANDIDATES_PATH", candidates_path)
    monkeypatch.setattr(batch2, "_SAMPLE90_PATH", sample90_path)
    monkeypatch.setattr(batch2, "_BATCH500_MANIFEST_PATH", batch500_path)
    monkeypatch.setattr(batch2, "_TOPIC_QUOTA", 10)

    selected, quotas = batch2._select_batch()

    selected_ids = {r["id"] for r in selected}
    assert "tech-0" not in selected_ids
    assert "tech-1" not in selected_ids
    assert "edu-0" not in selected_ids
    assert selected_ids == {"tech-2", "tech-3", "tech-4", "edu-1", "edu-2", "edu-3", "edu-4"}
    assert quotas == {"technology": 3, "education": 4}


def test_select_batch_caps_at_topic_quota(tmp_path: Path, monkeypatch) -> None:
    candidates = [{"id": f"g-{i}", "topic": "government", "type": "policies", "url": "x"} for i in range(50)]
    candidates_path = tmp_path / "candidates.json"
    sample90_path = tmp_path / "sample90.json"
    batch500_path = tmp_path / "batch500.json"
    candidates_path.write_text(json.dumps(candidates))
    sample90_path.write_text(json.dumps([]))
    batch500_path.write_text(json.dumps({"entries": []}))

    monkeypatch.setattr(batch2, "_CANDIDATES_PATH", candidates_path)
    monkeypatch.setattr(batch2, "_SAMPLE90_PATH", sample90_path)
    monkeypatch.setattr(batch2, "_BATCH500_MANIFEST_PATH", batch500_path)
    monkeypatch.setattr(batch2, "_TOPIC_QUOTA", 10)

    selected, quotas = batch2._select_batch()

    assert len(selected) == 10
    assert quotas == {"government": 10}


def test_select_batch_is_deterministic_given_fixed_seed(tmp_path: Path, monkeypatch) -> None:
    candidates = [{"id": f"g-{i}", "topic": "government", "type": "policies", "url": "x"} for i in range(50)]
    candidates_path = tmp_path / "candidates.json"
    sample90_path = tmp_path / "sample90.json"
    batch500_path = tmp_path / "batch500.json"
    candidates_path.write_text(json.dumps(candidates))
    sample90_path.write_text(json.dumps([]))
    batch500_path.write_text(json.dumps({"entries": []}))

    monkeypatch.setattr(batch2, "_CANDIDATES_PATH", candidates_path)
    monkeypatch.setattr(batch2, "_SAMPLE90_PATH", sample90_path)
    monkeypatch.setattr(batch2, "_BATCH500_MANIFEST_PATH", batch500_path)
    monkeypatch.setattr(batch2, "_TOPIC_QUOTA", 10)

    first, _ = batch2._select_batch()
    second, _ = batch2._select_batch()

    assert [r["id"] for r in first] == [r["id"] for r in second]
