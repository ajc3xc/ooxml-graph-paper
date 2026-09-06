"""Exploratory pilot: can Claude+Meridian vs Claude+generic-tools correctly
identify REAL formatting-compliance violations in a Word document, given a
prose description of the style rule?

Deliberately NOT part of the PAPER-S7 family system: this is a read-only
DIAGNOSIS task (find and report violations), not an edit/inverse pair, so it
doesn't fit that architecture's forward+inverse chain model at all. Reuses
claude_pair_runner.run_trial directly for the exact same arm-isolation
machinery (control: generic Read/Write/Edit/Bash, zero Meridian MCP access;
treatment: exactly one bounded Meridian tool call, zero generic editing
tools) every other trial in this project already relies on.

Two fixtures, both confirmed directly against the real
docs_intel.audit_equation_style function before this pilot was run:
  - `hard_equation_style_violations.docx`: exactly two known violations
    (misaligned_equation -- left-aligned instead of the default policy's
    centered; missing_trailing_punctuation -- no punctuation after the
    equation).
  - `hard_equation_style_compliant.docx`: a negative control -- a correctly
    centered equation with trailing punctuation, zero real findings. Tests
    for FALSE POSITIVES (does either arm hallucinate a violation that isn't
    there?), not just recall on real ones.

Grading here is necessarily cruder than PAPER-S7's structural checks: each
arm's own free-text final report is scanned for keyword evidence of each
violation, then compared against the fixture's known ground truth (for the
compliant fixture, "correct" means NEITHER keyword class appears). This is
exploratory, not confirmatory -- two documents, one trial per arm each,
reported honestly as pilot data points, not pooled with any locked corpus
or statistics.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_pair_runner import audit_isolation, run_trial  # noqa: E402
from docx_trial_broker import TrialSpec  # noqa: E402

FIXTURES = {
    "violations": Path(r"E:\MeridianData\ooxml-graph-paper\raw\hard-fixtures-v1\hard_equation_style_violations.docx"),
    "compliant": Path(r"E:\MeridianData\ooxml-graph-paper\raw\hard-fixtures-v1\hard_equation_style_compliant.docx"),
    "numbering": Path(r"E:\MeridianData\ooxml-graph-paper\raw\hard-fixtures-v1\hard_equation_numbering_violations.docx"),
}

_ALIGNMENT_PUNCTUATION_PROMPT = (
    "You are reviewing a Word document at the path given to you for formatting "
    "compliance against this style rule: every STANDALONE display equation (an "
    "equation that is the only content in its own paragraph) must be (a) "
    "horizontally CENTERED, and (b) followed immediately by trailing punctuation "
    "(a period, comma, semicolon, or colon).\n\n"
    "Check every equation in the document against both parts of this rule and "
    "report every violation you find -- which equation, which part of the rule "
    "it violates, and why. This is a READ-ONLY review: do not modify the "
    "document. When finished, give your findings as a clear final message "
    "(not a tool call)."
)

_NUMBERING_PROMPT = (
    "You are reviewing a Word document at the path given to you for formatting "
    "compliance against this style rule: the document contains table-numbered "
    "equations (a table row whose first cell holds an equation and whose second "
    "cell holds a parenthesized number like \"(1)\"). Every equation number must "
    "be UNIQUE (no two equations share the same number), and the numbers must "
    "form a CONTIGUOUS sequence starting from 1 with no gaps.\n\n"
    "Check every table-numbered equation against both parts of this rule and "
    "report every violation you find -- which equations are involved, which "
    "part of the rule is violated, and why. This is a READ-ONLY review: do not "
    "modify the document. When finished, give your findings as a clear final "
    "message (not a tool call)."
)

_TASK_PROMPTS = {
    "violations": _ALIGNMENT_PUNCTUATION_PROMPT,
    "compliant": _ALIGNMENT_PUNCTUATION_PROMPT,
    "numbering": _NUMBERING_PROMPT,
}


def build_specs(doc_label: str, fixture: Path) -> tuple[TrialSpec, TrialSpec]:
    prompt = _TASK_PROMPTS[doc_label]
    control = TrialSpec(
        trial_id=f"{doc_label}-control-forward",
        doc_label=doc_label,
        arm="control",
        direction="forward",
        family="formatting_compliance",
        input_docx=fixture,
        prompt=prompt,
        marker_text="n/a",
        treatment_tool="audit_equation_style",
        treatment_args={},
    )
    treatment = TrialSpec(
        trial_id=f"{doc_label}-treatment-forward",
        doc_label=doc_label,
        arm="treatment",
        direction="forward",
        family="formatting_compliance",
        input_docx=fixture,
        prompt=prompt,
        marker_text="n/a",
        treatment_tool="audit_equation_style",
        treatment_args={},
    )
    return control, treatment


_ALIGNMENT_KEYWORDS = ("center", "centred", "align", "left-align", "left align", "jc")
_PUNCTUATION_KEYWORDS = ("punctuation", "period", "trailing", "comma", "semicolon", "colon", "missing a .")
# A naive "does the topic get mentioned at all" check can't tell "this IS a
# violation" apart from "confirmed compliant, no violation here" -- a correct
# compliance report necessarily discusses both dimensions either way. Found
# live (2026-09-06): both arms correctly reported the compliant fixture as
# fully compliant on both dimensions, but the naive keyword check flagged
# both as "wrong" simply because they used the words "center"/"punctuation"
# while CONFIRMING compliance. This phrase-level check for an explicit
# compliance claim is still a crude proxy for real intent, not a
# replacement for reading the actual report, but it's what let that mistake
# get caught before being reported as a real finding.
_COMPLIANT_CLAIM_PHRASES = (
    "no violation", "no violations", "fully compliant", "is compliant",
    "compliant with both", "zero findings", "zero violations",
)
_DUPLICATE_NUMBER_KEYWORDS = ("duplicate", "same number", "both numbered", "reused", "repeated number")
_NUMBER_GAP_KEYWORDS = ("gap", "missing", "skip", "not contiguous", "out of sequence")


def _mentions_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def grade(result: dict, doc_label: str) -> dict:
    cj = result.get("claude_json_result") or {}
    report_text = str(cj.get("result") or "")
    claims_fully_compliant = _mentions_any(report_text, _COMPLIANT_CLAIM_PHRASES)

    if doc_label == "numbering":
        mentions_duplicate = _mentions_any(report_text, _DUPLICATE_NUMBER_KEYWORDS)
        mentions_gap = _mentions_any(report_text, _NUMBER_GAP_KEYWORDS)
        # Ground truth: equations 1&2 share number "(1)" (duplicate), and
        # number 2 is skipped (gap) -- correct means the report catches BOTH,
        # not merely one of the two distinct violation types.
        correct = mentions_duplicate and mentions_gap and not claims_fully_compliant
        return {
            "verdict_note": "exploratory phrase-based grading, not PAPER-S7-grade structural "
                            "checks; always spot-check report_text directly",
            "report_text": report_text,
            "mentions_duplicate_number": mentions_duplicate,
            "mentions_number_gap": mentions_gap,
            "claims_fully_compliant": claims_fully_compliant,
            "matches_ground_truth": correct,
            "is_error": cj.get("is_error"),
            "num_turns": cj.get("num_turns"),
            "wall_time_seconds": result.get("wall_time_seconds"),
        }

    mentions_alignment_topic = _mentions_any(report_text, _ALIGNMENT_KEYWORDS)
    mentions_punctuation_topic = _mentions_any(report_text, _PUNCTUATION_KEYWORDS)
    if doc_label == "violations":
        # Ground truth: both violations ARE present -- correct means the
        # report discusses both AND does not conclude "fully compliant".
        correct = mentions_alignment_topic and mentions_punctuation_topic and not claims_fully_compliant
    else:
        # doc_label == "compliant": ground truth is NO violations -- correct
        # means the report explicitly says so, not merely that it discusses
        # the topic (which a correct report does regardless, to confirm it).
        correct = claims_fully_compliant
    return {
        "verdict_note": "exploratory phrase-based grading (fixed 2026-09-06 to distinguish "
                        "'flags a violation' from 'confirms compliance' -- see comment above), "
                        "not PAPER-S7-grade structural checks; always spot-check report_text directly",
        "report_text": report_text,
        "mentions_alignment_topic": mentions_alignment_topic,
        "mentions_punctuation_topic": mentions_punctuation_topic,
        "claims_fully_compliant": claims_fully_compliant,
        "matches_ground_truth": correct,
        "is_error": cj.get("is_error"),
        "num_turns": cj.get("num_turns"),
        "wall_time_seconds": result.get("wall_time_seconds"),
    }


def main() -> int:
    # Optional: pass fixture labels as argv to run a subset (e.g. re-running
    # only a newly-added fixture rather than re-spending real API calls on
    # ones already verified in a prior invocation's saved pilot-result.json).
    selected_labels = sys.argv[1:] or list(FIXTURES.keys())
    fixtures_to_run = {k: v for k, v in FIXTURES.items() if k in selected_labels}
    for label, fixture in fixtures_to_run.items():
        if not fixture.exists():
            print(f"fixture not found: {fixture}", file=sys.stderr)
            return 1

    run_root = Path(r"E:\MeridianData\ooxml-graph-paper\runs\paper-s9-formatting-compliance-pilot")
    run_root.mkdir(parents=True, exist_ok=True)

    out_path = run_root / "pilot-result.json"
    all_results: dict[str, dict] = {}
    if out_path.exists():
        all_results = json.loads(out_path.read_text(encoding="utf-8"))

    for doc_label, fixture in fixtures_to_run.items():
        control_spec, treatment_spec = build_specs(doc_label, fixture)
        for spec in (control_spec, treatment_spec):
            print(f"running {doc_label}/{spec.arm}...", file=sys.stderr)
            res = run_trial(spec, run_root, model="sonnet")
            res["isolation_audit"] = audit_isolation(res)
            res["diagnosis_grading"] = grade(res, doc_label)
            all_results[f"{doc_label}-{spec.arm}"] = res

    out_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")

    for key, res in all_results.items():
        g = res["diagnosis_grading"]
        print(f"\n=== {key} ===")
        for field_name, value in g.items():
            if field_name in ("report_text", "verdict_note"):
                continue
            print(f"{field_name}: {value}")
        print(f"isolation_verdict: {res['isolation_audit'].get('isolation_verdict')}")

    print(f"\nFull result: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
