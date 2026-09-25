"""Tests for tools/margin_notes/build_doc_from_tex.py (the margin_notes DOC generator)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "tools" / "margin_notes" / "build_doc_from_tex.py"
_spec = importlib.util.spec_from_file_location("build_doc_from_tex", MODULE_PATH)
bd = importlib.util.module_from_spec(_spec)
sys.modules["build_doc_from_tex"] = bd
_spec.loader.exec_module(bd)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_renderer(labels=None, cites=None, numbers_path: Path | None = None):
    warnings: list[str] = []
    r = bd.Renderer(labels or {}, cites or {"a2020": "A 2020", "b2021": "B & C 2021"},
                    bd.Numbers(numbers_path or Path("does-not-exist-numbers.json")), warnings)
    return r, warnings


def tpl(s: str) -> str:
    return bd.cites_to_template(s)


OLD_HTML_TEMPLATE = """<!doctype html>
<html><body>
<div id="docInner"></div>
<script>
const META = {
  id: 'fixture',
  title: 'Fixture',
};
const CITES = {
  a2020: 'A 2020',
};
function cite(...keys) {
  return ` <cite contenteditable="false">(${keys.map(k => CITES[k] || k).join('; ')})</cite>`;
}

const SECTIONS = [
  { id: 'front', label: 'Title & abstract' },
  { id: 'intro', label: 'Intro (short)' },
];

const DOC = [
%DOC%
];

const PARA_IDS = DOC.filter(b => !b.type).map(b => b.id);
</script>
</body></html>
"""

AUX = r"""\relax
\newlabel{sec:intro}{{1}{1}{Introduction}{section.1}{}}
\newlabel{sec:methods-rerun}{{3.7}{8}{Confirmatory re-run environment}{subsection.3.7}{}}
\newlabel{tab:x}{{2}{3}{Caption with \emph {braces}}{table.2}{}}
"""

BIB = r"""@article{a2020,
  title = {{Alpha} Paper},
  author = {Aardvark, Ann},
  journal = {J. Things},
  year = {2020},
}
@misc{b2021,
  title = {Beta},
  author = {Bee, Bob and Cee, Carl},
  year = {2021},
}
@misc{c2022,
  title = {Gamma},
  author = {Dee, D. and Eff, E. and Gee, G.},
  year = {2022},
}
@techreport{org,
  title = {Spec},
  author = {{Ecma International}},
  year = {2016},
}
"""


def write_fixture(tmp_path: Path, tex_body: str, doc_js: str, numbers: dict | None = None,
                  html_newline: str = "\n") -> list[str]:
    tex = ("\\documentclass{article}\n\\newcommand{\\todo}[1]{#1}\n\\begin{document}\n\\maketitle\n"
           + tex_body + "\n\\end{document}\n")
    (tmp_path / "main.tex").write_text(tex, encoding="utf-8", newline="\n")
    (tmp_path / "main.aux").write_text(AUX, encoding="utf-8", newline="\n")
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8", newline="\n")
    if numbers is not None:
        (tmp_path / "numbers.json").write_text(json.dumps(numbers), encoding="utf-8")
    (tmp_path / "mn.html").write_text(OLD_HTML_TEMPLATE.replace("%DOC%", doc_js), encoding="utf-8",
                                      newline=html_newline)
    return ["--tex", str(tmp_path / "main.tex"), "--aux", str(tmp_path / "main.aux"),
            "--bib", str(tmp_path / "refs.bib"), "--numbers", str(tmp_path / "numbers.json"),
            "--html", str(tmp_path / "mn.html"), "--preview", str(tmp_path / "preview.html"), "--no-node"]


def generate(args: list[str]):
    ns = type("A", (), {})()
    it = iter(args)
    for k in it:
        if k.startswith("--") and k not in ("--no-node",):
            setattr(ns, k[2:].replace("-", "_"), next(it))
    return bd.generate(ns)


# ---------------------------------------------------------------------------
# inline conversion
# ---------------------------------------------------------------------------

def test_inline_formatting_dashes_escapes():
    r, w = make_renderer()
    got = r.render(r"\emph{a} \textbf{b} \texttt{c\_d} -- e --- f 50\% ``q'' x~y \texttt{<m:oMath>} vs.\ z")
    assert got == ('<em>a</em> <strong>b</strong> <code>c_d</code> &ndash; e &mdash; f 50% "q" x y '
                   '<code>&lt;m:oMath&gt;</code> vs. z')
    assert w == []


def test_math_flattening():
    r, _ = make_renderer()
    assert r.render(r"($p=0.0015$)") == "(p=0.0015)"
    assert r.render(r"$K=4$ cycles") == "K=4 cycles"
    assert r.render(r"[86.8, 100]$^\dagger$") == "[86.8, 100]†"
    assert r.render(r"$p<0.001$") == "p&lt;0.001"
    assert r.render(r"3 $\times$ 4") == "3 x 4"
    assert r.render(r"Tier 3 ($n_\text{eff}$)") == "Tier 3 (n_eff)"
    assert r.render(r"Inline citation$^{\text{a}}$") == "Inline citation<sup>a</sup>"
    assert r.render(r"a further $\sim$12{,}000 docs") == "a further ~12,000 docs"
    assert r.render(r"$\text{ICC}=0.124$") == "ICC=0.124"
    assert r.render(r"all $\ll$ the 90s timeout") == "all much less than the 90s timeout"


def test_ref_resolution(tmp_path):
    aux = tmp_path / "main.aux"
    aux.write_text(AUX, encoding="utf-8")
    labels = bd.parse_aux(aux)
    assert labels["tab:x"].title == r"Caption with \emph {braces}"
    r, w = make_renderer(labels=labels)
    assert r.render(r"Section~\ref{sec:methods-rerun} and Table~\ref{tab:x}") == "Section 3.7 and Table 2"
    assert r.render(r"\Cref{tab:x}; \cref{sec:intro}") == "Table 2; section 1"
    assert r.render(r"Section~\ref{sec:nope}") == "Section ??"
    assert any("sec:nope" in x for x in w)


def test_citations_template_and_static():
    r, w = make_renderer()
    got = tpl(r.render(r"tools alike \citep{a2020,b2021} -- and \citet{a2020} find"))
    assert got == "tools alike ${cite('a2020','b2021')} &ndash; and ${cite('a2020')} find"
    assert r.render_static(r"x \citep{b2021}") == 'x <cite contenteditable="false">(B &amp; C 2021)</cite>'
    r.render(r"\citep{zzz}")
    assert any("zzz" in x for x in w)


def test_bib_short_names(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(BIB, encoding="utf-8")
    names = {e.key: bd.bib_short_name(e) for e in bd.parse_bib(bib)}
    assert names == {"a2020": "Aardvark 2020", "b2021": "Bee & Cee 2021", "c2022": "Dee et al. 2022",
                     "org": "Ecma International 2016"}


def test_val_renders_numbers_json(tmp_path):
    nj = tmp_path / "numbers.json"
    nj.write_text(json.dumps({"_meta": {}, "values": {"k4.n": {"value": "2{,}000", "status": "verified"},
                                                         "pct": {"value": "83.3"}}}), encoding="utf-8")
    r, _ = make_renderer(numbers_path=nj)
    assert r.render(r"(\val{k4.n} resamples, \val{pct}\%)") == "(2,000 resamples, 83.3%)"


def test_val_fails_loudly_on_missing_file_or_key(tmp_path):
    r, _ = make_renderer(numbers_path=tmp_path / "numbers.json")
    with pytest.raises(bd.GenerationError, match="stats.alpha"):
        r.render(r"\val{stats.alpha}")
    (tmp_path / "numbers.json").write_text(json.dumps({"values": {"other": {"value": "1"}}}), encoding="utf-8")
    r2, _ = make_renderer(numbers_path=tmp_path / "numbers.json")
    with pytest.raises(bd.GenerationError, match="stats.beta"):
        r2.render(r"\val{stats.beta}")


def test_claim_is_stripped_in_text_but_kept_in_tex(tmp_path):
    r, _ = make_renderer()
    assert r.render(r"\claim{c-1}{The \emph{bounded} tool wins} here.") == "The <em>bounded</em> tool wins here."
    args = write_fixture(tmp_path, "\\section{Introduction}\n\\label{sec:intro}\n"
                         "Before \\claim{c-1}{the \\textbf{claim}} after.\n", "")
    res = generate(args)
    para = next(b for b in res.final if b.kind == "para")
    assert para.tex == r"Before \claim{c-1}{the \textbf{claim}} after."
    assert para.text == "Before the <strong>claim</strong> after."


def test_todo_and_pending():
    r, _ = make_renderer()
    assert r.render(r"x \todo{fix -- this}") == 'x <span class="editorial-flag">[TODO: fix &ndash; this]</span>'
    assert r.render(r"\pending{soon}") == '<span class="editorial-flag">[PENDING: soon]</span>'


# ---------------------------------------------------------------------------
# block structure
# ---------------------------------------------------------------------------

def test_footnote_extraction(tmp_path):
    args = write_fixture(tmp_path, "\\section{Introduction}\n\\label{sec:intro}\n"
                         "Main text here.\\footnote{Commit \\texttt{abc1234}, see $K=4$.} More text.\n", "")
    res = generate(args)
    kinds = [(b.kind, b.id) for b in res.final]
    assert kinds == [("para", "intro-1"), ("footnote", "intro-1-fn1")]
    para, fn = res.final
    assert para.text == "Main text here. More text."
    assert "\\footnote{Commit" in para.tex
    assert fn.tex == r"[footnote] Commit \texttt{abc1234}, see $K=4$."
    assert fn.text == '<span class="footnote-block">Footnote: Commit <code>abc1234</code>, see K=4.</span>'
    assert para.h2 == "Introduction"


def test_table_parsing_multirow_rules_dagger(tmp_path):
    table = r"""\section{Introduction}
\label{sec:intro}
\begin{table}[h]
\centering
\small
\begin{tabular}{lccc}
\toprule
Family & Arm & 95\% CI & Paired $p$ \\
\midrule
Bibliography entry & control   & [86.8, 100]$^\dagger$ & \multirow{2}{*}{1.0} \\
                   & treatment & [86.8, 100]$^\dagger$ & \\
\addlinespace
Caption$^{\text{c}}$ & control & [0, 19.2] & \multirow{2}{*}{\textbf{$<0.001$}} \\
                   & treatment & [1, 2] & \\
\bottomrule
\end{tabular}
\normalsize
\caption{A caption citing \citep{a2020} and Table~\ref{tab:x}.}
\label{tab:x}
\end{table}
"""
    res = generate(write_fixture(tmp_path, table, ""))
    t = res.final[0]
    assert (t.kind, t.id, t.label) == ("table", "tab-x", "Table 2")
    assert t.headers == ["Family", "Arm", "95% CI", "Paired p"]
    assert t.rows == [
        ["Bibliography entry", "control", "[86.8, 100]†", "1.0"],
        ["Bibliography entry", "treatment", "[86.8, 100]†", ""],
        ["Caption<sup>c</sup>", "control", "[0, 19.2]", "<strong>&lt;0.001</strong>"],
        ["Caption<sup>c</sup>", "treatment", "[1, 2]", ""],
    ]
    assert tpl(t.caption) == "A caption citing ${cite('a2020')} and Table 2."
    assert t.h2 == "Introduction"


def test_enumerate_split_with_defect_leads_and_inline_lists(tmp_path):
    doc_js = "{ id: 'defects-intro', tex: `x`, section: 'defects', h2: 'Defects', text: `Intro.` },"
    body = r"""\section{Defects}
\label{sec:defects}
Intro.

\begin{enumerate}
\item \textbf{First bug.} It broke.
\item Second, without a bold lead.
\end{enumerate}

Task list: \begin{itemize} \item \textbf{A} -- one. \item \textbf{B} -- two. \end{itemize}
Then \begin{description}\item[RQ1] Why? \end{description} done.
"""
    args = write_fixture(tmp_path, body, doc_js)
    text = (tmp_path / "mn.html").read_text(encoding="utf-8").replace(
        "{ id: 'intro', label: 'Intro (short)' },", "{ id: 'defects', label: 'Ten defects' },")
    (tmp_path / "mn.html").write_text(text, encoding="utf-8")
    res = generate(args)
    paras = [b for b in res.final if b.kind == "para"]
    assert [b.id for b in paras] == ["defects-intro", "defect-1", "defect-2", "defects-1"]
    assert paras[1].text == "<strong>Defect 1: First bug.</strong> It broke."
    assert paras[1].tex == r"\textbf{First bug.} It broke."
    assert paras[2].text == "<strong>Defect 2:</strong> Second, without a bold lead."
    assert paras[3].text == ("Task list: <strong>A</strong> &ndash; one. <strong>B</strong> &ndash; two. "
                             "Then <strong>RQ1</strong>: Why? done.")
    assert "{ id: 'defects', label: 'Ten defects' }" in res.region


# ---------------------------------------------------------------------------
# id carry-forward
# ---------------------------------------------------------------------------

CF_DOC = r"""{ id: 'abstract', tex: `Abstract text.`, section: 'front', h2: 'Abstract', text: `Abstract text here for the fixture.` },
{ id: 'intro-1', tex: `x`, section: 'intro', h2: 'Introduction', text: `Alpha paragraph one two three four five six seven eight nine ten eleven twelve.` },
{ id: 'intro-beta', tex: `x`, section: 'intro', text: `Beta paragraph which will be deleted entirely from the source file right now.` },
{ id: 'references-note', tex: `hand`, section: 'intro', text: `Hand-authored note ${cite('a2020')} kept verbatim.` },
{ id: 'intro-gamma', tex: `x`, section: 'intro', text: `Gamma paragraph thirteen fourteen fifteen sixteen seventeen eighteen nineteen.` },"""

CF_TEX = r"""\begin{abstract}
Abstract text here for the fixture.
\end{abstract}
\section{Introduction}
\label{sec:intro}
Alpha paragraph one two three four five six seven eight nine TEN eleven twelve.

Gamma paragraph thirteen fourteen fifteen sixteen seventeen eighteen nineteen.

Delta is brand new content that did not exist before in any form whatsoever.
"""


def test_carry_forward_matched_new_dropped_and_hand_authored(tmp_path):
    res = generate(write_fixture(tmp_path, CF_TEX, CF_DOC))
    ids = [b.id for b in res.final]
    assert ids == ["abstract", "intro-1", "references-note", "intro-gamma", "intro-2"]
    assert res.status["intro-1"][0] == "matched" and res.status["intro-1"][1] < 1.0
    assert res.status["intro-gamma"][1] == 1.0
    assert res.dropped == ["intro-beta"]
    assert [b.id for b in res.new_blocks] == ["intro-2"]
    hand = res.final[2]
    assert hand.kind == "hand"
    assert hand.raw.startswith("{ id: 'references-note', tex: `hand`") and "${cite('a2020')}" in hand.raw
    assert res.final[1].h2 == "Introduction" and res.final[0].h2 == "Abstract"
    assert "intro-beta" in res.retired
    assert "{ id: 'intro', label: 'Intro (short)' }" in res.region   # existing nav label kept


def test_write_refuses_drop_unless_allowed_then_check(tmp_path):
    args = write_fixture(tmp_path, CF_TEX, CF_DOC)
    html_path = tmp_path / "mn.html"
    before = html_path.read_bytes()
    assert bd.main(["--check"] + args) == 1                      # markers missing
    assert bd.main(["--write"] + args) == 1                      # would drop intro-beta
    assert html_path.read_bytes() == before
    assert bd.main(["--write", "--allow-drop", "intro-beta"] + args) == 0
    after = html_path.read_bytes().decode("utf-8")
    assert bd.BEGIN_MARKER + "\nconst CITES = {" in after
    assert "];\n" + bd.END_MARKER + "\n\nconst PARA_IDS" in after
    assert bd.RETIRED_PREFIX + "intro-beta" in after
    # META and app code untouched
    assert after.split(bd.BEGIN_MARKER)[0] == before.decode("utf-8").split("const CITES = {")[0]
    assert bd.main(["--check"] + args) == 0
    # regeneration is a fixed point, and a retired id is never reused
    res = generate(args)
    assert res.dropped == [] and res.new_blocks == []
    assert res.region == after[after.index(bd.BEGIN_MARKER):after.index(bd.END_MARKER) + len(bd.END_MARKER)]
    # a source edit makes --check fail
    tex = tmp_path / "main.tex"
    tex.write_text(tex.read_text(encoding="utf-8").replace("Delta is", "Delta was"), encoding="utf-8")
    assert bd.main(["--check"] + args) == 1


def test_crlf_file_stays_crlf_and_checks_clean(tmp_path):
    args = write_fixture(tmp_path, CF_TEX, CF_DOC, html_newline="\r\n")
    assert bd.main(["--write", "--allow-drop", "intro-beta"] + args) == 0
    raw = (tmp_path / "mn.html").read_bytes().decode("utf-8")
    assert raw.count("\n") == raw.count("\r\n")
    assert bd.main(["--check"] + args) == 0


def test_header_carry_forward_keeps_old_owner(tmp_path):
    doc_js = r"""{ id: 'tab-x', section: 'intro', type: 'table', label: 'Table 2', caption: `Cap.`, headers: ["A"], rows: [["1"]] },
{ id: 'intro-sub', tex: `x`, section: 'intro', h3: 'Sub', text: `Paragraph after the table with enough words to match well.` },"""
    body = r"""\section{Introduction}
\label{sec:intro}
\subsection{Sub}
\begin{table}\begin{tabular}{l}\toprule A \\ \midrule 1 \\ \bottomrule\end{tabular}\caption{Cap.}\label{tab:x}\end{table}

Paragraph after the table with enough words to match well.
"""
    res = generate(write_fixture(tmp_path, body, doc_js))
    tab, para = res.final
    assert (tab.id, tab.h2, tab.h3) == ("tab-x", "Introduction", None)
    assert (para.id, para.h3) == ("intro-sub", "Sub")
    assert res.dropped == []


def test_dropped_header_key_is_reported(tmp_path):
    doc_js = r"""{ id: 'intro-a', tex: `x`, section: 'intro', h2: 'Introduction', text: `First paragraph words one two three four five six.` },
{ id: 'intro-b', tex: `x`, section: 'intro', h3: 'Old sub', text: `Second paragraph words seven eight nine ten eleven twelve.` },"""
    body = r"""\section{Introduction}
\label{sec:intro}
First paragraph words one two three four five six.

Second paragraph words seven eight nine ten eleven twelve.
"""
    res = generate(write_fixture(tmp_path, body, doc_js))
    assert res.dropped == ["h:intro-b"]


# ---------------------------------------------------------------------------
# real repository (skipped when the paper/tool files are absent)
# ---------------------------------------------------------------------------

REAL = [REPO / "paper" / "main.tex", REPO / "paper" / "main.aux", REPO / "tools" / "margin_notes" / "margin_notes.html"]


@pytest.mark.skipif(not all(p.exists() for p in REAL), reason="real paper/tool files not present")
def test_real_repo_generation_is_idempotent(tmp_path):
    html = tmp_path / "margin_notes.html"
    shutil.copyfile(REAL[2], html)
    args = ["--html", str(html), "--preview", str(tmp_path / "p.html"), "--no-node",
            "--tex", str(REAL[0]), "--aux", str(REAL[1]), "--bib", str(REPO / "paper" / "refs.bib"),
            "--numbers", str(REPO / "paper" / "numbers.json")]
    res = generate(args)
    ids = [b.id for b in res.final]
    assert len(ids) == len(set(ids))
    for hid in bd.HAND_AUTHORED_IDS:
        if any(o.id == hid for o in res.old.blocks):
            assert hid in ids
    allow = ",".join(res.dropped)
    assert bd.main(["--write"] + (["--allow-drop", allow] if allow else []) + args) == 0
    assert bd.main(["--check"] + args) == 0
    again = generate(args)
    assert again.dropped == [] and again.new_blocks == []


@pytest.mark.skipif(shutil.which("node") is None or not all(p.exists() for p in REAL),
                    reason="node or real files not available")
def test_real_repo_preview_parses_in_node_and_build_chunks(tmp_path):
    args = ["--html", str(REAL[2]), "--preview", str(tmp_path / "p.html"),
            "--tex", str(REAL[0]), "--aux", str(REAL[1]), "--bib", str(REPO / "paper" / "refs.bib"),
            "--numbers", str(REPO / "paper" / "numbers.json")]
    res = generate(args)
    preview = tmp_path / "p.html"
    preview.write_text(bd.apply_region(res.old, res.region), encoding="utf-8", newline="")
    msgs = bd.verify_with_node(preview, res.final, REPO / "tools" / "margin_notes" / "build_chunks.js")
    assert msgs and all(m.startswith("ok") for m in msgs), msgs
