# PAPER-35/40: final gate — evidence package, limitations, and product demonstration claims (v1)

Status: the complete evidence bundle across PAPER-27 through PAPER-39, distinguishing three
claims per this item's own charge, with every required category present in some form --
either genuine evidence or an explicit, named `not_run`/limitation, never a silent gap.
**This is a synthesis document: every number and claim below is a pointer to a specific,
independently-verified prior artifact, not a new measurement.** This v1 supersedes the
original v0 gate (PAPER-35): the Docling document-AI track is now full-127-document, not a
10-document smoke slice, and one of v0's central claims (native beats python-docx on raw
paragraph text) has been genuinely revised after a gold-corpus bug fix exposed a shared,
previously-hidden limitation. That revision is reported in full below, not smoothed over.

## The three claims, kept separate as required

### Claim 1 — native Meridian OOXML/OMML preserves and editably writes Word structure

Evidence: `docs/gold-corpus-status-v0.md` (127-document corpus, real Word-COM render
receipts), `docs/word-roundtrip-preservation-contract-v0.md`, and the product hardening audit
across PAPER-33 and PAPER-38 (`docs/ooxml-package-safety-audit-v0.md`,
`docs/paper38-hardening-v0.md`). Identity/collision safety was already correct. **All 14
previously-unprotected cross-process write primitives in `docs_intel.py` are now protected**
(2 fixed under PAPER-33, the remaining 12 closed to zero under PAPER-38 -- `insert_cross_reference`,
`insert_citation`, `edit_citation`, `remove_citation`, `append_text_run_after_math`,
`insert_bibliography_entry`, `update_bibliography_entry`, `remove_bibliography_entry`,
`renumber_sequences`, `insert_tracked_paragraph`, `write_section`,
`retrofit_plaintext_captions`), each with a real, independently-verified concurrent-write
regression test. PAPER-38 also found and fixed a genuine silent-data-loss bug: unrecognized
MathML constructs (e.g. `\boxed{}`) were silently flattened to plain text with zero
diagnostic during LaTeX-to-OMML conversion; this now fails closed with a named exception.
**Status: supported, and strengthened since v0** -- the one residual gap v0 reported (12
unprotected write primitives) is now fully closed.

### Claim 2 — deterministic native extraction beats generic same-format parsers (python-docx) on native-structure tasks

**RE-REVISED 2026-08-30 (PAPER-S4): the paragraph-text tie described below is itself now
resolved.** The `_paragraph_text` bug named in this section (packages/docparse/docparse/
docs_intel.py and its vendored copy) is fixed at `dev@54d6f969`, independently verified,
with 10 new focused regression tests plus 771+61 existing tests re-run with no
regressions. The scorer was rerun against the same unchanged 127-document gold corpus:
native paragraph_node_f1 = 0.9984 vs python-docx 0.9836, p_hat = 0/2000 (n=122), mean
diff +0.0164 favoring native. Native genuinely beats python-docx on paragraph text again,
now on honest footing (both sides correctly include tab/break characters). See
`docs/final-results-correction-ledger-v1.md` and
`E:\MeridianData\ooxml-graph-paper\manifests\paper30-graph-eval-all-20260830T070431Z.json`.
The v0-to-v1 revision narrative directly below is retained for the record.

**This claim is revised from v0, based on new evidence, not merely restated.** PAPER-38 found
and fixed a real text-fidelity bug in this paper's own independent gold extractor (dropped
`<w:tab/>`/`<w:br/>` when reconstructing paragraph text; regenerated 71 of 127 documents'
gold text). PAPER-39 then re-ran the full 127-document graph-aware scoring pass against the
corrected gold and found:

- **Equation capability**: native 7/7 correct count and semantic class, versus python-docx's
  zero OMML API surface and 5/127 outright crashes on valid, Word-openable documents
  (`InvalidXmlError` on missing `<w:tblGrid>`). **Unchanged, strongly supported.**
- **Native paragraph-ID preservation**: 0.995 [0.984, 1.0], versus python-docx's zero
  capability to mint one at all. **Unchanged, strongly supported.**
- **Table structure and reading order**: no significant difference (p=1.0 both), an honest
  null result on those two axes, not a failure to find one. **Unchanged.**
- **Paragraph-text F1 -- REVISED.** v0 reported native beating python-docx here at p=0.0.
  After the gold-text fix, PAPER-39's full-corpus paired test now shows **native 0.981 vs.
  python-docx 0.984 -- p=0.903, not statistically significant.** Root cause, confirmed by
  direct code inspection: native Meridian's own real extraction function
  (`document_content_tree`'s `_paragraph_text`, present identically in both
  `packages/docparse/docparse/docs_intel.py` and its vendored copy in
  `extensions/meridian-docs/meridian_docs/_vendored_content_tree.py`) has the **same**
  `<w:t>`-only text-reconstruction bug the paper's gold extractor used to have. Before the
  fix, gold and native shared the bug, so they looked artificially aligned; python-docx's
  `.text` property never had this bug, so correcting gold moved its score toward, not away
  from, the truth. **This is a real, live product limitation**, flagged as follow-up task
  `task_945705a3`, not fixed under this paper's own file locks (the affected files are
  outside PAPER-36/38/39's resource claims).

**Status: supported for structure (equations, native identity, crash resistance);
NOT currently supported, without qualification, for raw paragraph-text content specifically**
-- that is a materially different, more honest claim than v0 made, and PAPER-40 exists in
part to make sure this correction is not lost or softened in the final telling.

### Claim 3 — native OOXML exposes information and guarantees unavailable to rendered-PDF document-AI systems

**This claim is now supported by full-corpus evidence, not a 10-document smoke slice.**
PAPER-36 ran Docling across all 127 documents (120 scored on the first pass, 6 crashed + 1
timed out; all 6 crashes and the timeout's shorter budget were retried, with 6/7 succeeding
cleanly on retry and one 68-page document confirmed to hit a genuine, persistent capacity
limit even at 3x the timeout). PAPER-39 then ran the full graph-aware paired comparison:

| Metric | native vs. Docling | python_docx vs. Docling |
|---|---|---|
| paragraph node F1 | +0.630, **p=0.0**, n=99 | +0.634, **p=0.0**, n=99 |
| reading-order accuracy | +0.010, **p=0.0**, n=95 | +0.007, **p=0.0**, n=93 |
| table node F1 | +0.162, **p=0.0**, n=56 | +0.162, **p=0.0**, n=56 |
| table row exact-match rate | +1.000, **p=0.0**, n=56 | +1.000, **p=0.0**, n=56 |

Docling **never once** achieves an exact table row count across 56 documents where it
detected any table structure at all. Its FAST-mode, no-formula-enrichment configuration finds
zero equations on every document (0/127) -- consistent with PAPER-28's single-document
finding that equations get OCR'd as literal glyph sequences, not semantic formulas. PAPER-34's
flatten-OMML-to-text ablation independently corroborates the mechanism: even a system that
captures equation *text* but not *structure* drops semantic-class accuracy from 1.0 to 0.643
-- a lower bound on what a pixel/OCR-only reader loses. Five specific facts remain, by
construction, unavailable to any PDF-only reader, named explicitly rather than scored as a
fabricated 0: native `w14:paraId`, revision history, source bindings/provenance, direct
editability, and raw OMML structure (`comparator-contract-v0.md` §7.3).

Resource cost, also now confirmed at full-corpus scale: Docling's mean wall time is 42.6s
(subprocess total 58.5s) vs. 0.17s/0.07s for native/python-docx, and peak memory is 1.68 GB
vs. 2-3 MB -- roughly 250-600x slower and 300-700x more memory, on CPU-only `torch` despite
an unused RTX 3080 being present on the host (a real, actionable, untried optimization
opportunity).

**Status: supported at full-corpus scale with formal paired significance** -- this is the
single largest evidentiary upgrade since v0, which had only a 10-document data point for this
claim. The hosted document-AI track (PAPER-32) remains `not_run` by design, no credential or
approval supplied, and is not needed to support this claim as framed (a local, open baseline
is sufficient evidence for the capability comparison being made).

## Evidence bundle checklist (per this item's own required categories)

| Category | Present? | Where |
|---|---|---|
| Corpus manifest | Yes, 127 documents, audited twice (PAPER-29, PAPER-37) | PAPER-29 found and fixed 1 real gap (a missing rights-rationale entry), 0 remaining after. PAPER-37 fixed nothing itself -- it excluded one new non-DOCX candidate source (MathMLben) and reconfirmed, rather than resolved, the corpus's existing known gaps (see limitations below): `docs/paper29-corpus-audit-v0.md`, `docs/paper37-corpus-audit-v0.md`, `E:\MeridianData\ooxml-graph-paper\gold\manifests\_run_manifest.json`/`_summary.json`/`_split.json` |
| Licenses/privacy decisions | Yes, per-document rationale for every non-fixture document | `_tier2_review.json`, `_docxcorpus_review.json` |
| Source/output hashes | Yes | `source_sha256` per gold manifest; `input_hash_sha256`/`output_hash_sha256` per render receipt; per-document input hashes in every run report |
| Code revision | Yes | Both repos dirty throughout, by explicit standing authorization; PAPER-26's pinned-worktree/dirty-snapshot mechanism is the formal reproducibility record |
| Pixi lock/prefix | Yes | `ooxml-graph-paper/pixi.lock` (isolated subproject environment) |
| Hardware | Yes | AMD Ryzen 7 7840U, 31.3 GB RAM, Windows 11 Home, NVIDIA RTX 3080 present but unused (CPU-only Docling) |
| Word version | Yes | `16.0.20326.20100` (Office16 Click-to-Run) |
| Model/API versions | Yes | Docling 2.123.0 stack fully pinned; no LLM/API model used as a scored baseline anywhere |
| Prompts | N/A, disclosed as such | No scored baseline is prompt-driven |
| Token/cost accounting | Yes | `deterministic_model_tokens: 0` for all three local systems; hosted track `not_run` with reason |
| Per-document failures | Yes, full corpus | python-docx: 5/127 crashes named. Docling: two independent full-corpus runs (PAPER-36, PAPER-39) each had a small, *different* set of transient crashes/timeouts, all but one (a 68-page document, a genuine persistent capacity limit) resolved on individual retry -- both runs' addenda retained separately, never silently merged into headline numbers |
| Confidence intervals | Yes | Bootstrap 95% CIs on every metric, full 127-document corpus, all three systems |
| Paired significance tests | Yes, all pairwise combinations | native-vs-python_docx, native-vs-Docling, python_docx-vs-Docling; exact method (paired sign-flip permutation, 2000 resamples, seed 20260828) and exact `n` stated for every reported p-value |
| Ablations | Yes, 4 of 6 run, 1 cross-referenced, 1 explicitly deferred | `docs/paper34-ablations-v0.md` |
| Receipts | Yes | 127/127 retained Word-COM render receipts, audited present twice |
| Known limitations | Yes, consolidated below | This section |

## Consolidated known limitations (collected from every prior item, not re-litigated here)

- **Zero of the 119 real-world documents in the corpus contain a native OMML equation**
  (PAPER-37, reconfirming PAPER-15's original finding) -- all 7 equation-bearing documents are
  hand-authored tier1/tier3 fixtures, not organic content. This bears directly on how to read
  both Claim 2 (native's "7/7 correct equation count and semantic class" is real but measured
  entirely on synthetic fixtures, not demonstrated on real-world documents) and Claim 3
  (Docling's "0/127 equations found" is trivially true for the 120 documents that have zero
  equations in gold to begin with; the equation-detection comparison is meaningfully tested
  only on those same 7 fixture documents, not across the full corpus).
- **RESOLVED 2026-08-30 (PAPER-S4).** Native Meridian's real paragraph-text extraction
  (`packages/docparse/docparse/docs_intel.py` and its vendored copy) previously shared a
  tab/br-dropping bug with what was, until PAPER-38, also a gold-corpus bug -- `task_945705a3`.
  The product fix is now merged (`dev@54d6f969`), independently verified, and rerun against
  the unchanged 127-document gold corpus: native genuinely beats python-docx on raw
  paragraph text again (p_hat = 0/2000, n=122, +0.0164 mean diff), on honest footing this
  time. Claim 2's scope is restored to "native beats python-docx on text and structure."
- **`text_token_f1`'s whitespace tokenization is a poor fit for CJK content** (PAPER-31) --
  unresolved, needs a script-aware tokenizer.
- **Pandoc and LibreOffice (Claim 2's other two named comparator families) are `not_run`** --
  neither is installed on this host; only python-docx was actually run against native
  Meridian for Claim 2.
- **Edge-level graph scoring covers only `contains` (via node correspondence) and order** --
  `caption_for`, `references`, `revises`, `clones`, `conflicts_with` are not yet separately
  scored edges; `caption`, `anchor`, `reference`, `source_binding`, `revision` node kinds have
  no candidate adapter yet for any comparator system.
- **Ablation (f) (born-digital vs. rasterized PDF) is `not_run`** -- no PDF rasterization
  library installed on this host.
- **Two individual documents sit at or past this pipeline's practical Docling processing
  budget on their own merits, independent of resource contention**: a 68-page document
  (`tier2-omegause-033-price-catalog`) confirmed to time out even at a 3x-longer 900s budget,
  and one large document (`tier2-omegause-025-business-plan`) whose clean retry took 398
  seconds, longer than the standard 300s timeout every other document is scored against --
  not assumed resolved just because one retry happened to finish.
- **Hosted document-AI (PAPER-32) is `not_run`** -- no credential, data-handling approval, or
  cost approval supplied; an ambient, unscoped AWS credential exists on this host but was
  explicitly not used, per standing instruction.
- **The shared parent product repository's full test suite shows exactly 169 failures**
  throughout this entire sprint, caused by a different, concurrent, in-progress, incomplete
  refactor unrelated to this paper's own changes (root-caused and disclosed in full in
  `docs/ooxml-package-safety-audit-v0.md`; reconfirmed unchanged in count across both PAPER-33
  and PAPER-38's separate hardening passes) -- a real statement about the current state of the
  shared codebase this evaluation runs against, not a defect this paper introduced.
- **A near-miss occurred and was disclosed in full during PAPER-33's hardening pass**: an
  agent overwrote an existing 40-test file down to 8 tests while claiming to have "added" a
  file; caught by independent verification, fully remediated (all 48 tests restored/added,
  verified), and documented rather than hidden.
- **PAPER-15's own original sprint item was reconciled** (a stale claim from a different,
  no-longer-active session, closed to match work already completed under later items) rather
  than left permanently orphaned.
- **Both repositories are dirty** (uncommitted working-tree state) throughout this entire
  evaluation, by explicit standing authorization -- PAPER-26's pinned-worktree/dirty-snapshot
  mechanism is the formal reproducibility answer to this.

## Is the final benchmark complete, per this item's own bar?

This item's own acceptance language: *"Final completion is allowed only when the corpus-wide
native/parser run and scorer have terminal manifests; a hosted AI track may remain explicitly
not_run."* Applying that test directly: the corpus-wide native/parser run is complete
(127/127 for native, 122/127 for python-docx with 5 named crashes), the local document-AI
track is now also corpus-wide complete (126/127 Docling, 1 genuine persistent capacity
limit), the scorer has terminal manifests for all three systems with full paired statistics,
and the hosted track is explicitly `not_run` by design, exactly as the bar permits.
**This gate is complete by its own stated bar.** What has changed since v0 is not
completeness but correctness: v0 was complete-but-narrower (a 10-document Docling slice, and
one now-corrected claim about paragraph text); this version is complete at full corpus scale
and states plainly where an earlier reported advantage did not survive a bug fix, rather than
letting a since-superseded number stand uncorrected in the final telling.
