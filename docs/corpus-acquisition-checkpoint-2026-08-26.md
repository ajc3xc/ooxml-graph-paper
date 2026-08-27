# Corpus acquisition checkpoint — 2026-08-26

This checkpoint records the first local acquisition pass for the OOXML graph paper. It does not
claim that the final benchmark gold corpus exists. All downloaded artifacts are on non-synced E:
storage; no OneDrive file was used as an input or output.

## What is now staged

### OmegaUse-OfficeVal native Office candidate pool

- Source: <https://huggingface.co/datasets/baidu-frontier-research/OmegaUse-OfficeVal>
- Local root: `E:\MeridianData\ooxml-graph-paper\raw\omega-officeval`
- Source tree snapshot: `hf-tree-main.json`
- Task/rubric snapshot: `tasks_and_rubrics_en.json`
- Dataset README: `README.md`
- Native DOCX files staged: **63**
- DOCX bytes staged: **90,198,480**
- Downloaded tree manifest SHA-256: `53AD032656F5A86E30B0AC31BA1F73DCDF595BBB3EC6B882E1E67983B7ACFB8B`
- Downloaded task/rubric SHA-256: `63C454B021BAC9C019B432287014F421502E2264C3A23D22AFFB39060189BA02`

The source repository declares Apache-2.0, but individual source provenance and privacy still need
to be reviewed before any document is promoted into graph gold or redistributed. The pool is
quarantined as `candidate_unlabeled`, not `gold`.

An independent package scan found:

| Feature | Documents containing it | Total elements |
|---|---:|---:|
| Tables | 47 | 644 |
| Drawings | 45 | 426 |
| Bookmarks | 54 | 646 |
| Fields | 13 | 1,239 |
| Content controls | 8 | 8 |
| Footnote references | 2 | 3 |
| Native OMML equations | 0 | 0 |
| Tracked insertions/deletions | 0 | 0 |

Conclusion: OmegaUse is useful for real-world OOXML structural stress and parser baselines, but
it cannot supply the equation/OMML track and cannot by itself satisfy the paired graph-gold gate.

### MathMLben equation-source candidate

- Source: <https://github.com/gipplab/MathMLben>
- Local root: `E:\MeridianData\ooxml-graph-paper\raw\mathmlben`
- Pinned Git commit: `26f841d022f1439a9466182673370ad9912d9844`
- Formula JSON records: **375**
- The original MathMLben paper describes a 305-expression core set; later repository records extend
  beyond that core.
- The records include corrected TeX, semantic TeX, MathML, source URI/title, and equation type
  fields suitable for selecting a stratified equation fixture list.
- No clear repository license file was found in the pinned checkout. Treat this as a local research
  candidate only until rights/usage terms are confirmed; do not redistribute it as project data.

Conclusion: MathMLben can provide the source/equation strata for a conversion sub-benchmark, but it
is not an OOXML package corpus and does not provide Word render receipts or native OMML gold.

### ReadingBank status

- Official repository: <https://github.com/doc-analysis/ReadingBank>
- Official full ZIP link supplied for this project currently returns HTTP 404:
  <https://drive.google.com/file/d/15SydqWAXWZZRtAmSf6ZD7b51A8ASuC8i/view?usp=drive_link>
- The official description says the released full material is preprocessed text/layout information
  derived from DOCX, with only an approximately 100-page example subset publicly exposed.

Conclusion: ReadingBank remains useful as a separate reading-order/layout context track if the
authors restore access, but it is not the primary OOXML graph gold source even when obtained.

### ReadingBank public examples actually available locally

- User-supplied source: `C:\Users\13144\Downloads\ReadingBank_images_examples.zip`
- E: copy: `E:\MeridianData\ooxml-graph-paper\raw\readingbank\ReadingBank_images_examples.zip`
- SHA-256: `8CB8BF352E476872CB56FAF12C3302085052A920268FDBFCBB26DDCA88DF7AB7`
- ZIP members: 99 PNG page images and 99 matching TXT annotations.
- Annotation rows: 19,953; every non-empty row has 8 tab-separated fields.
- Annotation shape observed: page/task id, token text, left/top/right/bottom coordinates, page width,
  and page height.
- ZIP integrity test: passed.

This is immediately usable for a ReadingBank layout/read-order context slice and for checking whether
document parsers preserve visible token order and coordinates. It contains no DOCX/OOXML packages,
OMML, native Word IDs, captions/references, revisions, or Word render receipts, so it cannot satisfy
the paired OOXML graph-gold gate by itself.

### New Drive-folder verification

The user-supplied folder
`https://drive.google.com/drive/folders/15Cu-dYmyh3PJEIERiYVcTiyv0c7798Of?usp=drive_link`
was inspected through the in-app browser. It contains exactly three visible items:

- `ReadingBank_images_examples.zip`, the same 11.2 MB public examples archive;
- `Caller ID`, a deleted shortcut whose original item is unavailable;
- `alazzani (Unzipped Files)`, an unrelated extracted Android package. Its visible contents include
  `AndroidManifest.xml`, `classes.dex`, `resources.arsc`, `META-INF`, `okhttp3`, and other Android
  package directories; it is not ReadingBank.

No full `ReadingBank.zip` is present in this folder. The examples archive is therefore the complete
ReadingBank artifact currently available to this project, not merely a partial local download of a
larger accessible corpus.

## What is still missing for the true benchmark corpus

No public source found in this investigation supplies all of the following together:

1. the original DOCX package;
2. independently authored node/edge graph gold for paragraphs, tables, equations, captions,
   anchors, references, source bindings, revisions, and clones;
3. verified Word render output and a retained render receipt;
4. per-document privacy/licensing provenance; and
5. adversarial malformed/unsupported cases with explicit expected failures.

Therefore the defensible corpus is a composed benchmark, not a downloaded single dataset:

- OmegaUse candidate documents for real-world structural variation after per-file review;
- the local ReadingBank examples ZIP for a separately reported image/layout context track;
- MathMLben-derived equation inputs after rights review;
- rights-clean or human-authored Word fixtures for the graph invariants;
- independently labeled and Word-rendered graph gold records;
- a held-out composite stress slice authored before implementation results are inspected.

## Next executable acquisition/preparation wave

1. Review the 63 OmegaUse DOCX files for PII, source provenance, equation absence, and feature
   diversity; select at most 10–12 rights-cleared real-world documents.
2. Select a stratified MathMLben subset covering fractions, scripts, radicals, accents, matrices,
   delimiters, large operators, limits, functions, and malformed/unsupported inputs; do not call it
   OMML gold until Word-authoritative outputs are independently checked.
3. Obtain human approval for Word COM as the canonical renderer and for the no-2030-revival scope.
4. Author the tier-1 Word fixtures and the tier-3 held-out composites using an independent path,
   then inspect raw OOXML and Word renders before Meridian sees the final gold labels.
5. Produce the actual E: gold manifest, graph records, retained PDFs, and hashes; only then unlock
   PAPER-15.

The current E: pool is therefore **ready for preprocessing and review**, but the final paired
DOCX/OOXML/Word-render gold corpus is correctly still blocked.
