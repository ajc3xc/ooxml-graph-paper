# Dataset landscape and acquisition decision — 2026-08-25

## DocBank

Official public PDF/token-layout corpus: 500K pages, 12 semantic labels, published train/dev/test indexes, and approximately 54.3 GB on the current Hugging Face dataset card. It is the canonical public-context track, not a paired DOCX graph corpus.

## OfficeComprehensionBenchmark (OCB)

Microsoft's Office benchmark evaluates structural/visual perception and grounded reasoning over Word, Excel, and PowerPoint. The reported full evaluation contains 244 files and 922 File Fidelity queries, plus a 124-file Domain Q&A track with 8,450 atomic assertions. It has a hybrid distribution model: some native Office files are hosted, while others are fetched from source URLs and converted to native Office formats. It is useful for real Office comprehension and fidelity context, but its labels are questions/assertions rather than a complete OOXML graph.

## DocuBench

Public benchmark of 72 hard, real-world documents across ten file types including DOCX. It supplies hand-verified JSON labels, schemas, raw baseline outputs, and a standalone scorer. Its headline score is schema extraction accuracy, so it is useful for structured extraction and LLM/token-cost comparisons but not a substitute for native OOXML graph gold.

## docx-corpus

Large public-web DOCX corpus reported at 736K+ files, with content hashes, language/type/topic labels, and ODC-BY licensing. It is potentially useful for distribution sampling and unlabeled robustness tests. It does not provide the node/edge/revision gold needed for the primary claim, and source takedown/licensing review is mandatory before materializing files.

## Decision

1. Keep DocBank as the public PDF/layout context track.
2. Prospect OCB and DocuBench for external native-Office/comprehension context and token/fidelity baselines.
3. Use docx-corpus only as an optional unlabeled DOCX distribution source after licensing/takedown review.
4. Build or hand-verify a small, independently generated DOCX graph gold set for the primary OOXML claim. Include paragraphs, styles, tables, equations, captions, fields, anchors, references, revisions, clones, malformed/ambiguous cases, and render receipts.
5. Never pool scores across these datasets; report each dataset and task separately.

Sources: [DocBank](https://github.com/doc-analysis/DocBank), [OfficeComprehensionBenchmark](https://huggingface.co/datasets/microsoft/OfficeComprehensionBenchmark), [DocuBench](https://github.com/DocuPipe/DocuBench), [docx-corpus](https://docxcorp.us/), [DOCX benchmark methodology](https://github.com/dealfluence/docx-benchmark).

## 2026-08-26 — PAPER-12: ReadingBank status, native-DOCX source inventory, gold-set sketch

This section extends the 2026-08-25 findings above; it does not restate or contradict them. It also inherits, rather than re-derives, the ReadingBank finding already recorded on sprint item PAPER-12 by a prior parallel investigation.

### ReadingBank (inherited finding, not re-verified end-to-end here)

The official full ReadingBank ZIP is unavailable (the published link returns HTTP 404). The current Google Drive dataset folder exposes only a public example file plus a shortcut whose target has been deleted. The old Azure Blob Storage workaround requires authentication credentials this project does not have. A Hugging Face mirror carries derived Parquet text/layout only, not raw DOCX/OOXML. Per the standing sprint decision, converter/graph-schema work does not block on ReadingBank. This item did not re-attempt the Drive/Azure/HF checks; it is carried forward as-is.

### Native-DOCX sanity/comparison source inventory

Each source below was re-checked against its primary page/repo on 2026-08-26 (not assumed from the name). OCB and DocuBench were already inventoried in the 2026-08-25 section above; they are re-verified here rather than re-described, with one correction noted for DocuBench.

**OfficeComprehensionBenchmark (OCB)** — re-verified, no material change from 2026-08-25. Hugging Face dataset card confirms it is still live, no gated login required. License is **CDLA-Permissive-2.0** for OCB-authored content (questions/answers/assertion rubrics), with sub-component carve-outs: U.S. government source files are public domain, Kaggle-hosted files are CC0-1.0/MIT only, and URL-referenced files retain their original publisher licenses. Three Kaggle CSVs originally in the eval set are excluded from the public release because their CC-BY-NC-SA-4.0 license is incompatible with redistribution — a concrete example of the license-carve-out risk this project needs to watch for if it ever redistributes a derived slice. Obtain via `huggingface.co/datasets/microsoft/OfficeComprehensionBenchmark`; directly-hosted files need no agreement, externally-referenced files must be fetched per-source and converted using the companion GitHub tooling. Verdict: usable as external comprehension/fidelity context per the 2026-08-25 decision; still not a paired OOXML graph gold source.

**DocuBench** — re-verified with a correction. The repo is live (`github.com/DocuPipe/DocuBench`), dual-licensed: code MIT, benchmark-authored labels/schemas CC-BY-4.0, source documents retain their original license per `SOURCES.md`. The 2026-08-25 note ("72 hard, real-world documents across ten file types including DOCX") is accurate but was read as implying meaningful DOCX coverage. Direct inspection of the `documents/` folder shows **exactly one** `.docx` file (`pw8elPW9.docx`) among the 72; the rest are PDF (majority), one XLSX, four JPEG, one TIFF, one PNG, two XML, one TXT, one HTML, one CSV. DocuBench is therefore a schema-extraction/LLM-cost benchmark that happens to include a single DOCX fixture, not a DOCX-focused corpus. Verdict: keep the 2026-08-25 decision (useful for extraction-accuracy/cost comparison context) but do not describe it as a DOCX source going forward — one file cannot support any DOCX-specific claim.

**OmegaUse-OfficeVal** — new to this inventory. Paper: [arXiv:2607.27155](https://arxiv.org/abs/2607.27155) (Baidu Frontier Research), "Benchmarking LLM Agents on Long-Horizon Office-Suite Tasks with Economic Grounding." Confirmed real, non-hallucinated repo and dataset: `github.com/baidu-frontier-research/OmegaUse-OfficeVal` (Apache-2.0, a submission-validation/scoring harness, not the corpus itself) and `huggingface.co/datasets/baidu-frontier-research/OmegaUse-OfficeVal` (also declared Apache-2.0, ungated). It contains 100 long-horizon office tasks built from practitioner requests, with **220 native input files** (63 DOCX, 31 PPTX, 25 XLSX, plus PDFs/media) and **115 golden output artifacts** (48 DOCX, 40 PPTX, 24 XLSX, 3 PDF), evaluated against 2,009 rubric-based, code-executed verifiers rather than open-ended LLM judging. Each task also carries two economic-grounding signals (human labor hours, task price proxy) that are irrelevant to this paper but do not taint the files themselves. Verdict: this is the most promising new lead in this batch — real native Office files with paired input/gold-output artifacts and an Apache-2.0 license permitting reuse. It is a task-completion benchmark (did the agent produce the right deliverable), not an OOXML-structure/graph benchmark, so its "gold" is at the deliverable-file level, not the node/edge level our schema needs — but the underlying DOCX/PPTX/XLSX files are candidate raw material for structural sanity-checking and for mining additional real-world OOXML feature diversity (tables, tracked changes, embedded objects) beyond what we would hand-author. Obtaining it needs no account or agreement.

**docx-benchmark (dealfluence)** — new to this inventory; previously only cited by URL for methodology, not inspected. Repo: `github.com/dealfluence/docx-benchmark`, license **AGPL-3.0-only** for the benchmark code/harness itself. It benchmarks whether AI tools/MCP servers preserve DOCX formatting, tracked changes, and file integrity across five agentic redlining scenarios (form filling, party swapping, comment-based policy review, playbook redlining, multi-file assembly) — a tool-correctness benchmark, not a document-understanding or graph benchmark. The `fixtures/` directory holds a handful of real native `.docx` contract templates across six sub-folders (`bonterms`, `common-paper`, `eu-scc`, `series-seed`, `uk-gov`, `ycombinator`) — small in count (the `series-seed` folder alone has 2 docx files plus a `LICENSE-INFO.txt`), not a corpus at scale. Critically, **fixture licensing is per-folder and independent of the AGPL-3.0 repo license**: `series-seed/LICENSE-INFO.txt` states the included Series Seed investment-agreement DOCX is a public-domain **CC0-1.0** template from the `seriesseed/equity` repository, explicitly free for any use including commercial. The other five fixture folders were not individually license-checked in this pass — each would need its own per-folder verification before reuse (Bonterms, Common Paper, EU SCCs, UK gov, and Y Combinator templates are each published under their own separate terms and must not be assumed CC0 by analogy to `series-seed`). Verdict: potentially useful as a tiny source of rights-clean, real-world, feature-rich (contracts have complex tables, numbering, cross-references) native DOCX files for the gold set, but only fixture-by-fixture after confirming each folder's own license file — not a bulk source.

**docx-corpus** — re-verified, no material change from 2026-08-25, with one clarification. `docxcorp.us` and the GitHub repo (`github.com/superdoc/docx-corpus`, MIT code license) both state "736K+ real .docx files," ODC-BY data license (confirmed via the site's own text: "Dataset is ODC-BY; source code is MIT"). The Hugging Face dataset card (`huggingface.co/datasets/superdoc-dev/docx-corpus`) confirms 737,000 rows, `license: odc-by`, no gated login, and clarifies that **the HF dataset itself ships metadata/hashes/URLs only** (63.6 MB) — the actual `.docx` binaries are fetched per-document from a CDN URL in each row, not bundled. A takedown process exists ("email help@docxcorp.us with the document hash or URL and proof of ownership. Processed within 7 days.") but there is no stated pre-screening for copyright/PII before ingestion from Common Crawl, and no explicit corpus-wide redistribution warranty beyond the ODC-BY label on the metadata. Verdict: unchanged from 2026-08-25 — usable only as an optional, unlabeled distribution-sampling source after a licensing/takedown review, and only for files individually fetched and hash-recorded, never as a bulk redistribution.

**WordScape** — new to this inventory, and the weakest lead. Paper: [arXiv:2312.10188](https://arxiv.org/abs/2312.10188) (NeurIPS 2023, DS3Lab). `github.com/DS3Lab/WordScape` is **not a dataset**, it is a *pipeline* (Apache-2.0 licensed code) that must be run against Common Crawl to produce one: it extracts links to Word files from Common Crawl, downloads them over HTTP, and renders/labels them. The repo distributes a preprocessed list of 9.4-9.5M Common Crawl URLs to Word documents (via Google Drive, with SHA256 checksums) so a user can skip the link-extraction step, but no pre-built annotated dataset or pre-fetched DOCX corpus is distributed by the project itself. The repo shows limited recent activity (few commits since the NeurIPS 2023 release; not confirmed actively maintained in 2026). Verdict: out of scope for this paper as a direct source — using it would mean re-running a multi-million-document Common Crawl acquisition pipeline ourselves, which is explicitly the kind of large-corpus acquisition this item is scoped to avoid. Noted for completeness only.

### Inventory summary

| Source | Real native DOCX/PPTX/XLSX? | Approx. scale | License (data) | Paired structural/graph gold? | Obtain |
|---|---|---|---|---|---|
| OfficeComprehensionBenchmark | Partial (hybrid hosted/URL) | 244 files (+124-file QA track) | CDLA-Permissive-2.0 (+ carve-outs) | No — QA/assertions, not a graph | HF, ungated |
| DocuBench | Yes, but only 1 of 72 files is DOCX | 1 DOCX file | CC-BY-4.0 (labels); per-source (docs) | No — schema-extraction JSON, not graph | GitHub, ungated |
| OmegaUse-OfficeVal | Yes | 220 input + 115 gold-output files (DOCX/PPTX/XLSX) | Apache-2.0 | No — deliverable-level gold, not node/edge | HF + GitHub, ungated |
| docx-benchmark | Yes (small fixture set) | Low tens of files across 6 folders | Mixed, per-folder (confirmed CC0-1.0 for `series-seed` only) | No — edit-fidelity harness, not graph | GitHub, ungated |
| docx-corpus | Yes (fetched per-file from CDN) | 736K+ | ODC-BY (metadata); per-file provenance unverified | No — unlabeled | HF/API/manifest, ungated |
| WordScape | Only via running the pipeline yourself | Up to ~40M pages if fully run | Apache-2.0 (code only) | No — no annotation matches this paper's schema | GitHub (pipeline) + Drive (URL list) |

None of the six sources provide a ready-made paired OOXML/OMML/render gold set matching `docs/graph-gold-schema-v0.md`. All are either (a) task/QA benchmarks whose "ground truth" is answers or deliverable files, not a node/edge/revision graph, or (b) unlabeled DOCX distribution sources. OmegaUse-OfficeVal and the CC0 `docx-benchmark/fixtures/series-seed` files are the two candidates worth a closer, individual look as raw material — not as substitutes for the gold set itself.

No files were downloaded or staged for this item. Per this session's action-permission rules, downloading files requires explicit user (not agent) permission, which was not sought in this investigation-only pass; staging even the small CC0 `series-seed` fixture is deferred to a future item where that permission can be obtained directly from the user.

### Gold-set sketch: paired OOXML/OMML/render gold for this paper's central claim

This builds on the gold manifest structure already frozen in `docs/graph-gold-schema-v0.md` (node vocabulary, structural edges, identity/revision rules, the JSON gold-record shape, and the six required invariants). It does not redefine that schema; it sketches the corpus and process needed to populate it credibly.

**Size.** Small and deep, not large and shallow: on the order of 30-40 documents total, sized so every document can be fully hand-verified rather than sampled. This paper's claim is about structural/graph fidelity of a native-DOCX pipeline, not about generalization at corpus scale — DocBank-style scale is the wrong shape for this track (per `comparator-contract-v0.md` Track A vs. Track B).

**Strata.** Three tiers, each targeting a different failure mode:

1. **Minimal hand-authored fixtures (~15-18 docs).** One or two invariants each, kept small enough to diff by eye: plain paragraphs/styles; a simple table; a merged-cell table; a nested table; a simple OMML equation; a numbered equation (exercising `insert_numbered_equation`); a deliberately malformed/oversized OMML payload (exercising the new `_OMML_MAX_XML_CHARS`/`_OMML_MAX_NESTING_DEPTH` bounds); an empty-equation-content case; a caption correctly bound to a figure/table; a caption with a dangling/unresolved anchor; a duplicate `w14:paraId` case; a cross-reference/field case; a footnote/endnote case; a tracked-change (insert/delete/revision) case; a copy-cloned section (to exercise `clones` + fresh-ID assignment); and a multi-part document (headers/footers + body). Each of these exists specifically because the schema names it as a required invariant or a named edge/node kind — the fixture set should be legible as a checklist against `graph-gold-schema-v0.md` section by section.
2. **Real-world native documents (~10-12 docs).** Sampled from rights-clean, individually-verified sources only — the CC0 `docx-benchmark/series-seed` template is a candidate; OCB's public-domain/CDLA-licensed files and OmegaUse-OfficeVal's Apache-2.0 input files are other candidates, each still needing per-file confirmation before use, not blanket trust in the dataset-level license tag. This tier exists because hand-authored fixtures alone cannot capture the messiness of real Word-authored XML (inconsistent style inheritance, tool-of-origin quirks, non-canonical OMML from equation editors, orphaned bookmarks) that the graph must handle as `ambiguous`/`synthetic` rather than crash on.
3. **Composite stress documents (~4-6 docs).** Longer documents combining many of the tier-1 features together (e.g., a short report with tables, equations, captions, cross-references, and one tracked change), to catch interaction bugs that isolated fixtures miss — order-of-containment errors, ID collisions across sections, or render receipts that pass per-feature but fail once composed.

**Independence.** The gold set must not be produced by running documents through `docs_intel.py`'s own parser and calling the output truth — that is circular and would make the "central claim" untestable by construction. Concretely:

- Tier-1 fixtures should be authored directly in Microsoft Word (or by hand-editing OOXML XML with a text editor against the ECMA-376/ISO-29500 spec), never generated by the meridian-docs write path under test. Their expected node/edge/fact content is written down by a human reading the resulting XML, not by running the extractor and eyeballing plausibility.
- Tier-2 real-world documents are gold-labeled by a second, independent extraction path — e.g., manual XML inspection plus a different library (`python-docx`, raw `lxml` on the part XML, or a from-scratch minimal reader) — cross-checked by a human, specifically so the gold labels do not share a bug with the implementation under test.
- A held-back subset (roughly a quarter of the set, chosen before implementation authors see the full list) is never used for debugging the extractor during development, so the reported numbers are not silently overfit to the visible fixtures.
- Whoever authors/labels the gold set records provenance per the schema's `provenance` field (producer, code_revision, created_at) and that producer must not be `docs_intel.py` itself for tier-1/tier-2 documents — a second human or independent tool is the producer of record.
- A second reviewer (not the author) re-derives node/edge counts for a sample of the set and signs off; disagreements become explicit `conflicts_with` edges in the gold record per the schema, not silently resolved in whichever direction is convenient.

**Render receipts.** Per invariant 5 in the schema (a render receipt names renderer, version, input hash, output hash, exit status, and observed checks), every gold document needs at least one *retained* render receipt, not the transient kind seen in the current probe. `runtime-capability-contract-v0.md`'s 2026-08-26 observed state confirms Word COM currently renders and verifies (`render_backend=word-com`, `render_verified=true`) but that the probe's PDF output was consumed by the render gate and not retained (`E:\MeridianData\ooxml-graph-paper\manifests\meridian-equation-word-probe-20260826.json`, `status: "capability_verified_not_benchmark_evidence"`). For the gold set specifically:
- Retain the rendered PDF/output artifact per document (not just a pass/fail flag), hashed and stored under `E:\MeridianData\ooxml-graph-paper\renders\`, so a human can independently re-inspect the render later without re-running Word.
- Where feasible, get a second, independent renderer's receipt (LibreOffice headless) alongside the Word-COM receipt, per the comparator contract's Track C rule that LibreOffice may be a separately labeled compatibility comparison but must never substitute for a Word receipt. LibreOffice is not currently installed on this host, so this is presently aspirational, not done.
- A document with no available renderer records an explicit `unknown` receipt per the schema, never a silently skipped row.

**Who verifies it.** At minimum: (1) one author who hand-builds or hand-labels each document and its gold record; (2) one independent reviewer, ideally someone who has not read `docs_intel.py`'s extraction code, who re-derives a sample of node/edge/fact counts from the raw XML/render output and either confirms or files a `conflicts_with` entry; (3) the render-gate step itself acts as a mechanical third check (does the document actually open/render in Word) but is not a substitute for (1)/(2) since it cannot catch a wrong node/edge label, only a broken file. None of this has been executed yet — this is a design sketch, not a completed gold set. No gold documents, human verification, or render receipts beyond the single existing equation probe currently exist for this track.

**What remains unresolved.** Actually building this gold set requires: a human to author/select and hand-verify the ~30-40 documents (not yet started); a second independent reviewer's time (not yet identified); a decision on which of the docx-benchmark/OCB/OmegaUse-OfficeVal files clear individual per-file license review (not yet done, and explicitly not authorized for bulk staging in this item); and either a LibreOffice install for the second-renderer cross-check or an explicit decision to run this paper's render-parity track on Word alone with LibreOffice reported as `unknown` throughout.

Sources: [OmegaUse-OfficeVal (arXiv)](https://arxiv.org/abs/2607.27155), [OmegaUse-OfficeVal GitHub](https://github.com/baidu-frontier-research/OmegaUse-OfficeVal), [OmegaUse-OfficeVal dataset (HF)](https://huggingface.co/datasets/baidu-frontier-research/OmegaUse-OfficeVal), [docx-benchmark](https://github.com/dealfluence/docx-benchmark), [docx-benchmark series-seed fixture license](https://github.com/dealfluence/docx-benchmark/blob/main/fixtures/series-seed/LICENSE-INFO.txt), [docx-corpus site](https://docxcorp.us/), [docx-corpus GitHub](https://github.com/superdoc/docx-corpus), [docx-corpus dataset (HF)](https://huggingface.co/datasets/superdoc-dev/docx-corpus), [WordScape GitHub](https://github.com/DS3Lab/WordScape), [WordScape paper (arXiv)](https://arxiv.org/abs/2312.10188), [DocuBench documents folder](https://github.com/DocuPipe/DocuBench/tree/main/documents), [OfficeComprehensionBenchmark (HF)](https://huggingface.co/datasets/microsoft/OfficeComprehensionBenchmark).

## 2026-08-27/28 — PAPER-28: pinning the local document-AI baseline (Docling)

Per the `comparator-contract-v0.md` §7 dual-track contract: this section pins **Docling** as
the local/open document-AI baseline for the rendered-PDF track. No hosted baseline
(Google Document AI / Azure Document Intelligence / AWS Textract) is pinned — no credential,
data-handling approval, or cost approval has been supplied, so PAPER-32's hosted track is
recorded as `not_run`, per explicit user instruction, not silently replaced with a manual
Claude PDF-reading pass.

### Installation and a real, reproducible Windows environment blocker

Added `docling>=2,<3` to this subproject's isolated `pixi.toml` (not the shared parent
lockfile). `pixi install` pulled a large dependency tree (`torch`, `transformers`,
`docling-ibm-models`, `docling-parse`, `rapidocr` — Docling's default PDF pipeline is a real
ML/vision stack, not a thin wrapper).

**A genuine, reproducible import-order bug was found and worked around, not hidden.**
`from docling.document_converter import DocumentConverter` (with nothing imported first)
fails on this host with:

```
OSError: [WinError 1114] A dynamic link library (DLL) initialization routine failed.
Error loading "...\torch\lib\c10.dll" or one of its dependencies.
```

Root cause, confirmed by direct bisection: docling's own import chain
(`document_converter` → `asciidoc_backend` → `base_models` → `pipeline_options` →
`asr_model_specs` → `pipeline_options_asr_model` → `pipeline_options_vlm_model` →
`from transformers import StoppingCriteria` → `import torch`) loads torch **lazily, deep
inside an unrelated ASCIIDoc/ASR code path**, and that deferred, nested `import torch`
fails every time. A plain top-level `import torch` executed first (before touching
`docling` at all) succeeds every time, and once torch is already in `sys.modules` the
subsequent `docling.document_converter` import succeeds too. Confirmed reproducible across
repeated fresh-process runs in both directions (fails every time without the workaround,
succeeds every time with it). Not bisected further to the exact conflicting DLL (this is a
well-known general class of Windows native-DLL search-order conflict between
PyTorch's bundled MKL/OpenMP runtime and another package's own bundled copy) — the
workaround (`import torch` as the first import in any script that also imports `docling`)
is documented here and applied in `tools/probe_docling.py` and must be applied in any
future Docling-invoking script on this host, e.g. PAPER-31's runner.

### Pinned versions (2026-08-27, this host, isolated pixi env)

| Package | Version |
|---|---|
| docling | 2.123.0 |
| docling-core | 2.92.0 |
| docling-ibm-models | 3.14.0 |
| docling-parse | 7.16.0 |
| transformers | 5.16.1 |
| torch | 2.13.0+cpu |
| huggingface-hub | 1.29.0 |
| onnxruntime | not installed (Docling's default OCR path used here is `rapidocr` on the `torch` backend, CPU device, not an ONNX backend) |

Default `PdfPipelineOptions()` on this install: `do_ocr=True`, `do_table_structure=True`
(`TableFormerMode.ACCURATE`), `do_formula_enrichment=False`, `do_code_enrichment=False`,
`generate_page_images=False`. **Formula enrichment is off by default** — a load-bearing
fact for the findings below, not a bug in the probe.

On first run, Docling downloaded real OCR/layout model weights on-host from
`modelscope.cn` (RapidOCR PP-OCRv6 detection/recognition/classification, ~31 MB total) and
Hugging Face Hub (`docling-project/docling-layout-heron`, `docling-project/docling-models`
TableFormer weights). This is Docling fetching its own public model artifacts, not any
transmission of corpus documents to a third party — consistent with the "local/open, no
document upload" framing PAPER-28 requires, and recorded here so the distinction is not
misread later as a hosted-API call.

### Capability probe: what Docling actually returns, run against real gold-corpus documents

Probe script: `tools/probe_docling.py`. Full machine-readable output:
`E:\MeridianData\ooxml-graph-paper\manifests\paper28-docling-probe.json` (per-document
input hash, wall time, item/table/formula counts, distinct labels) and
`E:\MeridianData\ooxml-graph-paper\manifests\paper28-docling-sample-doclingdocument.json`
(one full exported `DoclingDocument` JSON, for `composite-03-multi`'s rendered PDF).

**A critical distinction this probe surfaced: Docling has two structurally different code
paths, and only one of them is a document-AI system.** Feeding Docling a `.docx` directly
invokes its native DOCX backend (a deterministic structural parser over the OOXML,
comparable in kind to python-docx/Pandoc — **not** vision/OCR-based). Feeding Docling a
*rendered PDF* invokes its real document-AI pipeline (layout model + OCR + table-structure
model). Per §7.1's contract, **only the rendered-PDF path counts as this paper's
document-AI baseline; Docling's own DOCX backend belongs in the native-OOXML track's
parser/converter family, alongside python-docx/Pandoc, if used at all** — it must not be
mislabeled as a document-AI result.

Three conversions were run, all `ConversionStatus.SUCCESS` (no crashes), same underlying
document (`composite-03-multi`, gold: 2 equations, 2 tables, 2 captions) fed two ways plus
one additional single-equation fixture:

| Input | Path | Wall time | Text items | Tables found | Formula-labeled items |
|---|---|---:|---:|---:|---:|
| `composite-03-multi.docx` | Docling's own DOCX backend (parser/converter track, not document-AI) | 0.13 s | 5 | 0 | **2 / 2** |
| `composite-03-multi.pdf` (Word-COM render of the same document) | Docling's real document-AI PDF pipeline | 234.0 s | 4 | **0** | **0 / 2** |
| `fixture-02-equation.pdf` (Word-COM render, 1 equation) | Docling's real document-AI PDF pipeline | 3.3 s | 2 | 0 | 0 / 1 |

**Reading the rendered-PDF result honestly, from the exported DoclingDocument JSON**: the
whole page collapsed to 4 flat `"text"`-labeled items — `"Composite fixture 03: two
tables, two equations, two captions. T1 Table 1: 1"`, `"𝑥 2"`, `"T2"`, `"Table 2: 2 √2"`.
Both tables' cell contents were fused into surrounding paragraph text as undifferentiated
strings (no row/column/cell structure recovered at all, despite `do_table_structure=True`
being on by default — the table-structure model did not detect a table region on this
page). Both equations were OCR'd as literal Unicode glyph sequences (an italic mathematical
"𝑥" followed by "2") rather than recognized as a formula in any sense — expected, given
`do_formula_enrichment=False` by default, but the practical result is that **Docling's
rendered-PDF track, run with default settings, currently returns zero usable equation or
table structure on this document**, while Docling's own DOCX backend and Meridian's native
extraction each correctly found both equations. This is exactly the kind of concrete,
reproducible native-vs-document-AI gap PAPER-27's Claim (3) is about — recorded here as a
first real data point, not yet a full-corpus result (that is PAPER-31's job, and it must
re-run with `do_formula_enrichment=True` explicitly tried and reported as a separate
configuration before concluding formula recall is uniformly zero).

**Efficiency finding, load-bearing for PAPER-31 planning:** the default `TableFormerMode.
ACCURATE` + OCR pipeline took 234 seconds of CPU wall time for a single one-page PDF versus
0.13 seconds for the same content via Docling's own DOCX backend and ~0.1 second for
Meridian's native extraction (per `paper15-first-attempt-v0.md`). At that rate, a naive
127-document, default-settings Docling PDF pass could take on the order of hours to tens of
hours of CPU time depending on per-document page count and content density — PAPER-31 needs
an explicit time budget, a possibly-faster `TableFormerMode.FAST` configuration recorded as
a separate labeled run (not silently substituted for the default), and/or a reduced-slice
plan, not an unqualified "ran all 127 documents" claim.

### What is and is not pinned

- **Pinned**: Docling 2.123.0 (see version table above) as the local/open document-AI
  baseline; default `PdfPipelineOptions` behavior on this host; the torch-import-order
  workaround required to use it at all; one real per-document capability comparison
  (native-DOCX-backend vs. rendered-PDF-pipeline) showing a concrete formula/table
  recognition gap on rendered PDFs.
- **Not pinned / explicitly out of scope here**: any hosted document-AI processor
  (PAPER-32, `not_run` — no credential/approval supplied); a full 127-document Docling run
  with resource accounting (PAPER-31); `do_formula_enrichment=True` and
  `TableFormerMode.FAST` as alternate configurations (named above as follow-up, not yet
  run); DocBank/DocLayNet/OmniDocBench remain secondary literature/dataset context per
  PAPER-28's own scope note, not used as Docling inputs here.

Sources (this section only): [Docling GitHub](https://github.com/docling-project/docling), [Docling documentation — pipeline options](https://docling-project.github.io/docling/), [DoclingDocument schema (docling-core)](https://github.com/docling-project/docling-core).


