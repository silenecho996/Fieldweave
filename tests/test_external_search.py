import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from context import SRC  # noqa: F401

from external_search import parse_queries, search_external_literature
from app import answer_question
from search import load_entries
from context import KNOWLEDGE_DB


class ExternalQueryTests(unittest.TestCase):
    def test_parser_falls_back_to_original_question(self):
        self.assertEqual(parse_queries("not json", "BFS"), ["BFS"])
        self.assertEqual(
            parse_queries('```json\n{"queries":["breadth first search"]}\n```', "BFS"),
            ["breadth first search"],
        )

    def test_parser_respects_non_research_intent(self):
        self.assertEqual(
            parse_queries('{"research":false,"queries":[]}', "BFS"), [])

    def test_numeric_input_does_not_trigger_literature_search(self):
        with patch("external_search.generate") as generate, \
                patch("external_search.fetch_records") as fetch:
            result = search_external_literature("12346", SimpleNamespace(provider="deepseek"))
        self.assertFalse(result["research"])
        self.assertEqual(result["sources"], [])
        generate.assert_not_called()
        fetch.assert_not_called()

    def test_model_can_reject_non_research_input(self):
        with patch("external_search.generate",
                   return_value=('{"research":false,"queries":[]}', "")), \
                patch("external_search.fetch_records") as fetch:
            result = search_external_literature(
                "今天过得怎么样", SimpleNamespace(provider="deepseek"))
        self.assertEqual(result["sources"], [])
        fetch.assert_not_called()

    def test_technical_question_overrides_false_intent(self):
        with patch("external_search.generate",
                   return_value=('{"research":false,"queries":[]}', "")), \
                patch("external_search.fetch_records", return_value=[]) as fetch:
            result = search_external_literature(
                "Prim 算法是什么", SimpleNamespace(provider="deepseek"))
        self.assertTrue(result["research"])
        self.assertEqual(result["queries"], ["Prim 算法是什么"])
        self.assertEqual(fetch.call_count, 3)


class ExternalSearchTests(unittest.TestCase):
    def test_search_returns_deduplicated_public_sources(self):
        profile = SimpleNamespace(provider="deepseek")

        def fake_fetch(provider, query, limit):
            return [{
                "id": provider, "source": "MED", "title": "Breadth-first search",
                "authorString": "Ada Lovelace", "pubYear": "2020",
                "journalTitle": "Example", "abstractText": "Graph traversal",
                "doi": "10.1000/search",
            }]

        def fake_record(provider, raw):
            return {
                "id": "a" * 32, "title": "Breadth-first search",
                "authors": "Ada Lovelace", "year": "2020", "venue": "Example",
                "doi": "10.1000/search", "url": "https://doi.org/10.1000/search",
                "abstract": "Graph traversal", "provider": provider,
                "citation_count": 1, "topics": [],
            }

        with patch("external_search.generate",
                   return_value=('{"queries":["breadth first search"]}', "")), \
                patch("external_search.fetch_records", side_effect=fake_fetch), \
                patch("external_search.article_record", side_effect=fake_record):
            result = search_external_literature("BFS 是什么", profile)
        self.assertEqual(len(result["sources"]), 1)
        source = result["sources"][0]
        self.assertEqual(source["id"], "EXT-1")
        self.assertEqual(source["doi"], "10.1000/search")
        self.assertEqual(source["url"], "https://doi.org/10.1000/search")

    def test_no_profile_returns_nothing(self):
        self.assertEqual(search_external_literature("BFS", None)["sources"], [])


class ExternalAnswerTests(unittest.TestCase):
    def test_answer_uses_external_sources_when_local_has_no_hit(self):
        entries = load_entries(KNOWLEDGE_DB)
        source = {
            "id": "EXT-1", "title": "Breadth-first search", "authors": "Ada",
            "year": "2020", "venue": "Example", "doi": "10.1000/search",
            "url": "https://doi.org/10.1000/search", "provider": "OpenAlex",
            "abstract": "Graph traversal",
        }
        profile = SimpleNamespace(provider="deepseek")

        def external(_question):
            return {"queries": ["breadth first search"], "sources": [source], "errors": []}

        with patch("app.generate", return_value=("BFS 是逐层遍历图的方法 [EXT-1]", "")):
            result = answer_question(
                {"case": "MED", "mode": "auto", "question": "BFS 是什么"},
                entries, profile, external_fetcher=external)
        self.assertEqual(result["kind"], "external")
        self.assertEqual(result["source"], "deepseek")
        self.assertEqual(result["external_sources"][0]["id"], "EXT-1")
        self.assertIn("[EXT-1]", result["answer"])

    def test_numeric_input_returns_a_research_clarification(self):
        entries = load_entries(KNOWLEDGE_DB)
        profile = SimpleNamespace(provider="deepseek")

        def external(_question):
            return {"research": False, "queries": [], "sources": [], "errors": []}

        result = answer_question(
            {"case": "MED", "mode": "auto", "question": "12346"},
            entries, profile, external_fetcher=external)
        self.assertEqual(result["kind"], "general")
        self.assertEqual(result["source"], "local")
        self.assertIn("不是一个研究问题", result["answer"])
        self.assertEqual(result["external_sources"], [])


if __name__ == "__main__":
    unittest.main()
