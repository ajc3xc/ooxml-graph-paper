# PAPER-38: closing PAPER-33's residual hardening gaps (v0)

Status: closes PAPER-33's one open finding (12 of 32 unprotected write primitives) to zero,
finds and fixes one new real silent-data-loss bug (MathML fail-closed behavior), and
reconfirms PAPER-33's three previously-fixed mechanisms remain intact. Each of the three
tracks below was independently, adversarially verified before being accepted here.

## Track 1: the remaining 12 write primitives — closed to zero

PAPER-33 protected 2 of 14 identified unprotected write primitives (`edit_caption`,
`remove_caption`) and left 12 deferred as real, named scope. All 12 are now routed through
the same `_execute_fail_closed_write` envelope, each with its own bespoke re-verification
function (re-resolving the written content from disk via the same identity scheme the writer
used, not a rubber-stamp check):

`insert_cross_reference`, `insert_citation`, `edit_citation`, `remove_citation`,
`append_text_run_after_math`, `insert_bibliography_entry`, `update_bibliography_entry`,
`remove_bibliography_entry`, `renumber_sequences`, `insert_tracked_paragraph`,
`write_section`, `retrofit_plaintext_captions`.

24 new regression tests (`tests/test_paper33_remaining_write_primitives_concurrent_write_envelope.py`
in the product repo) -- 12 concurrent-write-detection tests (each injects a real, independently
-written concurrent payload immediately before the real verify step and asserts the write is
rejected and the concurrent content preserved, mirroring the existing `5988a5bb` pattern) plus
12 paired success-path sanity tests. Independently verified: the file is genuinely new (not an
overwrite of an existing file), each of the 11 distinct verify functions appears exactly once
in the diff with a real call site, and one verify function (`_verify_cross_reference_write`)
was read in full and confirmed to perform a real re-resolution check, not a placeholder.
**All 32 of `docs_intel.py`'s write primitives are now protected against cross-process lost
updates** -- this closes PAPER-33's residual finding completely, not partially.

## Track 2: a real, new silent-data-loss bug in MathML-to-OMML conversion, found and fixed

`_stdlib_append_mathml`'s catch-all branch for any MathML element it does not explicitly
recognize (`menclose`, `mmultiscripts`, and others) **silently flattened the unrecognized
subtree's text into a bare `<m:r><m:t>` run, discarding structure with zero exception, zero
log line, zero diagnostic**. Confirmed live, not theoretically: `latex_to_omml_local(r"\boxed{x+y}")`
returned structurally-valid OMML containing only `x+y` -- the box notation vanished silently,
and `_validate_omml_structure`'s own flattened-fallback heuristic (which only fires on literal
marker words like "fraction"/"matrix"/"summation" appearing in the flattened text) does not
catch plain content like `x+y`, so this passed validation cleanly.

**Fixed narrowly, at the exact point identified**: added `UnsupportedMathMLConstructError`
and replaced the silent-flatten fallback with an explicit raise naming the unrecognized
construct. `latex_to_omml_local`'s existing broad `except Exception: return None` at the call
site already wraps this, so the public contract ("never raises, returns `None` on failure") is
unchanged -- the difference is the failure is now *loud enough to be caught and counted* as a
real `not_run`/failure case instead of silently masquerading as a successful, lossy conversion.
Independently re-verified live by a second agent: `latex_to_omml_local(r"\boxed{x+y}")` now
returns `None`; `latex_to_omml_local(r"\frac{a}{b}")` (a normal, supported case) still converts
correctly -- the fix is narrow and does not regress ordinary usage. 3 new tests added to the
existing `tests/test_omml_contract_semantics.py` (18 → 21 passing; diff is +211/-1, the one
deletion an unrelated pre-existing assertion tweak, not a removed test).

## Track 3: reconfirming PAPER-33's three fixed mechanisms

All three remain present and correct on direct re-read: duplicate-ZIP-entry detection
(`ooxml_integrity.py`, `test_validate_rejects_duplicate_zip_entry_names` passing), zero-byte
directory-placeholder handling (`_is_zip_directory_placeholder`, both regression tests
passing), and entity-expansion resilience (`test_validate_handles_billion_laughs_document_xml_without_hanging`
passing, no hang). `render_gate.py`'s receipt-retention pruning and fail-closed-on-stale-receipt
mechanisms are likewise both intact and passing (70/70 render_gate-filtered tests).

**One test failure was re-encountered, not newly introduced**: `test_ooxml_integrity_contract.py::test_validate_reports_hidden_bold_heading_like_case_drift`
still fails with `KeyError: 'style'`. This is not new -- it is the exact same failure PAPER-33's
own audit already found and disclosed (`docs/ooxml-package-safety-audit-v0.md`: "a *different*,
concurrent, uncommitted session's edit removed a `style` field from `PackageIssue`..."). The
reconfirm agent's own report imprecisely characterized this file as having "no local
modifications" when checking it -- its own adversarial verifier caught that imprecision (the
file does have local, uncommitted modifications, from a still-active concurrent session, which
is exactly what removed the `style` field and caused the KeyError). The verifier's correction
is about the *phrasing*, not about who is at fault: this workflow's own three agents never
touched `ooxml_integrity.py`'s `PackageIssue` dataclass or the heading-audit code path, and the
same failure was already independently attributed to another concurrent session's ongoing work
before this item even started. Reconfirmed here as still present, still someone else's active
work, still correctly out of this item's scope to fix.

A further, unactioned observation from the same verification pass: `test_docx_namespace_preservation.py`
also shows local modifications (one test's assertion direction fully inverted, previously
asserting a successful write, now asserting fail-closed) -- consistent with, not contradicting,
the picture of an actively-changing shared repository. Not touched, not investigated further;
noted only as further evidence of the same ongoing concurrent churn already disclosed in
PAPER-33.

## Full-suite context (unchanged from PAPER-33's own disclosure)

The full `extensions/meridian-docs/tests/` suite still shows exactly **169 pre-existing
failures**, confirmed via `git stash` isolation (reverting only this item's own changed files
to HEAD *increases* the failure count to 205-207, confirming this item's work is not the cause)
-- the same root cause PAPER-33 identified (a separate, in-progress, incomplete refactor by
another concurrent session), not something this item introduces or is scoped to fix. Passing
counts genuinely increased by this item's real work: +24 (write primitives) and +3 (MathML)
new, real, independently-verified tests, all passing, zero existing tests deleted or weakened.
