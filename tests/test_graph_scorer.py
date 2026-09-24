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


# ---------------------------------------------------------------------------
# _comment_range_precision (PAPER-S24 comment_targeting)
# ---------------------------------------------------------------------------

def test_comment_range_precision_exact_match():
    result = graph_scorer._comment_range_precision(
        bracketed_para_ids={"TARGET01"}, target_para_id="TARGET01",
        confusable_sibling_para_ids=["SIB0001", "SIB0002"],
    )
    assert result["status"] == "exact_match"
    assert result["pass"] is True
    assert result["target_present"] is True
    assert result["confusable_siblings_absent"] is True


def test_comment_range_precision_wrong_target_same_cluster():
    """The precision failure mode this whole family exists to measure: the
    comment landed on a CONFUSABLE SIBLING of the intended target, not the
    target itself."""
    result = graph_scorer._comment_range_precision(
        bracketed_para_ids={"SIB0001"}, target_para_id="TARGET01",
        confusable_sibling_para_ids=["SIB0001", "SIB0002"],
    )
    assert result["status"] == "wrong_target_same_cluster"
    assert result["pass"] is False
    assert result["target_present"] is False
    assert result["confusable_siblings_absent"] is False


def test_comment_range_precision_wrong_target_other():
    """Landed on a paragraph that is neither the target nor in its
    confusable-sibling set at all -- a different, less specific failure mode
    than wrong_target_same_cluster."""
    result = graph_scorer._comment_range_precision(
        bracketed_para_ids={"UNRELATED9"}, target_para_id="TARGET01",
        confusable_sibling_para_ids=["SIB0001", "SIB0002"],
    )
    assert result["status"] == "wrong_target_other"
    assert result["pass"] is False


def test_comment_range_precision_no_range_found():
    result = graph_scorer._comment_range_precision(
        bracketed_para_ids=set(), target_para_id="TARGET01",
        confusable_sibling_para_ids=["SIB0001"],
    )
    assert result["status"] == "no_range_found"
    assert result["pass"] is False


def test_comment_range_precision_target_plus_extra_paragraph_is_not_exact_match():
    """A malformed range that correctly includes the target paragraph but
    ALSO brackets an extra, unrelated paragraph must not be credited as an
    exact match -- catches a control-arm hand-edit that puts
    commentRangeStart/commentRangeEnd in two different paragraphs."""
    result = graph_scorer._comment_range_precision(
        bracketed_para_ids={"TARGET01", "UNRELATED9"}, target_para_id="TARGET01",
        confusable_sibling_para_ids=["SIB0001"],
    )
    assert result["status"] == "wrong_target_other"
    assert result["exact_single_paragraph_match"] is False
    assert result["target_present"] is True
    assert result["pass"] is False


# ---------------------------------------------------------------------------
# score_comment_set_survival (PAPER-S24 comment_targeting)
# ---------------------------------------------------------------------------

def _comment_item(author: str, text: str, anchor_para_ids: tuple[str, ...]) -> dict:
    return {"author": author, "text": text, "anchor_para_ids": anchor_para_ids}


def test_comment_set_survival_clean_when_kept_comments_unchanged_and_one_new_added():
    organic = _comment_item("Adam Camerer", "An organic pre-existing comment.", ("ORGANIC1",))
    step1 = _comment_item("MeridianBench-step1", "step 1 marker", ("STEP0001",))
    checkpoint_a = [organic, step1]
    step2_new = _comment_item("MeridianBench-step2", "step 2 marker", ("STEP0002",))
    checkpoint_b = [organic, step1, step2_new]

    kept = {
        "organic:0": organic,
        "MeridianBench-step1": step1,
    }
    result = graph_scorer.score_comment_set_survival(
        checkpoint_a, checkpoint_b, kept, excluded_authors=["MeridianBench-step2"],
    )
    assert result["overall_status"] == "clean_comment_set_survival"
    assert result["organic:0"]["unchanged"] is True
    assert result["MeridianBench-step1"]["unchanged"] is True
    assert result["unintended_drift_detected"] is False


def test_comment_set_survival_detects_missing_kept_comment():
    organic = _comment_item("Adam Camerer", "An organic pre-existing comment.", ("ORGANIC1",))
    step1 = _comment_item("MeridianBench-step1", "step 1 marker", ("STEP0001",))
    checkpoint_a = [organic, step1]
    checkpoint_b = [organic]  # step1's own comment vanished between checkpoints

    kept = {"organic:0": organic, "MeridianBench-step1": step1}
    result = graph_scorer.score_comment_set_survival(checkpoint_a, checkpoint_b, kept)
    assert result["overall_status"] == "kept_comment_missing:MeridianBench-step1"
    assert result["MeridianBench-step1"]["present"] is False


def test_comment_set_survival_detects_re_anchored_comment_as_missing():
    """A kept comment still exists by the same author with the same text,
    but its range now brackets a DIFFERENT paragraph than it did at
    checkpoint A -- "still correctly anchored" (protocol section 4 item 3)
    has been violated even though the comment was not deleted outright.
    Matching is by the FULL (author, text, anchor_para_ids) tuple, never by
    author alone (see the function's own docstring: author is not a unique
    key across a document's real comments, so author-based matching would
    misclassify organic comments that share an author) -- a re-anchored
    comment therefore no longer matches its own expected tuple and is
    reported exactly like an outright deletion, `kept_comment_missing`, the
    same granularity score_keep_survival itself uses for its own elements."""
    step1_a = _comment_item("MeridianBench-step1", "step 1 marker", ("STEP0001",))
    step1_b_moved = _comment_item("MeridianBench-step1", "step 1 marker", ("WRONGPARA",))
    checkpoint_a = [step1_a]
    checkpoint_b = [step1_b_moved]

    kept = {"MeridianBench-step1": step1_a}
    result = graph_scorer.score_comment_set_survival(checkpoint_a, checkpoint_b, kept)
    assert result["overall_status"] == "kept_comment_missing:MeridianBench-step1"
    assert result["MeridianBench-step1"]["unchanged"] is False
    # The raw by-author count still shows a comment by this author exists in
    # B -- just not under its expected exact form -- retained as extra
    # diagnostic detail even though it doesn't change the top-level status.
    assert result["MeridianBench-step1"]["occurrences_checkpoint_b_by_author"] == 1


def test_comment_set_survival_detects_duplicated_kept_comment():
    step1 = _comment_item("MeridianBench-step1", "step 1 marker", ("STEP0001",))
    checkpoint_a = [step1]
    checkpoint_b = [step1, dict(step1)]  # duplicated between checkpoints

    kept = {"MeridianBench-step1": step1}
    result = graph_scorer.score_comment_set_survival(checkpoint_a, checkpoint_b, kept)
    assert result["overall_status"] == "kept_comment_duplicated:MeridianBench-step1"
    assert result["MeridianBench-step1"]["duplicated"] is True


def test_comment_set_survival_not_credited_when_checkpoint_a_already_wrong():
    """Mirrors score_keep_survival's own discipline: an element that was
    ALREADY missing/wrong at checkpoint A cannot be credited as "surviving"
    just because checkpoint B shows the same (wrong) state."""
    step1_expected = _comment_item("MeridianBench-step1", "step 1 marker", ("STEP0001",))
    step1_actual_at_a = _comment_item("MeridianBench-step1", "WRONG TEXT ALREADY", ("STEP0001",))
    checkpoint_a = [step1_actual_at_a]
    checkpoint_b = [step1_actual_at_a]  # identical to A, but A itself never matched "expected"

    kept = {"MeridianBench-step1": step1_expected}
    result = graph_scorer.score_comment_set_survival(checkpoint_a, checkpoint_b, kept)
    # Never matches the expected exact tuple at EITHER checkpoint -- not
    # credited as "unchanged" just because checkpoint B's wrong state
    # matches checkpoint A's wrong state.
    assert result["overall_status"] == "kept_comment_missing:MeridianBench-step1"
    assert result["MeridianBench-step1"]["exact_matches_checkpoint_a"] == 0
    assert result["MeridianBench-step1"]["unchanged"] is False


def test_comment_set_survival_detects_unintended_drift_outside_kept_set():
    """An extra, unaccounted-for comment appears at checkpoint B that is
    neither a kept comment nor this step's own excluded new one -- real,
    unattributed drift, distinct from every named kept-comment failure."""
    kept_comment = _comment_item("MeridianBench-step1", "step 1 marker", ("STEP0001",))
    checkpoint_a = [kept_comment]
    rogue = _comment_item("SomeoneElse", "an unexplained extra comment", ("ROGUE0001",))
    checkpoint_b = [kept_comment, rogue]

    kept = {"MeridianBench-step1": kept_comment}
    result = graph_scorer.score_comment_set_survival(
        checkpoint_a, checkpoint_b, kept, excluded_authors=["MeridianBench-step2"],
    )
    assert result["overall_status"] == "unintended_comment_drift_detected"
    assert result["unintended_drift_detected"] is True


def test_comment_set_survival_shared_author_organic_comments_graded_independently():
    """Regression test: real corpus data (protocol section 1.3) has organic
    comments that do NOT have unique authors -- jcshm-si.docx has 5 of its 6
    organic comments all authored "Claude (review flag)". Matching by author
    alone would let one such comment's survival vouch for a SIBLING organic
    comment sharing the same author but different text/anchor. This
    constructs exactly that shape: two organic comments, same author,
    different text/anchor -- one survives unchanged, the OTHER is silently
    dropped between checkpoints -- and asserts the drop is still caught."""
    organic_a = _comment_item("Claude (review flag)", "First organic note.", ("ORGA0001",))
    organic_b = _comment_item("Claude (review flag)", "Second organic note.", ("ORGA0002",))
    checkpoint_a = [organic_a, organic_b]
    checkpoint_b = [organic_a]  # organic_b silently vanished; organic_a (same author) survives fine

    kept = {"organic:0": organic_a, "organic:1": organic_b}
    result = graph_scorer.score_comment_set_survival(checkpoint_a, checkpoint_b, kept)

    assert result["organic:0"]["unchanged"] is True
    assert result["organic:1"]["unchanged"] is False
    assert result["overall_status"] == "kept_comment_missing:organic:1"


def test_comment_set_survival_shared_author_unrelated_comment_not_masked_as_kept():
    """Same shared-author real-corpus shape, but checking the REMAINDER/drift
    side rather than the per-element side: an untracked, genuinely NEW
    comment appears sharing an author with a kept organic comment -- it must
    still surface as unintended drift, not be silently absorbed because its
    author matches a kept entry's author."""
    organic_a = _comment_item("Claude (review flag)", "First organic note.", ("ORGA0001",))
    checkpoint_a = [organic_a]
    rogue_same_author = _comment_item("Claude (review flag)", "An unrelated NEW note.", ("ROGUE0001",))
    checkpoint_b = [organic_a, rogue_same_author]

    kept = {"organic:0": organic_a}
    result = graph_scorer.score_comment_set_survival(checkpoint_a, checkpoint_b, kept)

    assert result["organic:0"]["unchanged"] is True
    assert result["overall_status"] == "unintended_comment_drift_detected"
    assert result["unintended_drift_detected"] is True


def test_comment_set_survival_changed_status_when_checkpoint_a_lacked_exact_form():
    """The one shape that legitimately reaches "changed" rather than
    "missing": checkpoint A never had the exact expected form (0 exact
    matches), but checkpoint B does (1 exact match) -- credited as neither
    "missing" (it IS present at B) nor "unchanged" (A's own form was never
    confirmed valid, mirroring score_keep_survival's own discipline)."""
    expected = _comment_item("MeridianBench-step1", "step 1 marker", ("STEP0001",))
    wrong_at_a = _comment_item("MeridianBench-step1", "different text at A", ("STEP0001",))
    checkpoint_a = [wrong_at_a]
    checkpoint_b = [expected]

    kept = {"MeridianBench-step1": expected}
    result = graph_scorer.score_comment_set_survival(checkpoint_a, checkpoint_b, kept)

    assert result["overall_status"] == "kept_comment_changed:MeridianBench-step1"
    assert result["MeridianBench-step1"]["present"] is True
    assert result["MeridianBench-step1"]["unchanged"] is False


def test_comment_set_survival_empty_remainder_on_both_sides_is_clean_not_drift():
    """Regression test for the specific edge case this function's own
    docstring discloses: when the remainder (comments outside the kept set
    and this step's own excluded new one) is EMPTY on both checkpoints, a
    blind copy of score_keep_survival's own f1!=1.0 check would misfire
    (_prf1(0, 0, 0) returns f1=None, and None != 1.0), flagging every clean
    step as drift. Exercises exactly that all-empty-remainder shape."""
    kept_comment = _comment_item("MeridianBench-step1", "step 1 marker", ("STEP0001",))
    new_comment = _comment_item("MeridianBench-step2", "step 2 marker", ("STEP0002",))
    checkpoint_a = [kept_comment]
    checkpoint_b = [kept_comment, new_comment]

    kept = {"MeridianBench-step1": kept_comment}
    result = graph_scorer.score_comment_set_survival(
        checkpoint_a, checkpoint_b, kept, excluded_authors=["MeridianBench-step2"],
    )
    assert result["overall_status"] == "clean_comment_set_survival"
    assert result["unintended_drift_detected"] is False
