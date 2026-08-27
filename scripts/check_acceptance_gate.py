"""PAPER-20: integrated native-Word product acceptance gate.

Runs every fail-closed check named in PAPER-20's own sprint-item scope and produces one
machine-readable JSON report plus a human-readable summary. This script is the gate
itself, not a claim that the gate currently passes -- run it and read the actual
`overall_pass` field; do not assume.

Usage: pixi run python scripts/check_acceptance_gate.py
Writes: E:\\MeridianData\\ooxml-graph-paper\\manifests\\acceptance-gate-<UTC-ISO-timestamp>.json
"""
from __future__ import annotations

import datetime
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

# Windows consoles default to a legacy codepage (cp1252) that cannot encode
# equation/math Unicode characters (e.g. U+2211 SUM) that legitimately appear in
# check detail strings below -- force UTF-8 for stdout so a print never crashes the
# gate after its actual checks (and the JSON report) have already completed.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(r"C:\Users\13144\Documents\Meridian\repository")
PAPER_ROOT = Path(r"C:\Users\13144\Documents\Meridian\ooxml-graph-paper")
DATA_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper")

# The paper may execute against an intentionally dirty parent checkout while
# Meridian Docs hardening is still being developed.  These are the product
# files whose exact bytes must be pinned for a reproducible dirty-snapshot run.
# The full Git status/diff is also fingerprinted, so an unrelated concurrent
# edit still invalidates the run rather than being silently ignored.
PRODUCT_SNAPSHOT_PATHS = (
    Path("extensions/meridian-docs/meridian_docs/docs_intel.py"),
    Path("extensions/meridian-docs/meridian_docs/ooxml_integrity.py"),
    Path("extensions/meridian-docs/meridian_docs/render_gate.py"),
    Path("extensions/meridian-docs/meridian_docs/server.py"),
)

sys.path.insert(0, str(REPO_ROOT / "extensions" / "meridian-docs"))


def _check(name: str, category: str, passed: bool, detail: str, blocking: bool = True) -> dict:
    return {"name": name, "category": category, "passed": passed, "blocking": blocking, "detail": detail}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def capture_parent_snapshot() -> dict:
    """Capture a byte-stable identity for the shared parent checkout.

    This deliberately does not require a clean worktree.  A dirty run is
    reproducible only if HEAD, the complete porcelain state, the complete
    binary diff, and the product files used by the harness are unchanged from
    start to finish.  The diff itself is never embedded in the report; only
    its digest and status lines are retained.
    """
    def git_bytes(*args: str) -> bytes:
        proc = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True,
            timeout=60, check=True,
        )
        return proc.stdout

    status_bytes = git_bytes("status", "--porcelain=v1", "-z", "--untracked-files=all")
    diff_bytes = git_bytes("diff", "--binary", "HEAD")
    head = git_bytes("rev-parse", "HEAD").decode("ascii", errors="strict").strip()
    status_entries = [
        entry.decode("utf-8", errors="replace")
        for entry in status_bytes.split(b"\0") if entry
    ]
    product_hashes = {}
    for relative in PRODUCT_SNAPSHOT_PATHS:
        path = REPO_ROOT / relative
        product_hashes[relative.as_posix()] = (
            _sha256(path.read_bytes()) if path.is_file() else None
        )
    return {
        "head": head,
        "dirty": bool(status_entries),
        "status_entries": status_entries,
        "status_sha256": _sha256(status_bytes),
        "diff_sha256": _sha256(diff_bytes),
        "product_file_sha256": product_hashes,
    }


def parent_snapshot_equal(before: dict, after: dict) -> bool:
    """Compare the immutable identity fields, excluding human-facing status text."""
    keys = ("head", "dirty", "status_sha256", "diff_sha256", "product_file_sha256")
    return all(before.get(key) == after.get(key) for key in keys)


def changed_snapshot_fields(before: dict, after: dict) -> list[str]:
    """Return the fingerprint fields that differ, for actionable receipts."""
    keys = ("head", "dirty", "status_sha256", "diff_sha256", "product_file_sha256")
    return [key for key in keys if before.get(key) != after.get(key)]


def check_semantic_omml_hardening() -> list[dict]:
    """Semantic OMML loss / unsupported fallback text / empty operands -- exercises
    PAPER-13's hardened validator + converter directly, not by re-reading its notes."""
    from meridian_docs import docs_intel

    results = []

    # Empty operands (PAPER-13's Class 6 fix) must fail closed.
    empty_cases = [
        (r"\frac{}{}", "empty fraction"),
        (r"\min_{x} f(x)", "min with empty func argument"),
    ]
    for latex, label in empty_cases:
        omml = docs_intel.latex_to_omml_local(latex)
        results.append(_check(
            f"empty_operand_rejected:{label}", "semantic_omml_loss",
            passed=omml is None,
            detail=f"latex_to_omml_local({latex!r}) = {omml!r} (expected None)",
        ))

    # Fallback text (Class 4) must be rejected by the validator directly.
    m = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    fallback_payload = f'<m:oMath xmlns:m="{m}"><m:r><m:t>fraction a over b</m:t></m:r></m:oMath>'
    try:
        docs_intel._validate_omml_structure(fallback_payload)
        fallback_rejected = False
        fallback_detail = "validator ACCEPTED flattened fallback text -- should have raised"
    except ValueError as exc:
        fallback_rejected = True
        fallback_detail = str(exc)
    results.append(_check(
        "fallback_text_rejected", "unsupported_fallback_text",
        passed=fallback_rejected, detail=fallback_detail,
    ))

    # Correct, structurally valid input must still be ACCEPTED (the gate must not be
    # so strict it rejects legitimate math -- a false-fail is as real a bug as a
    # false-pass for a fail-closed gate).
    correct_omml = docs_intel.latex_to_omml_local(r"\frac{1}{2}")
    results.append(_check(
        "correct_equation_still_accepted", "semantic_omml_loss",
        passed=correct_omml is not None,
        detail=f"latex_to_omml_local(r'\\frac{{1}}{{2}}') = {correct_omml!r} (expected non-None)",
    ))

    # Known, documented, NOT-yet-fixed semantic loss (PAPER-11 Class 2) -- reported
    # as a non-blocking finding, not silently ignored and not falsely claimed fixed.
    sum_omml = docs_intel.latex_to_omml_local(r"\sum_{i=1}^{n} x_i")
    uses_nary = sum_omml is not None and "nary" in sum_omml
    results.append(_check(
        "sum_uses_true_nary_operator", "semantic_omml_loss",
        passed=uses_nary,
        detail=(
            "known open gap (omml-builder-audit-v0.md Class 2, not in PAPER-13's scope): "
            f"\\sum_i x_i converts to sSubSup side-scripts, not <m:nary>: {sum_omml!r}"
        ),
        blocking=False,
    ))

    return results


def check_render_capability() -> dict:
    """Renderer unavailable -- calls the REAL render_gate.check_render_capability
    against a genuine synthetic fixture, does not trust any cached probe manifest."""
    from meridian_docs import docs_intel

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{w}">'
        f'<w:body><w:p><w:r><w:t>Acceptance gate render probe.</w:t></w:r></w:p></w:body></w:document>'
    )
    fixture_path = DATA_ROOT / "renders" / "acceptance-gate-probe" / "probe.docx"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(fixture_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", package_rels)
        zf.writestr("word/document.xml", document_xml)

    try:
        result = docs_intel.render_gate.check_render_capability(str(fixture_path))
    except Exception as exc:  # noqa: BLE001 -- a broken checker is itself a gate failure, not a crash
        result = {"status": "failed", "reason": f"check_render_capability raised {type(exc).__name__}: {exc}"}

    return _check(
        "render_backend_available", "renderer_unavailable",
        passed=result.get("status") == "rendered",
        detail=f"check_render_capability real result: {result!r}",
    )


def check_package_integrity() -> dict:
    """ID/reference/relationship errors -- runs ooxml_integrity.validate_docx_package
    against the same probe fixture used above."""
    from meridian_docs import docs_intel

    fixture_path = DATA_ROOT / "renders" / "acceptance-gate-probe" / "probe.docx"
    raw = fixture_path.read_bytes()
    report = docs_intel.ooxml_integrity.validate_docx_package(raw)
    return _check(
        "package_integrity_clean", "id_reference_relationship_errors",
        passed=bool(report.get("ok")),
        detail=f"validate_docx_package: {report!r}",
    )


def check_parent_repo_worktree_clean(
    initial_snapshot: dict, allow_dirty_parent: bool,
) -> dict:
    """Require a clean root, or an explicitly enabled stable dirty snapshot.

    The dirty mode is intentionally not reported as ``parent_repo_worktree_clean``
    passing.  It records a separate non-clean execution contract and fails if
    any parent state changes while this gate is running.
    """
    current = capture_parent_snapshot()
    stable = parent_snapshot_equal(initial_snapshot, current)
    changed = changed_snapshot_fields(initial_snapshot, current)
    if not current["dirty"]:
        passed = stable
        detail = (
            f"parent checkout is clean and stable at HEAD {current['head']}"
            if passed else f"parent checkout changed during gate execution: {changed}"
        )
        name = "parent_repo_worktree_clean"
    elif allow_dirty_parent:
        passed = stable
        detail = (
            f"dirty-parent snapshot explicitly allowed; {len(current['status_entries'])} "
            f"entries pinned at HEAD {current['head']} with diff_sha256="
            f"{current['diff_sha256']}"
            if passed else f"dirty parent snapshot changed during gate execution: {changed}"
        )
        name = "parent_repo_dirty_snapshot_stable"
    else:
        passed = False
        detail = (
            f"{len(current['status_entries'])} porcelain entries in {REPO_ROOT}; "
            "rerun with --allow-dirty-parent only when the shared checkout is frozen "
            "and the resulting snapshot is recorded"
        )
        name = "parent_repo_worktree_clean"
    return _check(name, "dirty_unclaimed_worktree", passed, detail)


def check_parent_snapshot_unchanged(initial_snapshot: dict) -> dict:
    """Final fail-closed guard against concurrent edits after the main check."""
    final = capture_parent_snapshot()
    passed = parent_snapshot_equal(initial_snapshot, final)
    return _check(
        "parent_snapshot_unchanged_throughout_gate", "reproducibility",
        passed,
        (
            "initial and final parent checkout fingerprints match"
            if passed else
            f"parent checkout fingerprint changed during gate execution: "
            f"{changed_snapshot_fields(initial_snapshot, final)}; discard run"
        ),
    )


def check_corpus_provenance() -> dict:
    """Missing corpus provenance -- a real gold-set manifest must exist and be
    non-empty; benchmark-preregistration-v0.md's own checklist is the source of truth
    for whether one has actually been built."""
    prereg = PAPER_ROOT / "docs" / "benchmark-preregistration-v0.md"
    gold_manifest_dir = DATA_ROOT / "gold"
    gold_exists = gold_manifest_dir.exists() and any(gold_manifest_dir.iterdir()) if gold_manifest_dir.exists() else False
    return _check(
        "gold_corpus_provenance_exists", "missing_corpus_provenance",
        passed=gold_exists,
        detail=(
            f"{gold_manifest_dir} " + ("exists and is non-empty" if gold_exists else "does not exist or is empty")
            + f" -- see {prereg} Section 10 Acceptance Checklist (0/10 as of PAPER-19)"
        ),
    )


def check_untracked_artifacts() -> dict:
    """Untracked artifacts -- specifically new, unreviewed files under the parent
    repo's extensions/meridian-docs product code (not docs/tests, which are expected
    to accumulate during active sprint work)."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", "extensions/meridian-docs/meridian_docs"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    untracked = [ln for ln in proc.stdout.splitlines() if ln.startswith("??")]
    return _check(
        "no_untracked_product_code", "untracked_artifacts",
        passed=len(untracked) == 0,
        detail=f"untracked entries under extensions/meridian-docs/meridian_docs: {untracked!r}",
    )


PAPER8_APPROVAL_ARTIFACT = DATA_ROOT / "manifests" / "paper8-human-approval.json"


def check_word_authority_gate() -> dict:
    """Formal PAPER-8 human Word authority -- reads a durable, offline-checkable
    approval artifact rather than either (a) a live network call to the Meridian
    board, which would break this script's offline-runnable design, or (b) an
    unconditional False that can never reflect a real approval. Fail-closed on
    every anomaly: missing file, malformed JSON, missing/false `approved` field,
    or a missing `meridian_sprint_item` provenance block are all NOT satisfied.
    The artifact records a decision that already happened in the Meridian sprint
    tracker (see its own `meridian_sprint_item` field) -- this check does not
    grant approval, it verifies a durable record of one."""
    if not PAPER8_APPROVAL_ARTIFACT.is_file():
        return _check(
            "paper8_human_authority_approved", "human_authority", passed=False,
            detail=f"no approval artifact at {PAPER8_APPROVAL_ARTIFACT} -- defaults to NOT satisfied",
        )
    try:
        record = json.loads(PAPER8_APPROVAL_ARTIFACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(
            "paper8_human_authority_approved", "human_authority", passed=False,
            detail=f"approval artifact at {PAPER8_APPROVAL_ARTIFACT} could not be read/parsed: {exc}",
        )
    approved = record.get("approved") is True
    provenance = record.get("meridian_sprint_item")
    has_provenance = isinstance(provenance, dict) and provenance.get("item_id") and provenance.get("status") == "done"
    passed = approved and has_provenance
    return _check(
        "paper8_human_authority_approved", "human_authority", passed=passed,
        detail=(
            f"approval artifact: approved={record.get('approved')!r}, "
            f"approved_by={record.get('approved_by')!r}, approved_at={record.get('approved_at')!r}, "
            f"scope={record.get('scope')!r}, provenance_item={provenance!r}"
        ),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-dirty-parent", action="store_true",
        default=os.environ.get("MERIDIAN_ALLOW_DIRTY_PARENT") == "1",
        help=(
            "run against a dirty parent checkout only if its complete Git and "
            "product-file fingerprint remains unchanged; never pretends it is clean"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    initial_parent_snapshot = capture_parent_snapshot()
    checks: list[dict] = []
    parent_check = check_parent_repo_worktree_clean(initial_parent_snapshot, args.allow_dirty_parent)
    checks.append(parent_check)

    # A normal gate invocation must fail before rendering or running semantic
    # checks when the shared parent is dirty.  The explicit dirty mode is the
    # only route that permits expensive checks against that checkout.
    preflight_blocked = (
        initial_parent_snapshot["dirty"] and not args.allow_dirty_parent
    ) or not parent_check["passed"]
    skipped_checks: list[str] = []
    if preflight_blocked:
        skipped_checks.extend([
            "semantic_omml_hardening",
            "render_backend_available",
            "package_integrity_clean",
            "gold_corpus_provenance_exists",
            "no_untracked_product_code",
            "paper8_human_authority_approved",
        ])
    else:
        checks.extend(check_semantic_omml_hardening())
        checks.append(check_render_capability())
        checks.append(check_package_integrity())
        checks.append(check_corpus_provenance())
        checks.append(check_untracked_artifacts())
        checks.append(check_word_authority_gate())

    final_parent_snapshot = capture_parent_snapshot()
    checks.append(check_parent_snapshot_unchanged(initial_parent_snapshot))

    blocking_failures = [c for c in checks if c["blocking"] and not c["passed"]]
    non_blocking_findings = [c for c in checks if not c["blocking"] and not c["passed"]]
    overall_pass = len(blocking_failures) == 0

    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gate": "PAPER-20 integrated native-Word product acceptance",
        "overall_pass": overall_pass,
        "verdict": (
            "PASS -- PAPER-15 may proceed" if overall_pass
            else f"FAIL -- {len(blocking_failures)} blocking check(s) failed; PAPER-15 must NOT run"
        ),
        "checks": checks,
        "blocking_failures": [c["name"] for c in blocking_failures],
        "non_blocking_findings": [c["name"] for c in non_blocking_findings],
        "skipped_checks": skipped_checks,
        "execution_contract": {
            "parent_checkout_mode": (
                "dirty_snapshot_allowed" if args.allow_dirty_parent else "clean_required"
            ),
            "parent_snapshot": initial_parent_snapshot,
            "final_parent_snapshot": final_parent_snapshot,
            "snapshot_changed_fields": changed_snapshot_fields(
                initial_parent_snapshot, final_parent_snapshot,
            ),
            "requires_external_checkout_freeze": True,
            "product_snapshot_paths": [p.as_posix() for p in PRODUCT_SNAPSHOT_PATHS],
        },
    }

    DATA_ROOT.joinpath("manifests").mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = DATA_ROOT / "manifests" / f"acceptance-gate-{ts}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"=== {report['gate']} ===")
    print(f"Verdict: {report['verdict']}")
    print(f"Report written to: {out_path}")
    print()
    for c in checks:
        mark = "PASS" if c["passed"] else ("FAIL" if c["blocking"] else "FINDING")
        print(f"[{mark:7s}] {c['category']:32s} {c['name']}")
        if not c["passed"]:
            print(f"          {c['detail']}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
