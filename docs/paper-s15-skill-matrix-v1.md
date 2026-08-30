# PAPER-S15: frozen Claude skill/control-treatment tool matrix and DOCX contamination boundaries (v1)

Status: freezes the arm-boundary tool matrix and dataset-lane rules the PAPER-S7/S9
confirmatory benchmark runs against, based on a real, source-level investigation of the
Meridian Docs MCP tool surface (2026-08-30) plus the corpus-provenance audits already
completed by PAPER-S11/S12/S13. This is a methodology freeze, not new benchmark evidence.

## 1. The arm boundary (mechanism, not wording)

Unchanged from PAPER-S20's own design, reconfirmed still correct by the PAPER-S7 harness
generalization: every trial is a fresh, non-interactive `claude -p` subprocess with
`--strict-mcp-config` (control: zero MCP servers; treatment: only the local
`meridian-docs-pilot` stdio server, run from this paper repo's own pixi env), `--tools`
(control) / `--disallowedTools` (treatment), and `--add-dir <trial_root>` scoping
filesystem access. `tools/claude_pair_runner.py`'s `audit_isolation()` inspects the
recorded transcript post-hoc rather than trusting the CLI flags alone; two adversarial
canary trials (PAPER-S22) confirmed the boundary holds under an agent actively instructed
to try crossing it, in both directions.

**Generalization since S20 (PAPER-S7):** each trial now exposes exactly the ONE Meridian
tool its own direction needs via `--allowedTools` (e.g. a `citation`-family inverse trial
sees only `remove_citation`, not `insert_citation` too) -- tighter than S20's original
design, which exposed both directions' tools to every trial regardless of which one it
needed.

## 2. Frozen task-family tool matrix

A full source-level investigation of `extensions/meridian-docs/meridian_docs/docs_intel.py`
(20,100 lines) and `server.py` (3,060 lines) was run against every candidate family named in
this item's own scope. Verdicts, with file:line evidence, per family:

| Family | Forward tool | Inverse tool | Verdict | Notes |
|---|---|---|---|---|
| bibliography | `insert_bibliography_entry` | `remove_bibliography_entry` | **usable, in production use** | Keyed purely by `citation_key`; no anchor at all. Known limitation (found 2026-08-30 during long-horizon smoke testing): the forward call locate-or-CREATES a "References" heading the first time it runs on a document without one; the inverse never removes that heading. Both arms are affected identically -- see `docs/paper-s22-harness-verification-v1.md`'s correction section. |
| citation | `insert_citation` | `remove_citation` | **usable, in production use** | Both keyed by the SAME `anchor_para_id`, resolved once by the harness (`docx_anchor_prober.resolve_body_anchor`), never by either agent. Caveat: `remove_citation`/`edit_citation` operate on "the first" CSL_CITATION field in the paragraph -- safe usage is at most one citation per anchor paragraph. |
| caption | `insert_caption` | `remove_caption` | **usable_with_adaptation, blocked in this run by host contention** | `insert_caption` never returns the new caption paragraph's own id; resolved post-forward via `docx_anchor_prober.resolve_para_id_by_marker_text` (a content-based `parse_docx` re-scan, not `locate_anchor`'s seq-number-dependent query). Separately, real and reproduced (2 independent trials, 2026-08-30): `insert_caption` performs a SYNCHRONOUS Word-COM render-verification write gate (`_enforce_render_verification`) that fails closed (restore + error) on a render **timeout**, and `allow_degraded_render` is deliberately NOT honored for a timed-out/failed render (only for a genuinely unavailable backend) -- this is intentional product safety design, not a bug. Under this host's current concurrent-session load, both attempts hit the 60s render timeout. Excluded from this run's family set; a candidate for a future run under lower host contention or a longer render timeout. |
| cross_reference | `insert_cross_reference` | none existed; `remove_cross_reference` now implemented | **not usable in this run** | Confirmed by exhaustive grep: no removal primitive existed as of this investigation. A real gap, fixed separately in the parent repo (`extensions/meridian-docs`, branch `item/remove-cross-reference-mcp`, commit `a89dd999`, 83+379 tests passing) but not yet merged to `dev` as of this run -- another concurrent session held uncommitted changes to the same files, and this project's own rules forbid overwriting another session's in-progress work. Deferred to a future run once merged. |
| table structural (insert_column/split_cell/transpose_table/relocate_table) | various | none for insert_column/split_cell; transpose_table and relocate_table are self-invertible | **not usable in this run** | No whole-table create/remove primitive exists at any level -- confirmed by exhaustive grep across the full 20,100-line module and the complete `server.py` tool list. `insert_figure_block` is an image+caption primitive (inherits caption's render-gate issue), not a table primitive. |
| tracked-change edit | `insert_tracked_paragraph` (exists, NOT registered as an MCP tool) | none | **not usable** | Deliberately scoped narrow per the module's own comment: "insertion only... NOT deletion tracking or accept/reject." No accept/reject/`w:del` primitive exists anywhere in the package, and the insertion-only function is unreachable by any calling agent today regardless. |

**Frozen family set for this run: bibliography, citation, section_reorder.** (`section_reorder`
uses `move_section`, called twice -- see below.) Caption, cross_reference, table, and
tracked-change are explicitly excluded, each for a documented, real reason above, not a
silent omission.

### 2.1 section_reorder

`move_section(docx_path, section_id, destination_anchor_para_id, destination_position)` is
its own inverse: it moves (never copies) the live elements, so `section_id` and every
paragraph/bookmark keep their original id (`docs_intel.py:12620-12623`'s own docstring).
Calling it twice -- once to a destination anchor, once back to the section's original
preceding-neighbor anchor -- restores the original order exactly, using only ordinary
bookkeeping (the harness records the pre-move preceding/following heading ids via
`docx_anchor_prober.resolve_section_reorder_plan`, which requires >=3 headings; not every
document qualifies, and that is recorded as `not_applicable`, never forced).

## 3. Dataset lane and contamination boundary

Per this item's own notes ("must use the same admitted clean-holdout DOCX hashes and cannot
access quarantined or exposed development material"):

- **Corpus**: `manifests/paper-s7-corpus-manifest-v1.json`, derived from the DocOps
  benchmark (`external/docops-source`, Apache-2.0, GitHub `icip-cas/DocOps` commit
  `ccf7a751`) -- **not** the 127-document Meridian gold set, which
  `docs/paper-s9-long-horizon-benchmark-protocol-v0.md` section 2 explicitly rules out as a
  headline corpus (regression-only) and which PAPER-S12 independently found already
  exposed (read/scored 5+ times by this project's own pipeline).
- **License/PII/exposure status**: independently audited by PAPER-S13
  (`docs/paper-s13-docops-word-audit-v1.md`) -- per-file SHA-256, package-integrity, a
  bounded pattern-based PII scan (0 real hits, only RFC-2606 placeholder emails), and
  confirmed genuinely unexposed to this project's own extraction/scoring pipeline by
  PAPER-S12. This is real, completed screening, not a rubber-stamp -- see that audit's own
  explicit statement that the PII screen is pattern-based, not a manual legal-grade review.
- **Split**: DocOps' own preregistered `development`/`smoke`/`scale_up`/`final_holdout`
  split (seed 20260830, dated and fixed before this project's own S7 results existed) is
  reused, not re-derived, and remapped onto this benchmark's development/validation/
  primary-holdout terminology (`tools/build_s7_docops_corpus_manifest.py`). 4 multi-document
  "cross_doc_docops" tasks are excluded (single-document task templates only), leaving 38 of
  the original 42 single-.docx tasks: development=12, validation=12, primary_holdout=14.
- **Leakage rule**: DocOps' split unit is the whole task directory (never a sub-file),
  matching `comparator-contract-v0.md` section 4's "split by document, never by page."
- **Not yet done, explicitly**: a Word-COM render receipt has not yet been generated for
  DocOps' 46 raw input files (only the 38 used here need one; `tools/word_receipt_watchdog.py`
  is reused for this, generated per-trial at chain-start rather than as a separate
  pre-registration step).

## 4. What this item does not decide

Task-pair-count (long-horizon K) sweep values, the confirmatory model, and statistical
aggregation rules are locked in `docs/paper-s7-protocol-v1.md`, not here -- this item's own
scope is the tool matrix and dataset-lane boundary only.
