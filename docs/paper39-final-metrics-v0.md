# PAPER-39: final paired metrics, confidence intervals, and failure tables (v0)

Status: the real, full-127-document graph-aware scoring pass across all three systems
(native Meridian, python-docx, Docling), with bootstrap 95% confidence intervals and paired
significance tests for every pairwise comparison. Report:
`E:\MeridianData\ooxml-graph-paper\manifests\paper30-graph-eval-all-20260828T161244Z.json`.
Method throughout: `tools/graph_scorer.py`'s node correspondence, precision/recall/F1 by
kind, non-tautological reading-order metric, and independently re-derived equation
semantic-class accuracy (PAPER-30), extended in this item to compute pairwise paired
significance tests across all three systems (not just native-vs-python-docx).

## Statistical method, stated once, applying to every p-value below

**Paired sign-flip permutation test, 2,000 resamples, fixed seed 20260828.** For each metric,
only documents where BOTH systems in the pair have a real (non-null) value are included --
the exact paired sample count `n` is reported with every result, never omitted.
Under the null hypothesis of no systematic difference, each document's signed difference is
equally likely to have been negated; the reported `p` is the fraction of 2,000 random
sign-flips whose resampled mean absolute difference was at least as extreme as the one
actually observed. This is exact and does not assume a normal distribution. Every `p=0.0`
below means literally "0 of 2,000 permutations were as extreme as observed" -- reported as
such, not as a claim of mathematical impossibility.

## Terminal status, all three systems, all 127 documents

| System | scored | failed | crashed | timed_out |
|---|---:|---:|---:|---:|
| native_meridian | 127 | 0 | 0 | 0 |
| python_docx | 122 | 5 | 0 | 0 |
| docling_pdf_document_ai (this scoring run, before retry) | 119 | 0 | 5 | 3 |

Docling's crash/timeout set in *this* run (5 crashed: `tier2-docxcorpus-d4b0f603137ef5d1`,
`tier2-docxcorpus-4b9e8251787b5cd3`, `tier2-docxcorpus-31b78fbf950f9a3d`,
`tier2-omegause-059-project-proposal`, `tier2-omegause-025-business-plan`; 3 timed out:
`tier2-omegause-039-thesis-template`, `tier2-omegause-031-pinyin-worksheet`,
`tier2-omegause-033-price-catalog`) is **entirely different from PAPER-36's crash/timeout
set** (which used the same Docling configuration against the same documents' rendered PDFs,
just via `run_paper15_smoke.py`'s simplified scorer rather than this graph-aware one). Zero
overlap between the two runs' failure sets is itself further, reinforcing evidence that these
failures are driven by transient host conditions (this run's ~time window had its own
concurrent load), not by anything specific to those documents -- consistent with, not a
new contradiction of, PAPER-36's own finding.

**Retry status, confirmed**: all 7 non-price-catalog crashed/timed-out documents were retried
individually in isolation once the main run finished; **all 7 succeeded cleanly**
(`E:\MeridianData\ooxml-graph-paper\manifests\paper39-docling-retry-addendum.json`), reported
separately per this project's established methodology, not folded into the aggregate/paired
numbers above. One genuine, honestly-flagged nuance, not smoothed over: the document that had
crashed as `tier2-omegause-025-business-plan` took **398.4 seconds** on its clean retry --
longer than the standard 300-second timeout every document in this corpus is normally scored
against. Its original failure was a crash, not a timeout, so this isn't a contradiction, but
it means this specific document sits at or past the pipeline's practical per-document time
budget on its own merits, independent of resource contention -- a real, standing
capacity-boundary risk for this one large document, not assumed resolved just because this
particular retry (run with no explicit timeout change, but evidently enough contention-free
headroom this time) happened to finish. `tier2-omegause-033-price-catalog` (68 pages) was not
re-retried here -- PAPER-36 already established, at a 3x-longer 900s budget, that its timeout
is a genuine, persistent capacity limit, not resource contention.

## Full-corpus results: bootstrap 95% CIs

| Metric | native_meridian | python_docx | docling_pdf_document_ai |
|---|---:|---:|---:|
| paragraph node F1 | 0.981 [0.972, 0.989] n=127 | 0.984 [0.966, 0.996] n=122 | 0.349 [0.306, 0.396] n=99 |
| paragraph node precision | 0.980 [0.970, 0.989] n=127 | 0.984 [0.966, 0.996] n=122 | 0.320 n=119 |
| paragraph node recall | 0.983 [0.974, 0.991] n=127 | 0.984 [0.966, 0.996] n=122 | 0.307 n=119 |
| reading-order accuracy | 1.0 [1.0, 1.0] n=106 | 1.0 [1.0, 1.0] n=101 | 0.990 [0.980, 0.996] n=95 |
| table node F1 | 1.0 [1.0, 1.0] n=75 | 1.0 [1.0, 1.0] n=70 | 0.838 [0.790, 0.884] n=56 |
| table row exact-match rate | 1.0 [1.0, 1.0] n=75 | 1.0 [1.0, 1.0] n=70 | **0.0** [0.0, 0.0] n=56 |
| equation node F1 | 1.0 [1.0, 1.0] n=7 | not_applicable (0 capability) | not_applicable (0 OMML) |
| equation semantic-class accuracy | 1.0 [1.0, 1.0] n=7 | not_applicable | not_applicable |
| native paragraph-ID preservation | 0.995 [0.984, 1.0] n=95 evaluable | not_applicable (0 capability) | not_applicable (no native ID concept in a PDF) |

**Docling never once achieves an exact table row count** across 56 documents where it
detected at least some table structure (`table_row_exact_match_rate = 0.0`, a genuinely stark,
clean result) -- it can approximate that a table exists (`table_node_f1 = 0.838`) but
consistently gets the row count wrong.

## Paired significance tests, every pairwise comparison

### native_meridian vs. python_docx -- the central, most important, and most surprising result of this item

**SUPERSEDED 2026-08-30 (PAPER-S4) -- read this before the table below.** The `p=0.903`
tie reported here was itself an artifact of a real bug in Meridian's own native
`_paragraph_text` (identical tab/break-dropping bug to the one PAPER-38 fixed in gold),
not a genuine finding. That bug is now fixed at `dev@54d6f969` (`packages/docparse` +
the meridian-docs extension's vendored copy), independently verified, and the scorer
rerun against the same unchanged 127-document gold corpus: native paragraph_node_f1 =
0.9984 vs python_docx 0.9836, paired permutation mean diff = +0.0164 favoring native,
`p_hat = 0/2000` (n=122). Native genuinely beats python-docx on paragraph text fidelity
after all -- see `docs/final-results-correction-ledger-v1.md` for the full writeup and
`E:\MeridianData\ooxml-graph-paper\manifests\paper30-graph-eval-all-20260830T070431Z.json`
for the report. The original (now-superseded) analysis below is retained for the record,
not because it is still the current finding.

| Metric | mean diff (native - python_docx) | p | n |
|---|---:|---:|---:|
| paragraph node F1/precision/recall | **-0.0014** | **0.903** | 122 |
| reading-order accuracy | 0.0000 | 1.0 | 101 |
| table node F1 / row exact-match | 0.0000 | 1.0 | 70 |
| equation / paraId metrics | -- | untestable (n=0 paired) | -- |

**This is a real, honest reversal from PAPER-30's earlier result (which found p=0.0 favoring
native on this exact metric), and it must be reported precisely, not smoothed over.** Before
PAPER-38's tab/br gold-fidelity fix, native and gold shared an identical text-reconstruction
bug (both dropped `<w:tab/>`/`<w:br/>`), which made native's measured paragraph-text score
look artificially strong. After fixing gold correctly (gold's job is ground truth, not
matching any system under test), native's real, previously-masked gap became visible:
**native_meridian and python-docx are now statistically indistinguishable on paragraph-text
fidelity (p=0.903 -- nowhere close to significant)**, because native Meridian's own
extraction (`document_content_tree`'s `_paragraph_text`, in the real
`packages/docparse/docparse/docs_intel.py`, not just a paper-tooling artifact) has the
identical tab-dropping bug gold used to have. This is flagged as a live product limitation,
not fixed under this item's file locks (follow-up task `task_945705a3`).

**What remains true and strongly supported**: native's advantages in equation detection +
semantic classification (7/7 vs. 0 capability), native paragraph-ID preservation (0.995 vs.
0 capability), and the overall claim that native extraction is deterministic and complete
where python-docx crashes (5/127 crashes on valid documents) are untouched by this finding.
What is **no longer supported without qualification** is a blanket claim that native beats
python-docx on raw paragraph *text* content -- it does not, once gold text is measured
correctly, and PAPER-40 must state this plainly.

### native_meridian vs. docling_pdf_document_ai / python_docx vs. docling_pdf_document_ai

| Metric | native vs. Docling: diff, p, n | python_docx vs. Docling: diff, p, n |
|---|---|---|
| paragraph node F1 | +0.630, p=0.0, n=99 | +0.634, p=0.0, n=99 |
| paragraph node precision | +0.659, p=0.0, n=119 | +0.648, p=0.0, n=114 |
| paragraph node recall | +0.676, p=0.0, n=119 | +0.662, p=0.0, n=114 |
| reading-order accuracy | +0.010, p=0.0, n=95 | +0.007, p=0.0, n=93 |
| table node F1 | +0.162, p=0.0, n=56 | +0.162, p=0.0, n=56 |
| table row exact-match rate | +1.000, p=0.0, n=56 | +1.000, p=0.0, n=56 |

Both native-DOCX-reading systems beat the rendered-PDF document-AI system by a large,
statistically robust margin on every testable structural metric -- this is the real,
full-corpus confirmation of PAPER-27/34/35/36's central Claim-3 evidence, now with formal
paired significance behind it rather than resting on a 10-document smoke slice alone.

## Resource accounting (from PAPER-36's run, same corpus, same Docling configuration)

| Metric | native_meridian | python_docx | docling_pdf_document_ai |
|---|---:|---:|---:|
| wall time (mean, seconds) | 0.173 | 0.069 | 42.6 (subprocess total 58.5) |
| peak memory | 2.4 MB (Python-traced) | 2.6 MB (Python-traced) | 1.68 GB (process RSS) |
| deterministic model tokens | 0 | 0 | 0 |
| hosted API tokens/cost | n/a | n/a | not_run (PAPER-32, no credential/approval) |

`graph_scorer.py` itself does not track wall-time/RSS (a scoring-only library); these figures
are pulled from `run_paper15_smoke.py`'s separate resource-accounting pass over the identical
corpus and Docling configuration (`docs/paper36-docling-full-run-v0.md`), not re-measured
here, to avoid two divergent numbers for the same underlying fact.

## Editability and render gates

127/127 documents have `package_integrity.ok = True` and a retained, verified Word-COM render
receipt (`docs/paper29-corpus-audit-v0.md`) -- these gates are a corpus-membership
precondition already audited, not re-measured by this scoring pass.
