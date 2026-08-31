# PAPER-S7 section_reorder follow-up: result (v1)

Status: complete confirmatory result for the corpus and protocol preregistered in
`docs/paper-s7-section-reorder-followup-protocol-v1.md`. This document reports what was
actually found, including a real evaluator bug discovered mid-analysis and a result that
does **not** confirm the v1 corpus's suggestive direction.

## A second real harness defect found during analysis

Grading the completed trials, both arms showed a much lower pass rate (~60-63%) than the v1
corpus's section_reorder numbers (72.7-100%) -- worse than expected for a real capability
comparison, and suspicious because BOTH arms dropped by roughly the same amount. Inspecting
individual failures found every one sharing the identical failing check
(`moved_heading_still_present: false`) with every other check passing (valid docx, exact
paragraph multiset preserved, order genuinely changed) -- a strong signal of a grading bug,
not a real task failure.

Root cause: `docx_trial_evaluator.py`'s `grade_forward_trial_reorder` compared
`section_heading_text` (from `document_outline`'s raw, unstripped run text) against
`paragraphs_after` (from `_paragraph_texts`, which strips every paragraph). Any heading with
real, incidental leading/trailing whitespace in its OOXML runs -- common in organic
real-world documents, essentially absent from the curated DocOps benchmark corpus -- could
never match this check even on a byte-perfect round trip. Confirmed directly: candidate
`s7v2_sr_682a2e49bf2736bf`'s chosen heading text ends in a literal trailing space in the raw
OOXML; the evaluator's own paragraph extraction strips it before comparing.

Checked the v1 corpus for the same defect first: **zero of 52 v1 section_reorder chains**
hit this check at all, so v1's already-reported numbers are unaffected and unchanged.
20 of 96 v2 chains had this as their ONLY failing check.

Fixed in `tools/docx_trial_evaluator.py` (commit `2ccf4cb`, tests in
`tests/test_docx_trial_evaluator.py`): strip `section_heading_text` before the comparison.
Re-graded all 96 v2 forward trials against their already-produced output files -- no trials
were re-run, this is a pure re-scoring of existing artifacts. 17 of 96 flipped from `fail` to
`pass`.

## Result (corrected)

**v2 follow-up alone** (n=48 paired documents, validation+holdout combined):

| Arm | Pass rate | 95% CI |
|---|---:|---|
| Control | 75.0% (36/48) | [62.5%, 87.5%] |
| Treatment | 75.0% (36/48) | [62.5%, 87.5%] |

Paired permutation test: observed mean difference = 0.0, **p = 1.0**. Exactly tied.

**Combined v1 + v2** (n=59 paired documents -- pooling explicitly disclosed per the
preregistration's reporting plan; the two pools come from different source distributions,
curated DocOps benchmark tasks vs. real-world scraped documents):

| Arm | Pass rate | 95% CI |
|---|---:|---|
| Control | 74.6% (44/59) | [62.7%, 84.7%] |
| Treatment | 79.7% (47/59) | [69.5%, 89.8%] |

Paired permutation test: observed mean difference = -0.051 (favoring treatment), **p =
0.5665**.

## Honest conclusion

This does **not** confirm the v1 corpus's suggestive 72.7%-vs-100% finding. With 5x the
paired-document count, the direction still leans toward treatment but the effect nearly
vanishes (5 percentage points, not 27) and the p-value is nowhere near conventional
significance -- worse than v1's own underpowered p=0.24. The most defensible reading: v1's
n=11 result was likely a small-sample effect that regressed toward parity once real,
independently-sourced documents were added. Both arms handle `section_reorder` about
three-quarters of the time on real-world documents; treatment does not demonstrate a
reliable advantage here.

This is reported plainly because the preregistration committed to it in advance: "If this
follow-up's own result does not favor treatment, or is itself not significant, that is
reported plainly. This document does not commit to any particular outcome." The real value
of this exercise is not a confirmed effect -- it is a rigorous, disclosed null result plus
two genuine bugs found and fixed in the process (this evaluator defect, and the earlier PII
scanner false-negative), neither of which would have surfaced without actually running the
real acquisition-through-confirmatory pipeline instead of stopping at n=11.
