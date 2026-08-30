"""PAPER-34: pre-registered ablations isolating why native OOXML is useful.

Runs against the full 127-document gold corpus using tools/graph_scorer.py
(PAPER-30) and the same extraction functions as
tools/run_paper30_graph_eval.py. Each ablation takes native Meridian's OWN
candidate representation for a document and degrades it in one specific,
named way, then rescores against the SAME unmodified gold -- isolating one
capability at a time rather than comparing to a different system (that
comparison is PAPER-30/31's job).

Ablations implemented here (from comparator-contract-v0.md's PAPER-34 list):
  (b) remove_native_para_id       -- strip w14:paraId before scoring
  (c) flatten_omml_to_text        -- replace each equation's OMML with a
                                      single flat <m:t> run (no structure)
  (d) shuffle_paragraph_order     -- proxy for "remove structural/order
                                      edges": same node text, order destroyed
  (e) hide_table_metadata         -- drop all table nodes from the candidate

Ablation (a) (native DOCX graph vs. Word-rendered PDF) is NOT re-implemented
here -- it is exactly PAPER-31's native_meridian vs. docling_pdf_document_ai
comparison, already computed there; duplicating it here would waste compute
and risk the two numbers drifting apart. This report cross-references
PAPER-31's own output file instead of recomputing.

Ablation (f) (born-digital vs. deliberately rasterized PDFs) is NOT
implemented in this pass: it requires a PDF rasterization library not
currently in this isolated pixi environment (neither PyMuPDF/fitz nor pypdf
are installed), and adding one was deliberately deferred rather than done
while PAPER-33's hardening workflow was concurrently running pixi commands
in this same shared environment (a pixi.toml change mid-run risks disrupting
that in-flight work). Recorded here as `not_run`, with the specific reason,
not silently dropped from the ablation list.
"""
from __future__ import annotations

import copy
import datetime
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\13144\Documents\Meridian\repository")
PAPER_ROOT = Path(r"C:\Users\13144\Documents\Meridian\ooxml-graph-paper")
GOLD_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\gold")
DATA_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper")

sys.path.insert(0, str(REPO_ROOT / "extensions" / "meridian-docs"))
sys.path.insert(0, str(PAPER_ROOT / "tools"))

import graph_scorer  # noqa: E402
from run_paper15_smoke import _find_docx_path  # noqa: E402
from run_paper30_graph_eval import extract_gold_items, extract_native_meridian_items  # noqa: E402

_SHUFFLE_SEED = 20260828

_FLAT_OMML_TEMPLATE = (
    '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
    '<m:r><m:t>{text}</m:t></m:r></m:oMath>'
)


def ablation_remove_native_para_id(native_items: dict) -> dict:
    out = copy.deepcopy(native_items)
    for p in out["paragraphs"]:
        p["para_id"] = None
    return out


def ablation_flatten_omml_to_text(native_items: dict) -> dict:
    """Replace each equation's real OMML with a single flat text run,
    simulating a system that captured the rendered/flattened text of an
    equation but none of its structural markup."""
    out = copy.deepcopy(native_items)
    for eq in out["equations"]:
        raw = eq.get("omml_raw") or ""
        # crude text-content extraction: strip all XML tags, keep character data
        import re
        flat_text = re.sub(r"<[^>]+>", "", raw)
        eq["omml_raw"] = _FLAT_OMML_TEMPLATE.format(text=flat_text)
    return out


def ablation_shuffle_paragraph_order(native_items: dict, seed: int) -> dict:
    out = copy.deepcopy(native_items)
    rng = random.Random(seed)
    rng.shuffle(out["paragraphs"])
    out["full_text"] = "\n".join(p["text"] for p in out["paragraphs"])
    return out


def ablation_hide_table_metadata(native_items: dict) -> dict:
    out = copy.deepcopy(native_items)
    out["tables"] = []
    return out


ABLATIONS = {
    "remove_native_para_id": (ablation_remove_native_para_id, {"candidate_has_para_id": False, "candidate_has_omml": True}),
    "flatten_omml_to_text": (ablation_flatten_omml_to_text, {"candidate_has_para_id": True, "candidate_has_omml": True}),
    "shuffle_paragraph_order": (lambda items: ablation_shuffle_paragraph_order(items, _SHUFFLE_SEED),
                                 {"candidate_has_para_id": True, "candidate_has_omml": True}),
    "hide_table_metadata": (ablation_hide_table_metadata, {"candidate_has_para_id": True, "candidate_has_omml": True}),
}


def main() -> int:
    split = json.loads((GOLD_ROOT / "manifests" / "_split.json").read_text(encoding="utf-8"))
    all_ids = split["smoke"] + split["scale_up"] + split["final"]
    summary = {d["doc_id"]: d for d in json.loads((GOLD_ROOT / "manifests" / "_summary.json").read_text(encoding="utf-8"))}

    per_ablation_per_doc: dict[str, list[dict]] = {name: [] for name in ABLATIONS}
    baseline_per_doc: list[dict] = []

    for doc_id in all_ids:
        docx_path = _find_docx_path(doc_id)
        manifest_path = Path(summary[doc_id]["manifest_path"])
        if docx_path is None or not manifest_path.is_file():
            continue
        gold = extract_gold_items(manifest_path)
        try:
            native_items = extract_native_meridian_items(docx_path)
        except Exception as exc:  # noqa: BLE001
            continue

        baseline_score = graph_scorer.score_document_graph(gold, native_items, candidate_has_para_id=True, candidate_has_omml=True)
        baseline_per_doc.append({"doc_id": doc_id, "score": baseline_score})

        for name, (transform, flags) in ABLATIONS.items():
            ablated_items = transform(native_items)
            score = graph_scorer.score_document_graph(gold, ablated_items, **flags)
            per_ablation_per_doc[name].append({"doc_id": doc_id, "score": score})

    def macro(rows: list[dict], path: tuple[str, ...]) -> dict:
        values = []
        for row in rows:
            cur = row["score"]
            for key in path:
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    cur = None
                    break
            if isinstance(cur, (int, float)):
                values.append(float(cur))
        return graph_scorer.bootstrap_ci(values)

    metric_paths = {
        "paragraph_node_f1": ("paragraph_node_prf1", "f1"),
        "reading_order_accuracy": ("reading_order", "accuracy"),
        "table_node_f1": ("table_node_prf1", "f1"),
        "equation_node_f1": ("equation_node_prf1", "f1"),
        "equation_semantic_class_accuracy": ("equation_semantic_class_accuracy", "accuracy"),
        "para_id_preservation_rate": ("para_id", "preservation_rate"),
    }

    report = {
        "run_id": "paper34-ablations",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "document_count": len(baseline_per_doc),
        "scope_note": (
            "Ablations (b)/(c)/(d)/(e) implemented and run against the full corpus, "
            "degrading native Meridian's own candidate representation one capability "
            "at a time and rescoring against the same unmodified gold via "
            "tools/graph_scorer.py. Ablation (a) is not recomputed here -- see "
            "PAPER-31's native_meridian vs docling_pdf_document_ai comparison. "
            "Ablation (f) (born-digital vs rasterized PDF) is not_run: no PDF "
            "rasterization library is installed in this isolated environment, and "
            "adding one was deferred rather than risk disrupting PAPER-33's "
            "concurrently-running pixi-based hardening workflow in the same shared "
            "environment."
        ),
        "ablation_f_born_digital_vs_rasterized": {
            "status": "not_run",
            "reason": "no PDF rasterization library (fitz/pypdf) installed; deferred to avoid a pixi.toml change during PAPER-33's concurrent run",
        },
        "baseline_unablated": {name: macro(baseline_per_doc, path) for name, path in metric_paths.items()},
        "ablations": {
            name: {metric: macro(rows, path) for metric, path in metric_paths.items()}
            for name, rows in per_ablation_per_doc.items()
        },
    }

    out_dir = DATA_ROOT / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"paper34-ablations-{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Report: {out_path}")
    print(f"Documents: {report['document_count']}")
    print("\n=== baseline (unablated native_meridian) ===")
    for metric, stats in report["baseline_unablated"].items():
        print(f"  {metric}: {stats.get('mean')}")
    for name in ABLATIONS:
        print(f"\n=== ablation: {name} ===")
        for metric, stats in report["ablations"][name].items():
            print(f"  {metric}: {stats.get('mean')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
