"""Unit tests for tools/graph_scorer.py (PAPER-30).

Run with: pixi run python -m pytest tests/test_graph_scorer.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import graph_scorer  # noqa: E402


# ---------------------------------------------------------------------------
# _lcs_correspondence / _prf1
# ---------------------------------------------------------------------------

def test_lcs_correspondence_exact_match():
    pairs = graph_scorer._lcs_correspondence(["Hello world", "Second para"], ["Hello world", "Second para"])
    assert pairs == [(0, 0), (1, 1)]


def test_lcs_correspondence_case_and_whitespace_insensitive():
    pairs = graph_scorer._lcs_correspondence(["Hello   World"], ["hello world"])
    assert pairs == [(0, 0)]


def test_lcs_correspondence_blank_paragraph_matches_blank_paragraph():
    """Regression test: an earlier version excluded empty-string matches
    entirely, which scored a legitimately all-blank document (e.g. an
    image-only body) as 0 precision/recall even though extraction was
    structurally perfect. Found via a real corpus document
    (tier2-omegause-010-roadmap-diagram) during PAPER-30 development."""
    pairs = graph_scorer._lcs_correspondence([""], [""])
    assert pairs == [(0, 0)]


def test_lcs_correspondence_missing_paragraph_reduces_recall_not_precision():
    gold = ["A", "B", "C"]
    cand = ["A", "C"]  # candidate dropped "B"
    pairs = graph_scorer._lcs_correspondence(gold, cand)
    prf1 = graph_scorer._prf1(len(pairs), len(gold), len(cand))
    assert prf1["recall"] == 2 / 3
    assert prf1["precision"] == 1.0


def test_prf1_undefined_recall_when_gold_empty():
    result = graph_scorer._prf1(matched=0, gold_total=0, cand_total=3)
    assert result["recall"] is None  # undefined, not zero -- nothing to find
    assert result["f1"] is None


def test_prf1_perfect_score():
    result = graph_scorer._prf1(matched=5, gold_total=5, cand_total=5)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0


# ---------------------------------------------------------------------------
# _reading_order_accuracy
# ---------------------------------------------------------------------------

def test_reading_order_perfect_when_same_order():
    texts = ["Introduction section here", "Middle content block", "Conclusion remarks follow"]
    result = graph_scorer._reading_order_accuracy(texts, texts)
    assert result["accuracy"] == 1.0


def test_reading_order_detects_full_reversal():
    """The whole point of this metric: LCS-based correspondence cannot
    reveal reordering by construction, so this must use independent
    nearest-neighbor matching instead. A fully reversed document should
    score low reading-order accuracy, not a tautological 1.0."""
    texts = ["Introduction section here", "Middle content block", "Conclusion remarks follow"]
    reversed_texts = list(reversed(texts))
    result = graph_scorer._reading_order_accuracy(texts, reversed_texts)
    assert result["matched_pairs"] == 3
    assert result["accuracy"] == 0.0  # all 3 pairs are discordant under full reversal


def test_reading_order_undefined_with_fewer_than_two_matches():
    result = graph_scorer._reading_order_accuracy(["Only one paragraph here"], ["Only one paragraph here"])
    assert result["accuracy"] is None


def test_reading_order_large_document_completes_quickly():
    """Regression test for a real O(n^2) performance bug found during
    PAPER-30 development: comparing every candidate paragraph against every
    unused gold paragraph with a full SequenceMatcher.ratio() call stalled
    for minutes on real corpus documents with hundreds of paragraphs. This
    generates 400 mostly-distinct paragraphs and asserts the function
    returns well within a generous bound, not that it's merely correct."""
    import time

    gold_texts = [f"Paragraph number {i} contains some unique filler content about topic {i}." for i in range(400)]
    cand_texts = list(gold_texts)  # identical order -- exercises the exact-match fast path fully
    t0 = time.perf_counter()
    result = graph_scorer._reading_order_accuracy(gold_texts, cand_texts)
    elapsed = time.perf_counter() - t0
    assert result["accuracy"] == 1.0
    assert elapsed < 5.0, f"reading-order computation took {elapsed:.2f}s for 400 paragraphs -- performance regression"


def test_count_inversions_matches_naive_double_loop():
    import random

    rng = random.Random(42)
    for _ in range(20):
        seq = list(range(rng.randint(2, 30)))
        rng.shuffle(seq)
        naive = sum(1 for i in range(len(seq)) for j in range(i + 1, len(seq)) if seq[i] > seq[j])
        fast = graph_scorer._count_inversions(list(seq))
        assert fast == naive, f"mismatch on {seq}"


# ---------------------------------------------------------------------------
# Equation semantic-class accuracy
# ---------------------------------------------------------------------------

_CORRECT_FRACTION_OMML = (
    '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
    '<m:f><m:fPr><m:type m:val="bar"/></m:fPr>'
    '<m:num><m:r><m:t>1</m:t></m:r></m:num>'
    '<m:den><m:r><m:t>2</m:t></m:r></m:den></m:f></m:oMath>'
)


def test_equation_semantic_accuracy_matches_when_omml_identical():
    gold_nodes = [{"attrs": {"semantic_label": "correct", "order": 0}}]
    cand_equations = [{"omml_raw": _CORRECT_FRACTION_OMML}]
    result = graph_scorer._equation_semantic_accuracy(gold_nodes, cand_equations)
    assert result["status"] == "scored"
    assert result["accuracy"] == 1.0
    assert result["mismatches"] == []


def test_equation_semantic_accuracy_not_applicable_when_no_omml():
    """python-docx and Docling both lack OMML; this must be explicitly
    not_applicable, never a fabricated 0 (per comparator-contract-v0.md
    Section 7.3's not-applicable-vs-failure distinction)."""
    gold_nodes = [{"attrs": {"semantic_label": "correct", "order": 0}}]
    cand_equations_present_but_no_omml = [{"omml_raw": None}]
    result = graph_scorer._equation_semantic_accuracy(gold_nodes, cand_equations_present_but_no_omml)
    assert result["accuracy"] is None
    assert "not_applicable" in result["status"]


def test_equation_semantic_accuracy_undefined_when_no_equations_either_side():
    result = graph_scorer._equation_semantic_accuracy([], [])
    assert result["accuracy"] is None
    assert result["status"] == "undefined"


def test_reclassify_omml_handles_unparseable_string():
    assert graph_scorer._reclassify_omml("<not valid xml") is None


# ---------------------------------------------------------------------------
# Bootstrap CI and paired permutation test
# ---------------------------------------------------------------------------

def test_bootstrap_ci_reasonable_bounds_for_constant_values():
    # All-identical input is the one case the percentile bootstrap itself
    # cannot express any uncertainty for (every resample is identical to the
    # original sample), so this falls back to the exact Clopper-Pearson
    # interval rather than reporting a zero-width [1.0, 1.0] "interval".
    result = graph_scorer.bootstrap_ci([1.0] * 20)
    assert result["mean"] == 1.0
    assert result["method"] == "clopper_pearson_exact_fallback"
    assert result["ci_low"] == pytest.approx((0.05 / 2) ** (1.0 / 20))
    assert result["ci_high"] == 1.0


def test_bootstrap_ci_all_fail_uses_clopper_pearson_upper_bound():
    result = graph_scorer.bootstrap_ci([0.0] * 20)
    assert result["mean"] == 0.0
    assert result["method"] == "clopper_pearson_exact_fallback"
    assert result["ci_low"] == 0.0
    assert result["ci_high"] == pytest.approx(1.0 - (0.05 / 2) ** (1.0 / 20))


def test_bootstrap_ci_non_boundary_uses_ordinary_percentile_bootstrap():
    result = graph_scorer.bootstrap_ci([1.0] * 18 + [0.0] * 2)
    assert result["method"] == "percentile_bootstrap"


def test_bootstrap_ci_undefined_with_fewer_than_two_values():
    result = graph_scorer.bootstrap_ci([0.5])
    assert result["ci_low"] is None
    assert result["ci_high"] is None


def test_bootstrap_ci_none_values_excluded_not_treated_as_zero():
    result = graph_scorer.bootstrap_ci([1.0, None, 1.0, None, 1.0])
    assert result["n"] == 3
    assert result["mean"] == 1.0


def test_bootstrap_ci_is_deterministic_across_calls():
    values = [0.1, 0.5, 0.9, 0.3, 0.7, 0.2, 0.6, 0.4]
    a = graph_scorer.bootstrap_ci(values)
    b = graph_scorer.bootstrap_ci(values)
    assert a == b  # fixed seed -- reproducible, not flaky


def test_paired_permutation_detects_large_systematic_difference():
    a_vals = [0.9, 0.95, 0.92, 0.91, 0.93, 0.94, 0.96, 0.90]
    b_vals = [0.1, 0.15, 0.12, 0.11, 0.13, 0.14, 0.16, 0.10]
    result = graph_scorer.paired_permutation_test(a_vals, b_vals)
    assert result["observed_mean_diff"] > 0.7
    assert result["p_value"] < 0.05  # a large, consistent gap should be detected as significant


def test_paired_permutation_no_difference_gives_high_p_value():
    values = [0.5, 0.6, 0.4, 0.55, 0.45, 0.5, 0.6, 0.4]
    result = graph_scorer.paired_permutation_test(values, values)  # identical -- zero difference
    assert result["observed_mean_diff"] == 0.0
    assert result["p_value"] == 1.0  # every permutation is at least as extreme as "no difference"


def test_paired_permutation_ignores_unpaired_none_values():
    a_vals = [1.0, None, 1.0, 1.0]
    b_vals = [0.0, 0.0, None, 0.0]
    result = graph_scorer.paired_permutation_test(a_vals, b_vals)
    assert result["n_paired_documents"] == 2  # only indices 0 and 3 have values on both sides


# ---------------------------------------------------------------------------
# score_document_graph (integration-style, synthetic documents)
# ---------------------------------------------------------------------------

def _make_gold(paragraphs, tables=None, equations=None, equation_nodes=None):
    return {
        "paragraphs": paragraphs,
        "tables": tables or [],
        "equations": equations or [],
        "equation_nodes": equation_nodes or [],
        "full_text": "\n".join(p["text"] for p in paragraphs),
    }


def test_score_document_graph_perfect_native_like_candidate():
    gold = _make_gold([
        {"text": "First paragraph content", "para_id": "AAAA1111"},
        {"text": "Second paragraph content", "para_id": "BBBB2222"},
    ], tables=[{"row_count": 3, "col_count": 2}])
    candidate = {
        "paragraphs": [
            {"text": "First paragraph content", "para_id": "AAAA1111"},
            {"text": "Second paragraph content", "para_id": "BBBB2222"},
        ],
        "tables": [{"row_count": 3, "col_count": 2}],
        "equations": [],
        "full_text": "First paragraph content\nSecond paragraph content",
    }
    result = graph_scorer.score_document_graph(gold, candidate, candidate_has_para_id=True, candidate_has_omml=False)
    assert result["paragraph_node_prf1"]["f1"] == 1.0
    assert result["table_node_prf1"]["f1"] == 1.0
    assert result["table_row_exact_match_rate"] == 1.0
    assert result["para_id"]["preservation_rate"] == 1.0
    assert result["para_id"]["status"] == "scored"


def test_score_document_graph_para_id_not_applicable_for_python_docx_like_candidate():
    gold = _make_gold([{"text": "Some content here", "para_id": "AAAA1111"}])
    candidate = {"paragraphs": [{"text": "Some content here", "para_id": None}], "tables": [], "equations": [],
                 "full_text": "Some content here"}
    result = graph_scorer.score_document_graph(gold, candidate, candidate_has_para_id=False, candidate_has_omml=False)
    assert result["para_id"]["preservation_rate"] is None
    assert result["para_id"]["status"] == "not_applicable"


def test_score_document_graph_unsupported_kinds_are_declared_not_omitted():
    """reference/source_binding/revision have NO gold ground truth yet (a
    stronger, more precise statement than 'no candidate adapter') -- caption
    and anchor are no longer in this bucket at all, since PAPER-S5 gave them
    real, dedicated scoring (see the tests below)."""
    gold = _make_gold([{"text": "x", "para_id": None}])
    candidate = {"paragraphs": [{"text": "x", "para_id": None}], "tables": [], "equations": [], "full_text": "x"}
    result = graph_scorer.score_document_graph(gold, candidate, candidate_has_para_id=False, candidate_has_omml=False)
    for kind in ("reference", "source_binding", "revision"):
        assert result["unsupported_node_kinds"][kind] == graph_scorer.NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH
    assert "caption" not in result["unsupported_node_kinds"]
    assert "anchor" not in result["unsupported_node_kinds"]


def test_score_document_graph_unsupported_edge_kinds_use_correct_reasons():
    gold = _make_gold([{"text": "x", "para_id": None}])
    candidate = {"paragraphs": [{"text": "x", "para_id": None}], "tables": [], "equations": [], "full_text": "x"}
    result = graph_scorer.score_document_graph(gold, candidate, candidate_has_para_id=False, candidate_has_omml=False)
    # gold DOES resolve caption_for; no candidate computes an equivalent target yet.
    assert result["unsupported_edge_kinds"]["caption_for"] == graph_scorer.NOT_APPLICABLE_NO_ADAPTER
    # gold itself has no ground truth for these edge kinds at all.
    for kind in ("references", "revises", "clones", "conflicts_with"):
        assert result["unsupported_edge_kinds"][kind] == graph_scorer.NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH


def test_score_document_graph_caption_and_anchor_default_not_applicable():
    """Without explicitly passing candidate_has_caption_detection/
    candidate_has_anchor_detection=True, both default to not_applicable --
    matches every current real candidate adapter's actual capability."""
    gold = _make_gold([{"text": "x", "para_id": None}])
    gold["captions"] = [{"text": "Table 1: a caption"}]
    gold["anchors"] = [{"name": "_Ref100000000"}]
    candidate = {"paragraphs": [{"text": "x", "para_id": None}], "tables": [], "equations": [], "full_text": "x"}
    result = graph_scorer.score_document_graph(gold, candidate, candidate_has_para_id=False, candidate_has_omml=False)
    assert result["caption_node_prf1"]["status"] == graph_scorer.NOT_APPLICABLE_NO_ADAPTER
    assert result["anchor_node_prf1"]["status"] == graph_scorer.NOT_APPLICABLE_NO_ADAPTER


def test_score_document_graph_caption_scored_when_candidate_detects_captions():
    gold = _make_gold([{"text": "Intro paragraph", "para_id": None}])
    gold["captions"] = [{"text": "Table 1: revenue by quarter"}]
    candidate = {
        "paragraphs": [{"text": "Intro paragraph", "para_id": None}],
        "tables": [], "equations": [], "full_text": "Intro paragraph",
        "captions": [{"text": "Table 1: revenue by quarter"}],
    }
    result = graph_scorer.score_document_graph(
        gold, candidate, candidate_has_para_id=False, candidate_has_omml=False,
        candidate_has_caption_detection=True,
    )
    assert result["caption_node_prf1"]["status"] == "scored"
    assert result["caption_node_prf1"]["f1"] == 1.0


# ---------------------------------------------------------------------------
# _caption_node_accuracy / _anchor_node_accuracy (PAPER-S5)
# ---------------------------------------------------------------------------

def test_caption_node_accuracy_not_applicable_without_detection():
    result = graph_scorer._caption_node_accuracy(
        [{"text": "Figure 1: a diagram"}], [], candidate_has_caption_detection=False,
    )
    assert result["status"] == graph_scorer.NOT_APPLICABLE_NO_ADAPTER
    assert result["f1"] is None


def test_caption_node_accuracy_scored_missed_caption_reduces_recall():
    result = graph_scorer._caption_node_accuracy(
        [{"text": "Figure 1: a diagram"}, {"text": "Table 1: totals"}],
        [{"text": "Figure 1: a diagram"}],
        candidate_has_caption_detection=True,
    )
    assert result["status"] == "scored"
    assert result["recall"] == 0.5
    assert result["precision"] == 1.0


def test_anchor_node_accuracy_not_applicable_without_detection():
    result = graph_scorer._anchor_node_accuracy(
        [{"name": "_Ref1"}], [], candidate_has_anchor_detection=False,
    )
    assert result["status"] == graph_scorer.NOT_APPLICABLE_NO_ADAPTER
    assert result["f1"] is None


def test_anchor_node_accuracy_exact_name_multiset_match():
    result = graph_scorer._anchor_node_accuracy(
        [{"name": "_Ref1"}, {"name": "PAPER16_TESTBOOKMARK"}],
        [{"name": "_Ref1"}, {"name": "_Ref1"}],  # candidate over-reports one, misses the other
        candidate_has_anchor_detection=True,
    )
    assert result["status"] == "scored"
    assert result["matched"] == 1  # multiset intersection: min(1 gold "_Ref1", 2 cand "_Ref1") = 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5


# ---------------------------------------------------------------------------
# score_round_trip_editability (PAPER-S5)
# ---------------------------------------------------------------------------

def _make_items(paragraphs, tables=None, equations=None):
    return {
        "paragraphs": [{"text": t, "para_id": None} for t in paragraphs],
        "tables": tables or [],
        "equations": equations or [],
        "full_text": "\n".join(paragraphs),
    }


def test_score_round_trip_editability_clean_round_trip():
    pre = _make_items(["First paragraph", "Second paragraph"], tables=[{"row_count": 2, "col_count": 2}])
    post = _make_items(["First paragraph", "Second paragraph", "PAPER-S5 marker"],
                        tables=[{"row_count": 2, "col_count": 2}])
    result = graph_scorer.score_round_trip_editability(pre, post, marker_text="PAPER-S5 marker")
    assert result["marker_paragraph_round_tripped"] is True
    assert result["unintended_paragraph_drift_prf1"]["f1"] == 1.0
    assert result["table_count_stable"] is True
    assert result["overall_status"] == "clean_round_trip"


def test_score_round_trip_editability_detects_missing_marker():
    pre = _make_items(["First paragraph"])
    post = _make_items(["First paragraph"])  # Word round trip silently dropped the intended edit
    result = graph_scorer.score_round_trip_editability(pre, post, marker_text="PAPER-S5 marker")
    assert result["marker_paragraph_round_tripped"] is False
    assert result["overall_status"] == "marker_paragraph_missing_after_round_trip"


def test_score_round_trip_editability_detects_unintended_paragraph_loss():
    pre = _make_items(["First paragraph", "Second paragraph"])
    # post lost "Second paragraph" entirely (unintended drift) alongside the intended marker addition
    post = _make_items(["First paragraph", "PAPER-S5 marker"])
    result = graph_scorer.score_round_trip_editability(pre, post, marker_text="PAPER-S5 marker")
    assert result["marker_paragraph_round_tripped"] is True
    assert result["unintended_paragraph_drift_prf1"]["f1"] < 1.0
    assert result["overall_status"] == "unintended_paragraph_drift_detected"


def test_score_round_trip_editability_detects_equation_semantic_drift():
    pre = _make_items(["Some text"], equations=[{"omml_raw": _CORRECT_FRACTION_OMML}])
    empty_num_omml = (
        '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        '<m:f><m:num></m:num><m:den><m:r><m:t>2</m:t></m:r></m:den></m:f></m:oMath>'
    )
    post = _make_items(["Some text", "PAPER-S5 marker"], equations=[{"omml_raw": empty_num_omml}])
    result = graph_scorer.score_round_trip_editability(pre, post, marker_text="PAPER-S5 marker")
    assert result["equation_semantic_labels_stable"] is False
    assert result["overall_status"] == "equation_semantic_drift_detected"
