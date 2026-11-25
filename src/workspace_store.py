"""Local projects, conversations, turns, and files stored apart from the knowledge base."""

from base64 import b64decode
from binascii import Error as Base64Error
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import PurePath
import re
import sqlite3
from time import time_ns
from uuid import UUID, uuid4
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile
import zlib
from zlib import error as DecompressionError

from search import search_terms


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BODY = 4 * ((MAX_FILE_BYTES + 2) // 3) + 4096
MAX_CHAT_BODY = 8 * 1024 * 1024
MAX_PREVIEW_CHARS = 60_000
MAX_DOCUMENT_XML_BYTES = 2 * 1024 * 1024
MAX_PDF_STREAM_BYTES = 8 * 1024 * 1024
MAX_PDF_STREAMS = 300
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".tsv"}
FILE_EXTENSIONS = TEXT_EXTENSIONS | {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MODES = {"auto", "method", "concept"}
PROJECT_FIELDS = "id, name, description, sort_order"
CHAT_FIELDS = (
    "id, title, custom_title, project_id, case_code, mode, pinned_at, sort_order, updated_at"
)
CHAT_MIGRATION_FIELDS = "id, title, project_id, case_code, mode"
FILE_FIELDS = "id, name, size, project_id, chat_id, preview IS NOT NULL AS preview_available"
CANDIDATE_FIELDS = (
    "id, article_id, case_code, title, scenario, concept, method, rationale, "
    "conditions, limitations, evidence, notes, created_at, status, reviewed_at, "
    "merged_entry_id, review_note"
)
ALIGNMENT_FIELDS = (
    "id, project_id, source_case, target_case, task, input, model_result, "
    "final_result, status, note, created_at, reviewed_at"
)
MAX_ALIGNMENT_RESULT = 256_000
LOCAL_ENTRY_FIELDS = (
    "entry_id, case_code, scenario, concept, method, rationale, conditions, "
    "limitations, evidence, source_row, candidate_id, active"
)
CONTENT_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".pdf": "application/pdf",
}
WORD_PARAGRAPH = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
WORD_TEXT = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
CHAT_TABLE = """CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    custom_title INTEGER NOT NULL DEFAULT 0,
    project_id TEXT REFERENCES projects(id),
    case_code TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('auto', 'method', 'concept')),
    pinned_at INTEGER,
    sort_order INTEGER NOT NULL DEFAULT 0,
    deleted_at INTEGER,
    updated_at INTEGER NOT NULL
);"""
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    deleted_at INTEGER,
    created_at INTEGER NOT NULL
);
{CHAT_TABLE}
CREATE TABLE IF NOT EXISTS turns (
    ordinal INTEGER PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id),
    token TEXT,
    data TEXT NOT NULL,
    UNIQUE (chat_id, token)
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    size INTEGER NOT NULL,
    project_id TEXT REFERENCES projects(id),
    chat_id TEXT REFERENCES chats(id),
    preview TEXT,
    terms TEXT,
    content BLOB NOT NULL,
    created_at INTEGER NOT NULL,
    CHECK ((project_id IS NULL) <> (chat_id IS NULL))
);
CREATE INDEX IF NOT EXISTS turns_chat ON turns (chat_id, ordinal);
CREATE INDEX IF NOT EXISTS files_project ON files (project_id, created_at);
CREATE INDEX IF NOT EXISTS files_chat ON files (chat_id, created_at);
CREATE TABLE IF NOT EXISTS knowledge_candidates (
    id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    case_code TEXT NOT NULL,
    title TEXT NOT NULL,
    scenario TEXT NOT NULL,
    concept TEXT NOT NULL,
    method TEXT NOT NULL,
    rationale TEXT NOT NULL,
    conditions TEXT NOT NULL,
    limitations TEXT NOT NULL,
    evidence TEXT NOT NULL,
    notes TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_at INTEGER,
    merged_entry_id TEXT,
    review_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS candidates_case ON knowledge_candidates (case_code, created_at);
CREATE TABLE IF NOT EXISTS knowledge_entries_local (
    entry_id TEXT PRIMARY KEY,
    case_code TEXT NOT NULL,
    scenario TEXT NOT NULL,
    concept TEXT NOT NULL,
    method TEXT NOT NULL,
    rationale TEXT NOT NULL,
    conditions TEXT NOT NULL,
    limitations TEXT NOT NULL,
    evidence TEXT NOT NULL,
    source_row TEXT NOT NULL,
    candidate_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_versions (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    note TEXT NOT NULL,
    entries TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alignments (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    source_case TEXT NOT NULL,
    target_case TEXT NOT NULL,
    task TEXT NOT NULL,
    input TEXT NOT NULL,
    model_result TEXT NOT NULL,
    final_result TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    reviewed_at INTEGER
);
CREATE INDEX IF NOT EXISTS alignments_created ON alignments (created_at DESC);
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class WorkspaceError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def field_text(value, label, max_chars, *, required=False):
    if not isinstance(value, str):
        raise WorkspaceError(400, f"请填写{label}。")
    value = value.strip()
    if (required and not value) or len(value) > max_chars:
        raise WorkspaceError(400, f"{label}须在 {max_chars} 字以内。" if not required else f"{label}须为 1 至 {max_chars} 字。")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise WorkspaceError(400, f"{label}含有无法识别的字符。")
    return value


def ensure_object(value):
    if not isinstance(value, dict):
        raise WorkspaceError(400, "请求格式不正确。")
    return value


def normalize_mode(value):
    if not isinstance(value, str) or value not in MODES:
        raise WorkspaceError(400, "请选择方法推荐或概念对齐。")
    return value


def normalize_optional_id(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise WorkspaceError(400, "资源编号格式不正确。")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise WorkspaceError(400, "资源编号格式不正确。") from error
    if value.lower() not in {parsed.hex, str(parsed)}:
        raise WorkspaceError(400, "资源编号格式不正确。")
    return value.lower()


def normalize_turn(value):
    turn = ensure_object(value)
    clean = {
        "question": field_text(turn.get("question"), "问题", 600, required=True),
        "caseCode": field_text(turn.get("caseCode", ""), "案例编号", 40),
        "caseLabel": field_text(turn.get("caseLabel", ""), "案例名称", 120),
        "mode": normalize_mode(turn.get("mode")),
    }
    if "response" in turn and turn["response"] is not None:
        response = ensure_object(turn["response"])
        if (not isinstance(response.get("results"), list) or not isinstance(response.get("references"), list)
                or ("local_sources" in response and not isinstance(response["local_sources"], list))):
            raise WorkspaceError(400, "回答记录格式不正确。")
        clean["response"] = response
    if turn.get("error"):
        clean["error"] = field_text(turn["error"], "错误提示", 500)
    if "response" not in clean and "error" not in clean:
        raise WorkspaceError(400, "请保存已完成的问题和回答。")
    try:
        stored = json.dumps(clean, ensure_ascii=False, allow_nan=False)
        stored.encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as error:
        raise WorkspaceError(400, "回答记录含有无法保存的内容。") from error
    return clean, stored


def file_contents(payload):
    name = field_text(payload.get("name"), "文件名", 200, required=True)
    if any(char in name for char in "/\\") or any(ord(char) < 32 for char in name):
        raise WorkspaceError(400, "请使用不含路径的文件名。")
    extension = PurePath(name).suffix.lower()
    if extension not in FILE_EXTENSIONS:
        raise WorkspaceError(415, "请选择 PDF、DOCX、CSV、TSV、TXT、Markdown 或 PNG、JPEG、WebP 图片。")
    encoded = payload.get("data")
    if not isinstance(encoded, str):
        raise WorkspaceError(400, "没有收到文件内容。")
    if len(encoded) > 4 * ((MAX_FILE_BYTES + 2) // 3):
        raise WorkspaceError(413, "单个文件不能超过 5 MB。")
    try:
        content = b64decode(encoded, validate=True)
    except (ValueError, Base64Error) as error:
        raise WorkspaceError(400, "文件数据无法读取，请重新选择文件。") from error
    if not content:
        raise WorkspaceError(400, "请选择有内容的文件。")
    if len(content) > MAX_FILE_BYTES:
        raise WorkspaceError(413, "单个文件不能超过 5 MB。")
    return name, extension, content


PDF_STREAM = re.compile(rb"stream\s*\r?\n(.*?)endstream", re.S)
PDF_LITERAL = re.compile(rb"\((?:\\.|[^\\()])*\)")
PDF_HEX = re.compile(rb"<([0-9A-Fa-f\s]+)>\s*(?:Tj|'|\")")
PDF_ESCAPE = re.compile(rb"\\([nrtbf()\\]|[0-7]{1,3})")


def pdf_unescape(value):
    def replace(match):
        token = match.group(1)
        if token[:1] in b"01234567":
            return bytes([int(token, 8) & 0xFF])
        return {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(token, token)

    return PDF_ESCAPE.sub(replace, value)


def decode_pdf_text(value):
    if value.startswith(b"\xfe\xff"):
        return value[2:].decode("utf-16-be", "ignore")
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("latin-1", "ignore")


def inflate_pdf_stream(stream):
    try:
        engine = zlib.decompressobj()
        data = engine.decompress(stream, MAX_PDF_STREAM_BYTES + 1)
    except DecompressionError:
        return stream
    return b"" if len(data) > MAX_PDF_STREAM_BYTES else data


def pdf_stream_text(stream):
    data = inflate_pdf_stream(stream)
    parts = []
    for match in PDF_LITERAL.finditer(data):
        text = decode_pdf_text(pdf_unescape(match.group()[1:-1]))
        if text.strip():
            parts.append(text)
    for match in PDF_HEX.finditer(data):
        try:
            raw = bytes.fromhex(re.sub(rb"\s+", b"", match.group(1)).decode("ascii"))
        except ValueError:
            continue
        text = decode_pdf_text(raw)
        if text.strip():
            parts.append(text)
    return " ".join(parts)


def extract_pdf_text(content):
    """Best-effort text extraction for uncompressed and FlateDecode PDFs.

    Paths are not resolved through font ToUnicode maps, so CID-encoded
    documents may yield no usable text. Returning None keeps the preview
    honest instead of storing gibberish.
    """
    if not content.lstrip().startswith(b"%PDF") or b"/Encrypt" in content[:200_000]:
        return None
    chunks = []
    for index, match in enumerate(PDF_STREAM.finditer(content)):
        if index >= MAX_PDF_STREAMS:
            break
        text = pdf_stream_text(match.group(1))
        if text:
            chunks.append(text)
        if sum(len(chunk) for chunk in chunks) > MAX_PREVIEW_CHARS * 2:
            break
    text = "".join(char if char.isprintable() or char in "\n\t" else "" for char in "\n".join(chunks))
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 20:
        return None
    return text


def extract_preview(extension, content):
    if extension in TEXT_EXTENSIONS:
        if b"\x00" in content:
            return None
        try:
            value = content.decode("utf-8-sig")
        except UnicodeError:
            try:
                value = content.decode("gb18030")
            except UnicodeError:
                return None
    elif extension == ".docx":
        try:
            with ZipFile(BytesIO(content)) as document:
                with document.open("word/document.xml") as stream:
                    raw_markup = stream.read(MAX_DOCUMENT_XML_BYTES + 1)
            if len(raw_markup) > MAX_DOCUMENT_XML_BYTES:
                return None
            markup = raw_markup.decode("utf-8-sig")
            if "<!DOCTYPE" in markup:
                return None
            root = ElementTree.fromstring(markup)
            value = "\n".join(
                "".join(node.text or "" for node in paragraph.iter(WORD_TEXT))
                for paragraph in root.iter(WORD_PARAGRAPH)
            )
        except (BadZipFile, KeyError, RuntimeError, OSError, UnicodeError, DecompressionError, ElementTree.ParseError):
            return None
    elif extension == ".pdf":
        value = extract_pdf_text(content)
        if value is None:
            return None
    else:
        return None
    return value[:MAX_PREVIEW_CHARS].strip() or None


def preview_kind(name, has_preview):
    extension = PurePath(name).suffix.lower()
    if extension in {".png", ".jpg", ".jpeg", ".webp"}:
        return "image"
    if extension == ".pdf":
        return "pdf"
    return "text" if has_preview else "binary"


def search_snippet(text, query, radius=32):
    text = " ".join(text.split())
    index = text.casefold().find(query.casefold())
    if index < 0:
        clipped = text[:radius * 2]
        return clipped + ("…" if len(text) > len(clipped) else "")
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


class WorkspaceStore:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
            self.migrate_chat_modes(db)
            self.migrate_file_terms(db)
            self.migrate_sidebar_columns(db)
            self.migrate_knowledge_columns(db)
            self.migrate_lifecycle_columns(db)
            self.migrate_custom_titles(db)
        self.ensure_knowledge_baseline()

    @staticmethod
    def migrate_custom_titles(db):
        columns = {row[1] for row in db.execute("PRAGMA table_info(chats)")}
        if "custom_title" in columns:
            return
        with db:
            db.execute("ALTER TABLE chats ADD COLUMN custom_title INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def migrate_lifecycle_columns(db):
        chat_columns = {row[1] for row in db.execute("PRAGMA table_info(chats)")}
        project_columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
        entry_columns = {row[1] for row in db.execute("PRAGMA table_info(knowledge_entries_local)")}
        with db:
            if "deleted_at" not in chat_columns:
                db.execute("ALTER TABLE chats ADD COLUMN deleted_at INTEGER")
            if "deleted_at" not in project_columns:
                db.execute("ALTER TABLE projects ADD COLUMN deleted_at INTEGER")
            if "active" not in entry_columns:
                db.execute("ALTER TABLE knowledge_entries_local ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

    def ensure_knowledge_baseline(self):
        with self.connect(write=True) as db:
            if db.execute("SELECT 1 FROM knowledge_versions").fetchone():
                return
            db.execute(
                "INSERT INTO knowledge_versions (id, created_at, note, entries) VALUES (?, ?, ?, ?)",
                (uuid4().hex, time_ns(), "初始状态", "[]"),
            )

    @staticmethod
    def migrate_chat_modes(db):
        db.execute("PRAGMA foreign_keys=OFF")
        with db:
            db.execute("BEGIN IMMEDIATE")
            ddl = db.execute("SELECT sql FROM sqlite_master WHERE name='chats'").fetchone()[0]
            if "'auto'" in ddl:
                return
            db.execute(CHAT_TABLE.replace("EXISTS chats", "EXISTS chats_new"))
            columns = CHAT_MIGRATION_FIELDS + ", updated_at"
            db.execute(f"INSERT INTO chats_new ({columns}) SELECT {columns} FROM chats")
            db.execute("DROP TABLE chats")
            db.execute("ALTER TABLE chats_new RENAME TO chats")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise sqlite3.IntegrityError("Invalid workspace references during chat mode migration")

    @staticmethod
    def migrate_sidebar_columns(db):
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            if db.execute("SELECT 1 FROM schema_meta WHERE key='sidebar_order_v1'").fetchone():
                return
            chat_columns = {row[1] for row in db.execute("PRAGMA table_info(chats)")}
            project_columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
            if "pinned_at" not in chat_columns:
                db.execute("ALTER TABLE chats ADD COLUMN pinned_at INTEGER")
            if "sort_order" not in chat_columns:
                db.execute("ALTER TABLE chats ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            if "sort_order" not in project_columns:
                db.execute("ALTER TABLE projects ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            chat_rows = db.execute("SELECT id FROM chats ORDER BY updated_at DESC").fetchall()
            db.executemany("UPDATE chats SET sort_order=? WHERE id=?",
                           ((index, row[0]) for index, row in enumerate(chat_rows)))
            project_rows = db.execute("SELECT id FROM projects ORDER BY created_at").fetchall()
            db.executemany("UPDATE projects SET sort_order=? WHERE id=?",
                           ((index, row[0]) for index, row in enumerate(project_rows)))
            db.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('sidebar_order_v1', 'done')")

    @staticmethod
    def migrate_knowledge_columns(db):
        columns = {row[1] for row in db.execute("PRAGMA table_info(knowledge_candidates)")}
        with db:
            if "status" not in columns:
                db.execute("ALTER TABLE knowledge_candidates ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
            if "reviewed_at" not in columns:
                db.execute("ALTER TABLE knowledge_candidates ADD COLUMN reviewed_at INTEGER")
            if "merged_entry_id" not in columns:
                db.execute("ALTER TABLE knowledge_candidates ADD COLUMN merged_entry_id TEXT")
            if "review_note" not in columns:
                db.execute("ALTER TABLE knowledge_candidates ADD COLUMN review_note TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def migrate_file_terms(db):
        columns = {row[1] for row in db.execute("PRAGMA table_info(files)")}
        if "terms" in columns:
            return
        with db:
            db.execute("ALTER TABLE files ADD COLUMN terms TEXT")
            rows = db.execute("SELECT id, preview FROM files WHERE preview IS NOT NULL").fetchall()
            for file_id, preview in rows:
                db.execute("UPDATE files SET terms=? WHERE id=?",
                           (json.dumps(sorted(search_terms(preview)), ensure_ascii=False), file_id))

    @contextmanager
    def connect(self, *, write=False):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield db

    def index(self):
        with self.connect() as db:
            return {
                "projects": [dict(row) for row in db.execute(
                    f"SELECT {PROJECT_FIELDS} FROM projects WHERE deleted_at IS NULL"
                    " ORDER BY sort_order ASC, created_at ASC")],
                "chats": [dict(row) for row in db.execute(
                    f"SELECT {CHAT_FIELDS} FROM chats"
                    " WHERE deleted_at IS NULL AND (project_id IS NULL OR project_id IN"
                    " (SELECT id FROM projects WHERE deleted_at IS NULL))"
                    " ORDER BY (pinned_at IS NULL) ASC, sort_order ASC, updated_at DESC")],
                "files": [self.file_metadata(row) for row in db.execute(
                    f"SELECT {FILE_FIELDS} FROM files"
                    " WHERE (project_id IS NOT NULL AND project_id IN"
                    " (SELECT id FROM projects WHERE deleted_at IS NULL))"
                    " OR (chat_id IS NOT NULL AND chat_id IN"
                    " (SELECT id FROM chats WHERE deleted_at IS NULL))"
                    " ORDER BY created_at DESC")],
            }

    @staticmethod
    def file_metadata(row):
        file = dict(row)
        file["preview_available"] = bool(file["preview_available"])
        return file

    @staticmethod
    def project_row(db, project_id):
        project = db.execute(f"SELECT {PROJECT_FIELDS} FROM projects WHERE id=?", (project_id,)).fetchone()
        if project is None:
            raise WorkspaceError(404, "找不到该项目。")
        return project

    @staticmethod
    def chat_row(db, chat_id):
        chat = db.execute(f"SELECT {CHAT_FIELDS} FROM chats WHERE id=?", (chat_id,)).fetchone()
        if chat is None:
            raise WorkspaceError(404, "找不到该对话。")
        return chat

    @staticmethod
    def file_row(db, file_id, columns):
        row = db.execute(f"SELECT {columns} FROM files WHERE id=?", (file_id,)).fetchone()
        if row is None:
            raise WorkspaceError(404, "找不到该文件。")
        return row

    def project(self, payload, project_id=None):
        payload = ensure_object(payload)
        name = field_text(payload.get("name"), "项目名称", 80, required=True)
        description = field_text(payload.get("description", ""), "项目说明", 300)
        with self.connect(write=True) as db:
            if project_id is None:
                project_id = uuid4().hex
                sort_order = db.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM projects").fetchone()[0]
                db.execute(
                    "INSERT INTO projects (id, name, description, sort_order, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (project_id, name, description, sort_order, time_ns()),
                )
            else:
                self.project_row(db, project_id)
                db.execute("UPDATE projects SET name=?, description=? WHERE id=?", (name, description, project_id))
            return dict(self.project_row(db, project_id))

    def chat_data(self, db, chat_id):
        chat = dict(self.chat_row(db, chat_id))
        chat["turns"] = [
            json.loads(row["data"]) for row in
            db.execute("SELECT data FROM turns WHERE chat_id=? ORDER BY ordinal", (chat_id,))
        ]
        return chat

    def chat(self, chat_id):
        with self.connect() as db:
            return self.chat_data(db, chat_id)

    def recent_turns(self, chat_id):
        with self.connect() as db:
            self.chat_row(db, chat_id)
            rows = db.execute("SELECT data FROM turns WHERE chat_id=? ORDER BY ordinal DESC LIMIT 12", (chat_id,))
            return [json.loads(row["data"]) for row in reversed(rows.fetchall())]

    def new_chat(self, payload):
        payload = ensure_object(payload)
        chat_id = normalize_optional_id(payload.get("id")) or uuid4().hex
        project_id = normalize_optional_id(payload.get("project_id"))
        case_code = field_text(payload.get("case_code", ""), "案例编号", 40)
        mode = normalize_mode(payload.get("mode", "auto"))
        title = field_text(payload.get("title", "新对话"), "对话标题", 120, required=True)
        incoming = payload.get("turns", [])
        if not isinstance(incoming, list):
            raise WorkspaceError(400, "对话记录格式不正确。")
        turns = [normalize_turn(turn) for turn in incoming]
        if title == "新对话" and turns:
            title = " ".join(turns[0][0]["question"].split())[:120]
        with self.connect(write=True) as db:
            if db.execute("SELECT 1 FROM chats WHERE id=?", (chat_id,)).fetchone():
                return self.chat_data(db, chat_id)
            if project_id is not None:
                self.project_row(db, project_id)
            sort_order = db.execute("SELECT COALESCE(MIN(sort_order), 0) - 1 FROM chats").fetchone()[0]
            db.execute(
                "INSERT INTO chats (id, title, project_id, case_code, mode, pinned_at, sort_order, updated_at)"
                " VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                (chat_id, title, project_id, case_code, mode, sort_order, time_ns()),
            )
            db.executemany("INSERT INTO turns (chat_id, data) VALUES (?, ?)", ((chat_id, data) for _, data in turns))
            return self.chat_data(db, chat_id)

    def update_chat(self, chat_id, payload):
        payload = ensure_object(payload)
        turn = normalize_turn(payload["turn"]) if "turn" in payload else None
        turn_id = normalize_optional_id(payload.get("turn_id"))
        with self.connect(write=True) as db:
            chat = self.chat_row(db, chat_id)
            project_id = normalize_optional_id(payload.get("project_id", chat["project_id"]))
            if project_id is not None:
                self.project_row(db, project_id)
            case_code = field_text(payload.get("case_code", chat["case_code"]), "案例编号", 40)
            mode = normalize_mode(payload.get("mode", chat["mode"]))
            title = field_text(payload.get("title", chat["title"]), "对话标题", 120, required=True)
            custom_title = bool(chat["custom_title"])
            if "title" in payload and title != chat["title"] and title != "新对话":
                custom_title = True
            pinned_at = chat["pinned_at"]
            sort_order = chat["sort_order"]
            if project_id != chat["project_id"]:
                pinned_at = None
                sort_order = db.execute(
                    "SELECT COALESCE(MIN(sort_order), 0) - 1 FROM chats").fetchone()[0]
            if turn:
                values, stored = turn
                cursor = db.execute(
                    "INSERT INTO turns (chat_id, token, data) VALUES (?, ?, ?) ON CONFLICT (chat_id, token) DO NOTHING",
                    (chat_id, turn_id, stored),
                )
                if cursor.rowcount and title == "新对话":
                    title = " ".join(values["question"].split())[:120]
            db.execute(
                "UPDATE chats SET title=?, custom_title=?, project_id=?, case_code=?, mode=?,"
                " pinned_at=?, sort_order=?, updated_at=? WHERE id=?",
                (title, int(custom_title), project_id, case_code, mode,
                 pinned_at, sort_order, time_ns(), chat_id),
            )
            return self.chat_data(db, chat_id)

    def truncate_chat(self, chat_id, keep):
        """Keep the first `keep` turns, so an edited turn can be regenerated in place."""
        if not isinstance(keep, int) or isinstance(keep, bool) or keep < 0:
            raise WorkspaceError(400, "无法定位要编辑的问题。")
        with self.connect(write=True) as db:
            chat = self.chat_row(db, chat_id)
            total = db.execute("SELECT count(*) FROM turns WHERE chat_id=?", (chat_id,)).fetchone()[0]
            if keep > total:
                raise WorkspaceError(400, "无法定位要编辑的问题。")
            if keep == 0:
                db.execute("DELETE FROM turns WHERE chat_id=?", (chat_id,))
                # A renamed chat keeps its title when the first turn is regenerated.
                title = chat["title"] if chat["custom_title"] else "新对话"
            else:
                boundary = db.execute(
                    "SELECT ordinal FROM turns WHERE chat_id=? ORDER BY ordinal LIMIT 1 OFFSET ?",
                    (chat_id, keep - 1),
                ).fetchone()[0]
                db.execute("DELETE FROM turns WHERE chat_id=? AND ordinal > ?", (chat_id, boundary))
                title = chat["title"]
            db.execute("UPDATE chats SET title=?, updated_at=? WHERE id=?", (title, time_ns(), chat_id))
            return self.chat_data(db, chat_id)

    def pin_chat(self, chat_id, pinned):
        if type(pinned) is not bool:
            raise WorkspaceError(400, "置顶状态格式不正确。")
        with self.connect(write=True) as db:
            self.chat_row(db, chat_id)
            if pinned:
                sort_order = db.execute(
                    "SELECT COALESCE(MIN(sort_order), 0) - 1 FROM chats").fetchone()[0]
                db.execute("UPDATE chats SET pinned_at=?, sort_order=? WHERE id=?",
                           (time_ns(), sort_order, chat_id))
            else:
                db.execute("UPDATE chats SET pinned_at=NULL WHERE id=?", (chat_id,))
            return self.chat_data(db, chat_id)

    def move_chat(self, chat_id, project_id):
        project_id = normalize_optional_id(project_id)
        with self.connect(write=True) as db:
            self.chat_row(db, chat_id)
            if project_id is not None:
                self.project_row(db, project_id)
            sort_order = db.execute(
                "SELECT COALESCE(MIN(sort_order), 0) - 1 FROM chats").fetchone()[0]
            db.execute(
                "UPDATE chats SET project_id=?, pinned_at=NULL, sort_order=?, updated_at=?"
                " WHERE id=?",
                (project_id, sort_order, time_ns(), chat_id),
            )
            return self.chat_data(db, chat_id)

    def remove_chat(self, chat_id):
        with self.connect(write=True) as db:
            self.chat_row(db, chat_id)
            now = time_ns()
            db.execute("UPDATE chats SET deleted_at=?, updated_at=? WHERE id=?",
                       (now, now, chat_id))
        return {"removed": True}

    def remove_project(self, project_id, delete_files=False):
        if type(delete_files) is not bool:
            raise WorkspaceError(400, "删除选项格式不正确。")
        with self.connect(write=True) as db:
            self.project_row(db, project_id)
            now = time_ns()
            db.execute("UPDATE chats SET deleted_at=?, updated_at=? WHERE project_id=?",
                       (now, now, project_id))
            db.execute("UPDATE projects SET deleted_at=? WHERE id=?", (now, project_id))
        return {"removed": True, "files_removed": 0}

    def trash(self):
        with self.connect() as db:
            projects = [dict(row) for row in db.execute(
                "SELECT id, name, description, deleted_at FROM projects"
                " WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")]
            chats = [dict(row) for row in db.execute(
                "SELECT id, title, project_id, deleted_at FROM chats"
                " WHERE deleted_at IS NOT NULL AND (project_id IS NULL OR project_id IN"
                " (SELECT id FROM projects WHERE deleted_at IS NULL))"
                " ORDER BY deleted_at DESC")]
        for item in projects + chats:
            item["deleted_at"] = datetime.fromtimestamp(
                item["deleted_at"] / 1e9, timezone.utc).isoformat(timespec="seconds")
        return {"projects": projects, "chats": chats}

    def restore_chat(self, chat_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT id, project_id FROM chats WHERE id=?", (chat_id,)).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到该对话。")
            project_id = row["project_id"]
            if project_id is not None and db.execute(
                "SELECT deleted_at FROM projects WHERE id=?", (project_id,),
            ).fetchone()["deleted_at"] is not None:
                project_id = None
            db.execute("UPDATE chats SET deleted_at=NULL, project_id=? WHERE id=?",
                       (project_id, chat_id))
            return self.chat_data(db, chat_id)

    def restore_project(self, project_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到该项目。")
            db.execute("UPDATE projects SET deleted_at=NULL WHERE id=?", (project_id,))
            db.execute("UPDATE chats SET deleted_at=NULL WHERE project_id=?", (project_id,))
            return dict(self.project_row(db, project_id))

    def purge_chat(self, chat_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT deleted_at FROM chats WHERE id=?", (chat_id,)).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到该对话。")
            if row["deleted_at"] is None:
                raise WorkspaceError(409, "请先把聊天移入回收站。")
            db.execute("DELETE FROM files WHERE chat_id=?", (chat_id,))
            db.execute("DELETE FROM turns WHERE chat_id=?", (chat_id,))
            db.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        return {"purged": True}

    def purge_project(self, project_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT deleted_at FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到该项目。")
            if row["deleted_at"] is None:
                raise WorkspaceError(409, "请先把项目移入回收站。")
            db.execute("DELETE FROM turns WHERE chat_id IN (SELECT id FROM chats WHERE project_id=?)",
                       (project_id,))
            db.execute("DELETE FROM files WHERE project_id=? OR chat_id IN"
                       " (SELECT id FROM chats WHERE project_id=?)", (project_id, project_id))
            db.execute("DELETE FROM chats WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        return {"purged": True}

    def project_by_id(self, project_id):
        with self.connect() as db:
            row = db.execute(
                f"SELECT {PROJECT_FIELDS} FROM projects WHERE id=? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到该项目。")
            return dict(row)

    def project_chats(self, project_id):
        with self.connect() as db:
            rows = db.execute(
                "SELECT id FROM chats WHERE project_id=? AND deleted_at IS NULL"
                " ORDER BY updated_at DESC", (project_id,),
            ).fetchall()
            return [self.chat_data(db, row["id"]) for row in rows]

    def reorder(self, payload):
        payload = ensure_object(payload)
        groups = {}
        for key in ("projects", "chats"):
            ids = payload.get(key, [])
            if not isinstance(ids, list):
                raise WorkspaceError(400, "排序数据格式不正确。")
            if len(ids) > 500:
                raise WorkspaceError(400, "排序条目过多。")
            normalized = []
            for value in ids:
                item_id = normalize_optional_id(value)
                if item_id is None:
                    raise WorkspaceError(400, "排序数据格式不正确。")
                normalized.append(item_id)
            if len(set(normalized)) != len(normalized):
                raise WorkspaceError(400, "排序数据包含重复条目。")
            groups[key] = normalized
        with self.connect(write=True) as db:
            for key, normalized in groups.items():
                if not normalized:
                    continue
                table = "projects" if key == "projects" else "chats"
                placeholders = ",".join("?" for _ in normalized)
                existing = {row[0] for row in db.execute(
                    f"SELECT id FROM {table} WHERE id IN ({placeholders})", normalized)}
                if existing != set(normalized):
                    raise WorkspaceError(400, "排序条目不存在。")
                db.executemany(
                    f"UPDATE {table} SET sort_order=? WHERE id=?",
                    ((index, item_id) for index, item_id in enumerate(normalized)),
                )
        return {"reordered": True}

    def upload(self, payload):
        payload = ensure_object(payload)
        project_id = normalize_optional_id(payload.get("project_id"))
        chat_id = normalize_optional_id(payload.get("chat_id"))
        if (project_id is None) == (chat_id is None):
            raise WorkspaceError(400, "请选择把文件放到一个项目或一条对话中。")
        name, extension, content = file_contents(payload)
        preview = extract_preview(extension, content)
        terms = json.dumps(sorted(search_terms(preview)), ensure_ascii=False) if preview else None
        file_id = uuid4().hex
        with self.connect(write=True) as db:
            if project_id is not None:
                self.project_row(db, project_id)
            else:
                self.chat_row(db, chat_id)
            db.execute(
                "INSERT INTO files (id, name, size, project_id, chat_id, preview, terms, content, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (file_id, name, len(content), project_id, chat_id, preview, terms, content, time_ns()),
            )
            return self.file_metadata(self.file_row(db, file_id, FILE_FIELDS))

    def preview(self, file_id):
        with self.connect() as db:
            row = dict(self.file_row(db, file_id, f"{FILE_FIELDS}, preview"))
            preview = row.pop("preview")
            return self.file_metadata(row), preview, preview_kind(row["name"], bool(preview))

    def raw(self, file_id):
        with self.connect() as db:
            row = self.file_row(db, file_id, "name, content")
        extension = PurePath(row["name"]).suffix.lower()
        return row["name"], row["content"], CONTENT_TYPES.get(extension, "application/octet-stream")

    def download(self, file_id):
        with self.connect() as db:
            row = self.file_row(db, file_id, "name, content")
            return row["name"], row["content"]

    def remove_file(self, file_id):
        with self.connect(write=True) as db:
            cursor = db.execute("DELETE FROM files WHERE id=?", (file_id,))
            if not cursor.rowcount:
                raise WorkspaceError(404, "找不到该文件。")

    def local_sources(self, chat_id, question):
        with self.connect() as db:
            chat = self.chat_row(db, chat_id)
            files = db.execute(
                """
                SELECT id, name, preview, terms
                FROM files
                WHERE preview IS NOT NULL AND (chat_id=? OR project_id=?)
                ORDER BY created_at DESC
                LIMIT 80
                """,
                (chat_id, chat["project_id"]),
            ).fetchall()
        terms = search_terms(question)
        if not terms:
            return []
        matches = []
        for file in files:
            try:
                file_terms = set(json.loads(file["terms"])) if file["terms"] else search_terms(file["preview"])
            except (TypeError, ValueError):
                file_terms = search_terms(file["preview"])
            # Skip line-by-line tokenization unless the file as a whole matches.
            if not terms & file_terms:
                continue
            excerpts = re.findall(r"[^\r\n]{1,420}", file["preview"])
            score, excerpt = max(
                ((len(terms & search_terms(excerpt)), excerpt.strip()) for excerpt in excerpts), default=(0, ""),
            )
            if score and excerpt:
                matches.append((score, {"id": file["id"], "name": file["name"], "excerpt": excerpt}))
        matches.sort(key=lambda hit: hit[0], reverse=True)
        return [file for _, file in matches[:3]]

    def export(self):
        """Export projects, chats, turns and file metadata as JSON."""
        with self.connect() as db:
            projects = [dict(row) for row in db.execute(
                f"SELECT {PROJECT_FIELDS} FROM projects ORDER BY created_at DESC")]
            chats = [self.chat_data(db, row["id"]) for row in db.execute(
                "SELECT id FROM chats ORDER BY updated_at DESC")]
            files = [self.file_metadata(row) for row in db.execute(
                f"SELECT {FILE_FIELDS} FROM files ORDER BY created_at DESC")]
            alignments = [self.alignment_view(row, include_model=True) for row in db.execute(
                f"SELECT {ALIGNMENT_FIELDS} FROM alignments ORDER BY created_at DESC")]
        return {
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "projects": projects,
            "chats": chats,
            "files": files,
            "alignments": alignments,
            "note": "附件二进制内容未包含在此导出中；可在工作台逐个下载。",
        }

    @staticmethod
    def candidate_view(row):
        item = dict(row)
        item["created_at"] = datetime.fromtimestamp(
            item["created_at"] / 1e9, timezone.utc).isoformat(timespec="seconds")
        if item.get("reviewed_at"):
            item["reviewed_at"] = datetime.fromtimestamp(
                item["reviewed_at"] / 1e9, timezone.utc).isoformat(timespec="seconds")
        return item

    def candidate(self, payload):
        payload = ensure_object(payload)
        article_id = normalize_optional_id(payload.get("article_id"))
        if article_id is None:
            raise WorkspaceError(400, "缺少文献编号。")
        values = (
            article_id,
            field_text(payload.get("case_code"), "案例编号", 40, required=True),
            field_text(payload.get("title"), "标题", 800, required=True),
            field_text(payload.get("scenario"), "研究场景", 600, required=True),
            field_text(payload.get("concept", ""), "关联概念", 300),
            field_text(payload.get("method"), "方法名称", 300, required=True),
            field_text(payload.get("rationale", ""), "推荐理由", 1200),
            field_text(payload.get("conditions", ""), "适用条件", 600),
            field_text(payload.get("limitations", ""), "局限", 600),
            field_text(payload.get("evidence", ""), "证据", 3000),
            field_text(payload.get("notes", ""), "备注", 800),
        )
        candidate_id = uuid4().hex
        with self.connect(write=True) as db:
            db.execute(
                "INSERT INTO knowledge_candidates (article_id, case_code, title, scenario, concept,"
                " method, rationale, conditions, limitations, evidence, notes, id, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*values, candidate_id, time_ns()),
            )
            row = db.execute(
                f"SELECT {CANDIDATE_FIELDS} FROM knowledge_candidates WHERE id=?", (candidate_id,),
            ).fetchone()
            return self.candidate_view(row)

    def candidates(self):
        with self.connect() as db:
            return [self.candidate_view(row) for row in db.execute(
                f"SELECT {CANDIDATE_FIELDS} FROM knowledge_candidates ORDER BY created_at DESC")]

    def update_candidate(self, candidate_id, payload):
        payload = ensure_object(payload)
        with self.connect(write=True) as db:
            row = db.execute(
                f"SELECT {CANDIDATE_FIELDS} FROM knowledge_candidates WHERE id=?", (candidate_id,),
            ).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到这个待核对条目。")
            if row["status"] == "merged":
                raise WorkspaceError(409, "已入库条目不能再编辑。")
            article_id = normalize_optional_id(payload.get("article_id", row["article_id"]))
            if article_id is None:
                raise WorkspaceError(400, "缺少文献编号。")
            values = (
                article_id,
                field_text(payload.get("case_code", row["case_code"]), "案例编号", 40, required=True),
                field_text(payload.get("title", row["title"]), "标题", 800, required=True),
                field_text(payload.get("scenario", row["scenario"]), "研究场景", 600, required=True),
                field_text(payload.get("concept", row["concept"]), "关联概念", 300),
                field_text(payload.get("method", row["method"]), "方法名称", 300, required=True),
                field_text(payload.get("rationale", row["rationale"]), "推荐理由", 1200),
                field_text(payload.get("conditions", row["conditions"]), "适用条件", 600),
                field_text(payload.get("limitations", row["limitations"]), "局限", 600),
                field_text(payload.get("evidence", row["evidence"]), "证据", 3000),
                field_text(payload.get("notes", row["notes"]), "备注", 800),
            )
            db.execute(
                "UPDATE knowledge_candidates SET article_id=?, case_code=?, title=?, scenario=?,"
                " concept=?, method=?, rationale=?, conditions=?, limitations=?, evidence=?,"
                " notes=? WHERE id=?",
                (*values, candidate_id),
            )
            return self.candidate_view(db.execute(
                f"SELECT {CANDIDATE_FIELDS} FROM knowledge_candidates WHERE id=?", (candidate_id,),
            ).fetchone())

    def review_candidate(self, candidate_id, status, note=""):
        if status not in {"pending", "approved", "rejected"}:
            raise WorkspaceError(400, "审核状态不正确。")
        note = field_text(note, "审核备注", 800)
        with self.connect(write=True) as db:
            row = db.execute(
                f"SELECT {CANDIDATE_FIELDS} FROM knowledge_candidates WHERE id=?", (candidate_id,),
            ).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到这个待核对条目。")
            if row["status"] == "merged":
                raise WorkspaceError(409, "已入库条目不能再修改审核状态。")
            reviewed_at = time_ns() if status != "pending" else None
            db.execute(
                "UPDATE knowledge_candidates SET status=?, reviewed_at=?, review_note=? WHERE id=?",
                (status, reviewed_at, note, candidate_id),
            )
            return self.candidate_view(db.execute(
                f"SELECT {CANDIDATE_FIELDS} FROM knowledge_candidates WHERE id=?", (candidate_id,),
            ).fetchone())

    def approved_candidates(self):
        with self.connect() as db:
            return [self.candidate_view(row) for row in db.execute(
                f"SELECT {CANDIDATE_FIELDS} FROM knowledge_candidates"
                " WHERE status='approved' AND merged_entry_id IS NULL ORDER BY created_at")]

    def merge_candidates(self, assignments, note="候选条目合并"):
        if not assignments:
            raise WorkspaceError(400, "没有已通过的条目可以合并。")
        note = field_text(note, "版本说明", 300)
        candidate_ids = [item["candidate_id"] for item in assignments]
        placeholders = ",".join("?" for _ in candidate_ids)
        with self.connect(write=True) as db:
            rows = {row["id"]: row for row in db.execute(
                f"SELECT {CANDIDATE_FIELDS} FROM knowledge_candidates WHERE id IN ({placeholders})",
                candidate_ids,
            )}
            for item in assignments:
                row = rows.get(item["candidate_id"])
                if row is None or row["status"] != "approved" or row["merged_entry_id"]:
                    raise WorkspaceError(409, "有条目不在待合并状态，请刷新后重试。")
                if db.execute("SELECT 1 FROM knowledge_entries_local WHERE entry_id=?",
                              (item["entry_id"],)).fetchone():
                    raise WorkspaceError(409, "生成的条目编号已存在，请重试。")
            created = time_ns()
            for item in assignments:
                db.execute(
                    "INSERT INTO knowledge_entries_local (entry_id, case_code, scenario, concept,"
                    " method, rationale, conditions, limitations, evidence, source_row, candidate_id,"
                    " active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (item["entry_id"], item["case_code"], item["scenario"], item["concept"],
                     item["method"], item["rationale"], item["conditions"], item["limitations"],
                     item["evidence"], item["source_row"], item["candidate_id"], created),
                )
                db.execute(
                    "UPDATE knowledge_candidates SET status='merged', merged_entry_id=?, reviewed_at=?"
                    " WHERE id=?",
                    (item["entry_id"], created, item["candidate_id"]),
                )
            entries = [dict(row) for row in db.execute(
                f"SELECT {LOCAL_ENTRY_FIELDS} FROM knowledge_entries_local ORDER BY created_at")]
            version_id = self._snapshot_knowledge(db, note or "候选条目合并")
            return {"version": version_id, "merged": len(assignments), "total": len(entries)}

    def knowledge_entries(self, include_inactive=False):
        with self.connect() as db:
            sql = f"SELECT {LOCAL_ENTRY_FIELDS} FROM knowledge_entries_local"
            if not include_inactive:
                sql += " WHERE active=1"
            return [dict(row) for row in db.execute(sql + " ORDER BY created_at")]

    @staticmethod
    def _snapshot_knowledge(db, note):
        entries = [dict(row) for row in db.execute(
            f"SELECT {LOCAL_ENTRY_FIELDS} FROM knowledge_entries_local ORDER BY created_at")]
        version_id = uuid4().hex
        db.execute(
            "INSERT INTO knowledge_versions (id, created_at, note, entries) VALUES (?, ?, ?, ?)",
            (version_id, time_ns(), note, json.dumps(entries, ensure_ascii=False)),
        )
        return version_id

    def knowledge_versions(self):
        with self.connect() as db:
            rows = list(db.execute(
                "SELECT id, created_at, note, entries FROM knowledge_versions ORDER BY created_at ASC"))
        versions = []
        previous = {}
        for row in rows:
            entries = json.loads(row["entries"])
            for entry in entries:
                entry.setdefault("active", 1)
            current = {entry["entry_id"]: entry for entry in entries}
            added = [{"entry_id": key, "method": value["method"]}
                     for key, value in current.items() if key not in previous]
            removed = [{"entry_id": key, "method": value["method"]}
                       for key, value in previous.items() if key not in current]
            changed = [{"entry_id": key, "method": value["method"]}
                       for key, value in current.items()
                       if key in previous and previous[key] != value]
            versions.append({
                "id": row["id"],
                "created_at": datetime.fromtimestamp(
                    row["created_at"] / 1e9, timezone.utc).isoformat(timespec="seconds"),
                "note": row["note"],
                "count": len(entries),
                "added": added,
                "removed": removed,
                "changed": changed,
            })
            previous = current
        return list(reversed(versions))

    def update_local_entry(self, entry_id, payload):
        payload = ensure_object(payload)
        with self.connect(write=True) as db:
            row = db.execute(
                f"SELECT {LOCAL_ENTRY_FIELDS} FROM knowledge_entries_local WHERE entry_id=?",
                (entry_id,),
            ).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到这个工作台条目。")
            values = (
                field_text(payload.get("scenario", row["scenario"]), "研究场景", 600, required=True),
                field_text(payload.get("concept", row["concept"]), "关联概念", 300),
                field_text(payload.get("method", row["method"]), "方法名称", 300, required=True),
                field_text(payload.get("rationale", row["rationale"]), "推荐理由", 1200),
                field_text(payload.get("conditions", row["conditions"]), "适用条件", 600),
                field_text(payload.get("limitations", row["limitations"]), "局限", 600),
                field_text(payload.get("evidence", row["evidence"]), "证据", 3000),
            )
            db.execute(
                "UPDATE knowledge_entries_local SET scenario=?, concept=?, method=?, rationale=?,"
                " conditions=?, limitations=?, evidence=? WHERE entry_id=?",
                (*values, entry_id),
            )
            version = self._snapshot_knowledge(db, f"编辑条目 {entry_id}")
            return {
                "entry": dict(db.execute(
                    f"SELECT {LOCAL_ENTRY_FIELDS} FROM knowledge_entries_local WHERE entry_id=?",
                    (entry_id,)).fetchone()),
                "version": version,
            }

    def set_local_entry_active(self, entry_id, active):
        if type(active) is not bool:
            raise WorkspaceError(400, "条目状态格式不正确。")
        with self.connect(write=True) as db:
            row = db.execute(
                "SELECT entry_id FROM knowledge_entries_local WHERE entry_id=?", (entry_id,),
            ).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到这个工作台条目。")
            db.execute("UPDATE knowledge_entries_local SET active=? WHERE entry_id=?",
                       (1 if active else 0, entry_id))
            version = self._snapshot_knowledge(
                db, f"{'启用' if active else '停用'}条目 {entry_id}")
            return {
                "entry": dict(db.execute(
                    f"SELECT {LOCAL_ENTRY_FIELDS} FROM knowledge_entries_local WHERE entry_id=?",
                    (entry_id,)).fetchone()),
                "version": version,
            }

    def remove_local_entry(self, entry_id):
        with self.connect(write=True) as db:
            row = db.execute(
                "SELECT entry_id FROM knowledge_entries_local WHERE entry_id=?", (entry_id,),
            ).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到这个工作台条目。")
            db.execute("DELETE FROM knowledge_entries_local WHERE entry_id=?", (entry_id,))
            db.execute(
                "UPDATE knowledge_candidates SET status='approved', merged_entry_id=NULL"
                " WHERE merged_entry_id=?", (entry_id,))
            version = self._snapshot_knowledge(db, f"移出条目 {entry_id}")
            return {"removed": True, "version": version}

    def rollback_knowledge(self, version_id):
        with self.connect(write=True) as db:
            row = db.execute(
                "SELECT entries FROM knowledge_versions WHERE id=?", (version_id,),
            ).fetchone()
            if row is None:
                raise WorkspaceError(404, "找不到这个知识库版本。")
            entries = json.loads(row["entries"])
            db.execute("DELETE FROM knowledge_entries_local")
            for entry in entries:
                db.execute(
                    "INSERT INTO knowledge_entries_local (entry_id, case_code, scenario, concept,"
                    " method, rationale, conditions, limitations, evidence, source_row, candidate_id,"
                    " active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (entry["entry_id"], entry["case_code"], entry["scenario"], entry["concept"],
                     entry["method"], entry["rationale"], entry["conditions"], entry["limitations"],
                     entry["evidence"], entry["source_row"], entry.get("candidate_id"),
                     entry.get("active", 1), time_ns()),
                )
            ids = [entry["entry_id"] for entry in entries]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                db.execute(
                    f"UPDATE knowledge_candidates SET status='approved', merged_entry_id=NULL"
                    f" WHERE merged_entry_id IS NOT NULL AND merged_entry_id NOT IN ({placeholders})",
                    ids,
                )
                db.execute(
                    f"UPDATE knowledge_candidates SET status='merged' WHERE merged_entry_id IN ({placeholders})",
                    ids,
                )
            else:
                db.execute(
                    "UPDATE knowledge_candidates SET status='approved', merged_entry_id=NULL"
                    " WHERE merged_entry_id IS NOT NULL")
            return {"entries": len(entries)}

    def remove_candidate(self, candidate_id):
        with self.connect(write=True) as db:
            cursor = db.execute("DELETE FROM knowledge_candidates WHERE id=?", (candidate_id,))
            if not cursor.rowcount:
                raise WorkspaceError(404, "找不到这个待核对条目。")

    @staticmethod
    def alignment_view(row, include_model=False):
        item = dict(row)
        model_raw = item.pop("model_result", "{}")
        final_raw = item.pop("final_result", "{}")
        try:
            model = json.loads(model_raw) if isinstance(model_raw, str) else {}
        except ValueError:
            model = {}
        try:
            final = json.loads(final_raw) if isinstance(final_raw, str) else {}
        except ValueError:
            final = {}
        item["result"] = final
        item["edited"] = model != final
        if include_model:
            item["model_result"] = model
        for key in ("created_at", "reviewed_at"):
            if item.get(key):
                item[key] = datetime.fromtimestamp(
                    item[key] / 1e9, timezone.utc).isoformat(timespec="seconds")
        return item

    @staticmethod
    def _alignment_row(db, alignment_id):
        row = db.execute(
            f"SELECT {ALIGNMENT_FIELDS} FROM alignments WHERE id=?", (alignment_id,),
        ).fetchone()
        if row is None:
            raise WorkspaceError(404, "找不到这条对齐记录。")
        return row

    def alignment(self, alignment_id):
        with self.connect() as db:
            return self.alignment_view(
                self._alignment_row(db, alignment_id), include_model=True)

    def alignments(self, limit=30):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise WorkspaceError(400, "记录数量不正确。")
        with self.connect() as db:
            rows = db.execute(
                f"SELECT {ALIGNMENT_FIELDS} FROM alignments"
                " ORDER BY created_at DESC LIMIT ?", (limit,),
            ).fetchall()
        return [self.alignment_view(row) for row in rows]

    def create_alignment(self, payload):
        payload = ensure_object(payload)
        source_case = field_text(payload.get("source_case"), "源案例", 40, required=True)
        target_case = field_text(payload.get("target_case"), "目标案例", 40, required=True)
        if source_case == target_case:
            raise WorkspaceError(400, "源案例和目标案例需要不同。")
        task = payload.get("task")
        if task not in {"term", "compare"}:
            raise WorkspaceError(400, "请选择术语对齐或观点对照。")
        text = field_text(payload.get("input"), "对齐内容", 1200, required=True)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise WorkspaceError(400, "对齐结果格式不正确。")
        project_id = normalize_optional_id(payload.get("project_id"))
        model_result = json.dumps(result, ensure_ascii=False)
        if len(model_result) > MAX_ALIGNMENT_RESULT:
            raise WorkspaceError(400, "分析结果超过本地保存上限。")
        alignment_id = uuid4().hex
        with self.connect(write=True) as db:
            if project_id is not None:
                project = db.execute(
                    "SELECT 1 FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,),
                ).fetchone()
                if project is None:
                    raise WorkspaceError(404, "找不到该项目。")
            db.execute(
                "INSERT INTO alignments (id, project_id, source_case, target_case, task,"
                " input, model_result, final_result, status, note, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?)",
                (alignment_id, project_id, source_case, target_case, task, text,
                 model_result, model_result, time_ns()),
            )
            return self.alignment_view(
                self._alignment_row(db, alignment_id), include_model=True)

    def review_alignment(self, alignment_id, payload):
        payload = ensure_object(payload)
        status = payload.get("status")
        if status not in {"pending", "accepted", "rejected"}:
            raise WorkspaceError(400, "人工确认状态不正确。")
        note = field_text(payload.get("note", ""), "人工备注", 2000)
        final_result = payload.get("final_result")
        if final_result is not None and not isinstance(final_result, dict):
            raise WorkspaceError(400, "人工修订结果格式不正确。")
        with self.connect(write=True) as db:
            row = self._alignment_row(db, alignment_id)
            final_raw = row["final_result"]
            if final_result is not None:
                final_raw = json.dumps(final_result, ensure_ascii=False)
                if len(final_raw) > MAX_ALIGNMENT_RESULT:
                    raise WorkspaceError(400, "人工修订结果超过本地保存上限。")
            reviewed_at = time_ns() if status != "pending" else None
            db.execute(
                "UPDATE alignments SET final_result=?, status=?, note=?, reviewed_at=?"
                " WHERE id=?",
                (final_raw, status, note, reviewed_at, alignment_id),
            )
            return self.alignment_view(
                self._alignment_row(db, alignment_id), include_model=True)

    def export_candidates(self):
        entries = []
        for item in reversed(self.candidates()):
            note = f"备注：{item['notes']}\n" if item["notes"] else ""
            entries.append({
                "entry_id": f"PENDING-{item['id'][:12]}",
                "case_code": item["case_code"],
                "scenario": item["scenario"],
                "concept": item["concept"],
                "method": item["method"],
                "rationale": item["rationale"],
                "conditions": item["conditions"],
                "limitations": item["limitations"],
                "evidence": note + item["evidence"],
                "source_row": f"待核对：{item['title']}（文献 {item['article_id']}）",
            })
        return {
            "entries": entries,
            "note": "这些条目尚未写入只读知识库；核对后按 knowledge_entries 结构人工合并。",
        }

    def search_chats(self, query):
        query = field_text(query, "搜索词", 100)
        if not query:
            return []
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.connect() as db:
            rows = db.execute(
                """SELECT c.id, c.title, c.project_id, c.case_code, c.mode, t.data
                   FROM turns t JOIN chats c ON c.id=t.chat_id
                   WHERE t.data LIKE ? ESCAPE '\\'
                     AND c.deleted_at IS NULL
                     AND (c.project_id IS NULL OR c.project_id IN
                          (SELECT id FROM projects WHERE deleted_at IS NULL))
                   ORDER BY c.updated_at DESC, t.ordinal DESC
                   LIMIT 80""",
                (f"%{escaped}%",),
            ).fetchall()
        needle = query.casefold()
        groups = {}
        for row in rows:
            try:
                data = json.loads(row["data"])
            except ValueError:
                continue
            question = (data.get("question") or "").strip()
            answer = ((data.get("response") or {}).get("answer") or "").strip()
            haystack = question + "\n" + answer
            if needle not in haystack.casefold():
                continue
            group = groups.get(row["id"])
            if group is None:
                group = groups[row["id"]] = {
                    "chat_id": row["id"], "title": row["title"], "project_id": row["project_id"],
                    "case_code": row["case_code"], "mode": row["mode"], "matches": [],
                }
            if len(group["matches"]) < 2:
                group["matches"].append({
                    "question": question,
                    "snippet": search_snippet(haystack, query),
                })
        return list(groups.values())[:20]
