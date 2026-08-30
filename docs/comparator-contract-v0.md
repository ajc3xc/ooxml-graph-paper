# Comparator contract v0

Status: execution design; no benchmark results are claimed.

## 1. Evaluation tracks

### A. Primary: native DOCX/OOXML graph fidelity

Input is a `.docx` artifact. The gold record is an independently produced graph manifest, not merely the output of the implementation under test. Nodes include document parts, sections, paragraphs, runs, tables, cells, equations, captions, figures, anchors, references, and revisions. Edges include containment/order, anchor ownership, caption/reference linkage, source binding, and revision lineage.

This is the only track that can directly test the native-Word-XML thesis.

### B. Secondary: public PDF/layout context

DocBank is a public PDF/token-layout benchmark. Its official repository reports 500K pages split into 400K train, 50K development, and 50K test pages, with 12 semantic-unit labels. It is useful for evaluating PDF/layout parsers and for reproducing published BERT/RoBERTa/LayoutLM context, but it is not a paired DOCX/OOXML gold set.

DocBank must therefore be reported as a separate context track, never pooled with Track A scores.

### C. Rendered-parity track

Render the same DOCX through Microsoft Word as the canonical product authority. LibreOffice may provide a separately labeled compatibility comparison, but it must never stand in for Word fidelity or make a Word receipt appear verified. Compare page images, text extraction, table geometry, equation presence, captions, and reference placement. A render failure or unavailable Word environment is `unknown` or `fail`, never an unobserved pass.

### D. Native Office comprehension track

Use Word/LibreOffice structural and visual checks to test whether the produced DOCX remains natively understandable and editable. This is a human/tool acceptance gate, not a replacement for graph-level metrics.

## 2. Baselines

Track A baseline families:

1. Native Meridian OOXML/OMML graph extraction.
2. Generic DOCX extraction using the available parser stack, with structure deliberately normalized to the common schema.
3. Conversion-mediated extraction, such as DOCX-to-HTML/PDF/text, clearly labeled as a lossy conversion baseline.
4. Controlled ablations: remove paragraph IDs, remove raw XML/OMML, flatten tables, flatten equations, and disable render receipts.

Track B baseline families:

1. Existing local DocBank scoring pipeline.
2. Published DocBank BERT, RoBERTa, and LayoutLM reference numbers, reproduced only when the exact checkpoint and preprocessing are available.
3. One or more current open parser/model baselines selected after an availability and license audit. Each must have a frozen version, input modality, model size, hardware, and token/cost accounting.

No model is called “latest” without a dated version record.

## 3. Metrics

### Structural correctness

- Node precision, recall, and F1 by node type.
- Edge precision, recall, and F1 by edge type.
- Exact-match rate for paragraph identity, containment, order, caption ownership, references, and source bindings.
- Duplicate-ID, collision, orphan, and unresolved-reference rates.

### Content correctness

- Normalized text exact match, token F1, character edit distance, and order violations.
- Table cell/row/column structure F1, including merged-cell handling.
- Equation semantic match from canonical OMML structure, not flattened text alone.
- Equation punctuation/notation validity and missing/duplicated OMML rates.
- Caption, figure, table, and reference linkage accuracy.

### Render and operational correctness

- Word and LibreOffice render receipt pass/unknown/fail rates.
- Page-count, text-position, table-geometry, and equation-visibility discrepancies.
- Atomic-write, provenance-binding, and post-write verification pass rates.
- Failure taxonomy: malformed input, unsupported construct, ambiguous anchor, ID collision, renderer unavailable, stale receipt, and environment failure.

### Efficiency and cost

- Wall time, CPU time, peak RSS, peak VRAM, disk bytes written, and model/checkpoint bytes.
- Input/output token counts for model/API baselines, with tokenizer and counting method recorded.
- Network bytes and provider cost where applicable.
- For deterministic code paths, report zero model tokens but still report CPU, memory, disk, and wall-clock costs.

Efficiency is secondary to correctness and must not be used to hide a failed structural or render gate.

## 4. Split and statistical policy

- Split by document, never by page, for any newly assembled DOCX corpus.
- Preserve DocBank’s official train/dev/test split for Track B reproduction.
- First smoke slice: a small, deterministic manifest selected across document types and equation/table/caption strata.
- Scale-up slice: stratified validation subset with fixed random seed and no test-set tuning.
- Final test: one locked evaluation manifest, with bootstrap confidence intervals and paired per-document comparisons.
- Report macro and micro aggregates; do not average page scores as if pages were independent documents.

## 5. Comparability rules

- Do not compare a native DOCX graph score directly to a PDF layout score.
- Do not compare a parser after conversion against native OOXML without reporting conversion loss separately.
- Every result row records input artifact hash, dataset revision, code revision, model revision, environment, hardware, and receipt status.
- Missing renderer or model availability produces an explicit `not_run`/`unknown` row, not a silently omitted baseline.

## 6. Scope boundary

This contract does not authorize full-corpus download, model training, or reactivation of unrelated 2030 experiments. Those begin only after the DOCX gold-set source, Word render authority, and baseline availability gates are satisfied.

### 6.1 A distinct, fourth kind of claim: agentic editing, not extraction (PAPER-S9)

Everything in this contract (Tracks A-D, Claims 1-3 in §7 below) evaluates **extraction/fidelity**:
given a `.docx`, how well does a system read or render it. `docs/paper-s9-long-horizon-benchmark-protocol-v0.md`
specifies a different, fourth comparison this project also intends to make: **same Claude model,
same starting document, same task, Claude editing without Meridian's MCP tools versus Claude
editing with them** -- an agentic-writing/editing benchmark with its own paired forward/inverse-task
design, round-trip-confound accounting, and two-tier (fast validator + milestone Word COM)
verification pipeline. It is not folded into Claims 1-3 above and must not be pooled with their
scores.

Sources: [DocBank repository](https://github.com/doc-analysis/DocBank), [DocBank dataset card](https://huggingface.co/datasets/liminghao1630/DocBank), [DocBank paper](https://arxiv.org/abs/2006.01038).

## 7. PAPER-27: dual-track claim contract (native-OOXML vs. document-AI)

Frozen per PAPER-27. This section resolves a real ambiguity found in the first PAPER-15
attempt: "baseline" was being used for two different kinds of systems (parser libraries
that read the same `.docx` bytes, and systems that only ever see a rendered PDF). They are
not comparable on the same footing and must not be pooled.

### 7.1 Two tracks, not one

- **Native-OOXML track** (this paper's product claim). Input: the `.docx` package
  directly. Systems: Meridian's native extraction/writing (`document_content_tree`,
  `parse_docx_equations_local`), and parser/converter comparators that also read the
  `.docx` bytes directly -- **python-docx, Pandoc, LibreOffice are parser/converter
  comparators in this track, not document-AI systems.** They see the same native facts
  Meridian does (paragraphs, tables, raw OMML where their format supports it); the
  question is whether they preserve/expose those facts as well as Meridian does.
- **Document-AI track** (a separate, harder comparison). Input: the *rendered PDF only*
  -- the same source `.docx`, rendered through Word COM (canonical render authority,
  per PAPER-8/`runtime-capability-contract-v0.md`), then handed to a system that has
  **no access to the original OOXML** -- only pixels/text-layer-of-a-PDF. Candidate
  systems: Docling (local, open, pinned per PAPER-28) and, optionally and separately, one
  approved hosted document-AI processor (PAPER-32, gated on explicit credential/data/cost
  approval -- `not_run` otherwise, never silently substituted).

**Claude manually reading a rendered PDF in this conversation is exploratory only.** It is
not wrapped in a fixed API/model/prompt harness, is not reproducible run-to-run in the way
a pinned model+prompt+temperature would be, and must never be reported as a primary
benchmark baseline. Where used at all, it appears as labeled qualitative appendix evidence,
never pooled into the document-AI track's scored metrics.

### 7.2 Three distinct claims (do not conflate)

Per PAPER-35's own framing, this paper can support up to three separate claims, and each
needs its own evidence -- proving one does not prove the others:

1. **Native Meridian OOXML/OMML preserves and editably writes Word structure.** Evidenced
   by the gold corpus + render receipts + round-trip findings already gathered
   (`gold-corpus-status-v0.md`, `word-roundtrip-preservation-contract-v0.md`).
2. **Deterministic native extraction beats generic same-format parsers** (python-docx,
   Pandoc, LibreOffice) **on native-structure tasks.** Evidenced by the native-OOXML track
   above, scored against independent graph gold. This is the claim `paper15-first-attempt-v0.md`
   has real, if partial, evidence for already (para-ID preservation, equation extraction,
   crash resistance).
3. **Native OOXML exposes information and guarantees unavailable to rendered-PDF
   document-AI systems.** This is the hardest, most novel claim, and per PAPER-35's own
   gate: **it requires a real, reproducible document-AI baseline (Docling at minimum) or
   must be framed as a capability/observability analysis, not reported as a scored
   accuracy victory** if no such baseline ran. Do not claim (3) from claim (2)'s evidence.

### 7.3 What cannot be inferred from a PDF-only reader, by construction

These are not measured as "0% recall" against a system that was never asked -- they are
recorded as **not-applicable / unknown**, with the reason being architectural, not a
system failure: native `w14:paraId` / paragraph identity (a PDF has no paragraph-identity
concept at all); revision history (`w:ins`/`w:del` -- rendering flattens tracked changes to
their accepted-or-rejected visual state); source bindings / provenance metadata (not part
of any rendered page); direct editability (a PDF is not a `.docx` -- there is nothing to
write back to); and raw OMML structure (a PDF equation is pixels or, at best, a
vision-model's re-derived guess at the math, not the original `<m:oMath>` tree). Section
7.4's denominators formalize this.

### 7.4 Paired-input rules, denominators, and failure categories

- **Paired input**: every document-AI-track result row must name the exact source `.docx`
  hash it was rendered from, matching a native-OOXML-track row for the same document --
  never report a document-AI number without its paired native-track number alongside it.
- **Denominators**: a metric that is architecturally not-applicable to PDF-only input
  (7.3) is excluded from that system's denominator entirely -- it is not scored as 0 and
  does not silently drop out of the reported metric list; it is listed with an explicit
  `not_applicable` status and a one-line reason, per document-AI-track system.
- **Failure categories** (recorded per document, per system): `crashed`
  (raised/terminated before producing output), `timed_out`, `malformed_input` (system
  rejected a valid Word-renderable file), `not_applicable` (7.3), `not_run` (system
  unavailable/ungated, e.g. PAPER-32 without approval), and `scored` (a real comparable
  result exists).
