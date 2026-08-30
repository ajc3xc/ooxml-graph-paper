"""PAPER-15: first real, honestly-scoped Track A comparison on the smoke slice.

Per comparator-contract-v0.md Section 4 ("First smoke slice... small, deterministic
manifest") -- this is a FIRST ATTEMPT, not the full preregistered comparison.
Explicit, honest scope limitations, not silently omitted:

- Only 2 of 4 Track A baseline families run: (1) native Meridian OOXML/OMML extraction,
  (2) generic DOCX extraction via python-docx, "structure deliberately normalized to
  the common schema" per the contract's own wording for baseline family 2. Pandoc
  (conversion-mediated, family 3) and controlled ablations (family 4) are NOT run here
  -- Pandoc is not installed on this host. Per Section 5's comparability rule ("missing
  ... produces an explicit not_run/unknown row, not a silently omitted baseline"), those
  rows are recorded as not_run below, not left out.
- Metrics are a SIMPLIFIED, count/overlap-based proxy for the contract's full node
  precision/recall/F1-by-type spec, not a complete bipartite node-correspondence /
  graph-edit-distance scorer (which does not exist yet as of this run). This is stated
  explicitly in the report, not presented as the complete metric suite.
- Render/operational correctness (Track C) and efficiency/cost metrics are NOT computed
  here -- this script covers structural + content correctness only.

Usage: pixi run python tools/run_paper15_smoke.py
Writes: E:\\MeridianData\\ooxml-graph-paper\\manifests\\paper15-smoke-run-<timestamp>.json
"""
from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import platform
import shutil
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\13144\Documents\Meridian\repository")
PAPER_ROOT = Path(r"C:\Users\13144\Documents\Meridian\ooxml-graph-paper")
GOLD_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\gold")
DATA_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper")

sys.path.insert(0, str(REPO_ROOT / "extensions" / "meridian-docs"))
sys.path.insert(0, str(PAPER_ROOT / "tools"))


def _find_docx_path(doc_id: str) -> Path | None:
    for tier_dir in ("tier1", "tier2", "tier3"):
        p = GOLD_ROOT / tier_dir / f"{doc_id}.docx"
        if p.is_file():
            return p
    return None


def _text_f1(gold_text: str, cand_text: str) -> dict:
    gold_tokens = gold_text.split()
    cand_tokens = cand_text.split()
    if not gold_tokens and not cand_tokens:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not gold_tokens or not cand_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    matcher = difflib.SequenceMatcher(a=gold_tokens, b=cand_tokens, autojunk=False)
    matches = sum(block.size for block in matcher.get_matching_blocks())
    precision = matches / len(cand_tokens)
    recall = matches / len(gold_tokens)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _count_recall(gold_n: int, cand_n: int) -> float | None:
    if gold_n == 0:
        return None  # undefined, not zero -- avoid implying a false failure on a doc with no instances
    return min(cand_n, gold_n) / gold_n  # capped at 1.0 -- over-extraction is a separate, unpenalized-here concern


def _conditional_para_id_preservation(gold_ids: list[str | None], cand_ids: list[str | None]) -> float | None:
    """Preservation among paragraphs whose source actually has a native ID.

    Real DOCX files may legally omit w14:paraId. A synthetic fallback ID is
    useful for traversal but is not evidence of preservation, so missing gold
    IDs are excluded from this denominator rather than scored as failures.
    """
    expected = [idx for idx, value in enumerate(gold_ids) if value]
    if not expected:
        return None
    preserved = sum(
        idx < len(cand_ids) and cand_ids[idx] == gold_ids[idx]
        for idx in expected
    )
    return preserved / len(expected)


def extract_native_meridian(docx_path: Path) -> dict:
    from meridian_docs import docs_intel
    from meridian_docs._vendored_content_tree import document_content_tree

    tree = document_content_tree(str(docx_path))
    paragraphs = [b for b in tree["blocks"] if b["kind"] in ("paragraph", "heading")]
    tables = [b for b in tree["blocks"] if b["kind"] == "table"]
    equations = docs_intel.parse_docx_equations_local(str(docx_path))
    full_text = "\n".join(p["text"] for p in paragraphs)
    para_ids = [p["para_id"] for p in paragraphs]
    native_para_ids = sum(1 for para_id in para_ids if para_id and not para_id.startswith(("p", "sp")))
    return {
        "paragraph_count": len(paragraphs),
        "table_count": len(tables),
        "table_row_total": sum(t["row_count"] for t in tables),
        "table_col_total": sum(t["col_count"] for t in tables),
        "equation_count": len(equations),
        "full_text": full_text,
        "native_para_id_count": native_para_ids,
        "para_ids": para_ids,
    }


def extract_python_docx(docx_path: Path) -> dict:
    import docx

    document = docx.Document(str(docx_path))
    paragraphs = list(document.paragraphs)
    tables = list(document.tables)
    full_text = "\n".join(p.text for p in paragraphs)
    # python-docx has zero OMML/equation API surface (PAPER-14 finding, re-confirmed
    # structurally here rather than re-cited) and mints no w14:paraId at all.
    return {
        "paragraph_count": len(paragraphs),
        "table_count": len(tables),
        "table_row_total": sum(len(t.rows) for t in tables),
        "table_col_total": sum(len(t.columns) for t in tables),
        "equation_count": 0,
        "full_text": full_text,
        "native_para_id_count": 0,
        "para_ids": [None] * len(paragraphs),
        "para_id_preservation_rate": 0.0,
    }


def score_baseline(gold: dict, cand: dict, timing_s: float, peak_python_allocated_bytes: int) -> dict:
    text_score = _text_f1(gold["full_text"], cand["full_text"])
    return {
        "paragraph_count_recall": _count_recall(gold["paragraph_count"], cand["paragraph_count"]),
        "table_count_recall": _count_recall(gold["table_count"], cand["table_count"]),
        "table_row_recall": _count_recall(gold["table_row_total"], cand["table_row_total"]),
        "equation_count_recall": _count_recall(gold["equation_count"], cand["equation_count"]),
        "text_token_f1": text_score["f1"],
        "text_token_precision": text_score["precision"],
        "text_token_recall": text_score["recall"],
        "para_id_preservation_rate": _conditional_para_id_preservation(
            gold["top_level_para_ids"], cand.get("para_ids", []),
        ),
        "gold_para_id_coverage": (
            sum(bool(value) for value in gold["top_level_para_ids"])
            / len(gold["top_level_para_ids"])
            if gold["top_level_para_ids"] else None
        ),
        "wall_time_seconds": timing_s,
        # tracemalloc measures Python allocations, not process RSS. Keep the
        # distinction explicit so the paper never reports this proxy as RSS.
        "peak_python_allocated_bytes": peak_python_allocated_bytes,
        "raw_counts": {k: v for k, v in cand.items() if k not in ("full_text", "para_ids")},
    }


def extract_gold_reference(manifest_path: Path) -> dict:
    """Both baselines (document_content_tree's top-level body walk, and python-docx's
    .paragraphs property) only enumerate TOP-LEVEL body paragraphs -- neither descends
    into table cells to produce separate paragraph records (their text is still captured
    as part of the table's row/cell text, just not double-counted as paragraph nodes).
    The gold graph, by contrast, legitimately models a cell's paragraph as a real
    'paragraph' node with its own containment edge from a 'table_cell' node (per
    graph-gold-schema-v0.md). Comparing gold's inclusive total against either baseline's
    top-level-only count would show a large, spurious 'recall gap' that reflects a
    counting-scope mismatch, not a real extraction failure -- confirmed by inspection
    (one smoke document: 439 gold paragraph nodes, 433 of them cell-nested). Report both
    counts; use top-level-only for the recall comparison so the two sides are counting
    the same thing."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gold_record = manifest["gold_record"]
    nodes = gold_record["nodes"]
    edges = gold_record["edges"]
    cell_ids = {n["id"] for n in nodes if n["kind"] == "table_cell"}
    paragraph_like = [n for n in nodes if n["kind"] in ("paragraph", "caption")]
    para_ids = {n["id"] for n in paragraph_like}
    nested_para_ids = {e["dst"] for e in edges if e["kind"] == "contains" and e["src"] in cell_ids and e["dst"] in para_ids}
    top_level_paragraphs = [n for n in paragraph_like if n["id"] not in nested_para_ids]
    top_level_para_ids = [n.get("attrs", {}).get("w14_para_id") for n in top_level_paragraphs]
    tables = [n for n in nodes if n["kind"] == "table"]
    table_rows = [n for n in nodes if n["kind"] == "table_row"]
    equations = [n for n in nodes if n["kind"] == "equation"]
    full_text = gold_record["facts"]["text"]
    return {
        "paragraph_count": len(top_level_paragraphs),
        "top_level_para_ids": top_level_para_ids,
        "native_para_id_count": sum(bool(value) for value in top_level_para_ids),
        "paragraph_count_including_table_cells": len(paragraph_like),
        "table_count": len(tables),
        "table_row_total": len(table_rows),
        "table_col_total": sum(len(g) for g in gold_record["facts"]["table_grid"]),
        "equation_count": len(equations),
        "full_text": full_text,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_render_pdf(doc_id: str) -> Path | None:
    p = DATA_ROOT / "renders" / "gold" / doc_id / f"{doc_id}.pdf"
    return p if p.is_file() else None


def _run_docling_subprocess(pdf_path: Path, timeout_s: float) -> dict:
    """Run tools/docling_convert_one.py as an isolated subprocess for one PDF.

    PAPER-28's probe found `do_formula_enrichment=True` reliably crashes the
    whole process with a native panic, not a catchable Python exception --
    subprocess isolation means one document's crash costs one row, not the
    whole run. TableFormerMode.FAST (not the ACCURATE default) is used inside
    the worker: ACCURATE measured ~234s for one dense page versus ~28s under
    FAST for the same page, and a naive full-corpus ACCURATE run would not
    complete in any reasonable session time budget (859 total corpus pages).
    """
    import subprocess
    import tempfile

    try:
        import psutil
    except ImportError:
        psutil = None

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "result.json"
        cmd = [sys.executable, str(PAPER_ROOT / "tools" / "docling_convert_one.py"), str(pdf_path), str(out_path)]
        t0 = time.perf_counter()
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        ps_proc = None
        if psutil is not None:
            try:
                ps_proc = psutil.Process(proc.pid)
            except psutil.NoSuchProcess:
                ps_proc = None
        peak_rss_bytes = 0
        timed_out = False
        while True:
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if ps_proc is not None:
                    try:
                        peak_rss_bytes = max(peak_rss_bytes, ps_proc.memory_info().rss)
                    except Exception:  # noqa: BLE001 -- process may have just exited
                        pass
                if time.perf_counter() - t0 > timeout_s:
                    proc.kill()
                    proc.wait()
                    timed_out = True
                    break
        elapsed = time.perf_counter() - t0
        _, stderr = proc.communicate()

        if timed_out:
            return {
                "status": "timed_out",
                "wall_time_seconds_subprocess_total": elapsed,
                "peak_rss_bytes": peak_rss_bytes,
                "reason": f"exceeded {timeout_s}s subprocess timeout",
            }
        if proc.returncode != 0 or not out_path.exists():
            return {
                "status": "crashed",
                "wall_time_seconds_subprocess_total": elapsed,
                "peak_rss_bytes": peak_rss_bytes,
                "returncode": proc.returncode,
                "stderr_tail": (stderr or "")[-2000:],
            }
        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "crashed",
                "wall_time_seconds_subprocess_total": elapsed,
                "peak_rss_bytes": peak_rss_bytes,
                "reason": f"unreadable worker output JSON: {type(exc).__name__}: {exc}",
            }
        if payload.get("conversion_status") == "EXCEPTION":
            return {
                "status": "crashed",
                "wall_time_seconds_subprocess_total": elapsed,
                "peak_rss_bytes": peak_rss_bytes,
                "error": payload.get("error"),
            }
        payload["status"] = "scored"
        payload["peak_rss_bytes"] = peak_rss_bytes
        payload["wall_time_seconds_subprocess_total"] = elapsed
        return payload


def score_docling_baseline(gold: dict, cand: dict) -> dict:
    """Score Docling's rendered-PDF document-AI output against gold.

    Deliberately does NOT compute para_id_preservation_rate: per
    comparator-contract-v0.md Section 7.3, native paragraph identity cannot
    be inferred from a PDF-only reader by construction, so it is recorded as
    not_applicable rather than scored as a failure or silently omitted.
    """
    text_score = _text_f1(gold["full_text"], cand.get("full_text", ""))
    return {
        "table_count_recall": _count_recall(gold["table_count"], cand.get("table_count", 0)),
        "table_row_recall": _count_recall(gold["table_row_total"], cand.get("table_row_total", 0)),
        "equation_count_recall": _count_recall(gold["equation_count"], cand.get("equation_count", 0)),
        "text_token_f1": text_score["f1"],
        "text_token_precision": text_score["precision"],
        "text_token_recall": text_score["recall"],
        "para_id_preservation_rate": None,
        "para_id_status": "not_applicable",
        "para_id_not_applicable_reason": (
            "rendered PDF input has no native paragraph-identity concept "
            "(comparator-contract-v0.md Section 7.3) -- excluded from the "
            "denominator, not scored as a failure"
        ),
        "wall_time_seconds": cand.get("wall_time_seconds"),
        "wall_time_seconds_subprocess_total": cand.get("wall_time_seconds_subprocess_total"),
        "peak_rss_bytes": cand.get("peak_rss_bytes"),
        "page_count": cand.get("page_count"),
        "pipeline_config": cand.get("pipeline_config"),
        "raw_counts": {k: v for k, v in cand.items() if k not in ("full_text", "pipeline_config")},
    }


def _parse_args() -> object:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slice", choices=("smoke", "scale_up", "final", "all"), default="smoke",
        help="evaluation slice from gold/manifests/_split.json (default: smoke)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="optional report path; defaults to E:/.../manifests with a timestamp",
    )
    parser.add_argument(
        "--include-docling", action="store_true",
        help=(
            "run the Docling rendered-PDF document-AI baseline (PAPER-28/31). "
            "Opt-in: even at TableFormerMode.FAST this can take tens of "
            "seconds per page, so a full-corpus run can take hours."
        ),
    )
    parser.add_argument(
        "--docling-timeout-seconds", type=float, default=300.0,
        help="per-document subprocess timeout for the Docling baseline (default: 300s)",
    )
    parser.add_argument(
        "--resume-from", type=Path, default=None,
        help=(
            "a previous run's .checkpoint.jsonl file; already-completed doc_ids "
            "are loaded from it and skipped. Recommended whenever --include-docling "
            "is used, since a single Docling conversion can take minutes and an "
            "interrupted run would otherwise lose all prior progress."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    split = json.loads((GOLD_ROOT / "manifests" / "_split.json").read_text(encoding="utf-8"))
    if args.slice == "all":
        evaluation_ids = split["smoke"] + split["scale_up"] + split["final"]
    else:
        evaluation_ids = split[args.slice]
    summary = {d["doc_id"]: d for d in json.loads((GOLD_ROOT / "manifests" / "_summary.json").read_text(encoding="utf-8"))}

    out_dir = DATA_ROOT / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    checkpoint_path = out_dir / f"paper15-{args.slice}-run-{ts}.checkpoint.jsonl"

    already_done: dict[str, dict] = {}
    if args.resume_from and args.resume_from.is_file():
        for line in args.resume_from.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                already_done[row["doc_id"]] = row

    per_doc_results = list(already_done.values())
    checkpoint_fh = checkpoint_path.open("a", encoding="utf-8")
    try:
        _run_all_documents(args, evaluation_ids, summary, already_done, per_doc_results, checkpoint_fh)
    finally:
        checkpoint_fh.close()
    return _finalize_report(args, evaluation_ids, per_doc_results, checkpoint_path)


def _run_all_documents(args, evaluation_ids, summary, already_done, per_doc_results, checkpoint_fh) -> None:
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

        gold = extract_gold_reference(manifest_path)

        doc_result = {
            "doc_id": doc_id,
            "tier": summary[doc_id].get("tier"),
            "status": "scored",
            "input_docx_sha256": _sha256_file(docx_path),
            "gold_manifest_sha256": _sha256_file(manifest_path),
            "gold_reference_counts": {k: v for k, v in gold.items() if k != "full_text"},
        }

        for baseline_name, extract_fn in (("native_meridian", extract_native_meridian), ("python_docx", extract_python_docx)):
            try:
                tracemalloc.start()
                t0 = time.perf_counter()
                cand = extract_fn(docx_path)
                elapsed = time.perf_counter() - t0
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                doc_result[baseline_name] = score_baseline(gold, cand, elapsed, peak)
            except Exception as exc:  # noqa: BLE001 -- a baseline crashing on a document is itself a real, reportable result
                if tracemalloc.is_tracing():
                    tracemalloc.stop()
                doc_result[baseline_name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

        # Pandoc / LibreOffice / controlled ablations: explicit not_run, never silently omitted.
        pandoc = shutil.which("pandoc")
        office = shutil.which("soffice") or shutil.which("libreoffice")
        doc_result["pandoc_conversion_mediated"] = {
            "status": "not_run",
            "reason": "Pandoc is not installed on this host" if not pandoc else "not wired into this runner",
            "executable": pandoc,
        }
        doc_result["libreoffice_conversion"] = {
            "status": "not_run",
            "reason": "LibreOffice is not installed on this host" if not office else "not wired into this runner",
            "executable": office,
        }
        if args.include_docling:
            render_pdf = _find_render_pdf(doc_id)
            if render_pdf is None:
                doc_result["docling_pdf_document_ai"] = {
                    "status": "not_run",
                    "reason": "no retained Word-COM render PDF found for this doc_id",
                }
            else:
                docling_raw = _run_docling_subprocess(render_pdf, timeout_s=args.docling_timeout_seconds)
                if docling_raw.get("status") == "scored":
                    scored_result = score_docling_baseline(gold, docling_raw)
                    scored_result["status"] = "scored"
                    scored_result["render_pdf_sha256"] = _sha256_file(render_pdf)
                    doc_result["docling_pdf_document_ai"] = scored_result
                else:
                    doc_result["docling_pdf_document_ai"] = docling_raw
        else:
            doc_result["docling_pdf_document_ai"] = {
                "status": "not_run",
                "reason": "--include-docling not passed for this run",
            }
        doc_result["controlled_ablations"] = {"status": "not_run", "reason": "not built in this runner"}

        per_doc_results.append(doc_result)
        checkpoint_fh.write(json.dumps(doc_result, default=str) + "\n")
        checkpoint_fh.flush()


def _finalize_report(args, evaluation_ids, per_doc_results, checkpoint_path: Path) -> int:
    scored = [d for d in per_doc_results if d["status"] == "scored"]

    def macro_avg(baseline: str, metric: str) -> float | None:
        vals = [d[baseline][metric] for d in scored if isinstance(d.get(baseline), dict) and d[baseline].get(metric) is not None]
        return sum(vals) / len(vals) if vals else None

    baseline_metrics = {
        "native_meridian": ("paragraph_count_recall", "table_count_recall", "table_row_recall",
                            "equation_count_recall", "text_token_f1", "para_id_preservation_rate",
                            "wall_time_seconds", "peak_python_allocated_bytes"),
        "python_docx": ("paragraph_count_recall", "table_count_recall", "table_row_recall",
                        "equation_count_recall", "text_token_f1", "para_id_preservation_rate",
                        "wall_time_seconds", "peak_python_allocated_bytes"),
        "docling_pdf_document_ai": ("table_count_recall", "table_row_recall", "equation_count_recall",
                                    "text_token_f1", "wall_time_seconds",
                                    "wall_time_seconds_subprocess_total", "peak_rss_bytes"),
    }
    aggregate = {}
    for baseline, metrics in baseline_metrics.items():
        aggregate[baseline] = {metric: macro_avg(baseline, metric) for metric in metrics}

    evaluable_id_docs = {
        baseline: sum(
            1 for d in scored
            if d.get(baseline, {}).get("para_id_preservation_rate") is not None
        )
        for baseline in ("native_meridian", "python_docx")
    }

    baseline_status = {}
    for baseline in ("native_meridian", "python_docx", "pandoc_conversion_mediated",
                     "libreoffice_conversion", "docling_pdf_document_ai", "controlled_ablations"):
        counts = {}
        for row in per_doc_results:
            status = row.get(baseline, {}).get("status", "scored") if isinstance(row.get(baseline), dict) else "unknown"
            counts[status] = counts.get(status, 0) + 1
        baseline_status[baseline] = counts

    report = {
        "run_id": f"paper15-{args.slice}-structural-pass-1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "slice": args.slice,
        "document_count": len(evaluation_ids),
        "scored_count": len(scored),
        "corpus_run_manifest_sha256": _sha256_file(GOLD_ROOT / "manifests" / "_run_manifest.json"),
        "baseline_status_counts": baseline_status,
        "para_id_evaluable_document_counts": evaluable_id_docs,
        "deterministic_model_tokens": 0,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "python_docx_version": __import__("docx").__version__,
            "pandoc_executable": shutil.which("pandoc"),
            "libreoffice_executable": shutil.which("soffice") or shutil.which("libreoffice"),
            "docling_included": args.include_docling,
            "docling_config": (
                {"table_structure_mode": "FAST", "do_formula_enrichment": False,
                 "isolation": "one subprocess per document via tools/docling_convert_one.py",
                 "timeout_seconds": args.docling_timeout_seconds}
                if args.include_docling else None
            ),
        },
        "scope_note": (
            f"Structural pass on the {args.slice} slice ({len(evaluation_ids)} documents), per "
            "comparator-contract-v0.md Section 4. Native Meridian and python-docx are run; "
            "Pandoc, LibreOffice, and controlled ablations are explicitly recorded as not_run "
            "where unavailable or unwired. Docling (rendered-PDF document-AI track, per "
            "comparator-contract-v0.md Section 7) is run only when --include-docling is passed, "
            f"given its per-page cost (this run: {'included' if args.include_docling else 'not_run, --include-docling not passed'}). "
            "Metrics remain a simplified count/overlap proxy, not the contract's complete node "
            "precision/recall/F1 and graph-edit-distance scorer (that is PAPER-30's job). This is "
            "not the final native-vs-AI paper benchmark."
        ),
        "checkpoint_path": str(checkpoint_path),
        "macro_aggregate": aggregate,
        "per_document": per_doc_results,
    }

    out_dir = DATA_ROOT / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"paper15-smoke-run-{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"{args.slice} slice: {len(evaluation_ids)} documents, {len(scored)} scored")
    print(f"Report: {out_path}")
    print()
    for baseline, metrics in aggregate.items():
        print(f"=== {baseline} (macro avg across scored smoke docs) ===")
        for k, v in metrics.items():
            print(f"  {k}: {v}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
