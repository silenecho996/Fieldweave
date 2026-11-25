from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context import SRC  # noqa: F401  (adds src/ to sys.path)

from literature import (
    LiteratureStore, STOPWORDS, article_record, arxiv_records, dataset_record,
    inverted_abstract,
)
from workspace_store import WorkspaceError, WorkspaceStore

ARXIV_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v2</id>
    <published>2024-01-02T00:00:00Z</published>
    <title>Liver Segmentation Revisited</title>
    <summary>A study of abdominal organ segmentation.</summary>
    <author><name>Ada Lovelace</name></author>
    <link rel="alternate" href="https://arxiv.org/abs/2401.01234v2"/>
    <category term="cs.CV"/>
  </entry>
</feed>"""

OPENALEX_RAW = {
    "id": "https://openalex.org/W1234567890",
    "title": "Liver segmentation with deep learning",
    "publication_year": 2023,
    "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
    "primary_location": {
        "source": {"display_name": "Medical Image Analysis"},
        "landing_page_url": "https://example.org/article",
    },
    "abstract_inverted_index": {
        "Deep": [0], "learning": [1], "improves": [2], "segmentation": [3],
    },
    "doi": "https://doi.org/10.1000/xyz123",
    "cited_by_count": "42",
    "open_access": {"is_oa": True},
    "topics": [{"display_name": "Medical imaging"}],
}

EUROPE_PMC_RAW = {
    "id": "12345", "source": "MED", "title": "Liver segmentation review",
    "authorString": "Ada Lovelace", "pubYear": "2024",
    "journalTitle": "Medical Image Analysis", "abstractText": "U-Net on CT",
    "doi": "10.1000/liver-review", "isOpenAccess": "Y", "citedByCount": 7,
}


def article_data(article_id, title, abstract, provider, kind="article"):
    return {
        "id": article_id, "title": title, "authors": "", "year": "2024",
        "journal": "", "doi": "", "provider": provider, "url": "https://example.org",
        "abstract": abstract, "pmcid": "", "can_fetch": False, "kind": kind,
    }


class LiteratureMigrationTests(unittest.TestCase):
    def test_kind_column_is_added_and_backfilled(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workspace.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript("""
                    CREATE TABLE literature_articles (
                        id TEXT PRIMARY KEY, data TEXT NOT NULL, fulltext TEXT,
                        collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                    CREATE TABLE literature_records (
                        article_id TEXT NOT NULL, provider TEXT NOT NULL, data TEXT NOT NULL,
                        PRIMARY KEY (article_id, provider));
                    CREATE TABLE literature_cases (
                        article_id TEXT NOT NULL, case_code TEXT NOT NULL,
                        PRIMARY KEY (case_code, article_id));
                """)
                paper = article_data("a1", "Liver segmentation", "deep learning", "Europe PMC")
                dataset = article_data("a2", "Liver data", "open dataset", "Zenodo")
                db.execute("INSERT INTO literature_articles (id, data) VALUES (?, ?)",
                           ("a1", json.dumps(paper)))
                db.execute("INSERT INTO literature_articles (id, data) VALUES (?, ?)",
                           ("a2", json.dumps(dataset)))
                db.execute("INSERT INTO literature_records VALUES ('a1', 'Europe PMC', '{}')")
                db.execute("INSERT INTO literature_records VALUES ('a2', 'Zenodo', '{}')")
                db.execute("INSERT INTO literature_cases VALUES ('a1', 'MED')")
                db.execute("INSERT INTO literature_cases VALUES ('a2', 'MED')")

            store = WorkspaceStore(path)
            library = LiteratureStore(store)
            with store.connect() as db:
                kinds = {row["article_id"]: row["kind"] for row in
                         db.execute("SELECT article_id, kind FROM literature_cases")}
            self.assertEqual(kinds, {"a1": "article", "a2": "dataset"})
            self.assertEqual([item["id"] for item in library.list("MED", "article")["articles"]], ["a1"])
            self.assertEqual([item["id"] for item in library.list("MED", "dataset")["articles"]], ["a2"])


class RelatedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.temp.name) / "workspace.sqlite3")
        self.library = LiteratureStore(self.store)
        with self.store.connect(write=True) as db:
            for article_id, title, abstract in [
                ("a1", "Deep learning for liver segmentation", "U-Net on CT scans"),
                ("a2", "Influenza forecasting", "time series models"),
            ]:
                data = article_data(article_id, title, abstract, "Europe PMC")
                db.execute("INSERT INTO literature_articles (id, data) VALUES (?, ?)",
                           (article_id, json.dumps(data)))
                db.execute("INSERT INTO literature_cases (case_code, article_id, kind) VALUES ('MED', ?, 'article')",
                           (article_id,))

    def tearDown(self):
        self.temp.cleanup()

    def test_chinese_aliases_find_english_records(self):
        related = self.library.related("MED", "肝脏分割")
        self.assertEqual(related[0]["id"], "a1")

    def test_stemming_matches_plural(self):
        self.assertEqual(LiteratureStore._match_count({self.library._stem("network")}, "neural networks"), 1)
        self.assertEqual(LiteratureStore._match_count({"liver"}, "livers"), 1)

    def test_stopwords_are_ignored(self):
        self.assertIn("model", STOPWORDS)
        self.assertEqual(LiteratureStore._match_count({"model"}, "model model"), 0)

    def test_related_results_are_capped_at_ten(self):
        with self.store.connect(write=True) as db:
            for index in range(12):
                data = article_data(
                    f"x{index}", f"Liver segmentation study {index}", "U-Net on CT scans",
                    "Europe PMC")
                db.execute("INSERT INTO literature_articles (id, data) VALUES (?, ?)",
                           (data["id"], json.dumps(data)))
                db.execute(
                    "INSERT INTO literature_cases (case_code, article_id, kind) VALUES ('MED', ?, 'article')",
                    (data["id"],))
        related = self.library.related("MED", "liver segmentation")
        self.assertEqual(len(related), 10)
        self.assertIn("citation_count", related[0])
        self.assertIn("open_access", related[0])


class ProviderRecordTests(unittest.TestCase):
    def test_openalex_rebuilds_abstract_and_metrics(self):
        record = article_record("OpenAlex", OPENALEX_RAW)
        self.assertIsNotNone(record)
        self.assertEqual(record["title"], "Liver segmentation with deep learning")
        self.assertEqual(record["abstract"], "Deep learning improves segmentation")
        self.assertEqual(record["year"], "2023")
        self.assertEqual(record["authors"], "Ada Lovelace")
        self.assertEqual(record["venue"], "Medical Image Analysis")
        self.assertEqual(record["doi"], "10.1000/xyz123")
        self.assertEqual(record["url"], "https://example.org/article")
        self.assertEqual(record["citation_count"], 42)
        self.assertTrue(record["open_access"])
        self.assertEqual(record["topics"], ["Medical imaging"])
        self.assertRegex(record["id"], r"^[0-9a-f]{32}$")

    def test_arxiv_atom_is_parsed_into_article(self):
        records = arxiv_records(ARXIV_XML)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["authors"], ["Ada Lovelace"])
        self.assertEqual(records[0]["categories"], ["cs.CV"])
        record = article_record("arXiv", records[0])
        self.assertIsNotNone(record)
        self.assertEqual(record["title"], "Liver Segmentation Revisited")
        self.assertEqual(record["year"], "2024")
        self.assertEqual(record["journal"], "arXiv")
        self.assertEqual(record["url"], "https://arxiv.org/abs/2401.01234v2")
        self.assertTrue(record["open_access"])
        self.assertEqual(record["topics"], ["cs.CV"])
        self.assertEqual(record["doi"], "")
        self.assertRegex(record["id"], r"^[0-9a-f]{32}$")

    def test_inverted_abstract_follows_word_positions(self):
        self.assertEqual(
            inverted_abstract({"world": [1], "Hello": [0], "again": [2]}),
            "Hello world again",
        )
        self.assertEqual(inverted_abstract(None), "")


class ExpandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.temp.name) / "workspace.sqlite3")
        self.library = LiteratureStore(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_expand_deduplicates_across_queries_and_providers(self):
        arxiv_raw = arxiv_records(ARXIV_XML)[0]

        def fake_fetch(provider, query, limit):
            if provider == "Europe PMC":
                return [dict(EUROPE_PMC_RAW)]
            return [dict(arxiv_raw)]

        with patch("literature.fetch_records", side_effect=fake_fetch) as fetch:
            result = self.library.expand({"case": "MED", "limit_per_query": 2})

        self.assertEqual(result["found"], 2)
        self.assertEqual(result["added"], 2)
        self.assertEqual(result["provider_counts"], {"Europe PMC": 5, "arXiv": 5})
        self.assertEqual(fetch.call_count, 10)
        articles = self.library.list("MED")["articles"]
        self.assertEqual(len(articles), 2)
        self.assertEqual(
            {article["provider"] for article in articles}, {"Europe PMC", "arXiv"})

    def test_expand_requires_a_known_case(self):
        with self.assertRaises(WorkspaceError):
            self.library.expand({"case": "UNKNOWN", "limit_per_query": 2})


class DatasetRecordTests(unittest.TestCase):
    def test_only_open_dataset_with_safe_files_is_accepted(self):
        raw = {
            "id": 42,
            "metadata": {
                "title": "Open liver data", "access_right": "open",
                "resource_type": {"type": "dataset"},
                "license": {"id": "cc-by-4.0"}, "creators": [], "doi": "10.5281/zenodo.42",
            },
            "files": [
                {"key": "data.csv", "size": 10, "checksum": "md5:" + "a" * 32},
                {"key": "../evil.csv", "size": 10, "checksum": "md5:" + "b" * 32},
            ],
        }
        record = dataset_record(raw)
        self.assertIsNotNone(record)
        self.assertEqual([file["name"] for file in record["files"]], ["data.csv"])
        self.assertTrue(record["files"][0]["can_import"])

    def test_closed_dataset_is_rejected(self):
        raw = {"id": 1, "metadata": {"title": "Closed", "access_right": "closed"}}
        self.assertIsNone(dataset_record(raw))


if __name__ == "__main__":
    unittest.main()
