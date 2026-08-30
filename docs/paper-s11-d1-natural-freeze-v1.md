# PAPER-S11 INVESTIGATE: screen and freeze the bounded D1 DOCX expansion (v1)

Status: complete, run 2026-08-30. This item individually inspects every raw DOCX candidate
that was not promoted into the frozen 127-document D0 gold corpus, decides promote/reject for
each, and freezes the D1-natural development/validation set. It does not modify D0 and does
not touch the controlled D1 adversarial equation fixtures owned by PAPER-S10 or the MS-thesis
regression fixture.

## Bottom line

- **The candidate pool is 39 raw DOCX files, not 28.** The sprint item's own notes (and the
  pre-existing `docs/native-docx-corpus-candidate-manifest-v1.json`) said 28. An independent,
  from-scratch whole-file SHA-256 diff of every DOCX under `raw/{docx-corpus,omega-officeval,
  docx-benchmark}` against every DOCX under `gold/{tier1,tier2,tier3}` measures **39** (23
  docx-corpus + 16 omega-officeval + 0 docx-benchmark). This is independently confirmed by the
  narrative arithmetic already in `docs/gold-corpus-status-v0.md` (90 docx-corpus raw − 67
  promoted = 23 excluded; 63 omega-officeval raw − 47 promoted = 16 excluded; 2 docx-benchmark
  raw − 2 promoted = 0 excluded; 23+16+0 = 39). The prior "28" figure was stale/incorrect and is
  corrected in the candidate manifest, not silently carried forward.
- **All 39 candidates were inspected individually and all 39 are rejected.** Every one of the
  39 already has a real, specific, human-written PAPER-25 (docx-corpus) or PAPER-22/25
  (omega-officeval) per-file content review on record, and every one of those reviews already
  excluded the file — 38 for containing a real, identifiable individual's personal data (a name
  paired with a national ID number, student ID, phone number, email address, or home/work
  address) and 1 for sensitive child-safeguarding subject matter (a school policy explicitly
  describing categories of child sexual abuse, excluded independent of any PII finding). A
  prior independent privacy/content exclusion is not something this item re-litigates or
  overrides on missing-feature-coverage grounds.
- **None of the 39 would have added missing D0 coverage even if privacy were set aside.** An
  independent structural feature scan (fresh ZIP/XML inspection, not a reuse of the D0 audit
  script) found 0 of 39 candidates contain organic n-ary/matrix/accent/multi-script equations,
  0 contain a tracked deletion (`w:del`), and every table-bearing candidate already has an
  explicit `w:tblGrid` — none of the specific gaps the frozen-D0 audit
  (`docs/native-docx-corpus-expansion-v1.md`) identified are closed by this pool.
- **D1-natural freeze decision: 0 promotions from this pool.** D0 (127 documents) is unchanged.
  A genuine D1-natural expansion needs a fresh acquisition pass with its own privacy screening;
  it cannot be built by re-mining files this project's own prior, independent review already
  rejected for cause.

## Method

1. **Enumerate candidates by evidence, not by trusting the prior count.** Walked every `.docx`
   under `E:\MeridianData\ooxml-graph-paper\raw\{docx-corpus,omega-officeval,docx-benchmark}`
   (155 files) and every `.docx` under `E:\MeridianData\ooxml-graph-paper\gold\{tier1,tier2,
   tier3}` (127 files), computed a whole-file SHA-256 for each, and took the raw hashes with no
   match anywhere in gold as "not promoted." Gold tier2 documents are byte-identical whole-file
   copies of their raw source (independently confirmed by PAPER-S18's preflight and re-confirmed
   here: every one of the 116 tier2 gold hashes matched a raw hash exactly), so this diff is a
   sound, non-fuzzy way to identify the exact not-promoted set. Result: 155 raw, 127 gold, 116
   promoted-from-raw, **39 not promoted**, 11 gold-only (the 8 tier1 + 3 tier3 hand-authored
   fixtures with no raw/ counterpart, as expected). Zero raw-side hash collisions (each raw file
   is unique by content). Script: `s11_identify_unpromoted.py` (copy retained at
   `E:\MeridianData\ooxml-graph-paper\manifests\paper-s11\`).
2. **Recover the existing per-file review reasoning rather than re-reading 39 documents' full
   text from scratch.** Both source pools were already subjected to a genuine, independent,
   full-text, per-file review during PAPER-22/25 (see `docs/gold-corpus-status-v0.md`), with the
   actual reasoning persisted:
   - `raw/docx-corpus/review_results.json` — all 90 docx-corpus candidates, `verdict` +
     `content_summary` + `reasoning` + `contains_real_personal_data` per file. 23 `exclude`
     entries matched 1:1 by dataset id (filename stem) to all 23 docx-corpus files in this
     item's not-promoted set — a complete match, 0 unmatched.
   - `E:\MeridianData\ooxml-graph-paper\gold\manifests\_tier2_review.json` — an `excluded` list
     of 15 entries (one entry covers 2 files that turned out to be the exact same underlying
     "operating-anomaly dossier" filed under 3 different names, so 15 entries = 16 files). All
     16 omega-officeval files in this item's not-promoted set matched 1:1 by folder+filename —
     also a complete match, 0 unmatched.
   - Net: **all 39 candidates have a genuine, specific, already-adjudicated reject reason on
     file.** No candidate was rejected on this item's own unreviewed guess.
3. **Independently re-verify package integrity and structural features for all 39, from
   scratch.** Wrote a new, self-contained ZIP/XML scanner (`s11_scan_candidates.py`, stdlib
   only, no import of any Meridian Docs product module and no import of any existing
   gold-manifest-generation script) that opens each candidate as a zip, checks `zf.testzip()`
   plus presence of `[Content_Types].xml` and `word/document.xml`, parses `word/document.xml`,
   and counts: `w14:paraId` coverage, `m:oMath` containers and the same 8 equation feature
   families used throughout this project (fraction/radical/subscript/superscript/nary/
   matrix_or_array/accent_or_limit/multi_script), tables + explicit-`tblGrid` + `gridSpan` +
   `vMerge`, bookmarks, field/`instrText`, `w:ins`/`w:del` tracked-revision counts,
   header/footer part presence, drawings + floating (`wp:anchor`) anchors, hyperlinks, content
   controls (`w:sdt`), and custom XML parts. Result: **39/39 valid packages, 0 integrity
   failures, 0 SHA-256 mismatches** against step 1's hashes (script and full JSON output
   retained at `E:\MeridianData\ooxml-graph-paper\manifests\paper-s11\`).
4. **Build the merged promote/reject ledger.** `s11_build_ledger.py` joins the hash-diff output,
   the feature scan, and the recovered PAPER-22/25 review reasoning into one 39-row ledger with,
   per candidate: `candidate_id`, `path`, `sha256`, `size_bytes`, `package_integrity_ok`, the
   full `feature_vector`, an explicit `adds_missing_d0_coverage` check against the frozen-D0
   gaps, the matched prior `rationale_note`/`content_summary`/`contains_real_personal_data`, a
   `decision` (all 39 = `reject`), and explicit `not_applicable_not_promoted` /
   `not_run_not_promoted` sentinels for split assignment and Word render receipt (both are
   promotion-gated per `docs/native-docx-corpus-candidate-manifest-v1.json`'s own
   `promotion_requirements`, so neither was attempted for a rejected candidate — this is a
   stated policy consequence, not a skipped step). Full ledger:
   `E:\MeridianData\ooxml-graph-paper\manifests\paper-s11\s11_d1_natural_ledger.json`.

All three scripts and their JSON outputs are retained on the local E: data root, per this
project's storage policy, alongside their own SHA-256 (recorded below) for provenance.

| Artifact | SHA-256 |
|---|---|
| `s11_identify_unpromoted.py` | `a8dfc2e94ffa618b8cce1a9e80fdf349936d48300197888010f52ea194dc1c75` |
| `s11_scan_candidates.py` | `bb77e2412427ef1d285f0cc5403b583fa6b58f687e2e0090a51ad8ff513c7b78` |
| `s11_build_ledger.py` | `30a786b8ad4f664af833bd452384976a944797b0a258f66dc986c98e946cae9a` |
| `s11_d1_natural_ledger.json` | `4680a5b6e796cd34e74966c1c25f9fa6525fe3800c2ead56e05bbb4c8ae19fdf` |

## Structural feature scan results (all 39 candidates)

| Feature | Candidates with feature (of 39) |
|---|---:|
| `w14:paraId` present | 28 |
| Native `m:oMath` | 0 |
| Tables | 33 |
| `w:gridSpan` | 18 |
| `w:vMerge` | 7 |
| Tables missing explicit `w:tblGrid` | 0 (of the 33 table-bearing candidates, all had explicit `tblGrid`) |
| Bookmarks | 32 |
| Field/`instrText` | 10 |
| `w:ins` (tracked insertion) | 0 |
| `w:del` (tracked deletion) | 0 |
| Headers/footers | 29 |
| Drawings | 23 |
| Floating anchors | 13 |
| Hyperlinks | 10 |
| Content controls (`w:sdt`) | 5 |
| Custom XML | 24 |

The three feature families the frozen-D0 audit flagged as genuinely missing or thin —
organic n-ary/matrix/accent/multi-script equations, tracked deletions, and tables without
`tblGrid` — are **all still at 0** across this entire 39-file candidate pool. This pool cannot
close those gaps regardless of the privacy outcome.

## Reject reason breakdown (all 39)

| Reason | Count |
|---|---:|
| Real personal data: full name + national ID / student ID / phone / email / address (docx-corpus, PAPER-25 review) | 22 |
| Sensitive child-safeguarding subject matter (child sexual abuse policy content), no PII finding (docx-corpus, PAPER-25 review) | 1 |
| Real personal data: full name + student ID / national ID / phone (omega-officeval, PAPER-22/25 review) | 16 |

Representative examples (full reasoning for every file is in the ledger):

- **`b0cb08aded6a2bf...docx`** (docx-corpus): a Utah DOT quarterly progress report whose body
  reads `Name of Project Manager(s): Daniel Page / Phone Number: 801-965-4120 / E-Mail
  dpage@utah.gov` — full name plus phone plus email, the project's standing exclusion trigger.
- **`e273ff481ad4f31...docx`** (omega-officeval, `officeval_028/职称评审表.docx`): a filled
  professional-title review form with a real-format 18-digit national ID number tied to a named
  applicant, plus birth date, birthplace, employer, and 7 additional named witnesses — the most
  identifying single document in this pool.
- **`29806867a857ce1...docx`** (docx-corpus): a UK primary-school safeguarding policy template
  with every school-specific field left as an unfilled placeholder (no PII at all), excluded
  instead for extensively and explicitly defining child sexual abuse/behaviour categories —
  correctly excluded on subject-matter grounds independent of the PII rule.
- Three separate filenames across `officeval_001`, `officeval_015`, and `officeval_022` turned
  out, on the original PAPER-25 review, to be **the same underlying document** (a corporate
  "operating-anomaly dossier" containing `呈报人：顾启朝...联系电话：188278632124586`) filed three
  times under unrelated names — a real cross-folder content-reuse pattern in this dataset, not
  three independent documents.

## Decision

**D1-natural freeze: 0 promotions.** D0 remains exactly 127 documents, unmodified. Every one of
the 39 raw candidates not currently in D0 has a genuine, specific, already-adjudicated reason it
should stay out, and none would have closed a real D0 coverage gap even if that reason were set
aside. This item does not fabricate a promotion to hit a quota, and does not re-open a privacy
exclusion another independent review already made for cause — per this item's own instruction
("select only natural DOCX files that add missing coverage; do not fill a target quota") and the
project's standing rule against relaxing a privacy exclusion on this session's own judgment.

Consequently: **a genuine D1-natural corpus does not yet exist and cannot be built from this
specific candidate pool.** Building one requires a fresh acquisition pass (new source, new raw
files, new independent per-file privacy/content review) — out of this item's scope, which is
screening, and one that must land its own real privacy review, not reuse this ledger's "already
rejected" files under a relaxed bar. The controlled D1 *adversarial* equation fixture suite
(n-ary, matrix/array, accents, multi-script, etc.) remains PAPER-S10's separate, hand-authored
track and is unaffected by this freeze.

## What this item did not do

- Did not re-read the full text of all 39 documents from scratch. It located and cross-checked
  the existing, genuine, independent PAPER-22/25 per-file reviews (100% match rate, 0 files
  without a prior recorded reason) rather than duplicating that human-adjudicated work. If any
  reader wants a second, fully independent human re-review of a specific file's PII
  determination, the exact file and the prior reasoning are both in the ledger for that purpose.
- Did not attempt a Word render receipt or a document-level split assignment for any of the 39,
  since both are promotion-gated per this project's own `promotion_requirements` and 0 files
  were promoted. Recorded explicitly as `not_run_not_promoted` / `not_applicable_not_promoted`
  in the ledger, not left blank.
- Did not modify, move, or delete any file under `raw/` or `gold/`. This was a read-only
  screening pass.
