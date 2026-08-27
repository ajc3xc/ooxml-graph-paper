"""PAPER-22: run the independent extractor + package-integrity check + a REAL,
RETAINED Word-COM render receipt for each selected gold document, and write
one combined manifest per document under E:\\MeridianData\\ooxml-graph-paper\\gold\\manifests\\.

Package-integrity and render checks call real product modules
(ooxml_integrity, render_gate) -- that is legitimate: those check package
well-formedness and render capability, not graph fidelity, so using them here
does not make the GRAPH gold circular with what PAPER-15 benchmarks (the
independent_gold_extractor output is what stands in for graph gold).

PAPER-23: render receipts are now genuinely RETAINED via
tools/retained_render_receipt.py -- a from-scratch script (not a change to the
shared render_gate.py) that copies Word's PDF output out of its temp directory
before that directory is deleted, closing the gap this file's PAPER-22
docstring originally flagged as unresolved. See that script's own docstring
for the exact root cause it works around.

Usage: pixi run python tools/build_gold_manifests.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\13144\Documents\Meridian\repository")
sys.path.insert(0, str(REPO_ROOT / "extensions" / "meridian-docs"))
sys.path.insert(0, str(Path(__file__).parent))

import independent_gold_extractor as ige  # noqa: E402
import retained_render_receipt as rrr  # noqa: E402
from meridian_docs import docs_intel  # noqa: E402

GOLD_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\gold")
RENDER_ROOT = Path(r"E:\MeridianData\ooxml-graph-paper\renders\gold")


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def process(docx_path: Path, doc_id: str, tier: str) -> dict:
    result: dict = {"doc_id": doc_id, "tier": tier, "source_path": str(docx_path)}

    # 1. Independent graph-gold extraction (never touches docs_intel.py).
    gold_record = ige.extract(docx_path)
    result["gold_record"] = gold_record

    # 2. Real package-integrity check (product safety validator, not graph authorship).
    raw = docx_path.read_bytes()
    integrity = docs_intel.ooxml_integrity.validate_docx_package(raw)
    result["package_integrity"] = integrity

    # 3. Real, RETAINED Word-COM render receipt (tools/retained_render_receipt.py).
    RENDER_ROOT.mkdir(parents=True, exist_ok=True)
    doc_render_dir = RENDER_ROOT / doc_id
    try:
        receipt = rrr.retained_render_receipt(docx_path, doc_render_dir)
    except Exception as exc:  # noqa: BLE001 -- a crashing receipt script is itself the finding
        receipt = {"status": "failed", "exit_status": f"retained_render_receipt raised {type(exc).__name__}: {exc}",
                   "retained_pdf_path": None, "output_hash_sha256": None}
    result["render_result"] = {"status": receipt.get("status")}
    result["render_receipt"] = receipt

    # 4. Persist the combined manifest.
    manifests_dir = GOLD_ROOT / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    out_path = manifests_dir / f"{doc_id}.manifest.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    result["manifest_path"] = str(out_path)
    return result


import shutil as _shutil  # noqa: E402

TIER2_CANDIDATES = [
    # (source dir under raw/omega-officeval/task_files, filename, doc_id, review note)
    ("officeval_040", "简介素材.docx", "tier2-omegause-040-dept-intro",
     "Generic institutional department description (faculty counts, facilities, majors offered). No personal names."),
    ("officeval_009", "第三章研究结果.docx", "tier2-omegause-009-ch3-results",
     "Document's OWN text explicitly states its data is fictional/simulated and deliberately de-identified "
     "(quote: names/institutions/contacts/amounts \"rewritten into untraceable content\"; statistics \"simulated... "
     "do not correspond to any real individual or organization\"). Strongest-evidence candidate."),
    ("officeval_026", "项目式协作学习统计表.docx", "tier2-omegause-026-stats-table",
     "Pure aggregate statistics table (Levene/t-test values). No names, no identifying content."),
    ("officeval_031", "拼音乐园闯关测.docx", "tier2-omegause-031-pinyin-worksheet",
     "Generic first-grade Chinese phonics worksheet template. Name/class fields are blank underscores, not filled-in PII."),
    # PAPER-23 batch (25 candidates independently reviewed via 25 parallel, fresh, no-shared-context
    # agents, each reading the full document text itself -- 20 promoted below, 5 excluded in
    # TIER2_EXCLUDED. Full reasoning per file: E:\MeridianData\ooxml-graph-paper\gold\manifests\_tier2_review.json).
    ("officeval_001", "01_课时学习方案_观察一位校园志愿者_第一课时.docx", "tier2-omegause-001-01-lesson-plan",
     "Generic elementary lesson plan; no names, no IDs, no contact details anywhere."),
    ("officeval_001", "02_课时学习方案_方法交流与片段尝试_第一课时.docx", "tier2-omegause-001-02-lesson-plan",
     "Generic lesson plan, no PII. Reviewer independently re-verified via SHA256 after an environment "
     "anomaly (see PAPER-23 completion notes) produced a suspicious first-pass result for a different file."),
    ("officeval_001", "03_课时学习方案_身边人物初识.docx", "tier2-omegause-001-03-lesson-plan",
     "Generic lesson plan; only unnamed generic roles referenced, no PII."),
    ("officeval_001", "04_课时学习方案_人物细节描写_第二课时.docx", "tier2-omegause-001-04-lesson-plan",
     "Generic lesson plan; fictional unnamed role only, no PII."),
    ("officeval_001", "05_课时学习方案_匠心故事研读.docx", "tier2-omegause-001-05-lesson-plan",
     "Generic lesson plan; no person named at all, no PII."),
    ("officeval_001", "06_课时学习方案_家乡风物介绍_第二课时.docx", "tier2-omegause-001-06-lesson-plan",
     "Generic lesson plan; no PII, empty author metadata."),
    ("officeval_001", "07_课时学习方案_写一个让人记住的人_第一课时.docx", "tier2-omegause-001-07-lesson-plan",
     "Generic lesson plan; no PII."),
    ("officeval_006", "高一年级第一次数学周练111 (2).docx", "tier2-omegause-006-math-quiz",
     "Largely-empty math quiz shell; only a routine composer/reviewer teacher-name byline with no ID/contact attached -- below the exclusion bar."),
    ("officeval_015", "初中语文跨年级综合质量检测.docx", "tier2-omegause-015-lesson-plan",
     "Misleading filename (says 'quality assessment'), actual content is a generic lesson plan with no PII."),
    ("officeval_016", "小微企业财务数据管理规范化问题及改进路径研究.docx", "tier2-omegause-016-academic-essay",
     "Academic essay; only names present are standard in-text citation authors, no ID/contact attached."),
    ("officeval_018", "报告排版格式要求.docx", "tier2-omegause-018-formatting-spec",
     "Pure abstract typesetting/formatting rules; no personal content of any kind."),
    ("officeval_022", "华中区域零售项目经营异常核查封面.docx", "tier2-omegause-022-cover-sheet",
     "BORDERLINE, flagged for a second look: has a name ('林远芝') and a contact-info field, but the phone "
     "number's middle 4 digits are asterisk-masked ('186****2741'), not a complete usable number; company names read as synthetic. Promoted on that basis but worth re-checking."),
    ("officeval_022", "华中区域零售项目经营资金异常及现金流风险.docx", "tier2-omegause-022-audit-report",
     "Same case-study family as the cover sheet above; only a bare 'prepared by: 林远芝' byline with no ID/phone/contact attached -- below the exclusion bar."),
    ("officeval_030", "V2毕业设计论文格式要求.docx", "tier2-omegause-030-project-proposal",
     "Filename says 'thesis format requirements' but actual content is a generic project-proposal template; only unfilled blank submitter field, no PII."),
    ("officeval_037", "周测二_高三英语试题.docx", "tier2-omegause-037-english-exam",
     "English exam paper; only name is '李华' (Li Hua), the universal standard placeholder name used in ALL Chinese English-exam writing prompts, plus fictional characters in reading passages. No real PII."),
    ("officeval_039", "办公设备维护与巡检服务合同.docx", "tier2-omegause-039-thesis-template",
     "Filename/header says 'equipment maintenance contract' but body is a graduation-thesis formatting template; every name/ID/signature field is an unfilled blank ('______'). No PII."),
    ("officeval_059", "青梧谷灵MR共创计划_项目申报书.docx", "tier2-omegause-059-project-proposal",
     "Generic project proposal; only fill-in field (submitting organization) left blank. No PII."),
    ("officeval_088", "云溪5.0 D3滚筒洗衣机产品说明文档.docx", "tier2-omegause-088-product-spec-1",
     "Pure product spec/marketing copy; no person referenced at all."),
    ("officeval_088", "模板.docx", "tier2-omegause-088-blank-template",
     "Bare product-comparison template, every field an unfilled label. No PII."),
    ("officeval_088", "统帅三桶懒人洗衣机产品说明文档.docx", "tier2-omegause-088-product-spec-2",
     "Pure product spec/marketing copy; no person referenced at all."),
]

TIER2_EXCLUDED = [
    ("officeval_004", "毕业实习报告.docx / 毕业实习鉴定表.docx",
     "Contains a specific-looking student name, student ID number, and two named supervisors plus a named "
     "kindergarten and college. Dataset card claims a de-identification pipeline, but this specific instance "
     "was not independently verifiable as synthesized vs. lightly-reworded-real by this review pass. "
     "EXCLUDED from gold pending explicit human sign-off, not promoted on this session's own judgment."),
    ("officeval_001", "08_课时学习方案_习作讲评与修改_第二课时.docx",
     "Filename claims a lesson plan; actual content is a corporate 'operating-anomaly verification dossier' "
     "with a filled name+phone block: '呈报人：顾启朝...联系电话：188278632124586'. Same underlying document as "
     "the two exclusions below, found independently under a third, unrelated filename."),
    ("officeval_015", "九年级答题卡 (1) (3).docx",
     "Filename claims a 9th-grade answer sheet; actual content is the same '呈报人：顾启朝...联系电话：188278632124586' "
     "dossier as officeval_001/08 above -- the same underlying golden artifact duplicated under a second, "
     "unrelated filename."),
    ("officeval_022", "企业经营异常核查呈报材料.docx",
     "The same '呈报人：顾启朝...联系电话：188278632124586' dossier again, a third occurrence under a third filename."),
    ("officeval_028", "职称评审表.docx",
     "A FILLED-OUT professional-title review form: real-ID-format 18-digit national ID number "
     "('身份证号码：454045777852124578') tied to a named applicant ('梁景川'), plus birth date, birthplace, "
     "employer, education history, certificate numbers, and 7 additional named witnesses. The most "
     "identifying single document found in this review pass."),
    ("officeval_030", "V2成果说明书_A.docx",
     "Filled graduation-design cover page: student full name ('林若航') paired directly with a specific "
     "student ID number ('24A0318426'), plus a named advisor ('周雁宁')."),
]


def _stage_tier2() -> list[tuple[Path, str, str]]:
    staged_dir = GOLD_ROOT / "tier2"
    staged_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for subdir, fname, doc_id, _note in TIER2_CANDIDATES:
        src = Path(r"E:\MeridianData\ooxml-graph-paper\raw\omega-officeval\task_files") / subdir / fname
        dst = staged_dir / f"{doc_id}.docx"
        _shutil.copy2(src, dst)
        out.append((dst, doc_id, "tier2"))
    return out


def main() -> int:
    tier1_dir = GOLD_ROOT / "tier1"
    tier3_dir = GOLD_ROOT / "tier3"
    docs = []
    for p in sorted(tier1_dir.glob("*.docx")):
        docs.append((p, p.stem, "tier1"))
    docs.extend(_stage_tier2())
    for p in sorted(tier3_dir.glob("*.docx")):
        docs.append((p, p.stem, "tier3"))

    summary = []
    for docx_path, doc_id, tier in docs:
        r = process(docx_path, doc_id, tier)
        n_nodes = len(r["gold_record"]["nodes"])
        n_edges = len(r["gold_record"]["edges"])
        n_uncertain = len(r["gold_record"]["uncertainty"])
        integrity_ok = r["package_integrity"].get("ok")
        render_status = r["render_result"].get("status")
        retained = r["render_receipt"]["retained_pdf_path"] is not None
        print(
            f"{doc_id:30s} nodes={n_nodes:3d} edges={n_edges:3d} uncertainty={n_uncertain:3d} "
            f"integrity_ok={integrity_ok} render={render_status} pdf_retained={retained}"
        )
        summary.append({
            "doc_id": doc_id, "tier": tier, "nodes": n_nodes, "edges": n_edges,
            "uncertainty": n_uncertain, "integrity_ok": integrity_ok,
            "render_status": render_status, "pdf_retained": retained,
            "manifest_path": r["manifest_path"],
        })

    (GOLD_ROOT / "manifests" / "_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    review = {
        "promoted": [
            {"doc_id": doc_id, "source": f"{subdir}/{fname}", "note": note}
            for subdir, fname, doc_id, note in TIER2_CANDIDATES
        ],
        "excluded": [
            {"source_dir": subdir, "files": fname, "note": note}
            for subdir, fname, note in TIER2_EXCLUDED
        ],
    }
    (GOLD_ROOT / "manifests" / "_tier2_review.json").write_text(
        json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n{len(summary)} documents processed. Summary: {GOLD_ROOT / 'manifests' / '_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
