# OOXML package safety, graph integrity, and concurrency failure contract — audit v0

Status: investigation only. No product code was changed to produce this document. All findings below were
produced by (a) reading the cited functions in the parent monorepo with Serena/`meridian-extract` and `Read`,
and (b) running small, self-contained Python probes against the project's own `pixi` `default` environment
(`C:\Users\13144\Documents\Meridian\repository\.pixi\envs\default\python.exe`, Python 3.12.13, lxml 6.1.1 /
libxml2 2.15.3 — the same interpreter and library versions `extensions/meridian-docs` runs under). Every
empirical claim below states what was actually run and what came back; nothing here is inferred from
documentation alone where a runnable check was feasible. This document extends
`docs/graph-gold-schema-v0.md`, `docs/runtime-capability-contract-v0.md`, and `docs/comparator-contract-v0.md`
in this same subproject — it does not duplicate or contradict them; §4's duplicate-`w14:paraId` finding is a
direct gap against the invariant already stated in `graph-gold-schema-v0.md` §"Required invariants" item 4.

Scope: `extensions/meridian-docs/meridian_docs/docs_intel.py` (~21,003 lines) and
`extensions/meridian-docs/meridian_docs/ooxml_integrity.py` (429 lines), read-only. Test files read for
existing-coverage cross-reference: `test_docx_write_integrity.py`, `test_5988a5bb_docx_intel_concurrent_write_envelope.py`,
`test_docx_namespace_preservation.py`, `test_827b6bdc_duplicate_para_id.py`, plus (found while cross-checking
equation write paths) `test_docx_equation_fail_closed_contract.py` and `test_docx_numbered_equation_writer.py`.
All paths below are relative to `C:\Users\13144\Documents\Meridian\repository\` unless stated otherwise.

## Executive summary

| # | Topic | Status | Severity of gap |
|---|---|---|---|
| 1 | Malformed ZIP container | Partially protected | Medium |
| 2 | Malformed XML (per-part) | Well protected | Low |
| 3 | Relationship / content-type orphans | Well protected | Low |
| 4 | Duplicate `w14:paraId` | Detected, not enforced | Medium |
| 4b | Duplicate ZIP member names (same part name twice) | Unprotected | Medium |
| 5 | Namespace loss on write-back | Well protected | Low |
| 6 | Stale sidecar (index db) | Partially protected | Low–Medium |
| 7 | Path traversal in package part names | Protected by design | Informational |
| 8a | XXE — external entity file disclosure | Not vulnerable (verified) | None |
| 8b | XML entity expansion (billion laughs / quadratic blowup) | Unprotected (verified) | Medium |
| 9 | Lock / CAS / concurrency / backup machinery | Strong same-process, weak cross-process | Medium–High |

---

## 1. Malformed ZIP container handling

**Protected today.** The primary load path, `_load_docx_xml_stdlib` (`docs_intel.py:1764-1809`), wraps
`zipfile.ZipFile(io.BytesIO(raw))` in `try/except zipfile.BadZipFile` and re-raises as `ValueError(f"not a
valid .docx (not a ZIP): {path}")`. `validate_docx_package` (`ooxml_integrity.py:231-313`) does the same at
entry and additionally runs `archive.testzip()` to catch CRC failures on individual members
(`ooxml_integrity.py:239-241`). `_atomic_write_docx_bytes`'s post-write verification
(`docs_intel.py:2315-2517`, the `except (zipfile.BadZipFile, KeyError)` branch at `docs_intel.py:2406-2412`) re-opens the
*staged* file fresh off disk and rejects promotion if it isn't a valid ZIP after the flush.

**Gap.** `zipfile.BadZipFile` is a plain `Exception` subclass, not `OSError` — it is *not* caught by the "~25
existing `except OSError as exc: return {"error": ...}` guards" that `DocxWriteVerificationError`'s own
docstring (`docs_intel.py:1820-1826`) says protect most call sites. A direct count: `docs_intel.py` opens
`zipfile.ZipFile(` 34 times but only catches `zipfile.BadZipFile` locally at 15 of those sites (grep counts,
2026-08-26). This was **not** verified call-site-by-call-site (the file is ~21k lines; that would need its own
pass) — but the raw ratio means it is plausible that roughly half the ZIP-opening call sites let a malformed
ZIP raise an uncaught `BadZipFile` out of an MCP tool handler (a raw traceback rather than a typed
`{"error": ...}` response) rather than fail closed gracefully. This is inconsistency, not silent corruption —
worst case is an ugly error instead of a clean one — hence Medium, not High.

**Fixture idea:** a `.docx`-named file that is valid-looking (correct PK signature) but has its central
directory truncated or its EOCD record corrupted, fed to each of the non-`_load_docx_xml_stdlib` entry points
(e.g. `remove_package_part`, `insert_media_part`, any function calling `_docx_zip_entries`) to catalogue which
ones raise `BadZipFile` uncaught vs. return `{"error": ...}`. A companion fixture: a byte-for-byte truncated
real `.docx` (cut off mid-ZIP) exercises the same class of failure with a more realistic corruption shape than
a hand-built bad EOCD.

## 2. Malformed XML (per-part) handling

**Well protected.** Three independent layers:
- Load: `_load_docx_xml_stdlib` catches `ET.ParseError` on `word/document.xml` and re-raises `ValueError`
  (`docs_intel.py:1798-1801`).
- Package-wide: `validate_docx_package` parses *every* `.xml`/`.rels` member (`_xml_parts`,
  `ooxml_integrity.py:181-182`) with `ET.fromstring`, reporting `xml_parse_error` per part
  (`ooxml_integrity.py:246-249`).
- Write-time: `_atomic_write_docx_bytes` re-reads every `changed_parts` member fresh from the *staged* file and
  parses it with `ET.fromstring` (`docs_intel.py:2452-2471`, the parse itself at line 2469), rejecting promotion
  on `ET.ParseError` via the `xml_parse_errors` raise at `docs_intel.py:2483-2495`. The comment at
  `docs_intel.py:2432-2451` explains exactly why the structural-manifest counts alone would miss this: an
  unparsable part is silently counted as "0 elements" rather than raising.

**Residual gap (low, not deeply audited).** The changed-parts well-formedness check only fires for parts a
caller explicitly lists in `changed_parts`. Multi-part writers built by raw text splicing
(`_insert_before_symbol`-style byte splicing, e.g. `_insert_before_closing_tag`, referenced in the comment at
`docs_intel.py:2444-2449`) are exactly the case this exists for; whether *every* such writer actually passes
its changed part names into `changed_parts` was not individually re-verified for all ~30+ write primitives in
this pass.

## 3. Relationship and content-type orphans

**Well protected, and — this is the notable finding — actually wired into every promoted write, not just
exposed as an opt-in audit tool.** `validate_docx_package` checks, per package:

- `dangling_relationship`: every non-`External` `Relationship/@Target` in every `.rels` part must resolve
  (via `_resolve_target`, `ooxml_integrity.py:177-178`) to a part that exists in the archive
  (`ooxml_integrity.py:203-204`).
- `duplicate_relationship_id`: two `Relationship` elements in the same `.rels` part sharing an `Id`
  (`ooxml_integrity.py:205-207`).
- `dangling_relationship_reference`: an `r:id`/`r:embed` attribute anywhere in a content part whose value
  isn't a declared relationship `Id` in that part's `.rels` (`ooxml_integrity.py:263-267`).
- `missing_content_type` / `dangling_content_type`: every package member needs a `[Content_Types].xml`
  `Default`/`Override` entry, and every `Override` must point at a real part (`_content_type_issues`,
  `ooxml_integrity.py:212-228`).

The reason this is more than a standalone audit function: `_atomic_write_docx_bytes` (`docs_intel.py:2315-2517`)
unconditionally calls `ooxml_integrity.normalize_word_comment_attributes(payload)` as the first statement in its
try block (`docs_intel.py:2371-2376`), and that function *always* re-serializes `word/document.xml` (a required
part present in every valid `.docx`) into its own `changed` dict regardless of whether any legacy comment
attribute actually needed fixing (`ooxml_integrity.py:406-418`), so the `if not changed: return raw` early-out
(`ooxml_integrity.py:419-420`) is effectively dead for real documents. That means `validate_docx_package(result)`
(`ooxml_integrity.py:426`) runs on the **full post-edit package** on essentially every promoted write, and
raises `DocxPackageIntegrityError` — which `_atomic_write_docx_bytes` converts to `DocxWriteVerificationError`
(`docs_intel.py:2377-2381`) — if any of the above are present, *including issues that were already in the
source document before this particular edit* (since every unchanged part is copied byte-for-byte into
`result`). This is a genuinely strong gate and should be credited as such; it was not obvious without reading
both files together.

**Caveat that matters for §4:** `validate_docx_package`'s `ok` flag is computed from `issues` only
(`ooxml_integrity.py:311`, `"ok": not issues`); the `warnings` list (which is where duplicate `w14:paraId` and
heading-capitalization findings live) never blocks a write.

**Fixture idea:** a `.docx` whose `word/_rels/document.xml.rels` declares an `Id` used by an `r:id` in
`word/document.xml` but the `.rels` entry's own `Target` points at a part that was deleted from the ZIP (a
genuine dangling relationship), run through any write primitive that ends up promoting through
`_atomic_write_docx_bytes` — expected: `DocxWriteVerificationError`, `dest` untouched. A second fixture: same
setup but read-only (e.g. `document_outline`/`get_structure`) to confirm whether read paths surface the same
issue or silently ignore it (read paths do **not** call `validate_docx_package` at all — see §8's read-path
note).

## 4. Duplicate `w14:paraId` handling

**Detected in two independent places, blocking in neither.**

1. `validate_docx_package` collects every `w14:paraId` on every `w:p` in `word/document.xml`, counts
   duplicates with `collections.Counter`, and reports them as a **warning**, not an issue:
   `warnings.append(PackageIssue("duplicate_para_id", ..., "warning"))` (`ooxml_integrity.py:274-278`). Per §3,
   warnings never flip `ok` to `False`, so a document with duplicate paraIds is promoted normally through
   `_atomic_write_docx_bytes`.
2. `docs_intel.py` has its own, separate duplicate-detection surfaced at *read/index* time — confirmed covered
   by `test_827b6bdc_duplicate_para_id.py` (`test_vendored_document_content_tree_reports_duplicate_native_para_id`,
   `test_index_docx_structure_surfaces_duplicate_para_ids`, etc.). This is informational (surfaced to a caller
   who asks), not a write gate.

Separately, `_existing_para_ids` (`docs_intel.py:11441-11448`) — used by `_new_para_id`
(`docs_intel.py:11451-11459`) to mint fresh, collision-free IDs for clones/inserts — builds a Python `set` of
every paraId currently in the document. A `set` silently collapses duplicates; this function does not itself
detect or report that the input already contained duplicates, it only uses the deduplicated result as the
"taken" pool for new IDs. So minting new IDs never *introduces* a collision, but nothing in the mint path
*rejects* a document that already has one on input.

**Why this matters beyond docs_intel.py itself:** `docs/graph-gold-schema-v0.md` (this same subproject)
already states, as invariant 4 under "Required invariants": *"A successful write cannot promote a document
with duplicate IDs, malformed OMML containers, unresolved required references, or a stale render receipt."*
Malformed-OMML and unresolved-references are enforced (per the shared sprint context: `_validate_omml_structure`
hardening, and §3's dangling-relationship-reference check above). Duplicate-ID is not — this audit found the
exact place the contract's own invariant is unenforced. Severity Medium: this is not attacker-exploitable in
the security sense, but it is a documented product-contract gap with a graph-fidelity consequence (a paragraph
identity that resolves ambiguously breaks the "exact-match rate for paragraph identity" metric the
comparator contract, §3 "Structural correctness", commits to reporting).

**Fixture idea:** two `<w:p w14:paraId="00000001">` elements in `word/document.xml` (different text content, so
it's unambiguous this isn't a legitimate clone-with-fresh-id), run through (a) `validate_docx_package` directly
— expect `ok: True` with a `duplicate_para_id` warning (current behavior, to pin down as a regression baseline)
and (b) any write primitive that promotes the document unchanged (e.g. `edit_caption` on an unrelated
paragraph) — expect (current behavior) the duplicate to survive the round-trip untouched and unflagged as a
promotion blocker. A future hardening item would flip (b) to a fail-closed `DocxWriteVerificationError` by
promoting `duplicate_para_id` from `warnings` to `issues` — but that is a product-code decision outside this
investigation's scope.

## 4b. Duplicate ZIP member names (adjacent to path traversal, §7)

**Unprotected, and empirically verified to have concrete divergent-resolution behavior.** Nothing in
`validate_docx_package` or anywhere else checks whether `archive.namelist()` contains a repeated name (e.g. two
ZIP entries both literally named `word/document.xml`, which the ZIP format permits and does not itself
forbid). A probe against the project's own `pixi default` `zipfile` (Python 3.12.13) confirmed:

- `zipfile.ZipFile.read("word/document.xml")` and `.getinfo(...)` always resolve to the **last** entry with
  that name (`header_offset` of the second-written entry, not the first).
- `archive.testzip()` returns `None` (no error) for a package containing the duplicate — it is not treated as
  corruption.
- `docs_intel.py`'s own `_docx_zip_entries` helper (`docs_intel.py:4990-5002`, `entries[info.filename] =
  source.read(info.filename)`) collapses the duplicate into a single dict entry holding the *last* occurrence's
  bytes — the first occurrence's content is silently discarded with no warning.
- `_save_docx_xml_stdlib`'s repack loop (`docs_intel.py:2298-2304`, `for info in infos: data =
  src.read(info.filename); dst.writestr(info, data)`) does **not** remove the duplicate on write-back: both
  original `ZipInfo` entries are re-written to the output archive, and because `src.read(info.filename)`
  resolves by name (always the last duplicate) for *both* iterations, the repacked archive still has two
  members named `word/document.xml`, now both holding what used to be only the second entry's content. The
  ambiguity is preserved across a Meridian write, not healed by it.

This is not classic path traversal (§7 is genuinely well-protected), but it is the same family of concern the
task asked about ("relationship/content-type orphans... package part names"): a maliciously crafted `.docx`
could contain, say, two `word/document.xml` entries — an innocuous-looking one and a distinct
attacker-authored one — and rely on some consumer (this codebase, Word's own OPC reader, or another tool in
the pipeline) resolving "first" while another resolves "last". **This investigation did not test what Microsoft
Word itself does with a duplicate-named part** — that would require an actual Word COM round-trip, which is
out of scope for this investigation item — so the cross-consumer divergence is a plausible risk grounded in
Python's own documented resolution rule, not a confirmed Word-specific exploit. Flagged Medium pending that
follow-up.

**Fixture idea:** a `.docx` built with two `word/document.xml` ZIP entries (via `zipfile.ZipFile.writestr`
called twice with the same name, exactly as the probe script above did — `zf.writestr("word/document.xml",
b"...")` twice), containing visibly different paragraph text in each, run through: (a) `validate_docx_package`
— expect (current behavior) `ok: True`, no issue or warning raised at all; (b) `_load_docx_xml_stdlib` — expect
it to silently load whichever `zipfile` resolves as "last"; (c) — if Word availability allows per the sprint's
render-capability notes — open the same fixture in Word via COM and record which entry Word displays, to settle
the divergence question empirically in a later item.

## 5. Namespace loss on write-back

**Well protected — this is the most mature area of the four topics checked against existing tests.** The
"b17ef22b" design (docstring of `_save_docx_xml_stdlib`, `docs_intel.py:2229-2263`):

- `_root_namespace_declarations` (`docs_intel.py:2054-2075`) extracts every namespace prefix the *original*
  `word/document.xml` actually declared, straight from its source bytes via `ET.iterparse`'s own
  namespace-scope tracking (lexically faithful, not via ET's own prefix-renumbering serialization).
- `ooxml_integrity.serialize_document_xml_preserving_namespaces` (`ooxml_integrity.py:316-338`) re-parses both
  the original and the ET-mutated tree with **lxml** (not stdlib ET, which cannot preserve arbitrary prefixes
  such as `ns10` on serialization — see the module docstring at `ooxml_integrity.py:1-8`), builds the output
  root with the *original* `nsmap`, and self-verifies (`if LET.fromstring(result).nsmap != nsmap: raise
  DocxPackageIntegrityError(...)`, `ooxml_integrity.py:331-332`) before returning.
- `_assert_namespace_prefixes_preserved` (`docs_intel.py:2159-2198`) and
  `_assert_mc_ignorable_prefixes_declared` (`docs_intel.py:2201-2226`) run after re-parsing the serialized
  result (call sites at `docs_intel.py:2293-2294`) and raise `DocxWriteVerificationError` — fail-closed, before
  any bytes are staged to disk — if a prefix was renamed or if `mc:Ignorable` ends up referencing an undeclared
  prefix.

Existing test coverage in `test_docx_namespace_preservation.py` directly exercises: unmodified round-trip
preserves all original prefixes; a custom element prefix used only in the body survives; `mc:Ignorable`
value/validity survives; a real write path through `insert_caption` preserves namespaces end-to-end; `mc:Ignorable`
referencing an undeclared prefix fails closed; a namespace-prefix rename is caught and fails closed (defense in
depth); malformed serialization fails closed. That is real breadth, not just a happy-path test. No gap
identified here beyond the general "not every one of the ~30+ write primitives was traced individually to
confirm it truly always calls `_save_docx_xml_stdlib` / `_save_docx_with_new_parts_stdlib` rather than some
other, older serialization path" — this audit did not attempt that exhaustive trace given the file's size.

## 6. Stale sidecar (index db) handling

**Partially protected, mtime-only, no cross-process write lock beyond SQLite's own default.**

`check_staleness` (`docs_intel.py:919-945`) compares a `source_mtime` value stamped into the
`docx_index_meta` table at index time (`index_docx`, `docs_intel.py:960-1002`, comment at 990-995) against
`os.stat(source_path).st_mtime` right now (`_stat_mtime`, referenced at `docs_intel.py:940`). `_ensure_fresh`
(`docs_intel.py:948-957`) is the read-side hook: if `check_staleness` reports `stale=True` and a `source_path`
is tracked, it transparently calls `index_docx` again before serving a read.

Gaps, none of them exploitable in a security sense but all real correctness edges:
- **mtime-only, no content hash.** Two different byte-for-byte contents that happen to share an mtime (e.g. a
  file restored from a backup that preserves timestamps, or a filesystem with coarse mtime resolution) would
  report `stale=False` and serve the old cached index against new content. The gold-manifest schema
  (`docs/graph-gold-schema-v0.md`) already tracks `source_sha256` for gold records; the sidecar index does not
  use the equivalent for its own staleness signal.
- **Bytes-sourced indexes have zero staleness tracking, by explicit design** (`reason: "no-source-tracked"`,
  `docs_intel.py:938`) — documented behavior, not a bug, but worth restating here since "stale sidecar handling"
  was explicitly asked about: if the caller only ever passes raw bytes (never a file path) to `index_docx`, no
  later read can ever detect that a "newer" version of that content exists elsewhere.
- **TOCTOU window in `_ensure_fresh`.** Between `check_staleness`'s read and the triggered `index_docx` call, a
  concurrent writer could land another change; the read that follows would still reflect whichever generation
  won that race, with no re-check loop. Low impact — the next read would simply re-trigger the same check.
- **No busy-timeout tuning.** `_connect` (`docs_intel.py:753-908`) sets `PRAGMA journal_mode=WAL`
  (`docs_intel.py:761`, comment 753-759 explaining why) but does not set `sqlite3.connect(..., timeout=...)` or
  `PRAGMA busy_timeout`, so concurrent writers rely entirely on Python's `sqlite3` module default (5.0s) before
  a `sqlite3.OperationalError: database is locked` surfaces. Whether every `index_docx` caller catches that
  specific exception type was not verified in this pass.

**Fixture idea:** an index built against a real file, then the file's content replaced (different bytes) while
forcing the new mtime to equal the old one (e.g. `os.utime(path, (old_atime, old_mtime))` right after the
rewrite) — expected current behavior: `check_staleness` reports `stale=False`, `reason: "current"`, and a
subsequent read serves the stale cached paragraphs. A second fixture: two processes calling `index_docx` on the
same `index_db_path` at the same moment with WAL mode on, to see whether the default 5s busy timeout is
sufficient in practice or whether a slow delta-update can still surface `database is locked` to a caller.

## 7. Path traversal risk in package part names

**Protected by design — the strongest "nothing to fix" finding in this audit.** No call to
`zipfile.ZipFile.extractall()` or `.extract()` exists anywhere in `extensions/meridian-docs` (confirmed by
grep across the whole package directory, zero matches). Every write path repacks the archive **wholesale**,
in memory, into a fresh `zipfile.ZipFile(io.BytesIO(), "w")`, using either (a) the original `ZipInfo` objects
re-read by their own name from the source archive (`_save_docx_xml_stdlib`, `docs_intel.py:2298-2304`), or (b)
hardcoded/derived logical names such as `f"word/{target}"` or a `"word/media/"`-prefixed name
(`docs_intel.py:4233-4235`, `5359-5368`). Relationship-target resolution (`_resolve_target`,
`ooxml_integrity.py:177-178`; `_rel_target_part_name`, `docs_intel.py:5005-5026`) only ever produces a
**string key** compared against the archive's own `namelist()`/`entries` dict — it is never joined onto a real
OS directory. Concretely: a relationship `Target="../../../../etc/passwd"` normalizes (via
`posixpath.normpath`) to `"../../../etc/passwd"` — a relative string with leading `..` segments that can never
equal any real ZIP member name — so it surfaces as a `dangling_relationship` **issue** (blocking, per §3's
write-time gate), not an escape. Because the OOXML package is never extracted member-by-member onto disk, the
classic "zip-slip" vulnerability class (crafted entry name writes outside an intended extraction directory)
does not apply to this codebase's write path at all.

`remove_package_part` (`docs_intel.py:5299-...`, the guard at `5358-5368`) does its own `part_name.strip().lstrip("/")`
normalization and requires a literal `"word/media/"` string prefix — a value like
`"word/media/../../../secret"` would pass that literal prefix check, but since it is only ever used as a
dictionary-key lookup against `entries` (never `os.path.join`ed onto a real path), it can only match a ZIP
member that is itself named with that exact literal `..`-containing string — which is exactly the §4b duplicate/
odd-name concern, not a filesystem traversal.

No fixture needed for this topic beyond re-confirming the negative on any future refactor (i.e., a regression
test that fails loudly if `extractall`/`.extract(` is ever introduced anywhere in this package would be cheap
insurance — see the failure-injection ideas list at the end).

## 8. XML external entity (XXE) risk

Genuine, empirically checked question, run against the exact interpreter/lxml this extension ships with.
Probe script: `xxe_probe.py` (kept in this session's scratchpad, not committed — reproducible from the payloads
quoted below). Two payloads, each run through both parsers with **default** settings (no explicit `XMLParser`
configuration anywhere in either file — confirmed by reading both files' full import lists: `docs_intel.py:37-59`
has `import xml.etree.ElementTree as ET` and no `defusedxml`; `ooxml_integrity.py:9-23` has both
`xml.etree.ElementTree as ET` and, guarded by a bare `try/except ImportError`, `from lxml import etree as LET`
— also no `defusedxml`).

### 8a. External SYSTEM entity (classic XXE file disclosure) — **not vulnerable**

Payload: a `word/document.xml`-shaped document with
`<!DOCTYPE w:document [<!ENTITY xxe SYSTEM "file:///...">]>` and `&xxe;` referenced in a `<w:t>` run.

- `xml.etree.ElementTree.fromstring(payload)` → `ParseError: undefined entity &xxe;: line 6, column 25`. The
  external entity is never resolved; the local file's content never reaches the parsed tree.
- `lxml.etree.fromstring(payload)` (the exact call `serialize_document_xml_preserving_namespaces` makes on the
  *untrusted original* `word/document.xml` bytes, `ooxml_integrity.py:320`) → `XMLSyntaxError: Entity 'xxe' not
  defined, line 6, column 31`. Same outcome: not resolved.

Both stdlib `ElementTree` and lxml's plain `etree.fromstring()` (no explicit `resolve_entities`/`no_network`
parser configuration) refuse the external entity out of the box on this environment's versions. **No
`defusedxml` or equivalent guard exists anywhere in the pipeline** (confirmed absent from both files and not
installed in the `pixi default` env — `import defusedxml` raised `ImportError` in the probe) **and none is
currently needed for this specific vector**, given the versions in use. This should not be read as a permanent
guarantee — it is a property of the currently pinned Python/lxml versions, not of the code — but as of this
investigation, file-disclosure-via-XXE is not reproducible against this pipeline.

### 8b. Internal entity expansion (billion laughs / quadratic blowup) — **vulnerable, unmitigated**

Payload: 5 internal `ENTITY` declarations, each referencing the previous one 10 times (`&a0;` through `&a4;`,
final expansion `&a4;` in a `<w:t>` run) — a deliberately small-scale version of the classic attack to keep the
probe itself cheap regardless of outcome.

- `xml.etree.ElementTree.fromstring(payload)` → succeeds, no error, expands to 60,004 characters (10⁴ repeats
  of the 6-character base string, plus markup) with no size or depth check anywhere in the call path.
- `lxml.etree.fromstring(payload)` → same outcome, also 60,004 characters, also no error.

Neither parser rejected or capped this expansion at the tested scale. This matches Python's own documented
classification of `xml.etree.ElementTree` as vulnerable to billion-laughs/quadratic-blowup (unlike external
entity/DTD retrieval, which it documents as not vulnerable — consistent with §8a's empirical result). **This
investigation deliberately did not run a full-scale billion-laughs payload** (the classic form nests ~9 levels
at ×10 each for ~10⁹ amplification) to avoid actually exhausting memory/CPU on the investigation host — the
5-level/10⁴ probe is enough to demonstrate the absence of any guard, without demonstrating the full blast
radius. A future hardening item should measure the actual ceiling (libxml2 has historically had *some*
amplification-ratio protections baked into recent versions — this was not independently confirmed for
2.15.3 here) rather than assume unbounded blowup.

**Why this matters concretely:** this is not a hypothetical "some XML parser somewhere" — `word/document.xml`
from an attacker-supplied `.docx` reaches `ET.fromstring` on **every** load (`_load_docx_xml_stdlib`,
`docs_intel.py:1797`) and on dozens of other `archive.read(...)` sites throughout both files (`ET.fromstring`
appears at `ooxml_integrity.py:243`, `256`, `280`, `288`, `342`, and many more in `docs_intel.py`), and reaches
`LET.fromstring` on every write-back (`ooxml_integrity.py:320`, operating on the *original*, attacker-supplied
bytes, not the mutated tree). None of these call sites impose a size or nesting limit before parsing. A crafted
`.docx` opened purely for **reading** (e.g. via `document_outline`, `get_structure`, `index_document_structure`)
never touches the write pipeline's protections at all (§3, §4) — read paths have no equivalent gate — so this
is the one finding in this audit where the read-only surface, not just the write surface, is exposed.

**Fixture idea:** a `.docx` whose `word/document.xml` embeds a proper billion-laughs `DOCTYPE` (9 levels, ×10
each) sized to reliably trip a bounded-memory test harness (e.g. run under a subprocess with an RSS or
wall-clock cap, expecting the parse to either be rejected by a future guard or to be the thing that trips the
harness's own limit) — fed through `_load_docx_xml_stdlib` and, separately, through
`serialize_document_xml_preserving_namespaces`, to confirm both call sites are affected identically. The fix
direction (not implemented here, per this item's `document_only` scope) would be switching to `defusedxml`'s
`ElementTree` for the stdlib path and constructing an explicit `lxml.etree.XMLParser(resolve_entities=False,
no_network=True, huge_tree=False)` for the lxml path, rather than relying on `fromstring`'s defaults.

## 9. Lock / CAS / concurrency / backup machinery

**Strong same-process guarantees, explicitly-acknowledged-but-only-partially-mitigated cross-process gap.**

- `_docx_promotion_lock(dest)` (`docs_intel.py:1864-1876`) returns a `threading.RLock` from a process-global
  dict keyed by `os.path.normcase(os.path.abspath(dest))` (`docs_intel.py:1870-1875`), lazily created under a
  separate guard lock (`_DOCX_PROMOTION_LOCKS_GUARD`, a plain `threading.Lock`, `docs_intel.py:1861`). The
  module comment directly above it (`docs_intel.py:1834-1859`) is unusually explicit about scope: two threads
  in the *same process* can never interleave a stage→verify→promote cycle for the same destination path (RLock,
  reentrant since 5988a5bb so a caller doing its own extra verification can hold the lock across the whole
  sequence, not just the promote step) — but a lock is process-local by construction, so this provides **zero**
  protection against a second OS process (a second Meridian worker, a second CLI invocation, or even Word
  itself) promoting to the same `dest` in that window. The comment says so directly: *"It does NOT — and
  structurally cannot... protect against a DIFFERENT process promoting to the same dest in that window."*
- The actual filesystem swap is `os.replace(staged_path, dest)` (`docs_intel.py:2504`), which is atomic on the
  same filesystem — so a reader can never observe a torn/partially-written file, regardless of how many writers
  race. What is *not* protected is which writer's content ends up as the final state.
- **No cross-process lock primitive exists anywhere in this file** — confirmed by grep for `filelock`,
  `msvcrt`, `fcntl`, `O_EXCL`, `flock`, `portalocker`: zero matches in `docs_intel.py`.
- The stated cross-process mitigation is `_safe_restore_after_verification_failure`
  (`docs_intel.py:2779-2833`), a compare-and-swap check gating `_restore_docx_backup`: it re-reads `dest`'s
  *current* on-disk SHA-256 and compares it against `promoted_sha256` (the fingerprint of exactly what *this*
  writer promoted, always computed in `_atomic_write_docx_bytes` — `docs_intel.py:2401` —
  regardless of whether `pre_manifest` was supplied). Three outcomes, precisely documented in the function's own
  docstring: safe-to-restore (nobody touched `dest` since this writer's own promotion), positive
  cross-writer-detected (fingerprints differ — refuses to restore, correctly leaving the other writer's work
  alone), or indeterminate (missing fingerprint data — fails closed, no restore, not reported as a confirmed
  clobber). This is real, working protection, but it activates **only** on the specific path where a caller's
  own post-write verification (`_verify_docx_write` or equivalent) has *already found a mismatch* and is
  deciding whether restoring `dest + ".bak"` is safe.

  **The gap this leaves:** nothing gates the *promotion* step itself against a concurrent cross-process write.
  `_atomic_write_docx_bytes`'s own internal check (when `pre_manifest` is supplied) compares the *staged*
  artifact's structural counts against the `pre_manifest` the **caller** computed from whatever it loaded
  *before* staging — not against `dest`'s live on-disk state *at the moment of promotion*. If process A
  promotes a change between process B's load and B's own stage/verify, and B's edit happens not to move any of
  the `protected_keys` counts (media/style/relationship — equation count is deliberately unprotected per the
  `_save_docx_xml_stdlib` docstring, `docs_intel.py:2241-2243`), B's internal check passes and B promotes too —
  silently discarding A's already-promoted work, a classic lost-update. This is only ever *caught after the
  fact* by the CAS check above, and only for callers that layer their own additional post-write verification
  that happens to notice something is wrong. Per this sprint's shared context, a documented set of write
  primitives (`edit_caption`, `remove_caption`, `insert_citation`, `edit_citation`,
  `insert_bibliography_entry`, `insert_column`, `split_cell`, and roughly ten more) currently have **zero**
  post-write verification at all — for those specific functions, a cross-process lost-update is not
  "partially detected", it is entirely silent.

- Backup: `_atomic_write_docx_bytes` best-effort-copies `dest` to `dest + ".bak"` immediately before promotion
  (`docs_intel.py:2499-2503`, `shutil.copy2`, failure swallowed via bare `except OSError: pass`). Only **one**
  generation is kept — each successful write overwrites the previous `.bak`, so a restore can only ever recover
  the immediately prior version, not any deeper history. Informational, not a defect, but worth stating since
  the task asked specifically about the backup machinery.

Existing test coverage (`test_5988a5bb_docx_intel_concurrent_write_envelope.py`) directly exercises the
CAS-gated restore path end-to-end for `move_section`, `copy_section`, `relocate_table`, `relocate_figure`,
`insert_figure_block`, and `merge_docx_draft`-into-canonical — confirmed both "no concurrent write, safe to
restore" and "concurrent write detected, leave file untouched" branches are covered for those six callers. This
audit did **not** find equivalent concurrent-write-envelope test coverage naming the newer, this-sprint-hardened
equation writers (`edit_equation_local`, `remove_equation_local`, `insert_numbered_equation`) — their own
dedicated test file, `test_docx_equation_fail_closed_contract.py`, covers fail-closed behavior on a **single**
writer (render-unavailable refusal, degraded-render opt-in, a "lying save" verification catch) but its function
names show no concurrent-second-writer scenario. This is not confirmed as an actual gap in behavior (the shared
`_execute_fail_closed_write` helper these functions were retrofitted onto, per the sprint context, presumably
inherits the same CAS machinery), only as a gap in **named test coverage** for that specific scenario on those
specific three functions — worth an executor re-check rather than a re-derivation from scratch.

**Fixture idea (same-process):** two threads targeting the same `dest`, one holding `_docx_promotion_lock`
artificially long (e.g. via a monkeypatched `os.replace` that sleeps) while the other attempts a write —
confirm the second blocks until the first's full cycle completes, never interleaves.

**Fixture idea (cross-process, the real gap):** two separate OS processes (e.g. `multiprocessing.Process` or
two subprocess invocations, not threads) both loading the same source `.docx`, each making a
non-conflicting-by-protected-key-count edit (e.g. two different caption edits that don't change media/style/
relationship counts), both writing to the same `dest` with a small deliberate `time.sleep` inserted between
stage and promote (monkeypatched) to widen the race window — expected current behavior: both promotions
succeed, `os.replace` leaves whichever ran last, the other process's edit is silently lost, and neither process's
own return value reports any error. This is the concrete regression test that would prove (or, if behavior has
already changed, disprove) the gap described above.

---

## Summary table: what's protected today, by exact function

| Concern | Protecting function(s) | File:line |
|---|---|---|
| Bad ZIP on load | `_load_docx_xml_stdlib` | `docs_intel.py:1764-1809` |
| Bad ZIP / CRC on validate | `validate_docx_package` | `ooxml_integrity.py:231-313` |
| Bad ZIP on staged write | `_atomic_write_docx_bytes` (BadZipFile branch) | `docs_intel.py:2406-2412` |
| Malformed XML per-part (validate) | `validate_docx_package` / `_xml_parts` | `ooxml_integrity.py:181-182`, `243-249` |
| Malformed XML on changed parts (write) | `_atomic_write_docx_bytes` | `docs_intel.py:2452-2495` |
| Dangling relationship targets | `_relationship_records` | `ooxml_integrity.py:185-209` |
| Dangling `r:id`/`r:embed` references | `validate_docx_package` | `ooxml_integrity.py:260-267` |
| Duplicate relationship IDs | `_relationship_records` | `ooxml_integrity.py:205-207` |
| Missing/dangling content types | `_content_type_issues` | `ooxml_integrity.py:212-228` |
| Package-validation wired into every write | `_atomic_write_docx_bytes` → `normalize_word_comment_attributes` → `validate_docx_package` | `docs_intel.py:2371-2381`; `ooxml_integrity.py:387-429` |
| Duplicate `w14:paraId` (detect only) | `validate_docx_package` (warning) / duplicate-para-id read helpers | `ooxml_integrity.py:270-278` |
| New paraId collision avoidance | `_new_para_id` / `_existing_para_ids` | `docs_intel.py:11451-11459` / `11440-11447` |
| Namespace-prefix preservation | `serialize_document_xml_preserving_namespaces`, `_assert_namespace_prefixes_preserved`, `_assert_mc_ignorable_prefixes_declared` | `ooxml_integrity.py:316-338`; `docs_intel.py:2159-2198`, `2201-2226` |
| Sidecar staleness (mtime) | `check_staleness` / `_ensure_fresh` | `docs_intel.py:919-945` / `947-956` |
| No filesystem path traversal (no extraction) | (absence of `extractall`/`.extract(`; wholesale in-memory repack) | `docs_intel.py:2296-2304` and all `writestr` call sites |
| Same-process write serialization | `_docx_promotion_lock` | `docs_intel.py:1864-1876` |
| Cross-process clobber detection (post-hoc, restore path only) | `_safe_restore_after_verification_failure` | `docs_intel.py:2779-2833` |
| Atomic filesystem swap | `os.replace` inside `_atomic_write_docx_bytes` | `docs_intel.py:2504` |
| Best-effort single-generation backup | `_atomic_write_docx_bytes` | `docs_intel.py:2499-2503` |

## Summary table: what's NOT protected today

| Gap | Severity | Evidence |
|---|---|---|
| ~19/34 `zipfile.ZipFile(` call sites in `docs_intel.py` have no local `BadZipFile` catch | Medium | grep count; not individually traced to callers |
| Duplicate `w14:paraId` is a warning, never blocks promotion | Medium | `ooxml_integrity.py:270-278`, `ok` computed from `issues` only at line 311 |
| Duplicate ZIP member names (same part name twice) undetected; last-write-wins silently, preserved (not healed) across a Meridian write | Medium | empirically verified via `zip_dup_probe.py` against project's own `zipfile` |
| XML internal entity expansion (billion laughs / quadratic blowup) unmitigated on both `ET.fromstring` and `LET.fromstring`, on both read and write-back paths | Medium | empirically verified via `xxe_probe.py`; no `defusedxml`, no explicit parser hardening anywhere |
| Cross-process promotion race: no OS-level lock; CAS check only fires in the post-verification-failure restore branch, not as a promotion precondition | Medium–High | `docs_intel.py:1834-1861` (self-documented), `2779-2833`; ~15 write primitives per shared sprint context have zero post-write verification at all |
| Sidecar staleness is mtime-only, no content hash; bytes-sourced indexes untracked by design | Low–Medium | `docs_intel.py:919-945` |
| No busy-timeout tuning on sidecar SQLite connections beyond the 5s Python default | Low | `docs_intel.py:753-908`, no `timeout=`/`PRAGMA busy_timeout` |
| Single-generation `.bak` — no backup history/rotation | Low (informational) | `docs_intel.py:2503-2507` |

## What was empirically run (for reproducibility)

Both probe scripts were standalone, read `/tmp`-equivalent scratch files only, made zero edits to any file
under `extensions/meridian-docs`, and were executed against
`C:\Users\13144\Documents\Meridian\repository\.pixi\envs\default\python.exe` (Python 3.12.13, lxml 6.1.1 /
libxml2 2.15.3):

1. `xxe_probe.py` — external-SYSTEM-entity resolution and small-scale internal-entity-expansion, against both
   `xml.etree.ElementTree.fromstring` and `lxml.etree.fromstring` with default settings; also checked
   `defusedxml` importability (not installed).
2. `zip_dup_probe.py` — built a ZIP with two identically-named `word/document.xml` entries with different
   content, then reproduced `docs_intel.py`'s own `_docx_zip_entries`-style dict-building loop and
   `_save_docx_xml_stdlib`-style `infolist()`-driven repack loop against it to observe exactly which entry
   survives at each stage.

Both scripts are throwaway investigation artifacts (kept in this session's scratchpad,
`C:\Users\13144\AppData\Local\Temp\claude\...\scratchpad\`) — not part of the deliverable and not committed
anywhere; the fixture ideas above describe what a later CODE item should build as real, checked-in pytest
fixtures under `extensions/meridian-docs/tests/`.

## Explicit non-goals / what this document does not claim

- No product code was changed. `docs_intel.py`, `ooxml_integrity.py`, and the four cited test files were only
  read (via Serena/`meridian-extract` symbol tools and `Read`/`Grep`), consistent with this item's
  `artifact_kind: document_only`.
- No fixtures were created as committed test files — every "Fixture idea" above is a specification for a later
  CODE item, not a claim that the fixture exists.
- The malformed-ZIP call-site audit (§1) is a ratio from a grep count, not an exhaustive per-call-site trace of
  all 34 sites' actual error-handling behavior.
- The billion-laughs probe (§8b) deliberately stayed at small scale (10⁴, not the classic ~10⁹) to avoid
  resource exhaustion on the investigation host; the *absence of any guard* is confirmed, the *exact ceiling*
  before something (libxml2's own protections, or the OS) intervenes is not.
- §4b's cross-consumer divergence concern (does Word actually resolve duplicate-named ZIP parts differently
  from Python's `zipfile`?) was not tested against real Word — no Word COM automation was run in this
  investigation. The `runtime-capability-contract-v0.md` document already records that Word COM is available
  on this host; a follow-up item could resolve this specific open question directly.
- No claim is made about `meridian/doc_store.py` or `meridian/research_graph.py` (referenced only in passing by
  `graph-gold-schema-v0.md`'s "Existing implementation pointers") — this audit's scope was strictly the two
  named files plus their cited test files, per the item's explicit scope.
