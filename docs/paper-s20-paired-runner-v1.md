# PAPER-S20: symmetric Claude DOCX broker, fresh-process runner, isolation audit (v1)

Status: **harness built and mechanically validated end-to-end against the real `claude`
CLI. The actual 8-process commissioning pilot is BLOCKED, not run** -- a genuine
credential problem, not a code defect. Read the blocker section before assuming any
pilot numbers exist; none do.

## What was built

- `tools/docx_trial_broker.py` -- the symmetric `TrialSpec` schema and a task/inverse
  generator. Both arms receive the identical, implementation-agnostic English prompt
  (insert one paragraph with an exact, opaque marker string after a real anchor
  paragraph; the inverse removes it). The arm difference is enforced entirely by which
  tools the CLI invocation allows, never by prompt wording.
- `tools/claude_pair_runner.py` -- launches one fresh, non-interactive `claude -p`
  subprocess per trial with `--strict-mcp-config` (control: an empty `mcpServers`
  config; treatment: a config naming ONLY a local stdio launch of the meridian-docs
  extension's own MCP server, `extensions/meridian-docs/meridian_docs/server.py:main`,
  run via this paper repo's own editable-install pixi env -- never the parent repo's
  hosted orchestration MCP or its credentials, which this code never reads), plus
  `--allowedTools` restricted per arm and `--add-dir` scoping filesystem access to a
  fresh, private trial directory. Also implements `audit_isolation()`, a **post-hoc**
  transcript scan (not a re-trust of the CLI flags) that flags any `mcp__` reference in
  a control transcript or any unexpected MCP server name in a treatment transcript.
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

1. `claude --version` and a live `-p` invocation both confirmed the executable resolves
   and runs. Windows-specific finding: `claude` resolves to `claude.CMD` (an npm batch
   wrapper, not a native `.exe`); `subprocess.run` with `shell=False` cannot invoke it
   even given the fully-resolved absolute path -- `shell=True` is required. This is safe
   here specifically because the command is a Python **list** with the executable path
   already resolved via `shutil.which` (Python's own `list2cmdline` quotes every
   argument correctly), unlike the bare-command-name-plus-hand-built-shell-string
   pattern that caused a real PATH-ambiguity bug found elsewhere this sprint (`find`
   resolving to the wrong binary) -- there is no unqualified command name here for
   `cmd.exe`'s own PATH search to get wrong.
2. `--strict-mcp-config` with an empty `mcpServers` JSON file was accepted without
   error (control arm's isolation mechanism confirmed loadable).
3. `--mcp-config` pointed at a config naming a real path to the paper repo's own
   pixi-env Python plus `-m meridian_docs.server` was accepted without error (treatment
   arm's isolation mechanism confirmed loadable; the actual server process was not yet
   exercised end-to-end because trials never got past the authentication step below).

## BLOCKER (real, not a code defect): CLI authentication in non-interactive subprocess mode

Every trial invocation -- with and without `--bare`, with a minimal test prompt, with
`--permission-mode bypassPermissions` -- fails identically:

```
"result": "Failed to authenticate: OAuth session expired and could not be refreshed"
```

This reproduces even WITHOUT `--bare` (ruling out `--bare`'s own keychain-skip behavior
as the specific cause) and even for a trivial one-line prompt with no tool use at all.
The conclusion: this machine's cached Claude Code OAuth session is genuinely expired,
and a non-interactive `-p` subprocess cannot trigger the interactive re-auth flow that
would normally refresh it.

**No `.env` file or other sanctioned credential source for headless CLI use was found**
in this repo (checked `find . -maxdepth 2 -iname "*.env*"` -- no matches). No API key
was fabricated, guessed, or sourced from elsewhere; per this project's own standing
rule, a credential gap is exactly the class of thing to report as a genuine blocker, not
route around.

**What would unblock this** (a human action, outside Meridian, matching this item's own
allowed exception list for "credentials"): either run `claude login` interactively on
this machine to refresh the OAuth session (after which non-interactive `-p` subprocess
calls should work normally, since they were only ever failing on stale/expired auth, not
on any flag combination this harness uses), or supply a valid `ANTHROPIC_API_KEY`
environment variable for `claude_pair_runner.py`'s subprocess environment to inherit.

## What this means for the acceptance criteria

- Broker, runner, evaluator, and isolation-audit code: **built and mechanically
  validated as far as possible without live authentication.**
- The 8-process commissioning pilot itself: **not run.** Zero pilot numbers exist. Any
  future claim that this pilot has results must point to an actual manifest under
  `E:\MeridianData\ooxml-graph-paper\runs\paper-s20\<timestamp>\manifest.json` produced
  by `tools/run_paper_s20_pilot.py` after the auth blocker above is resolved -- this
  document is not that manifest and must never be cited as pilot evidence.
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
- The treatment arm's one exposed tool, `insert_highlighted_note`, does not produce a
  plain, unstyled paragraph the way the control arm's generic file-editing tools would
  -- this is expected and should not be treated as a confound to hide: the whole point
  of the comparison is generic-tool-editing versus Meridian's own bounded write
  primitive, not forcing byte-identical output styling between arms.
