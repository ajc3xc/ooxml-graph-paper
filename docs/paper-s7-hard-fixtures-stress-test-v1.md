# PAPER-S7: hard/ambiguous fixture stress test (v1)

Status: exploratory, not confirmatory. Three hand-authored fixtures were built specifically
to probe genuine structural ambiguity that the curated benchmark corpora are unlikely to
contain by chance -- not part of the locked v1/v2 corpora or their statistics, and this
document is not pooled with any confirmatory claim. Manifest:
`manifests/paper-s7-hard-fixtures-v1.json`. Purpose: find real bugs and real capability gaps
by deliberately trying to break the harness, rather than waiting for organic corpus data to
happen to hit them.

## The three fixtures

1. **Duplicate/ambiguous anchor text**: two paragraphs share an identical 77-character
   opening. `resolve_body_anchor` deterministically anchors treatment to one specific
   paragraph regardless; a control-arm agent given only that text snippet has to
   disambiguate between two candidates that look identical for the first 77 characters.
2. **Bibliography needing alphabetical insertion**: an existing "References" heading already
   contains two entries ("Adams" and "Zimmerman"); a new "Marker, Pilot" entry should land
   alphabetically between them, not merely be appended.
3. **Duplicate section headings**: two headings read identically ("Overview"), each
   belonging to a different top-level module, stressing whether section-reorder's own
   destination-heading resolution can be confused by a genuine name collision.

Each fixture was verified directly against the actual harness resolver functions before use
(not assumed to produce the intended ambiguity). **Corrected 2026-09-06**: an earlier revision
of this document claimed fixture 1's first draft "did not land where intended" and was
corrected via `tools/docx_anchor_prober.py` changes around 2026-09-03/04 -- an independent
pre-publication audit found no support for this anywhere: `resolve_body_anchor` has been
unchanged since it was written (commit `59d5fe7`, 2026-08-30) and has no dedicated regression
test at all. The commits actually in that file from 2026-09-03/04 (`8c7ae16`, `278d9cc`) fix a
completely different function, `resolve_section_reorder_plan`, backing fixture 3, not fixture
1. Removed the unsupported claim rather than repeat it.

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

### A real, previously-undiscovered product limitation (found, and now fixed)

Fixture 2 (bibliography alphabetization) produced a clean, striking result:

| Arm | Behavior |
|---|---|
| Control (generic tools) | Correctly inserted the new entry alphabetically between "Adams" and "Zimmerman" |
| Treatment (`insert_bibliography_entry`) | Appended the new entry at the end, after "Zimmerman", ignoring alphabetical order |

`insert_bibliography_entry` had no alphabetical-insertion logic -- it appended. A capable
generic-tool agent, given full document visibility and no such constraint, reasoned its way
to the correct position. This is a genuine, real gap the standard S7 grading (which only
checks that the entry's title text appears as its own paragraph, not its position) would
never surface, since position was never part of what was graded.

**Update (2026-09-04):** originally reported here as a finding deliberately left unfixed,
on the reasoning that "how should bibliography entries be ordered" was a real product design
question (by which field, locale-aware collation, numbered vs. alphabetical styles) needing
deliberate input rather than a guessed implementation. On reflection that caution was
overstated: `insert_bibliography_entry` already formats every entry as an APA 7th-edition
reference (`format_apa_reference`), and APA's own convention -- alphabetical by the leading
author string (title when there is no author), ties broken by year -- is not actually
ambiguous once the tool has already committed to a single citation style. Every existing
entry's own formatted text already carries the correct sort key (it always starts with
`"{author} ({year}). {title}."`), so no separate author/title field needed extracting.
Fixed in the parent repo (commit `4c7569de`, new `_alphabetical_insert_pos` helper) and
covered by 4 new tests in `tests/test_meridian_docs_bibliography_write.py` (insert-before,
insert-between two entries reproducing this exact Adams/Marker/Zimmerman scenario,
insert-after, and same-author year tie-breaking). See
`docs/paper-s8-final-evidence-v1.md` section 0 (defect 5) for the full evidence-package
writeup.

### Fixture 1 (duplicate anchor text): no result to report

**Corrected 2026-09-06**: an earlier revision of this document attributed fixture 1's
inconclusive status to "real Word-COM render-gate contention" during citation and equation
trials. An independent pre-publication audit found no raw run data anywhere for fixture 1's
citation or equation trials -- no chain-result.json, no slice-manifest entry, nothing beyond
the source fixture file itself -- so there is no evidence these trials were ever actually run.
The claimed mechanism was also only ever possible for half of what it described: citation's
`insert_citation`/`remove_citation` do pure stdlib zipfile/XML manipulation with no Word-COM
interaction at all, so render-gate contention could never have affected citation specifically,
only equation. Rather than repeat an unsupported explanation, this is disclosed plainly:
fixture 1's specific ambiguity was never actually exercised under real trial conditions here.
Worth running for the first time as a follow-up, not reported as a result in this document.

## Honest scope

This is three fixtures, run once, at real but modest scale (24 chains total). It is not a
systematic study of ambiguity handling and should not be read as one. Its value is
demonstrated directly by what it found: a real defect that had already contaminated
published numbers, and a real, previously invisible product limitation -- exactly the kind
of thing organic corpus documents, by construction, are less likely to contain (the curated
DocOps corpus was built for realistic single tasks, not deliberately pathological edge
cases).
