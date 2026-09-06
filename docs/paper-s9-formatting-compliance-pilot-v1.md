# PAPER-S9: formatting-compliance pilot (v1)

Status: exploratory, not confirmatory. Four fixtures (three hand-authored, one a real
organically-occurring document), one trial per arm each (8 real `claude` CLI trials total,
updated 2026-09-06 twice: first to add a 3rd fixture covering a different violation
dimension, then to add a 4th, organic fixture) -- not part of the locked PAPER-S7 corpora,
families, or statistics. Purpose: test whether a genuinely different task SHAPE -- read-only
diagnosis ("find every formatting violation") rather than edit/inverse -- shows any
capability gap between generic-tool reasoning and Meridian's bounded audit primitives.

**Headline result, added in this update:** the organic fixture did not just replicate "no
gap" -- it surfaced a real, previously-undiscovered bug in `audit_equation_style` itself,
found specifically BECAUSE control and treatment disagreed on a real document. See "A second,
more consequential bug" below. The bug is now fixed, tested, and the trial re-run to confirm.

## Why this needed its own harness

PAPER-S7's entire architecture is forward-edit + inverse-edit pairs graded by comparing the
output document's structure against ground truth. A compliance check never mutates the
document at all, so it doesn't fit that model: there is no "inverse," and grading has to
compare each arm's own free-text report against known ground truth, not document structure.
`tools/formatting_compliance_pilot.py` reuses `claude_pair_runner.run_trial` directly for the
exact same arm-isolation machinery every other trial in this project relies on (control:
generic Read/Write/Edit/Bash, zero Meridian MCP access; treatment: exactly one bounded tool,
`audit_equation_style`, zero generic editing tools) -- only the grading step is new.

The product capability this probes is real and already exists: `resolve_style_policy` plus
`audit_equation_style` (alignment, trailing punctuation, and numbering-consistency checks for
equations) and a sibling, `audit_figure_table_spacing`, with six named, source-cited venue
profiles (MST thesis, Drexel thesis, Chicago/Turabian, ASCE, JCSHM Springer, generic journal).
**This pilot only covers the equation-style audit** -- while scoping a figure/table-spacing
fixture, `audit_figure_table_spacing`/`FIGURE_TABLE_SPACING_PROFILES` were found to have been
removed from the file entirely mid-session (this repo's working tree is actively shared with
other concurrent sessions; see `feedback_shared_repo_commit_hygiene.md` in this project's
memory), too volatile to build a fixture against right now.

## Fixtures

Both verified directly against the real `docs_intel.audit_equation_style` function before any
trial was run (same discipline as every hard-authored PAPER-S7 fixture):

1. `hard_equation_style_violations.docx` -- one standalone display equation, deliberately
   left-aligned (violates the default policy's `center` expectation) with no trailing
   punctuation (violates `equation_punctuation_required`). Confirmed: exactly 2 findings,
   `misaligned_equation` and `missing_trailing_punctuation`.
2. `hard_equation_style_compliant.docx` -- a negative control: one standalone display
   equation, correctly centered, with a trailing period. Confirmed: 0 findings. Tests for
   FALSE POSITIVES (does either arm hallucinate a violation that isn't there?), not just
   recall on real ones -- a dimension the violations-only fixture alone couldn't measure.
3. `hard_equation_numbering_violations.docx` -- three table-numbered equations
   (`<w:tbl>` rows pairing an `<m:oMath>` cell with a parenthesized number cell, the
   `"(1)"`/`"(2a)"` pattern), numbered `(1)`, `(1)`, `(3)`: a genuine duplicate (two
   equations share number 1) AND a genuine gap (number 2 never appears) in the same
   fixture. A completely different violation CLASS from the first two fixtures --
   consistency across multiple equations, not a single equation's own formatting.
   Confirmed: exactly 2 findings, `duplicate_equation_number` and `equation_number_gap`.
4. **Organic, not hand-authored** -- candidate_id `9c3a58ce12b73d20` from the real
   PAPER-S6 cleared organic-equation corpus (topic-sampled, PII-screened, admitted; see
   `docs/paper-s6-organic-omml-round2-3-result-v1.md`). A real document with two display
   equations. Ground truth, confirmed directly against the raw XML: **both** equations are
   left-aligned (violates the default `center` policy) and both are followed by a
   parenthetical annotation ending in `)` (violates required trailing punctuation) --
   4 real violations total, not 2. This ground truth was not obvious up front; see the next
   section for how it was actually established.

## A methodology bug found and fixed along the way

The first grading pass flagged both arms as "wrong" on the compliant fixture, which looked
like a real false-positive-hallucination finding until the actual report text was read
directly: both arms had explicitly written "No violations found" / "fully compliant on both
dimensions" -- correct, not hallucinated. The bug was in the grader, not the models: a naive
keyword check for "does the report mention alignment/punctuation at all" can't distinguish
"this IS a violation" from "confirmed compliant, no violation here," since a correct report
necessarily discusses both dimensions either way to confirm them. Fixed by checking for an
explicit compliance claim (phrases like "no violations", "fully compliant") rather than mere
topic mention. Documented here rather than silently corrected, per this project's standing
"never quietly patch around a surprising result" discipline -- this project has now made a
version of this exact class of mistake (grading logic that can't tell two outcomes apart)
several times across different tools, and it is worth a reader's attention every time.

## A second, more consequential bug: a real defect in the tool itself

The first pass at the organic fixture did NOT look like the first three. Control (reading the
raw XML by hand) reported both equations as violating both rules. Treatment (calling
`audit_equation_style`) reported only equation 0 (`para_id 3D6EA19F`) -- confirmed by directly
inspecting the tool's actual JSON output, not just the model's summary. The two arms
genuinely disagreed about the state of a real document, which is exactly the situation this
project's standing rule -- always investigate a surprising result before writing it down --
exists for.

Dumping the raw XML for both equations' paragraphs side by side showed they are structurally
near-identical: neither has an explicit `w:jc` (both default to left) and both end in a
parenthetical annotation (`" (pre-OLRAC original)"` / `"(post-OLRAC correction)"`). The one
real difference: equation 1's paragraph (`para_id 65A25EA5`) has a
`<w:bookmarkStart w:name="_Hlk531118477"/>` immediately before `<m:oMath>` and a
`<w:bookmarkEnd/>` immediately after it -- an artifact Word writes automatically whenever a
cross-reference or an old-format hyperlink target lands near that spot in the document.

Reading `audit_equation_style`'s own source (`docs_intel.py`) confirmed the mechanism exactly:
its "is this a display equation, not prose mixed with an equation" check only excluded
`w:pPr` from the set of elements allowed to precede `<m:oMath>` -- a `w:bookmarkStart`, which
renders nothing, was counted as disqualifying "prose," silently skipping the ENTIRE equation
(both the alignment and the punctuation check) via the same code path meant for genuine
inline equations like "Einstein: E=mc^2". A small, direct, non-mutating Python script that
reproduced the function's own `siblings`/`top_idx`/`preceding` computation against the real
file proved this conclusively before any fix was written -- printing the exact sibling tag
order confirmed `w:bookmarkStart` lands in `preceding` and triggers the skip.

**This means the first read of this fixture had it backwards.** Control was objectively
correct; treatment's structured, tool-based report was objectively wrong -- not because the
model reasoned worse, but because the bounded tool it was given had a real defect that its
own clean JSON output gave no hint of. This is the opposite of every other trial in this
pilot (and of PAPER-S7 generally), where the tool-based arm's structured output was reliably
*more* accurate than free-form reasoning over raw XML.

**Fix:** excluded a small, confirmed set of zero-width OOXML markup -- `bookmarkStart`,
`bookmarkEnd`, `commentRangeStart`, `commentRangeEnd`, `proofErr` -- from the disqualifying
"preceding content" check, alongside `w:pPr`. A regression test also confirms genuine prose
before a bookmarked equation still correctly excludes it (the fix narrows the false
disqualification; it does not make the check vacuous). See
`extensions/meridian-docs/tests/test_docx_equation_style_audit.py`.

**Re-run after the fix:** treatment was re-run against the same organic document with the
patched tool. Its report now names both equations with all 4 real violations, matching
control's report exactly (spot-checked against the actual report text, not just the grader's
verdict):

> "The document contains **2 equations**, and **both violate both parts of the rule** (4
> violations total)... Equation 2 (para_id `65A25EA5`, ordinal 1) — Alignment violation ...
> Punctuation violation ..."

## Result

All 8 trials now match ground truth, manually spot-checked against the actual report text
(not just the automated grader) -- including the organic fixture's treatment arm, which only
reached a correct answer after the tool bug above was found and fixed:

| Fixture | Arm | Correctly identified? |
|---|---|---|
| violations (2 real violations) | control | Yes -- both violations named, with correct XML detail |
| violations (2 real violations) | treatment | Yes -- both violations named, matching the tool's exact expected/actual values |
| compliant (0 violations) | control | Yes -- explicitly confirmed compliant on both dimensions, no hallucination |
| compliant (0 violations) | treatment | Yes -- explicitly confirmed compliant on both dimensions, no hallucination |
| numbering (duplicate + gap) | control | Yes -- named both equations sharing "(1)", named 2 as the missing number |
| numbering (duplicate + gap) | treatment | Yes -- same, plus a concrete renumbering fix suggestion |
| organic (4 real violations across 2 equations) | control | Yes -- read the raw XML directly, caught both equations from the start |
| organic (4 real violations across 2 equations) | treatment | **No, on the first run** -- missed equation 1 entirely because of a real `audit_equation_style` bug (see above). **Yes, after the fix** -- re-run with the patched tool names all 4 violations correctly. |

Control's reports came from genuinely reading the raw OOXML (quoting the literal
`<w:jc w:val="left"/>` attribute, for instance, or tabulating all three equations' numbers
directly from the table cells) -- not a guess. Treatment's reports came from actually calling
`audit_equation_style` (one response also cross-checked with `get_document_review`) and
reporting its structured findings accurately -- accurately relative to what the tool actually
returned, which on the organic fixture's first run was itself wrong.

## Honest conclusion

At this sample size (n=4 documents, 1 trial per arm each, one re-run after a fix), the result
is more nuanced than "no capability gap." On three hand-authored fixtures across three
distinct violation classes (single-equation alignment, single-equation punctuation, and
cross-equation numbering consistency), both arms performed identically. On the one REAL,
organically-occurring document -- the only fixture not constructed to already fit the tool's
assumptions -- **treatment's bounded tool had a genuine, previously-undiscovered bug that
control's unbounded reasoning caught and treatment's own report did not**. That is a real,
if narrow, capability-relevant finding: a bounded audit tool is only as good as its own
correctness, and a real document surfaced an edge case (a bookmark wrapping an equation) that
none of the three hand-authored fixtures happened to exercise. The bug is now fixed and
verified end-to-end, so this specific gap no longer exists -- but the broader lesson is that
hand-authored fixtures, however carefully verified against the tool's current behavior, cannot
substitute for testing against real documents, which contain incidental structure (bookmarks,
comments, tracked changes, and similar Word artifacts) fixtures don't naturally include.
Sample size (n=4) still cannot support a statistical claim, and this was never intended as
one. Scaling this to a real sample -- more organic documents in particular, since that is
where the one real finding came from, and figure/table spacing once
`audit_figure_table_spacing` stabilizes in the shared repo -- is the natural next step, not
attempted here.
