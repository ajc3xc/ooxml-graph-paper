import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import compute_respec_cascade_statistics as r  # noqa: E402

GRADED = {"phase1_pass": True}


def _chain(status, phase3):
    return {"doc_label": "doc__anchor1", "arm": "control", "status": status,
            "phase1_result": GRADED, "phase2_result": {"phase2_pass": True}, "phase3_result": phase3}


def test_grader_exception_is_excluded_under_its_own_reason_not_the_chain_status():
    crashed = _chain("completed_with_failure", {"status": "grading_raised_exception", "reason": "KeyError: 'x'"})
    assert r._phase3_composite_outcome(crashed) is None
    _, excluded = r._group_by_document([crashed], r._phase3_composite_outcome, "phase3_composite")
    assert excluded[0]["reason"] == "phase3_grading_raised_exception: KeyError: 'x'"


def test_graded_failure_is_scored_zero_not_excluded():
    failed = _chain("completed_with_failure", {"phase3_pass": False})
    grouped, excluded = r._group_by_document([failed], r._phase3_composite_outcome, "phase3_composite")
    assert excluded == [] and grouped["control"] == {"doc": [0.0]}


def test_frozen_chain_is_scored_zero():
    frozen = {"doc_label": "doc__anchor2", "arm": "control", "status": "chain_broken_at_step_2.1",
              "phase1_result": GRADED, "phase2_result": None, "phase3_result": None}
    assert r._phase3_composite_outcome(frozen) == 0.0
