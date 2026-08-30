# Benchmark preregistration v0 (PAPER-19)

Status: preregistration draft, not accepted. **No final benchmark execution (PAPER-15) may run until
this document's Acceptance Checklist (§8) is entirely checked, in writing, by a human.** This is a
design/consolidation document — it does not itself acquire data, run code, or produce results.

This document does not redefine anything already frozen elsewhere. It locks the pieces those
documents left open (splits, seed, frozen baseline versions, equation semantic labels, failure
taxonomy consolidation, accounting scope, retention) and adds one acceptance gate. Read in this
order before this document: `graph-gold-schema-v0.md` (node/edge/gold-record shape), `comparator-contract-v0.md`
(tracks/baselines/metrics/split policy), `dataset-landscape-2026-08-25.md` including its 2026-08-26
PAPER-12 addendum (source inventory + gold-set sketch), `runtime-capability-contract-v0.md` (what's
actually runnable locally), `omml-builder-audit-v0.md` (PAPER-11 — feeds the equation semantic labels
below), `word-roundtrip-preservation-contract-v0.md` (PAPER-16), `ooxml-package-safety-audit-v0.md`
(PAPER-17), `converter-backend-acceptance-matrix-v0.md` (PAPER-10 — feeds the frozen baselines below).

## 1. Document strata (locked, inherited from PAPER-12 — not redefined)

Three tiers, ~30-40 documents total: minimal hand-authored fixtures (~15-18), real-world native
documents (~10-12), composite stress documents (~4-6). Full rationale and per-tier construction rules
are in `dataset-landscape-2026-08-25.md`'s "Gold-set sketch" section. This document adds only the
split/seed mechanics those tiers get assigned to (§3) — the tiers themselves are not re-litigated here.

## 2. Source licensing and privacy (locked, inherited — status unchanged)

No corpus has been downloaded or staged. Per PAPER-12's inventory, the only individually-license-clear
candidate for tier-2 real-world documents today is `docx-benchmark/fixtures/series-seed` (CC0-1.0,
verified via its own `LICENSE-INFO.txt`); every other candidate source (OCB, OmegaUse-OfficeVal,
docx-corpus, the remaining `docx-benchmark` fixture folders) requires per-file license confirmation
before use, not blanket trust in a dataset-level tag. No PII/privacy review has been performed because
no real-world third-party document has been staged yet; this is a precondition of §8, not a completed
step. Any tier-2 document sourced from a real person's or organization's content must have that
confirmed before staging, recorded in the document's own gold-record `provenance` field.

## 3. Document-level splits and seed (new — not defined elsewhere)

- **Seed: `20260826`** (the date this preregistration was drafted, chosen for a fixed, citable,
  non-cherry-picked value — not tuned after seeing any result, because no result exists yet).
- **Split unit: whole documents**, never pages or paragraphs, per `comparator-contract-v0.md` §4 ("Split
  by document, never by page"). A single document's nodes/edges/facts never cross a split boundary.
- **Three slices**, matching `comparator-contract-v0.md`'s existing three-stage testing philosophy
  (smoke → scale-up → final), applied to this gold set specifically:
  - **Smoke slice (fixed, hand-picked, not seed-dependent):** exactly one document per tier-1 fixture
    category named in the PAPER-12 sketch (equation, numbered equation, malformed-OMML, table, caption,
    dangling-anchor, duplicate-paraId, tracked-change, clone) — roughly 10-12 documents. Hand-picked
    rather than randomized so every structural invariant in `graph-gold-schema-v0.md` is guaranteed
    exercised at least once even in the smallest run.
  - **Scale-up slice:** the remaining tier-1 fixtures plus all tier-2 real-world documents, order
    shuffled using `seed=20260826` (Python `random.Random(20260826).shuffle(doc_ids)` over the
    lexicographically-sorted document-id list, so the procedure is exactly reproducible from the seed
    alone without needing to store the shuffled order separately).
  - **Final test slice:** all tier-3 composite stress documents, held out and never used for debugging
    the extractor during development (per PAPER-12's independence rule) — evaluated exactly once, after
    the scale-up slice's results are already reported, never re-run to chase a better number.
- Given the total corpus is ~30-40 documents (deliberately small and hand-verifiable per §1), there is
  no separate train/dev/test split in the ML sense — every document is evaluation-only. "Split" here
  means staged disclosure order (smoke → scale-up → final), not a held-out training partition.
- Bootstrap confidence intervals (per `comparator-contract-v0.md` §4) are computed over the **scale-up +
  final** slices combined at report time (≈20-28 documents), not the smoke slice alone — too small a
  sample for a meaningful interval.

## 4. Frozen baselines (new — pins specific versions from PAPER-10's matrix)

`converter-backend-acceptance-matrix-v0.md` (PAPER-10) inventoried candidates; this section is where
the actual run-list gets pinned. **No version has been installed or pinned yet** — the table below
names which baselines from that matrix this paper intends to actually run, and what "pin" means for
each; the version column is filled in at the point a baseline is actually installed for a real run,
not before (a preregistration that pins a version number nobody has installed yet would itself be an
unverified claim, which this project's own standing rule forbids).

| Baseline | Category (PAPER-10) | Intent | Version pin status |
|---|---|---|---|
| Native Meridian OOXML/OMML graph extraction | — (implementation under test) | primary | pinned to the exact `docs_intel.py` git SHA at run time, recorded in the run manifest (§6) |
| python-docx | A (genuine OOXML writer) | Track A baseline | not yet installed; pin its exact PyPI version at install time |
| LibreOffice headless conversion | A (re-derived, non-identity-preserving) | Track A ablation / Track C second renderer | **not installed on this host** (confirmed multiple times this sprint) — blocked until installed |
| Pandoc | B (lossy conversion baseline, explicitly labeled as such) | Track A comparison, never pooled with Track A native scores | not yet installed; pin exact version at install time |
| Aspose.Words | A (paid) | excluded — no budget authorization sought in this sprint | excluded, not blocked-pending |
| Docling (PDF pipeline) | document-AI track (comparator-contract-v0.md §7) — not Track A, never pooled with native/parser scores | **pinned and installed** (PAPER-28): `docling==2.123.0` (`docling-core` 2.92.0, `docling-ibm-models` 3.14.0, `docling-parse` 7.16.0, `transformers` 5.16.1, `torch` 2.13.0+cpu). First real capability probe (`docs/dataset-landscape-2026-08-25.md` PAPER-28 section) found 0/2 formulas and 0/2 tables recovered from a Word-COM-rendered PDF with default settings (`do_formula_enrichment=False`), versus 2/2 formulas via Docling's own separate DOCX backend (a parser/converter code path, not document-AI) and 2/2 via native Meridian — a first data point, not the full-corpus PAPER-31 run. |
| Docling (own DOCX backend) | A (deterministic structural parser, same family as python-docx/Pandoc) | Track A comparator, only if a fair-use case is made for including a second parser baseline — not yet decided | installed alongside the PDF pipeline above (same package); must be labeled as a parser/converter result, never reported as a document-AI result if used |
| Unstructured / MinerU / Mammoth.js | C (no OOXML output) | out of scope for Track A (input-only, cannot produce a comparable graph); may be cited as prior-art context only | not planned to be installed for this benchmark |
| Google Document AI / Azure Document Intelligence / AWS Textract | document-AI track, hosted (comparator-contract-v0.md §7, PAPER-32) | optional, gated on explicit credential + data-handling + cost approval | **not_run** — no credential, data-handling approval, or cost approval supplied; not substituted with manual Claude PDF reading per explicit user instruction |
| DocBank BERT/RoBERTa/LayoutLM reference numbers | Track B historical | reproduced only if exact checkpoint + preprocessing are available (comparator-contract-v0.md §2) | not attempted — no checkpoint sourced |

Any baseline actually run must have its installed version captured in the run manifest (§6) — this
table is the intent list, the manifest is the executed record. Per `comparator-contract-v0.md`, "No
model is called 'latest' without a dated version record."

## 5. Equation semantic labels (new — derived directly from PAPER-11's live audit)

`graph-gold-schema-v0.md` names `equation` as a node kind but does not sub-classify it. PAPER-11's
audit (`omml-builder-audit-v0.md` §9) produced exactly the taxonomy needed; this section adopts it as
the gold-record `facts.equation_class` label set for every equation node, rather than re-deriving one:

| Label | Meaning | Source |
|---|---|---|
| `correct` | Native OMML structurally matches the source LaTeX/Word semantics | PAPER-11 Class 1 |
| `lossy_reviewed` | Structurally valid, semantically approximate, and the approximation is named/reviewed (e.g. side-script sum/lim, dropped fence, numbering leak) | PAPER-11 Class 2 |
| `fails_closed` | Insertion correctly refused; no equation node exists to score | PAPER-11 Class 3 |
| `fallback_forbidden` | Flattened text masquerading as an equation with no matching structural element — must never appear in an accepted gold document | PAPER-11 Class 4 |
| `package_render_divergent` | Passes package-integrity validation but a real renderer refuses to open it, or vice versa | PAPER-11 Class 5 |
| `empty_required_child` | A required child tag is present but itself carries no content (e.g. `\frac{}{}`, `\min` argument) | PAPER-11 Class 6 |

A gold document containing an equation must record which label applies, from direct inspection of the
real OMML — the same independence rule as §3 of `dataset-landscape-2026-08-25.md` applies: the label is
assigned by the human/second-tool gold process, never by running `docs_intel.py`'s own validator and
trusting its verdict as ground truth.

## 6. Caption/reference/source/revision binding verification (new — operationalizes existing edges)

For each of `graph-gold-schema-v0.md`'s structural edges that a gold document exercises, the
independent labeler must record, per instance, exactly what a downstream metric checks:

- **`caption_for`**: does the caption paragraph's target resolve to exactly one figure/table (not zero,
  not multiple)? Record the resolution state explicitly (`resolved` / `ambiguous` / `dangling`) per
  invariant 3 in the schema — never silently pick one candidate.
- **`references`**: for every REF/PAGEREF/NOTEREF-style field or literal in-text mention, does its
  cached display text match the CURRENT target numbering at gold-authoring time? A stale cached
  reference is a distinct, recordable fact, not an error to silently correct.
- **`source_binds`**: for a generated/derived artifact node (e.g. a render receipt, a normalized fact),
  does it name the exact source file/part it was derived from?
- **`revises`**: for any document with more than one recorded revision, does the chain form a strict
  linear (or explicitly branching, if the schema is extended later) history with no erased prior
  revision?
- **`clones`**: for any copied node (exercising `copy_section`), does the clone carry a fresh native ID
  and an explicit `clones` edge back to its origin, per invariant 4?

Each of these becomes a per-instance boolean/enum fact in the gold record's `facts` block, not a
separate schema change — `graph-gold-schema-v0.md` already has the edge types; this section defines
what "correct" means operationally for scoring.

## 7. Failure taxonomy (consolidated, not new — merges comparator-contract-v0 + this sprint's audits)

`comparator-contract-v0.md` §3 already names: malformed input, unsupported construct, ambiguous anchor,
ID collision, renderer unavailable, stale receipt, environment failure. This sprint's investigation
items found concrete instances that map onto (not replace) that taxonomy, and one gap the taxonomy
should absorb:

| Existing category | New concrete instance found this sprint | Source |
|---|---|---|
| malformed input | billion-laughs XML entity expansion (no depth/size guard on internal entity expansion) | PAPER-17 |
| malformed input | duplicate ZIP part name (last-write-wins on read, never healed on write) | PAPER-17 |
| unsupported construct | `\min`/`\max`/`\operatorname{argmin}` → permanently empty `m:func` operand | PAPER-11 |
| unsupported construct | `mfenced`/fence loss for `\left...\right`, matrix brackets, `\binom` bar | PAPER-11 |
| ambiguous anchor | Word round-trip rewrites every `w14:paraId`/`textId`, breaking `anchor_para_id` addressing across a human edit session | PAPER-16 |
| renderer unavailable | LibreOffice not installed on this host (recurring, confirmed every session this sprint) | PAPER-4, PAPER-10, PAPER-16 |
| stale receipt | render receipts are transient (PDF consumed, not retained) unless a document is explicitly in the gold-set retention path (§9) | PAPER-11, dataset-landscape PAPER-12 addendum |
| **(new category)** `package_render_divergent` | `ooxml_integrity.validate_docx_package` reports clean on a file real Word COM refuses to open as corrupted | PAPER-11 §5.7/§8, independently corroborated by PAPER-16 finding the same test fixture's placeholder theme is schema-invalid DrawingML |

This is a reporting taxonomy for scoring failed/degraded rows, not a design spec for fixing each
instance — PAPER-13/14/20 (and future items) own the fixes; this table exists so the eventual PAPER-15
report can bucket every observed failure into a named, non-overlapping category instead of free text.

## 8. Token/runtime/resource accounting scope (confirms, does not extend, comparator-contract-v0 §3)

Full definition already lives in `comparator-contract-v0.md` §3 ("Efficiency and cost"): wall time, CPU
time, peak RSS, peak VRAM, disk bytes written, model/checkpoint bytes, input/output token counts with
tokenizer/counting method recorded, network bytes and provider cost where applicable, and an explicit
"deterministic code paths report zero model tokens but still report CPU/memory/disk/wall-clock" rule.
This preregistration adds one clarification for THIS benchmark specifically: because the primary Track
A baseline (native `docs_intel.py`) and python-docx/Pandoc are all deterministic, non-model code paths,
the *dominant* accounting axis for this paper's central claim is wall time + peak RSS + disk bytes, not
token cost — token/VRAM accounting only becomes load-bearing if/when a model-based baseline (an LLM
judge, a VLM OCR baseline) is added, which is not currently planned. GPU baselines, if run, must fit the
locally-confirmed RTX 3080's 20 GB VRAM per `runtime-capability-contract-v0.md`.

## 9. Artifact retention

- **Gold-set documents, gold records, and their render receipts**: retained indefinitely under
  `E:\MeridianData\ooxml-graph-paper\` (never OneDrive, never the paper subproject's own folder, per the
  standing storage rule) — these are the one-time-cost, hand-verified asset the whole benchmark depends
  on and must not be silently regenerated or lost.
- **Per-run outputs** (baseline outputs, computed metrics, raw scores): retained per run under
  `E:\MeridianData\ooxml-graph-paper\runs\<run_id>\`, keyed by a run manifest (below) — not overwritten
  by a later run.
- **Run manifest**, one per executed benchmark run, must record at minimum: dataset revision (gold-set
  version/hash), code revision (git SHA of `docs_intel.py` and this paper's own repo state), every
  frozen baseline's installed version (§4), hardware (this host's confirmed RTX 3080 20GB, CPU/RAM),
  wall time, and output hashes for every scored artifact. This is the same manifest shape
  `runtime-capability-contract-v0.md` and `comparator-contract-v0.md` §5 already require; this section
  confirms it applies to gold-set runs too, not just ad hoc probes.
- **Retention horizon**: no explicit deletion policy is set here (open item — a human should set one,
  e.g. "keep all runs for the life of the paper, prune after publication + N months"); until a horizon
  is set, the default is indefinite retention on E:.

## 10. Acceptance checklist — ALL of the following must be true, and signed off by a human, before PAPER-15 executes

- [ ] Gold-set corpus (§1) actually built: ~30-40 documents across all three tiers, not just sketched.
- [ ] Every gold document licensed/privacy-cleared per §2, with provenance recorded.
- [ ] Split/seed assignment (§3) actually computed and recorded (not just this document's procedure —
      the actual resulting document-id lists for smoke/scale-up/final).
- [ ] At least the Track A baselines in §4 (python-docx, Pandoc) actually installed with versions
      recorded; LibreOffice installed or explicitly declared out of scope for this run with reasoning.
- [ ] Every equation node in the gold set labeled per §5.
- [ ] Every caption/reference/source/revision-edge instance verified per §6.
- [ ] PAPER-13 (OMML hardening) and PAPER-14 (converter bakeoff harness) complete.
- [ ] PAPER-20 (integrated acceptance gate) passes.
- [ ] PAPER-8 (human render/Word authority gate) formally approved.
- [ ] A run manifest template (§9) is ready to be filled in for the actual run.

**Current status: 0 of 10 checked.** This preregistration exists so that, when work resumes on this
track, it is unambiguous what "ready to benchmark" means — not to claim readiness now.

## 11. PAPER-30: the graph-aware scorer this document originally deferred

Section 4's baseline table and this checklist both predate a real graph-aware scorer -- until
PAPER-30, only a simplified count/overlap proxy existed (`paper15-first-attempt-v0.md`). That gap
is now closed: `tools/graph_scorer.py` + `tools/run_paper30_graph_eval.py` implement real node-level
correspondence (not just counts), precision *and* recall (not recall alone) by node kind, a
non-tautological reading-order metric, independently re-derived equation semantic-class accuracy,
bootstrap 95% confidence intervals, and paired document-level permutation tests. Full results and
methodology: `docs/paper30-graph-scorer-v0.md`. This does not change the checklist above (the gold
corpus, license review, and Word/LibreOffice items are unrelated to the scorer), but it does mean a
real graph-level evaluation has now actually been *run* against the full 127-document corpus, not
merely specified.
