# PAPER-S23: respec cascade -- heterogeneous cross-family cycling with a genuine
mid-chain requirement change, on real structurally-complex documents (protocol v0)

Status: **lock (2026-09-20).** Both corpus-build-time preconditions from section 1.2
are now resolved and recorded in the dated addendum at the end of section 1.2. This
document freezes every design decision that must be frozen before any trial runs
(rotation order, respec rule, anchor-resolution method, grading checks, statistics,
confirm/disconfirm criteria) -- per this project's own discipline
(`docs/paper-s7-protocol-v1.md` section headers; `docs/benchmark-preregistration-v0.md`),
a design is not locked until its stated preconditions are actually checked, not merely
named.

This design was produced by comparing four independently-drafted candidate families
(dependency-chain, spec-change, real-document-scale, heterogeneous-cycling), each with
its own adversarial review, and merging the two elements those reviews scored highest
on implementability and lowest on unresolved risk: heterogeneous-cycling's
existing-tools-only architecture (directly extends this paper's one significant
finding, K=4 section reorder) and spec-change's core mechanism (a genuine mid-session
requirement reversal, not a repeated identical action) -- while dropping every element
either review flagged as a live blocker (dependency-chain's disputed
section-reorder baseline and unverified `relocate_table` caption-carrying behavior;
spec-change's 3-tool treatment bundle and its self-defeating ablation design;
real-document-scale's dependence on `insert_cross_reference`/`renumber_sequences` and
an unbuilt from-scratch gold-reference generator). No new Meridian tool name is
introduced anywhere in this design.

## 0. Why this design and not one of the four candidates alone

Every existing family in `paper/main.tex` except section-reorder's K=4 extension
reduces to a single isolated insert-then-reverse and lands near 100%/100% parity by
construction: no later edit from a different family ever touches the same structural
object, so there is no opportunity for one tool's output to be misread or stranded by
another tool's later edit, and no opportunity for a genuinely changed instruction to
force selective, partial undo. K=4 is the only place the current design puts real,
repeated pressure on structure -- but it repeats one identical action on one short
synthetic document. This design keeps K=4's core mechanism (fresh persistent-id
resolution vs. accumulated positional guessing under repeated pressure) but replaces
"one action repeated four times" with three qualitatively different pressures in one
continuous chain, on real, structurally dense documents:

1. **Heterogeneity** -- six different families' edits land on the same live document
   before any of them is reversed, so a later family's edit can be the first thing in
   this benchmark's history to corrupt an earlier, different family's still-standing
   output.
2. **A genuine requirement reversal** -- not an undo-everything-then-redo cycle, but a
   single injected instruction that keeps some elements, discards others, and
   redirects a third, forcing selective targeting rather than blanket revert/redo.
3. **A second, K=4-comparable exposure** -- the same six families are exercised again,
   forward+inverse, after the heterogeneous build-and-respec churn, giving a number
   directly comparable in shape (though not in magnitude, see section 6) to the
   paper's existing K=1 vs. K=4 result.

## 1. Corpus

### 1.1 Documents (locked, pending 1.2)

The three real, author-owned documents at
`D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\`, per
`PROVENANCE.md` (dated 2026-09-19, read directly for this design, not assumed):

| File | Paragraphs | Headings | `<m:oMath>` | `<w:tbl>` | Citations |
|---|---:|---:|---:|---:|---:|
| `masters-dissertation-defense.docx` | 3,445 | 111 | 510 | 131 | 168 |
| `jcshm-manuscript.docx` | 578 | 50 | 128 | 42 | 97 |
| `jcshm-si.docx` | 2,200 | 67 | 229 | 76 | 17 |

**Explicit correction, disclosed rather than absorbed:** an earlier task brief for
this design round quoted "785 paragraphs" for the dissertation document; the real,
on-repo figure is 3,445 (headings, 111, did match). This table uses only the
authoritative `PROVENANCE.md` numbers.

**These are NOT the same file as the `thesis-p30` fixture's source.** That fixture
(`docs/thesis-p30-fixture-v0.md`) used a *different* copy of a related document --
`Masters_Dissertation_Report_Defense_staging_v0_source_locked.docx` from the separate,
actively-edited `Masters_Thesis` repo, 1,186 paragraphs, 216 pages, 28 bookmarks,
SHA-256 `38d21c00...`. This design uses only the frozen `author-owned-personal` copy
named above; the two must never be conflated or their numbers blended.

Non-independence, already measured and disclosed in `PROVENANCE.md`, must be carried
into every statistic this design reports (section 6): manuscript shares 19.0% of its
own content with the dissertation (8.2% of the dissertation's); SI shares 16.7% of its
own content with the dissertation (7.7% of the dissertation's); manuscript and SI
share only 0.3% with each other.

### 1.2 Corpus-build-time preconditions (must resolve BEFORE this protocol locks)

1. **Promotion and hash-pin.** `PROVENANCE.md` states these three files are "not yet
   promoted to any gold/D0 corpus tier, and not yet used in any confirmatory-benchmark
   trial." Before any trial, compute and record SHA-256 for each file as staged for
   this family, and re-verify those hashes immediately before the primary run (mirroring
   `thesis-p30-fixture-v0.md`'s own before/after hash-verification discipline, since
   `masters-dissertation-defense.docx`'s underlying OneDrive source is known to have a
   sibling copy under active, separate, same-day editing elsewhere on this machine).
2. **Live tool-manifest re-check for `insert_table`/`remove_table`.** These are the
   existing `table_structural` family's treatment tools, wired in
   `tools/docx_trial_broker.py`, but **this session's own connected `meridian-docs`
   tool manifest does not currently expose either name** (confirmed directly against
   the live tool list, not inferred from documentation). This is the same class of
   defect one of the four candidate reviews independently caught for a different tool
   pair (`relocate_table`'s test-suite instability, `insert_cross_reference`'s
   inverse). Resolve this by re-querying the live manifest at actual corpus-build
   time:
   - If `insert_table`/`remove_table` ARE present: run the **six-family design**
     (section 2) as written.
   - If they are NOT present: run the disclosed **five-family contingency**
     (drop `table_structural` from the rotation; section 2.3 gives its exact revised
     rotation and respec rule). This substitution is decided by this one manifest
     check alone, performed once before any trial, never adjusted after seeing
     results.
3. **OMML screening.** None of the three documents has been run through
   `tools/screen_organic_omml_candidates.py` for the project's own S6/S18 organic-OMML
   adjudication ledger. Run this before trusting any equation-semantic-class detail in
   this family's results (it does not block the structural checks in section 4, which
   do not depend on OMML semantic classification).

### 1.2a Addendum (2026-09-20): preconditions resolved, protocol locked

1. **Promotion and hash-pin -- DONE.** SHA-256 computed directly against the live
   files at `D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\`
   (`Get-FileHash -Algorithm SHA256`, 2026-09-20):

   | File | SHA-256 |
   |---|---|
   | `jcshm-manuscript.docx` | `ADA276D4DE9DD346B2F2B6BE3CFAC9E7637F6ECA849E0AA2B516D7B70C294747` |
   | `jcshm-si.docx` | `8CCDF9DD53A1CB16DEF8FC6F22044C5902D553C47CD0781FEC29677486495CB8` |
   | `masters-dissertation-defense.docx` | `B3336B9809DFB0BCAC5D73E0F2E94ED4D899A98A93217F01FD6FCA648AE0F332` |

   `PROVENANCE.md`'s own "sha256 source" column previously recorded only "copied
   as-is" with no actual digest -- these are the first real hash-pins for these three
   files, not a re-verification against a prior value, and are also being written back
   into `PROVENANCE.md` directly. Re-verify these three digests again immediately
   before the primary run, per the precondition's own stated reason (a sibling copy of
   the dissertation source is under active, separate editing elsewhere on this
   machine).

2. **Live tool-manifest re-check -- DONE, five-family contingency confirmed.**
   Checked directly against this session's own connected `meridian-docs` MCP tool
   list: `insert_table` and `remove_table` are **not present** (confirmed absent, not
   merely undocumented -- the full list was enumerated and neither name appears,
   alongside `insert_column`/`split_cell`/`transpose_table`/`relocate_table`, which
   *are* present but are not this family's table-insertion primitive). Per the
   precondition's own decision rule (section 1.2 item 2), this means: **run the
   five-family contingency (section 2.3), never the six-family design (section 2.2),
   for this locked run.** This substitution was decided by this one manifest check
   alone, before any trial, and is not to be revisited after seeing results.

3. **OMML screening -- not run yet, does not block lock** per this precondition's own
   stated scope (structural checks in section 4 do not depend on OMML semantic
   classification). Tracked as a prerequisite for any future equation-semantic-class
   claim from this family, not for the structural confirm/disconfirm result in
   section 7.

## 2. Task family: `respec_cascade`

### 2.1 Anchor resolution (corpus-build time, once per document, reused verbatim
where it exists)

- Citation, equation, table (if in scope), caption anchors: `resolve_multiple_body_anchors`
  (`tools/docx_anchor_prober.py`), unmodified, `max_anchors=4`.
- Section-reorder plan (original position `O`, first destination `D1`):
  `resolve_multiple_section_reorder_plans`, unmodified, `max_plans=4`.
- Bibliography: no body anchor needed (document-global end-of-reference-list
  insertion), exactly as the existing `bibliography` family already does in
  `tools/docx_trial_broker.py::generate_bibliography_pair`.
- **New, this design only:** `resolve_section_redirect_plan` (add to
  `tools/docx_anchor_prober.py`), reusing `_try_section_plan_at`'s existing safety
  rules (non-blank heading text, same-level sibling, outward-scan for validity)
  to resolve a **second, distinct destination `D2`** for the same section, excluding
  both `O` and `D1`. If no valid `D2` exists for a given (document, anchor-set), that
  anchor-set is recorded `not_applicable: no_redirect_target`, not silently dropped.

A chain (one full three-phase run, section 2.2) at anchor-set index *i* uses the
*i*-th returned anchor/plan from every one of the above resolvers, consistently. All
resolver outputs for all anchor-sets of all three documents are computed and
**hash-recorded once**, before either arm runs, per the precondition in section 1.2
item 1 -- the literal targets are frozen, not re-derived per trial.

### 2.2 The three-phase chain (six-family version; five-family contingency in 2.3)

Fixed rotation order, decided here and never reordered per document or per result:

```
R = [ (1) Bibliography, (2) Citation, (3) SectionReorder, (4) Equation, (5) Table, (6) Caption ]
```

Each chain runs as a sequence of **fresh, independent agent processes** (one per
step below, not one long-lived conversation), sharing only the evolving `.docx` file
on disk -- this is deliberate, not an oversight: a single long session would let the
agent's own accumulated conversational memory of the document substitute for genuine
structural re-resolution, which would confound "the tool re-resolves a persistent id"
with "the model remembers what it did four turns ago." This mirrors the isolation
principle `tools/run_paper_s7_benchmark.py::run_chain` already uses for K-pair chains,
extended to a per-step rather than per-pair grain. The treatment arm's tool grant is
swapped to exactly that step's one bounded pair (plus `Read`) before each step; the
control arm always has exactly `Read`/`Write`/`Edit`/`Bash`, unchanged for the whole
chain -- this is the ONE structural invariant of the paper's existing six families
(exactly one bounded tool pair per treatment step, nothing else) and this design does
not violate it anywhere, unlike two of the four reviewed candidates.

**Phase 1 -- BUILD (6 steps, forward-only, in order R):**

| Step | Family | Action | Depends on |
|---|---|---|---|
| 1.1 | Bibliography | Insert entry `B` at the document-global anchor | none |
| 1.2 | Citation | Insert citation to `B` at anchor `C` | genuinely depends on 1.1: the citation must link to `B`'s actual key, checked at grading, not merely run after it |
| 1.3 | SectionReorder | Move section from `O` to `D1` | none (independent of 1.1-1.2) |
| 1.4 | Equation | Insert equation at anchor `E` | none |
| 1.5 | Table | Insert table at anchor `T` | none |
| 1.6 | Caption | Insert caption at anchor `Cap` | none |

End of Phase 1: document contains `B`, a citation to `B` at `C`, section moved to
`D1`, `E`, `T`, `Cap`, and nothing else changed.

**Phase 2 -- RESPEC (3 steps, one injected instruction wave, identical wording to
both arms, mechanically triggered by the harness the instant Phase 1's 6th step's own
per-step grading check passes -- never an LLM "does it look done" judgment):**

Fixed, deterministic rule (same for every document/anchor-set, decided here, not
per-document): **revert the 2nd and 5th family in rotation order (Citation, Table);
redirect the 3rd (SectionReorder); keep the 1st, 4th and 6th (Bibliography, Equation,
Caption) untouched.**

| Step | Family | Action | Depends on |
|---|---|---|---|
| 2.1 | Citation (inverse) | Remove the citation inserted at 1.2 | reverses 1.2; the citation's key/field code, not prose text, must be the removal target |
| 2.2 | Table (inverse) | Remove the table inserted at 1.5 | reverses 1.5 |
| 2.3 | SectionReorder | Move the section from `D1` to `D2` (NOT back to `O`) | the genuine cross-family test: the agent must recognize the section is currently at `D1` (its own Phase-1 output, not the document's original state) and move it onward, not simply reverse its own prior move |

`B`, `E`, and `Cap` receive **no action** in this phase -- they are graded for
survival (section 4, Phase-2 checkpoint), which is the actual test: can the arm
selectively touch exactly the two elements named for reversal and the one named for
redirection, while leaving three untouched siblings created earlier in the *same*
chain completely alone.

**Phase 3 -- SECOND EXPOSURE (6 steps, forward+inverse, same order R, K=4-comparable
in shape):**

| Step | Family | Action | Depends on |
|---|---|---|---|
| 3.1 | Bibliography | Insert entry `B2` (a second, distinct entry) at the same document-global anchor, then remove `B2` | `B` from 1.1 must still be present and untouched throughout |
| 3.2 | Citation | Insert a fresh citation to `B` at the SAME anchor `C` (vacated by 2.1), then remove it | must resolve `C` and `B`'s key correctly after 8 intervening heterogeneous steps and one selective revert |
| 3.3 | SectionReorder | Move the section from its CURRENT position (`D2`) to `D1` and back to `D2` | tests whether the section's identity, now twice-moved and mid-redirect, still resolves for a third and fourth move |
| 3.4 | Equation | Insert a fresh equation at the same anchor `E`, then remove it | `E` from 1.4 must still be present and untouched throughout |
| 3.5 | Table | Insert a fresh table at the same anchor `T` (vacated by 2.2), then remove it | |
| 3.6 | Caption | Insert a fresh caption at the same anchor `Cap`, then remove it | `Cap` from 1.6 must still be present and untouched throughout |

End of chain, expected final structure (computed once at corpus-build time,
per anchor-set, not "similar to before"): `B` present exactly once at its Phase-1
form; `E` present exactly once at its Phase-1 form; `Cap` present exactly once at its
Phase-1 form; citation absent (net of 1.2+2.1+3.2's insert-then-remove); table absent
(net of 1.5+2.2+3.5's insert-then-remove); section at `D2`; every paragraph outside
these six targets byte-identical to the pristine original.

### 2.3 Five-family contingency (if `insert_table`/`remove_table` are confirmed
absent from the live manifest per section 1.2 item 2)

`R' = [ (1) Bibliography, (2) Citation, (3) SectionReorder, (4) Equation, (5) Caption ]`.
Respec rule: revert the 2nd (Citation) only; redirect the 3rd (SectionReorder); keep
1st and 4th and 5th (Bibliography, Equation, Caption). Phase 1 = 5 steps, Phase 2 = 2
steps, Phase 3 = 5 forward+inverse steps. Everything else in this document applies
unchanged, with `table_structural` removed from every table in section 4-6 and the
contingency explicitly labeled in every reported result table -- never silently
merged with six-family results.

## 3. Fresh, contemporaneous isolated baseline (resolves the section-reorder baseline
provenance problem)

The published section-reorder K=1/K=4 figures (control 83.6%, treatment 92.9%,
p=0.271 at K=1; 67.3% vs 92.9% at K=4) are, as of this session's most recent commit
(`e7fd22f`, "record 3 more failed section_reorder source-reproduction attempts"), an
**open, unresolved data-provenance problem**: three independent attempts to trace that
number back to raw source data produced three different, non-matching candidates
(p=0.347, p=0.124, p=0.0595). This design does **not** compare its Phase 3 results
against that disputed historical number, or against any other family's historical
single-edit baseline. Instead:

For every (document, anchor-set, family, arm), run one **fresh, isolated K=1
forward+inverse trial** at the *identical* anchor used in this chain's Phase 1/3,
against a *fresh copy* of the *same pristine document snapshot*, on the *same day and
host* as the cascade chain -- reusing `tools/run_paper_s7_benchmark.py::run_chain`
completely unmodified, K=1. This isolated trial is this design's own control
condition, immune to any provenance question about a different run's historical
numbers, and directly comparable because every other variable (document snapshot,
anchor, day, host, model) is held fixed.

## 4. Grading (objective, structural, re-derived independently at three checkpoints
per chain -- never trusted from either arm's self-report)

All checks parse the persisted `.docx` XML directly (`lxml`/lxml-backed helpers in
`tools/graph_scorer.py` and `tools/docx_trial_evaluator.py`), per this project's
standing "never trust the system under test" rule.

**Package validity gate (both arms, after every one of the 9-15 steps in a chain,
not just at phase ends):** `tools/docx_trial_evaluator.py::_package_is_valid_docx`
(the real function name; several of the four candidate proposals cited a
non-existent `validate_docx_package` -- corrected here). A failure here freezes the
chain at that exact step and is logged `chain_broken_at_step_N`, a new failure-
taxonomy value; later steps are never run against a document already known to be
invalid.

**Checkpoint A (end of Phase 1):** for each of `B`, `C`-citation, `D1`-move, `E`, `T`,
`Cap`: content present exactly once, reachable at its resolved anchor, well-formed.
Zero paragraph-text diff outside these six targets, against the pristine original
(reusing the existing per-family "unchanged paragraphs" check each of the six current
families already applies to its own forward trial, generalized across all six targets
simultaneously in one pass -- new code, `grade_phase1_build` in
`tools/docx_trial_evaluator.py`).

**Checkpoint B (end of Phase 2 -- the design's central, novel test):**
1. Citation and table are **absent**: no dangling bookmark/field left behind, no
   orphaned reference.
2. Section is at `D2`, not `D1`, not `O`.
3. `B`, `E`, `Cap` are **byte-identical** to their own Checkpoint-A state -- a new
   running "keep survival" differ (`tools/graph_scorer.py`, new function
   `score_keep_survival`, generalizing `score_round_trip_editability`'s existing
   single-marker before/after diff to three named, arbitrary-kind elements checked
   against an intermediate, not just a final, checkpoint).
4. Zero paragraph-text diff anywhere outside {citation, table, section} relative to
   Checkpoint A.

**Checkpoint C (end of Phase 3 -- K=4-comparable primary outcome):** for each of the
six (or five) families' own forward+inverse step in Phase 3, its own existing grading
function reused unmodified (`grade_forward_trial_*`/`grade_inverse_trial_*` in
`tools/docx_trial_evaluator.py`, one family per row in section 2.2's step tables,
matching the exact function that already grades that family's single-edit trials
today) -- PLUS the final full-document check against the exact expected structure
given at the end of section 2.2, PLUS re-confirmation that `B`, `E`, `Cap` are still
present and unchanged (final collateral-damage close-out).

**New node-kind scorers required (do not yet exist -- confirmed by reading
`tools/graph_scorer.py` directly, which today has only `_caption_node_accuracy` and
`_anchor_node_accuracy`):** `_bibliography_entry_prf1` and `_citation_marker_prf1`,
built the same way (exact-match multiset PRF1, `not_applicable: no_candidate_adapter`
where an adapter genuinely cannot see the field, never a fabricated 0).

**Composite chain PASS** = Checkpoint A pass AND Checkpoint B pass AND Checkpoint C
pass AND every intermediate package-validity gate passed. A step-level failure is
logged with its own attribution (`chain_broken_at_step_N` for a package-validity
failure, `respec_broken_at_2.1`/`2.2`/`2.3` for a Checkpoint-B-specific failure,
`phase3_broken_at_<family>` for a Checkpoint-C-specific failure) -- never collapsed
into one opaque pass/fail without knowing where it broke, mirroring how K=4's own
root cause was traced mechanistically rather than asserted.

**Milestone Word-COM receipts:** at chain start (pristine) and at the end of each of
the three phases only (never after every raw tool call), via
`tools/word_receipt_watchdog.py::word_receipt_with_orphan_diagnostics` and
`tools/retained_render_receipt.py::retained_render_receipt`, reused unmodified, per
the two-tier fast-validator/milestone-render cadence `docs/paper-s9-long-horizon-
benchmark-protocol-v0.md` section 5 already establishes. A Word-COM failure is
recorded `not_run`/`failed` explicitly, never skipped silently.

## 5. New harness/grading code required (summary; each item cross-referenced above)

1. `tools/docx_anchor_prober.py`: new `resolve_section_redirect_plan` (resolves `D2`,
   excluding `O` and `D1`, reusing `_try_section_plan_at`'s existing safety rules).
2. `tools/docx_anchor_prober.py` (or a new small module): `resolve_respec_schedule`,
   producing and hash-pinning one full rotation's anchor-set (all six/five family
   targets plus `D2`) per document, per anchor-set index, before any trial.
3. `tools/graph_scorer.py`: `_bibliography_entry_prf1`, `_citation_marker_prf1` (new
   node-kind scorers, pattern-matched to the existing `_caption_node_accuracy`/
   `_anchor_node_accuracy`).
4. `tools/graph_scorer.py`: `score_keep_survival` (new, intermediate-checkpoint,
   multi-element byte-identical differ).
5. `tools/docx_trial_evaluator.py`: `grade_phase1_build`, `grade_phase2_respec`,
   `grade_phase3_second_exposure` -- new orchestration wiring existing per-family
   grading functions together per phase; only the wiring and Checkpoint B's
   keep-survival call are new logic, the per-family checks themselves are reused
   unmodified.
6. `tools/run_respec_cascade_family.py` (new orchestrator): fresh-agent-per-step
   execution across 3 phases, tool-grant swap per step (mirrors
   `tools/docx_trial_broker.py`'s existing per-family tool declarations, reused
   directly rather than re-declared), per-step `_package_is_valid_docx` gate, phase-
   boundary Word-COM milestones, explicit round-trip-count logging per arm (closing
   the same "fewer reopens" confound `run_paper_s7_benchmark.py::run_chain` already
   closes for K-pair chains, extended to this design's mixed step count).
7. `tools/compute_multianchor_extension_statistics.py`: extend with this family's
   phase-aware Tier 1/2/3 aggregation, reusing `estimate_icc_and_effective_n`,
   `weighted_mean`, `weighted_bootstrap_ci`, `weighted_paired_permutation_test`
   unmodified.
8. Hash-pin + promotion step (section 1.2 item 1) and live-manifest re-check
   (section 1.2 item 2), both one-time corpus-build actions, not code but required
   recorded evidence before lock.

## 6. N / sample-size plan (honest, non-independence disclosed up front)

- **Document level:** N=3 (dissertation, manuscript, SI) -- non-independent, per the
  overlap percentages in section 1.1. Reported as Tier 1 (unweighted per-document
  mean), explicitly labeled demonstration/mechanism-probing strength, not a powered
  confirmatory test on its own, matching this project's own established convention
  for the multi-anchor extension's real-document tier.
- **Anchor-set level:** up to 4 anchor-sets per document (capped by
  `resolve_multiple_body_anchors`/`resolve_multiple_section_reorder_plans`'s existing
  `max_anchors=4`/`max_plans=4`, further capped by however many anchor-sets also have
  a valid `D2` redirect target per `resolve_section_redirect_plan`); actual usable
  count is determined at corpus-build time and reported in full, including excluded
  anchor-sets and the specific reason each was excluded (`no_redirect_target`,
  family-specific `not_applicable`, etc.) -- never a silently reduced denominator.
  Nominal ceiling: 3 documents x 4 anchor-sets = 12 chains per arm; realistic
  expectation, stated here rather than after the fact, is fewer, since a valid `D2`
  is a genuinely new, untested eligibility condition.
- **Reported at three tiers**, reusing `compute_multianchor_extension_statistics.py`'s
  existing scheme unmodified: Tier 1 (unweighted per-document mean, N=3), Tier 2
  (anchor-set-count-weighted per-document mean), Tier 3 (pooled anchor-set-level
  estimate with one-way random-effects ICC-corrected effective N -- the existing
  multi-anchor extension already found ICC as high as 1.0 for section-reorder-type
  anchors within one document, so Tier 3's naive pooled N is expected to substantially
  overstate precision here too, and the ICC-corrected effective N, not the raw pooled
  N, is the number given headline weight).
- **Fresh isolated baseline (section 3):** one K=1 chain per (document, anchor-set,
  family, arm) -- reuses the exact same denominator structure as the cascade chains
  themselves, so the paired comparison in section 7 is always apples-to-apples at the
  same aggregation tier.
- 2000 resamples/permutations, seed `20260828`, reusing `graph_scorer.py`'s existing
  module constants (`_BOOTSTRAP_SEED`, `_PERMUTATION_RESAMPLES`) unmodified, for
  consistency with every other statistical claim in this paper.

## 7. Preregistration: confirm vs. disconfirm, decided here, before any trial runs

**Primary comparison (Checkpoint C, Phase 3, per family and pooled across all
six/five families, at the Tier 3 ICC-corrected-effective-N aggregation):**
`paired_permutation_test` between control's Phase 3 composite pass rate and
control's own fresh isolated-baseline pass rate (section 3, same anchor, same day,
same host) -- call this `control_drop`. Identically, `treatment_drop` for the
treatment arm. Then `paired_permutation_test` directly between control's and
treatment's Phase 3 composite pass rates.

**CONFIRMING** (the hypothesis that heterogeneous cross-family cycling plus a genuine
mid-chain requirement reversal degrades control's structural bookkeeping
disproportionately, generalizing the K=4 mechanism beyond same-family repetition)
requires ALL of:
- `control_drop` is statistically significant (two-sided permutation p < 0.05) AND its
  point estimate is at least 10 percentage points.
- `treatment_drop`'s 95% bootstrap CI overlaps zero, OR its point estimate is smaller
  than `control_drop`'s point estimate by at least 10 percentage points with p < 0.05
  on the direct control-vs-treatment paired test.
- Checkpoint B's `score_keep_survival` pass rate (the selective-revert test) is
  significantly higher for treatment than control (p < 0.05).

**DISCONFIRMING** (reject this family's hypothesis; report the null result in full,
exactly like the paper's existing bibliography/citation single-edit parity findings)
if ANY of:
- Both `control_drop` and `treatment_drop` are statistically indistinguishable from
  zero (both p > 0.10 or both point estimates under 10 percentage points) --
  heterogeneity plus one requirement reversal does not meaningfully stress either
  arm's bookkeeping beyond noise, at least at this chain length and corpus.
- Control's and treatment's Phase 3 composite pass rates are not significantly
  different from each other (p > 0.05), regardless of each arm's own drop from
  baseline.
- `treatment_drop` is equal to or larger than `control_drop`.

No other outcome pattern is defined as confirming or disconfirming; an ambiguous
result (e.g. significant on the primary pooled test but not on enough individual
families, or significant at Tier 3 but not Tier 1) is reported as **inconclusive**,
with every per-family, per-tier number shown, never resolved by selecting whichever
tier or subset looks cleanest after the fact.

**Render-gate / host-contention control (addresses this project's own documented
7-46%-to-100% swings for equation/caption pass rates under host contention):** every
chain runs on a dedicated, uncontended host, with host-load logged per trial. Any
chain that fails a step specifically via a render-gate timeout (not a structural
failure) is recorded as its own outcome (`render_gate_timeout`) and reported
separately, never folded into the headline `control_drop`/`treatment_drop` figures --
this is decided here, before any trial, specifically to prevent an environment
artifact from being read as a structural-bookkeeping finding.

## 8. Risks and confounds (disclosed, not hidden)

- **Fixed rotation and fixed respec rule.** Neither is randomized or counterbalanced
  across documents (a crossed design would need far more than 3 real documents to
  power). Results characterize this one chain, not "heterogeneous cycling in
  general" -- the same disclosure the paper's own existing K=4 section already
  makes about its single repeated action.
- **`table_structural`'s live availability is unresolved as of this document.**
  Section 1.2 item 2 and section 2.3 give the exact, pre-decided fallback; the choice
  is never made after seeing results.
- **Session-length / round-trip-count confound.** A six-family chain is 21 tool-call
  steps per arm (18 for the five-family contingency) -- both arms get an identical
  budget and logged round-trip count, closing the "fewer reopens" confound
  structurally, matching `run_paper_s7_benchmark.py::run_chain`'s existing K-pair
  design.
- **New grading code is first-use code.** `score_keep_survival`,
  `_bibliography_entry_prf1`, `_citation_marker_prf1`, and the phase orchestration in
  `grade_phase1_build`/`grade_phase2_respec`/`grade_phase3_second_exposure` have never
  run before. Per this project's own repeated experience with first-use evaluator
  bugs, a development-slice smoke phase (1 document, 1 anchor-set, both arms) runs
  and is manually spot-checked before validation/primary-holdout slices, per
  `docs/benchmark-preregistration-v0.md`'s smoke -> scale-up -> final discipline.
- **`D2` eligibility is a genuinely new, untested resolver condition.** Some
  anchor-sets may have no valid redirect target; the actual usable N could be
  meaningfully smaller than the nominal ceiling in section 6, and this must be
  reported, not glossed over.
- **Real-document engineering risk.** These documents are far denser (111-131
  headings/tables/equations) than anything the six family tools have previously been
  exercised against; new tool or resolver defects found while building this family
  are disclosed with root cause, not silently patched before results are reported,
  per this project's standing rule.

## 9. What this document does not decide

Whether a K>1 repetition of the full three-phase chain (a true heterogeneous
generalization of K=4, repeating the whole 21-step cycle rather than running it once)
is worth the added cost is future work, tracked separately, not attempted here. This
document also does not resolve the historical section-reorder K=1/K=4 baseline
provenance problem (`e7fd22f`) -- it works around that problem for this family's own
purposes (section 3) without claiming to fix it for the rest of the paper. Whether the
five-family contingency (section 2.3) or the six-family design (section 2.2) is the
one actually run is decided solely by the section 1.2 item 2 live-manifest check, and
that decision, once made, is recorded here in a dated addendum before the protocol is
marked **lock**.
