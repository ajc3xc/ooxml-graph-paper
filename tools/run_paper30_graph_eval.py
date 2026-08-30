"""PAPER-30: real graph-aware evaluation runner, using tools/graph_scorer.py.

This is a SEPARATE runner from run_paper15_smoke.py, not a replacement --
run_paper15_smoke.py's simplified count/overlap proxy remains a valid, already
-reported first attempt (paper15-first-attempt-v0.md). This script delivers
the upgrade PAPER-30 actually asks for: real node-level correspondence,
precision/recall/F1 by kind, a genuine reading-order metric, independently
re-derived equation semantic-class accuracy, bootstrap CIs, and paired
document-level permutation tests -- against the SAME 127-document gold corpus
and the SAME underlying extraction libraries (document_content_tree,
parse_docx_equations_local, python-docx), so results are directly comparable
to, not a fork of, the existing first-attempt numbers.

Per-item extraction here is intentionally separate from
run_paper15_smoke.py's extract_native_meridian/extract_python_docx, which
return aggregate counts only -- node-level correspondence needs the actual
per-paragraph/per-table/per-equation items, not just totals.

PAPER-S5 adds an OPT-IN, bounded Word round-trip editability +
render-equivalence check (`--round-trip-check`, `--round-trip-sample N`):
for a small deterministic sample of documents, a real Word-COM
open(ReadOnly=False) -> append one marker paragraph -> Save() -> Close()
round trip is performed against a disposable working copy (never the
original corpus file), then (a) native-Meridian extraction before vs. after
is diffed via `graph_scorer.score_round_trip_editability` for unintended
structural drift, and (b) retained Word render receipts of both copies are
compared for render-equivalence (page count). This is gated off by default
because it launches real Word processes per sampled document (slow, and
requires local Word COM) -- `not_run` with the exact reason is reported
when Word COM is unavailable, never a fabricated pass.

Usage:
  pixi run python tools/run_paper30_graph_eval.py --slice smoke
  pixi run python tools/run_paper30_graph_eval.py --slice all --include-docling
  pixi run python tools/run_paper30_graph_eval.py --slice smoke --round-trip-check --round-trip-sample 3
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import signal
import sys
import threading
from pathlib import Path
from typing import Any

REPO_ROOT = Path(r"C:\Users\13144\Documents\Meridian\repository")
PAPER_ROOT = Path(r"C:\Users\13144\Documents\Meridian\ooxml-graph-paper")
GOLD_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\gold")
DATA_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper")

sys.path.insert(0, str(REPO_ROOT / "extensions" / "meridian-docs"))
sys.path.insert(0, str(PAPER_ROOT / "tools"))

import graph_scorer  # noqa: E402
from retained_render_receipt import retained_render_receipt  # noqa: E402
from run_paper15_smoke import _find_docx_path, _find_render_pdf, _run_docling_subprocess  # noqa: E402

_WORD_ROUNDTRIP_MARKER_TEXT = "PAPER-S5 round-trip editability probe paragraph."
_WORD_ROUNDTRIP_TIMEOUT_SECONDS = 90.0
_WORD_ROUNDTRIP_CLEANUP_JOIN_SECONDS = 5.0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_gold_items(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gold_record = manifest["gold_record"]
    nodes = gold_record["nodes"]
    edges = gold_record["edges"]
    cell_ids = {n["id"] for n in nodes if n["kind"] == "table_cell"}
    para_like = [n for n in nodes if n["kind"] in ("paragraph", "caption")]
    para_ids_set = {n["id"] for n in para_like}
    nested = {e["dst"] for e in edges if e["kind"] == "contains" and e["src"] in cell_ids and e["dst"] in para_ids_set}
    top_level_paragraphs = [n for n in para_like if n["id"] not in nested]
    # PAPER-S5: caption nodes (a SEQ-field paragraph, per
    # independent_gold_extractor.py's _is_seq_field) and anchor nodes
    # (w:bookmarkStart names) as their own comparable lists, distinct from
    # the generic paragraph list above -- see graph_scorer.py's
    # _caption_node_accuracy / _anchor_node_accuracy.
    captions = [{"text": n.get("attrs", {}).get("text", "")} for n in top_level_paragraphs if n["kind"] == "caption"]
    anchors = [{"name": n.get("attrs", {}).get("name")} for n in nodes if n["kind"] == "anchor"]

    table_nodes = [n for n in nodes if n["kind"] == "table"]
    table_row_nodes = [n for n in nodes if n["kind"] == "table_row"]
    # rows-per-table, in document order, via containment edges (table -> table_row)
    table_id_order = [n["id"] for n in table_nodes]
    rows_by_table: dict[str, int] = {tid: 0 for tid in table_id_order}
    row_id_to_table = {}
    contains_edges = [e for e in edges if e["kind"] == "contains"]
    table_id_set = set(table_id_order)
    row_id_set = {n["id"] for n in table_row_nodes}
    for e in contains_edges:
        if e["src"] in table_id_set and e["dst"] in row_id_set:
            rows_by_table[e["src"]] = rows_by_table.get(e["src"], 0) + 1
    table_grid = gold_record["facts"].get("table_grid", [])
    tables = []
    for i, tid in enumerate(table_id_order):
        col_count = len(table_grid[i]) if i < len(table_grid) else 0
        tables.append({"row_count": rows_by_table.get(tid, 0), "col_count": col_count})

    equation_nodes = sorted(
        (n for n in nodes if n["kind"] == "equation"),
        key=lambda n: n.get("attrs", {}).get("order", 0),
    )
    equations = [{"omml_raw": n.get("attrs", {}).get("omml_raw")} for n in equation_nodes]

    return {
        "paragraphs": [
            {"text": n.get("attrs", {}).get("text", ""), "para_id": n.get("attrs", {}).get("w14_para_id")}
            for n in top_level_paragraphs
        ],
        "tables": tables,
        "equations": equations,
        "equation_nodes": equation_nodes,
        "captions": captions,
        "anchors": anchors,
        "full_text": gold_record["facts"]["text"],
    }


def _block_has_seq_field(block: dict) -> bool:
    """Mirrors independent_gold_extractor.py's own `_is_seq_field` heuristic
    (any SEQ field instruction in the paragraph), but reads it from
    document_content_tree's own per-paragraph `fields` list -- a REAL
    capability document_content_tree already computes (it parses
    w:fldSimple/w:fldChar field instructions for every paragraph) that
    run_paper15_smoke.py's/this module's extraction simply hadn't surfaced
    until PAPER-S5. This is genuinely native Meridian's own extraction
    capability, not a reimplementation bolted on from outside it."""
    return any((f.get("field_type") or "").upper() == "SEQ" for f in block.get("fields", []))


def extract_native_meridian_items(docx_path: Path) -> dict:
    from meridian_docs import docs_intel
    from meridian_docs._vendored_content_tree import document_content_tree

    tree = document_content_tree(str(docx_path))
    blocks = tree["blocks"]
    para_blocks = [b for b in blocks if b["kind"] in ("paragraph", "heading")]
    paragraphs = [
        {"text": b["text"], "para_id": b["para_id"] if not b["para_id"].startswith(("p", "sp")) else None}
        for b in para_blocks
    ]
    # PAPER-S5: caption nodes, via document_content_tree's own field parsing
    # (see _block_has_seq_field). Anchor/bookmark nodes remain
    # not_applicable: no candidate adapter -- document_content_tree exposes
    # no bookmark-listing API (confirmed by direct reading of
    # _vendored_content_tree.py this session; there is no bookmarkStart
    # handling in it at all), and this extraction deliberately does not
    # reimplement one outside Meridian's own library, which would test this
    # harness's own code rather than a real product capability.
    captions = [{"text": b["text"]} for b in para_blocks if _block_has_seq_field(b)]
    tables = [{"row_count": b["row_count"], "col_count": b["col_count"]} for b in blocks if b["kind"] == "table"]
    raw_equations = docs_intel.parse_docx_equations_local(str(docx_path))
    equations = [{"omml_raw": e.get("omml_raw")} for e in sorted(raw_equations, key=lambda e: e.get("ordinal", 0))]
    full_text = "\n".join(p["text"] for p in paragraphs)
    return {"paragraphs": paragraphs, "tables": tables, "equations": equations, "captions": captions,
            "anchors": [], "full_text": full_text}


def extract_python_docx_items(docx_path: Path) -> dict:
    import docx

    document = docx.Document(str(docx_path))
    paragraphs = [{"text": p.text, "para_id": None} for p in document.paragraphs]
    tables = [{"row_count": len(t.rows), "col_count": len(t.columns)} for t in document.tables]
    full_text = "\n".join(p["text"] for p in paragraphs)
    # python-docx has zero OMML/equation API surface (PAPER-14 finding) and
    # no field-instruction (SEQ/bookmark) API surface either (PAPER-S5) --
    # captions/anchors are genuinely not_applicable: no_candidate_adapter.
    return {"paragraphs": paragraphs, "tables": tables, "equations": [], "captions": [], "anchors": [],
            "full_text": full_text}


def extract_docling_items(render_pdf: Path, timeout_s: float) -> tuple[dict | None, dict]:
    """Returns (items, raw) -- items is None on any non-scored outcome, but
    `raw` always carries the real status (crashed/timed_out/scored) and
    detail, so callers never have to collapse distinct failure modes into one
    ambiguous label."""
    raw = _run_docling_subprocess(render_pdf, timeout_s=timeout_s)
    if raw.get("status") != "scored":
        return None, raw
    # Docling's "text" items are not the same granularity as OOXML paragraphs
    # (OCR/layout may merge or split relative to the source) -- treated here
    # as the paragraph-equivalent common-schema slot, per this module's own
    # declared schema note; genuinely different granularity is a real,
    # reported limitation, not silently normalized away.
    full_text = raw.get("full_text", "")
    paragraphs = [{"text": line, "para_id": None} for line in full_text.split("\n") if line.strip()]
    tables = [{"row_count": None, "col_count": None} for _ in range(raw.get("table_count", 0))]
    equations = [{"omml_raw": None} for _ in range(raw.get("equation_count", 0))]
    # PDF/OCR-derived text carries no OOXML field instructions or bookmarks
    # at all -- captions/anchors are genuinely not_applicable: no_candidate_adapter.
    items = {"paragraphs": paragraphs, "tables": tables, "equations": equations, "captions": [], "anchors": [],
              "full_text": full_text, "_raw": raw}
    return items, raw


def _word_open_edit_save_round_trip(docx_path: Path, work_path: Path,
                                     timeout: float = _WORD_ROUNDTRIP_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Real Word-COM open(ReadOnly=False) -> append one marker paragraph ->
    Save() -> Close() round trip against a disposable WORKING COPY at
    `work_path` (the original `docx_path` is only ever read, via
    `shutil.copyfile`, never opened for write). Modeled directly on the
    watchdog/cleanup pattern already validated in this repo by
    `retained_render_receipt.py` (read directly before writing this) and
    `docs/word-roundtrip-preservation-contract-v0.md`'s own `roundtrip.py`
    -- a bounded watchdog thread so a COM hang is caught and reported, never
    silently blocking the whole eval run.

    Returns `{"status": "ok"|"failed"|"timed_out"|"unavailable", ...}`.
    `"unavailable"` (pywin32 not importable) is a real, reportable capability
    gap, never silently skipped or treated as a pass.
    """
    try:
        import win32com.client
    except ImportError as exc:
        return {"status": "unavailable", "reason": f"pywin32 not importable: {exc}"}

    work_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(docx_path, work_path)

    outcome: dict[str, Any] = {}
    owned: dict[str, int | None] = {"pid": None}
    timeout_requested = threading.Event()

    def _worker() -> None:
        word = None
        doc = None
        try:
            import pythoncom

            pythoncom.CoInitialize()
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            try:
                import win32process

                _thread_id, process_id = win32process.GetWindowThreadProcessId(word.Hwnd)
                owned["pid"] = int(process_id)
            except Exception:
                owned["pid"] = None
            doc = word.Documents.Open(
                str(work_path.resolve()),
                ConfirmConversions=False,
                ReadOnly=False,
                AddToRecentFiles=False,
                Revert=False,
                OpenAndRepair=False,
                NoEncodingDialog=True,
            )
            rng = doc.Content
            rng.Collapse(0)  # wdCollapseEnd
            rng.InsertAfter("\r" + _WORD_ROUNDTRIP_MARKER_TEXT)
            doc.Save()
        except Exception as exc:  # noqa: BLE001
            outcome["exc"] = exc
        finally:
            if not timeout_requested.is_set():
                try:
                    if doc is not None:
                        doc.Close(False)
                except Exception:
                    pass
                try:
                    if word is not None:
                        word.Quit()
                except Exception:
                    pass

    worker_thread = threading.Thread(target=_worker, daemon=True)
    worker_thread.start()
    worker_thread.join(timeout)

    if worker_thread.is_alive():
        timeout_requested.set()
        pid = owned.get("pid")
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        worker_thread.join(_WORD_ROUNDTRIP_CLEANUP_JOIN_SECONDS)
        return {"status": "timed_out", "owned_pid": pid, "cleanup_pending": worker_thread.is_alive()}

    if "exc" in outcome:
        return {"status": "failed", "reason": f"{type(outcome['exc']).__name__}: {outcome['exc']}"}

    if not work_path.exists():
        return {"status": "failed", "reason": "Word COM reported success but the working copy is missing on disk"}

    return {"status": "ok", "marker_text": _WORD_ROUNDTRIP_MARKER_TEXT, "work_path": str(work_path)}


def run_round_trip_editability_check(doc_id: str, docx_path: Path, work_dir: Path,
                                      timeout: float = _WORD_ROUNDTRIP_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Real Word-COM round-trip editability + render-equivalence check for
    one document. Every sub-stage reports its own real status; a Word-COM
    failure at any stage is reported as `status: "failed"/"timed_out"/
    "unavailable"`, never silently treated as a pass. Only native-Meridian
    extraction is diffed (this paper's product-under-test); python-docx/
    Docling round-trip editability is out of scope for this check (they do
    not write DOCX at all in this harness)."""
    doc_work_dir = work_dir / doc_id
    pre_copy = doc_work_dir / f"{doc_id}-pre.docx"
    post_copy = doc_work_dir / f"{doc_id}-post.docx"
    doc_work_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(docx_path, pre_copy)

    round_trip = _word_open_edit_save_round_trip(docx_path, post_copy, timeout=timeout)
    if round_trip["status"] != "ok":
        return {"status": round_trip["status"], "reason": round_trip.get("reason"), "stage": "open_edit_save"}

    try:
        pre_items = extract_native_meridian_items(pre_copy)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "stage": "pre_extract", "reason": f"{type(exc).__name__}: {exc}"}
    try:
        post_items = extract_native_meridian_items(post_copy)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "stage": "post_extract", "reason": f"{type(exc).__name__}: {exc}"}

    editability = graph_scorer.score_round_trip_editability(pre_items, post_items, _WORD_ROUNDTRIP_MARKER_TEXT)

    render_dir = doc_work_dir / "renders"
    pre_receipt = retained_render_receipt(pre_copy, render_dir, timeout=timeout)
    post_receipt = retained_render_receipt(post_copy, render_dir, timeout=timeout)
    both_rendered = pre_receipt.get("status") == "rendered" and post_receipt.get("status") == "rendered"
    render_equivalence = {
        "pre_status": pre_receipt.get("status"),
        "post_status": post_receipt.get("status"),
        "pre_page_count": pre_receipt.get("page_count"),
        "post_page_count": post_receipt.get("page_count"),
        "page_count_equivalent": (
            (pre_receipt.get("page_count") == post_receipt.get("page_count")) if both_rendered else None
        ),
    }

    return {
        "status": "scored",
        "editability": editability,
        "render_equivalence": render_equivalence,
        "pre_copy": str(pre_copy),
        "post_copy": str(post_copy),
    }


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", choices=("smoke", "scale_up", "final", "all"), default="smoke")
    parser.add_argument("--include-docling", action="store_true")
    parser.add_argument("--docling-timeout-seconds", type=float, default=300.0)
    parser.add_argument("--resume-from", type=Path, default=None,
                         help="a previous run's JSONL checkpoint file; already-scored doc_ids are skipped")
    parser.add_argument("--round-trip-check", action="store_true",
                         help="PAPER-S5: run a real Word-COM open-edit-save round trip + render-equivalence "
                              "check on a deterministic sample of documents (slow; requires local Word COM)")
    parser.add_argument("--round-trip-sample", type=int, default=3,
                         help="how many documents (first N of this slice's evaluation_ids, deterministic) "
                              "to run --round-trip-check against")
    parser.add_argument("--round-trip-timeout-seconds", type=float, default=_WORD_ROUNDTRIP_TIMEOUT_SECONDS)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    split = json.loads((GOLD_ROOT / "manifests" / "_split.json").read_text(encoding="utf-8"))
    evaluation_ids = split["smoke"] + split["scale_up"] + split["final"] if args.slice == "all" else split[args.slice]
    summary = {d["doc_id"]: d for d in json.loads((GOLD_ROOT / "manifests" / "_summary.json").read_text(encoding="utf-8"))}

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = DATA_ROOT / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / f"paper30-graph-eval-{args.slice}-{ts}.checkpoint.jsonl"

    already_done: dict[str, dict] = {}
    if args.resume_from and args.resume_from.is_file():
        for line in args.resume_from.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                already_done[row["doc_id"]] = row

    per_doc_results = list(already_done.values())
    checkpoint_fh = checkpoint_path.open("a", encoding="utf-8")
    try:
        for doc_id in evaluation_ids:
            if doc_id in already_done:
                continue
            docx_path = _find_docx_path(doc_id)
            manifest_path = Path(summary[doc_id]["manifest_path"])
            if docx_path is None or not manifest_path.is_file():
                row = {"doc_id": doc_id, "status": "not_run", "reason": "source file or gold manifest missing"}
                per_doc_results.append(row)
                checkpoint_fh.write(json.dumps(row) + "\n")
                checkpoint_fh.flush()
                continue

            gold = extract_gold_items(manifest_path)
            row = {
                "doc_id": doc_id,
                "tier": summary[doc_id].get("tier"),
                "status": "scored",
                "input_docx_sha256": _sha256_file(docx_path),
            }

            try:
                native_items = extract_native_meridian_items(docx_path)
                row["native_meridian"] = graph_scorer.score_document_graph(
                    gold, native_items, candidate_has_para_id=True, candidate_has_omml=True,
                    candidate_has_caption_detection=True,
                )
            except Exception as exc:  # noqa: BLE001
                row["native_meridian"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

            try:
                pydocx_items = extract_python_docx_items(docx_path)
                row["python_docx"] = graph_scorer.score_document_graph(
                    gold, pydocx_items, candidate_has_para_id=False, candidate_has_omml=False,
                )
            except Exception as exc:  # noqa: BLE001
                row["python_docx"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

            if args.include_docling:
                render_pdf = _find_render_pdf(doc_id)
                if render_pdf is None:
                    row["docling_pdf_document_ai"] = {"status": "not_run", "reason": "no retained render PDF"}
                else:
                    docling_items, docling_raw = extract_docling_items(render_pdf, args.docling_timeout_seconds)
                    if docling_items is None:
                        # preserve the real status (crashed/timed_out) and detail, never
                        # collapsed into one ambiguous "crashed_or_timed_out" label
                        row["docling_pdf_document_ai"] = {
                            k: v for k, v in docling_raw.items() if k != "full_text"
                        }
                    else:
                        scored = graph_scorer.score_document_graph(
                            gold, docling_items, candidate_has_para_id=False, candidate_has_omml=False,
                        )
                        scored["docling_raw"] = {k: v for k, v in docling_items["_raw"].items() if k != "full_text"}
                        row["docling_pdf_document_ai"] = scored
            else:
                row["docling_pdf_document_ai"] = {"status": "not_run", "reason": "--include-docling not passed"}

            round_trip_sample_ids = evaluation_ids[: max(args.round_trip_sample, 0)]
            if args.round_trip_check and doc_id in round_trip_sample_ids:
                round_trip_work_dir = DATA_ROOT / "runs" / "paper-s5-round-trip" / f"{args.slice}-{ts}"
                try:
                    row["round_trip_editability"] = run_round_trip_editability_check(
                        doc_id, docx_path, round_trip_work_dir, timeout=args.round_trip_timeout_seconds,
                    )
                except Exception as exc:  # noqa: BLE001
                    row["round_trip_editability"] = {"status": "failed", "stage": "runner",
                                                      "reason": f"{type(exc).__name__}: {exc}"}
            elif args.round_trip_check:
                row["round_trip_editability"] = {"status": "not_run", "reason": "outside --round-trip-sample"}
            else:
                row["round_trip_editability"] = {"status": "not_run", "reason": "--round-trip-check not passed"}

            per_doc_results.append(row)
            checkpoint_fh.write(json.dumps(row, default=str) + "\n")
            checkpoint_fh.flush()
    finally:
        checkpoint_fh.close()

    scored = [d for d in per_doc_results if d.get("status") == "scored"]

    def metric_values(baseline: str, path: tuple[str, ...]) -> list[float]:
        values = []
        for d in scored:
            node = d.get(baseline)
            if not isinstance(node, dict):
                continue
            cur = node
            ok = True
            for key in path:
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    ok = False
                    break
            if ok and isinstance(cur, (int, float)):
                values.append(float(cur))
        return values

    metric_paths = {
        "paragraph_node_f1": ("paragraph_node_prf1", "f1"),
        "paragraph_node_precision": ("paragraph_node_prf1", "precision"),
        "paragraph_node_recall": ("paragraph_node_prf1", "recall"),
        "reading_order_accuracy": ("reading_order", "accuracy"),
        "table_node_f1": ("table_node_prf1", "f1"),
        "table_row_exact_match_rate": ("table_row_exact_match_rate",),
        "equation_node_f1": ("equation_node_prf1", "f1"),
        "equation_semantic_class_accuracy": ("equation_semantic_class_accuracy", "accuracy"),
        "para_id_preservation_rate": ("para_id", "preservation_rate"),
        "caption_node_f1": ("caption_node_prf1", "f1"),
        "anchor_node_f1": ("anchor_node_prf1", "f1"),
    }

    baselines = ["native_meridian", "python_docx"] + (["docling_pdf_document_ai"] if args.include_docling else [])
    aggregate = {}
    for baseline in baselines:
        aggregate[baseline] = {
            name: graph_scorer.bootstrap_ci(metric_values(baseline, path))
            for name, path in metric_paths.items()
        }

    def _get_metric(node, path):
        cur = node
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return None
        return cur if isinstance(cur, (int, float)) else None

    import itertools

    paired_tests = {}
    for baseline_a, baseline_b in itertools.combinations(baselines, 2):
        pair_key = f"{baseline_a}_vs_{baseline_b}"
        paired_tests[pair_key] = {}
        for name, path in metric_paths.items():
            a_vals, b_vals = [], []
            for d in scored:
                a_vals.append(_get_metric(d.get(baseline_a), path))
                b_vals.append(_get_metric(d.get(baseline_b), path))
            paired_tests[pair_key][name] = graph_scorer.paired_permutation_test(a_vals, b_vals)

    report = {
        "run_id": f"paper30-graph-eval-{args.slice}",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "slice": args.slice,
        "document_count": len(evaluation_ids),
        "scored_count": len(scored),
        "corpus_run_manifest_sha256": _sha256_file(GOLD_ROOT / "manifests" / "_run_manifest.json"),
        "environment": {"platform": platform.platform(), "python": platform.python_version(),
                         "docling_included": args.include_docling},
        "deterministic_model_tokens": 0,
        "scope_note": (
            "Real graph-aware scorer (tools/graph_scorer.py): node-level "
            "correspondence + precision/recall/F1 by kind, a non-tautological "
            "reading-order metric, independently re-derived equation "
            "semantic-class accuracy, bootstrap 95% CIs, and paired permutation "
            "significance tests (all pairwise combinations of whichever "
            "baselines were run this slice -- method: paired sign-flip "
            "permutation test, 2000 resamples, fixed seed 20260828, exact "
            "n_paired_documents recorded per metric per pair, never a bare "
            "p-value without those). PAPER-S5: caption/anchor node kinds are "
            "now real, scored metrics (caption: scored for native_meridian via "
            "document_content_tree's own SEQ-field parsing, not_applicable: "
            "no_candidate_adapter for python_docx/Docling; anchor: "
            "not_applicable: no_candidate_adapter for all three -- no candidate "
            "exposes a bookmark-listing API yet). reference/source_binding/"
            "revision node kinds, and references/revises/clones/conflicts_with "
            "edge kinds, are not_applicable: no_gold_ground_truth -- "
            "independent_gold_extractor.py itself produces no ground truth for "
            "these yet, distinct from a candidate-adapter gap. caption_for edge "
            "resolution is not_applicable: no_candidate_adapter (gold resolves "
            "it; no candidate computes an equivalent target yet). Named "
            "remaining scope, not a fabricated comparison."
        ),
        "aggregate_bootstrap_ci": aggregate,
        "paired_permutation_tests": paired_tests,
        "round_trip_check": {
            "requested": args.round_trip_check,
            "sample_size_requested": args.round_trip_sample if args.round_trip_check else 0,
            "results": [
                {"doc_id": d["doc_id"], "result": d.get("round_trip_editability")}
                for d in per_doc_results
                if isinstance(d.get("round_trip_editability"), dict)
                and d["round_trip_editability"].get("status") not in (None, "not_run")
            ],
        },
        "checkpoint_path": str(checkpoint_path),
        "per_document": per_doc_results,
    }

    out_path = out_dir / f"paper30-graph-eval-{args.slice}-{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"{args.slice} slice: {len(evaluation_ids)} documents, {len(scored)} scored")
    print(f"Report: {out_path}")
    for baseline, metrics in aggregate.items():
        print(f"=== {baseline} ===")
        for name, stats in metrics.items():
            print(f"  {name}: mean={stats.get('mean')} ci=[{stats.get('ci_low')}, {stats.get('ci_high')}] n={stats.get('n')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
