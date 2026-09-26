"""Schema-compatibility tests for tools/build_locked_pod_manifests.py's two outputs, run
against the REAL consumer functions (run_respec_cascade_sweep.load_document_manifest,
run_paper_s7_benchmark.check_corpus_slice) -- not by eyeballing the generated JSON.

Two things are checked per output file:
1. Against the actual generated pod-path file (manifests/paper-s25-respec-documents-v1.json /
   manifests/paper-s26-k4sr-replication-manifest-v1.json), the real function parses it without
   raising, and every doc_label/sha256 the locked selection file recorded comes back out.
   docx_path in these files is a POD path (/workspace/...), which is not absolute on Windows
   (no drive letter -- Path.is_absolute() is False here, though it is True on the Linux pod
   these files are actually consumed on), so the resolved paths on THIS machine do not point at
   real files; that is expected and is exactly why check (2) exists.
2. Against a LOCAL echo of the same manifest (docx_path replaced with each document's real,
   already hash-verified local path), the real function runs its full logic -- sha256
   verification (load_document_manifest + verify_documents) and, for S26, the actual
   resolve_section_reorder_plan family probe via check_corpus_slice -- and reports success,
   using whatever meridian_docs build is installed in THIS pixi environment (not necessarily
   the pin; the pin-time eligibility recompute itself is recorded separately in
   manifests/s25-respec-eligibility-at-pin-v1.json and manifests/s26-k4-eligibility-at-pin-v1.json
   and gated by build_locked_pod_manifests.build_s25_manifest/build_s26_manifest).

Skips (does not fail) if D:\\MeridianData is not mounted on the machine running this test.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_locked_pod_manifests as builder  # noqa: E402
import run_paper_s7_benchmark as s7  # noqa: E402
import run_respec_cascade_sweep as sweep  # noqa: E402
from rerun_selection_common import read_json  # noqa: E402

DATA_ROOT_MOUNTED = Path(r"D:\MeridianData").is_dir()
skip_no_data_root = pytest.mark.skipif(not DATA_ROOT_MOUNTED, reason="D:\\MeridianData not mounted on this machine")


def _locked_sha256_labels(locked_path: Path) -> dict[str, str]:
    return {d["doc_label"]: d["sha256"].lower() for d in read_json(locked_path)["documents"]}


# --- (1) schema shape of the real generated pod-path files -----------------------------------

def test_s25_pod_manifest_parses_with_load_document_manifest() -> None:
    assert builder.S25_OUT.is_file(), "run tools/build_locked_pod_manifests.py first"
    documents = sweep.load_document_manifest(builder.S25_OUT)
    expected = _locked_sha256_labels(builder.S25_LOCKED)
    assert set(documents) == set(expected)
    for label, info in documents.items():
        assert info["sha256"].lower() == expected[label]
        assert isinstance(info["docx_path"], Path)


def test_s26_pod_manifest_parses_with_check_corpus_slice(tmp_path: Path) -> None:
    assert builder.S26_OUT.is_file(), "run tools/build_locked_pod_manifests.py first"
    report = s7.check_corpus_slice(builder.S26_OUT, builder.S26_SPLIT, ("section_reorder",), tmp_path / "run")
    expected = _locked_sha256_labels(builder.S26_LOCKED)
    assert report["document_count"] == len(expected) == 60
    assert {row["doc_label"] for row in report["documents"]} == set(expected)
    # Pod paths are not real files on this (Windows, non-pod) machine -- that is expected and
    # is exactly why the local-echo end-to-end check below exists.


def test_s26_pod_manifest_has_one_split_covering_all_documents() -> None:
    manifest = read_json(builder.S26_OUT)
    assert {d["s7_split"] for d in manifest["documents"]} == {"primary_holdout"}


# --- (2) end-to-end against each document's real local file --------------------------------

@skip_no_data_root
def test_s25_local_echo_verifies_against_real_files(tmp_path: Path) -> None:
    manifest = builder.build_s25_manifest(verify_local=True)
    respec_index = builder._sha_index(read_json(builder.RESPEC_PUBLIC_CANDIDATES)["documents"], "local_path")
    locked_docs = {d["doc_label"]: d for d in read_json(builder.S25_LOCKED)["documents"]}
    local_manifest = {
        "documents": [
            {"doc_label": d["doc_label"], "sha256": d["sha256"],
             "docx_path": str(builder.resolve_local_docx_path(locked_docs[d["doc_label"]], respec_index, {}, kind="S25"))}
            for d in manifest["documents"]
        ]
    }
    local_path = tmp_path / "local-echo-s25.json"
    local_path.write_text(json.dumps(local_manifest), encoding="utf-8")

    documents = sweep.load_document_manifest(local_path)
    assert len(documents) == 8
    hashes = sweep.verify_documents(documents)  # raises ScheduleMismatchError on any mismatch
    assert len(hashes) == 8


@skip_no_data_root
def test_s26_local_echo_is_eligible_via_check_corpus_slice(tmp_path: Path) -> None:
    manifest = builder.build_s26_manifest(verify_local=True)
    k4sr_index = builder._sha_index(read_json(builder.K4SR_CANDIDATES)["documents"], "local_path")
    locked_docs = {d["doc_label"]: d for d in read_json(builder.S26_LOCKED)["documents"]}
    local_manifest = {
        "documents": [
            {"doc_label": d["doc_label"], "sha256": d["sha256"], "s7_split": d["s7_split"],
             "docx_path": str(builder.resolve_local_docx_path(locked_docs[d["doc_label"]], {}, k4sr_index, kind="S26"))}
            for d in manifest["documents"]
        ]
    }
    local_path = tmp_path / "local-echo-s26.json"
    local_path.write_text(json.dumps(local_manifest), encoding="utf-8")

    report = s7.check_corpus_slice(local_path, "primary_holdout", ("section_reorder",), tmp_path / "run")
    assert report["document_count"] == 60
    bad = [row for row in report["documents"] if not row.get("sha256_ok") or not row["families"]["section_reorder"]["applicable"]]
    assert bad == []
    assert report["ok"] is True


# --- build_locked_pod_manifests's own eligibility gate --------------------------------------

def test_eligibility_gate_refuses_when_a_document_is_missing_from_the_record(tmp_path: Path, monkeypatch) -> None:
    locked_docs = read_json(builder.S25_LOCKED)["documents"]
    bad_record = {
        "meridian_docs_pin_commit": "deadbeef",
        "documents": [{"sha256": locked_docs[0]["sha256"], "eligible_six_family": True}],  # missing the other 7
    }
    bad_path = tmp_path / "bad-eligibility.json"
    bad_path.write_text(json.dumps(bad_record), encoding="utf-8")
    with pytest.raises(builder.IneligibleAtPinError, match="does not cover exactly the locked document set"):
        builder._check_eligibility_gate(locked_docs, bad_path, "eligible_six_family", "S25")


def test_eligibility_gate_refuses_when_a_document_is_ineligible(tmp_path: Path) -> None:
    locked_docs = read_json(builder.S25_LOCKED)["documents"]
    record = {
        "meridian_docs_pin_commit": "deadbeef",
        "documents": [{"sha256": d["sha256"], "eligible_six_family": (i != 0)} for i, d in enumerate(locked_docs)],
    }
    bad_path = tmp_path / "one-ineligible.json"
    bad_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(builder.IneligibleAtPinError, match=locked_docs[0]["doc_label"]):
        builder._check_eligibility_gate(locked_docs, bad_path, "eligible_six_family", "S25")


def test_recorded_eligibility_at_pin_covers_all_68_and_all_eligible() -> None:
    s25 = read_json(builder.S25_ELIGIBILITY_AT_PIN)
    s26 = read_json(builder.S26_ELIGIBILITY_AT_PIN)
    assert s25["document_count"] == 8
    assert s26["document_count"] == 60
    assert s25["all_eligible"] is True
    assert s26["all_eligible"] is True
    assert s25["meridian_docs_pin_commit"] == s26["meridian_docs_pin_commit"] == "89c93fac6a9ee7a03d98baab34ba7043de983018"
