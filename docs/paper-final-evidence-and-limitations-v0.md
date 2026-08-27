# PAPER-9: paper evidence, limitations, and executor continuation handoff (v0)

Status: **synthesis of everything actually shown this sprint, not a benchmark-results paper.**
PAPER-15 (the comparative benchmark) has not run. This document exists to state precisely
what is and is not established, so a human can make the PAPER-8 call with full information.
This item (PAPER-9) is not marked complete in the sprint tracker while its own listed
dependency, PAPER-8, remains open — claiming otherwise would be exactly the kind of
fabricated gate-pass this sprint has repeatedly refused to produce.

## 1. What is genuinely established

### 1.1 The native OOXML/OMML write path is real and independently re-verified

- A live Meridian `insert_equation_local` call wrote a real LaTeX sum into a Word-created
  DOCX and Word itself rendered and verified it: `render_status=rendered,
  render_verified=true, render_backend=word-com`. This was re-verified independently, not
  taken on faith: the probe manifest file, its JSON content, and an independently
  recomputed SHA-256 of the input DOCX all matched (`converter-backend-acceptance-matrix-v0.md`
  §1). A second, independent Word-COM manifest from 12 minutes earlier corroborates it with
  a real 13,440-byte input and 15,578-byte output PDF, both hash-recorded and the PDF still
  on disk.
- Word is confirmed installed and reachable via COM (Office16 Click-to-Run, build
  16.0.20326.20100) on this host (`runtime-capability-contract-v0.md`).
- `insert_numbered_equation` (PAPER-5) produces a genuine `<m:oMath>`, a correctly
  auto-incrementing/renumbering label, and fresh, collision-free `w14:paraId`/`w14:textId`
  on every paragraph it touches — confirmed by directly parsing the resulting
  `word/document.xml`, not by trusting the writer's return value
  (`test_paper14_converter_bakeoff_demo.py`).
- Compared directly against python-docx (a real, actively-maintained, Word-openable
  baseline — not a strawman): python-docx exposes zero methods containing "math",
  "equation", or "omml" on `Document` or `Paragraph`, and mints no `w14:paraId` at all.
  Meridian does both. This is a verified capability gap, not a claim.

### 1.2 OMML hardening is real, tested, and includes intentional fail-closed behavior changes

- PAPER-11's audit found that `_validate_omml_structure` accepted 10 of 11 hand-crafted
  "required child present but empty" payloads, including the exact shape the real
  `\frac{}{}` and `\min`/`\max`/`argmin` converter paths produce
  (`omml-builder-audit-v0.md` §6).
- PAPER-13 fixed this generally (not with a special case per element): a required child
  must now carry visible text or nested structure, and `accPr` is correctly excluded as a
  property-only element. `latex_to_omml_local(r'\frac{}{}')` now returns `None`;
  `\min_x f(x)`, `\max_x f(x)`, and `\operatorname{argmin}_x f(x)` now return `None` too —
  an intentional behavior change pinned by test, replacing "silently renders a blank box in
  Word" with "refuses to insert." A correctly-formed `\frac{1}{2}` still converts, so the
  gate is not over-strict (`test_omml_contract_semantics.py`).
- PAPER-13 also fixed the `\overline{...}` accent-allowlist gap (latex2mathml emits
  U+2015 HORIZONTAL BAR, not the allowlisted U+00AF MACRON, so it was building `<m:limUpp>`
  instead of `<m:acc>`).
- A separate concurrent session (`audit-fix-claimed-paper-completions`, this sprint)
  independently re-audited the claim that OMML hardening was complete, found it was not —
  `\sum`/`\prod`/`\int` were still emitting `<m:sSubSup>`/`<m:sSub>` side-scripts instead of
  a true `<m:nary>`, and `\lim` was still emitting `<m:sSub>` instead of `<m:limLow>` — and
  fixed it, with regression coverage. **Independently re-confirmed by this document**: a
  fresh run of `scripts/check_acceptance_gate.py` (2026-08-26T15:38:52Z) now shows
  `sum_uses_true_nary_operator` = PASS, where it was a known open, non-blocking gap as
  recently as 2026-08-26T15:02:52Z.
- 94/94 focused tests (`test_omml_contract_semantics.py`, `test_docx_render_gate.py`,
  `test_docx_numbered_equation_writer.py`) pass against the parent repo's real,
  detached-Pixi environment, re-run and confirmed by this document.
- Not fixed, and honestly still broken: `\binom{n}{k}` renders a real, visibly wrong
  fraction bar (not just lossy — actively incorrect math); the `gather` environment
  silently merges two equations into one run with the row boundary lost and no error
  raised anywhere; a true `mmultiscripts` prescript flattens to indistinguishable digits
  and passes the validator undetected (`omml-builder-audit-v0.md` §5.3–§5.5). None of these
  three were in PAPER-13's fix scope.

### 1.3 Package safety has multiple real, verified protections — and real, verified gaps

- Malformed ZIP and malformed per-part XML are each checked at multiple independent
  layers (load-time, package-wide validation, write-time re-parse before promotion)
  (`ooxml-package-safety-audit-v0.md` §1–§2).
- Namespace preservation is fail-closed and self-verifying: the writer re-parses its own
  serialized output and raises before any byte is staged to disk if a prefix was renamed or
  an `mc:Ignorable` prefix went undeclared. Covered by `test_docx_namespace_preservation.py`
  across seven named scenarios, all confirmed by direct code reading (§5).
- The atomic-write/CAS-restore path (`_atomic_write_docx_bytes`,
  `_safe_restore_after_verification_failure`) was traced end-to-end and has real test
  coverage for six named callers across both its "safe to restore" and
  "concurrent-write-detected" branches (§9).
- Real, unmitigated gaps found and not yet fixed: XML internal-entity expansion is
  unguarded on both `xml.etree.ElementTree` and `lxml` (a 5-level ×10 probe expanded to
  60,004 characters with no error; `defusedxml` is not installed) — this is the one finding
  that also reaches read-only entry points, not just the write path (§8b). Duplicate
  `w14:paraId` is recorded only as a non-blocking warning, so a document with duplicate IDs
  is still promoted normally — a direct, documented violation of
  `graph-gold-schema-v0.md`'s own invariant 4 (§3–§4). Roughly 15+ non-equation write
  primitives (`edit_caption`, `insert_citation`, `insert_bibliography_entry`, and others)
  have zero post-write structural verification and zero render-gate coverage, making a
  cross-process lost-update silent for those functions specifically (§9).

### 1.4 One real Word round-trip was executed, and it is genuinely informative

- PAPER-16 ran a real Documents.Open(ReadOnly=False) → edit under Track Changes → Save →
  Close cycle inside a 90-second watchdog and diffed the XML before/after
  (`word-roundtrip-preservation-contract-v0.md`).
- Survived: body text, the numbered-equation table and its OMML structural tags
  (byte-identical `structural_tags`), the Word comment and its reference id, tracked
  revisions (real author/timestamp), bookmarks by name (only numeric IDs renumbered),
  sections.
- Did **not** survive, and this is load-bearing: **every paragraph's `w14:paraId` was
  rewritten by Word on save, including untouched paragraphs.** Since Meridian's own
  `_find_para_by_id`-style addressing is paraId-based, this means any edit session that
  routes through a human's Word save invalidates prior paraId-based addressing — flagged
  as a real risk needing an explicit re-anchoring step, not yet built anywhere.
- A real bug was found and root-caused (not fixed): the shared test fixture used by
  `test_docx_word_com_regression.py` is rejected by real Word COM
  ("file appears to be corrupted"), traced to schema-invalid `clrScheme`/`fontScheme`
  placeholders in `_THEME_XML`. This means several existing tests claiming to exercise a
  real-Word-render branch have, per this investigation, never actually done so on any
  machine with genuine Word since the fixture was written.

### 1.5 The benchmark methodology itself is fully pre-registered, not ad hoc

`comparator-contract-v0.md`, `benchmark-preregistration-v0.md`, `graph-gold-schema-v0.md`,
and `dataset-landscape-2026-08-25.md` collectively lock, in writing, before any result
exists: the three evaluation tracks and their comparability rules (never pool a native
DOCX-graph score with a PDF/layout score; a post-conversion parser must report its own
loss separately); four Track-A baseline families and which specific tools instantiate each
one; a reproducible seed/split procedure (`Random(20260826)`, document-level splits, three
named slices); a 6-class equation semantic label set inherited from PAPER-11's real audit;
a 15-node/11-edge graph vocabulary with explicit "ambiguous"/"synthetic" states instead of
guessing; and a 10-item human-signoff acceptance checklist that PAPER-15 may not bypass.

### 1.6 Reproducibility and environment claims are directly verified, not assumed

`executor-reproducibility-contract-v0.md` independently re-ran (not re-cited) the actual
commands: confirmed parent-repo HEAD and dirty-file list, reproduced the `pixi run test`
`&&`-chain argument-passthrough gotcha in a minimal scratch repro, re-collected the test
suite today (642 tests, correcting a stale 682 figure), and directly confirmed `lxml 6.1.1`
is present in **both** the `default` and `dev` Pixi environments — correcting an earlier
session's stale claim that `dev` lacked it.

## 2. What remains open

### 2.1 Blocking — must clear before PAPER-15 may run

These are the same three conditions `scripts/check_acceptance_gate.py` has now reported
FAIL against twice (2026-08-26T15:02:52Z and, re-run for this document,
2026-08-26T15:38:52Z), unchanged between runs:

1. **Parent repository worktree is dirty** — 82 porcelain entries both times, a mix of this
   sprint's own in-flight files (`docs_intel.py`, `ooxml_integrity.py`, `render_gate.py`,
   `server.py`) and the pre-existing "b67/MDE" effort. No benchmark run against this
   checkout can be pinned to a single citable commit SHA right now.
2. **No gold corpus exists.** `benchmark-preregistration-v0.md`'s acceptance checklist is
   0/10. `corpus-acquisition-checkpoint-2026-08-26.md` confirms real, licensed raw material
   is staged (63 OmegaUse DOCX files, a pinned MathMLben checkout, a small ReadingBank
   example slice) but none of it is rights-reviewed per-file, graph-gold-labeled by an
   independent path, or render-receipted — and OmegaUse alone contains **zero** native OMML
   equations, so it cannot supply the equation track by itself.
3. **PAPER-8 (human render/Word-authority approval) has not been granted.** This gate is
   deliberately not automatable and defaults to NOT satisfied; only a human can clear it.

Additional blocking gaps, not part of PAPER-20's automated check but genuinely open:
unmitigated XML entity-expansion (no `defusedxml`, no depth/size guard, reaches read-only
endpoints too); duplicate `w14:paraId` only warns rather than blocking promotion, a direct
violation of the graph schema's own stated invariant; ~15+ non-equation writers have zero
post-write verification; no audit-grade retained render receipt (source/output hash, Word
build, page count, freshness) exists yet for any render; no real open→edit→save round-trip
test is wired into pytest (PAPER-16's `roundtrip.py` is a candidate starting point, not
committed coverage). Toolchain: python-docx is installed and working in this paper
subproject's own isolated Pixi environment (used for PAPER-14's demonstration); Pandoc and
LibreOffice remain not installed anywhere on this host.

### 2.2 Known, documented, non-blocking — explicitly out of current scope

`\binom` visibly wrong fraction bar; `gather` silently dropping row boundaries;
`mmultiscripts` prescript flattening undetected by the validator's marker vocabulary;
`align` baking literal `(1)`/`(2)` numbering into cells (a double-numbering risk if
combined with `insert_numbered_equation` on the same content); the `aligned` `None` result
being an accidental side effect of a third-party XML-escaping bug rather than a deliberate
rejection; `move_section`/`copy_section` having real structural checks but no render-gate
parity; REF/PAGEREF/NOTEREF fields, content controls, and headers/footers never having been
exercised through a real Word round trip; DocBank/OCB/DocuBench/docx-corpus/WordScape all
confirmed as context-only or raw-material sources, none supplying a paired OOXML graph gold
set on their own; the official ReadingBank full ZIP remains 404.

## 3. Honest bottom line

The product-hardening work this sprint (PAPER-5, 6, 11, 13, 14, 16, 17, 18, 20, 21) is real,
independently re-verified where it mattered, and includes at least one instance of a
concurrent session catching and fixing a false completion claim rather than this session's
own account being taken at face value. The benchmark-design work (PAPER-10, 12, 19) is a
complete, internally consistent, pre-registered methodology with zero results attached to
it yet, by design. Nothing in this document should be read as a benchmark result, a claim
that PAPER-15 is ready to run, or a claim that PAPER-9 itself is complete — it is not, while
PAPER-8 is still open.

## 4. Continuation handoff

Once PAPER-8 is decided and, separately, the worktree is cleaned and a gold corpus with at
least the equation track exists: re-run `scripts/check_acceptance_gate.py` — it is
re-runnable at zero cost and is the authoritative live gate, not this document. If it
passes, PAPER-15 may claim and run against the exact frozen baselines and split procedure
`benchmark-preregistration-v0.md` already locked. If PAPER-8 is declined or deferred, the
product-hardening evidence in §1 still stands independently of the benchmark track.
