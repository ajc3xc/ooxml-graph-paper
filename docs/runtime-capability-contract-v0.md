# Runtime capability contract v0

## Fully local

- OOXML/OMML ZIP/XML parsing and graph projection.
- Existing `meridian-docs` structural extraction and DocBank scoring code.
- Gold-manifest validation, ID/relationship/notation checks, metric calculation, and statistical aggregation.
- CPU parser baselines and deterministic conversion experiments where the converter is installed.
- GPU baselines that fit the local RTX 3080's 20 GB VRAM, with batch size and precision recorded.
- Run manifests, logs, hashes, token counts, and derived outputs on `E:\MeridianData\ooxml-graph-paper`.

## Local but conditional

- Microsoft Word COM rendering: available only if Word responds within the bounded worker timeout.
- LibreOffice rendering: requires `soffice` or `libreoffice` to be installed and reachable.
- Any model baseline: requires a reproducible local checkpoint and a pinned dependency set.

## Requires meridian-docs / Word / LibreOffice

- Fresh structural extraction through the meridian-docs MCP surface.
- Word-native equation, caption, field, table, and reference behavior.
- Visual render receipts and page-level parity checks.
- Office editability/comprehension gates.

## Requires a tunnel or external service

- Hosted Meridian state or remote MCP tools when the local server is not running.
- Commercial/API document parsers or LLM baselines, including provider token and cost accounting.
- Any external dataset/model download not already staged locally.

External calls must write only a manifest/receipt into the local E: data root; secrets and machine-local paths never enter shared project state.

## Manual human setup gates

- Confirm the DOCX gold-set source and licensing.
- Install/activate Word or LibreOffice if render verification is required.
- Approve any paid/API baseline and provide credentials through local environment configuration.
- Approve full DocBank materialization if the 54.3 GB dataset and derived artifacts are desired.
- Approve reactivation of any unrelated 2030 OOXML experiment.

## Current observed state

Updated 2026-08-26. Pixi and the RTX 3080 are available locally. Microsoft Word is installed at the Office16 Click-to-Run location and responds through Word COM (`16.0.20326`, build `16.0.20326.20100`); `MML2OMML.XSL` is also present locally. `winword.exe` is not on PATH, so capability detection must use the registered COM/server path rather than `Get-Command winword`. A real Meridian equation insertion into a Word-created DOCX returned `render_status=rendered`, `render_verified=true`, and `render_backend=word-com`.

LibreOffice/`soffice` is not installed or on PATH. Word is therefore the canonical renderer on this host; LibreOffice remains an optional secondary compatibility renderer and must never substitute for Word evidence. The current Meridian render gate still needs an audit-grade retained receipt (source/PDF hashes, Word build/path, explicit export method, page count, freshness, and cleanup status). The probe manifest is kept at `E:\MeridianData\ooxml-graph-paper\manifests\meridian-equation-word-probe-20260826.json`.

The paper subproject contains planning documents and the Pixi environment only. Product code and its regression tests remain in the parent repository under `extensions/meridian-docs`; the subproject's own `pixi run test` currently collects zero tests.
