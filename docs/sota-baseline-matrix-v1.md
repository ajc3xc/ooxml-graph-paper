# Document-AI baseline matrix v1

Status: investigation snapshot, 2026-08-29. This is an availability and comparability
inventory, not a claim that every listed system has been benchmarked.

## Frozen study boundary

The primary paper evaluates native DOCX/OOXML/OMML structure. Document-AI systems are a
separate rendered-PDF track: each PDF must come from the same Word-rendered source DOCX,
and each result must retain the source DOCX hash. A PDF-only system is not scored as
having zero native paragraph IDs, revisions, provenance, or editable write-back; those
capabilities are `not_applicable` by construction.

OmniDocBench is the external reference for contemporary PDF parsing systems and metrics.
Its published model table is useful for selecting comparison candidates, but its scores
are not transferable to this DOCX/OOXML corpus. No system is called “latest” here without
a dated version and reproducible input/configuration record.

## Baseline matrix

| System | Input in this study | Role | Local status | Version/config evidence | 20-GB RTX 3080 status | Decision |
|---|---|---|---|---|---|---|
| Meridian native graph reader/writer | DOCX bytes | Primary product system | Existing product path; paper harness available | Parent `meridian-docs` revision must be recorded per run | Not applicable to deterministic parser | Required Track A system |
| `python-docx` | DOCX bytes | Same-format generic parser | Installed and previously run | `python-docx 1.2.0` | CPU sufficient | Required Track A comparator |
| Docling | Word-rendered PDF | Local document-AI baseline | Installed and previously run on CPU | `docling 2.123.0`; FAST pipeline used in PAPER-31 | GPU path unverified; current Torch is CPU-only | Required Track B baseline |
| Pandoc | DOCX or conversion output | Conversion-mediated comparator | Not installed/verified | No pinned binary/version | Not applicable | Optional; report `not_run` unless installed and pinned |
| LibreOffice/`soffice` | DOCX/PDF | Compatibility/render comparator | Not installed or on PATH | No binary/version | Not applicable | Optional only; never Word authority |
| MinerU / MinerU2.5 | Rendered PDF or direct DOCX depending adapter | Strong open parser/VLM candidate | Not installed or verified in this environment | Official project and OmniDocBench listing found; exact checkpoint/config still required | Candidate may fit, but must probe memory and runtime | Candidate Track B addition, not yet frozen as run |
| PaddleOCR PP-StructureV3 / PaddleOCR-VL | Rendered PDF/images | Strong open parser/VLM candidate | Not installed or verified in this environment | Official project and OmniDocBench listing found; exact release/checkpoint still required | Candidate requires a clean dependency probe | Candidate Track B addition, not yet frozen as run |
| GLM-OCR, olmOCR, dots.ocr, MonkeyOCR, OpenDoc | Rendered PDF/images | Additional open model candidates | Not installed or verified | Listed by current OmniDocBench materials; individual license/checkpoint audit required | Unknown until checkpoint probe | Do not add to primary run without selection and budget |
| Hosted Google/Azure/AWS document AI | Rendered PDF | External commercial comparator | `not_run` | No project-scoped credential, data approval, or cost approval | Hosted | Remains explicitly gated, never silently substituted |
| Manual Claude PDF reading | Rendered PDF | Qualitative exploratory evidence only | Not a fixed harness | Prompt/model/temperature and execution are not frozen | Not applicable | Never a scored benchmark baseline |

## Environment findings

The paper Pixi environment currently reports:

```text
Python 3.12.14
docling 2.123.0
torch 2.13.0+cpu
transformers 5.16.1
python-docx 1.2.0
lxml 6.1.2
torch.cuda.is_available() = False
```

This contradicts the weaker wording “GPU baseline available” in earlier runtime notes.
The machine may have an RTX 3080, but this environment cannot use it until a CUDA-enabled
Torch/Pixi environment is deliberately installed and verified. Existing Docling results
are therefore CPU results and must be reported that way.

## Fair-input and resource rules

1. Track A systems receive the exact DOCX package and are scored against independent
   native graph gold.
2. Track B systems receive only the Word-rendered PDF, never the original OOXML package.
3. Every run records source DOCX hash, PDF hash, dataset revision, code revision, model
   checkpoint/revision, prompt/configuration, hardware, wall time, peak RSS/VRAM, output
   hashes, token counts where applicable, and receipt status.
4. A model crash, timeout, malformed-input rejection, or unavailable dependency is a
   retained per-document failure category, not an omitted row.
5. CPU and GPU runs are separate configurations; they are never pooled into one timing
   number.
6. The initial comparison remains Meridian versus `python-docx` and Docling. MinerU or
   PaddleOCR-VL/PP-StructureV3 should be added only after a bounded smoke probe confirms
   that installation, licensing, input modality, and output normalization are viable.

## Current conclusion

The project has one real local document-AI baseline (Docling) and one real same-format
parser comparator (`python-docx`). It does not yet have a runnable, frozen multi-model
SOTA bakeoff. OmniDocBench supports selecting stronger open candidates, but its published
PDF results are external context, not evidence for Meridian's native DOCX claim.

## Primary references

- OmniDocBench repository: https://github.com/opendatalab/OmniDocBench
- OmniDocBench paper: https://arxiv.org/abs/2412.07626
- Docling documentation: https://docling-project.github.io/docling/usage/
- MinerU repository: https://github.com/opendatalab/MinerU
- PaddleOCR repository: https://github.com/PaddlePaddle/PaddleOCR
- PP-StructureV3 documentation: https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-StructureV3/PP-StructureV3.html
