"""PAPER-31: isolated single-document Docling conversion worker.

Run as a subprocess (one per document) from run_paper15_smoke.py, not
imported in-process. Isolation is deliberate: PAPER-28's probe found that
enabling `do_formula_enrichment=True` reliably crashes the whole Python
process with a native ("memory allocation of N bytes failed") panic, not a
catchable Python exception. Running each document's conversion as its own
subprocess means a native crash on one document costs one row of the
benchmark, not the entire run. do_formula_enrichment is deliberately left
OFF here (Docling's own default) because of that crash; TableFormerMode.FAST
is used instead of the default ACCURATE because PAPER-28/31 measured
ACCURATE at ~234s for one dense page versus ~28s for the same page under
FAST -- an ~8x speedup with no formula-enrichment involvement at all.

Usage: pixi run python tools/docling_convert_one.py <input_pdf> <output_json>
Exit code 0 with a JSON result on success; non-zero with best-effort partial
JSON (or nothing, if the crash is native/unrecoverable) on failure -- the
CALLER must treat a non-zero exit / missing output file as "crashed", not
retry silently.
"""
from __future__ import annotations

import json
import sys
import time

import torch  # noqa: F401 -- see tools/probe_docling.py docstring; must precede docling imports


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: docling_convert_one.py <input_pdf> <output_json>", file=sys.stderr)
        return 2
    input_path, output_path = sys.argv[1], sys.argv[2]

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.table_structure_options.mode = TableFormerMode.FAST
    opts.do_formula_enrichment = False  # crashes the process if enabled -- see module docstring
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

    t0 = time.perf_counter()
    result = converter.convert(input_path)
    elapsed = time.perf_counter() - t0

    doc = result.document
    texts = list(doc.texts) if hasattr(doc, "texts") else []
    tables = list(doc.tables) if hasattr(doc, "tables") else []
    formula_items = [t for t in texts if getattr(t, "label", None) and "formula" in str(t.label).lower()]
    full_text = "\n".join(getattr(t, "text", "") or "" for t in texts)

    table_row_total = 0
    table_col_total = 0
    for t in tables:
        data = getattr(t, "data", None)
        if data is not None:
            table_row_total += getattr(data, "num_rows", 0) or 0
            table_col_total += getattr(data, "num_cols", 0) or 0

    output = {
        "conversion_status": str(result.status),
        "wall_time_seconds": elapsed,
        "page_count": len(doc.pages) if hasattr(doc, "pages") else None,
        "text_item_count": len(texts),
        "table_count": len(tables),
        "table_row_total": table_row_total,
        "table_col_total": table_col_total,
        "equation_count": len(formula_items),
        "full_text": full_text,
        "pipeline_config": {"table_structure_mode": "FAST", "do_formula_enrichment": False, "do_ocr": opts.do_ocr},
    }
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 -- a Python-level (not native-panic) crash is still worth recording
        try:
            with open(sys.argv[2], "w", encoding="utf-8") as fh:
                json.dump({"conversion_status": "EXCEPTION", "error": f"{type(exc).__name__}: {exc}"}, fh)
        except Exception:
            pass
        raise
