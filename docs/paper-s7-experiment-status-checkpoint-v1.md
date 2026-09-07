# PAPER-S7/S8/S9: experiment status checkpoint (v1, 2026-09-06)

Status: a living checkpoint, not a results document. Written specifically so that after a
session interruption (this host has crashed or had the Claude Code process die several times
during this sprint), the exact state of every experiment can be recovered from this one file
without re-deriving anything from raw run directories. Update this file whenever a family's
status changes; do not let it go stale the way other docs in this project have.

## Complete (confirmatory scale, real, independently re-verified)

| Family | K=1 | K=4 | Notes |
|---|---|---|---|
| Bibliography | 100% / 100% (N=26/26) | 100% / 100% (N=26/26) | Defect 11 (MCP-loading flake) fixed 2026-09-06; harness now auto-retries this signature. |
| Citation | 100% / 100% (N=26/25*) | 100% / 100% (N=25*/25*) | Defect 10 (stale pre-fix statistics) fixed 2026-09-06. *1 chain per depth correctly excluded as a genuine 300s infra timeout ("blocked"), not scored as a failure. |
| Section_reorder | 83.6% / 92.9% (N=55/56), **p=0.27, not significant** | 67.3% / 92.9% (N=55/56), **p=0.0015, significant** | The one confirmed, significant directional finding in this project. Combined v1+v2 corpora. Mechanism (compounding drift from repeated cycling) is a real 9-of-12 majority pattern, not exceptionless -- see paper-s8 section 2.4. |

Timing (K=1, v1 corpus only, not formally powered -- paper-s8 section 2.7): treatment is
substantially faster for bibliography (46s vs 150s mean) and section_reorder (39s vs 175s
mean); a smaller, more variable gap for citation (117s vs 128s mean).

## Incomplete -- real, open work

| Family | Control | Treatment | Blocker |
|---|---|---|---|
| Equation | 10/11 resolved (1 genuine task failure), first real confirmatory-shaped attempt run 2026-09-06 on the 12-doc development slice only | **0/11 resolved, all blocked** | Render-verification gate's `chain_start` check times out. No confirmatory-scale (26-doc holdout+validation) run has EVER been attempted for this family, control or treatment. |
| Table_structural | 24/26 (92.3%) pass, full confirmatory scale, both directions | **1/26 resolved**, unchanged after a full re-run under materially better host conditions (13.7GB free vs 6.7GB) with the corrected `--model sonnet` (an earlier attempt accidentally used the harness's `haiku` default -- see below) | Same render-gate mechanism as equation. |
| Caption | **Zero run directories exist anywhere.** | **Zero run directories exist anywhere.** | Never attempted at confirmatory scale at all -- confirmed by direct filesystem search 2026-09-06, not just "excluded" in prose. |

**The diagnosis, refined 2026-09-06**: this is NOT simply "the shared host is busy." The
render-gate `chain_start` check (on the untouched pristine input, before any Meridian tool
call) fails almost exclusively for treatment, never for control, on the identical document.
`tools/run_paper_s7_benchmark.py` submits jobs as `(doc, control), (doc, treatment)` pairs;
under `--max-workers 1` this means treatment's first Word-COM automation call always runs
immediately after control's own 3 just-completed automations (chain_start + forward +
inverse) for the same document. Reproduced identically for both equation and table_structural,
at the same time, on the same host, under two very different memory conditions -- a specific,
testable sequencing effect, not diffuse contention.

**In progress right now (2026-09-06, this checkpoint)**: testing this hypothesis directly and
cheaply -- re-running ONE currently-blocked treatment chain each for table_structural and
equation in complete isolation (no preceding control chain in the same process), via
`run_chain` called directly rather than through the full harness's job queue. Script:
`test_sequencing_hypothesis.py` in this session's scratchpad
(`C:\Users\13144\AppData\Local\Temp\claude\...\scratchpad\`), run root
`E:\MeridianData\ooxml-graph-paper\runs\paper-s7-sequencing-isolation-test\`. **If this
completed successfully after this checkpoint was written and you are reading this fresh,
check that run root's `chain-result.json` files for `"status"` before assuming anything about
the outcome -- do not guess.**

- If isolation lets treatment succeed where the full-batch run blocked it: this CONFIRMS the
  sequencing hypothesis. Next step: modify `run_paper_s7_benchmark.py`'s job submission
  (either interleave a cooldown between a document's control and treatment chains, or process
  all of one arm before starting the other, whichever is cheaper to implement) and re-run
  equation + table_structural + caption at confirmatory scale for real.
- If it still blocks even in isolation: the sequencing hypothesis is REFUTED for at least this
  document; look instead at whether Word itself has degraded (orphaned processes, DCOM
  exhaustion) from the cumulative automation load of this whole multi-hour sprint, independent
  of immediate sequencing -- a machine restart before the next attempt would be the cheapest
  way to rule this in or out.

## Known, real bugs fixed this sprint (defects 1-11, full detail in paper-s8 section 0)

1-8: bibliography heading cleanup, citation stale-anchor-id, section_reorder whitespace
grading, section_reorder heading-level defect, bibliography alphabetization, PII scanner
false-negative, section_reorder blank-heading-text + blocked-chain statistics bug, citation
multi-field removal corruption. 9: equation grading-crash hardening (previously undisclosed in
the defect list despite being documented in section 2.5). 10: citation's statistics never
regenerated after defect 7's fix. 11: bibliography's one-off MCP-server-loading flake, now
auto-retried by `claude_pair_runner.run_trial`.

## Ablations / side investigations, status

- **Hard-fixtures stress test** (3 hand-authored adversarial fixtures): 2 of 3 produced real,
  reported findings (destination-heading-level defect via duplicate section headings;
  bibliography alphabetization gap). **Fixture 1 (duplicate anchor text) was never actually
  run** -- confirmed twice now by direct filesystem search, zero raw data exists. An
  unsupported narrative claiming it WAS run and inconclusive due to render-gate contention was
  found and removed 2026-09-06 (that mechanism was also impossible for citation specifically,
  which never touches Word-COM).
- **PAPER-S9 formatting-compliance pilot**: complete for its own explicitly exploratory scope
  (4 fixtures, 9 real trials, not meant to scale to confirmatory here). Found and fixed a real
  `audit_equation_style` bug (bookmark-before-equation silently skipped) along the way.
- **PAPER-S6 organic equation corpus**: cleared-document gate exceeded (35 cleared / 24
  needed). Topic-diversity gate only 6/8 (one pool exhausted at zero hits, one at near-zero
  after 800 samples) -- not blocking, but not closed either.
- **Pre-publication accuracy audit** (2026-09-06): 361 claims extracted from 7 docs +
  the Structural Ledger, independently re-derived from raw data. 53 mismatches found; 46
  corrected across 6 commits this sprint. The remaining 7 are either the frozen
  `paper-s7-protocol-v1.md` preregistration doc (expected to diverge from later results by
  design -- not a bug to fix) or minor phrasing precision not worth further churn.

## Where the live public summary stands

Structural Ledger artifact: `https://claude.ai/code/artifact/7af4510a-ea1e-4049-bb03-6abba2ac5cfe`
-- republished through this checkpoint with every correction above. 18 real defects disclosed
in its fixgrid.

## If you are picking this up cold after a crash

1. Read this file first, in full, before touching anything.
2. Check `git log --oneline -15` in this repo (`ooxml-graph-paper`) to see exactly which
   commits already landed -- the table above should match.
3. Check the sequencing-isolation test result (above) before deciding whether to launch a
   full confirmatory run for equation/table_structural/caption -- don't re-run blind.
4. Check host memory (`Get-CimInstance Win32_OperatingSystem` free physical memory) before
   launching anything Word-COM-heavy -- this host has crashed multiple times this sprint,
   plausibly tied to memory pressure from concurrent sessions' automation load.
5. `repository` (the product repo) accumulates commits from other concurrent sessions
   constantly -- never `git add -A` there; use the isolated-hunk technique documented in this
   project's memory (`feedback_shared_repo_commit_hygiene.md`).
