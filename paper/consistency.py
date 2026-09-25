"""Keep connected statements in main.tex consistent.

Two kinds of connection are tracked:
  * values  -- \\val{key} reads a reported number from numbers.json, so every
               place that states that number changes together;
  * claims  -- \\claim{id}{text} marks a place that states a recurring claim
               listed in claims.json (e.g. the same result restated in the
               abstract, results and conclusion).

Commands:
  check             validate references; exit 1 on errors (used by preflight / pre-commit)
  report            list every claim and every value stated in more than one place
  sites NAME        list every place a claim id or value key is stated
  tripwire          compare against a base (default: HEAD) and list the OTHER places
                    that state what was just changed; exit 3 if anything needs review
  hook-pre          Claude Code PreToolUse hook (reads the tool call on stdin)
  hook-post         Claude Code PostToolUse hook (reads the tool call on stdin)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TEX = HERE / "main.tex"
NUMBERS_JSON = HERE / "numbers.json"
CLAIMS_JSON = HERE / "claims.json"
NUMBERS_TEX = HERE / "numbers.tex"
MIRROR_HTML = REPO / "tools" / "margin_notes" / "margin_notes.html"
MIRROR_GEN = REPO / "tools" / "margin_notes" / "build_doc_from_tex.py"
STATE_DIR = REPO / ".claude" / "state" / "consistency"
FIGURE_STAMP = HERE / "figures" / "figures.stamp.json"
TRACKED = {TEX: "paper/main.tex", NUMBERS_JSON: "paper/numbers.json", CLAIMS_JSON: "paper/claims.json"}

sys.path.insert(0, str(HERE))
import gen_numbers  # noqa: E402


# ---------------------------------------------------------------- parsing

@dataclass
class Site:
    name: str          # claim id or value key
    kind: str          # "claim" | "value"
    text: str          # claim body (claims) or "" (values)
    line: int
    section: str
    excerpt: str


def comment_mask(src: str) -> list[bool]:
    mask = [False] * len(src)
    for m in re.finditer(r"(?<!\\)%[^\n]*", src):
        for i in range(m.start(), m.end()):
            mask[i] = True
    return mask


def brace_arg(src: str, open_idx: int) -> int:
    """Index of the '}' matching the '{' at open_idx (backslash-escape aware)."""
    depth = 0
    i = open_idx
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"unbalanced brace starting at offset {open_idx}")


class Doc:
    def __init__(self, src: str):
        self.src = src
        self.mask = comment_mask(src)
        self.line_starts = [0] + [m.end() for m in re.finditer(r"\n", src)]
        self.sections = [(m.start(), m.group(1), m.group(2)) for m in
                         re.finditer(r"\\(section|subsection)\*?\{([^}]*)\}", src)]
        a = src.find("\\begin{abstract}")
        b = src.find("\\end{abstract}")
        self.abstract = (a, b) if a >= 0 and b >= 0 else (-1, -1)

    def line_of(self, pos: int) -> int:
        lo, hi = 0, len(self.line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def section_of(self, pos: int) -> str:
        if self.abstract[0] < pos < self.abstract[1]:
            return "Abstract"
        sec = sub = ""
        for spos, kind, title in self.sections:
            if spos > pos:
                break
            if kind == "section":
                sec, sub = title, ""
            else:
                sub = title
        return sec + (" > " + sub if sub else "")

    def excerpt(self, pos: int, width: int = 110) -> str:
        a = max(pos - 30, 0)
        return re.sub(r"\s+", " ", self.src[a:a + width]).strip()

    def macro_calls(self, name: str, nargs: int):
        for m in re.finditer(r"\\" + name + r"(?![A-Za-z])\s*\{", self.src):
            if self.mask[m.start()]:
                continue
            args = []
            open_idx = m.end() - 1
            end = open_idx
            for _ in range(nargs):
                while self.src[open_idx] != "{":
                    open_idx += 1
                end = brace_arg(self.src, open_idx)
                args.append(self.src[open_idx + 1:end])
                open_idx = end + 1
            yield m.start(), end + 1, args

    def value_sites(self) -> list[Site]:
        return [Site(a[0].strip(), "value", "", self.line_of(s), self.section_of(s), self.excerpt(s))
                for s, _e, a in self.macro_calls("val", 1)]

    def claim_sites(self) -> list[Site]:
        return [Site(a[0].strip(), "claim", norm(a[1]), self.line_of(s), self.section_of(s), self.excerpt(s))
                for s, _e, a in self.macro_calls("claim", 2)]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_claims(path: Path | None = None) -> dict[str, dict]:
    path = path or CLAIMS_JSON
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("claims", {})


def load_values_or_empty(path: Path | None = None) -> dict[str, dict]:
    path = path or NUMBERS_JSON
    if not path.exists():
        return {}
    return gen_numbers.load_numbers(path)


# ---------------------------------------------------------------- check

def check(src: str | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    doc = Doc(src if src is not None else TEX.read_text(encoding="utf-8"))
    try:
        values = load_values_or_empty()
    except (ValueError, json.JSONDecodeError) as exc:
        return [str(exc)], []
    claims = load_claims()
    vsites = doc.value_sites()
    csites = doc.claim_sites()

    used_keys = Counter(s.name for s in vsites)
    for key in sorted(set(used_keys) - set(values)):
        lines = [s.line for s in vsites if s.name == key]
        errors.append(f"\\val{{{key}}} (line {', '.join(map(str, lines))}) is not in numbers.json")
    figure_keys = set(figure_stamp().get("values", {}))
    for key in sorted(set(values) - set(used_keys) - figure_keys):
        warnings.append(f"numbers.json key {key} is not used in main.tex or the figures")

    used_claims = Counter(s.name for s in csites)
    for cid in sorted(set(used_claims) - set(claims)):
        errors.append(f"\\claim{{{cid}}} is not defined in claims.json")
    for cid in sorted(set(claims) - set(used_claims)):
        errors.append(f"claims.json claim {cid} has no \\claim site in main.tex (stale ledger entry?)")
    for cid, entry in claims.items():
        for key in entry.get("depends_on", []):
            if key not in values:
                errors.append(f"claims.json claim {cid} depends_on unknown value key {key}")

    if values:
        if not NUMBERS_TEX.exists():
            errors.append("numbers.tex is missing: run `python paper/gen_numbers.py`")
        elif NUMBERS_TEX.read_text(encoding="utf-8") != gen_numbers.render_tex(values):
            errors.append("numbers.tex is stale: run `python paper/gen_numbers.py`")
        if "\\input{numbers}" not in doc.src:
            errors.append("main.tex does not \\input{numbers}")

    for lit, keys in literal_copies(doc.src, values):
        warnings.append(f"literal {lit} in main.tex equals registered value(s) {', '.join(keys)} -- use \\val{{...}} if it is the same quantity")
    return errors, warnings


def figure_stamp() -> dict:
    if not FIGURE_STAMP.exists():
        return {}
    return json.loads(FIGURE_STAMP.read_text(encoding="utf-8"))


def figure_staleness() -> list[str]:
    """The figure PDFs are drawn from numbers.json; the stamp records the
    values each was drawn with, so a changed value means a stale figure."""
    try:
        values = load_values_or_empty()
    except (ValueError, json.JSONDecodeError):
        return []
    if not values:
        return []
    stamp = figure_stamp()
    if not stamp:
        return ["paper/figures/figures.stamp.json is missing: run `pixi run python tools/make_paper_figures.py`"]
    stale = [f"{k} ({v} -> {values[k]['value'] if k in values else 'removed'})"
             for k, v in stamp.get("values", {}).items() if k not in values or values[k]["value"] != v]
    if stale:
        return ["figures are stale (drawn from old values: " + ", ".join(stale) +
                "): run `pixi run python tools/make_paper_figures.py`"]
    return []


def strip_vals_and_comments(text: str) -> str:
    text = re.sub(r"(?<!\\)%[^\n]*", "", text)
    return re.sub(r"\\val\{[^}]*\}", " ", text)


LITERAL_RE = re.compile(r"(?<![A-Za-z0-9_.{])\d+\.\d+(?![0-9])")


def decimal_index(values: dict[str, dict]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for key, entry in values.items():
        v = entry["value"]
        if "." in v and "{" not in v:
            idx.setdefault(v, []).append(key)
    return idx


def literal_copies(text: str, values: dict[str, dict]) -> list[tuple[str, list[str]]]:
    idx = decimal_index(values)
    body = strip_vals_and_comments(text)
    begin = body.find("\\begin{document}")
    body = body[begin:] if begin >= 0 else body
    seen = Counter(m.group(0) for m in LITERAL_RE.finditer(body))
    return [(lit, sorted(idx[lit])) for lit in sorted(seen) if lit in idx]


# ---------------------------------------------------------------- tripwire

def git_show(relpath: str, ref: str = "HEAD") -> str:
    try:
        return subprocess.run(["git", "show", f"{ref}:{relpath}"], cwd=REPO, capture_output=True,
                              text=True, encoding="utf-8", check=True).stdout
    except subprocess.CalledProcessError:
        return ""


def fmt_site(s: Site) -> str:
    return f"L{s.line} {s.section or '(preamble)'}: \"{s.excerpt}\""


def tripwire(base_tex: str, head_tex: str, base_vals: dict, head_vals: dict,
             base_claims: dict, head_claims: dict) -> list[str]:
    base, head = Doc(base_tex), Doc(head_tex)
    items: list[str] = []

    bc = {}
    for s in base.claim_sites():
        bc.setdefault(s.name, []).append(s)
    hc = {}
    for s in head.claim_sites():
        hc.setdefault(s.name, []).append(s)
    for cid in sorted(set(bc) | set(hc)):
        old = [s.text for s in bc.get(cid, [])]
        new_sites = hc.get(cid, [])
        new = [s.text for s in new_sites]
        if Counter(old) == Counter(new):
            continue
        stmt = (head_claims.get(cid) or base_claims.get(cid) or {}).get("statement", "")
        label = f"claim {cid}" + (f" ({stmt})" if stmt else "")
        old_pool = Counter(old)
        changed, unchanged = [], []
        for s in new_sites:
            if old_pool[s.text] > 0:
                old_pool[s.text] -= 1
                unchanged.append(s)
            else:
                changed.append(s)
        removed = sum(old_pool.values())
        if not new_sites:
            items.append(f"- {label}: every site was removed. Remove it from claims.json, or restore a site.")
            continue
        what = []
        if changed:
            what.append("changed " + ", ".join(f"L{s.line} {s.section}" for s in changed))
        if removed:
            what.append(f"removed {removed} site(s)")
        if unchanged:
            items.append(f"- {label}: you {' and '.join(what)}. These other site(s) state the same claim "
                         f"and were NOT changed -- re-read them and update or confirm:\n"
                         + "\n".join("    " + fmt_site(s) for s in unchanged))
        elif removed and changed:
            items.append(f"- {label}: you {' and '.join(what)}; confirm the claim still holds where it remains.")

    for key in sorted(set(base_vals) & set(head_vals)):
        if base_vals[key]["value"] != head_vals[key]["value"]:
            sites = [s for s in head.value_sites() if s.name == key]
            deps = [cid for cid, c in head_claims.items() if key in c.get("depends_on", [])]
            msg = (f"- value {key} changed {base_vals[key]['value']} -> {head_vals[key]['value']}. "
                   f"It updates automatically at {len(sites)} site(s); re-read the surrounding text for "
                   f"wording that depended on the old number (e.g. 'significant', 'larger', 'all').")
            if deps:
                msg += f" Claims that depend on it: {', '.join(deps)}."
            if sites:
                msg += "\n" + "\n".join("    " + fmt_site(s) for s in sites)
            items.append(msg)

    bv = Counter(s.name for s in base.value_sites())
    hv_sites = head.value_sites()
    hv = Counter(s.name for s in hv_sites)
    for key in sorted(bv):
        if hv[key] < bv[key] and hv[key] > 0:
            rest = [s for s in hv_sites if s.name == key]
            items.append(f"- value {key}: a statement using it was removed; it is still stated at:\n"
                         + "\n".join("    " + fmt_site(s) for s in rest)
                         + "\n  If the result itself was dropped, remove these too.")
        elif hv[key] == 0 and bv[key] > 0:
            items.append(f"- value {key}: its last use in main.tex was removed (it stays in numbers.json).")
    return items


# ---------------------------------------------------------------- hooks

def hook_payload() -> tuple[str, Path | None, dict]:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return "", None, {}
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ((ti.get("edits") or [{}])[0].get("file_path"))
    return tool, (Path(fp).resolve() if fp else None), ti


def same(a: Path | None, b: Path) -> bool:
    return a is not None and os.path.normcase(str(a)) == os.path.normcase(str(b.resolve()))


def edit_texts(tool: str, ti: dict, current: str) -> tuple[str, str, str]:
    """(removed_text, introduced_text, resulting_text) for an edit tool call."""
    if tool == "Write":
        new = ti.get("content", "")
        remaining = Counter(current.splitlines())
        added = []
        for ln in new.splitlines():
            if remaining[ln] > 0:
                remaining[ln] -= 1
            else:
                added.append(ln)
        return current, "\n".join(added), new
    edits = ti.get("edits") or [ti]
    result = current
    removed, introduced = [], []
    for e in edits:
        old_s, new_s = e.get("old_string", ""), e.get("new_string", "")
        removed.append(old_s)
        introduced.append(new_s)
        if old_s and old_s in result:
            result = result.replace(old_s, new_s) if e.get("replace_all") else result.replace(old_s, new_s, 1)
    return "\n".join(removed), "\n".join(introduced), result


def generated_region(html: str) -> str | None:
    a = html.find("// BEGIN GENERATED")
    b = html.find("// END GENERATED")
    return html[a:b] if a >= 0 and b > a else None


def hook_pre() -> int:
    tool, path, ti = hook_payload()
    if tool not in {"Edit", "Write", "MultiEdit"}:
        return 0
    if same(path, NUMBERS_TEX):
        print("paper/numbers.tex is generated. Edit paper/numbers.json instead, then run "
              "`python paper/gen_numbers.py` (build.ps1 also regenerates it).", file=sys.stderr)
        return 2
    if same(path, MIRROR_HTML) and MIRROR_HTML.exists():
        current = MIRROR_HTML.read_text(encoding="utf-8")
        before = generated_region(current)
        if before is not None:
            _, _, after_text = edit_texts(tool, ti, current)
            if generated_region(after_text) != before:
                print("The manuscript region of margin_notes.html (between BEGIN/END GENERATED) is generated "
                      "from paper/main.tex. Edit main.tex, then run "
                      "`python tools/margin_notes/build_doc_from_tex.py --write`.", file=sys.stderr)
                return 2
        return 0
    if same(path, TEX):
        try:
            values = load_values_or_empty()
        except (ValueError, json.JSONDecodeError):
            return 0
        if not values:
            return 0
        current = TEX.read_text(encoding="utf-8")
        removed, introduced, _ = edit_texts(tool, ti, current)
        idx = decimal_index(values)
        had = Counter(m.group(0) for m in LITERAL_RE.finditer(strip_vals_and_comments(removed)))
        new = Counter(m.group(0) for m in LITERAL_RE.finditer(strip_vals_and_comments(introduced)))
        hits = [(lit, idx[lit]) for lit in sorted(new) if lit in idx and new[lit] > had[lit]]
        if hits:
            lines = []
            for lit, keys in hits:
                refs = ", ".join("\\val{" + k + "}" for k in sorted(keys))
                lines.append(f"  {lit} is registered as {refs}")
            print("This edit types a reported number into main.tex by hand. Reported numbers live in "
                  "paper/numbers.json so every place that states them stays in sync:\n" + "\n".join(lines) +
                  "\nWrite \\val{key} instead. If it is a different quantity that happens to share the value, "
                  "add it to numbers.json under its own key and use that.", file=sys.stderr)
            return 2
    return 0


def snapshot_read(rel: str, path: Path) -> str:
    snap = STATE_DIR / rel.replace("/", "__")
    if snap.exists():
        return snap.read_text(encoding="utf-8")
    return git_show(rel)


def snapshot_write_all() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for path, rel in TRACKED.items():
        if path.exists():
            (STATE_DIR / rel.replace("/", "__")).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def parse_vals_text(text: str) -> dict:
    if not text.strip():
        return {}
    try:
        return json.loads(text).get("values", {})
    except json.JSONDecodeError:
        return {}


def parse_claims_text(text: str) -> dict:
    if not text.strip():
        return {}
    try:
        return json.loads(text).get("claims", {})
    except json.JSONDecodeError:
        return {}


def hook_post() -> int:
    tool, path, _ti = hook_payload()
    if tool not in {"Edit", "Write", "MultiEdit"} or not any(same(path, p) for p in TRACKED):
        return 0
    notes: list[str] = []
    if same(path, NUMBERS_JSON):
        try:
            values = gen_numbers.load_numbers()
            NUMBERS_TEX.write_text(gen_numbers.render_tex(values), encoding="utf-8", newline="\n")
            notes.append("numbers.tex regenerated from numbers.json.")
        except (ValueError, json.JSONDecodeError) as exc:
            notes.append(f"numbers.json is invalid, numbers.tex NOT regenerated: {exc}")
    base_tex = snapshot_read(TRACKED[TEX], TEX)
    base_vals = parse_vals_text(snapshot_read(TRACKED[NUMBERS_JSON], NUMBERS_JSON))
    base_claims = parse_claims_text(snapshot_read(TRACKED[CLAIMS_JSON], CLAIMS_JSON))
    head_tex = TEX.read_text(encoding="utf-8")
    head_vals = parse_vals_text(NUMBERS_JSON.read_text(encoding="utf-8")) if NUMBERS_JSON.exists() else {}
    head_claims = load_claims()
    try:
        items = tripwire(base_tex, head_tex, base_vals, head_vals, base_claims, head_claims)
    except ValueError as exc:
        items = [f"- could not parse main.tex: {exc}"]
    errors, _warnings = check(head_tex)
    snapshot_write_all()
    if MIRROR_GEN.exists() and same(path, TEX):
        notes.append("margin_notes mirror is now stale: run `python tools/margin_notes/build_doc_from_tex.py --write` "
                     "before publishing it.")
    if not items and not errors:
        if notes:
            print("\n".join(notes), file=sys.stderr)
        return 0
    out = ["Paper consistency check after this edit:"]
    if errors:
        out.append("Errors:")
        out.extend("- " + e for e in errors[:15])
    if items:
        out.append("Connected statements to review:")
        out.extend(items[:20])
        if len(items) > 20:
            out.append(f"... and {len(items) - 20} more (run `python paper/consistency.py tripwire`).")
    out.extend(notes)
    print("\n".join(out), file=sys.stderr)
    return 2


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("report")
    s = sub.add_parser("sites")
    s.add_argument("name")
    t = sub.add_parser("tripwire")
    t.add_argument("--base", default="HEAD", help="git ref to compare against (default HEAD)")
    sub.add_parser("hook-pre")
    sub.add_parser("hook-post")
    args = ap.parse_args()

    if args.cmd == "hook-pre":
        return hook_pre()
    if args.cmd == "hook-post":
        return hook_post()

    if args.cmd == "check":
        errors, warnings = check()
        for w in warnings:
            print("WARNING:", w)
        for e in errors:
            print("ERROR:", e)
        if errors:
            return 1
        doc = Doc(TEX.read_text(encoding="utf-8"))
        print(f"consistency OK: {len(doc.value_sites())} \\val uses, {len(doc.claim_sites())} \\claim sites")
        return 0

    doc = Doc(TEX.read_text(encoding="utf-8"))
    if args.cmd == "report":
        claims = load_claims()
        by = {}
        for s_ in doc.claim_sites():
            by.setdefault(s_.name, []).append(s_)
        for cid in sorted(by):
            print(f"claim {cid}: {claims.get(cid, {}).get('statement', '(not in claims.json)')}")
            for s_ in by[cid]:
                print("   ", fmt_site(s_))
        vb = {}
        for s_ in doc.value_sites():
            vb.setdefault(s_.name, []).append(s_)
        multi = {k: v for k, v in vb.items() if len({x.section for x in v}) > 1}
        print(f"\n{len(multi)} values stated in more than one section:")
        for k in sorted(multi):
            print(f"  {k}: " + "; ".join(f"L{x.line} {x.section}" for x in multi[k]))
        return 0
    if args.cmd == "sites":
        hits = [x for x in doc.claim_sites() + doc.value_sites() if x.name == args.name]
        for x in hits:
            print(fmt_site(x))
        return 0 if hits else 1
    if args.cmd == "tripwire":
        items = tripwire(git_show(TRACKED[TEX], args.base), TEX.read_text(encoding="utf-8"),
                         parse_vals_text(git_show(TRACKED[NUMBERS_JSON], args.base)),
                         parse_vals_text(NUMBERS_JSON.read_text(encoding="utf-8")) if NUMBERS_JSON.exists() else {},
                         parse_claims_text(git_show(TRACKED[CLAIMS_JSON], args.base)), load_claims())
        if not items:
            print(f"tripwire: nothing connected changed relative to {args.base}")
            return 0
        print(f"tripwire relative to {args.base}:")
        print("\n".join(items))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
