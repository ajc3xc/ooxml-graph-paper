# PAPER-37: untested-document and gold-corpus-addition audit (v0)

Status: a real reconciliation audit of the 127-document corpus against every backend's
actual test coverage, plus a review of every remaining raw candidate source for further
additions. Builds on, does not duplicate, PAPER-29's structural audit
(`docs/paper29-corpus-audit-v0.md`), which already confirmed every one of the 127 documents
has a source hash, render receipt, package-integrity result, graph manifest, and rights
rationale. This item's focus is different: per-backend test coverage and untapped candidate
sources.

## Per-backend coverage of the 127 documents

| Backend | Coverage | Source |
|---|---:|---|
| native_meridian | 127/127 scored | `docs/paper30-graph-scorer-v0.md` |
| python_docx | 122/127 scored, 5 crashed (`InvalidXmlError`, missing `<w:tblGrid>`) | `docs/paper30-graph-scorer-v0.md` |
| docling_pdf_document_ai | 10/127 scored as of PAPER-31 (smoke slice); PAPER-36 is running the remaining 117 at the time of this audit | `docs/paper31-local-baselines-v0.md`, in-progress PAPER-36 run |
| Pandoc | 0/127, `not_run` -- not installed on this host | every PAPER-15/30/31 report |
| LibreOffice | 0/127, `not_run` -- not installed on this host | every PAPER-15/30/31 report |
| Hosted document-AI | 0/127, `not_run` -- no credential/approval | `docs/runtime-capability-contract-v0.md` PAPER-32 section |

The 5 python-docx crash documents, named for completeness:
`fixture-01-baseline`, `fixture-04-caption`, `composite-01-report`, `composite-02-adversarial`,
`composite-03-multi` -- all 5 are hand-authored tier1/tier3 fixtures with valid,
Word-openable tables lacking an explicit `<w:tblGrid>` element (OOXML does not require one;
python-docx's `Table.columns` does).

## A new candidate source found and correctly excluded: MathMLben

`E:\MeridianData\ooxml-graph-paper\raw\mathmlben\` (a git checkout, not previously audited in
this project's dataset-landscape docs) is **not a native DOCX source at all**. Verified by
direct inspection, not assumed from the directory name: it is "GoUldI"/MathMLben
(`ag-gipp/MathMLben`), an academic MathML-formula-representation survey/conversion tool from
a 2018 JCDL paper (Schubotz et al.), shipped as a Node.js web app plus a dataset of 2,455
`.mml` (MathML), 660 `.tex`, and 308 `.xml` files -- **zero `.docx` files among its 3,889
tracked files**. Per this item's own standing rule ("do not treat ... PDF annotations as
native OOXML graph gold"), the same logic applies here for a different reason: this source
has no OOXML/DOCX content whatsoever to extract from. **Excluded from the gold corpus
entirely, not silently ignored** -- it is a MathML/LaTeX notation-conversion benchmark,
unrelated to Word documents, and contributes nothing to a paired-DOCX evaluation.

## ReadingBank, DocBank, and other non-DOCX raw sources: unchanged from prior audits

Re-confirmed present under `E:\MeridianData\ooxml-graph-paper\raw\` but not re-litigated here:
`ReadingBank` (derived text/layout only, no raw DOCX, per PAPER-12's original finding) and
`DocBank-repo`/`DocBank-repo-incomplete-20260825` (public PDF/token-layout corpus, explicitly
Track-B/secondary context per `comparator-contract-v0.md`, never native OOXML gold). Neither
contributed, nor should contribute, a single document to the 127-document gold set.

## docx-corpus and OmegaUse: exclusions are retained with rationale, not lost

Verified directly: `E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\review_results.json`
holds the full 90-document sample review (**67 promote, 23 exclude**, matching
`docs/gold-corpus-status-v0.md`'s prior count); `_docxcorpus_review.json` under
`gold\manifests\` is correctly a promoted-only extract used by the build pipeline, not a
sign that the 23 exclusions were dropped -- their rationale is intact in `review_results.json`.
Similarly, `_tier2_review.json`'s `excluded` array retains all 15 OmegaUse exclusions with
per-document rationale (real PII findings: filled national ID numbers, named students paired
with student IDs, etc. -- see `docs/gold-corpus-status-v0.md`).

**Untapped candidate pool, sized honestly**: `docx-corpus`'s own metadata lists 18,770
filtered (safety-pre-screened) candidates; only 90 have ever been individually reviewed
(67 promoted). Over 18,600 filtered-but-unreviewed candidates remain technically available.
**Expanding the corpus further is not undertaken in this item** -- PAPER-39/40 are scoped to
finalize scoring and reporting against the existing, already-audited 127-document corpus, and
expanding it now would require redoing PAPER-30/31/34's scoring passes on a larger, different
corpus, a materially larger undertaking than this audit item's own scope. This pool is
recorded here as a real, sized, available option for a future corpus-expansion item, not
silently unmentioned.

## Underrepresented strata (unchanged findings, reconfirmed)

- **Zero of the 119 real-world documents contain a native OMML equation.** All 7 (now: 8
  equation nodes across 7 documents, per PAPER-30) equation-bearing documents are
  hand-authored tier1/tier3 fixtures. This remains the corpus's clearest structural gap for
  testing equation fidelity against organic, real-world content.
- **Caption/reference coverage**: captions exist in the corpus (`fixture-04-caption`,
  `composite-01/03`) but no document exercises a `references`-edge (cross-reference field to a
  figure/table/equation) at the tier1/tier3 hand-authored level -- real-world `docx-corpus`/
  OmegaUse documents may contain field-based cross-references, but no fixture explicitly
  isolates this case the way `fixture-04-caption` isolates captions.
- **Tab-character text fidelity**: the gold-fidelity gap already found and flagged
  (`independent_gold_extractor.py` drops `<w:tab/>`/`<w:br/>`, task `task_ab325093`,
  `docs/paper30-graph-scorer-v0.md`) is a real, known limitation affecting any tab-heavy
  document's text-based scoring, not corpus-membership-worthy on its own but reconfirmed here
  as still open.

## Summary verdict

No new documents were added to the gold corpus in this item. One new candidate source
(MathMLben) was investigated and correctly excluded with reasoning recorded, rather than
either silently ignored or wrongly promoted. Per-backend coverage is now precisely
inventoried, including the in-progress PAPER-36 Docling expansion. The known equation-content
gap and tab-fidelity gap are reconfirmed as open, named limitations, not re-solved here.
