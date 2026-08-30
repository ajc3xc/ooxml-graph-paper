# PAPER-S18 PREFLIGHT: organic-OMML candidate screening (v1)

Status: preflight before S6, run 2026-08-30. This item builds the required independent
screening tool and rights/privacy adjudication ledger, then runs both against every DOCX
package currently available on local disk. It does not add any document to the gold corpus
and does not change D0. It confirms, via a fresh independent scan rather than by reusing a
prior claim, that zero organic (real-world, non-hand-authored) native-OMML DOCX candidates
currently exist locally, identifies one concrete but unexecuted acquisition lead, and leaves
S6 correctly blocked.

## Bottom line

- **0 organic native-OMML candidates found or admitted.** Every native-OMML document in every
  locally available pool is a hand-authored fixture.
- The required screening tool (`tools/screen_organic_omml_candidates.py`) and adjudication
  ledger schema now exist, are unit-tested, and were run for real against all 434 currently
  available DOCX packages (318 unique by whole-file SHA-256).
- One real, sized acquisition lead was identified (18,680 unreviewed `docx-corpus` URLs) but
  **not fetched** in this run: downloading third-party-hosted content is outside this
  preflight's read-only scope and requires an explicit human go-ahead this session did not
  seek or obtain. This is recorded as a blocker, not silently skipped or worked around.
- S6's unlock gate (>=24 clean organic units from >=8 independent source groups and >=6 task
  families, plus human rights/exposure approval) remains at 0/24, 0/8, 0/6, not approved.

## Scope and relationship to other items

This item is distinct from the D1 expansion plan in
`docs/native-docx-corpus-expansion-v1.md`: D1 is a set of *locally authored* fixtures built to
exercise missing OMML feature families (n-ary, matrix/array, accents, multi-script, etc.) and
is explicitly documented there as testing coverage, "not natural corpus prevalence." S18 is
the opposite pole: it screens for equations that occur *organically* in real-world documents,
which D1 fixtures can never substitute for. Both are needed; neither should be relabeled as
the other. This item also does not duplicate PAPER-29/37's structural corpus audits
(`docs/paper29-corpus-audit-v0.md`, `docs/paper37-corpus-audit-v0.md`); it re-derives the
native-OMML counts those audits already reported, independently, using a new purpose-built
scanner, rather than trusting the prior number without a fresh check.

## The screening tool

`tools/screen_organic_omml_candidates.py` is a read-only, source-agnostic ZIP/XML scanner. For
every `.docx` file under one or more `--root` directories (or explicit `--file` paths) it:

1. Computes a whole-package SHA-256 (`sha256`) and a separate content-level SHA-256 over the
   sorted `word/*.xml` part names and bytes (`content_sha256_for_dedup`), so byte-identical
   copies and content-identical-but-differently-packaged copies can each be detected.
2. Opens the file as a zip, checks `zf.testzip()`, confirms `[Content_Types].xml` and
   `word/document.xml` are present, and parses every `word/*.xml` part (document, headers,
   footers, footnotes, endnotes, comments, glossary) as XML. This is a lightweight,
   self-contained integrity check, intentionally narrower than and independent of the
   product's own `ooxml_integrity.validate_docx_package` (the deeper check
   `tools/build_gold_manifests.py` already uses for anything actually promoted to gold).
3. Walks every parsed part for elements in the OOXML Math namespace
   (`http://schemas.openxmlformats.org/officeDocument/2006/math`), counts `<m:oMath>`
   containers, and classifies child elements into the same 8 feature-family buckets already
   defined in `docs/native-docx-corpus-candidate-manifest-v1.json`'s `equation_classes`
   (fraction, radical, subscript, superscript, nary, matrix_or_array, accent_or_limit,
   multi_script), so results are directly comparable to that D1 audit.
4. Emits one adjudication-ledger record per file (`build_ledger_record`) carrying every field
   this item's own notes require: `source_url`, `source_retrieved_at`, `source_group`,
   `task_family`, `license_or_redistribution`, `privacy_pii_review`, `exposure_review`,
   `independent_gold_extracted`, `word_receipt`, and an `admission_decision`. Any field with no
   real answer yet is set to an explicit sentinel (`unassigned` / `unknown_pending_review` /
   `not_assessed` / `not_run` / `not_admitted`) -- never omitted or guessed.

It does **not** download anything (read-only over local disk), does not mutate or relabel any
existing D0 document, and does not import the product's parser (`docs_intel.py`) to make the
OMML-presence determination -- that determination comes entirely from raw ZIP/XML inspection.

**Tests**: `tests/test_screen_organic_omml_candidates.py`, 10 cases built against small
synthetic in-memory `.docx` packages (no dependency on the real corpus): correct
no-math/fraction/n-ary detection, hand-authored-by-name flagging, four distinct package
integrity failure modes (missing `[Content_Types].xml`, unparsable XML part, not-a-zip-at-all,
corrupt member), ledger-record default/override behavior, and whole-file duplicate detection.

```
pixi run python -m pytest tests/test_screen_organic_omml_candidates.py -v
```

Result: **10 passed, 0 failed** (run 2026-08-30, this item).

Script SHA-256 at the time of the run below:
`d7867341a9563f468f6196336b3cd6c7e2d503d031116875d7dbdedb77e2d55f`.

## Independent scan of every locally available DOCX pool

Run:

```
pixi run python tools/screen_organic_omml_candidates.py \
  --root "E:/MeridianData/ooxml-graph-paper/raw" \
  --root "E:/MeridianData/ooxml-graph-paper/external/docops-source" \
  --root "E:/MeridianData/ooxml-graph-paper/gold" \
  --out "E:/MeridianData/ooxml-graph-paper/manifests/s18-omml-screen-20260830T070958Z.json"
```

| Pool | Path | Packages scanned |
|---|---|---:|
| raw | `E:\MeridianData\ooxml-graph-paper\raw` | 155 |
| external/docops-source | `E:\MeridianData\ooxml-graph-paper\external\docops-source` | 152 |
| gold | `E:\MeridianData\ooxml-graph-paper\gold` | 127 |
| **Total scanned** | | **434** |
| **Unique by whole-file SHA-256** | | **318** |

The 116-package gap between 434 scanned and 318 unique is fully explained and verified, not
hand-waved: 116 `gold/tier2/*` documents are byte-identical whole-file copies of a `raw/`
source (the promotion step copies bytes as-is). The remaining 11 gold documents (8 tier1 + 3
tier3) are hand-authored with no `raw/` counterpart. Zero content-level duplicates were found
that were *not* also whole-file duplicates (`content_duplicate_groups_across_different_bytes`
is empty), i.e. no re-packaged-but-logically-identical copies were hiding under different
bytes.

`external/delegate52-source` was checked and correctly excluded, the same way PAPER-37 excluded
MathMLben: it is not a document source at all. Direct listing shows a cloned agentic-benchmark
harness repository (`model_agentic.py`, `run_relay.py`, `utils_dataset.py`, etc.) with zero
`.docx` files.

### Native-OMML result (independently re-derived)

| Metric | Value |
|---|---:|
| Documents with `<m:oMath>` | 7 |
| `<m:oMath>` containers total | 8 |
| ...of which hand-authored by filename (`fixture-*`/`composite-*`) | 7 |
| ...of which NOT hand-authored by filename (organic candidates) | **0** |
| Package integrity failures (malformed zip/XML) | 0 |

Feature-family totals across all 8 containers: `fraction=3, radical=2, subscript=1,
superscript=1`. `nary`, `matrix_or_array`, `accent_or_limit`, and `multi_script` are all 0.

This matches `docs/native-docx-corpus-candidate-manifest-v1.json`'s `equation_classes` counts
exactly, and matches this sprint item's own notes (7 packages / 8 containers, all hand-authored
tier1/tier3 fixtures). The match is a genuine cross-check, not a copy: it was produced by a
from-scratch scanner in this item, run against the real files, not by reading and restating the
prior document's numbers.

The 7 hand-authored documents, by path:

```
gold/tier1/fixture-02-equation.docx
gold/tier1/fixture-06-equation-radical.docx
gold/tier1/fixture-07-equation-empty-child.docx
gold/tier1/fixture-08-equation-fallback.docx
gold/tier3/composite-01-report.docx
gold/tier3/composite-02-adversarial.docx
gold/tier3/composite-03-multi.docx
```

None of these are relabeled as organic. Per this item's own standing instruction, they remain
exactly what they always were: hand-authored controlled fixtures.

Full raw scan output (434 per-file records plus summary):
`E:\MeridianData\ooxml-graph-paper\manifests\s18-omml-screen-20260830T070958Z.json`.

## The adjudication ledger: currently empty, by design, not by oversight

`build_ledger_record` was run for all 434 scanned packages (see the JSON above for the
per-file records, all with `admission_decision: "not_admitted"`). Zero records are organic
native-OMML candidates, so zero were promoted into
`manifests/s6-organic-omml-candidates-v1.json`'s `admitted_organic_candidates` list. The
ledger schema and tool are proven against the full existing corpus and are ready to run,
unmodified, against any newly staged candidate directory (`--root`/`--file`, optionally with a
`--metadata` sidecar supplying `source_url`, `source_group`, `task_family`, and license
information once known).

## One real acquisition lead, identified and explicitly not executed

`raw/docx-corpus/filtered_candidates.json` holds 18,770 pre-filtered candidate records (id,
filename, type, topic, language, word_count, confidence, and a `url` field pointing at
`https://docxcorp.us/documents/<sha256>.docx`). Only 90 of these were ever downloaded
(`raw/docx-corpus/files/`, matching `sample_90.json`/`sample_90_ids.json`) and individually
reviewed (67 promoted, 23 excluded, per `docs/gold-corpus-status-v0.md`). The remaining 18,680
records are metadata-only -- **no bytes are present locally**, so this scanner could not, and
did not, screen them.

Screening more of this pool would require fetching new third-party-hosted content over the
network from `docxcorp.us`. That is a deliberate boundary of this preflight item, not an
oversight: this item is scoped to independently screening files already present on local disk.
Per this project's standing operating policy, a new file download -- bulk or single -- requires
an explicit human go-ahead. That approval was not sought or obtained in this autonomous run, so
no download was attempted. This is recorded here as a real, sized, available option for a
future acquisition step, exactly as PAPER-37 recorded the (different) untapped `docx-corpus`
candidate pool for a future corpus-expansion item rather than silently ignoring it or
unilaterally acting on it.

**Feasibility caveat, stated honestly**: the base rate from the 90 already-downloaded samples
of this exact source is 0/90 documents with any native OMML, consistent with the project-wide
0/318 unique real-world packages. There is no source-specific evidence this pool would yield
organic OMML, let alone the specific under-covered feature families S6 most needs (`nary`,
`matrix_or_array`, `accent_or_limit`, `multi_script` are all still 0 project-wide). Downloading
more of it is a plausible lead, not a known fix, and should be sized and reasoned about with
that caveat in mind before a human authorizes it.

No other candidate-source lead was found. `docx-corpus`, `omega-officeval`, `docx-benchmark`,
`docops-source`, `mathmlben`, `DocBank-repo(-incomplete)`, `ReadingBank`, and
`delegate52-source` are the complete set of directories under `raw/` and `external/`; all were
enumerated and scanned or explicitly excluded above.

## S6 gate status

| Requirement | Required | Current |
|---|---:|---:|
| Clean organic OMML units | >= 24 | **0** |
| Independent source groups | >= 8 | **0** |
| Task families | >= 6 | **0** |
| Human rights/exposure approval | obtained | **not obtained** |

**S6 remains blocked.** This is the correct state given the evidence above, not a gap in this
item's work: zero organic native-OMML candidates exist in any locally available,
independently-scanned pool.

## What would actually unblock this

1. A human decides whether to authorize fetching some portion of the 18,680 unreviewed
   `docx-corpus` URLs (or a different public source), with the base-rate caveat above in view.
2. Any newly staged candidate directory -- from that source or elsewhere -- can be pointed at
   `tools/screen_organic_omml_candidates.py` immediately, without modification, to produce the
   same ledger fields recorded here.
3. Each admitted candidate still needs independent gold extraction
   (`tools/independent_gold_extractor.py`), a Word receipt where Word COM is available (per
   prior sessions' findings, Word COM and `MML2OMML.XSL` are installed and activation succeeds
   on this host), and explicit license/PII/exposure adjudication before it counts toward the
   24-unit / 8-group / 6-family gate.

## Outputs of this item

- `tools/screen_organic_omml_candidates.py` -- the independent scanner + ledger builder.
- `tests/test_screen_organic_omml_candidates.py` -- 10 unit tests, all passing.
- `E:\MeridianData\ooxml-graph-paper\manifests\s18-omml-screen-20260830T070958Z.json` -- the
  raw 434-record scan output.
- `E:\MeridianData\ooxml-graph-paper\manifests\s6-organic-omml-candidates-v1.json` -- the
  provisional S6 candidate manifest: 0 admitted candidates, full scan provenance, the
  acquisition lead, and the explicit gate status above.
- This document.

## Summary verdict

No organic native-OMML DOCX candidates were found, because none currently exist in any
locally available pool -- a finding independently re-derived in this item with a fresh,
unit-tested scanner rather than assumed from a prior claim. The required screening tool and
rights/privacy adjudication ledger now exist and are proven against the full 434-package
corpus, ready to run against any future candidate pool. One concrete, sized acquisition lead
(18,680 unreviewed `docx-corpus` URLs) was identified and explicitly not acted on, pending
human authorization to fetch third-party content, consistent with this project's standing
operating policy. S6 is correctly left blocked at 0/24 organic units, 0/8 source groups, 0/6
task families, with human rights/exposure approval not obtained.
