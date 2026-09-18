# OOXML-Graph Paper

Source, harness, and evaluation code for **"Bounded Structural Primitives versus Generic Tool
Use for Agentic Word Document Editing: A Confirmatory Benchmark"** (`paper/main.tex`) — a
confirmatory benchmark comparing Meridian Docs' bounded, atomic document-editing tools against
a generic Claude agent restricted to raw file/XML access, on the same model, across six real
`.docx` editing task families.

The paper is the primary artifact in this repository. See `paper/main.tex` for the full
methodology, results, ten disclosed infrastructure/harness defects, and limitations.

## What's in this repo

- `paper/` — the LaTeX source, figures, and bibliography for the paper itself.
- `tools/` — the benchmark harness (trial runner, statistics, grading/evaluator code) and the
  `margin_notes` review tool used to collect and act on editorial feedback during drafting.
- `tests/` — unit tests for the statistics and grading code.
- `docs/` — working notes from the project's own development: defect writeups, corpus-audit
  records, and intermediate result snapshots referenced throughout the paper.

## What's not in this repo

The underlying `.docx` corpus (a licensed slice of the DocOps benchmark corpus) is not included
and is not licensed for redistribution — see the paper's Limitations/Artifact-availability
section for what's released versus what remains restricted. Raw run data, renders, and model
caches are excluded via `.gitignore` and were never committed.

## Building the paper

```powershell
cd paper
.\build.ps1
```

Requires a working LaTeX toolchain (MiKTeX or TeX Live) with `latexmk`/`pdflatex` and `bibtex`
on `PATH`.

## Running the tests

```
pixi run test
```

Note: `pixi.toml` depends on two packages (`meridian-docparse`, `meridian-docs-mcp`) as editable
installs from a sibling `../repository` directory — the private parent Meridian monorepo that
this benchmark's treatment arm exercises. That repository is not included here, so the full test
suite and any live trial (treatment-arm) run are not reproducible standalone from just this
repo. The statistics/grading unit tests under `tests/` (`test_graph_scorer.py`,
`test_compute_s7_statistics.py`) exercise only this repo's own `tools/` code and have no such
dependency.
