"""Build the two pod-ready document manifests the locked S25/S26 harness commands load, from
the already-reviewed, already-locked document-selection files. Do not hand-edit the outputs --
re-run this script instead; it is deterministic and byte-reproducible against unchanged inputs.

    manifests/s25-respec-documents-locked.json  (8 docs)  -> manifests/paper-s25-respec-documents-v1.json
    manifests/s26-k4-documents-locked.json     (60 docs)  -> manifests/paper-s26-k4sr-replication-manifest-v1.json

Schema (confirmed by reading the real consumer functions, not assumed -- see
tests/test_build_locked_pod_manifests.py, which imports and calls both against the files this
script writes):

- S25: ``run_respec_cascade_sweep.load_document_manifest`` reads
  ``{"documents": [{"doc_label": str, "docx_path": str, "sha256": str}, ...]}``.
- S26: ``run_paper_s7_benchmark.check_corpus_slice`` reads
  ``{"documents": [{"doc_label": str, "docx_path": str, "sha256": str, "s7_split": str}, ...]}``,
  then filters to the rows whose ``s7_split`` equals the ``--split`` value the command line
  passes. Both locked S26 commands (docs/paper-s26-k4-section-reorder-confirmatory-protocol-v1.md
  section 10 and docs/runpod-rerun-runbook-draft.md) pass ``--split primary_holdout``, and
  section 1.2 item 6 already commits the pod-path form to ``s7_split: "primary_holdout"`` for
  every document. This script assigns that one split, verbatim, to all 60 documents: the
  protocol is explicit that "there is no validation slice, because the harness is not being
  debugged on this corpus" (single confirmatory run, not a train/val/holdout design) --
  "primary_holdout" is not invented here, it is the exact string both protocol documents already
  lock.

``docx_path`` in the two OUTPUT files is the POD path
(``/workspace/ooxml-graph-paper/corpus/<doc_label>.docx``), never this machine's local path --
that is the "pod-path form" both protocols describe, and it is what the runbook's provisioning
step (section 3.3) populates by copying each locked document's real file there before any locked
command runs. This script also resolves and SHA-256-verifies each document's REAL local file
(``resolve_local_docx_path`` / ``LocalResolutionError``) before trusting its hash into the pod
manifest -- that check exists purely to catch a stale/renamed/corrupted source file here, on this
machine, before the hash we hand to the pod is wrong.

Eligibility gate (closes the pin-time-recompute caveat, does not just re-flag it): before writing
anything, this script requires manifests/s25-respec-eligibility-at-pin-v1.json and
manifests/s26-k4-eligibility-at-pin-v1.json -- the recorded results of literally re-running the
harness's own resolvers (tools/respec_eligibility.analyze for S25's six-family anchor-sets,
tools/docx_anchor_prober.resolve_section_reorder_plan for S26) against an isolated venv built
from ``git archive 89c93fac6a9ee7a03d98baab34ba7043de983018 -- extensions/meridian-docs`` (the
locked pin), not the previously-used unpinned build. It checks those files' document sha256 sets
match the locked selection files exactly (so a later change to either locked file cannot silently
reuse a stale eligibility record) and that every document is eligible; if any document is NOT
eligible for what it was selected for at the pin, this script refuses to write either output file
and prints exactly which document, which family/rule, and why -- replacing a document is a human
decision, never one this script makes for itself. As recomputed 2026-09-26, all 68 documents
(8 S25 + 60 S26) are eligible at the pin (see those two files' own "note" field for why this was
a real recompute, not a copy-forward, even though the previously-used unpinned build turned out
to already contain the pin unchanged in the one file these resolvers read).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rerun_selection_common import MANIFESTS_DIR, file_sha256, read_json, write_json  # noqa: E402

S25_LOCKED = MANIFESTS_DIR / "s25-respec-documents-locked.json"
S26_LOCKED = MANIFESTS_DIR / "s26-k4-documents-locked.json"
RESPEC_PUBLIC_CANDIDATES = MANIFESTS_DIR / "respec_public_candidates.json"
K4SR_CANDIDATES = MANIFESTS_DIR / "k4sr_candidates.json"
S25_ELIGIBILITY_AT_PIN = MANIFESTS_DIR / "s25-respec-eligibility-at-pin-v1.json"
S26_ELIGIBILITY_AT_PIN = MANIFESTS_DIR / "s26-k4-eligibility-at-pin-v1.json"

S25_OUT = MANIFESTS_DIR / "paper-s25-respec-documents-v1.json"
S26_OUT = MANIFESTS_DIR / "paper-s26-k4sr-replication-manifest-v1.json"

POD_CORPUS_DIR = "/workspace/ooxml-graph-paper/corpus"
S26_SPLIT = "primary_holdout"  # locked verbatim by both protocol documents; see module docstring.


class LocalResolutionError(RuntimeError):
    """A locked document's real local file could not be found or its hash did not match."""


class IneligibleAtPinError(RuntimeError):
    """A document is not eligible, at the pin, for the benchmark it was selected for."""


def pod_docx_path(doc_label: str) -> str:
    return f"{POD_CORPUS_DIR}/{doc_label}.docx"


def _sha_index(docs: list[dict[str, Any]], path_key: str) -> dict[str, str]:
    idx: dict[str, str] = {}
    for d in docs:
        idx[d["sha256"].lower()] = d[path_key]
    return idx


def resolve_local_docx_path(doc: dict[str, Any], respec_index: dict[str, str], k4sr_index: dict[str, str],
                             *, kind: str) -> Path:
    """The REAL local file for a locked document row ({doc_label, source, sha256, ...}),
    hash-verified against its recorded sha256. `kind` is "S25" or "S26", for error messages
    only. Raises LocalResolutionError, never returns an unverified or missing path."""
    sha = doc["sha256"].lower()
    source = doc["source"]
    if source.startswith("author-owned"):
        # "author-owned, <absolute path>"
        path = Path(source.split(",", 1)[1].strip())
    else:
        index = respec_index if kind == "S25" else k4sr_index
        if sha not in index:
            raise LocalResolutionError(
                f"{kind} {doc['doc_label']}: sha256 {sha} not found in the candidate manifest "
                f"({'respec_public_candidates.json' if kind == 'S25' else 'k4sr_candidates.json'})")
        path = Path(index[sha])
    if not path.is_file():
        raise LocalResolutionError(f"{kind} {doc['doc_label']}: resolved local path does not exist: {path}")
    actual = file_sha256(path)
    if actual.lower() != sha:
        raise LocalResolutionError(
            f"{kind} {doc['doc_label']}: sha256 mismatch at {path} -- expected {sha}, got {actual}")
    return path


def _check_eligibility_gate(locked_docs: list[dict[str, Any]], eligibility_path: Path,
                             eligible_field: str, kind: str) -> None:
    """Refuses (IneligibleAtPinError) unless `eligibility_path` exists, covers exactly the
    sha256 set of `locked_docs`, and marks every one of them eligible."""
    if not eligibility_path.is_file():
        raise IneligibleAtPinError(
            f"{kind}: missing {eligibility_path.name} -- eligibility has not been recomputed at "
            "the pin. Run the pin recompute (see this module's docstring) before building the "
            "pod manifests; do not hand-edit or skip this file.")
    record = read_json(eligibility_path)
    by_sha = {r["sha256"].lower(): r for r in record["documents"]}
    locked_shas = {d["sha256"].lower() for d in locked_docs}
    if set(by_sha) != locked_shas:
        missing = locked_shas - set(by_sha)
        extra = set(by_sha) - locked_shas
        raise IneligibleAtPinError(
            f"{kind}: {eligibility_path.name} does not cover exactly the locked document set "
            f"(missing={sorted(missing)}, extra={sorted(extra)}). Re-recompute eligibility at "
            "the pin for the CURRENT locked selection before building the pod manifests.")
    problems = []
    for d in locked_docs:
        r = by_sha[d["sha256"].lower()]
        if not r[eligible_field]:
            problems.append(f"  - {d['doc_label']} (sha256 {d['sha256']}): {r}")
    if problems:
        raise IneligibleAtPinError(
            f"{kind}: {len(problems)} of {len(locked_docs)} locked documents are NOT eligible "
            f"at the pin ({record['meridian_docs_pin_commit']}), per {eligibility_path.name}. "
            "This is a human decision (replace the document), not something to improvise -- "
            "STOPPING without writing either pod manifest. Ineligible documents:\n" + "\n".join(problems))


def build_s25_manifest(*, verify_local: bool = True) -> dict[str, Any]:
    locked = read_json(S25_LOCKED)
    docs = locked["documents"]
    _check_eligibility_gate(docs, S25_ELIGIBILITY_AT_PIN, "eligible_six_family", "S25")
    if verify_local:
        respec_index = _sha_index(read_json(RESPEC_PUBLIC_CANDIDATES)["documents"], "local_path")
        for d in docs:
            resolve_local_docx_path(d, respec_index, {}, kind="S25")
    return {
        "schema": "paper-s25-respec-documents-v1",
        "derived_from": "manifests/s25-respec-documents-locked.json",
        "derived_from_sha256": file_sha256(S25_LOCKED),
        "meridian_docs_pin_commit": read_json(S25_ELIGIBILITY_AT_PIN)["meridian_docs_pin_commit"],
        "note": ("Pod-path form: docx_path is where the runbook's provisioning step (section 3.3) "
                 "copies the real file on the pod, not this machine's local path. Eligibility at "
                 "the pin: manifests/s25-respec-eligibility-at-pin-v1.json (all 8 eligible)."),
        "documents": [
            {"doc_label": d["doc_label"], "docx_path": pod_docx_path(d["doc_label"]), "sha256": d["sha256"]}
            for d in docs
        ],
    }


def build_s26_manifest(*, verify_local: bool = True) -> dict[str, Any]:
    locked = read_json(S26_LOCKED)
    docs = locked["documents"]
    _check_eligibility_gate(docs, S26_ELIGIBILITY_AT_PIN, "section_reorder_found_at_pin", "S26")
    if verify_local:
        k4sr_index = _sha_index(read_json(K4SR_CANDIDATES)["documents"], "local_path")
        for d in docs:
            resolve_local_docx_path(d, {}, k4sr_index, kind="S26")
    return {
        "schema": "paper-s26-k4sr-replication-manifest-v1",
        "derived_from": "manifests/s26-k4-documents-locked.json",
        "derived_from_sha256": file_sha256(S26_LOCKED),
        "meridian_docs_pin_commit": read_json(S26_ELIGIBILITY_AT_PIN)["meridian_docs_pin_commit"],
        "note": ("Pod-path form: docx_path is where the runbook's provisioning step (section 3.3) "
                 "copies the real file on the pod, not this machine's local path. s7_split is "
                 f'"{S26_SPLIT}" for every document -- one split covering all 60, locked verbatim '
                 "by docs/paper-s26-k4-section-reorder-confirmatory-protocol-v1.md section 1.2 "
                 "item 6 and the locked --split argument (section 10); there is no train/val/"
                 "holdout design because this is a single confirmatory run, not one being "
                 "debugged on this corpus. Eligibility at the pin: "
                 "manifests/s26-k4-eligibility-at-pin-v1.json (all 60 eligible)."),
        "documents": [
            {"doc_label": d["doc_label"], "docx_path": pod_docx_path(d["doc_label"]),
             "sha256": d["sha256"], "s7_split": S26_SPLIT}
            for d in docs
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-local-verify", action="store_true",
                     help="skip resolving/hash-verifying each document's real local file "
                          "(eligibility gate still applies). Only for environments without "
                          "D:\\MeridianData mounted; never use this to work around a real mismatch.")
    args = ap.parse_args(argv)
    verify_local = not args.skip_local_verify

    try:
        s25 = build_s25_manifest(verify_local=verify_local)
        s26 = build_s26_manifest(verify_local=verify_local)
    except (LocalResolutionError, IneligibleAtPinError) as exc:
        print(f"REFUSING to write pod manifests: {exc}", file=sys.stderr)
        return 1

    write_json(S25_OUT, s25, indent=1, ensure_ascii=False)
    write_json(S26_OUT, s26, indent=1, ensure_ascii=False)
    print(f"wrote {S25_OUT} ({len(s25['documents'])} documents)")
    print(f"wrote {S26_OUT} ({len(s26['documents'])} documents, s7_split={S26_SPLIT!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
