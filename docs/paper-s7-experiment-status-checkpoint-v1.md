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
| Equation | 10/11 resolved (1 genuine task failure), development-slice only (12 docs) -- no confirmatory-scale 26-doc run ever attempted | **0/11 resolved, all blocked, unchanged across 2 full-batch attempts** | `insert_equation`'s own internal write-time render-verification (LibreOffice `soffice --convert-to pdf`, 60s bound) -- see full diagnosis below. |
| Table_structural | 24/26 (92.3%) pass, full confirmatory scale, both directions | **1/26 resolved, unchanged across 4 full-batch attempts** at different times/memory conditions | Same mechanism as equation -- confirmed identical signature in 28 of 38 blocked chains across both families. |
| Caption | **Zero run directories exist anywhere.** | **Zero run directories exist anywhere.** | Never attempted at confirmatory scale at all -- confirmed by direct filesystem search 2026-09-06, not just "excluded" in prose. Shares the identical `insert_caption` render-verification path, so almost certainly hits the same wall if attempted. |

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

**Result of seizing that window (2026-09-06, ~19:30-22:39, ~3 hours)**: relaunched the full
remaining-chains resume for both families immediately after the isolated call succeeded.
Outcome: **no change at all** -- table_structural still 25/26 blocked (13+12, identical split
to every prior attempt), equation still 11/11 blocked. Checked immediately afterward for
leftover `soffice`/`WINWORD` processes: none found, and free memory was a healthy 9.74GB --
so this is not simple persistent process/memory leakage surviving after the fact either.

**This is now the 4th independent full-batch attempt** (haiku/bad-memory, sonnet/good-memory,
sonnet/good-memory again, sonnet/this-favorable-window), at different times of day and
memory conditions, all converging on the same ~96-100% treatment block rate -- while isolated,
standalone single calls (mine, and presumably whatever moment let 1-2 chains through each
batch) succeed quickly. The honest synthesis: the render-gate mechanism is not permanently
broken (a single call demonstrably works), but something about SUSTAINED, REPEATED
render-verification calls across many chains within one continuous multi-hour run reliably
degrades success to near-zero, and that degradation is not visible in memory/process state
once the run stops. This smells like a resource that degrades DURING sustained use and
recovers on its own once idle (a LibreOffice-internal state -- profile lock contention,
a leaked file handle or temp-file buildup that only shows up mid-run, a `soffice` background
listener that degrades under repeated rapid restarts) rather than anything visible to
Task Manager-level inspection.

## FOUND AND FIXED (2026-09-07): the real root cause was the shared soffice profile lock

Read `render_gate.py`'s actual `_soffice_render` implementation directly rather than continuing
to speculate: it invokes `soffice --headless --convert-to pdf ...` with **no
`-env:UserInstallation=` override**, meaning every single conversion on this machine -- from
this harness's own sequential chains AND from any other concurrent process on this shared host
-- uses ONE shared default LibreOffice profile directory and its lock file. Concurrent/rapid
contention for that lock is a well-documented LibreOffice failure mode, and the code's own
existing comment had already anticipated the exact symptom ("a render that hung once is likely
to hang again... never retried") without identifying the cause.

**Fix**: give each `_soffice_render` call its own private, isolated profile directory via
`-env:UserInstallation=`, so it can never contend with any other soffice invocation for the
shared lock (commit `7f32fb60` in `repository`, `extensions/meridian-docs/meridian_docs/
render_gate.py` + a new regression test in `test_docx_render_gate.py`). Standard practice for
concurrent/automated LibreOffice use.

**Verified live, directly, before trusting it**: called `insert_table` 10 times in a row
against fresh copies of the same document that had reliably blocked under the old code.
**Result: 10/10 succeeded, 9-19 seconds each, zero degradation across the run** -- the exact
sustained-use pattern that previously failed almost universally now works cleanly every time.

**Result of the first real re-run with this fix (2026-09-07, ~00:08-04:12, ~4 hours)**:
relaunched table_structural's remaining chains AND, for the first time ever, equation's TRUE
confirmatory corpus (holdout + validation, 26 documents, not the 12-doc development slice).
table_structural: **no change at all** (13/13 and 12/12 blocked, identical split to every
prior attempt). Equation (brand new data): control 49/51 clean + 2 completed_with_failure
(healthy), **treatment still overwhelmingly blocked**.

**But the FAILURE SIGNATURE had changed**, which is real, useful information, not just another
failure: classifying the new blocked chains found **44 of ~52 (85%) now show soffice CRASHING**
with exit code `3221226505` / `0xC0000409` (a Windows stack-buffer-overrun) instead of the old
60-second timeout. The isolation fix had genuinely worked -- it eliminated the HANG -- but
exposed a second, distinct problem: `check_render_capability` already classifies this kind of
nonzero-exit failure as retryable and retries once, but with ZERO delay (an immediate
`continue`). Confirmed 25 concurrent `claude` processes and 40 `python` processes running on
this shared host at the time -- a plausible real source of the resource contention causing the
crash, which a zero-delay retry gives no time to clear (matching the transcripts' own "fails on
every attempt" description).

**Second fix**: added a 2-second backoff before a retry (never before the first attempt, never
after a final non-retryable failure) -- commit `20eb8039`, 3 new regression tests. Relaunched
the identical completion run a second time with both fixes in place immediately after. Script:
`finish_with_fix.sh`, log `finish_with_fix2.log` in this session's scratchpad. **Check that
log's real output before assuming any outcome -- this is another multi-hour run.**

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
