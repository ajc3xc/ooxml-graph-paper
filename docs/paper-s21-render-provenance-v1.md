# PAPER-S21: pinned-parent snapshot and Word-COM receipt lifecycle hardening (v1)

Status: preflight infrastructure complete. Two new tools built and tested against real
Word COM and the currently-live (dirty) parent checkout; one genuine, previously-unknown
bug found and fixed in the process.

## Problem this closes

The paper Pixi environment imports `docparse`/`meridian_docs` through an **editable
install** pointing directly at the parent Meridian repo's live filesystem checkout
(`pixi.toml`: `path = "../repository/packages/docparse"`, `editable = true`). Any
scoring/render run's "native Meridian" result therefore silently depends on whatever
that checkout contains at the moment it runs -- including uncommitted, in-progress
changes from a concurrent session (this sprint has repeatedly observed other live
sessions committing to the same shared parent checkout in real time). A run against a
dirty, non-pinned parent is not independently reproducible.

Separately, an earlier probe left a Word automation process running in the background
-- this document explains why, with a concrete repro.

## Tool 1: `tools/prepare_pinned_parent_snapshot.py`

Read-only provenance inspector. Never mutates, stashes, cleans, or checks out anything
in the parent repo -- pure inspection. Records:

- Parent repo's exact git commit (`git rev-parse HEAD`) and whether the working tree is
  dirty (`git status --porcelain`), with a sample of dirty paths (never absolute machine
  paths, so the receipt is safe to embed in a shared manifest).
- Import resolution: confirms `docparse`/`meridian_docs` actually resolve to files
  *inside* the parent repo path (not a stale installed wheel or some other environment).
- MML2OMML.XSL presence/path (checked against the real, standard Office install
  locations, not assumed).
- A non-mutating Word COM activation probe (launches and immediately quits
  `Word.Application`, records `Version`/`Build`; never opens or renders a document).
- An overall `provenance_status`: `clean_pinned` only when the parent is on a known
  commit with **zero** dirty paths and imports resolve correctly; otherwise
  `degraded_dirty_or_unresolved`.

**Live test result (2026-08-30, run against the actual current parent checkout, not a
synthetic fixture):**

```
provenance_status: degraded_dirty_or_unresolved
parent_git.commit: 54d6f9692ab5c958b5aee5351a2f5b7433cd7650
parent_git.is_dirty: true (15 dirty paths, e.g. DEVLOG.md, meridian/db/__init__.py,
  meridian/mcp/handler.py -- from another session's own concurrent, unrelated work)
import_resolution: both docparse and meridian_docs correctly resolve to the parent
  repo path
mml2omml.found: true, C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL
```

This is the real, current state, not a hypothetical -- it directly demonstrates the
problem this tool exists to catch: any paper result generated *right now* would need to
be labeled degraded/non-confirmatory for product-code provenance, because the parent
checkout genuinely is dirty at this exact moment, due to unrelated concurrent activity.

## Tool 2: `tools/word_receipt_watchdog.py`

Wraps the existing, already-validated `tools/retained_render_receipt.py` (itself a
from-scratch, paper-local reimplementation of the parent repo's `render_gate.py`
watchdog/cleanup/COM-apartment pattern, chosen specifically so this paper item never
needs to touch the shared, actively-used parent `render_gate.py`) with an orphan-process
diagnostic layer, without changing the underlying render logic:

1. Snapshot `WINWORD.EXE` PIDs before the render starts.
2. Run the existing `retained_render_receipt()` unchanged.
3. Snapshot `WINWORD.EXE` PIDs again after it returns.
4. Classify every post-render PID: `pre_existing_unrelated` (never touched),
   `clean_no_new_word_process`, or a genuine orphan (new since our own launch, or the
   timeout path's own tracked `owned_pid` still alive).
5. For a genuine, provably-new orphan **only**, attempt a best-effort `terminate()` +
   wait, and record whether cleanup actually completed. A hard safety invariant
   (independently re-checked inside the cleanup function itself, not just trusted from
   the caller) refuses to terminate any PID that was present *before* our own launch,
   even if a caller's bookkeeping were wrong.

### Real bug found and fixed while building this

Testing tool 2 against real gold-corpus fixtures (`fixture-01-baseline.docx`,
`fixture-02-equation.docx`) reproduced the exact "probe left an automation process
behind" symptom this item names, **on every single successful render**, not as a rare
flake:

- `retained_render_receipt.py`'s own `cleanup_status` field reports `"clean"` whenever
  its worker *thread* finished (`not worker_thread.is_alive()`).
- That only confirms the **Python thread** returned after calling `word.Quit()`,
  `doc.Close()` etc. It does **not** confirm the underlying `WINWORD.EXE` **OS process**
  actually exited -- `Word.Application.Quit()` returning at the COM layer does not
  guarantee prompt OS-level process termination.
- Concretely: rendering `fixture-01-baseline.docx` left PID 39056 running as a real
  orphan after a `status: "rendered"` / `cleanup_status: "clean"` receipt. Rendering
  `fixture-02-equation.docx` immediately afterward reproduced it again with a new PID
  (27076) -- confirmed via `word_receipt_watchdog.py`'s own diagnostics, which correctly
  classified each as `unattributed_new_process`, terminated exactly that PID, confirmed
  it exited, and left the one genuinely pre-existing, unrelated `WINWORD.EXE` (PID 33628,
  present on this machine before any of this testing began) completely untouched in both
  cases.

This is now a known, reproducible, and *mitigated* (not just diagnosed) issue: every
caller that goes through `word_receipt_watchdog.py` instead of calling
`retained_render_receipt.py` directly gets orphan detection and safe, narrowly-scoped
cleanup for free, with a `cleanup_complete` field an evidence pipeline can gate on.

## Tests

`tests/test_word_receipt_watchdog.py` -- 5 focused tests covering the classification and
cleanup-safety logic with `psutil`/`retained_render_receipt` mocked (no real Word COM
dependency for the test suite itself): no-new-process is reported clean; a genuine new
orphan is detected, terminated, and confirmed gone; the hard pre-existing-PID guard
inside the cleanup function itself refuses to terminate a PID even if a caller passed it
in `orphan_pids` by mistake; a PID whose live process name isn't `winword.exe` is never
terminated (protects against PID reuse by an unrelated process between snapshots); the
timeout path's own tracked `owned_pid` still being alive is correctly reported as an
orphan. All 5 pass.

## What this item does NOT do (explicitly out of scope, per its own notes)

- Does not mutate, clean, or `git checkout` the parent worktree in any way.
- Does not kill any `WINWORD.EXE` process that existed before this tool's own launch,
  under any circumstance (enforced by a hard invariant check inside the cleanup
  function, independent of caller bookkeeping).
- Does not treat LibreOffice as Word authority; this item's scope is Word-COM only.
- Does not itself force the parent checkout to become clean -- it only detects and
  reports the current state. Achieving a clean, pinned parent snapshot for a
  confirmatory run is an operational step (e.g. running against a fresh `git worktree`
  checked out at a specific pinned commit) that a caller performs using this tool's
  output as the gate, not something this tool does automatically.

## Bounded pilot status

Per this item's own instruction ("keep product-code provenance marked degraded until
the clean parent snapshot is verified"): both tools are built, tested, and working
against real Word COM and the real (currently dirty) parent checkout. No paper result
generated before this item should be treated as having verified-clean parent provenance
-- they were all generated against whatever the parent checkout happened to contain at
the time, which per this same sprint's own history included at least one live,
in-progress, unrelated concurrent-session edit window. Future confirmatory (non-pilot)
runs should call `prepare_pinned_parent_snapshot.py` first and gate on
`provenance_status == "clean_pinned"`.
