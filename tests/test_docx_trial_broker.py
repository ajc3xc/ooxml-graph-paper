"""Unit tests for tools/docx_trial_broker.py's trial generators.

No dedicated test file existed for this module before PAPER-S24 (its
existing generators were only ever exercised indirectly, via
tests/test_run_paper_s7_benchmark.py and tests/test_s20_pilot.py) -- this
file is new, covering generate_comment_targeting_step, the one new generator
PAPER-S24 (docs/paper-s24-targeted-comment-protocol-v0.md section 5 item 2)
adds to this module.

Run with: pixi run python -m pytest tests/test_docx_trial_broker.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from docx_trial_broker import TrialSpec, generate_comment_targeting_step  # noqa: E402

_REGIME1_TARGET = {
    "regime": "within_table_run",
    "label": "MAT (DSE)",
    "para_id": "039441A1",
    "disambiguator_value": "3",
    "table_index": 66,
    "row_index": 2,
    "confusable_sibling_para_ids": ["2DE46CC1", "198E365A", "4A418D30"],
}

_REGIME2_TARGET = {
    "regime": "cross_table_scatter",
    "label": "Atomic",
    "para_id": "750735C0",
    "disambiguator_value": "5.1 MIDLINE RS3-SCORE COMPARISON",
    "table_index": 38,
    "row_index": 0,
    "confusable_sibling_para_ids": ["0ABBE918", "7AFD955C"],
}

_UNIQUE_TARGET = {
    "para_id": "3EB5EFEE",
    "text_snippet": "This thesis provides three core contributions to address this gap.",
}


def test_returns_a_single_trial_spec_not_a_pair():
    """No inverse exists for this family (protocol section 0.2) -- unlike
    every forward/inverse generator pair elsewhere in this module, this
    returns ONE TrialSpec, never a tuple."""
    spec = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmark1", 1, "ambiguous", _REGIME1_TARGET, "MeridianBench-trial1",
    )
    assert isinstance(spec, TrialSpec)


def test_direction_is_forward_and_family_is_comment_targeting():
    spec = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmark1", 1, "ambiguous", _REGIME1_TARGET, "MeridianBench-trial1",
    )
    assert spec.direction == "forward"
    assert spec.family == "comment_targeting"


def test_treatment_args_carry_the_harness_resolved_anchor_and_comment_mode():
    """Protocol section 2.3: treatment gets exactly Read +
    insert_highlighted_note(mode="comment", anchor_para_id=<harness-resolved>,
    text=<step marker>, author=<per-trial tag>) -- never mode="inline"."""
    spec = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmark1", 1, "ambiguous", _REGIME1_TARGET, "MeridianBench-trial1",
    )
    assert spec.treatment_tool == "insert_highlighted_note"
    assert spec.treatment_args["mode"] == "comment"
    assert spec.treatment_args["anchor_para_id"] == _REGIME1_TARGET["para_id"]
    assert spec.treatment_args["author"] == "MeridianBench-trial1"
    assert spec.treatment_args["text"] == spec.marker_text


def test_prompt_mentions_regime1_label_and_adjacent_cell_disambiguator():
    spec = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmark1", 1, "ambiguous", _REGIME1_TARGET, "MeridianBench-trial1",
    )
    assert "MAT (DSE)" in spec.prompt
    assert "3" in spec.prompt  # the disambiguator_value
    assert "anchor_para_id" not in spec.prompt  # never leaked into the shared prompt text


def test_prompt_mentions_regime2_label_and_heading_disambiguator():
    spec = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmark2", 1, "ambiguous", _REGIME2_TARGET, "MeridianBench-trial2",
    )
    assert "Atomic" in spec.prompt
    assert "5.1 MIDLINE RS3-SCORE COMPARISON" in spec.prompt


def test_prompt_for_unique_target_uses_text_snippet_and_no_regime_language():
    spec = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmark3", 2, "unique", _UNIQUE_TARGET, "MeridianBench-trial3",
    )
    assert _UNIQUE_TARGET["text_snippet"] in spec.prompt
    assert "does not appear anywhere else" in spec.prompt


def test_prompt_instructs_not_to_touch_other_comments():
    """Load-bearing for keep survival (protocol section 4 item 3): both arms
    must be told not to disturb earlier/organic comments."""
    spec = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmark1", 3, "ambiguous", _REGIME1_TARGET, "MeridianBench-trial1",
    )
    assert "leave" in spec.prompt.lower()
    assert "MeridianBench-trial1" in spec.prompt  # author name stated explicitly to both arms


def test_both_arms_get_the_identical_prompt():
    """Protocol section 2.3: "Both arms receive the identical prompt at each
    step." TrialSpec.prompt is shared -- the arm split lives entirely in
    which tools claude_pair_runner grants, never in prompt wording."""
    spec = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmark1", 1, "ambiguous", _REGIME1_TARGET, "MeridianBench-trial1",
    )
    assert spec.arm == ""  # unset by the generator -- the orchestrator overrides it per arm, prompt unchanged


def test_distinct_steps_get_distinct_trial_ids_and_marker_text():
    spec1 = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmarkX", 1, "ambiguous", _REGIME1_TARGET, "MeridianBench-t1",
    )
    spec2 = generate_comment_targeting_step(
        "jcshm-si", Path("doc.docx"), "chainmarkX", 2, "unique", _UNIQUE_TARGET, "MeridianBench-t2",
    )
    assert spec1.trial_id != spec2.trial_id
    assert spec1.marker_text != spec2.marker_text


def test_unknown_condition_raises():
    import pytest

    with pytest.raises(ValueError):
        generate_comment_targeting_step(
            "jcshm-si", Path("doc.docx"), "chainmark1", 1, "bogus_condition", _REGIME1_TARGET, "MeridianBench-t1",
        )
