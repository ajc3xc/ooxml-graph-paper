# PAPER-S25: respec_cascade re-run protocol, amendment 1 (dissertation exclusion; public-documents-only becomes the headline confirmatory measure)

Status: **LOCKED (decided 2026-09-28).** This is a dated, prospective amendment to
`docs/paper-s25-respec-cascade-rerun-protocol-v1.md` (locked 2026-09-26; referred to throughout
as "v1"). It follows the pattern v1 itself reserves for a post-lock change: a new, separately
dated protocol document, never an in-place edit of v1 (v1 section 11 item 2: "a grader, harness,
scoring or data correction found after [the verdict of record] ... is reported alongside the
verdict of record under its own label ... never in its place"; v1 sections 1.2, 10.2 and 10.6
call this pattern "amendment v1.1" / "amendment v1.x"). This document is that amendment, filed
as a separate numbered file rather than an in-place edit at the author's direction.

It amends v1 sections 6.2, 6.7, 6.8 (item 3), 7 and 8, **for the next confirmatory run only**. It
does not reopen, recompute, or reinterpret the verdict of record already reported for v1's
completed D=4 run (section 4 below), and it does not reopen any of v1's FINAL DECISIONS
(D-R1-D-R10, v1's status block and section 14) except where a decision below says so explicitly.

**Amendment decisions (2026-09-28, the author, final unless a later dated amendment says
otherwise):**

- **AD-1 (rationale: the dissertation is out-of-population for a confirmatory evaluation
  corpus).** `masters-dissertation-defense` (v1 section 1.1) is unpublished, self-authored
  committee-defense material -- not a published or submitted manuscript, and not representative
  of the target population the paper's confirmatory claim generalizes to. Reason and literature
  precedent: section 1 below.
- **AD-2 (headline measure change).** `confirm_disconfirm.public_documents_only` (computed by
  `tools/compute_respec_cascade_statistics.py`, exact shape verified against that file for this
  amendment -- section 2) is the **headline confirmatory measure** for the next confirmatory run.
  The full pooled `confirm_disconfirm` analysis (v1 section 6.2's P1-P4, computed over every
  document, author-owned and public) is retained at full statistical rigor and reported with the
  same completeness as before, but as a **secondary / sensitivity analysis** (v1 section 6.8), not
  as the primary claim. Section 2.
- **AD-3 (dissertation handling).** The dissertation is held out of the confirmatory statistic
  **entirely**: it is not in the next locked documents manifest (section 5) and is never scored as
  an independent unit in either the headline or the pooled-secondary analysis. It may be examined
  only as a disclosed sensitivity check, via the existing cluster-merge mechanism v1 section 6.8
  item 3 already defines -- never folded into a primary claim. Section 3.
- **AD-4 (non-retroactivity).** This amendment governs the next confirmatory run only. The D=4
  INCONCLUSIVE verdict of record already reported under v1 stands exactly as reported and is not
  recomputed, relabelled, or reinterpreted under this amendment. Section 4.

## 1. Rationale: excluding the dissertation from the confirmatory corpus

v1 section 1.1 already flags a related but distinct problem with the three author-owned
documents: "The author documents are not naive test items for the treatment" (the Meridian Docs
fix under test, commit `89c93fac`, was written because `move_section` failed on exactly these
three documents), and v1 answers that specific problem with condition C6 and the
public-documents-only analysis of section 6.7. That fix does not reach a second, separate
problem the author has identified: `masters-dissertation-defense.docx` is not a published or
submitted manuscript at all. It is unpublished committee-defense material belonging to the
paper's own author. Unlike `jcshm-manuscript` and `jcshm-si` (both are, or are being prepared as,
submitted/published manuscripts of joint work), the dissertation defense copy has no external
review, publication, or submission status of any kind, and a paper that reports a confirmatory
evaluation corpus containing the author's own unpublished thesis-defense material -- presented
without qualification as representative "real" documents -- has a construct-validity problem a
reviewer or thesis committee would reasonably raise: the corpus would not be an unbiased sample
of the target population (published or submitted OOXML documents circulating for real editing
work), and the author would be both the evaluated system's subject-matter debugger (v1 section
1.1) and the source of part of the evaluation material.

This concern has direct precedent in the artifact-documentation and evaluation-integrity
literature:

- **Datasheets for Datasets** and **Data Statements for NLP** both require that an evaluation
  artifact's provenance -- who created it, for what original purpose, and whether it is
  representative of the population a downstream claim generalizes to -- be documented and
  justified per artifact, not asserted in aggregate. An unpublished, self-authored thesis defense
  copy fails that per-artifact justification against "published/submitted manuscript."
- The **ACL Rolling Review Responsible NLP Research checklist** requires a per-artifact
  license/provenance disclosure for material used in a confirmatory evaluation; the same standard
  v1 section 1.2's D-R7 already invokes for the public documents applies with more force here,
  since the dissertation's provenance is not merely unverified (as the public corpus's is) but
  known and disqualifying.
- The **SWE-bench literature's critique of source concentration** as a validity flaw applies
  directly: a confirmatory corpus that includes a document authored by the same person running
  the evaluation concentrates the corpus's source in a way that threatens the claim's external
  validity, independent of any effect on statistical independence (which v1 section 1.4 already
  treats separately).
- The **"evaluator checks itself" literature** ("When LLMs Benchmark Themselves," "Peeking Behind
  Closed Doors") argues against self-authored or self-selected material entering the evaluation
  an author's own claim rests on. The dissertation is exactly that: material the author wrote,
  entering a corpus the author also selected, feeding a claim the author is making.

None of this reopens D-R2 (the *May 2026* dissertation version is not added -- a decision about a
near-duplicate, unaffected by this amendment) or v1 section 1.4's non-independence disclosure
(about correlation between the three author documents, a different problem from representativeness).
AD-1 is about the defense copy's provenance and representativeness, not its correlation with the
other two author documents.

## 2. Headline measure change: `confirm_disconfirm.public_documents_only` becomes primary

**Field path and shape, verified against `tools/compute_respec_cascade_statistics.py` for this
amendment** (not assumed): `confirm_disconfirm.public_documents_only` is a dict, present in the
statistics JSON only when `compute_respec_cascade_tiers` is given `public_doc_labels` -- i.e.
only when `compute_respec_cascade_statistics.py` is invoked with `--documents-manifest`. Its
shape, read directly from the source:

```
confirm_disconfirm.public_documents_only = {
  "note": "... protocol section 6.7 ...",
  "public_documents": [<doc_label>, ...],
  "n_public_documents": <int>,
  "control_drop": {...},                              # as-run Monte Carlo, continuity only
  "direct_control_vs_treatment_phase3": {...},
  "keep_survival_significance": {...},
  "chain_level": {
    "control_drop": {...},
    "direct_control_vs_treatment_phase3": {...},
    "keep_survival_significance": {...}
  },
  "document_level": {
    "control_drop": {...},
    "direct_control_vs_treatment_phase3": {...},
    "keep_survival_significance": {...}
  },
  "difference_in_drops": { "drop_difference_pp": ..., "chain_level": {...}, "document_level": {...} }
}
```

A document counts as "public" here purely by the locked documents manifest's own `source` field
containing the substring `"public"` (`compute_respec_cascade_statistics.main`: `"public" in
str(d.get("source", "")).lower()`); this already excludes every author-owned document (all three,
not just the dissertation) from `public_documents_only`, exactly as v1 section 6.7 intends. AD-2
does not change that filter. What it changes is which analysis the paper leads with.

**Operational note, disclosed:** v1's own locked `s25-statistics` command (v1 section 6.9) does
**not** pass `--documents-manifest`, so as literally written it never populates
`confirm_disconfirm.public_documents_only` at all (the tool's own `--documents-manifest` help
text: *"Omit to skip section 6.7 entirely (`confirm_disconfirm.public_documents_only` absent
from the output)"*). This was consistent with v1's own framing, where the public-only analysis
was a same-sign co-requirement (C6), not a headline number. For the next confirmatory run, the
locked `s25-statistics`-equivalent command **must** pass `--documents-manifest` pointing at the
run's locked documents manifest (section 5), or the headline measure this amendment requires is
silently absent from the output. This is a disclosed prerequisite of this amendment, not yet
implemented; `respec_rerun_verdict.py` (v1 prerequisite P-R5) will also need a corresponding
change to read `confirm_disconfirm.public_documents_only.{chain_level,document_level}` for
conditions C1-C4 rather than `confirm_disconfirm.pooled.{chain_level,document_level}`, before any
confirmatory trial under this amendment (in the spirit of v1 section 10.2's rule that a code
change after a lock is logged in `logs/deviations.md` and gated by a dated amendment -- this one).

**Amended section 7 mapping, for the next confirmatory run:**

| v1 section 7 condition | v1 (as locked) | Under this amendment |
|---|---|---|
| D1-D3 (DISCONFIRMING) | Evaluated on `confirm_disconfirm.pooled` | Evaluated on `confirm_disconfirm.public_documents_only` |
| C1 `control_drop_pp >= 10` | chain+document level p<0.05 on `pooled` | chain+document level p<0.05 on `public_documents_only` |
| C2 `direct_pp > 0` | chain+document level p<0.05 on `pooled` | chain+document level p<0.05 on `public_documents_only` |
| C3 `keep_survival_pp > 0` | chain+document level p<0.05 on `pooled` | chain+document level p<0.05 on `public_documents_only` |
| C4 `drop_difference_pp >= 10` | chain+document level p<0.05 on `pooled` | chain+document level p<0.05 on `public_documents_only.difference_in_drops` |
| C6 (public-only same-sign check) | Same sign as `pooled`, significance not required | Superseded: public-only is now primary, so the check inverts -- the full pooled analysis (secondary) is required to show the **same sign** as the headline public-only result, significance not required, reported as a robustness note beside the pooled sensitivity analysis |
| C5 (grader-exception / render-gate bounds) | Unchanged | Unchanged, applied to whichever analysis is primary |

The full pooled `confirm_disconfirm` analysis is still computed, still reported in full (every
field v1 sections 6.2-6.6 and 12 require), and still governs nothing about the verdict on its own
after this amendment -- it moves into v1 section 6.8's secondary/sensitivity role, reported with
the same prominence a sensitivity analysis gets under v1 section 12 item 2 ("all section 6.8
analyses ... with the same prominence as positive ones"), not with the prominence v1 section 8
reserves for the confirmatory claim.

v1 section 8's claims boundary is amended correspondingly: for the next run, "confirmed,"
"preregistered result," and "significant" without qualification may describe only the section 7
verdict as evaluated on `public_documents_only`; the pooled analysis's own significance (chain or
document level) is exploratory/sensitivity language exactly as v1 section 8 already requires for
every other section 6.8 item.

## 3. Dissertation handling: held out; re-inclusion only via the section 6.8 cluster-merge mechanism

The dissertation is removed from the confirmatory corpus outright (section 5): it is not a row in
the next locked documents manifest, so by construction it is absent from both the headline
`public_documents_only` measure and the secondary pooled measure. It is not merely "de-headlined"
the way the three author documents already are relative to `public_documents_only` (section 2) --
it does not enter the confirmatory statistic at all, at any level, under either analysis.

The **only** sanctioned way to look at the dissertation's data going forward is the cluster-merge
mechanism v1 section 6.8 item 3 already defines and uses for a different purpose:

> "Document-level tests with every author document merged into one cluster (D_eff = D - 2, or
> D - 3 with D-R2), for P1-P5." (v1 section 6.8, item 3; informally "section 6.8.3" elsewhere in
> this project's notes -- see the closing note below on how it is actually written in v1.)

v1 built this mechanism to test whether the document-level co-requirement (v1 section 6.3)
survives treating the correlated author documents as one statistical unit rather than three
independent ones, by giving them a shared cluster identity in
`graph_scorer.cluster_paired_sign_flip_test` (cluster id, not a separate code path) instead of
each document's own `doc_label`. This amendment reuses exactly that mechanism for a different
purpose: **if** a future sensitivity check re-admits the dissertation's chains, they do not get
their own independent document-level cluster id. They are merged into the same shared
author-document cluster identity that mechanism already assigns to `jcshm-manuscript` and
`jcshm-si`, so the dissertation can never be counted as its own independent document-level unit,
and can never by itself supply or break the document-level significance the decision rule
requires. Concretely: any such check reports the dissertation only inside the merged
author-cluster's `document_level` result (reducing `D_eff` by one relative to a corpus that
listed it separately), never as a standalone `per_document` entry (v1's `per_document` breakdown,
section 6.8's exploratory per-document reporting) feeding a confirmatory claim.

This is, and must remain, a **disclosed sensitivity check only**, reported the way v1 section 12
item 2 already requires every section 6.8 analysis to be reported (full prominence, clearly
labelled), and it never substitutes for, overrides, or is averaged into the headline
`public_documents_only` result or the secondary pooled result. No run may report a verdict that
depends on this check passing or failing.

## 4. Non-retroactivity: the D=4 verdict of record is not reopened

This amendment is dated 2026-09-28 and takes effect for the **next** confirmatory run only. It
does not touch the run already completed and reported under v1: D=4 (`jcshm-manuscript`,
`jcshm-si`, `masters-dissertation-defense`, and one public docx-corpus document, per
`manifests/s25-respec-documents-locked-v2.json`), whose official verdict is **INCONCLUSIVE** --
not because the treatment effect is absent (the chain-level signal was strong), but because at
D=4 the document-level test's exact p-value floor is 2/2^4 = 0.125 (v1 section 6.3's general
statement of this floor: "the smallest attainable two-sided p is 2/2^D"), which cannot reach
p<0.05 regardless of the data, so v1 section 7's document-level co-requirement (C1-C4) was
mathematically unreachable at that D.

Per v1 section 11 item 1 ("The first computed verdict is final. ... It is always reported, as the
preregistered result, whatever happens afterwards.") and item 2 ("Later corrections or reruns are
new, separately labelled analyses ... never in its place. A rerun is a new protocol version with
its own lock, run root and verdict of record."), that INCONCLUSIVE verdict:

- stands exactly as computed and reported, under v1's own decision rule as locked, with its own
  document set (including the dissertation) and its own `confirm_disconfirm.pooled` basis;
- is **not** retroactively recomputed under `public_documents_only`-as-headline;
- is **not** retroactively relabelled, reinterpreted, or described as anything other than
  INCONCLUSIVE because of this amendment;
- is **not** described in the paper as having been "actually confirming" under a different
  (this) measure -- if a `public_documents_only`-only recomputation of the D=4 data is ever
  produced for interest, it is reported under its own label as a **post-hoc, non-confirmatory
  analysis of the v1 run** (the same treatment v1 section 11 item 2 and section 12 item 3 give the
  2026-09-23 run's post-hoc re-analyses), never pooled with, and never substituted for, the
  verdict of record.

The next confirmatory run under this amendment is a new protocol version in the sense v1 section
11 already anticipates, with its own lock, its own run root, and its own verdict of record,
governed by this amendment's headline measure.

## 5. Corpus for the next confirmatory run

The next run revives a larger base corpus than the D=4 run actually executed, built from:

- **The original D=8 design**, `manifests/s25-respec-documents-locked.json` (v1 section 1.3,
  SHA-256 `b700bf2e7d942082e0596578c61924859f2e523bf1576614f33f3fcfe8e5137f`), **minus the
  dissertation** (`masters-dissertation-defense`, row 3 of that manifest's table) per AD-3 --
  leaving the 2 remaining author-owned documents (`jcshm-manuscript`, `jcshm-si`) and the 5
  public documents of v1 section 1.2/1.3 (`s25pub_d3ff0b3c...` through `s25pub_ede3e098...`), 7
  documents.
- **New documents sourced from GOVDOCS1 (Digital Corpora)** as a second, independent sourcing
  pipeline alongside the existing docx-corpus pool of v1 section 1.2, addressing the same
  source-concentration concern section 1 raises at the corpus level, not just for the
  dissertation. This sourcing effort is already staged in this repository as a sibling,
  in-progress task (`manifests/govdocs1-candidates-shortlist.json`) and is **not yet finalized**
  as of this amendment: eligibility (six-family usability, v1 section 1.5's criteria), licensing
  and PII screening (v1 section 1.2's disclosed standard, D-R7) and hash-rank selection for the
  GOVDOCS1 slice all remain to be run, at the pin, exactly as v1 section 1.5 requires for any
  document entering a locked manifest.
- **Target size D ~= 9-10 total** (7 revived non-dissertation documents plus 2-3 GOVDOCS1
  documents), to be fixed once the GOVDOCS1 eligibility pass completes.

The combined result will be locked as `manifests/s25-respec-documents-locked-v3.json` in a
follow-up commit once the GOVDOCS1 selection is finalized -- this amendment does not itself lock
that manifest, consistent with v1 section 1.5's rule that eligibility and selection are only
final once recomputed at the pin, and with v1 section 0's rule that a protocol change is
prospective and disclosed rather than guessed. Until `s25-respec-documents-locked-v3.json` exists
and is committed, no confirmatory trial may run under this amendment (the same gate v1 section
14 already applies to its own then-open placeholders).

## 6. What this amendment does not change

- v1's FINAL DECISIONS D-R1, D-R3-D-R10 (corpus size rationale as originally argued, six families,
  the Meridian Docs pin, CLI/auth, co-author sign-off, licensing standard, budget) are unaffected.
  D-R2 (the May 2026 dissertation version is not added) is unaffected and, if anything,
  reinforced by AD-1's reasoning.
- v1 section 5 (scoring), section 6.1, 6.3-6.6 (levels, exact tests, estimates, the
  difference-in-drops test itself), section 9 (power, as a methodology), and sections 10-11
  (execution and verdict-of-record mechanics) are unchanged in how they work; this amendment only
  changes which computed analysis is the headline claim and which document set feeds it.
- v1 section 1.4's non-independence disclosure (correlation between the three original author
  documents) is unaffected; it now applies to two documents (`jcshm-manuscript`, `jcshm-si`)
  instead of three, since the dissertation is out of the corpus.
- The 2026-09-23 (S23) run and its own verdict are untouched, as always (v1 section 8's last
  bullet).

**A note on section numbering, for anyone checking this amendment against v1 directly:** v1 does
not use decimal sub-headings inside section 6.8 (there is no literal "### 6.8.3" heading); section
6.8 is a single numbered list of nine sensitivity analyses, and the cluster-merge mechanism this
amendment reuses is list item 3 of that section ("Document-level tests with every author document
merged into one cluster ..."). This amendment cites it as "v1 section 6.8, item 3" for that
reason, matching what was actually written rather than a heading that does not exist in v1.
