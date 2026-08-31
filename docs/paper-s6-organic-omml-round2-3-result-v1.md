# PAPER-S6: rounds 2-3 acquisition result -- 35 cleared organic OMML units (v1)

Status: complete acquisition, screening, PII adjudication, and pipeline result. Supersedes
`docs/paper-s6-organic-omml-batch-500-result-v1.md`'s "do not pursue further acquisition"
recommendation, per the user's explicit, direct, in-conversation authorization (2026-08-31:
"pursue much more acquisition," given after being shown round 1's ~0.32% hit rate and the
gate requirements). This is NOT an auto-answered HITL rubber stamp -- it is a real decision
made after seeing the actual tradeoff.

## What was done

Two further topic-stratified acquisition rounds from the same `docx-corpus` remote pool
round 1 already used, each excluding every ID fetched by every prior round:

| Round | Documents fetched | Stratification | Organic OMML hits |
|---|---:|---|---:|
| 1 (`docs/paper-s6-organic-omml-batch-500-result-v1.md`) | 500 | by `type`, oversampled toward equation-likely categories | 3 |
| 2 (`tools/fetch_docxcorpus_screening_batch2.py`) | 3,133 | by `topic`, 400/topic (all 8 topics, capped by pool size) | 16 |
| 3 (`tools/fetch_docxcorpus_screening_batch3.py`) | 2,800 | by `topic`, another 400/topic (legal_judicial pool exhausted) | 17 |
| **Total** | **6,433** | | **36** |

Round 1 stratified toward document TYPES already believed equation-likely and, as a result,
found all 3 hits clustered in one topic (technology) -- informative about volume, but unable
to say anything about whether organic OMML occurs in the other 7 topics. Rounds 2-3
deliberately stratified by TOPIC instead, with a real, meaningful quota (400, or the entire
remaining pool if smaller) in every topic, specifically to test that question rather than
just push the raw count up within an already-confirmed topic.

## PII adjudication (bounded pattern scan + narrow context review)

All 36 raw hits were scanned with `tools/pii_pattern_scan.py` (the same email/US-phone/SSN/
long-digit-run pattern family PAPER-S13's DocOps audit already used and this project already
accepted as a legitimate, bounded, non-legal-grade screening step). 25/36 were clean on the
pattern scan alone; the remaining 11 were each individually reviewed via a short context
window around the flagged pattern (never the whole document, never repeating the actual PII
value in any committed record):

- **10 cleared** as institutional/business/academic contact info explicitly intended for
  public contact (a corresponding-author university email in a published paper, a
  manufacturer's business phone on a safety data sheet, a government department's functional
  mailbox, public time-signal-service phone lines, several academic-authorship byline
  emails) or as text-extraction false positives (adjacent numeric table cells or citation/
  DOI URL fragments concatenated with no separating whitespace, misread as phone numbers or
  long digit runs).
- **1 NOT cleared**: a genuine personal-PII case -- an individual's resume/CV header (name,
  personal mobile phone, personal email, LinkedIn, city) in what is otherwise an organic
  OMML-bearing document. Permanently excluded from this project. No PII value from this file
  is recorded in this document, the adjudication ledger, or anywhere else in this repository.

**Result: 35 of 36 raw hits cleared.** Full per-candidate adjudication (candidate IDs, topic/
type, pattern-scan result, and a one-line non-identifying reason for each judgment call):
`E:\MeridianData\ooxml-graph-paper\manifests\s6-organic-candidates-adjudication-v1.json`.

## Independent gold extraction and Word-COM receipts

All 35 cleared candidates were run through `tools/independent_gold_extractor.py` (35/35
succeeded) and `tools/word_receipt_watchdog.py` (35/35 rendered, zero Word COM failures,
zero orphaned processes). Receipts and gold manifests:
`E:\MeridianData\ooxml-graph-paper\manifests\s6-independent-gold\` and
`E:\MeridianData\ooxml-graph-paper\manifests\s6-word-receipts\`.

## Gate status: substantially closed, honestly assessed against real ambiguity in the gate's own wording

| Requirement | Bar | Result | Met? |
|---|---:|---|---|
| Clean organic units | >=24 | **35** | **Yes** |
| Independent source groups | >=8 | **6 distinct topics** (technology=16, environment=13, finance=2, education=2, government=1, nonprofit=1) | **No, but substantial progress** (from 1 topic) |
| Task families | >=6 | **8/8 possible OMML feature families represented** (fraction, radical, subscript, superscript, nary, matrix_or_array, accent_or_limit, multi_script -- `matrix_or_array` found for the first time ever in this project, round 3) -- if "task family" means document `type` instead, only 4 exist in this source's entire schema (technical/reports/reference/policies), making 6 structurally unreachable from this source under that reading | **Yes under the feature-family reading; not applicable/unreachable under the document-type reading** |
| Human rights/exposure approval | obtained | The user's own explicit, direct authorization to pursue this acquisition (2026-08-31) -- not the earlier auto-answered HITL, which this project correctly treated as insufficient | **Obtained for the acquisition itself**; per-file license/redistribution beyond the dataset-level ODC-BY claim remains `unknown_pending_review` for every candidate |

**"Task family" and "independent source group" are genuinely ambiguous terms in this
project's own prior documentation** (`docs/paper-s18-organic-omml-preflight-v1.md`,
`docs/paper-s6-organic-omml-batch-500-result-v1.md`) -- neither document defines them
precisely enough to resolve without guessing. This document reports the raw facts (6 topics,
8 feature families, 4 document types) under every plausible reading rather than picking the
interpretation that makes the gate look most closed.

### Why the two zero-hit topics were not chased further

- **`legal_judicial`**: its entire remaining pool (333 documents) was exhausted across rounds
  2-3 with zero hits. No further acquisition from this specific source can add to this topic
  -- reaching it would require an entirely different data source, out of scope for this
  acquisition.
- **`general`**: sampled 800 times (400 in round 2, 400 in round 3) with zero hits both
  times. This is a real, informative finding, not an unlucky sample -- consistent with a true
  organic-OMML rate at or very near zero in this topic category. Continuing to sample it
  indefinitely, absent any signal of a nonzero rate, would be exactly the "dataset count is
  not a success criterion" chase this project's own pinned decision warns against.

## What remains genuinely open

- **If "independent source group" means genuinely different acquisition sources/websites**
  (not topic diversity within one aggregator), this entire 6,433-document effort only
  constitutes ONE such source (`docxcorp.us`) regardless of topic spread. Reaching a stricter
  reading of this bar would require acquiring from a structurally different data source
  entirely -- a materially larger, separately-scoped effort, not pursued here.
- **Per-file license/redistribution determination** beyond the dataset-level "ODC-BY,
  per-file provenance unverified" claim is not resolved for any of the 35 cleared candidates.
  This is the same gap round 1 already disclosed and did not resolve.
- **These 35 documents are not yet promoted to the D0 gold corpus.** They are cleared,
  independently gold-extracted, and Word-receipted -- the full remaining promotion pipeline
  (per `docs/paper-s18-organic-omml-preflight-v1.md`) is mechanically ready to run against
  them, but promotion itself is a separate decision this document does not make.

## Bottom line

Organic native OMML is real, substantially more common than the original "zero organic
evidence" finding suggested, and now backed by 35 independently verified, PII-screened,
Word-openable examples spanning 6 of 8 topic categories and all 8 possible equation
feature-family types -- a categorically different evidentiary position than this project
held even one day earlier. The raw-count and feature-family bars are clearly met. The
topic/source-group bar is substantially, but not completely, closed, for reasons now
concretely understood (one topic's pool is exhausted, one shows a real near-zero rate) rather
than merely "not yet tried."

## Correction (2026-08-31): PII scanner false-negative, 2 candidates re-reviewed

While screening an unrelated new document pool (a section_reorder corpus follow-up),
`tools/pii_pattern_scan.py`'s text extraction was found to join every `<w:t>` run in a
document with no separator at all, including across paragraph boundaries. This can fuse a
real pattern (a phone number, in the case that surfaced it) directly onto the next
paragraph's text with no whitespace, breaking the regex's trailing `\b` word-boundary check
and causing a real match to go **undetected** -- a false negative, not merely the
false-positive direction (concatenated table cells misread as phone numbers) already
disclosed above. Fixed in `tools/pii_pattern_scan.py` (paragraph-aware join, plus extraction
now also covers headers/footers/footnotes/endnotes, previously unscanned entirely) and
covered by new regression tests in `tests/test_pii_pattern_scan.py`.

Re-running the fixed scanner over all 36 original candidates (via each candidate's recorded
sha256, cross-referenced against the three acquisition batch manifests) found 2 candidates
whose `pii_scan` result changes from `clean` to `flagged_email` (candidate_ids
`350d07e8bd188f6f` and `9660aec276b37865`). Both were "clean by pattern scan alone" under
the old, buggy scanner, meaning **neither ever received the narrow-context human review**
the other 11 pattern-flagged candidates got -- this correction closes that gap, not just the
scanner bug itself.

Narrow-context review of both (short window around the match only, PII value never recorded
in any committed file, per this document's own standing rule):

- `350d07e8bd188f6f`: a corresponding-author institutional academic email (`*.wur.nl`,
  Wageningen University) on a multi-author scientific paper -- the same
  `cleared_institutional_contact` category as candidate `c3f9be7e2df0fbe7` above.
- `9660aec276b37865`: two university-research-institute staff bylines (director and
  research assistant, named with job titles, `*.bahcesehir.edu.tr`) in what is clearly a
  circulated professional economics report -- the same institutional-byline category as the
  "several academic-authorship byline emails" already cleared elsewhere in this document.

**Result: both cleared as institutional contact info.** The headline count is unchanged --
still 35 of 36 cleared -- but for the right reason now: every candidate has actually been
reviewed, not accidentally waved through by a scanner bug. `manifests/
s6-organic-candidates-adjudication-v1.json`'s two affected records have been updated in
place (`pii_scan` and `adjudication` fields) to reflect this re-review; the summary counts
in that file are unchanged.
