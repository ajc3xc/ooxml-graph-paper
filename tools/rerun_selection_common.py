"""Shared defaults and I/O for the S25/S26 re-run document-selection tools.

The selection pipeline (see manifests/README.md) is:

    rerun_pool_exclusion.py index   -> manifests/docx_corpus_pool_index.json
    rerun_pool_exclusion.py scan    -> manifests/exclusion_hits_{data_root,repo}.json
    rerun_pool_exclusion.py union   -> manifests/touched_union.json
    scan_fresh_docx_pool.py         -> manifests/fresh_pool_structure_pii_scan.json
    respec_eligibility.py fresh     -> manifests/fresh_pool_respec_eligibility.json
    respec_eligibility.py organic   -> manifests/organic_respec_eligibility.json
    build_rerun_candidates.py k4sr  -> manifests/k4sr_candidates.json
    build_rerun_candidates.py respec-> manifests/respec_public_candidates.json
    select_rerun_documents.py ...   -> seeded review orders

Every manifest holds identifiers, hashes, paths, counts and resolver verdicts
only -- never document text. JSON is written with CRLF line endings on every
OS (the first run was on Windows), so a re-run is byte-comparable anywhere.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PAPER_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS_DIR = PAPER_ROOT / "manifests"
# Machine-specific locations; every tool takes them as overridable arguments.
DEFAULT_DATA_ROOT = r"D:\MeridianData\ooxml-graph-paper"
DEFAULT_MERIDIAN_REPO = r"C:\Users\13144\Documents\Meridian\repository"

POOL_SUBDIRS = ("batch-500-v1", "batch-2-v1", "batch-3-v1", "files")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any, *, indent: int, ensure_ascii: bool = True) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=ensure_ascii)


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rank_key(seed: int, doc_sha256: str) -> str:
    """Seeded, version-independent order key (no PRNG): ascending
    sha256(f"{seed}:{doc_sha256}") hex digest."""
    return hashlib.sha256(f"{seed}:{doc_sha256}".encode()).hexdigest()
