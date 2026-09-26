# PAPER-S26: preregistered replication of the K=4 section-reorder result on fresh documents (protocol v1)

Status: **LOCKED-PENDING-COMMIT (decided 2026-09-26).** Every `AUTHOR DECISION` placeholder below
is resolved by the FINAL DECISIONS of 2026-09-26 (this section and section 14). This document
still does not bind, and no confirmatory trial may run, until it is committed together with the
manifests it names (`manifests/s26-k4-documents-locked.json` and the other lock-time manifests)
-- the lock commit. After the lock, any change is a new protocol version with a dated reason
(section 11).

**Final decisions (2026-09-26, the author, delegated; not reopened by this revision):**
- **D-K1 (N = 60).** Section 9's power table gives N = 60 at 0.94 power for the observed effect
  size but only 0.48-0.56 at half the observed effect -- markedly below the N = 120 the original
  draft recommended for 0.80 power at half effect. Decided anyway to meet the Sunday 19:00
  deadline; the shortfall is disclosed here and repeated in section 9, and a NOT REPLICATED
  result at N = 60 is reported exactly as section 8 already requires (with the same prominence as
  a positive one), not reinterpreted as evidence of no effect.
- **D-K2 (seed = 20260925001, unchanged, not re-seeded).** The seed already recorded as
  `k4sr_candidates.json`'s own `proposed_seed` before this decision, so using it introduces no new
  outcome-dependent choice.
- **D-K6 (licence: dataset-level ODC-BY, per-file provenance unverified).** Same disclosure
  standard the currently published paper already uses for the existing section-reorder follow-up
  corpus (`main.tex`'s licensed-docops-corpus claim and its neighboring text); cited as precedent.
- **D-K7 (Meridian Docs pin = `89c93fac6a9ee7a03d98baab34ba7043de983018`; CLI `2.1.283`;
  subscription OAuth token).** Shared with S25 D-R4/D-R5; see that protocol's status block and
  section 4 for the verification of the pin (confirmed to exist and to contain the OMML-validator
  fix this run needs) and the CLI version resolution
  (`npm view @anthropic-ai/claude-code version`, 2026-09-26).
- **Selection method for the 60 documents (2026-09-26, disclosed deviation from the two-reviewer
  process drafted in section 1.2): hash rank alone**, from `k4sr_candidates.json`'s own
  `rank_under_proposed_seed` field, with no free-text content review and no near-duplicate check
  against the original 56-document K4 corpus beyond what the candidate pool's own touched-document
  exclusion already gives (section 1.1). Reason: no time before the deadline for a ~70-document
  content review (the follow-up's own promotion rate was 87%, so N = 60 promoted needs roughly 69
  reviewed). Produced deterministically by `tools/select_locked_documents.py k4`, with every
  document's SHA-256 verified against the actual file, not taken from the candidate manifest on
  faith. Disclosed as a limitation in section 12: no PII free-text screen beyond the pattern scan,
  and **no explicit 12-gram check against the original 56-document K4 corpus was run for this
  selection** (section 1.2 item 3's near-duplicate check is skipped along with the rest of the
  review). The pool is disjoint from the 90-document curated v1 corpus and the 48 v2 corpus by the
  touched-document exclusion (section 1.1, which counts every hex id/hash appearing anywhere under
  the data root or this repository, including v1's and v2's own filenames), which substantially
  reduces but does not by itself rule out a near-duplicate at the content level; this residual risk
  is accepted for v1 of this protocol and should be closed by a full review in any later version.

## 0. Why this exists

The paper's headline agentic-editing result is section reorder at K=4 on the 56-document
combined corpus: treatment 92.9% vs control 66.1%, p = 0.0015 (control 67.3% with the Note b
chain excluded, p = 0.0015). That comparison was **not preregistered**:

- `docs/paper-s7-protocol-v1.md` (locked at `1061e0e`) ran K=4 for bibliography only and named
  section reorder at K=4 as an explicit follow-up, not run in that pass (its section 5).
- `docs/paper-s7-section-reorder-followup-protocol-v1.md` preregistered a larger corpus at
  **K=1** only. The K=4 run on that corpus (2026-09-04) was added afterwards.
- The number then passed through post-hoc corrections, each disclosed: an evaluator whitespace
  fix (`2ccf4cb`), two resolver fixes (`8c7ae16`, `278d9cc`), excluding blocked chains
  (`b286c1b`), and the Note b rescoring of a timed-out control chain as a failure (`870e72d`,
  disclosed as post-hoc in `e1d4046`).

The paper currently calls it "the sole preregistered comparison this benchmark's design
specifies"; that sentence is wrong and is corrected separately from this protocol (D-K9). This
document preregisters a clean replication: the same prompts, grading and model, on documents
the harness has never touched, with every scoring rule, including timeouts, fixed before any
trial.

## 1. Corpus

### 1.1 Pool

`manifests/k4sr_candidates.json` (SHA-256 of the file
`4e33aaecff599ba088d857e180a0e3eba30acb70f7868d60dc108061cb80abe4`), built by
`python tools/build_rerun_candidates.py k4sr` (pipeline in `manifests/README.md`): **676
documents**, sorted by SHA-256. Funnel: all 6,433 downloaded docx-corpus documents (batches
500/2/3) -> 85 excluded as touched -> 6,348 fresh -> 1 unreadable -> 1,252 with >= 3 outline
headings -> 1,164 with a `resolve_section_reorder_plan` plan -> 772 clean under
`tools/pii_pattern_scan.py` -> 676 in the 3-25 heading band of the follow-up protocol. The same
scan reproduces the follow-up's 1,310 / 883 counts exactly. These counts were computed on the
unpinned build (b0d28a61) and are recomputed at the pin (section 1.3).

**Never touched by the harness.** A document is touched if any hex run of 12-64 characters in any
text file or file name under `D:\MeridianData\ooxml-graph-paper` or in this repository equals a
12-or-more-character prefix of its docx-corpus id or its file SHA-256 (18,379 files scanned;
`tools/rerun_pool_exclusion.py`, `manifests/touched_union.json`). This excludes all 48 follow-up
(v2) documents, the 36 S6 organic documents, all 90 documents of `raw/docx-corpus/files` and one
package-integrity failure. **Known gap** (D-K5): the follow-up's intermediate sample lists were
never saved, so up to 42 documents that its agents *read* during content review (but never ran
through the harness) may be in the pool. They are accepted as never touched by the harness, and
this is disclosed.

The pool is disjoint from the PAPER-S25 respec public pool (S25 section 1.2) by construction.

### 1.2 Seeded, outcome-blind selection

1. **Order (decided): seed = 20260925001, unchanged.** Ascending `sha256(f"{seed}:{doc_sha256}")`,
   no PRNG. This is `k4sr_candidates.json`'s own `proposed_seed`, recorded before this decision,
   so re-using it (rather than choosing a new one now, which could look outcome-motivated after
   the pool exists) is the more defensible choice. `k4sr_candidates.json` already carries
   `rank_under_proposed_seed` for every document under this exact seed; no separate review-queue
   file is regenerated by `select_rerun_documents.py` for this version (see item 2 below).
2. **Reviewers, review and near-duplicate check (as originally drafted; NOT run for this
   version, D-K10 superseded).** Kept here as the process a future protocol version should use if
   a full content review becomes possible before its own lock: two independent content reviews per
   document (`manifests/paper-s26-review-prompt-v1.md`,
   `manifests/paper-s26-review-checklist-v1.md`, never written for v1); promote only when both
   reviewers promote; skip a near-duplicate against an already-promoted document or the original
   K=4 corpus (11 v1 + 48 v2, listed in `manifests/paper-s26-k4sr-original-corpus-reference-v1.json`,
   **not created for v1** -- this file remains a genuine gap, disclosed in section 12, since
   building it needs the original run's own document list, which this pass did not reconstruct);
   log every verdict to `manifests/paper-s26-k4sr-review-log-v1.json`. **v1 instead takes the top N
   documents by hash rank alone** (see the status block and section 12); this subsection is not
   executed for v1.
3. (superseded by 2, above; kept for a future version.)
4. **Stop** at exactly **N = 60 promoted documents** (D-K1, decided; section 9).
5. **Pre-trial check** on the pod with the pinned build (locked command `s26-check`,
   section 3): SHA-256 matches and `resolve_section_reorder_plan` returns `found=True` for every
   document. A failing document is replaced by the next promotable one in order (rank 61, then 62,
   etc., per `manifests/k4sr_candidates.json`'s `rank_under_proposed_seed`), **only before the
   first confirmatory trial**, as a dated amendment v1.1 committed before any trial. After that
   nothing is replaced; a failure is reported as `not_applicable`.
6. **Manifest: locked 2026-09-26.** `manifests/s26-k4-documents-locked.json` (SHA-256
   `bc611e046cf5ca9b5990062b054c00f5725f784d716d4554510d5c9125c56787`, 60 documents), produced by
   `python tools/select_locked_documents.py k4` and verified against every file's actual SHA-256
   at generation time. Its pod-path form (`manifests/paper-s26-k4sr-replication-manifest-v1.json`,
   `{"documents": [{doc_label, docx_path, sha256, s7_split: "primary_holdout"}]}`, with
   `doc_label = "s26k4_<sha256[:16]>"` and paths `/workspace/ooxml-graph-paper/corpus/<doc_label>.docx`)
   is derived from it at provisioning time; **a launch must confirm the locked manifest's SHA-256
   equals the value above before deriving the pod manifest** (runbook section 3.3). All 60
   documents are confirmatory; there is no validation slice, because the harness is not being
   debugged on this corpus. Confirmed disjoint from `manifests/s25-respec-documents-locked.json`
   by direct SHA-256 set comparison at generation time (no overlap).

Per-file licence: dataset-level ODC-BY, per-file provenance unverified (D-K6, decided; see the
status block for the precedent cited). The paper reports documents by hash and aggregate outcomes
only; no document text or edited copy is released.

### 1.3 Recomputed at the pin

The structural scan, plan resolution and eligibility were computed with the unpinned editable
install (b0d28a61). Once the pin is decided and before any review verdict:
`pixi run python tools/scan_fresh_docx_pool.py` and `python tools/build_rerun_candidates.py k4sr`
with the pinned build installed, then the order of 1.2 item 1; the review walks the pinned
order. Differences from the committed b0d28a61 manifests are recorded in the lock commit. The
original corpus's 11 v1 + 45 v2 plans are also re-resolved at the pin and compared with the
plans the 2026-09-04 run used; any difference is reported, because it bears on how comparable
the replication is.

## 2. Task and harness (identical to the original K=4 run, except as listed)

Family `section_reorder`, `k_pairs = 4`, both arms, one chain per (document, arm). A chain is
four consecutive forward+inverse pairs (8 trials); each trial is a fresh `claude -p` process;
pair i+1 starts from pair i's inverse output. The plan (section to move and its destination) is
resolved once per document from the pristine file and reused for all four cycles and both arms.

| Code path (harness pin) | Role | Compared with `278d9cc` (2026-09-04, the resolver fix the corrected K=4 numbers rest on) |
|---|---|---|
| `docx_trial_broker.generate_section_reorder_pair` | prompts, forward and inverse | identical |
| `docx_anchor_prober.resolve_section_reorder_plan` | plan | identical |
| `docx_trial_evaluator.grade_forward_trial_reorder`, `grade_inverse_trial_reorder`, `_package_is_valid_docx` | grading | identical |
| `run_paper_s7_benchmark._safe_grade`, `_load_checkpoint` (function body) | grader guard, resume | identical; the trusted-status set it reads changed (difference 8) |
| `run_paper_s7_benchmark._grade_forward`, `_grade_inverse`, `_build_pair_specs`, `probe_family_applicability` | dispatch | changed only by added `table_structural` branches and an optional anchor override (default None); the `section_reorder` branches are identical |
| `run_paper_s7_benchmark.run_chain`, `run_corpus_slice` | chain, sweep | changed: differences 8-11 |
| `claude_pair_runner.run_trial`, `_build_command` | process | changed: differences 3, 5, 8, 9 |
| `claude_pair_runner._treatment_allowed_tools`, `_meridian_docs_mcp_config`, `audit_isolation` | tool grant, isolation | identical: treatment `Read` + `move_section`, control `Read`, `Write`, `Edit`, `Bash` |
| `compute_s7_statistics._chain_outcome`, `compute_statistics` | primary outcome | changed: the `blocked_*` statuses and `--blocked-policy`; the default policy reproduces every stored source byte-identically |

"Identical" was checked by comparing function source segments (AST) at `278d9cc` with the
working tree on 2026-09-25; P-K5 makes this a test at the harness pin, including a branch-level
comparison of the `section_reorder` branches of the dispatch functions.

Differences from the original run, disclosed:

1. Per-trial timeout **900 s** (original: 300 s; raised to 600 s in `be19deb`, 900 s in `7954983`).
2. A trial killed by the timeout whose output file changed and passes grading counts as
   completed (`09f1159`), in both arms.
3. A treatment trial whose MCP server never loaded is retried once (`ff3efc4`); since
   2026-09-25 the retry fires only on the CLI's own init record (server not connected and the
   tool not listed), never on the agent's wording, and the retry gets a fresh trial directory
   (the first attempt moves to `attic/`). It is an infrastructure retry that only the treatment
   arm can need, and it is counted and reported.
4. Long `doc_label` truncation fix (`435abb5`); no effect for the labels in 1.2.
5. Model id pinned in full (`claude-sonnet-5`; the original used the `sonnet` alias, which then
   resolved to `claude-sonnet-5`); CLI version pinned (the original's was not recorded); the
   CLI now runs with `--verbose`, so its init record is captured (`claude_json_result` keeps
   its meaning).
6. Meridian Docs pinned by commit (the original ran an unpinned editable install, so its exact
   `move_section` build is unknown).
7. Linux RunPod host, 6 workers on 8 vCPU, Word-COM receipts off (the original ran locally on
   Windows; receipts never entered grading).
8. A chain that stops early records why (`blocked_timeout`, `blocked_forward_failed`,
   `blocked_unreadable_input`, `blocked_inverse_unresolvable`), and these are trusted on resume
   (the original re-ran every `blocked` chain on relaunch). A trial with an infrastructure
   signature makes the chain `infra_blocked`; attempts are counted in a ledger outside the chain
   root; an untrusted chain root moves to `attic/` before a rerun.
9. The CLI session transcript is copied next to each trial (`session-transcript.jsonl`), and
   Meridian render-gate errors are extracted from it. Recorded only; no scoring effect.
10. A sweep-wide circuit breaker stops dispatch at the first global infrastructure signature
    (exit code 3).
11. Both arms of each document are submitted back to back in manifest order, as in the
    original, but the order within the pair is fixed by `--arm-order-seed` (the original always
    submitted control first).

## 3. Model, pins, environment and locked commands

- **Model** `claude-sonnet-5` via the `claude` CLI, `--model claude-sonnet-5`, both arms.
- **CLI** `@anthropic-ai/claude-code@2.1.283` (D-K7, decided 2026-09-26, shared with S25 D-R5,
  resolved via `npm view @anthropic-ai/claude-code version`); authentication: subscription OAuth
  token (D-K7, decided, shared with S25 D-R5), as PAPER-S25 section 4.
- **Meridian Docs** commit `89c93fac6a9ee7a03d98baab34ba7043de983018` (D-K7, decided, shared with
  S25 D-R4; verified 2026-09-26 to exist and to contain the OMML-validator fix -- see PAPER-S25
  section 4 for the verification detail).
- **Harness** `ooxml-graph-paper` commit **to be filled at the actual lock commit** (not yet made;
  see PAPER-S25 section 4 for why), containing section 13's prerequisites (confirmed present in
  the working tree 2026-09-26; `tools/k4_replication_verdict.py`, P-K6, is still **not present**
  and remains a blocking prerequisite -- the `s26-statistics` locked command will not parse until
  it exists), exported with `git archive` (`tools/`, `manifests/`, this protocol).
- **Environment, provenance, dependency constraints, archive, secret handling**: as PAPER-S25
  section 4 and `docs/runpod-rerun-runbook-draft.md`. Pod layout as PAPER-S25 section 10.1,
  with the run root `/workspace/ooxml-graph-paper/runs/rr-k4-v1`.

The commands are copied into the runbook byte for byte; the runbook launches them by
extracting these blocks from this file.

```bash
# locked-command: s26-check
cd /workspace/ooxml-graph-paper/tools
/home/bench/venv/bin/python run_paper_s7_benchmark.py --check-only \
  --corpus-manifest /workspace/ooxml-graph-paper/manifests/paper-s26-k4sr-replication-manifest-v1.json \
  --split primary_holdout --families section_reorder \
  --run-root /workspace/ooxml-graph-paper/runs/rr-k4-v1
```

```bash
# locked-command: s26-run
cd /workspace/ooxml-graph-paper/tools
/home/bench/venv/bin/python run_paper_s7_benchmark.py \
  --corpus-manifest /workspace/ooxml-graph-paper/manifests/paper-s26-k4sr-replication-manifest-v1.json \
  --split primary_holdout --families section_reorder --k-values 4 \
  --model claude-sonnet-5 --max-workers 6 --no-word-receipts \
  --arm-order-seed 20260925005 --max-chain-attempts 2 \
  --run-root /workspace/ooxml-graph-paper/runs/rr-k4-v1 \
  --provenance-json /workspace/ooxml-graph-paper/logs/provenance-rr-k4-v1.json
```

```bash
# locked-command: s26-statistics
cd /workspace/ooxml-graph-paper/tools
/home/bench/venv/bin/python compute_s7_statistics.py \
  /workspace/ooxml-graph-paper/runs/rr-k4-v1/slice-manifest.json \
  --blocked-policy fail \
  --out /workspace/ooxml-graph-paper/runs/rr-k4-v1/statistics/k4-replication-v1-statistics-fail.json
/home/bench/venv/bin/python compute_s7_statistics.py \
  /workspace/ooxml-graph-paper/runs/rr-k4-v1/slice-manifest.json \
  --blocked-policy exclude \
  --out /workspace/ooxml-graph-paper/runs/rr-k4-v1/statistics/k4-replication-v1-statistics-exclude.json
/home/bench/venv/bin/python k4_replication_verdict.py \
  --statistics /workspace/ooxml-graph-paper/runs/rr-k4-v1/statistics/k4-replication-v1-statistics-fail.json \
  --statistics-timeouts-excluded /workspace/ooxml-graph-paper/runs/rr-k4-v1/statistics/k4-replication-v1-statistics-exclude.json \
  --out /workspace/ooxml-graph-paper/runs/rr-k4-v1/statistics/k4-replication-v1-verdict.json
```

Exit codes of the run: 0 finished; 2 `--check-only` failed; 3 circuit breaker open. The
statistics are computed on the pod and again locally from the downloaded archive; the match
rule is PAPER-S25 section 6.9's (p-values, point estimates, counts and verdicts identical;
bootstrap CI bounds may differ in the last digit between Python versions, disclosed).

## 4. Outcomes

- **Primary: whole-chain pass.** 1 if every one of the 4 pairs passes both forward and inverse
  grading (`compute_s7_statistics._chain_outcome`), else 0, with section 5's rules for chains
  that did not finish. One value per (document, arm).
- **Secondary (exploratory, no verdict weight):** pass rate over pairs 1-3 (`steady_state`); the
  cycle at which each failing chain first fails, and which check failed (the mechanism the paper
  describes: control failures first appearing on cycle 2 or later, treatment failures on cycle
  1); per-trial wall time, tokens and cost by arm; counts of timeouts, recoveries (difference 2)
  and MCP retries (difference 3) by arm.

## 5. Scoring and exclusions (fixed now; the Note b question is decided here)

Every chain status is scored identically for both arms:

| Status | Recorded evidence | Score (primary, `--blocked-policy fail`) |
|---|---|---|
| `completed` | every pair graded pass | 1 |
| `completed_with_failure` | some pair failed grading, or an inverse did not complete | 0 |
| **`blocked_timeout`** | a forward trial reached 900 s, no infrastructure signature, output not recovered under difference 2 | **0 (failure)**; trusted on resume, never re-run |
| `blocked_forward_failed` | a forward process exited non-zero with a JSON result and no signature | 0; trusted, never re-run |
| `blocked_unreadable_input` | the prior pair's inverse output is unreadable | 0; trusted, never re-run |
| `blocked_inverse_unresolvable` | the forward output has no resolvable target | 0; trusted, never re-run |
| **`infra_blocked`** | **any** trial of the chain has an infrastructure signature (PAPER-S25 section 5.6: CLI API-error result, CLI stderr on an unclean exit, non-zero exit with no JSON and no timeout, foreign signal or NTSTATUS crash, MCP load failure in the init record), whatever that trial's own outcome | not scored; untrusted; chain root moved to `attic/` and the chain re-run from pair 0 |
| `aborted_circuit_open` | stopped by the circuit breaker after a global signature | not scored; relaunched after the event clears; not charged |
| `infra_excluded` | two chargeable attempts (`--max-chain-attempts 2`: the original and one rerun) ended `infra_blocked` (chain scope) or `harness_exception` | excluded; that document drops out of the paired analysis and is listed |
| `harness_exception` | the harness raised | not scored; re-run; charged |
| Grader exception | a `_safe_grade` stub: verdict `fail` with a reason starting `grading raised` | re-graded (below) |
| `not_applicable` | resolver found no plan | excluded; only possible if the pre-trial check was skipped |

**Why a timeout is a failure.** The task is defined with a fixed per-trial budget, the same for
both arms. An agent that has not finished in 900 s has not done the task: that is three times
the budget of the original run, and above the longest completed trial of any family recorded
before 2026-09-18 (575 s; 99th percentile of the slowest, render-gated families 392 s).
Timeouts are never re-run, including on resume: re-running only the unfinished chains would give
one arm extra attempts selected on outcome. Infrastructure failures are the only reruns, and
they are identified by recorded evidence the agent cannot produce, not by judgment. In the
original run, the Note b chain was excluded by the harness default and later rescored as a
failure after the results were known. Here the rule is fixed first, and the other scoring is
reported beside it (section 6.3).

**Grader exceptions and post-lock grading.** Only grader-exception stubs may be re-graded after
the lock and still feed section 7: the grader is fixed by a committed, tested change applied to
every stub of both arms, re-grading from the archived outputs. A stub that cannot be re-graded
is scored under the adverse bound (treatment chain 0, control chain 1) and under the favourable
bound; if the verdicts differ, the verdict is NOT REPLICATED, flagged. Any other grader
correction after the lock is a sensitivity analysis only and never changes the section 7
verdict (section 11).

A host that makes both arms slow would bias the timeout rule against control, whose trials take
about four times longer. Two safeguards: the pod is dedicated, with fixed `--max-workers 6`; and
timeouts in more than 5% of all trials, pooled across arms, halt the run as an environment
defect with a fixed remedy (section 10.4).

## 6. Test

### 6.1 Primary test

`graph_scorer.paired_permutation_test_exact` on the per-document (control, treatment) primary
outcomes over documents with an outcome in both arms. For 0/1 outcomes this is the exact
two-sided sign test on the discordant documents (exact McNemar). **Two-sided, alpha = 0.05.**
The p-value is an exact enumeration, so it needs no seed; the result's `exact` flag must be true.

### 6.2 Why two-sided

The original K=4 test, the paper's other tests and the PAPER-S25 tests are two-sided, so the
replication's p is comparable with the result it replicates, and a two-sided test can register a
reversal. A one-sided test is not chosen because the team that built the tool under test is
choosing the test, and the planned N gives adequate power two-sided (section 9). The author may
switch to one-sided before the lock (D-K3), never after; if so, section 7 (REVERSED becomes
descriptive only) and section 9 are rewritten in the same lock commit.

### 6.3 Estimates and sensitivity analyses (exploratory; no verdict weight except as stated)

- Each arm's pass rate with its 95% bootstrap CI (`bootstrap_ci`, 2000 resamples, seed
  `20260828`), and the paired difference with a 95% bootstrap CI over documents.
- Blocked chains excluded pairwise (`--blocked-policy exclude`), the harness default when the
  original ran. It sets the timeout-scoring label of section 7.
- The as-run Monte Carlo `paired_permutation_test`, for continuity with the published p.
- Grader-exception bounds and any post-lock grader correction (section 5).
- The original 56 documents and this replication combined, with the pooling disclosed (see
  section 8 for how it may be used).

## 7. Decision rule

Let `diff = treatment rate - control rate` over the paired documents and `p` the primary test's
p-value.

- **REPLICATED** if `diff > 0` and `p < 0.05`.
- **REVERSED** if `diff < 0` and `p < 0.05`.
- **NOT REPLICATED** otherwise (reported with `diff`, its CI and `p`).

A REPLICATED verdict is labelled **robust to timeout scoring** if the blocked-chains-excluded
analysis (6.3) also gives `diff > 0` and `p < 0.05`, and **dependent on timeout scoring**
otherwise. The label is part of the verdict and is reported with it. The verdict script
(`tools/k4_replication_verdict.py`, P-K6) applies this rule mechanically.

## 8. Claims (binding on the paper)

- The only confirmatory claim is the section 7 verdict with its label, `diff`, its CI and `p`.
  Only it may be described as "replicated", "confirmed" or "preregistered result".
- Steady-state rates, the per-cycle mechanism, cost and timing, every sensitivity analysis and
  the pooled original+replication analysis are exploratory; their p-values are printed as
  "(unadjusted, exploratory)".
- **The pooled original+replication analysis never appears in the abstract and never supports
  the word "replicated"**; the confirmatory claim rests on the replication alone.
- A NOT REPLICATED or REVERSED result is reported in the abstract with the same prominence the
  original result has, and the paper then describes the original K=4 result as a single
  unpreregistered finding that did not replicate.

## 9. N and power

**N = 60 (D-K1, decided 2026-09-26, final -- not reopened here).** Exact power of the section 6.1
test (two-sided, alpha 0.05, effect in the predicted direction), from enumerating the trinomial
of discordant counts:

| Effect model | N=40 | N=60 | N=80 | N=100 | N=120 |
|---|---|---|---|---|---|
| Observed joint 34/18/3/1 (92.9% vs 66.1%) | 0.78 | 0.94 | 0.98 | >0.99 | >0.99 |
| Alternative joint 35/17/2/2 | 0.84 | 0.97 | 0.99 | >0.99 | >0.99 |
| Half effect, 92.9% vs 79.5% (control-only pass 3/56) | 0.29 | 0.48 | 0.63 | 0.74 | 0.83 |
| Half effect, discordant 0.16 / 0.03 | 0.33 | 0.56 | 0.73 | 0.84 | 0.91 |

The joint was reconstructed from the stored Monte Carlo p = 0.0015. Replications usually find
smaller effects than the original; N = 120 would be the smallest size with at least 0.80 power at
half the observed effect under both half-effect models. **N = 60 is powered at 0.94-0.97 if the
effect holds near its published size, but only 0.48-0.56 at half the observed effect** -- the
author has accepted this shortfall explicitly to meet the Sunday 19:00 deadline, and it is
disclosed here and in the status block: a NOT REPLICATED result at N = 60 does not distinguish a
genuinely weaker or absent effect from an underpowered test for a real half-size effect, and the
paper must say so wherever this replication's result is cited, per section 8's reporting rule
(same prominence, no reinterpretation). At N = 60, reviewing about 69 documents would be expected
at the follow-up's 87% promotion rate -- **not run for this version** (see the status block: v1
selects by hash rank alone, so no review or promotion-rate reasoning actually applies to how the
60 were chosen; the 87% figure is kept here only to show what a from-scratch review at N = 60
would have cost in reviewer time, for a future version).

Cost (runbook section 13; control $0.35 / 85 s, treatment $0.24 / 19 s per trial): N = 60 is
60 x 16 = 960 trials, about **$293 API-equivalent** base including smoke, about **$351** with
the +20% rerun allowance; about 2.9 h of sweep, 8.1 h pod budget on its own (these are the
runbook's own already-tabulated N = 60 figures, section 13). For reference, N = 120 (no longer
describing this run) was about $576/$691, 5.8 h sweep, 12.4 h pod budget.

## 10. Execution

### 10.1 Smoke (never confirmatory; after the lock)

One K=4 chain per arm on one or two **non-fresh** practice documents from the original S7 v1
`validation` split, each with 12-gram overlap below 50% in both directions with every
confirmatory document (`tools/docx_ngram_overlap.py`); their SHA-256 values are recorded in the
lock commit. No pool document is used. Gates and the rule for code changes after the smoke phase
are PAPER-S25 section 10.2's: only a listed gate failure may be fixed, logged in
`logs/deviations.md`, with a new pin, an amendment committed before any confirmatory trial, and
a new smoke phase.

### 10.2 Pre-trial check

`s26-check` (section 3) must exit 0 on the pod before the first confirmatory trial; it writes
`check-report.json` and its SHA-256 into the run root. Results recorded.

### 10.3 Run once; order; monitoring

- The N documents run once. No document is added, removed or replaced after the first
  confirmatory trial, and there is no interim analysis. Running a smaller N first and adding
  documents if it misses significance is optional stopping and is not done.
- Both arms of each document are submitted back to back, in manifest order, the order within the
  pair fixed by `--arm-order-seed 20260925005`.
- Monitoring (runbook section 10) counts finished chains, the `infra_blocked` /
  `infra_excluded` / `aborted_circuit_open` / `harness_exception` statuses, the attempt ledger,
  timeouts pooled across arms, and spend. Pass/fail by arm is not computed until the sweep ends.

### 10.4 Pauses, halts and their fixed remedies

| Trigger | Kind | Remedy (fixed now) |
|---|---|---|
| Circuit breaker open (exit code 3) | pause | Wait until the limit or outage clears; relaunch the identical locked command in the same run root; stopped chains are not charged; logged. |
| Pod loss or interrupted sweep | pause | Runbook section 9; relaunch the identical command in the same run root; interrupted attempts are not charged. |
| Spend above 1.3x plan for the progress reached | pause | The author approves a higher budget (logged) and relaunches identically, or abandons: NOT EVALUATED. |
| Timeouts above 5% of trials, pooled across arms (after >= 100 trials) | halt | Environment defect. The run is NOT EVALUATED. A new run (amendment v1.x, new run root, same documents and pins, 900 s budget unchanged, `--max-workers 3`) starts from scratch. |
| Chain-scope `infra_blocked`, `infra_excluded` or `harness_exception` above 5% of chains | halt | As the next row. |
| Isolation violation, or a harness defect found during the run | halt | NOT EVALUATED. Fix and disclose; new pin, new protocol version, new run root; every chain of both arms re-run. |

A halted run's data are kept, archived and reported descriptively (section 11).

### 10.5 Archive before teardown

As PAPER-S25 section 10.7: every chain root with every trial's output `.docx` and
`session-transcript.jsonl`, `_chain_attempts/`, `attic/`, `check-report.json`, the manifests,
statistics, logs, provenance and deviations in one verified archive; the pre-download secret
scan clean; statistics recomputed locally and matching; a second verified copy; registered in
`paper/sources/` before any pod or volume is deleted.

## 11. Verdict of record, versions and halted runs (binding)

1. **The first computed verdict is final.** The first time `k4_replication_verdict.py` runs on
   the complete data of this protocol version, its output is the verdict of record for this
   version, always reported as the preregistered result, whatever happens afterwards.
2. **Later corrections or reruns are new, separately labelled analyses** reported alongside the
   verdict of record, never in its place. A rerun is a new protocol version with its own lock,
   run root and verdict of record. A v1 that comes out NOT REPLICATED stays in the paper as
   NOT REPLICATED whatever a later version shows.
3. **One registry table** in the paper, shared with PAPER-S25 section 11: every version and run
   of this line of work (the original unpreregistered K=4 result, S23, S25, S26 and any later
   version) with protocol and lock commit, model, run dates, data status, verdict of record and
   every later labelled analysis.
4. **Halted runs.** A run that is halted and not resumed is **NOT EVALUATED**: no test is run on
   its data, which are reported descriptively only. The remedy for each halt reason is the one
   fixed in section 10.4.
5. **Accidental early looks** at arm-level outcomes are logged in `deviations.md` and disclosed
   next to the verdict.

## 12. Reporting (whatever the outcome)

The verdict and its label; both arms' rates and CIs; the paired difference and CI; the exact p;
every section 6.3 analysis; every exclusion, `infra_blocked`, `infra_excluded`, timeout,
recovery, MCP retry and deviation by arm; the per-cycle mechanism breakdown; N reviewed,
promoted, rejected (with reasons) and replaced before trials; the registry table of section 11.

## 13. Code prerequisites (committed and tested before the lock)

**Done 2026-09-25 (working tree, uncommitted; committed before the lock):** the `blocked_*`
statuses trusted on resume; `infra_blocked` on any trial with an infrastructure signature
(`claude_pair_runner.classify_infra_signature`, pinned patterns and tests); the circuit breaker
(exit 3), attempt ledger, `--max-chain-attempts` and attic moves; `--blocked-policy
fail|exclude` (alias `--timeout-policy`) in `compute_s7_statistics`, default `exclude` so every
stored source regenerates byte-identically; `--check-only` with `check-report.json`;
`--arm-order-seed`; transcript copy and render-gate capture; the pool and selection tools
(`manifests/README.md`, `tools/select_rerun_documents.py`, `tools/docx_ngram_overlap.py`).

**Still required:**

- **P-K1** `compute_s7_statistics.py`: an exact test field
  (`paired_control_vs_treatment_significance_exact`, via `paired_permutation_test_exact`);
  grader-exception stubs detected by the `grading raised` reason prefix and listed; tests for
  every section 5 row.
- **P-K3** `--provenance-json` for `run_paper_s7_benchmark.py` (runbook P5).
- **P-K4** The manifest builder (review log to `paper-s26-k4sr-replication-manifest-v1.json`)
  and the near-duplicate check against promoted and original-corpus documents, committed with
  the review log and the reference list of 1.2 item 3.
- **P-K5** The function-identity check of section 2 as a test pinned to `278d9cc`, including
  the branch-level comparison.
- **P-K6** `tools/k4_replication_verdict.py`: applies section 7 and its label mechanically from
  the two statistics files, with tests for each branch.

## 14. Lock checklist: decisions the author must make first

**D-K1/D-K2/D-K6/D-K7 below are FINAL DECISIONS, decided by the author (delegated) on
2026-09-26 and not reopened by this or any later revision without a new dated decision.** Each is
also stated in full, with its one-line reason, in the status block at the top of this document.

- **D-K1 (decided): N = 60.** See the status block and section 9 for the power tradeoff accepted
  to meet the Sunday 19:00 deadline.
- **D-K2 (decided): seed = 20260925001, unchanged.** Already recorded as the pool's
  `proposed_seed` before this decision.
- **D-K3** Two-sided (this draft) -- kept; not reopened.
- **D-K4** The timeout rule of section 5 (timeout = failure, no reruns, 900 s) and the
  "robust / dependent" label of section 7 -- kept as already fixed in this draft.
- **D-K5** Accepted, as drafted: up to 42 documents read (not run) during the follow-up's review
  may be in the pool; not reconstructed.
- **D-K6 (decided): dataset-level ODC-BY, per-file provenance unverified, precedent cited from
  the published paper's existing licensed-docops-corpus disclosure.** See the status block.
- **D-K7 (decided): Meridian Docs `89c93fac6a9ee7a03d98baab34ba7043de983018`; CLI `2.1.283`;
  subscription OAuth token** (shared with PAPER-S25 D-R4/D-R5). See section 3 and the status
  block.
- **D-K8 (superseded).** The originally planned ~140-document content review is not run for this
  version (status block, section 1.2 item 2); pod-session sharing with PAPER-S25 is left as a
  scheduling choice for whoever provisions the pod.
- **D-K9** Correct the paper's "sole preregistered comparison" sentence now, independently of
  this run -- still open, not addressed by this protocol lock (it is a change to the paper's prose
  elsewhere, not to this protocol or its manifests).
- **D-K10 (superseded by the hash-rank selection, section 1.2): no reviewer names are needed for
  this version**, since the two-reviewer content review is not run for v1. A future version that
  restores the content review must fill this in.

**Still open, genuinely not decidable from a laptop without the pod (disclosed, not guessed):**
the harness commit SHA (section 3, filled at the actual commit that locks this file), and
`manifests/paper-s26-k4sr-original-corpus-reference-v1.json` (section 1.2 item 3, not created --
building it needs the original K4 run's own document list, which was not reconstructed in this
pass). Neither blocks committing this protocol version's decisions; the harness SHA blocks the
confirmatory launch itself.

Then, in this order: prerequisites of section 13 committed (confirmed present in the working tree
2026-09-26, not yet committed); the scan and pool recomputed at the pin (1.3) once the pinned
build is available; every locked command checked to parse at the harness pin (`--help` -- done
2026-09-26 for `run_paper_s7_benchmark.py`, `compute_s7_statistics.py`; `k4_replication_verdict.py`
does not exist yet and is a blocking gap, P-K6 above); one commit locks this file together with
`manifests/s26-k4-documents-locked.json`.

## 15. Risks (disclosed)

- **Different population.** The pool is scraped real-world documents in a 3-25 heading band, like
  the follow-up's v2 corpus but unlike the curated v1 DocOps documents; the replication speaks
  for this population.
- **Build drift.** The original `move_section` build is unknown; a changed tool could move the
  treatment rate either way.
- **Timeout rule.** A slow host favours treatment under section 5; the pooled timeout halt and
  the timeouts-excluded analysis are the guards.
- **Unknown model drift** in `claude-sonnet-5` between 2026-09-04 and the run date.
- **Usage limits.** The circuit breaker stops the sweep at the first global signature; a limit
  hit is never scored as a task failure in either arm.
