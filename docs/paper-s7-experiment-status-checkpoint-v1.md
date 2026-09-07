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

**The diagnosis, corrected and precisely pinned down 2026-09-06 (this was the third and final
hypothesis -- the first two were tested directly and REFUTED, kept below for the record):**

1. ~~Diffuse "shared host contention"~~ -- REFUTED. Re-running the same 25 table_structural
   chains under materially better host memory (13.7GB free vs 6.7GB) produced the identical
   25/26-blocked result, unchanged.
2. ~~Chain-sequencing (treatment's first Word-COM call always follows control's automations
   for the same document)~~ -- REFUTED. Re-running one blocked chain per family for
   table_structural and equation via `run_chain` directly, completely alone, with zero
   preceding chain in the same process, still blocked both times.
3. **CONFIRMED, by directly reading the raw chain data and independently reproducing it
   myself**: `insert_table`/`insert_equation` each perform their OWN internal write-time
   render-verification (LibreOffice `soffice --convert-to pdf`, 60-second bound) AFTER making
   the edit, and reject/roll back the write if that conversion doesn't finish in time. Control
   never calls this tool at all (it edits raw XML directly), so it never hits this path --
   which is exactly why control is unaffected while treatment overwhelmingly is. Classified
   every currently-blocked treatment chain across both families (38 total): **28 of 38 (74%)**
   show this EXACT signature in their own transcript (near-identical wording across
   independently-run trials -- "soffice --convert-to pdf exceeds its 60-second bound", tool
   safely restores the file each time); the other **10 of 38 (26%)** are genuine
   subprocess-level timeouts (the whole `claude -p` CLI call exceeded the harness's own 300s
   cap) -- a different, more classic infra failure mode, still real but distinct.

   **Directly verified this is not a fixed, permanent block**: called `insert_table` myself,
   directly (bypassing the CLI/agent entirely), against the identical document and anchor that
   had just failed in the benchmark -- it succeeded in 4.3 seconds, first attempt, render
   verified. The mechanism works correctly when LibreOffice/host conditions are momentarily
   favorable; the failure rate is real but TIME-VARYING, not structural. This reopens a real
   possibility that a well-timed re-run (or a paced one -- fewer chains per batch, or a pause
   between batches to let LibreOffice settle) can genuinely complete these families at
   confirmatory scale, which the earlier "sequencing" and "shared-memory-contention" framings
   had made sound close to hopeless.

   **Not yet determined**: WHY soffice's reliability varies over time -- plausible mechanisms
   include LibreOffice's own single-instance profile lock degrading after many rapid
   consecutive conversions within one long-running harness process, or orphaned `soffice.bin`
   processes from earlier timed-out conversions never fully releasing (the harness's own
   Word-side orphan-cleanup logic, visible in every receipt's `orphan_diagnostics` field, does
   not appear to have a LibreOffice-side equivalent -- worth checking
   `render_gate.py`/`check_render_capability` for one). Not investigated further this session;
   a real, scoped next step if this recurs.

**In progress right now (2026-09-06, this checkpoint)**: immediately after confirming the
render-gate works under current conditions, relaunched the full remaining-chains resume for
table_structural (25 blocked treatment chains) and equation (development-slice, 11 blocked
treatment chains) via `finish_remaining_experiments.sh` (background task, log
`finish_remaining_experiments_v3.log` in this session's scratchpad) -- seizing the favorable
window rather than just documenting it. **Check that log and the actual chain-result.json
files under the same run roots as before for real status before assuming any outcome.**

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
