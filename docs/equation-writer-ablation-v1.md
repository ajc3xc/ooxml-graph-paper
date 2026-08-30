# Equation-writer ablation v1 (PAPER-S10)

Status: bounded converter/writer ablation, complete for the structural/semantic comparison;
Word-render receipts blocked this session (see Section 6). Not a survey — 13 named D1
categories, one representative case each, run through exactly two independent converters plus
one supplementary internal probe. All numbers below come from live execution recorded in
`docs/equation-d1-fixture-manifest-v1.json`, not from memory or transcription.

## 1. Scope and method

**What this item extends**: `docs/omml-builder-audit-v0.md` (PAPER-11) already probed
Meridian's `latex_to_omml_local`/`_stdlib_append_mathml` live, against 38 hand-picked LaTeX
strings, and found several defect classes. This item asks two further questions PAPER-11 could
not: (1) do those defects actually occur on **real, organic formulas** from a citable benchmark
corpus, not just hand-picked adversarial LaTeX, and (2) how does Meridian's converter compare
against an **independent second implementation** — Microsoft's own MML2OMML.XSL — on the exact
same formulas?

**What was executed live** (every OMML string quoted below came from one of these three real
calls, not from reading source):

1. `meridian_docs.docs_intel.latex_to_omml_local(latex)` — imported unmodified from this
   pixi environment's editable `meridian-docs-mcp` dependency
   (`C:\Users\13144\Documents\Meridian\repository\extensions\meridian-docs\meridian_docs\docs_intel.py`),
   exactly as PAPER-11 did.
2. Microsoft's real, pinned `MML2OMML.XSL`
   (`C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL`, SHA-256
   `fdbb663cbbf0ab0b8387d1c65f6691ac6771e96bbb8b4a256af251834e35ed72`, shipped with WINWORD.EXE
   16.0.20326.20112 on this host), run via `lxml.etree.XSLT` directly against each case's MathML.
3. `docs_intel._stdlib_append_mathml` called directly (one supplementary probe, D1-13 only —
   see Section 5.3).

No product code was read-and-transcribed in place of running it, no product code was modified,
and no dataset content is redistributed — only the 13 individual formulas actually used are
quoted, each with its exact source-record path and SHA-256.

**Independent inspection**: every OMML output (from both converters) was re-parsed and
classified by a from-scratch Python structural inspector
(`s10_run_conversions.py::classify_omml`, methodology retained in this session's scratchpad and
reproducible from the manifest) that does **not** call either converter's own validator. It
checks for the specific OOXML element each category requires (`m:f`, `m:rad`, `m:nary`, `m:acc`,
`m:d`, `m:eqArr`/`m:m`, `m:func`/`m:limLow`, `m:sSub`/`m:sSup`/`m:sPre`), whether that element's
required children carry non-empty content, and whether the whole tree has silently flattened to
plain text runs. Results were then cross-checked a second, independent way by round-tripping the
materialized DOCX fixtures back through the live `extract_equations` MCP tool and diffing the
extracted OMML against what was written — byte-identical in every case (Section 4).

## 2. Case list: 13 D1 categories, one case each

9 categories are backed by a real MathMLben record, selected by scanning all 374 usable records
(both `math_inputtex` and `correct_mml` present) for a category-matching regex over
`math_inputtex`, then hand-verifying the match. 4 categories (alignment, malformed/empty
operands, forbidden flattening, plus one supplementary function/limit control) are explicit
hand-authored LaTeX/MathML pairs, used only where MathMLben's inline, single-formula corpus does
not naturally contain the construct — stated explicitly per case below, not silently substituted.

| case | category | source | LaTeX / MathML used |
|---|---|---|---|
| D1-01 | fraction | mathmlben #27 | `v = \frac{c}{n}` |
| D1-02 | radical | mathmlben #65 | `H^1(K)=\sqrt{2}` |
| D1-03 | n-ary w/ limits | mathmlben #36 | `n = \prod_{i=1}^r p_i^{a_i}` |
| D1-04 | matrix/array | mathmlben #285 | `|A| = \begin{vmatrix} a & b\\c & d \end{vmatrix}=ad-bc` |
| D1-05 | accent | mathmlben #237 | `h_{i}=\sum_{j}\hat{w}_{ij}s_{j}` |
| D1-06 | fence | mathmlben #26 | `L\left(C\right) \leq L\left(T\right)` |
| D1-07 | binomial | mathmlben #295 | `\binom{n}{k} = \frac{n!}{k!(n-k)!}.` |
| D1-08a | functions/limits | mathmlben #103 | `\operatorname{ph}z=\theta+2n\pi,` |
| D1-08b | functions/limits (hand) | hand-authored | `\lim_{x \to 0} f(x)` |
| D1-09 | scripts/multi-scripts | mathmlben #110 | `f(x)=\sum^{\infty}_{k=0}a_{k}x^{k}` |
| D1-10 | alignment (hand) | hand-authored | `\begin{aligned}x&=1\\y&=2\end{aligned}` |
| D1-11 | punctuation/numbering | mathmlben #35 | `P(n) = \frac{k}{n}.` |
| D1-12 | malformed/empty operands (hand) | hand-authored | `\frac{}{}` |
| D1-13 | forbidden flattening (hand) | hand-authored | MathML `mmultiscripts` (no LaTeX form exists) |

**Honest gap**: MathMLben's real, naturally-occurring corpus contains `\operatorname{}` calls but
no bare `\lim`/`\min`/`\max`/`\sup`/`\inf` under any reasonable length bound (checked up to 90
characters across all 374 records) — so D1-08b supplements D1-08a with one hand-authored `\lim`
control specifically to re-test PAPER-11's `\lim` finding independently. D1-09's organic record
turned out to carry a big-operator-with-limits feature (`\sum^{\infty}_{k=0}`) alongside its
simple single-level scripts (`a_k`, `x^k`) — reported honestly below rather than re-labeled to
look like a cleaner multi-script-only example.

## 3. Headline comparative findings

All classifications and raw OMML strings are in `docs/equation-d1-fixture-manifest-v1.json`
(`cases[]`). Summary:

| case | category | Meridian result | MS MML2OMML.XSL result |
|---|---|---|---|
| D1-01 | fraction | correct | correct |
| D1-02 | radical | correct | correct |
| D1-03 | n-ary w/ limits | **lossy — side-script (`sSubSup`), not `m:nary`** | correct — real `m:nary` |
| D1-04 | matrix/array | correct grid, but `|...|` bars flattened to text | correct grid **and** proper `m:d` fence w/ `begChr`/`endChr="|"` |
| D1-05 | accent | correct | correct, **plus a spurious duplicate `<m:acc>`** (Section 5.1) |
| D1-06 | fence | **totally flattened** — no structure at all | correct — builds `m:func`+`m:d` for `L(...)` |
| D1-07 | binomial | **visibly wrong** — real fraction bar, parens lost | correct — `m:d` fence around a bar-less (`noBar`) fraction |
| D1-08a | functions/limits (`\operatorname`) | **totally flattened** — no `m:func` at all | correct `m:func` |
| D1-08b | functions/limits (`\lim`) | lossy — `sSub` on plain-text "lim" | correct `m:limLow` |
| D1-09 | scripts/multi-scripts | correct side-scripts | correct side-scripts (but see Section 5.2) |
| D1-10 | alignment | **fails closed (`None`)** | correct — represents it as a hidden-placeholder `m:m` matrix |
| D1-11 | punctuation/numbering | correct (period stays inside the same run) | correct (no period — see Section 5.4) |
| D1-12 | malformed/empty operands | accepts empty num/den | **also** accepts empty num/den |
| D1-13 | forbidden flattening (prescript) | no LaTeX path; internal probe **flattens to `X3412`** | correct — real `m:sPre` prescript |

Nine of thirteen categories show Microsoft's independent reference producing a structurally
correct result where Meridian's converter is lossy, flattened, or visibly wrong (D1-03, D1-04's
fence, D1-06, D1-07, D1-08a, D1-08b, D1-10, D1-13). This is not a new claim — PAPER-11 already
found the nary/fence/binomial/function/lim/alignment defect classes by direct probing — but it is
the first time those exact defect classes are (a) confirmed on organic, citable formulas rather
than hand-picked LaTeX, and (b) shown against a second, independently-authored converter getting
the same inputs right. Two findings below are new to this session.

## 4. Independent cross-check: round-trip through a real DOCX

Every accepted OMML string (13 Meridian outputs incl. the D1-13 internal probe, 14 MS-XSL
outputs) was injected into a **real python-docx-template** DOCX — not the minimal
`document.xml`-only package `tools/build_tier1_fixtures.py` uses, which
`docs/omml-builder-audit-v0.md` §5.7/§8 already found Word can refuse to open. Each paragraph
was stamped with a real `w14:paraId`. The two consolidated fixtures:

| fixture | cases included | SHA-256 |
|---|---|---|
| `paper-s10-d1-meridian.docx` | 13 (all except D1-10, which failed closed) | `3fdb8a1533d48548f72afa74bfb7e0d4afefe70d9654a7f9411f0eadce4d0446` |
| `paper-s10-d1-msxsl.docx` | 14 (all) | `7e8e6f62e17be26dada0dcc40d931f051fa4df45694b3c383c26484bc8b5a14a` |

Both were then read back through the live `extract_equations` MCP tool. Every extracted
`omml_raw` string was **byte-identical** to what was written — this is independent confirmation
that (a) the DOCX package round-trips through a real OOXML zip write/read without corruption, and
(b) the earlier structural classification was not an artifact of reading the in-memory string
before it was ever serialized.

`audit_equation_style` was also run against both fixtures live. It flagged all 13/14 equations as
`misaligned_equation` (left, not center) and `missing_trailing_punctuation` — expected and
correctly reported, since these fixtures were built by direct XML injection rather than through
Meridian's own `insert_equation` (which applies `style_policy` centering and paragraph
conventions automatically); this is a property of how the fixture was assembled, not a converter
finding. One genuine, useful side-finding did fall out of it: D1-11's Meridian output keeps the
source LaTeX's trailing period **inside the same `<m:oMath>`** as a final run (because the
period was part of the literal LaTeX string handed to `latex_to_omml_local`), and
`audit_equation_style`'s trailing-punctuation check — which looks for a separate run
**immediately after** the `m:oMath` node — does not see it and flags it as missing punctuation
regardless. The equation is not wrong, but it is invisible to this document-level style check
because of *where* the punctuation structurally lives. This is worth a follow-up note for
whoever owns `audit_equation_style` next, not a fix made here.

## 5. New findings this session (not in PAPER-11)

### 5.1 Microsoft's own MML2OMML.XSL duplicates content on genuine LaTeXML "parallel markup" MathML — root-caused, not just observed

D1-05's MS-XSL output contains **two** `<m:acc>` elements for `\hat{w}` — one correctly nested
inside the `m:nary`'s summand, one spurious, floating right before `</m:oMath>`. This was
root-caused, not just noted: record 237's `correct_mml` embeds a Content-MathML
`<annotation-xml encoding="MathML-Content">` sibling block (LaTeXML's standard "parallel markup"
convention), and because the Wikidata definition for `\hat{w}` is unresolved
(`"hat{w}_{ij}": ["synaptic weight", {}]` — an empty QID map), LaTeXML's fallback there embeds a
raw presentation-MathML `<mover accent="true">` fragment *inside* a `<ci>` wrapper in that
Content-MathML block, instead of a clean `<csymbol>` reference. Stripping the
`<annotation-xml>`/`<annotation>` block and re-running the **same, unmodified** MML2OMML.XSL
transform drops the duplicate: 2 `<m:acc>` → 1. Confirmed by direct A/B transform, in
`docs/equation-d1-fixture-manifest-v1.json` under `D1-05.msxsl_annotation_stripped_probe`.

This matters directly for this item's own instruction ("do not use MML2OMML output as gold
without independent inspection") — it is exactly the kind of defect that instruction anticipates,
and it only shows up on real, in-the-wild "parallel markup" MathML of the kind a genuine digital
library or LaTeXML pipeline produces, not on clean textbook-only presentation MathML. It should
not be over-generalized: it was observed on 1 of 9 organic records, and the trigger condition
(an unresolved semantic annotation falling back to an embedded presentation fragment) is
specific and now precisely named, not "MS's XSL is unreliable" in general.

### 5.2 MS-XSL's function-detection heuristic over-fires on some non-function constructs

D1-06 (`L(C) \le L(T)`) and D1-09's inner `\sum^\infty_{k=0}a_k x^k` term are both wrapped in
`m:func` by MS-XSL, treating "identifier immediately followed by parenthesised/juxtaposed
content" as a function application even when there is no function-call semantics (a plain
variable `L` followed by a fenced argument; a big-operator term followed by its coefficient).
This is visually mostly harmless (the rendering looks the same either way) but is a real
structural-semantics quirk in the reference converter, and is exactly why this item asked that
MML2OMML output be independently inspected rather than treated as unconditional gold.

### 5.3 Meridian's `_stdlib_append_mathml`, called directly on a genuine prescript, reproduces PAPER-11's case 32 exactly

Since `latex_to_omml_local` has no LaTeX-side prescript input path at all (no LaTeX package for
`mmultiscripts` was fed), D1-13's "Meridian" result is `not_applicable` for the primary
LaTeX-in comparison. As a supplementary probe (same live-function methodology as PAPER-11 case
32), `docs_intel._stdlib_append_mathml` was called directly on the D1-13 MathML
(`mmultiscripts`: base `X`, sub `3`, sup `4`, presub `1`, presup `2`). Result:
`<m:oMath><m:r><m:t>X3412</m:t></m:r></m:oMath>` — total flattening, all four script positions
merged into one indistinguishable digit string, zero structural tags. MS-XSL, given the identical
MathML, produces a correct `<m:sPre>` prescript structure. This is the cleanest side-by-side
comparison in the whole ablation: identical input, one implementation destroys the information
completely, the other renders it correctly.

### 5.4 The malformed-empty-operand finding is not Meridian-specific

PAPER-11 §6 documented that Meridian's `_validate_omml_structure` accepts an `<m:f>` with both
`<m:num>`/`<m:den>` empty. This session independently confirmed Meridian still does
(`<m:f><m:num><m:e/></m:num><m:den><m:e/></m:den></m:f>` for `\frac{}{}`) — but also found that
**Microsoft's own MML2OMML.XSL does the same thing** for the equivalent empty `<mfrac>` MathML
(`<m:f><m:fPr><m:type m:val="bar"/></m:fPr><m:num/><m:den/></m:f>`, no `<m:e>` wrapper at all but
equally empty). This reframes PAPER-11's finding: an OOXML writer accepting a structurally
well-formed but visually-empty fraction is not uniquely a Meridian validator gap — it appears to
be permitted by the format itself, at least as far as Microsoft's own reference converter is
concerned. The actionable lever remains the same (Meridian's own `_validate_omml_structure`
choosing to be *stricter* than the format technically requires), but "the format allows this"
and "Meridian's validator misses it" are different claims, and only the second one is something
Meridian's own code controls.

## 6. Word-render receipts: blocked this session (honest gap, not fabricated)

The item requires "Word-render every accepted fixture" and retained PDF hashes/receipts. This
was attempted five times against three different files through two different tool entry points,
and **every attempt timed out**:

| target | method | result |
|---|---|---|
| `paper-s10-d1-meridian.docx` (13 eqs) | `check_render_capability` | client-side request timeout |
| `paper-s10-d1-msxsl.docx` (14 eqs) | `check_render_capability` | client-side request timeout |
| `baseline-sanity.docx` (1 eq) | `check_render_capability` | timeout, no WINWORD.EXE spawned |
| `baseline-sanity.docx` (1 eq), retry | `check_render_capability` | timeout, no WINWORD.EXE spawned |
| `adversarial/raw-empty-num.docx` | `insert_equation(allow_degraded_render=True)` | timeout; WINWORD.EXE (PID 17420) spawned and had to be manually terminated |

Two of the five attempts visibly spawned a real `WINWORD.EXE` process (PID 33628, then PID
17420), one of which ran for several minutes before this session terminated it with `taskkill`.
Word COM itself is confirmed installed on this host (`WINWORD.EXE` file present, version
`16.0.20326.20112` read successfully) and was independently confirmed **live-functional on this
exact host** in `docs/omml-builder-audit-v0.md` §8 on 2026-08-26. The most likely explanation is
Word-COM contention from other concurrent agent sessions active in this same repository during
this wave (this task's own operating instructions note several sibling `PAPER-S*` items were
running in parallel) — consistent with `docs/omml-builder-audit-v0.md`'s own §8 observation that
orphaned `WINWORD.EXE` processes can accumulate across a session even on otherwise-successful
runs. This was not diagnosed further, per this task's instruction not to retry a failing
operation in a loop.

One genuine positive did fall out of the one `insert_equation` attempt: the file was confirmed,
by SHA-256, to have been **restored to its exact pre-call byte state**
(`783ce36bd7c4beeae4ca23663938a209c5172124fff57b9be23756a0ae8dfa87`, matching its own
`.bak`) rather than left partially written when the render step could not complete —
independent, live confirmation that the fail-closed promote/restore contract described in
`docs/omml-builder-audit-v0.md` §2 held even when the render backend itself hung.

**Consequence, stated plainly**: no PDF receipt, no Word-openability confirmation, and no visual
rendering was obtained for any D1 fixture this session. This is recorded in
`docs/equation-d1-fixture-manifest-v1.json` (`word_render_status`) as `blocked_this_session`
with the full attempt log, not glossed over or reported as passing.

## 7. Latency and memory

Both converters ran in well under a second per formula; exact per-case numbers are in the
manifest (`latency_s` fields). Representative: D1-01 (simple fraction) — Meridian 0.6 ms request
latency observed in an earlier standalone probe of MML2OMML.XSL was 1.6 ms; both converters'
per-case `latency_s` in the manifest are consistently sub-10-millisecond for every one of the 14
cases. Memory was measured with Python's `tracemalloc` (`peak_traced_bytes` per case) — this is a
real, reproducible number but is scoped to Python-heap allocations traced during the call only;
it is not a process-level RSS profile and is reported with that caveat rather than as a
general "memory footprint" claim.

## 8. What this item does not establish

This is a 13-case bounded ablation, not a corpus-scale benchmark — it should not be read as a
prevalence estimate ("X% of real formulas trigger this defect"); it is a targeted, evidence-based
confirmation that each named defect class occurs on organic input, not only on hand-picked
adversarial LaTeX. No Word-render, visual-fidelity, or PDF-receipt evidence was obtained (Section
6). The `\lim`/multiscript/alignment/malformed-operand/forbidden-flattening categories rely on
hand-authored LaTeX/MathML pairs where the organic corpus did not supply a natural example —
each one is labeled as such above, not blended silently into the "organic" count. No claim here
overrides or narrows `docs/omml-builder-audit-v0.md`'s own findings; this item corroborates and
extends them with a second, independent converter and organic inputs, and adds three findings
(5.1, 5.3, 5.4) that are new.

## 9. Evidence index

- `E:\MeridianData\ooxml-graph-paper\runs\equations\s10-conversion-results.json` — full raw
  per-case conversion results (both converters, both classifications, both supplementary probes).
- `E:\MeridianData\ooxml-graph-paper\runs\equations\fixtures\paper-s10-d1-meridian.docx` /
  `paper-s10-d1-msxsl.docx` — materialized D1 fixtures (hashes above).
- `E:\MeridianData\ooxml-graph-paper\runs\equations\fixtures\adversarial\` — the three adversarial
  raw-OMML control base files and the one attempted (timed-out, restored) `insert_equation` call.
- `docs/equation-d1-fixture-manifest-v1.json` — the consolidated, machine-readable version of all
  of the above, including every raw OMML string quoted in this document.
