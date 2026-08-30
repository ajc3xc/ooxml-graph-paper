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

Usage:
  pixi run python tools/run_paper30_graph_eval.py --slice smoke
  pixi run python tools/run_paper30_graph_eval.py --slice all --include-docling
"""
from __future__ import annotations

import datetime
import hashlib
import json
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\13144\Documents\Meridian\repository")
PAPER_ROOT = Path(r"C:\Users\13144\Documents\Meridian\ooxml-graph-paper")
GOLD_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\gold")
DATA_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper")

sys.path.insert(0, str(REPO_ROOT / "extensions" / "meridian-docs"))
sys.path.insert(0, str(PAPER_ROOT / "tools"))

import graph_scorer  # noqa: E402
from run_paper15_smoke import _find_docx_path, _find_render_pdf, _run_docling_subprocess  # noqa: E402


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
        "full_text": gold_record["facts"]["text"],
    }


def extract_native_meridian_items(docx_path: Path) -> dict:
    from meridian_docs import docs_intel
    from meridian_docs._vendored_content_tree import document_content_tree

    tree = document_content_tree(str(docx_path))
    blocks = tree["blocks"]
    paragraphs = [
        {"text": b["text"], "para_id": b["para_id"] if not b["para_id"].startswith(("p", "sp")) else None}
        for b in blocks if b["kind"] in ("paragraph", "heading")
    ]
    tables = [{"row_count": b["row_count"], "col_count": b["col_count"]} for b in blocks if b["kind"] == "table"]
    raw_equations = docs_intel.parse_docx_equations_local(str(docx_path))
    equations = [{"omml_raw": e.get("omml_raw")} for e in sorted(raw_equations, key=lambda e: e.get("ordinal", 0))]
    full_text = "\n".join(p["text"] for p in paragraphs)
    return {"paragraphs": paragraphs, "tables": tables, "equations": equations, "full_text": full_text}


def extract_python_docx_items(docx_path: Path) -> dict:
    import docx

    document = docx.Document(str(docx_path))
    paragraphs = [{"text": p.text, "para_id": None} for p in document.paragraphs]
    tables = [{"row_count": len(t.rows), "col_count": len(t.columns)} for t in document.tables]
    full_text = "\n".join(p["text"] for p in paragraphs)
    # python-docx has zero OMML/equation API surface (PAPER-14 finding).
    return {"paragraphs": paragraphs, "tables": tables, "equations": [], "full_text": full_text}


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
    items = {"paragraphs": paragraphs, "tables": tables, "equations": equations, "full_text": full_text,
              "_raw": raw}
    return items, raw


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", choices=("smoke", "scale_up", "final", "all"), default="smoke")
    parser.add_argument("--include-docling", action="store_true")
    parser.add_argument("--docling-timeout-seconds", type=float, default=300.0)
    parser.add_argument("--resume-from", type=Path, default=None,
                         help="a previous run's JSONL checkpoint file; already-scored doc_ids are skipped")
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
            "p-value without those). caption/anchor/reference/revision/"
            "source_binding node kinds are explicitly not_applicable: "
            "no_candidate_adapter extracts them yet -- named remaining scope, "
            "not a fabricated comparison."
        ),
        "aggregate_bootstrap_ci": aggregate,
        "paired_permutation_tests": paired_tests,
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
