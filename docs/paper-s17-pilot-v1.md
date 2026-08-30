# PAPER-S17 PILOT: bounded structural and Claude A/B evidence (v1)

**LABEL: PILOT / NON-CONFIRMATORY.** This is a preliminary evidence package
produced while PAPER-S6 (the organic-OMML clean-holdout gate) remains closed.
It must not be pooled with PAPER-S7/S8 final evidence, must not be used to
clear the S6 clean-holdout gate, tune final rules, or claim confirmatory
superiority. Sprint item: `d5a64f3c-5001-4ee8-9d35-35cc6ba3b774`.

Harness: `tools/run_paper_s17_pilot.py` (this session). Raw machine-readable
report: `E:\MeridianData\ooxml-graph-paper\runs\paper-s17-pilot\paper-s17-pilot-20260830T080747Z.json`.

## 1. Structural/native-parser scorer on D0/127 (the staged gold corpus)

Re-ran the already-verified `tools/run_paper30_graph_eval.py` harness
(PAPER-30/PAPER-S5) against the full staged 127-document gold corpus this
session, `--slice all`:

```
pixi run python tools/run_paper30_graph_eval.py --slice all
```

- **127/127 documents scored** (0 crashes, 0 not_run).
- Report: `E:\MeridianData\ooxml-graph-paper\manifests\paper30-graph-eval-all-20260830T080504Z.json`
  (SHA-256 `cd2b47fa2f83598538ef7234eec83424b3318300c49e588c37b503db885b8e62`).
- Corpus run-manifest SHA-256 (identifies exactly which corpus snapshot this
  scored, per the report's own `corpus_run_manifest_sha256` field) is embedded
  in that report.
- Wall time: ~11.4 s for all 127 documents (both `native_meridian` and
  `python_docx` baselines; Docling/document-AI baseline not requested this
  run -- out of this pilot's bounded scope, already covered separately by
  earlier PAPER-30/PAPER-36 work).

Headline aggregate metrics (bootstrap 95% CI; full per-metric breakdown incl.
precision/recall/reading-order/table/equation/caption/anchor is in the cited
report, not retyped here to avoid drift from the source of truth):

| Metric | native_meridian | python_docx |
|---|---|---|
| paragraph_node_f1 | 0.9984 [0.9953, 1.0], n=127 | 0.9836 [0.9665, 0.9956], n=122 |
| reading_order_accuracy | 1.0 [1.0, 1.0], n=106 | 0.99999 [0.99999, 1.0], n=101 |
| table_node_f1 | 1.0 [1.0, 1.0], n=75 | 1.0 [1.0, 1.0], n=70 |
| equation_node_f1 | 1.0 [1.0, 1.0], n=7 | not_applicable (no equation API; n=0) |
| para_id_preservation_rate | 0.9947 [0.9842, 1.0], n=95 | not_applicable (no para-id API; n=0) |
| caption_node_f1 | 1.0 [1.0, 1.0], n=8 | not_applicable (no candidate adapter; n=0) |

This is descriptive re-confirmation of the existing D0/127 structural
pipeline against the current staged corpus snapshot, not a new finding --
consistent with the PAPER-S5/PAPER-30 numbers already on record.

## 2. Word receipts (attempted, real, bounded sample)

Also re-ran `--slice smoke --round-trip-check --round-trip-sample 2` this
session to obtain fresh Word-COM round-trip receipts (open, edit, save,
close against a disposable working copy -- never the original corpus file):

- Report: `E:\MeridianData\ooxml-graph-paper\manifests\paper30-graph-eval-smoke-20260830T080617Z.json`.
- 2/2 sampled documents (`tier2-omegause-010-roadmap-diagram`,
  `tier2-docxcorpus-61c750fca9dfb8ca`): `clean_round_trip`, render-equivalent
  (identical pre/post page counts: 1 and 13 pages respectively).
- No WINWORD.EXE processes were observed running before or interfering
  during this check.

This satisfies "Word receipts are attempted where available" for the D0/127
lane. A larger round-trip sample was not run this session to keep the pilot
bounded; 2/2 clean is the real, current n.

## 3. Structural/native-parser scorer on development/regression material (thesis-p30 fixture)

The `thesis-regression-fixtures` track (sprint item `f9194db0`) already
produced one real, Word-verified fixture in a prior session: a base/forward/
inverse triple derived from the user's real MS thesis (page 30, "Chapter 5"
-> "Section 5" correction), built and independently verified end to end
(`overall_pass: true`) -- see `docs/thesis-p30-fixture-v0.md` and
`E:\MeridianData\ooxml-graph-paper\fixtures\thesis-p30\manifest.json`
(commit `04cacd3`). That prior work already covered the localized-diff,
negative-control, bookmark/field/paragraph-count, formatting-preservation,
full-round-trip, OOXML package-validation, and Word-COM-receipt checks; it is
cited here, not repeated.

This session additionally ran this item's own D0/127 structural extractors
(`extract_native_meridian_items`, `extract_python_docx_items`, the same
functions `run_paper30_graph_eval.py` uses -- reused, not reimplemented)
directly against that fixture's three DOCX files, as the "development/
regression material" pass this item's notes require:

- **Fixture integrity re-verified**: recomputed SHA-256 of all three files
  (base/forward/inverse) exactly matches the hash already on record in the
  fixture's own `manifest.json` -- confirms no drift since the prior session
  built it. (The real, live thesis document at
  `C:\Users\13144\Documents\Masters_Thesis\...` was **not** touched or
  re-opened this session, per this item's own constraint; only the isolated
  E: fixture copies were read.)
- Both extractors ran cleanly on all three variants -- **0 crashes**, ~0.2-0.7 s
  per extraction.
- Structural counts (paragraphs/tables/equations/captions) are **identical
  across base/forward/inverse** for both extractors -- expected, since the
  fixture's own edit is a single in-place text substitution
  (`"Chapter 5"` -> `"Section 5"`, 7 characters -> 7 characters) that changes
  no paragraph/table/equation/caption structure. This is a real regression
  check, not an assumption: `native_meridian` reports 1186 paragraphs / 124
  tables / 408 equations / 0 captions identically for all three; `python_docx`
  agrees on paragraphs (1186) and tables (124) but reports 0 equations on all
  three, consistent with the already-documented PAPER-14 finding that
  `python-docx` has no OMML/equation extraction API at all (not a fixture
  defect).
- No fixture text is reproduced here (only counts), since the underlying
  content is the user's real personal thesis draft.

This is a structural sanity/regression pass, **not** a `graph_scorer`
precision/recall/F1 run: there is no independent gold record for this
fixture, and per PAPER-S16 none should be built -- this material is
development/regression only, never primary holdout, and is not pooled with
the D0/127 numbers above.

## 4. Paired Claude without-versus-with Meridian pilot: not_run (real blocker, re-confirmed live)

Per this item's own instruction, the paired pilot is attempted **only if the
local Claude runner and treatment broker are actually available**. The
PAPER-S20 harness code is present and was mechanically validated in a prior
session (`docs/paper-s20-paired-runner-v1.md`, commit `35ae41f`,
2026-08-30 02:27): `tools/docx_trial_broker.py`, `tools/claude_pair_runner.py`,
`tools/docx_trial_evaluator.py`, `tools/run_paper_s20_pilot.py` all exist and
were confirmed loadable (control's empty `--strict-mcp-config` and
treatment's meridian-docs-only `--mcp-config` both accepted without error).

This session re-probed live execution directly (not assumed from the earlier
document) with a minimal, bounded, non-interactive call using the control
arm's own isolation mechanism:

```
claude -p "reply with exactly: PING_OK" --strict-mcp-config --mcp-config '{"mcpServers":{}}'
```

Result (returncode 1, 1.97 s):
```
Failed to authenticate: OAuth session expired and could not be refreshed
```

This is the **identical** error PAPER-S20 recorded ~5.5 hours earlier,
re-confirmed still present in this environment right now. No API key or
other credential was fabricated, guessed, or sourced to route around this --
per this project's standing rule, a credential/auth gap is reported as a
genuine blocker, not worked around.

**Status: not_run.** Reason: non-interactive `claude -p` subprocess
authentication is blocked (expired OAuth session; a non-interactive process
cannot trigger the interactive re-auth flow). Unblocking requires a human to
either run `claude login` interactively on this machine, or supply a valid
`ANTHROPIC_API_KEY` for the subprocess environment -- both outside this
item's/this session's remit. Zero Claude A/B pilot numbers exist; none are
fabricated here.

## 5. Resource accounting (this pilot session)

| Step | Wall time |
|---|---|
| D0/127 full structural scorer (`--slice all`) | 11.4 s |
| Smoke slice + 2-doc Word round-trip sample | 30.7 s |
| thesis-p30 fixture structural pass (3 files x 2 extractors) | ~3.5 s total |
| Claude CLI live auth probe | 2.0 s |
| `tests/test_graph_scorer.py` regression suite | 0.18 s, 36/36 passed |

No GPU, no Docling, no model inference was used in this pilot -- purely
deterministic local parsing plus one bounded Word-COM sample and one bounded
CLI auth probe.

## 6. What this pilot does not establish

- Does not clear the PAPER-S6 organic-OMML clean-holdout gate (still 0/24
  clean units from the required 8 source groups/6 task families).
- Does not produce any paired Claude-with-vs-without-Meridian numbers (the
  lane is genuinely blocked on authentication, not run).
- Does not extend the thesis-p30 fixture into a multi-fixture regression
  suite (still exactly one fixture under that track, per
  `docs/thesis-p30-fixture-v0.md`'s own scope note).
- Does not constitute or imply confirmatory superiority for any candidate.

## 7. require_verification gap (honest, not routed around)

This sprint item has `require_verification=1`: completion requires an
independent PASS filed by a **different**, fresh, no-memory subsession that
inspected the change with read-only tools (`verifier_session_id` +
`verification_verdict='pass'` on `complete_sprint_item`). No such independent
verifier subsession was available to this execution. Per this project's own
rule against self-verification under a different label, `complete_sprint_item`
was called **without** fabricating those fields; if the platform refuses with
`VERIFICATION_REQUIRED`, the item is left `in_progress` with this honest
report on record rather than marked done by any other means.
