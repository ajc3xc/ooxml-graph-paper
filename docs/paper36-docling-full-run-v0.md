# PAPER-36: full 127-document Docling comparison (v0)

Status: the complete corpus-wide Docling run PAPER-31 explicitly deferred for resource-budget
reasons. All 127 documents now have a terminal status for every backend. Report:
`E:\MeridianData\ooxml-graph-paper\manifests\paper15-smoke-run-20260828T154212Z.json`.
Checkpoint (incremental, resumable): `paper15-all-run-20260828T133716Z.checkpoint.jsonl`.

## Terminal status, every document, every backend

| Backend | scored | failed | crashed | timed_out |
|---|---:|---:|---:|---:|
| native_meridian | 127 | 0 | 0 | 0 |
| python_docx | 122 | 5 | 0 | 0 |
| docling_pdf_document_ai (as originally run) | 120 | 0 | 6 | 1 |
| docling_pdf_document_ai (reconciled after individual retries) | **126** | 0 | **0** | **1** |
| Pandoc | 0 (`not_run`, not installed) | -- | -- | -- |
| LibreOffice | 0 (`not_run`, not installed) | -- | -- | -- |

The reconciled row is the honest final picture: all 6 crashes resolved cleanly on isolated
retry (transient resource contention); the one timeout is a genuine, persistent capacity
limit (see below), not resolved by retrying with 3x the time budget.

Docling configuration for this run (unchanged from PAPER-28/31): `TableFormerMode.FAST`,
`do_formula_enrichment=False` (crashes the process natively if enabled, per PAPER-28), one
subprocess per document for crash isolation, 300-second per-document timeout.

## Macro-average results, full corpus

| Metric | native_meridian | python_docx | docling_pdf_document_ai |
|---|---:|---:|---:|
| paragraph_count_recall | 1.0 | 1.0 | -- |
| table_count_recall | 1.0 | 1.0 | 0.726 |
| table_row_recall | 1.0 | 1.0 | 0.671 |
| equation_count_recall | 1.0 | 0.0 | 0.0 |
| text_token_f1 | 0.722 | 0.698 | 0.611 |
| para_id_preservation_rate | 0.995 | 0.0 | not_applicable |
| wall time (mean, seconds) | 0.173 | 0.069 | **42.6** (subprocess total: 58.5) |
| peak memory | 2.4 MB (Python-traced) | 2.6 MB (Python-traced) | **1.68 GB** (process RSS) |

This confirms, at full-corpus scale, the same pattern PAPER-31's 10-document smoke slice
found: Docling meaningfully under-detects table structure on rendered PDFs relative to
reading the same document's native OOXML directly (0.726/0.671 vs. 1.0/1.0), finds zero
equations on any document via its FAST/no-formula-enrichment configuration, and costs
roughly 250-600x the wall time and 300-700x the memory of the deterministic native/parser
baselines. **`text_token_f1` dropped for all three systems relative to PAPER-31's smoke-slice
numbers** (native: 0.798->0.722; python-docx: 0.782->0.698; Docling: 0.666->0.611) --
this is not a regression in any system, it is the corrected gold text (PAPER-38's tab/br
fix, applied corpus-wide) changing the denominator for everyone; see the dedicated section
below, since the *relative* effect on native vs. python-docx is the more important, and more
surprising, story.

## 7 non-`scored` Docling outcomes -- named, and re-investigated, not left as a bare count

`tier2-omegause-033-price-catalog` (the corpus's single largest document at 68 pages)
**timed out** at the 300-second per-document limit -- an expected, capacity-driven outcome
for a page count that large under FAST-mode OCR/table inference, not a defect.

6 documents **crashed** with the identical Windows `STATUS_ACCESS_VIOLATION` (`0xC0000005`,
exit code `3221225477`) PAPER-31 first observed on a different single document during a
period of heavy concurrent load: `tier2-docxcorpus-fcf0d7bdf71d9756`,
`tier2-docxcorpus-392c7d7c263d52db`, `tier2-omegause-009-ch3-results`,
`tier2-docxcorpus-bfb35496a7d01232`, `tier2-docxcorpus-e63dc39fa8b54d6a`,
`tier2-omegause-088-product-spec-2`. This run's ~2-hour wall-clock window overlapped with
PAPER-38's own hardening workflow running concurrently on this shared host, the same kind of
resource contention PAPER-31 identified as the cause of its one crash. **All 6 were retried
individually, plus the timeout retried at a longer 900-second limit, once both concurrent
background jobs had finished** -- outcome recorded honestly below once the retries land,
not assumed in either direction before checking.

**Retry outcome, confirmed: all 6 crashes were transient, resource-contention artifacts, not
deterministic per-document defects.** Each of the 6 was retried individually, in isolation,
via `tools/docling_convert_one.py`, after both concurrent background jobs (this run and
PAPER-38's hardening workflow) had finished. **All 6 succeeded cleanly on retry**, producing
real, substantial output (3-12 pages, 15-209 seconds each, genuine extracted text/table/
equation counts, not empty or error stubs). Durable record:
`E:\MeridianData\ooxml-graph-paper\manifests\paper36-docling-crash-retry-addendum.json`.
Per this project's established methodology (matching PAPER-15's equation addendum), these
retry results are reported here explicitly and separately -- **not silently folded back into
the main run's 120/127 aggregate macro-averages above**, which remain the honest record of
the run as it was actually executed, crashes included. The retry demonstrates that Docling's
FAST-mode pipeline itself is not the cause of these 6 failures; running heavy local ML
inference concurrently with other heavy local workloads on a single shared host is.

The 68-page timeout (`tier2-omegause-033-price-catalog`) was separately retried at a longer
900-second limit (3x the original) after concurrent load had cleared -- **it timed out
again**, reaching 2.84 GB peak RSS before being killed at exactly 900.4 seconds. Unlike the
6 crashes, this is **not** a transient, resource-contention artifact: the same document
failed to complete under generous conditions and a 3x larger time budget. This is a genuine,
reportable capacity limitation of Docling's CPU-only, `TableFormerMode.FAST` pipeline on this
host for a document of this size (68 pages) -- not a bug, and not evidence the pipeline is
broken on smaller/typical documents (120 of 121 non-price-catalog documents completed
successfully, most in well under a minute), but a real, page-count-scaling boundary that a
production evaluation covering documents this large would need to budget for explicitly
(e.g. a per-document timeout scaled to page count, or accepting that outlier-length documents
are out of scope for a CPU-only local pipeline). Final status: `timed_out` at both 300s and
900s, reported as such, not silently retried into a fabricated "eventually succeeded."

## The tab/br gold-fidelity fix's real, corpus-wide effect -- read this carefully

PAPER-38 fixed a real bug in the paper's independent gold extractor (dropped `<w:tab/>` and
`<w:br/>` when reconstructing paragraph text) and regenerated all 127 gold manifests'
`text` fields (71 of 127 documents' gold text actually changed). Re-running the graph-aware
scorer (PAPER-30) after that fix produced a genuinely important, easy-to-misread result:

**native_meridian's own measured paragraph-text fidelity *dropped* (graph-scorer
`paragraph_node_f1`: 0.998 -> 0.981) while python-docx's *held steady or slightly improved*
(0.967 -> 0.984) -- python-docx is now essentially tied with, or fractionally ahead of,
native Meridian on this specific text-content metric.**

This is not evidence that native extraction got worse, and it is not evidence that
python-docx is now "better." It is evidence of a **shared, previously-hidden bug**: native
Meridian's own real paragraph-text-extraction function (`document_content_tree`'s
`_paragraph_text`, in both `packages/docparse/docparse/docs_intel.py` and its vendored copy
`extensions/meridian-docs/meridian_docs/_vendored_content_tree.py`) has the **identical**
`<w:t>`-only text-reconstruction bug the paper's gold extractor used to have. Before the fix,
gold and native shared the same bug, so they looked perfectly aligned on tab-heavy documents
by coincidence, not by genuine fidelity. Fixing gold alone (correctly, since gold's job is to
reflect ground truth, not to match any system under test) exposed native's real, previously-
masked text-fidelity gap for the first time. python-docx's `.text` property never had this
bug, so correcting gold moved its score toward, not away from, the truth.

**This finding is flagged as a live product bug, not fixed under this item's file locks**
(the affected files, `packages/docparse/docparse/docs_intel.py` and
`extensions/meridian-docs/meridian_docs/_vendored_content_tree.py`, are outside PAPER-36/38's
resource claims) -- recorded as follow-up task `task_945705a3`. **PAPER-39/40 must report
this precisely**: native Meridian's structural advantages (paragraph *count*, table
structure, equation detection and semantic classification, native paragraph-ID preservation)
remain real, large, and statistically supported; its *text-content* fidelity advantage over
python-docx specifically, on this one narrow metric, does not currently hold once gold is
measured correctly, and that must not be hidden, rounded away, or attributed to python-docx
"winning" rather than to a shared, now-exposed extraction gap.

## What this run is and is not evidence for

This is now genuine, full-127-document Track-3 evidence (`comparator-contract-v0.md` §7.2):
native OOXML's table-structure and equation-semantic advantages over a rendered-PDF
document-AI system hold at full corpus scale, not just on a 10-document sample. It is not yet
evidence with formal paired confidence intervals and significance tests against Docling
specifically -- that full statistical treatment, using this run's per-document data, is
PAPER-39's job.
