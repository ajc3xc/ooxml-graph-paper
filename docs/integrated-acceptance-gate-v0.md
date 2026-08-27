# Integrated native-Word product acceptance gate v0 (PAPER-20)

Status: gate implemented and run. **Current verdict: FAIL.** This document does not claim
readiness -- it documents what the gate checks, how to run it, and the actual result of
running it once, honestly.

## What this is

`scripts/check_acceptance_gate.py` (in this paper subproject) is the single
machine-readable acceptance report PAPER-20 asks for. It synthesizes PAPER-11 (OMML
audit), PAPER-13 (validator/converter hardening), PAPER-14 (converter bakeoff), PAPER-16
(Word round-trip), PAPER-17 (package safety), and PAPER-18 (executor reproducibility) by
**running real checks against the current code and environment**, not by re-stating their
prose findings. Run it with:

```
pixi run python scripts/check_acceptance_gate.py
```

When the parent Meridian checkout is intentionally shared and dirty during
development, use:

```
pixi run python scripts/check_acceptance_gate.py --allow-dirty-parent
```

This does not make the parent checkout appear clean. It records the parent
`HEAD`, complete porcelain status, binary diff digest, and exact product-file
hashes in the report, then fails closed if that fingerprint changes during the
run. The default remains clean-checkout-required for a final benchmark.

It writes a timestamped JSON report to `E:\MeridianData\ooxml-graph-paper\manifests\` and
prints a human-readable summary. Exit code is `0` only when every *blocking* check passes.

## What it checks, and why each maps to PAPER-20's named fail-closed conditions

| PAPER-20 condition | Check(s) | Blocking? |
|---|---|---|
| Semantic OMML loss | `\frac{}{}` and `\min` now rejected end-to-end (PAPER-13); a correct equation is still accepted (a fail-closed gate that's too strict is its own bug); `\sum` still uses side-scripts not `<m:nary>` | Empty-operand rejection and correct-equation-acceptance are blocking; the `\sum`/nary gap is a known, out-of-PAPER-13-scope finding, reported as non-blocking |
| Unsupported fallback text | flattened "fraction a over b" text is rejected by `_validate_omml_structure` | Blocking |
| Empty operands | same as semantic-OMML-loss row above (PAPER-13's central fix) | Blocking |
| Renderer unavailable | `render_gate.check_render_capability` run for real against a fresh synthetic fixture | Blocking |
| ID/reference/relationship errors | `ooxml_integrity.validate_docx_package` run for real against the same fixture | Blocking |
| Dirty/unclaimed worktree | clean parent by default; explicit dirty-snapshot mode records and rechecks the complete parent fingerprint | Blocking |
| Missing corpus provenance | does `E:\MeridianData\ooxml-graph-paper\gold\` exist and hold anything | Blocking |
| Untracked artifacts | live `git status --porcelain` scoped to `extensions/meridian-docs/meridian_docs` | Blocking |
| Formal PAPER-8 human Word authority | **not automatable from this script** (no sprint-board query dependency by design, so the gate stays runnable offline) -- defaults to NOT satisfied; whoever runs this must confirm PAPER-8's live status and treat that field as authoritative, not this script's default | Blocking |

What it deliberately does **not** attempt: ID stability/preservation across a human Word
edit session (PAPER-16 already ran that as a real, one-off live probe; automating it as a
repeatable gate check would need the same 90s-watchdog Word-COM harness PAPER-16 built,
which is a real follow-up, not done here), and stale/missing render-*receipt* retention
(no receipt-retention mechanism exists yet at all per PAPER-19 -- there is nothing to check
staleness of).

## Actual result of running it (2026-08-26)

```
Verdict: FAIL -- 3 blocking check(s) failed; PAPER-15 must NOT run

[PASS   ] empty_operand_rejected:empty fraction
[PASS   ] empty_operand_rejected:min with empty func argument
[PASS   ] fallback_text_rejected
[PASS   ] correct_equation_still_accepted
[FINDING] sum_uses_true_nary_operator          (non-blocking, known open gap)
[PASS   ] render_backend_available             (real Word COM render, not cached)
[PASS   ] package_integrity_clean
[FAIL   ] parent_repo_worktree_clean           82 porcelain entries in the parent repo
[FAIL   ] gold_corpus_provenance_exists        no gold corpus built yet (PAPER-19: 0/10)
[PASS   ] no_untracked_product_code
[FAIL   ] paper8_human_authority_approved      not confirmed by this script (by design)
```

Full JSON: `E:\MeridianData\ooxml-graph-paper\manifests\acceptance-gate-20260826T150252Z.json`.

## Reading this honestly

PAPER-13's hardening genuinely works end to end (4 of 4 blocking OMML checks pass, run
against the real converter/validator, not mocked). Word COM render capability and package
integrity both pass for real, right now, on this host. The three blocking failures are not
code bugs -- they are exactly the three things this whole sprint has consistently found
still open: the parent repository has 82 uncommitted changes (a mix of this sprint's own
work and the pre-existing "b67/MDE" effort documented in earlier items -- see PAPER-18's
executor-reproducibility-contract-v0.md for the full inventory), no gold corpus has been
built (PAPER-19's preregistration checklist is honestly 0/10), and PAPER-8's human approval
has not been granted. **PAPER-15 (the benchmark) must not run until all three clear.**

This gate is re-runnable at zero cost whenever any of those three conditions changes --
that is the point of making it a script instead of a one-time manual checklist.

## Repository boundary

The paper harness is its own local Git repository at
`C:\Users\13144\Documents\Meridian\ooxml-graph-paper`, with code, tests, and
methodology committed there. The Meridian Docs implementation remains owned by
the parent Meridian repository. Benchmark inputs, renders, receipts, and ZIP
archives remain on `E:\MeridianData\ooxml-graph-paper` and are not synced into
either repository. A clean parent worktree is preferred for publication; the
dirty-snapshot mode exists to keep development moving while preserving an
auditable product identity.
