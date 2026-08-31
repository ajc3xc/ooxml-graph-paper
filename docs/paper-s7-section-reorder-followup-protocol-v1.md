# PAPER-S7 section_reorder follow-up: preregistration (v1)

Status: **preregistration lock**, declared 2026-08-31 BEFORE running any trial against this
corpus or looking at any outcome data from it. Written in direct response to
`docs/paper-s7-protocol-v1.md`'s own explicit deferral ("whether... a larger corpus should
be added is future work, tracked separately," section 9) -- this document is that separately
tracked follow-up, not an amendment to the locked v1 protocol or its corpus.

## Why this exists

`docs/paper-s7-protocol-v1.md`'s locked 38-document corpus yields only 11 validation+holdout
documents applicable to `section_reorder` (>=3 real headings), giving a K=1 paired result of
control 72.7% (8/11) vs treatment 100% (11/11), p=0.2395 -- directionally favoring treatment
but underpowered at n=11. The v1 corpus is explicitly locked to prevent exactly the kind of
post-hoc expansion that would look like chasing significance after a disappointing result.
The honest, non-p-hacking way to add real power is a genuinely new, separately preregistered
corpus and confirmatory pass -- declared here, before any trial runs against it -- not a
quiet edit to the locked v1 manifest.

## Corpus (locked as of this document)

`manifests/paper-s7-corpus-manifest-v2-section-reorder-followup.json`, 48 real documents,
independently sourced from the same `docx-corpus` remote pool PAPER-S6's organic-OMML
acquisition already used (batches 500/2/3, already downloaded to local disk from prior
acquisition rounds -- no new fetching for this follow-up).

Provenance chain, fully reproducible:

1. **Structural eligibility scan**: all 6,433 already-downloaded documents scanned via
   `docx_anchor_prober.resolve_section_reorder_plan` (the same function the harness itself
   uses to gate `section_reorder` applicability) for >=3 real `w:pStyle`-tagged headings.
   1,310 qualify.
2. **PII pattern scan**: `tools/pii_pattern_scan.py` (post the 2026-08-31 false-negative fix
   -- paragraph-aware text join, headers/footers/footnotes/endnotes now covered) over all
   1,310. 883 clean.
3. **Random reproducible sample**: 90 candidates drawn from the clean pool restricted to a
   realistic heading-count band (3-25; documents outside this band are excluded as likely
   reference/index artifacts, not genuine short business-report sections), seed `20260831002`.
   The first 55 were content-reviewed (see next step); the remaining 35 are an unused reserve
   if a second review batch is ever needed.
4. **Content review**: 55 candidates, each independently assessed by two agent reviewers for
   (a) free-text personal PII a regex cannot catch, and (b) content quality/suitability for a
   realistic "move one section" editing task. 48/55 promotable; 0 rejected for PII, 7 for
   content quality (bare indices, blank policy templates, synthetic test-fixture data).
5. **Split**: all 48 promotable documents, seed `20260831003`, 10 assigned `validation`
   (a sanity-check slice only -- this follow-up reuses the v1 harness's already-validated
   `section_reorder` broker/evaluator code unchanged, so there is no harness logic left to
   debug against this slice; it exists purely to catch corpus-specific OOXML surprises this
   real-world pool might contain that the curated DocOps v1 corpus didn't, before spending on
   the full holdout run), 38 assigned `primary_holdout` (the confirmatory measurement).

No document from the locked v1 corpus appears in this manifest, and no document from this
manifest will ever be added to the v1 corpus manifest.

## Family, tool matrix, model, statistics (all reused unchanged from v1)

- **Family: `section_reorder` only.** Bibliography and citation are already at 96-100% pass
  rate on both arms in v1 (p=1.0, near-ceiling parity) -- there is no meaningful difference
  left to power up for those families, and running them here would not change that.
- **Tool matrix, trial construction, K=1 only, model (`sonnet`), grading, and statistics
  (`bootstrap_ci` + `paired_permutation_test`, 2000 resamples/permutations, seed `20260828`)**:
  identical to `docs/paper-s7-protocol-v1.md` sections 2-7, unmodified. This follow-up changes
  only the document pool, nothing about how a trial is built, run, or graded.

## Reporting plan (locked)

- This follow-up's own result (n=38 primary_holdout, or n=48 combined with its own validation
  slice) is reported on its own terms as an independent replication, not silently pooled into
  v1's n=11 figure.
- A combined analysis (v1's 11 + this follow-up's up to 48 = up to 59 paired documents) MAY
  additionally be reported, but only with the pooling explicitly disclosed -- the two pools
  come from different source distributions (curated DocOps benchmark tasks vs. real-world
  scraped documents) and that difference must never be hidden.
- If this follow-up's own result does not favor treatment, or is itself not significant, that
  is reported plainly. This document does not commit to any particular outcome.

## Stopping rule (locked)

Primary_holdout (38 documents) is run exactly once per this protocol version, mirroring v1
section 8. A harness defect found during the run halts it, gets fixed and disclosed, and
primary_holdout is re-run in full under the corrected harness.
