from contextlib import closing
import json
import sqlite3
import tempfile
import time
import unittest
from types import SimpleNamespace
import uuid
from pathlib import Path

from context import KNOWLEDGE_DB

import app
from app import (
    RequestError, analyze_alignment, answer_question, checked_citations, citation_ids,
    collect_method_docs, conversation_context, generate_literature_candidates,
    merge_alignment_edit, parse_alignment_result, parse_candidate_entries,
    validate_question,
)
from search import load_entries
from unittest.mock import patch

from workspace_store import WorkspaceStore


class CitationTests(unittest.TestCase):
    def test_supported_citation_formats(self):
        cases = {
            "见 [MED-04]。": ["MED-04"],
            "见 [MED-04, MED-07]。": ["MED-04", "MED-07"],
            "见 [MED-04，MED-07]。": ["MED-04", "MED-07"],
            "见 【MED-04】。": ["MED-04"],
            "见 [MED-04][MED-07]。": ["MED-04", "MED-07"],
            "见 [ MED-04 ]。": ["MED-04"],
            "没有引用": [],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(citation_ids(text), expected)

    def test_duplicate_ids_are_removed(self):
        self.assertEqual(citation_ids("[MED-04] 和 【MED-04】"), ["MED-04"])

    def test_only_citations_for_retrieved_entries_are_kept(self):
        hits = [{"entry_id": "MED-04"}, {"entry_id": "MED-06"}]
        cited, valid = checked_citations("见【MED-04, MED-07】；另见医学文献 [COVID-19]。", hits)
        self.assertEqual(cited, {"MED-04", "MED-07"})
        self.assertEqual(valid, {"MED-04", "MED-06"})
        self.assertTrue(cited - valid)

    def test_citation_with_other_case_prefix_is_ignored(self):
        cited, _ = checked_citations("见 [FIN-01]。", [{"entry_id": "MED-04"}])
        self.assertEqual(cited, set())


class ValidationTests(unittest.TestCase):
    def test_valid_payload_is_stripped(self):
        self.assertEqual(
            validate_question({"case": "MED", "mode": "auto", "question": "  肝脏分割  "}),
            ("MED", "auto", "肝脏分割"),
        )

    def test_bad_mode_is_rejected(self):
        with self.assertRaises(RequestError):
            validate_question({"case": "MED", "mode": "unknown", "question": "问题"})

    def test_long_question_is_rejected(self):
        with self.assertRaises(RequestError):
            validate_question({"case": "MED", "mode": "auto", "question": "长" * 601})


class AnswerFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = load_entries(KNOWLEDGE_DB)

    def test_method_answer_returns_up_to_six_results(self):
        response = answer_question(
            {"case": "MED", "mode": "method", "question": "肝脏 CT 分割有哪些方法？"}, self.entries,
        )
        self.assertEqual(response["mode"], "method")
        self.assertEqual(response["retrieval_case"], "MED")
        self.assertEqual(response["source"], "local")
        self.assertLessEqual(len(response["results"]), 6)
        self.assertGreaterEqual(len(response["results"]), 3)
        self.assertEqual(len(response["references"]), len(response["results"]))

    def test_automatic_question_gets_grounded_answer(self):
        response = answer_question(
            {"case": "MED", "mode": "auto", "question": "肝脏 CT 分割有哪些方法？"}, self.entries,
        )
        self.assertNotEqual(response.get("kind"), "general")
        self.assertTrue(response["results"])

    def test_unrelated_question_falls_back_to_general(self):
        response = answer_question(
            {"case": "MED", "mode": "auto", "question": "今天天气怎么样？"}, self.entries,
        )
        self.assertEqual(response["kind"], "general")
        self.assertTrue(response["notice"])
        self.assertEqual(response["results"], [])

    def test_unrelated_question_does_not_fall_back_to_selected_case(self):
        response = answer_question(
            {"case": "FIN", "mode": "auto", "question": "BFS对于计算机有什么用"},
            self.entries,
        )
        self.assertEqual(response["kind"], "general")
        self.assertEqual(response["results"], [])

    def test_concept_question_returns_mappings(self):
        response = answer_question(
            {"case": "MED", "mode": "concept",
             "question": "医学影像中的病灶区域识别，对应计算机视觉中的什么任务？"},
            self.entries,
        )
        self.assertEqual(response["mode"], "concept")
        self.assertIn("target", response["results"][0])
        self.assertTrue(response["references"])

    def test_unknown_case_is_rejected(self):
        with self.assertRaises(RequestError):
            answer_question({"case": "XXX", "mode": "method", "question": "肝脏分割"}, self.entries)


class KnowledgeOverlayTests(unittest.TestCase):
    def candidate(self):
        return {
            "article_id": uuid.uuid4().hex, "case_code": "MED", "title": "覆盖层测试",
            "scenario": "肝脏 CT 分割", "method": "OverlayNet", "concept": "图像分割",
            "rationale": "测试", "conditions": "有标注", "limitations": "小样本",
            "evidence": "测试证据", "notes": "",
        }

    def test_merge_assigns_next_id_and_entries_are_searchable(self):
        with tempfile.TemporaryDirectory() as temp:
            store = WorkspaceStore(Path(temp) / "workspace.sqlite3")
            candidate = store.candidate(self.candidate())
            store.review_candidate(candidate["id"], "approved")
            result = app.merge_approved_candidates(load_entries(KNOWLEDGE_DB), store)
            self.assertEqual(result["merged"], 1)
            overlay = store.knowledge_entries()
            self.assertEqual([entry["entry_id"] for entry in overlay], ["MED-20"])
            entries = app.cached_entries(KNOWLEDGE_DB, store)
            self.assertEqual(len(entries), 51)
            added = next(entry for entry in entries if entry["entry_id"] == "MED-20")
            self.assertTrue(added["case_name"])
            self.assertEqual(added["method"], "OverlayNet")
            catalog = app.case_catalog(entries)
            self.assertEqual(next(item for item in catalog if item["code"] == "MED")["count"], 17)
            response = app.answer_question(
                {"case": "MED", "mode": "method", "question": "OverlayNet 分割方法"}, entries)
            self.assertIn("MED-20", [item["entry_id"] for item in response["results"]])

    def test_merge_without_approved_entries_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = WorkspaceStore(Path(temp) / "workspace.sqlite3")
            with self.assertRaises(RequestError):
                app.merge_approved_candidates(load_entries(KNOWLEDGE_DB), store)


class ProjectReportTests(unittest.TestCase):
    def test_report_contains_project_chat_and_methods(self):
        with tempfile.TemporaryDirectory() as temp:
            store = WorkspaceStore(Path(temp) / "workspace.sqlite3")
            project = store.project({"name": "报告项目", "description": "测试说明"})
            chat = store.new_chat({
                "project_id": project["id"], "case_code": "MED", "mode": "auto",
                "title": "报告聊天",
            })
            turn = {
                "question": "肝脏分割有哪些方法？", "caseCode": "MED",
                "caseLabel": "医学影像", "mode": "method",
                "response": {
                    "answer": "推荐 U-Net。",
                    "results": [{"entry_id": "MED-01", "method": "U-Net", "scenario": "肝脏"}],
                    "references": [{"entry_id": "MED-01", "text": "证据", "links": []}],
                },
            }
            store.update_chat(chat["id"], {"turn": turn, "turn_id": str(uuid.uuid4())})
            report = app.build_project_report(
                store, None, store.project_by_id(project["id"]), {"MED": "医学影像"})
            self.assertIn("# 项目报告：报告项目", report)
            self.assertIn("报告聊天", report)
            self.assertIn("肝脏分割有哪些方法", report)
            self.assertIn("U-Net", report)
            self.assertIn("MED-01", report)
            self.assertIn("待核对条目", report)


class BackupTests(unittest.TestCase):
    def test_backup_creates_snapshot_and_keeps_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workspace.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE sample (value TEXT)")
                db.execute("INSERT INTO sample VALUES ('ok')")
            first = app.backup_workspace(path, keep=2)
            time.sleep(0.002)
            second = app.backup_workspace(path, keep=2)
            time.sleep(0.002)
            third = app.backup_workspace(path, keep=2)
            for target in (first, second, third):
                self.assertIsNotNone(target)
            self.assertTrue(third.exists())
            backups = list((Path(temp) / ".backups").glob("workspace-*.sqlite3"))
            self.assertEqual(len(backups), 2)
            self.assertTrue(all(target.exists() for target in backups))
            with closing(sqlite3.connect(backups[0])) as db:
                self.assertEqual(db.execute("SELECT value FROM sample").fetchone()[0], "ok")
            self.assertIsNone(app.backup_workspace(Path(temp) / "missing.sqlite3"))


class ThinkingTests(unittest.TestCase):
    def test_model_answer_keeps_reasoning(self):
        entry = next(item for item in load_entries(KNOWLEDGE_DB) if item["entry_id"] == "MED-01")
        hits = [entry]
        results = [entry]
        profile = SimpleNamespace(provider="deepseek")
        with patch.object(app, "generate", return_value=("推荐 [MED-01]。", "先分析问题。")):
            source, answer, notice, thinking = app.model_answer(
                "问题", "method", results, hits, profile, (), "问题")
        self.assertEqual(source, "deepseek")
        self.assertEqual(answer, "推荐 [MED-01]。")
        self.assertEqual(notice, "")
        self.assertEqual(thinking, "先分析问题。")

    def test_general_answer_keeps_reasoning(self):
        profile = SimpleNamespace(provider="deepseek")
        with patch.object(app, "generate", return_value=("普通回答", "普通思考")):
            result = app.general_answer("问题", profile, ())
        self.assertEqual(result["answer"], "普通回答")
        self.assertEqual(result["thinking"], "普通思考")
        self.assertEqual(result["source"], "deepseek")


class CandidateGenerationTests(unittest.TestCase):
    def test_fenced_json_is_parsed_and_limited(self):
        entries = [{"method": f"M{index}", "scenario": "scenario"} for index in range(5)]
        text = "```json\n" + json.dumps({"entries": entries}, ensure_ascii=False) + "\n```"
        self.assertEqual([item["method"] for item in parse_candidate_entries(text)],
                         ["M0", "M1", "M2"])

    def test_unparseable_answer_is_rejected(self):
        with self.assertRaises(RequestError):
            parse_candidate_entries("这里没有 JSON")

    def test_candidates_are_deduplicated_and_saved_for_review(self):
        saved = []

        class FakeWorkspace:
            def candidates(self):
                return [{"case_code": "MED", "method": "U-Net"}]

            def candidate(self, payload):
                saved.append(payload)
                return {"id": "candidate-1", **payload}

        article = {
            "id": "a" * 32, "title": "Liver segmentation", "authors": "Ada",
            "year": "2024", "venue": "Journal", "doi": "", "url": "https://example.org/paper",
            "abstract": "U-Net works.", "fulltext": {},
        }
        entries = [
            {"case_code": "MED", "method": "u net"},
            {"case_code": "FIN", "method": "Other method"},
        ]
        model_output = json.dumps({"entries": [
            {"method": "U-Net", "scenario": "肝脏分割"},
            {"method": "Transformer", "scenario": "肝脏分割", "concept": "分割",
             "rationale": "适合长距离依赖", "conditions": "数据充足",
             "limitations": "算力要求高", "evidence": "", "quote": "U-Net works."},
            {"method": "Transformer", "scenario": "重复条目"},
        ]}, ensure_ascii=False)
        with patch("app.generate", return_value=(model_output, "")) as generate:
            result = generate_literature_candidates(
                article, "MED", object(), FakeWorkspace(), entries)
        self.assertEqual([item["method"] for item in result["created"]], ["Transformer"])
        self.assertEqual(result["skipped"], ["U-Net", "Transformer"])
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["notes"], "由模型从文献自动提取，待核对。")
        self.assertIn("https://example.org/paper", saved[0]["evidence"])
        self.assertIn("原文片段：U-Net works.", saved[0]["evidence"])
        self.assertEqual(saved[0]["conditions"], "数据充足")
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[2].count("Liver segmentation"), 1)


def alignment_entry(entry_id, case_code, method, concept, evidence="来源 https://example.org/paper"):
    return {
        "entry_id": entry_id, "case_code": case_code, "case_name": case_code,
        "method": method, "concept": concept, "scenario": "研究场景",
        "rationale": "推荐理由", "conditions": "适用条件", "limitations": "局限",
        "evidence": evidence, "source_row": "",
    }


class AlignmentTests(unittest.TestCase):
    def test_result_parser_sanitizes_lists_and_evidence_ids(self):
        payload = {
            "source_concept": "病灶分割",
            "target_concept": "异常检测",
            "relation": "都关注偏离正常模式的位置",
            "same": [f"共同点 {index}" for index in range(9)],
            "differences": [{"dimension": "数据", "source": "影像", "target": "交易"}],
            "conditions": ["有标注"],
            "limitations": ["跨域迁移"],
            "consensus": ["需要人工复核"],
            "conflicts": [{"point": "标签", "source": "像素", "target": "交易", "reason": "粒度不同"}],
            "complements": ["规则与模型互补"],
            "suggestions": ["先做小样本验证"],
            "evidence_ids": ["[MED-04]", "FIN-01", "XXX-99", "FIN-01"],
            "confidence": "unsupported",
        }
        text = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        result = parse_alignment_result(text)
        self.assertEqual(len(result["same"]), 6)
        self.assertEqual(result["evidence_ids"], ["MED-04", "FIN-01", "XXX-99"])
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["differences"][0]["dimension"], "数据")

    def test_unparseable_result_is_rejected(self):
        with self.assertRaises(RequestError):
            parse_alignment_result("没有 JSON")

    def test_analysis_filters_unknown_evidence_and_adds_references(self):
        entries = [
            alignment_entry("MED-04", "MED", "UNet++", "病灶分割"),
            alignment_entry("FIN-01", "FIN", "逻辑回归", "违约概率"),
        ]
        model_output = json.dumps({
            "source_concept": "病灶分割", "target_concept": "异常检测",
            "relation": "都关注异常区域", "same": ["需要定位"],
            "differences": [{"dimension": "数据", "source": "影像", "target": "交易"}],
            "conditions": [], "limitations": [], "consensus": ["需要复核"],
            "conflicts": [], "complements": [], "suggestions": ["小样本验证"],
            "evidence_ids": ["MED-04", "FIN-01", "XXX-99"], "confidence": "medium",
        }, ensure_ascii=False)
        payload = {"source_case": "MED", "target_case": "FIN", "task": "term",
                   "input": "病灶分割"}
        with patch("app.generate", return_value=(model_output, "")) as generate:
            result = analyze_alignment(
                payload, entries, SimpleNamespace(provider="deepseek"))
        self.assertEqual(result["evidence_ids"], ["MED-04", "FIN-01"])
        self.assertEqual(len(result["references"]), 2)
        self.assertEqual(result["references"][0]["case_name"], "医学影像")
        self.assertEqual(result["source_label"], "医学影像")
        self.assertEqual(result["target_label"], "金融风险")
        self.assertEqual(result["model"], "DeepSeek")
        self.assertEqual(result["notice"], "")
        content = generate.call_args.args[2]
        self.assertIn("MED-04", content)
        self.assertIn("FIN-01", content)

    def test_analysis_accepts_sqlite_rows_from_the_real_database(self):
        entries = load_entries(KNOWLEDGE_DB)
        model_output = json.dumps({
            "source_concept": "病灶分割", "target_concept": "可疑交易识别",
            "relation": "都关注异常目标", "same": ["需要定位异常"],
            "differences": [{"dimension": "数据", "source": "影像", "target": "交易"}],
            "conditions": [], "limitations": [], "consensus": [], "conflicts": [],
            "complements": [], "suggestions": [], "evidence_ids": ["MED-01", "FIN-04"],
            "confidence": "medium",
        }, ensure_ascii=False)
        with patch("app.generate", return_value=(model_output, "")):
            result = analyze_alignment(
                {"source_case": "MED", "target_case": "FIN", "task": "term",
                 "input": "病灶分割"},
                entries, SimpleNamespace(provider="deepseek"))
        self.assertEqual([ref["entry_id"] for ref in result["references"]],
                         ["MED-01", "FIN-04"])
        self.assertEqual(result["references"][0]["case_name"], "医学影像")

    def test_human_edit_only_changes_allowed_fields(self):
        current = {"target_concept": "异常检测", "relation": "旧关系",
                   "evidence_ids": ["MED-04"]}
        merged = merge_alignment_edit(current, {
            "target_concept": "可疑交易识别", "relation": "新关系",
            "evidence_ids": ["FIN-01"], "unknown": "ignored",
        })
        self.assertEqual(merged["target_concept"], "可疑交易识别")
        self.assertEqual(merged["relation"], "新关系")
        self.assertEqual(merged["evidence_ids"], ["MED-04"])


class MethodDocCollectionTests(unittest.TestCase):
    def test_collect_counts_created_and_updated_records(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = WorkspaceStore(Path(temp) / "workspace.sqlite3")
            crawled = {
                "source": "sklearn", "label": "scikit-learn 用户指南", "found": 1,
                "documents": [{
                    "id": "a" * 32, "source": "sklearn",
                    "source_label": "scikit-learn 用户指南",
                    "url": "https://scikit-learn.org/stable/page.html",
                    "title": "Guide", "text": "Method documentation",
                }],
                "errors": [],
            }
            with patch("app.crawl_source", return_value=crawled):
                first = collect_method_docs("sklearn", "MED", workspace)
                second = collect_method_docs("sklearn", "MED", workspace)
            self.assertEqual(first["added"], 1)
            self.assertEqual(first["updated"], 0)
            self.assertEqual(second["added"], 0)
            self.assertEqual(second["updated"], 1)
            self.assertEqual(len(workspace.method_doc_runs()), 2)
            self.assertEqual(len(workspace.method_documents("MED")), 1)


class ContextTests(unittest.TestCase):
    def test_turns_are_ordered_oldest_first(self):
        recent = [
            {"question": "第一问", "response": {"answer": "第一答"}},
            {"question": "第二问", "response": {"answer": "第二答"}},
        ]
        self.assertEqual(conversation_context(recent), [
            {"提问": "第一问", "回答": "第一答"},
            {"提问": "第二问", "回答": "第二答"},
        ])

    def test_results_become_a_fallback_answer(self):
        recent = [{"question": "问", "response": {"results": [{"method": "U-Net"}, {"method": "V-Net"}]}}]
        context = conversation_context(recent)
        self.assertIn("U-Net", context[0]["回答"])

    def test_context_stays_within_budget(self):
        recent = [{"question": "问" * 600, "response": {"answer": "答" * 5000}} for _ in range(12)]
        context = conversation_context(recent)
        total = sum(len(item["提问"]) + len(item["回答"]) for item in context)
        self.assertLess(total, app.HISTORY_BUDGET)


if __name__ == "__main__":
    unittest.main()
