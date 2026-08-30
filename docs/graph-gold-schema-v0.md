# OOXML/OMML graph and gold-manifest schema v0

Status: design checkpoint; no graph implementation yet.

## Node vocabulary

`document_snapshot`, `package_part`, `section`, `paragraph`, `table`, `table_row`, `table_cell`, `run`, `equation`, `caption`, `anchor`, `reference`, `source_binding`, `revision`, and `render_receipt`.

The graph is a typed projection of parsed OOXML facts. It must not silently replace missing facts with guesses.

## Structural edges

- `contains`: document/part/section/table/row/cell/paragraph/run containment.
- `orders`: document-local sibling order.
- `anchors`: native anchor identity to its current structural target.
- `caption_for`: caption to figure/table target.
- `references`: text/reference field to referenced figure/table/equation.
- `source_binds`: source file or generated artifact to the represented node.
- `revises`: prior node revision to its superseding revision.
- `clones`: copied node to its origin; clones receive fresh native IDs.
- `renders_as`: structural node or snapshot to render receipt.
- `derived_from`: normalized/parser output to its source fact.
- `conflicts_with`: mutually inconsistent facts that must remain visible.

## Identity and revisions

- Use the existing document identity key for the graph-global prefix.
- Use unambiguous native `w14:paraId` values for paragraph anchors.
- Duplicate or missing IDs become explicit `ambiguous`/`synthetic` states; never guess.
- Runs are position-scoped within a snapshot because OOXML supplies no stable run ID.
- A clone always receives a fresh paragraph/text ID and a `clones` edge to its origin.
- Content fingerprints are separate from native identity, byte hashes, and render receipts.
- Re-indexing appends a new revision and records `revises`; it must not erase history.

## Gold manifest

Each gold record contains:

```json
{
  "document": {"source_uri": "...", "source_sha256": "...", "revision": "..."},
  "nodes": [{"id": "...", "kind": "paragraph", "anchor": "...", "attrs": {}}],
  "edges": [{"src": "...", "kind": "contains", "dst": "...", "attrs": {}}],
  "facts": {"text": "...", "omml_canonical": "...", "table_grid": []},
  "uncertainty": [{"id": "...", "reason": "...", "status": "unknown"}],
  "provenance": {"producer": "...", "code_revision": "...", "created_at": "..."}
}
```

The gold manifest must be generated independently of the implementation under test, retain unknown/ambiguous facts, and identify whether an attribute is explicit OOXML, derived normalization, or heuristic inference.

## Required invariants

1. Every non-root node has exactly one containment parent in its snapshot unless the OOXML structure explicitly permits otherwise.
2. Sibling order is deterministic and separately recorded from semantic identity.
3. Every native anchor resolves to zero, one, or multiple candidates with an explicit resolution state.
4. A successful write cannot promote a document with duplicate IDs, malformed OMML containers, unresolved required references, or a stale render receipt.
5. A render receipt names renderer, version, input hash, output hash, exit status, and observed checks; missing renderer capability is `unknown`.
6. Every graph edge is typed and directionally documented; unsupported relations are not silently coerced.

## Existing implementation pointers

The parent repository's prior planning audit is `docs/meridian-build-b67-3-ooxml-omml-document-graph-2026-08-25.md`. Existing fact sources include `meridian/doc_store.py`, `meridian/research_graph.py`, `extensions/meridian-docs/meridian_docs/docs_intel.py`, and the render/provenance gate modules. This child document is the paper-facing contract; implementation changes remain a later sprint item.

## Implementation status (PAPER-S5, 2026-08-30)

Full detail and evidence: `docs/paper-s5-graph-edge-adapters-v1.md`. Short summary against the node/edge vocabulary declared above, so this contract stays checkable at a glance without opening the evidence doc:

| Kind | Gold ground truth exists? | Scored today? | Reason if not |
|---|---|---|---|
| `paragraph`, `table`, `table_row`, `table_cell`, `equation` | Yes | Yes (`tools/graph_scorer.py`, PAPER-30/S5) | -- |
| `caption` | Yes (`independent_gold_extractor.py`'s SEQ-field heuristic) | Yes for native Meridian; `not_applicable: no_candidate_adapter` for python-docx/Docling | those two libraries expose no field-instruction API |
| `anchor` | Yes (`w:bookmarkStart` names) | `not_applicable: no_candidate_adapter` for all three current candidates | none expose a bookmark-listing API yet; scorer function itself is real and tested |
| `reference`, `source_binding`, `revision` | **No** | `not_applicable: no_gold_ground_truth` | `independent_gold_extractor.py` does not produce these node kinds yet |
| `contains`, `orders` (via reading order) | Yes | Yes | -- |
| `caption_for` | Yes (resolved to nearest preceding top-level table) | `not_applicable: no_candidate_adapter` | no candidate computes an equivalent target resolution yet |
| `references`, `revises`, `clones`, `conflicts_with` | **No** | `not_applicable: no_gold_ground_truth` | not produced by the gold extractor yet |
| `anchors` (edge), `derived_from`, `renders_as` | Partial/no | Not separately scored | out of scope for PAPER-S5; `renders_as` is addressed structurally by the new round-trip render-equivalence check, not as a scored graph edge |

`package_part` and `run` nodes, and Word round-trip editability / render-equivalence, are covered separately: `tools/graph_scorer.score_round_trip_editability` plus `tools/run_paper30_graph_eval.py`'s `_word_open_edit_save_round_trip`/`run_round_trip_editability_check` perform a real Word-COM open(ReadOnly=False)→edit→Save()→Close() round trip and diff a candidate's own before/after extraction (not a gold comparison) for unintended structural drift, plus before/after retained render receipts for page-count render-equivalence.

