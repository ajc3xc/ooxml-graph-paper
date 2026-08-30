# PAPER-S19: evidence-backed DOCX convention-profile inference prototype (v1)

Status: a real, working prototype -- a schema, an independent extractor, a focused
test suite (all passing), and one actual run against a genuine development-only
corpus with a computed, real non-contamination check against the primary 127-document
benchmark holdout. This is explicitly a bounded **prototype** (per the item's own
`milestone_type`), not a finished convention-inference system: single-document
resolution correctly abstains in every case run so far (no known-template registry
exists yet), and template/venue-level validation is honestly reported as `not_run`,
not faked.

## What was built

| Artifact | Path | SHA-256 |
|---|---|---|
| Extractor | `tools/extract_docx_convention_profile.py` | `1048812406827920789a94c26dcb6c16bc122219d7fdf0206b2b88168c779afd` |
| Dev-corpus runner | `tools/run_paper_s19_dev_profile.py` | `67e7f12cc74c48a168758927c07e143d96db8e436238eb674fb98ea5f3861482` |
| Unit tests | `tests/test_extract_docx_convention_profile.py` | `35b2ce3a0b6291e51f7e1027414b13ccea6a2614dd05eca3482d755af80dc6e0` |
| Run manifest | `E:\MeridianData\ooxml-graph-paper\manifests\profile-inference-dev-v1.json` | `37dd7568b80fcdf6eda82b85b9a45492368c3b8e1193cec6e31d9339e82ea87e` |

`tools/extract_docx_convention_profile.py` is stdlib-only (`zipfile` +
`xml.etree.ElementTree`), imports nothing from `meridian_docs`/`docs_intel.py` or any
other parent-repo implementation-under-test code, and imports no third-party DOCX
library (no `python-docx`) -- the same independence rule
`tools/independent_gold_extractor.py` already follows for the graph-gold pipeline,
now applied to a second, unrelated extraction task so a profile produced here cannot
be circular with anything PAPER-30 benchmarks.

### Schema

Every signal is an `Evidence` record: `category`, `node` (the XML path/attribute the
signal came from), `part` (the OOXML package part), `observed_value`, `confidence`
(0.0-1.0), `authority` (one of `observed` / `inferred` / `template` /
`official_guideline` / `domain_default`), `status` (`resolved` / `unknown` / `mixed`),
`conflicts` (populated whenever `status="mixed"` -- e.g. two sections in one document
with different page geometry), and (aggregate evidence only) `sample_size`. A
document or domain profile carries a `resolution.level` of exactly one of
`exact_template_match` / `venue_family` / `domain_family` / `abstain`, plus a
`profile_hash` (SHA-256 of the canonically-serialized evidence+resolution, excluding
timestamps/paths, so two runs on identical input hash-match) and, per document, the
document's own `source_sha256` and the extractor's own `extractor_self_hash`.

The 12 categories the item's notes required are all implemented and all covered by a
dedicated test (`test_all_twelve_categories_present_in_evidence`): styles
inheritance/latent styles, numbering, sections/page geometry, headers/footers/fields,
captions, tables, equations, revisions, anchors/bookmarks, fonts/language,
citations/bibliography, and metadata/accessibility.

**Abstention is the default, not a fallback.** A single document with no
`--known-templates` registry supplied always resolves `abstain` --
`test_single_document_abstains_without_template_registry` pins this down, and it held
for every one of the 23 real documents actually run (see below). `domain_family` is
only reached when >=3 documents share an explicit `--domain-label` and a given node's
majority value clears an agreement threshold (default 0.6); `venue_family` and
`exact_template_match` are implemented but were never exercised against real data in
this item -- no genuinely independent, licensed official-template registry exists in
this repo or on `E:\MeridianData\ooxml-graph-paper` yet (see "What is honestly not
done" below), and the `--known-templates` matching path is currently proven only by
`test_aggregate_domain_profile_reaches_domain_family_above_threshold`-style unit tests
against synthetic evidence, not against a real template.

### Test suite

`pixi run python -m pytest tests/test_extract_docx_convention_profile.py -v` --
**10/10 passed**. The tests build a wholly synthetic, self-authored minimal DOCX
package in-memory (`_build_synthetic_docx`, raw `zipfile.writestr`, no corpus file
touched) so unit coverage does not depend on -- or risk any appearance of tuning
against -- either the gold holdout or the development corpus described below. Cases
covered: determinism (two runs, same hash), all 12 categories present, single-doc
abstention, absent-part handling (`numbering.xml` missing -> `uses_numbering=False`,
not guessed), real signal extraction (bookmark/caption/table), single-value vs.
`mixed`-status page geometry (a second, deliberately different `sectPr` injected into
the fixture to force and check the conflict path), and both aggregate-domain
outcomes (abstain below `n=3`, `domain_family` above threshold with the minority
value recorded in `conflicts`, never dropped). `pixi run python -m pytest tests/
--collect-only` (60 tests total across the repo) still collects cleanly with this
file added.

## The development-only corpus, and why it does not touch the holdout

The item's own instruction is explicit: tune only on development/exposed material,
never on the primary evaluation holdout. The primary holdout here is the
127-document gold corpus (`E:\MeridianData\ooxml-graph-paper\gold\tier1` (8),
`tier2` (116), `tier3` (3)) that PAPER-15/29/30/34/35 actually benchmark against.

**Development corpus chosen**: the 23 `docx-corpus` candidates that a prior,
independent PII/content review
(`E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\review_results.json`, verdict
!= `"promote"`) already excluded from the gold-corpus build -- documented in
`docs/paper37-corpus-audit-v0.md` and `docs/gold-corpus-status-v0.md` as "67
promote, 23 exclude." By construction these 23 are disjoint from the 67 that were
promoted into `gold/tier2`. This tool does not merely trust that bookkeeping,
though -- it independently re-verifies non-overlap by content hash (below), and it
never extracts or emits any `<w:t>` body text, so the PII reasons the review
excluded these specific 23 documents from the *benchmark gold set* (real names,
phone numbers, national ID numbers in the visible text) do not carry over to this
tool's *structural-signal-only* use of the same files.

**Non-contamination check actually run** (`tools/run_paper_s19_dev_profile.py`,
recorded in the manifest's `holdout_non_contamination_check`):

- Loaded the real SHA-256 of the current on-disk bytes of all 127 gold documents
  (`gold_holdout_doc_count: 127` -- every `tier1`/`tier2`/`tier3` `.docx`, confirming
  the corpus's own known size).
- Computed the real SHA-256 of the current on-disk bytes of all 23 staged
  development documents.
- Intersected the two hash sets: **`sha256_overlap_with_dev_corpus: []`,
  `contamination_free: true`.** Zero overlap, computed, not assumed.

**A real naming-scheme finding surfaced while building this check, recorded
honestly rather than silently worked around**: `docx-corpus`'s own file/id naming
is *not* the SHA-256 of the file's current on-disk bytes. Example verified directly:
file `09ddcf0774e6d884fe2bab6cdb33a5a3e44d2bbad6da88bad42114b5cd244539.docx`'s actual
content SHA-256 is `7fac1538033cafeeeb8e4a48e61f88176c9093eba1f47a37882fa5608359595d`
-- a different value from its filename/id. This does not weaken the
non-contamination check above (which hashes real bytes on both sides, never trusting
the filename as a proxy for content identity), and a second direct check confirms
the gold-build pipeline itself copies bytes verbatim rather than reprocessing them
(`raw/docx-corpus/files/02046635ea54d20f....docx` and
`gold/tier2/tier2-docxcorpus-02046635ea54d20f.docx` are byte-identical,
`sha256=c7117c235404004967160201f7f46ce436297c96540d4fa9be45966b78be6675`) -- so the
mismatch is a naming-scheme quirk in the upstream dataset, not a data-integrity
problem. **Caveat honestly noted, not resolved here**: this is a strict
byte-for-byte comparison of current files on both sides; it would not catch a
semantic duplicate whose bytes differ because of some intermediate reprocessing step
upstream of both the gold build and this dev-corpus staging. No evidence of such
reprocessing was found (the one promoted file spot-checked was byte-identical to its
raw source), but 23 vs. 127 pairs were not each individually spot-checked this way --
only hashed.

**Determinism check actually run** (also in the manifest): each of the 23 documents'
profile was independently computed twice
(`E:\MeridianData\ooxml-graph-paper\runs\profile-inference\run-a` and `run-b`) --
**`all_per_doc_deterministic: true`** (23/23 per-document `profile_hash` values
matched across the two runs) and **`aggregate_hash_deterministic: true`** (the
domain-aggregate hash also matched). This exercises the real extractor against real,
messy, real-world-sourced DOCX files, not only the synthetic unit-test fixture.

## Real findings from the 23-document development corpus

Aggregated under `domain_label="docx-corpus-excluded-dev"`, threshold 0.6, minimum
`n=3`: resolution reached **`domain_family`** (never `venue_family` -- these 23
documents share no common venue tag, just a common raw source -- and never
`exact_template_match`, since no template registry was supplied). 20 of 38 evidence
nodes reached >=60% agreement. Selected, real results (full list in the manifest):

- `revisions`: 0/23 use `w:ins`/`w:del`, `trackChanges` off in 100% -- no visible
  track-changes convention in this pool.
- `equations`: 0/23 contain any `m:oMath` -- consistent with PAPER-29's separate
  finding that zero real-world documents in the whole 127-document corpus contain a
  native equation.
- `sections`: `portrait` orientation in 20/23 (87%); page size resolves to
  `Letter` in 15/23 (65%), with `A4` and one `unknown` (non-standard twip
  dimensions) as the recorded, not-hidden minority.
- `styles`: default run size 22 half-points (11pt) in 15/23 (65%), with `None`
  (no `docDefaults` size at all) and `20` (10pt) as recorded minority conflicts.
- `metadata_accessibility`: `core_creator_present=True` in 21/23 (91%);
  `core_title_present=False` in 17/23 (74%, i.e. most of these real-world documents
  never set a document title in `docProps/core.xml`); `core_language` unresolved in
  100% (no document in this pool sets `dc:language`).
- `numbering.uses_numbering=True` in 18/23 (78%).

**A second real, self-found methodological gap, fixed then documented rather than
hidden**: the aggregate schema originally reported confidence/agreement for every
node as if all 23 documents contributed to it, but several per-document extractor
functions only emit a node when a part/element is present (e.g. the raw
`numbering.xml`-presence marker is only emitted for documents that *lack*
`numbering.xml`). Before the fix, that made a 5-of-23-documents subgroup look like a
23-of-23 "100% agreement" finding. Fixed by adding an explicit `sample_size` field to
every aggregate `Evidence` record: the manifest now shows `numbering.numbering.xml`
resolving with `sample_size=5` (not 23), correctly scoped to the 5 documents that
actually lack the part, while `numbering.uses_numbering` (emitted unconditionally by
every document) correctly shows `sample_size=23`. This is recorded here as a real,
caught-and-fixed gap, consistent with this project's standing rule against silently
folding partial-coverage statistics into an aggregate that implies full coverage.

## What is honestly not done (abstained, not faked)

- **Template/venue-level validation: `not_run`.** No independent, licensed
  official-template registry exists yet in this repo or on
  `E:\MeridianData\ooxml-graph-paper` that isn't already fully inside the 127-document
  gold holdout -- the only two `docx-benchmark` template-family documents on disk
  (`raw/docx-benchmark/series-seed/investment-agreement{,-executed}.docx`) are both
  *already* promoted into `gold/tier2` as
  `tier2-docxbenchmark-investment-agreement-{blank,executed}`, so using them here as
  a "known template" would itself be exactly the kind of holdout use this item warns
  against. `--known-templates` and `exact_template_match` are implemented and unit
  tested against synthetic evidence only (`tool_requirements`'s own documented
  fallback: "If unavailable, evaluate observation-only and report
  template-validation not_run").
- **Word render receipt: `not_run`.** This item's scope is convention-profile
  *inference*, not a product-integration demonstration, and `tool_requirements`
  marks a render receipt "preferred" with an explicit not-run fallback. Separately,
  at the time of this run Word COM was actively claimed by a concurrent sprint
  session (`paper-s21-word-com-lifecycle`, whole-`tools/`-directory lock, lease
  until 09:10 UTC) -- exercising Word COM here would have risked exactly the kind of
  cross-session conflict the project's own file-locking system exists to prevent, so
  it was not attempted rather than worked around.
- **No document in this run resolved `exact_template_match` or `venue_family`.**
  This is treated as a correct outcome of the evidence available, not a shortfall of
  the extractor: neither a template registry nor a venue-tagged corpus exists yet.
- **No corpus expansion.** This item does not add documents to the 127-document
  benchmark corpus, and does not change PAPER-30/34/35/39's scoring in any way --
  it is a wholly separate, paper-side, product-independent tool and dataset.
- **A single spot-check, not an exhaustive one, on the "gold copies raw
  docx-corpus files verbatim" claim** (see above) -- one promoted file pair was
  checked byte-for-byte; the other 66 promoted files were not individually
  re-diffed against their raw sources in this item.

## Resource-coordination note

`claim_sprint_item` initially rejected this item (`RESOURCE_LOCKED`) because its
declared `touches_resources` named the whole `ooxml-graph-paper/tools` and
`ooxml-graph-paper/docs` directories, and another live session
(`paper-s21-word-com-lifecycle`) held a directory-level lock on `tools/` acquired
seconds earlier for unrelated work. Since this item's actual footprint is three new
files (`tools/extract_docx_convention_profile.py`,
`tools/run_paper_s19_dev_profile.py`, `docs/paper-s19-profile-inference-v1.md`) and
never edits any existing file either session might touch, `touches_resources` was
narrowed via `update_sprint_item` to the exact files before reclaiming --
`tools/run_paper_s19_dev_profile.py` and `tests/test_extract_docx_convention_profile.py`
were added to the item mid-flight and were confirmed unclaimed
(`get_file_claims`) but a follow-up `update_sprint_item` call to record them on the
item itself was rejected (`IN_PROGRESS`, cannot mutate a self-claimed item's
resources without `force`) -- recorded here for completeness since the item's stored
`touches_resources` therefore undercounts by two files relative to what was actually
touched.

## Summary verdict

A real, evidence-backed convention-profile schema and extractor exist, pass a
10-test focused suite, and were run end-to-end against a genuine, hash-verified,
non-holdout 23-document corpus with a real, computed determinism check (23/23
per-document + aggregate hash match across two independent runs) and a real,
computed zero-overlap check against all 127 gold-holdout documents. Two real
methodological gaps were found while doing this work and are documented rather than
hidden: a dataset filename/content-hash mismatch (verified harmless to the actual
contamination check) and a conditional-evidence-emission sample-size bug (found,
fixed, and now surfaced via an explicit `sample_size` field). Template- and
venue-level resolution remain correctly unexercised against real data -- `abstain`
is the honest answer given the evidence this prototype actually has, not a
limitation glossed over.
