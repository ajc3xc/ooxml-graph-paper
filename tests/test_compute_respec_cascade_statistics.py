import json
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


# ---------------------------------------------------------------------------
# Frozen-chain modes (2026-09-25)
# ---------------------------------------------------------------------------

KS_CLEAN = {"phase2_pass": True, "keep_survival": {"overall_status": "clean_keep_survival"}}


def _frozen_in_phase2():
    return {"doc_label": "doc__anchor2", "arm": "control", "status": "chain_broken_at_step_2.1",
            "phase1_result": GRADED, "phase2_result": None, "phase3_result": None}


def _frozen_in_phase3_new_format():
    # What the orchestrator writes since 2026-09-25: finished round trips graded.
    return {"doc_label": "doc__anchor3", "arm": "control", "status": "chain_broken_at_step_3.4-inverse",
            "freeze_cause": "anchor_reresolution_failed", "freeze_detail": "equation marker gone",
            "phase1_result": GRADED, "phase2_result": KS_CLEAN,
            "phase3_result": {"status": "frozen_before_checkpoint_c", "phase3_pass": False, "families": {
                "bibliography": {"verdict": "pass"}, "citation": {"verdict": "pass"},
                "section_reorder": {"verdict": "pass"}, "equation": {"verdict": "not_completed"},
                "caption": {"verdict": "not_run"}}}}


def test_default_frozen_chain_mode_is_the_protocols_fail():
    assert r.DEFAULT_FROZEN_CHAIN_MODE == "fail"


def test_fail_mode_scores_every_unreached_checkpoint_zero():
    frozen2, frozen3 = _frozen_in_phase2(), _frozen_in_phase3_new_format()
    for family in r.FAMILIES:
        assert r._phase3_family_outcome(frozen2, family, "fail") == 0.0
        # verdicts of round trips finished before the freeze are not Checkpoint-C outcomes
        assert r._phase3_family_outcome(frozen3, family, "fail") == 0.0
    assert r._phase2_keep_survival_outcome(frozen2, "fail") == 0.0
    # Checkpoint B was reached before the Phase-3 freeze: its real outcome counts
    assert r._phase2_keep_survival_outcome(frozen3, "fail") == 1.0
    assert r._phase3_composite_outcome(frozen3) == 0.0


def test_exclude_mode_reproduces_the_as_run_exclusion():
    frozen2, frozen3 = _frozen_in_phase2(), _frozen_in_phase3_new_format()
    for family in r.FAMILIES:
        assert r._phase3_family_outcome(frozen2, family, "exclude") is None
        assert r._phase3_family_outcome(frozen3, family, "exclude") is None
    assert r._phase2_keep_survival_outcome(frozen2, "exclude") is None
    assert r._phase2_keep_survival_outcome(frozen3, "exclude") == 1.0


def test_unknown_frozen_chain_mode_is_refused():
    import pytest
    with pytest.raises(ValueError):
        r._phase3_family_outcome(_frozen_in_phase2(), "citation", "impute")


def _completed(doc_label, arm, family_pass, ks_pass=True):
    return {"doc_label": doc_label, "arm": arm, "status": "completed" if family_pass else "completed_with_failure",
            "phase1_result": GRADED,
            "phase2_result": {"phase2_pass": ks_pass,
                              "keep_survival": {"overall_status": "clean_keep_survival" if ks_pass else "keep_violated"}},
            "phase3_result": {"phase3_pass": family_pass,
                              "families": {f: {"verdict": "pass" if family_pass else "fail"} for f in r.FAMILIES}}}


def _baseline(doc_label, arm):
    return {"doc_label": doc_label, "arm": arm, "status": "completed", "k_pairs": 1,
            "pairs": [{"forward": {"grading": {"verdict": "pass"}}, "inverse": {"grading": {"verdict": "pass"}}}]}


def _synthetic_run():
    labels = [f"doc{d}__anchor{a}" for d in range(3) for a in range(2)]
    cascade = [_completed(label, "treatment", True) for label in labels]
    cascade += [_completed(label, "control", True) for label in labels[:2]]
    cascade += [{**_frozen_in_phase2(), "doc_label": label} for label in labels[2:4]]
    cascade += [{**_frozen_in_phase3_new_format(), "doc_label": label} for label in labels[4:]]
    baseline = {f: [_baseline(label, arm) for label in labels for arm in ("control", "treatment")] for f in r.FAMILIES}
    return cascade, baseline


def test_report_records_mode_and_counts_frozen_chains_only_in_fail_mode():
    cascade, baseline = _synthetic_run()
    fail = r.compute_respec_cascade_tiers(cascade, baseline)
    exclude = r.compute_respec_cascade_tiers(cascade, baseline, frozen_chain_mode="exclude")
    assert fail["frozen_chain_mode"] == "fail" and exclude["frozen_chain_mode"] == "exclude"
    assert fail["confirm_disconfirm"]["pooled"]["control_drop"]["n_paired_anchor_sets"] == 30
    assert exclude["confirm_disconfirm"]["pooled"]["control_drop"]["n_paired_anchor_sets"] == 10
    assert len(fail["frozen_chains"]) == 4
    frozen3 = [c for c in fail["frozen_chains"] if c["status"].startswith("chain_broken_at_step_3")][0]
    assert frozen3["freeze_cause"] == "anchor_reresolution_failed"
    assert frozen3["phase3_verdicts_before_freeze"]["equation"] == "not_completed"


def test_chain_level_test_clusters_the_pooled_family_outcomes_by_chain():
    cascade, baseline = _synthetic_run()
    pooled = r.compute_respec_cascade_tiers(cascade, baseline)["confirm_disconfirm"]["pooled"]
    chain_level = pooled["chain_level"]["direct_control_vs_treatment_phase3"]
    naive_exact = pooled["observation_level_exact"]["direct_control_vs_treatment_phase3"]
    # 6 chains x 5 families: the chain-level test sees 6 units, 4 of them nonzero
    assert chain_level["n_clusters"] == 6 and chain_level["n_paired_observations"] == 30
    assert chain_level["exact"] is True and chain_level["p_value"] == 2 / 2 ** 4
    assert naive_exact["exact"] is True and naive_exact["p_value"] == 2 / 2 ** 20
    # the as-run field keeps its meaning (observation-level Monte Carlo) and its diff
    assert pooled["direct_control_vs_treatment_phase3"]["n_paired_anchor_sets"] == 30
    assert pooled["direct_control_vs_treatment_phase3"]["observed_mean_diff"] == chain_level["observed_mean_diff"]


def test_tier1_gains_an_exact_test_with_the_three_document_floor():
    cascade, baseline = _synthetic_run()
    report = r.compute_respec_cascade_tiers(cascade, baseline)
    tier1 = report["outcome_measures"]["a_phase3_composite_pass_rate"]["tier1_per_document_unweighted"]
    assert tier1["paired_significance_exact"]["p_value_floor"] == 0.25
    assert tier1["paired_significance_exact"]["p_value"] >= 0.25


def test_a_family_without_baseline_chains_fails_loudly():
    import pytest
    cascade, baseline = _synthetic_run()
    baseline["equation"] = []
    with pytest.raises(ValueError, match="equation"):
        r.compute_respec_cascade_tiers(cascade, baseline)
    # A six-family rotation over five-family baselines (no table_structural) is refused too.
    _, baseline = _synthetic_run()
    with pytest.raises(ValueError, match="table_structural"):
        r.compute_respec_cascade_tiers(cascade, baseline, families=r.SIX_FAMILIES)


def test_post_hoc_tests_are_labelled_in_the_output():
    cascade, baseline = _synthetic_run()
    report = r.compute_respec_cascade_tiers(cascade, baseline)
    status = report["analysis_status"]
    for field in ("confirm_disconfirm.*.chain_level", "confirm_disconfirm.*.observation_level_exact",
                  "confirm_disconfirm.whole_chain_composite_direct",
                  "outcome_measures.*.tier1_per_document_unweighted.paired_significance_exact"):
        assert status[field] == "post_hoc_for_2026-09-23_run"
    assert "section7_primary_test" not in report
    assert "post_hoc_for_2026-09-23_run" in report["section7_tests_note"]
    assert "package-invalid" in report["frozen_chain_mode_note"]


def test_shared_tiered_report_is_unchanged_for_other_callers():
    report = r._tiered_report({"a": [1.0], "b": [0.0]}, {"a": [1.0], "b": [1.0]})
    assert "paired_significance_exact" not in report["tier1_per_document_unweighted"]


# ---------------------------------------------------------------------------
# M1 (2026-09-26): infra_blocked / infra_excluded / aborted_circuit_open must
# be excluded (None) from every outcome measure, not scored a hard 0.0 --
# probed directly against all three outcome functions, as the review demanded.
# ---------------------------------------------------------------------------

_INFRA_STATUSES = ("infra_blocked", "infra_excluded", "aborted_circuit_open")


def _infra_chain(status):
    # An infra-stopped chain never reaches any phase: every phase result is
    # None, exactly what run_respec_cascade_family.py actually writes for
    # infra_blocked (STATUS_INFRA_BLOCKED result), infra_excluded
    # (exhausted_chain_result's base_result) and aborted_circuit_open (the
    # sweep's own CircuitOpenError-catch synthetic result).
    return {"doc_label": "doc__anchor1", "arm": "control", "status": status,
            "phase1_result": None, "phase2_result": None, "phase3_result": None}


def test_infra_statuses_are_excluded_from_the_composite_measure():
    for status in _INFRA_STATUSES:
        assert r._phase3_composite_outcome(_infra_chain(status)) is None, status


def test_infra_statuses_are_excluded_from_the_per_family_measure():
    for status in _INFRA_STATUSES:
        for mode in r.FROZEN_CHAIN_MODES:
            assert r._phase3_family_outcome(_infra_chain(status), "bibliography", mode) is None, (status, mode)


def test_infra_statuses_are_excluded_from_keep_survival():
    for status in _INFRA_STATUSES:
        for mode in r.FROZEN_CHAIN_MODES:
            assert r._phase2_keep_survival_outcome(_infra_chain(status), mode) is None, (status, mode)


def test_infra_statuses_are_excluded_end_to_end_not_scored_zero():
    # Before the fix, `_EXCLUDED_STATUSES` lacked these three, so the
    # composite fell through to its "froze or missing phase result" branch
    # and scored 0.0 -- this is the exact regression the review's probe found.
    cascade, baseline = _synthetic_run()
    cascade = cascade + [_infra_chain(status) for status in _INFRA_STATUSES]
    report = r.compute_respec_cascade_tiers(cascade, baseline)
    reasons = {e["reason"] for e in report["excluded_observations"] if e["doc_label"] == "doc__anchor1"}
    assert reasons == set(_INFRA_STATUSES)


# ---------------------------------------------------------------------------
# M2 / P-R1 (2026-09-26): --blocked-policy threaded through _baseline_outcome,
# and the fail_graded_prefreeze / package_invalid_only frozen-chain modes the
# S25 locked s25-statistics command requires.
# ---------------------------------------------------------------------------

def _blocked_baseline(doc_label, arm):
    return {"doc_label": doc_label, "arm": arm, "status": "blocked_timeout", "k_pairs": 1, "pairs": []}


def test_blocked_policy_default_reproduces_the_stored_statistics():
    assert r._baseline_outcome(_blocked_baseline("d", "control")) is None


def test_blocked_policy_fail_scores_a_blocked_baseline_zero():
    assert r._baseline_outcome(_blocked_baseline("d", "control"), "fail") == 0.0


def test_compute_respec_cascade_tiers_threads_blocked_policy_to_baselines():
    cascade, baseline = _synthetic_run()
    label = next(iter(baseline["bibliography"]))["doc_label"]
    baseline["bibliography"][0] = _blocked_baseline(label, "control")
    excluded = r.compute_respec_cascade_tiers(cascade, baseline)
    failed = r.compute_respec_cascade_tiers(cascade, baseline, blocked_policy="fail")
    assert excluded["blocked_policy"] == "exclude" and failed["blocked_policy"] == "fail"
    ex_reasons = [e for e in excluded["excluded_observations"] if e["doc_label"] == label and e["arm"] == "control"
                  and e["measure"] == "baseline_bibliography"]
    fail_reasons = [e for e in failed["excluded_observations"] if e["doc_label"] == label and e["arm"] == "control"
                    and e["measure"] == "baseline_bibliography"]
    assert len(ex_reasons) == 1 and len(fail_reasons) == 0


def _frozen_package_invalid():
    frozen = _frozen_in_phase3_new_format()
    frozen["freeze_cause"] = "package_invalid"
    return frozen


def _frozen_other_cause():
    frozen = _frozen_in_phase3_new_format()
    frozen["freeze_cause"] = "other"
    return frozen


def test_fail_graded_prefreeze_uses_the_pre_freeze_verdict_and_fails_the_rest():
    frozen = _frozen_in_phase3_new_format()  # families: bib/citation/section_reorder pass, equation/caption not reached
    assert r._phase3_family_outcome(frozen, "bibliography", "fail_graded_prefreeze") == 1.0
    assert r._phase3_family_outcome(frozen, "equation", "fail_graded_prefreeze") == 0.0
    assert r._phase3_family_outcome(frozen, "caption", "fail_graded_prefreeze") == 0.0
    # Below Checkpoint B there is no partial credit: scores exactly like "fail".
    frozen2 = _frozen_in_phase2()
    assert r._phase2_keep_survival_outcome(frozen2, "fail_graded_prefreeze") == 0.0
    # A chain that reached Checkpoint B keeps its real outcome regardless of mode.
    assert r._phase2_keep_survival_outcome(frozen, "fail_graded_prefreeze") == 1.0


def test_fail_graded_prefreeze_with_a_failing_pre_freeze_verdict_scores_zero():
    frozen = _frozen_in_phase3_new_format()
    frozen["phase3_result"]["families"]["bibliography"]["verdict"] = "fail"
    assert r._phase3_family_outcome(frozen, "bibliography", "fail_graded_prefreeze") == 0.0


def test_package_invalid_only_follows_freeze_cause():
    package_invalid, other = _frozen_package_invalid(), _frozen_other_cause()
    # package_invalid freezes score exactly like fail_graded_prefreeze ...
    assert r._phase3_family_outcome(package_invalid, "bibliography", "package_invalid_only") == 1.0
    assert r._phase3_family_outcome(package_invalid, "equation", "package_invalid_only") == 0.0
    # ... any other cause is excluded (None), not imputed.
    assert r._phase3_family_outcome(other, "bibliography", "package_invalid_only") is None
    assert r._phase3_family_outcome(other, "equation", "package_invalid_only") is None
    frozen2 = _frozen_in_phase2()
    assert r._phase2_keep_survival_outcome({**frozen2, "freeze_cause": "package_invalid"}, "package_invalid_only") == 0.0
    assert r._phase2_keep_survival_outcome({**frozen2, "freeze_cause": "other"}, "package_invalid_only") is None


def test_new_frozen_chain_modes_are_accepted_by_the_report():
    cascade, baseline = _synthetic_run()
    for mode in ("fail_graded_prefreeze", "package_invalid_only"):
        report = r.compute_respec_cascade_tiers(cascade, baseline, frozen_chain_mode=mode)
        assert report["frozen_chain_mode"] == mode


def test_locked_s25_statistics_command_runs_end_to_end(tmp_path):
    """Reproduces the S25 `# locked-command: s25-statistics` loop (docs/
    paper-s25-respec-cascade-rerun-protocol-v1.md section 6.9) on a synthetic
    run tree: every mode in the loop must parse and run without an argparse
    error (P-R1 / M2)."""
    run_root = tmp_path / "primary"
    baseline_root = tmp_path / "baselines"
    cascade, baseline = _synthetic_run()
    for chain in cascade:
        chain_dir = run_root / f"{chain['doc_label']}-{chain['arm']}"
        chain_dir.mkdir(parents=True, exist_ok=True)
        (chain_dir / "chain-result.json").write_text(json.dumps(chain), encoding="utf-8")
    for family, chains in baseline.items():
        for chain in chains:
            chain_dir = baseline_root / family / f"{chain['doc_label']}-{chain['arm']}"
            chain_dir.mkdir(parents=True, exist_ok=True)
            (chain_dir / "chain-result.json").write_text(json.dumps(chain), encoding="utf-8")
    out_dir = tmp_path / "statistics"
    for mode in ("fail_graded_prefreeze", "fail", "exclude", "package_invalid_only"):
        rc = r.main([
            "--run-root", str(run_root), "--baseline-run-root", str(baseline_root),
            "--frozen-chain-mode", mode, "--blocked-policy", "fail",
            "--out", str(out_dir / f"respec-rerun-v1-statistics-{mode}.json"),
        ])
        assert rc == 0
        written = json.loads((out_dir / f"respec-rerun-v1-statistics-{mode}.json").read_text(encoding="utf-8"))
        assert written["frozen_chain_mode"] == mode and written["blocked_policy"] == "fail"
