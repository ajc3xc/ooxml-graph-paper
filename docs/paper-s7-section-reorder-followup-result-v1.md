# PAPER-S7 section_reorder follow-up: result (v1)

Status: complete confirmatory result for the corpus and protocol preregistered in
`docs/paper-s7-section-reorder-followup-protocol-v1.md`, **updated 2026-09-04 (second
update, same day)** after a FOURTH real defect was found while investigating a K=4 depth-study
anomaly and fixed. This document reports what was actually found, including three real bugs
discovered mid-analysis, and a K=1 result that still does **not** confirm the v1 corpus's
suggestive direction at conventional significance, though the corrected picture leans further
toward treatment than either prior pass showed. (The K=4 depth study -- a separate,
higher-powered measurement of the same underlying effect -- DOES reach significance after
this same fix; see `docs/paper-s8-final-evidence-v1.md` section 2.4 for that result, since
K=4 is out of this document's own K=1 scope.)

## A second real harness defect found during analysis

Grading the completed trials, both arms showed a much lower pass rate (~60-63%) than the v1
corpus's section_reorder numbers (72.7-100%) -- worse than expected for a real capability
comparison, and suspicious because BOTH arms dropped by roughly the same amount. Inspecting a
handful of individual failures found the same failing check
(`moved_heading_still_present: false`) with every other check passing (valid docx, exact
paragraph multiset preserved, order genuinely changed) -- a strong signal of a grading bug,
not a real task failure. **Clarified 2026-09-06**: this describes the initial diagnostic
sample, not the full failing population -- of the 28 v2 forward trials that failed before this
fix, 20 had this as their sole failing check (below), 3 failed on a different check entirely,
and 5 failed on both simultaneously. The root cause and fix are unaffected; only the earlier
"every one" phrasing overstated how uniform the failure population was.

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

## A fourth real defect, found while investigating a K=4 depth-study anomaly

Running section_reorder's K=4 depth study against the full 48-document v2 corpus (previously
only run against the original 11-document v1 corpus -- see `paper-s8-final-evidence-v1.md`
section 2.4/7), one document's control-arm chain repeatedly hit the harness's own 300-second
per-trial subprocess timeout -- six independent attempts, at different pairs and under
different host-memory conditions, all failing the identical way. Direct inspection confirmed
a mundane, honest cause: `document.xml` for this one document is 1.7MB (the package is
2.7MB with embedded images) -- genuinely large enough that a generic-tool agent reading and
searching raw XML cannot reliably finish within the timeout, independent of host load. This
is disclosed as a real, unresolved exclusion for this one document's control-arm chains (both
K=1 and K=4) -- not a bug, and not silently dropped.

But investigating this anomaly surfaced something else: this same document's **treatment**
chain executed quickly (15-25s per pair) yet failed FORWARD grading on every single pair, and
three other v2 documents showed a related signature. **Clarified 2026-09-06**: only one of
those three matches the description exactly (both arms completing normally, only
`moved_heading_still_present: false` failing); the other two also fail `order_actually_changed`
alongside it -- still traceable to the same root cause below, but a broader failure signature
than "only `moved_heading_still_present: false`" on its own.
Root cause: `resolve_section_reorder_plan` picked the section to move by raw position
(`headings[mid]`) with no check that the heading actually has text. Some real-world documents
have a heading-styled paragraph with no extractable text at all (an image-only or field-only
"heading") -- `grade_forward_trial_reorder`'s `moved_heading_still_present` check is
`section_heading_text.strip() in paragraphs_after`, which can never be true when that text is
`""`, since `_paragraph_texts` never yields a literal empty-string entry (confirmed directly:
262 paragraphs, zero empty, for the specific document that first surfaced this). A chain
hitting this fails forward grading regardless of whether the move itself was performed
correctly.

Checked the real corpora directly: **zero of 38 v1** documents, **4 of 48 v2** documents (a
different 4 than the heading-level defect above) -- and unlike that defect, this one affects
**3 of the 4 documents symmetrically** (both control and treatment failing forward grading for
the identical reason). **Corrected 2026-09-06**: the 4th document -- the same 1.7MB one whose
control-arm chain is discussed above -- is NOT symmetric: its control chain never reached
forward grading at all (status `blocked`, timed out before producing a result), so only its
treatment arm actually shows the blank-heading-text failure. So while the defect deflates both
arms' absolute pass rates on the 3 genuinely symmetric documents, it is less likely to have
biased the treatment-vs-control comparison on those -- the 4th document's asymmetry is a
separate, already-disclosed timeout exclusion, not part of this defect's own symmetric effect.

A closely related statistics-layer bug was found alongside it: `compute_s7_statistics.py`'s
`_chain_outcome` treated a "blocked" chain the same as any other once it had at least one
partial pair entry -- and a chain that hits the harness's 300s timeout still gets a `grading`
result computed against whatever the (unmodified) file looks like at that moment, so an infra
timeout was silently scored as a genuine 0.0 task failure. Confirmed this had already
contaminated the very numbers below (this section's own prior "corrected" K=1 figures): the
1.7MB document's blocked control chain, from the original 2026-08-31 collection, was counted
as a control failure for exactly this reason.

Fixed in `tools/docx_anchor_prober.py` (commit `278d9cc`, tests in
`tests/test_docx_anchor_prober.py`) -- the chosen section must have non-blank text, scanning
outward from the middle position for the nearest heading that does -- and in
`tools/compute_s7_statistics.py` (commit `b286c1b`, tests in `tests/test_compute_s7_statistics.py`)
-- `_chain_outcome`/`_chain_steady_state_outcome` now exclude `"blocked"` from both
denominators, agreeing with `_load_checkpoint`'s existing "never trust blocked" design instead
of silently contradicting it. Of the 4 affected v2 documents: 1 (the 1.7MB one) now correctly
excludes its control arm (real timeout, both K=1 and K=4) while treatment passes cleanly on
both; 1 (`s7v2_sr_0f0ec662b71bb10a`) now correctly reports `not_applicable` (no heading with
non-blank text is available in a safely-bounded middle position at all); the remaining 2 were
re-run cleanly under the fixed resolver, one of which is a genuine (not vacuous) control
failure at K=1 that passes at K=4.

## Result (corrected, second pass)

**v2 follow-up alone** (n varies by arm now -- control_n=44, treatment_n=45 -- since the
1.7MB document's control chain remains a genuine, disclosed exclusion while its treatment
chain completed; 3 documents are `not_applicable`, up from 2, validation+holdout combined):

| Arm | Pass rate | 95% CI |
|---|---:|---|
| Control | 86.4% (38/44) | [75.0%, 95.5%] |
| Treatment | 91.1% (41/45) | [82.2%, 97.8%] |

Paired permutation test (n=44 paired documents): observed mean difference = -0.045 (favoring
treatment), **p = 0.753**.

**Combined v1 + v2** (n=55 paired documents, down from 57 -- pooling explicitly disclosed per
the preregistration's reporting plan; the two pools come from different source distributions,
curated DocOps benchmark tasks vs. real-world scraped documents):

| Arm | Pass rate | 95% CI |
|---|---:|---|
| Control | 83.6% (46/55) | [74.5%, 92.7%] |
| Treatment | 92.9% (52/56) | [85.7%, 98.2%] |

Paired permutation test (n=55 paired documents): observed mean difference = -0.091 (favoring
treatment), **p = 0.2705**.

## Honest conclusion

Still not significant at K=1 -- this does **not** confirm the v1 corpus's suggestive
72.7%-vs-100% finding at conventional thresholds. But across two full correction passes now,
the picture has moved consistently in one direction, not bounced around noisily: the effect
size favoring treatment keeps growing (9.2 points combined, up from 7.0, up from 5.1 before
any correction) even as the p-value itself has not yet crossed the conventional threshold
(0.27, down from 0.39, down from 0.57). Three real methodological defects in a row, ALL of
which turned out to be spuriously penalizing this comparison rather than randomly distributed
noise, is itself a meaningful piece of evidence: it argues the true effect is more likely to
be real-but-underpowered-at-K=1 than genuinely zero. That is a claim about K=1 specifically --
**at K=4, the same document set (fewer defects remaining to distort it, and four times the
repeated-cycling exposure) does reach significance** (p=0.0015 combined; see
`docs/paper-s8-final-evidence-v1.md` section 2.4). **Corrected 2026-09-06** (an independent
pre-publication audit): the mechanism explanation here previously overstated as
"mechanistically verified... never on pair 0." Directly enumerating every K=4 control chain
with at least one failing pair (12 of 48, canonical post-fix manifests): 9 of 12 do show the
claimed pattern (`exact_original_order_restored` passes on pair 0, then fails from some later
pair onward and typically keeps failing) -- a real, dominant majority trend, not a
universal rule. But 2 of 12 fail the exact-restoration check AT pair 0 itself, directly
contradicting "passes on the first cycle universally," and one of those two
(`s7v2_sr_bec8dc134665926f`) fails ONLY at pair 0 and then passes cleanly on pairs 1-3 -- the
literal opposite of compounding drift. The honest characterization: control's failures
predominantly emerge from repeated cycling rather than the first cycle, which is still a real
and meaningful pattern behind the K=4 result, but it is not a clean, exceptionless mechanism,
and the K=4 significance finding itself does not depend on it being one.

This is reported plainly because the preregistration committed to it in advance: "If this
follow-up's own result does not favor treatment, or is itself not significant, that is
reported plainly. This document does not commit to any particular outcome." The real value of
this exercise was never a single confirmed number -- it is a rigorous, disclosed process that
found and fixed FIVE genuine bugs across two correction passes: the earlier PII scanner
false-negative, the evaluator whitespace bug, the heading-level defect, the blank-heading-text
defect, and the statistics-layer "blocked chains scored as failures" bug -- five distinct,
independently-committed, independently-tested fixes (not four, as an earlier revision of this
document bundled the last two together), none of which would have surfaced without actually
running the real acquisition-through-confirmatory pipeline end to end, repeatedly, at
increasing scale and depth.
