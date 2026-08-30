# PAPER-S12: prior 127-document exposure audit and long-horizon Claude holdout freeze (v0)

Status: a real, read-only reconciliation of the existing 127-document gold corpus's
**usage history** (not its structural/provenance correctness -- that is PAPER-29's and
PAPER-37's job, both already done and re-verified here, not repeated). This item's charge
is different: decide whether any part of the 127 can honestly be called a **clean holdout**
for a *new* long-horizon Claude benchmark (PAPER-S7/S9/S17), and freeze that decision in a
durable, checkable place before those items can rely on it.

Evidence base for every claim below: direct inspection of
`E:\MeridianData\ooxml-graph-paper\gold\manifests\*.json`,
`E:\MeridianData\ooxml-graph-paper\manifests\*.json`,
`E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\*.json`, file mtimes on this host, and
`git log` on this repo (`C:\Users\13144\Documents\Meridian\ooxml-graph-paper`, branch
`dev`). No product code was read or modified for this item (`required_tool` scope:
"gold/manifests + paper git history and run logs; no product mutation").

## Headline verdict

**None of the 127 documents is a clean holdout.** All 127 have been read, scored, and used
to debug/tune the extraction and scoring code at least once, several as recently as today
(2026-08-30). The existing `_split.json` (10 smoke / 58 scale_up / 59 final, seed
20260826) is -- exactly as this item's own notes already stated -- **continuity history for
regression-tracking the scorer's own development, not a leakage-free split for a new
model-facing benchmark.** Any PAPER-S7/S9/S17 claim that treats this corpus, or any slice
of it, as a fresh, blind test set for Claude would be false. A genuinely clean long-horizon
Claude holdout does not yet exist in this project and must come from unexposed material
(PAPER-S11's D1 expansion, PAPER-S18's organic-OMML screen, PAPER-S13's DocOps suite, or
PAPER-S14's OmegaUse-OfficeVal Word-only screen -- none of which have contributed a document
to the 127 audited here).

## 1. Exposure timeline: the 127 corpus has been re-scored at least 5 times, most recently today

Direct filesystem evidence (`E:\MeridianData\ooxml-graph-paper\manifests\`, mtimes on this
host, all times local -05:00 unless marked Z):

| Event | File(s) | When |
|---|---|---|
| docx-corpus 90-doc review written (67 promoted) | `gold/manifests/_docxcorpus_review.json` | 2026-08-27 13:49 |
| Split assignment written (10/58/59, seed 20260826) | `gold/manifests/_split.json` | 2026-08-27 14:04 |
| OmegaUse/docx-benchmark review finalized (incl. PAPER-29's rights-rationale fix) | `gold/manifests/_tier2_review.json` | 2026-08-27 23:34 |
| PAPER-29 structural/provenance audit | `gold/manifests/paper29-corpus-audit.json` | 2026-08-27 23:36 |
| Corpus rebuild / run manifest | `gold/manifests/_run_manifest.json` | 2026-08-28 08:44 |
| **Full-127 graph-scorer runs** (`paper30-graph-eval-all-*.json`) | 5 distinct full-corpus scoring passes | 2026-08-28 05:15, 05:18, 13:45, 16:12, and **2026-08-30 07:04 (today, ~2h before this audit)** |
| Smoke-slice (10-doc) scorer runs | `paper30-graph-eval-smoke-*.json` | 4 distinct passes, 2026-08-28 05:12-16:02 |
| PAPER-15 smoke-run passes | `paper15-smoke-run-*.json` | 8 distinct passes, 2026-08-27 22:30 through 2026-08-28 15:42 |
| PAPER-34 ablation runs | `paper34-ablations-*.json` | 3 distinct passes, 2026-08-28 05:33-05:44 |
| Acceptance-gate re-runs (reads corpus-provenance state each time) | `acceptance-gate-*.json` | 12 distinct passes, 2026-08-26 15:01 through 2026-08-27 23:44 |

The most recent full-corpus re-score (`paper30-graph-eval-all-20260830T070431Z.json`, per
`docs/final-results-correction-ledger-v1.md`) followed a real code fix to
`docparse.docs_intel._paragraph_text` (parent-repo `dev@54d6f969`, independently confirmed
via `git show` on the parent repo, read-only, for this audit) that was itself discovered by
inspecting this exact corpus's own scored output for a tab/break-handling gap
(`task_ab325093`). The commit's own message is the clearest evidence available that this is
a real look-at-the-data-then-fix-the-code cycle, not a hypothetical concern: it states the
bug had been "artificially inflating a 'native beats python-docx on paragraph text'
comparison by coincidence (both sides dropped tabs identically) rather than genuine
fidelity," and that it was "found via the ooxml-graph-paper project (PAPER-30/36/38)." That
is this project's own record of a reported benchmark result changing as a direct
consequence of studying this specific corpus's scored output -- the single clearest
evidence that this corpus has functioned as a development set for the extraction/scoring
code, not a blind test set, right up through the day of this audit.

**This is not a criticism of that work** (PAPER-S4's fix was correct and well-evidenced on
its own terms) -- it is the concrete mechanism by which "exposure" actually happened, named
so the next benchmark item does not accidentally reuse the same 127 documents believing
them still blind.

## 2. Classification of all 127 documents

Using the six-lane vocabulary this item and PAPER-S16 both specify
(development / exposed validation-regression / clean primary holdout / research-only
quarantine / context-only / rejected-held):

| Lane | Count | Which documents | Basis |
|---|---:|---|---|
| **Development (fixtures)** | 11 | 8 tier1 hand-authored (`fixture-01`..`fixture-08`) + 3 tier3 composites (`composite-01/02/03`) | Purpose-built by this project's own agents to exercise named schema invariants; the authors know the exact expected graph by construction, so these were never blind in the first place. |
| **Exposed validation/regression** | 116 | All tier2: 47 OmegaUse-OfficeVal + 2 docx-benchmark + 67 docx-corpus | Real-world documents, individually content-reviewed, then scored across >=5 full-corpus passes (Section 1). Includes the 3 privacy-flagged and 6 near-duplicate-lineage documents below, which carry an additional flag on top of this base lane. |
| **Clean primary holdout** | **0** | none | This is the finding this item exists to establish. See headline verdict. |
| **Research-only quarantine** | 3 | `tier2-docxcorpus-e4ca0131c803b4f0`, `tier2-docxcorpus-6786f21f5e4a2d03`, `tier2-docxcorpus-36608e408865d04a` | `contains_real_personal_data: true` in `_docxcorpus_review.json`. Already used inside this project's internal scoring runs (cannot be retroactively un-used) but must not be redistributed, published, or included in any externally-released dataset/artifact bundle without explicit privacy sign-off. See Section 3. |
| **Context-only** | 3 sources (not part of the 127) | MathMLben, ReadingBank, DocBank-repo(-incomplete) under `raw/` | Investigated and correctly excluded per PAPER-12/PAPER-37 (no native DOCX content, or PDF/layout-only) -- kept as landscape context for the paper's SOTA discussion, never promoted. |
| **Rejected/held** | 38 | 15 OmegaUse exclusions (`_tier2_review.json.excluded`) + 23 docx-corpus exclusions (`raw/docx-corpus/review_results.json`, verdict=exclude) | Individually reviewed and excluded, each for a specific, retained PII/privacy rationale (filled national-ID numbers, named students+IDs, internal GxP validation records with named testers, etc.). Rationale preserved, not deleted. |

Total accounted for in the promoted corpus: 11 + 116 = 127, matches
`_run_manifest.json`'s `total_documents: 127` and PAPER-29's audit. The 38 rejected + 3
context-only-source directories are outside the 127 and were never part of any split.

**One small, honestly-flagged reconciliation gap in the rejected/held count itself:**
`docs/gold-corpus-status-v0.md`'s PAPER-25 narrative states "63/63 [OmegaUse candidates]
now reviewed: 23 promoted, 9 excluded" for the second wave alone, on top of an earlier
"20 new promotions and 5 new exclusions." Directly counting the structured files gives
`_tier2_review.json.promoted.Count = 49` (47 OmegaUse + 2 docx-benchmark) and
`.excluded.Count = 15` -- i.e. 47 + 15 = 62 OmegaUse documents accounted for in the
machine-readable record, one short of the narrative's cumulative "63." This item did not
track down the missing one (a withdrawn candidate, a collapsed duplicate-filename entry, or
a narrative miscount are all equally plausible and none was verified) -- recorded as a real,
open, one-document discrepancy between prose and structured data rather than silently
reconciled to whichever number looked cleaner. It does not change the 127-document promoted
total, which is independently confirmed by manifest file count.

### 2a. The three research-only-quarantine documents, verified directly

Read in full from `_docxcorpus_review.json` (not inferred from the boolean flag alone):
all three trip the flag on **`docProps/core.xml` authorship metadata (a real personal name
as document creator/last-modified-by), not on document-body content**. The reviewing
agent's own reasoning for all three explicitly states the body text has zero individual
PII and argues the metadata name alone is borderline/does-not-meet-the-exclusion-bar --
but still set `contains_real_personal_data: true`, and this item's own charge is to
surface exactly that kind of self-flagged item for a **human** privacy sign-off, not to
re-adjudicate it in an agent's own favor. Recorded, unresolved, pending human decision:

- `tier2-docxcorpus-e4ca0131c803b4f0` (Oxford finance activity-code guidance; metadata
  creator "Alan Glaum", Company "University of Oxford") -- **smoke slice**.
- `tier2-docxcorpus-6786f21f5e4a2d03` (Hong Kong OCLP/Umbrella Movement coding manual;
  metadata creator "Ami Lall", Company "London Borough of Hounslow") -- **smoke slice**.
- `tier2-docxcorpus-36608e408865d04a` (industrial RBAC permissions matrix; metadata creator
  "Lena Plambeck") -- **scale_up slice**.

Two of these three sit in the 10-document **smoke** slice -- the slice most likely to be
copied into a quick demo, a README example, or a lightweight external-facing artifact
precisely because it is small. Flagging this concretely: **do not use the smoke slice for
any external-facing demo or publication figure without the privacy sign-off this item is
surfacing**, independent of whatever PAPER-S16 decides about splits generally.

## 3. Near-duplicate lineage: a real finding, not previously reconciled

PAPER-29's audit checked for **exact** duplicate `source_sha256` across all 127 and found
zero (confirmed independently: all 127 `id` values in `_docxcorpus_review.json` /
`_tier2_review.json` are distinct 64-hex-char SHA-256 strings). That check cannot catch
**near-duplicates** -- the same underlying document scraped/authored twice under different
bytes. Reading every one of the 67 docx-corpus `content_summary`/`reasoning` fields in full
(not sampled) surfaced three such pairs, confirmed against `raw/docx-corpus/sample_90.json`
source metadata:

| Pair | Doc A | Doc B | Evidence they are the same underlying document | Split placement |
|---|---|---|---|---|
| "Tom Thomas Remembered" (IU East professor tribute) | `tier2-docxcorpus-5beb34d4b70c54f0` | `tier2-docxcorpus-346e7a7d99ef290b` | Near-identical body text (same 4 awards, same bibliography, same career dates); source metadata lists **different** crawl `filename`/`type`/`topic` labels ("content"/reference/education vs. "Download"/reports/government) for what is verifiably the same article -- proof the dataset's own per-file metadata cannot be trusted to catch this. | A in **scale_up**, B in **final** -- **cross-split**. |
| Hong Kong OCLP/Umbrella Movement coding manual (Table 1, 29 variables) | `tier2-docxcorpus-6786f21f5e4a2d03` | `tier2-docxcorpus-dff1f5375a5c57fd` | Identical extracted-text length (3,001 chars both), identical table structure/variable list, different `docProps` authorship names ("Ami Lall" vs. "Christian Hviid Mortensen") -- the same research codebook filed by two people. Source `filename` fields are unrelated to the actual content in both records ("ehcp-annual-review-guidance..." and "156161"), another metadata-mismatch confirmation. | A in **smoke** (also the research-only-quarantine document above), B in **final** -- **cross-split**. |
| Bleak Hill Primary School "Charging and remissions policy" (Autumn 2023) | `tier2-docxcorpus-1a0fe2a06ec23c72` | `tier2-docxcorpus-f09dec98eee75ade` | Same school, same policy, same year, same fee figures (e.g. "£4.50 per child per session"), same `cp:lastModifiedBy` = "Laura Knapper" in both records' metadata. | Both in **final** -- same slice, so not a cross-split leak, but still double-counts one underlying policy document as two independent test items. |

**Two of three pairs are split across different D0 slices** (scale_up/final and
smoke/final). This is exactly the failure mode PAPER-S16's own notes warn against
("no primary run with ... cross-split source collision") and was not previously reconciled
anywhere in PAPER-29 or PAPER-37, because both of those audits checked hash-identity, not
content-similarity. Distinct `source_sha256` values were re-verified for all three pairs
(confirmed not byte-identical), so this is a genuine near-duplicate gap, not a contradiction
of PAPER-29's exact-duplicate finding.

This finding is scoped to the 67 docx-corpus documents only (full-text reasoning read for
all 67); the 47 OmegaUse and 2 docx-benchmark documents were not re-read line-by-line in
this pass beyond what PAPER-25/29/37 already document (their own near-duplicate case --
three officeval filenames sharing one underlying "顾启朝" dossier -- was already caught
and **excluded**, not promoted, per `docs/gold-corpus-status-v0.md`). A full near-duplicate
sweep of the 49 OmegaUse/docx-benchmark documents is out of this item's bounded scope and is
recorded here as a real, un-closed gap, not silently skipped.

## 4. License/rights mapping: confirmed incomplete, as this item's notes already stated

Per `docs/dataset-landscape-2026-08-25.md`'s own source table: docx-corpus carries
**ODC-BY at the dataset/metadata level only; "per-file provenance unverified."** No
per-document rights-holder identification was performed for any of the 67 promoted
docx-corpus documents beyond the content-privacy review already covered above -- content
safety (no PII, not an internal/leaked document) was checked; copyright/rights provenance
of each individual source page was not. This is a real, unresolved gap for any external
release of the corpus (as opposed to internal benchmark scoring, which is not itself a
redistribution act). OmegaUse-OfficeVal (Apache-2.0) and the two `docx-benchmark`
CC0-1.0 documents have real, machine-readable rights rationale per PAPER-29's fix; the
67 docx-corpus documents do not have an equivalent per-file rights record beyond the
dataset-level ODC-BY claim.

## 5. The external/docops-source deletion wave: confirmed present, correctly left untouched

Per this item's explicit instruction ("treat ... as unrelated/unsafe until independently
reconciled"): `E:\MeridianData\ooxml-graph-paper\external\docops-source` is its own git
working tree with **12,589 staged deletions** (`git status --porcelain` inside that
directory, read-only check performed for this audit only). This is unrelated to the
127-document gold corpus (a separate PAPER-S13 DocOps acquisition track) and was not
touched, inspected further, or reconciled by this item -- confirmed to exist at the scale
this item's notes anticipated, nothing more.

## 6. What this item froze, and where

Two durable artifacts record this freeze, so PAPER-S16 (split methodology) and
PAPER-S7/S9/S17 (the actual long-horizon Claude benchmark) do not have to re-derive it:

1. This document (`docs/paper-s12-holdout-exposure-audit-v0.md`).
2. A machine-readable freeze record,
   `E:\MeridianData\ooxml-graph-paper\manifests\s12-holdout-exposure-freeze.json`, listing
   every one of the 127 doc_ids with its lane assignment from Section 2, the 3
   research-only-quarantine doc_ids with their slice placement, and the 3 near-duplicate
   pairs with their split placement -- generated directly from the manifests cited above,
   not hand-typed.

**Frozen decision:** the 127-document corpus and its `_split.json` (10/58/59) remain valid
and usable for what they already are -- the native-vs-`python-docx`-vs-Docling structural
comparison this project has been reporting (PAPER-15/29/30/31/34/35/36/37/38/39) -- but are
**not eligible** to be presented as, or silently reused as, the long-horizon Claude
editing-benchmark holdout. Any future item that wants a Claude holdout must source it from
material with zero rows in Section 1's exposure timeline.

## 7. What this item did not do, honestly

- Did not re-verify graph-content correctness (PAPER-29/PAPER-30's job, not repeated).
- Did not perform a full pairwise near-duplicate sweep of all 127 x 127 documents --
  Section 3's three pairs were found by reading all 67 docx-corpus summaries/reasoning in
  full and cross-checking against source metadata; the 49 OmegaUse/docx-benchmark documents
  were checked only against prior audits' own findings, not independently re-read here.
- Did not obtain the human privacy sign-off Section 2a calls for -- that decision belongs
  to a person, not this session, and is recorded as open, not resolved.
- Did not reconcile or touch the `external/docops-source` deletion wave (Section 5), per
  explicit instruction.
- Did not source or stage any new, unexposed documents for an actual clean holdout --
  that is PAPER-S11/S13/S14/S18's job, not this one's.
