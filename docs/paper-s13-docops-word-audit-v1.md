# PAPER-S13: DocOps native-Word task/verifier subset -- acquisition and audit (v1)

Status: investigation complete. Real, staged, licensed corpus audited end-to-end by direct
inspection (not filenames, not the sprint item's own prior summary taken on faith). One count
in the prior sprint-item note is corrected here with evidence (38 -> 42, see "Corrected count"
below); one genuine execution blocker is recorded (verifier harness dependency gap); no task was
executed through the DocOps Harbor Docker pipeline (out of scope for a static audit -- see
"What was not done").

## 0. What is staged, and where

`E:\MeridianData\ooxml-graph-paper\external\docops-source` is a real git checkout of
`https://github.com/icip-cas/DocOps.git`, HEAD commit `ccf7a751bc5c8a69c1cdd0400125d53455b33be3`
(verified via `git rev-parse HEAD` and `git remote get-url origin` inside that checkout, not
assumed from directory naming). It is the official DocOps benchmark release: 210 Harbor task
directories under `tasks/`, Apache-2.0 licensed (`LICENSE`, sha256
`c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`), described in its `README.md`
as accompanying arXiv:2607.19865 ("DocOps: A Verifiable Benchmark for Autonomous Agents in Complex
Document Operations", Jiang et al. 2026), project page `docopsbench.github.io`.

Every task directory follows the Harbor format: `task.toml` (schema_version 1.1, metadata +
environment + verifier config), `instruction.md`, `environment/` (Dockerfile, input document(s),
`task_metadata.json`, `original_task_description.txt`), `tests/` (`test.sh`, `test_outputs.py`,
`verifier_utils.py`, `task_metadata.json`). All 210 `task.toml` files parsed without error
(`tomllib`, Python 3.12.14 via this project's pixi env).

All audit outputs referenced below are written to
`E:\MeridianData\ooxml-graph-paper\manifests\docops\` as machine-readable JSON, produced by
`tools`-equivalent scripts run from this session (scripts themselves are in the session scratchpad,
not checked into the paper repo -- see "Reproducibility" at the end for exact recreation steps):

- `docops_all_task_records.json` -- all 210 tasks, full parsed metadata + classification + hashes
- `docops_pure_word_manifest.json` -- the 42-task eligible manifest (authoritative; see below)
- `docops_pure_word_manifest_strict38.json` -- the narrower 38-task alternate (for traceability)
- `docops_excluded_word_like_ledger.json` -- 29 Word-adjacent tasks excluded, with reasons
- `docops_audit_summary.json` -- the summary counts reproduced in this document
- `docops_skill_bundle_hashes.json` -- sha256 of every file in `skills/doc/`
- `docops_pii_scan.json` -- pattern-based PII screen results over all 42 tasks' input `.docx` files
- `docops_prereg_split_v1.json` -- the preregistered development/smoke/scale-up/final-holdout split

## 1. Inclusion methodology, and a corrected count

The prior sprint-item note (written before this investigation) stated: "A metadata audit found
38 pure Word tasks with task.toml metadata `doc_type="word"`... The 38 pure Word tasks break down
as 12 atomic L1, 10 same-type composite L2, 5 single-document workflow L3, 5 cross-document Word
workflow L4, and 6 docops_v2 L3 Word tasks."

**That 38-task, literal-string count is reproduced exactly** by filtering `metadata.doc_type ==
"word"` (case-insensitive, exact match) across all 210 `task.toml` files: 12 + 10 + 5 + 5 + 6 = 38,
matching the prior note's own breakdown digit-for-digit. This confirms the prior note was not
fabricated -- it is a real, reproducible count under that specific filter.

**However, that filter is not the correct inclusion rule**, and the sprint item's own instruction
says so: "Use task.toml metadata, primary modality, explicit input/output paths, and test verifier
behavior as the inclusion authority" (plural signals, not `doc_type` alone). Direct inspection
found that DocOps tags **semantically identical single-Word-document tasks with two different
literal `doc_type` strings**: `"word"` (38 tasks) and `"docx"` (4 tasks: `docops_v2_l3_001`
through `docops_v2_l3_004`). Both groups have:

- `primary_modality` naming only Word (`"Word (.docx)"` or `"Word document (.docx)"`)
- every `*_PATH` environment variable referencing only `.docx`
- the same benchmark family and immediately-adjacent numbering (`docops_v2_l3_001`..`010`, where
  `001`-`004` say `doc_type="docx"` and `005`-`010` say `doc_type="word"` -- same task author, same
  batch, no substantive difference in modality)

There is no principled reason under the item's own multi-signal inclusion rule to exclude
`docops_v2_l3_001`..`004`. **The corrected, authoritative pure-Word manifest has 42 tasks, not
38.** Both are preserved on disk (`docops_pure_word_manifest.json` = 42;
`docops_pure_word_manifest_strict38.json` = 38 subset) so downstream consumers can pick either,
but 42 is what this audit recommends and what the preregistered split (`docops_prereg_split_v1.json`)
is built from.

Classification logic, applied per task (not per filename):
1. `doc_type` (from `[metadata]`) must equal exactly `"word"` or `"docx"` -- not a substring match
   against `primary_modality` (an earlier draft of this classifier used `"word" in primary_modality`
   and wrongly included 21 multi-format L4 tasks, e.g. `docops_v2_l4_066_word_xlsx_...` whose
   `primary_modality` reads `"Word (.docx) and Excel (.xlsx)"` -- corrected before this manifest
   was finalized).
2. `doc_type` must not contain `"+"` (DocOps' own convention for declaring a mixed-format task,
   e.g. `"word+xlsx"`, `"pdf+docx+xlsx"`).
3. `primary_modality` must not name another format (excel/xlsx/pdf/ppt/pptx/powerpoint/spreadsheet).
4. Every `*_PATH` environment variable must reference only Word-family extensions (`.docx`/`.doc`)
   or a non-document verifier-answer artifact (see point 5) -- never a competing document format
   (`.xlsx`, `.pdf`, `.pptx`, etc.).
5. **`.txt` output paths are not treated as disqualifying.** `OUTPUT_PATH=/root/submission/final_answer.txt`
   is DocOps' standard verifier-answer convention for extraction/reasoning-class atomic tasks
   **across every format family**, confirmed identical on `atomic__excel_007_exception_credit_extraction_seed`
   (`.xlsx` input, `.txt` output) and on the two Word tasks that use it
   (`atomic__word_005_meeting_minutes_extraction_seed`, `atomic__word_008_policy_conflict_reasoning_seed`).
   It is not a second input/output document type, so it does not make an otherwise-pure-Word task
   "mixed." Both are correctly counted in the 42.

### 42-task manifest by difficulty tier

| Tier | Count | Task-name family |
|---|---:|---|
| L1-atomic | 12 | `atomic__word_001`..`012` |
| L2-composite | 10 | `composite_same_type__wordc_001`..`010` |
| L3-single-document-workflow | 14 | `single_doc_workflow__wordwf_001`..`005` (5) + `docops_v2_l3_001`..`004`,`006`..`010` (9) |
| L3-single-document-long-flow | 1 | `docops_v2_l3_009_docx_incident_manual_publication` |
| L4-cross-document | 5 | `cross_doc_docops__wordxr_001`..`005` |
| **Total** | **42** | |

### 29-task excluded ledger (Word-adjacent, correctly excluded)

Every task where `doc_type` or `primary_modality` mentions Word but the task is genuinely
mixed-format. Full reasons in `docops_excluded_word_like_ledger.json`; by declared `doc_type`:

| doc_type value | count | reason |
|---|---:|---|
| `word+xlsx` | 14 | Word + Excel cross-document workflow (L4) |
| `pdf+word`, `word+pdf` | 4 | Word + PDF cross-document workflow (L4) |
| `word+ppt` | 1 | Word + PowerPoint cross-document workflow (L4) |
| `docx+pdf+xlsx`, `pdf+docx+xlsx`, `pdf+xlsx+docx` | 5 | three-way mixed, Word is one of three formats |
| `ppt+docx` | 1 | Word + PowerPoint cross-document workflow (L4) |
| `pptx+xlsx` (Word named only in `primary_modality` text, not `doc_type`) | 2 | mixed, non-Word `doc_type` but modality text mentions Word incidentally |
| `pdf+xlsx` (same) | 2 | mixed, non-Word `doc_type`, modality mentions Word incidentally |

This matches, and is more complete than, the prior note's partial enumeration ("14 word+xlsx, 2
word+pdf, 1 word+ppt" = 17 of the 29 -- the note's own closing clause, "and other mixed/pure
non-Word tasks are not part of the pure DOCX track," already flagged that its list was not
exhaustive).

## 2. License, provenance, and PII audit

**License**: DocOps repository is Apache-2.0 (`LICENSE`, sha256 above). The bundled `skills/doc/`
directory (the Word-editing skill referenced by this item) carries its own
`skills/doc/LICENSE.txt` (sha256 `4dd13869245e356246a5b770723247bbb80a8f07a181d1d3d873a1734297cdb9`),
consistent with the README's "third-party components and bundled skills retain their own license
notices" statement. No license conflict found for the 42-task Word subset or the skill bundle.

**Provenance / source_type** (from `task.toml` `[metadata].source_type`, 42-task manifest):

| source_type | count | tasks |
|---|---:|---|
| Reddit-derived representative benchmark seed | 12 | `atomic__word_001`..`012` |
| Composite same-type benchmark seed | 10 | `wordc_001`..`010` |
| Single-document workflow V1 | 5 | `wordwf_001`..`005` |
| DocOps v2 final L3 dataset | 10 | `docops_v2_l3_001`..`004`,`006`..`010` |
| Cross-document document-ops V7 realworld | 3 | 3 of the 5 `wordxr` tasks |
| Cross-document skill-gap V2 | 2 | remaining 2 `wordxr` tasks |

The "Reddit-derived" tasks are not scraped user posts verbatim: each task's
`environment/original_task_description.txt` names the inspiring Reddit thread(s) (public r/word
posts about generic formatting problems -- headings, TOC, letter tone) and then states a
synthetic "User Task Description" describing a fictional document the benchmark author wrote for
the task. Spot-checked 3 of the 12 directly (`atomic__word_001`, `_003`, `_005`); the actual
`.docx` bodies contain clearly fictional content (e.g. a letter addressed to "Meridian Retail"
about a "refrigeration retrofit package" -- a placeholder business scenario, not a real
correspondence).

**PII pattern scan** (`tools`-equivalent script, `docops_pii_scan.json`): all 46 input `.docx`
files across the 42 pure-Word tasks (some tasks bundle more than one Word document) were unzipped
and their `word/document.xml` visible text scanned for email addresses, US-format phone numbers,
SSN-pattern digit groups, and long digit runs (potential card numbers).

- 0 SSN-pattern matches, 0 phone-pattern matches, across all 46 files.
- 19 email-like strings found, in 5 files (`atomic__word_001`, `docops_v2_l3_005`..`008`) --
  **every one uses a reserved documentation domain**: `@example.com` or `@example.test`
  (RFC 2606), e.g. `retrofit-core@example.com`, `maya.chen@example.test`. These are synthetic
  placeholders, not real addresses.
- 1 file (`single_doc_workflow__wordwf_005`) triggered the long-digit-run heuristic; manually
  inspected the matched text and it is a budget table (`45000 52000 97000`, adjacent numeric table
  cells the regex over-matched, not a real numeric identifier).

**Finding: no PII observed in the 42-task pure-Word subset** under this pattern-based screen. This
is a bounded, reproducible regex pass over 46 files' extracted text, not a substitute for a legal
or manual per-document review -- it would not catch PII expressed as prose (a real name embedded
in an otherwise-fictional sentence, for instance), only structured patterns. No such structured PII
was found, and every scraped placeholder used a domain reserved by RFC 2606 for documentation
purposes, consistent with a deliberately-synthesized benchmark rather than repurposed real
correspondence.

## 3. Task taxonomy

**Verifier strictness** (`[metadata].verifier_mode`, 42-task manifest):

| verifier_mode | count |
|---|---:|
| semantic-strict | 32 |
| semantic-structural-copyedit-style-strict | 3 |
| semantic-structural-strict | 4 |
| semantic-structural-xml-metadata-style-strict | 1 |
| semantic-strict-one-to-one | 2 |

**Output kind** (derived from `OUTPUT_PATH` extension): 40 of 42 tasks are `docx_roundtrip`
(edited `.docx` submitted back); 2 are `derived_text_answer` (`final_answer.txt` --
`atomic__word_005`, `atomic__word_008`, both extraction/reasoning atomic tasks, per point 5 of the
methodology above).

**Structural content, scanned directly from each task's input `.docx` package** (zip + XML
inspection, no Word dependency; per-task detail in `docops_pure_word_manifest.json`'s
`docx_input_files[].structural_scan`): every one of the 46 input files opened as a valid zip with
a `word/document.xml` part. Aggregate presence across the 46 files: tables present in several
(`<w:tbl>` count > 0), no native OMML equations found in any of the 46 (`<m:oMath` absent
throughout -- consistent with this project's other findings that organic OMML is essentially
absent from real-world/benchmark DOCX corpora), bookmarks and fields present in a minority,
footnotes/endnotes and comments largely absent. This is a task-input audit, not a task-output
audit -- what the *edited* document should contain is defined by each task's verifier, not by the
seed's own structure.

## 4. Inverse-suitability labels (heuristic, human-auditable)

**Protocol finding restated and reconfirmed**: DocOps does not provide DELEGATE-52-style paired
forward/backward prompts. Every task in the release (not just the Word subset) is a one-way
"reach this final state" instruction plus a deterministic artifact-level verifier
(`tests/test_outputs.py`, using `python-docx`/`openpyxl`/`pptx`/`pypdf` assertions against the
submitted file, run via `pytest` inside `tests/test.sh`). There is no mechanism in DocOps itself
for treating an edit as reversible or for generating its semantic inverse. Any reversibility
claim about a DocOps task is this project's own downstream construction (per DELEGATE-52's
relay/reversible-edit design), not something inherited from DocOps -- restating the same caution
the prior note already recorded, now with the verifier source code confirmed by direct reading
(`tests/test_outputs.py`, `tests/verifier_utils.py`) rather than inferred from `instruction.md` text
alone.

A heuristic, keyword-driven inverse-suitability label was computed per task from its
`atomic_operation(s)` and `keywords` fields (rules and rationale strings in the audit script;
full per-task output in `docops_pure_word_manifest.json`'s `inverse_suitability` field). This is a
**starting point for future manual review, not a validated ground truth** -- distribution across
the 42 tasks:

| label | count | meaning |
|---|---:|---|
| not-reversible | 21 | operation is lossy or generative (delete, extract, generate, insert, reasoning) with no artifact-only inverse |
| ambiguous | 14 | free-form editing/copyedit; reversibility depends on whether a pre-edit diff is retained out-of-band |
| partially-reversible | 4 | theme/style/hierarchy/table changes, invertible only if original state is retained as ground truth |
| reversible | 3 | pure reorder or additive-highlight operations with a well-defined structural inverse |

## 5. Skill bundle (frozen)

The bundled Word skill (`skills/doc/`, referenced by the prior note as "the standard-skill
baseline candidate") was hashed file-by-file before any run, per the item's requirement to freeze
it. 6 files, sha256 in `docops_skill_bundle_hashes.json`:

| file | sha256 |
|---|---|
| `skills/doc/LICENSE.txt` | `4dd13869245e356246a5b770723247bbb80a8f07a181d1d3d873a1734297cdb9` |
| `skills/doc/SKILL.md` | `0a635585817d1ac96e8e512114d08258b70f9e54ce0052078a258291ac13a8ed` |
| `skills/doc/agents/openai.yaml` | `b77d452b23dfa0bef7788728317254f07bddcd5f2be1d6678d5c3cf754b833ae` |
| `skills/doc/assets/doc-small.svg` | `bd5415fbbfe72c66c1527411d61625731fdd2f75b25d1542510b6ddef699ebe0` |
| `skills/doc/assets/doc.png` | `7eadf1088e5062f681dba6596173a1df13bbfbcddd8a8a9bb78fd2071947dcf8` |
| `skills/doc/scripts/render_docx.py` | `52b3c3158913ebcad2ada7b8193970b70453239e255054aa2d60c1683af08751` |

Per README and `SKILL.md`, this is a generic `python-docx` + `soffice`/`pdftoppm`/`render_docx.py`
render-review-cleanup workflow, matching the prior note's characterization. It is preserved here
as a baseline-comparison candidate; using it in a Meridian-vs-baseline comparison is future work,
not part of this audit.

## 6. Verifier compatibility -- structurally intact, but a real local-execution blocker found

**Structural presence**: all 42 pure-Word tasks have a complete `tests/` directory --
`test.sh`, `test_outputs.py`, `verifier_utils.py`, `task_metadata.json` all present, 42/42, zero
missing. `test_outputs.py` sha256-hashed per task in `docops_all_task_records.json` for future
drift detection.

**One full implementation read end-to-end** (`atomic__word_001_engineering_report_toc_hierarchy_seed`):
`tests/test.sh` runs `pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py`, writes a
`reward.txt` of `1`/`0` from the pytest exit code. `test_outputs.py` opens the submitted `.docx`
with `python-docx`, asserts on specific paragraph text and style-signature equality (e.g. that
four heading levels share a consistent style). This is a genuine, deterministic, artifact-level
check with no dependency on an LLM judge or on Word itself -- confirms the prior note's
"deterministic artifact-level verifiers" characterization by reading the actual code, not by
trusting the README's claim.

**Genuine blocker found and recorded (not silently worked around)**: `tests/verifier_utils.py` --
the shared verifier-support module used by every task family, including the pure-Word ones --
does an unconditional top-level `import pdfplumber` and `import pypdf`. Attempting to import this
module in this project's current pixi environment fails:

```
ModuleNotFoundError: No module named 'pdfplumber'
```

verified directly (`pixi run python -c "import sys; sys.path.insert(0, '<task>/tests'); import
verifier_utils"` from this paper repo). `pytest`, `python-docx`, `openpyxl`, and `python-pptx` are
already present in this project's pixi env and import cleanly; only `pdfplumber` and `pypdf` (both
PDF-only libraries, irrelevant to every Word task's actual assertions) are missing. **Consequence**:
none of the 42 Word verifiers can currently be executed standalone (outside DocOps' own Harbor
Docker image) in this paper's environment without first adding `pdfplumber` and `pypdf` to
`pixi.toml` -- a one-line-per-package dependency addition, not attempted in this item because
modifying the shared environment/dependency file was judged out of scope for a read-only
investigation, and because doing so is better bundled with whichever future item actually wires
up local verifier execution (so the change is tested against a real run, not left speculative).

**What was not done, and why**: no task was executed through DocOps' own Harbor/Docker pipeline
(`docker/`, `third_party/harbor/`) -- that requires building or loading the release's Docker base
images and running the full agent-vs-verifier loop per task, which is a materially larger
undertaking than a static audit and is properly scoped to whichever future item actually runs the
benchmark (e.g. a PAPER-S17/S20-family execution item), not this INVESTIGATE item. No verifier was
executed locally end-to-end either, because of the `pdfplumber`/`pypdf` gap above -- fixing the gap
and running one verifier for real is a natural next step, explicitly flagged rather than silently
deferred.

## 7. Preregistered development / smoke / scale-up / final-holdout split

Full split in `docops_prereg_split_v1.json`. Follows the same staged-disclosure philosophy as
`docs/benchmark-preregistration-v0.md` §3 (smoke -> scale-up -> final; fixed drafting-date seed;
split by whole unit; final slice never touched during development), extended with an explicit
**development** stage before smoke -- unlike that document's already-built internal extractor,
DocOps is a brand-new third-party harness integration (parsing `task.toml`, wiring the Harbor
verifier contract, adapting I/O paths) that needs a freely-inspectable sandbox before even a smoke
test is meaningful.

- **Seed: `20260830`** (this document's drafting date -- fixed before any DocOps Word task was run
  through this paper's pipeline, not tuned after seeing a result).
- **Split unit**: the whole task directory (never a sub-file), matching
  `comparator-contract-v0.md` §4's "split by document, never by page."
- **Procedure, per difficulty tier** (L1-atomic, L2-composite, L3-single-document [workflow +
  long-flow combined], L4-cross-document): `development` and `smoke` are the
  lexicographically-first N task-dir ids of the tier (hand-picked, not seed-dependent -- same
  rationale as the existing smoke-slice convention: guarantee every tier is exercised even in the
  smallest run). The tier's remaining ids are shuffled with `random.Random(20260830).shuffle()`
  and sliced into `scale_up` then `final_holdout` in shuffled order.
- **Counts**: development 9, smoke 4, scale_up 13, final_holdout 16 (total 42).
- **Rules** (recorded in the split file itself, restated here): `final_holdout` is never opened,
  read, or used for debugging the DocOps integration during development -- evaluated exactly once,
  after `scale_up` results are already reported. `development` is the only stage where
  task-specific prompt/pipeline tuning is permitted.

Smoke set (one per tier, for fast integration-breakage detection):
`atomic__word_001_engineering_report_toc_hierarchy_seed`,
`composite_same_type__wordc_001_repair_hierarchy_and_standardize_styles_seed`,
`cross_doc_docops__wordxr_001_publish_minutes_from_agenda_attendance_and_motion_log_seed`,
`docops_v2_l3_001_docx_controlled_document_release_repair`.

## 8. Summary verdict

- Real, licensed, provenance-verified DocOps release staged at
  `E:\MeridianData\ooxml-graph-paper\external\docops-source` (Apache-2.0, HEAD
  `ccf7a751bc5c8a69c1cdd0400125d53455b33be3`, 210 tasks, 0 parse errors).
- **Corrected pure-Word count: 42 tasks** (not 38 -- the 38-task figure is reproduced exactly and
  kept for traceability, but undercounts by 4 tasks that differ from the other 38 only in a
  `doc_type` string spelling, not in modality, I/O, or verifier behavior).
- 29 Word-adjacent tasks correctly excluded with itemized reasons (mixed-format, not pure Word).
- License clear (Apache-2.0, repo + skill bundle both hashed); no PII found in a 46-file
  pattern-based scan of the 42-task subset's input documents (placeholder emails all use RFC
  2606 reserved domains).
- Full taxonomy (difficulty, source_type, verifier_mode, output_kind), heuristic inverse-suitability
  labels, and frozen skill-bundle hashes recorded.
- Verifier harness is structurally complete for all 42 tasks and one implementation was read and
  confirmed genuinely deterministic/artifact-based; **a real, unresolved local-execution blocker**
  (missing `pdfplumber`/`pypdf` in this project's pixi env, required transitively by the shared
  `verifier_utils.py` even for pure-Word tasks) is recorded rather than glossed over.
- A preregistered, seeded, reproducible development/smoke/scale-up/final-holdout split of the
  42-task manifest is committed to `docops_prereg_split_v1.json`.
- **Not done, explicitly**: no task was executed through DocOps' Harbor/Docker pipeline; no
  verifier was executed end-to-end locally (blocked on the dependency gap above); the pixi
  environment itself was not modified by this item.

## Reproducibility

All figures in this document were computed, not estimated, by three scripts run from this paper
repo's pixi environment (`pixi run python <script>.py`) against the staged checkout and manifest
directory named in §0. The scripts are not checked into `tools/` as part of this INVESTIGATE item
(no product code was intended to ship here) but their exact logic is reproducible from the method
described in §1 (classification), §2 (PII regexes: email/phone/SSN/digit-run patterns over
`word/document.xml` `<w:t>` run text), and §7 (split procedure, fully specified including the RNG
seed and per-tier stage sizes) -- anyone re-running the same procedure against the same
`ccf7a751bc5c8a69c1cdd0400125d53455b33be3` checkout will reproduce the same 42/29/split counts
exactly, since every non-hand-picked step is seeded and every hand-picked step is a
lexicographic-order rule stated explicitly above.
