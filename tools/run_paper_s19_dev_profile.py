"""One-shot runner for PAPER-S19: stages the development-only DOCX corpus,
runs tools/extract_docx_convention_profile.py against it, verifies
determinism (two independent runs must hash-match), verifies zero SHA-256
overlap between the development corpus and the primary 127-document gold
holdout (tier1+tier2+tier3), and writes a single manifest recording all of
this evidence.

Development corpus definition (chosen deliberately, not by convenience):
the 23 docx-corpus candidates that a prior, independent PII/content review
(`E:\\MeridianData\\ooxml-graph-paper\\raw\\docx-corpus\\review_results.json`)
excluded from gold -- so by construction none of them are in the paper's
127-document benchmark holdout, and this tool's own SHA-256 check below
re-verifies that claim directly against the actual gold files rather than
trusting the review file's bookkeeping alone. These documents are used here
ONLY for structural signals (styles/numbering/geometry/etc.) -- this script
never reads or emits any <w:t> body text, so the PII reasons the review
excluded them from the benchmark gold set do not carry over to this use.

Usage: pixi run python tools/run_paper_s19_dev_profile.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_docx_convention_profile as profiler  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper")
DOCX_CORPUS_DIR = DATA_ROOT / "raw" / "docx-corpus"
GOLD_DIR = DATA_ROOT / "gold"
STAGING_DIR = DATA_ROOT / "runs" / "profile-inference" / "dev-corpus-docxcorpus-excluded"
RUN_A_DIR = DATA_ROOT / "runs" / "profile-inference" / "run-a"
RUN_B_DIR = DATA_ROOT / "runs" / "profile-inference" / "run-b"
MANIFEST_OUT = DATA_ROOT / "manifests" / "profile-inference-dev-v1.json"

DOMAIN_LABEL = "docx-corpus-excluded-dev"
DOMAIN_THRESHOLD = 0.6


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def stage_dev_corpus() -> list[Path]:
    review = json.loads((DOCX_CORPUS_DIR / "review_results.json").read_text(encoding="utf-8"))
    excluded_ids = sorted(x["id"] for x in review if x.get("verdict") != "promote")
    files_dir = DOCX_CORPUS_DIR / "files"
    staged = []
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    for doc_id in excluded_ids:
        matches = [f for f in files_dir.glob(f"{doc_id}*.docx")]
        if not matches:
            raise FileNotFoundError(f"excluded id {doc_id} has no file in {files_dir}")
        src = matches[0]
        dst = STAGING_DIR / src.name
        if not dst.exists() or _sha256_file(dst) != _sha256_file(src):
            shutil.copy2(src, dst)
        staged.append(dst)
    return staged


def gold_holdout_hashes() -> dict[str, str]:
    """doc_id -> sha256 for every document in the primary 127-doc holdout."""
    out = {}
    for tier_dir in ("tier1", "tier2", "tier3"):
        d = GOLD_DIR / tier_dir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.docx")):
            out[f.stem] = _sha256_file(f)
    return out


def run_twice_and_check_determinism(staged_files: list[Path]) -> dict:
    if RUN_A_DIR.exists():
        shutil.rmtree(RUN_A_DIR)
    if RUN_B_DIR.exists():
        shutil.rmtree(RUN_B_DIR)
    RUN_A_DIR.mkdir(parents=True)
    RUN_B_DIR.mkdir(parents=True)

    profiles_a = [profiler.extract_document_profile(f) for f in staged_files]
    profiles_b = [profiler.extract_document_profile(f) for f in staged_files]
    for pa, pb in zip(profiles_a, profiles_b):
        (RUN_A_DIR / f"{pa['doc_id']}.profile.json").write_text(
            json.dumps(pa, indent=2, sort_keys=True), encoding="utf-8")
        (RUN_B_DIR / f"{pb['doc_id']}.profile.json").write_text(
            json.dumps(pb, indent=2, sort_keys=True), encoding="utf-8")

    per_doc_hash_matches = {
        pa["doc_id"]: (pa["profile_hash"] == pb["profile_hash"])
        for pa, pb in zip(profiles_a, profiles_b)
    }
    agg_a = profiler.aggregate_domain_profile(profiles_a, DOMAIN_LABEL, DOMAIN_THRESHOLD)
    agg_b = profiler.aggregate_domain_profile(profiles_b, DOMAIN_LABEL, DOMAIN_THRESHOLD)

    return {
        "profiles": profiles_a,
        "per_doc_determinism_ok": per_doc_hash_matches,
        "all_per_doc_deterministic": all(per_doc_hash_matches.values()),
        "aggregate_a": agg_a,
        "aggregate_hash_deterministic": agg_a["profile_hash"] == agg_b["profile_hash"],
    }


def main() -> int:
    staged = stage_dev_corpus()
    print(f"staged {len(staged)} development-only documents at {STAGING_DIR}")

    holdout_hashes = gold_holdout_hashes()
    print(f"loaded {len(holdout_hashes)} gold-holdout source hashes (tier1+tier2+tier3)")

    dev_hashes = {f.name: _sha256_file(f) for f in staged}
    overlap = sorted(set(dev_hashes.values()) & set(holdout_hashes.values()))

    result = run_twice_and_check_determinism(staged)

    manifest = {
        "schema_version": profiler.SCHEMA_VERSION,
        "item": "PAPER-S19",
        "extractor_self_hash": profiler._extractor_self_hash(),
        "development_corpus": {
            "source": "E:/MeridianData/ooxml-graph-paper/raw/docx-corpus (review_results.json verdict != 'promote')",
            "count": len(staged),
            "staged_dir": str(STAGING_DIR),
            "doc_sha256": dev_hashes,
        },
        "holdout_non_contamination_check": {
            "gold_holdout_doc_count": len(holdout_hashes),
            "gold_holdout_dirs": [str(GOLD_DIR / t) for t in ("tier1", "tier2", "tier3")],
            "sha256_overlap_with_dev_corpus": overlap,
            "contamination_free": len(overlap) == 0,
        },
        "determinism_check": {
            "per_doc_hash_match": result["per_doc_determinism_ok"],
            "all_per_doc_deterministic": result["all_per_doc_deterministic"],
            "aggregate_hash_deterministic": result["aggregate_hash_deterministic"],
            "run_a_dir": str(RUN_A_DIR),
            "run_b_dir": str(RUN_B_DIR),
        },
        "per_document_profiles_summary": [
            {
                "doc_id": p["doc_id"],
                "source_sha256": p["source_sha256"],
                "profile_hash": p["profile_hash"],
                "resolution": p["resolution"]["level"],
                "categories_present": p["categories_present"],
            }
            for p in result["profiles"]
        ],
        "aggregate_domain_profile": result["aggregate_a"],
    }
    MANIFEST_OUT.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote manifest: {MANIFEST_OUT}")
    print(f"contamination_free={manifest['holdout_non_contamination_check']['contamination_free']} "
          f"all_per_doc_deterministic={manifest['determinism_check']['all_per_doc_deterministic']} "
          f"aggregate_hash_deterministic={manifest['determinism_check']['aggregate_hash_deterministic']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
