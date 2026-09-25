import io
import json
import sys
from pathlib import Path

import pytest

PAPER = Path(__file__).resolve().parent.parent / "paper"
sys.path.insert(0, str(PAPER))

import consistency  # noqa: E402
import gen_numbers  # noqa: E402

VALUES = {
    "respec.composite.treatment.t1.rate": {"value": "83.3", "status": "verified"},
    "respec.composite.control.t1.rate": {"value": "8.3", "status": "verified"},
    "harness.permutations": {"value": "2{,}000", "status": "verified"},
}

TEX = r"""\documentclass{article}
\input{numbers}
\begin{document}
\begin{abstract}
The bounded tool finishes \claim{respec-headline}{\val{respec.composite.treatment.t1.rate}\% of chains
against \val{respec.composite.control.t1.rate}\%}.
\end{abstract}
\section{Results}
We ran \val{harness.permutations} permutations. % 83.3 in a comment is ignored
\claim{respec-headline}{The tool completes \val{respec.composite.treatment.t1.rate}\% of chains}.
\section{Conclusion}
\claim{respec-headline}{a larger magnitude (\val{respec.composite.treatment.t1.rate}\%)}.
\end{document}
"""

CLAIMS = {"respec-headline": {"statement": "respec chain completion treatment vs control",
                              "depends_on": ["respec.composite.treatment.t1.rate"]}}


def test_render_tex_is_deterministic_and_defines_every_key():
    tex = gen_numbers.render_tex(VALUES)
    assert tex == gen_numbers.render_tex(dict(reversed(list(VALUES.items()))))
    for key, entry in VALUES.items():
        assert f"\\@namedef{{pv@{key}}}{{{entry['value']}}}" in tex
    assert "\\DeclareRobustCommand{\\val}" in tex


def test_load_numbers_rejects_bad_keys_and_values(tmp_path):
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"values": {"Bad Key": {"value": "1", "status": "verified"},
                                        "a.b": {"value": "5\\%", "status": "verified"},
                                        "c.d": {"value": "1", "status": "guess"}}}))
    with pytest.raises(ValueError) as exc:
        gen_numbers.load_numbers(p)
    msg = str(exc.value)
    assert "bad key syntax" in msg and "special character" in msg and "status" in msg


@pytest.mark.parametrize("printed,source,ok", [
    ("92.9", 0.9285714, True),     # proportion printed as a percentage
    ("92.9", 92.857, True),
    ("0.0015", 0.00149, True),
    ("0.0015", 0.0025, False),
    ("2{,}000", 2000, True),
    ("83.3", 0.8, False),
])
def test_matches_printed(printed, source, ok):
    assert gen_numbers.matches_printed(printed, source) is ok


def test_resolve_locator_handles_lists_and_dotted_keys():
    obj = {"results": [{"a.b": {"p": 0.5}}]}
    assert gen_numbers.resolve_locator(obj, "results.0.[a.b].p") == 0.5


def test_resolve_locator_selectors():
    obj = {"groups": [{"family": "bib", "k_pairs": 1, "p": 1.0},
                      {"family": "sr", "k_pairs": 1, "p": 0.27},
                      {"family": "sr", "k_pairs": 4, "p": 0.0015}]}
    assert gen_numbers.resolve_locator(obj, "groups[family=sr,k_pairs=4].p") == 0.0015
    assert gen_numbers.resolve_locator(obj, "groups[family=bib].p") == 1.0
    with pytest.raises(KeyError):
        gen_numbers.resolve_locator(obj, "groups[family=sr].p")


def test_doc_finds_sites_with_sections_and_ignores_comments():
    doc = consistency.Doc(TEX)
    vals = doc.value_sites()
    assert [v.name for v in vals].count("respec.composite.treatment.t1.rate") == 3
    claims = doc.claim_sites()
    assert [c.section for c in claims] == ["Abstract", "Results", "Conclusion"]
    assert claims[0].text.startswith("\\val{respec.composite.treatment.t1.rate}")


def test_literal_copies_ignores_val_and_comments():
    assert consistency.literal_copies(TEX, VALUES) == []
    assert consistency.literal_copies(TEX.replace("We ran", "About 83.3 of"), VALUES) == [
        ("83.3", ["respec.composite.treatment.t1.rate"])]


def test_literal_copies_ignores_tikz_and_version_numbers():
    vals = {"x.y": {"value": "1.5", "status": "verified"}, "a.b": {"value": "1.0", "status": "verified"}}
    tex = ("\\begin{document}\n\\begin{tikzpicture}\\node at (-3.4, 1.5) {};\\end{tikzpicture}\n"
           "under the Meridian Source License 1.0 (MSL-1.0).\n")
    assert consistency.literal_copies(tex, vals) == []
    assert consistency.literal_copies(tex + "a factor of 1.5\n", vals) == [("1.5", ["x.y"])]


def test_tripwire_lists_unchanged_sites_of_an_edited_claim():
    head = TEX.replace("The tool completes", "The bounded tool completes")
    items = consistency.tripwire(TEX, head, VALUES, VALUES, CLAIMS, CLAIMS)
    assert len(items) == 1
    text = items[0]
    assert "claim respec-headline" in text and "changed L10 Results" in text
    assert "Abstract" in text and "Conclusion" in text


def test_tripwire_flags_value_change_and_dependent_claims():
    new_vals = dict(VALUES)
    new_vals["respec.composite.treatment.t1.rate"] = {"value": "80.0", "status": "verified"}
    items = consistency.tripwire(TEX, TEX, VALUES, new_vals, CLAIMS, CLAIMS)
    assert any("83.3 -> 80.0" in i and "respec-headline" in i for i in items)


def test_tripwire_flags_removed_statement_of_a_value():
    head = TEX.replace(r"We ran \val{harness.permutations} permutations.", "We ran permutations.")
    items = consistency.tripwire(TEX, head, VALUES, VALUES, CLAIMS, CLAIMS)
    assert any("harness.permutations: its last use" in i for i in items)


def test_tripwire_quiet_when_nothing_connected_changed():
    head = TEX.replace(r"\section{Results}", r"\section{Results}" + "\nAn unrelated sentence.")
    assert consistency.tripwire(TEX, head, VALUES, VALUES, CLAIMS, CLAIMS) == []


def test_edit_texts_for_write_reports_only_added_lines():
    removed, introduced, result = consistency.edit_texts("Write", {"content": "a\nb\nc\n"}, "a\nc\n")
    assert introduced == "b" and result == "a\nb\nc\n"


def _run_hook(monkeypatch, fn, payload):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", err)
    return fn(), err.getvalue()


@pytest.fixture
def paper_dir(tmp_path, monkeypatch):
    (tmp_path / "numbers.json").write_text(json.dumps({"values": VALUES}), encoding="utf-8")
    (tmp_path / "main.tex").write_text(TEX, encoding="utf-8")
    monkeypatch.setattr(consistency, "TEX", tmp_path / "main.tex")
    monkeypatch.setattr(consistency, "NUMBERS_JSON", tmp_path / "numbers.json")
    monkeypatch.setattr(consistency, "NUMBERS_TEX", tmp_path / "numbers.tex")
    monkeypatch.setattr(consistency, "MIRROR_HTML", tmp_path / "margin_notes.html")
    return tmp_path


def test_hook_pre_blocks_hand_typed_registered_number(monkeypatch, paper_dir):
    code, err = _run_hook(monkeypatch, consistency.hook_pre, {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(paper_dir / "main.tex"), "old_string": "We ran",
                       "new_string": "Treatment reached 83.3\\% and we ran"}})
    assert code == 2 and "respec.composite.treatment.t1.rate" in err


def test_hook_pre_allows_val_and_existing_literals(monkeypatch, paper_dir):
    code, _ = _run_hook(monkeypatch, consistency.hook_pre, {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(paper_dir / "main.tex"), "old_string": "We ran",
                       "new_string": "Treatment reached \\val{respec.composite.treatment.t1.rate}\\% and we ran"}})
    assert code == 0
    code, _ = _run_hook(monkeypatch, consistency.hook_pre, {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(paper_dir / "main.tex"), "old_string": "was 83.3 then",
                       "new_string": "was 83.3 afterwards"}})
    assert code == 0


def test_hook_pre_blocks_editing_generated_files(monkeypatch, paper_dir):
    code, err = _run_hook(monkeypatch, consistency.hook_pre, {
        "tool_name": "Write", "tool_input": {"file_path": str(paper_dir / "numbers.tex"), "content": "x"}})
    assert code == 2 and "numbers.json" in err
    html = "<script>\nconst META={};\n// BEGIN GENERATED x\nconst DOC=[1];\n// END GENERATED\nrest\n</script>"
    (paper_dir / "margin_notes.html").write_text(html, encoding="utf-8")
    code, _ = _run_hook(monkeypatch, consistency.hook_pre, {
        "tool_name": "Edit", "tool_input": {"file_path": str(paper_dir / "margin_notes.html"),
                                            "old_string": "const DOC=[1];", "new_string": "const DOC=[2];"}})
    assert code == 2
    code, _ = _run_hook(monkeypatch, consistency.hook_pre, {
        "tool_name": "Edit", "tool_input": {"file_path": str(paper_dir / "margin_notes.html"),
                                            "old_string": "rest", "new_string": "rest2"}})
    assert code == 0


def test_hook_pre_ignores_unrelated_files(monkeypatch, paper_dir):
    code, _ = _run_hook(monkeypatch, consistency.hook_pre, {
        "tool_name": "Edit", "tool_input": {"file_path": str(paper_dir / "other.py"),
                                            "old_string": "a", "new_string": "83.3"}})
    assert code == 0
