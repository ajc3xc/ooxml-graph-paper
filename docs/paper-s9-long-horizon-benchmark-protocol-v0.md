# PAPER-S9: fast long-horizon DOCX writing benchmark protocol, with milestone Word validation (v0)

Status: protocol design + tool-capability investigation. **No benchmark trial has been run.**

**Update (2026-08-30, later same day):** the validator gap this document found in §5/§6.2 is
now fixed in the parent repo. `validate_docx_package()` had two real blind spots: an
`if not rel_ids: continue` guard that skipped the dangling-relationship-reference check
entirely whenever a part's own `.rels` file was missing or declared zero relationships
(exactly the adversarial case below), and no check at all for a ZIP containing the same part
name twice. Both are fixed in
`extensions/meridian-docs/meridian_docs/ooxml_integrity.py` (parent repo commit `563b9d68`),
with new regression tests in `test_ooxml_integrity_contract.py`, and independently re-verified
by re-running the exact two adversarial constructions below against the fixed validator via
`tools/s9_validator_probe.py` (this repo) -- both now correctly report `ok: false` with the
specific issue code (`dangling_relationship_reference`, `duplicate_zip_part`); the good fixture
still reports `ok: true`. Fresh output retained at
`E:\MeridianData\ooxml-graph-paper\manifests\paper-s9-validator-probe-postfix.json`. This closes
the "fast gate has known blind spots" caveat for these two specific failure modes -- it does not
claim the fast validator now catches every possible structural regression, only these two,
previously-demonstrated ones.
Every fact below is either (a) a design decision this document is making, (b) a pointer to an
already-frozen decision in another doc, or (c) a probe this session ran itself today
(2026-08-30), with its exact command, output, and file path given so it can be re-run and
checked rather than trusted. Nothing here is a benchmark result.

This is the protocol PAPER-S7 ("paired Claude without-versus-with Meridian DOCX editing and
reversal study") needs before it can execute. A same-day preflight audit of S7
(session `a104b61d-34cd-46da-b629-92b90408b4ba`, diagnostic task `dbded845`) found "no paired
Claude control/treatment broker, fresh-process runner, task/inverse generator, external
evaluator, isolation auditor, or trial manifests exist" -- this document does not build those
(that is PAPER-S20's CODE scope: "implement symmetric Claude DOCX broker, fresh-process
runner"), it specifies what they must implement and records which of their load-bearing
primitives already work today versus which are blocked, with evidence.

## 0. This is a fourth, distinct claim -- do not fold it into Claims 1-3

`comparator-contract-v0.md` §7.2 and `docs/paper35-final-gate-v0.md` already define and evidence
three claims, all about **extraction/fidelity**: native OOXML/OMML preserves Word structure
(Claim 1), native extraction beats generic parsers (Claim 2), native OOXML exposes information
unavailable to rendered-PDF document-AI (Claim 3). This item's own track field is
`"primary product benchmark design"`, and its notes describe a different comparison entirely:
**same Claude model, same starting `.docx`, same task -- Claude editing it without Meridian's
MCP tools versus Claude editing it with them.** That is an end-to-end agentic-writing/editing
comparison, not an extraction-accuracy comparison. It has its own success criteria (did the
edit happen correctly, does the file stay Word-openable, is the edit actually reversible) and
its own failure modes (an agent corrupting the package, drifting across a long session, or
silently producing a plausible-looking but structurally wrong result). Calling this "Claim 4"
anywhere in future paper text is a placeholder, not something this document decides on the
paper's behalf.

## 1. The paired design

- **Unit of comparison**: one `(document, task)` pair, run twice from the same starting
  `.docx` bytes -- once in a **control** condition (Claude with only generic file/editing
  tools, no Meridian MCP surface) and once in a **treatment** condition (Claude with the
  Meridian Docs MCP tools available). Same model, same prompt template, same tool budget cap,
  same task description, in both arms. Model and prompt are recorded verbatim per run, per
  `comparator-contract-v0.md` §5 ("No model is called 'latest' without a dated version
  record.").
- **Forward + inverse task pairs, not forward tasks alone.** Every mechanically generated
  forward task (e.g. "insert a numbered table of the following data before the section titled
  X", "add a citation for reference Y after paragraph Z") is paired with an explicit inverse/
  reversal task ("now remove exactly the table you just inserted, restoring the document to its
  prior structure"). The forward task alone can only measure "did the edit appear to work";
  the inverse task is what actually tests whether the agent's own edit was clean enough to be
  mechanically undone -- a direct, cheap proxy for whether the edit corrupted or drifted the
  document's structure in a way that only shows up later. This reuses, rather than re-derives,
  the round-trip fragility already documented in `word-roundtrip-preservation-contract-v0.md`
  and `benchmark-preregistration-v0.md` §7 (Word rewrites every `w14:paraId`/`textId` on a
  human-driven round trip) -- a long-horizon agent session is exactly the setting where that
  kind of drift compounds silently across many turns.
- **Task generation is mechanical, not hand-written per document.** A small set of parameterized
  task templates (insert/remove table, insert/remove citation, insert/remove caption, insert/
  remove cross-reference, insert/remove tracked-change edit, reorder a section and reorder it
  back) are instantiated against each document's actual structure (using
  `get_structure`/`document_outline`-style introspection to find valid insertion points), so the
  task set scales with corpus size without per-document authoring effort, and so the same
  template family is comparable across strata. Hand-written, document-specific tasks may still
  exist for the tier-1 fixture regression documents (per §2 below) but must not be the only
  source of tasks for the heterogeneous development/validation/primary-holdout documents.

## 2. Corpus role: general research controls first, Meridian fixtures are regression-only

Per this item's own notes, correcting an easy failure mode: **the corpus must be heterogeneous
across document family, author/source, style, layout, complexity, and formatting conventions,
and every document gets the same general research controls** (paired forward/inverse tasks,
same split rules, same audit log). The existing Meridian-specific corpus -- the 127-document
gold set with its hand-authored OMML/OOXML stress fixtures and the MS-thesis formatting fixture
(`docs/gold-corpus-status-v0.md`, `docs/paper29-corpus-audit-v0.md`) -- is **retained as
regression coverage** (it already has hashes, render receipts, and known structural edge cases
worth re-exercising), but it must not be the corpus this benchmark's headline numbers are
computed from, and it must not be used to claim a universal result. PAPER-S12's own exposure
audit (in progress, item `485bc551-...`) found this same 127-document set has real prior scorer
exposure and incomplete license mapping for a clean holdout -- an independent reason, on top of
the heterogeneity requirement, that this pool cannot double as the primary evaluation corpus
for this specific benchmark.

## 3. Split terminology and leakage rule

Per this item's notes (as corrected by PAPER-S16's methodology item, `43579e82-...`, which
supersedes the "development/hard/holdout" phrasing that also appears earlier in this same
sprint item's notes): **use development, validation, and primary-holdout terminology; do not
construct a development-vs-hard ablation.** No model weights are being trained here, so there
is no train/test split in the ML sense -- "split" means staged disclosure order, exactly as
`benchmark-preregistration-v0.md` §3 already defines it for the extraction benchmark (smoke →
scale-up → final). This benchmark reuses that same three-stage discipline:

- **Development** documents: used to debug the task generator, the broker, and the fast
  validator itself. Freely re-run, freely inspected.
- **Validation** documents: run once the harness is believed correct, results inspectable, no
  further harness changes made in response to a specific validation-slice failure without
  re-declaring it development data.
- **Primary holdout**: run exactly once per frozen harness/prompt version, reported whether the
  result is favorable or not.
- **Leakage rule (from this item's own notes, stated plainly because it is easy to get backwards):
  keep near-duplicates, same-source documents, and derivative versions of one another in the
  SAME split.** A document and a near-duplicate of it must never land on opposite sides of a
  split boundary -- that would let the treatment or control condition "learn" the document
  family across the split. This is a document-family-level split, not merely a document-level
  split (`comparator-contract-v0.md` §4's "split by document, never by page" is necessary but
  not sufficient here).

## 4. Round-trip limits and long-horizon session structure

"Long-horizon" here means the harness deliberately runs many forward/inverse task pairs in
sequence against the same document within one trial, to see whether quality degrades as the
session lengthens -- not a single one-shot edit. Two distinct kinds of "round trip" must not be
conflated when the harness is built:

1. **Task round trips**: how many forward+inverse pairs run in one trial before it ends. This
   is the actual independent variable of "long-horizon" and should be swept (e.g. 1, 4, 16 pairs)
   rather than fixed at one value, so degradation-with-length is an observable curve, not a
   single point.
2. **Process/session round trips**: how many times the harness tears down and restarts the
   agent process and/or reopens the `.docx` from disk between task pairs. A control-arm agent
   without Meridian's live-document MCP tools will likely re-open the file (via whatever generic
   tool it has) on every turn; a treatment-arm agent may hold a live document session across
   turns. **This is exactly the axis PAPER-16's finding warns about** (a `w14:paraId` rewrite on
   every Word-mediated round trip): if the control arm's task naturally forces more
   process/session round trips than the treatment arm's does, an observed treatment advantage
   could be confounded with "fewer round trips" rather than "better tool support" for the same
   number of round trips. **The broker (PAPER-S20) must record and pin the round-trip count per
   arm per trial as its own logged variable**, not leave it as an implicit side effect of how
   each arm happens to work, so this confound can be checked rather than assumed away.
3. **A hard round-trip/turn budget cap must exist for every trial** (both a tool-call budget and
   a wall-clock/cost budget, mirroring `comparator-contract-v0.md` §3's efficiency accounting) so
   a stuck or looping agent cannot silently consume unbounded runtime or spend -- this is what
   `--max-budget-usd` (see §6.2) and a fixed max-turns setting are for.

## 5. Two-tier verification: fast per-step validator, Word COM only at milestones

The title's "fast" and "milestone Word validation" are both load-bearing constraints, not
decoration: Word COM is the canonical render/openability authority
(`comparator-contract-v0.md` §1.C, `runtime-capability-contract-v0.md`), but it is a real
external process with meaningful per-call latency and a documented history of leaving orphaned
`WINWORD.EXE` processes behind if not carefully watchdogged (`tools/word_receipt_watchdog.py`,
written for exactly this reason under PAPER-S21). Calling it after every single agent tool call
in a long-horizon, many-round-trip trial would make the benchmark slow and would multiply the
process-leak surface by the number of steps. The design is therefore two-tier:

- **Per-step (fast)**: after every atomic edit operation, run the existing static OOXML/package
  validator (`meridian_docs.docs_intel.ooxml_integrity.validate_docx_package`, exercised via
  `scripts/check_acceptance_gate.py`'s own `check_package_integrity` pattern) against the
  in-progress package bytes. No Word process involved; this is the "fast" per-operation gate.
- **Milestone (Word COM)**: at fixed checkpoints -- start of trial, after every forward/inverse
  pair completes (not after every raw tool call), and at trial end -- run a retained,
  watchdog-wrapped Word COM render (`tools/retained_render_receipt.py` +
  `tools/word_receipt_watchdog.py`) and keep the receipt. A trial whose fast-validator checks all
  pass but whose milestone Word render fails (or whose milestone page/text/openability checks
  regress from the previous milestone) is a genuine finding about that arm, not a harness bug to
  paper over.

**A load-bearing gap found today, not assumed:** this session ran the real validator against a
known-good fixture and two distinct adversarial fixtures it constructed itself (script and raw
output below, also retained at
`E:\MeridianData\ooxml-graph-paper\manifests\paper-s9-validator-probe.json`). The validator
correctly accepted the good fixture, but **also reported `ok: true` with zero issues/warnings
on both adversarial fixtures** -- one containing a dangling relationship reference
(`r:id="rId99"` on a `<w:drawing>` with no matching entry in `word/_rels/document.xml.rels`),
and one containing a duplicate ZIP part name (`word/document.xml` written twice with different
content). This is a **replication, with fresh direct evidence, of an already-documented gap**
(`ooxml-package-safety-audit-v0.md`; also named in `benchmark-preregistration-v0.md` §7's failure
taxonomy: "duplicate ZIP part name (last-write-wins on read, never healed on write)"), not a new
discovery -- but it matters concretely for this protocol's design: **the fast per-step validator
cannot be trusted, on its own, to catch every structural regression an agent could introduce
between milestones.** Milestone cadence (how many task pairs elapse between Word COM checks)
must therefore be chosen knowing the fast gate has real, specific blind spots, not treated as an
equivalent-but-cheaper substitute for it.

Validator probe script (`s9_validator_probe.py`, run via
`pixi run python <script>` from this repo root; imports
`meridian_docs.docs_intel` read-only, modifies nothing):

```python
good_report = docs_intel.ooxml_integrity.validate_docx_package(good_bytes)
dangling_report = docs_intel.ooxml_integrity.validate_docx_package(dangling_bytes)
duplicate_report = docs_intel.ooxml_integrity.validate_docx_package(duplicate_bytes)
```

Actual output (`paper-s9-validator-probe.json`, generated 2026-08-30):

```json
{
  "good_fixture": {"ok": true, "verdict": "as_expected"},
  "adversarial_dangling_relationship_ref": {"ok": true, "verdict": "unexpected_ok_true_on_adversarial_input"},
  "adversarial_duplicate_zip_part": {"ok": true, "verdict": "unexpected_ok_true_on_adversarial_input"}
}
```

## 6. Tool-requirement verification run today (2026-08-30)

This item's `tool_requirements` named three required tools, each with its own verification
instruction. All three were actually exercised this session, not assumed from prior sessions'
notes -- results below, evidence retained under
`E:\MeridianData\ooxml-graph-paper\manifests\`.

### 6.1 Word COM renderer -- WORKING, fresh receipt produced

Verification instruction: "Render a fresh fixture and retain a provenance-bound receipt."

Ran `pixi run python tools/word_receipt_watchdog.py <fresh 977-byte fixture> <out_dir> --timeout 90`
against a fixture built by this session
(`E:\MeridianData\ooxml-graph-paper\manifests\paper-s9-fixtures\s9-word-com-probe.docx`,
`sha256=15bd312b007933393a8d0a8f521412a145ac5652bbe00ed2d8b809039522a394`). Full receipt retained
at `E:\MeridianData\ooxml-graph-paper\manifests\paper-s9-word-com-receipt.json`:

```json
{
  "render_receipt": {
    "renderer": "word-com", "status": "rendered", "exit_status": "ok",
    "word_version": "16.0", "word_build": "16.0.20326", "page_count": 1,
    "output_hash_sha256": "672072ce9a65883dd9c7c745f284feca12d6d7e02f6c333ab1b95c0f154aac82",
    "output_size_bytes": 18216, "cleanup_status": "clean"
  },
  "orphan_diagnostics": {
    "owned_pid_status": "unattributed_new_process",
    "cleanup_attempts": [{"pid": 28452, "action": "terminated", "confirmed_exited": true}],
    "cleanup_complete": true
  }
}
```

One pre-existing `WINWORD.EXE` (pid 33628, from an unrelated concurrent session on this
machine) was correctly left untouched. Word COM is confirmed working end-to-end, including
watchdog cleanup of the process this probe itself spawned, for use as the milestone renderer
in §5.

### 6.2 OOXML/package validator -- WORKING, but with the gap in §5

Verification instruction: "Run validator against a known-good and adversarial DOCX fixture."
Done; see §5 above and `paper-s9-validator-probe.json`.

### 6.3 Agentic model harness -- BLOCKED on this host today, reproducibly

Verification instruction: "Run one fixed task with pinned model/prompt/tool budget." The `claude`
CLI (v2.1.226, confirmed via `claude --version`) does support the needed primitives for a fixed,
pinned, budget-capped run: `-p`/`--print` (non-interactive), `--model <alias>`, `--max-budget-usd
<amount>`, `--output-format json`, `--disallowedTools`/`--allowedTools`, `--session-id`. This
session attempted the simplest possible instantiation -- a fresh, isolated `claude -p` subprocess
with a trivial fixed prompt, `--model haiku`, `--max-budget-usd 0.02`, run from a scratch
directory outside both this repo and the parent Meridian repo:

```
claude -p "Reply with exactly this text and nothing else: PROBE_OK" \
  --model haiku --max-budget-usd 0.02 --output-format json \
  --disallowedTools "Bash Edit Write Read WebFetch WebSearch Grep Glob"
```

Both this attempt and a variant without `--setting-sources`/`--strict-mcp-config` restrictions
failed identically:

```json
{"is_error": true, "total_cost_usd": 0, "terminal_reason": "api_error",
 "result": "Failed to authenticate: OAuth session expired and could not be refreshed"}
```

Full evidence, both attempts, retained at
`E:\MeridianData\ooxml-graph-paper\manifests\paper-s9-harness-auth-probe.json`. Root cause,
directly inspected rather than guessed: this session's own process carries
Claude-Agent-SDK-managed auth env markers (`CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH`,
`CLAUDE_CODE_HOST_SESSION_ID`, `CLAUDE_CODE_MESSAGING_TOKEN`, ...) that a bare `claude -p`
subprocess does not get routed through; that subprocess falls back to the plain OAuth credential
cache at `C:\Users\13144\.claude\.credentials.json`, whose modify time (2026-08-26) is four days
stale as of this probe (2026-08-30) and which a non-interactive invocation cannot itself refresh
(refreshing needs an interactive browser login, which this investigation did not attempt --
that is a real human/credential gate, not something an agent should paper over).

**This directly confirms and root-causes the same-day S7 preflight finding** ("no ... fresh-
process runner ... exist"): the blocker is not merely that nobody has written the broker code
yet, it is that the most direct fresh-process implementation cannot authenticate at all on this
host right now. **PAPER-S20's broker cannot be validated end-to-end until a human refreshes this
host's `claude` CLI login (an interactive step, out of scope for this session and for any
autonomous agent under this project's own credential-handling rules) --** or until it is
confirmed that the broker will instead run as an in-process Agent SDK session (inheriting this
session's own working auth) rather than a bare CLI subprocess, which is an architecture decision
for PAPER-S20 to make explicitly, not default into.

## 7. Audit log schema (per trial)

Every trial (one document × one task-pair-count × one arm) must log, at minimum: document id +
source hash, task template id and its concrete instantiation (parameters used), arm
(`control`/`treatment`), model + prompt template version, tool budget cap and actual spend
(`total_cost_usd`, tokens, per `comparator-contract-v0.md` §3), turn count and process/session
round-trip count (§4), per-step fast-validator verdicts, milestone Word-COM receipt hashes and
verdicts (§5, §6.1), and a final classification into the existing failure taxonomy
(`comparator-contract-v0.md` §3 + `benchmark-preregistration-v0.md` §7's consolidated table --
`crashed`, `timed_out`, `malformed_input`, `not_applicable`, `not_run`, `scored`, plus this
paper's own `package_render_divergent` category, which §5's validator gap makes newly relevant
here too). Aggregate and per-stratum reporting (document family/source/style/layout/complexity)
per this item's own notes; no pooling of strata into a single number that hides which document
families the result actually holds for.

## 8. Open items this document does not resolve

- **The broker, fresh-process runner, task/inverse generator, external evaluator, and isolation
  auditor themselves are unbuilt** -- PAPER-S20's scope, informed by §4's round-trip-confound
  requirement and §6.3's auth blocker.
- **The actual heterogeneous corpus for this benchmark is not assembled.** §2 names what it must
  NOT be (the existing 127-document Meridian-fixture pool as a universal claim); assembling the
  real one is not this item's scope.
- **Milestone cadence (how many task pairs between Word COM checks) is not numerically fixed
  here.** §5 gives the reasoning constraint (the fast gate has known blind spots); the actual
  number is a tuning decision for whoever runs the first development-slice trials.
- **The external/independent evaluator** that judges whether a forward task was correctly
  performed (beyond "did the file stay valid/openable") is undesigned -- this document only
  specifies the structural/openability verification tier (§5), not a content-correctness judge.

## 9. What this document does not claim

No forward or inverse task has been run against any real document by any Claude arm. No
control-vs-treatment comparison exists. The only things demonstrated to work today are: Word COM
rendering with a retained, watchdog-cleaned receipt (§6.1); the existing fast structural
validator, including a real, reproduced gap in what it catches (§6.2, §5); and that a bare `claude
-p` subprocess is currently blocked by a stale host OAuth credential (§6.3). All three are
genuine, reproducible findings from this session's own commands, not carried over unverified from
any other session's notes.
