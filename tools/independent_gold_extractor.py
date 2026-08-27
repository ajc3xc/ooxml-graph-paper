"""Independent OOXML graph-gold extractor for PAPER-22.

Deliberately does NOT import meridian_docs / docs_intel.py or anything from the
parent repository's implementation under test. Parses word/document.xml directly
with stdlib xml.etree.ElementTree + zipfile only, so a gold record produced here
cannot be circular with the product code PAPER-15 will benchmark
(graph-gold-schema-v0.md: "generated independently of the implementation under
test"). Where a fact can't be confidently resolved, it goes into `uncertainty`,
not a guess folded into `nodes`/`facts` (graph-gold-schema-v0.md's own rule).

Usage: pixi run python tools/independent_gold_extractor.py <docx_path> [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_NS = {"w": _W, "w14": _W14, "m": _M}


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extractor_self_hash() -> str:
    return _sha256(Path(__file__).read_bytes())


def _local_text(elem: ET.Element) -> str:
    """Concatenate w:t descendant text within one element (paragraph or run)."""
    parts = [t.text or "" for t in elem.iter(_q(_W, "t"))]
    return "".join(parts)


# benchmark-preregistration-v0.md Section 5's 6-class equation semantic label
# set, computed independently (own structural inspection of the OMML, not a
# call into docs_intel._validate_omml_structure or any product code).
_EQUATION_REQUIRED_CHILD_TAGS = {"num", "den", "e", "sub", "sup", "deg"}
_FALLBACK_MARKER_WORDS = ("fraction", "over", "summation", "subscript", "superscript", "cases", "matrix")


def _classify_equation(eq: ET.Element) -> tuple[str, str]:
    """Returns (label, reason). Labels: correct, empty_required_child,
    fallback_forbidden, or unknown (when neither heuristic applies and no
    reference source exists to judge lossy_reviewed/package_render_divergent/
    fails_closed against -- those three need a source LaTeX/MathML or a render
    comparison this extractor doesn't have, so this classifier never emits them)."""
    structural_children = [c for c in eq.iter() if c is not eq]
    has_any_math_structure = any(
        c.tag.startswith(f"{{{_M}}}") and c.tag != _q(_M, "r") and c.tag != _q(_M, "t")
        for c in structural_children
    )
    flat_text = _local_text(eq).strip().lower()
    if not has_any_math_structure and any(w in flat_text for w in _FALLBACK_MARKER_WORDS):
        return "fallback_forbidden", f"no OMML structural elements present; flattened text contains a fallback marker word ({flat_text!r})"

    for child in eq.iter():
        local_tag = child.tag.rsplit("}", 1)[-1]
        if local_tag in _EQUATION_REQUIRED_CHILD_TAGS:
            has_visible_content = bool(_local_text(child).strip()) or any(
                gc.tag.startswith(f"{{{_M}}}") for gc in child
            )
            if not has_visible_content:
                return "empty_required_child", f"<m:{local_tag}> is present but carries no visible text or nested structure"

    return "correct", "has real OMML structural elements; all required-child slots this classifier checks carry visible content"


def _is_seq_field(p: ET.Element) -> bool:
    for instr in p.iter(_q(_W, "instrText")):
        if instr.text and instr.text.strip().upper().startswith("SEQ"):
            return True
    for fld in p.iter(_q(_W, "fldSimple")):
        instr = fld.get(_q(_W, "instr")) or ""
        if instr.strip().upper().startswith("SEQ"):
            return True
    return False


def extract(docx_path: Path) -> dict:
    raw = docx_path.read_bytes()
    source_sha256 = _sha256(raw)

    with zipfile.ZipFile(docx_path) as zf:
        try:
            doc_xml_bytes = zf.read("word/document.xml")
        except KeyError as exc:
            raise ValueError(f"{docx_path}: no word/document.xml in package") from exc
        part_names = zf.namelist()

    uncertainty: list[dict] = []
    try:
        root = ET.fromstring(doc_xml_bytes)
    except ET.ParseError as exc:
        return {
            "document": {"source_uri": str(docx_path), "source_sha256": source_sha256, "revision": None},
            "nodes": [],
            "edges": [],
            "facts": {"text": "", "omml_canonical": [], "table_grid": []},
            "uncertainty": [{"id": "doc", "reason": f"word/document.xml failed to parse: {exc}", "status": "unknown"}],
            "provenance": _provenance(),
        }

    body = root.find(_q(_W, "body"))
    nodes: list[dict] = [{"id": "doc", "kind": "document_snapshot", "anchor": None, "attrs": {"part_count": len(part_names)}}]
    edges: list[dict] = []
    full_text_parts: list[str] = []
    omml_canonical: list[str] = []
    table_grids: list[list[int]] = []

    seen_para_ids: dict[str, int] = {}
    section_idx = 0
    para_order = 0
    table_order = 0

    def _add_edge(src: str, kind: str, dst: str, attrs: dict | None = None) -> None:
        edges.append({"src": src, "kind": kind, "dst": dst, "attrs": attrs or {}})

    def _walk_paragraph(p: ET.Element, parent_id: str, order: int) -> str:
        nonlocal para_order
        para_id_attr = p.get(_q(_W14, "paraId"))
        text_id_attr = p.get(_q(_W14, "textId"))
        if para_id_attr is None:
            pid = f"para-synthetic-{para_order}"
            uncertainty.append({"id": pid, "reason": "no w14:paraId present on this w:p", "status": "synthetic"})
            anchor = None
        else:
            seen_para_ids[para_id_attr] = seen_para_ids.get(para_id_attr, 0) + 1
            pid = f"para-{para_id_attr}"
            anchor = para_id_attr
        text = _local_text(p)
        full_text_parts.append(text)
        equations = p.findall(f".//{_q(_M, 'oMath')}")
        is_caption = _is_seq_field(p)
        node = {
            "id": pid,
            "kind": "paragraph",
            "anchor": anchor,
            "attrs": {
                "w14_para_id": para_id_attr,
                "w14_text_id": text_id_attr,
                "text": text,
                "order": order,
                "has_equation": bool(equations),
                "is_caption_candidate": is_caption,
            },
        }
        nodes.append(node)
        _add_edge(parent_id, "contains", pid, {"order": order})

        for i, eq in enumerate(equations):
            eq_id = f"{pid}-eq{i}"
            eq_xml = ET.tostring(eq, encoding="unicode")
            omml_canonical.append(eq_xml)
            label, reason = _classify_equation(eq)
            nodes.append({
                "id": eq_id, "kind": "equation", "anchor": None,
                "attrs": {
                    "omml_raw": eq_xml, "order": i,
                    "semantic_label": label, "semantic_label_reason": reason,
                },
            })
            _add_edge(pid, "contains", eq_id, {"order": i})
            if label != "correct":
                uncertainty.append({
                    "id": eq_id,
                    "reason": f"equation labeled {label!r} by independent classifier: {reason}",
                    "status": "ambiguous",
                })

        if is_caption:
            node["kind"] = "caption"
            uncertainty.append({
                "id": pid,
                "reason": "caption detected heuristically via a SEQ field; caption_for target not resolved by this extractor pass",
                "status": "ambiguous",
            })

        for bm in p.iter(_q(_W, "bookmarkStart")):
            bm_name = bm.get(_q(_W, "name"))
            bm_id = bm.get(_q(_W, "id"))
            if bm_name and not bm_name.startswith("_GoBack"):
                anchor_id = f"anchor-{bm_id}-{bm_name}"
                nodes.append({
                    "id": anchor_id, "kind": "anchor", "anchor": bm_name,
                    "attrs": {"bookmark_id": bm_id, "name": bm_name},
                })
                _add_edge(pid, "anchors", anchor_id, {})

        para_order += 1
        return pid

    def _walk_table(tbl: ET.Element, parent_id: str, order: int) -> str:
        nonlocal table_order
        tbl_id = f"table-{table_order}"
        rows = tbl.findall(_q(_W, "tr"))
        grid: list[int] = []
        nodes.append({"id": tbl_id, "kind": "table", "anchor": None, "attrs": {"order": order, "row_count": len(rows)}})
        _add_edge(parent_id, "contains", tbl_id, {"order": order})
        for r_i, tr in enumerate(rows):
            row_id = f"{tbl_id}-row{r_i}"
            cells = tr.findall(_q(_W, "tc"))
            grid.append(len(cells))
            nodes.append({"id": row_id, "kind": "table_row", "anchor": None, "attrs": {"order": r_i, "cell_count": len(cells)}})
            _add_edge(tbl_id, "contains", row_id, {"order": r_i})
            for c_i, tc in enumerate(cells):
                cell_id = f"{row_id}-cell{c_i}"
                nodes.append({"id": cell_id, "kind": "table_cell", "anchor": None, "attrs": {"order": c_i, "text": _local_text(tc)}})
                _add_edge(row_id, "contains", cell_id, {"order": c_i})
                for p_i, p in enumerate(tc.findall(_q(_W, "p"))):
                    _walk_paragraph(p, cell_id, p_i)
        table_grids.append(grid)
        table_order += 1
        return tbl_id

    top_level_sequence: list[tuple[str, str, int]] = []  # (kind, node_id, top_order) for caption_for resolution

    if body is not None:
        sec_id = f"section-{section_idx}"
        nodes.append({"id": sec_id, "kind": "section", "anchor": None, "attrs": {"order": section_idx}})
        _add_edge("doc", "contains", sec_id, {"order": section_idx})
        top_order = 0
        for child in body:
            tag = child.tag
            if tag == _q(_W, "p"):
                pid = _walk_paragraph(child, sec_id, top_order)
                para_node = next(n for n in nodes if n["id"] == pid)
                top_level_sequence.append((para_node["kind"], pid, top_order))
                top_order += 1
            elif tag == _q(_W, "tbl"):
                tbl_id = _walk_table(child, sec_id, top_order)
                top_level_sequence.append(("table", tbl_id, top_order))
                top_order += 1
            elif tag == _q(_W, "sectPr"):
                continue
            else:
                uncertainty.append({"id": f"{sec_id}-child{top_order}", "reason": f"unrecognized body-level element {tag!r}, not extracted", "status": "unknown"})
                top_order += 1

    # benchmark-preregistration-v0.md Section 6: every caption/reference/edge
    # instance must get an EXPLICIT resolved/ambiguous/dangling state, never a
    # silent guess. Resolve each top-level caption to the nearest PRECEDING
    # top-level table in the same section (the one real, checkable heuristic
    # available without a human-authored ground truth); anything else becomes
    # an explicit dangling record, not a vague "ambiguous" catch-all.
    tables_in_order = [(nid, order) for kind, nid, order in top_level_sequence if kind == "table"]
    for kind, nid, order in top_level_sequence:
        if kind != "caption":
            continue
        preceding_tables = [t for t in tables_in_order if t[1] < order]
        # Remove the generic "ambiguous, not resolved by this extractor pass" note
        # added at caption-detection time -- Section 6 resolution below replaces it
        # with a specific resolved/dangling record.
        uncertainty[:] = [u for u in uncertainty if u.get("id") != nid]
        if preceding_tables:
            target_id = preceding_tables[-1][0]
            _add_edge(nid, "caption_for", target_id, {"resolution": "nearest_preceding_top_level_table"})
        else:
            uncertainty.append({
                "id": nid,
                "reason": "Section 6 caption_for resolution: no preceding top-level table found in this section -- explicitly dangling, not guessed",
                "status": "dangling",
            })

    dup_para_ids = {pid: count for pid, count in seen_para_ids.items() if count > 1}
    for pid, count in dup_para_ids.items():
        uncertainty.append({"id": f"para-{pid}", "reason": f"w14:paraId {pid!r} appears {count} times in this document (duplicate)", "status": "ambiguous"})

    # Bookmarks inside table cells: _walk_table's per-cell paragraph loop already
    # calls _walk_paragraph, which emits anchor nodes + their `anchors` edge, so
    # no separate top-level bookmark pass is needed (a prior version here duplicated
    # anchor nodes with no edges at all -- caught by an independent reviewer pass;
    # see docs/gold-corpus-status-v0.md).

    return {
        "document": {"source_uri": str(docx_path), "source_sha256": source_sha256, "revision": None},
        "nodes": nodes,
        "edges": edges,
        "facts": {
            "text": "\n".join(t for t in full_text_parts if t),
            "omml_canonical": omml_canonical,
            "table_grid": table_grids,
        },
        "uncertainty": uncertainty,
        "provenance": _provenance(),
    }


def _provenance() -> dict:
    import datetime

    return {
        "producer": "tools/independent_gold_extractor.py",
        "producer_self_sha256": _extractor_self_hash(),
        "producer_note": "stdlib xml.etree.ElementTree + zipfile only; does not import meridian_docs or docs_intel.py",
        "code_revision": None,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx_path", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    record = extract(args.docx_path)
    out_path = args.out or args.docx_path.with_suffix(".gold.json")
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path} -- {len(record['nodes'])} nodes, {len(record['edges'])} edges, {len(record['uncertainty'])} uncertainty entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
