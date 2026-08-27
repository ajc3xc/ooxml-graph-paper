# Executor reproducibility contract v0

Status: investigation plus paper-harness update. The paper harness is now a
separate local Git repository; no parent product code was changed by this update.
All historical findings below were directly observed on 2026-08-26 (commands run,
outputs read, files listed) rather than inferred from prior notes; where a prior
session's claim is repeated, it is marked as re-verified or flagged as a
discrepancy. This document extends `runtime-capability-contract-v0.md` and
`checkpoint-2026-08-25.md`; it does not duplicate or contradict them.

## 1. Repository boundary and the empty paper `tests/` directory

Two separate root directories are in play:

- `C:\Users\13144\Documents\Meridian\ooxml-graph-paper` — the paper subproject.
  **A separate local Git repository on branch `dev`**, containing the paper
  harness, scripts, tests, and methodology. Its data and render roots remain
  outside Git on `E:\MeridianData\ooxml-graph-paper`.
- `C:\Users\13144\Documents\Meridian\repository` — the parent repo. A real git
  worktree on branch `dev`; it owns the Meridian Docs implementation and may
  remain dirty during active development.

The paper does not duplicate or fork the Meridian Docs implementation. For an
interim run, `scripts/check_acceptance_gate.py --allow-dirty-parent` pins the
shared parent checkout's HEAD, complete Git status/diff, and exact product-file
hashes. A change to any of those fingerprints fails the gate. For publication,
the same implementation should be committed on a dedicated parent branch and
benchmarked from a clean worktree at that revision.

The paper subproject's `pixi.toml` declares one task, `test = "python -m
pytest"`, with `src/` and `tests/` both present as directories but containing
zero files (confirmed with `ls -la`: each directory lists only `.` and `..`).
There is no `pyproject.toml`, `pytest.ini`, `setup.cfg`, or `conftest.py`
anywhere in the subproject to point pytest at a different root.

Collection was actually run, not just cited:

```
$ cd C:\Users\13144\Documents\Meridian\ooxml-graph-paper
$ pixi run test --collect-only -q
Pixi task (test): python -m pytest --collect-only -q
no tests collected in 0.01s
```

A real (non-collect-only) run was also executed to check the exit code, since
"no tests collected" printed to stdout is not itself proof the run is treated
as a failure by anything downstream:

```
$ pixi run test
============================= test session starts =============================
platform win32 -- Python 3.12.14, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\13144\Documents\Meridian\ooxml-graph-paper
collected 0 items
============================ no tests ran in 0.02s ============================
EXIT_CODE=5
```

pytest's own exit code 5 (`no tests ran`) is emitted correctly — this is not a
false-green 0. Any executor that checks only `echo $?` gets a truthful
non-zero result. The danger is entirely in *tooling that doesn't check the
exit code* and instead greps stdout for the string `FAILED` (absent here) or
treats "no error printed" as success — see Section 7.

Why it's empty: the paper subproject's `pixi.toml` declares editable
`pypi-dependencies` on `../repository/packages/docparse` and
`../repository/extensions/meridian-docs` (confirmed by reading `pixi.toml`
directly), i.e. it *imports* the product code rather than owning it. The
product implementation and its regression tests live entirely in the parent
repo, principally under `extensions/meridian-docs/tests` (642 tests collected
there today — see Section 2) and the parent repo's top-level `tests/` (11,271
of 11,342 collected in the default marker selection — see Section 2). No
product coverage exists in the paper subproject and none should be inferred
from an empty local collection.

## 2. Parent repo's real test-running procedure

`pixi.toml` in the parent repo is **not** a thin wrapper over plain pytest.
Reading the `[tasks]` block directly:

```
test = "python scripts/run_tests.py tests/ -q --tb=short --ignore=tests/test_demo_ux.py --ignore=tests/test_rate_limit_serial.py -m \"not subprocess_isolated\" && python scripts/run_tests.py --serial tests/test_rate_limit_serial.py -q --tb=short && python scripts/run_tests.py --serial tests/ -q --tb=short -m subprocess_isolated"
```

This is a **three-step, `&&`-chained shell command**, every step routed
through `scripts/run_tests.py` (never raw `pytest`):

1. Main sweep: `tests/` minus `test_demo_ux.py` and `test_rate_limit_serial.py`,
   minus anything marked `subprocess_isolated`.
2. `test_rate_limit_serial.py` alone, forced serial (`--serial`) — the
   in-repo comment explains this test depends on real wall-clock spacing
   between requests and is corrupted by parallel worker CPU contention.
3. Everything marked `subprocess_isolated`, forced serial — the comment
   explains xdist workers each spawning real OS subprocesses have produced
   Windows NTSTATUS crash codes (`ACCESS_VIOLATION`, `DLL_NOT_FOUND`,
   `CONTROL_C_EXIT`) from pure contention, not real regressions.

`test-pg` and `test-cov` are the same three-step shape with `TEST_DATABASE_URL`
routing (`test-pg`) or `--cov` (`test-cov`) added. `test-fast` is a fixed
11-file allowlist run directly (no wrapper chaining, no lock).

### Why `pixi run test --collect-only -q` starts real execution

The prior session's finding is correct, and the mechanism is now verified by
direct reproduction rather than by reading the shell text alone. `pixi run
<task> <extra args>` appends the caller's extra CLI arguments to the **end of
the fully resolved task command string**, not to each `&&`-chained
sub-command and not to the first one. A minimal reproduction confirms this
concretely (built in the scratchpad, not in either real repo, specifically so
this could be checked without touching the real 11k-test suite):

```
[tasks]
test = "python -c \"print('STEP-A ran for real')\" && python -c \"print('STEP-B ran for real')\" && python -c \"print('STEP-C ran for real')\""
```

```
$ pixi run test --collect-only -q
Pixi task (test): python -c "print('STEP-A ran for real')" && python -c "print('STEP-B ran for real')" && python -c "print('STEP-C ran for real')" --collect-only -q
STEP-A ran for real
STEP-B ran for real
STEP-C ran for real
```

`--collect-only -q` landed only after STEP-C's own command text, and STEP-A
and STEP-B ran unconditionally and in full before STEP-C was even reached.
Applied to the real parent-repo `test` task, that means `pixi run test
--collect-only -q` runs the **entire main sweep (step 1) and the entire
serial rate-limit test (step 2) for real**, and only step 3
(`scripts/run_tests.py --serial tests/ -q --tb=short -m subprocess_isolated`)
receives the appended flags — and even there, whether that step actually
stays collect-only depends on `run_tests.py`'s own argument handling (next
paragraph). This is a genuine footgun: an executor trying to "just count
tests" on the parent repo via `pixi run test --collect-only` will instead run
thousands of real tests it did not intend to run.

`scripts/run_tests.py` (1,346 lines, read directly) does have real
collect-only awareness, but it is internal and does not rescue a caller from
the pixi arg-append problem above. Every invocation (`main()`, line 1193)
unconditionally runs its own internal preflight collection
(`collect_count()`, called at line 1288) purely to decide serial-vs-`-n auto`
scheduling — this preflight always runs a real `pytest --collect-only -q -p
no:xdist` subprocess regardless of what the caller passed. After that,
`build_run_args()` (line 435) builds the *actual* run command by starting
from `list(pytest_args)` (i.e. whatever trailing args the caller supplied)
and appending `--durations=20`, `--timeout=60`, and either `-p no:xdist` or
`-n auto --dist=worksteal`. Critically, it does **not** strip a caller-
supplied `--collect-only` back out — so if `--collect-only` is present in
`pytest_args` when `run_tests.py` itself is invoked directly (not through the
`&&`-chained pixi task), the real run stays collect-only too. This was
verified directly, safely, and without ever running the real suite:

```
$ cd C:\Users\13144\Documents\Meridian\repository
$ pixi run python scripts/run_tests.py tests/ --collect-only -q -m "not subprocess_isolated" --ignore=tests/test_demo_ux.py --ignore=tests/test_rate_limit_serial.py
...
11271/11342 tests collected (71 deselected) in 12.73s
```

12.73 seconds for over 11,000 test IDs, with output limited to a list of node
IDs (no `PASSED`/`FAILED` lines) is consistent with genuine collection, not
execution. This is the safe pattern: call `scripts/run_tests.py` directly
with `--collect-only` already embedded in its own argument list, never
through `pixi run test --collect-only`.

`run_tests.py`'s pass/fail classification is fail-closed in a way worth
recording verbatim (read at lines 1046–1093): pytest's own exit code is
mapped to `STATE_PASSED` only on exact `returncode == 0`; a process signal
maps to `STATE_CRASHED`; pytest's own `INTERNAL_ERROR`/`USAGE_ERROR` (3, 4)
map to `STATE_CRASHED`; `INTERRUPTED` (2) maps to `STATE_CANCELLED`; **every
other exit code, including pytest's `5` ("no tests ran"), falls into the
`else` branch and maps to `STATE_FAILED`.** So a hypothetical zero-collected
run through `run_tests.py` is correctly reported `failed`, not `passed` — a
real fail-closed design, not an accidental one. There is also a durable
`TestRunLock`/`TestRunTracker` (repo-root-scoped lock file) shared across all
three chained steps and across concurrent invocations from other sessions;
a run attempted while another is active gets a duplicate-report rejection
(exit 2) rather than silently running alongside it, unless `--supersede` is
passed and the previous owner PID is confirmed dead.

Also directly observed: the parent repo's actual test-file surface under
`extensions/meridian-docs/tests` shifted while this investigation was
running. `pixi run python -m pytest extensions/meridian-docs/tests
--collect-only -q -p no:xdist` (plain pytest, default env, no marker
filtering) collected **642 tests today**, not the 682 cited in the shared
session context. `git status --porcelain -- extensions/meridian-docs/tests`
shows why — the checkout is mid-edit (Section 3):

```
 D extensions/meridian-docs/tests/test_982f8564_batch_transform.py
 M extensions/meridian-docs/tests/test_docx_namespace_preservation.py
 D extensions/meridian-docs/tests/test_mde_b1_equation_integrity_audit.py
 D extensions/meridian-docs/tests/test_mde_b2_equation_diff_repair.py
 D extensions/meridian-docs/tests/test_render_receipts.py
?? extensions/meridian-docs/tests/test_docx_equation_fail_closed_contract.py
?? extensions/meridian-docs/tests/test_docx_numbered_equation_writer.py
```

Four deletions, one modification, two new untracked files — net a plausible
explanation for a ~40-test swing, not independently reconciled file-by-file.
This is flagged rather than silently repeated: **the 682-failure/169-failure
baseline cited in the shared context is itself a moving target while the
working tree stays dirty.** Any future session re-quoting "169 of 682" should
re-run collection first and note the count it actually saw.

## 3. Parent repo dirty-checkout state

Directly checked with `git status` and `git status --porcelain=v1`, not
assumed:

```
On branch dev
Your branch is up to date with 'origin/dev'.
```

81 total porcelain lines: 4 untracked (`.codex/`,
`extensions/meridian-docs/tests/test_docx_equation_fail_closed_contract.py`,
`extensions/meridian-docs/tests/test_docx_numbered_equation_writer.py`,
`workspace/docx-wave2-final-qa/.meridian-outputs-cache/`) and 77
modified/deleted-but-tracked paths, including exactly the files the shared
context named as part of the in-flight b67/MDE equation-integrity effort:
`extensions/meridian-docs/meridian_docs/docs_intel.py`,
`extensions/meridian-docs/meridian_docs/ooxml_integrity.py`,
`extensions/meridian-docs/meridian_docs/render_gate.py`, and
`extensions/meridian-docs/meridian_docs/server.py`, plus a long tail of
`meridian/*.py`, `docs/*.md`, and `extensions/meridian-outputs/*` changes.
`HEAD=c2b0d03b0c136bdf102850cb8787adac0861da98`, matching `origin/dev`.

**Implication for reproducibility claims:** no run performed against this
checkout right now can be pinned to a single, citable git commit. A run
manifest's "code revision" field cannot honestly read just the HEAD SHA — it
would silently claim the committed `c2b0d03b…` tree when the code actually
executed includes 77 uncommitted, unreviewed edits. Until this checkout is
committed (or a run is taken from a clean worktree/branch checked out from a
specific commit), any benchmark result produced here must record **both**
`HEAD` **and** a diff hash/patch (e.g. `git diff | sha256sum`, or an archived
`git diff` file) alongside it — never just the SHA. This is the single
biggest concrete reproducibility gap this investigation found.

## 4. Is an isolated git worktree actually needed here

Two different scopes need two different answers.

**The paper subproject** (`ooxml-graph-paper`) is not a git repository at
all — `git worktree add` cannot be run there because there is no `.git` to
attach a worktree to. `worktree_suggested=true` on this sprint item, and the
`worktree_setup_cmd` it returned (`git worktree add
.claude/worktrees/ba0d71ac -b worktree/cac69156`), is only meaningful **if
run from inside the parent repo** — its own `touches_resources` list mixes
paper-subproject paths (`file:pixi.toml`, `file:README.md`,
`docs/runtime-capability-contract-v0.md`, all of which exist in the paper
subproject) with a parent-repo path (`file:extensions/meridian-docs/tests`),
which is itself worth flagging: the sprint tool's resource-locking layer does
not distinguish which of the two repos a relative path belongs to, so a
`file:` lock on `extensions/meridian-docs/tests` taken while cwd'd in the
paper subproject does not actually protect the real directory on disk unless
the executor separately knows to `cd` into the parent repo first. This
session did not create a worktree (task was investigation-only, no files
edited), consistent with the shared context's note that direct edits worked
fine for prior single-session work.

**The parent repo** already uses worktrees heavily and routinely as its
normal working pattern — `git worktree list` returns well over 100 entries,
the large majority under `repository/.claude/worktrees/*`, `repository/
.codex/worktrees/*`, and sibling directories like `C:\Users\13144\Documents\
Meridian\worktrees\*`. This is not a hypothetical recommendation; it is the
house pattern already in continuous use by many concurrent sessions on this
machine. `pixi.toml`'s own top-of-file comment block documents why:
detached Pixi environments are keyed per-worktree-path so each worktree gets
its own resolved environment, and a dedicated `pixi_env_retention.py` /
`orphan_reaper.py` pair exists specifically to reclaim those when a worktree
is deleted.

**Recommendation:** for a future CODE item that edits parent-repo files
(especially `docs_intel.py` at ~20,000 lines, already twice corrupted this
sprint by stale-offset symbol edits per the shared context, or anything under
`extensions/meridian-docs/`), use a worktree — not as a defense against
symbol-editing offset corruption itself (that is a Serena/meridian-extract
tool-chaining problem, unrelated to git isolation), but because this repo
already has 100+ concurrent worktrees in active use and a single-session
direct edit on the shared `dev` checkout risks colliding with one of those
other live sessions' in-flight, currently-uncommitted changes (Section 3) —
isolation here is about not stepping on other *humans'/agents'* uncommitted
work, not about protecting against your own tool-chaining bugs. For
investigation-only items with zero file edits (like this one), a worktree
adds setup/teardown cost for no isolation benefit and is reasonably skipped,
matching what the prior session already found.

## 5. Code-intel/tunnel availability

`codebase-memory-mcp` **is** indexed for this repository, under multiple
project names (checked with `list_projects`, then `index_status` on the
primary one):

```
index_status("meridian-repo") ->
{
  "status": "ready",
  "nodes": 126821,
  "edges": 980840,
  "root_path": "C:/Users/13144/Documents/Meridian/repository",
  "git": { "branch": "dev", "head_sha": "c2b0d03b0c136bdf102850cb8787adac0861da98", ... }
}
```

Other entries also resolve to the same repo root under different names/scopes
(`meridian-build`, `meridian-canonical`, `meridian-docs` scoped to
`extensions/meridian-docs` at 1,576 nodes, `meridian-outputs` scoped to
`extensions/meridian-outputs` at 935 nodes, plus several worktree-specific
indexes such as `Meridian-ci-code-intel-receipt-normalization`). The paper
subproject is **not** indexed under any name — `index_status("ooxml-graph-
paper")` returns `project not found or not indexed` and lists the 16
projects that are (confirmed live, not assumed).

One caveat worth recording: `index_status`'s `head_sha` matches the
*committed* `HEAD`, and the response carries no explicit "dirty" or
"last-indexed-at" signal distinguishing "indexed at this exact working tree
state" from "indexed at this commit, uncommitted changes since not
reflected." Given Section 3's finding that the checkout is dirty, code-intel
queries against `docs_intel.py` and friends should be treated as **possibly
one edit-generation behind** the literal file on disk until proven otherwise
— cross-check anything load-bearing with a direct `Read`/`Grep` rather than
trusting the graph alone for files known to be in the dirty set.

## 6. E: artifact root, restricted datasets, lockfiles, and run manifests

### E: artifact root — observed layout

`E:\MeridianData\ooxml-graph-paper` contains exactly: `derived/` (empty),
`logs/` (5 files — HTML page captures from a ReadingBank source-availability
check, e.g. `readingbank-drive-folder.html`), `manifests/` (5 JSON files:
`docbank-metadata-2026-08-25.json`, `local-docx-smoke-2026-08-25.json`,
`meridian-equation-word-probe-20260826.json`, `render-capability-2026-08-25
.json`, `word-render-probe-20260826.json`), `model-cache/` (empty), `raw/`
(three subdirectories: `DocBank-repo`, `DocBank-repo-incomplete-20260825`,
`ReadingBank`), and `renders/` (two probe-output subdirectories from today's
Word render probes). Nothing under this root is on OneDrive, and the paper
subproject's own `.gitignore` explicitly excludes `data/`, `runs/`,
`renders/`, and `model-cache/` from ever landing in C:\, consistent with the
policy stated in `README.md` and `runtime-capability-contract-v0.md`.

### Restricted-dataset staging — re-verified, not re-derived

`raw/DocBank-repo/DocBank_samples/DocBank_samples` contains exactly 600
files, confirmed by direct listing and `wc -l`; at 6 files per sample
(`.txt`, `.jpg`, `_ann.jpg`, `_ori.jpg`, `_black.pdf`, `_color.pdf`) that is
exactly 100 sample documents — matching the shared context's "exactly 100
real sample docs" claim, now independently re-counted rather than trusted.
`raw/DocBank-repo/README.md` states the dataset license was updated to
Apache-2.0 (read directly). `raw/DocBank-repo-incomplete-20260825` contains
only a `.git` directory — no payload — confirming its name is accurate: it
really is an incomplete/abandoned clone attempt, not a second copy of usable
data. `raw/ReadingBank` contains a single 222,955-byte
`ReadingBank_images_examples.zip` and nothing else; the full ReadingBank raw
package is not staged. **No full DocBank corpus (54.3 GB) or full ReadingBank
package is present anywhere on this machine as observed by this
investigation, and none was downloaded as part of it.** Licensing/dataset
sourcing decisions beyond what's already staged are covered in
`dataset-landscape-2026-08-25.md` and are not re-litigated here.

### Lockfile state — both repos

- Paper subproject: `pixi.lock` exists (31,920 bytes, last modified
  2026-08-25 07:01, same session as `pixi.toml`).
- Parent repo: `pixi.lock` exists (674,051 bytes, last modified 2026-08-24
  09:58). `git status --porcelain -- pixi.lock` returns **nothing** — the
  lockfile itself has zero uncommitted drift relative to `HEAD`, unlike the
  77 other dirty paths in Section 3. `pixi run --locked -e default python
  --version` was run directly (rather than trusting `pixi info`'s summary)
  and succeeded (`Python 3.12.13`) without a lock-mismatch error, which is
  pixi's own strict "refuse to resolve, use exactly what's locked" mode —
  positive evidence the committed lock is currently consistent with the
  committed manifest.

**A discrepancy with the shared context worth flagging plainly.** The shared
context states running tests requires `.pixi/envs/default` specifically
because "`.pixi/envs/dev` does NOT have lxml." Two things were found that
complicate this claim:

1. `pixi info` in the parent repo prints, on every invocation: `WARN
   Environments found in 'C:\Users\13144\Documents\Meridian\repository
   \.pixi\envs', this will be ignored and the environment will be installed
   in the 'detached-environments' directory: 'C:/Users/13144/.pixi/
   workspace-envs\meridian-6725095497969888438'.` The in-repo `.pixi\envs\
   default` and `.pixi\envs\dev` folders on disk (dated July, confirmed with
   `ls -la`) are **stale and explicitly ignored** by pixi itself — real
   `pixi run` invocations resolve to the external detached-environments
   root instead (`C:\Users\13144\.pixi\workspace-envs\`, which currently
   holds roughly 200 accumulated per-worktree environment directories,
   confirming the orphan-accumulation problem `pixi.toml`'s own header
   comment documents).
2. Directly testing both environments today: `pixi run python -c "import
   lxml; print(lxml.__version__)"` (default) and `pixi run -e dev python -c
   "import lxml; print(lxml.__version__)"` (dev) **both** printed `lxml
   6.1.1` — no failure in either. This is explainable: `pixi.toml`'s
   `[environments]` block defines `dev = { features = ["dev"], solve-group =
   "default" }`, which layers the `dev` feature *on top of* the default
   feature set (which is where `lxml` is declared) rather than replacing it,
   and both share one solve-group.

This investigation cannot fully reconcile *why* an earlier session observed
`.pixi/envs/dev` lacking lxml — plausibly it inspected the now-stale in-repo
`.pixi\envs\dev` folder directly (e.g. via a raw path to its `python.exe`)
rather than through `pixi run -e dev`, which would explain the discrepancy
without contradicting either observation. What is verified, today, live: **a
plain `pixi run -e dev <cmd>` in the parent repo does resolve lxml
correctly.** Any future session should re-verify this itself rather than
propagating either claim uncritically — environments here are unusually easy
to get confused between the stale in-repo folder and the real detached one.

### What a genuine run manifest should contain

Extending (not replacing) `comparator-contract-v0.md` §5's "every result row
records..." list into a concrete schema for this paper's future benchmark
runs:

```json
{
  "run_id": "uuid-or-ULID",
  "started_at_utc": "...", "finished_at_utc": "...", "wall_time_seconds": 0,
  "dataset": { "name": "...", "revision_or_commit": "...", "manifest_sha256": "..." },
  "code": {
    "repo": "C:\\Users\\13144\\Documents\\Meridian\\repository",
    "git_head_sha": "c2b0d03b0c136bdf102850cb8787adac0861da98",
    "git_branch": "dev",
    "dirty": true,
    "uncommitted_diff_sha256": "... (required whenever dirty=true)",
    "paper_subproject_note": "ooxml-graph-paper has no git history; record file mtimes/hashes of any changed doc/config instead of a SHA"
  },
  "environment": {
    "pixi_lock_sha256": "...",
    "pixi_environment_name": "default|dev|...",
    "resolved_prefix": "C:/Users/13144/.pixi/workspace-envs/<key>/envs/<env>",
    "python_version": "3.12.13",
    "os": "Windows 11 10.0.26200"
  },
  "hardware": { "gpu": "RTX 3080 20480MiB", "driver": "591.86", "cpu_cores": 0 },
  "model_or_checkpoint": { "name_or_none": null, "revision_or_none": null, "frozen": true },
  "render_backend": { "used": "word-com|libreoffice|none", "verified": true },
  "token_accounting": { "applicable": false, "input_tokens": 0, "output_tokens": 0, "tokenizer": null },
  "outputs": [ { "path": "...", "sha256": "...", "bytes": 0 } ],
  "test_gate": { "collected": 0, "passed": 0, "failed": 0, "exit_code": 0, "runner": "pixi run test | scripts/run_tests.py" }
}
```

Every field above maps to something this investigation actually confirmed is
observable on this machine right now (git SHA/dirty flag, pixi.lock hash,
resolved prefix path, GPU/driver string from the checkpoint doc, render
backend from the Word-COM probe manifest) — nothing here is aspirational.

## 7. Verified, copy-pasteable executor commands

All of the following were actually run during this investigation, with the
exact output shown above in Sections 1–2; they are repeated here as a
standalone reference block.

**Paper subproject — safe collection check (already safe, no chaining):**
```
cd C:\Users\13144\Documents\Meridian\ooxml-graph-paper
pixi run test --collect-only -q
```
Expect `no tests collected in 0.01s`. This is correct and expected today —
it is not a bug to fix, it is the documented state of an empty scaffold.

**Paper subproject — real run (will exit 5, not 0, until real tests exist):**
```
cd C:\Users\13144\Documents\Meridian\ooxml-graph-paper
pixi run test
```

**Parent repo — safe collection check (bypasses the unsafe chained task):**
```
cd C:\Users\13144\Documents\Meridian\repository
pixi run python scripts/run_tests.py tests/ --collect-only -q -m "not subprocess_isolated" --ignore=tests/test_demo_ux.py --ignore=tests/test_rate_limit_serial.py
```
Never run `pixi run test --collect-only` in the parent repo — see Section 2
for the exact mechanism by which that starts two full real test steps first.

**Parent repo — scoped collection check on just the product under test:**
```
cd C:\Users\13144\Documents\Meridian\repository
pixi run python -m pytest extensions/meridian-docs/tests --collect-only -q -p no:xdist
```

**Parent repo — the real, full, intended test gate (this is what CI runs):**
```
cd C:\Users\13144\Documents\Meridian\repository
pixi run test
```
This genuinely executes the full three-step chain from Section 2. Budget for
it accordingly — it is not fast (11k+ tests across two serial carve-outs plus
an `-n auto` sweep) — and expect the pre-existing 169-of-682 (or nearby,
given Section 2's drift finding) `extensions/meridian-docs`-scoped failures
described in the shared context, all traced to the minimal-fixture/
`ooxml_integrity` required-parts gate mismatch, not to anything this
investigation touched.

**Parent repo — Postgres-backed gate (only if `TEST_DATABASE_URL` is set):**
```
cd C:\Users\13144\Documents\Meridian\repository
TEST_DATABASE_URL=postgresql://meridian:meridian@localhost:5432/meridian_test pixi run test-pg
```
Not run in this investigation — no local Postgres instance was confirmed
reachable, and standing up one was out of scope for an investigation-only
item.

**Either repo — confirm the lockfile is actually honored before trusting a run:**
```
pixi run --locked -e default python --version
```
Fails loudly if `pixi.lock` has drifted from `pixi.toml`; succeeded in the
parent repo today (`Python 3.12.13`).

## Failure policy: what a FALSE green run looks like, and how to catch it

A run must be treated as **not trustworthy** — regardless of what exit code
or summary line it printed — if any of the following hold. Each is a real,
observed mechanism from this investigation, not a hypothetical.

1. **`--collect-only` was passed to `pixi run test` in the parent repo.**
   Detect: the command line itself. If you see `pixi run test --collect-only`
   (or any extra args appended to the `test`/`test-pg`/`test-cov` task) in a
   log, the run is invalid — two of its three chained steps ran for real
   before collection was ever reached. Fix: call `scripts/run_tests.py`
   directly with `--collect-only` embedded in its own argument list (Section
   7), never append it to the pixi task invocation.

2. **A reported "0 collected" (or a `collected 0 items` line) is treated as
   passing.** Detect: search the run's own stdout for `collected 0 items` or
   `no tests ran`, or check that `test_gate.collected` in the run manifest
   (Section 6) is `> 0`. This investigation confirmed the paper subproject's
   `pixi run test` correctly exits `5` on zero collection (not a false 0),
   and the parent repo's `run_tests.py` correctly maps *any* non-zero pytest
   exit code — including `5` — to `STATE_FAILED` (Section 2, verified by
   reading the exact branch at `scripts/run_tests.py:1046-1065`). The false-
   green risk is entirely downstream: a wrapper script or dashboard that
   checks `"FAILED" not in output` instead of the exit code, or that reports
   "0 failed" without also reporting "0 passed" as suspicious, will silently
   treat an empty collection as a clean pass. Fix: always assert `collected
   > 0 AND exit_code == 0 AND passed > 0` together, never any one alone.

3. **The run claims a git SHA without also recording dirty state.** Detect:
   a run manifest with a `git_head_sha` field but no `dirty` boolean, or
   `dirty: true` with no accompanying diff hash. Section 3 confirmed the
   parent repo has 81 dirty porcelain entries right now; a manifest that
   reports only `c2b0d03b…` is claiming reproducibility it does not have.
   Fix: always emit both `git_head_sha` and `dirty`, and when `dirty=true`,
   also emit a hash of `git diff` (or archive the diff itself) — see the
   manifest schema in Section 6.

4. **A lock-mismatch was silently re-solved instead of failing.** Detect:
   compare a plain `pixi run` against `pixi run --locked`. If `--locked`
   fails where plain `pixi run` succeeds, the environment that actually ran
   was NOT the one `pixi.lock` describes — pixi silently re-solved instead.
   Verified today that this repo's lock is currently consistent
   (`--locked` succeeded), so this specific failure is not currently active,
   but it is a live risk any time `pixi.toml` changes without a matching
   `pixi lock` / `pixi install` step landing in the same commit.

5. **A test-run lock conflict was force-superseded without confirming the
   other run was actually dead.** `run_tests.py`'s own code (read directly,
   lines ~1231-1274) already fails closed here by design — `--supersede`
   only proceeds if `owner_pid_is_confirmed_alive()` plus a confirmed kill;
   an unconfirmed kill leaves the victim's record untouched and returns exit
   2 rather than reporting a false-clean takeover. Detect a violation of this
   only by looking for a manually-deleted lock file or a hand-edited
   `TestRunRecord` state — neither should ever be done by an executor.

6. **Code-intel (`codebase-memory-mcp`) results are trusted for a file known
   to be in the dirty set (Section 3) without a direct `Read`/`Grep`
   cross-check.** Detect: any claim about current `docs_intel.py`,
   `render_gate.py`, `ooxml_integrity.py`, or `server.py` behavior sourced
   only from `search_graph`/`get_code_snippet` without an accompanying direct
   file read. `index_status` carries a `head_sha` but no dirty/freshness
   flag (Section 5) — it cannot itself tell you whether it reflects the 77
   uncommitted edits sitting on top of that SHA right now.

7. **A benchmark result is reported for DocBank/ReadingBank without stating
   which slice was used.** Only 100 DocBank samples and one ReadingBank
   example zip are staged (Section 6) — any reported number implying
   evaluation over the full 500K-page DocBank split or the full ReadingBank
   corpus, when only the 100-sample staging exists locally, is fabricated by
   definition. Detect: cross-check any reported dataset size against what is
   actually staged under `E:\MeridianData\ooxml-graph-paper\raw`.

No dataset was downloaded, no code was edited, and no test suite's real
(non-collect-only) results are claimed as evaluated by this investigation
beyond what is explicitly quoted above (the paper subproject's genuine 0-item
collection/exit-5 run, and the parent repo's two genuine collect-only
counts). The full parent-repo `pixi run test` three-step gate was
deliberately **not** executed in full during this investigation — it was
established to be safe and correctly wired (Section 2's read of the
exit-code mapping), but actually running it end-to-end was out of scope for
an investigation-only item and was left for whichever future session next
needs a real pass/fail gate.

## PAPER-26 update (2026-08-27T16:40Z): a pinned, isolated benchmark checkout now exists

Created via `git worktree add` from the shared parent repo at
`.claude/worktrees/3698394d` (branch `worktree/90fd7a16`), pinned to base commit
`7278a44fa455bb4d5c51217350536095b9f07e2d`. This is purely additive -- the shared
checkout other concurrent sessions are using was never touched, reset, or cleaned.

The 4 files `scripts/check_acceptance_gate.py` already pins byte-identity for
(`PRODUCT_SNAPSHOT_PATHS`: `docs_intel.py`, `ooxml_integrity.py`, `render_gate.py`,
`server.py`) were then overlaid into the worktree with their current, uncommitted,
intentionally-hardened content from the shared checkout -- confirmed via SHA-256 that
all 4 genuinely differ from the base commit (real in-flight hardening exists). Full,
human-readable `git diff HEAD` patches for each file are retained at
`E:\MeridianData\ooxml-graph-paper\manifests\pinned-worktree-patches\` for provenance
review. Everything else in the worktree is byte-identical to the base commit.

**Verification, and an honest limitation found while verifying it:** importing
`meridian_docs.docs_intel` from the isolated worktree and running the same semantic
checks `check_acceptance_gate.py` runs against the live tree (empty-fraction rejection,
correct-fraction acceptance, `\sum` using true `<m:nary>`, `ooxml_integrity` import)
all pass identically -- the pinning is functionally sound for what PAPER-15 actually
calls into. However, the full parent pytest suite does **not** pass unmodified against
this worktree: 2 failures
(`test_validator_rejects_malformed_fraction_and_flattened_fallback`,
`test_validate_reports_hidden_bold_heading_like_case_drift`) occur because those
tests' *expectations* are themselves part of other uncommitted, in-flight work in the
shared checkout's test files, which are not in `PRODUCT_SNAPSHOT_PATHS` and were
therefore not pinned. This does not affect PAPER-15 (which calls the pinned functions
directly, verified above, not pytest), but this worktree is **not** a general-purpose
substitute for the shared checkout if a future session wants to run the full test
suite reproducibly too -- that would need the relevant test files pinned alongside
their product files, a slightly larger scope than what `capture_parent_snapshot()`
itself was designed to check.

Full machine-readable record: `E:\MeridianData\ooxml-graph-paper\manifests\pinned-worktree-manifest.json`.
