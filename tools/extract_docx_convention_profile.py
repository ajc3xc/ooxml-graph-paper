"""Independent DOCX convention-profile extractor for PAPER-S19 (prototype).

Purpose: infer an evidence-backed profile of the DOCX *authoring conventions* a
document (or a group of documents) exhibits -- styles inheritance, numbering,
page geometry, header/footer field usage, caption conventions, table/equation
usage, revision-tracking, anchors/bookmarks, font/language defaults, citation
field usage, and metadata/accessibility hygiene -- WITHOUT using the product
parser as gold and WITHOUT reading the primary 127-document benchmark holdout
(E:\\MeridianData\\ooxml-graph-paper\\gold\\tier1|tier2|tier3) as input. This
mirrors tools/independent_gold_extractor.py's own rule: stdlib zipfile +
xml.etree.ElementTree only, no python-docx, no import of meridian_docs /
docs_intel.py or any parent-repo implementation-under-test code.

Every signal this tool emits is an `Evidence` record carrying its own node
path, source part, a confidence, an explicit authority class (observed /
inferred / template / official_guideline / domain_default), and any observed
conflicts -- never a bare value with no provenance. A document (or corpus)
profile's overall `resolution` is one of exact_template_match / venue_family /
domain_family / abstain, and this tool ABSTAINS by default: it only reports
exact_template_match when an explicit --known-templates registry is supplied
and matches, and only reports venue_family/domain_family when run in batch
mode across >=3 documents sharing an explicit --domain-label, with the
per-category agreement fraction recorded as the confidence. A single document
with no template registry and no domain label always resolves to `abstain`
-- this is treated as a correct, honest answer, not a failure.

Usage:
    pixi run python tools/extract_docx_convention_profile.py <docx_or_dir> \
        [--out DIR] [--domain-label NAME] [--domain-threshold 0.6] \
        [--known-templates FILE.json]

Determinism: running this tool twice on the same input(s) must produce an
identical `profile_hash` per document and an identical aggregate hash for a
batch -- this is checked by tests/test_extract_docx_convention_profile.py and
re-verified for the actual development corpus in
docs/paper-s19-profile-inference-v1.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "s19-profile-v1"

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC = "http://purl.org/dc/elements/1.1/"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_PR = "http://schemas.openxmlformats.org/package/2006/relationships"


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extractor_self_hash() -> str:
    return _sha256_bytes(Path(__file__).read_bytes())


AUTHORITY_LEVELS = ("observed", "inferred", "template", "official_guideline", "domain_default")


@dataclass
class Evidence:
    category: str
    node: str
    part: str
    observed_value: Any
    confidence: float
    authority: str
    status: str = "resolved"  # resolved | unknown | mixed
    conflicts: list = field(default_factory=list)
    # Only meaningful for aggregate (domain/venue-level) evidence: how many of
    # the domain's documents actually emitted this node. None for per-document
    # evidence, where it would trivially always be 1. Several per-document
    # categories only emit a node when a part/element is present (e.g. page
    # geometry nodes are skipped entirely for a document with zero <w:sectPr>
    # elements), so different aggregate nodes within the same domain can and
    # do average over different document counts -- this field makes that
    # explicit instead of leaving it implicit in the aggregate's evidence list.
    sample_size: int | None = None

    def __post_init__(self) -> None:
        if self.authority not in AUTHORITY_LEVELS:
            raise ValueError(f"unknown authority level: {self.authority!r}")
        if self.status not in ("resolved", "unknown", "mixed"):
            raise ValueError(f"unknown status: {self.status!r}")

    def key(self) -> tuple:
        return (self.category, self.node, self.part)


def _sorted_dicts(evidences: list[Evidence]) -> list[dict]:
    return [asdict(e) for e in sorted(evidences, key=Evidence.key)]


# --------------------------------------------------------------------------
# Package loading helpers
# --------------------------------------------------------------------------


class DocxPackage:
    """Thin, read-only wrapper over a DOCX zip -- no product code involved."""

    def __init__(self, path: Path):
        self.path = path
        self.raw_bytes = path.read_bytes()
        self.sha256 = _sha256_bytes(self.raw_bytes)
        self._zip = zipfile.ZipFile(path)
        self._names = set(self._zip.namelist())

    def has(self, part: str) -> bool:
        return part in self._names

    def parts_matching(self, prefix: str, suffix: str) -> list[str]:
        return sorted(n for n in self._names if n.startswith(prefix) and n.endswith(suffix))

    def xml(self, part: str) -> ET.Element | None:
        if part not in self._names:
            return None
        data = self._zip.read(part)
        try:
            return ET.fromstring(data)
        except ET.ParseError:
            return None

    def close(self) -> None:
        self._zip.close()


# --------------------------------------------------------------------------
# Per-category extractors. Each returns list[Evidence]. All authority levels
# are 'observed' (directly read from this package) unless explicitly noted as
# 'inferred' (a heuristic derived from an observed value, e.g. classifying a
# page size as "Letter" from its raw twip dimensions).
# --------------------------------------------------------------------------


def _styles_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/styles.xml"
    root = pkg.xml(part)
    if root is None:
        ev.append(Evidence("styles", "styles.xml", part, None, 1.0, "observed",
                            status="resolved"))
        return ev
    style_els = root.findall(_q(_W, "style"))
    by_type = Counter(s.get(_q(_W, "type"), "unknown") for s in style_els)
    ev.append(Evidence("styles", "style_count_by_type", part, dict(by_type), 1.0, "observed"))

    # inheritance depth: basedOn chains
    id_to_base = {}
    for s in style_els:
        sid = s.get(_q(_W, "styleId"))
        based = s.find(_q(_W, "basedOn"))
        id_to_base[sid] = based.get(_q(_W, "val")) if based is not None else None
    depths = []
    for sid in id_to_base:
        seen, cur, depth = set(), sid, 0
        while id_to_base.get(cur) and cur not in seen:
            seen.add(cur)
            cur = id_to_base[cur]
            depth += 1
            if depth > 50:
                break
        depths.append(depth)
    max_depth = max(depths) if depths else 0
    ev.append(Evidence("styles", "max_basedOn_inheritance_depth", part, max_depth, 1.0, "observed"))

    # docDefaults default font/size
    doc_defaults = root.find(_q(_W, "docDefaults"))
    default_font = None
    default_size = None
    if doc_defaults is not None:
        rpr_default = doc_defaults.find(f"{_q(_W, 'rPrDefault')}/{_q(_W, 'rPr')}")
        if rpr_default is not None:
            rfonts = rpr_default.find(_q(_W, "rFonts"))
            if rfonts is not None:
                default_font = rfonts.get(_q(_W, "ascii"))
            sz = rpr_default.find(_q(_W, "sz"))
            if sz is not None:
                default_size = sz.get(_q(_W, "val"))
    ev.append(Evidence("styles", "docDefaults_rFonts_ascii", part, default_font,
                        0.9 if default_font else 0.5, "observed",
                        status="resolved" if default_font else "unknown"))
    ev.append(Evidence("styles", "docDefaults_sz_halfpoints", part, default_size,
                        0.9 if default_size else 0.5, "observed",
                        status="resolved" if default_size else "unknown"))

    # latent styles
    latent = root.find(_q(_W, "latentStyles"))
    if latent is not None:
        ev.append(Evidence("styles", "latentStyles_count", part,
                            int(latent.get(_q(_W, "count"), 0) or 0), 1.0, "observed"))
        ev.append(Evidence("styles", "latentStyles_defLockedState", part,
                            latent.get(_q(_W, "defLockedState")), 0.9, "observed"))
    else:
        ev.append(Evidence("styles", "latentStyles_count", part, None, 1.0, "observed",
                            status="unknown"))
    return ev


def _numbering_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/numbering.xml"
    root = pkg.xml(part)
    if root is None:
        ev.append(Evidence("numbering", "numbering.xml", part, None, 1.0, "observed",
                            status="resolved"))
        ev.append(Evidence("numbering", "uses_numbering", part, False, 1.0, "inferred"))
        return ev
    ev.append(Evidence("numbering", "uses_numbering", part, True, 1.0, "inferred"))
    abstract_nums = root.findall(_q(_W, "abstractNum"))
    fmt_counter: Counter = Counter()
    for an in abstract_nums:
        for lvl in an.findall(_q(_W, "lvl")):
            numfmt = lvl.find(_q(_W, "numFmt"))
            if numfmt is not None:
                fmt_counter[numfmt.get(_q(_W, "val"), "unknown")] += 1
    ev.append(Evidence("numbering", "numFmt_usage_by_level", part, dict(fmt_counter), 1.0, "observed"))
    num_instances = root.findall(_q(_W, "num"))
    ev.append(Evidence("numbering", "num_instance_count", part, len(num_instances), 1.0, "observed"))
    ev.append(Evidence("numbering", "abstractNum_count", part, len(abstract_nums), 1.0, "observed"))
    return ev


def _sections_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/document.xml"
    root = pkg.xml(part)
    if root is None:
        return ev
    body = root.find(_q(_W, "body"))
    sect_prs = [] if body is None else body.findall(f".//{_q(_W, 'sectPr')}")
    if not sect_prs:
        ev.append(Evidence("sections", "sectPr_count", part, 0, 1.0, "observed", status="unknown"))
        return ev
    ev.append(Evidence("sections", "sectPr_count", part, len(sect_prs), 1.0, "observed"))

    pg_sizes, pg_mars, orients = [], [], []
    for sp in sect_prs:
        pgsz = sp.find(_q(_W, "pgSz"))
        if pgsz is not None:
            pg_sizes.append([pgsz.get(_q(_W, "w")), pgsz.get(_q(_W, "h"))])
            orients.append(pgsz.get(_q(_W, "orient"), "portrait"))
        pgmar = sp.find(_q(_W, "pgMar"))
        if pgmar is not None:
            pg_mars.append([pgmar.get(_q(_W, a)) for a in
                             ("top", "bottom", "left", "right", "header", "footer", "gutter")])

    def _mixed_or_single(values: list, node: str, category_conf: float):
        seen_json: dict[str, Any] = {}
        for v in values:
            seen_json[json.dumps(v, sort_keys=True)] = v
        distinct = [seen_json[k] for k in sorted(seen_json)]
        if not distinct:
            return Evidence(category="sections", node=node, part=part, observed_value=None,
                             confidence=1.0, authority="observed", status="unknown")
        if len(distinct) == 1:
            return Evidence(category="sections", node=node, part=part, observed_value=distinct[0],
                             confidence=category_conf, authority="observed", status="resolved")
        return Evidence(category="sections", node=node, part=part, observed_value=distinct[0],
                         confidence=category_conf / len(distinct), authority="observed",
                         status="mixed", conflicts=[str(d) for d in distinct[1:]])

    ev.append(_mixed_or_single(pg_sizes, "pgSz_w_h_twips", 1.0))
    ev.append(_mixed_or_single(orients, "pgSz_orient", 1.0))
    ev.append(_mixed_or_single(pg_mars, "pgMar_top_bottom_left_right_header_footer_gutter", 1.0))

    # inferred paper-size classification from the resolved (or first) pgSz
    if pg_sizes:
        w, h = pg_sizes[0]
        label = "unknown"
        try:
            wi, hi = int(w), int(h)
            if (wi, hi) in ((12240, 15840), (15840, 12240)):
                label = "Letter"
            elif (wi, hi) in ((11906, 16838), (16838, 11906)):
                label = "A4"
        except (TypeError, ValueError):
            pass
        ev.append(Evidence("sections", "pgSz_inferred_paper_label", part, label, 0.7, "inferred"))
    return ev


def _headers_footers_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    hdr_parts = pkg.parts_matching("word/header", ".xml")
    ftr_parts = pkg.parts_matching("word/footer", ".xml")
    ev.append(Evidence("headers_footers", "header_part_count", "word/", len(hdr_parts), 1.0, "observed"))
    ev.append(Evidence("headers_footers", "footer_part_count", "word/", len(ftr_parts), 1.0, "observed"))

    field_types: Counter = Counter()
    for part in hdr_parts + ftr_parts:
        root = pkg.xml(part)
        if root is None:
            continue
        for instr in root.iter(_q(_W, "instrText")):
            text = (instr.text or "").strip()
            token = text.split()[0].upper() if text.split() else ""
            if token:
                field_types[token] += 1
        for fs in root.iter(_q(_W, "fldSimple")):
            instr = fs.get(_q(_W, "instr"), "")
            token = instr.strip().split()[0].upper() if instr.strip().split() else ""
            if token:
                field_types[token] += 1
    ev.append(Evidence("headers_footers", "field_code_usage", "word/header*.xml,word/footer*.xml",
                        dict(field_types), 1.0 if field_types else 0.6, "observed",
                        status="resolved" if field_types else "unknown"))
    return ev


def _captions_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/document.xml"
    root = pkg.xml(part)
    if root is None:
        return ev
    seq_labels: Counter = Counter()
    for instr in root.iter(_q(_W, "instrText")):
        text = (instr.text or "").strip()
        if text.upper().startswith("SEQ "):
            tokens = text.split()
            if len(tokens) >= 2:
                seq_labels[tokens[1]] += 1
    ev.append(Evidence("captions", "SEQ_field_label_usage", part, dict(seq_labels),
                        1.0 if seq_labels else 0.6, "observed",
                        status="resolved" if seq_labels else "unknown"))
    return ev


def _tables_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/document.xml"
    root = pkg.xml(part)
    if root is None:
        return ev
    tbls = root.findall(f".//{_q(_W, 'tbl')}")
    ev.append(Evidence("tables", "tbl_count", part, len(tbls), 1.0, "observed"))
    if tbls:
        has_grid = sum(1 for t in tbls if t.find(_q(_W, "tblGrid")) is not None)
        styles_used = Counter()
        for t in tbls:
            tp = t.find(_q(_W, "tblPr"))
            if tp is not None:
                ts = tp.find(_q(_W, "tblStyle"))
                if ts is not None:
                    styles_used[ts.get(_q(_W, "val"))] += 1
        ev.append(Evidence("tables", "tbl_with_tblGrid_count", part, has_grid, 1.0, "observed"))
        ev.append(Evidence("tables", "tblStyle_usage", part, dict(styles_used),
                            1.0 if styles_used else 0.6, "observed",
                            status="resolved" if styles_used else "unknown"))
    return ev


def _equations_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/document.xml"
    root = pkg.xml(part)
    if root is None:
        return ev
    omath = root.findall(f".//{_q(_M, 'oMath')}")
    ev.append(Evidence("equations", "oMath_count", part, len(omath), 1.0, "observed"))
    return ev


def _revisions_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/document.xml"
    root = pkg.xml(part)
    settings_root = pkg.xml("word/settings.xml")
    track_changes = False
    if settings_root is not None:
        track_changes = settings_root.find(_q(_W, "trackChanges")) is not None
    ev.append(Evidence("revisions", "settings_trackChanges_enabled", "word/settings.xml",
                        track_changes, 1.0, "observed"))
    if root is not None:
        ins_count = len(root.findall(f".//{_q(_W, 'ins')}"))
        del_count = len(root.findall(f".//{_q(_W, 'del')}"))
        ev.append(Evidence("revisions", "ins_element_count", part, ins_count, 1.0, "observed"))
        ev.append(Evidence("revisions", "del_element_count", part, del_count, 1.0, "observed"))
    return ev


def _anchors_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/document.xml"
    root = pkg.xml(part)
    if root is None:
        return ev
    bookmarks = root.findall(f".//{_q(_W, 'bookmarkStart')}")
    names = [b.get(_q(_W, "name")) for b in bookmarks]
    non_reserved = [n for n in names if n and not n.startswith("_")]
    ev.append(Evidence("anchors", "bookmarkStart_count", part, len(bookmarks), 1.0, "observed"))
    ev.append(Evidence("anchors", "user_named_bookmark_count", part, len(non_reserved), 1.0, "observed"))
    internal_hyperlinks = 0
    for h in root.findall(f".//{_q(_W, 'hyperlink')}"):
        if h.get(_q(_W, "anchor")) is not None:
            internal_hyperlinks += 1
    ev.append(Evidence("anchors", "internal_hyperlink_count", part, internal_hyperlinks, 1.0, "observed"))
    return ev


def _fonts_language_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/document.xml"
    root = pkg.xml(part)
    if root is None:
        return ev
    langs = Counter(lang.get(_q(_W, "val")) for lang in root.iter(_q(_W, "lang"))
                     if lang.get(_q(_W, "val")))
    ev.append(Evidence("fonts_language", "w:lang_val_usage", part, dict(langs),
                        1.0 if langs else 0.5, "observed", status="resolved" if langs else "unknown"))
    fonts_root = pkg.xml("word/fontTable.xml")
    if fonts_root is not None:
        font_names = [f.get(_q(_W, "name")) for f in fonts_root.findall(_q(_W, "font"))]
        ev.append(Evidence("fonts_language", "fontTable_font_count", "word/fontTable.xml",
                            len(font_names), 1.0, "observed"))
    return ev


def _citations_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    part = "word/document.xml"
    root = pkg.xml(part)
    if root is None:
        return ev
    citation_tokens = 0
    for instr in root.iter(_q(_W, "instrText")):
        text = (instr.text or "").strip().upper()
        if text.startswith("CITATION") or text.startswith("BIBLIOGRAPHY") or text.startswith("ADDIN"):
            citation_tokens += 1
    ev.append(Evidence("citations", "citation_or_bibliography_field_count", part, citation_tokens,
                        1.0, "observed"))
    return ev


def _metadata_accessibility_evidence(pkg: DocxPackage) -> list[Evidence]:
    ev: list[Evidence] = []
    core = pkg.xml("docProps/core.xml")
    if core is not None:
        title_el = core.find(_q(_DC, "title"))
        lang_el = core.find(_q(_DC, "language"))
        creator_el = core.find(_q(_DC, "creator"))
        ev.append(Evidence("metadata_accessibility", "core_title_present", "docProps/core.xml",
                            bool(title_el is not None and (title_el.text or "").strip()), 1.0, "observed"))
        ev.append(Evidence("metadata_accessibility", "core_language", "docProps/core.xml",
                            lang_el.text if lang_el is not None else None,
                            0.9 if lang_el is not None else 0.5, "observed",
                            status="resolved" if lang_el is not None else "unknown"))
        ev.append(Evidence("metadata_accessibility", "core_creator_present", "docProps/core.xml",
                            bool(creator_el is not None and (creator_el.text or "").strip()), 1.0, "observed"))
    else:
        ev.append(Evidence("metadata_accessibility", "core.xml", "docProps/core.xml", None, 1.0,
                            "observed", status="unknown"))

    # accessibility: alt-text on drawings (wp:docPr@descr / @title)
    doc_root = pkg.xml("word/document.xml")
    if doc_root is not None:
        drawings = doc_root.findall(f".//{_q(_WP, 'docPr')}")
        with_alt = sum(1 for d in drawings if (d.get("descr") or d.get("title")))
        ev.append(Evidence("metadata_accessibility", "drawing_count", "word/document.xml",
                            len(drawings), 1.0, "observed"))
        if drawings:
            ev.append(Evidence("metadata_accessibility", "drawing_with_alt_text_count",
                                "word/document.xml", with_alt, 1.0, "observed"))
    return ev


_CATEGORY_FUNCS = {
    "styles": _styles_evidence,
    "numbering": _numbering_evidence,
    "sections": _sections_evidence,
    "headers_footers": _headers_footers_evidence,
    "captions": _captions_evidence,
    "tables": _tables_evidence,
    "equations": _equations_evidence,
    "revisions": _revisions_evidence,
    "anchors": _anchors_evidence,
    "fonts_language": _fonts_language_evidence,
    "citations": _citations_evidence,
    "metadata_accessibility": _metadata_accessibility_evidence,
}


def _canonical_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(blob)


def extract_document_profile(docx_path: Path, known_templates: list[dict] | None = None) -> dict:
    pkg = DocxPackage(docx_path)
    try:
        evidences: list[Evidence] = []
        for fn in _CATEGORY_FUNCS.values():
            evidences.extend(fn(pkg))
        evidence_dicts = _sorted_dicts(evidences)

        resolution = {"level": "abstain", "reason": "no known-template registry supplied", "matched_template": None}
        if known_templates:
            for tmpl in known_templates:
                if _profile_matches_template(evidence_dicts, tmpl.get("evidence", [])):
                    resolution = {
                        "level": "exact_template_match",
                        "reason": f"structural match against known template {tmpl.get('name')!r}",
                        "matched_template": tmpl.get("name"),
                    }
                    break
            else:
                resolution = {"level": "abstain", "reason": "known-template registry supplied but no match",
                              "matched_template": None}

        categories_present = {
            cat: any(e["observed_value"] not in (None, {}, [], 0, False) and e["status"] != "unknown"
                     for e in evidence_dicts if e["category"] == cat)
            for cat in _CATEGORY_FUNCS
        }
        profile_core = {"schema_version": SCHEMA_VERSION, "evidence": evidence_dicts, "resolution": resolution}
        profile = {
            **profile_core,
            "doc_id": docx_path.stem,
            "source_path": str(docx_path),
            "source_sha256": pkg.sha256,
            "extractor_self_hash": _extractor_self_hash(),
            "categories_present": categories_present,
            "profile_hash": _canonical_hash(profile_core),
        }
        return profile
    finally:
        pkg.close()


def _profile_matches_template(evidence_dicts: list[dict], template_evidence: list[dict]) -> bool:
    key_categories = {"sections", "styles", "numbering"}
    a = {(e["category"], e["node"]): e["observed_value"] for e in evidence_dicts if e["category"] in key_categories}
    b = {(e["category"], e["node"]): e["observed_value"] for e in template_evidence if e["category"] in key_categories}
    if not b:
        return False
    return all(a.get(k) == v for k, v in b.items())


def aggregate_domain_profile(profiles: list[dict], domain_label: str, threshold: float) -> dict:
    """Aggregate per-document evidence into a domain-level profile. Only ever
    reaches 'domain_family' (never 'venue_family' or 'exact_template_match' --
    those require, respectively, an explicit venue tag this prototype does not
    have, and a known-template registry) when >=3 documents share a node's
    value at or above `threshold` agreement; otherwise abstains per-node.
    """
    by_key: dict[tuple, list] = defaultdict(list)
    for prof in profiles:
        for e in prof["evidence"]:
            by_key[(e["category"], e["node"], e["part"])].append(e["observed_value"])

    agg_evidence = []
    for (category, node, part), values in sorted(by_key.items()):
        hashable = [json.dumps(v, sort_keys=True) for v in values]
        counts = Counter(hashable)
        total = len(hashable)
        top_value_json, top_count = counts.most_common(1)[0]
        agreement = top_count / total if total else 0.0
        if total >= 3 and agreement >= threshold:
            status = "resolved" if len(counts) == 1 else "mixed"
            conflicts = [v for v, c in counts.items() if v != top_value_json]
            agg_evidence.append(Evidence(
                category=category, node=node, part=part,
                observed_value=json.loads(top_value_json), confidence=round(agreement, 4),
                authority="domain_default", status=status,
                conflicts=[json.loads(c) for c in conflicts], sample_size=total,
            ))
        else:
            agg_evidence.append(Evidence(
                category=category, node=node, part=part, observed_value=None,
                confidence=round(agreement, 4), authority="inferred", status="unknown",
                conflicts=[f"n={total} insufficient or below threshold={threshold}"], sample_size=total,
            ))

    resolvable = [e for e in agg_evidence if e.status != "unknown" and e.authority == "domain_default"]
    level = "domain_family" if resolvable else "abstain"
    reason = (f"{len(resolvable)}/{len(agg_evidence)} node(s) reached >= {threshold:.0%} agreement "
              f"across {len(profiles)} documents tagged domain={domain_label!r}")
    evidence_dicts = _sorted_dicts(agg_evidence)
    core = {
        "schema_version": SCHEMA_VERSION,
        "domain_label": domain_label,
        "document_count": len(profiles),
        "threshold": threshold,
        "evidence": evidence_dicts,
        "resolution": {"level": level, "reason": reason, "matched_template": None},
    }
    core["profile_hash"] = _canonical_hash({k: v for k, v in core.items() if k != "profile_hash"})
    core["member_doc_ids"] = sorted(p["doc_id"] for p in profiles)
    core["member_source_sha256"] = sorted(p["source_sha256"] for p in profiles)
    return core


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="A .docx file or a directory of .docx files")
    ap.add_argument("--out", default=None, help="Output directory for per-document + aggregate JSON")
    ap.add_argument("--domain-label", default=None, help="Tag applied when aggregating a directory of documents")
    ap.add_argument("--domain-threshold", type=float, default=0.6)
    ap.add_argument("--known-templates", default=None, help="Optional JSON file: list of {name, evidence}")
    args = ap.parse_args(argv)

    known_templates = None
    if args.known_templates:
        known_templates = json.loads(Path(args.known_templates).read_text(encoding="utf-8"))

    in_path = Path(args.input)
    docx_files = sorted(in_path.glob("*.docx")) if in_path.is_dir() else [in_path]

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    profiles = []
    for f in docx_files:
        prof = extract_document_profile(f, known_templates=known_templates)
        profiles.append(prof)
        if out_dir:
            (out_dir / f"{f.stem}.profile.json").write_text(
                json.dumps(prof, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"doc_id": prof["doc_id"], "profile_hash": prof["profile_hash"],
                           "resolution": prof["resolution"]["level"]}))

    if len(profiles) > 1 and args.domain_label:
        agg = aggregate_domain_profile(profiles, args.domain_label, args.domain_threshold)
        if out_dir:
            (out_dir / f"_aggregate_{args.domain_label}.json").write_text(
                json.dumps(agg, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"domain_label": agg["domain_label"], "profile_hash": agg["profile_hash"],
                           "resolution": agg["resolution"]["level"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
