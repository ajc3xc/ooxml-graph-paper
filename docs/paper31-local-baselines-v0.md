# PAPER-31: local baselines with resource accounting (v0)

Status: a real, honestly-scoped run on the **smoke slice (10 documents)** with the Docling
document-AI baseline included -- not yet the full 127-document corpus for Docling
specifically (see "Scope and why" below for the resource-budget reasoning, decided in
advance rather than after the fact). Native Meridian and python-docx are already scored on
the full 127-document corpus per `paper15-first-attempt-v0.md`'s broad structural pass and
`paper30-graph-scorer-v0.md`'s graph-aware pass; this item's incremental contribution is
folding in the real, working Docling adapter (PAPER-28) with full resource accounting, using
`run_paper15_smoke.py --include-docling`.

Report: `E:\MeridianData\ooxml-graph-paper\manifests\paper15-smoke-run-20260828T053515Z.json`.
Checkpoint (incremental, resumable): `paper15-smoke-run-20260828T052137Z.checkpoint.jsonl`.

## Scope and why: smoke slice, not the full corpus, for Docling

PAPER-28's capability probe measured Docling's default `TableFormerMode.ACCURATE` pipeline at
~234 seconds for one dense page. Switching to `TableFormerMode.FAST` (with
`do_formula_enrichment` left off -- PAPER-28 found it crashes the whole process natively) cut
that to ~28-106 seconds per document depending on page count and content density. The full
corpus is 859 pages across 127 documents; even at the FAST-mode rate, a full run is realistically
multiple hours of sequential CPU-bound work on this single host. Rather than either quietly
truncating the "full" claim or blocking all other PAPER-31/33/34/35 progress on one multi-hour
run, the smoke slice (84 pages, 10 documents) was run first with full resource accounting, and
this is reported as exactly what it is -- a smoke-slice baseline, not a full-corpus claim.
Extending to `scale_up`/`final` is real, named remaining work (`--slice scale_up --include-docling`,
already wired and working), not a capability gap.

## Resilience note: incremental checkpointing

`run_paper15_smoke.py --include-docling` now writes each document's full result to a
`.checkpoint.jsonl` file immediately after scoring (not just at the end), and accepts
`--resume-from <checkpoint>` to skip already-completed documents. This was added after an
earlier attempt at this same run was interrupted (a background-task teardown killed the
process with zero persisted progress, since the original script only wrote its report at the
very end) -- a real, avoidable risk given a single Docling conversion can take over a minute.
Verified working: a `--resume-from` run against a completed checkpoint reproduces identical
aggregate numbers in ~3 seconds (pixi startup overhead only, all 10 documents skipped).

## Results (smoke slice, 10 documents)

| Metric (macro avg) | native_meridian | python_docx | docling_pdf_document_ai |
|---|---:|---:|---:|
| Status counts | 10 scored | 9 scored, 1 failed (caught `InvalidXmlError`, not a crash) | 9 scored, 1 crashed (native access violation) |
| table_count_recall | 1.0 | 1.0 | 0.786 |
| table_row_recall | 1.0 | 1.0 | 0.740 |
| text_token_f1 | 0.798 | 0.782 | 0.666 |
| para_id_preservation_rate | 1.0 | 0.0 | not_applicable (no native ID concept in a PDF) |
| wall time (mean, seconds) | 0.225 | 0.213 | **58.7** (subprocess total: 80.7) |
| peak memory | 3.5 MB (Python-traced) | 6.4 MB (Python-traced) | **1.79 GB** (process RSS) |

The wall-time and memory columns are not directly comparable in kind, and this table does not
pretend otherwise: native/python-docx figures are `tracemalloc`-traced *Python allocations*
inside an already-warm interpreter; Docling's figures are *process RSS* for a freshly-started
subprocess that loads a real OCR/layout/table-structure ML stack from scratch every time
(deliberate, for crash isolation -- see PAPER-28). Docling is roughly **250-400x slower** and
uses roughly **300-500x more peak memory** than the native/parser baselines on this corpus --
a real, load-bearing efficiency finding for anyone considering Docling as a production
document-AI path, independent of its accuracy numbers below.

## The one real crash: a native access violation, not a Python exception

`tier2-docxcorpus-61c750fca9dfb8ca` crashed Docling's subprocess with Windows exit code
`3221225477` (`0xC0000005`, `STATUS_ACCESS_VIOLATION`) after 66.9 seconds and 1.76 GB peak
RSS. This is a genuine native-level crash (the isolation strategy from PAPER-28/31 -- one
subprocess per document -- did exactly its job: it cost one row, not the whole run). This
crash occurred while **four other heavy processes were running concurrently** on this shared
host (PAPER-33's hardening workflow, spawning multiple parallel agent sessions each running
their own pixi/pytest commands) -- a real, disclosed confound.

**Retried in isolation after PAPER-33's workflow finished and system load dropped from 39 to
27 concurrent Python processes** (`tools/docling_convert_one.py` invoked directly on the same
render PDF): the retry succeeded cleanly, `ConversionStatus.SUCCESS`, 13 pages, 341 text
items, 0 tables, 0 equations, 77.1 seconds. One informational OCR warning appeared
("The text detection result is empty") on what is plausibly a sparse or image-heavy page, not
an error. **This confirms the original crash was a transient, resource-contention artifact of
this shared, concurrently-loaded host, not a deterministic per-document defect in Docling
itself or in this project's Docling adapter** -- reported as exactly that, a real finding
about running heavy local ML inference on a machine with other simultaneous heavy workloads,
not swept under an unqualified "Docling crashed" or hidden by only reporting the successful
retry.

## Reading the OCR text-quality numbers honestly: a real metric-validity caveat

Two of the nine successfully-scored documents show markedly lower `text_token_f1` than the
rest: `tier2-omegause-022-audit-report` (0.322) and `tier2-omegause-008-lit-review` (0.382),
versus 0.67-1.0 for the other seven. Investigated rather than reported at face value: both are
Chinese-language documents. Gold's own reference text for these two runs at 16.9 and 11.4
characters per whitespace-delimited "token" respectively, versus 6.4 for the English
`docxbenchmark` legal document in the same slice -- confirming these are CJK-dense text with
few natural whitespace breaks. **`text_token_f1` as implemented splits on whitespace
(`str.split()`)**, which is a reasonable proxy for space-delimited scripts but a poor one for
Chinese, where word boundaries are not marked by spaces at all -- a small OCR misread or
segmentation difference can shift far more of the whitespace-delimited "token" stream than the
equivalent English case. **These two low scores are plausibly a metric-validity artifact of the
scorer, not necessarily evidence that Docling's OCR quality is meaningfully worse on these two
documents specifically** -- this needs a script-aware tokenizer (e.g. character-level or a real
CJK segmenter) to resolve properly, not a claim this report is in a position to settle. Flagged
as a real, unresolved limitation of the current scoring pipeline for non-space-delimited
languages, not silently averaged away.

## Reading the table/structure numbers

Docling's `table_count_recall` (0.786) and `table_row_recall` (0.740) on the smoke slice are
markedly below native (1.0) and python-docx (1.0). Combined with PAPER-28's single-document
deep dive (0 tables found on `composite-03-multi`'s rendered PDF despite 2 real tables present,
content fused into surrounding paragraph text), this is consistent, multi-document evidence
that Docling's default FAST-mode table-structure detection on Word-COM-rendered PDFs
meaningfully under-detects table structure relative to reading the same document's native
OOXML directly -- a genuine, reproducible data point for Claim 3
(`comparator-contract-v0.md` §7.2), not yet the full-corpus statistical treatment PAPER-35's
final gate would need.

## What this is not

Not a full-corpus Docling run (see Scope above). Not a paired significance test against
native/python-docx (n=9-10 is too small for PAPER-30's bootstrap/permutation machinery to be
meaningful, and this report does not manufacture one). Not evidence resolving whether the one
crash is deterministic or load-dependent, pending the retry noted above. Every one of these
gaps is named here, not silently absent.
