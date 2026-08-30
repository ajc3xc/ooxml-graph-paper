# thesis-p30 regression fixture: section-terminology correction (v0)

Sprint item: `f9194db0-3b32-4207-b875-c776c6e52d73` -- "MS thesis page-30 formatting
fixture: section terminology correction and regression verification" (track
`thesis-regression-fixtures`).

Status: **one real fixture built, edited, round-tripped, and Word-verified end to
end; overall_pass=true.** This is a single regression fixture, not a suite. No
other fixtures exist yet under this track (see "What this does not cover" below).

## Why this took real investigation

The sprint item's notes describe the required edit precisely ("replace incorrect
'Chapter 5' terminology with 'Section 5' ... page 30 ... while preserving the
surrounding sentence, formatting, paragraph identity, fields/bookmarks/references,
and unrelated document content") but do not point at a file. Its own escape hatch
is explicit: *"If the current source artifact is unavailable, preserve the
requirement as blocked rather than inventing the original thesis content."* So
before writing anything, the actual source had to be located and confirmed real.

What was checked, in order, all read-only:
- `recovery/codex-graph-paper-thread-recovered.md` and `recovery/codex-graph-paper-last-3-hours.md`
  (untracked local session transcripts) confirm the "MS thesis" referenced across
  this project's docs is the user's own real Missouri S&T MS thesis, used for
  months as the historical development case for Meridian Docs -- not a public
  dataset document. (The `tier2-omegause-*-thesis*` files under
  `E:\MeridianData\ooxml-graph-paper\gold\tier2\` are unrelated: they are public
  OmegaUse-OfficeVal template documents, not the user's thesis.)
- No file under the `ooxml-graph-paper` repo or its `E:\MeridianData\ooxml-graph-paper`
  data tree contains the user's actual thesis content.
- The real thesis project was located at `C:\Users\13144\Documents\Masters_Thesis\`
  -- a separate, unrelated git repo, under **active, same-day editing** (dozens of
  `manual_review_v*` iterations dated 2026-08-29/30, including AI figure-callout
  review comments from a different agent, author `Codex`, in
  `..._v44_figure_callout_review_comments_20260830.docx`). This directory was
  treated as **strictly read-only** throughout: nothing under `Masters_Thesis\`
  was ever opened for writing, and the true source file's SHA-256 was verified
  identical before and after all work (see below).
- A raw byte-level scan (`[Cc]hapter\s*5\b` / `\b[Cc]hapters\b` against every
  `word/document.xml` in `Masters_Thesis\staging\documents\`, 120 `.docx` files)
  found the literal defect in exactly **one** file:
  `Masters_Dissertation_Report_Defense_staging_v0_source_locked.docx` -- the
  pipeline's own labeled starting point ("v0", "source_locked") before the
  ~58 rounds of manual review that followed. None of the later reviewed versions
  (`v44`, `v57b`, `v58`, all checked directly) still contain the defect, nor did
  their `comments.xml` (where present) mention it -- the `Codex` comments found
  there are unrelated (missing figure-callout references, `FC-001..FC-047`). So
  the specific wording this item describes exists in the real, on-disk **v0
  baseline draft**, not in whatever the thesis looks like right now.
- Word COM (`win32com`, a **fresh `DispatchEx` instance**, never `Dispatch` --
  so this never attached to any other session's running Word process) confirmed
  the defect sentence lands on **page 30 of 216** in that v0 draft, matching the
  item's "page 30" description exactly.

Source file (read-only; never modified by this work):
```
C:\Users\13144\Documents\Masters_Thesis\staging\documents\Masters_Dissertation_Report_Defense_staging_v0_source_locked.docx
SHA-256: 38d21c00759df44b68e72ca3f5441135223c5113838e83ed5dcfc31eee7c617f  (size 21,604,715 bytes)
```
Verified identical (same SHA-256) both immediately after copying and again after
all fixture work below was complete.

## The actual defect (paragraph 197, "THESIS ORGANIZATION", page 30)

One run (of 17) inside one paragraph reads:

> "...Section 4 gives the experimental setup, specifically evaluation for
> centerline geometry and width comparison. **Chapter 5** presents the results
> and analysis for the centerline extraction, and width estimation methods
> compared to the baselines, as well as discussing the findings of results,
> weaknesses, and implications from the method. Section 6 concludes the
> thesis..."

Every other section reference in that same roadmap sentence ("Section 2",
"Section 3", "Section 4", "Section 6") already says "Section" -- "Chapter 5" is
the one leftover term from before this thesis was restructured from
chapter-numbered to section-numbered. There is no separate bare "chapters"
(plural) instance anywhere in the document needing the same fix; the only other
"chapter" occurrences in the whole package are two unrelated bibliography
citations to external FHWA documents ("Chapter 7 - NHI-05-037...", "Chapter 4.
Cracks - Petrographic Methods...") that must **not** be touched.

## What was built

Everything lives under the local data drive, not the git repo, matching this
project's existing fixture/gold storage convention:
```
E:\MeridianData\ooxml-graph-paper\fixtures\thesis-p30\
    build_and_verify_fixture.py   -- the harness (source of all evidence below)
    thesis-p30-base.docx          -- exact copy of the real v0 source (hash above)
    thesis-p30-forward.docx       -- base + the "Chapter 5" -> "Section 5" edit
    thesis-p30-inverse.docx       -- forward + the reversal edit ("Section 5" -> "Chapter 5")
    manifest.json                 -- full machine-readable receipt (hashes, checks, Word receipts)
```

**Why the harness script is not under `ooxml-graph-paper/tools/`:** that
directory was held under a live Meridian sprint resource lock (first by session
`paper-s21-word-com-lifecycle`, then by `paper-s20-claude-broker-harness`) for
the entire duration of this work -- confirmed live via `list_sessions` and
`get_file_claims`, not assumed. `claim_sprint_item` for this item was attempted
first as instructed and rejected with `RESOURCE_LOCKED` on
`file:ooxml-graph-paper/tools`. Rather than write into a directory another live
session owns, the harness was kept self-contained next to its own fixture data
(the item's other declared resource, `file:E:/MeridianData/ooxml-graph-paper/fixtures`,
was never locked). The item was consequently **never formally claimed**
in the Meridian sprint board -- see "Claim status" below.

### The edit itself

Surgical, not a document-wide find/replace: the harness locates the one `<w:r>`
run whose text contains `"Chapter 5"`, asserts it is the only run in the
paragraph containing that token and that the token appears exactly once inside
one `<w:t>` node, and rewrites only that node's text
(`target_t.text = target_t.text.replace("Chapter 5", "Section 5", 1)`) via
`lxml`, leaving the run's formatting (`rPr`), the other 16 runs in the
paragraph, and every other part of the package byte-for-byte as produced by
`python-docx`'s own re-serialization of the unchanged parts.

### Verification performed (all in `manifest.json`, `overall_pass: true`)

| Check | Result |
|---|---|
| Exactly one body paragraph's text changed (base vs. forward) | true (paragraph 197 only) |
| The change is exactly `"Chapter 5"` -> `"Section 5"`, nothing else in that paragraph | true |
| Headers/footers/footnotes/endnotes text unchanged | true (no diffs in any of those sources) |
| Bookmark count unchanged (`w:bookmarkStart`) | true (28 -> 28) |
| Field count unchanged (`w:fldSimple`, `w:fldChar`) | true (0 -> 0, none present) |
| Paragraph count unchanged | true (1186 -> 1186) |
| Negative control: `"Chapter 7"` citation untouched | true (1 -> 1) |
| Negative control: `"Chapter 4"` citation untouched | true (1 -> 1) |
| Run count + run formatting (bold/italic/font/size) preserved on the edited paragraph | true |
| Inverse (reversal) round-trips to base text exactly, across all sources | true |
| Inverse round-trips run formatting exactly | true |
| OOXML package structural validation (zip integrity, required parts present, `document.xml` / `[Content_Types].xml` well-formed) -- forward | true, no problems |
| OOXML package structural validation -- inverse | true, no problems |
| Word COM open receipt -- base (fresh `DispatchEx`, read-only open, then closed unsaved) | opened OK, found `"Chapter 5 presents the results"` on **page 30 of 216** |
| Word COM open receipt -- forward | opened OK, found `"Section 5 presents the results"` on **page 30 of 216** |
| Word COM open receipt -- inverse | opened OK, found `"Chapter 5 presents the results"` on **page 30 of 216** |

Page count is identical (216) across base/forward/inverse -- expected, since
`"Chapter"` and `"Section"` are both 7 characters, so this specific edit cannot
have shifted pagination even in principle; that was confirmed rather than
assumed.

Hashes (from `manifest.json`):
```
base:     38d21c00759df44b68e72ca3f5441135223c5113838e83ed5dcfc31eee7c617f  (21,604,715 bytes)
forward:  1e36093b789e27863226ce0c120ed64f65aa6f825cb49125f6f0a4129348a8a0  (20,829,779 bytes)
inverse:  85eb79805308a75d3ded734b4a9744c4a29d86cf5c114655938a294ce23c0f15  (20,829,784 bytes)
```
(forward/inverse are smaller than base because `python-docx` re-serializes and
recompresses the whole package on save -- this is a known, harmless side effect
of round-tripping through `python-docx`'s `Document.save()`, not evidence of
lost content: every text/structure check above passed, including the full
paragraph-by-paragraph diff across body, headers/footers, footnotes, and
endnotes.)

All three Word COM opens used a **fresh `DispatchEx("Word.Application")`
instance per call**, `Visible=False`, `ReadOnly=True`, each explicitly
`Quit()`-ed in a `finally` block -- deliberately never `Dispatch()` (which can
attach to another session's already-running Word process). One `WINWORD.EXE`
process was observed still running after this script finished; given multiple
other concurrent sessions in this sprint are independently exercising Word COM
(e.g. `paper-s21-word-com-lifecycle`) and the user's own thesis is under live
same-day editing, that process cannot be attributed to this script with
certainty (this script's own three instances each called `Quit()`), and it was
left alone rather than killed, since it may belong to someone else's live work.

## Claim status (honest gap)

This item could **not** be formally claimed via `claim_sprint_item`: it declares
`touches_resources: ["file:ooxml-graph-paper/tools", "file:E:/MeridianData/ooxml-graph-paper/fixtures"]`,
and `file:ooxml-graph-paper/tools` was held by another live session for the
entire work window (verified twice, ~10 minutes apart, by two different
holders). The work above never wrote to `ooxml-graph-paper/tools`, so no
conflicting edit occurred, but the sprint-board claim itself was never
acquired. `complete_sprint_item` is being called directly against the still-
`pending` item as a result.

## Independent verification

Not performed. `require_verification` is set on this item; completing it
requires a genuinely separate verifier session (a fresh, no-memory subsession
inspecting the change with read-only tools) and this execution was a single
bounded agent run with no such subsession spawned. This is recorded honestly
rather than filing a self-verification under a different label.

## What this does not cover

- This is **one** fixture. The item's boilerplate about "iterative fix-and-retest
  cycles over the full fixture suite" presumes a `thesis-regression-fixtures`
  suite with a shared runner; no such suite or runner exists yet anywhere in
  this repo or in `E:\MeridianData\ooxml-graph-paper\fixtures\` -- this is the
  first fixture under that track. Building a shared multi-fixture runner (e.g.
  under `tests/`) is future work, out of this item's bounded scope, and was not
  attempted here.
- The fixture exercises a hand-written `python-docx`/`lxml` edit, not Meridian
  Docs' own paragraph-editing tool (`update_paragraph` / the `meridian-docs`
  MCP surface). Whether Meridian Docs' own editor would make this same edit
  with the same discipline (localized, formatting-preserving, no collateral
  changes) was not tested here and is a natural next step for this track.
- The real, live thesis document itself was **not** edited, and this fixture
  makes no claim about the current state of that document (which has moved on
  through ~58 further review iterations since the `v0` baseline used here, and
  no longer contains this specific defect).
