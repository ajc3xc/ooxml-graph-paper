# PAPER-S7 section_reorder follow-up: result (v1)

Status: complete confirmatory result for the corpus and protocol preregistered in
`docs/paper-s7-section-reorder-followup-protocol-v1.md`, **updated 2026-09-04** after a
third real defect was found via a deliberate stress test and fixed. This document reports
what was actually found, including two real bugs discovered mid-analysis, and a result that
still does **not** confirm the v1 corpus's suggestive direction, though the corrected picture
leans somewhat more toward treatment than the first pass showed.

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

## A third real defect, found via a deliberate stress test

Separately from the evaluator whitespace bug above, three small hand-authored fixtures were
built specifically to probe genuine structural ambiguity -- duplicate/ambiguous anchor text,
an existing bibliography needing alphabetical (not just appended) insertion, and duplicate
heading text across two subsections of a document (`manifests/paper-s7-hard-fixtures-v1.json`,
exploratory, not part of the confirmatory corpus or its statistics). The duplicate-heading
fixture exposed that
`resolve_section_reorder_plan` picked its destination anchor as simply the next heading in
document order, with no awareness of heading LEVEL. On a document with nested
Heading1/Heading2 structure, that next heading is very often a Heading2 that is itself a
CHILD of the section just chosen: e.g. a real corpus document's plan chose "Application
Process" (level 1) to move, then picked "Guidance on Completing a CV Application" (level 2,
a subheading OF Application Process itself) as the destination -- a logically incoherent
instruction: move a section to appear after a heading that is part of itself.

`move_section` correctly (and defensibly) treats this as a no-op, since the destination is
already inside the source range being moved. But that graded as a **treatment failure** in
every affected case, while control's arbitrary natural-language interpretation of the same
nonsensical instruction often happened to satisfy the grader's loose checks anyway (same
paragraph multiset, order changed, heading still present -- none of which require the
reordering to correspond to any sensible interpretation of the instruction). Checked the
real v2 corpus directly rather than assuming impact: **4 of 48 documents** had this exact
defect. Checked the v1 corpus too: zero cases -- its K=1 and K=4 numbers are unaffected.

Fixed in `tools/docx_anchor_prober.py` (commit `8c7ae16`, tests in
`tests/test_docx_anchor_prober.py`): the destination must now be a genuine sibling (same
heading level as the chosen section), scanning forward past any deeper child headings. Full
corpus re-audit after the fix: zero incoherent plans remain. Of the 4 affected documents, 2
now correctly report `not_applicable` (no sibling-level heading exists to move into at all)
and 2 get a corrected, coherent destination -- re-run under the fixed resolver, both arms
now pass cleanly on both.

## Result (corrected)

**v2 follow-up alone** (n=46 paired documents after the plan-coherence correction, down from
48 -- 2 documents are now correctly `not_applicable`, validation+holdout combined):

| Arm | Pass rate | 95% CI |
|---|---:|---|
| Control | 80.4% (37/46) | [69.6%, 91.3%] |
| Treatment | 82.6% (38/46) | [71.7%, 93.5%] |

Paired permutation test: observed mean difference = -0.022 (favoring treatment), **p = 1.0**.

**Combined v1 + v2** (n=57 paired documents -- pooling explicitly disclosed per the
preregistration's reporting plan; the two pools come from different source distributions,
curated DocOps benchmark tasks vs. real-world scraped documents):

| Arm | Pass rate | 95% CI |
|---|---:|---|
| Control | 78.9% (45/57) | [68.4%, 89.5%] |
| Treatment | 86.0% (49/57) | [75.4%, 94.7%] |

Paired permutation test: observed mean difference = -0.070 (favoring treatment), **p =
0.3885**.

## Honest conclusion

Still not significant -- this does **not** confirm the v1 corpus's suggestive 72.7%-vs-100%
finding at conventional thresholds. But the correction genuinely moved the picture, not just
the headline number: the effect size favoring treatment grew (7.0 points combined, up from
5.1) and the p-value improved meaningfully (0.39, down from 0.57) once a real methodological
defect that was specifically penalizing treatment got fixed. The most defensible reading is
now more nuanced than the pre-correction "small-sample effect regressing to parity" framing:
there may be a real, modest advantage for treatment on section_reorder that this sample size
still cannot confirm, rather than no effect at all. This is exactly why the fixture-stress-test
effort was worth doing, and exactly why it is reported here in full rather than only
mentioning the fix without its effect on the actual numbers.

This is reported plainly because the preregistration committed to it in advance: "If this
follow-up's own result does not favor treatment, or is itself not significant, that is
reported plainly. This document does not commit to any particular outcome." The real value
of this exercise was never a single confirmed number -- it is a rigorous, disclosed process
that found and fixed three genuine bugs (this heading-level defect, the evaluator whitespace
bug, and the earlier PII scanner false-negative), none of which would have surfaced without
actually running the real acquisition-through-confirmatory pipeline, and one of which
(this one) would never have surfaced without deliberately trying to break the harness with
harder, more ambiguous test content instead of stopping at "it works."
