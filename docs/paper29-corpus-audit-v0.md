# PAPER-29: gold corpus reconciliation audit (v0)

Status: a real, automated, independently-run audit of the existing 127-document gold
corpus and its manifests -- not a re-generation of the corpus. Read-only over
`E:\MeridianData\ooxml-graph-paper\gold\manifests`, plus one small, evidence-backed fix
applied to close a genuine gap it found.

Tool: `tools/audit_gold_corpus.py`. Full machine-readable output:
`E:\MeridianData\ooxml-graph-paper\gold\manifests\paper29-corpus-audit.json`.

## What was checked, per document (all 127)

1. Source hash (`gold_record.document.source_sha256`) present.
2. Word-COM render receipt present in the manifest (`render_receipt` field) **and** the
   retained PDF actually exists on disk at `renders/gold/<doc_id>/<doc_id>.pdf` -- both
   halves are required; a receipt field with no retained file, or a file with no receipt
   record, both count as a gap.
3. Package-integrity result present, and if present, actually `ok: true` (not merely
   present-but-failing).
4. Independent-provenance sanity check: `gold_record.provenance.producer` must not be
   null/empty/`docs_intel.py` itself (the schema's own anti-circularity rule).
5. Split assignment (`smoke`/`scale_up`/`final`) present in `_split.json`.
6. For docx-corpus-sourced documents: an explicit `verdict: "promote"` entry in
   `_docxcorpus_review.json`, keyed by the exact doc_id used in the corpus.
7. For OmegaUse- and docx-benchmark-sourced documents: a rights/privacy rationale entry
   in `_tier2_review.json`'s `promoted` list.
8. Corpus-wide: duplicate underlying source content (same `source_sha256` promoted under
   two different `doc_id`s).

## Results

**126 of 127 checks landed clean on the first pass; one real gap was found and fixed
(not hidden), leaving 0 open issues after the fix.**

| Check | Result |
|---|---:|
| Missing source hash | 0 |
| Missing/unretained render receipt | 0 |
| Missing package-integrity result | 0 |
| Package-integrity present but failing | 0 |
| Missing split assignment | 0 |
| Suspect/missing independent provenance | 0 |
| docx-corpus documents without a `promote` verdict | 0 |
| Duplicate source content across distinct doc_ids | 0 (127 documents, 127 distinct `source_sha256` values) |
| Missing machine-readable rights rationale | **2, found and fixed** (see below) |

Sanity cross-checks against raw data (to rule out the audit script vacuously passing):
`composite-03-multi` correctly shows 2 equation nodes and 2 caption nodes;
`fixture-02-equation` shows 1; `fixture-04-caption` shows 1; corpus-wide equation-node
count is 8 across 7 equation-bearing documents (matches `paper15-first-attempt-v0.md`'s
addendum, where `composite-03-multi` alone contributes 2 of the 8 equation nodes to the
7-document set). A sample `package_integrity` record and `render_receipt` record were
read directly and confirmed to carry real fields (`ok`, `part_count`; `renderer`,
`word_version`, `input_hash_sha256`, `output_hash_sha256`, `retained_pdf_path`), not
placeholder/boolean-only stand-ins.

## The one real gap found: rights rationale for the two docx-benchmark documents

`tier2-docxbenchmark-investment-agreement-blank` and
`tier2-docxbenchmark-investment-agreement-executed` had a real, verified license
rationale -- but it lived only as prose in `docs/dataset-landscape-2026-08-25.md`
("the included Series Seed investment-agreement DOCX is a public-domain CC0-1.0 template
... explicitly free for any use including commercial"), not in the same machine-readable
`_tier2_review.json` structure used for all 47 OmegaUse-sourced documents. This is a real
reconciliation inconsistency (the item's own charge: "reconcile ... any candidates that
were promoted without enough content review" recorded in a checkable place), not a
license problem with the documents themselves.

**Verified, not merely inferred, before fixing:** read the "executed" variant's actual
extracted paragraph text directly from its gold manifest before writing a rationale for
it. It fills the Series Seed template with "Stark Industries, Inc.", "Anthony Stark",
"200 Park Avenue, New York, NY 10166", and "anthony@starkindustries.com" -- the Marvel
Comics fictional company/character used as the illustrative example in the upstream
`docx-benchmark` repository's own fixture, not a real, identifiable person's data. This
was confirmed by direct text inspection, not assumed from the filename or the "executed"
label alone.

**Fix applied**: added both doc_ids to `_tier2_review.json`'s `promoted` list with a note
citing the CC0-1.0 `fixtures/series-seed/LICENSE-INFO.txt` source and the direct-text
verification above. Re-running the audit after this fix shows 0 open issues corpus-wide.

## What this audit does not cover

This is a structural/provenance reconciliation pass, not a re-verification of the
underlying graph *content* correctness (node/edge accuracy) -- that is
`independent_gold_extractor.py`'s own job and `paper15-first-attempt-v0.md`'s scoring
pass, not this audit. It also does not re-run Word-COM rendering or re-check package
integrity from scratch; it reads the existing recorded results and confirms they are
present, coherent, and (for package integrity) actually passing, rather than merely
present.
