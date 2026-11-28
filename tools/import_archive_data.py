"""Merge teammate archive data into the local knowledge and literature stores.

The archives are treated as data only. No Python from either archive is executed.
"""

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from workspace_store import WorkspaceStore  # noqa: E402

BASE_DB = ROOT / "data" / "knowledge-base.sqlite3"
WORKSPACE_DB = ROOT / "data" / "workspace.sqlite3"
LIT_ARCHIVE = ROOT / "literature_crawler_submission_20261127.zip"
DATA_ARCHIVE = ROOT / "crawler_data_submission.zip"
BACKUP_DIR = ROOT / "data" / ".import-backups"
DOI = re.compile(r"10\.\d{4,}/[^\s<>\"'）】]+", re.I)
DOI_URL = re.compile(r"https?://(?:dx\.)?doi\.org/(10\.\d{4,}/[^\s<>\"'）】]+)", re.I)
ENTRY_FIELDS = (
    "entry_id", "case_code", "scenario", "concept", "method", "rationale",
    "conditions", "limitations", "evidence", "source_row",
)
EXTRA_FIELDS = {
    "paper_id": "INTEGER",
    "review_status": "TEXT DEFAULT '已复核'",
    "evidence_quote": "TEXT DEFAULT ''",
    "candidate_id": "INTEGER",
    "review_note": "TEXT DEFAULT ''",
    "review_source": "TEXT DEFAULT '人工复核'",
    "merged_into": "TEXT DEFAULT ''",
}
NEW_STATUS_SKIP = {"依据待补"}


def normalized_doi(value):
    if not isinstance(value, str):
        return ""
    value = value.strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    match = DOI.fullmatch(value)
    return value if match else ""


def read_archive_sqlite(archive):
    if not archive.exists():
        raise SystemExit(f"找不到归档：{archive}")
    with zipfile.ZipFile(archive) as zipped:
        name = next((name for name in zipped.namelist()
                     if name.lower().endswith(".sqlite3")), None)
        if name is None:
            raise SystemExit(f"归档中没有 SQLite 数据库：{archive}")
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as handle:
            handle.write(zipped.read(name))
            temporary = Path(handle.name)
    connection = sqlite3.connect(temporary.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection, temporary


def ensure_columns(connection):
    columns = {row[1] for row in connection.execute("PRAGMA table_info(knowledge_entries)")}
    with connection:
        for name, definition in EXTRA_FIELDS.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE knowledge_entries ADD COLUMN {name} {definition}")


def split_blocks(evidence):
    return [block.strip() for block in re.split(r"\n\s*\n", evidence or "") if block.strip()]


def block_doi(block):
    url = DOI_URL.search(block)
    if url:
        return normalized_doi(url.group(1))
    value = DOI.search(block)
    return normalized_doi(value.group(0)) if value else ""


def add_authors(block, authors):
    if not authors or "作者：" in block:
        return block
    lines = block.splitlines()
    index = len(lines)
    for position, line in enumerate(lines):
        if line.strip().lower().startswith(("http://", "https://")):
            index = position
            break
    lines.insert(index, "作者：" + authors.strip())
    return "\n".join(lines)


def enrich_evidence(evidence, literature_by_doi):
    blocks = split_blocks(evidence)
    if not blocks:
        return evidence or ""
    enriched = []
    for block in blocks:
        item = literature_by_doi.get(block_doi(block))
        if item and item["authors"]:
            block = add_authors(block, item["authors"])
        enriched.append(block)
    return "\n\n".join(enriched)


def build_new_evidence(entry, paper, literature_by_doi):
    evidence = (entry["evidence"] or "").strip()
    if not evidence:
        lines = []
        if paper and paper["title"]:
            suffix = f"（{paper['publication_year']}）" if paper["publication_year"] else ""
            lines.append(paper["title"] + suffix)
        if paper and paper["authors"]:
            lines.append("作者：" + paper["authors"])
        if paper and paper["venue"]:
            lines.append(paper["venue"])
        evidence = "\n".join(lines)
    if paper:
        evidence = add_authors(evidence, paper["authors"])
        doi = normalized_doi(paper["doi"])
        link = "https://doi.org/" + doi if doi else (paper["url"] or "")
        if link and link.lower() not in evidence.lower():
            evidence = (evidence + "\n" + link).strip()
    return enrich_evidence(evidence, literature_by_doi)


def import_base(base_path, lit_db, data_db, apply):
    current = sqlite3.connect(base_path)
    current.row_factory = sqlite3.Row
    if apply:
        ensure_columns(current)
        current.commit()
    lit_entries = {row["entry_id"]: dict(row) for row in lit_db.execute(
        "SELECT * FROM knowledge_entries")}
    lit_literature = {
        normalized_doi(row["doi"]): dict(row) for row in lit_db.execute(
            "SELECT * FROM literature")
    }
    current_entries = {row["entry_id"]: dict(row) for row in current.execute(
        "SELECT * FROM knowledge_entries")}
    changed = []
    for entry_id, current_entry in current_entries.items():
        lit_entry = lit_entries.get(entry_id)
        if not lit_entry:
            continue
        chosen = lit_entry["evidence"]
        if len(current_entry["evidence"] or "") > len(chosen or ""):
            chosen = current_entry["evidence"]
        enriched = enrich_evidence(chosen, lit_literature)
        if enriched != current_entry["evidence"]:
            changed.append((entry_id, enriched))
    new_entries = []
    for row in data_db.execute("SELECT * FROM knowledge_entries"):
        item = dict(row)
        if item["entry_id"] in current_entries:
            continue
        if item.get("merged_into"):
            continue
        if item.get("review_status") in NEW_STATUS_SKIP:
            continue
        paper = data_db.execute(
            "SELECT * FROM papers WHERE paper_id=?", (item.get("paper_id"),)
        ).fetchone()
        evidence = build_new_evidence(item, paper, lit_literature)
        new_entries.append({
            **{field: item.get(field, "") for field in ENTRY_FIELDS},
            "evidence": evidence,
            "source_row": ((item.get("source_row") or "")
                           + f"；OpenAlex paper_id={item.get('paper_id')}").strip("；"),
            "paper_id": item.get("paper_id"),
            "review_status": item.get("review_status", "已复核"),
            "evidence_quote": item.get("evidence_quote", ""),
            "candidate_id": item.get("candidate_id"),
            "review_note": item.get("review_note", ""),
            "review_source": item.get("review_source", "人工复核"),
            "merged_into": item.get("merged_into", ""),
        })
    print(f"evidence updates: {len(changed)}")
    print(f"new entries: {len(new_entries)}")
    for entry_id, _ in changed[:5]:
        print("  update", entry_id)
    for entry in new_entries[:5]:
        print("  add", entry["entry_id"], entry["method"][:50])
    if not apply:
        current.close()
        return {"changed": len(changed), "new": len(new_entries), "papers": 0}

    with current:
        current.execute("ALTER TABLE knowledge_entries ADD COLUMN paper_id INTEGER") \
            if "paper_id" not in {r[1] for r in current.execute(
                "PRAGMA table_info(knowledge_entries)")} else None
        for entry_id, evidence in changed:
            current.execute(
                "UPDATE knowledge_entries SET evidence=?, review_status='已复核',"
                " review_source=COALESCE(review_source, '原始知识库')"
                " WHERE entry_id=?", (evidence, entry_id))
        for entry in new_entries:
            columns = list(entry)
            placeholders = ",".join("?" for _ in columns)
            current.execute(
                f"INSERT OR IGNORE INTO knowledge_entries ({','.join(columns)})"
                f" VALUES ({placeholders})",
                [entry[column] for column in columns])
    current.close()
    return {"changed": len(changed), "new": len(new_entries), "papers": 0}


def import_papers(workspace_path, data_db, apply):
    queries = {}
    for row in data_db.execute("SELECT paper_id, case_code FROM paper_queries"):
        queries.setdefault(row["paper_id"], set()).add(row["case_code"])
    papers = list(data_db.execute("SELECT * FROM papers"))
    if not apply:
        print(f"papers: {len(papers)}")
        return 0
    store = WorkspaceStore(workspace_path)
    added = 0
    linked = 0
    with store.connect(write=True) as conn:
        for paper in papers:
            cases = queries.get(paper["paper_id"], set())
            if not cases:
                continue
            doi = normalized_doi(paper["doi"])
            key = doi or "OpenAlex:" + str(paper["source_id"])
            article_id = sha256(key.encode("utf-8")).hexdigest()[:32]
            article = {
                "id": article_id, "title": paper["title"] or "",
                "authors": paper["authors"] or "", "year": str(paper["publication_year"] or ""),
                "journal": paper["venue"] or "", "venue": paper["venue"] or "",
                "doi": doi, "provider": "OpenAlex",
                "url": paper["url"] or (("https://doi.org/" + doi) if doi else ""),
                "abstract": paper["abstract"] or "", "pmcid": "", "can_fetch": False,
                "citation_count": 0, "open_access": bool(paper["license"]), "topics": [],
            }
            cursor = conn.execute(
                "INSERT OR IGNORE INTO literature_articles (id, data) VALUES (?, ?)",
                (article_id, json.dumps(article, ensure_ascii=False)))
            if cursor.rowcount:
                added += 1
            conn.execute(
                "INSERT OR IGNORE INTO literature_records (article_id, provider, data)"
                " VALUES (?, 'OpenAlex', ?)", (article_id, paper["raw_json"] or "{}"))
            for case_code in cases:
                result = conn.execute(
                    "INSERT OR IGNORE INTO literature_cases (case_code, article_id, kind)"
                    " VALUES (?, ?, 'article')", (case_code, article_id))
                linked += result.rowcount
    print(f"papers added: {added}, case links: {linked}")
    return added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE_DB)
    parser.add_argument("--workspace", type=Path, default=WORKSPACE_DB)
    parser.add_argument("--lit-archive", type=Path, default=LIT_ARCHIVE)
    parser.add_argument("--data-archive", type=Path, default=DATA_ARCHIVE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lit_db, lit_temp = read_archive_sqlite(args.lit_archive)
    data_db, data_temp = read_archive_sqlite(args.data_archive)
    try:
        if args.apply:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(args.base, BACKUP_DIR / f"knowledge-before-{stamp}.sqlite3")
            if args.workspace.exists():
                shutil.copy2(args.workspace, BACKUP_DIR / f"workspace-before-{stamp}.sqlite3")
        base_result = import_base(args.base, lit_db, data_db, args.apply)
        papers = import_papers(args.workspace, data_db, args.apply)
        print(json.dumps({**base_result, "papers": papers, "applied": args.apply},
                         ensure_ascii=False, indent=2))
    finally:
        lit_db.close()
        data_db.close()
        lit_temp.unlink(missing_ok=True)
        data_temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
