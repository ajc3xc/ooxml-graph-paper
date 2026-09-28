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
    """One measure's {chain_level, document_level} pair. _full_stats fans
    these into the REAL sibling-grouped shape compute_respec_cascade_
    statistics.py actually produces: confirm_disconfirm.pooled.chain_level/
    document_level each hold every measure's test as a sibling dict (see
    _section7_primary_tests / _flatten_section7_tests), not nested inside
    each measure the way this helper's own return value is shaped -- that
    shape only exists transiently here, as a convenience for building the
    three measures' tests together before _full_stats regroups them."""
    return {
        "chain_level": _node(chain_diff, chain_p, exact=exact),
        "document_level": _node(doc_diff, doc_p, exact=exact),
    }


def _public_documents_only_headline(
    *,
    control_drop=None,
    direct=None,
    keep_survival=None,
    drop_difference=None,
    public_documents=("s25pub_aaa000", "s25pub_bbb111"),
):
    """Amendment 1 (`docs/paper-s25-respec-cascade-rerun-protocol-v1-amendment-1.md`,
    section 2, AD-2)'s shape for `confirm_disconfirm.public_documents_only`,
    verified there against `compute_respec_cascade_statistics.py`'s
    `compute_respec_cascade_tiers` (the `if public_doc_labels:` block): flat
    `control_drop`/`direct_control_vs_treatment_phase3`/
    `keep_survival_significance` (as-run Monte Carlo, kept for continuity --
    what pre-amendment `_extract_public_only` reads) PLUS `chain_level` and
    `document_level` siblings, each holding all three measures, PLUS
    `difference_in_drops` in the same `{chain_level, document_level,
    drop_difference_pp}` shape as the pooled `confirm_disconfirm.
    difference_in_drops`. Defaults are confirming-shaped and agree in sign
    and (deliberately) exact value with `_full_stats`'s own defaults, so a
    test that uses both untouched exercises "headline present, same
    everything" cleanly; individual tests override just the piece(s) they
    need."""
    control_drop = control_drop if control_drop is not None else _measure(-0.15, 0.01, -0.15, 0.02)
    direct = direct if direct is not None else _measure(-0.20, 0.01, -0.20, 0.02)
    keep_survival = keep_survival if keep_survival is not None else _measure(-0.10, 0.01, -0.10, 0.02)
    drop_difference = drop_difference if drop_difference is not None else _measure(0.13, 0.01, 0.13, 0.02)
    return {
        "note": "protocol section 6.7; amendment 1 section 2 (AD-2)",
        "public_documents": list(public_documents),
        "n_public_documents": len(public_documents),
        "control_drop": {"observed_mean_diff": control_drop["chain_level"]["observed_mean_diff"]},
        "direct_control_vs_treatment_phase3": {"observed_mean_diff": direct["chain_level"]["observed_mean_diff"]},
        "keep_survival_significance": {"observed_mean_diff": keep_survival["chain_level"]["observed_mean_diff"]},
        "chain_level": {
            "control_drop": control_drop["chain_level"],
            "direct_control_vs_treatment_phase3": direct["chain_level"],
            "keep_survival_significance": keep_survival["chain_level"],
        },
        "document_level": {
            "control_drop": control_drop["document_level"],
            "direct_control_vs_treatment_phase3": direct["document_level"],
            "keep_survival_significance": keep_survival["document_level"],
        },
        "difference_in_drops": {
            "chain_level": drop_difference["chain_level"],
            "document_level": drop_difference["document_level"],
            "drop_difference_pp": 100.0 * drop_difference["chain_level"]["observed_mean_diff"],
        },
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
    public_documents_only_override=None,
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
                "chain_level": {
                    "control_drop": control_drop["chain_level"],
                    "treatment_drop": treatment_drop["chain_level"],
                    "direct_control_vs_treatment_phase3": direct["chain_level"],
                },
                "document_level": {
                    "control_drop": control_drop["document_level"],
                    "treatment_drop": treatment_drop["document_level"],
                    "direct_control_vs_treatment_phase3": direct["document_level"],
                },
            },
            "difference_in_drops": {
                "chain_level": drop_difference["chain_level"],
                "document_level": drop_difference["document_level"],
            },
            "keep_survival_significance_chain_level": keep_survival_chain,
            "keep_survival_significance_document_level": keep_survival_document,
            "public_documents_only": (
                public_documents_only_override
                if public_documents_only_override is not None
                else {
                    "control_drop": {"observed_mean_diff": public_control_drop_diff},
                    "direct_control_vs_treatment_phase3": {"observed_mean_diff": public_direct_diff},
                }
            ),
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
    del primary["confirm_disconfirm"]["pooled"]["document_level"]["control_drop"]
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
    del primary["confirm_disconfirm"]["pooled"]["chain_level"]["control_drop"]["exact"]
    del primary["confirm_disconfirm"]["pooled"]["chain_level"]["control_drop"]["n_clusters"]
    del primary["confirm_disconfirm"]["pooled"]["document_level"]["direct_control_vs_treatment_phase3"]["n_clusters"]
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


# ---------------------------------------------------------------------------
# Amendment 1 (docs/paper-s25-respec-cascade-rerun-protocol-v1-amendment-1.md,
# section 2, AD-2): confirm_disconfirm.public_documents_only becomes the
# headline basis for C1-C4 once it carries the chain_level/document_level
# shape; falls back to the pooled basis otherwise; C6 inverts into a
# non-gating robustness note; the pooled analysis is reported in full as a
# secondary/sensitivity block.
# ---------------------------------------------------------------------------

def test_pooled_basis_used_and_no_secondary_block_when_headline_shape_absent(tmp_path):
    """Backward compatibility (item 2 of the amendment task): a statistics
    file whose public_documents_only lacks the chain_level/document_level
    shape -- exactly today's other fixtures in this file, and the real D=4
    statistics files, which predate prerequisite P-R4 -- must verify/print
    exactly as before this amendment: pooled basis, no secondary block, C6
    still a hard gate."""
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    primary = _full_stats("fail_graded_prefreeze")  # legacy flat public_documents_only (no chain_level/document_level)
    _write_all_modes(stats_dir, primary, _full_stats("exclude"))
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["headline_basis"] == "pooled"
    assert report["numbers"]["secondary_pooled_analysis"] is None
    assert report["robustness_note"] is None
    assert report["verdict"] == "CONFIRMING"
    assert report["conditions"]["C6_public_documents_only"] is True
    assert report["conditions"]["C6_is_hard_gate"] is True


def test_headline_public_documents_only_governs_verdict_when_present(tmp_path):
    """Amendment section 2: once public_documents_only carries the
    chain_level/document_level shape, C1-C4 come from it, not from
    confirm_disconfirm.pooled -- even when the pooled numbers alone (still
    fully computed and reported as the secondary/sensitivity analysis) would
    themselves be CONFIRMING. Here the headline's control_drop_pp (3pp) is
    too small for C1, while the pooled control_drop_pp (15pp, _full_stats's
    default) is not."""
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    headline = _public_documents_only_headline(control_drop=_measure(-0.03, 0.01, -0.03, 0.02))
    primary = _full_stats("fail_graded_prefreeze", public_documents_only_override=headline)
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["headline_basis"] == "public_documents_only"
    assert report["verdict"] == "INCONCLUSIVE"
    assert report["conditions"]["C1_control_drop"] is False
    assert report["numbers"]["control_drop"]["pp"] == pytest.approx(3.0)

    secondary = report["numbers"]["secondary_pooled_analysis"]
    assert secondary is not None
    assert secondary["verdict"] == "CONFIRMING"
    assert secondary["conditions"]["C1_control_drop"] is True
    assert secondary["numbers"]["control_drop"]["pp"] == pytest.approx(15.0)


def test_c6_robustness_note_same_sign_when_pooled_and_headline_agree(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    # Defaults agree in sign (and value) between pooled and headline.
    headline = _public_documents_only_headline()
    primary = _full_stats("fail_graded_prefreeze", public_documents_only_override=headline)
    exclude = _full_stats("exclude", public_documents_only_override=headline)  # also CONFIRMING-shaped
    _write_all_modes(stats_dir, primary, exclude)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["headline_basis"] == "public_documents_only"
    assert report["verdict"] == "CONFIRMING"
    note = report["robustness_note"]
    assert note["control_drop_same_sign"] is True
    assert note["direct_same_sign"] is True
    assert note["same_sign_overall"] is True
    assert report["conditions"]["C6_is_hard_gate"] is False


def test_c6_robustness_note_flags_opposite_sign_between_pooled_and_headline(tmp_path):
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    # Headline (public-only) direct effect points the confirming way, but
    # the pooled secondary analysis's direct effect points the opposite way
    # (observed_mean_diff positive -> direct_pp <= 0).
    headline = _public_documents_only_headline()
    primary = _full_stats(
        "fail_graded_prefreeze",
        direct=_measure(0.10, 0.01, 0.10, 0.02),
        public_documents_only_override=headline,
    )
    _write_all_modes(stats_dir, primary)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["headline_basis"] == "public_documents_only"
    note = report["robustness_note"]
    assert note["direct_same_sign"] is False
    assert note["same_sign_overall"] is False
    # A contrary pooled signal still drives the pooled-gated D1-D3 verdict.
    assert report["verdict"] == "DISCONFIRMING"
    assert report["sub_label"] == "contrary"


def test_freeze_scoring_robustness_label_ignores_c6_in_headline_mode(tmp_path):
    """robustness_label() must not treat C6 as a gate once it has been
    demoted to a robustness note (amendment section 2) -- otherwise a
    CONFIRMING, fully robust run would be mislabelled dependent_on_freeze_
    scoring merely because C6 is no longer a plain boolean gate."""
    stats_dir = tmp_path / "statistics"
    stats_dir.mkdir()
    headline = _public_documents_only_headline()
    primary = _full_stats("fail_graded_prefreeze", public_documents_only_override=headline)
    exclude = _full_stats("exclude", public_documents_only_override=headline)  # also satisfies C1-C4
    _write_all_modes(stats_dir, primary, exclude)
    out = tmp_path / "verdict.json"

    assert v.main(["--statistics-dir", str(stats_dir), "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "CONFIRMING"
    assert report["freeze_scoring_robustness_label"] == "robust_to_freeze_scoring"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
