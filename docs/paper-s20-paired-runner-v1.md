# PAPER-S20: symmetric Claude DOCX broker, fresh-process runner, isolation audit (v1)

Status: **harness built and its auth/invocation corrections mechanically validated
against the real `claude` CLI; the latest arm-boundary-corrected commissioning attempt
is blocked and requires S22 follow-up**. A complete-looking earlier run is not valid
pilot evidence because `--safe-mode` disabled the treatment MCP server and the initial
`--allowedTools` use did not create a hard tool-visibility boundary. Do not cite pilot
numbers without checking the manifest and the CLI boundary mode used.

## What was built

- `tools/docx_trial_broker.py` -- the symmetric `TrialSpec` schema and a task/inverse
  generator. Both arms receive the identical, implementation-agnostic English prompt
  (insert one paragraph with an exact, opaque marker string after a real anchor
  paragraph; the inverse removes it). The arm difference is enforced entirely by which
  tools the CLI invocation allows, never by prompt wording.
- `tools/claude_pair_runner.py` -- launches one fresh, non-interactive `claude -p`
  subprocess per trial with project-only settings and `--strict-mcp-config` (control:
  an empty `mcpServers` config; treatment: a config naming ONLY a local stdio launch
  of the meridian-docs extension's own MCP server, run via this paper repo's own
  editable-install pixi env -- never the parent repo's hosted orchestration MCP or
  its credentials, which this code never reads), plus native-executable invocation,
  `--tools` for the control built-in set, treatment-side `--disallowedTools` for
  generic editors/shell tools, and `--add-dir` scoping filesystem access to a fresh,
  private trial directory.
- The CLI flags are deliberately distinguished: `--allowedTools` is only an
  auto-approval list, not a visibility filter. The treatment MCP server still exports
  its full tool catalogue, so S22 must either provide a one-tool MCP facade or prove
  an explicit deny-list before claiming the original "exactly one writer" boundary.
- `audit_isolation()` remains a **post-hoc** transcript scan (not a re-trust of CLI
  flags) that flags any `mcp__` reference in a control transcript or any unexpected
  MCP server name in a treatment transcript. The current JSON-only output is weaker
  than a full tool-call transcript; use stream output if S22 needs exact call-level
  auditing.
- `tools/docx_trial_evaluator.py` -- grades a trial's output DOCX against the broker's
  ground truth entirely outside the agent: valid-package check, exact marker-paragraph
  presence/absence, correct insertion position, no collateral paragraph loss, and (for
  the inverse) exact reconstruction of the pre-forward paragraph sequence.
- `tools/run_paper_s20_pilot.py` -- the 8-trial driver (2 frozen docs x 2 arms x
  {forward, inverse}, where each arm's inverse trial operates on THAT SAME arm's own
  forward output, not the pristine fixture or the other arm's output).

## Real mechanical validation performed

Every non-authentication-dependent piece of the pipeline was exercised against the real
CLI, not assumed:

1. `claude --version`, `claude auth status`, and live `-p` invocations confirmed the
   executable and the user's OAuth login work. Windows-specific finding: PATH resolves
   to an npm `.cmd`/`.ps1` wrapper, and the old `shell=True` list invocation swallowed
   the prompt. The runner now resolves the adjacent native `claude.exe` and uses
   `shell=False`, preserving every argument.
2. `--strict-mcp-config` with an empty `mcpServers` JSON file was accepted without
   error (control arm's isolation mechanism confirmed loadable).
3. `--mcp-config` pointed at a config naming a real path to the paper repo's own
   pixi-env Python plus `-m meridian_docs.server` was accepted and connected. A focused
   treatment trace loaded `search_document`, found the real anchor id, and successfully
   called `insert_highlighted_note` against a copied DOCX.

## Authentication-mode finding and current unblock status

The initial trial invocation failed with:

```
"result": "Failed to authenticate: OAuth session expired and could not be refreshed"
```

That initial result was a genuine expired OAuth session. After the user re-authenticated,
`claude auth status` reported an active Claude.ai login. A minimal invocation succeeds
under `--safe-mode`, but `--safe-mode` also disables MCP servers; the same invocation
under `--bare` reports `Not logged in` because Claude Code 2.1.226 skips keychain/OAuth
reads in bare mode. The runner therefore uses project-only settings (not safe mode),
`--strict-mcp-config`, explicit built-in/tool deny controls, and trial-root scoping.

## Harness correction: failed trials cannot count as document passes

The first reproduction exposed a separate harness bug: the pilot graded every copied
DOCX even when the Claude subprocess returned an authentication error. Because an
inverse trial was then run against the untouched forward input, its unchanged paragraph
sequence satisfied the inverse evaluator and produced four misleading document passes;
the driver also returned exit code 0 and reported all eight isolation audits as clean.

The pilot now records `execution_status` separately from document grading, marks
process/API/authentication failures as `not_run`, skips an inverse whose required
forward trial did not complete, reports a manifest-level `status=blocked`, and returns
exit code 2 whenever the complete eight-trial commissioning matrix did not execute.
Only a completed Claude process can receive an evaluator pass or an isolation-clean
count. This correction does not create pilot evidence; a complete matrix still requires
the treatment-arm contract to converge under the corrected boundary.

**No `.env` file or other sanctioned credential source for headless CLI use was found**
in this repo (checked `find . -maxdepth 2 -iname "*.env*"` -- no matches). No API key
was fabricated, guessed, or sourced from elsewhere; per this project's own standing
rule, a credential gap is exactly the class of thing to report as a genuine blocker, not
route around.

The auth prerequisite is now satisfied for the project-only invocation on this machine.
An approved `ANTHROPIC_API_KEY` remains an alternative, but no credential should be
written into the repository or trial manifests.

## What this means for the acceptance criteria

- Broker, runner, evaluator, and authentication/invocation controls: **built and
  mechanically validated against the live CLI.**
- Latest boundary-corrected commissioning attempt:
  `E:\MeridianData\ooxml-graph-paper\runs\paper-s20\20260830T191343Z\manifest.json`.
  It reached 4/8 completed trials: the 4 control trials passed; both treatment-forward
  trials reached the local MCP path but timed out after 300 seconds; treatment inverses
  were skipped. The output artifacts show one comment-mode write and one inline-note
  write, confirming the service was reached but the symmetric task did not converge.
- A focused, explicitly guided treatment smoke test succeeded with an inline note, so
  this is not an authentication or local-server outage. It is a treatment-task/tool
  contract and hard-boundary issue. S22 owns the replan: choose a genuinely reversible
  bounded operation (or make the two directions' bounded writers explicit), and expose
  only the intended MCP write surface before rerunning the matrix.
- This item is left **in_progress with `blocker_kind=manual`**, not marked done, per
  this sprint's own rule to never claim something is done when it isn't.

## Design choices worth a reviewer's attention

- The model pinned for the pilot is `haiku` (cheap/fast) -- appropriate for a
  commissioning pilot proving the harness works, explicitly NOT appropriate for a
  confirmatory benchmark claim about model capability with/without Meridian.
- The single task type (insert-marker-paragraph-after-anchor / remove-it) was chosen
  for how unambiguously gradable it is with a purely structural (not semantic) diff,
  matching this item's own instruction to reuse DELEGATE-52's relay/reversal pattern as
  a methodology reference, not as already-integrated evidence.
- The treatment arm's `insert_highlighted_note` is a one-way note writer, not a generic
  paragraph insert/delete API. Under an explicit hint it can place a note after an
  anchor, but the original symmetric forward/inverse task leaves its inverse without
  a corresponding removal primitive. This is the central S22 design issue, not a
  cosmetic styling difference to ignore.
