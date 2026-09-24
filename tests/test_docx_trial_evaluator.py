"""Regression tests for tools/docx_trial_evaluator.py's structural grading."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from docx_trial_evaluator import (  # noqa: E402
    grade_comment_targeting_chain,
    grade_comment_targeting_step,
    grade_forward_trial_equation,
    grade_forward_trial_reorder,
    grade_forward_trial_table_structural,
    grade_inverse_trial_equation,
    grade_inverse_trial_table_structural,
)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _make_docx(tmp_path: Path, name: str, paragraphs: list[str]) -> Path:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>'
    ).encode("utf-8")
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("_rels/.rels", "<Relationships/>")
        zf.writestr("word/document.xml", document_xml)
    return path


def _equation_paragraph_xml(marker: str) -> str:
    return (
        f'<w:p><m:oMath xmlns:m="{_M}">'
        f'<m:r><m:t>x = {marker}</m:t></m:r>'
        f'</m:oMath></w:p>'
    )


def _make_docx_raw_body(tmp_path: Path, name: str, body_xml: str) -> Path:
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}"><w:body>{body_xml}</w:body></w:document>'
    ).encode("utf-8")
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("_rels/.rels", "<Relationships/>")
        zf.writestr("word/document.xml", document_xml)
    return path


def _table_paragraph_xml(marker: str) -> str:
    return (
        "<w:tbl><w:tblGrid><w:gridCol w:w=\"1000\"/></w:tblGrid>"
        f"<w:tr><w:tc><w:p><w:r><w:t>{marker}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )


def test_reorder_forward_passes_when_heading_has_no_incidental_whitespace(tmp_path: Path) -> None:
    before = ["Heading A", "Body A", "Heading B", "Body B"]
    after = ["Heading B", "Body B", "Heading A", "Body A"]
    output = _make_docx(tmp_path, "clean.docx", after)

    result = grade_forward_trial_reorder(output, before, "Heading B")

    assert result["verdict"] == "pass"
    assert result["checks"]["moved_heading_still_present"] is True


def test_reorder_forward_passes_when_plans_heading_text_has_trailing_whitespace(tmp_path: Path) -> None:
    """Found live (2026-08-31) grading real-world documents: document_outline
    returns raw, unstripped run text for a heading (real OOXML runs commonly
    carry incidental trailing whitespace), while the grader's own paragraph
    extraction strips every paragraph. A byte-perfect round trip on such a
    document was being graded 'fail' purely from this whitespace mismatch --
    not a real capability gap, but it disproportionately penalized organic
    documents (rare in the curated benchmark corpus, common in real-world
    scraped documents) on BOTH arms equally, masking the true pass rate."""
    # paragraphs_before is itself always produced by _paragraph_texts (already
    # stripped) in the real harness -- only document_outline's heading text is
    # ever unstripped, so that's the only side of this fixture that carries it.
    before = ["Heading A", "Body A", "Heading B", "Body B"]
    after = ["Heading B", "Body B", "Heading A", "Body A"]
    output = _make_docx(tmp_path, "whitespace.docx", after)

    # section_heading_text as document_outline would actually return it: unstripped.
    result = grade_forward_trial_reorder(output, before, "Heading B ")

    assert result["verdict"] == "pass"
    assert result["checks"]["moved_heading_still_present"] is True


def test_reorder_forward_fails_when_heading_genuinely_missing(tmp_path: Path) -> None:
    before = ["Heading A", "Body A", "Heading B", "Body B"]
    after = ["Body B", "Heading A", "Body A"]  # heading B genuinely dropped
    output = _make_docx(tmp_path, "missing.docx", after)

    result = grade_forward_trial_reorder(output, before, "Heading B")

    assert result["verdict"] == "fail"
    assert result["checks"]["moved_heading_still_present"] is False


def test_equation_forward_passes_when_marker_equation_present(tmp_path: Path) -> None:
    """A pure-equation paragraph's parse_docx() text field comes back empty
    (confirmed directly, 2026-09-03): its content lives in <m:oMath>/<m:t>,
    not the <w:t> runs that field reads. grade_forward_trial_equation must
    use the equation-specific parser (parse_docx_equations_local's
    flat_text), not a plain paragraph-text search, or it could never pass."""
    before = ["Anchor paragraph."]
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _equation_paragraph_xml("1234567890")
    output = _make_docx_raw_body(tmp_path, "eq_forward.docx", body)

    result = grade_forward_trial_equation(output, before, "1234567890")

    assert result["verdict"] == "pass"
    assert result["checks"]["marker_equation_present_exactly_once"] is True


def test_equation_forward_fails_when_only_plain_text_inserted(tmp_path: Path) -> None:
    """The whole point of this family: a control-arm agent that inserts
    plain text reading "x = 1234567890" instead of a real <m:oMath> must
    fail, not pass on a text-substring technicality -- this is a genuine
    test of native OOXML math structure, not just visible text."""
    before = ["Anchor paragraph."]
    body = (
        "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>x = 1234567890</w:t></w:r></w:p>"
    )
    output = _make_docx_raw_body(tmp_path, "eq_plaintext.docx", body)

    result = grade_forward_trial_equation(output, before, "1234567890")

    assert result["verdict"] == "fail"
    assert result["checks"]["marker_equation_present_exactly_once"] is False


def test_equation_inverse_passes_when_equation_removed_and_paragraphs_restored(tmp_path: Path) -> None:
    before_forward = ["Anchor paragraph."]
    output = _make_docx(tmp_path, "eq_inverse_ok.docx", before_forward)

    result = grade_inverse_trial_equation(output, before_forward, "1234567890")

    assert result["verdict"] == "pass"
    assert result["checks"]["marker_equation_removed"] is True


def test_equation_inverse_fails_when_equation_still_present(tmp_path: Path) -> None:
    before_forward = ["Anchor paragraph."]
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _equation_paragraph_xml("1234567890")
    output = _make_docx_raw_body(tmp_path, "eq_inverse_fail.docx", body)

    result = grade_inverse_trial_equation(output, before_forward, "1234567890")

    assert result["verdict"] == "fail"
    assert result["checks"]["marker_equation_removed"] is False


def test_table_structural_forward_passes_when_marker_table_cell_present(tmp_path: Path) -> None:
    before = ["Anchor paragraph."]
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _table_paragraph_xml("PILOT-S7-TABLE-abc123")
    output = _make_docx_raw_body(tmp_path, "table_forward.docx", body)

    result = grade_forward_trial_table_structural(output, before, "PILOT-S7-TABLE-abc123")

    assert result["verdict"] == "pass"
    assert result["checks"]["marker_table_cell_present_exactly_once"] is True
    assert result["checks"]["no_original_paragraph_lost"] is True


def test_table_structural_forward_fails_when_original_paragraph_lost(tmp_path: Path) -> None:
    before = ["Anchor paragraph.", "A second original paragraph."]
    # "A second original paragraph." is missing from the output.
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _table_paragraph_xml("PILOT-S7-TABLE-abc123")
    output = _make_docx_raw_body(tmp_path, "table_forward_lost.docx", body)

    result = grade_forward_trial_table_structural(output, before, "PILOT-S7-TABLE-abc123")

    assert result["verdict"] == "fail"
    assert result["checks"]["no_original_paragraph_lost"] is False


def test_table_structural_inverse_passes_when_table_removed_and_paragraphs_restored(tmp_path: Path) -> None:
    before_forward = ["Anchor paragraph."]
    output = _make_docx(tmp_path, "table_inverse_ok.docx", before_forward)

    result = grade_inverse_trial_table_structural(output, before_forward, "PILOT-S7-TABLE-abc123")

    assert result["verdict"] == "pass"
    assert result["checks"]["marker_table_removed"] is True


def test_table_structural_inverse_fails_when_table_still_present(tmp_path: Path) -> None:
    before_forward = ["Anchor paragraph."]
    body = "<w:p><w:r><w:t>Anchor paragraph.</w:t></w:r></w:p>" + _table_paragraph_xml("PILOT-S7-TABLE-abc123")
    output = _make_docx_raw_body(tmp_path, "table_inverse_fail.docx", body)

    result = grade_inverse_trial_table_structural(output, before_forward, "PILOT-S7-TABLE-abc123")

    assert result["verdict"] == "fail"
    assert result["checks"]["marker_table_removed"] is False


# ---------------------------------------------------------------------------
# grade_comment_targeting_step / grade_comment_targeting_chain (PAPER-S24)
# ---------------------------------------------------------------------------

def _make_docx_with_comments(
    tmp_path: Path, name: str, body_xml: str, comments_xml: str | None = None,
) -> Path:
    """Mirrors this file's own `_make_docx_raw_body`, plus an optional
    `word/comments.xml` part (omitted entirely when None -- exercises the
    real "document with zero comments, no comments.xml part at all" case
    protocol section 1.3 found true of masters-dissertation-defense.docx)."""
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}" xmlns:w14="{_W14}"><w:body>{body_xml}</w:body></w:document>'
    ).encode("utf-8")
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("_rels/.rels", "<Relationships/>")
        zf.writestr("word/document.xml", document_xml)
        if comments_xml is not None:
            zf.writestr("word/comments.xml", comments_xml)
    return path


def _para_with_comment_range(
    para_id: str, text: str, comment_id: str, split_range: bool = False,
) -> str:
    """A <w:p> carrying the real commentRangeStart/commentRangeEnd/
    commentReference shape `_stage_word_comment` produces (start right after
    pPr -- omitted here, so at index 0 -- end appended, reference run last).
    split_range=True deliberately puts commentRangeEnd in a SEPARATE
    following paragraph (a malformed control-arm edit) to exercise
    _comment_range_precision's multi-paragraph-bracket detection."""
    if not split_range:
        return (
            f'<w:p w14:paraId="{para_id}">'
            f'<w:commentRangeStart w:id="{comment_id}"/>'
            f'<w:r><w:t>{text}</w:t></w:r>'
            f'<w:commentRangeEnd w:id="{comment_id}"/>'
            f'<w:r><w:commentReference w:id="{comment_id}"/></w:r>'
            f"</w:p>"
        )
    return (
        f'<w:p w14:paraId="{para_id}">'
        f'<w:commentRangeStart w:id="{comment_id}"/>'
        f'<w:r><w:t>{text}</w:t></w:r>'
        f"</w:p>"
    )


def _plain_para(para_id: str, text: str) -> str:
    return f'<w:p w14:paraId="{para_id}"><w:r><w:t>{text}</w:t></w:r></w:p>'


def _comments_xml(entries: list[tuple[str, str, str]]) -> str:
    """entries: [(comment_id, author, text), ...]."""
    body = "".join(
        f'<w:comment w:id="{cid}" w:author="{author}" w:initials="X" w:date="2026-09-24T00:00:00Z">'
        f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p></w:comment>'
        for cid, author, text in entries
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<w:comments xmlns:w="{_W}">{body}</w:comments>'


_ORGANIC_AUTHOR = "Adam Camerer"
_ORGANIC_TEXT = "An organic pre-existing comment."


def _organic_kept_entry() -> dict:
    return {"author": _ORGANIC_AUTHOR, "text": _ORGANIC_TEXT, "anchor_para_ids": ("ORGANIC1",)}


def test_comment_targeting_step_passes_correct_target_and_kept_priors_survive(tmp_path: Path) -> None:
    before_body = (
        _para_with_comment_range("ORGANIC1", "Organic paragraph.", "0")
        + _plain_para("TARGET01", "Target row text.")
        + _plain_para("SIB0001", "Sibling row text.")
    )
    before = _make_docx_with_comments(
        tmp_path, "before.docx", before_body, comments_xml=_comments_xml([("0", _ORGANIC_AUTHOR, _ORGANIC_TEXT)]),
    )
    after_body = (
        _para_with_comment_range("ORGANIC1", "Organic paragraph.", "0")
        + _para_with_comment_range("TARGET01", "Target row text.", "1")
        + _plain_para("SIB0001", "Sibling row text.")
    )
    after = _make_docx_with_comments(
        tmp_path, "after.docx", after_body,
        comments_xml=_comments_xml([
            ("0", _ORGANIC_AUTHOR, _ORGANIC_TEXT), ("1", "MeridianBench-t1", "step marker"),
        ]),
    )

    result = grade_comment_targeting_step(
        after, before, author_tag="MeridianBench-t1", target_para_id="TARGET01",
        confusable_sibling_para_ids=["SIB0001"], kept_comments={"organic:0": _organic_kept_entry()},
    )

    assert result["outcome"] == "correct_target"
    assert result["step_pass"] is True
    assert result["keep_survival_ok"] is True
    assert result["zero_paragraph_text_diff"] is True


def test_comment_targeting_step_detects_wrong_target_same_cluster(tmp_path: Path) -> None:
    before_body = _plain_para("TARGET01", "Target row text.") + _plain_para("SIB0001", "Sibling row text.")
    before = _make_docx_with_comments(tmp_path, "before.docx", before_body)
    # The new comment lands on the SIBLING, not the actual target.
    after_body = (
        _plain_para("TARGET01", "Target row text.")
        + _para_with_comment_range("SIB0001", "Sibling row text.", "0")
    )
    after = _make_docx_with_comments(
        tmp_path, "after.docx", after_body, comments_xml=_comments_xml([("0", "MeridianBench-t1", "step marker")]),
    )

    result = grade_comment_targeting_step(
        after, before, author_tag="MeridianBench-t1", target_para_id="TARGET01",
        confusable_sibling_para_ids=["SIB0001"], kept_comments={},
    )

    assert result["outcome"] == "wrong_target_same_cluster"
    assert result["step_pass"] is False


def test_comment_targeting_step_detects_no_comment_created(tmp_path: Path) -> None:
    before_body = _plain_para("TARGET01", "Target row text.")
    before = _make_docx_with_comments(tmp_path, "before.docx", before_body)
    after = _make_docx_with_comments(tmp_path, "after.docx", before_body)  # untouched -- no new comment at all

    result = grade_comment_targeting_step(
        after, before, author_tag="MeridianBench-t1", target_para_id="TARGET01",
        confusable_sibling_para_ids=[], kept_comments={},
    )

    assert result["outcome"] == "no_comment_created"
    assert result["step_pass"] is False
    assert result["exactly_one_new_comment_by_author"] is False


def test_comment_targeting_step_detects_prior_organic_comment_corrupted(tmp_path: Path) -> None:
    """The new comment correctly targets TARGET01, but the pre-existing
    organic comment was lost along the way -- protocol section 4 item 3's
    keep-survival check must catch this even though the step's OWN target
    was hit exactly."""
    before_body = (
        _para_with_comment_range("ORGANIC1", "Organic paragraph.", "0") + _plain_para("TARGET01", "Target row text.")
    )
    before = _make_docx_with_comments(
        tmp_path, "before.docx", before_body, comments_xml=_comments_xml([("0", _ORGANIC_AUTHOR, _ORGANIC_TEXT)]),
    )
    # Organic comment's range markers are GONE in the output -- corrupted.
    after_body = (
        _plain_para("ORGANIC1", "Organic paragraph.")
        + _para_with_comment_range("TARGET01", "Target row text.", "1")
    )
    after = _make_docx_with_comments(
        tmp_path, "after.docx", after_body, comments_xml=_comments_xml([("1", "MeridianBench-t1", "step marker")]),
    )

    result = grade_comment_targeting_step(
        after, before, author_tag="MeridianBench-t1", target_para_id="TARGET01",
        confusable_sibling_para_ids=[], kept_comments={"organic:0": _organic_kept_entry()},
    )

    assert result["outcome"] == "prior_comment_corrupted"
    assert result["step_pass"] is False
    assert result["keep_survival_ok"] is False


def test_comment_targeting_step_detects_unexpected_paragraph_text_diff(tmp_path: Path) -> None:
    """A comment insertion never legitimately touches paragraph TEXT
    (protocol section 4 item 4) -- even with the new comment correctly
    targeted and no comment-level corruption, an unrelated paragraph's text
    changing must still fail the step."""
    before_body = _plain_para("TARGET01", "Target row text.") + _plain_para("OTHER001", "Original other text.")
    before = _make_docx_with_comments(tmp_path, "before.docx", before_body)
    after_body = (
        _para_with_comment_range("TARGET01", "Target row text.", "0")
        + _plain_para("OTHER001", "UNEXPECTEDLY CHANGED other text.")
    )
    after = _make_docx_with_comments(
        tmp_path, "after.docx", after_body, comments_xml=_comments_xml([("0", "MeridianBench-t1", "step marker")]),
    )

    result = grade_comment_targeting_step(
        after, before, author_tag="MeridianBench-t1", target_para_id="TARGET01",
        confusable_sibling_para_ids=[], kept_comments={},
    )

    assert result["zero_paragraph_text_diff"] is False
    assert result["outcome"] == "prior_comment_corrupted"
    assert result["step_pass"] is False


def test_comment_targeting_step_package_invalid_short_circuits(tmp_path: Path) -> None:
    before_body = _plain_para("TARGET01", "Target row text.")
    before = _make_docx_with_comments(tmp_path, "before.docx", before_body)
    missing_output = tmp_path / "does_not_exist.docx"

    result = grade_comment_targeting_step(
        missing_output, before, author_tag="MeridianBench-t1", target_para_id="TARGET01",
        confusable_sibling_para_ids=[], kept_comments={},
    )

    assert result["package_valid"] is False
    assert result["outcome"] == "chain_broken_at_step_k"
    assert result["step_pass"] is False


def test_comment_targeting_chain_passes_when_every_step_passes():
    passing_step = {"outcome": "correct_target", "step_pass": True}
    result = grade_comment_targeting_chain(
        [passing_step, passing_step, passing_step], ["ambiguous", "unique", "ambiguous"],
    )
    assert result["chain_pass"] is True
    assert result["first_failed_chain_position"] is None
    assert [p["condition"] for p in result["per_position"]] == ["ambiguous", "unique", "ambiguous"]


def test_comment_targeting_chain_reports_first_failed_position():
    passing_step = {"outcome": "correct_target", "step_pass": True}
    failing_step = {"outcome": "wrong_target_same_cluster", "step_pass": False}
    result = grade_comment_targeting_chain(
        [passing_step, failing_step, passing_step], ["ambiguous", "unique", "ambiguous"],
    )
    assert result["chain_pass"] is False
    assert result["first_failed_chain_position"] == 2


def test_comment_targeting_chain_rejects_mismatched_lengths():
    import pytest

    with pytest.raises(ValueError):
        grade_comment_targeting_chain([{"step_pass": True}], ["ambiguous", "unique"])
