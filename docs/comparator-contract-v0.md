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

Sources: [DocBank repository](https://github.com/doc-analysis/DocBank), [DocBank dataset card](https://huggingface.co/datasets/liminghao1630/DocBank), [DocBank paper](https://arxiv.org/abs/2006.01038).
