# PAPER-S22: independent commissioning and audit of the S20 harness (v1)

## CORRECTION (2026-08-30, later same day): the original "8/8 passed" claim below is wrong

While building PAPER-S7's long-horizon (K-pair) extension, a K=4 bibliography chain smoke
test surfaced a real evaluator gap: `docx_trial_evaluator.grade_inverse_trial` checked "the
marker is gone" and "no ORIGINAL paragraph was lost," but never checked for an UNEXPECTED
paragraph being left behind. `insert_bibliography_entry` locates-or-CREATES a "References"
heading paragraph the first time it runs on a document that doesn't have one yet;
`remove_bibliography_entry` only ever removes the entry it added, never that shared heading
-- a reasonable design (you would not want the whole References section auto-deleted just
because its last entry was removed), but it means the forward+inverse pair, as this task
was originally worded, is NOT a true document-level round trip on a virgin document: a
"References" heading is left behind permanently after the first cycle.

The evaluator was fixed (added an `exact_paragraph_list_restored` check) and used to
RE-GRADE the actual saved output `.docx` files from both real pilot runs below (no new API
calls -- these are the same bytes already on disk, re-evaluated):

| Run | Old reported pass | Corrected pass | What changed |
|---|---|---|---|
| `20260830T205231Z` (control-arm corruption run) | 7/8 | **4/8** | All 4 forwards still pass. `control/inverse` still fails (real package corruption, unaffected by this fix). The other 3 inverses (`treatment/inverse` fixture-01, `control/inverse` and `treatment/inverse` fixture-02) flip pass->fail: each left a `References` heading behind. |
| `20260830T213803Z` (Word-COM-receipts run) | 8/8 | **4/8** | All 4 forwards still pass. All 4 inverses flip pass->fail, all for the identical `References`-heading reason. |

**This affects both arms equally** -- control and treatment both leave the same heading
behind, because it is a property of the TASK WORDING (the inverse instruction says "remove
that entire reference entry... paragraph," never "remove the References section"), not of
which tool implementation performed it. It therefore does not change the control-vs-treatment
comparison or invalidate the earlier, separately-diagnosed OOXML-corruption finding (a
different failure mode entirely, in a different check that runs before the paragraph-list
comparison). It does mean every "8/8"-style claim below and in this session's chat history
overstated how many trials achieved an exact document-level round trip -- the true number,
under a complete evaluator, was 4/8 both times. Corrected pass rate, root cause, and
re-grading method are retained here rather than silently edited into the numbers below, per
this project's own standing rule against quietly adjusting a reported result.

The fixed evaluator (`tools/docx_trial_evaluator.py`, PAPER-S7) is now the one used for all
new S7 trials; the historical numbers below are left as originally written, with this
correction as the authoritative amendment.

---

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

**Root cause, found by reading the trial's own retained Claude Code session transcript
(2026-08-30, later same day)** -- not guessed: the control-arm agent unzipped the docx,
edited `word/document.xml` with a Python script (correctly), then re-zipped it. Its first
`zip`/`cp` attempts appear to have failed silently (no `zip` binary producing the expected
archive in that shell), so it fell back to PowerShell's `Compress-Archive -Path
'[Content_Types].xml','_rels','word' ...`. `-Path` performs **wildcard** resolution, and
`[Content_Types]` is valid PowerShell wildcard syntax for a character class (any single
character from the set `C,o,n,t,e,_,T,y,p,s`) -- it does not match the literal file named
`[Content_Types].xml`. That parameter silently failed to resolve, so `Compress-Archive`
built the archive without it, and the OOXML package's own literally-bracketed required part
name was the casualty. This is a real, independently identifiable failure class (bracket-named
parts are a known PowerShell wildcard footgun; the fix on that side would be `-LiteralPath`,
not `-Path`), not an unexplained "something went wrong" -- and it is non-deterministic across
runs (a later re-run of this same pilot, see the Word-COM update below, did not reproduce it,
because the model did not choose the same shell fallback sequence that run). It confirms the
control arm's exposure to this failure class is a property of using generic, non-package-aware
shell tooling at all, not a one-off fluke.

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

**Update (2026-08-30, later same day): this gap is now closed.** `tools/run_paper_s20_pilot.py`
now calls `word_receipt_watchdog.word_receipt_with_orphan_diagnostics()` at the milestone
cadence `docs/paper-s9-long-horizon-benchmark-protocol-v0.md` section 5 specifies for today's
single-pair harness shape (trial-start on the pristine fixture, after the forward output, after
the inverse output) -- any failure records an explicit `not_run`/`failed` status rather than
being silently skipped or treated as a pass. Re-ran the full 8-trial pilot with this wired in
(`E:\MeridianData\ooxml-graph-paper\runs\paper-s20\20260830T213803Z\manifest.json`): 8/8 executed,
8/8 graded pass, 8/8 isolation-clean, and now also **10/10 Word-COM milestone receipts rendered**
(8 post-pair + 2 trial-start), each with confirmed orphan-process cleanup
(`cleanup_complete: true`). This run happened not to reproduce the earlier control-arm
package-corruption finding -- consistent with the root-cause analysis above: it is a real but
non-deterministic property of the model's on-the-fly scripting choices each run (which shell
fallback path it happens to take), not a fixed, always-reproducing bug.
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
