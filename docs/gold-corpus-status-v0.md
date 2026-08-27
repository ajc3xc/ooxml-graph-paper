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
