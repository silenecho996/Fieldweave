import unittest

from context import SRC  # noqa: F401  (adds src/ to sys.path)

from method_docs import DocumentParser, clean_text, crawl_source, normalize_url, source_list


DOCUMENT = """
<html>
  <head><title>Methods Guide</title><script>not visible</script></head>
  <body>
    <nav>navigation menu</nav>
    <main>
      <h1>Choosing a method</h1>
      <p>This documentation explains how to choose a method for a research
      problem and which assumptions should be checked before applying it.
      It also describes the data requirements, evaluation criteria, common
      failure modes, and the conditions under which a simpler baseline may be
      a better choice for a cross-disciplinary research project.</p>
      <a href="/stable/page2.html?utm=1#section">Next page</a>
      <a href="https://evil.example/outside">Outside</a>
    </main>
  </body>
</html>
"""


class MethodDocParserTests(unittest.TestCase):
    def test_parser_skips_scripts_and_navigation(self):
        parser = DocumentParser()
        parser.feed(DOCUMENT)
        parser.close()
        text = clean_text(parser.parts)
        self.assertEqual(clean_text(parser.title_parts), "Methods Guide")
        self.assertIn("Choosing a method", text)
        self.assertNotIn("not visible", text)
        self.assertNotIn("navigation menu", text)
        self.assertIn("/stable/page2.html?utm=1#section", parser.links)

    def test_url_normalization_drops_query_and_fragment(self):
        self.assertEqual(
            normalize_url("https://scikit-learn.org/stable/page.html?x=1#top"),
            "https://scikit-learn.org/stable/page.html",
        )
        self.assertEqual(normalize_url("http://example.org/a"), "")

    def test_source_list_is_exposed(self):
        sources = source_list()
        self.assertTrue(sources)
        self.assertTrue(all("key" in item and "seed" in item for item in sources))


class MethodDocCrawlTests(unittest.TestCase):
    def fake_fetch(self, url):
        if url.endswith("page2.html"):
            return DOCUMENT.replace("Methods Guide", "Second Guide")
        return DOCUMENT

    def test_crawl_stays_on_whitelisted_domain_and_deduplicates(self):
        result = crawl_source(
            "sklearn", fetcher=self.fake_fetch,
            robots=lambda url: (True, ""), sleeper=lambda _: None,
            max_pages=2,
        )
        self.assertEqual(result["found"], 2)
        self.assertEqual(len(result["documents"]), 2)
        self.assertTrue(all(
            document["url"].startswith("https://scikit-learn.org/stable/")
            for document in result["documents"]
        ))
        self.assertIn("Choosing a method", result["documents"][0]["text"])
        self.assertNotIn("evil.example", " ".join(
            document["url"] for document in result["documents"]))

    def test_robots_disallow_stops_collection(self):
        result = crawl_source(
            "sklearn", fetcher=self.fake_fetch,
            robots=lambda url: (False, "robots.txt 禁止采集"),
            sleeper=lambda _: None, max_pages=2,
        )
        self.assertEqual(result["found"], 0)
        self.assertTrue(result["errors"])

    def test_invalid_source_is_rejected(self):
        with self.assertRaises(Exception):
            crawl_source("not-a-source", fetcher=self.fake_fetch)


class MethodDocWorkspaceTests(unittest.TestCase):
    def test_save_list_and_remove_round_trip(self):
        import tempfile
        from pathlib import Path
        from workspace_store import WorkspaceStore

        with tempfile.TemporaryDirectory() as temp:
            store = WorkspaceStore(Path(temp) / "workspace.sqlite3")
            document = store.save_method_document({
                "id": "a" * 32, "source": "sklearn",
                "source_label": "scikit-learn 用户指南",
                "url": "https://scikit-learn.org/stable/page.html",
                "title": "Guide", "text": "Long method documentation",
                "case_code": "MED",
            })
            self.assertEqual(document["case_code"], "MED")
            self.assertTrue(document["created"])
            listed = store.method_documents("MED")
            self.assertEqual(len(listed), 1)
            self.assertIn("excerpt", listed[0])
            self.assertNotIn("text", listed[0])
            detail = store.method_document("a" * 32)
            self.assertEqual(detail["text"], "Long method documentation")
            repeated = store.save_method_document({
                "id": "a" * 32, "source": "sklearn",
                "source_label": "scikit-learn 用户指南",
                "url": "https://scikit-learn.org/stable/page.html",
                "title": "Updated Guide", "text": "Updated text",
                "case_code": "MED",
            })
            self.assertFalse(repeated["created"])
            self.assertEqual(store.method_document("a" * 32)["title"], "Updated Guide")
            run = store.record_method_doc_run({
                "source": "sklearn", "case_code": "MED",
                "started_at": 1, "finished_at": 2,
                "found": 1, "created": 1, "updated": 0, "errors": ["one error"],
            })
            self.assertEqual(run["errors"], ["one error"])
            self.assertEqual(len(store.method_doc_runs()), 1)
            store.remove_method_document("a" * 32)
            self.assertEqual(store.method_documents("MED"), [])


if __name__ == "__main__":
    unittest.main()
