import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import compute_respec_cascade_statistics as crs  # noqa: E402
import graph_scorer  # noqa: E402
import reanalyze_respec_cascade as ra  # noqa: E402
import reconstruct_respec_observations as rro  # noqa: E402


@pytest.fixture(scope="module")
def inputs():
    return rro.load_inputs()


@pytest.fixture(scope="module")
def recon(inputs):
    return rro.reconstruct(inputs)


@pytest.fixture(scope="module")
def output(inputs, recon):
    return ra.build_output(inputs, recon)


# ---------------------------------------------------------------------------
# Reconstruction reproduces the stored statistics
# ---------------------------------------------------------------------------

def test_every_reconstruction_reproduces_the_stored_file_in_exclude_mode(inputs, recon):
    stored = inputs["statistics"]
    assert recon["reconstructions"]
    with rro.as_run_summation():
        for reconstruction in recon["reconstructions"]:
            chains, bchains = rro.build_chains(recon["cascade_meta"], recon["baseline_meta"], reconstruction)
            report = crs.compute_respec_cascade_tiers(chains, bchains, frozen_chain_mode="exclude")
            pooled = report["confirm_disconfirm"]["pooled"]
            # The pipeline's own seeded Monte Carlo test, as reported.
            assert pooled["control_drop"]["n_paired_anchor_sets"] == 29
            assert pooled["control_drop"]["p_value"] == 0.219
            assert pooled["control_drop"]["observed_mean_diff"] == stored["confirm_disconfirm"]["pooled"]["control_drop"]["observed_mean_diff"]
            assert pooled["direct_control_vs_treatment_phase3"]["n_paired_anchor_sets"] == 30
            report, _ = rro._with_stored_reason_convention(report, recon["cascade_meta"])
            assert rro.stored_mismatches(stored, report, skip=rro._PATH_FIELDS) == []


def test_only_control_keep_survival_cells_are_ambiguous(recon):
    reconstructions = recon["reconstructions"]
    assert len(reconstructions) == 3
    assert all(r["phase3"] == reconstructions[0]["phase3"] for r in reconstructions)
    assert all(r["baseline"] == reconstructions[0]["baseline"] for r in reconstructions)
    assert all(r["keep_survival"]["treatment"] == reconstructions[0]["keep_survival"]["treatment"] for r in reconstructions)
    # Every reconstruction keeps the stored control keep-survival total (5 of 11).
    assert {sum(r["keep_survival"]["control"].values()) for r in reconstructions} == {5}


def test_reconstruction_fails_loudly_when_nothing_reproduces(inputs):
    broken = copy.deepcopy(inputs)
    broken["statistics"]["confirm_disconfirm"]["bibliography"]["direct_control_vs_treatment_phase3"]["p_value"] = 0.242
    with pytest.raises(rro.ReconstructionError):
        rro.reconstruct(broken)


def test_chain_statuses_must_reproduce_the_composite(inputs):
    broken = copy.deepcopy(inputs)
    broken["statistics"]["outcome_measures"]["a_phase3_composite_pass_rate"]["tier1_per_document_unweighted"][
        "treatment_n_documents"] = 2
    with pytest.raises(rro.ReconstructionError, match="composite"):
        rro.reconstruct(broken)


def test_phase3_step_family_follows_the_rotation():
    assert rro.phase3_step_family("3.5-inverse") == "caption"
    assert rro.phase3_step_family("3.5-inverse", crs.SIX_FAMILIES) == "table_structural"
    assert rro.phase3_step_family("2.1") is None


def test_as_run_summation_is_restored():
    before = graph_scorer.__dict__.get("sum")
    with rro.as_run_summation():
        pass
    assert graph_scorer.__dict__.get("sum") is before
    assert rro.left_to_right_sum([0.1, 0.2, 0.3]) == (0.1 + 0.2) + 0.3


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def test_output_is_deterministic_and_matches_the_committed_file(output, inputs, recon):
    text = ra.serialize(output)
    assert text == ra.serialize(ra.build_output(inputs, recon))
    assert ra.OUT.read_text(encoding="utf-8") == text


def test_key_numbers(output):
    as_run = output["scenarios"]["as_run"]["measures"]
    protocol = output["scenarios"]["protocol"]["measures"]
    assert as_run["pooled_control_drop"]["tests"]["observation_level_as_run"]["p_value"] == 0.219
    assert as_run["pooled_direct"]["tests"]["chain_level"]["p_value"] == 0.25
    assert as_run["pooled_direct"]["tests"]["chain_level"]["n_units"] == 6
    assert as_run["pooled_control_drop"]["tests"]["chain_level"]["p_value"] == 0.5
    assert protocol["pooled_control_drop"]["n_paired_observations"] == 54
    assert protocol["pooled_direct"]["tests"]["chain_level"]["p_value"] == 2 / 2 ** 8
    assert protocol["keep_survival_direct"]["tests"]["chain_level"]["p_value"] == 2 / 2 ** 7
    assert protocol["whole_chain_composite_direct"]["tests"]["chain_level"]["p_value"] == 2 / 2 ** 9
    # Three documents: no document-level p below 2/2**3.
    assert protocol["pooled_direct"]["tests"]["document_level_exact"]["p_value"] == 0.25
    assert output["n_phase3_round_trips_finished_before_freeze"] == 10


def test_section7_verdicts(output):
    s = output["scenarios"]
    assert s["as_run"]["section7"]["chain_level"]["verdict"] == "DISCONFIRMING"
    assert s["protocol"]["section7"]["chain_level"]["verdict"].startswith("INCONCLUSIVE (confirming conditions met")
    assert s["protocol"]["section7"]["chain_level"]["tier1_min_attainable_p"] == 0.25


def test_post_hoc_tests_are_labelled_and_none_is_called_primary(output):
    assert "primary_test" not in output
    for name in ("chain_level", "observation_level_exact", "document_level_exact", "whole_chain_composite_direct"):
        assert output["analysis_status"][name] == "post_hoc_for_2026-09-23_run"
    assert output["analysis_status"]["observation_level_as_run"] == "as_run_reported"
    assert "Primary" not in output["tests"]["chain_level"]
    assert output["scenarios"]["as_run"]["analysis_status"] == "as_run_reported"
    assert output["scenarios"]["protocol"]["analysis_status"] == "post_hoc_for_2026-09-23_run"


def test_fail_scoring_is_described_as_an_imputation_for_these_freezes(output):
    # All 5 control freezes were at steps that also check marker re-resolution; the cause was not recorded.
    assert [f["freeze_step_checks_marker_re_resolution"] for f in output["frozen_chains"]] == [True] * 5
    assert "imputation" in output["scenarios"]["protocol"]["description"]
    for scenario in output["scenarios"].values():
        assert "control / jcshm-si__anchor3" in scenario["description"]
        assert "excluded" in scenario["description"]


def test_not_run_families_excluded_scenarios(output):
    s = output["scenarios"]
    fail = s["protocol_not_run_families_excluded"]
    passed = s["protocol_not_run_families_excluded_finished_round_trips_pass"]
    for scenario, p_control in ((fail, 15 / 256), (passed, 154 / 256)):
        drop = scenario["measures"]["pooled_control_drop"]
        # 54 protocol observations less the 11 never-run control cells (2.1: 5, 3.2-inverse: 3, 3.4-inverse: 1 x 3).
        assert drop["n_paired_observations"] == 43
        assert drop["tests"]["chain_level"]["p_value"] == p_control
        assert scenario["phase3_families_never_run"] == "excluded"
        assert scenario["phase3_round_trip_in_progress_at_freeze"] == "scored as failures"
    assert fail["finished_round_trips_before_freeze"] == "scored as failures"
    assert passed["finished_round_trips_before_freeze"] == "scored as passes"
    assert fail["measures"]["pooled_direct"]["tests"]["chain_level"]["p_value"] == 2 / 2 ** 7


def test_bounds_span_all_assignments_with_protocol_and_all_pass_as_ends(output):
    b = output["bounds"]["under_protocol_scoring"]
    assert b["n_phase3_assignments"] == 1024 and len(b["unknown_cells"]) == 10
    s = output["scenarios"]
    ranges = b["chain_level_ranges"]["pooled_control_drop"]
    for end, scenario in (("min", "protocol"), ("max", "protocol_finished_round_trips_pass")):
        chain_level = s[scenario]["measures"]["pooled_control_drop"]["tests"]["chain_level"]
        assert ranges["effect_pp"][end] == chain_level["effect_pp"]
        assert ranges["p_value"][end] == chain_level["p_value"]
    assert (ranges["p_value"]["min"], ranges["p_value"]["max"]) == (11 / 512, 7 / 64)
    # Excluding the 10 round trips is an intermediate point, not a bound.
    excluded = b["intermediate_scenarios"]["protocol_finished_round_trips_excluded"]["pooled_control_drop"]
    assert excluded["inside_the_ranges"] is True
    assert ranges["p_value"]["min"] < excluded["p_value"] < ranges["p_value"]["max"]
    # The direct comparison is significant at chain level under every assignment.
    assert b["chain_level_ranges"]["pooled_direct"]["p_value"]["max"] == 2 / 2 ** 8
    # Measures these cells cannot touch do not move.
    for name in ("pooled_treatment_drop", "keep_survival_direct", "whole_chain_composite_direct"):
        r = b["chain_level_ranges"][name]
        assert r["effect_pp"]["min"] == r["effect_pp"]["max"] and r["p_value"]["min"] == r["p_value"]["max"]
    counts = b["section7_chain_level_verdict_counts"]["verdict"]
    assert sum(counts.values()) == 1024
    assert counts == {"INCONCLUSIVE (confirming conditions met, but not at Tier 1)": 818, "INCONCLUSIVE": 204,
                      "DISCONFIRMING": 2}
    nr = output["bounds"]["with_not_run_families_excluded"]["chain_level_ranges"]["pooled_control_drop"]["p_value"]
    assert (nr["min"], nr["max"]) == (15 / 256, 154 / 256)


def test_grader_crash_chain_sensitivity(output):
    sensitivity = output["scenarios"]["protocol"]["grader_crash_chain_sensitivity"]
    assert sensitivity["chains"] == ["control / jcshm-si__anchor3"]
    assert sensitivity["n_phase3_assignments"] == 32 and sensitivity["n_composite_assignments"] == 2
    control_drop = sensitivity["chain_level_ranges"]["pooled_control_drop"]
    assert control_drop["n_paired_observations"] == {"min": 59, "max": 59}
    assert (control_drop["p_value"]["min"], control_drop["p_value"]["max"]) == (11 / 1024, 30 / 1024)
    composite = sensitivity["chain_level_ranges"]["whole_chain_composite_direct"]
    assert composite["n_paired_observations"] == {"min": 12, "max": 12}
    assert sum(sensitivity["section7_chain_level_verdict_counts"]["verdict"].values()) == 32
    assert sum(sensitivity["section7_chain_level_verdict_counts"]["verdict_with_whole_chain_composite_direct"].values()) == 64
    # Every scenario carries one.
    assert all("grader_crash_chain_sensitivity" in s for s in output["scenarios"].values())


# ---------------------------------------------------------------------------
# The cluster test on a hand-checkable example
# ---------------------------------------------------------------------------

def test_chain_level_test_flips_a_chains_observations_together():
    a = {"bibliography::docA__anchor0": 1.0, "citation::docA__anchor0": 1.0, "bibliography::docB__anchor0": 1.0}
    b = {key: 0.0 for key in a}
    tests = ra.run_tests(a, b)["tests"]
    # Chain sums 2 and 1: of the 4 patterns +-2+-1, |3| twice -> 2/4.
    assert tests["chain_level"]["p_value"] == 0.5
    assert tests["chain_level"]["n_units"] == 2
    assert tests["chain_level"]["observed_mean_diff"] == 1.0
    # Three independent observations: all-same-sign 2 of 8 patterns.
    assert tests["observation_level_exact"]["p_value"] == 0.25
    assert tests["document_level_exact"]["p_value"] == 0.5


def test_cluster_whose_differences_cancel_carries_no_weight():
    ids = ["c1", "c1", "c2", "c2"]
    result = graph_scorer.cluster_paired_sign_flip_test(ids, [1.0, 1.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0])
    # Sums: c1 = 2, c2 = 0. Only +-2 remain, both as extreme as observed.
    assert result["p_value"] == 1.0
    assert result["observed_mean_diff"] == 0.5
    assert result["exact"] is True
