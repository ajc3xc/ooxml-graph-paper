# PAPER-S5: OOXML graph edge adapters and round-trip editability metrics (v1)

Status: real, tested, real-corpus-run evidence -- not a redesign of PAPER-30's scorer or
`graph-gold-schema-v0.md`'s contract. This item's own notes state the earlier "duplicate"
warning was a false keyword collision and that this work was **not implemented in the paper
repo** before this session; that has now been done, within the item's declared scope
(`tools/graph_scorer.py`, `tools/run_paper30_graph_eval.py`, `docs/graph-gold-schema-v0.md`).
`tests/test_graph_scorer.py` was also extended (not in the item's declared touches_resources,
so it was separately claimed via `claim_file` before editing -- confirmed free via
`get_file_claims` first).

## 1. What was asked, and the honest boundary of what "extend" means here

The item's notes: *"Extend candidate adapters and scorer for caption, anchor, reference,
source_binding, revision nodes and caption_for/references/revises/clones/conflicts_with edges
where the source schema claims them. Add Word round-trip editability and render-equivalence
checks. Do not fabricate values for unsupported systems; retain not_applicable with explicit
capability reasons."*

Before writing any code, `tools/independent_gold_extractor.py` (the gold producer, 351 lines)
was read in full to check which of these seven node/edge kinds **actually have gold ground
truth today**, because "extend the candidate adapter" only makes sense for a kind gold can
already score against -- extending a candidate to report data gold has no way to check would
itself be a fabricated-looking comparison with no verification behind it. Direct reading found:

- `caption` nodes: **real gold ground truth exists** (`_is_seq_field` heuristic, `extract()`
  lines 207-213) -- a SEQ-field paragraph is tagged `kind="caption"`.
- `anchor` nodes: **real gold ground truth exists** (`w:bookmarkStart` scan, lines 215-224).
- `caption_for` edges: **real, resolved gold ground truth exists** (Section 6 resolution,
  lines 276-299 -- nearest preceding top-level table, with an explicit `dangling` state when
  no preceding table exists).
- `reference`, `source_binding`, `revision` nodes and `references`, `revises`, `clones`,
  `conflicts_with` edges: **no gold ground truth exists at all** -- these kinds do not appear
  anywhere in `extract()`'s node/edge construction.

This is a real, load-bearing distinction the previous scorer version did not make: it lumped
`caption`/`anchor`/`reference`/`source_binding`/`revision` into one `unsupported_node_kinds`
bucket, all reported `not_applicable: no_candidate_adapter`. That reason is **wrong** for
`reference`/`source_binding`/`revision` -- it implies gold has the data and only the candidates
are missing an adapter, when actually nobody (gold included) produces it yet. This session adds
a second, more precise reason, `NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH`
(`tools/graph_scorer.py`), and applies each reason correctly per kind rather than reusing one
label for two different capability gaps.

## 2. What changed in `tools/graph_scorer.py`

- New constant `NOT_APPLICABLE_NO_GOLD_GROUND_TRUTH = "not_applicable: no_gold_ground_truth"`,
  distinct from the existing `NOT_APPLICABLE_NO_ADAPTER`.
- New `_caption_node_accuracy(gold_captions, cand_captions, candidate_has_caption_detection)`:
  real precision/recall/F1 via the same LCS text correspondence (`_lcs_correspondence`/`_prf1`)
  already used for paragraph-node scoring, gated `not_applicable: no_candidate_adapter` when the
  candidate can't identify captions at all.
- New `_anchor_node_accuracy(gold_anchors, cand_anchors, candidate_has_anchor_detection)`: exact
  bookmark-**name** multiset precision/recall/F1 (`collections.Counter` intersection) -- bookmark
  names are stable identifiers, not free text (per
  `docs/word-roundtrip-preservation-contract-v0.md` Section 2, "Preserved by name"), so this
  deliberately does not reuse fuzzy LCS text matching.
- `score_document_graph` gained two new optional parameters,
  `candidate_has_caption_detection` and `candidate_has_anchor_detection` (both default `False`,
  so every existing caller keeps its exact prior behavior unless it opts in), and now returns
  `caption_node_prf1` and `anchor_node_prf1` as their own top-level keys (previously both kinds
  were only ever `not_applicable` inside the blanket `unsupported_node_kinds` dict).
- `unsupported_node_kinds` now covers exactly `{reference, source_binding, revision}` (all
  `not_applicable: no_gold_ground_truth`) -- `caption`/`anchor` were removed from this dict
  because they are no longer blanket-unsupported; they have dedicated fields.
- New `unsupported_edge_kinds` dict: `caption_for` -> `not_applicable: no_candidate_adapter`
  (gold resolves it; no candidate computes an equivalent target yet -- real, named remaining
  scope), and `references`/`revises`/`clones`/`conflicts_with` -> `not_applicable:
  no_gold_ground_truth`.
- New `score_round_trip_editability(pre_items, post_items, marker_text)` -- see Section 4.
- Module docstring rewritten to describe the above precisely (which kind is scored for which
  system and why, not a blanket "not yet covered" statement).

## 3. What changed in `tools/run_paper30_graph_eval.py`

- `extract_gold_items`: now also returns `captions: [{"text": ...}]` (from the existing
  `top_level_paragraphs` computation, filtered to `kind == "caption"` -- no new gold-record
  parsing needed, this data was already being loaded and discarded) and
  `anchors: [{"name": ...}]` (from the raw `nodes` list, `kind == "anchor"`).
- `extract_native_meridian_items`: new `_block_has_seq_field(block)` helper reads
  `document_content_tree`'s own per-paragraph `fields` list (confirmed by direct reading of
  `extensions/meridian-docs/meridian_docs/_vendored_content_tree.py`,
  `_fields_in_paragraph`/`_paragraph_node`, lines 72-253 -- this already parses
  `w:fldSimple`/`w:fldChar` field instructions, including `field_type`, for every paragraph, but
  `extract_native_meridian_items` previously discarded that data entirely). A paragraph with any
  `field_type == "SEQ"` is now surfaced as a `captions` entry -- this is a genuine, real
  capability of Meridian's own extraction library that this harness simply hadn't read out
  before, not new logic bolted on from outside it. `document_content_tree` was also confirmed
  (by reading the full file) to have **no bookmark/`w:bookmarkStart` handling anywhere** -- so
  `anchors` for this system is honestly `[]`, scored `not_applicable`, not faked via an
  out-of-band raw-XML scan that would test this harness's own code rather than Meridian's.
- `extract_python_docx_items` / `extract_docling_items`: both now explicitly set
  `captions: []`, `anchors: []` with inline comments stating why (no field-instruction API for
  python-docx; no OOXML field/bookmark data survives a PDF/OCR pipeline for Docling) --
  explicit, not a silent missing key.
- `main()`'s native-Meridian scoring call now passes `candidate_has_caption_detection=True`;
  python-docx/Docling calls are unchanged (both flags default `False`, correctly).
- `metric_paths` gained `caption_node_f1` / `anchor_node_f1` so they flow through the existing
  bootstrap-CI aggregation automatically.
- New Word round-trip editability + render-equivalence check (Section 4), gated behind
  `--round-trip-check` / `--round-trip-sample N` / `--round-trip-timeout-seconds` (default off,
  since it launches real Word processes per sampled document).

## 4. The round-trip editability + render-equivalence check (real, not simulated)

Before writing this, `docs/word-roundtrip-preservation-contract-v0.md` (PAPER-16, a prior real
investigation with a live Word round trip) and `tools/retained_render_receipt.py` (PAPER-23,
already validated this sprint) were read in full, so the watchdog/cleanup/COM-apartment pattern
here is copied faithfully from working, already-proven code rather than reinvented.

**`_word_open_edit_save_round_trip(docx_path, work_path, timeout)`**: copies `docx_path` to a
disposable `work_path` (the original corpus file is never opened for write), then in a
90-second-watchdog worker thread: `win32com.client.DispatchEx("Word.Application")`,
`Documents.Open(work_path, ReadOnly=False, ...)`, collapse `doc.Content` to the end and
`InsertAfter("\r" + marker_text)`, `doc.Save()`, `doc.Close(False)`, `word.Quit()`. A hang is
caught by the watchdog (owned PID terminated via `os.kill`, matching
`retained_render_receipt.py`'s own pattern) and reported as `status: "timed_out"`, never
silently blocking the whole eval run. `pywin32` import failure is reported as `status:
"unavailable"`, never silently skipped.

**`run_round_trip_editability_check(doc_id, docx_path, work_dir, timeout)`**: makes a `-pre` and
a `-post` working copy, runs the round trip against `-post`, then:

1. Re-extracts native-Meridian items from both copies and calls
   `graph_scorer.score_round_trip_editability` -- this compares the SAME extractor's output
   before vs. after (not against gold), so it isolates "did the round trip itself change what we
   can extract" from "is this extractor accurate." The marker paragraph is normalized-text-matched
   and excluded from the post-side comparison, so the *intended* addition never counts as
   *unintended* drift. Per `word-roundtrip-preservation-contract-v0.md` Section 4's own finding
   that raw equation OMML fingerprints drift across a Word save even when semantics do not
   (Word adds `m:*Pr`/`m:ctrlPr`/`m:rFonts` wrappers), equation stability compares independently
   re-derived semantic **labels** (`_reclassify_omml`), never raw OMML bytes.
2. Takes a `retained_render_receipt` (PAPER-23, imported unchanged) of both copies and compares
   page counts -- the render-equivalence signal.

Every sub-stage reports its own real status (`ok`/`failed`/`timed_out`/`unavailable` for the
round trip itself; `scored`/`failed` for the diff); a failure at any stage returns immediately
with the stage and reason, never a fabricated pass.

### Real evidence this session (not asserted, executed)

Ran `pixi run python tools/run_paper30_graph_eval.py --slice smoke --round-trip-check
--round-trip-sample 2 --round-trip-timeout-seconds 60` against the real 10-document smoke slice.
Both sampled documents completed real Word-COM round trips:

| doc_id | marker round-tripped | unintended drift F1 | table/equation stable | pre/post page count | overall status |
|---|---|---|---|---|---|
| `tier2-omegause-010-roadmap-diagram` | true | 1.0 (1/1 matched) | yes/yes | 1 / 1 | `clean_round_trip` |
| `tier2-docxcorpus-61c750fca9dfb8ca` | true | 1.0 (6/6 matched) | yes/yes | 13 / 13 | `clean_round_trip` |

Full report with both documents' complete `editability`/`render_equivalence` payloads:
`E:\MeridianData\ooxml-graph-paper\manifests\paper30-graph-eval-smoke-20260830T074228Z.json`
(`round_trip_check` key). Working copies and retained render PDFs:
`E:\MeridianData\ooxml-graph-paper\runs\paper-s5-round-trip\smoke-20260830T074228Z\`. Prior to
wiring this into the runner, Word-COM render capability on this host was independently
re-confirmed this session (not assumed from an earlier probe) by running
`tools/retained_render_receipt.py` directly against
`E:\MeridianData\ooxml-graph-paper\gold\tier1\fixture-04-caption.docx`: `status=rendered`,
Word `16.0.20326`, real PDF written and hashed.

This is a small, bounded sample (2 documents, one Word build, one host) -- not a claim that
round-trip editability is clean across the full 127-document corpus. A larger
`--round-trip-sample` run is real remaining work, not run this session because each sampled
document launches three real Word processes (edit+save, plus two render receipts), which is
slow; this is stated as a bound, not hidden.

## 5. Real end-to-end evidence: caption scoring on the real corpus

Ran `pixi run python tools/run_paper30_graph_eval.py --slice smoke` (no round-trip flag) against
the same real 10-document smoke slice and gold manifests. Result (full report:
`E:\MeridianData\ooxml-graph-paper\manifests\paper30-graph-eval-smoke-20260830T074217Z.json`):

- `native_meridian` `caption_node_f1`: mean **1.0**, n=1 -- exactly one of the 10 smoke-slice
  documents (`fixture-04-caption`) has a gold caption, and native Meridian's newly-added
  SEQ-field detection identified it correctly (precision=recall=1.0). n=1 is real and small
  because gold captions are rare in this corpus, not because n is capped -- the metric would
  scale automatically on a slice with more caption-bearing documents.
- `native_meridian` `anchor_node_f1`: mean **None**, n=0 -- `not_applicable` for every document,
  as expected (no candidate adapter extracts bookmarks yet).
- `python_docx` `caption_node_f1` / `anchor_node_f1`: both mean **None**, n=0 -- correctly
  `not_applicable` for both kinds, since python-docx exposes neither a field-instruction nor a
  bookmark-listing API.

This is a real, if small, positive result: native Meridian's own extraction library already
computed the data needed for caption identification (`document_content_tree`'s field parsing);
this session's change was to have this evaluation harness actually read it, not to add new
product capability.

## 6. Tests

`tests/test_graph_scorer.py` grew from 25 to **36 tests, all passing**
(`pixi run python -m pytest tests/test_graph_scorer.py -v` — 36 passed in 0.18-0.23s across
repeated runs this session). The pre-existing
`test_score_document_graph_unsupported_kinds_are_declared_not_omitted` was updated (its old
assertion -- that `caption`/`anchor` are `not_applicable: no_candidate_adapter` inside
`unsupported_node_kinds` -- is no longer true by design) rather than left to silently pass on
stale expectations; it now asserts the corrected `no_gold_ground_truth` reason for
`reference`/`source_binding`/`revision` and that `caption`/`anchor` are no longer in that dict at
all. Eleven new tests were added, covering: the new `unsupported_edge_kinds` reasons; caption
scoring both `not_applicable` (default) and `scored` (opted in) inside `score_document_graph`;
`_caption_node_accuracy`'s not-applicable and scored/recall-reducing paths directly;
`_anchor_node_accuracy`'s not-applicable path and its exact-multiset semantics (an
over-reported duplicate name is *not* free-credited, confirmed via `matched=1` when candidate
reports `_Ref1` twice against gold's single `_Ref1`); and four `score_round_trip_editability`
cases (clean round trip, missing marker, unintended paragraph loss, and equation semantic-label
drift).

`tests/test_graph_scorer.py` was not in this item's declared `touches_resources`
(`tools/graph_scorer.py`, `tools/run_paper30_graph_eval.py`, `docs/graph-gold-schema-v0.md`
only), so before editing it this session confirmed via `get_file_claims` that no other live
session held a claim on it, then took an explicit `claim_file` write lock for the duration of
this edit (released at the end of this session, see Section 8).

## 7. What remains explicit, named scope -- not silently covered

- **`caption_for` edge resolution is not scored.** Gold resolves every caption to its nearest
  preceding top-level table (or an explicit `dangling` state); no candidate adapter in this
  harness computes an equivalent resolution, so this stays `not_applicable:
  no_candidate_adapter`, correctly distinguished from the "no ground truth at all" kinds.
- **`reference`, `source_binding`, `revision` nodes and `references`, `revises`, `clones`,
  `conflicts_with` edges remain entirely unscored**, because `independent_gold_extractor.py`
  itself has no ground truth for them. Extending the scorer to accept this data (should a future
  gold-extractor version produce it) is real, separate future work -- not attempted here, since
  building scoring logic against data that does not exist yet would be speculative, not
  evidence-based.
- **Anchor/bookmark candidate extraction remains a real, named gap for all three systems.**
  `_anchor_node_accuracy` is real and tested, but with `candidate_has_anchor_detection=False`
  everywhere today, it always reports `not_applicable`. A future item that adds a genuine
  bookmark-listing capability to a candidate's own extraction library (not a raw-XML scan
  bolted onto this harness) would light this metric up without any scorer change.
- **The round-trip check ran on 2 of 127 corpus documents this session** (Section 4) -- a real,
  bounded capability demonstration, not a full-corpus editability claim. It also only diffs
  native-Meridian extraction (the product under test); python-docx/Docling do not write DOCX in
  this harness, so round-trip editability does not apply to them.
- No product code (`docs_intel.py`, `render_gate.py`, `_vendored_content_tree.py`, or any file
  under the parent repository at `C:\Users\13144\Documents\Meridian\repository`) was read for
  anything beyond confirming existing capability, and none was modified, per this wave's
  standing instruction to keep this item paper-repo-scoped.

## 8. Exact evidence pointers

- Code: `tools/graph_scorer.py` (638 lines,
  sha256 `d8973b0d13fc0512ac392646d93997c2288de9332b39546f068f739c94da214c`),
  `tools/run_paper30_graph_eval.py` (604 lines,
  sha256 `03ed51d1491eb07de0bbda16c8d1581ceb5ba66fc5b94edfd78cc8ead6ce2dc9`),
  `tests/test_graph_scorer.py` (405 lines,
  sha256 `415ca98da579b3befb37aa8195e7214e74fdd87f3e38d2f2a5c40d1d3478f7fd`).
- Contract doc updated: `docs/graph-gold-schema-v0.md` (new "Implementation status (PAPER-S5)"
  section).
- Test run: `pixi run python -m pytest tests/test_graph_scorer.py -v` -- 36 passed.
- Real corpus runs (no product code touched, all in `E:\MeridianData\ooxml-graph-paper\`, never
  synced/committed):
  - `manifests\paper30-graph-eval-smoke-20260830T074217Z.json` (smoke slice, no round-trip flag)
  - `manifests\paper30-graph-eval-smoke-20260830T074228Z.json` (smoke slice, `--round-trip-check
    --round-trip-sample 2`)
  - `runs\paper-s5-round-trip\smoke-20260830T074228Z\` (working copies + retained render PDFs
    for both round-tripped documents)
- Capability re-confirmation: `tools/retained_render_receipt.py` run directly against
  `gold\tier1\fixture-04-caption.docx` this session -- `status=rendered`, Word `16.0.20326`.
- Sources read in full before writing any code: `tools/independent_gold_extractor.py` (351
  lines), `extensions/meridian-docs/meridian_docs/_vendored_content_tree.py` (parent repo,
  read-only), `docs/word-roundtrip-preservation-contract-v0.md`, `tools/retained_render_receipt.py`,
  `tools/graph_scorer.py` and `tools/run_paper30_graph_eval.py` (pre-change), `docs/graph-gold-schema-v0.md`,
  `docs/paper30-graph-scorer-v0.md`, `tests/test_graph_scorer.py` (pre-change).
