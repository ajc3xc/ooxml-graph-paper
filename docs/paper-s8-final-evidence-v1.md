# PAPER-S8: PAPER-S7 final evidence and limitations package (v1)

Status: the real, executed result of `docs/paper-s7-protocol-v1.md`'s locked confirmatory
design, **updated 2026-09-04 after four real harness/evaluator defects were found, fixed, and
disclosed** (the fourth via a deliberate stress test using hand-authored adversarial
fixtures, not organic corpus data), plus a separately preregistered section_reorder
follow-up (`docs/paper-s7-section-reorder-followup-protocol-v1.md`) and a 4th task family,
equation (section 2.5). Every number below comes from an
actual `claude` CLI run against real documents, graded by `tools/docx_trial_evaluator.py`
entirely outside the agent, aggregated by `tools/compute_s7_statistics.py` using
`tools/graph_scorer.py`'s existing bootstrap/permutation functions unmodified. This is
PAPER-S9's fourth, distinct claim (`comparator-contract-v0.md` section 6.1): an
agentic-editing comparison, never pooled with Claims 1-3 (native-OOXML-extraction fidelity).

Raw manifests (corrected, current):
`E:\MeridianData\ooxml-graph-paper\runs\paper-s7\validation-k1-fixrerun-20260831T145852Z\`,
`...\holdout-k1-fixrerun-20260831T145852Z\`,
`E:\MeridianData\ooxml-graph-paper\runs\paper-s7-v2-section-reorder\` (follow-up corpus).
K=4 depth-study manifests are still being (re-)collected as of this writing -- see section 7.

## 0. What changed since the original run (read this first)

Three real defects were found and fixed during post-hoc investigation of surprising results,
each disclosed in full rather than quietly patched around:

1. **Bibliography's 0%/0% both-arms result** was a real product gap:
   `remove_bibliography_entry` never cleaned up the "References" heading
   `insert_bibliography_entry` creates on first use. Fixed upstream (parent repo commit
   `d65cea2f`, a new opt-in `remove_heading_if_empty` parameter) and wired into the harness
   (`5814d2c`). Result: **both arms now pass 96-100%** (section 2.1).
2. **Citation's apparent treatment underperformance** (88.5% vs control's 96.2% in the
   original run) was a harness bug, not a real capability gap: the inverse trial reused an
   `anchor_para_id` resolved from the *pristine* document, but Meridian's synthetic
   content-derived id changes once forward's own edit modifies that paragraph's text --
   stale only for treatment, since control's instructions are always a fresh text search.
   Fixed by deferring inverse-spec construction until after forward completes, mirroring the
   caption family's existing pattern (`1eb8603`). Result: **treatment jumps to parity with
   control, 96.2% vs 100%** (section 2.2).
3. **Section_reorder's grading itself had a bug** discovered while running a follow-up
   corpus for more statistical power: `grade_forward_trial_reorder` compared an unstripped
   heading string against stripped paragraph text, silently failing on any real-world
   document with incidental whitespace in a heading (`2ccf4cb`). Zero impact on the original
   26-document corpus (confirmed directly), but it explains why an initial pass over the new,
   independently-sourced 48-document follow-up corpus looked artificially bad. Fixed and all
   affected trials re-graded from their existing output files (no re-run needed). The
   follow-up's real, corrected result is section 2.3's most important finding: **it does not
   confirm the original corpus's suggestive direction.**

4. **A second, distinct section_reorder defect** surfaced by deliberately building
   hand-authored adversarial fixtures to probe genuine structural ambiguity, rather than
   waiting for organic corpus data to happen to hit it: `resolve_section_reorder_plan`
   picked its destination heading with no awareness of heading level, so on documents with
   nested Heading1/Heading2 structure it could pick a heading that is itself a CHILD of the
   section being moved -- a logically incoherent "move this section to appear after part of
   itself." `move_section` correctly no-ops on this; the grader read that as a **treatment**
   failure while control's arbitrary response to the same nonsense instruction often passed
   anyway. Confirmed in 4 of 48 v2 documents, zero in v1. Fixed (`8c7ae16`); the 2 documents
   with a genuinely corrected plan were re-run and now pass on both arms. Result: section
   2.3's combined figure improves from p=0.57 to **p=0.39** -- still not significant, but a
   meaningfully different picture than before the fix.

A fifth defect (a false-negative in `tools/pii_pattern_scan.py`, the tool used to screen
acquired documents for personal data before promoting them into any corpus) was also found
and fixed during this work; see `docs/paper-s6-organic-omml-round2-3-result-v1.md`'s
correction section for that one's full writeup -- it affects acquisition safety, not any
number in this document.

## 1. What was run

- **Corpus**: 26 documents (12 validation + 14 primary_holdout, DocOps-derived, per
  `docs/paper-s7-protocol-v1.md` section 1), plus a separately preregistered 48-document
  section_reorder-only follow-up corpus (`docs/paper-s7-section-reorder-followup-protocol-v1.md`)
  built specifically because the original corpus only yields 11 section_reorder-applicable
  documents.
- **Families**: bibliography, citation, section_reorder (3 of 6+ candidate families
  investigated -- section 5).
- **K-pair sweep**: breadth pass at K=1 across all 3 families on both corpora; a depth
  sub-study at K=4 (bibliography, citation, section_reorder) on the original v1 corpus,
  section 2.4 -- delayed by repeated real infrastructure interruptions on a shared host
  (three separate crashes; see section 7 and `tools/run_paper_s7_benchmark.py`'s new
  checkpoint/resume support, added mid-collection specifically because of this) but now
  complete.
- **Model**: `claude-sonnet-5` (`--model sonnet`) throughout.
- **Arms**: control (generic Read/Write/Edit/Bash, zero Meridian MCP access) vs. treatment
  (exactly one Meridian bounded write-primitive pair per family, zero generic editing tools)
  -- isolation audited per trial, both directions clean throughout.
- **Primary holdout was run twice** for the original v1 corpus, both for the concurrency
  defect described in section 4 AND for the citation/bibliography fixes described above --
  each re-run following the protocol's own stopping rule (halt, fix, disclose, re-run in
  full). All v1 numbers below are from the final, corrected re-run.

## 2. Results

### 2.1 bibliography (fixed)

| K | Arm | N | Pass rate (95% CI) |
|---|---|---:|---|
| 1 | control | 26 | 100% [100%, 100%] |
| 1 | treatment | 26 | 96.2% [88.5%, 100%] |

Paired significance: `observed_mean_diff=+0.038`, `p=1.0` -- statistically indistinguishable;
both arms near-ceiling. This is the expected, correct shape of a genuine round-trip-fidelity
result once the real heading-cleanup gap (section 0) was closed -- a **parity** finding, not
a difference to chase further significance on. The one treatment "failure" out of 26 is a
single grading edge case, not a repeated pattern.

### 2.2 citation (fixed)

| K | Arm | N | Pass rate (95% CI) |
|---|---|---:|---|
| 1 | control | 26 | 100% [100%, 100%] |
| 1 | treatment | 26 | 96.2% [88.5%, 100%] |

Paired significance: `observed_mean_diff=+0.038`, `p=1.0` -- statistically indistinguishable.
The single remaining treatment "failure" is a genuine process-level timeout on one forward
call, unrelated to the stale-anchor-id bug that was fixed (confirmed by inspecting that
specific chain directly). Like bibliography, this is a **parity** result once the harness
defect was closed, not evidence of a real difference between arms in either direction.

### 2.3 section_reorder (investigated, honestly does not confirm)

**Original v1 corpus** (n=11 applicable documents, unaffected by any of the three fixes --
confirmed directly, zero of 52 v1 section_reorder chains hit the grading whitespace bug):

| Arm | N | Pass rate (95% CI) |
|---|---:|---|
| control | 11 | 72.7% [45.5%, 100%] |
| treatment | 11 | 100% [100%, 100%] |

Paired significance: `p=0.2395` -- directionally favors treatment, not statistically
significant, wide CI. This is the number that motivated a real follow-up rather than either
accepting it as confirmed or quietly dropping it.

**Follow-up v2 corpus** (n=46 after a second correction below, independently sourced,
PII-screened, and content-reviewed -- `docs/paper-s7-section-reorder-followup-protocol-v1.md`;
grading bug from section 0 fixed before this result was computed):

| Arm | N | Pass rate (95% CI) |
|---|---:|---|
| control | 46 | 80.4% [69.6%, 91.3%] |
| treatment | 46 | 82.6% [71.7%, 93.5%] |

Paired significance: `observed_mean_diff=-0.022` (favoring treatment), `p=1.0`.

**Combined v1+v2** (n=57, pooling explicitly disclosed -- the two pools come from different
source distributions, curated DocOps benchmark tasks vs. real-world scraped documents):

| Arm | N | Pass rate (95% CI) |
|---|---:|---|
| control | 57 | 78.9% [68.4%, 89.5%] |
| treatment | 57 | 86.0% [75.4%, 94.7%] |

Paired significance: `observed_mean_diff=-0.070`, `p=0.3885`.

**A second correction, found by deliberately trying to break the harness (2026-09-04)**:
three hand-authored fixtures were built to probe genuine structural ambiguity (not part of
the confirmatory corpus). One -- duplicate heading text across two subsections -- exposed
that `resolve_section_reorder_plan` picked its destination heading with no awareness of
heading LEVEL, so on documents with nested Heading1/Heading2 structure it could pick a
Heading2 that is itself a CHILD of the section being moved: a logically incoherent "move
this section to appear after part of itself." `move_section` correctly no-ops on this
(destination already inside the source range); that graded as a spurious **treatment**
failure while control's arbitrary response to the same nonsensical instruction often
satisfied the grader's loose checks anyway. Confirmed present in 4 of 48 v2 documents (zero
in v1). Fixed (`docx_anchor_prober.py` commit `8c7ae16`): the destination must now be a
genuine sibling heading. 2 of the 4 affected documents now correctly report
`not_applicable`; the other 2 were re-run under the corrected resolver and now pass cleanly
on both arms. The numbers above already reflect this correction -- see
`docs/paper-s7-section-reorder-followup-result-v1.md` for the pre-correction figures and
full audit.

**Honest conclusion**: still not significant at conventional thresholds, but the corrected
picture is more nuanced than "no effect." The effect size favoring treatment grew (7.0
points combined, up from 5.1 pre-correction) and the p-value improved meaningfully (0.39,
down from 0.57) once a defect that specifically penalized treatment was fixed. This does
not confirm the original 11-document corpus's suggestive 72.7%-vs-100% direction at n=11 --
that gap was still driven by small-sample variance, not a large real effect -- but it no
longer supports "small-sample fluke, true effect is zero" as confidently as the
pre-correction number did. A larger follow-up remains the honest way to settle this either
way. Full writeup: `docs/paper-s7-section-reorder-followup-result-v1.md`.

### 2.4 Depth sub-study: K=4, repeated edit cycles (original v1 corpus only)

Complete as of 2026-09-02, after three real infrastructure interruptions (a session
disconnect, shared-host resource contention, and a full computer crash) that motivated
adding checkpoint/resume support to `run_chain` mid-collection (commit `deb2e90`) --
each chain now writes an atomic result file and a re-run skips anything already
genuinely finished, rather than losing hours of prior work to redo it. This sub-study was
run only against the original 26-document v1 corpus, per the locked protocol's own
disclosed cost-driven scope (section 5 of `docs/paper-s7-protocol-v1.md`); it was not run
against the 48-document section_reorder follow-up corpus.

| Family | K | Arm | N | Whole-chain pass rate (95% CI) | Steady-state pairs 2-4 (95% CI) |
|---|---|---|---:|---|---|
| Bibliography | 4 | control | 26 | 100% [100%, 100%] | 100% [100%, 100%] |
| Bibliography | 4 | treatment | 26 | 100% [100%, 100%] | 100% [100%, 100%] |
| Citation | 4 | control | 26 | 96.2% [88.5%, 100%] | 98.7% [96.2%, 100%] |
| Citation | 4 | treatment | 26 | 96.2% [88.5%, 100%] | 98.1% [94.2%, 100%] |
| Section reorder | 4 | control | 11 | 63.6% [36.4%, 90.9%] | 90.9% [81.8%, 100%] |
| Section reorder | 4 | treatment | 11 | 100% [100%, 100%] | 100% [100%, 100%] |

Paired significance (whole chain): bibliography `p=1.0`, citation `p=1.0`, section_reorder
`p=0.119`.

Bibliography and citation both hold their K=1 parity finding under repeated cycling --
neither arm shows compounding drift across 4 consecutive edit cycles, and citation's
steady-state numbers (excluding the first pair) are essentially perfect for both arms.
Section_reorder's K=4 whole-chain gap (63.6% vs 100%) is numerically larger than its K=1
result and closer to conventional significance (p=0.119 vs p=0.24) -- but this is still the
same n=11 original corpus, not the properly-powered 59-document combined sample from
section 2.3. It does not override that null result; it is additional, honestly-reported
descriptive evidence about repeated-cycle behavior specifically, at a sample size too small
to draw a confirmatory conclusion from on its own. The steady-state figures (90.9% vs 100%)
suggest most of the gap concentrates in the first cycle rather than compounding further.

## 3. What this evidence does and does not support

**Supported**, on these corpora, at this sample size, with this model:
- Bibliography and citation show no significant difference between arms -- both fixed from
  real defects (harness and product) to genuine near-ceiling parity.
- Section_reorder, investigated across two independently-sourced corpora totaling 57 paired
  documents (after correcting a real plan-coherence defect, section 2.3), shows a direction
  favoring treatment (86.0% vs 78.9%) that is not statistically significant at this sample
  size (p=0.39). The original 11-document corpus's much larger suggestive gap did not
  replicate, but the corrected combined result no longer reads as a clean small-sample fluke
  either -- a genuinely open question, not a settled null.

**Not supported by this evidence**:
- Any claim that Meridian's bounded tools outperform generic editing on these three task
  families -- none show a significant edge in either direction once real defects are fixed.
- A general claim across ALL task types -- only 3 of 6+ candidate families were tested.
- Any claim about caption, cross_reference, table-structural, or tracked-change editing --
  none were run (section 5).
- Generalization beyond these specific corpora and a K in {1, 4} sweep.

This is a materially different bottom line than earlier drafts of this document reported,
and it is reported here exactly as found: real product/harness bugs were fixed (raising two
families from misleading or backwards-looking results to genuine parity), and a real,
good-faith attempt to confirm the one remaining suggestive finding came back null. That is
the actual evidentiary state of this work.

## 4. The concurrency-collision incident (a real, disclosed methodological finding)

The FIRST primary_holdout run (`holdout-k4-20260831T013513Z`) contained one control-arm
trial (`docops_v2_l3_008_docx_mobility_board_packet_release`, K=4, pair 0 forward) whose
output `word/document.xml` collapsed from 48,052 to 2,701 bytes -- 307 paragraphs down to
7 -- while every other ZIP part in the package stayed byte-identical to the original.

### 4.1 Root cause, found by reading the actual transcript, not guessed

The agent's own recorded Bash commands show a **correct, safe editing approach**: extract
to a temp directory, insert two new paragraphs via `content[:idx] + new_paras + content[idx:]`
(pure insertion, nothing removed), then rebuild the archive by copying every original ZIP
entry via Python's `zipfile` module and substituting only the modified `document.xml`. This
script is not the bug.

The actual defect: the agent extracted to a **fixed, non-trial-specific path**
(`C:\Users\...\AppData\Local\Temp\claude\extract_doc`) rather than a location scoped to its
own trial. Cross-referencing trial start/end timestamps in the run manifest found a
**second, independent control-arm trial**
(`docops_v2_l3_006_docx_grant_closeout_release`, inverse direction) running with a
partially overlapping wall-clock window: that trial ran 02:09:13.5-02:10:00.8 UTC against
this one's 02:09:40.3-02:10:32.6 UTC, an overlap of roughly 20 of each trial's ~50 seconds
(about 40% of either window) -- concurrent, but not fully coincident.
Under this harness's own concurrent execution (`--max-workers 3`), two agents independently
choosing the same conventional-looking scratch path very likely collided: one process's
`rm -rf extract_doc/* && unzip` interleaving with the other's in-progress edit, truncating
whichever document was mid-read at that moment.

This is a **harness concurrency defect**, not evidence about generic-tool editing quality
per se: `--add-dir <trial_root>` (documented in `docs/paper-s15-skill-matrix-v1.md` section
1) grants ADDITIONAL directory access, it does not confine Bash to only that directory --
an agent remains free to read/write anywhere the OS user account can, including a shared
global temp path.

### 4.2 Fix and re-verification

`tools/claude_pair_runner.py`'s `run_trial()` now points `TEMP`/`TMP`/`TMPDIR` at a
trial-unique `scratch/` subdirectory for every subprocess (commit `8d3d291`), so an agent
that reasonably assumes "the system temp directory" is private to its own process actually
gets one that is. Checked all collected slice manifests for the same signature (>5 missing
original paragraphs in one grading result): found in exactly one trial, the one described
above. Per the protocol's own stopping rule, the complete primary_holdout slice was re-run
in full under the corrected harness rather than patched around.

### 4.3 Why this belongs in the paper, not just a bugfix log

A benchmark whose control arm's own generic tooling can silently interact with concurrently
running processes via shared, conventional OS paths is itself a small piece of real evidence
about the operational fragility of ad-hoc, script-based document editing under real-world
multi-process conditions -- distinct from, but related to, this paper's broader thesis about
bounded, atomic operations being safer than unrestricted generic tool access. Meridian's own
write primitives never touch a shared global scratch path; each operates via a direct,
sequential Python function call scoped to its own `docx_path` argument, structurally immune
to this specific collision class.

## 5. Families excluded, with real reasons (per `docs/paper-s15-skill-matrix-v1.md`)

- **caption**: `insert_caption` performs a synchronous Word-COM render-verification write
  gate that fails closed (by design, per `_enforce_render_verification`'s documented
  three-state contract) on a render timeout, not merely an unavailable backend. Reproduced
  twice on this host under concurrent session load. A candidate for a future run under
  lower host contention or a longer render timeout, not a permanent exclusion.
- **cross_reference**: `insert_cross_reference` had no removal primitive as of this run's
  design. `remove_cross_reference` was implemented, tested (83+379 tests passing), and has
  now been merged to the parent repo's `dev` branch (commit `a89dd999`) -- too late to
  include in this run, a clean candidate for the next one.
- **table-structural**: no whole-table create/remove primitive exists at any level;
  `insert_column`/`split_cell` have zero inverse of any kind.
- **tracked-change**: `insert_tracked_paragraph` exists as library code but is not
  registered as an MCP tool, and no accept/reject/deletion-tracking primitive exists at all.

## 6. Explicit, disclosed scope limitations

- 3 of 6+ candidate task families (this document's whole subject).
- K=1 confirmed on both corpora; K=4 depth data (section 2.4) is complete but only against
  the original v1 corpus, not the section_reorder follow-up -- see section 7.
- Section_reorder's follow-up corpus (48 documents) comes from a different source
  distribution (real-world scraped documents) than the original 26-document DocOps-derived
  corpus -- the combined n=59 figure discloses this pooling rather than hiding it.
- `claude-sonnet-5` only -- no cross-model comparison.
- Isolation was audited per trial (post-hoc transcript scan) and held throughout, but the
  concurrency-collision incident (section 4) shows a DIFFERENT kind of cross-trial
  interference than the control-reaching-Meridian violation the isolation audit itself
  checks for.
- Three real defects (sections 0, 2.3, and the PII scanner correction in
  `docs/paper-s6-organic-omml-round2-3-result-v1.md`) were found DURING this project's own
  analysis of its own results, not by external review -- disclosed in full per this
  project's standing "never quietly patch around a surprising result" discipline, but a
  reader should weigh that these are the defects THIS team happened to notice, not a claim
  that no further defects exist.

## 7. Recommended next steps (not run here)

- **K=4 depth study is complete** (section 2.4) -- it took three interruptions to collect
  (a session disconnect, `STATUS_DLL_INIT_FAILED` process-launch failures under real
  shared-host resource contention, and a full computer crash; none a harness or product
  defect), which is exactly what motivated adding checkpoint/resume support to the harness
  itself mid-collection rather than continuing to manually audit and restart.
- Run section_reorder's K=4 depth study against the 48-document follow-up corpus too, now
  that checkpointing makes a multi-hour run far cheaper to sustain -- would give a properly
  powered read on whether section_reorder's K=4 gap (section 2.4) is real or, like its K=1
  counterpart, regresses toward parity with more data.
- Re-run caption after either reducing host contention or raising its render timeout.
- Add cross_reference now that `remove_cross_reference` is merged.
- K=16 depth, cost permitting.
- A dedicated cross-trial-interference audit dimension (distinct from the existing
  control-reaches-Meridian isolation check) given section 4's finding.
