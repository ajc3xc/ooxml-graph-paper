"""PAPER-S7: the confirmatory paired Claude-without-vs-with-Meridian DOCX
editing benchmark. Generalizes PAPER-S20's commissioning harness (single
family, 2 fixtures, haiku) to the full design locked in
docs/paper-s7-protocol-v1.md: multiple task families, the real DocOps
development/validation/primary-holdout corpus
(manifests/paper-s7-corpus-manifest-v1.json), a long-horizon K-pair sweep, and
a confirmatory model.

A "chain" is the actual long-horizon unit per docs/paper-s9-long-horizon-
benchmark-protocol-v0.md section 4: K forward+inverse pairs of the SAME
family, run against the SAME document and arm, each pair its own fresh
process (so process/session round trips = K for BOTH arms symmetrically,
by construction -- see that section's confound warning), with pair i+1
starting from pair i's own inverse output. After the full chain, the final
document is compared against the ORIGINAL pristine paragraphs -- the
strongest available test of whether repeated insert+remove cycles introduce
cumulative drift even when each cycle nominally undoes itself.

Word-COM milestones (two-tier verification, protocol section 5): once at
chain start (the pristine input), then once after every pair -- never after
every raw tool call.
"""
from __future__ import annotations

import concurrent.futures
import dataclasses
import datetime
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_anchor_prober import (  # noqa: E402
    resolve_body_anchor,
    resolve_para_id_by_marker_text,
    resolve_section_reorder_plan,
)
from docx_trial_broker import (  # noqa: E402
    TrialSpec,
    _paragraph_texts,
    generate_bibliography_pair,
    generate_caption_forward,
    generate_caption_inverse,
    generate_citation_pair,
    generate_section_reorder_pair,
    new_marker,
)
from docx_trial_evaluator import (  # noqa: E402
    grade_forward_trial,
    grade_forward_trial_inline,
    grade_forward_trial_reorder,
    grade_inverse_trial,
    grade_inverse_trial_inline,
    grade_inverse_trial_reorder,
)
from claude_pair_runner import audit_isolation, run_trial  # noqa: E402
from word_receipt_watchdog import word_receipt_with_orphan_diagnostics  # noqa: E402

_WORD_RECEIPT_TIMEOUT_SECONDS = 90.0
_FAMILIES = ("bibliography", "citation", "caption", "section_reorder")


def _milestone_word_receipt(docx_path: Path, out_dir: Path, *, milestone: str) -> dict[str, Any]:
    if not docx_path.is_file():
        return {"milestone": milestone, "status": "not_run", "reason": "input docx does not exist"}
    try:
        result = word_receipt_with_orphan_diagnostics(docx_path, out_dir, timeout=_WORD_RECEIPT_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        return {"milestone": milestone, "status": "not_run", "reason": f"{type(exc).__name__}: {exc}"}
    result["milestone"] = milestone
    result["status"] = result.get("render_receipt", {}).get("status", "unknown")
    return result


def probe_family_applicability(family: str, docx_path: Path) -> dict[str, Any]:
    """Determine, harness-side, whether this document supports this family at
    all -- an inapplicable family is reported as not_applicable, never forced
    or silently dropped (PAPER-S9 protocol's own corpus-heterogeneity design:
    not every document need support every template)."""
    if family in ("bibliography",):
        return {"applicable": True}
    if family in ("citation", "caption"):
        anchor = resolve_body_anchor(docx_path)
        if not anchor["found"]:
            return {"applicable": False, "reason": anchor["reason"]}
        return {"applicable": True, "anchor": anchor}
    if family == "section_reorder":
        plan = resolve_section_reorder_plan(docx_path)
        if not plan["found"]:
            return {"applicable": False, "reason": plan["reason"]}
        return {"applicable": True, "plan": plan}
    raise ValueError(f"unknown family {family!r}")


def _build_pair_specs(
    family: str, doc_label: str, docx_path: Path, marker: str, applicability: dict[str, Any],
) -> tuple[TrialSpec, TrialSpec | None]:
    """Returns (forward, inverse-or-None). inverse is None only for caption,
    whose inverse args cannot be built until the forward trial's own output
    is inspected -- see resolve_para_id_by_marker_text."""
    if family == "bibliography":
        return generate_bibliography_pair(doc_label, docx_path, marker)
    if family == "citation":
        anchor = applicability["anchor"]
        return generate_citation_pair(
            doc_label, docx_path, marker, anchor["anchor_para_id"], anchor["anchor_text_snippet"],
        )
    if family == "caption":
        anchor = applicability["anchor"]
        forward = generate_caption_forward(
            doc_label, docx_path, marker, anchor["anchor_para_id"], anchor["anchor_text_snippet"],
        )
        return forward, None
    if family == "section_reorder":
        plan = applicability["plan"]
        return generate_section_reorder_pair(
            doc_label, docx_path, marker,
            plan["section_id"], plan["section_heading_text"],
            plan["original_preceding_heading_para_id"], plan["original_preceding_heading_text"],
            plan["destination_heading_para_id"], plan["destination_heading_text"],
        )
    raise ValueError(f"unknown family {family!r}")


def _grade_forward(family: str, output_docx: Path, paragraphs_before: list[str], spec: TrialSpec, applicability: dict[str, Any]) -> dict[str, Any]:
    if family in ("bibliography", "caption"):
        return grade_forward_trial(output_docx, paragraphs_before, spec.marker_text)
    if family == "citation":
        return grade_forward_trial_inline(
            output_docx, paragraphs_before, applicability["anchor"]["anchor_full_text"], spec.marker_text,
        )
    if family == "section_reorder":
        return grade_forward_trial_reorder(output_docx, paragraphs_before, spec.marker_text)
    raise ValueError(f"unknown family {family!r}")


def _grade_inverse(family: str, output_docx: Path, paragraphs_before_forward: list[str], spec: TrialSpec) -> dict[str, Any]:
    if family in ("bibliography", "caption"):
        return grade_inverse_trial(output_docx, paragraphs_before_forward, spec.marker_text)
    if family == "citation":
        return grade_inverse_trial_inline(output_docx, paragraphs_before_forward, spec.marker_text)
    if family == "section_reorder":
        return grade_inverse_trial_reorder(output_docx, paragraphs_before_forward)
    raise ValueError(f"unknown family {family!r}")


def run_chain(
    family: str, doc_label: str, docx_path: Path, arm: str, k_pairs: int, model: str,
    run_root: Path, *, word_receipts_enabled: bool = True,
) -> dict[str, Any]:
    # Windows MAX_PATH (260 chars) is a real constraint here: chain_root
    # nests trial directories several levels deep under a long E: run root,
    # and DocOps doc_labels can be 60+ chars on their own -- truncate rather
    # than let a long label silently produce a WinError 267 deep in
    # subprocess creation.
    short_doc_label = doc_label[:32]
    chain_id = f"{short_doc_label}-{family}-{arm}-k{k_pairs}-{new_marker('c')}"
    chain_root = run_root / chain_id
    chain_root.mkdir(parents=True, exist_ok=True)

    applicability = probe_family_applicability(family, docx_path)
    if not applicability["applicable"]:
        return {
            "chain_id": chain_id, "doc_label": doc_label, "family": family, "arm": arm,
            "k_pairs": k_pairs, "model": model, "status": "not_applicable",
            "reason": applicability["reason"], "pairs": [],
        }

    original_paragraphs = _paragraph_texts(docx_path)
    receipts: list[dict[str, Any]] = []
    if word_receipts_enabled:
        receipts.append(_milestone_word_receipt(docx_path, chain_root / "receipts" / "chain-start", milestone="chain_start"))

    current_input = docx_path
    pairs: list[dict[str, Any]] = []
    chain_status = "completed"

    for pair_index in range(k_pairs):
        paragraphs_before_this_pair = _paragraph_texts(current_input)
        marker = new_marker(f"s7-{family}")
        forward_spec, inverse_spec = _build_pair_specs(family, doc_label, current_input, marker, applicability)
        forward_spec = dataclasses.replace(forward_spec, arm=arm, pair_index=pair_index, trial_id=f"p{pair_index}-forward")

        fwd_result = run_trial(forward_spec, chain_root, model=model)
        fwd_result["isolation_audit"] = audit_isolation(fwd_result)
        fwd_execution_ok = fwd_result.get("returncode") == 0 and not fwd_result.get("timed_out")
        fwd_grading = (
            _grade_forward(family, Path(fwd_result["output_docx_path"]), paragraphs_before_this_pair, forward_spec, applicability)
            if fwd_execution_ok else {"verdict": "not_run", "reason": "forward process did not complete"}
        )
        fwd_result["grading"] = fwd_grading
        if word_receipts_enabled and fwd_execution_ok:
            receipts.append(_milestone_word_receipt(Path(fwd_result["output_docx_path"]), chain_root / "receipts" / f"p{pair_index}-forward", milestone="after_pair_forward"))

        pair_record: dict[str, Any] = {"pair_index": pair_index, "forward": fwd_result}

        if not fwd_execution_ok:
            chain_status = "blocked"
            pairs.append(pair_record)
            break

        if inverse_spec is None:
            resolved = resolve_para_id_by_marker_text(Path(fwd_result["output_docx_path"]), forward_spec.marker_text)
            if not resolved["found"]:
                pair_record["inverse"] = None
                pair_record["inverse_resolution_error"] = resolved["reason"]
                chain_status = "blocked"
                pairs.append(pair_record)
                break
            inverse_spec = generate_caption_inverse(
                doc_label, Path(fwd_result["output_docx_path"]), forward_spec.trial_id, forward_spec.marker_text, resolved["para_id"],
            )

        inverse_spec = dataclasses.replace(
            inverse_spec, arm=arm, pair_index=pair_index, trial_id=f"p{pair_index}-inverse",
            input_docx=Path(fwd_result["output_docx_path"]),
        )
        inv_result = run_trial(inverse_spec, chain_root, model=model)
        inv_result["isolation_audit"] = audit_isolation(inv_result)
        inv_execution_ok = inv_result.get("returncode") == 0 and not inv_result.get("timed_out")
        inv_grading = (
            _grade_inverse(family, Path(inv_result["output_docx_path"]), paragraphs_before_this_pair, inverse_spec)
            if inv_execution_ok else {"verdict": "not_run", "reason": "inverse process did not complete"}
        )
        inv_result["grading"] = inv_grading
        if word_receipts_enabled and inv_execution_ok:
            receipts.append(_milestone_word_receipt(Path(inv_result["output_docx_path"]), chain_root / "receipts" / f"p{pair_index}-inverse", milestone="after_pair_inverse"))

        pair_record["inverse"] = inv_result
        pairs.append(pair_record)

        if not inv_execution_ok or inv_grading.get("verdict") != "pass":
            chain_status = "completed_with_failure"
            current_input = Path(inv_result["output_docx_path"]) if inv_execution_ok else current_input
            continue

        current_input = Path(inv_result["output_docx_path"])

    final_paragraphs = _paragraph_texts(current_input) if current_input.is_file() else None
    cumulative_fidelity = final_paragraphs == original_paragraphs if final_paragraphs is not None else False

    return {
        "chain_id": chain_id, "doc_label": doc_label, "family": family, "arm": arm,
        "k_pairs": k_pairs, "model": model, "status": chain_status,
        "pairs_completed": len(pairs), "cumulative_fidelity_after_k_cycles": cumulative_fidelity,
        "pairs": pairs, "word_com_receipts": receipts,
    }


def run_corpus_slice(
    corpus_manifest_path: Path, split: str, families: tuple[str, ...], k_values: tuple[int, ...],
    model: str, run_root: Path, *, max_workers: int = 4, word_receipts_enabled: bool = True,
) -> dict[str, Any]:
    manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    documents = [d for d in manifest["documents"] if d["s7_split"] == split]

    jobs = [
        (doc, family, k)
        for doc in documents
        for family in families
        for k in k_values
    ]

    run_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                run_chain, family, doc["doc_label"], Path(doc["docx_path"]), arm, k, model, run_root,
                word_receipts_enabled=word_receipts_enabled,
            ): (doc["doc_label"], family, arm, k)
            for doc, family, k in jobs
            for arm in ("control", "treatment")
        }
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                doc_label, family, arm, k = key
                results.append({
                    "chain_id": f"{doc_label}-{family}-{arm}-k{k}-EXCEPTION",
                    "doc_label": doc_label, "family": family, "arm": arm, "k_pairs": k,
                    "status": "harness_exception", "reason": f"{type(exc).__name__}: {exc}",
                    "pairs": [],
                })

    manifest_out = {
        "schema": "paper-s7-benchmark-slice-v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "split": split, "families": list(families), "k_values": list(k_values), "model": model,
        "document_count": len(documents), "chain_count": len(results),
        "chains": results,
    }
    out_path = run_root / "slice-manifest.json"
    out_path.write_text(json.dumps(manifest_out, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-manifest", type=Path, default=Path(r"E:\MeridianData\ooxml-graph-paper\manifests\paper-s7-corpus-manifest-v1.json"))
    parser.add_argument("--split", required=True, choices=["development", "validation", "primary_holdout"])
    parser.add_argument("--families", nargs="+", default=list(_FAMILIES))
    parser.add_argument("--k-values", nargs="+", type=int, default=[1])
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--no-word-receipts", action="store_true")
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args(argv)

    manifest = run_corpus_slice(
        args.corpus_manifest, args.split, tuple(args.families), tuple(args.k_values),
        args.model, args.run_root, max_workers=args.max_workers,
        word_receipts_enabled=not args.no_word_receipts,
    )

    counts: dict[str, int] = {}
    for chain in manifest["chains"]:
        status = chain.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps(counts, indent=2))
    print(f"Slice manifest: {args.run_root / 'slice-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
