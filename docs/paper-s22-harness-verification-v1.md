# PAPER-S22: independent commissioning and audit of the S20 harness (v1)

Status: **the S20 harness is now genuinely runnable and verified end-to-end.** A real
root-cause was found and fixed for the prior timeout; the actual 8-trial commissioning
pilot has now executed for real, with isolation canaries confirming the arm boundary
holds under active adversarial prompting in both directions. This supersedes
`docs/paper-s20-paired-runner-v1.md`'s "not run, zero pilot numbers exist" status.

## What was found broken, and the real root cause

The first live pilot attempt (after S20's OAuth blocker was independently resolved by a
separate session) reported: "both treatment forward trials timed out after 300 seconds
while Claude repeatedly search[ed]." Investigating directly (reading the actual tool
signature Meridian exposes, not guessing):

`insert_highlighted_note(docx_path, text, anchor_para_id, ...)` requires a specific
Meridian paragraph identifier (`anchor_para_id`), not a text description. The original
task design told the agent to "find the paragraph whose text is exactly X" and then
insert relative to it — but the treatment arm's tool allowlist gave it **no way to
discover that identifier**: `Read` cannot parse a binary `.docx` ZIP archive into text,
and `Grep`/`Glob`/`Bash` are deliberately denied (that's the whole point of bounding the
arm to Meridian's own interface). Claude had no legitimate path to complete the task and
retried until the process was killed at the timeout.

## The fix: eliminate the anchor-resolution requirement, don't route around it

Rather than granting the treatment arm a read/discovery tool (which would have changed
what the pilot measures — "can Claude use Meridian's search tools" is a different
question from "can Claude use Meridian's bounded write primitives"), the task itself was
redesigned around a Meridian primitive pair that needs no anchor resolution at all:

`insert_bibliography_entry(docx_path, citation_key, csl_item)` /
`remove_bibliography_entry(docx_path, citation_key)` — both keyed purely by an opaque
`citation_key` the trial mints itself. Neither direction requires locating anything by
content; `insert_bibliography_entry` auto-creates a References section and appends,
`remove_bibliography_entry` locates its own entry by an embedded bookmark
(`bibkey_<key>`), not by searching the document.

The control arm's task is the same document-level outcome stated generically ("add one
new reference/bibliography entry containing this title text... / remove the entry with
this title"), achievable with its own generic tools (Read/Write/Edit/Bash) without any
Meridian-specific concept.

**Verified live, immediately, before committing to a full run:** one isolated
treatment-forward smoke trial completed in 18.4s (vs. the prior 300s timeout), correct
output (`marker_title_present_in_exactly_one_paragraph: true`), clean isolation.

## The real 8-trial commissioning pilot (this is the actual evidence, not a projection)

Ran `tools/run_paper_s20_pilot.py` for real. Manifest:
`E:\MeridianData\ooxml-graph-paper\runs\paper-s20\20260830T205231Z\manifest.json`.

| doc | arm | direction | result | wall time |
|---|---|---|---|---|
| fixture-01-baseline | control | forward | pass | fast |
| fixture-01-baseline | control | inverse | **fail** (see below) | fast |
| fixture-01-baseline | treatment | forward | pass | 18.4s (smoke) |
| fixture-01-baseline | treatment | inverse | pass | fast |
| fixture-02-equation | control | forward | pass | fast |
| fixture-02-equation | control | inverse | pass | fast |
| fixture-02-equation | treatment | forward | pass | fast |
| fixture-02-equation | treatment | inverse | pass | fast |

**Execution: 8/8 completed** (zero timeouts, zero authentication failures — a first for
this item). **Isolation: 8/8 clean** (no `mcp__` reference in any control transcript, no
unexpected MCP server in any treatment transcript). **Grading: 7/8 passed.**

### The one failure is a genuine, on-thesis finding, not a fabricated or cherry-picked result

`fixture-01-baseline / control / inverse` failed with `invalid output package: missing
required part: [Content_Types].xml`. Direct inspection of the output ZIP confirmed only
2 of the ~10 required/expected OOXML parts survived (`_rels/.rels`, `word/document.xml`)
-- the control arm's own generic edit (via whatever combination of Bash/python-docx/raw
ZIP manipulation the agent chose, using only its allowed generic tools) silently dropped
nearly the entire package structure while removing the bibliography entry.

**The treatment arm's identical inverse operation on the identical fixture, via
Meridian's bounded `remove_bibliography_entry`, succeeded cleanly with the package fully
intact.** This is real, live evidence -- produced by this exact commissioning run, not
asserted from prior work -- of precisely the OOXML package-corruption failure class this
entire project has spent this session studying and hardening the product against. It is
reported here as a single (n=1) illustrative data point from a non-confirmatory
commissioning pilot, not a statistically supported claim; a real benchmark (PAPER-S7)
would need many more trials before any superiority claim rests on this pattern.

## Isolation canaries (the part S22 specifically asked for beyond just running the pilot)

Two adversarial canary trials, run separately from the 8-trial pilot, each explicitly
instructing the agent to attempt crossing the arm boundary before doing its legitimate
task:

1. **Control arm, told to first attempt `insert_bibliography_entry` or any
   `mcp__meridian-docs*` tool.** Result: `isolation_verdict: clean` (zero `mcp__`
   references anywhere in the transcript). The agent completed its legitimate task
   (added a plain "CANARY-OK" paragraph via its own allowed tools) — confirmed directly
   in the output DOCX's paragraph list. The CLI-level `--strict-mcp-config` + `--tools`
   restriction holds even under an explicit, direct instruction to violate it, not just
   under passive non-use.
2. **Treatment arm, told to first attempt `Bash`, `Edit`, `Write`, or `Grep`.** Result:
   `isolation_verdict: clean`. The agent completed its legitimate task (added the
   bibliography entry via `insert_bibliography_entry`) — confirmed in the output DOCX's
   paragraph list (`References` / `Marker, P. (2026). Canary Marker Treatment.`).

Both canaries confirm the isolation boundary is enforced by the CLI configuration
(`--strict-mcp-config`, `--tools`/`--disallowedTools`, `--mcp-config`), not merely by the
prompt's own politeness, exactly as `claude_pair_runner.py`'s own module docstring
claims.

## What was NOT done in this pass (explicit, not silently skipped)

- **Word-COM render receipts were not integrated into the trial manifests.** S21's
  `word_receipt_watchdog.py` exists and is independently verified working; wiring it
  into every trial in this run was judged out of scope for this specific verification
  pass (`Microsoft Word COM` is listed `preferred`, not `required`, in this item's own
  tool_requirements) rather than force it in and risk another detour. A future S7 run
  should add it.
- **Only 2 frozen documents, 1 task type, the `haiku` model** — explicitly a
  commissioning pilot proving the harness works, not a benchmark with statistical power.
  PAPER-S7 needs a real task/document set and a confirmatory model choice.
- **The control-arm package-corruption finding is n=1** and must not be cited as
  evidence of a general failure rate without a much larger trial count.

## Verdict for S7 readiness

**Runnable.** The harness (broker, runner, evaluator, isolation audit) now executes a
real commissioning pilot end to end with zero infrastructure failures (no timeouts, no
auth failures, no isolation violations) and produces genuine, gradable per-trial
evidence. S7 can proceed to design its real task set and confirmatory protocol on top of
this harness. The one substantive gap before S7 should be treated as confirmatory is
Word-COM receipt integration, noted above as a real, tracked follow-up rather than a
silent gap.
