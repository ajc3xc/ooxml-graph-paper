# PAPER-S6: bounded 500-document acquisition result (v1)

Status: bounded screening acquisition complete, per human-answered HITL
`f24d8e0e-bdf4-47df-81b8-f0392fca954b` (2026-08-30, Adam: "Approve a bounded
acquisition of metadata-listed candidates, subject to per-file rights/privacy/
exposure adjudication and no redistribution"). **This revises, not confirms,**
the prior "zero organic OMML" finding -- read the numbers below carefully.

## What was done

500 documents (not the full 18,680-record candidate pool) fetched from the
docx-corpus remote candidate list (`raw/docx-corpus/filtered_candidates.json`),
excluding the 90 already sampled. Stratified by the pool's own `type` field,
weighted toward equation-likelier categories: technical=200, reports=125,
reference=100, policies=75 (seed 20260830, reproducible). Rate-limited
sequential fetch (1 req/sec, real User-Agent identifying the pull as bounded
academic screening), 500/500 downloaded successfully, 0 failures.
Manifest: `E:\MeridianData\ooxml-graph-paper\manifests\docxcorpus-batch-500-v1.json`.

Scanned with the existing, unmodified S18 scanner
(`tools/screen_organic_omml_candidates.py`) against
`raw/docx-corpus/batch-500-v1/`.
Output: `E:\MeridianData\ooxml-graph-paper\manifests\s6-batch-500-omml-screen-v1.json`.

## Result: 3 organic OMML documents found (not zero)

| candidate_id (first 16 hex) | type | topic | OMML containers | feature families |
|---|---|---|---:|---|
| `100995cdd09ba0e1` | technical | technology | 5 | accent_or_limit=2, fraction=2 |
| `16301d3c45ca9a9b` | technical | technology | 4 | (none matched by classifier) |
| `3ac63c39c40a125c` | reports | technology | 7 | fraction=5, radical=1 |

All 3 pass package integrity (`ok: true`), none match the hand-authored-fixture
naming heuristic (`looks_hand_authored_by_name: false`). One unrelated document
in the batch (`7999bbea7cf478e2`) failed package integrity (`missing
word/document.xml`) -- a genuinely corrupt/malformed source file from the
crawl, not connected to the equation finding; not investigated further as it
is out of scope for this item.

**This is the first organic (non-fixture) native-OMML evidence found in this
entire investigation**, across all prior scanning (434 local files: 0 hits;
first 90 remote samples: 0 hits). Revised cumulative base rate: 3 organic hits
across 934 total documents scanned so far (~0.32%), all three clustered in
`topic=technology` -- i.e. a real but narrow and rare signal, not spread
across diverse source groups.

## What this does NOT establish

- **The S6 confirmatory gate remains closed.** It requires >=24 clean organic
  units from >=8 independent source groups and >=6 task families. 3 units,
  all from one topic within one crawl source, does not approach that bar, and
  extrapolating the observed ~0.3-0.6% hit rate, reaching 24 would require
  screening on the order of several thousand more documents -- explicitly the
  kind of dataset-count chase this project's own pinned decision
  ("dataset count is not a success criterion") argues against pursuing for a
  bounded equation ablation that is not the paper's primary thesis.
- **None of the 3 candidates is admitted.** Per the scanner's own ledger
  fields, all three remain `admission_decision: not_admitted`,
  `privacy_pii_review: not_assessed`, `exposure_review: not_assessed`,
  `license_or_redistribution: unknown_pending_review`, `word_receipt:
  not_run`. No content from these files has been read, quoted, or exposed
  beyond structural metadata (OMML container counts and feature-family
  classification) in this document or elsewhere. They are retained locally
  only, per the HITL's no-redistribution condition.
- **This does not change the corpus's D0 status.** The 127-document D0 corpus
  is untouched; these 3 files are not proposed for promotion.

## Recommendation

Do not pursue further acquisition rounds to chase the 24-unit bar -- report
equation-capability results (semantic classification accuracy, etc.) as
fixture/pilot-evidence only, exactly as this project's own prior
recommendation already concluded, now with a materially more precise
underlying fact: organic native OMML is confirmed to exist in real-world
DOCX at a low single-digit-per-mille rate, concentrated in technology-topic
technical documents, rather than being entirely absent. This is a more
defensible, more honest claim for publication than either "zero exists" or
an inflated claim built by chasing the full 18,680-record pool.

If a future item wants to actually admit these 3 candidates (or expand
further), it needs: per-file rights/license determination, PII/privacy
review of body content (not done here -- deliberately, given no clear
redistribution/product-linkage decision has been made), independent raw-XML
gold extraction, and a Word-COM open/render receipt -- the same pipeline
every other admitted document in this corpus went through.
