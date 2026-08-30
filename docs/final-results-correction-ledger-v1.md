# Final-results correction ledger v1

Status: read-only reconciliation of the existing PAPER-35 through PAPER-39 evidence,
2026-08-29. This ledger identifies wording that must be corrected before publication or
before calling the study a complete multi-baseline bakeoff. It does not rerun the scorer.

## Denominator and terminology corrections

| Existing wording/problem | Correct interpretation | Publication rule |
|---|---|---|
| “116 versus 119 documents” | 127 total = 8 tier-1 hand-authored + 116 tier-2 organic/source documents + 3 tier-3 composites. Thus 119 are non-tier-1, but only 116 are the organic tier-2 pool. | Always state total, tier counts, and whether a result is organic, composite, or fixture-only. |
| “0 of the 119 real-world documents contain OMML” | The direct XML audit found 7 OMML-bearing documents among 127 total, all in tier 1/tier 3. The 116 tier-2 documents contain zero OMML. The 3 tier-3 composites are constructed, not real-world. | Say “0/116 organic tier-2 documents” and separately “7/11 fixture/composite documents” only where relevant. |
| “Docling found 0/127 equations” | Most documents have no equation gold. The meaningful organic denominator is 0/116 because none contain equations; the fixture/composite equation denominator is 0/7 equation-bearing documents under the tested PDF path. | Never present 0/127 as broad equation-detection evidence without the zero-prevalence caveat. |
| Table row exact match `n=56` | This is a conditional subset where the metric was defined/scored, not the whole 127-document corpus. | Report the conditional denominator and selection rule beside every table-row number. |
| Per-metric `n` values | Missing/undefined/native-only metrics have different denominators. They are not interchangeable with corpus size. | Keep exact paired `n` in every table and label `not_applicable`, `not_run`, `failed`, and `unknown`. |

## Statistical wording corrections

The permutation procedure used 2,000 paired sign flips. A displayed `p=0.0` means that
zero of 2,000 sampled permutations were at least as extreme; it does not prove a literal
mathematical p-value of zero. Replace every such display with either:

- `p_hat = 0/2000` (empirical resampling result); or
- the conservative upper-bound wording `p < 1/2000` when a conventional p-value is needed.

Retain the exact seed, resample count, paired denominator, and mean difference. Do not
claim significance for equation or paragraph-ID comparisons where there is no paired
comparator value.

## Backend status corrections

The local evidence package is complete for the specifically executed systems, but it is
not a complete SOTA bakeoff:

- Meridian native extraction: 127/127 scored.
- `python-docx`: 122/127 scored; 5 valid Word-renderable documents rejected/crashed because
  its table parser assumed an explicit `w:tblGrid`.
- Docling PDF path: PAPER-36's first run was 120 scored, 6 crashed, 1 timed out; isolated
  retries resolved the 6 crashes but not the 68-page timeout. PAPER-39 is a separate
  graph-aware run with 119 scored, 5 crashed, and 3 timed out before its own retry
  addendum. These runs must not be merged into one headline status.
- Pandoc: not run; not installed/verified.
- LibreOffice: not run; not installed/verified.
- Hosted document-AI: not run by explicit credential, data-handling, and cost gate.
- MinerU, PaddleOCR-VL/PP-StructureV3, and other open candidates: identified but not yet
  installed, frozen, or benchmarked in this environment.

The defensible statement is therefore “full-corpus local Meridian/python-docx comparison
plus full-corpus Docling PDF-path evidence,” not “all current document-AI systems were
beaten.”

## Input-path corrections

Direct-DOCX systems and PDF-only systems answer different questions:

1. Meridian and `python-docx` receive the native DOCX package.
2. Docling receives a PDF rendered from the paired DOCX by Word and cannot observe raw
   OMML, native paragraph identity, revision lineage, provenance bindings, or editability.
3. A PDF-only system's lack of those native fields is `not_applicable`, not a scored zero.
4. Direct-DOCX parser results must never be pooled with rendered-PDF document-AI results as
   one undifferentiated accuracy number.

## Claims currently supported

### Supported with current evidence

- Meridian preserves and exposes native document structure that the tested generic parser
  does not expose, especially native paragraph identity and semantic OMML on the controlled
  equation fixtures.
- `python-docx` has a real robustness failure on valid DOCX packages lacking explicit
  `w:tblGrid`; this is a parser-comparison result, not proof that every generic parser fails.
- On the tested 127-document Word-rendered-PDF path, Docling under-detects table structure
  and is substantially more expensive in the recorded CPU configuration.
- Native OOXML retains facts that are architecturally unavailable to PDF-only processing,
  subject to clearly labeling this as an input-modality capability result.
- **Meridian beats `python-docx` on raw paragraph text fidelity -- resolved 2026-08-30
  (PAPER-S4).** The tab/break reconstruction gap this ledger previously flagged (Meridian
  0.981 vs `python-docx` 0.984, `p=0.903`, a null result) was caused by a real bug in
  Meridian's own native paragraph-text extraction (`docparse.docs_intel._paragraph_text`
  and its vendored copy in `extensions/meridian-docs/meridian_docs/_vendored_content_tree.py`),
  which dropped `<w:tab/>` and `<w:br/>`/`<w:cr/>` entirely -- the identical bug this
  project's own gold extractor had already been fixed for. The parent-repo fix landed at
  `dev@54d6f969` (packages/docparse + meridian-docs extension, 10 new focused regression
  tests, 771+61 existing tests re-run with no regressions, independent verifier PASS). The
  paper scorer was rerun against the unchanged 127-document gold corpus with this fix live
  (editable install, no data/gold changes): Meridian paragraph_node_f1 = 0.9984 [0.9953,
  1.0] vs `python-docx` 0.9836 [0.9665, 0.9956], paired permutation test mean diff
  = +0.0164 favoring Meridian, `p_hat = 0/2000` (n=122 paired documents). This is a real,
  non-inflated result: both extractions now correctly include tab/break characters that
  were always present in the source DOCX, so the improvement reflects genuine content
  Meridian was previously dropping, not a scoring artifact. Report:
  `E:\MeridianData\ooxml-graph-paper\manifests\paper30-graph-eval-all-20260830T070431Z.json`.

### Not currently supported or only narrowly supported

- Meridian beats all document-AI systems or current SOTA. Only Docling was actually run as
  a local document-AI baseline; other candidates remain not run.
- General OMML coverage. Organic tier-2 contains no OMML, and the controlled set covers
  only fractions, radicals, one subscript, and one superscript. N-ary, matrix, accent,
  limit, and multi-script claims require D1 fixtures.
- Complete graph-edge fidelity. The current scorer covers node correspondence, containment,
  and order, but does not separately score all declared edge families such as caption,
  reference, revision, clone, conflict, or source binding.

## Resource-accounting caveats

The current timing and memory figures compare warm-process Python tracing for deterministic
parsers against fresh subprocess RSS for Docling crash isolation. They are useful operational
measurements for the recorded configurations, but not a controlled apples-to-apples systems
benchmark. All reported Docling numbers are CPU-only because the current Torch environment
is `2.13.0+cpu` with CUDA unavailable despite an RTX 3080 being present in the machine.

Use the wording “recorded CPU configuration” and report wall time, process model, memory
method, hardware, and model-loading policy together. A CUDA rerun is a separate experiment,
not a replacement of the CPU result.

## Remaining unscored or unresolved evidence

- Native graph edges: `caption_for`, `references`, `revises`, `clones`, `conflicts_with`,
  and `source_binding` need explicit candidate adapters and edge-level scores.
- Caption and reference detection on the organic corpus is not fully validated.
- CJK text-token F1 needs character-aware or script-aware scoring.
- The Word render receipt is retained, but the audit-grade receipt schema should continue to
  retain source/PDF hashes, Word build, export method, page count, freshness, and cleanup.
- One long document exceeds the practical Docling CPU timeout even after a 3x retry.

## Final gate wording

The executed local comparison can be called terminal under the local-track contract if the
terminal manifests and receipts are retained. The overall paper must still call the SOTA
comparison incomplete until at least one additional selected open candidate is frozen and
run, or explicitly narrow its claim to Meridian versus `python-docx` plus Docling. No final
publication claim should imply that the hosted track or every OmniDocBench-listed model ran.
