# OOXML-Graph Paper

This is the paper subproject under `meridian-build`. It evaluates native DOCX/OOXML/OMML structure against document-parser and document-AI baselines.

## Local execution layout

- Source, Pixi project, manifests, and tests: this directory on the local C: drive.
- Large data, renders, model caches, run outputs, and logs: `E:\MeridianData\ooxml-graph-paper`.
- OneDrive/synced locations are reference-only. Do not place experiment artifacts there.

## Current checkpoint — 2026-08-26

- The local machine has Pixi and an NVIDIA GeForce RTX 3080 with 20,480 MiB VRAM.
- The Meridian repository already contains DocBank scoring support at `packages/docparse/docparse/docbank_scoring.py` and synthetic tests at `tests/test_docbank_scoring.py`.
- No paired DOCX/OOXML graph corpus is present locally, and no final benchmark or GPU baseline has been launched.
- ReadingBank remains a useful Word-derived layout context source, but its full raw package is not staged and its public derived material is not native OOXML graph gold.
- The first executable benchmark wave must use a small approved paired DOCX/OOXML/Word-render gold set; DocBank/ReadingBank are separate context tracks, not substitutes for that gold.
- A real Meridian equation-to-Word render probe has passed locally; semantic OMML hardening and retained receipts remain open.

## Repository boundary

This folder is the paper subproject: planning docs, benchmark harnesses, manifests, and local experiment metadata. Product implementation and regression tests are in the parent repository at `C:\Users\13144\Documents\Meridian\repository`, especially `extensions/meridian-docs`. Do not add product patches here or treat an empty local test collection as product coverage.

## Guardrails

1. Freeze the comparator, graph schema, split policy, and provenance manifest before downloading a large corpus.
2. Start with official indexes/preview samples and a small smoke slice.
3. Run native OOXML parsing and scoring locally; use the RTX 3080 only for explicitly selected GPU baselines.
4. Every run must record dataset revision, code revision, model revision, hardware, environment, token accounting, wall time, and output hashes.
5. Do not reactivate unrelated 2030 OOXML experiments without explicit human approval.
