# PAPER-S7: confirmatory paired Claude-without-vs-with-Meridian benchmark protocol (v1)

Status: **preregistration lock.** Every design decision below is fixed BEFORE the
validation and primary-holdout slices are run (general preregistration discipline
confirmed to bind this track by PAPER-S7 recon, 2026-08-30, even though
`benchmark-preregistration-v0.md` itself never names this track -- see
`docs/paper-s15-skill-matrix-v1.md` section 4 for the boundary between what that item
freezes and what this document freezes). The development slice may be freely run and
inspected before and after this lock (per
`docs/paper-s9-long-horizon-benchmark-protocol-v0.md` section 3's own terminology) --
nothing in the development slice run so far (harness-debugging smoke tests against the
`fixture-01`/`fixture-02` tier-1 GOLD fixtures, a *different* pool from this benchmark's
real corpus) has touched the actual 12-document PAPER-S7 development slice, let alone
validation or primary_holdout.

This is PAPER-S9's fourth, distinct claim (`comparator-contract-v0.md` section 6.1): an
agentic-editing comparison, not an extraction-fidelity comparison. It must never be pooled
with Claims 1-3.

## 1. Corpus (locked)

`manifests/paper-s7-corpus-manifest-v1.json`, built by
`tools/build_s7_docops_corpus_manifest.py` from DocOps' own preregistered split
(`manifests/docops/docops_prereg_split_v1.json`, seed 20260830, PAPER-S13/S16 -- reused, not
re-derived). 38 single-document tasks (4 multi-document "cross_doc_docops" tasks excluded --
this benchmark's task templates are single-document edits):

| Split | Count | Source DocOps stages |
|---|---:|---|
| development | 12 | `development` + `smoke` |
| validation | 12 | `scale_up` |
| primary_holdout | 14 | `final_holdout` |

Full provenance, license (Apache-2.0), and PII-screening status: `docs/paper-s15-skill-matrix-v1.md`
section 3.

## 2. Task families (locked)

Three families, per the tool-matrix freeze in `docs/paper-s15-skill-matrix-v1.md` section 2:
**bibliography, citation, section_reorder.** Caption, cross_reference, table-structural, and
tracked-change families are explicitly excluded for this run, each for a documented,
real reason (Word-COM render-gate timeout under host contention; a missing removal
primitive not yet merged; no whole-table primitive exists; no accept/reject primitive
exists) -- not a silent reduction.

Every family's forward+inverse anchor (or section-reorder plan) is resolved ONCE by the
harness itself (`tools/docx_anchor_prober.py`), never by either agent -- this is the
structural fix for the original PAPER-S20 anchor-resolution failure mode, generalized to
every family rather than re-solved per family.

A document that does not support a given family (e.g. `section_reorder` needs >=3 headings)
is recorded `not_applicable` for that (document, family) pair, never forced or hidden.

## 3. Long-horizon K-pair sweep (locked, with a disclosed scope reduction)

`docs/paper-s9-long-horizon-benchmark-protocol-v0.md` section 4 illustrates sweeping
K in {1, 4, 16}. **This run sweeps K in {1, 4} only.** K=16 is explicitly dropped for
this run: at a confirmatory model's per-trial cost (see section 5), a K=16 chain across
every (document, family, arm) combination in the validation+holdout slices would
multiply already-substantial API cost and wall-clock time roughly 4x over K=4 alone,
for a benchmark whose primary confirmatory question (does an arm's editing quality
degrade as edits accumulate, and does that differ by arm) is already directly testable
at K=4 against K=1's single-shot baseline. K=16 is left as an explicit, disclosed
follow-up for a future, separately-budgeted run, not silently dropped from the design
without comment.

A "chain" is K consecutive forward+inverse pairs of the SAME family/document/arm, each
its own fresh `claude -p` process (`tools/run_paper_s7_benchmark.py::run_chain`), pair
i+1 starting from pair i's own inverse output. This makes process/session round trips
equal K for BOTH arms symmetrically, by construction -- closing PAPER-S9 section 4.2's
confound warning structurally rather than by measurement alone: neither arm can gain an
advantage from "fewer reopens," because both reopen the file exactly K times, always.

## 4. Model (locked)

**`sonnet`** (resolves to `claude-sonnet-5` per `claude --version`/`--model sonnet` probe,
2026-08-30 -- recorded here as the dated version this run actually used, per
`comparator-contract-v0.md` section 5's "no model called 'latest' without a dated version
record") for the validation and primary_holdout slices. `haiku` (`claude-haiku-4-5-20251001`)
remains for the development slice only, matching PAPER-S20's own precedent that a
cheap/fast model is appropriate for harness debugging but not for a confirmatory claim.

## 5. Trial budget and scope (locked, with disclosed cost-driven bounds)

A single `sonnet` trial's system-prompt cache is NOT shared across trials (each is a fresh,
isolated process by design -- PAPER-S15's arm-boundary mechanism), so every trial pays a
full cache-creation cost (~$0.25-0.30 observed for a trivial one-turn probe) rather than
the much cheaper cache-read cost a shared session would get. Running the full cross product
(3 families x 2 K-values x 2 arms x every document) against all 26 validation+holdout
documents would be 3x2x2x26 = 312 chains at a plausible average of several dollars each for
K=4 chains -- real money, and per this project's own "no runaway scope" discipline, a
bounded, explicitly-scoped design is preregistered instead of an unbounded cross product:

- **Breadth pass (K=1 only)**: all 3 families x both arms x every document in validation
  and primary_holdout. This is the primary confirmatory measurement.
- **Depth sub-study (K=4)**: the `bibliography` family only (best-understood, cheapest,
  fewest known confounds) x both arms x every document in validation and primary_holdout.
  This directly tests the long-horizon degradation question without requiring the full
  breadth x depth cross product.
- `citation` and `section_reorder` at K=4 are an explicit, disclosed follow-up, not run in
  this pass.

Trial counts this design commits to:
- Validation: 12 docs x 3 families x 1 arm-pair (2 arms) = 72 K=1 chains, plus 12 docs x 1
  family x 2 arms = 24 K=4 chains. 96 total (before any `not_applicable` exclusions).
- Primary holdout: 14 docs x 3 families x 2 arms = 84 K=1 chains, plus 14 docs x 2 arms = 28
  K=4 chains. 112 total (before any `not_applicable` exclusions).

`not_applicable` counts (e.g. `section_reorder` on a document with <3 headings) are
recorded per family, per split, in the run manifest -- never silently dropped from the
denominator without being named.

## 6. Verification (locked)

Two-tier, per `docs/paper-s9-long-horizon-benchmark-protocol-v0.md` section 5:

- **Fast per-step**: `docx_trial_evaluator.py`'s per-family structural grading (package
  validity, exact-paragraph-list restoration for new-paragraph families, exact anchor-text
  restoration for inline families, exact-order restoration for `section_reorder`) --
  including the `exact_paragraph_list_restored` check added 2026-08-30 after it caught a
  real gap in the original PAPER-S20/S22 evaluator (see
  `docs/paper-s22-harness-verification-v1.md`'s correction section).
- **Milestone (Word COM)**: at chain start (the pristine input) and after every pair --
  never after every raw tool call -- via `tools/word_receipt_watchdog.py`, recording an
  explicit `not_run`/`failed` status on any Word COM failure rather than skipping silently.

## 7. Statistics (locked)

Reuses `tools/graph_scorer.py`'s existing `bootstrap_ci` and `paired_permutation_test`
functions unmodified (confirmed reusable as-is on 0/1 pass/fail outcomes by PAPER-S7 recon,
2026-08-30 -- both are pure arithmetic over lists of numbers with no domain assumptions;
`bootstrap_ci`'s returned "mean" of a 0/1 vector IS the pass rate, and the sign-flip
permutation test on paired 0/1 differences is a valid exact test for matched-pairs binary
data):

- **Pass-rate + 95% bootstrap CI**, per (family, K, arm), computed separately over
  validation and primary_holdout, and over validation+holdout combined -- the combined
  number is the reported confirmatory figure (mirroring `benchmark-preregistration-v0.md`
  section 3's own "computed over scale_up + final slices combined... too small a sample
  for a meaningful interval" rule for the sibling extraction benchmark), never the
  validation slice alone.
- **Paired control-vs-treatment significance**, per (family, K), via `paired_permutation_test`
  on the paired (same document) control/treatment 0/1 outcome vectors, computed over the
  same validation+holdout combined sample.
- A trial that is `not_applicable` for its (document, family) pair is excluded from that
  family's denominator entirely, not scored as 0 and not silently dropped from the reported
  count.
- 2000 resamples/permutations, seed `20260828` -- `graph_scorer.py`'s own existing module
  constants, reused rather than re-chosen, for consistency with every other statistical
  claim in this paper.

## 8. Stopping rule (locked)

Primary_holdout is run exactly once per this frozen protocol version. If a harness defect is
found DURING the primary_holdout run (not merely an expected-and-recorded `not_applicable`
or `not_run`), the run is halted, the defect is fixed and disclosed, and primary_holdout is
re-run in full under the corrected harness -- the partial, defect-affected run's numbers are
retained in this document's revision history, never quietly discarded. Re-running validation
in response to a specific validation-slice failure would require re-declaring this protocol
version and is not done silently.

## 9. What this document does not decide

Whether K=16, the caption/cross_reference/table/tracked-change families, or a larger corpus
should be added is future work, tracked separately (this session flagged
`remove_cross_reference` as implemented but not yet merged; caption's render-gate timeout as
environment-dependent, not fundamental). This document does not claim PAPER-S9's full
long-horizon design (all families, full K sweep, a from-scratch heterogeneous corpus) is
complete -- only that a real, bounded, honestly-scoped confirmatory slice of it is now
locked and ready to execute.
