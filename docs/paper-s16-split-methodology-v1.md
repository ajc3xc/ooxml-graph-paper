# PAPER-S16: frozen development/holdout split lanes and anti-overfitting gate (v1)

Status: methodology freeze across every data pool this project currently holds, per this
item's own gate: "no primary run with missing rights receipt, missing hash, missing
modality, unresolved privacy review, or cross-split source collision." This assigns every
existing pool to a lane rather than re-deriving new splits -- each pool's own audit (cited
below) is the evidence; this document's job is only to freeze the LANE taxonomy and the
assignment, not to re-run any screening.

## 1. Lane taxonomy (frozen)

| Lane | Meaning | Eligible for a primary (holdout) run? |
|---|---|---|
| `development` | Freely inspectable, freely re-run; used to debug harness/prompts. | No -- development-only. |
| `exposed_validation_regression` | Real, audited data, but already read/scored repeatedly by this project's own pipeline. Valid for regression re-exercise, never for a primary/confirmatory holdout claim. | No. |
| `clean_primary_holdout` | Audited (license, PII/privacy, hash, package-integrity) AND confirmed unexposed to the specific pipeline being evaluated. Evaluated exactly once per protocol version. | Yes -- this is the only lane a primary-holdout claim may draw from. |
| `research_only_quarantine` | Real data, present on disk, with SOME screening (e.g. integrity/feature scan) but NOT full per-file license/privacy review. Usable for exploratory/screening work only. | No. |
| `context_only` | A real, useful reference (published benchmark numbers, a different-modality corpus) that answers a related but distinct question and must never be pooled with this project's own scored claims. | No -- never scored as this project's own result. |
| `rejected_held` | Explicitly excluded for a real, specific, documented cause (PII, safeguarding, license). Permanently excluded, not a pool to revisit casually. | No. |

## 2. Lane assignment (frozen)

| Pool | Lane | Evidence |
|---|---|---|
| 127-document Meridian gold set (tier1/tier2/tier3) | `exposed_validation_regression` | PAPER-S12's holdout-exposure audit (`docs/paper-s12-holdout-exposure-audit-v0.md`) found all 127 already read/scored 5+ times by this project's own extraction/scoring pipeline. Per PAPER-S9 protocol section 2, this pool is regression-only for the S7/S9 agentic-editing track and must never be its headline/primary corpus. |
| DocOps `development`+`smoke` DocOps stages (12 single-.docx tasks, PAPER-S7's `development` split) | `development` | `manifests/paper-s7-corpus-manifest-v1.json`; freely used for the harness-debugging development slice already run (2026-08-30). |
| DocOps `scale_up` stage (12 single-.docx tasks, PAPER-S7's `validation` split) | Functions as this project's `exposed_validation_regression` equivalent for the S7/S9 track once results are inspected during protocol iteration -- inspectable per `docs/paper-s9-long-horizon-benchmark-protocol-v0.md` section 3's "validation" stage, but not re-touched after a specific validation-slice failure without re-declaring the protocol version (`docs/paper-s7-protocol-v1.md` section 8). | `docs/paper-s13-docops-word-audit-v1.md` (license, per-file SHA-256, package-integrity, pattern-based PII scan); PAPER-S12 confirms genuinely unexposed to this project's own pipeline before this project's own S7 run started. |
| DocOps `final_holdout` stage (14 single-.docx tasks, PAPER-S7's `primary_holdout` split) | `clean_primary_holdout` | Same PAPER-S13/S12 audit as above, PLUS never opened/read/used for debugging during PAPER-S7's development slice (per DocOps' own preregistered split rule, reused verbatim: "final_holdout is never opened, read, or used for debugging... evaluated exactly once"). This is the only pool in this project currently eligible to back a PAPER-S7 primary-holdout claim. |
| `batch-500-v1` (500 docx-corpus documents, PAPER-S6) | `research_only_quarantine` | Only OMML-presence + package-integrity screened; explicitly `privacy_pii_review: not_assessed` per-file (PAPER-S6 recon, 2026-08-30). Usable for further screening labor (a disclosed, separate future recommendation), never as primary-run input as-is. |
| 39 raw-pool documents outside the 127 gold set (23 docx-corpus + 16 omega-officeval) | `rejected_held` | PAPER-S11's independent whole-file SHA-256 diff confirms these are real, specific, adjudicated exclusions (PII/safeguarding cause), not merely unpromoted. Permanently excluded. |
| MS thesis page-30 formatting fixture (`f9194db0`'s own regression fixture) | `context_only` | **This item's own explicit instruction: do not call this pool "clean validation."** It is a single, hand-authored regression fixture for one specific section-terminology bug, not an audited, held-out corpus sample -- useful as regression context for that one fix, never as evidence for a corpus-level split claim. |
| DocBank (public PDF/layout benchmark) | `context_only` | `comparator-contract-v0.md` section 1.B: a public PDF/token-layout benchmark, not a paired DOCX/OOXML gold set -- reported as a separate context track, never pooled with native-OOXML-track scores. |

## 3. Cross-split source-collision check (this item's own gate)

- The DocOps split (`manifests/docops/docops_prereg_split_v1.json`) is defined at the whole
  task-directory level (never a sub-file), matching `comparator-contract-v0.md` section 4's
  "split by document, never by page" -- confirmed no task directory appears in more than one
  DocOps stage.
- The 127-document gold set and the DocOps pool are disjoint sources entirely (different
  acquisition pipelines, different hosts) -- no collision is possible between the
  `exposed_validation_regression` and `clean_primary_holdout` lanes above.
- `batch-500-v1` was fetched with `seed 20260830, excluding the 90 already sampled` (PAPER-S6's
  own notes) -- explicitly deduplicated against the existing 90-document docx-corpus sample
  before being placed in `research_only_quarantine`.

## 4. What this item does not do

This freezes the LANE taxonomy and assignment; it does not re-run any screening, does not
build a new split (PAPER-S7's corpus reuses DocOps' own preregistered split rather than
re-deriving one -- see `docs/paper-s7-protocol-v1.md` section 1), and does not resolve
`research_only_quarantine`/`rejected_held` pools into a usable primary-run source. A
corpus-agnostic split-ASSIGNMENT algorithm (family-level bin-packing against target
fractions, for a future pool that does not already have its own preregistered split) is
implemented and tested separately at `tools/build_dev_validation_holdout_split.py`, kept as
reusable infrastructure rather than applied here, since DocOps already had a fixed, dated,
pre-existing split this item's own gate says to reuse rather than override.
