"""Which docx-corpus pool documents has this project already touched?

Three steps, run from the repo root (stdlib only):

    python tools/rerun_pool_exclusion.py index  [--data-root D]
    python tools/rerun_pool_exclusion.py scan   --target data [--data-root D]
    python tools/rerun_pool_exclusion.py scan   --target repo
    python tools/rerun_pool_exclusion.py union  [--data-root D]

index: hashes every .docx under <data-root>/raw/docx-corpus/{batch-500-v1,
  batch-2-v1, batch-3-v1, files} (the docx-corpus id is the file name, not
  the file hash) -> manifests/docx_corpus_pool_index.json.

scan: finds every pool document referenced anywhere -- by docx-corpus id, by
  file sha256, or by any >=12-hex-char prefix of either (doc labels such as
  s7v2_sr_<16hex> and S6 candidate ids use 16-hex prefixes) -- in any
  text-like file or any file/dir NAME under the scanned roots. --target data
  scans <data-root> minus the raw DocBank/ReadingBank/model-cache trees and
  the pool .docx directories; --target repo scans this repo's working tree
  minus manifests/ (which lists every pool document by construction).

union: a document is touched if any scanned file references it, except the
  seven pool-wide acquisition/screening listings that enumerate whole batches
  (listing is not use). Writes manifests/touched_union.json, whose
  fresh_indices are indices into the pool index (batches 500/2/3 only; all of
  files/ is the gold/paper15/paper30/s12 corpus and is excluded anyway).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rerun_selection_common import (  # noqa: E402
    DEFAULT_DATA_ROOT,
    MANIFESTS_DIR,
    PAPER_ROOT,
    POOL_SUBDIRS,
    file_sha256,
    read_json,
    write_json,
)

POOL_INDEX = MANIFESTS_DIR / "docx_corpus_pool_index.json"
HITS_OUT = {"data": MANIFESTS_DIR / "exclusion_hits_data_root.json", "repo": MANIFESTS_DIR / "exclusion_hits_repo.json"}
TOUCHED_UNION = MANIFESTS_DIR / "touched_union.json"

# Relative to <data-root>: never scanned for references.
DATA_SKIP_DIRS = (
    r"raw\DocBank-repo",
    r"raw\DocBank-repo-incomplete-20260825",
    r"raw\ReadingBank",
    r"model-cache",
    r"raw\docx-corpus\batch-500-v1",
    r"raw\docx-corpus\batch-2-v1",
    r"raw\docx-corpus\batch-3-v1",
    r"raw\docx-corpus\files",
)
# Relative to the repo root: this pipeline's own outputs.
REPO_SKIP_DIRS = ("manifests",)
SKIP_DIR_NAMES = (".git", "node_modules", ".pixi", "__pycache__")
TEXT_EXT = {".json", ".jsonl", ".md", ".txt", ".csv", ".tsv", ".py", ".log", ".yaml", ".yml", ".html", ".tex", ".xml", ".ndjson", ".out", ".err"}
MAX_TEXT_BYTES = 400 * 1024 * 1024
HEX = re.compile(rb"(?<![0-9a-fA-F])[0-9a-fA-F]{12,64}(?![0-9a-fA-F])")

# Relative to <data-root>: acquisition/screening listings that enumerate whole batches.
POOL_WIDE_LISTINGS = (
    r"raw\docx-corpus\filtered_candidates.json",
    r"manifests\docxcorpus-batch-2-v1.json",
    r"manifests\docxcorpus-batch-3-v1.json",
    r"manifests\docxcorpus-batch-500-v1.json",
    r"manifests\s6-batch-2-omml-screen-v1.json",
    r"manifests\s6-batch-3-omml-screen-v1.json",
    r"manifests\s6-batch-500-omml-screen-v1.json",
)


def cmd_index(args: argparse.Namespace) -> int:
    root = os.path.join(args.data_root, "raw", "docx-corpus")
    out = []
    for sub in POOL_SUBDIRS:
        d = os.path.join(root, sub)
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith(".docx"):
                continue
            p = os.path.join(d, name)
            out.append({"id": name[:-5].lower(), "batch": sub, "path": p, "sha256": file_sha256(p), "size": os.path.getsize(p)})
    write_json(args.out, out, indent=1)
    print(len(out), Counter(o["batch"] for o in out))
    ids = Counter(o["id"] for o in out)
    print("dup ids across batches:", sum(1 for v in ids.values() if v > 1))
    shas = Counter(o["sha256"] for o in out)
    print("dup sha:", sum(1 for v in shas.values() if v > 1))
    return 0


class _Matcher:
    """Maps a hex token to the pool documents whose id or sha256 starts with it."""

    _FIXED = (12, 16, 24, 32, 40, 64)

    def __init__(self, pool: list[dict]):
        self.pool = pool
        self.prefix_to_docs: dict[str, set[int]] = defaultdict(set)
        for i, d in enumerate(pool):
            for key in (d["id"], d["sha256"]):
                for n in self._FIXED:
                    self.prefix_to_docs[key[:n]].add(i)
        self._by_len: dict[int, dict[str, set[int]]] = {}

    def _prefix_by_len(self, tok: str) -> set[int] | None:
        n = len(tok)
        if n not in self._by_len:
            m: dict[str, set[int]] = defaultdict(set)
            for i, d in enumerate(self.pool):
                m[d["id"][:n]].add(i)
                m[d["sha256"][:n]].add(i)
            self._by_len[n] = m
        return self._by_len[n].get(tok)

    def hits_in(self, blob: bytes) -> set[int]:
        found: set[int] = set()
        for m in HEX.finditer(blob):
            tok = m.group(0).decode().lower()
            docs = self.prefix_to_docs.get(tok)
            if docs is None and len(tok) not in self._FIXED:
                docs = self._prefix_by_len(tok)
            if docs:
                found |= docs
        return found


def cmd_scan(args: argparse.Namespace) -> int:
    pool = read_json(args.pool)
    if args.target == "data":
        roots = args.root or [args.data_root]
        skip = [os.path.join(args.data_root, p) for p in DATA_SKIP_DIRS]
    else:
        roots = args.root or [str(PAPER_ROOT)]
        skip = [os.path.join(str(PAPER_ROOT), p) for p in REPO_SKIP_DIRS]
    skip_dirs = {os.path.normcase(p) for p in skip + list(args.skip)}
    out_path = args.out or HITS_OUT[args.target]
    matcher = _Matcher(pool)

    per_file: dict[str, set[int]] = {}
    scanned = 0
    for root in roots:
        for dp, dns, fns in os.walk(root):
            if os.path.normcase(dp) in skip_dirs:
                dns[:] = []
                continue
            dns[:] = [d for d in dns if os.path.normcase(os.path.join(dp, d)) not in skip_dirs and d not in SKIP_DIR_NAMES]
            for name in dns + fns:
                h = matcher.hits_in(name.encode())
                if h:
                    per_file.setdefault("NAME:" + os.path.join(dp, name), set()).update(h)
            for fn in fns:
                p = os.path.join(dp, fn)
                if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
                    continue
                try:
                    if os.path.getsize(p) > MAX_TEXT_BYTES:
                        continue
                    with open(p, "rb") as f:
                        blob = f.read()
                except OSError:
                    continue
                scanned += 1
                h = matcher.hits_in(blob)
                if h:
                    per_file.setdefault(p, set()).update(h)

    out = {"roots": roots, "text_files_scanned": scanned,
           "per_file": {k: sorted(v) for k, v in sorted(per_file.items())}}
    write_json(out_path, out, indent=0)
    print("scanned", scanned, "files with hits", len(per_file), "->", out_path)
    for k, v in sorted(per_file.items(), key=lambda kv: -len(kv[1]))[:60]:
        print(len(v), k)
    return 0


def cmd_union(args: argparse.Namespace) -> int:
    pool = read_json(args.pool)
    pool_wide = {os.path.join(args.data_root, p) for p in POOL_WIDE_LISTINGS}
    touched: dict[int, list[str]] = {}
    for fn in args.hits:
        d = read_json(fn)
        for f, idxs in d["per_file"].items():
            if f in pool_wide:
                continue
            for i in idxs:
                touched.setdefault(i, []).append(f)
    fresh = [i for i, d in enumerate(pool) if i not in touched and d["batch"] != "files"]
    files_untouched = [i for i, d in enumerate(pool) if d["batch"] == "files" and i not in touched]
    print("pool", len(pool), "touched", len(touched), "fresh (batches 500/2/3, untouched)", len(fresh),
          "files/ untouched (excluded anyway)", len(files_untouched))
    print(Counter(pool[i]["batch"] for i in touched))
    write_json(args.out, {
        "pool_wide_listings_ignored": sorted(pool_wide),
        "touched": {pool[i]["id"]: {"sha256": pool[i]["sha256"], "batch": pool[i]["batch"],
                                    "referenced_in": sorted(set(v))[:50], "reference_count": len(set(v))}
                    for i, v in touched.items()},
        "fresh_indices": fresh,
    }, indent=1)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="hash every pool .docx")
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--out", type=Path, default=POOL_INDEX)
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("scan", help="find pool documents referenced in files under a root")
    p.add_argument("--target", choices=("data", "repo"), required=True)
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--root", action="append", default=None, help="override the scanned root(s)")
    p.add_argument("--skip", action="append", default=[], help="extra directory to skip (absolute)")
    p.add_argument("--pool", type=Path, default=POOL_INDEX)
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("union", help="union of scan hits -> touched set and fresh indices")
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--pool", type=Path, default=POOL_INDEX)
    p.add_argument("--hits", type=Path, nargs="+", default=[HITS_OUT["data"], HITS_OUT["repo"]],
                   help="scan outputs, in order (data root first)")
    p.add_argument("--out", type=Path, default=TOUCHED_UNION)
    p.set_defaults(func=cmd_union)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
