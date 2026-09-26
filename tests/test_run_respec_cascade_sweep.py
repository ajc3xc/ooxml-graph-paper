"""Unit tests for tools/run_respec_cascade_sweep.py's archive step and
six-family table anchors (2026-09-25). No sweep is run.

Run with: pixi run python -m pytest tests/test_run_respec_cascade_sweep.py -v
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import run_respec_cascade_sweep as sweep  # noqa: E402

_t0 = datetime.datetime(2026, 9, 25, tzinfo=datetime.timezone.utc)


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _fake_run(tmp_path: Path) -> tuple[Path, Path]:
    run_root, baseline_root = tmp_path / "runs", tmp_path / "baseline-runs"
    chain = run_root / "doc-abc-respec_cascade-control"
    final = _write(chain / "3.5-caption-inverse" / "doc.docx", b"final docx")
    _write(chain / "1.1-bibliography-forward" / "doc.docx", b"intermediate docx")
    _write(chain / "1.1-bibliography-forward" / "step-result.json", b"{}")
    _write(chain / "chain-result.json", json.dumps({"status": "completed", "final_output_docx": str(final)}).encode())
    _write(run_root / "sweep-manifest.json", b"{}")
    _write(run_root / "sweep.log", b"log line\n")
    b_chain = baseline_root / "citation" / "doc-citation-control-k1"
    b_fwd = _write(b_chain / "fwd" / "doc.docx", b"baseline forward")
    _write(b_chain / "chain-result.json", json.dumps({"status": "completed", "pairs": [
        {"forward": {"output_docx_path": str(b_fwd)}, "inverse": {"output_docx_path": str(b_chain / "missing.docx")}},
    ]}).encode())
    return run_root, baseline_root


def test_archive_packs_results_logs_and_named_docx_with_a_checkable_manifest(tmp_path: Path):
    run_root, baseline_root = _fake_run(tmp_path)
    out = tmp_path / "out" / "run.tar.gz"
    summary = sweep.archive_run({"run-root": run_root, "baseline-run-root": baseline_root}, out, all_docx=False)

    with tarfile.open(out, "r:gz") as tar:
        names = set(tar.getnames())
        manifest = json.loads(tar.extractfile(sweep._ARCHIVE_MANIFEST_NAME).read())
        for arcname, entry in manifest["files"].items():
            assert hashlib.sha256(tar.extractfile(arcname).read()).hexdigest() == entry["sha256"]
    assert {
        "run-root/doc-abc-respec_cascade-control/chain-result.json",
        "run-root/doc-abc-respec_cascade-control/3.5-caption-inverse/doc.docx",
        "run-root/doc-abc-respec_cascade-control/1.1-bibliography-forward/step-result.json",
        "run-root/sweep-manifest.json", "run-root/sweep.log",
        "baseline-run-root/citation/doc-citation-control-k1/chain-result.json",
        "baseline-run-root/citation/doc-citation-control-k1/fwd/doc.docx",
    } <= names
    assert "run-root/doc-abc-respec_cascade-control/1.1-bibliography-forward/doc.docx" not in names
    assert summary["named_docx_not_archived"] == [str((baseline_root / "citation/doc-citation-control-k1/missing.docx").resolve())]
    assert (out.parent / "run.tar.gz.sha256").read_text(encoding="utf-8").split()[0] == summary["sha256"]
    assert hashlib.sha256(out.read_bytes()).hexdigest() == summary["sha256"]
    assert json.loads((out.parent / "run.tar.gz.manifest.json").read_text(encoding="utf-8")) == manifest


def test_archive_all_docx_adds_intermediate_documents(tmp_path: Path):
    run_root, _ = _fake_run(tmp_path)
    out = tmp_path / "run.tar.gz"
    sweep.archive_run({"run-root": run_root}, out, all_docx=True)
    with tarfile.open(out, "r:gz") as tar:
        assert "run-root/doc-abc-respec_cascade-control/1.1-bibliography-forward/doc.docx" in tar.getnames()


def test_archive_default_is_all_docx(tmp_path: Path):
    """Review minor: every intermediate document is needed to re-grade a
    chain, so the archive keeps them all unless told otherwise."""
    run_root, _ = _fake_run(tmp_path)
    out = tmp_path / "run.tar.gz"
    summary = sweep.archive_run({"run-root": run_root}, out)
    with tarfile.open(out, "r:gz") as tar:
        assert "run-root/doc-abc-respec_cascade-control/1.1-bibliography-forward/doc.docx" in tar.getnames()
    assert json.loads((tmp_path / "run.tar.gz.manifest.json").read_text(encoding="utf-8"))["all_docx"] is True
    assert summary["file_count"] > 0


def test_archive_named_only_also_follows_step_result_json(tmp_path: Path):
    """In named-only mode a document named only by a step-result.json (a
    Checkpoint A/B or Phase-3 inverse output) is still archived."""
    run_root, _ = _fake_run(tmp_path)
    step_dir = run_root / "doc-abc-respec_cascade-control" / "2.3-section_reorder-redirect"
    checkpoint_b = _write(step_dir / "doc.docx", b"checkpoint B")
    _write(step_dir / "step-result.json", json.dumps({"output_docx_path": str(checkpoint_b)}).encode())
    out = tmp_path / "run.tar.gz"
    sweep.archive_run({"run-root": run_root}, out, all_docx=False)
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    assert "run-root/doc-abc-respec_cascade-control/2.3-section_reorder-redirect/doc.docx" in names
    assert "run-root/doc-abc-respec_cascade-control/1.1-bibliography-forward/doc.docx" not in names


def test_archive_cli_named_docx_only_flag(tmp_path: Path):
    run_root, _ = _fake_run(tmp_path)
    out = tmp_path / "cli.tar.gz"
    assert sweep.main(["--run-root", str(run_root), "--archive", str(out), "--archive-only",
                       "--archive-named-docx-only"]) == 0
    with tarfile.open(out, "r:gz") as tar:
        assert "run-root/doc-abc-respec_cascade-control/1.1-bibliography-forward/doc.docx" not in tar.getnames()


def test_archive_only_cli(tmp_path: Path):
    run_root, baseline_root = _fake_run(tmp_path)
    out = tmp_path / "cli.tar.gz"
    assert sweep.main(["--run-root", str(run_root), "--baseline-run-root", str(baseline_root),
                       "--archive", str(out), "--archive-only"]) == 0
    assert out.is_file()
    with pytest.raises(SystemExit):
        sweep.main(["--run-root", str(run_root), "--archive-only"])


def test_add_table_anchors_excludes_other_families_and_marks_missing(monkeypatch: pytest.MonkeyPatch):
    seen: dict = {}

    def fake_resolver(docx_path, max_anchors, exclude_para_ids):
        seen["exclude"] = set(exclude_para_ids)
        return [{"found": True, "anchor_para_id": "T0", "anchor_text_snippet": "t", "anchor_full_text": "t"}]

    monkeypatch.setattr(sweep, "resolve_multiple_body_anchors", fake_resolver)
    schedule = [
        {"anchor_set_index": i, "usable": True, "citation_anchor": {"found": True, "anchor_para_id": f"C{i}"},
         "equation_anchor": {"found": True, "anchor_para_id": f"E{i}"}, "caption_anchor": {"found": True, "anchor_para_id": f"K{i}"}}
        for i in range(2)
    ]
    out = sweep.add_table_anchors(Path("doc.docx"), schedule, max_anchor_sets=2)
    assert seen["exclude"] == {"C0", "E0", "K0", "C1", "E1", "K1"}
    assert out[0]["table_anchor"]["anchor_para_id"] == "T0" and out[0]["usable"] is True
    assert out[1]["usable"] is False and out[1]["reason"] == "missing_table_anchor"
    assert "table_anchor" not in schedule[0]  # input not modified


# ---------------------------------------------------------------------------
# 2026-09-25: document manifest, schedule hashing, --check-only, relaunch
# reading the stored schedule, arm interleaving, circuit breaker (review
# items 17, 19, 21 and P-R6). The resolver and the chain runner are faked.
# ---------------------------------------------------------------------------

def _anchor(prefix: str, i: int) -> dict:
    return {"found": True, "anchor_para_id": f"{prefix}{i}", "anchor_text_snippet": f"{prefix}{i}",
            "anchor_full_text": f"{prefix}{i} text"}


def _fake_schedule(docx_path, max_anchor_sets):
    return [
        {"anchor_set_index": i, "usable": True, "citation_anchor": _anchor("C", i), "equation_anchor": _anchor("E", i),
         "caption_anchor": _anchor("K", i), "section_reorder_plan": {"found": True, "section_id": f"S{i}"}}
        for i in range(max_anchor_sets)
    ]


@pytest.fixture
def docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: dict = {"resolve": 0, "chains": []}

    def fake_resolve(docx_path, max_anchor_sets):
        calls["resolve"] += 1
        return _fake_schedule(docx_path, max_anchor_sets)

    def fake_tables(docx_path, max_anchors, exclude_para_ids):
        return [_anchor("T", i) for i in range(max_anchors)]

    def fake_chain(doc_label, docx_path, arm, model, run_root, entry, **kwargs):
        calls["chains"].append((doc_label, arm, kwargs))
        return {"chain_id": f"{doc_label}-{arm}", "doc_label": doc_label, "arm": arm, "status": "completed"}

    monkeypatch.setattr(sweep, "resolve_respec_schedule", fake_resolve)
    monkeypatch.setattr(sweep, "resolve_multiple_body_anchors", fake_tables)
    monkeypatch.setattr(sweep, "run_respec_cascade_chain", fake_chain)
    rows = []
    for label in ("pub-a", "pub-b"):
        path = _write(tmp_path / "corpus" / f"{label}.docx", f"docx {label}".encode())
        rows.append({"doc_label": label, "docx_path": f"corpus/{label}.docx",
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = tmp_path / "documents.json"
    manifest.write_text(json.dumps({"documents": rows}), encoding="utf-8")
    return {"manifest": manifest, "calls": calls, "run_root": tmp_path / "run", "tmp": tmp_path}


def test_document_manifest_resolves_relative_paths_and_checks_hashes(docs):
    documents = sweep.load_document_manifest(docs["manifest"])
    assert list(documents) == ["pub-a", "pub-b"]
    assert sweep.verify_documents(documents)["pub-a"] == hashlib.sha256(b"docx pub-a").hexdigest()
    (docs["tmp"] / "corpus" / "pub-b.docx").write_bytes(b"tampered")
    with pytest.raises(sweep.ScheduleMismatchError, match="pub-b"):
        sweep.verify_documents(documents)
    assert sweep.main(["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]),
                       "--check-only"]) == 2
    assert docs["calls"]["resolve"] == 0 and not (docs["run_root"] / sweep.SCHEDULE_NAME).exists()


def test_check_only_hashes_the_schedule_and_runs_no_trial(docs, capsys):
    argv = ["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]), "--six-family",
            "--check-only"]
    assert sweep.main(argv) == 0
    report = json.loads(capsys.readouterr().out)
    schedule_bytes = (docs["run_root"] / sweep.SCHEDULE_NAME).read_bytes()
    sha = hashlib.sha256(schedule_bytes).hexdigest()
    assert report["anchor_schedules_sha256"] == sha and report["ok"] is True
    meta = json.loads((docs["run_root"] / sweep.SCHEDULE_META_NAME).read_text(encoding="utf-8"))
    assert meta["anchor_schedules_sha256"] == sha and meta["rotation"] == "six_family"
    assert set(meta["documents"]) == {"pub-a", "pub-b"}
    assert all(e["table_anchor"]["found"] for s in json.loads(schedule_bytes).values() for e in s)
    assert docs["calls"]["chains"] == []
    # the same check again reads, never re-resolves
    assert sweep.main(argv + ["--expected-schedule-sha256", sha]) == 0
    assert docs["calls"]["resolve"] == 2  # one resolve per document, first check only


def test_check_only_fails_when_a_document_lacks_usable_anchor_sets(docs, monkeypatch):
    def short_schedule(docx_path, max_anchor_sets):
        entries = _fake_schedule(docx_path, max_anchor_sets)
        entries[-1] = {**entries[-1], "usable": False, "reason": "no_caption_anchor"}
        return entries

    monkeypatch.setattr(sweep, "resolve_respec_schedule", short_schedule)
    assert sweep.main(["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]),
                       "--check-only"]) == 2


def test_expected_hash_mismatch_on_a_fresh_resolve_adopts_nothing(docs):
    code = sweep.main(["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]),
                       "--check-only", "--expected-schedule-sha256", "0" * 64])
    assert code == 2
    assert not (docs["run_root"] / sweep.SCHEDULE_NAME).exists()
    assert (docs["run_root"] / "anchor-schedules.rejected.json").is_file()


def test_relaunch_reads_the_stored_schedule_and_refuses_any_mismatch(docs, monkeypatch):
    documents = sweep.load_document_manifest(docs["manifest"])
    sweep.check_primary_sweep(docs["run_root"], documents=documents)

    def must_not_resolve(*_a, **_k):
        raise AssertionError("a relaunch must never re-resolve the schedule")

    monkeypatch.setattr(sweep, "resolve_respec_schedule", must_not_resolve)
    manifest = sweep.run_primary_sweep(docs["run_root"], "haiku", documents=documents, max_workers=1)
    assert manifest["chain_count"] == 16
    # rotation change
    with pytest.raises(sweep.ScheduleMismatchError, match="rotation"):
        sweep.run_primary_sweep(docs["run_root"], "haiku", documents=documents, six_family=True)
    # tampered schedule file
    path = docs["run_root"] / sweep.SCHEDULE_NAME
    path.write_bytes(path.read_bytes().replace(b'"C0"', b'"C9"'))
    with pytest.raises(sweep.ScheduleMismatchError, match="recorded"):
        sweep.run_primary_sweep(docs["run_root"], "haiku", documents=documents)
    assert sweep.main(["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"])]) == 2


def test_legacy_schedule_without_meta_is_adopted_only_with_the_expected_hash(docs):
    documents = sweep.load_document_manifest(docs["manifest"])
    docs["run_root"].mkdir(parents=True)
    legacy = {label: _fake_schedule(None, 4) for label in documents}
    data = sweep._schedule_bytes(legacy)
    (docs["run_root"] / sweep.SCHEDULE_NAME).write_bytes(data)
    with pytest.raises(sweep.ScheduleMismatchError, match="meta"):
        sweep.check_primary_sweep(docs["run_root"], documents=documents)
    report = sweep.check_primary_sweep(docs["run_root"], documents=documents,
                                       expected_schedule_sha256=hashlib.sha256(data).hexdigest())
    assert report["ok"] is True and docs["calls"]["resolve"] == 0
    assert json.loads((docs["run_root"] / sweep.SCHEDULE_META_NAME).read_text())["adopted_existing_schedule"] is True


def test_primary_sweep_interleaves_arms_and_stops_on_the_breaker(docs, monkeypatch):
    """A HARD global kind (api_authentication, not usage_limit/api_rate_limit)
    still trips the breaker permanently and stops the sweep -- unchanged by
    the 2026-09-25 rate-limit handling addition (tests/test_usage_cap.py and
    test_primary_sweep_auto_retries_and_resumes_after_a_usage_cap below cover
    the NEW usage_limit/api_rate_limit auto-retry behavior)."""
    documents = sweep.load_document_manifest(docs["manifest"])

    def tripping_chain(doc_label, docx_path, arm, model, run_root, entry, **kwargs):
        docs["calls"]["chains"].append((doc_label, arm))
        breaker = kwargs["circuit_breaker"]
        if breaker.is_open:
            raise sweep.CircuitOpenError("open")
        breaker.trip({"kinds": ["api_authentication"], "scope": "global"}, f"{doc_label}/{arm}")
        return {"chain_id": f"{doc_label}-{arm}", "doc_label": doc_label, "arm": arm, "status": "infra_blocked"}

    monkeypatch.setattr(sweep, "run_respec_cascade_chain", tripping_chain)
    manifest = sweep.run_primary_sweep(docs["run_root"], "haiku", documents=documents, max_workers=1, arm_order_seed=3)
    order = manifest["submission_order"]
    assert [row[0] for row in order[:2]] == ["pub-a__anchor0", "pub-a__anchor0"]
    assert all({order[i][1], order[i + 1][1]} == {"control", "treatment"} for i in range(0, len(order), 2))
    assert manifest["circuit_breaker"]["open"] is True
    assert len(manifest["usage_cap_rounds"]) == 1 and manifest["usage_cap_rounds"][0]["usage_cap_round"] is False
    statuses = [c["status"] for c in manifest["chains_summary"]]
    assert statuses.count("infra_blocked") == 1 and statuses.count("aborted_circuit_open") == 15
    assert manifest["anchor_schedules_sha256"] == json.loads(
        (docs["run_root"] / sweep.SCHEDULE_META_NAME).read_text())["anchor_schedules_sha256"]
    assert sweep.main(["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]),
                       "--max-workers", "1"]) == 3


def test_primary_sweep_auto_retries_and_resumes_after_a_usage_cap(docs, monkeypatch):
    """Rate-limit handling: a usage_limit/api_rate_limit trip pauses and
    auto-resumes WITHIN this one call -- no relaunch of run_primary_sweep is
    needed, unlike the hard-kind case above. Uses a fake, injected
    UsagePauseController (no real sleep -- task item 5)."""
    documents = sweep.load_document_manifest(docs["manifest"])
    tripped_once = {"done": False}

    def flaky_chain(doc_label, docx_path, arm, model, run_root, entry, **kwargs):
        docs["calls"]["chains"].append((doc_label, arm))
        breaker = kwargs["circuit_breaker"]
        pc = kwargs["pause_controller"]
        if breaker.is_open:
            # Every OTHER chain in the same round (fresh breaker, already
            # tripped by the first one below) aborts, exactly like a real
            # chain's own _check_circuit call.
            raise sweep.CircuitOpenError("open")
        if not tripped_once["done"]:
            tripped_once["done"] = True
            signature = {"kinds": ["usage_limit"], "scope": "global", "evidence": ["api_error_status 429"]}
            breaker.trip(signature, f"{doc_label}/{arm}")
            # A real chain reaches this via claude_pair_runner.infra_signature_of
            # (called from inside run_respec_cascade_chain's own _run_step);
            # simulate that here since run_respec_cascade_chain is stubbed out.
            if pc is not None:
                pc.note_trial({"claude_json_result": {"result": "You've hit your usage limit."}}, signature, f"{doc_label}/{arm}")
            return {"chain_id": f"{doc_label}-{arm}", "doc_label": doc_label, "arm": arm, "status": "infra_blocked",
                    "infra_signature": signature}
        return {"chain_id": f"{doc_label}-{arm}", "doc_label": doc_label, "arm": arm, "status": "completed"}

    monkeypatch.setattr(sweep, "run_respec_cascade_chain", flaky_chain)
    sleeps: list[float] = []
    pause_controller = sweep.UsagePauseController(sleep=sleeps.append, now_fn=lambda: _t0)
    manifest = sweep.run_primary_sweep(
        docs["run_root"], "haiku", documents=documents, max_workers=1, arm_order_seed=3,
        pause_controller=pause_controller,
    )
    assert len(manifest["usage_cap_rounds"]) == 2
    assert manifest["usage_cap_rounds"][0]["usage_cap_round"] is True
    assert manifest["usage_cap_rounds"][0]["retried"] == 16  # 1 infra_blocked + 15 aborted_circuit_open
    assert manifest["usage_cap_rounds"][1]["usage_cap_round"] is False
    assert manifest["circuit_breaker"]["open"] is False
    statuses = [c["status"] for c in manifest["chains_summary"]]
    assert statuses.count("completed") == 16 and "infra_blocked" not in statuses and "aborted_circuit_open" not in statuses
    assert sleeps  # the loop actually waited (via the injected sleep, not a real one)
    assert pause_controller.state()["resume_count"] == 1
    assert manifest["usage_cap_status"]["pause_episodes"] == 0  # mark_success reset it after the clean round


# ---------------------------------------------------------------------------
# --provenance-json (wf4_report.txt section 1.2, gap 2).
# ---------------------------------------------------------------------------

_PROVENANCE_KEYS = {
    "schema", "argv", "command_line", "repo_git_commit", "meridian_docs", "model",
    "documents_manifest_path", "documents_manifest_sha256", "schedule_path", "schedule_sha256",
    "hostname", "python_version", "start_time_utc", "end_time_utc", "exit_status",
}


def test_check_only_never_writes_provenance(docs):
    prov = docs["run_root"] / "provenance.json"
    assert sweep.main(["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]),
                       "--check-only", "--provenance-json", str(prov)]) == 0
    assert not prov.exists()


def test_real_run_writes_provenance_before_dispatch_and_updates_it_at_the_end(docs, monkeypatch):
    """The record must exist (with the schedule's own sha256 already filled
    in) before any chain is dispatched -- write_provenance_start is called
    right after prepare_schedules, inside run_primary_sweep, before the
    dispatch loop -- and the SAME file is updated in place with the end time
    and exit status once the run finishes."""
    prov = docs["run_root"] / "logs" / "provenance.json"
    seen_at_first_dispatch: dict = {}

    real_chain = sweep.run_respec_cascade_chain

    def spying_chain(doc_label, docx_path, arm, model, run_root, entry, **kwargs):
        if not seen_at_first_dispatch:
            seen_at_first_dispatch["exists"] = prov.is_file()
            if prov.is_file():
                seen_at_first_dispatch["record"] = json.loads(prov.read_text(encoding="utf-8"))
        return {"chain_id": f"{doc_label}-{arm}", "doc_label": doc_label, "arm": arm, "status": "completed"}

    monkeypatch.setattr(sweep, "run_respec_cascade_chain", spying_chain)
    argv = ["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]),
            "--model", "claude-sonnet-5", "--max-workers", "1", "--provenance-json", str(prov)]
    code = sweep.main(argv)
    assert code == 0

    assert seen_at_first_dispatch["exists"] is True  # written before any trial dispatched
    start_record = seen_at_first_dispatch["record"]
    assert set(start_record) == _PROVENANCE_KEYS
    assert start_record["end_time_utc"] is None and start_record["exit_status"] is None
    assert start_record["model"] == "claude-sonnet-5"
    assert start_record["documents_manifest_path"] == str(docs["manifest"])
    assert start_record["documents_manifest_sha256"] == hashlib.sha256(docs["manifest"].read_bytes()).hexdigest()
    schedule_bytes = (docs["run_root"] / sweep.SCHEDULE_NAME).read_bytes()
    assert start_record["schedule_sha256"] == hashlib.sha256(schedule_bytes).hexdigest()
    assert start_record["schedule_path"] == str(docs["run_root"] / sweep.SCHEDULE_NAME)
    assert start_record["repo_git_commit"]  # non-empty: this repo's HEAD
    assert "meridian_docs" in start_record and isinstance(start_record["meridian_docs"], dict)
    assert start_record["argv"][0].endswith(".py") or "run_respec_cascade_sweep" in " ".join(start_record["argv"])

    final_record = json.loads(prov.read_text(encoding="utf-8"))
    assert final_record["exit_status"] == 0
    assert final_record["end_time_utc"] is not None
    assert final_record["schedule_sha256"] == start_record["schedule_sha256"]  # unchanged by the end update


def test_a_refused_start_updates_an_existing_provenance_file_with_the_refusal_status(docs):
    """A relaunch that refuses to start (schedule mismatch) after a prior
    successful run's provenance file already exists still gets its exit
    status recorded, without disturbing the earlier start-of-run fields."""
    documents = sweep.load_document_manifest(docs["manifest"])
    prov = docs["run_root"] / "provenance.json"
    assert sweep.main(["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]),
                       "--max-workers", "1", "--provenance-json", str(prov)]) == 0
    first = json.loads(prov.read_text(encoding="utf-8"))

    code = sweep.main(["--run-root", str(docs["run_root"]), "--documents-manifest", str(docs["manifest"]),
                       "--six-family", "--provenance-json", str(prov)])
    assert code == 2  # rotation mismatch on relaunch
    second = json.loads(prov.read_text(encoding="utf-8"))
    assert second["exit_status"] == 2
    assert second["argv"] == first["argv"]  # start-of-run content untouched by the refusal path
