# PAPER-S9: formatting-compliance pilot (v1)

Status: exploratory, not confirmatory. Three hand-authored fixtures, one trial per arm each
(6 real `claude` CLI trials total, updated 2026-09-06 to add a 3rd fixture covering a
different violation dimension) -- not part of the locked PAPER-S7 corpora, families, or
statistics. Purpose: test whether a genuinely different task SHAPE -- read-only diagnosis
("find every formatting violation") rather than edit/inverse -- shows any capability gap
between generic-tool reasoning and Meridian's bounded audit primitives.

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

## Result

All 6 trials matched ground truth, manually spot-checked against the actual report text (not
just the automated grader):

| Fixture | Arm | Correctly identified? |
|---|---|---|
| violations (2 real violations) | control | Yes -- both violations named, with correct XML detail |
| violations (2 real violations) | treatment | Yes -- both violations named, matching the tool's exact expected/actual values |
| compliant (0 violations) | control | Yes -- explicitly confirmed compliant on both dimensions, no hallucination |
| compliant (0 violations) | treatment | Yes -- explicitly confirmed compliant on both dimensions, no hallucination |
| numbering (duplicate + gap) | control | Yes -- named both equations sharing "(1)", named 2 as the missing number |
| numbering (duplicate + gap) | treatment | Yes -- same, plus a concrete renumbering fix suggestion |

Control's reports came from genuinely reading the raw OOXML (quoting the literal
`<w:jc w:val="left"/>` attribute, for instance, or tabulating all three equations' numbers
directly from the table cells) -- not a guess. Treatment's reports came from actually calling
`audit_equation_style` (one response also cross-checked with `get_document_review`) and
reporting its structured findings accurately.

## Honest conclusion

At this sample size (n=3 documents, 1 trial per arm each), **no capability gap between arms
on this task, across three distinct violation classes** (single-equation alignment,
single-equation punctuation, and cross-equation numbering consistency). This is not a claim
that none exists -- three documents is nowhere near enough data to support any statistical
claim, and this was never intended as one. It is a clean, now twice-replicated signal that the
task shape itself works (the harness correctly captures and grades a diagnosis task, not just
edit tasks) and that genuine, hand-verified violations were neither missed by either arm nor
hallucinated by either arm on the compliant fixture. Scaling this to a real sample -- more
documents, and figure/table spacing once `audit_figure_table_spacing` stabilizes in the shared
repo -- is the natural next step, not attempted here.
