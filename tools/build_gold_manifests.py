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
    # PAPER-25 second batch (32 remaining candidates independently reviewed; 23 promoted here, 9 excluded below).
    ("officeval_002", "城市社区微气候韧性评价与公共空间更新研究_.docx", "tier2-omegause-002-thesis",
     "Master's thesis; author/advisor names appear only in standard thesis-title-page convention, no ID/contact attached."),
    ("officeval_003", "部门协调会记录 (1).docx", "tier2-omegause-003-meeting-minutes",
     "Meeting minutes with many staff names in business roles, but no phone/ID/contact number attached to any of them."),
    ("officeval_008", "文献翻译译文.docx", "tier2-omegause-008-lit-review",
     "Academic literature review; text explicitly states it uses fictional material/district names to avoid real project data."),
    ("officeval_010", "技术路线图.docx", "tier2-omegause-010-roadmap-diagram",
     "Zero text runs; body is one embedded generic flowchart image with an explicit no-real-data disclaimer."),
    ("officeval_012", "东岳技术学院高等教育自学考试毕业论文格式.docx", "tier2-omegause-012-thesis-template",
     "Formatting template; personal-info fields explicitly marked 'to be filled in by the candidate' and left blank."),
    ("officeval_013", "基于Spark的园区能耗分析与可视化系统论文.docx", "tier2-omegause-013-survey-paper",
     "Academic survey paper; explicitly states it avoids real project data via fictional names/generalized metrics; no ID/phone found."),
    ("officeval_014", "冻结肩多模态康复研究.docx", "tier2-omegause-014-thesis-1",
     "Master's thesis; author/advisor in standard citation convention only, patient data explicitly de-identified/coded in the text itself."),
    ("officeval_014", "毕业论文要求_星途理工大学.docx", "tier2-omegause-014-formatting-notice",
     "Generic institutional formatting notice; only names are illustrative citation examples."),
    ("officeval_016", "澄禾社区生鲜服务满意度研究.docx", "tier2-omegause-016-thesis-2",
     "Thesis with all identity fields left as blank template placeholders; body explicitly states its data is fictional/constructed."),
    ("officeval_019", "初中化学模拟试题.docx", "tier2-omegause-019-chem-exam",
     "Generic exam; name/class/exam-number fields are instructions to fill in, nothing actually filled."),
    ("officeval_019", "模板.docx", "tier2-omegause-019-english-exam",
     "Generic English exam; instructs students not to use real names/school names; none present."),
    ("officeval_020", "《浅赏叙事古文，读懂处世道理》.docx", "tier2-omegause-020-lesson-plan",
     "Generic lesson plan/case study; no individual named at all."),
    ("officeval_022", "企业经营情况说明书.docx", "tier2-omegause-022-anomaly-statement",
     "Fictional business anomaly narrative; the one contact field present is already partially masked (186****2741), not a complete number."),
    ("officeval_024", "城市社区绿地可达性与居民步行行为研究.docx", "tier2-omegause-024-thesis",
     "Thesis; signature fields explicitly blank, text states names/addresses were deliberately not collected during the underlying survey."),
    ("officeval_024", "论文模版.docx", "tier2-omegause-024-thesis-template",
     "Thesis template; every identity field is an explicit placeholder (AAA/XXX/WWO*000***), not a real filled-in value."),
    ("officeval_025", "青岭山居旅居营造计划.docx", "tier2-omegause-025-business-plan",
     "Student business-plan proposal; team names appear with no ID/phone/contact attached, analogous to a standard byline."),
    ("officeval_033", "家居零售价目册.docx", "tier2-omegause-033-price-catalog",
     "Pure product catalog; no person referenced at all."),
    ("officeval_035", "002 毕业设计外文翻译封面及格式要求（普通班）.docx", "tier2-omegause-035-cover-template",
     "Cover-page template; name field holds only a generic placeholder ('王大一'), ID/advisor fields left blank."),
    ("officeval_036", "public_ready_statement.docx", "tier2-omegause-036-bank-statement-template",
     "Fictional bank statement template; no person named, only a fictional company name."),
    ("officeval_080", "要求.docx", "tier2-omegause-080-slide-instructions",
     "Pure task-instruction text for editing a slide deck; no personal content."),
    ("officeval_088", "小天鹅12KG滚筒洗衣机产品说明文档.docx", "tier2-omegause-088-product-spec-3",
     "Pure product spec/marketing copy; no person referenced at all."),
    ("officeval_088", "米家8KG滚筒洗衣机产品说明文档.docx", "tier2-omegause-088-product-spec-4",
     "Pure product spec/marketing copy; no person referenced at all."),
    ("officeval_088", "美的8KG波轮洗衣机产品说明文档.docx", "tier2-omegause-088-product-spec-5",
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
    # PAPER-25 second batch: 9 new exclusions, ALL confirmed distinct from the 顾启朝 dossier case study --
    # a separate, very common pattern in this dataset: real-format student name + student-ID pairs filled
    # into thesis/report cover pages (not blank template fields).
    ("officeval_005", "综合设计指导书.docx",
     "Embedded sample report cover page fills in 3 student names each paired 1:1 with a student ID number."),
    ("officeval_007", "幼儿园自然探究活动课程设计.docx",
     "Thesis cover page: filled name ('林诗'/'林诗学') paired with student ID 'B20251782'."),
    ("officeval_007", "齐鲁启明继续教育学院论文模板.docx",
     "Template's sample cover page filled (not blank) with name '苏启西' + student ID 'B20231399'."),
    ("officeval_011", "课程资料.docx",
     "Template's sample cover page filled with name '苏启西' + student ID 'B20231399' (same pair as officeval_007's template, likely a shared example)."),
    ("officeval_012", "城市社区雨水花园参与式维护机制研究.docx",
     "Thesis cover page: filled name '林诗' + student ID 'B20251782' (same pair as officeval_007's thesis)."),
    ("officeval_018", "公共书房运营规划书.docx",
     "Thesis-proposal cover page: filled name '许芷涵' + 10-digit student ID '2360140827'."),
    ("officeval_021", "毕业设计论文.docx",
     "Same cover page as officeval_018: filled name '许芷涵' + student ID '2360140827' (duplicate case, different filename)."),
    ("officeval_021", "毕业设计论文开题报告 (模版).docx",
     "Same name+ID pair again: '许芷涵' + '2360140827', in an opening-report template."),
    ("officeval_023", "董事會數位素養對企業低碳轉型績效的影響.docx",
     "Thesis title page: filled name '林澄韵' + student ID 'M260742018555', recurring in acknowledgments."),
]


TIER2_DOCX_BENCHMARK = [
    # (filename under raw/docx-benchmark/series-seed, doc_id, review note)
    ("investment-agreement.docx", "tier2-docxbenchmark-investment-agreement-blank",
     "Series Seed investment agreement, [COMPANY NAME] placeholder throughout -- pure blank legal template, CC0-1.0."),
    ("investment-agreement-executed.docx", "tier2-docxbenchmark-investment-agreement-executed",
     "Same template 'executed' with the standard legal-tech demo filler 'Stark Industries, Inc.' (fictional, "
     "not a real party) -- no real signatory names found in spot-check. CC0-1.0."),
]


def _stage_tier2_docxcorpus() -> list[tuple[Path, str, str]]:
    """Data-driven (not hardcoded like the two lists above -- 67 entries is too many to
    hand-maintain as tuples): reads the real review verdicts written by the PAPER-25
    docx-corpus review workflow and stages only the ones marked promote."""
    review_path = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\review_results.json")
    if not review_path.is_file():
        return []
    reviews = json.loads(review_path.read_text(encoding="utf-8"))
    src_dir = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\files")
    staged_dir = GOLD_ROOT / "tier2"
    staged_dir.mkdir(parents=True, exist_ok=True)
    out = []
    review_by_id = {}
    for r in reviews:
        if r.get("verdict") != "promote":
            continue
        doc_id = f"tier2-docxcorpus-{r['id'][:16]}"
        src = src_dir / f"{r['id']}.docx"
        if not src.is_file():
            continue
        dst = staged_dir / f"{doc_id}.docx"
        _shutil.copy2(src, dst)
        out.append((dst, doc_id, "tier2"))
        review_by_id[doc_id] = r
    review_summary_path = GOLD_ROOT / "manifests" / "_docxcorpus_review.json"
    review_summary_path.write_text(json.dumps(review_by_id, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _stage_tier2() -> list[tuple[Path, str, str]]:
    staged_dir = GOLD_ROOT / "tier2"
    staged_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for subdir, fname, doc_id, _note in TIER2_CANDIDATES:
        src = Path(r"E:\MeridianData\ooxml-graph-paper\raw\omega-officeval\task_files") / subdir / fname
        dst = staged_dir / f"{doc_id}.docx"
        _shutil.copy2(src, dst)
        out.append((dst, doc_id, "tier2"))
    for fname, doc_id, _note in TIER2_DOCX_BENCHMARK:
        src = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-benchmark\series-seed") / fname
        dst = staged_dir / f"{doc_id}.docx"
        _shutil.copy2(src, dst)
        out.append((dst, doc_id, "tier2"))
    out.extend(_stage_tier2_docxcorpus())
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
