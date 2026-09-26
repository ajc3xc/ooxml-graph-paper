# PAPER-S25: respec_cascade re-run on more documents, claude-sonnet-5, six families (protocol v1)

Status: **LOCKED-PENDING-COMMIT (decided 2026-09-26).** Every `AUTHOR DECISION` placeholder below
is resolved by the FINAL DECISIONS of 2026-09-26 (this section and section 14). This document
still does not bind, and no confirmatory trial may run, until it is committed together with the
artifacts it names (`manifests/s25-respec-documents-locked.json` and the other lock-time
manifests) -- the lock commit. After the lock, any change is a new protocol version with a dated
reason, never an in-place edit (section 11).

**Final decisions (2026-09-26, the author, delegated; not reopened by this revision):**
- **D-R1 (D = 8).** 3 already-used author-owned documents (section 1.1) + 5 public documents
  selected by hash rank from `manifests/respec_public_review_queue.json`'s existing eligible
  queue (seed 20260925002, already recorded there; not re-seeded). Reason: the Sunday 19:00
  deadline leaves no time for the originally drafted two-reviewer content review of 9 candidates;
  hash-rank selection under an outcome-blind seed that predates this decision keeps the selection
  unbiased even without that review, and section 9's power table already reports D = 8 (was
  computed as a table row in the original draft): 86.1% at scenario A, 58.2% at scenario B
  (control freeze halved), 27.9% at scenario B (control never freezes) -- lower than D = 12, and
  disclosed as such (section 9, revised below).
- **D-R2 (no).** The May 2026 dissertation (`Masters_Dissertation_Report.docx`) is not added.
  Reason: power is adequate at D = 8 for the primary scenarios per the analysis above, and a
  correlated version of an already-used document (about 34% 12-gram overlap with the defense
  copy, section 1.1) would weaken the independence the document-level co-requirement (section
  6.3) depends on, not strengthen it.
- **D-R4 (Meridian Docs pin = `89c93fac6a9ee7a03d98baab34ba7043de983018`).** Verified 2026-09-26
  against `C:\Users\13144\Documents\Meridian\repository` (read-only): the commit exists
  (`git cat-file -t 89c93fac` -> `commit`; full id
  `89c93fac6a9ee7a03d98baab34ba7043de983018`, authored 2026-09-22, branch
  `docs-intel-journal-preset-externalization-20260918`, not on `main` or `dev`) and its diff to
  `extensions/meridian-docs` contains exactly the OMML validator fix this run needs: the
  `_validate_omml_structure` check for `m:num`/`m:den` changes from
  `element.find(_qm("e")) is None` to `len(element) == 0`, per the commit message and diff hunk
  inspected directly. No alternate commit search was needed.
- **D-R5 (CLI version = `2.1.283`; subscription token).** Resolved 2026-09-26 via
  `npm view @anthropic-ai/claude-code version` (registry-current at decision time; record the
  actually-installed `claude --version` again on the pod per section 4, since the registry can
  move between now and provisioning). Subscription OAuth token (not an API key): the runbook's
  `tools/usage_cap.py` pause/resume already handles a cap hit, no billing event is needed, and
  usage limits become the circuit breaker's concern (section 5.6), not a billing risk.
- **D-R6 (no separate co-author/committee sign-off beyond the author's own direction).** The
  author has directed the reuse of the three author-owned documents for this rerun; they were
  already used once under the same authority. Disclosed as a limitation: no additional written
  co-author or committee permission exists for this rerun beyond that direction, and this mirrors
  exactly how the documents were used in the original S23 run.
- **D-R7 (licence: dataset-level ODC-BY, per-file provenance unverified).** Same disclosure
  standard the currently published paper already uses for the existing section-reorder follow-up
  corpus (`main.tex`'s licensed-docops-corpus claim and its neighboring text); cited as precedent
  rather than inventing new wording. Documents are reported by hash only; no text or excerpt is
  released.
- **Known pool gap (accepted, not reconstructed).** Up to 42 documents the original follow-up
  review process read but never ran (S26's D-K5) may be present in the K4 candidate pool that
  this run's public documents are drawn from a disjoint slice of; their exact identity is not
  recoverable and no attempt is made to reconstruct the list (S26 section 1.1 carries the
  disclosure for the K4 corpus itself; it is noted here because both corpora share one pool
  build).

Every number below that depended on the drafted default D = 12 is revised to D = 8 in this
version; where the surrounding prose still shows a D = 12 worked example for context, it is
marked as such.

This protocol replaces nothing. `docs/paper-s23-respec-cascade-protocol-v0.md` (locked at
`370d6d4`) and its 2026-09-23 run stay on record exactly as they are, and the paper keeps
reporting them (section 12). This is a new, separately preregistered experiment. It keeps
the S23 task design (sections 2-3 of S23, reused by reference where unchanged), and fixes
every problem the 2026-09-25 audit and its review found in S23 and in its pipeline.

## 0. Why a new protocol, and what it changes

The 2026-09-23 run (haiku, five families, 3 author documents x 4 anchor-sets = 12 chains per
arm) cannot answer its own question, and its raw `chain-result.json` files and step outputs
were lost when the pod and volume were deleted.

| Audit finding (S23 v0 or its pipeline) | Consequence | This protocol |
|---|---|---|
| `_phase3_family_outcome` and `_phase2_keep_survival_outcome` excluded frozen chains, although S23 section 4 counts a frozen chain as failing | 5 of 12 control chains, 0 treatment, left the per-family and keep-survival denominators | A frozen chain fails every checkpoint it did not reach (section 5.2) |
| All 5 control freezes were at marker re-resolution points, which S23 does not define as freezes; scoring them `fail` imputes 0 to families that never ran | The lost run's verdict moved from DISCONFIRMING to INCONCLUSIVE on this imputation alone | A re-resolution failure fails only that family's round trip and the chain continues (section 2.4); freezes remain only for package-invalid output |
| `_freeze` discarded Phase-3 round trips that finished before the freeze | 10 finished round trips were never graded | They are graded and used (section 5.2) |
| The freeze cause was not recorded | Cause unknown for all 5 freezes | `freeze_cause`, `frozen_family` and `freeze_forward_step` recorded (section 5.3) |
| Pooled section-7 tests treated the family outcomes of one chain as independent | Anti-conservative p-values | Cluster sign-flip tests by chain, with a document-level co-requirement (sections 6-7) |
| `paired_permutation_test` is Monte Carlo only | p can undershoot its exact floor | Exact enumeration (section 6.4) |
| S23 section 7's Tier-1 clause could never be met with 3 documents (smallest document-level p = 0.25) | CONFIRMING was unreachable | Rule rewritten to be reachable and unambiguous (section 7) |
| The cascade-specific claim (control degrades more than treatment) had no test | Equal drops in both arms would still confirm 8-22% of the time | A difference-in-drops cluster test is required (sections 6.6, 7) |
| A timed-out chain was re-run on every resume | Timeouts silently re-run, mostly in control | Timeouts get their own statuses, trusted on resume (section 5.6) |
| The infrastructure signal included evidence the agent can produce (`is_error`, its own text) | A task failure could be excluded as infrastructure | Only CLI, API and process evidence counts, pinned in code (section 5.6) |
| `table_structural` was dropped because a stale, separately installed Meridian Docs build lacked `insert_table`/`remove_table` | Five-family contingency ran for the wrong reason | Six families; availability checked against the pinned build (section 2.3) |
| Meridian Docs was an unpinned editable install | Build under test unknown | Pinned by commit, installed without `-e` (section 4) |
| The run used `--model haiku` | Not the paper's main-benchmark model | `claude-sonnet-5`; a new experiment, not a replication (section 4) |
| Pod and volume deleted 2 minutes after only 4 summary JSONs were copied | Nothing can be re-graded | Archive, verify and recompute locally before teardown (section 10.7) |

## 1. Corpus

### 1.1 Author-owned documents (fixed)

The three documents of the 2026-09-23 run, at
`D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal\`. Hashes were first pinned in
S23 section 1.2a and re-verified 2026-09-25:

| doc_label | File | SHA-256 | headings / oMath / tables | six-family anchor-sets |
|---|---|---|---|---|
| `jcshm-manuscript` | `jcshm-manuscript.docx` | `ADA276D4DE9DD346B2F2B6BE3CFAC9E7637F6ECA849E0AA2B516D7B70C294747` | 54 / 128 / 42 | 4 / 4 |
| `jcshm-si` | `jcshm-si.docx` | `8CCDF9DD53A1CB16DEF8FC6F22044C5902D553C47CD0781FEC29677486495CB8` | 68 / 229 / 76 | 4 / 4 |
| `masters-dissertation-defense` | `masters-dissertation-defense.docx` | `B3336B9809DFB0BCAC5D73E0F2E94ED4D899A98A93217F01FD6FCA648AE0F332` | 121 / 510 / 131 | 4 / 4 |

These three were exposed to a *haiku* agent in the lost run. No model carries memory between
runs, and on the unpinned build (b0d28a61) the resolver gives the same anchor-sets as the lost
run (section_ids checked against `runs/paper-s23-final/anchor-schedules.json`, 2026-09-25).
Section 1.5 repeats this check at the pin.

**The author documents are not naive test items for the treatment.** Meridian Docs commit
`89c93fac` (2026-09-22) was written because `move_section` refused exactly these three
documents, and every pin option contains it (section 4). The treatment tool was therefore
debugged on confirmatory documents. Two consequences, fixed now: CONFIRMING requires the
public documents alone to show the same direction of effect (condition C6, section 7), and the
public-documents-only analysis is reported with the same prominence as the pooled one
(section 6.7).

**Optional fourth author document: decided NO (D-R2, 2026-09-26, final).** The May 2026
dissertation version `C:\Users\13144\OneDrive\Documents\Masters_Dissertation_Report.docx`,
SHA-256 `1F90C43AC27893C82F7F935DDFD6BA7A8C27950427786CB76C223C3CBD9CF473`, 132 / 376 / 75,
4/4 six-family anchor-sets, is **not** added. Reason: it is an earlier version of the same work
(about 34% of its 12-grams appear in the defense copy; four other May files are 82-99%
duplicates of it and are never used), and adding a correlated version of an already-used
document would weaken the independence the document-level co-requirement needs without a
compensating power gain -- section 9 shows D = 8 already gives adequate power at the realistic
B-row scenarios. No other author file is eligible either way: the remaining candidates are
near-duplicates of documents above, already touched by the harness (`38D21C00...`, the
thesis-p30 fixture source), or of unconfirmed authorship (`0B8DE410...`, the Codex-produced
staging draft).

### 1.2 Public documents (seeded, outcome-blind selection)

- **Pool.** `manifests/respec_public_candidates.json` (98 documents, SHA-256 of the file
  `846595846998aec4fb8b05a4364725c818c0c35e69e6ef88fae212e01c142b6d`), built by
  `python tools/build_rerun_candidates.py respec` (pipeline in `manifests/README.md`). It holds
  7 cleared S6 organic documents and 91 fresh docx-corpus documents with more than 25 headings.
  It is disjoint from the PAPER-S26 pool by construction (the organic documents are excluded
  there as touched; the fresh ones fall outside S26's 3-25 heading band).
- **Eligibility.** `six_family_usable == 4` (78 documents on the unpinned build), recomputed at
  the pin before any review (section 1.5).
- **Order.** Ascending `sha256(f"{seed}:{doc_sha256}")` with **seed `20260925002`**, no PRNG,
  identical on every Python version: `python tools/select_rerun_documents.py respec-queue
  --seed 20260925002` writes `manifests/respec_public_review_queue.json` (on the unpinned build
  SHA-256 `6b4094aa6047cb814adbe1afdc645eedc98a0304165e398f77dc64119028e4d1`; the first ranks
  are `d3ff0b3c...`, `acd13431...`, `c04412c3...`, `66157a47...`, `ede3e098...`).
- **Selection method: decided 2026-09-26, hash rank, not the two-reviewer content review drafted
  below.** The Sunday 19:00 deadline leaves no time to run the two-independent-reviewer content
  review this subsection originally specified for up to 9 candidates. FINAL DECISIONS instead
  takes the top 5 documents of the existing eligible review queue
  (`manifests/respec_public_review_queue.json`, 78 eligible, seed 20260925002, already recorded
  before this decision was made) by hash rank alone, with no free-text PII or suitability review
  beyond the pattern-based PII scan already in the candidate manifest
  (`pii_status: "tools/pii_pattern_scan clean (pattern scan only; no free-text review yet)"`).
  This is a disclosed lock-time deviation from the process below, produced deterministically and
  reproducibly by `tools/select_locked_documents.py respec` (not hand-written), and verified
  against each file's actual SHA-256 (section 1.3). **Residual risk, disclosed:** without the
  free-text review, personal information a regex cannot catch, or unsuitability as a real
  multi-section document, would not be caught before the lock; the pre-trial check (section 10.3)
  only re-verifies hashes and anchor-set usability, not content. If either is found after the
  lock, it is handled exactly as the pre-trial replacement rule below (replaced before the first
  confirmatory trial only).
- **Reviewers, review and near-duplicate process (as originally drafted; NOT run for this
  version because of D-R9 above).** Kept here as the process a future protocol version should use
  if a full content review becomes possible before its own lock: two independent content reviews
  per document (`manifests/paper-s25-review-prompt-v1.md` and
  `manifests/paper-s25-review-checklist-v1.md`, never written for v1); promote only when both
  reviewers promote; skip a near-duplicate when 50% or more of its stride-4 word 12-grams occur in
  an already-promoted or author document, or the reverse (`tools/docx_ngram_overlap.py`; ranks 2,
  7 and 13 of the queue share an identical 33-heading / 10-table profile and are likely template
  siblings, flagged for a future review but **not excluded here**, since v1 skips the review
  step entirely and takes ranks 1-5 as computed); stop at D - 3 promoted documents; log every
  verdict to `manifests/paper-s25-respec-public-review-log-v1.json`.
- **Pre-trial replacement only.** Before the first confirmatory trial, the pod re-checks every
  document (section 10.3). A document that fails is replaced by the next promotable document in
  order (rank 6, `bc30c7b7...`, then rank 7, etc., per `manifests/respec_public_review_queue.json`);
  the new document manifest and schedule hash are committed as dated amendment v1.1 before any
  trial. After the first confirmatory trial nothing is replaced; a failure is reported as
  `not_applicable`.
- **Licence and personal data: dataset-level ODC-BY, per-file provenance unverified (D-R7,
  decided 2026-09-26).** Same disclosure standard the currently published paper already uses for
  the existing section-reorder follow-up corpus (`main.tex`'s licensed-docops-corpus claim and
  its neighboring text), cited as precedent. `batch-500-v1` is `privacy_pii_review: not_assessed`,
  which the (skipped, see above) content review would have covered; this is now a disclosed gap
  rather than a covered one. The paper reports documents by hash and aggregate statistics only;
  no document text, excerpt or edited copy is released. D-R6 (co-author/committee permission,
  above) does not relax this for the author documents either: no separate release is made.

### 1.3 Document list and manifest (locked 2026-09-26)

`manifests/s25-respec-documents-locked.json` (SHA-256
`b700bf2e7d942082e0596578c61924859f2e523bf1576614f33f3fcfe8e5137f`), produced by
`python tools/select_locked_documents.py respec` and verified against every file's actual
SHA-256 at generation time (not taken from a candidate manifest on faith).

| # | doc_label | SHA-256 | Source | Review-queue rank |
|---|---|---|---|---|
| 1 | `jcshm-manuscript` | `ada276d4de9dd346b2f2b6be3cfac9e7637f6eca849e0aa2b516d7b70c294747` | author-owned, section 1.1 | - |
| 2 | `jcshm-si` | `8ccdf9dd53a1cb16def8fc6f22044c5902d553c47cd0781fec29677486495cb8` | author-owned, section 1.1 | - |
| 3 | `masters-dissertation-defense` | `b3336b9809dfb0bcac5d73e0f2e94ed4d899a98a93217f01fd6fca648ae0f332` | author-owned, section 1.1 | - |
| 4 | `s25pub_d3ff0b3c3f2d72d3` | `d3ff0b3c3f2d72d3e1aa59de7ab04446b2e470ba21987ea66b0702d4b14fa968` | public, section 1.2 | 1 |
| 5 | `s25pub_acd134313c175f4e` | `acd134313c175f4e5d9ceb10f33454115c977153a91e83cdccad73303ed4a428` | public, section 1.2 | 2 |
| 6 | `s25pub_c04412c3eeda841d` | `c04412c3eeda841d22fd345d3ca5ed3757ec528500d4cd542a82e29d1e5b18b5` | public, section 1.2 | 3 |
| 7 | `s25pub_66157a47a2b464f1` | `66157a47a2b464f153124998c373a6336d75560439381c4e2df80c1b997732bd` | public, section 1.2 | 4 |
| 8 | `s25pub_ede3e0981b844b40` | `ede3e0981b844b40238ef074e5c00b69de453a3292825d2a2a1a9598d179079f` | public, section 1.2 | 5 |

D = 8. The May 2026 dissertation (D-R2 = no) is not in this table.

The document manifest `manifests/paper-s25-respec-documents-v1.json` (pod-path form of the table
above, `{"documents": [{doc_label, docx_path, sha256}]}` with paths
`/workspace/ooxml-graph-paper/corpus/<doc_label>.docx`) is derived from
`manifests/s25-respec-documents-locked.json` at provisioning time (copy each `docx_path` under
`corpus/<doc_label>.docx` per runbook section 3.3); both sweeps check every SHA-256 against it
before anything else (`run_respec_cascade_sweep.load_document_manifest`). **A launch must load
`manifests/s25-respec-documents-locked.json` and confirm its SHA-256 equals
`b700bf2e7d942082e0596578c61924859f2e523bf1576614f33f3fcfe8e5137f` before deriving the pod
manifest**, so a stale or swapped locked-document file is caught before any corpus copy (runbook
section 3.3 states this check).

### 1.4 Non-independence (disclosed, carried into the analysis)

The three author documents are one body of work. By the 12-gram measure of
`tools/docx_ngram_overlap.py`, 63% of the manuscript and 76% of the SI occur in the
dissertation; `PROVENANCE.md` reports 19.0% and 16.7% with an unstated method, and its figures
should be corrected. The primary document-level test treats each document as its own unit; a
preregistered sensitivity analysis (section 6.8) treats all author documents as **one**
cluster.

### 1.5 Anchor-sets and eligibility, at the pin

- Per document, **4 anchor-sets**, from `resolve_respec_schedule(path, max_anchor_sets=4)` plus
  `run_respec_cascade_sweep.add_table_anchors` (the fourth body-anchor pool, resolved after
  citation, equation and caption with the same exclusion chaining, so the five-family anchors
  are unchanged).
- An anchor-set is usable only if it has a citation, equation, table and caption anchor, a
  section plan (`O`, `D1`) and a distinct redirect target `D2`. A document is eligible only if
  **all 4** anchor-sets are usable; documents are never used partially, so every document
  contributes exactly 4 chains per arm.
- **Everything is recomputed at the pin before any review verdict.** All eligibility so far
  was computed with the unpinned editable install (b0d28a61). Once D-R4 is decided:
  `pixi run python tools/respec_eligibility.py fresh` and `... organic` with the pinned build
  installed, then `build_rerun_candidates.py respec` and `select_rerun_documents.py
  respec-queue --seed 20260925002`; the review walks the pinned queue. Differences from the
  committed b0d28a61 manifests are recorded in the lock commit.
- **Author schedules at the pin.** The pinned schedule of each author document is compared with
  `runs/paper-s23-final/anchor-schedules.json` (section_ids and para_ids per anchor-set); every
  difference is reported. The pinned schedule is used either way. An author document with fewer
  than 4 usable six-family anchor-sets at the pin is dropped before the lock and replaced by one
  more public document, disclosed.
- **Schedule hash.** At lock, `run_respec_cascade_sweep.py --check-only` is run at the pins on
  the final document manifest; the `anchor-schedules.json` SHA-256 it prints is written into
  the locked commands (section 10.1, `<LOCK: S25 anchor-schedules sha256>`). The schedule holds
  anchor texts and ids, no file paths, so the laptop value is valid on the pod. The sweeps
  refuse to start on any other schedule, and a relaunch reads the stored schedule and never
  re-resolves it.

Nominal size at D = 12: **48 chains per arm** (52 if D-R2 = yes), and 48 x 6 = 288 fresh K=1
baseline chains per arm.

## 2. Task: the six-family respec_cascade chain

### 2.1 Rotation and respec rule (S23 section 2.2, unchanged)

`R = [Bibliography, Citation, SectionReorder, Equation, Table, Caption]`. Phase 1 builds all
six (steps 1.1-1.6). Phase 2 reverts Citation (2.1) and Table (2.2) and redirects the section
from `D1` to `D2` (2.3), leaving `B`, `E` and `Cap` untouched. Phase 3 runs one forward+inverse
round trip per family in order R (3.1-3.6; section reorder goes `D2 -> D1 -> D2`). That is
**21 agent steps per chain** (6 + 3 + 12), each a fresh `claude -p` process sharing only the
`.docx` on disk. Per (document, anchor-set), both arms, the chains plus the six K=1 baseline
chains of section 3 are **66 trials** (2 x (21 + 6 x 2)).

The expected final structure, the per-step dependencies and the isolation principle are those
of S23 section 2.2, read with the six-family rotation.

### 2.2 Implementation

`tools/run_respec_cascade_family.py::run_respec_cascade_chain(..., six_family=True)` at the
pinned harness commit (section 4). Table steps run at 1.5, 2.2 and 3.5; caption at 1.6 and 3.6.
Six-family chain ids contain `-six-`. Every freeze maps its step to a family through the
chain's recorded `rotation` (`step_family`), so 3.5 is table, not caption.

### 2.3 table_structural availability (replaces S23 section 1.2 item 2)

The check is made against the build under test, on the pod, before any trial:

1. The registered tool list of the pinned install (`meridian_docs.server.mcp.list_tools()`,
   sorted, stored as `logs/tool-manifest.json`, its SHA-256 in the provenance) contains
   `insert_table` and `remove_table`.
2. The smoke chain (section 10.2) passes the insert_table render-verification gate on the pod's
   render backend **without** `allow_degraded_render`, in both a Phase-1 and a Phase-3 step.

If both hold, the run is six-family. If either fails, that is a listed smoke-gate failure
(section 10.2) to fix before any confirmatory trial, **not** a trigger for a five-family
fallback. If it cannot be fixed, the author decides whether to run five families under a new
protocol version written before any confirmatory trial, never after confirmatory data exist.

### 2.4 Marker re-resolution (decided now; replaces the freeze)

Six steps need the harness to find, in the arm's own output, the marker a forward step
inserted: 2.1 (citation revert), 2.2 (table revert), 3.2-inverse, 3.4-inverse, 3.5-inverse
(table) and 3.6-inverse (caption). The resolvers are unchanged at the pin
(`resolve_para_id_by_marker_text`, `resolve_equation_para_id_by_marker`,
`resolve_table_index_by_marker`).

**Rule: a re-resolution failure fails that family's round trip, and the chain continues.**

- Phase 3: the inverse step is not run; the family's Phase-3 outcome is fail; the chain
  continues from the forward step's output.
- Phase 2: the revert step is not run; the chain continues from the current document;
  Checkpoint B is graded as usual (the un-reverted citation or table makes `citation_absent` or
  `table_absent` false, so Phase 2 fails), and keep-survival is scored as usual.
- The chain result lists every event under `reresolution_failures` with the step, the family
  and `_forward_step_summary` of the forward step that inserted the marker (its `timed_out`,
  `returncode`, `docx_changed` and package validity), so a harness timeout that left the
  document unchanged is distinguishable from the arm deleting the marker.

Code reference (prerequisite P-R9): in
`tools/run_respec_cascade_family.py::_run_respec_cascade_attempt`, the six calls
`_freeze(..., cause=FREEZE_CAUSE_ANCHOR_RERESOLUTION, forward_step=...)` (after
`resolved_cit`, `resolved_tbl`, `resolved_cit2`, `resolved_eq2`, `resolved_tbl2` and
`resolved_cap2` return `found=False`) are replaced by this rule, with a test for each of the
six points. After P-R9 a chain freezes only when a step's output fails
`_package_is_valid_docx` (`freeze_cause` `package_invalid`) or for a cause the orchestrator
records as `other`.

Why: freezing on a missing marker imputes 0 to every later family, which the chain never ran,
and it can reflect harness brittleness to hand-edited XML as much as a broken document. Failing
only the affected family keeps the arm accountable for losing its own marker and observes the
rest of the chain. The sensitivity analysis of section 6.8 item 5 excludes these failures
instead.

## 3. Fresh isolated K=1 baselines (S23 section 3, six families)

For every (document, anchor-set, family, arm): one K=1 forward+inverse chain at the identical
anchor, on a fresh copy of the pristine document, via `tools/run_respec_cascade_baselines.py`
calling `tools/run_paper_s7_benchmark.py::run_chain` with the anchor override. The baseline
sweep takes its anchor-sets only from the primary run's `anchor-schedules.json` (hash checked
against its meta file and the locked hash; there is no re-resolve fallback), its documents from
the primary run's meta file (re-hashed and checked against the document manifest), and its
families from the primary rotation (six-family adds `table_structural` at each anchor-set's
`table_anchor`). A family with zero baseline chains stops the sweep. Baseline chains carry
`doc_label = f"{doc_label}__anchor{i}"`, the pairing key of the statistics.

**Timing.** The baselines run **on the same pod session as the primary sweep or its documented
replacement pod** (identical pins and image; the replacement recorded in `pod_history`), and
**start within 48 hours of the end of the primary sweep**. The harness runs them as a separate
sweep after the primary one, not interleaved with it; this is disclosed, and host load and
model drift between the two sweeps are a stated confound of the drop measures (section 15).

## 4. Arms, model, pins and environment

- **Arms.** Control: `Read`, `Write`, `Edit`, `Bash` for every step. Treatment: `Read` plus
  exactly the one Meridian Docs tool the step needs, swapped per step
  (`claude_pair_runner._treatment_allowed_tools`). Prompts: `tools/docx_trial_broker.py` at the
  harness pin. Identical wording to both arms.
- **Model.** `claude-sonnet-5`, passed as the full id (`--model claude-sonnet-5`, never the
  `sonnet` alias). The smoke phase confirms `modelUsage` contains `claude-sonnet-5` and no other
  Sonnet or Opus model (the CLI's own `claude-haiku-4-5` helper calls are expected and
  recorded). The 2026-09-23 run used haiku; the paper states the model change wherever both are
  cited.
- **CLI.** `@anthropic-ai/claude-code@2.1.283` (D-R5, decided 2026-09-26: resolved from
  `npm view @anthropic-ai/claude-code version` at decision time; the registry can move before
  provisioning, so `claude --version` is recorded in the provenance and re-checked before each
  launch, and a later registry version is not substituted without a new dated decision). The
  harness runs it with `--output-format json --verbose`, so the CLI's own init record (MCP server
  status, tool list) is captured; `claude_json_result` still holds the final result record.
- **Authentication: subscription OAuth token (D-R5, decided 2026-09-26).** Not an API key:
  `tools/usage_cap.py`'s pause/resume already handles a usage-limit hit without a billing event,
  and the circuit breaker (section 5.6) stops the sweep at a usage limit either way. The secret
  lives only in a mode-0600 file on the pod's container disk (runbook section 6). (An
  OAuth-authenticated subscription session was already used today for an unrelated, bounded
  cost-measurement probe under a separate, now-revoked credential; it has no bearing on this
  pin.)
- **Meridian Docs.** Commit `89c93fac6a9ee7a03d98baab34ba7043de983018` (D-R4, decided 2026-09-26,
  **verified this same day** against `C:\Users\13144\Documents\Meridian\repository`, read-only:
  `git cat-file -t 89c93fac` returns `commit`; the commit exists, dated 2026-09-22, on branch
  `docs-intel-journal-preset-externalization-20260918` (not `main` or `dev`); its diff to
  `extensions/meridian-docs` contains exactly the OMML-validator fix this run needs -- the
  `_validate_omml_structure` check for `m:num`/`m:den` changed from
  `element.find(_qm("e")) is None` to `len(element) == 0`, confirmed by reading the commit
  message and diff hunk directly, not inferred from the runbook's own claim about it). It also
  contains `insert_table`/`remove_table` (tool-manifest check, section 2.3). Main `f92d2710` does
  **not** contain the fix. Exported with `git archive` and installed without `-e`; tree id and tar
  SHA-256 in the provenance.
- **Harness.** `ooxml-graph-paper` commit **to be filled at the actual lock commit** (not yet
  made: this pass leaves every change staged-but-uncommitted per the author's instruction; the
  value is `git rev-parse HEAD` immediately after the commit that locks this protocol file
  together with the manifests it names), exported with `git archive` (never copied from a working
  tree), including `tools/`, `manifests/` and this protocol. It must contain every prerequisite of
  section 13 -- confirmed present in the working tree 2026-09-26 (`tools/run_sweep_to_completion.py`
  and the `compute_respec_cascade_statistics.py` frozen-chain-mode/`--blocked-policy` additions
  described in section 13, plus a runaway-cost circuit breaker distinct from the infrastructure
  one: a running-total-cost check against every chain-result.json's `claude_json_result.total_cost_usd`
  under the watched run roots, checked between relaunch rounds, hard abort at $1,350 (3x the top
  of the $150-450 expected budget, section 14), writing `cost-circuit-breaker.json` with a clear
  reason on trip); `tools/respec_rerun_verdict.py` (P-R5) is still **not present** and remains a
  blocking prerequisite (section 13) -- the `s25-statistics` locked command will not parse until
  it exists.
- **Dependencies.** Installed from a constraints file frozen at the smoke phase
  (`logs/constraints.txt`, its SHA-256 in the provenance), so a reinstall on a replacement pod
  gets the same versions.
- **Per-step timeout.** `claude_pair_runner._TIMEOUT_SECONDS = 900`, the same for both arms.
- **Host.** One dedicated RunPod CPU pod (cpu3c, 8 vCPU / 16 GB, Secure Cloud), Linux,
  `--max-workers 6`, every process as the non-root user `bench`, Word-COM receipts off.
  Procedures: `docs/runpod-rerun-runbook-draft.md`.
- **Provenance.** Every manifest carries the runbook's section 3.4 provenance object.

## 5. Scoring (fixed now; applies identically to both arms)

### 5.1 Outcomes per chain

| Measure | Unit | Pass (1) | Fail (0) |
|---|---|---|---|
| Per-family Phase-3 outcome, 6 per chain | (chain, family) | the family's Checkpoint-C verdict is `pass` | anything else, including sections 2.4 and 5.2 |
| Keep-survival | chain | `phase2_result.keep_survival.overall_status == "clean_keep_survival"` | any other status; froze before Checkpoint B |
| Whole-chain composite | chain | Checkpoints A, B, C and every package-validity gate pass | anything else; any freeze |
| Chain completion | chain | status `completed` or `completed_with_failure` | status `chain_broken_at_step_*` |
| Baseline, 6 per anchor-set | (anchor-set, family) | `compute_s7_statistics._chain_outcome == 1.0` | 0.0, and every `blocked_*` status (section 5.6) |

### 5.2 Frozen chains

A chain freezes when a step's output fails `_package_is_valid_docx` (after P-R9, the only
freeze besides `other`). A frozen chain:

- fails every checkpoint it did not reach (keep-survival = 0 if it froze before Checkpoint B;
  composite = 0; completion = 0);
- **Phase-3 families not reached** (the family in progress, `not_completed`, and every later
  family, `not_run`) = 0;
- **Phase-3 round trips that finished before the freeze** are graded, and that verdict is the
  family's outcome. These are graded against the round trip's own output, not against the final
  document as a completed chain's Checkpoint C is; this is a slightly easier check, it applies to
  whichever arm freezes, and it is disclosed wherever the numbers are cited.

This is statistics mode `fail_graded_prefreeze` (prerequisite P-R1), the primary scoring. The
modes `fail` (all of a frozen chain's Phase-3 outcomes = 0), `exclude` (the 2026-09-23
behaviour) and `package_invalid_only` (freezes with cause `package_invalid` scored as in the
primary mode, freezes with any other cause excluded) are sensitivity analyses.

**Freeze-scoring robustness label (part of the verdict).** A CONFIRMING verdict is labelled
**robust to freeze scoring** if conditions C1-C4 and C6 of section 7 also hold under `exclude`,
and **dependent on freeze scoring** otherwise. The label is reported with the verdict wherever
the verdict is cited.

### 5.3 Freeze cause

Every frozen chain records `freeze_cause` (`package_invalid` or `other`; after P-R9 no chain
records `anchor_reresolution_failed`), `freeze_detail`, `frozen_at_step`, `frozen_family`
(through the chain's rotation) and the frozen step's result. The report lists every frozen
chain with these fields and its pre-freeze Phase-3 verdicts, by arm.

### 5.4 Marker re-resolution failures

Scored as section 2.4: the family observation (Phase 3) or the Phase-2 revert fails. Every
event is listed by arm with its `freeze_forward_step`-style summary. A re-resolution failure
whose forward step timed out without changing the document is still the arm's failure (the
timeout is the arm's, section 5.6).

### 5.5 Grader exceptions and post-lock grading

- **Verdict inputs.** Every observation is graded by the as-run graders at the harness pin.
  The only observations that may be re-graded after the lock and still feed section 7 are
  **grader-exception stubs**: a `grading_raised_exception` stub listed in the chain's
  `grading_exceptions`, or a baseline `_safe_grade` stub (verdict `fail`, reason starting
  `grading raised`). These are identified by the code path, not by judgment.
- **Stubs.** The grader is fixed by a committed, tested change (disclosed as a deviation) and
  **every stub of both arms** is re-graded from the archived step outputs with it. No other
  observation is re-graded for the verdict.
- **Stubs that cannot be re-graded** (archived output missing): the verdict is computed under
  the **adverse bound per arm** (a treatment Phase-3 or keep-survival observation = 0; a
  treatment baseline = 1; a control Phase-3 or keep-survival observation = 1; a control
  baseline = 0, so control_drop is smallest and direct and treatment_drop least favourable to
  the hypothesis) and under the symmetric **favourable bound**. If the two verdicts differ, the
  verdict is INCONCLUSIVE (condition C5).
- **Any other grader correction after the lock** (a defect claimed after the lock, however it
  is shown) is a **sensitivity analysis only**, labelled "post-lock grader correction", and never
  changes the section 7 verdict (section 11).

### 5.6 Timeouts, blocked baselines and infrastructure failures

- **Timeouts.** A step that reaches the 900 s timeout without an infrastructure signature is
  part of the arm's performance: the chain continues from whatever the step left on disk, and
  grading scores the consequences. A K=1 baseline chain that stops early records why:
  `blocked_timeout`, `blocked_forward_failed` (non-zero exit with a JSON result and no
  signature), `blocked_unreadable_input` or `blocked_inverse_unresolvable`. Each scores 0
  (`--blocked-policy fail`). All four are trusted on resume and never re-run.
- **Infrastructure signature** (`claude_pair_runner.classify_infra_signature`, with the kinds
  and patterns pinned in `INFRA_KIND_SCOPES` and `INFRA_ERROR_TEXT_PATTERNS` and tested in
  `tests/test_claude_pair_runner_infra.py`). Only evidence the agent cannot produce counts:
  1. the CLI's own API-error result (`is_error` true with subtype `success`) with
     `api_error_status` 401/403/429/529/5xx or matching error-type text;
  2. matching CLI stderr, only when the run did not end cleanly;
  3. a non-zero exit with no JSON result and no timeout;
  4. a negative return code (foreign signal) or a Windows NTSTATUS crash code;
  5. for treatment, the CLI's init record showing `meridian-docs-pilot` not connected and the
     trial's tool not listed.

  Never signatures: `is_error` alone, HTTP 400 errors such as "Prompt is too long",
  `error_max_turns`, `error_during_execution`, a harness timeout, or anything in the agent's own
  text (limit-like agent text is recorded as `unconfirmed_infra_text` only). Changing the
  pinned list after the lock is a protocol deviation.
- **A chain with any step or trial carrying a signature is `infra_blocked`**, whatever that
  trial's own outcome. It is never trusted on resume; its root is moved to `attic/` and it is
  re-run from the start.
- **Global signatures** (rate or usage limit, overload, authentication, API 5xx, connection)
  open the sweep-wide circuit breaker: no new trial starts, the chains it stops become
  `aborted_circuit_open`, and the sweep exits with code 3. Neither the global-signature attempt
  nor the aborted attempts count toward the rerun limit. After the event clears, the identical
  locked command is relaunched in the same run root (section 10.6).
- **Chain-scope signatures** and `harness_exception` count. `--max-chain-attempts 2` allows the
  original attempt and one rerun; a chain with two chargeable attempts becomes `infra_excluded`:
  excluded from every measure for that arm, its matched pairs drop out, and it is listed. The
  attempt ledger lives outside the chain root (`<run root>/_chain_attempts/`).
- **Statistics.** `infra_blocked`, `infra_excluded`, `aborted_circuit_open`,
  `harness_exception` and `not_applicable` are excluded from every measure and listed (for
  respec chains, prerequisite P-R2 adds the first three to
  `compute_respec_cascade_statistics._EXCLUDED_STATUSES`).
- `not_applicable` found at run time (should not happen after section 10.3's check): excluded
  for both arms and reported.

### 5.7 Render-gate timeouts

`run_trial` copies each trial's CLI session transcript (found by `session_id`) next to the
trial as `session-transcript.jsonl` (falling back to `cli-messages.json`) and reads only the
`tool_result` blocks of `mcp__meridian-docs-pilot__*` calls, matched by the pinned
`RENDER_GATE_ERROR_PATTERNS`. A trial records `render_gate_errors` and `render_gate_timeout`;
a respec chain records `step_log` and `render_gate_timeout_steps`.

- **Primary scoring: no special treatment.** A step whose Meridian tool hit a render-gate
  timeout is graded like any other step: a Phase-3 step through its family's observation, a
  Phase-1 or Phase-2 step through the checkpoints it feeds. A render-gate timeout that left the
  task undone is a treatment failure. It is never excluded and never re-run.
- **Sensitivity (a), excluded:** the S23 rule. The family observation (Phase-3 step) or the chain
  (Phase-1/2 step) is dropped together with its matched control observation.
- **Sensitivity (b), adverse bound (condition C5):** every observation touched by a
  render-gate-timeout step is forced to 0.
- There is no halt on render-gate timeouts: only treatment tools have a render gate, so a halt
  would give one arm an exit. The smoke phase checks the gate before any confirmatory trial.

## 6. Measures and tests

### 6.1 Sign conventions

- `control_drop_pp = 100 x mean(baseline - Phase-3)` over matched (family, chain) observations
  of the control arm; `treatment_drop_pp` likewise. Positive = worse after the cascade.
- `direct_pp = 100 x mean(treatment Phase-3 - control Phase-3)` over matched (family, chain)
  observations. Positive favours treatment.
- `keep_survival_pp`, `composite_pp`, `completion_pp` = 100 x mean(treatment - control) over
  matched chains. Positive favours treatment.
- `drop_difference_pp = control_drop_pp - treatment_drop_pp` over (family, chain) observations
  with all four values present (section 6.6).

The statistics script reports `observed_mean_diff` as A - B with A = cascade (drops) or A =
control (direct), so a negative value there is a drop or a treatment advantage; the verdict
script (P-R5) converts to the conventions above.

### 6.2 Primary measures

| # | Measure | Pooling | Pairing |
|---|---|---|---|
| P1 | `control_drop` | 6 families pooled | control Phase-3 vs control baseline, same family / document / anchor-set |
| P2 | `treatment_drop` | 6 families pooled | the same for treatment |
| P3 | `direct` | 6 families pooled | control vs treatment Phase-3, same family / document / anchor-set |
| P4 | `keep_survival` | per chain | control vs treatment, same document / anchor-set |
| P5 | `completion` | per chain | control vs treatment, same document / anchor-set |

Only the section 7 verdict is confirmatory (section 8). P2 and P5 enter the verdict only as
stated in section 7 (P2 through D2, D3 and C4; P5 not at all).

### 6.3 Levels

- **Chain level (primary test for every measure).** `graph_scorer.cluster_paired_sign_flip_test`
  with cluster = (document, anchor-set) chain: all observations of one chain, and of its matched
  baselines, flip sign together. Reported under `chain_level`.
- **Document level (co-requirement for CONFIRMING).** The same function with cluster = original
  document (4 chains, up to 24 family observations per document). Reported under
  `document_level` (P-R4). With D = 12 the smallest attainable two-sided p is 2/2^12 = 0.00049.
- **Observation level.** `paired_permutation_test_exact` and the as-run Monte Carlo
  `paired_permutation_test`, reported for continuity with S23, never used for a verdict or a
  claim.

Why both chain and document level: the family outcomes of one chain are strongly correlated
(binary r = 0.87 in the lost run). When documents differ in their own arm effect, the
chain-level test rejects a true null 9-11% (document latent ICC 0.2) to 15-21% (ICC 0.5) of the
time at nominal 5%, while the document-level test stays at 1.6-5.0% (section 9). Requiring both
for CONFIRMING keeps the chain as the primary unit without letting its anti-conservatism decide
the verdict.

### 6.4 Exact tests, as implemented

`graph_scorer._sign_flip_p_value` (harness pin): the two-sided p is the exact share of all
2^units sign patterns whose |sum| is at least the observed |sum|, built by convolution over
units (a zero-sum unit is skipped). It is exact whenever units <= 20, and also for more units
while the null distribution has at most 2^20 distinct sums, which always holds here: unit sums
are integers in [-6, 6] (chain) or [-24, 24] (document), and [-12, 12] or [-48, 48] for the
difference in drops. Otherwise it falls back to a seeded Monte Carlo estimate (2000 draws, seed
`20260828`, p = (k+1)/(N+1)). Each result carries `exact`; every primary p is expected to be
exact, and a non-exact primary p is reported as a deviation.

### 6.5 Estimates and intervals

Each measure reports both arms' rates, the paired difference in pp, and a 95% cluster bootstrap
CI at the chain and at the document level
(`compute_multianchor_extension_statistics.weighted_bootstrap_ci`, 2000 resamples, seed
`20260828`). Tier 1/2/3 figures (`_tiered_report`) are reported as descriptive continuity with
S23.

### 6.6 Difference-in-drops test (the cascade-specific claim)

For every matched (document, anchor-set, family) with a control Phase-3, control baseline,
treatment Phase-3 and treatment baseline observation:
`d = (control_baseline - control_phase3) - (treatment_baseline - treatment_phase3)`,
d in {-2, ..., 2}. `drop_difference_pp = 100 x mean(d)`, tested with
`cluster_paired_sign_flip_test` at chain level and at document level (P-R4, output key
`drop_difference`). Observations missing any of the four values are left out of this test and
counted.

### 6.7 Public-documents-only analysis

P1, P3, P4 and the difference in drops, at chain and document level, over the public documents
only (the smallest document-level p with 9 public documents is 2/2^9 = 0.0039). Reported beside
the pooled analysis with the same prominence. Condition C6 (section 7) requires the same sign
there; significance is not required.

### 6.8 Secondary and sensitivity analyses (reported; exploratory; no weight in section 7 except as stated)

1. Whole-chain composite, control vs treatment (chain and document level).
2. Per family (6 families), P1-P3 at chain and document level, Holm-adjusted across the six
   families within each measure.
3. Document-level tests with every author document merged into one cluster (D_eff = D - 2, or
   D - 3 with D-R2), for P1-P5.
4. Frozen-chain modes `fail`, `exclude` and `package_invalid_only` (section 5.2); `exclude` also
   sets the robustness label.
5. Marker re-resolution failures excluded instead of failed (section 2.4).
6. Render-gate timeouts excluded, and forced to 0 (section 5.7).
7. Grader-exception bounds (section 5.5) and any post-lock grader correction.
8. Baselines scored with `--blocked-policy exclude`.
9. Freeze counts and causes, re-resolution failures and timeouts by arm and step; per-step wall
   time, tokens and cost by arm (from `step-result.json` and `step_log`).

### 6.9 Analysis commands (locked)

Run on the pod after the baseline sweep, and again locally from the downloaded archive
(runbook section 11); both at the harness pin, Python version recorded.

```bash
# locked-command: s25-statistics
cd /workspace/ooxml-graph-paper/tools
for MODE in fail_graded_prefreeze fail exclude package_invalid_only; do
  /home/bench/venv/bin/python compute_respec_cascade_statistics.py \
    --run-root /workspace/ooxml-graph-paper/runs/rr-respec-v1/primary \
    --baseline-run-root /workspace/ooxml-graph-paper/runs/rr-respec-v1/baselines \
    --six-family --frozen-chain-mode "$MODE" --blocked-policy fail \
    --out "/workspace/ooxml-graph-paper/runs/rr-respec-v1/statistics/respec-rerun-v1-statistics-$MODE.json"
done
/home/bench/venv/bin/python respec_rerun_verdict.py \
  --statistics-dir /workspace/ooxml-graph-paper/runs/rr-respec-v1/statistics \
  --out /workspace/ooxml-graph-paper/runs/rr-respec-v1/statistics/respec-rerun-v1-verdict.json
```

**Match rule for the local recompute:** every p-value, point estimate, count and verdict field
must be identical; bootstrap CI bounds may differ in the last printed digit between Python
versions (float summation), which is disclosed, not corrected.

## 7. Decision rule (evaluated mechanically by `respec_rerun_verdict.py`)

"Significant" means two-sided exact p < 0.05. Quantities are pooled across the six families
(P1-P3, difference in drops) or per chain (P4), under the primary scoring of section 5.

**Step 1: DISCONFIRMING** if ANY of:

- D1. `direct`: chain-level p >= 0.05, or `direct_pp <= 0`.
- D2. Both drops null: (`control_drop` chain-level p > 0.10 AND `treatment_drop` chain-level p >
  0.10), OR (`control_drop_pp < 10` AND `treatment_drop_pp < 10`).
- D3. `treatment_drop_pp >= control_drop_pp`.

DISCONFIRMING is defined to include **"not detected at this sample size"**. Every DISCONFIRMING
verdict carries a mandatory sub-label:

- `contrary` if `direct_pp <= 0`, or `control_drop_pp <= 0`, or D3 holds: the point estimates
  point against the hypothesis;
- `not_detected_at_D=<D>` otherwise: the hypothesised effect was not detected at this D. The
  paper then says "no detectable effect at D = <D>", never "no effect" or "disproved". Under a
  real half-size effect this happens 17.5% of the time at D = 12 (section 9).

**Step 2: CONFIRMING** if not disconfirming and ALL of:

- C1. `control_drop_pp >= 10`, with chain-level p < 0.05 AND document-level p < 0.05.
- C2. `direct_pp > 0`, with chain-level p < 0.05 AND document-level p < 0.05.
- C3. `keep_survival_pp > 0`, with chain-level p < 0.05 AND document-level p < 0.05.
- C4. `drop_difference_pp >= 10`, with the difference-in-drops test (section 6.6) chain-level
  p < 0.05 AND document-level p < 0.05.
- C5. If any grader-exception bound applies (5.5): the verdict is the same under both bounds.
  If any render-gate timeout occurred: C1-C4 also hold under the adverse bound of 5.7 (b).
- C6. Public documents only (section 6.7): `control_drop_pp > 0` and `direct_pp > 0`.

**Step 3: otherwise INCONCLUSIVE**, reported with the list of conditions that were and were not
met.

C1-C4 and D1-D3 cannot hold together (C1 excludes D2, C2 excludes D1, C4 excludes D3), so the
verdict is always exactly one of the three. A CONFIRMING verdict carries the freeze-scoring
label of section 5.2. Chain completion (P5) is always reported with its tests, but the verdict
does not depend on it: a freeze already scores as failure in P1, P3 and P4. A significant
negative `treatment_drop` (treatment above its own baseline) is reported, not treated as a
failure.

## 8. Claims (binding on the paper)

- **Confirmatory claims** are only: the section 7 verdict, its sub-label or robustness label,
  and the values of the conditions it rests on. Only these may be described as "confirmed",
  "preregistered result", or "significant" without qualification.
- **Everything else is exploratory**: P2 and P5 as stand-alone results, the composite, the
  per-family tests, the author-cluster analysis, the public-only analysis beyond C6, every
  sensitivity analysis, and every observation-level p. A p-value from these is printed either
  as "(unadjusted, exploratory)" or Holm-adjusted within its pre-listed family: the secondary
  family {P2, P5, composite} at chain level, and the six families within each of P1-P3 for the
  per-family tests. No per-family claim is made from an unadjusted p.
- "Treatment is robust to the cascade" (or any wording that one arm degrades more than the
  other) may be claimed only inside a CONFIRMING verdict, because only C4 tests it.
- The abstract states the verdict and its label, D, the model and the three effects of C1-C3,
  whatever the outcome; a DISCONFIRMING or INCONCLUSIVE verdict gets the same prominence a
  CONFIRMING one would.
- The 2026-09-23 run is never pooled with this run, and none of its post-hoc analyses is
  described as confirmatory.

## 9. Sample size and power

Simulation of the exact section 7 rule (D1-D3, C1-C4 with the chain AND document
co-requirement and the difference-in-drops test in C4), primary scoring
`fail_graded_prefreeze`, exact tests (`graph_scorer.cluster_paired_sign_flip_test`), R = 10,000
per cell, seed 20260925, Monte Carlo SE <= 0.5 points. D = documents x 4 anchor-sets. Script:
`scratchpad/wf_rerun_prep2/power/power_s25_exact_rule.py` (to be committed with the lock as
`tools/power_s25_exact_rule.py`). Conditions C5 and C6 are not modelled.

**P(CONFIRMING), %**

| Scenario | control_drop / direct / keep-survival gap (pp) | D=8 | D=10 | D=12 | D=14 | D=16 | D=20 | D=24 / 32 / 40 | D for 80% | D for 90% |
|---|---|---|---|---|---|---|---|---|---|---|
| A lost-run-like, haiku freeze rate 5/12 | 31 / 61 / 58 | 86.1 | 95.1 | 98.5 | 99.5 | 99.9 | 100.0 | - | 8 | 10 |
| B control freeze halved | 24 / 54 / 56 | 58.2 | 75.1 | 85.8 | 91.7 | 95.2 | 98.6 | - | 12 | 14 |
| B control never freezes | 16 / 47 / 55 | 27.9 | 38.8 | 50.4 | 59.6 | 67.4 | 78.6 | 86.9 / 92.9 / 95.7 | 24 | 32 |
| C half effect | 15 / 46 / 29 | 22.9 | 42.9 | 57.9 | 68.1 | 75.9 | 85.1 | 89.8 / 93.1 / 95.5 | 20 | 32 |
| C quarter effect (control_drop < 10) | 8 / 38 / 15 | 1.1 | 4.6 | 10.5 | 16.6 | 21.2 | 27.4 | 27.3 / 23.8 / 22.6 | never | never |
| E document clustering 0.2 | 31 / 61 / 58 | 70.8 | 85.7 | 93.2 | 97.1 | 98.4 | 99.6 | - | 10 | 12 |
| E document clustering 0.5 | 31 / 61 / 58 | 51.0 | 68.2 | 78.2 | 86.1 | 91.0 | 96.4 | - | 14 | 16 |
| E clustering 0.5 + half effect | 15 / 46 / 29 | 6.3 | 15.2 | 25.6 | 33.1 | 40.6 | 50.4 | 59.2 / 73.5 / 82.3 | 40 | >40 |
| G treatment off ceiling | 31 / 51 / 53 | 51.0 | 65.9 | 78.0 | 85.6 | 89.9 | 95.8 | - | 14 | 20 |
| F Sonnet K=1 baselines, drop 30 | 30 / 32 / 57 | 85.7 | 96.2 | 99.2 | 99.8 | 99.9 | 100.0 | - | 8 | 10 |
| F Sonnet K=1 baselines, drop 15 | 15 / 17 / 28 | 17.6 | 39.5 | 57.5 | 70.1 | 77.2 | 86.2 | 88.5 / 92.3 / 95.2 | 20 | 32 |
| F Sonnet K=1 baselines, drop 8 | 8 / 10 / 15 | 0.8 | 3.4 | 6.9 | 10.3 | 12.6 | 17.3 | 17.3 / 16.7 / 15.4 | never | never |

**Which rows apply.** Every lost-run freeze was a marker re-resolution failure, and section 2.4
no longer freezes on those, so the freeze-dependent part of scenario A will not recur as such:
a re-resolution failure now costs one family, not the rest of the chain. The realistic range is
between the A row and the B rows. At D = 12 the B rows give 50-86%; D = 16 gives 67-95%; D = 20
gives 79-99%.

**DISCONFIRMING under a real effect** (almost all through D2's point clause; hence the
sub-label of section 7): half effect 17.5% at D = 12 and 12.0% at D = 20; control never freezes
17.9% and 12.1%; strong clustering plus half effect 28.7% and 22.5%. D1 fires only when
baselines are near ceiling (Sonnet K=1 rates): 8.6% at a 15pp drop and 38.5% at 8pp, D = 12.

**Nulls (R = 20,000 per cell, D = 8 / 12 / 20).** False CONFIRMING of this rule: global null
<= 0.1%; no control drop but a real direct gap 0.1-1.9%; identical arms under a real cascade
<= 0.1%; no keep-survival gap 0.6-1.7%; **equal drops in both arms 1.8-3.2%** (without the
difference-in-drops test it was 7.8-22.2%). The difference-in-drops test costs no power when
treatment is at ceiling (A-E) and 18 points at D = 12 when it is not (G: 95.9% without it,
78.0% with it).

**D = 8 (D-R1, decided 2026-09-26, final -- not reopened here).** From the section 9 table above:
scenario A (lost-run-like effect and freeze rate) gives 86.1% at D = 8; scenario B (control freeze
halved) 58.2%; scenario B (control never freezes) 27.9%; half effect 22.9%. This is markedly
below the >= 90% that D = 16-20 would give under the more robust B rows, and the author has
accepted that tradeoff explicitly to meet the Sunday 19:00 deadline (the run must be launched,
not maximally powered): D = 8 is enough to detect a lost-run-like effect with high probability,
and a null result at D = 8 under a real half-size effect is expected roughly one time in four
(section 9's D2 disconfirming-sub-label rate) and is reported as "not detected at this sample
size," never as "no effect," exactly as section 7 already requires. A document-level p < 0.05 is
impossible below D = 6, so D = 8 keeps the document-level co-requirement meaningful.

**Cost at D = 8** (runbook section 13 unit costs: $16.64/author-document unit, $13.30/public-document
unit, 66 trials/unit): 3 author units + 5 public units = 8 x 66 = 528 trials, about
**$116 API-equivalent** base ($3 x $16.64 + 5 x $13.30 = $49.92 + $66.50 = $116.42) plus smoke,
**$140** with the +20% rerun allowance. Well inside the $150-450 combined-run expected budget and
the $1,350 runaway-cost circuit breaker (section 14 final decisions). For reference, the
original draft's larger-D figures (no longer describing this run): D = 12 about $695/$834,
D = 16 about $908/$1,090, D = 20 about $1,121/$1,345.

## 10. Execution

### 10.1 Run layout and locked commands

Pod layout (identical strings in the runbook): `/workspace/ooxml-graph-paper/` holds
`pins/`, `tools` (symlink into the exported harness), `manifests/`, `docs/`, `corpus/`,
`runs/rr-respec-v1/primary`, `runs/rr-respec-v1/baselines`, `runs/rr-respec-v1/statistics`,
`logs/`, `archive/`. The commands below are copied into the runbook byte for byte; the
runbook launches them by extracting these blocks from this file (runbook section 8).

**`<LOCK: S25 anchor-schedules sha256>` and `<LOCK: S25 smoke document sha256>` are deliberately
still open placeholders in this revision, not filled with a guessed or precomputed value.** Both
are outputs of running `run_respec_cascade_sweep.py --check-only` (and, for the smoke document,
the section 10.2 selection procedure) against the **pinned** Meridian Docs build
(`89c93fac`, now decided) and the actual corpus files on the pod or an equivalent pinned-build
environment -- section 1.5 requires the eligibility and schedule to be recomputed at the pin
before any review verdict, and this pass had neither the pinned build installed locally nor pod
access (out of scope: "never start/stop/create/connect to a RunPod pod"). Filling these values
without actually running the pinned resolver would risk exactly the kind of silent
misreporting this protocol exists to prevent (section 0's own audit history). They are filled by
running the `s25-check`-equivalent step once the pinned build is available (runbook section 3.1
already gives the `git archive` export commands), and the runbook's own launch-script extractor
(section 8.1) refuses to write `launch/*.sh` while either placeholder remains, so an unfilled
value cannot silently reach a launch.

```bash
# locked-command: s25-check
cd /workspace/ooxml-graph-paper/tools
/home/bench/venv/bin/python run_respec_cascade_sweep.py --check-only \
  --run-root /workspace/ooxml-graph-paper/runs/rr-respec-v1/primary \
  --documents-manifest /workspace/ooxml-graph-paper/manifests/paper-s25-respec-documents-v1.json \
  --six-family --max-anchor-sets 4 \
  --expected-schedule-sha256 <LOCK: S25 anchor-schedules sha256>
```

```bash
# locked-command: s25-primary
cd /workspace/ooxml-graph-paper/tools
/home/bench/venv/bin/python run_respec_cascade_sweep.py \
  --run-root /workspace/ooxml-graph-paper/runs/rr-respec-v1/primary \
  --documents-manifest /workspace/ooxml-graph-paper/manifests/paper-s25-respec-documents-v1.json \
  --six-family --max-anchor-sets 4 --model claude-sonnet-5 --max-workers 6 \
  --expected-schedule-sha256 <LOCK: S25 anchor-schedules sha256> \
  --arm-order-seed 20260925004 --max-chain-attempts 2 \
  --provenance-json /workspace/ooxml-graph-paper/logs/provenance-rr-respec-v1-primary.json
```

```bash
# locked-command: s25-baselines
cd /workspace/ooxml-graph-paper/tools
/home/bench/venv/bin/python run_respec_cascade_baselines.py \
  --run-root /workspace/ooxml-graph-paper/runs/rr-respec-v1/primary \
  --baseline-run-root /workspace/ooxml-graph-paper/runs/rr-respec-v1/baselines \
  --documents-manifest /workspace/ooxml-graph-paper/manifests/paper-s25-respec-documents-v1.json \
  --six-family --model claude-sonnet-5 --max-workers 6 \
  --expected-schedule-sha256 <LOCK: S25 anchor-schedules sha256> \
  --arm-order-seed 20260925004 --max-chain-attempts 2 \
  --provenance-json /workspace/ooxml-graph-paper/logs/provenance-rr-respec-v1-baselines.json
```

Exit codes: 0 finished; 2 refused to start (a hash, schedule, rotation or manifest mismatch,
or a family with no baseline chain) or `--check-only` failed; 3 circuit breaker open.

### 10.2 Smoke phase (never confirmatory; after the lock)

- **Smoke document (not an author document).** The first document, in ascending
  `sha256(f"20260925003:{doc_sha256}")` order, of `manifests/respec_public_candidates.json`
  that is **not** in the review queue (`six_family_usable < 4`, so it can never be
  confirmatory), whose `--check-only --six-family --max-anchor-sets 1` passes at the pin, and
  whose 12-gram overlap with every
  confirmatory document is **below 50% in both directions** (`tools/docx_ngram_overlap.py`).
  It gets a regex PII check and one content review. Its SHA-256 is recorded in the lock commit
  (`<LOCK: S25 smoke document sha256>`).
- **Scope.** One six-family chain per arm (`--max-anchor-sets 1`) plus its 12 baselines, run root
  `runs/smoke-s25-<date>/` (commands in runbook section 7). No confirmatory document or
  anchor-set is used.
- **Gates** (runbook section 7): model id and CLI version; tool manifest; no process as root;
  no isolation violation; no `harness_exception` or `infra_blocked`; the insert_table render
  gate of 2.3; `step-result.json`, `step_log`, `session-transcript.jsonl` and provenance present;
  per-trial cost and wall time within 2x of plan; archive round trip verified.
- **Code changes after the smoke phase are allowed only to fix a listed gate failure:** the
  render gate of 2.3; a missing required tool; an infrastructure-classification error seen in a
  smoke trial (a signature missed or wrongly assigned); a missing step record, transcript copy
  or provenance field; a `harness_exception`; an isolation-audit error; an archive or secret
  scan failure. Each such change is logged in `logs/deviations.md` (gate, change, commit), gets
  a new harness pin and protocol amendment v1.x committed before any confirmatory trial, and a
  new smoke phase. No other code change is permitted after the lock.

### 10.3 Pre-trial check (on the pod)

`s25-check` must exit 0: every document's SHA-256 equals the manifest, all four anchor-sets of
every document are usable, and the schedule hash equals the locked value. The check writes the
schedule and its meta file into the primary run root, where the primary sweep reads (never
re-resolves) them. Its output goes to `logs/s25-check.log`.

### 10.4 Order

Primary sweep (96 chains at D = 12) first, then the baseline sweep (576 chains), one fixed run
root each (section 10.1). Within each sweep both arms of each unit are submitted back to back,
in manifest order, the arm order within each pair fixed by `--arm-order-seed 20260925004`.
The baselines start within 48 h of the primary sweep's end (section 3). Nothing is deleted;
superseded data go to the attic with a line in `logs/deviations.md`.

### 10.5 Monitoring

- The design runs **once**, at the fixed D. No documents are added, removed or replaced after
  the first confirmatory trial, whatever the interim numbers look like.
- The heartbeat (runbook section 10) reports only pooled counts: finished chains, the
  `infra_blocked` / `infra_excluded` / `aborted_circuit_open` / `harness_exception` counts, the
  attempt ledger, timeouts pooled across arms, and spend. No pass/fail count, per-arm outcome or
  statistic is computed until the baseline sweep ends, and no decision may cite one.

### 10.6 Pauses, halts and their fixed remedies

| Trigger | Kind | Remedy (fixed now) |
|---|---|---|
| Circuit breaker open (exit code 3, a global signature) | pause | Wait until the limit or outage clears; relaunch the identical locked command in the same run root. Stopped chains re-run without being charged. Logged in `deviations.md` with the signature. |
| Pod loss or interrupted sweep | pause | Runbook section 9 recovery; relaunch the identical command in the same run root; interrupted attempts are not charged. |
| Spend above 1.3x plan for the progress reached | pause | The author approves a higher budget (logged) and the identical command is relaunched, or abandons the run: NOT EVALUATED (section 11). |
| Timeouts above 5% of trials, pooled across arms (after >= 100 trials) | halt | Environment defect. The run is NOT EVALUATED. A new run (amendment v1.x, new run root, same documents, pins and 900 s budget, `--max-workers 3`) starts from scratch. |
| Chain-scope `infra_blocked`, `infra_excluded` or `harness_exception` above 5% of chains | halt | Harness or environment defect: as the next row. |
| Isolation violation, or any harness defect found during the run | halt | NOT EVALUATED. Fix and disclose; new harness pin, new protocol version and new run root; every chain of both arms re-run. |

There is no halt on arm outcomes and none on render-gate timeouts (section 5.7). A halted run's
data are kept, archived and reported descriptively (section 11).

### 10.7 Archive before teardown (binding)

No pod or volume is deleted until all of the following are done (runbook sections 11-12): every
chain root with every step's `doc.docx`, `step-result.json` and `session-transcript.jsonl`; the
baseline roots; `anchor-schedules.json` and its meta file; `_chain_attempts/` and `attic/`;
manifests, statistics, logs, provenance and `deviations.md` are in one archive; the
pre-download secret scan (which covers every transcript copy) is clean; the archive's SHA-256
and every per-file SHA-256 verify on the laptop's `C:`; the statistics recomputed locally from
the extracted tree match the pod's under the rule of 6.9; a second copy verifies at a second
location; the archive and its SHA-256 are registered in `paper/sources/`.

## 11. Verdict of record, versions and halted runs (binding)

1. **The first computed verdict is final.** The first time `respec_rerun_verdict.py` runs on the
   complete data of this protocol version, its output is the verdict of record for this
   version. It is always reported, as the preregistered result, whatever happens afterwards.
2. **Later corrections or reruns are new, separately labelled analyses.** A grader, harness,
   scoring or data correction found after that point, or a rerun of any part of the
   experiment, is reported alongside the verdict of record under its own label (for example
   "S25 v1, post-lock correction 1" or "S25 v2 rerun"), never in its place. A rerun is a new
   protocol version with its own lock, run root and verdict of record.
3. **One registry table.** The paper has a single table listing every version and run of this
   line of work (the original unpreregistered K=4 result, S23 v0 and its 2026-09-23 run with its
   post-hoc re-analysis, S25 v1 and any v1.x or v2, S26 v1 and later): protocol and lock commit,
   model, run dates, data status, verdict of record, and every later labelled analysis.
4. **Halted runs.** A run that is halted and not resumed is **NOT EVALUATED**: no test is run on
   its data, and its partial data (counts, costs, halt reason, pooled progress) are reported
   descriptively only. The remedy for each halt reason is the one fixed in section 10.6.
5. **Accidental early looks.** If any arm-level outcome is computed before the sweep ends, it is
   logged in `deviations.md` and disclosed next to the verdict.

## 12. Reporting (whatever the outcome)

1. The section 7 verdict with its sub-label or robustness label, every condition's value, and
   every primary measure at chain, document and observation level, with rates, differences,
   CIs and exact flags; the public-documents-only analysis with the same prominence.
2. All section 6.8 analyses, all exclusions with reasons, every frozen chain with cause, every
   re-resolution failure, `infra_blocked`, `infra_excluded`, render-gate timeout, grader
   exception and deviation. Null and adverse results are reported with the same prominence as
   positive ones.
3. **The 2026-09-23 run, as it stands**, in its own table, never pooled: haiku, five families,
   3 documents x 4 anchor-sets. In section 6.1's conventions:
   - *As run* (`paper/sources/respec-cascade-statistics.json`, frozen chains excluded): pooled
     control_drop 17.2pp (n = 29, chain-level p = 0.5, document-level p = 0.75); direct 46.7pp
     in treatment's favour (chain-level p = 0.25); keep-survival 54.5pp (p = 0.031); whole-chain
     composite 81.8pp (p = 0.0039). S23 section 7 verdict **DISCONFIRMING at chain, observation
     and document level**.
   - *Under S23's own section-4 scoring, every frozen cell = 0*
     (`paper/sources/respec-cascade-reanalysis.json`, post hoc): control_drop 40.7pp
     (chain-level p = 0.021); direct 70.9pp (p = 0.0078); keep-survival 58.3pp (p = 0.016);
     composite 81.8pp (p = 0.0039). S23 section 7 verdict **INCONCLUSIVE at chain level and at
     observation level** (confirming conditions met, but not the Tier-1 clause) and
     **DISCONFIRMING at document level** (3 documents; the smallest document-level p is 0.25, so
     CONFIRMING was unreachable).
   - *Bounds, never reported without the verdict above.* The 10 Phase-3 round trips that
     finished before a freeze were never graded: over all 1,024 assignments, control_drop runs
     from 22.2pp (all pass, chain-level p = 0.109) to 40.7pp (all fail, p = 0.021, the scenario
     above); excluding them gives 34.1pp (p = 0.047), an intermediate case, not a bound. The
     chain-level verdict over the assignments: 818 INCONCLUSIVE with confirming conditions met,
     204 INCONCLUSIVE, 2 DISCONFIRMING. If the families a frozen chain never ran are excluded
     rather than scored 0, control_drop runs from 32.6pp (p = 0.059) to 9.3pp (p = 0.60), and the
     chain-level verdict is DISCONFIRMING in 974 and INCONCLUSIVE in 50 of the 1,024
     assignments. The direct comparison stays significant at chain level under every bound
     (p = 0.0078, or 0.0156 with never-run families excluded).
   - The grader-crash chain (`jcshm-si` anchor-set 3, control, 5 Phase-3 cells) is excluded
     throughout; over its 32 assignments the scenario above has control_drop chain-level p
     0.011-0.029, and the bound scenarios can shift by one verdict category.
   - The paper says that the frozen-chain correction and the chain-level test were applied after
     the 2026-09-23 results were known.
4. This protocol's commit, the harness and Meridian Docs pins, the model and CLI version, the
   archive SHA-256, and the registry table of section 11.

## 13. Code prerequisites (committed and tested before the lock)

**Done 2026-09-25 (in the working tree, uncommitted; committed before the lock):**
frozen-chain modes `fail`/`exclude`; `freeze_cause`, `frozen_family` (through the rotation),
`freeze_forward_step`; pre-freeze Phase-3 grading; `grading_exceptions`; `step-result.json`
and `step_log`; the exact and cluster tests and `chain_level` fields; the six-family
orchestrator and statistics; archive of every `.docx` by default; the infrastructure guard
(`classify_infra_signature`, pinned patterns, `infra_blocked`), circuit breaker (exit 3),
attempt ledger and `--max-chain-attempts`, attic moves for untrusted chain roots and reused trial
directories; the `blocked_*` statuses trusted on resume and `--blocked-policy` in
`compute_s7_statistics`; render-gate capture from the session transcript; `--check-only`,
schedule meta file and `--expected-schedule-sha256`; `--documents-manifest` for both sweeps; the
six-family baselines with `table_structural` and the zero-family guard; arms submitted back to
back with `--arm-order-seed`; the selection tools and manifests (`manifests/README.md`).

**Still required:**

- **P-R1** `compute_respec_cascade_statistics.py`: frozen-chain modes `fail_graded_prefreeze`
  (the primary) and `package_invalid_only` (section 5.2); the completion measure P5; a
  `--blocked-policy` option passed to `_chain_outcome` for the baselines; tests.
- **P-R2** Statistics side of the guard: add `infra_blocked`, `infra_excluded` and
  `aborted_circuit_open` to `_EXCLUDED_STATUSES`; the render-gate sensitivity fields
  (excluded, forced to 0) from `render_gate_timeout_steps`; tests.
- **P-R4** `document_level` tests beside every `chain_level` entry; the difference-in-drops test
  (`drop_difference`, section 6.6); the public-documents-only analysis (6.7); the author-cluster
  sensitivity; the re-resolution-excluded sensitivity; Holm adjustment for the per-family and
  secondary families.
- **P-R5** `tools/respec_rerun_verdict.py`: applies section 7 (with sub-labels, C5, C6 and the
  freeze-scoring label) and 6.1's sign conventions mechanically from the four statistics files,
  with tests on hand-built inputs for each branch.
- **P-R6** `--provenance-json` for both sweeps (runbook P5), copied into their manifests.
- **P-R7** Move the six-family table grading from the orchestrator wrappers into
  `tools/docx_trial_evaluator.py` (recommended, not blocking; if not done, the smoke phase
  exercises it on a real document).
- **P-R8** The document-manifest builder (review log to `paper-s25-respec-documents-v1.json`)
  and the smoke-document selection of 10.2, committed with the manifests.
- **P-R9** Marker re-resolution: fail the family's round trip and continue (section 2.4), with
  six tests.
- **P-R10** The power script committed as `tools/power_s25_exact_rule.py`, extended to the
  final rule if P-R4/P-R5 change anything it models.

## 14. Lock checklist: decisions the author must make first

**All of D-R1/2/4/5/6/7 below are FINAL DECISIONS, decided by the author (delegated) on
2026-09-26 and not reopened by this or any later revision without a new dated decision.** Each is
also stated in full, with its one-line reason, in the status block at the top of this document.

- **D-R1 (decided): D = 8.** 3 author-owned + 5 public documents. See the status block and section
  9 for the reason and the power tradeoff accepted to meet the Sunday 19:00 deadline.
- **D-R2 (decided): no.** The May 2026 dissertation is not added. "The MS dissertation report" is
  the defense copy already in section 1.1 (`masters-dissertation-defense`); the May 2026 file is a
  distinct, earlier, correlated version and stays excluded.
- **D-R3** Six families (this draft) confirmed.
- **D-R4 (decided): `89c93fac6a9ee7a03d98baab34ba7043de983018`.** Verified to exist and to contain
  the OMML-validator fix (section 4); no cherry-pick alternative is needed.
- **D-R5 (decided): CLI `2.1.283`; subscription OAuth token.** See section 4.
- **D-R6 (decided): no separate sign-off beyond the author's own direction to reuse the three
  documents, disclosed as a limitation.** See the status block.
- **D-R7 (decided): dataset-level ODC-BY, per-file provenance unverified, precedent cited from
  the published paper's existing licensed-docops-corpus disclosure.** See the status block.
- **D-R8** Section 7 as written (chain-level primary with a document-level co-requirement) --
  kept; not reopened.
- **D-R9 (superseded by the 2026-09-26 hash-rank selection, section 1.2): no reviewer names are
  needed for this version**, since the two-reviewer content review is not run for v1 (disclosed
  deviation, section 1.2). A future version that restores the content review must fill this in.
- **D-R10** Budget: $150-450 expected for the combined S25+S26 run (D = 8 costs about $116-140 of
  that on its own, section 9), hard abort at $1,350 (3x the top of the range) via the runaway-cost
  circuit breaker in `tools/run_sweep_to_completion.py` (section 4, section 13). Pod-session
  sharing with PAPER-S26: left to whoever actually provisions the pod, since neither protocol's
  correctness depends on it (runbook section 14 item 5 already treats it as a scheduling choice).

**Still open, genuinely not decidable from a laptop without the pod (disclosed, not guessed):**
`<LOCK: S25 anchor-schedules sha256>` and `<LOCK: S25 smoke document sha256>` (section 10.1), the
harness commit SHA (section 4, filled at the actual commit that locks this file), and the
document manifest's review-queue provenance beyond hash rank (section 1.2's disclosed gap). None
of these block committing this protocol version's decisions; they block the confirmatory launch
itself, and the runbook's launch-script extractor (section 8.1) already refuses to proceed while
any of them is unfilled.

Then, in this order: prerequisites of section 13 committed (confirmed present in the working tree
2026-09-26, not yet committed); the eligibility, queue and author schedules recomputed at the pin
(1.5) once the pinned build is available; the schedule hash computed and the two remaining
`<LOCK: ...>` values filled; every locked command checked to parse at the harness pin (`--help` --
done 2026-09-26 for `run_respec_cascade_sweep.py`, `run_respec_cascade_baselines.py`,
`compute_respec_cascade_statistics.py`; `respec_rerun_verdict.py` does not exist yet and is a
blocking gap, P-R5 above); one commit locks this file together with
`manifests/s25-respec-documents-locked.json`.

## 15. Risks and confounds (disclosed)

- **Model and family changes.** Sonnet and six families, against haiku and five; the new result
  replicates nothing and is not pooled with the old one.
- **The lost run's effect may not recur.** Sonnet may lose markers less often than haiku did,
  and section 2.4 no longer freezes on a lost marker; power then falls toward the B rows of
  section 9.
- **Correlated author documents** (1.4), and a public pool of long, OMML-free documents: the
  author documents are the only ones with native equations, and the treatment tool was debugged
  on them (1.1).
- **Baselines run after the primary sweep** (section 3): host load and any server-side model
  drift between the sweeps are confounded with the drops, equally for both arms.
- **First-use code.** Six-family grading has only run on a synthetic one-cell table; the smoke
  phase is the first real test.
- **Fixed rotation and respec rule**, as in S23 section 8.
- **Usage limits** during six concurrent sessions: the circuit breaker stops the sweep, and a
  limit hit is never scored as a task failure in either arm.
