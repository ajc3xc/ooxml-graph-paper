"""Tests for tools/k4_replication_verdict.py (PAPER-S26 section 7, P-K6).

Fixtures hand-build compute_s7_statistics.py-shaped `groups` entries plus the
`paired_control_vs_treatment_significance_exact` field (prerequisite P-K1,
not yet implemented in compute_s7_statistics.py) -- see the module docstring
of k4_replication_verdict.py for why the verdict script requires it anyway.
`test_missing_exact_field_fails_loudly` exercises exactly today's real gap.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import k4_replication_verdict as v  # noqa: E402


def _group(*, observed_mean_diff=None, p_value=None, exact=True, n_paired_documents=56,
           include_exact_field=True, include_mc_field=True, control_n=60, treatment_n=60,
           family=v.FAMILY, k_pairs=v.K_PAIRS):
    group = {
        "family": family,
        "k_pairs": k_pairs,
        "control_n": control_n,
        "treatment_n": treatment_n,
        "control_pass_rate_ci": {"mean": 0.661, "ci_low": 0.52, "ci_high": 0.78, "n": control_n},
        "treatment_pass_rate_ci": {"mean": 0.929, "ci_low": 0.85, "ci_high": 0.98, "n": treatment_n},
        "paired_n": n_paired_documents,
    }
    if include_mc_field:
        group["paired_control_vs_treatment_significance"] = {
            "observed_mean_diff": observed_mean_diff, "p_value": p_value, "n_paired_documents": n_paired_documents,
        }
    if include_exact_field:
        group["paired_control_vs_treatment_significance_exact"] = {
            "observed_mean_diff": observed_mean_diff, "p_value": p_value, "exact": exact,
            "n_paired_documents": n_paired_documents,
        }
    return group


def _stats(groups, blocked_policy_tag=None, unregradable=None):
    stats = {"schema": "paper-s7-statistics-v1", "chain_count": 60, "groups": groups}
    if blocked_policy_tag is not None:
        stats["blocked_policy"] = blocked_policy_tag
    if unregradable is not None:
        stats["unregradable_grader_exception_stubs"] = unregradable
    return stats


def _write(path: Path, stats: dict) -> None:
    path.write_text(json.dumps(stats), encoding="utf-8")


# ---------------------------------------------------------------------------
# The three verdict outcomes
# ---------------------------------------------------------------------------

def test_replicated_robust_to_timeout_scoring(tmp_path):
    # control 0.661, treatment 0.929 -> observed_mean_diff (control - treatment) = -0.268 -> diff = +0.268 > 0.
    fail_stats = _stats([_group(observed_mean_diff=-0.268, p_value=0.0015, exact=True)],
                         blocked_policy_tag={"policy": "fail"})
    exclude_stats = _stats([_group(observed_mean_diff=-0.24, p_value=0.004, exact=True)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "REPLICATED"
    assert report["timeout_scoring_robustness_label"] == "robust_to_timeout_scoring"
    assert report["primary_fail_scoring"]["diff"] == pytest.approx(0.268)


def test_replicated_dependent_on_timeout_scoring(tmp_path):
    fail_stats = _stats([_group(observed_mean_diff=-0.268, p_value=0.0015, exact=True)],
                         blocked_policy_tag={"policy": "fail"})
    # Excluding blocked chains flips the sign under this (synthetic) exclude-scoring run.
    exclude_stats = _stats([_group(observed_mean_diff=0.05, p_value=0.4, exact=True)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "REPLICATED"
    assert report["timeout_scoring_robustness_label"] == "dependent_on_timeout_scoring"


def test_reversed(tmp_path):
    # diff = treatment - control < 0 and significant.
    fail_stats = _stats([_group(observed_mean_diff=0.20, p_value=0.01, exact=True)],
                         blocked_policy_tag={"policy": "fail"})
    exclude_stats = _stats([_group(observed_mean_diff=0.20, p_value=0.01, exact=True)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "REVERSED"
    assert report["timeout_scoring_robustness_label"] == "not_applicable"


def test_not_replicated_when_not_significant(tmp_path):
    fail_stats = _stats([_group(observed_mean_diff=-0.05, p_value=0.30, exact=True)],
                         blocked_policy_tag={"policy": "fail"})
    exclude_stats = _stats([_group(observed_mean_diff=-0.05, p_value=0.30, exact=True)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "NOT REPLICATED"
    assert report["timeout_scoring_robustness_label"] == "not_applicable"


# ---------------------------------------------------------------------------
# Fail loudly, don't guess
# ---------------------------------------------------------------------------

def test_missing_exact_field_fails_loudly(tmp_path, capsys):
    """Today's real gap (P-K1 not yet implemented): only the Monte Carlo
    field is present. The script must refuse, not fall back to it."""
    fail_stats = _stats(
        [_group(observed_mean_diff=-0.268, p_value=0.0015, include_exact_field=False)],
        blocked_policy_tag={"policy": "fail"},
    )
    exclude_stats = _stats([_group(observed_mean_diff=-0.24, p_value=0.004, include_exact_field=False)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 2
    assert not out.exists()
    err = capsys.readouterr().err
    assert "paired_control_vs_treatment_significance_exact" in err
    assert "P-K1" in err


def test_non_exact_flag_fails_loudly(tmp_path, capsys):
    fail_stats = _stats([_group(observed_mean_diff=-0.268, p_value=0.0015, exact=False)],
                         blocked_policy_tag={"policy": "fail"})
    exclude_stats = _stats([_group(observed_mean_diff=-0.24, p_value=0.004, exact=True)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 2
    assert "exact" in capsys.readouterr().err


def test_unregradable_grader_exception_stub_fails_loudly(tmp_path, capsys):
    fail_stats = _stats([_group(observed_mean_diff=-0.268, p_value=0.0015, exact=True)],
                         blocked_policy_tag={"policy": "fail"}, unregradable=1)
    exclude_stats = _stats([_group(observed_mean_diff=-0.24, p_value=0.004, exact=True)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 2
    assert "grader-exception" in capsys.readouterr().err


def test_wrong_blocked_policy_tag_is_caught(tmp_path, capsys):
    # --statistics must be the --blocked-policy fail file; here it looks like exclude.
    fail_stats = _stats([_group(observed_mean_diff=-0.268, p_value=0.0015, exact=True)])
    exclude_stats = _stats([_group(observed_mean_diff=-0.24, p_value=0.004, exact=True)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 2
    assert "blocked-policy fail" in capsys.readouterr().err


def test_missing_group_for_family_and_k_pairs_is_caught(tmp_path, capsys):
    fail_stats = _stats([_group(observed_mean_diff=-0.268, p_value=0.0015, exact=True, k_pairs=1)],
                         blocked_policy_tag={"policy": "fail"})
    exclude_stats = _stats([_group(observed_mean_diff=-0.24, p_value=0.004, exact=True, k_pairs=1)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 2
    assert "no group" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Missing-but-OPTIONAL fields must not crash
# ---------------------------------------------------------------------------

def test_missing_optional_fields_do_not_crash(tmp_path):
    fail_group = _group(observed_mean_diff=-0.268, p_value=0.0015, exact=True, include_mc_field=False)
    del fail_group["control_pass_rate_ci"]
    del fail_group["treatment_pass_rate_ci"]
    fail_stats = _stats([fail_group], blocked_policy_tag={"policy": "fail"})
    exclude_stats = _stats([_group(observed_mean_diff=-0.24, p_value=0.004, exact=True)])
    fail_path, exclude_path, out = tmp_path / "fail.json", tmp_path / "exclude.json", tmp_path / "verdict.json"
    _write(fail_path, fail_stats)
    _write(exclude_path, exclude_stats)

    rc = v.main(["--statistics", str(fail_path), "--statistics-timeouts-excluded", str(exclude_path), "--out", str(out)])

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "REPLICATED"
    assert report["primary_fail_scoring"]["control_pass_rate_ci"] is None
    assert report["primary_fail_scoring"]["monte_carlo_significance_for_reference_only"] is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
