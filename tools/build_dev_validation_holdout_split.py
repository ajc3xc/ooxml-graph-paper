"""PAPER-S16: development/validation/primary-holdout split assignment.

Implements docs/paper-s9-long-horizon-benchmark-protocol-v0.md section 3's split rule for the
agentic-editing benchmark corpus: staged disclosure order (development -> validation ->
primary-holdout), assigned at DOCUMENT-FAMILY granularity, never at the individual-document
level -- "keep near-duplicates, same-source documents, and derivative versions of one another in
the SAME split" (section 3's leakage rule). A document family is any set of documents this
project's own corpus manifest already considers related (same source template, same author/
source batch, or an explicitly recorded near-duplicate group) -- the caller supplies that
grouping; this module never infers it from content similarity itself, to avoid quietly baking in
an unvalidated similarity heuristic as if it were the leakage ground truth.

This module is deliberately corpus-agnostic: it takes a family->document-count mapping and a
fixed seed and returns a family->split assignment. It does not download, screen, or select which
documents exist -- that is a separate, corpus-specific step (see docs/paper-s7-protocol-v1.md).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
from pathlib import Path
from typing import Any

_SPLITS = ("development", "validation", "primary_holdout")


@dataclasses.dataclass(frozen=True)
class FamilySplitTarget:
    """Target FRACTION of total documents (not families) per split. Family assignment is
    then a bin-packing problem against these fractions, not an exact per-family quota --
    exact document-count balance is not achievable when families vary in size and must stay
    intact, so this reports the ACHIEVED fractions alongside the requested ones rather than
    silently claiming the requested split was hit exactly."""
    development: float = 0.40
    validation: float = 0.30
    primary_holdout: float = 0.30

    def __post_init__(self) -> None:
        total = self.development + self.validation + self.primary_holdout
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"split fractions must sum to 1.0, got {total}")


def assign_family_splits(
    family_sizes: dict[str, int],
    *,
    seed: int,
    targets: FamilySplitTarget = FamilySplitTarget(),
) -> dict[str, Any]:
    """Assign every family to exactly one split via a greedy largest-family-first bin-pack
    against the target document-count fractions, using `seed` only to break ties among
    equal-sized families (so the assignment is deterministic and reproducible, not sensitive
    to whatever order the caller happened to build the dict in).

    Greedy-largest-first is a deliberate choice over a more "fair" approach: because a split
    must never break a family apart, a small number of large families can make hitting exact
    fractions to the document impossible. This is not a modeling detail hidden from the
    report -- achieved_fractions in the return value must be checked against requested_targets
    before trusting the split has the intended balance, and reported in the split manifest.
    """
    if not family_sizes:
        raise ValueError("family_sizes must be non-empty")
    if any(size <= 0 for size in family_sizes.values()):
        raise ValueError("every family must have a positive document count")

    total_documents = sum(family_sizes.values())
    target_counts = {
        "development": targets.development * total_documents,
        "validation": targets.validation * total_documents,
        "primary_holdout": targets.primary_holdout * total_documents,
    }

    rng = random.Random(seed)
    families = list(family_sizes.items())
    # Deterministic tie-break: shuffle once under the fixed seed, then stable-sort by size
    # descending -- equal-size families keep the seed-shuffled relative order instead of
    # whatever order the input dict happened to have.
    rng.shuffle(families)
    families.sort(key=lambda item: item[1], reverse=True)

    assigned: dict[str, str] = {}
    running_counts = {split: 0 for split in _SPLITS}
    for family_id, size in families:
        # Assign to whichever split is currently furthest BELOW its target count (in absolute
        # documents), so large families get placed where they cause the least imbalance.
        deficits = {
            split: target_counts[split] - running_counts[split] for split in _SPLITS
        }
        chosen = max(deficits, key=lambda split: deficits[split])
        assigned[family_id] = chosen
        running_counts[chosen] += size

    achieved_fractions = {
        split: (running_counts[split] / total_documents if total_documents else 0.0)
        for split in _SPLITS
    }

    return {
        "schema": "paper-s16-split-manifest-v1",
        "seed": seed,
        "total_documents": total_documents,
        "total_families": len(family_sizes),
        "requested_fractions": {
            "development": targets.development,
            "validation": targets.validation,
            "primary_holdout": targets.primary_holdout,
        },
        "achieved_fractions": achieved_fractions,
        "achieved_document_counts": running_counts,
        "family_assignment": assigned,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "family_sizes_json", type=Path,
        help="path to a JSON object mapping family_id -> document count",
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--development-fraction", type=float, default=0.40)
    parser.add_argument("--validation-fraction", type=float, default=0.30)
    parser.add_argument("--primary-holdout-fraction", type=float, default=0.30)
    args = parser.parse_args(argv)

    family_sizes = json.loads(args.family_sizes_json.read_text(encoding="utf-8"))
    targets = FamilySplitTarget(
        development=args.development_fraction,
        validation=args.validation_fraction,
        primary_holdout=args.primary_holdout_fraction,
    )
    result = assign_family_splits(family_sizes, seed=args.seed, targets=targets)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "family_assignment"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
