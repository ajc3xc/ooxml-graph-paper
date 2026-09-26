"""Word 12-gram overlap between .docx files (stdlib only), the granularity
PROVENANCE.md reports and the S25/S26 near-duplicate rule uses:

    overlap(A|B) = share of A's stride-4 word 12-grams that occur anywhere in B
                   (all positions of B).

Words are lower-cased \\w+ runs of word/document.xml's <w:t> text, joined per
paragraph. Outputs are ratios only, never text.

    python tools/docx_ngram_overlap.py refs  --items items.json --ref LABEL [--ref LABEL ...] --out out.json
        For every item: its word count, overlap with each reference, and with
        the union of all references ("of_self_in_any_used"). A reference label's
        --strip-prefix (default "USED_") is dropped from its key.
    python tools/docx_ngram_overlap.py pairs --items items.json --labels A B [C ...] --out out.json
        overlap(A|B) for every ordered pair of the given labels.

items.json = [{"label": ..., "path": ...}, ...]. Author-owned documents are
private: keep their items and outputs outside the repo unless the author
decides otherwise.
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rerun_selection_common import read_json, write_json  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
N = 12
STRIDE = 4


def words(path: str | Path) -> list[str]:
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    out: list[str] = []
    for para in root.iter(W + "p"):
        out += re.findall(r"\w+", "".join(t.text or "" for t in para.iter(W + "t")).lower())
    return out


def all_grams(ws: list[str]) -> set[tuple[str, ...]]:
    return {tuple(ws[j:j + N]) for j in range(len(ws) - N + 1)}


def sampled_grams(ws: list[str]) -> list[tuple[str, ...]]:
    return [tuple(ws[j:j + N]) for j in range(0, len(ws) - N + 1, STRIDE)]


def cmd_refs(args: argparse.Namespace) -> int:
    items = read_json(args.items)
    T = {i["label"]: words(i["path"]) for i in items}
    allg = {k: all_grams(v) for k, v in T.items()}
    samp = {k: sampled_grams(v) for k, v in T.items()}
    union: set[tuple[str, ...]] = set().union(*(allg[r] for r in args.ref))
    res = {}
    for k in T:
        s = samp[k]
        row: dict = {"words": len(T[k])}
        for r in args.ref:
            key = r[len(args.strip_prefix):] if args.strip_prefix and r.startswith(args.strip_prefix) else r
            row["of_self_in_" + key] = round(sum(1 for g in s if g in allg[r]) / len(s), 3) if s else None
        row["of_self_in_any_used"] = round(sum(1 for g in s if g in union) / len(s), 3) if s else None
        res[k] = row
        print(k, row)
    write_json(args.out, res, indent=1)
    return 0


def cmd_pairs(args: argparse.Namespace) -> int:
    paths = {i["label"]: i["path"] for i in read_json(args.items)}
    T = {k: words(paths[k]) for k in args.labels}
    allg = {k: all_grams(v) for k, v in T.items()}
    samp = {k: sampled_grams(v) for k, v in T.items()}
    out = {}
    for a in args.labels:
        for b in args.labels:
            if a != b:
                out[f"{a} | {b}"] = round(sum(1 for g in samp[a] if g in allg[b]) / max(1, len(samp[a])), 3)
                print(f"{out[f'{a} | {b}']:.3f}  share of {a} in {b}")
    write_json(args.out, out, indent=1)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("refs", help="overlap of every item with each reference and their union")
    p.add_argument("--items", type=Path, required=True)
    p.add_argument("--ref", action="append", required=True)
    p.add_argument("--strip-prefix", default="USED_")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=cmd_refs)

    p = sub.add_parser("pairs", help="overlap for every ordered pair of labels")
    p.add_argument("--items", type=Path, required=True)
    p.add_argument("--labels", nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=cmd_pairs)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
