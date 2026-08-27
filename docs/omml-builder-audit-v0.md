# OMML builder audit v0

Status: investigation complete (PAPER-11). All findings below were produced either by reading the
current source in `C:\Users\13144\Documents\Meridian\repository\extensions\meridian-docs\meridian_docs\`
or by executing the real, unmodified product code from a scratch probe script under the pixi
`default` environment (which has both `lxml` and `latex2mathml`). No line of `docs_intel.py`,
`render_gate.py`, or `ooxml_integrity.py` was edited to produce this document, matching the
investigation-only scope of this item.

## 1. Scope and method

**What was executed live** (not just read): `latex_to_omml_local`, `_stdlib_append_mathml`,
`_validate_omml_structure`, `_omml_semantic_record`, `ooxml_integrity.validate_docx_package`,
`render_gate.check_render_capability`, and `docs_intel.insert_equation_local`, called directly
against real inputs from six scratch probe scripts. Scripts and raw JSON output live under this
session's scratchpad (`.../scratchpad/omml_probe*.py`, `probe*_out.json`) and are reproducible by
re-running them against the same pixi environment; they are not part of the deliverable and were
not committed anywhere.

**Correction to the item's own pointer**: the item text names
`packages/docparse/docparse/latex_intel.py` as the converter. That file exists but contains only
`LatexStructuralParser` (headings/citations/bibliography parsing) — no OMML conversion. The actual
LaTeX→OMML converter (`latex_to_omml_local`), the MathML→OMML tree builder
(`_stdlib_append_mathml`), and the validator (`_validate_omml_structure`) all live in
`extensions/meridian-docs/meridian_docs/docs_intel.py` (lines 7651–8109 for this cluster). The
audit below follows the code as it actually is.

**What this audit does not do**: it does not modify `docs_intel.py` or any hardening code; it does
not stand up a benchmark; it does not claim DocBank or any other external corpus was touched. One
live Word COM render was re-verified this session (see §8) and one live Word COM render attempt on
a synthetic fixture failed — both are reported exactly as observed, including a cleanup step for an
orphaned `WINWORD.EXE` process my own probe left running.

## 2. Pipeline as observed

```
payload (raw "<m:oMath>..." OR LaTeX string)
  -> _resolve_omml(payload)                         [docs_intel.py:8087]
       starts with "<"  -> _validate_omml_structure(payload)  (raises ValueError on bad XML)
       else              -> latex_to_omml_local(payload)      (never raises; returns None on failure)
                              latex2mathml.converter.convert(latex)   [3rd-party, pure Python]
                              -> ET.fromstring(mathml_str)            [can raise ET.ParseError]
                              -> _stdlib_append_mathml(mathml_root, omath)  [docs_intel.py:7680]
                              -> _validate_omml_structure(raw)        [docs_intel.py:7888]
  -> _build_omath_paragraph(omml_raw, ...)           [docs_intel.py:8703] (wraps in a fresh <w:p>)
  -> _execute_fail_closed_write(...)                 [docs_intel.py:3007]
       save()      -> _save_docx_xml_stdlib / atomic write (ooxml_integrity hooks run here)
       verify()    -> _verify_equation_write(...)    [docs_intel.py:8747]  <-- text/id match ONLY,
                                                           does NOT re-run _validate_omml_structure
       provenance  -> _check_artifact_provenance_binding(...)
       render gate -> render_gate.check_render_capability(docx_path)   [render_gate.py:754]
       promote/restore on any failure above
```

Two points fall directly out of reading this chain, not inference:

1. **`_validate_omml_structure` is the only place that ever inspects OMML structural validity.**
   It runs once, before the write. `_verify_equation_write` (the post-write structural check) only
   compares flattened `<m:t>` text and `w14:paraId`/`w14:textId` — confirmed by reading its full
   body (docs_intel.py:8746–8863). Anything `_validate_omml_structure` accepts at insert time is
   never re-checked again by anything in the fail-closed pipeline.
2. **`render_gate.check_render_capability` proves the file opens/rasterizes, not that any one
   equation is semantically sound.** Word does not refuse to open a document because one equation
   has a blank fraction slot; it just shows a blank box. A structurally-empty-but-valid-XML
   equation and a well-formed one are indistinguishable to the render gate.

## 3. LaTeX/MathML cases exercised (38 total, exceeding the 23 the prior probe logged)

All rows below were produced by a live call to `latex_to_omml_local` (or, where noted, a direct
`_stdlib_append_mathml` call on hand-built MathML) against the current code, not transcribed from
memory.

| # | Input | Observed OMML shape | Classification |
|---|---|---|---|
| 1 | `\frac{1}{2}` | `<m:f><m:num><m:e>1</m:e></m:num><m:den><m:e>2</m:e></m:den></m:f>` | Class 1 — correct |
| 2 | `x^2` | `<m:sSup><m:e>x</m:e><m:sup>2</m:sup></m:sSup>` | Class 1 |
| 3 | `x_i` | `<m:sSub>...</m:sSub>` | Class 1 |
| 4 | `x_i^2` | `<m:sSubSup>...</m:sSubSup>` | Class 1 |
| 5 | `\sqrt{x+1}` | `<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>x+1</m:e></m:rad>` | Class 1 |
| 6 | `\sqrt[3]{x}` | `<m:rad><m:deg>3</m:deg><m:e>x</m:e></m:rad>` | Class 1 |
| 7 | `\sum_{i=1}^{n} x_i` | `<m:sSubSup><m:e>∑</m:e><m:sub>i=1</m:sub><m:sup>n</m:sup></m:sSubSup><m:sSub>x<sub>i</sub></m:sSub>` | Class 2 — confirmed: side-scripts, not `m:nary` |
| 8 | `\prod_{i=1}^{n} x_i` | same shape as #7 with ∏ | Class 2 — same side-script issue |
| 9 | `\int_0^1 x\,dx` | `<m:sSubSup><m:e>∫</m:e><m:sub>0</m:sub><m:sup>1</m:sup></m:sSubSup>` + flat runs `x d x` | Class 2 — same side-script issue; also no `dx` differential grouping |
| 10 | `\lim_{x \to 0} f(x)` | `<m:sSub><m:e>lim</m:e><m:sub>x→0</m:sub></m:sSub>` + flat runs `f(x)` | Class 2 — plain-text "lim" base with a subscript, not `m:func`/`m:limLow` |
| 11 | `\overline{AB}` | `<m:limUpp><m:e>AB</m:e><m:lim>―</m:lim></m:limUpp>` | Class 2 — confirmed. Root cause below (§5.1) |
| 12 | `\hat{x}` | `<m:acc><m:accPr><m:chr m:val="^"/></m:accPr><m:e>x</m:e></m:acc>` | Class 1 — correct accent |
| 13 | `\bar{x}` | `<m:acc>...m:val="¯"...</m:acc>` | Class 1 |
| 14 | `\vec{v}` | `<m:acc>...m:val="→"...</m:acc>` | Class 1 |
| 15 | `\tilde{n}` | `<m:acc>...m:val="~"...</m:acc>` | Class 1 |
| 16 | `\min_{x} f(x)` | `<m:sSub><m:e><m:func><m:fName>min</m:fName><m:e/></m:func></m:e><m:sub>x</m:sub></m:sSub>` + flat `f(x)` | Class 2/new bug — `<m:func>`'s own `<m:e>` is **always empty** (§5.2) |
| 17 | `\max_{x} f(x)` | same shape as #16 | same bug |
| 18 | `\operatorname{argmin}_x f(x)` | same shape as #16 | same bug |
| 19 | `f(x)=\begin{cases}1 & x>0\\0 & x\le 0\end{cases}` | `<m:eqArr>` with 2 rows × 2 cells, correct | Class 1 (grid); parens/brace around `f(x)=` are flat text, expected |
| 20 | `\begin{matrix}a&b\\c&d\end{matrix}` | `<m:eqArr>` 2×2, correct | Class 1 |
| 21 | `\begin{pmatrix}a&b\\c&d\end{pmatrix}` | `<m:eqArr>` 2×2 correct, but `(` `)` are flat `<m:r>` runs **outside** the array | Class 2 — fence lost (§5.3) |
| 22 | `\begin{bmatrix}a&b\\c&d\end{bmatrix}` | same as #21 with `[` `]` | Class 2 — same |
| 23 | `\begin{array}{cc}a&b\\c&d\end{array}` | `<m:eqArr>` 2×2, correct | Class 1 |
| 24 | `\begin{aligned}x&=1\\y&=2\end{aligned}` | **`None`** (conversion fails) | Fails closed, but by accident — root cause below (§5.4) |
| 25 | `\begin{align}x&=1\\y&=2\end{align}` | `<m:eqArr>` 2 rows, **each row's last cell contains literal `(1)`/`(2)`** (LaTeX's own auto-numbering leaked into content) | Class 2 — new finding (§5.4) |
| 26 | `\begin{split}x&=1\\y&=2\end{split}` | `<m:eqArr>` 2 rows, correct (no numbering leak) | Class 1 (row-grouping) — best of the alignment family |
| 27 | `\begin{gather}x=1\\y=2\end{gather}` | **flat runs `x=1y=2`, row break silently dropped, no separator at all** | Class 2 — worse than #24: no error, no marker, content merges without a trace |
| 28 | `\left( x + y \right)` | flat runs `( x + y )`, **no `<m:d>` fence element** | Class 2 — `mfenced` handling in `_stdlib_append_mathml` is unreachable for this LaTeX form (§5.3) |
| 29 | `\|v\|` | flat runs `‖ v ‖` | Class 2 — no norm/fence structure |
| 30 | `\binom{n}{k}` | flat `(` + `<m:f><m:num>n</m:num><m:den>k</m:den></m:f>` + flat `)` — **real fraction bar rendered for a bar-less binomial coefficient**, parens lost | Class 2 — new finding (§5.3) |
| 31 | `{}_1^2X_3^4` (prescript idiom, no package) | two adjacent `<m:sSubSup>`, first with **empty `<m:e/>` base** | Class 2 / gap trigger — passes validator (§6) |
| 32 | `mmultiscripts` MathML directly (true prescript: `X` sub 3 sup 4, presub 1 presup 2) | **`<m:r><m:t>X3412</m:t></m:r>`** — fully flattened, no digit is distinguishable from another | Class 4 trigger — **not caught** by `_OMML_FALLBACK_MARKERS` (§5.5) |
| 33 | `\alpha + \beta` | flat runs, correct (no structure needed) | Class 1 |
| 34 | `\frac{1}{1+\frac{1}{x}}` | nested `<m:f>` × 2, correct | Class 1 |
| 35 | `\frac{}{}` | `<m:f><m:num><m:e/></m:num><m:den><m:e/></m:den></m:f>` | **Validator gap — accepted; §6** |
| 36 | `\frac{1}{` (unbalanced) | `None` | Class 3 — correctly fails closed |
| 37 | `hello world` (plain text) | flat character runs | Class 1 (degenerate but valid) |
| 38 | `` (empty string) | `None` | Class 3 — correctly fails closed, short-circuits before calling `latex2mathml` at all |

## 4. Prior-probe findings: verified, and where they needed correction

- **Sum/prod/integral side-script semantics** (case 7–9): confirmed exactly as logged. Root cause
  read directly from `_stdlib_append_mathml`'s `munder`/`mover`/`munderover` branch
  (docs_intel.py:7833–7851): `latex2mathml` emits `msubsup` for these operators (a plain
  script pair), never `munderover`, so the branch that *would* build `<m:nary>` never fires. This
  matches the independent, same-day evidence in
  `E:\MeridianData\ooxml-graph-paper\manifests\meridian-equation-word-probe-20260826.json`, whose
  `omml_observation` block records the identical `sSubSup`/`sSub` shape for `\sum_{i=1}^n x_i` — I
  reproduced that exact shape myself in this session rather than trusting the manifest at face
  value.
- **lim side-script semantics** (case 10): confirmed — plain `sSub`, not a function/limit
  structure.
- **overline/overset → `limUpp` mapping** (case 11): confirmed, and the root cause is now precise
  rather than descriptive. `_stdlib_append_mathml`'s single-character accent allowlist is
  `{"^", "~", "¯", "→", "⃗", "ˆ"}` (docs_intel.py:7823). `latex2mathml` renders `\overline{...}`
  as MathML `<mover><mo accent="true">‗</mo></mover>` using **U+2015 HORIZONTAL BAR**, a different
  code point from the U+00AF MACRON already in the allowlist. Because U+2015 is not in the set, the
  generic branch runs instead and builds `<m:limUpp>` — an "upper limit" structure, not an accent.
  This is a one-character allowlist gap, not a deep design problem, and is worth naming precisely
  for whoever picks up PAPER-13/14.
- **Prescript flattening**: the prior note was correct but conflated two different code paths that
  behave differently, now separated as cases 31 and 32. The no-package LaTeX idiom
  `{}_1^2X_3^4` does **not** flatten — it becomes two side-by-side `sSubSup` elements, the first with
  an empty base (this is actually an instance of the §6 gap, not a fallback). A genuine
  `mmultiscripts` prescript (what a real prescript-aware LaTeX→MathML path would emit) **does**
  flatten completely, to indistinguishable digits, and is the more serious of the two.
- **`aligned` → `conversion_none`**: confirmed as an observed outcome, but the mechanism claimed
  (or implied) by "conversion_none" — a deliberate, recognized rejection of an unsupported construct
  — is not what happens. See §5.4: it is an accidental XML well-formedness failure in the
  third-party `latex2mathml` output, caught by a blanket `except Exception: return None`. This
  matters because the same accident does **not** happen for `align`, `split`, `array`, or `gather`
  (cases 25–27), so "the aligned family is unsupported and safely rejected" is not an accurate
  general statement — only bare `aligned` currently gets that accidental protection, and `gather`
  (case 27) is actively worse: it converts "successfully" while silently destroying a row boundary.
- **Empty-child validator acceptance**: this is the item's central flagged gap. §6 gives it a full,
  standalone treatment, including verifying precisely what PAPER-5 did and did not close.

## 5. New findings from this session (not in the prior probe notes)

### 5.1 `overline` root cause (see §4) — precise character-set fix target, not just a symptom.

### 5.2 `<m:func>`'s argument slot is *always* empty by construction

`_stdlib_append_mathml`'s text-tag branch (docs_intel.py:7699–7706), triggered whenever a token's
text is `min`/`max`/`argmin`/`argmax`/`sup`/`inf`, builds:

```python
func = ET.SubElement(parent, _qm("func"))
f_name = ET.SubElement(func, _qm("fName"))
run = ET.SubElement(f_name, _qm("r"))
ET.SubElement(run, _qm("t")).text = text
ET.SubElement(func, _qm("e"))       # <-- created, never populated, ever
return
```

There is no code path that puts anything inside that `<m:e>`. This isn't input-dependent — it
fires identically for every one of cases 16–18. Traced back through the intermediate MathML
(`l2m.convert(r"\min_{x} f(x)")` → `<msub><mo>min</mo><mrow><mi>x</mi></mrow></msub><mi>f</mi>...`),
the underlying reason is that `latex2mathml` never groups `f(x)` as an argument of `min` in the
first place — LaTeX's `\min_x f(x)` is just juxtaposition, not function application syntax — so by
the time `_stdlib_append_mathml` wraps the operator token in an OOXML "function apply" (`m:func`)
structure, it has no argument to put in the required `<m:e>` slot and leaves it empty
unconditionally. OOXML's `m:func` contract implies a bound argument; Word will render a visible
blank box after "min". This is a converter defect, independently confirmed by direct execution.

### 5.3 Fence/delimiter and no-bar-fraction loss is real and reproducible, not a hypothesis

`_stdlib_append_mathml` does have a `mfenced` branch (docs_intel.py:7825) that correctly builds
`<m:d>`. It is simply never reached by the three LaTeX forms most likely to appear in a real paper:

- `\left( ... \right)` — `latex2mathml` emits `<mo fence="true">` tokens inside a bare `<mrow>`,
  never `<mfenced>` (confirmed via direct `latex2mathml.converter.convert` introspection). The
  `fence="true"` attribute is discarded; `(`/`)` become ordinary text runs.
- `pmatrix`/`bmatrix` — the bracket characters are emitted as sibling `<mo>` tokens around
  `<mtable>`, not wrapping it, so the same thing happens: real 2×2 `eqArr` grid, literal-text
  brackets glued on the outside with no auto-sizing/fence semantics.
- `\binom{n}{k}` — `latex2mathml` emits `<mfrac linethickness="0">` (a request for a bar-less
  stacked pair) wrapped in sized `<mo>` parens. `_stdlib_append_mathml`'s `mfrac` handler
  (docs_intel.py:7756) ignores all attributes and always builds a normal `<m:f>`, so Word renders a
  visible fraction bar for what should be a barless binomial coefficient, and the parens are lost
  the same way as above.

Net effect: the `mfenced`-handling code exists but is effectively dead for the LaTeX inputs that
would actually invoke it in practice. This should be treated as a converter gap, not just a
"semantically lossy but acceptable" curiosity, because the visual result (a fraction bar where
there should be none) is arguably worse than a flattened fallback would be.

### 5.4 The `aligned`/`align`/`split`/`gather` family is internally inconsistent, and the safe case is accidental

Direct inspection of `latex2mathml.converter.convert()` output plus `ET.fromstring()` on that
output shows precisely why `aligned` returns `None`: it renders the `&` alignment markers as a
literal, **unescaped** `<mi>&</mi>` token in its MathML string —

```
<mi>x</mi><mi>&</mi><mo>=</mo><mn>1</mn>...
```

— which is not well-formed XML (a bare `&` must be `&amp;`). `ET.fromstring(mathml_str)` raises
`xml.etree.ElementTree.ParseError: not well-formed (invalid token)`, which propagates up through
`latex_to_omml_local`'s blanket `except Exception: return None`. The fail-closed outcome is real
and correct, but it is an accident of a third-party library's XML-escaping bug, not a recognized
"we don't support LaTeX alignment environments" code path. `align`, `split`, `array`, and `gather`
all route through a different `latex2mathml` renderer that emits a genuine `<mtable>` (no literal
`&`), so none of them hit this accidental protection:

- `align` and `split` both convert to correct `eqArr` row grids. `align` additionally bakes LaTeX's
  own auto equation numbering (`(1)`, `(2)`) into the array as ordinary cell text — a real
  double-numbering risk if a caller also uses the dedicated `insert_numbered_equation` (PAPER-5)
  path for the same equation.
- `gather` is the worst outcome observed anywhere in this audit: it converts "successfully" with no
  error and no fallback marker, but the row boundary is carried by `<mspace linebreak="newline"/>`
  in the MathML, a tag `_stdlib_append_mathml` does not recognize in any branch (not a row tag, not
  a text tag, no dedicated case), so it falls to the generic "flatten remaining text" catch-all
  (docs_intel.py:7846), which extracts zero text from an `<mspace>` and appends nothing. Two
  logically separate equations (`x=1` and `y=2`) silently become one run `x=1y=2` with the boundary
  between them gone, and nothing downstream — not `_validate_omml_structure`, not
  `_omml_semantic_record`'s issue list — can tell.

### 5.5 `_OMML_FALLBACK_MARKERS` has no coverage for multiscript/prescript notation

Case 32 (`mmultiscripts`) produces `<m:r><m:t>X3412</m:t></m:r>` — a flattened run with zero
structural tags. `_validate_omml_structure`'s fallback check only rejects a flattened run if its
text contains one of a fixed marker-word set: `fraction`, `cases`, `matrix`, `summation`,
`subscript`, `superscript`, `argmin` (docs_intel.py:7869–7873). None of these substrings occur in
`X3412`, so the flattened, information-destroying result passes cleanly. This is a distinct gap
from the empty-child one in §6 — it is about the *fallback-detection marker vocabulary* being
incomplete, not about required-child emptiness.

### 5.6 Two independent, divergent "is this flattened OMML suspicious" implementations exist

`_validate_omml_structure`'s `_OMML_FALLBACK_MARKERS` (insert-time gate, blocks the write) and
`_omml_semantic_record`'s `flattened_markers` regex tuple (docs_intel.py:7983–7988, used for
post-hoc semantic-drift comparison, e.g. section-replace preservation checks) are separate lists
with different vocabularies — the semantic-record version additionally matches `\hat|\bar|\vec`
style macros, `_`/`^` script markers, and `||...||` norms via regex, which the insert-time gate does
not check for at all. A future edit to one is not guaranteed to be reflected in the other; they
should either be unified or explicitly documented as intentionally different (insert-time gate vs.
downstream drift detector).

### 5.7 `validate_docx_package` (ooxml_integrity) can certify a file Word refuses to open — confirmed live, not hypothetical

This was tested directly, in this session, against the real `word-com` backend (see §8 for the full
transcript). Summary: the test suite's own `_write_word_authored_docx` fixture (from
`tests/test_docx_word_com_regression.py`, the fixture used by its "real backend" regression tests)
was written fresh to a scratch directory and checked two ways:

- `ooxml_integrity.validate_docx_package(raw_bytes)` → `{"ok": true, "issues": [], "warnings": [],
  "part_count": 11}` — a clean bill of health.
- `render_gate.check_render_capability(path)` on the **same, untouched file**, in the **same
  session**, with Word COM independently confirmed functional (see §8) → `"status": "failed"`,
  `"reason": "Word COM render failed: com_error: ... 'The file appears to be corrupted.'"`.

I did not root-cause which specific part Word objects to (the Content-Types/rels/document.xml all
look schema-plausible on inspection), and this may be specific to this hand-authored test fixture
rather than to files Meridian itself ever writes (Meridian's own write path always starts from a
real Word- or LibreOffice-produced `.docx` and only mutates targeted XML, which is a different risk
profile than building every OPC part from scratch in a test file). What is not in question is the
gap itself: passing `validate_docx_package` is evidence of well-formed XML and present required
parts, and is not evidence that Word will open the file. No test in this repository currently
cross-checks the two.

### 5.8 Post-render editability is not checked anywhere

Searched the full `docs_intel.py`/`render_gate.py`/`ooxml_integrity.py` surface for any check that
goes beyond "Word can open and rasterize this file" to "the inserted equation is a genuinely
editable native Word math object after the fact" (e.g., round-tripping through Word's own
equation-editor object model, or re-opening and re-saving). None exists. The closest artifact is a
docstring sentence in `_validate_omml_structure` itself, motivating the validator by exactly this
risk ("malformed fractions and fallback prose can still open as a visually plausible but
non-editable equation") — but the validator addresses structural XML shape, not a live editability
proof. `check_render_capability`/`check_word_com_render_receipt` prove "opens and converts to PDF",
which is a strictly weaker claim.

### 5.9 No audit-grade render receipt

Confirmed by reading `check_render_capability` (render_gate.py:754–847) and
`check_word_com_render_receipt` (render_gate.py:680–690) in full: the returned `detail` dict for a
`"rendered"` result carries only `converted_via` and `output_filename` (word-com) or backend-specific
equivalents for soffice. There is no source/output SHA-256, no Word build/path, no page count, no
timestamp/freshness field, and no cleanup-status field. This matches — and, by reading the actual
function bodies rather than trusting the prose, now directly confirms — the gap already named in
`runtime-capability-contract-v0.md`'s "Current observed state" section.

## 6. The empty-child validator gap, precisely scoped

**What PAPER-5 actually fixed** (verified by reading `_validate_omml_structure`, docs_intel.py:7888,
and by exercising it directly): an `<m:oMath>` with **zero** flattened text **and** zero recognized
structural tag names anywhere in the tree is rejected —

```
<m:oMath></m:oMath>                        -> REJECTED ("no visible content")
<m:oMath><m:r></m:r></m:oMath>             -> REJECTED ("no visible content")
```

This closes exactly one case: the whole equation is empty top to bottom.

**What remains open**, confirmed with 16 hand-crafted adversarial `<m:oMath>` payloads run directly
through the live `_validate_omml_structure`:

| Payload (abbreviated) | Result |
|---|---|
| `<m:f><m:num><m:e/></m:num><m:den><m:e/></m:den></m:f>` (both slots empty) | **ACCEPTED** |
| `<m:f><m:num><m:e/></m:num><m:den><m:e>2</m:e></m:den></m:f>` (num empty, den has content) | **ACCEPTED** |
| `<m:sSub><m:e/><m:sub>i</m:sub></m:sSub>` (empty base) | **ACCEPTED** |
| `<m:sSup><m:e>x</m:e><m:sup/></m:sSup>` (empty exponent) | **ACCEPTED** |
| `<m:rad><m:deg/><m:e/></m:rad>` (empty radicand) | **ACCEPTED** |
| `<m:func><m:fName>min</m:fName><m:e/></m:func>` (empty argument — matches the real converter's own output, §5.2) | **ACCEPTED** |
| `<m:d><m:e/></m:d>` (empty fence content) | **ACCEPTED** |
| `<m:nary><m:e/></m:nary>` (empty nary operand) | **ACCEPTED** |
| `<m:eqArr><m:e><m:e>1</m:e><m:e/></m:e></m:eqArr>` (one empty grid cell) | **ACCEPTED** |
| `<m:acc><m:accPr><m:chr m:val="^"/></m:accPr><m:e/></m:acc>` (empty accent target) | **ACCEPTED** |
| `<m:f><m:num><m:e>1</m:e></m:num></m:f>` (den tag missing entirely — different bug class) | REJECTED ("missing required child element(s): den") — already covered by the existing `_OMML_REQUIRED_CHILDREN` tag-presence check and by `test_omml_contract_semantics.py::test_validator_rejects_malformed_fraction_and_flattened_fallback` |
| `<m:oMathPara>...` / wrong root tag / non-XML / oversized (>20,000 chars) / over-deep (>40 levels) | all correctly REJECTED — these bound/shape checks work as documented |

**Root cause, read directly from the code**: `_OMML_REQUIRED_CHILDREN` (docs_intel.py:7855) and the
`num`/`den` special case (docs_intel.py:7940–7941) both check only that a required **tag** is
present among an element's children (`element.find(_qm("e")) is None`, or a set-membership test on
child tag names). Neither checks whether that child, once found, itself has any content (text or a
nested structural tag). The whole-`oMath` check (docs_intel.py:7942) only fires when the *entire*
tree's flattened text is empty **and** no structural tag name appears anywhere — and an empty `<m:e/>`
nested inside a present `<m:f>`/`<m:rad>`/`<m:d>`/etc. still leaves that structural tag name in
`names`, so the whole-tree check is satisfied (i.e., does not fire) even when the visible content is
entirely absent, as `\frac{}{}` (case 35) demonstrates end to end through the real converter, not
just via a hand-built adversarial payload.

**This is confirmed to be a live, reachable code path, not just adversarial XML nobody would ever
send**: `latex_to_omml_local(r"\frac{}{}")` produces exactly the first row of the table above through
the real, unmodified pipeline (probe 1, case 35), and the `min`/`max`/`argmin` cases (16–18) produce
the `<m:func>` empty-`<m:e>` row through the real converter on ordinary, plausible LaTeX input, not
contrived edge cases.

**Confirmed NOT caught by anything downstream either**: `_verify_equation_write` only checks
flattened text and paragraph identity (§2), so an accepted empty-numerator fraction passes
post-write verification too. `render_gate.check_render_capability` proves Word opens the file, not
that any given equation slot has visible content. No test in `test_omml_contract_semantics.py`,
`test_semantic_equation_manifest.py`, or `test_docx_equation_fail_closed_contract.py` exercises this
— confirmed by reading all three files; the one existing "empty" test
(`test_validator_rejects_malformed_fraction_and_flattened_fallback`, docs_intel test line 33) uses
`<m:num />` (tag absent), a different and already-covered defect class.

## 7. Existing test coverage cross-check (read in full, not sampled)

- **`test_omml_contract_semantics.py`** (79 lines): root-tag/`oMathPara` rejection, one
  tag-missing-entirely fraction rejection, one flattened-fallback-text rejection, one
  well-formed-fraction/subscript/array acceptance, one MathML→OMML wrapper-preservation check, one
  identity/style check on `_build_omath_paragraph`. Five tests total; none construct a present-but-
  empty required child.
- **`test_semantic_equation_manifest.py`**: covers structured-vs-flattened same-text
  discrimination, inline/`oMathPara` acceptance, function/norm/limit structural recording, manifest
  comparison rejecting missing/replaced equations, and section-scoping. Exercises the
  `_omml_semantic_record` machinery, not the insert-time validator's empty-child handling.
- **`test_docx_equation_fail_closed_contract.py`**: entirely about the PAPER-5/PAPER-6 fail-closed
  retrofit for `edit_equation_local`/`remove_equation_local` — render-unavailable handling, degraded-
  render opt-in, "lying save" detection, and the shared-helper wiring for `insert_equation_local`.
  All fixture OMML payloads used are simple, valid, non-adversarial (e.g., a single-run equation);
  none probe validator boundaries.
- **`test_docx_word_com_regression.py`**: real (unmocked) render-backend regression tests for
  caption/equation/note inserts, each branching on the three real `check_render_capability` states.
  Uses `_SIMPLE_OMATH` (a bare text run) only — never an adversarial payload. This is also the file
  whose fixture builder is implicated in §5.7/§8.

None of the current test files give any coverage to the four fixture classes this item was asked to
produce a corpus spec for. §9 below is written to fill exactly that hole.

## 8. Live probe transcript (Word COM / package integrity)

Run in this session, in order:

1. `render_gate.check_render_capability()` against the real, previously-produced
   `E:\MeridianData\ooxml-graph-paper\renders\meridian-equation-probe-20260826\input.docx` (the same
   file behind the `meridian-equation-word-probe-20260826.json` manifest referenced in the shared
   sprint context) — **took 50.0s, returned `{"status": "rendered", "backend": "word-com", "detail":
   {"converted_via": "word-com", "output_filename": "render_probe.pdf"}}`**. This independently
   re-confirms, rather than just trusts, that Word COM is genuinely functional on this machine right
   now.
2. Built a fresh copy of the test suite's `_write_word_authored_docx` fixture in a scratch temp
   dir and ran `check_render_capability` against it, untouched, before any Meridian write — **took
   4.1s and returned `"status": "failed"`, `"reason": "Word COM render failed: com_error:
   (-2147352567, 'Exception occurred.', (0, 'Microsoft Word', 'The file appears to be corrupted.',
   'wdmain11.chm', 25272, -2146822496), None)"`**. Reproduced twice (once contaminated by a scripting
   bug on my part, described next; once clean).
3. First attempt at step 2 was contaminated: my scratch script lacked
   `if __name__ == "__main__":`/`freeze_support()` guards, and `render_gate`'s Word-COM backend uses
   `multiprocessing` with Windows' `spawn` start method, which re-imports the launching script as
   `__main__` in the child process. Without the guard this caused the whole probe script to
   recursively re-execute inside the spawned worker, producing two garbled `RuntimeError`
   ("attempt... before the current process has finished its bootstrapping phase") results before a
   third, less-contaminated attempt surfaced the real Word COM error above. I fixed the script with a
   proper `__main__` guard and reran cleanly (result above, step 2, is the clean rerun). This is a
   caveat about my own probe harness, not a finding about the product.
4. After the contaminated run, `tasklist` showed one orphaned `WINWORD.EXE` (PID 14028, ~130MB)
   left running; I terminated it with `taskkill /PID 14028 /F` before continuing, to avoid leaving a
   stray Office process behind.
5. Ran `ooxml_integrity.validate_docx_package()` against the identical fixture bytes from step 2 —
   returned `{"ok": true, "issues": [], "warnings": [], "part_count": 11}`. This is the basis for
   §5.7. I did not attempt to insert an equation into a file Word already refuses to open (there is
   no render state left to meaningfully test past that point); the `insert_equation_local` call in
   the contaminated run correctly failed closed and restored the file (`file_restored: true`, no
   `document.xml` byte change), which is at least a positive confirmation that the fail-closed
   contract behaves correctly when the render gate reports `"failed"`.

No claim is made here about *why* Word rejects this specific fixture, and no claim is made that
Meridian's own write path produces files with the same defect — Meridian always starts from a
real Word/LibreOffice-authored `.docx`, this fixture is hand-assembled from raw XML strings in a
test file. The reproducible fact is narrower and still worth recording: **`validate_docx_package`
returning a clean bill of health is not sufficient evidence a file will open in Word**, on this
machine, today.

**Additional operational observation, not otherwise claimed anywhere in this project's docs**: after
the two clean (non-contaminated) `check_render_capability` calls in this session — the step 1 sanity
check and the step 2 fixture check — a follow-up `tasklist` found three more orphaned `WINWORD.EXE`
processes still running (PIDs 7688, 26084, 27060; the third had already exited by the time
`taskkill` reached it). `render_gate.py` does call `word.Quit()` on normal completion and error
paths (confirmed by reading lines ~456–462 and ~559–564), and has a separate, working
`_terminate_owned_process`/timeout path for the case where a render exceeds its time bound — but
`Quit()` succeeding does not appear to guarantee the `WINWORD.EXE` process actually exits on this
machine. I terminated all of them manually rather than leave them running. This was not something I
went looking for; it surfaced purely from routine `tasklist` hygiene checks between probe runs. It
is reported here as an observed fact, not diagnosed further (I did not instrument `word.Quit()`
itself or check whether these three specific PIDs correspond 1:1 to my two calls or include a
straggler from an earlier attempt), and is worth a follow-up item independent of the OMML audit
proper: repeated real-backend test runs on a Word-COM-capable machine may accumulate orphaned
`WINWORD.EXE` processes over a session even when every individual call reports success.

## 9. Adversarial fixture corpus spec for PAPER-13

Each fixture below names its input, the exact gate that should fire, and the expected outcome. This
is a specification for a later CODE item to implement as real pytest fixtures/parametrized cases —
nothing here has been added to the repository.

### Class 1 — correct native OMML (must be ACCEPTED, and must round-trip exactly)

| id | input | expect |
|---|---|---|
| C1-01 | `\frac{1}{2}` | accepted; `<m:f>` with non-empty `num`/`den` |
| C1-02 | `x_i^2` | accepted; `<m:sSubSup>` |
| C1-03 | `\sqrt[3]{x}` | accepted; `<m:rad>` with non-empty `deg`/`e` |
| C1-04 | `\hat{x}`, `\bar{x}`, `\vec{v}`, `\tilde{n}` | accepted; `<m:acc>` for each (regression guard on the accent allowlist) |
| C1-05 | `\begin{cases}...\end{cases}`, `\begin{matrix}...\end{matrix}`, `\begin{array}{cc}...\end{array}` | accepted; correct row/column `<m:eqArr>` shape |
| C1-06 | raw `<m:oMath>` payload (not LaTeX) with a well-formed nested fraction | accepted via the `_resolve_omml` raw-XML branch |

### Class 2 — semantically lossy output (must be ACCEPTED at insert time — this class documents
known, reviewed loss, not a bug bar — but must be flagged by `_omml_semantic_record`'s issue list or
a future stricter gate, and is exactly the corpus a fidelity metric should score against)

| id | input | expected lossy shape | why it matters |
|---|---|---|---|
| C2-01 | `\sum_{i=1}^{n} x_i` | `sSubSup`, not `nary` | side-script vs. true big-operator rendering |
| C2-02 | `\lim_{x\to 0} f(x)` | `sSub` on text "lim" | not a semantic limit/function structure |
| C2-03 | `\overline{AB}` | `limUpp`, not `acc` | accent-char allowlist miss (§4) |
| C2-04 | `\left( x+y \right)` | flat parens, no `<m:d>` | fence semantics dropped (§5.3) |
| C2-05 | `\begin{pmatrix}a&b\\c&d\end{pmatrix}` | flat parens outside a correct `eqArr` | same fence loss, matrix family |
| C2-06 | `\binom{n}{k}` | barred `<m:f>` instead of bar-less stack | visibly wrong math, not just lossy (§5.3) |
| C2-07 | `\min_{x} f(x)` / `\max` / `\operatorname{argmin}_x` | `<m:func>` with permanently empty `<m:e>` | converter bug, not just notation loss (§5.2) |
| C2-08 | `\begin{align}x&=1\\y&=2\end{align}` | `eqArr` cells contain literal `(1)`/`(2)` | numbering-collision risk with `insert_numbered_equation` |
| C2-09 | `\begin{gather}x=1\\y=2\end{gather}` | flat run `x=1y=2`, **no row separator at all** | silent, undetectable content merge — the single worst case in this audit |

### Class 3 — unsupported input that should fail closed (must return `None`/raise `ValueError`,
never a partial or silently-corrupted write)

| id | input | expect |
|---|---|---|
| C3-01 | `\frac{1}{` (unbalanced braces) | `latex_to_omml_local` returns `None`; `insert_equation_local` returns `{"error": ...}`, no write |
| C3-02 | `` (empty string) | `None`, short-circuited before calling `latex2mathml` |
| C3-03 | raw payload `<m:oMathPara>...` | `ValueError("m:oMath root required; m:oMathPara is not accepted")` |
| C3-04 | raw payload that is not XML at all | `ValueError("OMML payload is not valid XML: ...")` |
| C3-05 | raw payload > 20,000 characters | `ValueError` citing the char limit (regression guard on the PAPER-5 bound) |
| C3-06 | raw payload nested > 40 levels deep | `ValueError` citing the nesting limit (regression guard on the PAPER-5 bound) |
| C3-07 | `\begin{aligned}x&=1\\y&=2\end{aligned}` | `None` today (documented as an *accidental* pass, §5.4 — this fixture exists to catch a regression if `latex2mathml` is ever upgraded to fix its own XML escaping and this silently starts "succeeding" with unreviewed output) |

### Class 4 — fallback-text forbidden (flattened text with a structural marker but no matching
OOXML structural element; must be REJECTED)

| id | input | expect |
|---|---|---|
| C4-01 | raw `<m:oMath><m:r><m:t>fraction a over b</m:t></m:r></m:oMath>` | rejected — already covered by existing test |
| C4-02 | raw `<m:oMath><m:r><m:t>x squared plus y summation</m:t></m:r></m:oMath>` | rejected via the `summation` marker |
| C4-03 | direct MathML `mmultiscripts` input (true prescript: base + sub + sup + presub + presup) | **currently ACCEPTED — this is the fixture that should force `_OMML_FALLBACK_MARKERS` to gain prescript/multiscript coverage (§5.5)** |
| C4-04 | raw `<m:oMath><m:r><m:t>x_1 to the power of 2</m:t></m:r></m:oMath>` (subscript/superscript spelled out in prose, no `_`/`^`) | currently ACCEPTED (no keyword hit) — documents the marker vocabulary's inherent incompleteness; include as a known-accepted control unless/until the mechanism changes |

### Class 5 (new — not in the item's original four, added because it was found live this session) —
DOCX package validity vs. Word open/render divergence

| id | fixture | expect |
|---|---|---|
| C5-01 | the exact `_write_word_authored_docx` fixture from `test_docx_word_com_regression.py`, checked with both `validate_docx_package` and a REAL (unmocked) `check_render_capability` in the same test | today: `validate_docx_package` reports `ok: true`; `check_render_capability` reports `"failed"` with a Word "file appears to be corrupted" `com_error` — this divergence itself is the thing to pin down and either fix the fixture or document as an accepted Word-strictness gap |
| C5-02 | the same fixture, opened and immediately re-saved once by Word COM (if C5-01's divergence is fixed), to establish a first real post-render-editability check | not yet exercised by anything in the repo (§5.8) — this is the seed for closing that gap, not a fixture that exists today |

### Class 6 — empty-required-child matrix (the item's flagged gap, made into fixtures directly)

Every row from the §6 table (`<m:f>` both/one-side empty, `<m:sSub>`/`<m:sSup>` empty slot,
`<m:rad>` empty radicand, `<m:func>` empty argument, `<m:d>` empty fence, `<m:nary>` empty operand,
`<m:eqArr>` empty cell, `<m:acc>` empty target) should become one parametrized test asserting
**REJECTED** once PAPER-13 extends `_validate_omml_structure` to walk into each required child and
require it to itself carry text or a nested structural tag, not just exist as a tag. The one
already-passing row (`<m:f><m:num><m:e>1</m:e></m:num></m:f>`, den tag missing entirely) should stay
in the suite as a not-this-bug control so a future fix cannot accidentally regress the check that
already works.

## 10. Honest scope note

No dataset was downloaded. No benchmark numbers are claimed. No code in `docs_intel.py`,
`render_gate.py`, or `ooxml_integrity.py` was modified — every "confirmed" statement above came from
either reading the current source at the cited line numbers or executing that exact source, unedited,
from a throwaway scratch script, against throwaway scratch `.docx` fixtures under the OS temp
directory (never under the paper subproject, never under E:\MeridianData, nothing committed). Four
orphaned `WINWORD.EXE` processes accumulated across the session's probe runs (one from a buggy first
attempt at the probe script, three from otherwise-clean runs — see §8) and were identified and
terminated via `tasklist`/`taskkill`; a final check confirmed none remained. The
`meridian-equation-word-probe-20260826.json` manifest's core
claim (Word COM renders a real Meridian-inserted equation) was independently re-executed in this
session, not merely read and trusted, and its `omml_observation` shape for `\sum_{i=1}^n x_i` was
cross-checked bit-for-bit against a fresh live conversion in this session.
