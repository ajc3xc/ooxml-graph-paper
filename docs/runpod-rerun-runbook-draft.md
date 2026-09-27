# RunPod re-run runbook (DRAFT, uncommitted, 2026-09-25, revised after review)

Scope: two preregistered runs on one dedicated RunPod CPU pod.

1. **PAPER-S25, respec_cascade re-run** (`docs/paper-s25-respec-cascade-rerun-protocol-v1.md`):
   D documents (3 author documents plus public documents), six families, 4 anchor-sets per
   document, both arms, 21-step chains, plus fresh K=1 baselines for every family.
2. **PAPER-S26, K=4 section-reorder replication**
   (`docs/paper-s26-k4-section-reorder-confirmatory-protocol-v1.md`): N documents the harness has
   never touched, both arms.

**The protocols win on any conflict.** Every launch and statistics command in this runbook is a
byte-identical copy of a `# locked-command:` block in a protocol, and section 8 launches them by
extracting those blocks from the protocol files themselves.

**FINAL DECISIONS, 2026-09-26 (delegated to this session; stated in full, with reasons, in each
protocol's status block and section 14; not reopened here):**
D-R1 D = 8 (3 author + 5 public); D-K1 N = 60; D-R4/D-K7 Meridian Docs pin
`89c93fac6a9ee7a03d98baab34ba7043de983018` (verified 2026-09-26 to exist in
`C:\Users\13144\Documents\Meridian\repository` and to contain the OMML-validator fix, section 3.1
below); D-R5/D-K7 CLI `@anthropic-ai/claude-code@2.1.283` (resolved 2026-09-26 via
`npm view @anthropic-ai/claude-code version`; re-check `claude --version` on the pod, since the
registry can move before provisioning), subscription OAuth token (not an API key); D-R2 no (May
2026 dissertation not added); D-R6 no separate co-author/committee sign-off beyond the author's
own direction to reuse the three documents (disclosed limitation, mirrors the original run);
D-R7/D-K6 licence: dataset-level ODC-BY, per-file provenance unverified (same disclosure standard
the published paper already uses for its existing section-reorder follow-up corpus, cited as
precedent). Both document lists are locked, not by a fresh two-reviewer content review (no time
before the deadline) but by hash rank alone under each corpus's already-recorded seed, produced by
`tools/select_locked_documents.py` and verified against every file's actual SHA-256:
`manifests/s25-respec-documents-locked.json` (SHA-256
`b700bf2e7d942082e0596578c61924859f2e523bf1576614f33f3fcfe8e5137f`, 8 documents) and
`manifests/s26-k4-documents-locked.json` (SHA-256
`bc611e046cf5ca9b5990062b054c00f5725f784d716d4554510d5c9125c56787`, 60 documents), confirmed
disjoint from each other by SHA-256 set comparison. **A runaway-cost circuit breaker** distinct
from the existing infrastructure one is now implemented in `tools/run_sweep_to_completion.py`:
it sums `claude_json_result.total_cost_usd` across every `chain-result.json` under the watched run
roots, checked between relaunch rounds, and halts before any further relaunch at **$1,350** (3x
the top of the $150-450 expected combined-run budget), writing `cost-circuit-breaker.json` with a
clear reason on trip (section 10 below, and S25 section 4 / S26 section 3).

This draft is for the person who runs it (the author, or a session the author has cleared to
spend money). Nothing in this file has been executed. The evidence behind the recorded numbers
is in the scratchpad notes (`.../scratchpad/wf_rerun_prep/runbook/notes.txt`, `aggregate.py`,
`power_k4.py`; the corrected cost model is `.../scratchpad/wf_rerun_prep2/protocols/cost_model_v2.py`
and the heartbeat of section 10 was tested there as `heartbeat.py`).

---

## 0. Lessons from earlier runs that shape this runbook

| What happened | Where recorded | What this runbook does about it |
|---|---|---|
| All 156 chains blocked in 0.4 s: the `claude` CLI refuses `bypassPermissions` when run as root | status checkpoint L1433-1439 | Every harness process runs as the non-root user `bench` (section 5) |
| Pods vanished from the account with no warning (404, not EXITED) on 09-12, 09-13, 09-20 and 09-23 (the last one mid-sweep). Network volumes survived each time | checkpoint L1419, L1489-1494, L1539; transcript 09-23 03:48 UTC | Run roots on the network volume; hourly pulls to the laptop; a written recovery procedure (section 9) |
| On 09-23 the pod and volume were deleted about 2 minutes after only 4 summary JSONs were copied off. The raw trees and every step's `.docx` were lost | transcript 09-23 06:07-06:08 UTC | Archive, local sha256 verification, local re-computation of the statistics and a second copy, and only then teardown (sections 11-12) |
| Meridian Docs was copied from the shared `repository` working tree and installed with `pip install -e`. No commit was recorded | transcript 09-22 22:05-22:10 UTC | Clean `git archive` export of one named commit, installed without `-e`, recorded in every manifest (section 3) |
| The protocol dropped table_structural because a stale local Meridian Docs build lacked `insert_table`/`remove_table` | audit | The pinned build must list both tools, checked on the pod before any trial (section 7) |
| The run root changed between attempts, and partial data was cleared before relaunching | transcript 09-23 03:57, 04:50 UTC | One fixed run root per sweep. Nothing is deleted: the harness itself moves superseded attempts to `<run root>/attic/` |
| A relaunch re-ran every timed-out chain (untrusted `blocked`) | review, 2026-09-25 | Timeouts now have their own trusted statuses; only `infra_blocked` and harness exceptions are re-run (section 9) |
| Launching with `nohup` over ssh left the ssh client hanging | transcript | Launch inside `tmux new-session -d` |
| For the teardown `curl`, `RUNPOD_KEY` was written to `/tmp/rpkey.txt` | transcript 09-23 06:08 UTC | API calls go only through Python helpers that read `.env` in memory (sections 4, 12) |
| The respec harness did not save step-level results, so the lost run has no timing or cost data | `tools/run_respec_cascade_family.py` (before 2026-09-25) | Every step writes `step-result.json`; every chain writes `step_log`; every trial keeps its CLI transcript (done) |
| The lost respec run used `--model haiku` | `paper/sources/respec-cascade-*-manifest.json` | `--model claude-sonnet-5`; the protocols treat it as a new experiment |
| The local `D:` USB NVMe threw I/O errors while retrieved files were being read (09-20) | checkpoint L1541 | Download to `C:` first, verify there, then copy to `D:` and verify again |

---

## 1. Blocking prerequisites (no pod, no spend until all are done)

The code prerequisites are listed, with their status, in S25 section 13 and S26 section 13.
In short, **re-verified 2026-09-26** (status column updated from the 2026-09-25 draft; items
whose status changed are marked):

| Item | Status 2026-09-26 |
|---|---|
| Frozen-chain modes `fail`/`exclude`, freeze cause, pre-freeze grading, step records, exact and cluster tests | done (uncommitted) |
| Six-family chain (21 steps) and six-family baselines with `table_structural` | done (uncommitted) |
| `--documents-manifest` for both respec sweeps, SHA-256 checked first | done (uncommitted) |
| Infrastructure guard (pinned patterns), `infra_blocked`, circuit breaker (exit 3), attempt ledger, attic moves, `--max-chain-attempts` | done (uncommitted) |
| `blocked_*` statuses trusted on resume; `--blocked-policy` in `compute_s7_statistics` | done (uncommitted) |
| `--check-only` for both sweep types; schedule meta file; `--expected-schedule-sha256` | done (uncommitted) |
| Transcript copy and render-gate capture; `--verbose` CLI | done (uncommitted) |
| Selection tools and manifests (`manifests/README.md`); locked document manifests (`tools/select_locked_documents.py`, `manifests/s25-respec-documents-locked.json`, `manifests/s26-k4-documents-locked.json`) | **done 2026-09-26** (uncommitted) |
| S25 **P-R1** `fail_graded_prefreeze`/`package_invalid_only` frozen-chain modes, **P-R2** `infra_blocked`/`infra_excluded`/`aborted_circuit_open` added to `_EXCLUDED_STATUSES`, `--blocked-policy` for `compute_respec_cascade_statistics.py`; `run_respec_cascade_family.py` writes the `infra_excluded` result as an exhausted chain's own checkpoint | **done 2026-09-26** (uncommitted; tested, `pixi run python -m pytest tests/test_compute_respec_cascade_statistics.py tests/test_run_respec_cascade_family.py -q` passes) |
| A runaway-cost circuit breaker distinct from the infrastructure one, and a mechanical relaunch-to-fixed-point wrapper for any locked sweep command (B1) | **done 2026-09-26**: `tools/run_sweep_to_completion.py` (uncommitted; `pixi run python -m pytest tests/test_run_sweep_to_completion.py -q` passes) |
| S25 P-R4 (document-level tests, difference-in-drops, public-only, author-cluster, Holm adjustment), **P-R5** (`tools/respec_rerun_verdict.py`), P-R8, P-R9 (re-resolution fail-and-continue), P-R10 | **pending** -- P-R5 in particular means the `s25-statistics` locked command's `respec_rerun_verdict.py` step has no script to run yet |
| `--provenance-json` for all three sweep scripts (S25 P-R6, S26 P-K3) | **pending, confirmed absent 2026-09-26** by grep and by direct invocation: `run_respec_cascade_sweep.py --check-only ... --provenance-json X` errors `unrecognized arguments: --provenance-json X`. The `s25-primary`, `s25-baselines` and `s26-run` locked commands will not parse until this exists; `s25-check` and `s26-check` (which do not pass it) already parse. |
| S26 P-K1, P-K4, P-K5, **P-K6** (`tools/k4_replication_verdict.py`) | **pending**; P-K6 blocks `s26-statistics`'s verdict step the same way P-R5 blocks `s25-statistics`'s |
| Both protocols locked, each in one commit, with every FINAL DECISION filled | **decisions filled 2026-09-26** (this pass); the commit itself is deliberately not made -- every change in this pass stays staged-but-uncommitted per instruction, for the main session to review and commit |

Record the protocol lock commits in the provenance. **Net effect on "ready to launch":** the
document-selection and cost-safety gaps this pass covered are closed; the CLI-argument gap
(`--provenance-json`) and the two verdict scripts (P-R5, P-K6) are not, and are the concrete
remaining blockers before any confirmatory `s25-primary`, `s25-baselines`, `s26-run`, or the
statistics blocks' verdict steps can be launched. `s25-check` and `s26-check` can run today,
modulo the pinned Meridian Docs build being installed.

---

## 2. Model and CLI

- Model: `--model claude-sonnet-5`. Pass the full ID, not the `sonnet` alias. The smoke phase
  checks that `modelUsage` contains `claude-sonnet-5` and no other Sonnet or Opus model (the
  CLI's own `claude-haiku-4-5` helper calls are expected). Every manifest records the set of
  `modelUsage` keys.
- CLI: `npm install -g @anthropic-ai/claude-code@2.1.283` (D-R5/D-K7, decided 2026-09-26,
  resolved via `npm view @anthropic-ai/claude-code version` at decision time). The 09-22 pod got
  whatever npm served that day (2.1.280); the laptop has 2.1.226; the registry can move again
  before provisioning. Record `claude --version` in the provenance and check it again before each
  launch -- if it no longer equals `2.1.283`, that is a deviation to log in `deviations.md`, not
  a silent substitution. The harness calls it with `--output-format json --verbose`.
- Per-trial timeout stays at `_TIMEOUT_SECONDS = 900` (`claude_pair_runner.py`).

## 3. Pinning the code

### 3.1 Meridian Docs: which commit

`main` does not carry the fix the author documents need.

| Commit | Has `insert_table`/`remove_table` | Has the OMML validator fix (`len(element) == 0`) | Where it is |
|---|---|---|---|
| `f92d2710` (main, 09-14) | yes | **no** (old check: `element.find(_qm("e")) is None`) | main, dev, origin/main |
| `89c93fac` (09-22) | yes | yes | only branch `docs-intel-journal-preset-externalization-20260918` |

Without the validator fix, `move_section` refused all three author documents. `origin/main`
(`103e1498`) still has the old check. **The pin is `89c93fac6a9ee7a03d98baab34ba7043de983018`
(D-R4/D-K7, decided 2026-09-26).** Re-verified this same day, read-only against
`C:\Users\13144\Documents\Meridian\repository`: `git cat-file -t 89c93fac` returns `commit`;
`git show 89c93fac -- extensions/meridian-docs` contains exactly the described diff hunk
(`_validate_omml_structure`'s `m:num`/`m:den` check changed from
`element.find(_qm("e")) is None` to `len(element) == 0`); the commit is on branch
`docs-intel-journal-preset-externalization-20260918`, dated 2026-09-22, not on `main` or `dev`.
No cherry-pick alternative was needed. Every command below is read-only on `repository`.

```bash
# Laptop, Git Bash. PIN is the full SHA chosen above.
PIN=<full-sha>
OUT=/c/Users/13144/AppData/Local/Temp/rerun-pins      # outside both repos
mkdir -p "$OUT"
git -C /c/Users/13144/Documents/Meridian/repository archive --format=tar \
    --prefix=meridian-docs-$PIN/ "$PIN:extensions/meridian-docs" > "$OUT/meridian-docs-$PIN.tar"
git -C /c/Users/13144/Documents/Meridian/repository rev-parse "$PIN:extensions/meridian-docs"  # tree id -> provenance
sha256sum "$OUT/meridian-docs-$PIN.tar"                                                         # -> provenance
```

### 3.2 Paper harness

- Commit the prerequisites on `dev`, then lock both protocols. `git status --porcelain tools/
  manifests/ docs/` must print nothing for the files the run uses.
- Export the harness **with the manifests and both protocols**, so the pod reads the locked
  command blocks from the locked files:
  `git -C <paper repo> archive --format=tar --prefix=harness-<SHA>/ <SHA> tools manifests docs/paper-s25-respec-cascade-rerun-protocol-v1.md docs/paper-s26-k4-section-reorder-confirmatory-protocol-v1.md > harness-<SHA>.tar`.
  Record `git rev-parse <SHA>:tools` and the tar's sha256.
- Never `scp -r` the working directory. The lost run did that while other sessions were
  modifying `tools/`.

### 3.3 Corpus

**Before deriving the pod-path manifests, confirm the frozen document lists have not been
swapped or edited:**

```bash
sha256sum manifests/s25-respec-documents-locked.json    # must equal b700bf2e7d942082e0596578c61924859f2e523bf1576614f33f3fcfe8e5137f
sha256sum manifests/s26-k4-documents-locked.json        # must equal bc611e046cf5ca9b5990062b054c00f5725f784d716d4554510d5c9125c56787
```

Both were produced by `python tools/select_locked_documents.py respec` / `k4` (S25 section 1.3,
S26 section 1.2 item 6), which verifies every listed document's SHA-256 against the actual file at
generation time, not on faith. Derive the pod-path manifests
(`manifests/paper-s25-respec-documents-v1.json`,
`manifests/paper-s26-k4sr-replication-manifest-v1.json`, same `{doc_label, sha256}` pairs, pod
paths `/workspace/ooxml-graph-paper/corpus/<doc_label>.docx`) only after both hashes match. From
the laptop, copy each document under exactly that name. The `s25-check` and `s26-check` commands
(section 8) verify every SHA-256 on the pod before any trial and exit non-zero on a mismatch --
this is a second, independent check, not a substitute for the one above.

### 3.4 Provenance object (goes into every manifest via `--provenance-json`)

```json
{
  "run_id": "rr-respec-v1-primary | rr-respec-v1-baselines | rr-k4-v1 | smoke-...",
  "protocol_doc": "docs/<protocol>.md", "protocol_commit": "<sha>",
  "harness_commit": "<sha>", "harness_tools_tree": "<tree id>", "harness_tar_sha256": "<sha256>",
  "meridian_docs_commit": "<PIN>", "meridian_docs_tree": "<tree id>", "meridian_docs_tar_sha256": "<sha256>",
  "meridian_docs_tool_manifest_sha256": "<sha256 of sorted tool-name list>", "meridian_docs_tool_count": 0,
  "model": "claude-sonnet-5", "claude_cli_version": "<x.y.z>", "auth_mode": "subscription_token | api_key",
  "python": "<version>", "constraints_sha256": "<sha256 of logs/constraints.txt>", "libreoffice": "<soffice --version>",
  "corpus_manifest": "<path>", "corpus_manifest_sha256": "<sha256>",
  "anchor_schedules_sha256": "<S25 only: the locked value>",
  "pod": {"id": "<pod id>", "cpu_flavor": "cpu3c", "vcpu": 8, "datacenter": "<dc>", "image": "<image>", "costPerHr": 0.0},
  "pod_history": [], "network_volume_id": "<id>", "max_workers": 6, "user": "bench"
}
```

The `pod` block is rewritten and `pod_history` appended if the pod is replaced (section 9).

## 4. Instance

- **Flavor:** `cpu3c`, 8 vCPU / 16 GB, Secure Cloud (not spot). Recorded rate $0.24/hr (pod
  `azdyvr9x01bry4`, 09-23). The locked commands use `--max-workers 6`, so the 4 vCPU fallback is
  not used for confirmatory sweeps (it would change a locked command).
- **Image:** `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`. It is RunPod-published
  and ships the SSH bootstrap. A plain `python:3.11` image had no SSH.
- **Storage:**
  - A **new, dedicated** network volume, 60 GB. The archive temporarily duplicates the run
    tree, and the author documents are about 9 MB each with one copy per step.
  - The volume sits in the datacenter the pod is pinned to (`dataCenterIds`). Container disk:
    30 GB.
  - Do **not** reuse `sam31-annotator-permavol`, and do not touch other projects' pods or
    volumes (a `dnabert-phylogpn-finetune` pod was RUNNING on this account on 09-20).
  - Creating a volume needs at least $5 of account balance.
- **Provisioning:** copy `tools/provision_runpod_s7_rerun.py` to a new file (the scripts' own
  rule is "copy, do not edit in place"). Change `name`, `NETWORK_VOLUME_NAME`,
  `NETWORK_VOLUME_SIZE_GB=60`, `CONTAINER_DISK_GB=30`, and the vCPU order to `(8,)`. Run
  `--dry-run` first. Record the returned `id` and `costPerHr` straight into the provenance.
- `RUNPOD_KEY` stays in the gitignored `.env`. It is only read in memory by these scripts. It
  never goes into a file, onto a command line, or into the transcript.

## 5. Pod setup (about 10 minutes; container disk is lost if the pod vanishes)

```bash
# as root on the pod (ssh -p <port> root@<ip>)
apt-get update -qq && apt-get install -y -qq tmux libreoffice --no-install-recommends
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y -qq nodejs
npm install -g @anthropic-ai/claude-code@<VERSION> && claude --version
id -u bench 2>/dev/null || useradd -m -s /bin/bash bench
mkdir -p /workspace/ooxml-graph-paper/{pins,corpus,runs,archive,logs,launch}
chown -R bench:bench /workspace/ooxml-graph-paper
```

From the laptop, `scp` the two pin tars into `/workspace/ooxml-graph-paper/pins` and the
documents into `/workspace/ooxml-graph-paper/corpus` (section 3.3). Then:

```bash
# as bench (su - bench)
cd /workspace/ooxml-graph-paper/pins
sha256sum meridian-docs-<PIN>.tar harness-<SHA>.tar          # must equal the laptop values
tar -xf meridian-docs-<PIN>.tar && tar -xf harness-<SHA>.tar
python3 -m venv /home/bench/venv
/home/bench/venv/bin/pip install -q --upgrade pip
# First pod: unconstrained install, frozen at the smoke phase (section 7) into logs/constraints.txt.
# Every later install (a replacement pod): add  -c /workspace/ooxml-graph-paper/logs/constraints.txt
/home/bench/venv/bin/pip install -q ./meridian-docs-<PIN> python-docx requests   # NOT -e
/home/bench/venv/bin/python -c "import meridian_docs; print(meridian_docs.__file__)"   # must be site-packages, not pins/
cd /workspace/ooxml-graph-paper
ln -sfn pins/harness-<SHA>/tools tools
ln -sfn pins/harness-<SHA>/manifests manifests
ln -sfn pins/harness-<SHA>/docs docs
```

The harness starts the treatment MCP server as `sys.executable -m meridian_docs.server`, so
running the sweeps with `/home/bench/venv/bin/python` guarantees the pinned install is used.

## 6. Authenticating the CLI without credentials in any tracked file

**Decided (D-R5/D-K7, 2026-09-26): subscription OAuth token, not an API key.** `tools/usage_cap.py`
already implements the pause/resume this needs for a usage-limit hit, so no billing event is
required and the circuit breaker's exit-code-3 behaviour (section 9) is the only consequence of a
limit.

- **Subscription token** (`claude setup-token`, worked on 09-22/23): usage counts against the
  subscription, `total_cost_usd` is an API-equivalent figure, and usage limits apply (the
  circuit breaker stops the sweep at the first one, exit code 3).
- **API key** (not used): billed at about the section 13 figures; no subscription limits. Kept
  here only as the alternative that was considered and rejected.

Steps (token; an API key is handled the same way, file `api_key` instead of `oauth_token`):

1. As `bench`, on the pod: `tmux new-session -d -s auth -x 220 -y 50 "claude setup-token"`,
   then `tmux capture-pane -t auth -p | grep -A2 https://` to get the authorization URL.
2. The **author** opens the URL in their own browser and authorizes. They paste the returned
   code into the pane with `tmux load-buffer` / `paste-buffer`, then press Enter as a separate
   keypress. The operating session never types, stores or echoes the code for them.
3. Write the printed token straight to `/home/bench/.config/rerun/oauth_token` (directory mode
   `0700`, file mode `0600`, owner `bench`). Clear the pane
   (`tmux clear-history -t auth; tmux kill-session -t auth`).
   - The secret lives on the **container disk**, never on `/workspace`, the archive, the laptop,
     the repo or any log. A vanished pod needs one more OAuth round trip from the author.
4. Every launch reads it into the environment inside `launch/run.sh` (section 8), never on an
   argv.
5. **Leak check.** `run_trial` copies the whole environment into every trial and control agents
   have Bash, so an agent can read the variable and write it into its scratch files, its
   transcript or its final message. Section 11's secret scan covers every file that leaves the
   pod, including each trial's `session-transcript.jsonl`, `cli-messages.json`,
   `step-result.json` and `scratch/`. A hit stops the download: redact that file, record the
   redaction in `logs/deviations.md`, re-hash, and continue.
6. After the run: `shred -u` the secret file before teardown. The author revokes the token (or
   the API key) from their account settings.

## 7. Smoke phase (go/no-go; after the protocols are locked; never confirmatory)

1. **Environment checks.** `whoami` prints `bench`; `claude --version` equals the pin;
   `soffice --version` recorded; `claude -p "Reply with PONG" --model claude-sonnet-5
   --output-format json` returns PONG and `modelUsage` contains `claude-sonnet-5`.
2. **Tool manifest** (its sha256 goes into the provenance):
   ```bash
   /home/bench/venv/bin/python -c "import asyncio, json, meridian_docs.server as s; \
   names = sorted(t.name for t in asyncio.run(s.mcp.list_tools())); print(json.dumps(names))" \
   > /workspace/ooxml-graph-paper/logs/tool-manifest.json
   ```
   It must contain `insert_table`, `remove_table`, `move_section`, `insert_caption`,
   `remove_caption`, `insert_equation`, `remove_equation`, `insert_citation`,
   `remove_citation`, `insert_bibliography_entry` and `remove_bibliography_entry`.
3. **Smoke documents** are fixed in the lock commits: for S25, a public pool document outside
   the review queue with under 50% 12-gram overlap with every confirmatory document (S25 section
   10.2; manifest `manifests/paper-s25-smoke-document-v1.json`); for S26, one or two S7 v1
   `validation` documents, same overlap rule (S26 section 10.1; manifest
   `manifests/paper-s26-smoke-manifest-v1.json`, `s7_split: "validation"`). **No author
   document and no confirmatory document is used.**
4. **Respec smoke** (not locked commands; `SM=/workspace/ooxml-graph-paper/runs/smoke-s25-<date>`):
   ```bash
   cd /workspace/ooxml-graph-paper/tools
   /home/bench/venv/bin/python run_respec_cascade_sweep.py --check-only --run-root $SM/primary \
     --documents-manifest /workspace/ooxml-graph-paper/manifests/paper-s25-smoke-document-v1.json \
     --six-family --max-anchor-sets 1
   /home/bench/venv/bin/python run_respec_cascade_sweep.py --run-root $SM/primary \
     --documents-manifest /workspace/ooxml-graph-paper/manifests/paper-s25-smoke-document-v1.json \
     --six-family --max-anchor-sets 1 --model claude-sonnet-5 --max-workers 6 \
     --arm-order-seed 20260925004 --max-chain-attempts 2
   /home/bench/venv/bin/python run_respec_cascade_baselines.py --run-root $SM/primary \
     --baseline-run-root $SM/baselines --six-family --model claude-sonnet-5 --max-workers 6 \
     --arm-order-seed 20260925004 --max-chain-attempts 2
   ```
   (run through `launch/run.sh`-style wrapping so the secret is in the environment; section 8.3).
5. **K=4 smoke** (`--split validation`, run root `runs/smoke-s26-<date>`, otherwise the
   `s26-run` arguments with the smoke manifest).
6. **Freeze the dependency set**: `/home/bench/venv/bin/pip freeze > /workspace/ooxml-graph-paper/logs/constraints.txt`;
   its sha256 goes into the provenance.
7. **Statistics and archive dry run** on the smoke roots: the statistics scripts, then the full
   section 11 archive, secret scan, download and verification.

**Go/no-go gates.** Every item must hold; otherwise stop.

- No `harness_exception`, `infra_blocked` or `aborted_circuit_open`; every trial's
  `infra_signature` is null and `unconfirmed_infra_text` empty (or explained).
- No trial ran as root; no isolation violation.
- `modelUsage` keys as in section 2.
- Treatment table steps (1.5, 3.5) called `insert_table`/`remove_table`, changed the document,
  and have no `render_gate_errors` (the gate passed without `allow_degraded_render`).
- Every respec step directory has `step-result.json` and `session-transcript.jsonl` (or
  `cli-messages.json`); every respec chain result has `step_log`; every run_chain result has
  per-trial records under `pairs`; every manifest has `provenance` and `circuit_breaker`.
- Per-trial `total_cost_usd` and wall time within 2x of section 13.
- Archive verified locally; secret scan clean.

**A code change after the smoke phase is allowed only to fix a listed gate failure** (S25
section 10.2): logged in `logs/deviations.md`, new pins, a protocol amendment committed before
any confirmatory trial, and a new smoke phase. Nothing else changes after the lock.

## 8. Confirmatory launches

### 8.1 Extract the locked commands from the locked protocols (on the pod, as bench)

```bash
cd /workspace/ooxml-graph-paper
python3 - <<'PY'
import pathlib, re
root = pathlib.Path("/workspace/ooxml-graph-paper")
for name in ("paper-s25-respec-cascade-rerun-protocol-v1.md", "paper-s26-k4-section-reorder-confirmatory-protocol-v1.md"):
    text = (root / "docs" / name).read_text(encoding="utf-8")
    for m in re.finditer(r"```bash\n(# locked-command: ([a-z0-9-]+)\n.*?)```", text, re.S):
        body, cid = m.group(1), m.group(2)
        assert "<LOCK:" not in body and "AUTHOR DECISION" not in body, f"{cid}: unfilled placeholder"
        (root / "launch" / f"{cid}.sh").write_text(body, encoding="utf-8")
        print(cid, "->", f"launch/{cid}.sh")
PY
```

At lock time, on the laptop, the same regex applied to this runbook must give the same blocks,
byte for byte (`pixi run python`):

```python
import pathlib, re
d = pathlib.Path("docs")
pat = re.compile(r"```bash\n(# locked-command: ([a-z0-9-]+)\n.*?)```", re.S)
def blocks(f): return {m.group(2): m.group(1) for m in pat.finditer((d / f).read_text(encoding="utf-8"))}
proto = {**blocks("paper-s25-respec-cascade-rerun-protocol-v1.md"), **blocks("paper-s26-k4-section-reorder-confirmatory-protocol-v1.md")}
book = blocks("runpod-rerun-runbook-draft.md")
assert proto == book, sorted(k for k in set(proto) | set(book) if proto.get(k) != book.get(k))
print("identical:", sorted(proto))
```

### 8.2 The locked commands (copies of S25 sections 6.9 and 10.1, S26 section 3)

```bash
# locked-command: s25-check
cd /workspace/ooxml-graph-paper/tools
/home/bench/venv/bin/python run_respec_cascade_sweep.py --check-only \
  --run-root /workspace/ooxml-graph-paper/runs/rr-respec-v1/primary \
  --documents-manifest /workspace/ooxml-graph-paper/manifests/paper-s25-respec-documents-v1.json \
  --six-family --max-anchor-sets 4 \
  --expected-schedule-sha256 e59d36fe20fcd766f4e3e0967cec6d324bccf5f64d721e2d5b957f4a3a50eeeb
```

```bash
# locked-command: s25-primary
cd /workspace/ooxml-graph-paper/tools
/home/bench/venv/bin/python run_respec_cascade_sweep.py \
  --run-root /workspace/ooxml-graph-paper/runs/rr-respec-v1/primary \
  --documents-manifest /workspace/ooxml-graph-paper/manifests/paper-s25-respec-documents-v1.json \
  --six-family --max-anchor-sets 4 --model claude-sonnet-5 --max-workers 6 \
  --expected-schedule-sha256 e59d36fe20fcd766f4e3e0967cec6d324bccf5f64d721e2d5b957f4a3a50eeeb \
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
  --expected-schedule-sha256 e59d36fe20fcd766f4e3e0967cec6d324bccf5f64d721e2d5b957f4a3a50eeeb \
  --arm-order-seed 20260925004 --max-chain-attempts 2 \
  --provenance-json /workspace/ooxml-graph-paper/logs/provenance-rr-respec-v1-baselines.json
```

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

The statistics blocks `s25-statistics` and `s26-statistics` are in section 11.

### 8.3 Launching

```bash
# as bench, once: the wrapper puts the secret in the environment, never on an argv, and logs the exit code
cat > /workspace/ooxml-graph-paper/launch/run.sh <<'SH'
#!/bin/bash
set -u
ID="$1"; LOG="/workspace/ooxml-graph-paper/logs/$ID.log"
if [ -f /home/bench/.config/rerun/oauth_token ]; then export CLAUDE_CODE_OAUTH_TOKEN="$(cat /home/bench/.config/rerun/oauth_token)"; fi
if [ -f /home/bench/.config/rerun/api_key ]; then export ANTHROPIC_API_KEY="$(cat /home/bench/.config/rerun/api_key)"; fi
echo "=== $(date -u +%FT%TZ) start $ID" >> "$LOG"
bash "/workspace/ooxml-graph-paper/launch/$ID.sh" >> "$LOG" 2>&1
RC=$?
echo "=== $(date -u +%FT%TZ) end $ID exit=$RC" >> "$LOG"
exit $RC
SH
# then, one at a time, each after the previous one has ended with exit=0:
tmux new-session -d -s s25-check     "bash /workspace/ooxml-graph-paper/launch/run.sh s25-check"
tmux new-session -d -s s25-primary   "bash /workspace/ooxml-graph-paper/launch/run.sh s25-primary"
tmux new-session -d -s s25-baselines "bash /workspace/ooxml-graph-paper/launch/run.sh s25-baselines"   # within 48 h of the primary's end
tmux new-session -d -s s26-check     "bash /workspace/ooxml-graph-paper/launch/run.sh s26-check"
tmux new-session -d -s s26-run       "bash /workspace/ooxml-graph-paper/launch/run.sh s26-run"
```

Exit codes (in the log's `end ... exit=` line): **0** finished; **2** refused to start (hash,
schedule, rotation or manifest mismatch; a family with no baseline chain) or a `--check-only`
failure: stop and investigate, never delete or edit the schedule; **3** circuit breaker open:
section 9.

## 9. Checkpoint, resume and pod-vanish recovery

- Every chain writes `chain-result.json` atomically into its own chain root on the network
  volume. On relaunch with the **identical command and run root**:
  - trusted and returned unchanged: `completed`, `completed_with_failure`, `not_applicable`,
    respec `chain_broken_at_step_*`, and run_chain's `blocked_timeout`,
    `blocked_forward_failed`, `blocked_unreadable_input`, `blocked_inverse_unresolvable`.
    **Timeouts are never re-run.**
  - re-run: `infra_blocked`, the legacy `blocked`, and chains with no checkpoint (a harness
    exception, an abort, an interruption). Before the new attempt the harness itself moves the
    old chain root to `<run root>/attic/<chain_id>/<UTC timestamp>/`, and `run_trial` moves any
    non-empty trial directory it would reuse to `<run root>/attic/<trial_id>/<UTC timestamp>/`.
  - every attempt is counted in `<run root>/_chain_attempts/<chain_id>.json`. With
    `--max-chain-attempts 2`, a chain whose two chargeable attempts (chain-scope `infra_blocked`
    or `harness_exception`) are used up returns `infra_excluded`. Global signatures, breaker
    stops and interruptions are never charged.
  - the respec sweeps read the stored `anchor-schedules.json` and never re-resolve it.
- Never change a run root, never delete or move anything by hand. Every manual intervention gets
  a line in `logs/deviations.md`.
- **Circuit breaker (exit 3).** The log names the signature (`CIRCUIT BREAKER OPEN: ...`), and
  the sweep manifest records `circuit_breaker.tripped`. Wait until the limit resets or the
  outage clears (for a usage limit, the reset time the CLI reported), log it in
  `deviations.md`, then relaunch the identical command (section 8.3). If the breaker trips again
  within an hour of a relaunch, stop and tell the author.
- **Pod gone** (`GET /pods/{id}` returns 404, or the pod is missing from `GET /pods`):
  1. Check `GET /networkvolumes`: the volume is listed and its size is unchanged.
  2. Provision a new pod with the same script, the same volume, the same `dataCenterIds` and the
     same image.
  3. Redo section 5 as root, then the venv install **with `-c logs/constraints.txt`**. Pins,
     corpus and runs survive on the volume; re-check their sha256.
  4. Redo section 6 (a new token; the author has to be present).
  5. Append the new pod to `pod_history` in each provenance file.
  6. Compare the chain-result counts with the last hourly pull, then relaunch the identical
     command. The baselines must still start within 48 h of the primary sweep's end (S25
     section 3).

## 10. Progress monitoring

**Heartbeat every 15 minutes** (a local loop or a scheduled check). It must never show pass/fail
or anything per arm (S25 section 10.5, S26 section 10.3).

- `GET /pods/{id}` through a Python helper that reads `.env`: status and `costPerHr`.
- Over SSH: the tmux session is alive (`tmux ls`), and the last lines of `logs/<id>.log` (an
  `end ... exit=` line means the sweep stopped; exit 3 means section 9).
- `df -h /workspace`.
- The pooled progress script below, which reads only what the harness writes: each respec
  step's `step-result.json` (written as the step ends), each chain's `chain-result.json`
  (run_chain trials under `pairs[*].forward|inverse`, visible when the chain ends), and the
  attempt ledgers. It skips `attic/`. Install it once as `/home/bench/heartbeat.py`:

```bash
cat > /home/bench/heartbeat.py <<'PY'
#!/usr/bin/env python3
"""Pooled progress heartbeat: no arm breakdown, no pass/fail. Exit 1 when a halt signal fires."""
import argparse, collections, json, pathlib
INFRA = ("infra_blocked", "infra_excluded", "aborted_circuit_open", "harness_exception")
def load(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError): return None
def add(acc, t):
    r = t.get("claude_json_result") if isinstance(t.get("claude_json_result"), dict) else {}
    acc["trials"] += 1; acc["usd"] += float(r.get("total_cost_usd") or 0.0)
    acc["timeouts"] += bool(t.get("timed_out")); acc["rg_timeouts"] += bool(t.get("render_gate_timeout"))
    acc["infra_trials"] += bool(t.get("infra_signature"))
def scan(root, acc):
    seen = set()
    for f in root.rglob("step-result.json"):
        if "attic" in f.relative_to(root).parts: continue
        s = load(f)
        if isinstance(s, dict): add(acc, s); seen.add(str(f.parent.resolve()))
    for f in root.rglob("chain-result.json"):
        if "attic" in f.relative_to(root).parts: continue
        c = load(f)
        if not isinstance(c, dict): continue
        st = str(c.get("status")); acc["chains"][st if st in INFRA else "finished"] += 1
        for p in c.get("pairs") or []:
            for k in ("forward", "inverse"):
                t = p.get(k) if isinstance(p, dict) else None
                if isinstance(t, dict) and str(pathlib.Path(t.get("trial_root") or "-").resolve()) not in seen: add(acc, t)
    for d in root.rglob("_chain_attempts"):
        if "attic" in d.relative_to(root).parts: continue
        for f in d.glob("*.json"):
            for a in (load(f) or {}).get("attempts") or []:
                acc["ends"][str(a.get("ended_status"))] += 1; acc["charged"] += bool(a.get("counts_toward_limit"))
ap = argparse.ArgumentParser(); ap.add_argument("roots", nargs="+", type=pathlib.Path)
ap.add_argument("--expected-chains", type=int, required=True); ap.add_argument("--planned-usd", type=float, required=True)
a = ap.parse_args()
acc = {"trials": 0, "usd": 0.0, "timeouts": 0, "rg_timeouts": 0, "infra_trials": 0, "chains": collections.Counter(), "ends": collections.Counter(), "charged": 0}
for r in a.roots:
    if r.is_dir(): scan(r.resolve(), acc)
done = acc["chains"]["finished"]; prog = done / a.expected_chains; plan = a.planned_usd * prog
share = acc["timeouts"] / acc["trials"] if acc["trials"] else 0.0; infra = sum(acc["chains"][s] for s in INFRA)
halts = []
if done >= 10 and plan > 0 and acc["usd"] > 1.3 * plan: halts.append("SPEND above 1.3x plan for the progress reached")
if acc["trials"] >= 100 and share > 0.05: halts.append("TIMEOUTS above 5% of trials, pooled")
if infra > 0.05 * a.expected_chains: halts.append("infra/harness statuses above 5% of chains (check the log for exit 3 first)")
print(json.dumps({"finished_chains": done, "expected_chains": a.expected_chains, "progress": round(prog, 3),
    "infra_chain_statuses": {s: acc["chains"][s] for s in INFRA}, "ledger_end_statuses": dict(acc["ends"]),
    "chargeable_attempts": acc["charged"], "trials_seen": acc["trials"], "trials_with_infra_signature": acc["infra_trials"],
    "timeouts_pooled": acc["timeouts"], "timeout_share_pooled": round(share, 4), "render_gate_timeouts": acc["rg_timeouts"],
    "api_equivalent_usd_seen": round(acc["usd"], 2), "planned_usd_for_progress": round(plan, 2), "halt_signals": halts}, indent=2))
raise SystemExit(1 if halts else 0)
PY
# at D = 8 and N = 60 (FINAL DECISIONS 2026-09-26; section 13 base figures without smoke,
# recomputed from the unit costs of section 13: 3 author + 5 public document units):
/home/bench/venv/bin/python /home/bench/heartbeat.py /workspace/ooxml-graph-paper/runs/rr-respec-v1/primary   --expected-chains 64  --planned-usd 74
/home/bench/venv/bin/python /home/bench/heartbeat.py /workspace/ooxml-graph-paper/runs/rr-respec-v1/baselines --expected-chains 384 --planned-usd 42
/home/bench/venv/bin/python /home/bench/heartbeat.py /workspace/ooxml-graph-paper/runs/rr-k4-v1               --expected-chains 120 --planned-usd 283
# for reference, the original draft's D = 12 / N = 120 figures (no longer describing this run):
# primary --expected-chains 96 --planned-usd 433; baselines --expected-chains 576 --planned-usd 245;
# k4 --expected-chains 240 --planned-usd 566
```

- **Expected chains.** S25 primary 8 per document (8D; **64 at D = 8**); S25 baselines 48 per
  document (48D; **384**); S26 2 per document (2N; **120 at N = 60**). Planned USD scales with D
  and N (section 13). (Original draft used D = 12 / N = 120: 96 / 576 / 240; no longer this run.)
- **Halt signals** (exit 1) map to the protocols' fixed remedies (S25 section 10.6, S26 section
  10.4). A spend signal pauses the sweep for the author; the others halt it. Pause or halt =
  kill the tmux session; checkpoints stay.
- **Hourly incremental pull.** `rsync` every `chain-result.json`, `step-result.json`,
  `_chain_attempts/*.json`, manifest and log, without `.docx` and without transcripts, to
  `C:\rr\<run_id>\incremental\` on the laptop. Do not open chain results there before the
  sweep ends (no arm-level look, S25 section 11 item 5).

## 11. Statistics, archive, download and verification

After the last sweep ends (and after the smoke phase, as a dry run), on the pod, as bench:

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

The first run of each verdict script on the complete data is the verdict of record (S25 section
11, S26 section 11). Then the archive:

```bash
cd /workspace/ooxml-graph-paper
RUN=rr-all-v1; A=archive/$RUN; mkdir -p "$A"
cp logs/*.json logs/*.txt logs/*.log logs/deviations.md "$A"/ 2>/dev/null
cp -r /home/bench/.claude/projects "$A/claude-session-transcripts"   # superset of the per-trial copies; NOT ~/.claude.json or credentials
# secret scan BEFORE anything leaves the pod. runs/ holds every session-transcript.jsonl,
# cli-messages.json, step-result.json, scratch/ and attic/. The secret is read from its file, never printed.
for S in /home/bench/.config/rerun/oauth_token /home/bench/.config/rerun/api_key; do
  [ -f "$S" ] && grep -rlF -f "$S" runs "$A" && echo "SECRET FOUND -- STOP"
done
grep -rlE "sk-ant-[A-Za-z0-9_-]{10,}" runs "$A" && echo "KEY-LIKE STRING FOUND -- STOP"
# per-file manifest over EVERYTHING that is archived
find runs "$A" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$A/SHA256SUMS"
tar -cf "archive/$RUN.tar" runs "$A"          # .docx are already zip-compressed; no gzip
sha256sum "archive/$RUN.tar" > "archive/$RUN.tar.sha256"
wc -l "$A/SHA256SUMS"; du -sh "archive/$RUN.tar"
```

"Every raw result" means: every chain root (`chain-result.json`, every step or trial directory
with `doc.docx`, `step-result.json`, `session-transcript.jsonl` or `cli-messages.json`,
`scratch/` and MCP config); the baseline roots; `anchor-schedules.json` and
`anchor-schedules.meta.json`; `check-report.json`; `_chain_attempts/` and `attic/` of every run
root; every manifest and statistics file; the logs, `constraints.txt`, `tool-manifest.json` and
the provenance files; `deviations.md`. (`run_respec_cascade_sweep.py --archive ... --archive-only`
writes a subset of this for the respec roots; the tar above is the one that is verified.)
Size: about 9 MB per author-document step copy x 21 steps x 24 author chains, plus baselines and
public documents, roughly 10-20 GB.

**Laptop (Git Bash). Download to `C:` first; keep the path short.**

```bash
mkdir -p /c/rr && cd /c/rr
scp -P <port> root@<ip>:/workspace/ooxml-graph-paper/archive/rr-all-v1.tar* .    # or rsync --partial
sha256sum -c rr-all-v1.tar.sha256                  # 1. tar identical to the pod's
tar -xf rr-all-v1.tar
sha256sum -c archive/rr-all-v1/SHA256SUMS | grep -v ': OK$'   # 2. every file OK -> no output
```

Local recompute from a `git archive` of the harness pin (never the shared working tree), with
`pixi run python`, the same arguments as the locked statistics commands and the local paths
`C:/rr/runs/...` for every `/workspace/ooxml-graph-paper/runs/...` path.

Verification checklist. **All items must be ticked before teardown.**

1. The tar sha256 matches.
2. Every line of `SHA256SUMS` is OK, and the line count equals the pod's `wc -l`.
3. Counts outside `attic/`: `chain-result.json` files equal the expected chains of section 10
   (96 + 576 + 240 at D = 12, N = 120), and every sweep manifest has `circuit_breaker.open`
   false and a `provenance` block. Every respec chain result has `step_log`, and for each step id
   in it a step directory with `step-result.json` and a transcript copy; every run_chain result
   has a per-trial record for each trial it ran under `pairs`. Missing transcripts are listed,
   not fatal.
4. The statistics recomputed locally match the pod's: every p-value, point estimate, count and
   verdict field identical; bootstrap CI bounds may differ in the last digit (S25 section 6.9).
5. Copy the tar and its `.sha256` to a second location (`D:\MeridianData\ooxml-graph-paper\runs\`,
   plus an off-machine copy if available) and run `sha256sum -c` again there.
6. Register the archive with its sha256 in `paper/sources/`.

## 12. Teardown (only after section 11's checklist is complete)

1. `shred -u` the secret file(s) in `/home/bench/.config/rerun/` on the pod.
2. Terminate the pod: `DELETE /pods/{id}`, expect 204; confirm it is absent from `GET /pods`.
3. Delete the network volume: `DELETE /networkvolumes/{id}`, expect 204; confirm it is absent
   from `GET /networkvolumes`.
4. Make every call through a Python helper that loads `RUNPOD_KEY` from `.env` into memory.
   Never use `curl` with the key in a shell variable or a temp file.
5. The author revokes the token or API key.
6. Record the final pod-hours and `costPerHr` in the checkpoint doc.

## 13. Cost estimate

The model figure is the CLI's own `total_cost_usd` (API-equivalent USD, including its internal
haiku helper calls): consumed from the subscription with a token, billed with an API key.
Model: `cost_model_v2.py` in the scratchpad (this draft's earlier figures counted 20 steps and
64-trial units; they are superseded).

**Per-trial planning rates, claude-sonnet-5.** Recorded means, except where marked EXTRAP.

| Family | Control, author docs | Treatment, author docs | Control, public docs | Treatment, public docs |
|---|---|---|---|---|
| section_reorder | $0.43 / 97 s | $0.22 / 22 s | $0.35 / 85 s | $0.24 / 19 s |
| equation | $0.38 / 93 s | $0.20 / 25 s | $0.19 / 38 s | $0.17 / 15 s |
| caption | $0.19 / 39 s | $0.20 / 25 s | $0.18 / 37 s | $0.19 / 18 s |
| bibliography | $0.30 / 60 s EXTRAP | $0.21 / 24 s EXTRAP | $0.18 / 44 s | $0.19 / 15 s |
| citation | $0.25 / 45 s EXTRAP | $0.23 / 24 s EXTRAP | $0.18 / 35 s | $0.22 / 30 s |
| table_structural | $0.20 / 40 s EXTRAP | $0.21 / 24 s EXTRAP | $0.13 / 25 s EXTRAP | $0.18 / 18 s |

Author-document rates: the multi-anchor extension's author subset (RunPod, 09-19, n=16 each).
Public rates: that extension's public subset plus the 09-02 K=4 bibliography/citation run. The
09-13 S7 RunPod re-run cost about half as much per treatment trial; the newer rates are used on
purpose (the 09-19 CLI sent about 2x more uncached input). Recorded totals for scale: S7 RunPod
re-run 312 trials, $36.55, 27 min; multi-anchor extension 744 trials, $149; K=4
section-reorder v2 729 trials, $146. No per-step respec data exists from the lost run.

**Unit costs.** One (document, anchor-set) unit = both arms x (21-step chain + 6 K=1 baseline
chains of 2 trials) = **66 trials**: **$16.64** on an author document ($10.60 chain + $6.04
baselines), **$13.30** on a public document ($8.50 + $4.80). One K=4 document = 2 arms x 8
trials = 16 trials, **$4.72**.

| Scenario | Trials | Model base (incl. smoke) | Model +20% | Sweep wall | Pod budget (setup, smoke, archive, x1.5) | Compute |
|---|---|---|---|---|---|---|
| **S25, D = 8** (3 author + 5 public) -- **FINAL DECISIONS, this run** | 528 | **$116** (primary $74, baselines $42) | **$140** | about 2.7 h primary + 1.5 h baselines | about 8.9 h | about $2.18 |
| S25, D = 12 (3 author + 9 public, original draft, no longer this run) | 3,168 | $695 (primary $433, baselines $245) | $834 | 4.1 h primary + 2.3 h baselines | 13.3 h | $3.27 |
| S25, D = 13 (D-R2 = yes: 4 author + 9 public) | 3,432 | $762 | $914 | 4.5 + 2.5 h | 14.3 h | $3.51 |
| S25, D = 16 (3 + 13) | 4,224 | $908 | $1,090 | 5.3 + 3.0 h | 16.2 h | $3.99 |
| S25, D = 20 (3 + 17) | 5,280 | $1,121 | $1,345 | 6.6 + 3.7 h | 19.1 h | $4.71 |
| S25, D = 12, control respec steps at 1.5x cost | 3,168 | $812 | $975 | as D = 12 | 13.3 h | $3.27 |
| **S26, N = 60** -- **FINAL DECISIONS, this run** | 960 | **$293** (sweep $283) | **$351** | 2.9 h | 8.1 h | $1.99 |
| S26, N = 120 (original draft, no longer this run) | 1,920 | $576 (sweep $566) | $691 | 5.8 h | 12.4 h | $3.05 |
| **Both, D = 8 + N = 60, one pod session -- FINAL DECISIONS, this run** | 1,488 | **$409** | **$491** | about 4.2 h + 2.9 h | about 14.8 h | about $4.17 |
| Both, D = 12 + N = 120, one pod session (original draft, no longer this run) | 5,088 | $1,271 | $1,525 | 12.2 h | about 23.5 h | about $6 |

**Budget ceiling (D-R10/D-K8, decided 2026-09-26).** $150-450 is the expected total for the
combined D = 8 + N = 60 run (the $409/$491 row above sits inside that range, with headroom for the
D = 8 row's own smaller documents costing somewhat more per trial than assumed, and for the
"control respec steps at 1.5x cost" scenario, which at D = 8 would be proportionally about
$116 x 1.17 = $136 base). **Hard abort at 3x the top of that range = $1,350**, distinct from the
existing infrastructure circuit breaker: `tools/run_sweep_to_completion.py` sums
`claude_json_result.total_cost_usd` across every `chain-result.json` under the watched run roots,
checked between relaunch rounds, and halts before any further relaunch if the running total would
exceed $1,350, writing `cost-circuit-breaker.json` with the running total and the reason. This is
a stop-relaunching check, not a mid-sweep kill switch inside a single launch; a single launch that
is already running when the total crosses the threshold is not interrupted, only the next relaunch
is refused.

Assumptions (planning values, not quotes): model and CLI as in section 2 with per-trial token
use like 09-19's; a respec step costs the same as the isolated trial of its family (control
steps on a grown document may cost more: see the 1.5x row); every selected document has 4
usable anchor-sets; 6 workers at 80% parallel efficiency; 2.5 h fixed for provisioning, setup,
smoke, archive, verification and teardown (plus 1 h for the second smoke in the combined row);
x1.5 contingency for one pod-vanish recovery and stragglers; pod $0.24/hr (recheck the returned
`costPerHr`); volume $0.07/GB-month assumed; +20% model contingency for reruns and a repeated
smoke. The critical path (the longest control respec chain, 21 steps x about 65 s, about 23
min) is far below the sweep time, so wall time is throughput-bound. Excluded: laptop time and
any subscription fee.

## 14. Cost-control plan

1. Approve a budget before provisioning (D-R10 / D-K8): model spend at the chosen row's "+20%"
   figure; compute capped at $10.
2. Dry run first (`--dry-run` on the provisioning copy), then the smoke phase. No confirmatory
   launch until every smoke gate passes.
3. One pod for all sweeps, one dedicated volume; the pod exists only from setup to verified
   archive.
4. The 15-minute heartbeat carries the pooled API-equivalent spend and signals at 1.3x plan for
   the progress reached; the author decides (S25 section 10.6).
5. On a subscription token, a usage limit trips the circuit breaker (exit 3); relaunch after the
   reset. Consider running S26 in a separate window from S25; the smoke gives a per-trial
   reading.
6. Teardown follows immediately after the section 11 checklist. Both DELETE calls confirmed with
   204 and then with a listing, the same day.
7. After the run, list the account's pods and volumes. Nothing from this run may remain, and
   nothing from other projects gets touched.
8. Never retry by hand. The harness re-runs only `infra_blocked` chains and harness exceptions,
   within `--max-chain-attempts 2`, and records every attempt in `_chain_attempts/`.

## 15. Risks and decisions for the author

- **Pin choice (section 3.1).** `main` lacks the validator fix, so pinning `f92d2710` would make
  `move_section` refuse the author documents. Decide D-R4 before the eligibility recomputation
  the protocols require at the pin.
- **Model change.** The lost respec run was haiku. The Sonnet re-run is a new preregistered
  experiment; it does not overwrite the haiku data, which stay reported at every level with
  their post-hoc re-analysis labelled as such (S25 section 12).
- **D and N.** Power for the exact S25 rule is in S25 section 9 (D = 12 is enough only if the
  lost run's effect and freeze pattern recur; 16-20 is more robust); power for S26 is in S26
  section 9 (N = 120 for 0.80 at half the observed effect). Both are fixed at the lock; adding
  documents after seeing results is optional stopping and is not done.
- **Integrity.** Report every preregistered outcome whatever it shows; the first computed
  verdict of each protocol version is final (S25 and S26 section 11); list every deviation.
- **Usage limits.** Six concurrent Sonnet sessions for several hours may hit them; the circuit
  breaker makes a limit a pause, never a scored failure.
- **Pod vanishing** has happened 4 times (09-12, 09-13, 09-20, 09-23). Expect at least one
  recovery; the wall budget includes it.
- **Secrets in trial environments.** Control agents can read environment variables; the
  pre-download secret scan in section 11 is mandatory.
- **Local disk.** `D:` had sustained USB I/O errors on 09-20, so verify on `C:` first.
