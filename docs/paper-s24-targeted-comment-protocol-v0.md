# PAPER-S24: targeted native Word-comment placement under repeated,
lookalike-cluster targeting pressure (protocol v0)

Status: **lock (2026-09-24).** Originally drafted "not locked" pending the one
genuinely new, load-bearing artifact this family depends on: a real
`resolve_comment_targeting_clusters` resolver, actually built and run against the
three real corpus files rather than estimated from ad hoc exploratory scripts. That
precondition is now resolved -- see section 1.2b's dated addendum -- along with the
other two section-8 preconditions gating lock specifically (corpus SHA-256
re-verification; a live re-check that no comment-removal/resolve/edit tool has
appeared since design). The smoke-test precondition (section 8's own separate item)
still gates moving to validation/primary trials, not this design lock, exactly
mirroring `docs/paper-s23-respec-cascade-protocol-v0.md`'s own precedent (that
document's own 1.2a addendum locked on resolved corpus-build preconditions, with its
harness build and smoke test following as later, post-lock phases).

This design was produced by comparing four independently-drafted candidate families
(precision-scale, accumulated-state, find-inverse, distractor-corpus), each with two
independent adversarial reviews, plus this session's own direct re-verification against
live source and the live corpus files (not merely a re-read of the candidates' claims).
It keeps: accumulated-state's fresh-process-per-step, K-distinct-never-repeated-target
chain shape (the element both of its reviews said should carry into synthesis "largely
as-is"); find-inverse's chain-position "keep survival" grading generalization of
`respec_cascade`'s Checkpoint-B idea; precision-scale's diagnosis of the
`locate_anchor`-table-cell-id/`insert_word_comment`-anchor-id format mismatch, with a
concrete, now-verified-buildable fix; and distractor-corpus's correctly-redirected,
real, measured finding that this corpus's actual duplicate-paragraph difficulty lives
in table rows, not body-paragraph "boilerplate" -- while replacing its specific,
demonstrably-broken digit-normalization clustering key with a corrected, two-regime
clustering rule derived from this session's own direct inspection of the real table
rows (section 1.2). It drops: any framing built around `flag_for_review` as a fallback
primitive (confirmed absent from the live manifest, and, newly found this session,
confirmed to unconditionally *refuse* table/table-cell anchors even if it becomes live
-- see section 0.3 -- so it cannot serve this family's actual difficulty locus either
way); precision-scale's single-continuous-session design (dropped in favor of the
paper's dominant fresh-process-per-step isolation convention); and every corpus
"showcase example" from any candidate that did not survive this session's own direct
re-scan (distractor-corpus's fabricated "Atomic x6" row values; accumulated-state's
"Mean Tan-Angle Error"/"Curvature RMS Ratio" examples, both of which this session
confirms sit inside the dissertation's duplicate-native-`w14:paraId` defect set).

## 0. Why this design, and what changed after this session's own direct verification

### 0.1 The user's own motivating aside is mechanistically explained, independently reconfirmed

`insert_highlighted_note(mode="comment")` delegates to `insert_word_comment`
(`docs_intel.py:20750`), which delegates its actual part-plumbing to
`_stage_word_comment` (`docs_intel.py:20619-20747`), read in full this session. Its
range-marker mechanics are unambiguous: `commentRangeStart` is spliced in immediately
after the target paragraph's `pPr` (or at index 0), `commentRangeEnd` is appended at
that same paragraph's own end, and the `commentReference` run follows -- all confined to
the one `paragraph` object the caller passed in. There is no code path that wraps more
than one paragraph. This directly explains the motivating observation that "comments
can't span multiple sequential sections as I scroll down": a native Word comment
produced by this tool surface is structurally incapable of spanning more than one
paragraph, by construction, not by bug. Every one of the four candidates verified this
identically; this session's own read confirms it a fifth time, independently.

### 0.2 No inverse exists -- confirmed exhaustively, one more time, with a corrected count

A `grep` this session for `def.*comment|remove_word_comment|resolve_comment|edit_comment`
against the live, 27,000+-line `docs_intel.py` returns exactly four functions:
`_find_para_by_id` (a generic paragraph resolver, not comment-specific -- matches only
because "comment" is not in it; excluded), `_next_word_comment_id`,
`_stage_word_comment`, `insert_word_comment`, and `flag_for_review`. **`flag_for_review`
is the one function two of precision-scale's and accumulated-state's own reviews found
that the candidates' own narrower `def.*comment` patterns missed** (it has no "comment"
in its name). None of the four are a removal, resolution, or edit of an existing
comment. `remove_docx_package_part` (`docs_intel.py:5191`, exposed as
`remove_package_part`) was read in full: line 5253 unconditionally refuses any
`part_name` not starting with `word/media/` -- `word/comments.xml` can never reach that
code path. **Conclusion, independently reconfirmed a fifth time: no safe inverse exists
today.** This family cannot use the forward-insert + own-inverse-remove shape every
other family in `paper/main.tex` uses, for the same structural reason `table_structural`
was dropped from `respec_cascade`'s rotation, and this document builds around that fact
rather than working around it silently (section 3).

### 0.3 A finding this session adds beyond all four candidates: `flag_for_review` would not help even if it went live

`flag_for_review` (`docs_intel.py:21751-21908`, `@mcp.tool()`-registered in
`server.py:2704`) is confirmed absent from this session's live connected
`meridian-docs` `ToolSearch` manifest (queried with several phrasings, e.g. "flag_for_
review resolve comment remove edit" -- no match), the same class of gap `respec_cascade`
found for `insert_table`/`remove_table`. But reading its body this session surfaces a
fact none of the four candidates' reviews fully drew out: when `anchor` is a
`locate_anchor`-style query dict, `flag_for_review` **unconditionally refuses** any
resolution whose `element_type` is `"table"` or `"table_cell"` (lines 21859-21869,
`"flag_for_review only supports paragraph/heading/caption anchors, not table or
table-cell targets"`). Since section 1.2 below shows this corpus's real, measured
difficulty signal is almost entirely inside table rows, `flag_for_review` -- even if it
becomes live -- is not a substitute primitive for this family's actual difficulty locus,
directly or as a future fallback. This closes an open question two candidates left
dangling ("if `flag_for_review` becomes available, this design should very likely
switch to it") with a verified "no."

### 0.4 The corpus's real difficulty signal, re-derived directly this session (not taken from any candidate's own numbers)

Every candidate's own corpus numbers were internally disputed by its two reviews (counts
ranging from 59 to 236 depending on methodology, one fabricated example, two
showcase examples that turned out to sit inside a real duplicate-`paraId` defect). Rather
than adjudicate between them, this session ran its own independent `zipfile`/
`ElementTree` scan (no `python-docx` dependency) directly against the three live,
hash-pinned files at `D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\`.
Results, and what they settle, are in section 1.2.

## 1. Corpus

### 1.1 Documents and standing preconditions

The same three hash-pinned, author-owned documents `respec_cascade` uses, per
`PROVENANCE.md` (dated 2026-09-20) and re-confirmed structurally this session:

| File | Total `<w:p>` (body+table) | Direct body-child `<w:p>` | `<w:tbl>` | Native `w14:paraId` coverage |
|---|---:|---:|---:|---:|
| `jcshm-manuscript.docx` | 616 | 395 | 42 | 616/616 (100%) |
| `jcshm-si.docx` | 2,325 | 541 | 76 | 2,325/2,325 (100%) |
| `masters-dissertation-defense.docx` | 3,630 | 1,155 | 131 | 3,630/3,630 (100%) |

**These totals differ from `PROVENANCE.md`'s own cited raw-XML figures** (578/2,200/
3,445), consistent with every candidate's own observation that `PROVENANCE.md`'s scan
appears not to descend into table cells while a full body+table `<w:p>` walk (used here,
and needed for this family, whose entire difficulty locus is inside tables) does. This
is flagged, not silently reconciled, exactly as `respec_cascade`'s own protocol flagged
its "785 vs 3,445" correction.

Re-verify the three SHA-256 pins in `PROVENANCE.md` immediately before any trial, per
that file's own stated reason (a sibling copy of the dissertation source is under
active, separate editing elsewhere on this machine) -- not yet re-done this session
(section 8).

### 1.2 The real, measured difficulty structure (settles the cross-candidate dispute)

**Negative finding, independently reconfirmed a third time (distractor-corpus's own
scan, its reviews' independent re-scans, and this session's own scan all agree):
zero exact-duplicate body paragraphs (len>15, count>=3) exist in any of the three
documents.** The "repeated boilerplate paragraph" / "near-identical numbered list item"
difficulty pattern the original task brief speculated about is **not a real feature of
this corpus**, full stop. Any design built on body-paragraph duplication (as
accumulated-state's original showcase examples were) is building on a pattern that does
not exist at the body-paragraph level in these three files.

**What is real, measured directly this session, and reproduces on a plain `<w:tbl>` row
walk: table first-cell ("label") text duplicated 3+ times.**

| Document | Duplicate-label groups (first cell, count>=3) | Largest groups |
|---|---:|---|
| `jcshm-manuscript.docx` | 4 | `Method` x4, `MAT (DSE)` x4, `MAT (Raw)` x4, `DT + Depth` x3 |
| `jcshm-si.docx` | 27 | `MAT (Raw)` x16, `MAT (DSE)` x15, `MAE`/`RMSE`/`\|Bias\|` x14 each, `Combined` x11, `Atomic` x10, `0-6px`/`6-12px`/`12-20px` x7 each |
| `masters-dissertation-defense.docx` | 30 | `MAT (Raw)` x20, `MAT (DSE)` x19, `MAE`/`RMSE`/`\|Bias\|` x14 each, `Combined` x13, `Atomic` x12, `DT` x10 |

Reading the actual rows behind these groups (not just counting label text) reveals
**two distinct, real difficulty regimes, not one** -- both directly relevant, neither
identified cleanly by any single candidate:

- **Regime 1, "within-table run":** the label repeats as several *consecutive* rows in
  ONE table, differentiated by an adjacent cell's value. Directly dumped this session,
  `jcshm-si.docx` table 66: `MAT (DSE)` labels rows 1-9 consecutively, differentiated
  only by the second cell ("Ceil Factor": 1, 2, 3, 4, 5, 6, 8, 10, 12) -- the label cell
  itself is byte-identical across all 9 rows. Table 4 shows a second within-table
  pattern: `0-6px`/`6-12px`/`12-20px`/`20-140px` group headers, each shared by 5-7
  sub-rows differentiated by a *categorical* method name (`DT`, `DT + Depth`,
  `MAT (DSE)`, `MAT (Raw)`, `EOB (DSE)`, `ESD (DSE)`, `PCA (DSE)`) in the second cell,
  not a digit. **This falsifies distractor-corpus's specific `resolve_lookalike_row_
  clusters` design, which keyed clustering on digit-normalizing the label cell itself**
  -- confirmed independently by both of that candidate's reviews and by this session's
  own dump: the varying value never lives in the label cell in either sub-pattern, so a
  resolver must cluster on (table index, literal label text) and treat *whichever
  adjacent cell actually varies* (numeric or categorical) as the human-realistic
  disambiguator, not assume digit-normalization of the label itself.
- **Regime 2, "cross-table scatter":** a short label recurs once (or a handful of
  times) *per table*, scattered across many *different*, structurally parallel small
  tables. Directly dumped this session: `Atomic` (paired with `Combined`/`All`-style
  sibling rows) appears in 7 distinct small tables in `jcshm-si.docx` alone, each table
  reporting a different metric set for the same three groups. **This is the pattern
  distractor-corpus's own "Atomic x6, values 0.5/130/90.77" worked example claimed but
  does not actually match** -- that specific example, with those specific values, does
  not exist in the corpus (confirmed independently by one of its own reviews and by this
  session); the real `Atomic` duplication is genuine but is cross-table scatter (which
  *table* is "the Atomic row," not which row within one table), a different
  disambiguation problem needing a different human-realistic locator (surrounding
  section/table-caption identity, not an adjacent-cell value).
- Manuscript's own `MAT (DSE)` x4 group, dumped this session, turns out to be **entirely
  Regime 2** (one occurrence each in four separate tables, `tbl38`/`39`/`40`/`41`) -- the
  manuscript has essentially no Regime-1 (within-table run) structure and only a thin,
  4-group Regime-2 pool. This is a real, measured, per-document asymmetry, carried into
  section 6 honestly rather than forced to parity.

**A real, previously-underweighted corpus hazard, independently reconfirmed:**
`masters-dissertation-defense.docx` has **236 duplicate native `w14:paraId` values**
shared across **472 of its 3,630 paragraphs (~13%)** -- a real, Word-invalid defect in
this specific file (`jcshm-manuscript.docx` and `jcshm-si.docx` have zero such
duplicates, confirmed this session). Reading `_find_para_by_id` (`docs_intel.py:3451-
3540`) confirms it **fails closed**: it raises `AmbiguousParagraphIdError` whenever the
requested `anchor_para_id` is a native `paraId` shared by more than one paragraph
anywhere in the document (`e21b2ca7`, lines 3483-3514), rather than guessing. Spot-
checking this session's own sampled `MAT (DSE)`/`MAT (Raw)` row paragraphs in the
dissertation against the duplicate set found none of the specifically sampled rows
collide -- but this is a spot-check, not an exhaustive clearance, and any resolver built
for this family **must** filter every candidate target through
`_vendored_content_tree._find_duplicate_native_para_ids` (the same helper
`_find_para_by_id` itself calls) before freezing it as a target, or the resolver can
silently hand the harness an anchor that will make `insert_word_comment` error out on
first use.

**Table-cell paragraphs are addressable by native `paraId` directly, closing precision-
scale's own central blocker.** `_find_para_by_id`'s docstring and body (confirmed by
reading it this session) state that "only schemes 1 and 3" (native `w14:paraId` and
legacy positional `p{N}`) apply inside tables -- the synth-id scheme (`sp<hash>`) is
body-direct-children-only. Separately, `locate_anchor`'s table-cell resolution path
returns a synthetic `tbl<n>:r<n>:c<n>` id (confirmed present in its own docstring text,
not re-read line-by-line this session but consistent with every candidate's citation)
that `_find_para_by_id` does not accept. **This session's own corpus scan resolves the
practical question precision-scale's reviews raised but could not close:** since every
sampled table-cell paragraph in all three documents already carries a real, usable
native `w14:paraId` (100% coverage, confirmed above), a harness-side resolver that reads
`word/document.xml` directly and extracts each target row's native `w14:paraId` --
bypassing `locate_anchor`'s lossy table-cell scheme entirely, exactly as this session's
own exploratory scan did -- can hand `insert_word_comment`/`insert_highlighted_note` a
working `anchor_para_id` for a table-cell target today. This is real, new harness code
(section 5), not yet built as frozen harness logic, but it is now confirmed buildable
rather than merely hoped to be.

### 1.2b Addendum (2026-09-24): resolver built and run, preconditions resolved, protocol locked

`resolve_comment_targeting_clusters` (section 2.2) is now real code in
`tools/docx_anchor_prober.py`, not a plan -- built reusing
`independent_gold_extractor.py`'s namespace constants and `_local_text` helper (never
duplicating OOXML text-extraction logic), with its own dedicated single top-to-bottom
`word/document.xml` walk tracking nearest-preceding-heading text for Regime 2 (neither
`docs_intel.parse_docx` nor `independent_gold_extractor.extract()`'s own generic graph
tracks paragraph style at all, so this could not be assembled from either alone).
Deliberately does **not** call
`meridian_docs._vendored_content_tree._find_duplicate_native_para_ids` for the
mandatory uniqueness filter (section 2.2 item 2) -- confirmed by reading that
function's own source that it only scans body-DIRECT-CHILD `<w:p>` elements and would
silently see zero duplicates among every table-cell paragraph this family's candidates
actually are. A dedicated full-document (body+table) `w14:paraId` scan is computed in
the same pass instead.

Run for real against the three hash-pinned corpus files
(`tools/freeze_comment_targeting_schedule.py --max-k 8 --min-group-size 3`, output
hash-pinned at `D:\MeridianData\ooxml-graph-paper\runs\paper-s24\comment-targeting-schedule-v1.json`):

| Document | Regime-1 clusters | Regime-2 clusters | Duplicate `w14:paraId` values | Usable K (capped at 8) | Excluded candidates |
|---|---:|---:|---:|---:|---:|
| `jcshm-manuscript.docx` | 0 | 4 | 0 | 4 | 0 |
| `jcshm-si.docx` | 21 | 18 | 0 | 8 | 0 |
| `masters-dissertation-defense.docx` | 22 | 16 | **236** | 8 | 0 |

Every number in this table matches this document's own earlier predictions closely
enough to trust the resolver, not merely to hope it is correct: the manuscript's
Regime-1 count of exactly 0 and Regime-2 count of exactly 4 matches section 1.2's own
direct-dump finding ("the manuscript has essentially no Regime-1... and only a thin,
4-group Regime-2 pool") precisely; the dissertation's duplicate-`w14:paraId` count of
**236** is an exact match to section 1.2's own independently-dumped figure. Zero
excluded candidates on all three documents means every selected target's own
duplicate-paraId check passed cleanly -- the mandatory filter (section 2.2 item 2) is
exercised and produces a real, non-trivial nonzero count on the one document where a
real collision risk exists (236, dissertation), while never spuriously excluding a
clean candidate on any of the three.

Section 6's own K figures are corrected from provisional estimates to these frozen,
real numbers: **manuscript K=4 (Regime-2-only, exactly as predicted, no Regime-1 pool
to draw from at all); SI K=8; dissertation K=8** (both capped at this run's
`max_k=8` -- SI's and the dissertation's own real cluster pools, 39 and 38 respectively,
comfortably exceed 8, so raising `max_k` in a later run is a live option, not a corpus
ceiling, should more chain depth be wanted).

Corpus SHA-256 hashes (section 8's own named precondition) were re-verified this
session, computed directly from the same three files the resolver just read, and match
`PROVENANCE.md`'s 2026-09-20 pins exactly, byte for byte, on all three documents --
confirming no drift since that pin.

Tool-surface absence (section 8's own named, explicitly time-bound precondition) was
re-checked live one final time this session via `ToolSearch` against several phrasings
("remove resolve edit comment word docx delete") against the current, live connected
`meridian-docs` manifest: still no comment-removal/resolve/edit tool and no
`flag_for_review` tool exposed. Sections 0.2/0.3's conclusions stand, re-confirmed a
sixth time, immediately before lock.

What remains, unchanged from section 8, and now the sole gate before any
validation/primary trial rather than before this lock: the live smoke test (one
document, one Regime-1 target, one Regime-2 target, both arms), and the harness/grading
code items in section 5 beyond the resolver itself (items 2-7), none of which are yet
built.

### 1.3 Pre-existing organic content (a real grading hazard, independently reconfirmed)

Directly read this session:

| Document | `word/comments.xml` present | Organic comments | Authors |
|---|---|---:|---|
| `jcshm-manuscript.docx` | yes | 1 | `Adam Camerer` |
| `jcshm-si.docx` | yes | 6 | 5x `Claude (review flag)`, 1x `Adam Camerer` |
| `masters-dissertation-defense.docx` | **no** | 0 | n/a |

A naive "count total `<w:comment>` entries before/after" grading check would be wrong
from step one on two of the three documents. Grading (section 4) must filter by a
per-trial author tag and separately verify every pre-existing comment survives each
chain byte-identical. The dissertation's missing `comments.xml` part means its first
insertion in this family exercises the "create the part from scratch" code path in
`_stage_word_comment` (lines 20659-20662), while the other two documents exercise the
"extend an existing part" path -- both need real trial coverage, not one silently
standing in for the other.

## 2. Task family: `comment_targeting`

### 2.1 What "repeated" means here, and why (adopted from accumulated-state, both of
its reviews' explicit recommendation to carry it forward "largely as-is")

K=4 and `respec_cascade` both isolate structural re-resolution from the agent's own
conversational memory by running fresh, independent processes per step, sharing only
the evolving `.docx` on disk. This family keeps that isolation principle rather than
precision-scale's single-continuous-session alternative (which that candidate itself
flagged as a deliberate, only-shape-comparable deviation): a genuinely new mechanism
deserves to be tested without also changing the paper's standing memory-isolation
convention, and mixing the two would make it impossible to say which change produced
any observed effect.

Since no inverse exists (section 0.2), "repeated" cannot mean K=4's literal
insert-undo-insert-undo. It means: **one chain = K sequential, distinct, never-repeated
comment-placement steps, each its own fresh agent process, sharing one evolving
document.** Repeating the same target twice is explicitly excluded (not merely
discouraged): inserting a comment adds a `commentReference` run but no visible `<w:t>`
text (confirmed by reading `_stage_word_comment`), so a control-arm agent working from
raw XML could, in principle, filter out already-commented occurrences of a repeated
label from its remaining candidate pool, mechanically shrinking an ambiguous target set
with every step -- a real confound removed by construction rather than measured and
corrected after the fact, adopted directly from accumulated-state's reasoning.

**Interleaved design (adapted, not copied verbatim, from accumulated-state's ambiguous/
unique interleaving):** each chain alternates between an **ambiguous target** (drawn
from a Regime-1 or Regime-2 cluster, section 1.2) and a **unique target** (a paragraph
whose exact text is not duplicated anywhere in the document -- headings and long body
sentences qualify given section 1.2's negative body-paragraph-duplication finding).
This gives a paired, within-chain answer to a question a pure ambiguous-only sweep
cannot answer on its own: does accuracy degrade because *targets accumulate* (would show
on unique targets too) or specifically because *ambiguity and accumulation compound*
(would show only on ambiguous targets)? K is capped by the weaker of the two pools per
document; per section 1.2, the manuscript's thin Regime-2-only pool (4 groups) means its
usable K is materially smaller than the SI's or dissertation's -- reported honestly at
corpus-build time (section 6), not forced to a common K.

**Primary readout: per-chain-position pass rate (1..K), separately for the ambiguous and
unique conditions, by arm** -- directly testing whether precision degrades with
accumulation (the state-drift signature) versus staying flat, the same K=4-style
question in a shape suited to a family with no literal round-trip.

### 2.2 Anchor resolution (corpus-build time, new code, not yet built -- section 8)

New `resolve_comment_targeting_clusters(docx_path, max_k, min_group_size=3)` (add to
`tools/docx_anchor_prober.py`, mirroring `resolve_respec_schedule`'s and
`resolve_multiple_section_reorder_plans`'s existing pattern of freezing and hash-pinning
resolver output once, before any trial):

1. Walk every `<w:tbl>` row; for Regime 1, group rows *within the same table* by exact
   first-cell text (count>=3), recording which adjacent cell actually varies (numeric
   or categorical, per section 1.2's own two sub-patterns) as the human-realistic
   disambiguator text. For Regime 2, group rows *across all tables in the document* by
   exact first-cell text (count>=3), recording each occurrence's enclosing table's
   nearest preceding heading/caption as the human-realistic disambiguator.
2. For every candidate target paragraph (the specific table-cell paragraph selected as
   ground truth for a given cluster), resolve its native `w14:paraId` **directly from
   the raw `document.xml` walk** (never via `locate_anchor`'s lossy `tbl<n>:r<n>:c<n>`
   scheme for table cells, per section 1.2's closed blocker), and **reject any candidate
   whose `paraId` appears in `_find_duplicate_native_para_ids`'s output** for that
   document -- the mandatory uniqueness filter section 1.2 identifies as necessary,
   confirmed necessary specifically for `masters-dissertation-defense.docx`.
3. Select a matched pool of unique-paragraph targets (body sentences/headings, exact
   text unmatched elsewhere) the same size as the ambiguous pool, resolved by whichever
   of the three existing `_find_para_by_id` schemes applies (native, synth, or legacy).
4. Freeze and hash-record one full (document -> ordered target list, alternating
   ambiguous/unique, each with its own confusable-sibling set for Regime-1/Regime-2
   grading) schedule per document, before any trial runs -- mirroring
   `resolve_respec_schedule`'s existing convention exactly.

### 2.3 Control vs. treatment tool grants

- **Treatment**, per step: exactly `Read` + `insert_highlighted_note(mode="comment",
  anchor_para_id=<harness-resolved>, text=<step marker>, author=<per-trial tag>)`.
  Never `mode="inline"` (a highlighted paragraph, a different OOXML mechanism entirely,
  not a real Word comment, and not what the user's own motivating scenario asked about).
  This is **not a tool pair** -- the first family in this paper without one, since no
  inverse exists (section 0.2). Each individual step still honors the paper's
  "exactly one bounded tool per treatment step" invariant; the family as a whole departs
  from the pairing shape every other family has, disclosed explicitly here and in
  section 3, not smoothed over.
- **Control:** `Read`/`Write`/`Edit`/`Bash`, unchanged for the whole chain, exactly as
  every other family -- hand-writing `word/comments.xml`, the relationship, the
  content-type override, and splicing `commentRangeStart`/`commentRangeEnd`/
  `commentReference` into the target paragraph in `word/document.xml`, mirroring what
  `_stage_word_comment` does natively.

Both arms receive the identical prompt at each step: the target's confusable label text
plus a realistic disambiguator (the adjacent-cell value for Regime 1, the surrounding
table/section identity for Regime 2) -- mirroring how the user's own framing was phrased
("edit this specific line," not "edit the only line containing X") and how existing
families already hand a quoted snippet to both arms via
`generate_citation_forward`-style prompt construction in `tools/docx_trial_broker.py`.
Only the treatment arm additionally receives the harness-resolved `anchor_para_id` as an
exact tool argument, the same asymmetry every existing family already tests.

## 3. Fresh/baseline comparison: why this family's baseline question differs from
`respec_cascade`'s, and what it is instead

`respec_cascade`'s section 3 baseline exists to route around a *specific, disputed
historical number* (the section-reorder K=1/K=4 figures, whose provenance three
independent reproduction attempts could not agree on). This family has no such disputed
historical baseline to route around -- it is a brand-new family with nothing published
yet. So "fresh baseline" here means something narrower and more literal: **for every
(document, target, arm), run one isolated, single-step trial at the identical target and
anchor used in the chain, against a fresh copy of the same pristine document snapshot,
same day and host as the chain runs** -- reusing the same per-step harness machinery
this family's own orchestrator already needs (section 5), just invoked once, outside any
chain. This is this family's own control condition for one specific, real question the
interleaved chain design alone cannot answer: is a given target's pass rate at chain
position 1 already different from that same target's pass rate in complete positional
isolation (no prior chain steps of any kind, ambiguous or unique)? If step-1-in-chain and
isolated-single-shot accuracy match closely, any degradation seen at later chain
positions (section 2.1's primary readout) is attributable to accumulation, not to some
property of "being step 1 of something" specifically. If they do not match, that is
itself a reportable, disclosed finding requiring the chain-position degradation curve to
be read starting from the isolated baseline, not from position 1.

This document does **not** claim this isolated baseline is directly comparable in
magnitude to any other family's published single-edit numbers (per section 0.2, this
family has no inverse and therefore no forward+inverse "pass rate" comparable to
bibliography/citation/etc.'s own K=1 figures) -- it is comparable only within this
family, to this family's own chained results, exactly parallel to how `respec_cascade`'s
own Phase-3 numbers are stated to be comparable to K=4 only "in shape," never claimed
identical in mechanism or magnitude.

## 4. Grading (objective, structural, re-derived from real `.docx` XML at every
checkpoint -- never from either arm's self-report)

All checks parse `word/comments.xml` and `word/document.xml` directly
(`lxml`/`lxml`-backed helpers in `tools/graph_scorer.py`/`tools/docx_trial_evaluator.py`,
per this project's standing "never trust the system under test" rule).
`list_internal_notes` is explicitly **not** used as ground truth anywhere in this
family: it is confirmed (by reading `insert_highlighted_note`'s source this session) to
surface `mode="comment"` insertions too (`note_id = f"_MComment{comment_id}"`,
upserted when `index_db_path` is passed) -- so it is not inline-only as its name might
suggest -- but it remains a sidecar populated by the very tool under test at insertion
time, never an independent re-derivation, exactly this project's standing rule for every
other family.

**Package validity gate (both arms, after every step, not just at chain end):**
`tools/docx_trial_evaluator.py::_package_is_valid_docx`, reused unmodified. A failure
freezes the chain at that step, logged `chain_broken_at_step_k` (the existing failure-
taxonomy value `respec_cascade` already introduced).

**Per-step check (new: `grade_comment_targeting_step`):**
1. Exactly one new `<w:comment>` exists, identified by a distinct per-trial author tag
   (e.g. `f"MeridianBench-{trial_id}"`) -- necessary given section 1.3's organic-comment
   finding on two of three documents.
2. Its `commentRangeStart`/`commentRangeEnd` bracket exactly the intended target
   paragraph and **no other paragraph in that target's frozen confusable-sibling set**
   (the presence-AND-absence check precision-scale's own review independently praised as
   "a real, non-trivial addition beyond what existing verifiers do") -- verifiable
   directly because `_stage_word_comment` never brackets more than one paragraph
   (section 0.1).
3. **Keep survival** (adopted and generalized from find-inverse's design, itself
   generalizing `respec_cascade`'s Checkpoint-B `score_keep_survival`): every comment
   inserted at steps `1..k-1` in this chain is still present, still correctly anchored,
   still byte-identical, and every pre-existing organic comment (section 1.3) is still
   present and byte-identical. New function `score_comment_set_survival` in
   `tools/graph_scorer.py`, generalizing `score_keep_survival` from three fixed named
   elements to a growing, per-chain set.
4. Zero paragraph-*text* diff anywhere in the document relative to the immediately-prior
   checkpoint -- a real comment insertion never touches run text (confirmed by reading
   `_stage_word_comment`), so this is a strict, cheap invariant, stricter than
   bibliography/citation/caption require of themselves since those legitimately mutate
   text.

**Outcome taxonomy per step** (adopted from distractor-corpus's proposal, which both its
reviews accepted without objection): `correct_target` / `wrong_target_same_cluster` (the
precision failure mode this family exists to measure) / `wrong_target_other` /
`no_comment_created` / `prior_comment_corrupted` / `chain_broken_at_step_k`.

**Chain-level composite:** per-chain pass = every step `correct_target` AND every
keep-survival check passed AND every package-validity gate passed. Primary statistic:
per-chain-position pass rate (1..K), by condition (ambiguous/unique) and by arm (section
2.1); secondary: `wrong_target_same_cluster` rate trend by chain position, by arm (the
literal mistargeting-under-accumulation signature).

## 5. New harness/grading code required

1. `tools/docx_anchor_prober.py`: **new** `resolve_comment_targeting_clusters` (section
   2.2) -- walks tables for Regime-1/Regime-2 clusters, resolves native `paraId`
   directly from raw XML for table-cell targets (bypassing `locate_anchor`), applies the
   mandatory `_find_duplicate_native_para_ids` filter, selects a matched unique-target
   pool, hash-pins the interleaved per-document schedule. The single largest new
   component in this family -- everything else below is orchestration/grading wiring
   around it.
2. `tools/docx_trial_broker.py`: **new** `generate_comment_targeting_step` -- one
   `TrialSpec` per chain/step/condition, quoting the target's confusable label plus its
   realistic disambiguator (adjacent-cell value or table/section identity per regime),
   identical wording to both arms.
3. `tools/docx_trial_evaluator.py`: **new** `grade_comment_targeting_step`,
   `grade_comment_targeting_chain` -- reuses `_package_is_valid_docx` unmodified for the
   per-step gate; new orchestration logic only.
4. `tools/graph_scorer.py`: **new** `_comment_range_precision` (presence-AND-absence
   scorer, pattern-matched to `_bibliography_entry_prf1`/`_citation_marker_prf1`'s
   existing exact-match style) and **new** `score_comment_set_survival` (generalizes the
   existing `score_keep_survival` from three fixed elements to a growing per-chain set).
5. `tools/run_comment_targeting_family.py` (**new** orchestrator): fresh-agent-per-step
   execution across K steps, tool-grant swap to exactly `Read` + `insert_highlighted_note`
   per treatment step, per-step `_package_is_valid_docx` gate, per-trial author-tag
   generation, explicit round-trip-count logging per arm -- structurally copied from
   `tools/run_respec_cascade_family.py`'s fresh-agent-per-step pattern, not built from
   scratch. Also runs section 3's isolated single-step baseline trials (same per-step
   machinery, invoked once, outside a chain).
6. `tools/run_comment_targeting_sweep.py` (**new**, analogous to
   `tools/run_respec_cascade_sweep.py`): drives the family across all documents and
   available target schedules, aggregating per-position results.
7. `tools/compute_multianchor_extension_statistics.py` (or
   `tools/compute_respec_cascade_statistics.py`): **extended**, not rewritten, with a
   per-chain-position, per-condition (ambiguous/unique) aggregation dimension, reusing
   `estimate_icc_and_effective_n`, `weighted_mean`, `weighted_bootstrap_ci`,
   `weighted_paired_permutation_test` **unmodified**, same seed value (`20260828`) and
   resample count (2000) already used across `graph_scorer.py` and
   `compute_multianchor_extension_statistics.py` (these are independently-declared
   constants with matching values across modules, not a shared import -- confirmed this
   session by reading both files directly; cite the value, not a shared constant name).
8. **Not required, confirmed by this session's own read:** any change to
   `insert_highlighted_note`/`insert_word_comment` themselves, and no use of
   `flag_for_review` anywhere in this design (section 0.3).

## 6. N / sample-size plan (honest, Tier 1/2/3 discipline, non-independence disclosed)

- **Document level:** N=3 (dissertation, manuscript, SI), non-independent per
  `PROVENANCE.md`'s own disclosed overlap percentages (manuscript<->dissertation 19.0%/
  8.2%; SI<->dissertation 16.7%/7.7%; manuscript<->SI 0.3%), carried forward unmodified.
  Reported as Tier 1 (unweighted per-document mean).
- **Target/chain level:** per-document K is capped by the *smaller* of that document's
  ambiguous-target pool and its matched unique-target pool (section 2.1), and is **not**
  forced to a common value across documents. **Frozen by the real resolver run
  (section 1.2b): manuscript K=4 (Regime-2-only, 4 usable clusters total, none
  excluded), SI K=8, dissertation K=8** (both capped at this run's `max_k=8`; SI's and
  the dissertation's real cluster pools, 39 and 38 respectively, exceed the cap, so a
  later run could raise it). Zero candidates were excluded on any document, including
  the dissertation despite its 236 duplicate-`w14:paraId` values -- the mandatory
  uniqueness filter (section 2.2 item 2) never had to fall back past a cluster's first
  candidate on any of the frozen targets this run selected.
- **Isolated-baseline level (section 3):** one single-step trial per (document, target,
  arm), same denominator structure as the chain targets themselves, so the section-3
  comparison is always apples-to-apples at the same aggregation tier.
- **Reported at three tiers**, reusing `compute_multianchor_extension_statistics.py`'s
  existing scheme unmodified: Tier 1 (unweighted per-document mean), Tier 2
  (target-count-weighted per-document mean), Tier 3 (pooled target-level estimate with
  ICC-corrected effective N) -- Tier 3's naive pooled N is expected to overstate
  precision here too, per the same prior finding `respec_cascade`/multi-anchor already
  established for this corpus, so the ICC-corrected effective N gets headline weight,
  not the raw pooled N.
- 2000 resamples/permutations, seed `20260828` (section 5, item 7).

## 7. Preregistration: confirm vs. disconfirm, decided here, before any trial runs

**Primary comparison (per-chain-position pass rate, ambiguous condition, at the Tier 3
ICC-corrected-effective-N aggregation):** `paired_permutation_test` between control's
position-1 and position-K pass rates (the direct chain-position-degradation test); the
same comparison for treatment; then `paired_permutation_test` directly between control's
and treatment's per-position pass-rate curves. Secondary: the same three comparisons
restricted to the unique condition (isolates "accumulation alone" from "ambiguity plus
accumulation"), and `score_comment_set_survival`'s own per-position pass rate, by arm.

**CONFIRMING** (heterogeneous, no-inverse repeated targeting pressure degrades control's
structural bookkeeping under accumulated ambiguity, generalizing the K=4/`respec_cascade`
mechanism to a family with no round-trip) requires ALL of:
- Control's ambiguous-condition pass rate shows a statistically significant downward
  trend across chain position (p<0.05) with a point estimate of at least 10 percentage
  points, position 1 vs. position K.
- Treatment's ambiguous-condition trend is either not significant, or its degradation is
  smaller than control's by at least 10 percentage points with p<0.05 on the direct
  control-vs-treatment paired test.
- Control's ambiguous-vs-unique pass-rate gap at matched chain positions is significant
  (p<0.05) at position K (isolating ambiguity-plus-accumulation jointly, not
  accumulation alone) while treatment's corresponding gap is not, or is materially
  smaller.
- `score_comment_set_survival`'s pass rate is significantly higher for treatment than
  control at chain position K (p<0.05) -- the selective-precision-under-load analogue of
  `respec_cascade`'s own Checkpoint-B test.
- Position-1 chain accuracy is not significantly different from the isolated-baseline
  (section 3) accuracy for either arm (confirms any later-position degradation is
  attributable to accumulation, not to some property of position 1 itself).

**DISCONFIRMING** (reject this family's hypothesis; report the null in full) if ANY of:
- Control shows no significant chain-position trend on ambiguous targets (repetition
  does not measurably bite here, at this K and this corpus).
- Control's ambiguous-vs-unique gap is not significant at any chain position (this
  corpus's duplicate-label clusters are not measurably harder than any other target for
  a text-searching control agent, undercutting this family's core premise).
- Treatment shows the same degradation pattern as control (the persistent-id mechanism
  is not protective for this task -- itself a reportable, honest null, exactly like the
  paper's existing bibliography/citation single-edit parity findings).
- Position-1 chain accuracy is significantly different from the isolated baseline for
  either arm and that difference is not itself explained and reported (an ambiguous
  "something about position 1 specifically" result, not cleanly attributable to
  accumulation).

No other outcome pattern is defined as confirming or disconfirming; an ambiguous result
is reported as **inconclusive**, with every per-document, per-condition, per-tier number
shown, never resolved by selecting whichever tier or subset looks cleanest after the
fact -- the same discipline `respec_cascade`'s own section 7 commits to.

**Render-gate / host-contention control:** every chain runs on a dedicated, uncontended
host, host-load logged per trial; any step failing specifically via a render-gate
timeout (not a structural failure) is recorded as its own outcome
(`render_gate_timeout`) and reported separately, never folded into headline pass rates
-- reused directly from `respec_cascade`'s own precedent (its section 7), given the same
real risk applies here (`insert_word_comment` invokes `_enforce_render_verification` on
**every single call**, confirmed by reading its source this session, unlike
`respec_cascade`'s amortized 3-phase-boundary cost -- a K-step chain pays this gate K
times, a genuine, disclosed throughput risk, not yet solved, see section 8).

## 8. Risks and confounds (disclosed, not hidden; every live blocker any candidate's
review found that this session was not able to fully resolve is carried forward here)

- **Resolved 2026-09-24 (section 1.2b): `resolve_comment_targeting_clusters` is built
  and has run against the three real corpus files, hash-pinned output at
  `D:\MeridianData\ooxml-graph-paper\runs\paper-s24\comment-targeting-schedule-v1.json`.**
  Was the single largest reason this document was not locked; is not a remaining risk.
- **Still open, and the sole gate before any validation/primary trial: no live
  smoke-test call has been made.** This document's claim that a directly-resolved
  native `w14:paraId` for a table-cell paragraph can be passed to
  `insert_word_comment`/`insert_highlighted_note(mode="comment")` successfully is
  verified only by reading `_find_para_by_id`'s source, confirming 100% `paraId`
  coverage on sampled table-cell paragraphs, and confirming the resolver itself runs
  cleanly end-to-end -- no actual `insert_word_comment`/`insert_highlighted_note` tool
  call against these three files has been made yet. A real smoke test (one document,
  one Regime-1 target, one Regime-2 target, both arms) must run and be manually
  spot-checked before any validation/primary trial, per
  `docs/benchmark-preregistration-v0.md`'s standing smoke -> scale-up -> final
  discipline.
- **Resolved 2026-09-24 (section 1.2b): SHA-256 corpus hashes re-verified**, computed
  directly from the same three files the resolver read, matching `PROVENANCE.md`'s
  2026-09-20 pins exactly on all three documents.
- **Resolved 2026-09-24 (section 1.2b), but genuinely time-bound, not a one-time
  check: tool-surface absence was re-confirmed live immediately before lock** (no
  comment-removal/resolve/edit tool, no live `flag_for_review`, no
  `insert_table`/`remove_table`-style surprise). Re-check again at actual harness-build
  and smoke-test time regardless -- a manifest can change between this lock and
  whenever the smoke test above actually runs, the same standing precondition
  `respec_cascade`'s own protocol names for its own tool dependencies.
- **No round-trip metric is possible for this family, a structural fact, not a gap
  worked around quietly** (section 0.2); its outcome measure (per-chain-position
  precision and its trend) is not comparable in magnitude to the other six families'
  forward+inverse pass-rate figures and must never be pooled with them.
- **Per-step render-verification cost is real and unsolved.** `insert_word_comment` runs
  `_enforce_render_verification` unconditionally on every call (confirmed by reading the
  function this session), unlike `respec_cascade`'s three-phase-boundary amortization.
  A K=8 chain pays this cost 8 times per arm per document. This is a genuine,
  unresolved throughput risk, flagged, not absorbed into the design as if it were free.
- **Per-document asymmetry is real, measured, and not evened out.** The manuscript's
  usable target pool (4 groups, Regime-2-only, per section 1.2) is materially thinner
  than the SI's or dissertation's (20+ groups each, both regimes) -- document-level N=3
  is honest but the manuscript's own chains will be shorter and less statistically
  informative on their own, reported per-document, never silently averaged over.
- **The dissertation's 13%-paragraph duplicate-`paraId` defect is a real, disclosed
  corpus property**, not a design flaw -- it requires the mandatory uniqueness filter in
  section 2.2 item 2, and any future target selection for this document must re-apply
  that filter, not assume this session's spot-check (which found no collisions among the
  specific `MAT (DSE)`/`MAT (Raw)` rows sampled) generalizes to every candidate target.
- **Difficulty operationalization is two measured regimes, not the whole space.**
  Regime 1 (within-table run) and Regime 2 (cross-table scatter) are the sharpest
  evidence this session could measure directly in the real tables; other plausible
  "hard to target" patterns (near-miss numbered list items, similar-but-not-identical
  headings) were checked and found absent at the body-paragraph level (section 1.2's
  negative finding) but were not exhaustively checked at every other structural level;
  this design should not be read as covering the general case of "hard targeting" in
  arbitrary documents.
- **First-use grading and orchestration code remains, beyond the resolver.**
  `resolve_comment_targeting_clusters` itself has now run for real (section 1.2b);
  `score_comment_set_survival`, `_comment_range_precision`, and the chain orchestration
  in `grade_comment_targeting_step`/`grade_comment_targeting_chain` (section 5 items
  2-7) have not been written yet, let alone run.

## 9. What this document does not decide

The exact per-document K and target list (frozen only once `resolve_comment_targeting_
clusters` actually runs against the three real files, per section 8 -- this document's
own K<=8/K<=4 figures are provisional, ad hoc-scan estimates, not a lock); whether a
future comment-removal/resolve primitive, if one is ever added to the live manifest,
should be retrofitted into this family as a true round-trip variant or reserved for a
separate one (section 0.2/0.3 establish that today's `flag_for_review`, even if it goes
live, would not qualify, since it refuses table/table-cell anchors outright); whether the
per-step render-verification throughput cost (section 8) is acceptable at the full
planned K or requires a batched-verification tool change -- an open engineering question,
not resolved here; and whether Regime 1 and Regime 2 targets should be weighted equally
in the primary comparison or analyzed as fully separate sub-families -- this document
interleaves them for a single paired ambiguous/unique comparison (section 2.1) but does
not yet decide whether Regime 1 vs. Regime 2 itself deserves its own confirm/disconfirm
test, left for the corpus-build-time resolver's actual yield to inform.