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

## PAPER-32: hosted document-AI track capability report (2026-08-28)

Per `comparator-contract-v0.md` §7 and the explicit user instruction governing this sprint
("Do not upload documents to Google Document AI, Azure, AWS, or any other hosted API
unless a specific provider, credential, data-handling approval, and cost approval are
explicitly supplied. Continue the local Docling track immediately and document any hosted
track as not_run if those approvals are absent."), the hosted document-AI track is
recorded here as **`not_run`**, not attempted, and not silently replaced with any manual
Claude PDF-reading pass.

**Status of the three named candidate hosted processors, checked directly rather than
assumed:**

| Provider | Credential present in this environment? | Data-handling approval? | Cost approval? |
|---|---|---|---|
| Google Document AI (Layout Parser) | No — no `GOOGLE_APPLICATION_CREDENTIALS`/service-account key and no `~/.config/gcloud` directory found on this host | Not sought | Not sought |
| Azure Document Intelligence (Layout) | No — no endpoint/key environment variables set | Not sought | Not sought |
| AWS Textract (AnalyzeDocument) | **Ambient only, not project-scoped**: a generic `[default]` profile exists in `~/.aws/credentials` and `~/.aws/config` on this host (checked for profile names only; no secret key material was read or will be read). This is almost certainly left over from unrelated prior work on this machine, not something provisioned for this project. Per the explicit user instruction governing this sprint ("a specific provider, credential, data-handling approval, and cost approval are explicitly supplied"), an ambient, unscoped local credential does **not** satisfy that gate — using it for this purpose without a separate, explicit approval would be exactly the kind of unauthorized-use case the instruction exists to prevent. Treated as **not present** for this item's purposes. | Not sought | Not sought |

All three gates are unmet for all three candidate providers; per the comparator contract's
own rule (§7.4: `not_run` = "system unavailable/ungated"), this entire track is `not_run`,
with reason `no_credential_no_approval`, not `unknown` and not a silently-omitted row.

**What would be required to un-block this**, recorded for whoever later decides whether to
pursue it: (1) an explicit user/organization decision on which single provider to use
(the contract limits this to *one* hosted processor, never multiple pooled together);
(2) a credential provisioned through this project's own environment configuration, never
hand-typed into a request by an agent; (3) an explicit data-handling approval given that
the corpus contains real-world documents sourced from docx-corpus/OmegaUse-OfficeVal
(public-web/task-benchmark sources, not private data, but still a third-party upload
decision the user must make, not an agent); (4) an explicit cost approval, since
per-page hosted document-AI billing is a real, non-trivial recurring cost across a
127-document, often multi-page corpus.

No exploratory manual/VLM PDF-reading pass was substituted for this track in this item —
per explicit standing instruction, that approach was rejected as a benchmark baseline
entirely, not merely deferred to "qualitative appendix" status.

Machine-readable capability report: `E:\MeridianData\ooxml-graph-paper\manifests\paper32-hosted-document-ai-capability-report.json`.
