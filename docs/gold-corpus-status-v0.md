# PAPER-22/23: gold corpus construction status (v0, superseded PAPER-22 draft)

Status: **35-document corpus built and verified, within the ~30-40 target range.**
PAPER-15 (the actual benchmark) still has not run. This document states exactly what
exists, what was found while building it, and what remains genuinely open -- it is not a
readiness claim.

## What exists (35 documents)

| Tier | Count | Source |
|---|---:|---|
| tier1 (hand-authored fixtures) | 8 | Raw-XML-authored, targeting named schema invariants + all applicable equation semantic-label classes this extractor can compute |
| tier2 (real-world) | 24 | OmegaUse-OfficeVal (Apache-2.0), individually content-reviewed for PII, not license-only cleared |
| tier3 (composite stress) | 3 | Raw-XML-authored, combining multiple features per document |

Every document has: a real independent graph-gold extraction
(`tools/independent_gold_extractor.py`, stdlib-only, never imports `docs_intel.py`), a
real `ooxml_integrity.validate_docx_package` check, and a real, **retained** Word-COM
render receipt (`tools/retained_render_receipt.py`) -- PDF + input/output SHA-256 +
Word version/build + page count, genuinely saved to disk, not the transient probe PAPER-22
left unresolved. All 35 rendered successfully (`status=rendered`); 35/35 have a retained
PDF. A run-level manifest exists at
`E:\MeridianData\ooxml-graph-paper\gold\manifests\_run_manifest.json` (tool code hashes,
per-document manifest hashes, tier counts, hardware, installed packages, render/integrity
summaries). The pre-registered split procedure (seed 20260826) now populates all three
slices for real: 5 smoke / 15 scale_up / 15 final (`_split.json`).

## New this pass (PAPER-23), beyond the PAPER-22 first tranche

1. **Equation semantic labels are now computed**, independently (own OMML structural
   inspection, not a call into the product validator): `correct`, `empty_required_child`,
   `fallback_forbidden` are all covered by dedicated tier-1 fixtures
   (fixtures 02/06/07/08). `lossy_reviewed`, `package_render_divergent`, and `fails_closed`
   are NOT computable by this extractor without a reference source or a render comparison
   -- honestly left unlabeled rather than guessed.
2. **Caption/reference-edge verification (Section 6) is now real**, not a vague
   "ambiguous" placeholder: every caption resolves to an explicit `resolved` (nearest
   preceding top-level table, with a `caption_for` edge) or `dangling` state.
3. **Render receipt retention is fixed**, via a from-scratch script
   (`tools/retained_render_receipt.py`) that copies Word's PDF out before its temp
   directory is deleted -- the exact root cause PAPER-22 identified but didn't fix.
   `render_gate.py` itself was **not** touched (out of this item's scope; it is shared,
   parent-repo, actively-used-elsewhere code).
4. **Tier-3 composite documents exist** (3 of the planned 4-6): a realistic combined
   report, an adversarial duplicate-paraId case with real surrounding content, and a
   multi-table/multi-equation/multi-caption stress case.
5. **Corpus grew from 9 to 35 real-world+fixture documents.** 25 additional OmegaUse
   candidates were independently reviewed -- not license-checked only, each one's actual
   text read by a fresh, isolated agent with no shared context -- yielding 20 new
   promotions and 5 new exclusions (full reasoning: `gold\manifests\_tier2_review.json`).

## Findings from doing this work

- **A real, previously-unknown dataset quirk**: 3 of the 25 newly-reviewed candidates
  (`officeval_001/08`, `officeval_015`'s "答题卡", `officeval_022`'s "呈报材料" file) turned
  out to be **the same underlying document** -- a corporate "operating-anomaly dossier"
  containing a name+phone-number block (`呈报人：顾启朝...联系电话：188278632124586`) --
  duplicated under three unrelated filenames in three different task folders, each
  independently caught and excluded by a separate reviewing agent for the same reason.
- **`officeval_028`'s 职称评审表 is the most identifying single document found this
  sprint**: a filled professional-title review form with a real-ID-format 18-digit
  national ID number, birth date, birthplace, employer, education history, certificate
  numbers, and 7 additional named witnesses. Excluded.
- **`officeval_030`'s V2成果说明书_A** has a filled student name + student ID + named
  advisor on its cover page. Excluded.
- **One borderline promoted case flagged for a second look**: `officeval_022`'s cover
  sheet (`tier2-omegause-022-cover-sheet`) has a name plus a *partially masked* phone
  number (`186****2741`). Promoted on the reasoning that a masked number isn't a complete,
  actionable identifier, but this is a judgment call worth independent confirmation, not a
  clean case like the other 19 promotions.
- **An environment-integrity anomaly surfaced during the review batch**, unrelated to any
  document's content: one reviewing agent reported that a script it wrote to read
  `officeval_001/02` was silently altered on disk before execution, and it initially got
  output for a *different* file (`officeval_001/08`) without asking. The agent caught this
  itself (the result didn't match what it expected), rejected the untrusted output,
  rewrote the script under a new name, and re-verified via SHA-256 before trusting its
  second attempt -- so the affected document's review is sound. The anomaly itself (a
  script substituted on disk between write and execution) is worth investigating
  independently; it did not recur in any of the other 24 reviews and this session cannot
  explain it (the most likely candidate given ~10 concurrent Meridian sessions active on
  this same host throughout this sprint is a scratch-path collision, but that is a guess,
  not a diagnosis).

## Still honestly not done

- **Not the full corpus.** 35 documents is within the ~30-40 target range but not
  confirmed final; ~38 of the original ~63 OmegaUse candidates remain unreviewed; all of
  MathMLben and ReadingBank remain unconverted (MathMLben's own license status is still
  unresolved per `dataset-landscape-2026-08-25.md` -- correctly not used as a promotion
  source here either).
- **3 of the planned 4-6 tier-3 composites** -- not the full range.
- **`lossy_reviewed`, `package_render_divergent`, `fails_closed` equation labels**: no
  fixture in this corpus currently exercises these; they need either a source LaTeX/MathML
  reference to compare against or a deliberately-broken render case, neither built here.
- **Pandoc and LibreOffice remain not installed** anywhere on this host.
- **The one borderline tier-2 promotion** (masked-phone cover sheet) and the officeval_004
  exclusion from PAPER-22 both still await explicit human sign-off, not resolved by this
  session's own judgment.

## PAPER-20 acceptance gate, re-run after this work (2026-08-27T12:45:26Z)

**Still FAIL, 2 blocking conditions** (down from the original 3, unchanged from the
post-PAPER-22 state):

- `gold_corpus_provenance_exists`: **PASS** (was already passing after PAPER-22; corpus is
  now substantially larger).
- `parent_repo_worktree_clean`: **FAIL** -- 89 porcelain entries (up from 83 after
  PAPER-22; other concurrent sessions' work, not this session's -- not touched, per this
  item's explicit constraint).
- `paper8_human_authority_approved`: **FAIL** by the script's own design (cannot query the
  live board); true state per the board is **approved** (2026-08-26, scoped to render
  authority, recorded on that sprint item's completion notes).

**PAPER-15 remains correctly blocked**, now by exactly one real external condition (the
shared parent-repo worktree) plus the corpus-completeness gaps listed above -- not claimed
ready.

## PAPER-24 update (2026-08-27T16:24Z): the acceptance gate now genuinely PASSES

Two real fixes landed in the PARENT repo (claimed via Meridian file-locks first; a
pre-existing, unrelated, in-flight test failure from another concurrent session's
uncommitted heading-capitalization work was found, confirmed unrelated via inspection,
and left untouched):

1. **`ooxml_integrity._content_type_issues` false-positive fixed.** Root-caused precisely:
   the validator flagged every zero-byte ZIP directory-placeholder entry (`_rels/`,
   `word/`, etc. -- confirmed via `zipfile.infolist()`, `file_size=0`, name ends in `/`) as
   `missing_content_type` with severity error. OPC parts are addressable byte streams; a
   directory placeholder is not a part and the spec never requires a content-type
   declaration for one. Added `_is_zip_directory_placeholder()` and two regression tests
   (`test_validate_ignores_zip_directory_placeholder_entries_for_content_type`,
   `test_validate_still_rejects_a_real_missing_content_type` -- the second guards against
   the fix silently swallowing a genuine gap). All 35 gold documents now show
   `package_integrity.ok=True` (was 16/35 before this fix, 19/35 false-positive).
2. **PAPER-8's static False replaced with a durable, offline-checkable approval artifact**
   (`E:\MeridianData\ooxml-graph-paper\manifests\paper8-human-approval.json`), read by
   `check_word_authority_gate()`. Fails closed on: missing file, malformed JSON,
   `approved != true`, or missing Meridian sprint-item provenance. The artifact records the
   real 2026-08-26 approval (sprint item 882d486e, scoped to render authority, 2030
   explicitly excluded) -- it does not grant approval, it verifies a durable record of one.

Adam separately built (git commits `c263fe7`/`f15fd65`, this same morning) a real
dirty-parent execution mode in `scripts/check_acceptance_gate.py`
(`capture_parent_snapshot()`, `--allow-dirty-parent` / `MERIDIAN_ALLOW_DIRTY_PARENT=1`):
it fingerprints HEAD + full porcelain status + full diff + the four pinned product files,
and fails closed if any of that changes between the start and end of one gate run. Running
the gate with `--allow-dirty-parent` now against the fixed validator and the durable
PAPER-8 artifact:

```
Verdict: PASS -- PAPER-15 may proceed
[PASS] parent_repo_dirty_snapshot_stable
[PASS] (all semantic-OMML, render, package-integrity, corpus-provenance, untracked-artifact checks)
[PASS] paper8_human_authority_approved
[PASS] parent_snapshot_unchanged_throughout_gate
```

## PAPER-25 update (2026-08-27T17:10Z): 35 -> 60 documents; the "48 golden artifacts" don't exist

Reviewed all remaining 32 staged OmegaUse candidates (63/63 now reviewed): 23 promoted, 9
excluded. All 9 exclusions confirmed distinct from the earlier "顾启朝" dossier, and are
mostly a second, equally systematic pattern: real-format student name + student-ID pairs
filled into thesis/report cover pages. Several of THOSE 9 are themselves the same
underlying document reused under different filenames across task folders (e.g. the same
"许芷涵/2360140827" pair appears in 3 separate files) -- this dataset has more cross-folder
content reuse than filenames suggest.

Checked the OmegaUse-OfficeVal HF repository's actual file tree (734 tracked paths) before
attempting anything: **there is no "golden artifacts" folder.** The dataset card's "48 DOCX
golden artifacts" is a statistic about the paper's own evaluation set, not a distributable
file collection in this repo -- PAPER-25's own notes assumed otherwise. Verified, not
assumed, before reporting this.

With explicit human download authorization obtained, added 2 more documents from
`docx-benchmark`'s `series-seed` folder (CC0-1.0 public domain, previously identified but
never staged pending permission): a blank Series Seed investment agreement template and
its "executed" variant (filled with the standard legal-tech demo filler "Stark Industries,
Inc.", not a real party -- spot-checked). Real, different-domain content (legal contract,
not academic/institutional Chinese documents).

**Corpus now stands at 60 documents** (8 tier1 + 49 tier2 + 3 tier3), all 60 with
`integrity_ok=True`, `render=rendered`, and a retained PDF -- genuinely clean, not
selectively reported. Split re-applied: 6 smoke / 27 scale_up / 27 final.

**Still short of the "100+" target, and the remaining realistic path (a docx-corpus
sample) is a materially different risk than what's been reviewed so far**: docx-corpus is
736K+ files of real scraped web content with, per `dataset-landscape-2026-08-25.md`,
"per-file provenance unverified" and licensing/takedown review explicitly flagged as
mandatory -- not a purpose-built, privacy-reviewed synthetic benchmark like OmegaUse. This
needs its own explicit go-ahead, separate from the general download permission already
given (which was granted expecting the safer golden-artifacts option, which turned out not
to exist).

## PAPER-25 continuation (2026-08-27T19:05Z): 60 -> 127 documents, target reached

Per explicit human instruction to keep going until the 100+ target was actually met, pursued
the previously-flagged docx-corpus path with a stricter review standard than OmegaUse's
(justified: docx-corpus is real Common-Crawl-scraped web content with **no** upstream
privacy screening, unlike OmegaUse's purpose-built, privacy-engineered benchmark).

**Sampling, not raw random draw:** downloaded the dataset's real HF metadata (`superdoc-dev/docx-corpus`,
736,706 rows, columns `id/filename/type/topic/language/word_count/confidence/url`) and
safety-pre-filtered *before* downloading any document content: `type` in
{technical, reference, policies, reports} (excluding forms/correspondence/creative/administrative/legal
as higher-risk categories), `language=en`, classifier `confidence>0.85`, `word_count` in
[200, 5000], and explicitly excluding the `healthcare` topic. This narrowed 736,706 rows to
18,770 candidates before a single file was fetched. Sampled 90 (seed 20260826) from that
pre-filtered pool, downloaded all 90 to `E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\files\`,
verified all 90 are valid ZIP/DOCX packages.

**Review, with a stricter bar:** 90 documents independently reviewed (fresh, isolated agents,
full-text read of each) under an explicitly stricter instruction than OmegaUse's -- exclude on
ANY real individual's personal information (not just name+ID), any document reading as an
internal/leaked artifact not intended for public redistribution, "when in doubt, exclude."
Result: **67 promoted, 23 excluded** (a 74% promotion rate, consistent with the pre-filtering
working). The exclusions are real and specific -- e.g. a filled GxP validation record naming
a specific test engineer with exact work timestamps; several government "Transportation Pooled
Fund Program" quarterly reports naming individual program managers; UK school policies naming
specific safeguarding leads. These read as genuine internal/institutional documents that happen
to name real people in their working capacity -- correctly excluded per the stricter bar, even
though several would likely have been borderline-promotable under OmegaUse's narrower
name+ID-specifically criterion. Full reasoning per file: `E:\MeridianData\ooxml-graph-paper\gold\manifests\_docxcorpus_review.json`.

Verified zero content-hash duplicates among the 67 promoted files, and (separately, as a basic
provenance sanity check) that all 67 are valid, distinct DOCX packages.

**Final corpus: 127 documents**, all with `integrity_ok=True`, `render=rendered`, and a
retained PDF -- zero failures across the full rebuild. Breakdown: 8 tier1 (hand-authored) +
47 tier2-OmegaUse-OfficeVal + 2 tier2-docx-benchmark (CC0-1.0) + 67 tier2-docx-corpus
(Common-Crawl, ODC-BY, ~74% of a safety-pre-filtered, independently-reviewed 90-document
sample) + 3 tier3 (composite). Split re-applied: 10 smoke / 58 scale_up / 59 final, all three
genuinely populated at meaningful size for the first time.

**Re-ran `scripts/check_acceptance_gate.py --allow-dirty-parent` after this expansion: still
PASS, all 12 checks**, confirming the corpus-provenance and package-integrity checks hold at
the new scale, not just the smaller one.

**This PASS does not authorize running PAPER-15.** PAPER-25 (expand to a deduplicated
100+ document pool) and PAPER-26 (pin the product revision and isolate the benchmark
checkout from the shared, still-dirty parent) are both still pending, and each explicitly
states in its own sprint-item notes that PAPER-15 must not run until it completes too. A
passing PAPER-20 gate is necessary but was never sufficient on its own -- the corpus-scale
and reproducible-isolation requirements are separate, larger conditions this single gate
script does not check.

## PAPER-35 final-gate update (2026-08-28): the condition above has since been satisfied

PAPER-25 and PAPER-26 both completed prior to this update. PAPER-29 subsequently
re-audited this same 127-document corpus end-to-end (`docs/paper29-corpus-audit-v0.md`) and
found it clean after one real, fixed gap (a missing machine-readable rights-rationale entry
for the 2 docx-benchmark documents). The real, informal count/overlap PAPER-15 pass, the real
graph-aware PAPER-30 pass, and the real PAPER-31 local-baseline run (including Docling on the
smoke slice) have all since actually executed against this exact corpus -- see
`docs/paper15-first-attempt-v0.md`, `docs/paper30-graph-scorer-v0.md`, and
`docs/paper31-local-baselines-v0.md`. This corpus-status document's own job is done; the final
synthesis lives in `docs/paper35-final-gate-v0.md`, which this note exists only to link
forward to, not to duplicate.
