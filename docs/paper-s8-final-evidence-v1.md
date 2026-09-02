# PAPER-S8: PAPER-S7 final evidence and limitations package (v1)

Status: the real, executed result of `docs/paper-s7-protocol-v1.md`'s locked confirmatory
design, **updated 2026-09-02 after two real harness/evaluator defects were found, fixed, and
disclosed**, plus a separately preregistered section_reorder follow-up
(`docs/paper-s7-section-reorder-followup-protocol-v1.md`). Every number below comes from an
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

A fourth defect (a false-negative in `tools/pii_pattern_scan.py`, the tool used to screen
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
  sub-study at K=4 (bibliography, citation, section_reorder) is in progress, delayed by
  repeated real infrastructure interruptions on a shared host -- see section 7.
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

**Follow-up v2 corpus** (n=48, independently sourced, PII-screened, and content-reviewed --
`docs/paper-s7-section-reorder-followup-protocol-v1.md`; grading bug from section 0 fixed
before this result was computed):

| Arm | N | Pass rate (95% CI) |
|---|---:|---|
| control | 48 | 75.0% [62.5%, 87.5%] |
| treatment | 48 | 75.0% [62.5%, 87.5%] |

Paired significance: `observed_mean_diff=0.0`, `p=1.0` -- **exactly tied.**

**Combined v1+v2** (n=59, pooling explicitly disclosed -- the two pools come from different
source distributions, curated DocOps benchmark tasks vs. real-world scraped documents):

| Arm | N | Pass rate (95% CI) |
|---|---:|---|
| control | 59 | 74.6% [62.7%, 84.7%] |
| treatment | 59 | 79.7% [69.5%, 89.8%] |

Paired significance: `observed_mean_diff=-0.051`, `p=0.5665`.

**Honest conclusion**: the follow-up does not confirm the original corpus's suggestive
direction. With 5x the paired-document count, the apparent effect nearly vanishes (5 points,
not 27) and the p-value is nowhere near significant -- actually worse than the original
underpowered p=0.24. The most defensible reading is that the original n=11 result was a
small-sample effect that regressed toward parity once real, independently-sourced documents
were added. Full writeup: `docs/paper-s7-section-reorder-followup-result-v1.md`.

## 3. What this evidence does and does not support

**Supported**, on these corpora, at this sample size, with this model:
- Bibliography and citation show no significant difference between arms -- both fixed from
  real defects (harness and product) to genuine near-ceiling parity.
- Section_reorder, investigated across two independently-sourced corpora totaling 59 paired
  documents, shows no statistically significant difference between arms either. The original
  11-document corpus's suggestive direction did not replicate.

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
- K=1 confirmed on both corpora; K=4 depth data is incomplete as of this writing (section 7).
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

- **K=4 depth study** (bibliography/citation/section_reorder degradation over repeated
  cycles) is in progress but has been interrupted twice by real shared-host resource
  contention (confirmed via `Win32_Process`/`Win32_OperatingSystem` inspection: Windows
  `STATUS_DLL_INIT_FAILED` process-launch failures under <10GB free RAM with 65+ concurrent
  python/node/claude processes from other work on the same machine) -- not a harness or
  product defect. Currently retrying at reduced concurrency (`--max-workers 1`).
- Re-run caption after either reducing host contention or raising its render timeout.
- Add cross_reference now that `remove_cross_reference` is merged.
- K=16 depth, cost permitting.
- A dedicated cross-trial-interference audit dimension (distinct from the existing
  control-reaches-Meridian isolation check) given section 4's finding.
