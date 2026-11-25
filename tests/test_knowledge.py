import unittest

from context import KNOWLEDGE_DB

from knowledge import (
    CASE_PRESETS, COVERAGE, MAPPINGS, PAPER_LINKS, Mapping, align_concepts,
    automatic_scope, case_catalog, coverage_keyword_matches, coverage_report,
    follow_up_scope, mapping_matches, reference,
)
from search import load_entries


class ConfigTests(unittest.TestCase):
    def test_config_has_three_cases_and_mappings(self):
        self.assertEqual(set(CASE_PRESETS), {"MED", "EPI", "FIN"})
        for code in CASE_PRESETS:
            self.assertIn(code, MAPPINGS)
            self.assertTrue(MAPPINGS[code])

    def test_paper_links_are_loaded(self):
        self.assertTrue(PAPER_LINKS)
        self.assertRegex(PAPER_LINKS["UNETR: Transformers for 3D Medical Image Segmentation"], r"^\d{4}\.\d{4,5}")

    def test_catalog_counts_entries(self):
        catalog = {item["code"]: item for item in case_catalog(load_entries(KNOWLEDGE_DB))}
        self.assertEqual(catalog["MED"]["count"], 10)
        self.assertEqual(catalog["MED"]["label"], "医学影像")
        self.assertIn("method", catalog["MED"]["examples"])

    def test_ascii_keywords_use_word_boundaries(self):
        mapping = Mapping(("rt",), "a", "b", "c", "d", ("X-1",))
        self.assertEqual(mapping_matches(mapping, "heart rate"), set())
        self.assertEqual(mapping_matches(mapping, "估计 rt 值"), {"rt"})

    def test_coverage_taxonomy_has_tasks_for_every_case(self):
        self.assertEqual(set(COVERAGE), set(CASE_PRESETS))
        for code, tasks in COVERAGE.items():
            self.assertTrue(tasks)
            self.assertTrue(all(task.target >= 1 for task in tasks))
            self.assertEqual(len({task.key for task in tasks}), len(tasks))

    def test_coverage_report_counts_tasks_and_exposes_gaps(self):
        report = coverage_report(load_entries(KNOWLEDGE_DB), "MED")
        self.assertEqual(len(report["cases"]), 1)
        case = report["cases"][0]
        self.assertEqual(case["code"], "MED")
        self.assertEqual(case["entries"], 10)
        self.assertEqual(len(case["tasks"]), len(COVERAGE["MED"]))
        self.assertTrue(any(task["status"] == "gap" for task in case["tasks"]))
        for task in case["tasks"]:
            self.assertEqual(task["gap"], max(0, task["target"] - task["count"]))
            self.assertEqual(task["count"], len(task["entry_ids"]))
            self.assertIn(task["status"], {"gap", "thin", "covered"})

    def test_coverage_keywords_keep_ascii_word_boundaries(self):
        self.assertFalse(coverage_keyword_matches("rt", "heart rate"))
        self.assertTrue(coverage_keyword_matches("rt", "估计 rt 值"))


class AlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = load_entries(KNOWLEDGE_DB)
        cls.med = [item for item in cls.entries if item["case_code"] == "MED"]
        cls.epi = [item for item in cls.entries if item["case_code"] == "EPI"]

    def test_strongest_mapping_comes_first(self):
        mappings, evidence = align_concepts("需要定位病灶并给出边界框做检测", self.med, "MED")
        self.assertEqual(mappings[0]["target"], "目标检测")
        self.assertTrue(evidence)

    def test_segmentation_example(self):
        mappings, _ = align_concepts("医学影像中的病灶区域识别，对应计算机视觉中的什么任务？", self.med, "MED")
        self.assertEqual(mappings[0]["target"], "图像分割")

    def test_new_epi_mapping_is_reachable(self):
        targets = [item["target"] for item in
                   align_concepts("评估停课和口罩令的干预效果", self.epi, "EPI")[0]]
        self.assertIn("中断时间序列分析", targets)

    def test_unrelated_question_returns_no_mapping(self):
        mappings, evidence = align_concepts("今天天气怎么样", self.med, "MED")
        self.assertEqual(mappings, [])
        self.assertEqual(evidence, [])


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = load_entries(KNOWLEDGE_DB)

    def test_topic_question_routes_to_case(self):
        case, mode, _ = automatic_scope("肝脏 CT 分割有哪些方法", self.entries, "MED", ())
        self.assertEqual(case, "MED")
        self.assertEqual(mode, "method")

    def test_concept_intent_routes_to_concept(self):
        case, mode, _ = automatic_scope("病灶区域识别对应什么任务", self.entries, "MED", ())
        self.assertEqual((case, mode), ("MED", "concept"))

    def test_unrelated_question_has_no_scope(self):
        self.assertIsNone(automatic_scope("今天天气怎么样", self.entries, "MED", ()))

    def test_ordinal_follow_up_resolves_entry(self):
        recent = [{
            "question": "肝脏分割有哪些方法？",
            "caseCode": "MED",
            "response": {
                "retrieval_case": "MED", "mode": "method", "source": "local",
                "results": [{"entry_id": "MED-01"}, {"entry_id": "MED-02"}],
            },
        }]
        scope = follow_up_scope("第二种方法是什么", self.entries, recent)
        self.assertIsNotNone(scope)
        case, mode, query = scope
        self.assertEqual((case, mode), ("MED", "method"))
        self.assertIn("[MED-02]", query)

    def test_topic_reset_breaks_follow_up(self):
        recent = [{"question": "肝脏", "caseCode": "MED", "response": {
            "retrieval_case": "MED", "mode": "method", "source": "local",
            "results": [{"entry_id": "MED-01"}],
        }}]
        self.assertIsNone(follow_up_scope("换个话题：第二种方法", self.entries, recent))


class ReferenceTests(unittest.TestCase):
    def test_links_are_extracted_and_cleaned(self):
        item = {
            "entry_id": "MED-01",
            "evidence": "Ronneberger et al. https://arxiv.org/abs/1505.04597。另见 https://example.org/a",
        }
        result = reference(item)
        self.assertEqual(result["links"], [
            "https://arxiv.org/abs/1505.04597",
            "https://example.org/a",
        ])

    def test_links_with_credentials_are_skipped(self):
        item = {"entry_id": "X-1", "evidence": "https://user:pass@example.org/a"}
        self.assertEqual(reference(item)["links"], [])


if __name__ == "__main__":
    unittest.main()
