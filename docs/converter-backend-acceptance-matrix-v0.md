# Converter backend and Word-native product acceptance matrix — v0

Status: investigation only. No baseline has been wired into a run. This document extends `comparator-contract-v0.md` (Section 2, baseline families) and `runtime-capability-contract-v0.md` (render authority and manual gates); it does not restate or contradict either. Research performed 2026-08-26 via primary-source web search (project READMEs, LICENSE files, and official docs); version numbers are reported as observed on that date, not asserted as permanently current.

## 1. Probe-artifact verification (Word COM capability claim)

The shared session context claimed a real Meridian equation insertion completed with `render_status=rendered`, `render_verified=true`, `render_backend=word-com`, backed by `E:\MeridianData\ooxml-graph-paper\manifests\meridian-equation-word-probe-20260826.json`. This was independently re-verified, not merely re-cited:

- **File exists.** `meridian-equation-word-probe-20260826.json`, 1,506 bytes, last written 2026-08-26 07:57:09, at the claimed path.
- **Content matches the claim.** The JSON's `meridian_result` block reads `"status": "inserted"`, `"render_status": "rendered"`, `"render_verified": true`, `"render_backend": "word-com"`, `"inserted_para_id": "3802CF5E"`, `"inserted_text_id": "3EB8B83F"`.
- **Hash cross-check (not just file-existence).** The probe records `input.sha256_after_write = B756601076D716C0D646C5D36F990D92F488C285803D2E52F50F7BAF2A1B4F45` for `E:/MeridianData/ooxml-graph-paper/renders/meridian-equation-probe-20260826/input.docx`. That file exists on disk (11,449 bytes, plus an `input.docx.bak`), and its current SHA-256 (recomputed independently via `Get-FileHash`) is **an exact match**: `B756601076D716C0D646C5D36F990D92F488C285803D2E52F50F7BAF2A1B4F45`. This is real evidence the artifact was generated from an actual file write, not hand-typed.
- **Corroborating timeline in the same manifests directory.** Two other manifests bracket the claim and are internally consistent with the shared context's timeline: `render-capability-2026-08-25.json` records the earlier failure (`"status": "failed"`, `"reason": "Word COM render exceeded its 60s bound"`, all of `soffice`/`libreoffice`/`winword` path-probes false); `word-render-probe-20260826.json` (07:49, 12 minutes before the equation probe) records a **separate, simpler** Word COM capability probe — `WINWORD.EXE 16.0.20326`, a real 13,440-byte input DOCX and a real 15,578-byte output PDF, both with recorded SHA-256 hashes. That PDF is still present on disk at `E:\MeridianData\ooxml-graph-paper\renders\word-probe-20260826b\probe.pdf`.
- **The equation-probe's own PDF was not retained.** Per the probe's `limitations` field, the render receipt PDF was "consumed by the render gate" — so no `render_probe.pdf` was found under the equation-probe render directory, and none was expected. This is consistent, not a gap in the evidence trail.
- **The probe is honest about its own limits**, in its own words: `"status": "capability_verified_not_benchmark_evidence"`, `"omml_observation": {"benchmark_ready": false, "reason": "semantic notation and validator hardening remain open"}`, and explicitly: *"This verifies the Meridian-to-Word render path for one fixture, not equation visual fidelity or benchmark quality"* and *"A formal Word human gate and audit-grade retained receipt are still required for PAPER-8/PAPER-15."*

**Conclusion:** the capability claim is verified — real file, real hash match, corroborating sibling probes, no fabrication detected. It proves Word COM rendering is *currently reachable* on this host and that one real Meridian-authored equation round-tripped through Word without failing. It does **not** clear the semantic-OMML-correctness gate (PAPER-11 territory: the probe's own `sum_representation`/`operand_representation` observation is descriptive, not validated against a gold OMML structure) or the audit-grade retained-receipt gate (PAPER-20 territory: this run's own PDF was consumed, and the probe explicitly flags the retained-receipt requirement as still open). Both follow-on items should treat this probe as capability evidence only, per the existing sprint-item note.

## 2. Baseline inventory (researched 2026-08-26)

Scope: tools that could plausibly serve as Track A baseline families 2–3 (`comparator-contract-v0.md` §2) or as a secondary renderer under the Rendered-parity track (§1.C). All findings below are from web search against current (2026) project pages, GitHub LICENSE files, and vendor pricing pages, not from pretrained-knowledge recall.

| Tool | License | 2026 status observed | DOCX direction |
|---|---|---|---|
| **python-docx** (`python-openxml/python-docx`) | MIT | Actively maintained; PyPI at 1.2.0 | Read + write real OOXML |
| **Apache POI (XWPF)** | Apache-2.0 | Actively maintained ASF project; OOXML support since POI 3.5 | Read + write real OOXML (Java) |
| **docx4j** | Apache-2.0 (dual with a commercial Plutext offering for support) | Actively maintained; commonly compared against POI as more ergonomic for Word manipulation | Read + write real OOXML (Java) |
| **Aspose.Words** | Commercial, closed-source. Pricing starts ~$1,175 (v26.6, developer license); free/trial builds are watermarked | Actively sold/updated product | Read + write real OOXML |
| **LibreOffice** (headless `soffice --convert-to`) | MPL-2.0, jointly LGPLv3+ for new contributions | Free, actively maintained; **not installed on this host** per `runtime-capability-contract-v0.md` | Read + write real OOXML via its own filter implementation |
| **Pandoc** | GPL-2.0-or-later | Actively released (3.x series observed across sources on 2026-08-26; exact build not pinned here per the "no baseline called latest without a dated version" rule) | Read DOCX into Pandoc's internal AST; **writes a real, Word-openable .docx** from that AST via a reference-template mechanism |
| **Docling** (IBM / Linux Foundation AAIF) | MIT (core); Granite-Docling-258M VLM component Apache-2.0 | Actively developed; donated to Linux Foundation's Agentic AI Foundation in 2026; Docling OpenShift Operator shipped with Red Hat in 2026 | DOCX is **input only**; exports to Markdown/JSON/HTML/DocLang. No DOCX/OOXML export path found |
| **Unstructured** (OSS core) | Apache-2.0 | Actively maintained (0.24.0 observed, 2026-07-06) | DOCX is **input only** (`partition_docx`); emits typed JSON elements (Title/NarrativeText/Table/…). No OOXML write-back found |
| **MinerU** (OpenDataLab) | "MinerU Open Source License" (Apache-2.0-based, custom terms): free unless the user's org exceeds 100M MAU or $20M/month revenue, and hosted-service use must credit MinerU visibly | Actively developed; now supports DOCX/PPTX/XLSX in addition to PDF/images | DOCX is **input only**; emits Markdown/JSON for RAG-style consumption. No OOXML export found |
| **MarkItDown** (Microsoft) | MIT | Actively maintained (0.1.7 observed, 2026-07-29) | DOCX is **input only**; emits Markdown. No OOXML export |
| **Mammoth.js** | BSD-2-Clause | Actively maintained | DOCX is **input only**; emits HTML, explicitly by dropping most direct formatting in favor of semantic style mapping |

Licensing-for-research-use summary: every entry above except Aspose.Words is free to use for this paper's research purposes without a purchase (MIT/BSD/Apache-2.0/MPL-2.0/GPL-2.0-or-later all permit research and internal use; GPL's copyleft terms only bind if modified Pandoc code were redistributed, which is out of scope here). MinerU's free tier comfortably covers a research paper's scale but carries a visible-attribution obligation if results are served through a hosted service. Aspose.Words is the only candidate that requires a purchased or evaluation (watermarked) license before it could produce a usable, unwatermarked baseline artifact — this falls under `runtime-capability-contract-v0.md`'s "Approve any paid/API baseline" manual gate and has not been approved.

## 3. Word-native product acceptance matrix

The determining question, per this item's brief: **does the tool's own output land back in genuinely Word-native, editable OOXML, or is its output a lossy/flattened approximation (HTML, Markdown, PDF, plain extracted JSON) that a human could not reopen and keep editing as the same Word document?** This is independent of how good the tool is at its actual job — a flattening tool can be excellent at flattening and still fail this test by design.

### Category A — genuine, directly Word-openable OOXML output (native writer, structure-preserving intent)

| Tool | Verdict | Caveat |
|---|---|---|
| python-docx | Word-native | Real OOXML writer, but a narrow, hand-coded API surface: no native chart/SmartArt authoring, and equation/OMML work requires raw-XML injection rather than a high-level call. A resave can silently drop document features the library doesn't model. |
| Apache POI (XWPF) / docx4j | Word-native | Broader OOXML coverage than python-docx in places (per direct tooling comparisons found in search), still bounded by whatever each library's object model implements. |
| Aspose.Words | Word-native | Broadest commercial fidelity claim found, but gated on payment; unlicensed output is watermarked and unusable as a clean baseline. |
| LibreOffice (headless resave/export) | Word-native, but re-derived | Produces a real .docx a human can reopen in Word, but it is regenerated through LibreOffice's own independent OOXML filter — expect `w14:paraId` churn, style renormalization, and known gaps (complex field codes, SmartArt, some OMML constructs). This is exactly why `runtime-capability-contract-v0.md` already treats LibreOffice as a **secondary compatibility renderer that must never substitute for Word evidence** — this investigation's finding reinforces, not revises, that existing framing. Not installed on this host currently.

### Category B — real OOXML container, but content is AST-mediated (structure not identity-preserving)

| Tool | Verdict | Caveat |
|---|---|---|
| Pandoc (DOCX→DOCX) | Word-native file, non-identity-preserving | The output file genuinely opens and edits in Word — unlike every Category C tool below — but content passes through Pandoc's own generic document AST first. Paragraph IDs, comments, most direct formatting, and (per Pandoc's own open issues) track-changes-on-write are not preserved; math is re-expressed as OMML generated from Pandoc's math AST rather than carried through from the source OMML tree. Per `comparator-contract-v0.md` §2 family 3, this must be reported as a clearly labeled **conversion-mediated / lossy baseline**, never compared directly against native OOXML graph scores without reporting the conversion loss separately (§5). |

### Category C — no OOXML output at all (pure flattening / extraction)

| Tool | Verdict | Caveat |
|---|---|---|
| Docling | Not Word-native | DOCX is input-only; output is Markdown/JSON/HTML/DocLang. Cannot be reopened as the same Word document under any circumstance. |
| Unstructured (OSS) | Not Word-native | `partition_docx` emits typed JSON elements; no write-back path exists. |
| MinerU | Not Word-native | DOCX is one of several inputs; output is Markdown/JSON for RAG pipelines. |
| MarkItDown | Not Word-native | DOCX→Markdown only, explicitly built for LLM ingestion, not document production. |
| Mammoth.js | Not Word-native | DOCX→HTML only, and deliberately lossy by design (semantic style mapping, direct formatting dropped). |

None of the Category C tools can ever pass this paper's Track D (native Office comprehension) or Track C (rendered-parity, Word-authority) checks by construction — their output is not an OOXML package, so there is nothing for Word to open. They remain legitimate as Track A family-3 conversion-mediated *content* baselines (their extracted text/structure can still be scored against the gold manifest's text/order/table facts) and as Track B/D comprehension-context tools, but they cannot stand in for a Word-native acceptance claim, and the comparator contract's §5 rule ("do not compare a parser after conversion against native OOXML without reporting conversion loss separately") applies to every one of them.

## 4. Mapping onto the comparator contract's Track A baseline families

- **Family 2** ("generic DOCX extraction using the available parser stack, with structure deliberately normalized to the common schema"): best served by python-docx (already an editable dependency of this paper's own toolchain family) and optionally Apache POI/docx4j if a second, independently-implemented OOXML reader is wanted to avoid single-implementation bias. Both are Category A — native OOXML I/O — so the "lossy" risk here is confined to each library's own feature-coverage gaps, not to a conversion step.
- **Family 3** ("conversion-mediated extraction… clearly labeled as a lossy conversion baseline"): Pandoc (Category B) and any of the Category C extraction tools (Docling, Unstructured, MinerU, MarkItDown, Mammoth.js) are candidates, each to be labeled by exactly which lossy step it represents (AST round-trip vs. Markdown/JSON/HTML flattening) rather than lumped together.
- **Family 4** (controlled ablations) is orthogonal — it operates on Meridian's own output, not a third-party tool, and is unaffected by this inventory.
- **Track C (rendered-parity)**: Word COM remains the sole verified render authority on this host (Section 1 above); LibreOffice remains available only as an optional, clearly-labeled secondary compatibility renderer once installed, never a Word substitute, unchanged from `runtime-capability-contract-v0.md`.

## 5. What this item does not establish

This investigation inventories availability, licensing, and I/O direction only. It does not benchmark any tool's actual extraction accuracy, does not pin exact tool versions for a frozen baseline run (per `comparator-contract-v0.md` §2, "No model is called 'latest' without a dated version record" — a real baseline run must record the exact installed version, not the range observed here), and does not install or invoke LibreOffice, Aspose.Words, Pandoc, or any of the extraction tools locally. No baseline family has been executed. No dataset was downloaded. No claim in this document should be read as clearing PAPER-11 (semantic OMML correctness) or PAPER-20 (retained-receipt audit grade) — those remain open per the existing sprint notes.

Sources: [python-docx](https://github.com/python-openxml/python-docx), [Apache POI XWPF](https://poi.apache.org/components/document/), [docx4j vs POI comparison](https://blog.fileformat.com/word-processing/apache-poi-vs-docx4j-vs-openxml-sdk-which-one-should-you-use/), [Aspose.Words pricing](https://purchase.aspose.com/pricing/words/family/), [LibreOffice licenses](https://www.libreoffice.org/licenses/), [Pandoc](https://github.com/jgm/pandoc), [Pandoc track-changes issue](https://github.com/jgm/pandoc/issues/1562), [Pandoc OMML display-math issue](https://github.com/jgm/pandoc/issues/11674), [Docling document converter reference](https://docling-project.github.io/docling/reference/document_converter/), [Docling GitHub](https://github.com/docling-project/docling), [Unstructured GitHub](https://github.com/Unstructured-IO/unstructured), [Unstructured LICENSE](https://github.com/Unstructured-IO/unstructured/blob/main/LICENSE.md), [MinerU GitHub](https://github.com/opendatalab/MinerU), [MinerU LICENSE](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md), [MarkItDown GitHub](https://github.com/microsoft/markitdown), [Mammoth.js](https://github.com/mwilliamson/mammoth.js/).
