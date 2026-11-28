import unittest

from context import KNOWLEDGE_DB

from search import load_entries, search, search_terms


def entry(entry_id, case, method, concept, scenario, rationale="", evidence="证据"):
    return {
        "entry_id": entry_id, "case_code": case, "case_name": case,
        "method": method, "concept": concept, "scenario": scenario,
        "rationale": rationale, "conditions": "", "limitations": "",
        "evidence": evidence, "source_row": "",
    }


class SearchTermsTests(unittest.TestCase):
    def test_chinese_bigrams_and_single_characters(self):
        self.assertIn("肝脏", search_terms("肝脏分割"))
        self.assertIn("分割", search_terms("肝脏分割"))
        self.assertIn("肝", search_terms("肝"))

    def test_common_terms_are_removed(self):
        self.assertNotIn("方法", search_terms("有什么方法"))
        self.assertNotIn("怎么", search_terms("怎么做"))

    def test_english_terms_survive(self):
        self.assertIn("segmentation", search_terms("liver segmentation"))
        self.assertNotIn("123", search_terms("123"))


class SearchRankingTests(unittest.TestCase):
    ENTRIES = [
        entry("MED-01", "MED", "U-Net", "肝脏分割", "肝脏 CT 分割", "U-Net 用于分割"),
        entry("MED-09", "MED", "Faster R-CNN", "病灶检测", "病灶定位", "检测框定位病灶"),
        entry("EPI-01", "EPI", "SIR 模型", "传播动力学", "传染病传播", "房室模型"),
    ]

    def test_matching_method_ranks_first(self):
        results = search("肝脏 CT 分割", self.ENTRIES)
        self.assertEqual(results[0]["entry_id"], "MED-01")

    def test_limit_is_respected(self):
        results = search("分割 检测 传播", self.ENTRIES, limit=1)
        self.assertEqual(len(results), 1)

    def test_unrelated_question_returns_nothing(self):
        self.assertEqual(search("今天天气怎么样", self.ENTRIES), [])

    def test_synonym_expansion(self):
        # “掩膜” expands to 分割, so the segmentation entry should be found.
        results = search("想要掩膜", self.ENTRIES)
        self.assertEqual(results[0]["entry_id"], "MED-01")

    def test_duplicate_methods_yield_to_a_distinct_alternative(self):
        entries = [
            entry("MED-01", "MED", "U-Net", "肝脏分割", "肝脏 CT 分割"),
            entry("MED-02", "MED", "U-Net", "肝脏分割", "肝脏 CT 分割"),
            entry("MED-03", "MED", "Transformer", "肝脏分割", "肝脏 CT 分割"),
        ]
        results = search("肝脏 CT 分割", entries, limit=2)
        self.assertEqual([item["entry_id"] for item in results], ["MED-01", "MED-03"])

    def test_exact_method_name_gets_a_bonus(self):
        entries = [
            entry("MED-01", "MED", "U-Net", "肝脏分割", "CT 分割"),
            entry("MED-02", "MED", "Transformer", "肝脏分割", "CT 分割"),
        ]
        self.assertEqual(search("请比较 U-Net 的适用条件", entries)[0]["entry_id"], "MED-01")

    def test_single_incidental_rationale_bigram_is_not_relevant(self):
        entries = [
            entry("FIN-14", "FIN", "XGBoost", "信用违约预测", "信用风险",
                  "模型在计算效率上表现较好"),
        ]
        self.assertEqual(search("BFS对于计算机有什么用", entries), [])


class RealKnowledgeBaseTests(unittest.TestCase):
    def test_database_contains_three_cases(self):
        entries = load_entries(KNOWLEDGE_DB)
        self.assertEqual(len(entries), 50)
        self.assertEqual({item["case_code"] for item in entries}, {"MED", "EPI", "FIN"})


if __name__ == "__main__":
    unittest.main()
