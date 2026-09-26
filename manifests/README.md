# Re-run document-selection manifests (S25 respec_cascade, S26 K=4 section-reorder)

These files are the document-selection inputs for the two drafted re-runs
(`docs/paper-s25-respec-cascade-rerun-protocol-v1.md`,
`docs/paper-s26-k4-section-reorder-confirmatory-protocol-v1.md`). They were first
produced on 2026-09-25 in a session scratchpad and moved here unchanged.

**Content policy.** JSON only: identifiers, file hashes, local paths, sizes, counts,
docx-corpus metadata (type/topic/language/word count) and resolver/scanner verdicts.
No document text (no heading text, no snippets) and no documents. Author-owned
documents are not listed here.

**Status.** Candidate pools and review orders only. Nothing here is a locked corpus,
and no document has been content-reviewed for either study. Pending author decisions,
left open on purpose:

- S25 document count D: `<PENDING: default 12>`
- S26 document count N: `<PENDING: default 120>`
- Meridian Docs pin: `<PENDING: default 89c93fac>`. Every resolver-derived file below
  was computed with the **unpinned** editable install from
  `C:\Users\13144\Documents\Meridian\repository` at b0d28a61 (working tree). Re-run the
  resolver steps at the chosen pin before the protocols lock.
- The seeds (S25 20260925002, S26 proposed 20260925001) are the protocol drafts' values
  and are fixed only when the protocols lock.

## How to regenerate

Run from the repo root. `python` is enough for the stdlib steps; the resolver steps
import `meridian_docs` and need `pixi run python`. Set `PYTHONDONTWRITEBYTECODE=1`.
Machine-specific locations are arguments: `--data-root` (default
`D:\MeridianData\ooxml-graph-paper`) and `--meridian-repo` (default
`C:\Users\13144\Documents\Meridian\repository`). All JSON is written with CRLF line
endings on every OS, so re-runs are byte-comparable.

| Step | Command | Output |
|---|---|---|
| 1 | `python tools/rerun_pool_exclusion.py index` | `docx_corpus_pool_index.json` |
| 2 | `python tools/rerun_pool_exclusion.py scan --target data` | `exclusion_hits_data_root.json` |
| 3 | `python tools/rerun_pool_exclusion.py scan --target repo` | `exclusion_hits_repo.json` |
| 4 | `python tools/rerun_pool_exclusion.py union` | `touched_union.json` |
| 5 | `pixi run python tools/scan_fresh_docx_pool.py` | `fresh_pool_structure_pii_scan.json` |
| 6 | `pixi run python tools/respec_eligibility.py fresh` | `fresh_pool_respec_eligibility.json` |
| 7 | `pixi run python tools/respec_eligibility.py organic` | `organic_respec_eligibility.json` |
| 8 | `python tools/build_rerun_candidates.py k4sr --generated-at 2026-09-25T19:19:11+00:00 --paper-commit e1d4046` | `k4sr_candidates.json` |
| 9 | `python tools/build_rerun_candidates.py respec` | `respec_public_candidates.json` |
| 10 | `python tools/select_rerun_documents.py respec-queue --seed 20260925002` | `respec_public_review_queue.json` |

S26 review order (not saved; the seed is set at lock):
`python tools/select_rerun_documents.py k4sr --seed <locked seed> [--out PATH]`.
`tools/docx_ngram_overlap.py` computes the 12-gram near-duplicate measure used for the
author-document analysis and the protocols' near-duplicate skip rule. Its author-document
outputs stay outside the repo.

## Files

| File | What it is | sha256 |
|---|---|---|
| `docx_corpus_pool_index.json` | All 6,523 `.docx` under `raw/docx-corpus/{batch-500-v1,batch-2-v1,batch-3-v1,files}`: docx-corpus id (the file name), batch, path, file sha256, size. `touched_union.json`'s `fresh_indices` index into this list. | `0fc1d6207384eaaba9e1804caf850117757c1d548687be3e6e645c59f7545360` |
| `exclusion_hits_data_root.json` | Every file under the data root (18,379 text files scanned; DocBank, ReadingBank, model-cache and the pool `.docx` directories skipped) whose content or name contains a >=12-hex-char prefix of a pool document's id or sha256, with the matched pool indices. | `6b86083762abc5a5267cc8404c2008ea6a66d031ff7b8374583645760572925e` |
| `exclusion_hits_repo.json` | The same scan over this repo's working tree (189 text files at the time; `manifests/` is skipped on re-runs because it lists every pool document). | `a888537823624b904d89376540870cc6de4092621f4f87c208640f6ed8bc3600` |
| `touched_union.json` | The 175 touched pool documents (all 90 of `files/`, plus 85 batch documents: the 48 v2 follow-up, the 36 S6 organic and 7999bbea) with up to 50 referencing files each, the seven pool-wide listings not counted as use, and the 6,348 fresh indices. | `0c6e0e9ce3a3010f6c53b34f9056fd7b9d2a9fe07f61d641b07abcf6397b7434` |
| `fresh_pool_structure_pii_scan.json` | For each of the 6,348 fresh documents: outline heading count, `resolve_section_reorder_plan` verdict (reason; `section_id` and `heading_count` when found) and the `pii_pattern_scan` verdict and counts. | `062c7a3c44a0dbb4404cb6c052e975e941bdc5c3cea2ce2aec2bcec024b17dd4` |
| `fresh_pool_respec_eligibility.json` | Respec eligibility summary (paragraph/heading/oMath/table counts, anchor pool sizes, five- and six-family usable anchor-set counts) for the 772 fresh plan-found, PII-pattern-clean documents. | `795a91d8affe0ceae895bbbe403d73aafac21bc2f185d704e31e45eb1ba6c711` |
| `organic_respec_eligibility.json` | The same summary for the 36 S6 organic-OMML adjudicated candidates, with their adjudication, PII-scan flag and licence status. | `5ecc74e4dc43e91c7d0e9c34a2698c196f14f5da2a94ffe9b3f6112fad6b7618` |
| `k4sr_candidates.json` | **S26 pool.** 676 fresh documents with a plan, a clean PII pattern scan and 3-25 plan headings, sorted by sha256, with source URL, corpus metadata, respec anchor-set counts and rank under the proposed seed 20260925001. Includes the funnel (6,433 -> 85 touched -> 6,348 -> 1,252 >=3 headings -> 1,164 plan -> 772 PII-clean -> 676 in band). | `4e33aaecff599ba088d857e180a0e3eba30acb70f7868d60dc108061cb80abe4` |
| `respec_public_candidates.json` | **S25 public pool.** 98 documents: 7 cleared S6 organic candidates with >=1 anchor-set, and 91 fresh documents with >25 outline headings (outside the K=4 band, so disjoint from `k4sr_candidates.json`) and >=1 anchor-set. | `846595846998aec4fb8b05a4364725c818c0c35e69e6ef88fae212e01c142b6d` |
| `respec_public_review_queue.json` | **S25 review order.** The 78 candidates with all 4 six-family anchor-sets, ranked by `sha256(f"{seed}:{doc_sha256}")` with seed 20260925002. | `6b4094aa6047cb814adbe1afdc645eedc98a0304165e398f77dc64119028e4d1` |

## Reproduction check (2026-09-25)

Each step was re-run from these tools against the same data root, resolver build
(b0d28a61) and repo HEAD (e1d4046):

- Byte-identical to the saved scratchpad output: steps 1, 2, 4, 8, 9 and 10, including
  both candidate pools (the sha256 values the protocol drafts cite).
- Step 3 gives the same hits for every file (so the same touched set; step 4 on the
  re-run output is byte-identical), but `text_files_scanned` is 202 rather than 189
  because the working tree has gained files since. The saved 189 version is kept here.
- Steps 5-7 are byte-identical to the saved scratchpad output after that output is
  reduced to the persisted format. The persisted format drops heading text (the scan's
  `section_heading_text`/`destination_heading_text`, and the organic file's per-set
  `anchor_sets`) and per-document timing (`seconds`). Step 8 reads only `section_id` and
  `heading_count`, so it is unaffected.
- `REPRODUCTION_CHECK_ALL_BATCH_DOCS` in `tools/build_rerun_candidates.py`
  (1,310 / 883 over all 6,433 batch documents) is a recorded constant, not a scan output.
  It was re-verified from the saved fresh and touched-document scans.

Caveats for later re-runs:

- Step 8 records `git rev-parse --short=7 HEAD` of this repo unless `--paper-commit` is
  given.
- Step 3 flags any pool document that repo text names by id or sha256 prefix. Once
  selected documents are named in docs, a re-scan will mark them touched. The saved
  `touched_union.json` is the pre-selection record.
- Steps 5-7 depend on the installed Meridian Docs build.
