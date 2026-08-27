# PAPER-15: first real Track A comparison attempt (v0)

Status: **a real, honestly-scoped first attempt on the smoke slice, not the complete
preregistered benchmark.** Explicit scope limitations below, not silently omitted.

## Scope of this attempt

- **2 of 4** Track A baseline families from `comparator-contract-v0.md` §2: (1) native
  Meridian OOXML/OMML extraction (`document_content_tree` + `parse_docx_equations_local`,
  the real product code), (2) generic DOCX extraction via python-docx. Pandoc
  (conversion-mediated) and controlled ablations are recorded as `not_run` per §5's
  comparability rule ("missing... produces an explicit not_run/unknown row, not a
  silently omitted baseline") -- Pandoc is not installed on this host.
- **Metrics are a simplified count/overlap-based proxy**, not the full node
  precision/recall/F1-by-type + graph-edit-distance scorer `comparator-contract-v0.md`
  §3 specifies -- that complete scorer does not exist yet. This attempt reports
  paragraph/table/row/equation count recall (capped at 1.0, undefined when gold has zero
  instances) and text token F1 via `difflib.SequenceMatcher`, plus wall time and peak RSS.
- Track C (render-parity) and full efficiency/cost accounting are not covered here.
- Run only against the **smoke slice** (10 of 127 documents), per §4's staged-evaluation
  design -- this is intentionally the first, smallest slice, not the locked final manifest.

## A real scoring bug found and fixed while building this

The gold reference initially counted every paragraph node, including ones nested inside
table cells (a real, correct part of the graph schema). Neither baseline enumerates those
as separate paragraph records (`document_content_tree`'s body walk and python-docx's
`.paragraphs` are both top-level-only; cell text is still captured, just as part of the
table's row/cell data, not as distinct paragraph nodes). Comparing gold's inclusive count
against either baseline's top-level-only count produced a spurious ~58% "recall" for
*both* baselines alike on the first run -- confirmed by inspection (one smoke document:
439 gold paragraph nodes, 433 of them cell-nested) to be a counting-scope mismatch, not a
real extraction gap. Fixed to compare top-level-only counts on both sides; recall for
both baselines is 1.0 after the fix.

## Results: smoke slice (10 documents, all scored, zero crashes)

| Metric (macro avg) | native_meridian | python_docx |
|---|---:|---:|
| paragraph_count_recall | 1.0 | 1.0 |
| table_count_recall | 1.0 | 1.0 |
| table_row_recall | 1.0 | 1.0 |
| equation_count_recall | undefined (0 equations in this slice) | undefined |
| text_token_f1 | 0.798 | 0.782 |
| **para_id_preservation_rate** | **1.0** | **0.0** |
| wall_time_seconds (mean) | 0.123 | 0.065 |
| peak_rss_bytes (mean) | 3.58 MB | 6.43 MB |

Full report: `E:\MeridianData\ooxml-graph-paper\manifests\paper15-smoke-run-20260827T223203Z.json`.

**The random smoke draw happened to contain zero equation-bearing documents** -- an honest
gap, not a hidden one. See the addendum below.

## Equation addendum (not part of the random smoke sample -- targeted, not silently added to the aggregate)

All 7 documents in the entire 127-document corpus with at least one gold equation node
(all 7 are hand-authored tier1/tier3 fixtures -- **zero of the 116 real-world documents
contain any native OMML equation at all**, a real limitation of this corpus's composition
for testing equation fidelity against real-world content, not just synthetic fixtures):

| Document | Gold equations | native_meridian found | python_docx found |
|---|---:|---:|---:|
| fixture-02-equation | 1 | 1 | 0 |
| fixture-06-equation-radical | 1 | 1 | 0 |
| fixture-07-equation-empty-child | 1 | 1 | 0 |
| fixture-08-equation-fallback | 1 | 1 | 0 |
| composite-01-report | 1 | 1 | **crashed** |
| composite-02-adversarial | 1 | 1 | **crashed** |
| composite-03-multi | 2 | 2 | **crashed** |

**native_meridian: 7/7 correct equation counts.** **python_docx: 0/4 equations found where
it ran, and crashed on all 3 remaining documents** with
`InvalidXmlError: required <w:tblGrid> child element not present` -- these 3 documents
have real, valid, Word-openable tables (confirmed rendered via real Word COM,
`docs/gold-corpus-status-v0.md`) that simply lack an explicit `<w:tblGrid>` element, which
OOXML does not strictly require but python-docx's `Table.columns` property does. This is a
genuine baseline robustness gap, not manufactured: python-docx cannot even be asked about
these documents' equations without crashing first on their table structure.
Full data: `E:\MeridianData\ooxml-graph-paper\manifests\paper15-equation-addendum.json`.

## Runner readiness update (2026-08-27)

The runner now accepts `--slice smoke|scale_up|final|all` and can execute the
entire 127-document structural pass. Each row records the input DOCX hash and
gold-manifest hash; the run records the corpus-manifest hash, Python/package
environment, explicit availability of Pandoc/LibreOffice, baseline status
counts, and deterministic model-token count (`0`). The memory metric is named
`peak_python_allocated_bytes` because it comes from `tracemalloc`; it is not
process RSS.

Example:

```
pixi run python tools/run_paper15_smoke.py --slice all
```

This is still a structural Meridian-vs-`python-docx` pass. Pandoc, LibreOffice,
PDF/vision/document-AI adapters, Track C render parity, and the complete
node/edge graph scorer remain explicit `not_run`/out-of-scope fields until
those adapters and metrics are implemented and pinned.

## Reading this honestly

The one metric that actually tests this paper's central claim --
`para_id_preservation_rate` -- shows exactly the expected, stark gap (1.0 vs 0.0), and the
equation addendum reproduces PAPER-14's structural finding empirically rather than just
citing it (native: 7/7 correct; python-docx: 0/4 plus 3 crashes). The other structural
metrics (paragraph/table/row recall) are equal between baselines once the counting-scope
bug was fixed -- that is a correct, honest null result on those specific axes, not a
failure to find a difference. This is a first attempt: no Pandoc/LibreOffice baseline, no
full graph-edit-distance scorer, no equation coverage in the random smoke sample, and only
10 of 127 documents. It does not constitute the complete, locked PAPER-15 benchmark
`benchmark-preregistration-v0.md` describes.

## Broad structural pass (127 documents, 2026-08-27T23:42Z)

After the smoke attempt, the same runner was executed against all 127 gold
documents. This is a broad structural pass, not a claim that the complete
native-vs-AI benchmark is finished.

| Metric (macro average) | native_meridian | python_docx |
|---|---:|---:|
| paragraph/table/row count recall | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| equation count recall | 1.0 | 0.0 |
| text token F1 | 0.727 | 0.694 |
| conditional native paragraph-ID preservation | 0.995 | 0.0 |
| wall time per document (seconds) | 0.097 | 0.034 |
| peak Python allocation | 2.41 MB | 2.63 MB |

Native Meridian scored all 127 documents. `python-docx` scored 122 and
crashed on 5 valid Word-renderable documents with
`InvalidXmlError: required <w:tblGrid> child element not present`. The equation
track contains 7 documents; Meridian found all equations, while `python-docx`
found none on the documents where it completed and crashed on the three
composite equation documents.

The ID metric is conditional: 95 documents contain native gold paragraph IDs
and are ID-evaluable; 32 do not and are reported as unavailable rather than
treated as failures. Meridian's one non-perfect case is the intentionally
adversarial duplicate-`paraId` composite and is retained as a failure to
investigate, not silently normalized away.

Full report: `E:\MeridianData\ooxml-graph-paper\manifests\paper15-smoke-run-20260827T234225Z.json`.

Still missing for the original thesis: a complete graph node/edge scorer, a
pinned PDF/AI or vision baseline on Word-rendered inputs, conversion baselines
(Pandoc/LibreOffice), and Track C render-parity metrics. This broad pass is
evidence for native DOCX robustness against a generic DOCX parser, not yet
evidence that deterministic OOXML beats document-AI systems.
