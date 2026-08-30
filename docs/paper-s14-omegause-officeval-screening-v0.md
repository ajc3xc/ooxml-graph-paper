# PAPER-S14 INVESTIGATE: OmegaUse-OfficeVal Word-only secondary task set screening (v0)

Status: a real, evidence-based screening of the locally staged
`baidu-frontier-research/OmegaUse-OfficeVal` release (100 agent tasks) against this item's
own acceptance criteria -- native-`.docx` input+deliverable only, license/hash verification,
independence from the 127-document graph corpus, and verifier reproducibility. **Bottom
line: 13 of the 100 tasks meet the strict "inputs and deliverables are native .docx"
criterion, and all 13 fail the independence audit** -- every one of them draws its input
files from the same 63-file raw `.docx` pool that this project already fully triaged for the
primary corpus (47 promoted into `gold/tier2` as structural-fidelity gold documents, 16
excluded for unresolved PII). **No Word-only OmegaUse-OfficeVal task is adopted as a
secondary task set by this item.** This is a screening/investigation deliverable only; no
code, corpus, or sprint-scope changes were made.

## Bottom line

- **Dataset is real and correctly staged.** `baidu-frontier-research/OmegaUse-OfficeVal`,
  Apache-2.0, 100 tasks, confirmed live on Hugging Face (fetched 2026-08-30) with identical
  license and task-distribution numbers (Word 37 / PowerPoint 39 / Excel 19 / PDF 4 /
  cross-file 1) as the locally staged `README.md`. The companion evaluation-harness GitHub
  repo (`baidu-frontier-research/OmegaUse-OfficeVal`, also Apache-2.0) exists and contains
  real per-task verifier code, confirmed by direct fetch of its README.
- **13 tasks are strictly "Word-only"** (every input file and every deliverable-format token
  the task's own usability rubric names is `.doc`/`.docx`): `officeval_001, 007, 010, 012,
  015, 018, 021, 022, 023, 024, 026, 030, 033`.
- **0 of those 13 are independent of the 127-document graph corpus.** All 13 draw their
  input files from the same 63-file raw `task_files` `.docx` pool this project already
  reviewed end-to-end for the primary corpus:
  - **4 tasks** (`010, 024, 026, 033`) have **100% of their input files already promoted**
    into `gold/tier2` as scored structural-fidelity documents (PAPER-25/29/30/37).
  - **6 tasks** (`001, 012, 015, 018, 022, 030`) are **partially overlapping**: some inputs
    promoted into gold, and (see below) the remaining input(s) excluded for unresolved PII.
  - **3 tasks** (`007, 021, 023`) have zero promoted-gold overlap, but **100% of their
    inputs are exactly the files this project's own prior review excluded from gold for
    unresolved, human-real-looking PII** (filled student name+ID pairs, a phone-number
    dossier) -- "clean of corpus overlap" here means "still carries the unresolved privacy
    flag that kept it out of gold in the first place," not "safe to use."
  - Net: **every one of the 13 candidate tasks is blocked**, by corpus non-independence,
    unresolved PII risk, or both. No held-out, rights-clear Word-only task survives.
- **Verifier reproducibility: not established, and not fabricated as established.** The
  locally staged HF dataset repo ships only natural-language rubrics (`dim1`/`dim2` text),
  not executable verifier code. The executable verifiers live in the separate companion
  GitHub repo; this item confirmed that repo's existence, license (Apache-2.0), and
  documented dependencies (Python 3.10+, `pywin32`/Office COM required for exactly 9 of the
  100 verifiers: `001, 008, 019, 022, 023, 030, 039, 074, 081`) via two independent fetches
  of its README, but **did not clone, install, or execute it**. Reproducibility of any
  specific task's score is therefore unverified in practice, only plausible in principle.
- **Recommendation: do not adopt OmegaUse-OfficeVal as a Word-only secondary task set in
  its current form.** See "Paths not taken" below for what would have to change first.

## Scope and relationship to other items

This item screens the 100-task **agent-task** release (`raw/omega-officeval/`,
`tasks_and_rubrics_en.json`) against the criteria in its own sprint notes. It does not
duplicate, and instead directly builds on and cross-checks, the file-level provenance work
already on record in `docs/gold-corpus-status-v0.md` (the OmegaUse-OfficeVal promotion/
exclusion history for the 127-document corpus) and `docs/paper37-corpus-audit-v0.md` (which
already flagged, at a higher level, that OmegaUse-derived documents are part of the primary
corpus). Those documents established *which raw files* were promoted or excluded and *why*;
this item is the first to connect that decision to the *agent-task* definitions that
reference those same files, which is what actually creates or avoids the independence
problem for a task-completion benchmark.

## Method (no fabrication -- every number below is computed from the files cited)

1. **Located the local staging.** `E:\MeridianData\ooxml-graph-paper\raw\omega-officeval\`
   contains `README.md` (the HF dataset card, YAML frontmatter confirms `license: apache-2.0`,
   `pretty_name: OmegaUse-OfficeVal`), `hf-tree-main.json` (a 734-entry HF API tree snapshot),
   `tasks_and_rubrics_en.json` (100 merged English task+rubric records), and `task_files/`
   (63 real `.docx` files across 47 non-empty `officeval_NNN` folders; folder numbering is
   sparse, e.g. `017, 027, 029, 032, 034, 038` etc. are present in the 100-task schema but
   have no locally staged `.docx` under `task_files` because their inputs are non-Word
   formats).
2. **Verified the schema by direct inspection**, not by trusting the README's prose: each
   record in `tasks_and_rubrics_en.json` has keys `id, instruction, operation_intent, domain,
   human_labor_time, task_price_proxy, price_source, origin_files` (list of `{url, dest}`),
   `rubrics` (`{dim1: [...], dim2: [...]}`). No `origin_files_json`/`rubrics_json` string
   fields exist in this file (those names only apply to the separate Parquet/Data-Studio
   copies per the README) -- an initial script draft assumed the wrong key names and was
   corrected before producing any number in this report.
3. **Classified deliverable format from the task's own rubric text, not a guess.** Every
   `dim1` usability item states its required delivered format in plain language, e.g. task
   `officeval_001`'s `dim1[0]`: *"The delivered files are in Word format, have the .doc
   extension, and can be opened normally."* A task is `word_only` only if (a) every
   `origin_files[].dest` extension is `.doc`/`.docx`/`.dotx`, AND (b) every recognizable
   format-extension token found anywhere in that task's `dim1` text is also a Word extension.
   Tasks where `dim1` names no recognizable extension token are excluded from the strict set
   rather than guessed into it (0 such cases occurred among the docx-input tasks). This
   method's aggregate broader count (any task whose `dim1` mentions `.doc`/`.docx` at all,
   regardless of input purity) reproduces the dataset card's own stated "Word: 37 tasks (37%)"
   figure exactly (37/37), which is strong corroborating evidence the extraction method is
   sound, not an artifact of a loose heuristic.
4. **License verified twice, independently.** Locally: `README.md` YAML frontmatter,
   `license: apache-2.0`. Live: `WebFetch` of
   `https://huggingface.co/datasets/baidu-frontier-research/OmegaUse-OfficeVal`
   (2026-08-30) returned the same license and the same 37/39/19/4/1 task-type breakdown,
   confirming the local copy is an authentic, unmodified snapshot of the public release, not
   a locally altered or fabricated one.
5. **Hashes verified three independent ways**, not merely read from one manifest:
   - `gold/manifests/_omegause_inventory.json` records a `sha256` for all 63 raw `.docx`
     files (generated by a prior session).
   - Cross-checked against `hf-tree-main.json`'s recorded HF git-blob `oid` + `size` for all
     8 files in `officeval_001/`: recomputed the git-blob SHA-1
     (`sha1("blob " + len + "\0" + content)`) directly from the local files myself and it
     matched the recorded `oid` for all 8/8 files, byte-for-byte -- an independent
     cryptographic confirmation the local files are unmodified copies of the exact release
     tree, not merely files with matching names/sizes.
   - Directly re-hashed (SHA-256) all 47 `gold/tier2/tier2-omegause-*.docx` files myself
     (not reused from any manifest) to build the ground-truth "promoted into gold" set used
     for the overlap analysis below.
6. **Cross-referenced task input files against the actual promoted-gold set by content
   hash**, not by directory-name pattern matching. An earlier draft of this analysis
   mistakenly compared task inputs against the full 63-file raw inventory (which trivially
   "overlaps" 100% of any docx-input task, since all task inputs are drawn from that same
   raw pool by construction) -- that draft was discarded before being reported. The
   corrected check compares each task's input file's SHA-256 against the SHA-256 of the 47
   files physically present in `gold/tier2/`.
7. **Read the actual PII exclusion rationale** for every excluded file that a candidate
   Word-only task depends on, from `gold/manifests/_tier2_review.json`'s `excluded` array
   (human-readable notes from the original per-file review), rather than treating
   "not promoted" as an unexamined residual category.
8. **Verified the companion verifier repository** (`github.com/baidu-frontier-research/
   OmegaUse-OfficeVal`) exists and its README states real verifier/dependency facts, via two
   separate `WebFetch` calls (one on the rendered GitHub page, one on the raw `README.md`)
   that agreed on every specific (100 verifiers, 9 COM-requiring task IDs, Apache-2.0,
   Python 3.10+, `pywin32` Windows-only). Did not clone or execute this repository -- out of
   scope for a read-only screening item, and not needed to reach the independence-audit
   conclusion above (which is decisive on its own).

## The 13 strict Word-only candidate tasks, in full

| Task | Domain | Labor (min) | Price (yuan, source) | Inputs | Promoted-into-gold / total | COM-required (official harness) |
|---|---|---:|---|---:|---:|:---:|
| officeval_001 | Education & Examination | 204 | 50, estimated | 8 | 7/8 | yes |
| officeval_007 | Academic Papers | 150 | 18, estimated | 2 | 0/2 (both PII-excluded) | no |
| officeval_010 | Engineering & Technology | 228 | 31, estimated | 1 | 1/1 | no |
| officeval_012 | Academic Papers | 114 | 33, estimated | 2 | 1/2 | no |
| officeval_015 | Education & Examination | 92 | 60, explicit | 2 | 1/2 | no |
| officeval_018 | Business Operations | 251 | 48, estimated | 2 | 1/2 | no |
| officeval_021 | Academic Papers | 77 | 25, estimated | 2 | 0/2 (both PII-excluded) | no |
| officeval_022 | Business Operations | 287 | 48, estimated | 4 | 3/4 | yes |
| officeval_023 | Academic Papers | 87 | 44, estimated | 1 | 0/1 (PII-excluded) | yes |
| officeval_024 | Academic Papers | 211 | 38, estimated | 2 | 2/2 | no |
| officeval_026 | Education & Examination | 84 | 50, estimated | 1 | 1/1 | no |
| officeval_030 | Academic Papers | 152 | 45, estimated | 2 | 1/2 | yes |
| officeval_033 | Business Operations | 307 | 33, estimated | 1 | 1/1 | no |

Domain histogram: Academic Papers 6, Education & Examination 3, Business Operations 3,
Engineering & Technology 1. Labor time 77-307 min (avg 173); price proxy 18-60 yuan (avg 40,
12/13 estimated by domain experts, 1/13 an explicit practitioner-supplied price). Language:
task instructions are Chinese-native (`tasks/`), with a maintained English translation
(`task-en/`, `rubrics-en/`, and the merged `tasks_and_rubrics_en.json` used for this audit).
Style: predominantly Chinese academic (thesis/report), administrative, and lesson-plan
documents -- the same genre mix already present in the corpus's `tier2` real-world stratum,
which is expected since they are drawn from the identical source pool.

The exact non-promoted input file for each partial-overlap and fully-excluded task, with the
original reviewer's verbatim rationale (from `gold/manifests/_tier2_review.json`):

- `officeval_001/08_...docx`, `officeval_015/九年级答题卡 (1) (3).docx`,
  `officeval_022/企业经营异常核查呈报材料.docx`: **the same underlying document**
  (a corporate "operating-anomaly verification dossier" with a filled name+phone block)
  appearing under three unrelated filenames in three different task folders.
- `officeval_030/V2成果说明书_A.docx`: filled graduation-design cover page, student name +
  student ID + named advisor.
- `officeval_007/幼儿园自然探究活动课程设计.docx`, `officeval_012/城市社区雨水花园参与式维护机制研究.docx`:
  same filled name + student-ID pair, in two different task folders.
- `officeval_007/齐鲁启明继续教育学院论文模板.docx`: a "template" whose sample cover page is filled
  with a real-looking name + student ID rather than left blank.
- `officeval_018/公共书房运营规划书.docx`, `officeval_021` (both its files):
  the same filled name + 10-digit student ID pair, across three files in two folders.
- `officeval_023/董事會數位素養對企業低碳轉型績效的影響.docx`: filled name + student ID recurring in
  the acknowledgments section.

Every one of these was independently flagged by the prior review as "EXCLUDED from gold
pending explicit human sign-off, not promoted on this session's own judgment" -- i.e., these
are not confirmed-safe files this item can simply repurpose; they carry the exact same
unresolved privacy question for a task-completion use as they did for a structural-gold use.

## Why the independence failure is total, not partial

The dataset's entire 63-file raw `.docx` pool was already exhaustively triaged by this
project before this item started (`docs/gold-corpus-status-v0.md`: "Reviewed all remaining
32 staged OmegaUse candidates (63/63 now reviewed)"): every file ended up either promoted
into `gold/tier2` (47 files) or excluded pending human PII sign-off (16 files). Because the
13 strict Word-only tasks' input files are, by definition of the strict criterion, drawn
exclusively from this same fully-triaged 63-file `.docx` pool, there is no way to find a
"held-out, never-reviewed, rights-clear" native-`.docx` OmegaUse-OfficeVal task today --
every candidate is provably one or the other of the two already-adjudicated buckets, and
both buckets are individually disqualifying for a supposedly-independent secondary set.

## Paths not taken (recorded for a future planning decision, not executed here)

- **Re-litigating corpus composition** (removing the 47 promoted `tier2-omegause-*`
  documents from the 127-document corpus so they could instead serve only the OmegaUse
  task-completion track, or vice versa) would invalidate already-completed scoring passes
  (PAPER-30/31/34/39 all scored against the current 127-document set) and is a materially
  larger, cross-cutting decision outside this screening item's scope -- the same caution
  PAPER-37 gave for corpus expansion applies here for corpus subtraction.
- **Getting the 16 PII-excluded files their pending human sign-off** (or a final decision to
  discard them) is a prerequisite independent of this item, already logged as open in
  `gold-corpus-status-v0.md`.
- **The other 87 OmegaUse-OfficeVal tasks** (PowerPoint/Excel/PDF-output, or Word-output
  tasks whose inputs include non-`.docx` reference material such as images or PDFs) were
  not screened against this item's strict Word-only criterion by design -- 2 of the 37
  broader "Word-output" tasks (`officeval_029`, `officeval_038`) have zero raw-docx-pool
  overlap risk simply because their inputs aren't `.docx` at all (`.jpg`, `.pdf`
  respectively), which is out of this item's scope but worth a future item's attention if a
  looser Word-deliverable-only (not Word-input-also) definition is ever wanted.
- **Cloning and running the companion verifier harness** was not attempted; this item
  confirmed the harness's existence, license, and platform requirements from its public
  README only.

## Artifacts produced by this screening (not committed to the repo; scratch evidence)

- `audit_omegause.py` / `audit_omegause_v2.py`: the classification and (corrected)
  overlap-check scripts described above, run via `pixi run python`.
- `omegause_audit_v2_output.json` (+ `.summary.json`): full per-task classification and
  per-file promoted/excluded detail for all 100 tasks.
- `gold_tier2_omegause_hashes.json`: SHA-256 of all 47 physically-present
  `gold/tier2/tier2-omegause-*.docx` files, computed directly by this item.
- `git_blob_check.json`: independent git-blob-SHA1 recomputation for the 8
  `officeval_001` files, matching `hf-tree-main.json`'s recorded `oid` values.

These live under this session's scratch directory, not the repo, since they are
investigation working files, not paper deliverables; the counts and file lists they support
are reproduced in full in the tables above.
