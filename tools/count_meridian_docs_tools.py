"""Count and classify the Meridian Docs MCP server's tools at one commit.

Reads extensions/meridian-docs/meridian_docs/server.py from the Meridian repository
with `git show <commit>:<path>` (read-only; no checkout), finds every @mcp.tool(),
assigns each a class from CLASSES below, and writes paper/sources/meridian-docs-tools.json.
The paper's tool counts (tools.* in paper/numbers.json) are read from that file.

A tool missing from CLASSES is an error, so a new tool can't silently change a count.

    python tools/count_meridian_docs_tools.py --repository ../repository --commit f92d2710
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVER = "extensions/meridian-docs/meridian_docs/server.py"

# The eleven tools the benchmark's treatment arm uses (tools/docx_trial_broker.py treatment_tool=).
ANCHOREDIT = frozenset({
    "insert_bibliography_entry", "remove_bibliography_entry", "insert_citation", "remove_citation",
    "move_section", "insert_equation", "remove_equation", "insert_table", "remove_table",
    "insert_caption", "remove_caption"})


def _group(cls: str, names: str) -> dict[str, str]:
    return {name: cls for name in names.split()}


# "editing" = single-target content/structure edits that change the .docx (the primary tools);
# everything else is a secondary class. Assigned by reading each tool's docstring.
CLASSES = {
    **_group("editing", """
        insert_image insert_figure_block insert_media_part remove_package_part
        insert_caption edit_caption remove_caption insert_cross_reference remove_cross_reference
        insert_citation edit_citation remove_citation
        insert_equation edit_equation append_text_run_after_math remove_equation
        insert_bibliography_entry update_bibliography_entry remove_bibliography_entry
        write_section move_section copy_section relocate_figure relocate_table
        insert_table remove_table insert_column split_cell transpose_table"""),
    **_group("annotation", "highlight_document insert_highlighted_note flag_for_review"),
    **_group("whole-document repair", "renumber_sequences retrofit_plaintext_captions"),
    **_group("discovery", """
        document_outline parse_document search_document read_document_snapshot locate_anchor
        locate_anchors find_image_paragraph extract_equations get_section_content find_references_to
        scan_citation_keys extract_paragraph_images find_caption_paragraph"""),
    **_group("index-backed read", """
        get_structure get_paragraph search_paragraphs get_structure_elements get_equations
        list_internal_notes"""),
    **_group("audit", """
        get_document_review audit_document audit_equation_style audit_equation_contract
        audit_equation_integrity compare_equation_structures scan_stale_notes audit_caption_style
        audit_table_style audit_heading_style audit_cross_document_consistency
        audit_manuscript_structure audit_reference_consistency"""),
    **_group("render verification", """
        check_render_capability render_with_receipt list_render_receipts check_release_render_gate"""),
    **_group("indexing and ingest", """
        index_document index_document_structure index_equations ingest_local_document
        ingest_local_document_structure"""),
    **_group("in-document bibliography reconcile", "sync_bibliography"),
    **_group("helper", "format_reference find_orphaned_docx_staged_files"),
    **_group("batch and draft", """
        merge_docx_draft plan_batch_transform apply_batch_transform apply_and_merge_batch_transform
        build_prose_edit_packet apply_prose_edit_packets apply_reviewable_edit_transaction
        repair_equation_batch"""),
    **_group("style-preset configuration", """
        get_journal_style_preset list_journal_style_presets save_user_journal_style_preset
        delete_user_journal_style_preset get_journal_style_preset_provenance"""),
}


def registered_tools(source: str) -> list[str]:
    def is_tool(dec: ast.expr) -> bool:
        node = dec.func if isinstance(dec, ast.Call) else dec
        return isinstance(node, ast.Attribute) and node.attr == "tool" and getattr(node.value, "id", None) == "mcp"

    return sorted(fn.name for fn in ast.walk(ast.parse(source))
                  if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(map(is_tool, fn.decorator_list)))


def classify(tools: list[str]) -> dict:
    unknown = [t for t in tools if t not in CLASSES]
    if unknown:
        raise SystemExit(f"unclassified tools, add them to CLASSES: {unknown}")
    missing = sorted(ANCHOREDIT - set(tools))
    if missing:
        raise SystemExit(f"AnchorEdit tools not registered at this commit: {missing}")
    by_class = Counter(CLASSES[t] for t in tools)
    return {
        "counts": {"total": len(tools), "editing": by_class["editing"], "anchoredit": len(ANCHOREDIT),
                   "by_class": dict(sorted(by_class.items()))},
        "tools": {t: {"class": CLASSES[t], "anchoredit": t in ANCHOREDIT} for t in tools},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repository", type=Path, default=REPO.parent / "repository")
    ap.add_argument("--commit", default="f92d2710")
    ap.add_argument("--out", type=Path, default=REPO / "paper" / "sources" / "meridian-docs-tools.json")
    args = ap.parse_args()
    commit = subprocess.run(["git", "-C", str(args.repository), "rev-parse", args.commit],
                            capture_output=True, text=True, check=True).stdout.strip()
    source = subprocess.run(["git", "-C", str(args.repository), "show", f"{commit}:{SERVER}"],
                            capture_output=True, text=True, encoding="utf-8", check=True).stdout
    result = {"server": SERVER, "commit": commit, **classify(registered_tools(source))}
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{commit[:8]}: {result['counts']['total']} tools, {result['counts']['editing']} editing, "
          f"{result['counts']['anchoredit']} AnchorEdit -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
