"""PAPER-S23: primary-run sweep driver for the respec_cascade task family
(docs/paper-s23-respec-cascade-protocol-v0.md, locked, five-family
contingency). Resolves anchor-sets for all 3 real author-owned documents
(protocol section 1.1), then runs one run_respec_cascade_chain per
(document, anchor_set_index, arm) via ThreadPoolExecutor -- mirrors
tools/run_paper_s7_benchmark.py::run_corpus_slice's own concurrency pattern
exactly (same primitive, same as-completed collection, same
harness_exception degrade-on-raise), generalized from that function's
(family, k) job grid to this family's (document, anchor_set_index) grid.

doc_label uses the f"{original_doc_label}__anchor{i}" convention
tools/compute_respec_cascade_statistics.py's loaders already document and
expect (see that module's SCHEMA section) -- this is the load-bearing
integration contract for section 7's paired comparison.

Every anchor-set resolved -- usable or not -- is recorded (never silently
dropped), per protocol section 6's N-disclosure discipline.

--six-family runs protocol section 2.2's six-family rotation (adds
table_structural; each anchor-set gets a table anchor from
add_table_anchors) instead of the five-family contingency.

--archive <path.tar.gz> packs the run (and --baseline-run-root, if given)
into one tar.gz with a sha256 manifest, after the sweep or, with
--archive-only, on its own: every chain-result.json, step-result.json and
other JSON/log/text file and, by default, every .docx (every intermediate
document is needed to re-grade a chain); --archive-named-docx-only keeps only
the .docx files a chain-result.json or step-result.json names. Download it
BEFORE tearing down the pod or its volume -- the 2026-09-23 run's raw results
were lost that way.

Documents (P-R6): --documents-manifest <json> with rows {doc_label,
docx_path, sha256}; every SHA-256 is checked before anything else. Without
it, the three author documents of REAL_DOCUMENTS (hashes recorded, not
checked).

Anchor schedule (review item 19): the schedule is resolved once and written
to <run-root>/anchor-schedules.json with anchor-schedules.meta.json (its
sha256, the documents and their hashes, the rotation). A relaunch READS an
existing schedule and never re-resolves it, and refuses to start when the
file, its recorded hash, the documents, the rotation or
--expected-schedule-sha256 disagree. --check-only resolves (or verifies) and
hashes the schedule, reports usable anchor-sets per document, and exits
without running any trial (non-zero unless every document has
--max-anchor-sets usable anchor-sets).

Both arms of each (document, anchor-set) are submitted back to back
(--arm-order-seed fixes their order); a sweep-wide circuit breaker stops
dispatch at the first global infrastructure signature (exit code 3); and
--max-chain-attempts applies the rerun limit (claude_pair_runner).

Usage:
    python run_respec_cascade_sweep.py --run-root <dir> --model haiku [--max-anchor-sets 4] [--max-workers 4] [--six-family]
        [--documents-manifest <json>] [--expected-schedule-sha256 <hex>] [--check-only]
        [--arm-order-seed <int>] [--max-chain-attempts 2]
        [--archive <dir>/respec-cascade-run.tar.gz --baseline-run-root <dir>]
    python run_respec_cascade_sweep.py --run-root <dir> --baseline-run-root <dir> --archive <path.tar.gz> --archive-only
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_pair_runner import ATTIC_DIR_NAME, CircuitBreaker, CircuitOpenError  # noqa: E402
from docx_anchor_prober import resolve_multiple_body_anchors, resolve_respec_schedule  # noqa: E402
from provenance import build_provenance, write_provenance_end, write_provenance_start  # noqa: E402
from run_paper_s7_benchmark import arm_order  # noqa: E402
from run_respec_cascade_family import STATUS_ABORTED_CIRCUIT_OPEN, run_respec_cascade_chain  # noqa: E402
from usage_cap import UsagePauseController, run_with_usage_cap_retry  # noqa: E402

# The three real author-owned documents (docs/paper-s23-respec-cascade-protocol-v0.md
# section 1.1, hash-pinned 2026-09-20 in raw/author-owned-personal/PROVENANCE.md).
# Base directory is overridable via RESPEC_CASCADE_CORPUS_DIR (e.g. a Linux
# RunPod path like /workspace/ooxml-graph-paper/corpus, where the local
# Windows raw/author-owned-personal path obviously does not exist) -- found
# live, 2026-09-22, when this hardcoded Windows path crashed the sweep at
# startup on a fresh RunPod pod.
_CORPUS_DIR = Path(os.environ.get(
    "RESPEC_CASCADE_CORPUS_DIR",
    r"D:\MeridianData\ooxml-graph-paper\raw\author-owned-personal",
))
REAL_DOCUMENTS: dict[str, Path] = {
    "jcshm-manuscript": _CORPUS_DIR / "jcshm-manuscript.docx",
    "jcshm-si": _CORPUS_DIR / "jcshm-si.docx",
    "masters-dissertation-defense": _CORPUS_DIR / "masters-dissertation-defense.docx",
}


SCHEDULE_NAME = "anchor-schedules.json"
SCHEDULE_META_NAME = "anchor-schedules.meta.json"
SCHEDULE_META_SCHEMA = "paper-s25-respec-anchor-schedule-meta-v1"


class ScheduleMismatchError(RuntimeError):
    """A document hash, the stored anchor schedule, its recorded hash or the
    expected (locked) hash disagree: the sweep refuses to start."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_document_manifest(path: Path) -> dict[str, dict[str, Any]]:
    """{doc_label: {"docx_path": Path, "sha256": str | None}} from a document
    manifest {"documents": [{doc_label, docx_path, sha256}, ...]} (the same
    file both the primary and the baseline sweep read). A relative docx_path
    is resolved against the manifest's own directory. Order is kept."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    documents: dict[str, dict[str, Any]] = {}
    for row in manifest["documents"]:
        label = row["doc_label"]
        if label in documents:
            raise ValueError(f"{path}: duplicate doc_label {label!r}")
        docx_path = Path(row["docx_path"])
        if not docx_path.is_absolute():
            docx_path = path.parent / docx_path
        documents[label] = {"docx_path": docx_path, "sha256": row.get("sha256")}
    if not documents:
        raise ValueError(f"{path}: no documents")
    return documents


def default_documents() -> dict[str, dict[str, Any]]:
    """The three author documents of REAL_DOCUMENTS, with no expected hash."""
    return {label: {"docx_path": path, "sha256": None} for label, path in REAL_DOCUMENTS.items()}


def verify_documents(documents: dict[str, dict[str, Any]]) -> dict[str, str]:
    """{doc_label: sha256} of every document, checked against the expected
    sha256 where one is given. Raises ScheduleMismatchError on a missing file
    or any mismatch -- before any schedule is resolved or trial started."""
    hashes: dict[str, str] = {}
    problems: list[str] = []
    for label, doc in documents.items():
        path = Path(doc["docx_path"])
        if not path.is_file():
            problems.append(f"{label}: {path} does not exist")
            continue
        actual = _sha256_file(path)
        expected = doc.get("sha256")
        if expected is not None and actual.lower() != str(expected).lower():
            problems.append(f"{label}: sha256 {actual} != expected {expected}")
        hashes[label] = actual
    if problems:
        raise ScheduleMismatchError("document check failed: " + "; ".join(problems))
    return hashes


def resolve_all_schedules(
    max_anchor_sets: int = 4, documents: dict[str, Path] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """One resolve_respec_schedule call per document ({doc_label: docx path};
    REAL_DOCUMENTS by default). The result, written once to
    anchor-schedules.json, is the single source of truth the baseline sweep
    (run_respec_cascade_baselines.py) takes its per-family anchors from --
    both sweeps must see the IDENTICAL frozen anchor-sets, per protocol
    section 2.1's "literal targets are frozen, not re-derived per trial."""
    documents = REAL_DOCUMENTS if documents is None else documents
    return {label: resolve_respec_schedule(path, max_anchor_sets=max_anchor_sets) for label, path in documents.items()}


def _schedule_bytes(schedules: dict[str, list[dict[str, Any]]]) -> bytes:
    # The exact serialization anchor-schedules.json has always had.
    return json.dumps(schedules, indent=2, ensure_ascii=False).encode("utf-8")


def read_schedule_meta(run_root: Path) -> dict[str, Any] | None:
    path = run_root / SCHEDULE_META_NAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_verified_schedule(
    run_root: Path, *, expected_sha256: str | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], str]:
    """(schedules, meta, sha256) of the anchor schedule already stored in
    `run_root`, after checking the file's sha256 against the one recorded
    in its meta file and against `expected_sha256` when given. Never
    resolves anything. Raises ScheduleMismatchError when the schedule or its
    meta file is missing or any hash disagrees."""
    path = run_root / SCHEDULE_NAME
    if not path.is_file():
        raise ScheduleMismatchError(
            f"{path} does not exist: run the primary sweep (or its --check-only) first",
        )
    data = path.read_bytes()
    sha = _sha256_bytes(data)
    meta = read_schedule_meta(run_root)
    if meta is None:
        raise ScheduleMismatchError(f"{run_root / SCHEDULE_META_NAME} does not exist; the schedule's hash is unrecorded")
    problems = []
    if meta.get("anchor_schedules_sha256") != sha:
        problems.append(f"file sha256 {sha} != recorded {meta.get('anchor_schedules_sha256')}")
    if expected_sha256 is not None and expected_sha256.lower() != sha:
        problems.append(f"file sha256 {sha} != expected {expected_sha256}")
    if problems:
        raise ScheduleMismatchError(f"{path}: " + "; ".join(problems))
    return json.loads(data.decode("utf-8")), meta, sha


def prepare_schedules(
    run_root: Path, documents: dict[str, Path], document_hashes: dict[str, str], *,
    six_family: bool, max_anchor_sets: int, expected_sha256: str | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    """The run's anchor schedule and its sha256 (review item 19).

    If <run_root>/anchor-schedules.json exists (a relaunch) it is READ, never
    re-resolved, and accepted only when its sha256 matches its meta file and
    `expected_sha256`, and the meta file's documents, document hashes,
    rotation and max_anchor_sets match this launch. A schedule without a meta
    file (written before 2026-09-25) is adopted only when `expected_sha256`
    matches it. Otherwise the schedule is resolved (plus table anchors for
    six_family) and written with its meta file -- unless `expected_sha256`
    is given and differs, in which case it is written to
    anchor-schedules.rejected.json instead and the launch refused."""
    path = run_root / SCHEDULE_NAME
    rotation = "six_family" if six_family else "five_family_contingency"
    if path.is_file():
        data = path.read_bytes()
        sha = _sha256_bytes(data)
        meta = read_schedule_meta(run_root)
        problems: list[str] = []
        if meta is None:
            if expected_sha256 is None:
                problems.append("no anchor-schedules.meta.json (unrecorded hash); pass --expected-schedule-sha256 to adopt it")
        else:
            if meta.get("anchor_schedules_sha256") != sha:
                problems.append(f"file sha256 {sha} != recorded {meta.get('anchor_schedules_sha256')}")
            if meta.get("rotation") != rotation:
                problems.append(f"rotation {meta.get('rotation')!r} != this launch's {rotation!r}")
            if meta.get("max_anchor_sets") != max_anchor_sets:
                problems.append(f"max_anchor_sets {meta.get('max_anchor_sets')} != {max_anchor_sets}")
            recorded = {label: d.get("sha256") for label, d in (meta.get("documents") or {}).items()}
            if recorded != document_hashes:
                problems.append(f"documents {recorded} != this launch's {document_hashes}")
        if expected_sha256 is not None and expected_sha256.lower() != sha:
            problems.append(f"file sha256 {sha} != expected {expected_sha256}")
        schedules = json.loads(data.decode("utf-8"))
        if set(schedules) != set(documents):
            problems.append(f"schedule documents {sorted(schedules)} != {sorted(documents)}")
        if problems:
            raise ScheduleMismatchError(f"refusing to reuse {path}: " + "; ".join(problems))
        if meta is None:
            _write_schedule_meta(run_root, sha, documents, document_hashes, rotation, max_anchor_sets, adopted=True)
        return schedules, sha

    schedules = resolve_all_schedules(max_anchor_sets, documents)
    if six_family:
        schedules = {
            label: add_table_anchors(documents[label], schedule, max_anchor_sets)
            for label, schedule in schedules.items()
        }
    data = _schedule_bytes(schedules)
    sha = _sha256_bytes(data)
    run_root.mkdir(parents=True, exist_ok=True)
    if expected_sha256 is not None and expected_sha256.lower() != sha:
        (run_root / "anchor-schedules.rejected.json").write_bytes(data)
        raise ScheduleMismatchError(
            f"resolved schedule sha256 {sha} != expected {expected_sha256}; written to anchor-schedules.rejected.json, "
            "no schedule adopted",
        )
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    _write_schedule_meta(run_root, sha, documents, document_hashes, rotation, max_anchor_sets, adopted=False)
    return schedules, sha


def _write_schedule_meta(
    run_root: Path, sha: str, documents: dict[str, Path], document_hashes: dict[str, str], rotation: str,
    max_anchor_sets: int, *, adopted: bool,
) -> None:
    meta = {
        "schema": SCHEDULE_META_SCHEMA,
        "written_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "anchor_schedules_sha256": sha,
        "adopted_existing_schedule": adopted,
        "rotation": rotation, "max_anchor_sets": max_anchor_sets,
        "documents": {
            label: {"docx_path": str(path), "sha256": document_hashes.get(label)} for label, path in documents.items()
        },
    }
    (run_root / SCHEDULE_META_NAME).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def schedule_usability(schedules: dict[str, list[dict[str, Any]]], max_anchor_sets: int) -> dict[str, Any]:
    """Per document: usable anchor-sets out of `max_anchor_sets`, and the
    reasons for the unusable ones. `ok` when every document has all of them."""
    documents = {}
    for label, schedule in schedules.items():
        usable = sum(1 for entry in schedule if entry.get("usable"))
        documents[label] = {
            "usable": usable, "resolved": len(schedule),
            "unusable_reasons": [entry.get("reason") for entry in schedule if not entry.get("usable")],
        }
    return {"ok": all(d["usable"] >= max_anchor_sets for d in documents.values()), "documents": documents}


def add_table_anchors(
    docx_path: Path, schedule: list[dict[str, Any]], max_anchor_sets: int = 4,
) -> list[dict[str, Any]]:
    """Six-family rotation only: gives every anchor-set of `schedule` (one
    document's resolve_respec_schedule output) the i-th table anchor, resolved
    exactly the way resolve_respec_schedule resolves citation/equation/caption
    -- resolve_multiple_body_anchors, excluding every para_id those three
    families already claim anywhere in the schedule, so no two families edit
    the same paragraph. An anchor-set with no table anchor becomes unusable
    with reason "missing_table_anchor" (recorded, never dropped). Returns new
    dicts; `schedule` is not modified."""
    claimed = {
        entry[key]["anchor_para_id"]
        for entry in schedule
        for key in ("citation_anchor", "equation_anchor", "caption_anchor")
        if (entry.get(key) or {}).get("found")
    }
    table_anchors = resolve_multiple_body_anchors(docx_path, max_anchors=max_anchor_sets, exclude_para_ids=claimed)
    out: list[dict[str, Any]] = []
    for i, entry in enumerate(schedule):
        entry = dict(entry)
        entry["table_anchor"] = (
            table_anchors[i] if i < len(table_anchors)
            else {"found": False, "reason": "no eligible body paragraph left for a table anchor"}
        )
        if entry.get("usable") and not entry["table_anchor"].get("found"):
            entry["usable"] = False
            entry["reason"] = "missing_table_anchor"
        out.append(entry)
    return out


def check_primary_sweep(
    run_root: Path, *, max_anchor_sets: int = 4, six_family: bool = False,
    documents: dict[str, dict[str, Any]] | None = None, expected_schedule_sha256: str | None = None,
) -> dict[str, Any]:
    """--check-only: verifies the documents, resolves (or reads and
    verifies) the anchor schedule, and reports its sha256 and usability. No
    trial is started. Raises ScheduleMismatchError on any hash problem."""
    documents = default_documents() if documents is None else documents
    document_hashes = verify_documents(documents)
    run_root.mkdir(parents=True, exist_ok=True)
    schedules, sha = prepare_schedules(
        run_root, {label: Path(d["docx_path"]) for label, d in documents.items()}, document_hashes,
        six_family=six_family, max_anchor_sets=max_anchor_sets, expected_sha256=expected_schedule_sha256,
    )
    return {
        "anchor_schedules_sha256": sha, "document_hashes": document_hashes,
        "rotation": "six_family" if six_family else "five_family_contingency",
        **schedule_usability(schedules, max_anchor_sets),
    }


def _respec_chain_key(job: dict[str, Any]) -> tuple[str, str]:
    return (job["scoped_label"], job["arm"])


def run_primary_sweep(
    run_root: Path, model: str, *, max_anchor_sets: int = 4, max_workers: int = 4,
    word_receipts_enabled: bool = False, six_family: bool = False,
    documents: dict[str, dict[str, Any]] | None = None, expected_schedule_sha256: str | None = None,
    arm_order_seed: int | None = None, max_chain_attempts: int | None = None,
    pause_controller: UsagePauseController | None = None, max_usage_cap_rounds: int | None = None,
    provenance_json: Path | None = None, documents_manifest_path: Path | None = None,
    argv: list[str] | None = None,
) -> dict[str, Any]:
    """`documents`: {doc_label: {"docx_path", "sha256"}} (load_document_manifest);
    REAL_DOCUMENTS when None. Hashes are verified and the schedule prepared
    (prepare_schedules) before any trial starts.

    `provenance_json`, when given, is written (build_provenance/
    write_provenance_start) right after the schedule is prepared above --
    still before any trial dispatches -- with the now-known schedule path
    and sha256; `documents_manifest_path` is the raw --documents-manifest
    CLI value (None when the default REAL_DOCUMENTS were used), recorded
    alongside its own sha256. The caller (main()) updates the same file with
    the end time/exit status once the run finishes (write_provenance_end).

    Rate-limit handling (2026-09-25): dispatched in rounds via
    usage_cap.run_with_usage_cap_retry -- see run_paper_s7_benchmark.
    run_corpus_slice's docstring for the exact semantics, shared verbatim
    here. `pause_controller` defaults to a fresh UsagePauseController writing
    its heartbeat to `<run_root>/usage-cap-status.json`.
    """
    documents = default_documents() if documents is None else documents
    document_hashes = verify_documents(documents)
    doc_paths = {label: Path(d["docx_path"]) for label, d in documents.items()}
    run_root.mkdir(parents=True, exist_ok=True)
    schedules, schedule_sha = prepare_schedules(
        run_root, doc_paths, document_hashes, six_family=six_family, max_anchor_sets=max_anchor_sets,
        expected_sha256=expected_schedule_sha256,
    )
    if provenance_json is not None:
        record = build_provenance(
            argv if argv is not None else sys.argv, model=model,
            documents_manifest=documents_manifest_path,
            schedule_path=run_root / SCHEDULE_NAME, schedule_sha256=schedule_sha,
        )
        write_provenance_start(provenance_json, record)
    if pause_controller is None:
        pause_controller = UsagePauseController(heartbeat_path=run_root / "usage-cap-status.json")

    all_jobs: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for doc_label, schedule in schedules.items():
        for entry in schedule:
            if not entry["usable"]:
                excluded.append({
                    "doc_label": doc_label, "anchor_set_index": entry["anchor_set_index"],
                    "reason": entry["reason"],
                })
                continue
            scoped_label = f"{doc_label}__anchor{entry['anchor_set_index']}"
            # Both arms of each (document, anchor-set) are one job each so a
            # usage-cap retry round can re-dispatch exactly the chains it
            # needs to; arm order within a pair is still fixed by arm_order.
            for arm in arm_order(arm_order_seed, scoped_label):
                all_jobs.append({"doc_label": doc_label, "scoped_label": scoped_label, "entry": entry, "arm": arm})

    def dispatch_round(jobs: list[dict[str, Any]], circuit_breaker: CircuitBreaker) -> tuple[dict[Any, dict[str, Any]], list[Any]]:
        round_results: dict[Any, dict[str, Any]] = {}
        round_submission: list[Any] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            # Submitted in document order, both arms of each pair back to
            # back on the first round; the executor starts jobs in
            # submission order.
            for job in jobs:
                future = pool.submit(
                    run_respec_cascade_chain,
                    job["scoped_label"], doc_paths[job["doc_label"]], job["arm"], model, run_root, job["entry"],
                    word_receipts_enabled=word_receipts_enabled, six_family=six_family,
                    circuit_breaker=circuit_breaker, max_chain_attempts=max_chain_attempts,
                    pause_controller=pause_controller,
                )
                key = _respec_chain_key(job)
                futures[future] = key
                round_submission.append([job["scoped_label"], job["arm"]])
            for future in concurrent.futures.as_completed(futures):
                scoped_label, arm = key = futures[future]
                try:
                    round_results[key] = future.result()
                except CircuitOpenError as exc:
                    round_results[key] = {
                        "chain_id": f"{scoped_label}-respec_cascade-{arm}-ABORTED",
                        "doc_label": scoped_label, "family": "respec_cascade", "arm": arm,
                        "status": STATUS_ABORTED_CIRCUIT_OPEN, "reason": str(exc),
                        "phase1_result": None, "phase2_result": None, "phase3_result": None,
                    }
                except Exception as exc:  # noqa: BLE001 -- one job's crash must not lose the others
                    round_results[key] = {
                        "chain_id": f"{scoped_label}-respec_cascade-{arm}-EXCEPTION",
                        "doc_label": scoped_label, "family": "respec_cascade", "arm": arm,
                        "status": "harness_exception", "reason": f"{type(exc).__name__}: {exc}",
                        "phase1_result": None, "phase2_result": None, "phase3_result": None,
                    }
        return round_results, round_submission

    final_results, submission_order, usage_cap_rounds = run_with_usage_cap_retry(
        dispatch_round, all_jobs, pause_controller, job_key=_respec_chain_key,
        make_circuit_breaker=CircuitBreaker, max_rounds=max_usage_cap_rounds,
    )
    results = list(final_results.values())
    final_circuit_breaker = usage_cap_rounds[-1]["circuit_breaker"] if usage_cap_rounds else CircuitBreaker().state()

    manifest = {
        "schema": "paper-s23-respec-cascade-primary-sweep-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": model, "max_anchor_sets": max_anchor_sets,
        "rotation": "six_family" if six_family else "five_family_contingency",
        "anchor_schedules_sha256": schedule_sha, "document_hashes": document_hashes,
        "arm_order_seed": arm_order_seed, "max_chain_attempts": max_chain_attempts,
        "submission_order": submission_order,
        "circuit_breaker": final_circuit_breaker,
        "usage_cap_rounds": usage_cap_rounds,
        "usage_cap_status": pause_controller.state(),
        "chain_count": len(results),
        "excluded_anchor_sets": excluded,
        "chains_summary": [
            {"chain_id": r.get("chain_id"), "doc_label": r.get("doc_label"), "arm": r.get("arm"), "status": r.get("status"),
             "freeze_cause": r.get("freeze_cause")}
            for r in results
        ],
    }
    (run_root / "sweep-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return manifest


# ---------------------------------------------------------------------------
# Archive: one downloadable tar.gz of everything needed to re-grade and
# re-aggregate the run, with a sha256 manifest.
# ---------------------------------------------------------------------------

_ARCHIVE_TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".log", ".txt", ".md", ".csv", ".out", ".err"})
_ARCHIVE_MANIFEST_NAME = "ARCHIVE-MANIFEST.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _docx_paths_named_in(value: Any) -> list[str]:
    """Every "output_docx_path"/"final_output_docx" string anywhere in a
    chain-result.json (cascade chains name their final document and, when
    frozen, the frozen step's output; K=1 baseline chains name each trial's
    output)."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, v in value.items():
            if key in ("output_docx_path", "final_output_docx") and isinstance(v, str):
                found.append(v)
            else:
                found.extend(_docx_paths_named_in(v))
    elif isinstance(value, list):
        for v in value:
            found.extend(_docx_paths_named_in(v))
    return found


def archive_run(roots: dict[str, Path], archive_path: Path, *, all_docx: bool = True) -> dict[str, Any]:
    """Packs `roots` ({name in archive: directory}) into `archive_path`
    (.tar.gz): every JSON/log/text file (every chain-result.json and
    step-result.json, sweep and baseline manifests, anchor schedules, logs,
    copied session transcripts), and every .docx -- or, with all_docx=False,
    only every .docx a chain-result.json or step-result.json names (each
    chain's final document, a frozen step's output, every step's output
    including the Checkpoint A/B documents and each Phase-3 inverse output,
    each K=1 baseline trial's output). all_docx is the default since
    2026-09-25: every intermediate document is needed to re-grade a chain.
    A manifest of {archive path: sha256, bytes}
    is stored inside the archive as ARCHIVE-MANIFEST.json and next to it as
    `<archive>.manifest.json`; the archive's own sha256 goes to
    `<archive>.sha256` (sha256sum format) so the download can be checked.
    Named .docx files that are missing, or outside every root, are listed
    in the manifest rather than silently skipped."""
    named_docx: set[Path] = set()
    for root in roots.values():
        if not root.is_dir():
            continue
        for pattern in ("chain-result.json", "step-result.json"):
            for cr in root.rglob(pattern):
                if ATTIC_DIR_NAME in cr.relative_to(root).parts:
                    # An earlier attempt moved to the attic names paths from
                    # before the move; its files are archived where they are.
                    continue
                try:
                    chain = json.loads(cr.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                named_docx.update(Path(p).resolve() for p in _docx_paths_named_in(chain))

    members: list[tuple[str, Path]] = []
    for name, root in roots.items():
        if not root.is_dir():
            continue
        root_resolved = root.resolve()
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.resolve() == archive_path.resolve():
                continue
            suffix = path.suffix.lower()
            if suffix in _ARCHIVE_TEXT_SUFFIXES or (
                suffix == ".docx" and (all_docx or path.resolve() in named_docx)
            ):
                members.append((f"{name}/{path.resolve().relative_to(root_resolved).as_posix()}", path))

    archived = {p.resolve() for _, p in members}
    not_archived = sorted(str(p) for p in named_docx if p not in archived)
    manifest = {
        "schema": "paper-s23-respec-cascade-archive-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "roots": {name: str(root) for name, root in roots.items()},
        "all_docx": all_docx,
        "files": {arcname: {"sha256": _sha256_file(path), "bytes": path.stat().st_size} for arcname, path in members},
        "named_docx_not_archived": not_archived,
    }
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = archive_path.with_name(archive_path.name + ".tmp")
    with tarfile.open(tmp_path, "w:gz") as tar:
        for arcname, path in members:
            tar.add(path, arcname=arcname, recursive=False)
        info = tarfile.TarInfo(_ARCHIVE_MANIFEST_NAME)
        info.size = len(manifest_bytes)
        info.mtime = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        tar.addfile(info, io.BytesIO(manifest_bytes))
    tmp_path.replace(archive_path)

    archive_sha256 = _sha256_file(archive_path)
    archive_path.with_name(archive_path.name + ".manifest.json").write_bytes(manifest_bytes)
    archive_path.with_name(archive_path.name + ".sha256").write_text(
        f"{archive_sha256}  {archive_path.name}\n", encoding="utf-8",
    )
    return {
        "archive": str(archive_path), "sha256": archive_sha256, "bytes": archive_path.stat().st_size,
        "file_count": len(members), "named_docx_not_archived": not_archived,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-anchor-sets", type=int, default=4)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--word-receipts", action="store_true", help="Enable Word-COM milestone receipts (Windows only; off by default for RunPod/Linux runs).")
    parser.add_argument(
        "--six-family", action="store_true",
        help="Run the six-family rotation R (protocol section 2.2, adds table_structural) instead of the five-family contingency R'.",
    )
    parser.add_argument(
        "--archive", type=Path, default=None,
        help="Write a .tar.gz of the run (plus --baseline-run-root) with a sha256 manifest. Download it before any pod teardown.",
    )
    parser.add_argument("--baseline-run-root", type=Path, default=None, help="Also archive this baseline run root (run_respec_cascade_baselines.py output).")
    parser.add_argument("--archive-only", action="store_true", help="Skip the sweep; only write --archive.")
    parser.add_argument(
        "--archive-all-docx", action="store_true",
        help="Archive every .docx (the default since 2026-09-25; kept for compatibility).",
    )
    parser.add_argument(
        "--archive-named-docx-only", action="store_true",
        help="Archive only the .docx files a chain-result.json or step-result.json names.",
    )
    parser.add_argument(
        "--documents-manifest", type=Path, default=None,
        help="JSON {\"documents\": [{doc_label, docx_path, sha256}]}; every sha256 is checked first. "
             "Omitted: the three author documents of REAL_DOCUMENTS.",
    )
    parser.add_argument(
        "--expected-schedule-sha256", default=None,
        help="Refuse to start unless anchor-schedules.json has this sha256 (the hash locked in the protocol).",
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="Verify the documents, resolve (or read and verify) and hash the anchor schedule, report usable "
             "anchor-sets, and exit without running any trial (non-zero unless every document has "
             "--max-anchor-sets usable anchor-sets).",
    )
    parser.add_argument("--arm-order-seed", type=int, default=None,
                        help="Seed for each matched pair's arm submission order. Omitted: control first.")
    parser.add_argument("--max-chain-attempts", type=int, default=None,
                        help="Rerun limit per chain (see claude_pair_runner.begin_chain_attempt). Omitted: no limit.")
    parser.add_argument(
        "--max-usage-cap-rounds", type=int, default=None,
        help="Safety valve: stop auto-retrying after this many usage-cap/rate-limit pause-and-resume rounds "
             "(circuit_breaker stays open, exit 3). Omitted: unlimited -- the sweep resumes on its own for as "
             "long as the account keeps hitting its usage cap or a transient rate limit, with no relaunch needed.",
    )
    parser.add_argument(
        "--usage-cap-base-backoff-seconds", type=float, default=30.0,
        help="Backoff before the first retry after a usage-cap/rate-limit pause when the CLI gave no reset time.",
    )
    parser.add_argument(
        "--usage-cap-max-backoff-seconds", type=float, default=1800.0,
        help="Cap on the exponential backoff between usage-cap/rate-limit retry rounds (default 30 minutes).",
    )
    parser.add_argument(
        "--provenance-json", type=Path, default=None,
        help="Write a provenance record here (argv, this repo's git commit, the installed Meridian Docs "
             "package's commit/version, model, documents-manifest path+sha256, the resolved anchor schedule "
             "path+sha256, hostname, start/end time, exit status) right after the schedule is prepared -- "
             "still before any trial dispatches -- on a real run (not --check-only/--archive-only), then "
             "update it with the end time and exit status when the run finishes.",
    )
    args = parser.parse_args(argv)
    if args.archive_only and args.archive is None:
        parser.error("--archive-only needs --archive")
    if args.archive_all_docx and args.archive_named_docx_only:
        parser.error("--archive-all-docx and --archive-named-docx-only are mutually exclusive")

    def _archive() -> None:
        roots = {"run-root": args.run_root}
        if args.baseline_run_root is not None:
            roots["baseline-run-root"] = args.baseline_run_root
        print(json.dumps(archive_run(roots, args.archive, all_docx=not args.archive_named_docx_only), indent=2))

    if args.archive_only:
        _archive()
        return 0

    documents = load_document_manifest(args.documents_manifest) if args.documents_manifest is not None else None
    if args.check_only:
        try:
            report = check_primary_sweep(
                args.run_root, max_anchor_sets=args.max_anchor_sets, six_family=args.six_family,
                documents=documents, expected_schedule_sha256=args.expected_schedule_sha256,
            )
        except ScheduleMismatchError as exc:
            print(f"CHECK FAILED: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 2

    pause_controller = UsagePauseController(
        heartbeat_path=args.run_root / "usage-cap-status.json",
        base_backoff_seconds=args.usage_cap_base_backoff_seconds,
        max_backoff_seconds=args.usage_cap_max_backoff_seconds,
    )
    try:
        manifest = run_primary_sweep(
            args.run_root, args.model, max_anchor_sets=args.max_anchor_sets,
            max_workers=args.max_workers, word_receipts_enabled=args.word_receipts, six_family=args.six_family,
            documents=documents, expected_schedule_sha256=args.expected_schedule_sha256,
            arm_order_seed=args.arm_order_seed, max_chain_attempts=args.max_chain_attempts,
            pause_controller=pause_controller, max_usage_cap_rounds=args.max_usage_cap_rounds,
            provenance_json=args.provenance_json, documents_manifest_path=args.documents_manifest,
        )
    except ScheduleMismatchError as exc:
        print(f"REFUSING TO START: {exc}", file=sys.stderr)
        if args.provenance_json is not None:
            write_provenance_end(args.provenance_json, exit_status=2)
        return 2
    print(json.dumps({
        "chain_count": manifest["chain_count"],
        "excluded_anchor_set_count": len(manifest["excluded_anchor_sets"]),
        "status_counts": {
            status: sum(1 for c in manifest["chains_summary"] if c["status"] == status)
            for status in sorted({c["status"] for c in manifest["chains_summary"]})
        },
    }, indent=2))
    print(f"Full manifest: {args.run_root / 'sweep-manifest.json'}")
    if manifest["usage_cap_rounds"]:
        print(f"Usage-cap pause/resume rounds: {len(manifest['usage_cap_rounds'])} "
              f"(heartbeat: {args.run_root / 'usage-cap-status.json'})")
    if args.archive is not None:
        _archive()
    exit_status = 3 if manifest["circuit_breaker"]["open"] else 0
    if manifest["circuit_breaker"]["open"]:
        print(f"CIRCUIT BREAKER OPEN: {json.dumps(manifest['circuit_breaker'])}", file=sys.stderr)
    if args.provenance_json is not None:
        write_provenance_end(args.provenance_json, exit_status=exit_status)
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
