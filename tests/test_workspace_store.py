import base64
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
import zlib

from context import SRC  # noqa: F401  (adds src/ to sys.path)

from workspace_store import WorkspaceError, WorkspaceStore, extract_preview


def make_pdf(text, compress=False):
    content = f"BT /F1 12 Tf ({text}) Tj ET".encode("ascii")
    if compress:
        content = zlib.compress(content)
    return (b"%PDF-1.4\n1 0 obj\n<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
            + content + b"\nendstream\nendobj\n%%EOF\n")


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.temp.name) / "workspace.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def turn(self, question="肝脏分割有哪些方法？"):
        return {
            "question": question,
            "caseCode": "MED",
            "caseLabel": "医学影像",
            "mode": "method",
            "response": {"results": [], "references": []},
        }

    def test_project_chat_and_turn_round_trip(self):
        project = self.store.project({"name": "课题", "description": "说明"})
        chat = self.store.new_chat({
            "project_id": project["id"], "case_code": "MED", "mode": "auto", "title": "新对话",
        })
        self.assertEqual(chat["title"], "新对话")
        updated = self.store.update_chat(chat["id"], {
            "turn": self.turn(), "turn_id": str(uuid.uuid4()),
        })
        self.assertEqual(len(updated["turns"]), 1)
        self.assertEqual(updated["title"], "肝脏分割有哪些方法？")
        self.assertEqual(len(self.store.recent_turns(chat["id"])), 1)

    def test_duplicate_turn_is_ignored(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        token = str(uuid.uuid4())
        payload = {"turn": self.turn(), "turn_id": token}
        self.assertEqual(len(self.store.update_chat(chat["id"], payload)["turns"]), 1)
        self.assertEqual(len(self.store.update_chat(chat["id"], payload)["turns"]), 1)

    def test_truncate_chat_keeps_earlier_turns(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        for question in ("第一问", "第二问", "第三问"):
            self.store.update_chat(chat["id"], {
                "turn": self.turn(question), "turn_id": str(uuid.uuid4()),
            })
        truncated = self.store.truncate_chat(chat["id"], 1)
        self.assertEqual([turn["question"] for turn in truncated["turns"]], ["第一问"])
        self.assertEqual(truncated["title"], "第一问")

    def test_truncate_all_resets_title_for_regenerated_first_turn(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        self.store.update_chat(chat["id"], {
            "turn": self.turn("旧问题"), "turn_id": str(uuid.uuid4()),
        })
        truncated = self.store.truncate_chat(chat["id"], 0)
        self.assertEqual(truncated["turns"], [])
        self.assertEqual(truncated["title"], "新对话")
        updated = self.store.update_chat(chat["id"], {
            "turn": self.turn("新问题"), "turn_id": str(uuid.uuid4()),
        })
        self.assertEqual(updated["title"], "新问题")

    def test_renamed_chat_keeps_title_when_first_turn_is_regenerated(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        self.store.update_chat(chat["id"], {
            "turn": self.turn("旧问题"), "turn_id": str(uuid.uuid4()),
        })
        renamed = self.store.update_chat(chat["id"], {"title": "我的肝脏研究"})
        self.assertEqual(renamed["title"], "我的肝脏研究")
        self.assertEqual(renamed["custom_title"], 1)
        truncated = self.store.truncate_chat(chat["id"], 0)
        self.assertEqual(truncated["turns"], [])
        self.assertEqual(truncated["title"], "我的肝脏研究")
        regenerated = self.store.update_chat(chat["id"], {
            "turn": self.turn("新问题"), "turn_id": str(uuid.uuid4()),
        })
        self.assertEqual(regenerated["title"], "我的肝脏研究")

    def test_alignment_create_review_and_human_edit_round_trip(self):
        project = self.store.project({"name": "对齐项目"})
        record = self.store.create_alignment({
            "project_id": project["id"], "source_case": "MED", "target_case": "FIN",
            "task": "term", "input": "病灶分割", "result": {
                "source_concept": "病灶分割", "target_concept": "异常检测",
                "relation": "都关注异常区域", "evidence_ids": ["MED-04"],
            },
        })
        self.assertEqual(record["status"], "pending")
        self.assertFalse(record["edited"])
        self.assertEqual(record["result"]["target_concept"], "异常检测")
        self.assertEqual(len(self.store.alignments()), 1)

        reviewed = self.store.review_alignment(record["id"], {
            "status": "accepted", "note": "已和团队确认",
        })
        self.assertEqual(reviewed["status"], "accepted")
        self.assertEqual(reviewed["note"], "已和团队确认")
        self.assertTrue(reviewed["reviewed_at"])
        self.assertFalse(reviewed["edited"])

        edited = self.store.review_alignment(record["id"], {
            "status": "accepted", "note": "目标概念改为更具体的表述",
            "final_result": {
                **reviewed["result"], "target_concept": "可疑交易识别",
            },
        })
        self.assertTrue(edited["edited"])
        self.assertEqual(edited["result"]["target_concept"], "可疑交易识别")
        self.assertEqual(edited["model_result"]["target_concept"], "异常检测")
        self.assertEqual(self.store.alignment(record["id"])["result"]["target_concept"],
                         "可疑交易识别")

    def test_alignment_rejects_same_case(self):
        with self.assertRaises(WorkspaceError):
            self.store.create_alignment({
                "source_case": "MED", "target_case": "MED", "task": "term",
                "input": "分割", "result": {},
            })

    def test_truncate_rejects_invalid_keep(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        self.store.update_chat(chat["id"], {"turn": self.turn(), "turn_id": str(uuid.uuid4())})
        for keep in (-1, 2, "1", True, None, 1.0):
            with self.subTest(keep=keep), self.assertRaises(WorkspaceError):
                self.store.truncate_chat(chat["id"], keep)

    def test_pin_and_move_chat(self):
        project = self.store.project({"name": "项目"})
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        pinned = self.store.pin_chat(chat["id"], True)
        self.assertIsNotNone(pinned["pinned_at"])
        self.assertEqual(self.store.index()["chats"][0]["id"], chat["id"])
        moved = self.store.move_chat(chat["id"], project["id"])
        self.assertEqual(moved["project_id"], project["id"])
        self.assertIsNone(moved["pinned_at"])
        unpinned = self.store.pin_chat(chat["id"], False)
        self.assertIsNone(unpinned["pinned_at"])
        with self.assertRaises(WorkspaceError):
            self.store.pin_chat(chat["id"], "yes")

    def test_update_chat_move_unpins_and_reorders(self):
        project = self.store.project({"name": "项目"})
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        self.store.pin_chat(chat["id"], True)
        updated = self.store.update_chat(chat["id"], {"project_id": project["id"]})
        self.assertEqual(updated["project_id"], project["id"])
        self.assertIsNone(updated["pinned_at"])

    def test_reorder_chats_and_projects(self):
        first = self.store.project({"name": "P1"})
        second = self.store.project({"name": "P2"})
        chats = [self.store.new_chat({"case_code": "MED", "mode": "auto"}) for _ in range(3)]
        self.store.reorder({"chats": [chats[2]["id"], chats[0]["id"], chats[1]["id"]]})
        order = [chat["id"] for chat in self.store.index()["chats"]]
        self.assertEqual(order[:3], [chats[2]["id"], chats[0]["id"], chats[1]["id"]])
        self.store.reorder({"projects": [second["id"], first["id"]]})
        self.assertEqual([project["id"] for project in self.store.index()["projects"]],
                         [second["id"], first["id"]])
        for payload in (
            {"chats": [chats[0]["id"], chats[0]["id"]]},
            {"chats": [uuid.uuid4().hex]},
            {"chats": "invalid"},
            {"projects": [uuid.uuid4().hex]},
        ):
            with self.subTest(payload=payload), self.assertRaises(WorkspaceError):
                self.store.reorder(payload)

    def test_knowledge_entry_edit_disable_remove_and_diff(self):
        candidate = self.store.candidate(self.candidate_payload())
        self.store.review_candidate(candidate["id"], "approved")
        assignment = {
            "candidate_id": candidate["id"], "entry_id": "MED-92", "case_code": "MED",
            "scenario": candidate["scenario"], "concept": candidate["concept"],
            "method": candidate["method"], "rationale": candidate["rationale"],
            "conditions": candidate["conditions"], "limitations": candidate["limitations"],
            "evidence": candidate["evidence"], "source_row": "候选条目：测试",
        }
        self.store.merge_candidates([assignment], "初始合并")
        updated = self.store.update_local_entry("MED-92", {"method": "U-Net 改"})
        self.assertEqual(updated["entry"]["method"], "U-Net 改")
        inactive = self.store.set_local_entry_active("MED-92", False)
        self.assertEqual(inactive["entry"]["active"], 0)
        self.assertEqual(self.store.knowledge_entries(), [])
        self.assertEqual(len(self.store.knowledge_entries(include_inactive=True)), 1)
        versions = self.store.knowledge_versions()
        self.assertTrue(any(version["changed"] for version in versions))
        self.store.remove_local_entry("MED-92")
        self.assertEqual(self.store.knowledge_entries(include_inactive=True), [])
        restored = self.store.candidates()[0]
        self.assertEqual(restored["status"], "approved")
        self.assertIsNone(restored["merged_entry_id"])
        self.assertTrue(any(version["removed"] for version in self.store.knowledge_versions()))

    def test_remove_chat_moves_to_trash_then_purges(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        self.store.update_chat(chat["id"], {"turn": self.turn(), "turn_id": str(uuid.uuid4())})
        self.store.upload({
            "chat_id": chat["id"], "name": "a.txt",
            "data": base64.b64encode("内容".encode("utf-8")).decode("ascii"),
        })
        self.store.remove_chat(chat["id"])
        self.assertNotIn(chat["id"], [item["id"] for item in self.store.index()["chats"]])
        self.assertEqual(self.store.index()["files"], [])
        self.assertIn(chat["id"], [item["id"] for item in self.store.trash()["chats"]])
        self.store.restore_chat(chat["id"])
        self.assertIn(chat["id"], [item["id"] for item in self.store.index()["chats"]])
        self.store.remove_chat(chat["id"])
        self.store.purge_chat(chat["id"])
        with self.assertRaises(WorkspaceError):
            self.store.chat(chat["id"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM turns WHERE chat_id=?",
                                        (chat["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM files WHERE chat_id=?",
                                        (chat["id"],)).fetchone()[0], 0)

    def test_remove_project_moves_to_trash_then_restores(self):
        project = self.store.project({"name": "项目"})
        chat = self.store.new_chat({"project_id": project["id"], "case_code": "MED", "mode": "auto"})
        self.store.upload({
            "project_id": project["id"], "name": "p.txt",
            "data": base64.b64encode("内容".encode("utf-8")).decode("ascii"),
        })
        self.store.remove_project(project["id"])
        self.assertEqual(self.store.index()["projects"], [])
        self.assertEqual(self.store.index()["chats"], [])
        self.assertEqual(self.store.index()["files"], [])
        self.assertIn(project["id"], [item["id"] for item in self.store.trash()["projects"]])
        self.store.restore_project(project["id"])
        self.assertEqual([item["id"] for item in self.store.index()["projects"]], [project["id"]])
        self.assertEqual([item["id"] for item in self.store.index()["chats"]], [chat["id"]])
        self.assertEqual(len(self.store.index()["files"]), 1)
        self.store.remove_project(project["id"])
        self.store.purge_project(project["id"])
        self.assertEqual(self.store.index()["projects"], [])
        self.assertEqual(self.store.index()["chats"], [])
        self.assertEqual(self.store.index()["files"], [])
        with self.assertRaises(WorkspaceError):
            self.store.chat(chat["id"])

    def test_purge_requires_trash(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        project = self.store.project({"name": "项目"})
        with self.assertRaises(WorkspaceError):
            self.store.purge_chat(chat["id"])
        with self.assertRaises(WorkspaceError):
            self.store.purge_project(project["id"])

    def test_export_contains_projects_chats_and_note(self):
        project = self.store.project({"name": "课题"})
        chat = self.store.new_chat({"project_id": project["id"], "case_code": "MED", "mode": "auto"})
        self.store.update_chat(chat["id"], {"turn": self.turn(), "turn_id": str(uuid.uuid4())})
        exported = self.store.export()
        self.assertEqual(len(exported["projects"]), 1)
        self.assertEqual(len(exported["chats"]), 1)
        self.assertEqual(len(exported["chats"][0]["turns"]), 1)
        self.assertIn("附件二进制", exported["note"])
        self.assertIn("exported_at", exported)
        self.assertEqual(exported["alignments"], [])

    def test_search_chats_matches_questions(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        self.store.update_chat(chat["id"], {"turn": self.turn(), "turn_id": str(uuid.uuid4())})
        results = self.store.search_chats("肝脏")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["chat_id"], chat["id"])
        self.assertIn("肝脏", results[0]["matches"][0]["snippet"])
        self.assertEqual(self.store.search_chats("不存在的内容"), [])
        self.assertEqual(self.store.search_chats(""), [])

    def test_search_escapes_like_wildcards(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        self.store.update_chat(chat["id"], {"turn": self.turn("100% 匹配"), "turn_id": str(uuid.uuid4())})
        self.assertEqual(len(self.store.search_chats("%")), 1)

    def test_candidate_lifecycle_and_export(self):
        candidate = self.store.candidate({
            "article_id": uuid.uuid4().hex, "case_code": "MED", "title": "论文 A",
            "scenario": "肝脏 CT 分割", "method": "U-Net", "concept": "图像分割",
            "rationale": "常用基线", "conditions": "有标注", "limitations": "需要数据",
            "evidence": "Ronneberger et al.", "notes": "待核对",
        })
        self.assertEqual(len(self.store.candidates()), 1)
        exported = self.store.export_candidates()
        self.assertEqual(len(exported["entries"]), 1)
        self.assertTrue(exported["entries"][0]["entry_id"].startswith("PENDING-"))
        self.assertIn("待核对", exported["entries"][0]["evidence"])
        self.store.remove_candidate(candidate["id"])
        self.assertEqual(self.store.candidates(), [])

    def test_candidate_requires_article_and_method(self):
        with self.assertRaises(WorkspaceError):
            self.store.candidate({"case_code": "MED", "title": "A", "scenario": "S", "method": "M"})
        with self.assertRaises(WorkspaceError):
            self.store.candidate({
                "article_id": uuid.uuid4().hex, "case_code": "MED",
                "title": "A", "scenario": "S", "method": "",
            })

    def candidate_payload(self, title="论文 A"):
        return {
            "article_id": uuid.uuid4().hex, "case_code": "MED", "title": title,
            "scenario": "肝脏 CT 分割", "method": "U-Net", "concept": "图像分割",
            "rationale": "常用基线", "conditions": "有标注", "limitations": "需要数据",
            "evidence": "Ronneberger et al.", "notes": "待核对",
        }

    def test_candidate_edit_and_review(self):
        candidate = self.store.candidate(self.candidate_payload())
        self.assertEqual(candidate["status"], "pending")
        updated = self.store.update_candidate(candidate["id"], {
            "title": "改名后的候选", "method": "nnU-Net",
        })
        self.assertEqual(updated["title"], "改名后的候选")
        self.assertEqual(updated["method"], "nnU-Net")
        approved = self.store.review_candidate(candidate["id"], "approved", "已核对")
        self.assertEqual(approved["status"], "approved")
        self.assertIsNotNone(approved["reviewed_at"])
        self.assertEqual(approved["review_note"], "已核对")
        pending = self.store.review_candidate(candidate["id"], "pending")
        self.assertIsNone(pending["reviewed_at"])
        with self.assertRaises(WorkspaceError):
            self.store.review_candidate(candidate["id"], "unknown")

    def test_merge_candidates_and_rollback(self):
        candidate = self.store.candidate(self.candidate_payload())
        self.store.review_candidate(candidate["id"], "approved")
        assignment = {
            "candidate_id": candidate["id"], "entry_id": "MED-91", "case_code": "MED",
            "scenario": candidate["scenario"], "concept": candidate["concept"],
            "method": candidate["method"], "rationale": candidate["rationale"],
            "conditions": candidate["conditions"], "limitations": candidate["limitations"],
            "evidence": candidate["evidence"], "source_row": "候选条目：测试",
        }
        result = self.store.merge_candidates([assignment], "测试合并")
        self.assertEqual(result["merged"], 1)
        self.assertEqual(result["total"], 1)
        entries = self.store.knowledge_entries()
        self.assertEqual([entry["entry_id"] for entry in entries], ["MED-91"])
        merged = self.store.candidates()[0]
        self.assertEqual(merged["status"], "merged")
        self.assertEqual(merged["merged_entry_id"], "MED-91")
        with self.assertRaises(WorkspaceError):
            self.store.review_candidate(candidate["id"], "approved")
        with self.assertRaises(WorkspaceError):
            self.store.update_candidate(candidate["id"], {"title": "不能改"})
        versions = self.store.knowledge_versions()
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]["count"], 1)
        self.assertEqual(versions[-1]["note"], "初始状态")
        self.store.rollback_knowledge(versions[-1]["id"])
        self.assertEqual(self.store.knowledge_entries(), [])
        restored = self.store.candidates()[0]
        self.assertEqual(restored["status"], "approved")
        self.assertIsNone(restored["merged_entry_id"])
        with self.assertRaises(WorkspaceError):
            self.store.merge_candidates([], "空")

    def test_image_preview_kind_and_raw_content_type(self):
        chat = self.store.new_chat({"case_code": "MED", "mode": "auto"})
        payload = b"\x89PNG\r\n\x1a\n" + b"0" * 32
        file = self.store.upload({
            "chat_id": chat["id"], "name": "figure.png",
            "data": base64.b64encode(payload).decode("ascii"),
        })
        metadata, preview, kind = self.store.preview(file["id"])
        self.assertEqual(kind, "image")
        self.assertIsNone(preview)
        name, content, content_type = self.store.raw(file["id"])
        self.assertEqual((name, content, content_type), ("figure.png", payload, "image/png"))


class PdfExtractionTests(unittest.TestCase):
    def test_uncompressed_pdf_text(self):
        text = extract_preview(".pdf", make_pdf("Hello PDF extraction test"))
        self.assertIn("Hello PDF extraction test", text)

    def test_flate_compressed_pdf_text(self):
        text = extract_preview(".pdf", make_pdf("Compressed PDF text survives", compress=True))
        self.assertIn("Compressed PDF text survives", text)

    def test_encrypted_pdf_is_skipped(self):
        content = b"%PDF-1.4 /Encrypt 1 0 R\nstream\n(secret) Tj\nendstream\n"
        self.assertIsNone(extract_preview(".pdf", content))

    def test_non_pdf_bytes_are_skipped(self):
        self.assertIsNone(extract_preview(".pdf", b"not a pdf at all"))


class MigrationTests(unittest.TestCase):
    def test_old_candidate_schema_gets_review_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript("""
                    CREATE TABLE knowledge_candidates (
                        id TEXT PRIMARY KEY, article_id TEXT NOT NULL, case_code TEXT NOT NULL,
                        title TEXT NOT NULL, scenario TEXT NOT NULL, concept TEXT NOT NULL,
                        method TEXT NOT NULL, rationale TEXT NOT NULL, conditions TEXT NOT NULL,
                        limitations TEXT NOT NULL, evidence TEXT NOT NULL, notes TEXT NOT NULL,
                        created_at INTEGER NOT NULL);
                    INSERT INTO knowledge_candidates VALUES
                        ('c1', 'a1', 'MED', '标题', '场景', '概念', '方法', '理由',
                         '条件', '局限', '证据', '备注', 1);
                """)
            store = WorkspaceStore(path)
            with store.connect() as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(knowledge_candidates)")}
                self.assertTrue({"status", "reviewed_at", "merged_entry_id", "review_note"} <= columns)
                row = db.execute("SELECT status, review_note FROM knowledge_candidates WHERE id='c1'").fetchone()
                self.assertEqual((row["status"], row["review_note"]), ("pending", ""))

    def test_old_files_and_chat_schema_is_upgraded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript("""
                    CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL,
                        description TEXT NOT NULL, created_at INTEGER NOT NULL);
                    CREATE TABLE chats (id TEXT PRIMARY KEY, title TEXT NOT NULL,
                        project_id TEXT REFERENCES projects(id), case_code TEXT NOT NULL,
                        mode TEXT NOT NULL CHECK (mode IN ('method', 'concept')),
                        updated_at INTEGER NOT NULL);
                    CREATE TABLE turns (ordinal INTEGER PRIMARY KEY, chat_id TEXT NOT NULL,
                        token TEXT, data TEXT NOT NULL, UNIQUE (chat_id, token));
                    CREATE TABLE files (id TEXT PRIMARY KEY, name TEXT NOT NULL,
                        size INTEGER NOT NULL, project_id TEXT REFERENCES projects(id),
                        chat_id TEXT REFERENCES chats(id), preview TEXT,
                        content BLOB NOT NULL, created_at INTEGER NOT NULL);
                    INSERT INTO projects VALUES ('p1', '旧项目', '', 1);
                    INSERT INTO chats VALUES ('c1', '旧聊天', 'p1', 'MED', 'method', 2);
                    INSERT INTO files VALUES ('f1', '旧文件', 3, NULL, 'c1', '肝脏分割', X'00', 3);
                """)
            store = WorkspaceStore(path)
            with store.connect() as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(files)")}
                self.assertIn("terms", columns)
                terms = json.loads(db.execute("SELECT terms FROM files WHERE id='f1'").fetchone()[0])
                self.assertIn("肝脏", terms)
                chat = db.execute("SELECT mode, pinned_at, sort_order FROM chats WHERE id='c1'").fetchone()
                self.assertEqual(chat["mode"], "method")
                self.assertIsNone(chat["pinned_at"])
                self.assertEqual(chat["sort_order"], 0)
                project_columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
                self.assertIn("sort_order", project_columns)
                self.assertTrue(db.execute(
                    "SELECT 1 FROM schema_meta WHERE key='sidebar_order_v1'").fetchone())


if __name__ == "__main__":
    unittest.main()
