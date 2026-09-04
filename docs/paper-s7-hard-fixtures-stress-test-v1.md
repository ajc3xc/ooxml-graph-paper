# PAPER-S7: hard/ambiguous fixture stress test (v1)

Status: exploratory, not confirmatory. Three hand-authored fixtures were built specifically
to probe genuine structural ambiguity that the curated benchmark corpora are unlikely to
contain by chance -- not part of the locked v1/v2 corpora or their statistics, and this
document is not pooled with any confirmatory claim. Manifest:
`manifests/paper-s7-hard-fixtures-v1.json`. Purpose: find real bugs and real capability gaps
by deliberately trying to break the harness, rather than waiting for organic corpus data to
happen to hit them.

## The three fixtures

1. **Duplicate/ambiguous anchor text**: two paragraphs share an identical 80-character
   opening. `resolve_body_anchor` deterministically anchors treatment to one specific
   paragraph regardless; a control-arm agent given only that text snippet has to
   disambiguate between two candidates that look identical for the first 80 characters.
2. **Bibliography needing alphabetical insertion**: an existing "References" heading already
   contains two entries ("Adams" and "Zimmerman"); a new "Marker, Pilot" entry should land
   alphabetically between them, not merely be appended.
3. **Duplicate section headings**: two headings read identically ("Overview"), each
   belonging to a different top-level module, stressing whether section-reorder's own
   destination-heading resolution can be confused by a genuine name collision.

Each fixture was verified directly against the actual harness resolver functions before use
(not assumed to produce the intended ambiguity) -- see git history for
`tools/docx_anchor_prober.py` around 2026-09-03/04 for the iteration this took (fixture 1's
first draft did not land where intended, since `resolve_body_anchor` picks by document
position, not content; corrected before running anything for real).

## What this found

### A real, previously-undiscovered harness defect (fixed, and it changed already-published numbers)

Fixture 3 exposed that `resolve_section_reorder_plan` picked its destination heading with no
awareness of heading level, producing a logically incoherent plan on documents with nested
heading structure. This was not just a toy-fixture problem: a direct audit of the real,
already-run v1 and v2 corpora found the identical defect in **4 of 48 v2 follow-up
documents** (zero in v1). Fixed in `tools/docx_anchor_prober.py` (commit `8c7ae16`). Full
writeup, including the corrected statistics: `docs/paper-s7-section-reorder-followup-result-v1.md`.

This is the headline finding from this exercise: a hand-authored fixture built purely to
probe an interesting edge case surfaced a real defect that had been silently degrading
already-published confirmatory results.

### A real, undiscovered product limitation (documented, not fixed here)

Fixture 2 (bibliography alphabetization) produced a clean, striking result:

| Arm | Behavior |
|---|---|
| Control (generic tools) | Correctly inserted the new entry alphabetically between "Adams" and "Zimmerman" |
| Treatment (`insert_bibliography_entry`) | Appended the new entry at the end, after "Zimmerman", ignoring alphabetical order |

`insert_bibliography_entry` has no alphabetical-insertion logic -- it appends. A capable
generic-tool agent, given full document visibility and no such constraint, reasoned its way
to the correct position. This is a genuine, real gap the standard S7 grading (which only
checks that the entry's title text appears as its own paragraph, not its position) would
never surface, since position was never part of what was graded.

This is reported as a finding, not fixed here: unlike the section_reorder defect above
(which had one unambiguous correct behavior -- do not treat a child heading as a sibling
destination), "how should bibliography entries be ordered" is a real product design
question (by which field -- author surname, year, citation key? locale-aware collation?
numbered vs. alphabetical styles both exist in real usage) that deserves deliberate design
input, not a guessed implementation bundled into a benchmark session.

### Fixture 1 (duplicate anchor text): inconclusive under real trial conditions

Citation and equation trials against this fixture were affected by real Word-COM
render-gate contention from running concurrently with other jobs during this same
session (see the equation family's own smoke-test writeup for the render-gate finding this
overlaps with) -- the specific ambiguity this fixture targets was not cleanly exercised.
Worth re-running in isolation as a follow-up, not reported as a result here.

## Honest scope

This is three fixtures, run once, at real but modest scale (24 chains total). It is not a
systematic study of ambiguity handling and should not be read as one. Its value is
demonstrated directly by what it found: a real defect that had already contaminated
published numbers, and a real, previously invisible product limitation -- exactly the kind
of thing organic corpus documents, by construction, are less likely to contain (the curated
DocOps corpus was built for realistic single tasks, not deliberately pathological edge
cases).
