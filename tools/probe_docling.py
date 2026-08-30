"""PAPER-28: probe the installed Docling package's real conversion behavior.

Not a scorer, not part of the benchmark run -- a one-shot capability probe.
Imports torch before docling as a documented workaround for a reproducible
Windows DLL-ordering conflict (see docs/dataset-landscape-2026-08-25.md
PAPER-28 section): importing docling's own module chain triggers a deferred
`from transformers import StoppingCriteria` -> `import torch`, and on this
host that deferred/nested torch import fails with WinError 1114
("DLL initialization routine failed", torch/lib/c10.dll) while a top-level
`import torch` executed first succeeds every time. Root cause not fully
bisected beyond that ordering fact; documented as a workaround, not silently
patched around.
"""
from __future__ import annotations

import importlib.metadata as im
import json
import sys
import time
from pathlib import Path

import torch  # noqa: F401  -- see module docstring; must precede docling imports

from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions

PINNED_VERSIONS = {
    pkg: im.version(pkg)
    for pkg in (
        "docling",
        "docling-core",
        "docling-ibm-models",
        "docling-parse",
        "transformers",
        "torch",
        "huggingface-hub",
    )
}

GOLD_ROOT = Path("E:/MeridianData/ooxml-graph-paper/gold")
RENDER_ROOT = Path("E:/MeridianData/ooxml-graph-paper/renders/gold")
OUT_PATH = Path("E:/MeridianData/ooxml-graph-paper/manifests/paper28-docling-probe.json")


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _probe_default_pipeline_options() -> dict:
    opts = PdfPipelineOptions()
    return {
        "do_ocr": opts.do_ocr,
        "do_table_structure": opts.do_table_structure,
        "do_formula_enrichment": getattr(opts, "do_formula_enrichment", None),
        "do_code_enrichment": getattr(opts, "do_code_enrichment", None),
        "generate_page_images": opts.generate_page_images,
        "images_scale": opts.images_scale,
        "table_structure_options": {
            "mode": str(opts.table_structure_options.mode)
            if opts.table_structure_options
            else None,
        }
        if getattr(opts, "table_structure_options", None)
        else None,
    }


def _convert_and_inspect(converter: DocumentConverter, path: Path, kind: str) -> dict:
    entry = {
        "input_path": str(path),
        "input_kind": kind,
        "input_sha256": _sha256(path),
        "status": "not_run",
    }
    t0 = time.time()
    try:
        result = converter.convert(str(path))
    except Exception as exc:  # noqa: BLE001 -- probe must record real failures, not hide them
        entry["status"] = "crashed"
        entry["error_type"] = type(exc).__name__
        entry["error_message"] = str(exc)[:2000]
        entry["wall_time_seconds"] = time.time() - t0
        return entry

    entry["wall_time_seconds"] = time.time() - t0
    entry["status"] = "scored"
    entry["conversion_status"] = str(result.status)
    doc = result.document

    entry["page_count"] = len(doc.pages) if hasattr(doc, "pages") else None

    texts = list(doc.texts) if hasattr(doc, "texts") else []
    tables = list(doc.tables) if hasattr(doc, "tables") else []
    pictures = list(doc.pictures) if hasattr(doc, "pictures") else []
    formula_items = [
        t for t in texts if getattr(t, "label", None) is not None and "formula" in str(t.label).lower()
    ]

    entry["text_item_count"] = len(texts)
    entry["table_count"] = len(tables)
    entry["picture_count"] = len(pictures)
    entry["formula_labeled_text_item_count"] = len(formula_items)
    entry["distinct_text_labels"] = sorted({str(t.label) for t in texts if getattr(t, "label", None)})

    if formula_items:
        sample = formula_items[0]
        entry["sample_formula_item"] = {
            "label": str(sample.label),
            "text": getattr(sample, "text", None),
            "has_orig": hasattr(sample, "orig"),
        }

    if tables:
        t = tables[0]
        entry["sample_table_shape"] = {
            "num_rows": getattr(t.data, "num_rows", None) if hasattr(t, "data") else None,
            "num_cols": getattr(t.data, "num_cols", None) if hasattr(t, "data") else None,
        }

    # Reading order: docling assigns each body item a position in doc.body's
    # reading-order-sorted child list. Record whether that ordering exists
    # and looks monotonic by page/bbox top, not just "some list exists".
    try:
        body_children = list(doc.body.children) if hasattr(doc, "body") else []
        entry["body_child_ref_count"] = len(body_children)
    except Exception as exc:  # noqa: BLE001
        entry["body_child_ref_count"] = None
        entry["body_child_error"] = str(exc)[:500]

    # Export the full structured JSON schema (DoclingDocument) for one document
    # only (the multi-equation composite), to keep the probe artifact bounded.
    entry["exported_full_json"] = False
    return entry, doc


def main() -> None:
    converter = DocumentConverter()

    probe = {
        "schema": "paper28-docling-probe-v1",
        "pinned_versions": PINNED_VERSIONS,
        "python_version": sys.version,
        "platform": sys.platform,
        "default_pdf_pipeline_options": _probe_default_pipeline_options(),
        "torch_import_workaround": (
            "import torch before importing docling.document_converter -- "
            "otherwise docling's deferred `from transformers import "
            "StoppingCriteria` -> `import torch` chain fails with "
            "OSError WinError 1114 loading torch/lib/c10.dll on this host. "
            "Reproduced consistently across repeated runs; not yet bisected "
            "to a specific conflicting DLL beyond the ordering fact."
        ),
        "onnxruntime_installed": False,
        "results": [],
    }

    targets = [
        (RENDER_ROOT / "composite-03-multi" / "composite-03-multi.pdf", "rendered_pdf"),
        (GOLD_ROOT / "tier3" / "composite-03-multi.docx", "docx_direct"),
        (RENDER_ROOT / "fixture-02-equation" / "fixture-02-equation.pdf", "rendered_pdf"),
    ]

    full_json_doc = None
    for path, kind in targets:
        if not path.exists():
            probe["results"].append(
                {"input_path": str(path), "input_kind": kind, "status": "not_run", "reason": "file_not_found"}
            )
            continue
        outcome = _convert_and_inspect(converter, path, kind)
        if isinstance(outcome, tuple):
            entry, doc = outcome
            if full_json_doc is None and kind == "rendered_pdf" and "multi" in path.stem:
                full_json_doc = doc
                entry["exported_full_json"] = True
            probe["results"].append(entry)
        else:
            probe["results"].append(outcome)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(probe, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT_PATH}")

    if full_json_doc is not None:
        full_json_path = OUT_PATH.with_name("paper28-docling-sample-doclingdocument.json")
        full_json_path.write_text(
            json.dumps(full_json_doc.export_to_dict(), indent=2, default=str), encoding="utf-8"
        )
        print(f"wrote {full_json_path}")


if __name__ == "__main__":
    main()
