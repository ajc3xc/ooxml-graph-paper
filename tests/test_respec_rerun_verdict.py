"""Tests for tools/respec_rerun_verdict.py (PAPER-S25 section 7, P-R5).

Fixtures are hand-built statistics dicts matching the schema
compute_respec_cascade_statistics.py produces PLUS the `document_level`
(section 6.3), `drop_difference` (section 6.6) and `public_documents_only`
(section 6.7) fields that prerequisite P-R4 has not yet added -- see the
module docstring of respec_rerun_verdict.py for why the verdict script
requires them anyway (fail loudly, do not guess) and one test below
(`test_missing_document_level_fails_loudly`) exercises exactly today's real
gap: a statistics file with `chain_level` but no `document_level`.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import respec_rerun_verdict as v  # noqa: E402

MODES = ("fail_graded_prefreeze", "fail", "exclude", "package_invalid_only")


def _node(diff, p, exact=True, n_clusters=8):
    return {"observed_mean_diff": diff, "p_value": p, "exact": exact, "n_clusters": n_clusters}


def _measure(chain_diff, chain_p, doc_diff, doc_p, exact=True):
    return {
        "chain_level": _node(chain_diff, chain_p, exact=exact),
        "document_level": _node(doc_diff, doc_p, exact=exact),
    }


def _full_stats(
    mode,
    *,
    blocked_policy="fail",
    control_drop=None,
    treatment_drop=None,
    direct=None,
    drop_difference=None,
    keep_survival_chain=None,
    keep_survival_document=None,
    public_control_drop_diff=-0.05,
    public_direct_diff=-0.05,
    render_gate_timeouts=None,
    unregradable=None,
):
    """A statistics dict that satisfies every section 7 CONFIRMING condition
    by default; individual tests override just the measure(s) they need to
    push toward DISCONFIRMING or INCONCLUSIVE."""
    control_drop = control_drop if control_drop is not None else _measure(-0.15, 0.01, -0.15, 0.02)
    treatment_drop = treatment_drop if treatment_drop is not None else _measure(-0.02, 0.5, -0.02, 0.5)
    direct = direct if direct is not None else _measure(-0.20, 0.01, -0.20, 0.02)
    drop_difference = drop_difference if drop_difference is not None else _measure(0.13, 0.01, 0.13, 0.02)
    keep_survival_chain = keep_survival_chain if keep_survival_chain is not None else _node(-0.10, 0.01)
    keep_survival_document = keep_survival_document if keep_survival_document is not None else _node(-0.10, 0.02)
    stats = {
        "frozen_chain_mode": mode,
        "blocked_policy": blocked_policy,
        "render_gate_timeouts": render_gate_timeouts if render_gate_timeouts is not None else [],
        "confirm_disconfirm": {
            "pooled": {
                "control_drop": control_drop,
                "treatment_drop": treatment_drop,
                "direct_control_vs_treatment_phase3": direct,
                "drop_difference": drop_difference,
            },
            "keep_survival_significance_chain_level": keep_survival_chain,
            "keep_survival_significance_document_level": keep_survival_document,
            "public_documents_only": {
                "control_drop": {"observed_mean_diff": public_control_drop_diff},
                "direct_control_vs_treatment_phase3": {"observed_mean_diff": public_direct_diff},
            },
        },
    }
    if unregradable is not None:
        stats["unregradable_grader_exception_stubs"] = unregradable
    return stats


def _minimal_stats(mode, blocked_policy="fail"):
    return {"frozen_chain_mode": mode, "blocked_policy": blocked_policy}


def _write(stats_dir: Path, mode: str, stats: dict) -> None:
    (stats_dir / f"respec-rerun-v1-statistics-{mode}.json").write_text(json.dumps(stats), encoding="utf-8")


def _write_all_modes(stats_dir: Path, primary_stats: dict, exclude_stats: dict | None = None) -> None:
    _write(stats_dir, "fail_graded_prefreeze", primary_stats)
    _write(stats_dir, "exclude", exclude_stats if exclude_stats is not None else _minimal_stats("exclude"))
    _write(stats_dir, "fail", _minimal_stats("fail"))
    _write(stats_dir, "package_invalid_only", _minimal_stats("package_invalid_only"))


# ---------------------------------------------------------------------------
# The three verdict outcomes
# ---------------------------------------------------------------------------

def test_confirming_verdict_robust_to_freeze_scoring(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats("fail_graded_prefreeze")
    exclude = _full_stats("exclude")  # also satisfies C1-C4, C6
    _write_all_modes(stats_dir, primary, exclude)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "CONFIRMING"
    assert report["sub_label"] is None
    assert report["freeze_scoring_robustness_label"] == "robust_to_freeze_scoring"
    assert all(report["conditions"][k] for k in (
        "C1_control_drop", "C2_direct", "C3_keep_survival", "C4_drop_difference",
        "C5_grader_and_render_gate_bounds", "C6_public_documents_only",
    ))
    assert not any(report["conditions"][k] for k in ("D1_direct_not_significant_or_non_positive", "D2_both_drops_null", "D3_treatment_drop_at_least_control_drop"))


def test_confirming_verdict_dependent_on_freeze_scoring(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats("fail_graded_prefreeze")
    # Under `exclude`, C1 (control_drop_pp >= 10) no longer holds.
    exclude = _full_stats("exclude", control_drop=_measure(-0.03, 0.4, -0.03, 0.4))
    _write_all_modes(stats_dir, primary, exclude)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "CONFIRMING"
    assert report["freeze_scoring_robustness_label"] == "dependent_on_freeze_scoring"


def test_disconfirming_contrary_sublabel_when_direct_effect_points_the_wrong_way(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    # direct_pp <= 0 (observed_mean_diff positive) -> D1 holds, and "contrary".
    primary = _full_stats("fail_graded_prefreeze", direct=_measure(0.10, 0.01, 0.10, 0.02))
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "DISCONFIRMING"
    assert report["sub_label"] == "contrary"
    assert report["conditions"]["D1_direct_not_significant_or_non_positive"] is True
    assert report["freeze_scoring_robustness_label"] == "not_applicable"


def test_disconfirming_not_detected_sublabel_when_effect_is_simply_absent(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    # Both drops small and non-significant (D2), point estimates still point
    # the right way (not "contrary"): control_drop_pp(6) > treatment_drop_pp(5).
    primary = _full_stats(
        "fail_graded_prefreeze",
        control_drop=_measure(-0.06, 0.30, -0.06, 0.30),
        treatment_drop=_measure(-0.05, 0.30, -0.05, 0.30),
        direct=_measure(-0.08, 0.20, -0.08, 0.20),
    )
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "DISCONFIRMING"
    assert report["sub_label"] == "not_detected_at_D=8"
    assert report["conditions"]["D2_both_drops_null"] is True


def test_inconclusive_when_one_confirming_condition_fails(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    # Not disconfirming, but drop_difference_pp < 10 -> C4 fails.
    primary = _full_stats("fail_graded_prefreeze", drop_difference=_measure(0.05, 0.01, 0.05, 0.02))
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "INCONCLUSIVE"
    assert report["conditions"]["C4_drop_difference"] is False
    assert report["freeze_scoring_robustness_label"] == "not_applicable"


# ---------------------------------------------------------------------------
# Fail loudly, don't guess
# ---------------------------------------------------------------------------

def test_missing_document_level_fails_loudly(tmp_path, capsys):
    """Today's real gap (P-R4 not yet implemented): chain_level is present,
    document_level is not. The script must refuse to compute a verdict, not
    silently fall back to the chain-level p-value alone."""
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats("fail_graded_prefreeze")
    del primary["confirm_disconfirm"]["pooled"]["control_drop"]["document_level"]
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    rc = v.main(["--statistics-dir", str(stats_dir), "--out", str(out)])

    assert rc == 2
    assert not out.exists()
    err = capsys.readouterr().err
    assert "document_level" in err
    assert "P-R4" in err


def test_missing_statistics_file_for_a_mode_fails_loudly(tmp_path, capsys):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    _write(stats_dir, "fail_graded_prefreeze", _full_stats("fail_graded_prefreeze"))
    _write(stats_dir, "exclude", _minimal_stats("exclude"))
    _write(stats_dir, "fail", _minimal_stats("fail"))
    # package_invalid_only file missing entirely.
    out = tmp_path / "verdict.json"

    rc = v.main(["--statistics-dir", str(stats_dir), "--out", str(out)])

    assert rc == 2
    assert not out.exists()
    assert "package_invalid_only" in capsys.readouterr().err


def test_render_gate_timeout_blocks_c5_instead_of_assuming_it_holds(tmp_path, capsys):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats(
        "fail_graded_prefreeze",
        render_gate_timeouts=[{"doc_label": "d1", "arm": "treatment", "chain_broken_at_step": "3.2"}],
    )
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    rc = v.main(["--statistics-dir", str(stats_dir), "--out", str(out)])

    assert rc == 2
    assert not out.exists()
    assert "render-gate" in capsys.readouterr().err


def test_unregradable_grader_exception_stub_blocks_c5(tmp_path, capsys):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats("fail_graded_prefreeze", unregradable=2)
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    rc = v.main(["--statistics-dir", str(stats_dir), "--out", str(out)])

    assert rc == 2
    assert "grader-exception" in capsys.readouterr().err


def test_wrong_frozen_chain_mode_recorded_in_file_is_caught(tmp_path, capsys):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats("fail_graded_prefreeze")
    primary["frozen_chain_mode"] = "fail"  # mislabeled
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    rc = v.main(["--statistics-dir", str(stats_dir), "--out", str(out)])

    assert rc == 2
    assert "frozen_chain_mode" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Missing-but-OPTIONAL fields must not crash
# ---------------------------------------------------------------------------

def test_missing_optional_fields_do_not_crash(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats("fail_graded_prefreeze")
    # "exact" and "n_clusters" are descriptive, not required by the rule.
    del primary["confirm_disconfirm"]["pooled"]["control_drop"]["chain_level"]["exact"]
    del primary["confirm_disconfirm"]["pooled"]["control_drop"]["chain_level"]["n_clusters"]
    del primary["confirm_disconfirm"]["pooled"]["direct_control_vs_treatment_phase3"]["document_level"]["n_clusters"]
    # unregradable_grader_exception_stubs is simply absent (never disclosed).
    assert "unregradable_grader_exception_stubs" not in primary
    _write_all_modes(stats_dir, primary, _full_stats("exclude"))
    out = tmp_path / "verdict.json"

    rc = v.main(["--statistics-dir", str(stats_dir), "--out", str(out)])

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "CONFIRMING"
    assert report["numbers"]["c5_detail"]["unregradable_grader_exception_stubs"] == 0


def test_non_exact_p_value_is_reported_as_a_deviation_not_a_failure(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats(
        "fail_graded_prefreeze",
        control_drop=_measure(-0.15, 0.01, -0.15, 0.02, exact=False),
    )
    _write_all_modes(stats_dir, primary, _full_stats("exclude"))
    out = tmp_path / "verdict.json"

    rc = v.main(["--statistics-dir", str(stats_dir), "--out", str(out)])

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "CONFIRMING"
    assert any("control_drop" in d for d in report["deviations"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
