# PAPER-S8: PAPER-S7 final evidence and limitations package (v1)

Status: the real, executed result of `docs/paper-s7-protocol-v1.md`'s locked confirmatory
design. Every number below comes from an actual `claude` CLI run against real DocOps
documents, graded by `tools/docx_trial_evaluator.py` entirely outside the agent, aggregated
by `tools/compute_s7_statistics.py` using `tools/graph_scorer.py`'s existing bootstrap/
permutation functions unmodified. This is PAPER-S9's fourth, distinct claim
(`comparator-contract-v0.md` section 6.1): an agentic-editing comparison, never pooled with
Claims 1-3 (native-OOXML-extraction fidelity).

Raw manifests: `E:\MeridianData\ooxml-graph-paper\runs\paper-s7\validation-k1-20260830T232217Z\`,
`...\validation-k4-20260831T000200Z\`, `...\holdout-k1-rerun-20260831T023817Z\`,
`...\holdout-k4-rerun-20260831T033222Z\`. Combined statistics:
`E:\MeridianData\ooxml-graph-paper\manifests\paper-s7-final-statistics-v1.json`.

## 1. What was run

- **Corpus**: 26 documents (12 validation + 14 primary_holdout, DocOps-derived, per
  `docs/paper-s7-protocol-v1.md` section 1 / `docs/paper-s16-split-methodology-v1.md`).
- **Families**: bibliography, citation, section_reorder (3 of 6+ candidate families
  investigated -- caption, cross_reference, table-structural, and tracked-change were
  excluded with documented reasons, section 5 below).
- **K-pair sweep**: breadth pass at K=1 across all 3 families; depth sub-study at K=4,
  bibliography only (per protocol section 5's disclosed cost-driven scope reduction --
  K=16 was not run).
- **Model**: `claude-sonnet-5` (`--model sonnet`) for both validation and primary_holdout.
- **Arms**: control (generic Read/Write/Edit/Bash, zero Meridian MCP access) vs. treatment
  (exactly one Meridian bounded write-primitive pair per family, zero generic editing
  tools) -- isolation audited per trial, both directions clean throughout this run.
- **Primary holdout was run twice.** The first run (`holdout-k1-20260830T004708Z` /
  `holdout-k4-20260831T013513Z`) surfaced a real harness defect (section 4) and was
  superseded, per the protocol's own stopping rule, by a full re-run
  (`holdout-k1-rerun-20260831T023817Z` / `holdout-k4-rerun-20260831T033222Z`) under the
  corrected harness. All numbers in this document are from the corrected re-run; the
  original run is retained on disk for the record, not as evidence.

## 2. Results

### 2.1 bibliography

| K | Arm | N | Pass rate (95% CI) |
|---|---|---:|---|
| 1 | control | 26 | 0.0% [0.0%, 0.0%] |
| 1 | treatment | 26 | 0.0% [0.0%, 0.0%] |
| 4 (whole chain) | control | 26 | 0.0% [0.0%, 0.0%] |
| 4 (whole chain) | treatment | 26 | 0.0% [0.0%, 0.0%] |
| 4 (steady state, pairs 2-4) | control | 26 | 94.9% [88.5%, 100%] |
| 4 (steady state, pairs 2-4) | treatment | 26 | **100% [100%, 100%]** |

**0% is not a failure of the harness or the product -- it is `insert_bibliography_entry`
locate-or-CREATING a "References" heading the first time it runs on a document without one,
which `remove_bibliography_entry` never removes** (a real, reasonable design choice --
you would not want a whole section auto-deleted because its last entry was removed). This
was found live during development-slice testing (`docs/paper-s22-harness-verification-v1.md`'s
correction section) and reproduces on **100% of 52 applicable K=1 chains across both arms**,
confirming it is a universal, task-wording-level property, not an arm-specific defect --
paired significance test: `p=1.0`, `observed_mean_diff=0.0`.

The steady-state metric (pairs 2 through 4 of the K=4 chains, i.e. every cycle AFTER the
one-time heading creation) tells the real long-horizon story: **neither arm shows
compounding drift** with repeated insert+remove cycling, but **treatment is perfectly
reliable (100%, 26/26) while control has a small, nonzero residual failure rate (94.9%,
~1-2 of 26)** even once past the known first-cycle side effect. This is descriptive, not a
formally paired significance-tested claim (the steady-state metric was added after seeing
the K=4 pattern, per this project's own "record what you see, don't dress it up" rule --
see section 4.3).

### 2.2 citation

| K | Arm | N | Pass rate (95% CI) |
|---|---|---:|---|
| 1 | control | 26 | 96.2% [88.5%, 100%] |
| 1 | treatment | 26 | 88.5% [76.9%, 100%] |

Paired significance: `observed_mean_diff=+0.077` (control minus treatment), `p=0.628` --
**not statistically significant.** Control nominally edges out treatment here, driven in
part by one genuine treatment-arm timeout at primary_holdout (`insert_citation`, 300s,
`composite_same_type__wordc_005...`, reported honestly as a real outcome, not excluded or
retried) plus one further treatment grading failure. This is an honest null result: at this
sample size, citation does not show a significant arm difference in either direction.

### 2.3 section_reorder

| Phase | Arm | Result |
|---|---|---|
| Development (n=2, non-confirmatory) | control | 0/2 pass |
| Development (n=2, non-confirmatory) | treatment | 2/2 pass |
| Validation (n=5 applicable) | control | 4/5 pass (80%) |
| Validation (n=5 applicable) | treatment | 5/5 pass (100%) |
| Primary holdout (n=6 applicable) | control | 5/6 pass (83.3%) |
| Primary holdout (n=6 applicable) | treatment | 6/6 pass (100%) |
| **Combined validation+holdout (confirmatory)** | control | **81.8% [54.5%, 100%], n=11** |
| **Combined validation+holdout (confirmatory)** | treatment | **100% [100%, 100%], n=11** |

Paired significance: `observed_mean_diff=-0.182` (control minus treatment, i.e. treatment
ahead by ~18 points), `p=0.5255` -- **not statistically significant** at this sample size
(only 11 of 26 documents have >=3 headings and qualify for this family at all; see section
5). **This is the honest, complete version of a story that looked much more dramatic
early**: development's tiny n=2 sample showed a stark 2/2-vs-0/2 split that would have been
tempting to headline. It held up directionally through validation and holdout (treatment
consistently at or near 100%, control consistently somewhat below), but the WIDE confidence
interval on control's combined 81.8% (spanning 54.5% to 100%) and the non-significant
p-value mean this must be reported as a **suggestive, not confirmed, direction** --
regression toward a more modest (if still real-looking) effect as sample size grew, exactly
the pattern a well-designed confirmatory follow-up is supposed to reveal and exactly why
this project's own preregistration discipline exists.

## 3. What this evidence does and does not support

**Supported**: on this corpus, at this sample size, with this model:
- Bibliography's inverse pair has a universal, symmetric, one-time structural side effect
  (both arms), and treatment shows zero further degradation across repeated cycles while
  control shows a small residual failure rate once past that point (descriptive finding).
- Citation shows no significant difference between arms.
- Section_reorder shows a numerically consistent direction favoring treatment across three
  independent samples (development, validation, holdout) but does not reach statistical
  significance at n=11 paired documents.

**Not supported by this evidence**:
- A general claim that Meridian's bounded tools outperform generic editing across ALL task
  types -- only 3 of 6+ investigated families were tested, and citation shows no
  significant edge either way.
- Any claim about caption, cross_reference, table-structural, or tracked-change editing --
  none were run (section 5).
- A claim of statistical significance for section_reorder -- report the direction and the
  wide CI, not a confirmed win.
- Generalization beyond this specific DocOps-derived, 26-document, single-session-per-trial
  corpus and a K in {1, 4} sweep (K=16 was not run).

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
(`docops_v2_l3_006_docx_grant_closeout_release`, inverse direction) running with an
almost-fully-overlapping wall-clock window (both active roughly 02:09:13-02:10:32 UTC).
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
gets one that is. Checked all four collected slice manifests (development, validation x2,
the original holdout x2) for the same signature (>5 missing original paragraphs in one
grading result): **found in exactly one trial, the one described above.** Per the
protocol's own stopping rule (section 8), the complete primary_holdout slice was re-run in
full under the corrected harness rather than patched around; the re-run
(`holdout-k1-rerun-20260831T023817Z` / `holdout-k4-rerun-20260831T033222Z`) showed no
further instance of this failure signature -- the SAME `docops_v2_l3_008` document, K=4,
control arm, re-run under the fix, showed only modest, non-catastrophic verdict failures
(no chain in the re-run lost more than a handful of paragraphs).

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
- K in {1, 4}, not the full {1, 4, 16} range `docs/paper-s9-long-horizon-benchmark-protocol-v0.md`
  illustrates -- K=16 explicitly dropped for cost, not silently.
- A DocOps-derived, 26-document corpus (12 validation + 14 holdout) -- real, licensed,
  audited, and confirmed unexposed to this project's own pipeline, but not a from-scratch
  heterogeneous corpus built for this benchmark specifically.
- `claude-sonnet-5` only -- no cross-model comparison.
- Isolation was audited per trial (post-hoc transcript scan) and held throughout, but the
  concurrency-collision incident (section 4) shows a DIFFERENT kind of cross-trial
  interference than the control-reaching-Meridian violation the isolation audit itself
  checks for -- worth a dedicated audit dimension in a future run.
- The steady-state (pairs 2-4) metric was defined after observing the K=4 data pattern; it
  is reported descriptively, not as a preregistered, formally significance-tested claim.

## 7. Recommended next steps (not run here)

- Re-run caption after either reducing host contention or raising its render timeout.
- Add cross_reference now that `remove_cross_reference` is merged.
- A from-scratch heterogeneous corpus, sized for adequate power on section_reorder
  specifically (n=11 applicable documents was the binding constraint on that family's CI
  width this run).
- K=16 depth, cost permitting.
- A dedicated cross-trial-interference audit dimension (distinct from the existing
  control-reaches-Meridian isolation check) given section 4's finding.
