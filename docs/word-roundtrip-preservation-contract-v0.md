# Word round-trip editability and non-equation preservation contract v0

Status: investigation checkpoint (PAPER-16). One real Microsoft Word COM
open→edit→save round trip was executed and diffed this session (not merely
read about or assumed). No product code was edited to produce this document.
Extends `runtime-capability-contract-v0.md` (Word COM availability),
`comparator-contract-v0.md` (Track D: native Office comprehension/editability
gate), and `graph-gold-schema-v0.md` (identity/revision invariants) — read
those first; this document does not repeat their content.

## 1. What was actually run this session

Word COM **is** available on this host (16.0.20326, build 16.0.20326.20100;
confirmed independently of the earlier `meridian-equation-word-probe-20260826.json`
probe, which this session re-verified rather than trusted blindly — see §6).
Using it, this session built a real fixture, opened it in Word with
`ReadOnly=False`, made a real edit under Track Changes, saved it, closed
Word, and diffed `word/document.xml` / `word/comments.xml` before vs. after
with `ElementTree`. This is a genuinely new artifact for this project: the
existing test suite (`test_docx_word_com_regression.py`,
`test_section_equation_preservation.py`) never opens Word with
`ReadOnly=False` and never saves — see §5.

**Fixture construction** (`build_fixture.py`, archived at
`E:\MeridianData\ooxml-graph-paper\renders\word-roundtrip-preservation-20260826\`):
a small full-part DOCX (paragraphs + `[Content_Types].xml` + both `.rels`
parts + styles/fontTable/settings/webSettings/theme/docProps, following the
same "Word-authored fixture" shape as
`test_docx_word_com_regression.py`'s `_write_word_authored_docx`), then real
calls into `docs_intel.py`:

1. A manually-inserted plain bookmark (`PAPER16_TESTBOOKMARK`) — there is no
   dedicated `insert_bookmark` writer in `docs_intel.py`, so this one step
   was hand-built XML, not a call into a product writer.
2. `insert_numbered_equation(..., payload=r"\sum_{i=1}^n x_i", trailing_punctuation=".")`
3. `insert_caption(..., kind="Table", label_text="PAPER-16 round-trip test table")`
4. `insert_highlighted_note(..., mode="comment")` (→ `insert_word_comment`)

All three writer calls went through their real, unmocked
`_enforce_render_verification` gate and got back
`render_status=rendered / render_verified=true / render_backend=word-com` —
i.e. every fixture-building step was itself independently confirmed to open
in real Word before the round-trip experiment began.

**Round trip** (`roundtrip.py`): `win32com.client.DispatchEx("Word.Application")`,
`Documents.Open(work_path, ReadOnly=False, ConfirmConversions=False,
OpenAndRepair=False, ...)`, `doc.TrackRevisions = True`, append a sentence
via `doc.Content` collapsed to the end, `doc.TrackRevisions = False`,
`doc.Save()`, `doc.Close(False)`, `word.Quit()` — all inside a 90-second
watchdog thread modeled directly on `render_gate._word_com_render_thread`
(lines 406–507 of `render_gate.py`), so a hang would have been caught and
reported rather than blocking indefinitely. **It did not hang**: the worker
finished in 6.0 seconds.

**Diff** (`diff_roundtrip.py`): re-parsed both `word/document.xml` and
`word/comments.xml` before/after and compared paraIds, bookmarks,
SEQ/REF field instructions, OMML structural tags, comment references,
content-control count, table count, tracked-revision counts, full text,
namespace prefixes, and section-properties count.

## 2. Fixture matrix — construct × observed outcome

Legend: **preserved** = present and semantically unchanged after the round
trip; **normalized** = present but Word rewrote its representation without
changing meaning; **lost** = genuinely gone; **not exercised** = not built
into this session's fixture, reported from code inspection only.

| Construct | Outcome this session | Evidence |
|---|---|---|
| Body text content | **Preserved** | Full-text diff: pre-round-trip text is an exact prefix of post-round-trip text (the appended sentence is the only addition). |
| `w14:paraId` (paragraph identity) | **Normalized, not stable** | Every paragraph's `paraId` was rewritten by Word on save — including paragraphs the round trip never touched (e.g. the heading paragraph, `10000001` → `12C78080`). One paragraph (the caption, which `insert_caption` leaves with no `paraId` at all — see its own code comment, "newly inserted para has no w14:paraId yet") went from absent to a real Word-assigned `paraId`. |
| `w14:textId` | **Normalized, not stable** | Same pattern as `paraId`; most untouched paragraphs got the Word sentinel `77777777`, the newly-typed paragraph got a real fresh value. |
| Numbered-equation table (`insert_numbered_equation`'s 2-cell `<w:tbl>`) | **Preserved structurally** | Table count 1→1; `(1)` label text and OMML both survived; re-parsed correctly by `parse_docx_equations_local` after the round trip (`pattern='table-numbered', number='(1)', flat_text='∑i=1nxi'`). |
| OMML semantic structure (`m:sSub`/`m:sSubSup` nesting) | **Preserved** | `_equation_semantic_manifest`'s `structural_tags` was byte-identical before/after (`{'sSub': 1, 'sSubSup': 1}`), with zero `issues` either side. |
| OMML content fingerprint | **Normalized (content hash changes)** | Word added `m:sSubPr`/`m:sSubSupPr`/`m:ctrlPr`/`m:rPr`/`m:rFonts` (Cambria Math) property wrappers around every equation node on save. The manifest's per-entry fingerprint changed (`244ffea6…` → `7ceb4e69…`) despite identical `structural_tags`/`issues`. See §4 for the implication. |
| Manual plain bookmark | **Preserved by name** | `PAPER16_TESTBOOKMARK` present before and after; only its local `@w:id` (9001→1) was renumbered — the name, not the numeric id, is the stable identifier. |
| Caption's auto-generated `_Ref` cross-reference bookmark | **Preserved by name** | `_Ref100000000` present before and after; `@w:id` renumbered (100000000→2) the same way. |
| Caption SEQ field | **Preserved, form normalized** | `insert_caption` writes `<w:fldSimple w:instr="SEQ Table \* ARABIC">`; Word rewrote this into the full `fldChar begin / w:instrText / fldChar separate / cached result / fldChar end` complex-field form on save. The field instruction text itself (`SEQ Table \* ARABIC`) is unchanged. See §4 — this is a real risk for any reader that only scans `w:instrText` elements. |
| REF/PAGEREF/NOTEREF fields | **Not exercised** | None were built into this fixture. `move_section`/`copy_section` (code-read only this session) run `find_references_to` pre-write and repoint in-range `REF`/`PAGEREF`/`NOTEREF` targets at renamed bookmarks on copy — not empirically round-tripped through Word this session. |
| Word comment (`insert_word_comment` via `mode="comment"`) | **Preserved** | `word/comments.xml`'s single comment (id, author=`PAPER-16`, full text) is byte-identical before/after; the body's `w:commentReference` id is unchanged. |
| Comment companion parts | **Added by Word, not by Meridian** | `word/commentsExtended.xml`, `word/commentsIds.xml`, `word/people.xml` did not exist before the round trip; Word added all three on save, plus correct relationships in `word/_rels/document.xml.rels` and correct `Override` entries in `[Content_Types].xml`. Meridian's `insert_word_comment` writes only `word/comments.xml`. |
| Tracked revisions | **Preserved / correctly produced** | `doc.TrackRevisions=True` produced a real `<w:ins>` wrapping the typed run, with a genuine author name and UTC timestamp read from the local Word installation's identity (not a script-supplied value), plus the expected `<w:ins>` on the *preceding* paragraph's mark (standard Word semantics for inserting a new final paragraph). `w:ins`/`w:del` count: 0→2 (one on the new run, one on the preceding paragraph mark), 0 deletions. |
| Content controls (`w:sdt`) | **Not exercised** | No dedicated `docs_intel.py` writer creates one; `append_text_run_after_math` explicitly refuses to guess an insertion point inside `sdtContent` rather than risk it (docs_intel.py, near line 9973). Not built into this fixture. |
| Headers/footers | **Not exercised** | `set_page_header`/`set_page_footer` exist (docs_intel.py:16559, 16622) and carry the same `allow_degraded_render`/`degraded_render_reason` render-gate contract per code inspection, but were not built into this fixture or round-tripped. |
| Sections (`w:sectPr`) | **Preserved, content enriched** | Count 1→1. The pre-round-trip `<w:sectPr/>` was empty (hand-authored); Word filled in real `w:pgSz`/`w:pgMar`/`w:cols` values on save — additive normalization, not data loss. |
| Tables (other than the equation table) | Only the equation table existed in this fixture; count 1→1, unaffected. |
| Namespaces on `<w:document>` | **Normalized (Word adds its full standard set)** | Before: 3 prefixes (`w`, `w14`, `m`) — exactly what Meridian's writers declare. After: ~30 prefixes (`mc`, `r`, `wp`, `wps`, `wpg`, `w10`, `w15`, `w16*`, `cx1`–`cx8`, `aink`, `am3d`, `o`, `v`, `oel`, `wne`, `wpc`, `wpi`). This is normal Word save behavior, not evidence of a problem, but a byte-level "did anything change" diff must tolerate it. |
| Relationships / `[Content_Types].xml` | **Preserved and correctly extended** | Every pre-existing relationship/override survived; the three new comment-companion parts got correct new relationship ids and content-type overrides — Word's own additions are internally consistent. |
| Package-required parts (`[Content_Types].xml`, `_rels/.rels`) | **Preserved** | Both present before and after; this is also independently what `ooxml_integrity.py`'s required-parts gate checks on every Meridian write (see shared sprint context). |
| Source bindings / provenance metadata | **Not exercised** | Nothing in this fixture carried `artifact_provenance`-style binding metadata; not tested. |

## 3. A second, real Meridian write against the genuine Word-produced package

After the round trip, this session copied `after_roundtrip.docx` and called
`insert_highlighted_note(..., anchor_para_id="66513F85")` — one of the
**Word-regenerated** paraIds from §2, addressed correctly by first calling
`docs_intel.parse_docx` to read the new ids back out, exactly as a real
caller would have to after a human's Word session. This succeeded end to
end: `status=inserted, render_status=rendered, render_verified=true,
render_backend=word-com`. `check_render_capability` also independently
confirmed the Word-produced package itself still renders. This is concrete,
positive evidence that the fail-closed writer chain (`_execute_fail_closed_write`,
`ooxml_integrity`'s required-parts gate, and the render gate) works correctly
against a **genuinely Word-produced** package, not only against
Meridian-authored fixtures — provided the caller re-resolves paraIds after
any human Word session (§2's central finding).

## 4. Two load-bearing risks this session surfaced

1. **`anchor_para_id` addressing does not survive a human's Word session.**
   Every paraId in this fixture was rewritten by Word on save, including
   paragraphs nobody touched. Any caller (a saved plan, a cached graph
   node id, a prior extraction run) that stores a `w14:paraId` and expects
   to re-anchor a later Meridian write against it **must** treat that id as
   invalidated the moment a human has opened and saved the document in
   Word — this is not specific to any one writer, it applies to the entire
   `_find_para_by_id`-based addressing scheme used throughout
   `docs_intel.py`. This was not previously demonstrated in this project's
   docs with a live Word instance; it now is.
2. **Equation content fingerprints drift across a Word save even when the
   semantics do not.** `_equation_semantic_manifest`'s `structural_tags`
   (docs_intel.py:8003) is stable — it does not see Word's `Pr`/`ctrlPr`
   font-property wrappers as a structural change, and this session confirmed
   that directly. Its content **fingerprint** is not stable across the same
   save. `move_section`/`copy_section` (docs_intel.py:13505, 13858) compute
   baseline and post-write fingerprints from the *same* already-Word-touched
   document, so this was not observed to break either of those two
   functions in this session — but any future caller that persists a
   fingerprint from *before* a human's Word session and compares it
   *after* would see a false "changed" result. Flagged as an acceptance
   criterion in §7, not asserted as an existing bug (not tested against
   `move_section`/`copy_section` directly across a real round trip this
   session).

## 5. The render gate is a PDF-export capability probe, not a round trip

`render_gate.check_render_capability` (render_gate.py:754) and its Word-only
wrapper `check_word_com_render_receipt` (render_gate.py:680) — the gate
wired into `insert_equation_local`, `insert_numbered_equation`,
`edit_equation_local`, `remove_equation_local`, `insert_caption`,
`insert_highlighted_note`, `set_page_header`/`set_page_footer`, and
`insert_word_comment` via `_execute_fail_closed_write`/
`_enforce_render_verification` — opens the document with **`ReadOnly=True`**
and calls `doc.SaveAs(pdf_path, FileFormat=wdFormatPDF)`
(render_gate.py:406–507, `_word_com_render_thread`). It never saves the
document back as `.docx`. This is real, valuable evidence that the document
opens and renders in Word, but it is **not** evidence about round-trip
preservation, native editability after save, or what Word normalizes on
save — none of the existing test files exercise that path at all.
`test_docx_word_com_regression.py` and `test_section_equation_preservation.py`
were both read this session specifically to confirm this: every test in
both files either (a) monkeypatches `check_render_capability` and never
touches real Word, or (b) drives the real `check_render_capability` but only
through its `ReadOnly=True`/PDF-export path — never `Documents.Open(...,
ReadOnly=False)` followed by `Save()`. This session's `roundtrip.py` is new
automation, not a reuse of an existing round-trip harness, because no such
harness exists in the repository yet.

## 6. A concrete bug found in the shared test fixture

`test_docx_word_com_regression.py`'s `_write_word_authored_docx` (its
literal byte content — `_CONTENT_TYPES_XML`, `_ROOT_RELS_XML`,
`_DOCUMENT_XML`, `_DOCUMENT_RELS_XML`, `_STYLES_XML`, `_FONT_TABLE_XML`,
`_SETTINGS_XML`, `_WEB_SETTINGS_XML`, `_THEME_XML`, `_CORE_PROPS_XML`,
`_APP_PROPS_XML`, reproduced byte-for-byte and probed directly this
session, not paraphrased) is **rejected by real Word COM** with
`com_error: (..., 'Microsoft Word', 'The file appears to be corrupted.', ...)`.
Isolated by binary search across the fixture's parts: the cause is
`_THEME_XML`'s placeholder `<a:clrScheme name="Office"/>` and
`<a:fontScheme name="Office"/>` — both are schema-invalid DrawingML (the
real schema requires 12 named color children under `clrScheme` and
`majorFont`/`minorFont` children under `fontScheme`; the fixture supplies
neither). Substituting a fully-populated, schema-valid `theme1.xml` (same
document/styles/comments content, only the theme part changed) made the
otherwise-identical package open and render successfully via the same real
`word-com` backend (`status=rendered`). This means the four "real backend or
structural fallback" tests at the bottom of `test_docx_word_com_regression.py`
(`test_insert_caption_real_backend_or_structural_fallback`,
`test_insert_equation_real_backend_or_structural_fallback`,
`test_insert_highlighted_note_real_backend_or_structural_fallback`,
`test_word_authored_fixture_itself_is_structurally_valid`) — which explicitly
claim to exercise "a real backend IS available … render_status ==
'rendered' with real backend evidence, exercising the genuine automation
path end to end" — will, on any machine with genuine Word installed (this
one), instead take their own `FAILED` branch every time, never the
`RENDERED` branch, because the shared fixture cannot actually open in real
Word. The tests still pass (their `FAILED` branch asserts `render_status ==
FAILED` and restore-on-failure, which is genuinely what happens), so this is
not a test-suite regression — but the "real backend, rendered" branch of
those four tests has, as far as this investigation can tell, never actually
been exercised on real Word by anyone, on any machine that has genuine Word
installed, since the fixture was written. This was not a code edit — no
product or test file was modified this session — it is reported here as an
investigation finding for a future hardening pass to fix (regenerate
`_THEME_XML` with a schema-valid `clrScheme`/`fontScheme`, or switch the
fixture builder to a real Word/`python-docx`-produced theme part).

## 7. Fail-closed protection matrix (writers touched by this item)

Confirmed by direct code reading this session (extends, and narrows to
exact evidence, the shared-context summary of the prior session's PAPER-5/6
work):

| Writer | Structural post-write verify | Render-gate call | Uses `_execute_fail_closed_write` |
|---|---|---|---|
| `insert_equation_local` (8866) | Yes (`_verify_equation_write`, 8747) | Yes | Yes |
| `insert_numbered_equation` (9332) | Yes (`_verify_numbered_equation_write`, 9196) | Yes | Yes |
| `edit_equation_local` (9701) | Yes (`_verify_equation_edit_write`, 9641) | Yes | Yes |
| `remove_equation_local` (10070) | Yes (`_verify_equation_removal_write`, 10011) | Yes | Yes |
| `insert_caption` (6237) | Yes (`_verify_caption_write`, 6141) + optional `artifact_provenance` check | Yes | No — hand-duplicated equivalent sequence, predates the helper |
| `insert_highlighted_note` mode=inline (12507) | Yes (`_verify_note_write`, 12436) | Yes | No — hand-duplicated equivalent sequence |
| `insert_highlighted_note` mode=comment (12507) | Delegates to `insert_word_comment` (17153), which has its own gate | Yes (via delegate) | N/A (delegate) |
| `move_section` (13505) | Yes (`_verify_docx_write`, 3198 — structural counts + content hash + equation semantic manifest + bookmark-split pre-check) | **No** | No |
| `copy_section` (13858) | Yes (`_verify_docx_write`, 3198) + `_verify_image_ownership` | **No** | No |
| `insert_citation` (7368) | **No** | **No** | No |
| `insert_bibliography_entry` (10655) | **No** | **No** | No |

`move_section`/`copy_section` have real, substantial protection (structural
counts, content-hash of the moved/copied range, a semantic equation-manifest
comparison that rejects flattened OMML pre-move, bookmark-split detection,
reference-safety pre-checks, image-ownership post-checks) but confirmed by
code reading — **no call to `_enforce_render_verification` or
`check_render_capability` appears anywhere in either function** — their
return payloads carry no `render_status`/`render_verified`/`render_backend`
keys at all, unlike every equation/caption/note writer above. `insert_citation`
and `insert_bibliography_entry` have neither structural re-verification nor
a render gate; a caller gets back a `status=inserted` payload built purely
from in-memory intent, with no re-read-from-disk confirmation at all. This
matches and sharpens the shared-context note that "~10 more write functions
still have zero fail-closed protection" — this item confirms `insert_citation`
and `insert_bibliography_entry` by direct reading of their full bodies, and
confirms `move_section`/`copy_section` are structurally protected but
render-gate-blind.

## 8. Exact code and test pointers

- `extensions/meridian-docs/meridian_docs/docs_intel.py`
  - `_execute_fail_closed_write`: 3006–3137
  - `_verify_docx_write`: 3198
  - `_build_caption_paragraph`: 3712
  - `insert_caption`: 6237–6530
  - `_verify_caption_write`: 6141
  - `insert_cross_reference`: 7020
  - `insert_citation`: 7368–7444
  - `_equation_semantic_manifest`: 8003
  - `insert_equation_local`: 8866–9036
  - `_verify_equation_write`: 8747
  - `insert_numbered_equation`: 9332–9619
  - `_verify_numbered_equation_write`: 9196
  - `edit_equation_local`: 9701–9879
  - `_verify_equation_edit_write`: 9641
  - `remove_equation_local`: 10070–10191
  - `_verify_equation_removal_write`: 10011
  - `insert_bibliography_entry`: 10655–10753
  - `insert_highlighted_note`: 12507–12708
  - `_verify_note_write`: 12436
  - `move_section`: 13505–13851
  - `copy_section`: 13858–14392
  - `set_page_header` / `set_page_footer`: 16559–16618 / 16622
  - `insert_word_comment`: 17153
- `extensions/meridian-docs/meridian_docs/render_gate.py`
  - `_word_com_render_thread`: 406–507 (the `ReadOnly=True` / PDF-export-only
    watchdog pattern this session's `roundtrip.py` copied the shape of, but
    changed to `ReadOnly=False` + `Save()` for a real round trip)
  - `_word_com_render` / `_word_com_render_isolated` dispatch: 647–653
  - `check_word_com_render_receipt`: 680–690
  - `check_render_capability`: 754–847
- `extensions/meridian-docs/tests/test_docx_word_com_regression.py`
  - `_write_word_authored_docx`: 703–724 (schema-invalid theme part — §6)
  - Real-backend-or-fallback tests: 778–897
- `extensions/meridian-docs/tests/test_section_equation_preservation.py`
  - Pure-Python structural/semantic-manifest tests only, no live Word — read
    in full this session (125 lines).

## 9. Fail-closed acceptance criteria for a future hardening pass

1. **paraId re-resolution contract.** Any tool or workflow that persists a
   `w14:paraId` across a human-editing session boundary must document (and
   ideally enforce, e.g. by re-reading paraIds via `parse_docx` before
   reuse) that the id is not guaranteed stable across an intervening Word
   save. A gold-manifest/graph snapshot taken before a human edit needs an
   explicit re-anchoring or re-diff step, not a raw paraId lookup, before
   any subsequent Meridian write.
2. **Field-code reader must handle both `w:fldSimple` and complex-field
   forms.** Any code that scans for `SEQ`/`REF`/`PAGEREF`/`NOTEREF`
   instructions by looking only at `w:instrText` elements will silently miss
   a field that Meridian wrote as `w:fldSimple` and that has not yet been
   touched by Word. `find_references_to`/`scan_citation_keys`-style readers
   should be audited for this specifically (not done this session — reading
   their full bodies was out of scope for this item's fixture).
3. **Equation-fingerprint comparisons must not cross a Word-editing session
   boundary without normalization.** If any future feature persists an
   equation fingerprint (or reuses `_equation_semantic_manifest`'s
   fingerprint field) to detect drift between two points in time that might
   span a human Word session, it must compare `structural_tags`/semantic
   content, not the raw fingerprint, or must re-derive both sides fresh from
   documents that have been through the same normalization pass.
4. **`move_section`/`copy_section` render-gate parity.** These two functions
   have real structural protection but no render-capability gate at all,
   unlike every equation/caption/note writer. Before either is promoted to a
   "safe to run unattended" tier, decide explicitly whether they need
   `_enforce_render_verification` too (a section move/copy can, in
   principle, produce a structurally-valid-but-Word-rejects-it document the
   same way §6's fixture did) or whether their existing structural checks
   are considered sufficient — this was not decided in this investigation.
5. **`insert_citation`/`insert_bibliography_entry` fail-closed retrofit.**
   Confirmed (not assumed) to have zero post-write verification and zero
   render-gate coverage. These are the two most schema-fragile writers in
   the file (hand-built complex-field XML for citations; heading-detection
   plus paragraph-range splicing for bibliography entries) and are prime
   candidates for the next `_execute_fail_closed_write` retrofit, following
   the exact pattern already applied to `edit_equation_local`/
   `remove_equation_local` in this sprint.
6. **Regenerate `_write_word_authored_docx`'s theme part.** §6's fixture bug
   should be fixed (schema-valid `clrScheme`/`fontScheme`, or a
   `python-docx`-produced theme) so the "real backend" branch of its four
   dependent tests can actually execute on a machine with genuine Word, not
   only the `FAILED` branch it has silently been exercising instead.
7. **A real open→edit→save round-trip test does not exist yet.** `roundtrip.py`
   from this session (archived under
   `E:\MeridianData\ooxml-graph-paper\renders\word-roundtrip-preservation-20260826\`)
   is a candidate starting point for a genuine pytest-integrated round-trip
   regression test, gated the same way the existing "real backend or
   structural fallback" tests are (branch on the real observed
   `check_render_capability`/equivalent status rather than assuming
   availability), but it is not currently wired into the test suite — doing
   so is implementation work, out of scope for this investigation-only item.

## 10. Non-goals / explicitly not claimed

- This is not a statistically representative sample of DOCX documents — one
  small fixture, one round trip, one machine, one Word build.
- No claim is made about LibreOffice round-trip behavior; LibreOffice is not
  installed on this host (confirmed again this session via
  `render_gate.detect_backend`, which reported only `word-com` available).
- `edit_equation_local`, `remove_equation_local`, headers/footers, content
  controls, REF/PAGEREF/NOTEREF fields, and `move_section`/`copy_section`
  were **not** driven through a real Word round trip this session — every
  claim about them above is explicitly labeled as code-inspection-only in
  §2/§7, not empirically observed.
- No product code (`docs_intel.py`, `render_gate.py`, `ooxml_integrity.py`,
  or any test file) was modified this session, per this item's
  investigation-only scope.

## 11. Artifacts

- Probe manifest: `E:\MeridianData\ooxml-graph-paper\manifests\word-roundtrip-preservation-probe-20260826.json`
- Fixture, round-trip output, scripts, and raw diff/reparse output:
  `E:\MeridianData\ooxml-graph-paper\renders\word-roundtrip-preservation-20260826\`
  (`before_roundtrip.docx`, `after_roundtrip.docx`,
  `after_second_meridian_write.docx`, `build_fixture.py`, `roundtrip.py`,
  `diff_roundtrip.py`, `manifest_and_reparse_output.txt`)

Sources consulted: `docs/runtime-capability-contract-v0.md`,
`docs/comparator-contract-v0.md`, `docs/graph-gold-schema-v0.md`,
`docs/checkpoint-2026-08-25.md`, `docs/dataset-landscape-2026-08-25.md`,
`extensions/meridian-docs/meridian_docs/docs_intel.py`,
`extensions/meridian-docs/meridian_docs/render_gate.py`,
`extensions/meridian-docs/tests/test_docx_word_com_regression.py`,
`extensions/meridian-docs/tests/test_section_equation_preservation.py`,
`E:\MeridianData\ooxml-graph-paper\manifests\meridian-equation-word-probe-20260826.json`,
`E:\MeridianData\ooxml-graph-paper\manifests\word-render-probe-20260826.json`.
