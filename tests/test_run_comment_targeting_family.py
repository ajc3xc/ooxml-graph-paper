"""Unit tests for tools/run_comment_targeting_family.py (PAPER-S24).

Follows tests/test_run_paper_s7_benchmark.py's own established convention
for this class of orchestrator (see that file's `fake_run_trial`/
`monkeypatch.setattr(..., "run_trial", fake_run_trial)` pattern): no real
`claude -p` subprocess is ever invoked here. A fake `run_trial` writes a
synthetic `.docx` fixture that mirrors exactly what the REAL
`insert_highlighted_note(mode="comment")` tool call (or a correct
hand-authored control-arm edit) would have produced, so the REAL
`grade_comment_targeting_step`/`grade_comment_targeting_chain` grading path
runs unmocked and is genuinely exercised end to end -- only the subprocess
boundary is stubbed.

Run with: pixi run python -m pytest tests/test_run_comment_targeting_family.py -v
"""
from __future__ import annotations

import json
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import run_comment_targeting_family as rctf  # noqa: E402
from run_comment_targeting_family import (  # noqa: E402
    _doc_tag,
    _interleaved_steps,
    _load_checkpoint,
    _seed_organic_kept_comments,
    _short_doc_label,
    _write_checkpoint,
    run_comment_targeting_chain,
    run_comment_targeting_isolated_baseline,
)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"


# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------

def _para_xml(para_id: str, text: str) -> str:
    return f'<w:p w14:paraId="{para_id}"><w:r><w:t>{text}</w:t></w:r></w:p>'


def _write_docx(path: Path, body_xml: str, comments_xml: str | None = None) -> None:
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<w:document xmlns:w="{_W}" xmlns:w14="{_W14}"><w:body>{body_xml}</w:body></w:document>'
    ).encode("utf-8")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("_rels/.rels", "<Relationships/>")
        zf.writestr("word/document.xml", document_xml)
        if comments_xml is not None:
            zf.writestr("word/comments.xml", comments_xml)


def _organic_comments_xml(author: str, text: str, comment_id: str = "0") -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<w:comments xmlns:w="{_W}">'
        f'<w:comment w:id="{comment_id}" w:author="{author}" w:date="2026-09-24T00:00:00Z">'
        f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p></w:comment></w:comments>'
    )


def _qn(tag: str) -> str:
    return f"{{{_W}}}{tag}"


def _fake_insert_comment(
    input_docx: Path, output_docx: Path, target_para_id: str, author: str, text: str,
    *, strip_comment_author: str | None = None,
) -> None:
    """Writes `output_docx` = `input_docx` plus one new native comment
    anchored to `target_para_id`, using the exact XML shape
    `_stage_word_comment` produces (commentRangeStart at paragraph start,
    commentRangeEnd at paragraph end, commentReference run last). If
    `strip_comment_author` is given, also DELETES the first existing
    `<w:comment>` by that author (and its own range markers) before adding
    the new one -- used to simulate a step that corrupts an earlier/organic
    comment while still correctly placing its own new one."""
    with zipfile.ZipFile(input_docx) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names if n not in ("word/document.xml", "word/comments.xml")}
        doc_bytes = zf.read("word/document.xml")
        comments_bytes = zf.read("word/comments.xml") if "word/comments.xml" in names else None

    root = ET.fromstring(doc_bytes)
    body = root.find(_qn("body"))
    target = next(p for p in body.iter(_qn("p")) if p.get(f"{{{_W14}}}paraId") == target_para_id)

    comments_root = ET.fromstring(comments_bytes) if comments_bytes is not None else ET.fromstring(
        f'<w:comments xmlns:w="{_W}"/>'
    )

    if strip_comment_author is not None:
        stripped_id = None
        for c in list(comments_root.findall(_qn("comment"))):
            if c.get(_qn("author")) == strip_comment_author:
                stripped_id = c.get(_qn("id"))
                comments_root.remove(c)
                break
        if stripped_id is not None:
            for p in body.iter(_qn("p")):
                for tag in ("commentRangeStart", "commentRangeEnd"):
                    for el in list(p.findall(_qn(tag))):
                        if el.get(_qn("id")) == stripped_id:
                            p.remove(el)
                for run in list(p.findall(_qn("r"))):
                    ref = run.find(_qn("commentReference"))
                    if ref is not None and ref.get(_qn("id")) == stripped_id:
                        p.remove(run)

    existing_ids: list[int] = []
    for el in root.iter():
        local = el.tag.rsplit("}", 1)[-1]
        if local in ("commentRangeStart", "commentRangeEnd", "commentReference"):
            value = el.get(_qn("id"))
            if value is not None:
                try:
                    existing_ids.append(int(value))
                except ValueError:
                    pass
    for c in comments_root.findall(_qn("comment")):
        try:
            existing_ids.append(int(c.get(_qn("id"), "-1")))
        except ValueError:
            pass
    new_id = str(max(existing_ids, default=-1) + 1)

    comment_el = ET.SubElement(comments_root, _qn("comment"))
    comment_el.set(_qn("id"), new_id)
    comment_el.set(_qn("author"), author)
    comment_el.set(_qn("date"), "2026-09-24T00:00:00Z")
    cp = ET.SubElement(comment_el, _qn("p"))
    cr = ET.SubElement(cp, _qn("r"))
    ct = ET.SubElement(cr, _qn("t"))
    ct.text = text

    start = ET.Element(_qn("commentRangeStart"))
    start.set(_qn("id"), new_id)
    target.insert(0, start)
    end = ET.Element(_qn("commentRangeEnd"))
    end.set(_qn("id"), new_id)
    target.append(end)
    ref_run = ET.SubElement(target, _qn("r"))
    ref = ET.SubElement(ref_run, _qn("commentReference"))
    ref.set(_qn("id"), new_id)

    with zipfile.ZipFile(output_docx, "w") as zf:
        for name, data in parts.items():
            zf.writestr(name, data)
        zf.writestr("word/document.xml", ET.tostring(root, encoding="utf-8"))
        zf.writestr("word/comments.xml", ET.tostring(comments_root, encoding="utf-8"))


def _make_fake_run_trial(behaviors: dict[str, object] | None = None, calls: list[str] | None = None):
    """`behaviors` maps `spec.trial_id` -> either a wrong target para_id
    (str, simulating a mistargeted comment), `"no_comment"` (untouched
    copy), `"corrupt"` (an invalid package), or a callable
    `(spec, output_path) -> None` for full custom control. Any trial_id not
    in `behaviors` gets the default, correctly-targeted behavior."""
    behaviors = behaviors or {}

    def fake_run_trial(spec, chain_root, *, model):
        if calls is not None:
            calls.append(spec.trial_id)
        trial_root = chain_root / spec.trial_id
        trial_root.mkdir(parents=True, exist_ok=True)
        output_path = trial_root / "doc.docx"
        behavior = behaviors.get(spec.trial_id)

        if behavior == "corrupt":
            output_path.write_bytes(b"not a real zip file")
        elif behavior == "no_comment":
            shutil.copyfile(spec.input_docx, output_path)
        elif callable(behavior):
            behavior(spec, output_path)
        elif isinstance(behavior, str):  # a wrong target para_id
            _fake_insert_comment(spec.input_docx, output_path, behavior, spec.treatment_args["author"], spec.treatment_args["text"])
        else:
            _fake_insert_comment(
                spec.input_docx, output_path,
                spec.treatment_args["anchor_para_id"], spec.treatment_args["author"], spec.treatment_args["text"],
            )

        return {
            "trial_id": spec.trial_id, "doc_label": spec.doc_label, "arm": spec.arm,
            "direction": spec.direction, "family": spec.family, "pair_index": spec.pair_index,
            "model": model, "started_at": "2026-09-24T00:00:00", "wall_time_seconds": 0.1,
            "timed_out": False, "returncode": 0,
            "input_hash_sha256": "in", "output_hash_sha256": "out", "docx_changed": True,
            "trial_root": str(trial_root), "output_docx_path": str(output_path),
            "cli_command_argv": [], "claude_json_result": None, "stdout_tail": "", "stderr_tail": "",
            "mcp_flake_retry_triggered": False,
        }

    return fake_run_trial


def _json_roundtrip(value):
    """Grading dicts carry real Python tuples (e.g. `anchor_para_ids`) that
    become JSON arrays once written to a checkpoint and read back --
    comparing a freshly-computed in-memory result against one reloaded from
    a checkpoint must normalize through the same round trip first, or a
    tuple-vs-list mismatch looks like a real inequality when the underlying
    data is identical."""
    return json.loads(json.dumps(value))


def _basic_schedule(usable_k: int = 2) -> dict:
    ambiguous = [
        {
            "regime": "within_table_run", "label": "MAT (DSE)", "para_id": f"AMB{i:04d}",
            "disambiguator_value": str(i), "table_index": 0, "row_index": i,
            "confusable_sibling_para_ids": [f"AMBSIB{i}{j}" for j in range(2)],
        }
        for i in range(usable_k)
    ]
    unique = [
        {"para_id": f"UNQ{i:04d}", "text_snippet": f"Unique paragraph number {i}."}
        for i in range(usable_k)
    ]
    return {"usable_k": usable_k, "ambiguous_targets": ambiguous, "unique_targets": unique}


_ORGANIC_PARA_XML = (
    '<w:p w14:paraId="ORGANIC1">'
    '<w:commentRangeStart w:id="0"/>'
    '<w:r><w:t>An organic paragraph.</w:t></w:r>'
    '<w:commentRangeEnd w:id="0"/>'
    '<w:r><w:commentReference w:id="0"/></w:r>'
    "</w:p>"
)


def _fixture_docx(tmp_path: Path, usable_k: int = 2, organic_comment: bool = False) -> Path:
    schedule = _basic_schedule(usable_k)
    body_parts = []
    for t in schedule["ambiguous_targets"]:
        body_parts.append(_para_xml(t["para_id"], t["label"]))
        for sib in t["confusable_sibling_para_ids"]:
            body_parts.append(_para_xml(sib, t["label"]))
    for t in schedule["unique_targets"]:
        body_parts.append(_para_xml(t["para_id"], t["text_snippet"]))
    if organic_comment:
        # Real commentRangeStart/End/Reference markers, not just a bare
        # paragraph -- _comment_bracketed_para_ids needs the actual range
        # markers to resolve which paragraph this organic comment anchors
        # to, exactly like a real organic comment in the corpus would have.
        body_parts.insert(0, _ORGANIC_PARA_XML)
    body = "".join(body_parts)
    comments_xml = _organic_comments_xml("Adam Camerer", "An organic pre-existing comment.") if organic_comment else None
    path = tmp_path / "pristine.docx"
    _write_docx(path, body, comments_xml=comments_xml)
    return path


# ---------------------------------------------------------------------------
# Pure-logic helpers
# ---------------------------------------------------------------------------

def test_doc_tag_is_stable_and_short():
    tag = _doc_tag("masters-dissertation-defense")
    assert len(tag) == 8
    assert tag == _doc_tag("masters-dissertation-defense")


def test_short_doc_label_avoids_prefix_collision():
    """Regression precedent copied from run_respec_cascade_family.py's own
    2026-09-22 fix: two labels sharing a long common prefix must not
    truncate to the same short label."""
    a = _short_doc_label("masters-dissertation-defense__anchor0")
    b = _short_doc_label("masters-dissertation-defense__anchor3")
    assert a != b


def test_interleaved_steps_alternates_ambiguous_and_unique():
    schedule = _basic_schedule(usable_k=3)
    steps = _interleaved_steps(schedule)
    assert len(steps) == 6
    assert [s[0] for s in steps] == ["ambiguous", "unique", "ambiguous", "unique", "ambiguous", "unique"]
    assert [s[1] for s in steps] == [1, 1, 2, 2, 3, 3]
    assert steps[0][2] == schedule["ambiguous_targets"][0]
    assert steps[5][2] == schedule["unique_targets"][2]


def test_interleaved_steps_empty_when_usable_k_zero():
    assert _interleaved_steps({"usable_k": 0, "ambiguous_targets": [], "unique_targets": []}) == []


def test_checkpoint_round_trip(tmp_path: Path):
    result = {"chain_id": "x", "status": "completed"}
    _write_checkpoint(tmp_path, result)
    assert _load_checkpoint(tmp_path) == result


def test_checkpoint_not_trusted_for_untrusted_status(tmp_path: Path):
    _write_checkpoint(tmp_path, {"chain_id": "x", "status": "some_unknown_infra_flake"})
    assert _load_checkpoint(tmp_path) is None


def test_seed_organic_kept_comments_empty_when_no_comments_part(tmp_path: Path):
    path = _fixture_docx(tmp_path, usable_k=1, organic_comment=False)
    assert _seed_organic_kept_comments(path) == {}


def test_seed_organic_kept_comments_finds_the_real_organic_comment(tmp_path: Path):
    path = _fixture_docx(tmp_path, usable_k=1, organic_comment=True)
    kept = _seed_organic_kept_comments(path)
    assert len(kept) == 1
    entry = next(iter(kept.values()))
    assert entry["author"] == "Adam Camerer"
    assert entry["anchor_para_ids"] == ("ORGANIC1",)


# ---------------------------------------------------------------------------
# run_comment_targeting_chain (fake_run_trial, real grading)
# ---------------------------------------------------------------------------

def test_chain_completes_and_passes_when_every_step_correctly_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docx_path = _fixture_docx(tmp_path, usable_k=2)
    schedule = _basic_schedule(usable_k=2)
    monkeypatch.setattr(rctf, "run_trial", _make_fake_run_trial())

    result = run_comment_targeting_chain(
        "test-doc", docx_path, "treatment", "sonnet", tmp_path / "run-root", schedule,
        word_receipts_enabled=False,
    )

    assert result["status"] == "completed"
    assert result["steps_run"] == 4  # 2 * usable_k
    assert result["round_trip_count"] == 4
    assert result["chain_grade"]["chain_pass"] is True
    assert [p["condition"] for p in result["chain_grade"]["per_position"]] == ["ambiguous", "unique", "ambiguous", "unique"]


def test_chain_is_resumable_and_does_not_rerun_completed_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docx_path = _fixture_docx(tmp_path, usable_k=1)
    schedule = _basic_schedule(usable_k=1)
    calls: list[str] = []
    monkeypatch.setattr(rctf, "run_trial", _make_fake_run_trial(calls=calls))
    run_root = tmp_path / "run-root"

    first = run_comment_targeting_chain("test-doc", docx_path, "control", "sonnet", run_root, schedule, word_receipts_enabled=False)
    calls_after_first = len(calls)
    second = run_comment_targeting_chain("test-doc", docx_path, "control", "sonnet", run_root, schedule, word_receipts_enabled=False)

    assert _json_roundtrip(second) == _json_roundtrip(first)
    assert len(calls) == calls_after_first  # no new subprocess calls on resume


def test_chain_not_applicable_when_usable_k_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docx_path = _fixture_docx(tmp_path, usable_k=1)
    monkeypatch.setattr(rctf, "run_trial", _make_fake_run_trial())

    result = run_comment_targeting_chain(
        "test-doc", docx_path, "treatment", "sonnet", tmp_path / "run-root",
        {"usable_k": 0, "ambiguous_targets": [], "unique_targets": []}, word_receipts_enabled=False,
    )

    assert result["status"] == "not_applicable"
    assert result["steps_run"] == 0


def test_chain_freezes_at_the_first_invalid_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docx_path = _fixture_docx(tmp_path, usable_k=2)
    schedule = _basic_schedule(usable_k=2)
    # Step 2 (the first "unique" step) produces a corrupt package.
    # spec.trial_id is exactly `step_id` ("step{n}-{condition}{condition_
    # position}") -- SCOPED to chain_root, which already encodes doc_label/
    # arm in its own path -- never chain_id-prefixed again (mirrors
    # run_respec_cascade_family.py's own "1.1-bibliography-forward"-style
    # step ids).
    behaviors = {"step2-unique1": "corrupt"}
    monkeypatch.setattr(rctf, "run_trial", _make_fake_run_trial(behaviors))

    result = run_comment_targeting_chain(
        "test-doc", docx_path, "treatment", "sonnet", tmp_path / "run-root", schedule, word_receipts_enabled=False,
    )

    assert result["status"] == "chain_broken_at_step_step2-unique1"
    assert result["steps_run"] == 2
    assert result["chain_grade"]["step_count"] == 1  # only step 1 was graded before the freeze


def test_chain_detects_wrong_target_same_cluster_and_reports_completed_with_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    docx_path = _fixture_docx(tmp_path, usable_k=1)
    schedule = _basic_schedule(usable_k=1)
    wrong_sibling = schedule["ambiguous_targets"][0]["confusable_sibling_para_ids"][0]
    monkeypatch.setattr(rctf, "run_trial", _make_fake_run_trial({"step1-ambiguous1": wrong_sibling}))

    result = run_comment_targeting_chain(
        "test-doc", docx_path, "treatment", "sonnet", tmp_path / "run-root", schedule, word_receipts_enabled=False,
    )

    assert result["status"] == "completed_with_failure"
    assert result["chain_grade"]["chain_pass"] is False
    assert result["chain_grade"]["per_position"][0]["outcome"] == "wrong_target_same_cluster"
    # The second (unique) step still ran and passed -- one bad step doesn't
    # abort the chain the way a package-validity failure does.
    assert result["chain_grade"]["per_position"][1]["step_pass"] is True


def test_chain_detects_organic_comment_corrupted_partway_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docx_path = _fixture_docx(tmp_path, usable_k=1, organic_comment=True)
    schedule = _basic_schedule(usable_k=1)

    def strip_organic(spec, output_path):
        _fake_insert_comment(
            spec.input_docx, output_path, spec.treatment_args["anchor_para_id"],
            spec.treatment_args["author"], spec.treatment_args["text"],
            strip_comment_author="Adam Camerer",
        )

    monkeypatch.setattr(rctf, "run_trial", _make_fake_run_trial({"step1-ambiguous1": strip_organic}))

    result = run_comment_targeting_chain(
        "test-doc", docx_path, "treatment", "sonnet", tmp_path / "run-root", schedule, word_receipts_enabled=False,
    )

    assert result["status"] == "completed_with_failure"
    assert result["chain_grade"]["per_position"][0]["outcome"] == "prior_comment_corrupted"


# ---------------------------------------------------------------------------
# run_comment_targeting_isolated_baseline
# ---------------------------------------------------------------------------

def test_isolated_baseline_runs_a_single_step_and_grades_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docx_path = _fixture_docx(tmp_path, usable_k=1)
    schedule = _basic_schedule(usable_k=1)
    calls: list[str] = []
    monkeypatch.setattr(rctf, "run_trial", _make_fake_run_trial(calls=calls))

    result = run_comment_targeting_isolated_baseline(
        "test-doc", docx_path, "treatment", "sonnet", tmp_path / "run-root",
        "ambiguous", 0, schedule["ambiguous_targets"][0], word_receipts_enabled=False,
    )

    assert result["status"] == "completed"
    assert result["step_grade"]["outcome"] == "correct_target"
    assert len(calls) == 1  # exactly one subprocess round trip, no chain involved


def test_isolated_baseline_is_resumable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docx_path = _fixture_docx(tmp_path, usable_k=1)
    schedule = _basic_schedule(usable_k=1)
    calls: list[str] = []
    monkeypatch.setattr(rctf, "run_trial", _make_fake_run_trial(calls=calls))
    run_root = tmp_path / "run-root"

    first = run_comment_targeting_isolated_baseline(
        "test-doc", docx_path, "control", "sonnet", run_root, "unique", 0, schedule["unique_targets"][0],
        word_receipts_enabled=False,
    )
    second = run_comment_targeting_isolated_baseline(
        "test-doc", docx_path, "control", "sonnet", run_root, "unique", 0, schedule["unique_targets"][0],
        word_receipts_enabled=False,
    )

    assert _json_roundtrip(second) == _json_roundtrip(first)
    assert len(calls) == 1
