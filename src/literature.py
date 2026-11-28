"""Collect public research records and openly licensed articles into SQLite."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import md5, sha256
from html.parser import HTMLParser
from http.client import HTTPException
import json
from pathlib import Path
import re
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from search import search_terms
from workspace_store import WorkspaceError, WorkspaceStore, ensure_object, field_text


EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
CROSSREF = "https://api.crossref.org/works"
ZENODO = "https://zenodo.org/api/records"
OPENALEX = "https://api.openalex.org/works"
ARXIV = "https://export.arxiv.org/api/query"
ARXIV_NS = "{http://www.w3.org/2005/Atom}"
CASE_TOPICS = {
    "MED": (
        "liver segmentation CT", "medical image segmentation",
        "U-Net medical image segmentation", "transformer medical image segmentation",
        "abdominal organ segmentation",
    ),
    "EPI": (
        "time-varying reproduction number", "epidemic forecasting",
        "infectious disease nowcasting", "intervention effect epidemiology",
        "spatial clustering infectious disease",
    ),
    "FIN": (
        "credit risk default prediction", "fraud detection machine learning",
        "anti-money laundering detection", "graph neural network financial risk",
        "financial stress testing",
    ),
}
EXPAND_PROVIDERS = {
    "MED": ("Europe PMC", "arXiv"),
    "EPI": ("Europe PMC", "OpenAlex"),
    "FIN": ("OpenAlex", "Crossref"),
}
CASES = {
    "MED": ("Europe PMC", '"liver segmentation"'),
    "EPI": ("Europe PMC", '"time-varying reproduction number"'),
    "FIN": ("Crossref", "credit risk default prediction logistic regression"),
}
MAX_RECORDS = 10
MAX_METADATA = 3 * 1024 * 1024
MAX_ARTICLE = 4 * 1024 * 1024
MAX_DATA_FILE = 10 * 1024 * 1024
DATASET_QUERIES = {"MED": "liver segmentation", "EPI": "influenza", "FIN": "loan default"}
PMCID = re.compile(r"PMC[0-9]+")
DOI = re.compile(r"10\.\d{4,}/[^\s]+", re.IGNORECASE)
OPEN_LICENSE = re.compile(r"https?://creativecommons\.org/(?:licenses/[^/\s]+|publicdomain/(?:zero|mark))/[0-9.]+/?", re.I)
FIELD_ALIASES = {
    "肝脏": "liver", "肝": "liver", "分割": "segmentation", "勾画": "segmentation",
    "轮廓": "segmentation", "影像": "imaging", "计算机断层": "computed tomography",
    "磁共振": "magnetic resonance imaging", "超声": "ultrasound",
    "病灶": "lesion", "病变": "lesion", "肿瘤": "tumor", "结节": "nodule",
    "前列腺": "prostate", "胰腺": "pancreas", "脑": "brain", "肾": "kidney",
    "检测": "detection", "定位": "localization", "分类": "classification",
    "识别": "recognition", "标注": "annotation", "三维": "3d", "体素": "voxel",
    "深度学习": "deep learning", "神经网络": "neural network", "卷积": "convolutional",
    "疫情": "epidemic", "传播": "transmission", "再生数": "reproduction",
    "传播动力学": "transmission dynamics", "干预": "intervention", "疫苗": "vaccine",
    "病例": "incidence", "预测": "forecasting", "时间序列": "time series",
    "时空": "spatiotemporal", "聚集": "cluster", "统计": "statistics", "贝叶斯": "bayesian",
    "信用": "credit", "违约": "default", "借款": "credit", "风险": "risk",
    "逻辑回归": "logistic regression", "回归": "regression", "森林": "forest",
    "异常": "anomaly", "异常检测": "anomaly detection", "欺诈": "fraud",
    "反洗钱": "anti-money laundering", "交易": "transaction", "信用评分": "credit scoring",
    "波动": "volatility", "风险价值": "value at risk", "压力测试": "stress test",
    "文本": "text", "图神经网络": "graph neural network", "传染": "contagion",
}
STOPWORDS = {
    "the", "how", "what", "with", "for", "can", "use", "and", "which", "from", "into",
    "using", "based", "this", "that", "these", "those", "their", "our", "are", "was",
    "were", "has", "have", "had", "not", "but", "its", "his", "her", "they", "them",
    "study", "studies", "paper", "article", "research", "method", "methods", "model",
    "models", "data", "dataset", "datasets", "analysis", "result", "results",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS literature_articles (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    fulltext TEXT,
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS literature_records (
    article_id TEXT NOT NULL REFERENCES literature_articles(id),
    provider TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (article_id, provider)
);
CREATE TABLE IF NOT EXISTS literature_cases (
    article_id TEXT NOT NULL REFERENCES literature_articles(id),
    case_code TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'article',
    PRIMARY KEY (case_code, article_id)
);
CREATE TABLE IF NOT EXISTS literature_data_files (
    article_id TEXT NOT NULL REFERENCES literature_articles(id),
    file_id TEXT NOT NULL,
    content BLOB NOT NULL,
    PRIMARY KEY (article_id, file_id)
);
"""


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean(value, limit):
    if not isinstance(value, str):
        return ""
    reader = PlainText()
    reader.feed(value)
    reader.close()
    return " ".join(" ".join(reader.parts).split())[:limit]


def first(items):
    return items[0] if isinstance(items, list) and items else ""


def case_settings(case_code, kind="article"):
    if not isinstance(case_code, str) or case_code not in CASES:
        raise WorkspaceError(400, "请选择一个研究案例")
    if kind == "dataset":
        return "Zenodo", DATASET_QUERIES[case_code]
    if kind != "article":
        raise WorkspaceError(400, "请选择论文或公开数据集")
    return CASES[case_code]


def download(url, limit, *, missing=None):
    request = Request(url, headers={"User-Agent": "ResearchWorkbench/1.0 (academic literature prototype)", "Accept": "*/*"})
    try:
        with urlopen(request, timeout=12) as response:
            data = response.read(limit + 1)
    except HTTPError as error:
        error.close()
        if error.code == 429:
            raise WorkspaceError(429, "文献来源请求较多，请稍后重试") from error
        if error.code == 404 and missing:
            raise WorkspaceError(404, missing) from error
        raise WorkspaceError(502, "文献来源暂时无法提供数据，请稍后重试") from error
    except (URLError, OSError, HTTPException) as error:
        raise WorkspaceError(502, "无法连接文献来源，请确认网络后重试") from error
    if len(data) > limit:
        raise WorkspaceError(502, "来源返回内容超过单次处理上限")
    return data


def arxiv_records(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise WorkspaceError(502, "暂时无法读取 arXiv 返回数据") from error
    records = []
    for entry in root.findall(ARXIV_NS + "entry"):
        link = ""
        for node in entry.findall(ARXIV_NS + "link"):
            if node.attrib.get("rel") == "alternate" and node.attrib.get("href"):
                link = node.attrib["href"]
                break
        records.append({
            "id": (entry.findtext(ARXIV_NS + "id") or "").strip(),
            "title": (entry.findtext(ARXIV_NS + "title") or "").strip(),
            "summary": (entry.findtext(ARXIV_NS + "summary") or "").strip(),
            "published": (entry.findtext(ARXIV_NS + "published") or "").strip(),
            "authors": [(node.findtext(ARXIV_NS + "name") or "").strip()
                        for node in entry.findall(ARXIV_NS + "author")],
            "link": link,
            "categories": [node.attrib.get("term", "")
                           for node in entry.findall(ARXIV_NS + "category")],
        })
    return records


def fetch_records(provider, query, limit):
    if provider == "Europe PMC":
        params = {"query": f"TITLE_ABS:({query}) AND OPEN_ACCESS:Y", "format": "json",
                  "resultType": "core", "pageSize": limit}
        url = EUROPE_PMC + "search?" + urlencode(params)
    elif provider == "Crossref":
        params = {"query.bibliographic": query, "filter": "type:journal-article", "rows": limit}
        url = CROSSREF + "?" + urlencode(params)
    elif provider == "OpenAlex":
        params = {"search": query, "filter": "type:article", "per-page": limit}
        url = OPENALEX + "?" + urlencode(params)
    elif provider == "arXiv":
        params = {"search_query": f'all:"{query}"', "start": 0, "max_results": limit,
                  "sortBy": "relevance", "sortOrder": "descending"}
        url = ARXIV + "?" + urlencode(params)
    else:
        # Free text within a quoted clause keeps the open-access and resource filters in effect.
        term = query.replace('\\', ' ').replace('"', ' ').strip()
        params = {"q": f'resource_type.type:dataset AND access_right:open AND ("{term}")',
                  "size": limit}
        url = ZENODO + "?" + urlencode(params)
    raw = download(url, MAX_METADATA)
    if provider == "arXiv":
        return arxiv_records(raw)
    try:
        payload = json.loads(raw)
        if provider == "Europe PMC":
            return payload["resultList"]["result"]
        if provider == "Crossref":
            return payload["message"]["items"]
        if provider == "OpenAlex":
            return payload.get("results", [])
        return payload["hits"]["hits"]
    except (ValueError, KeyError, TypeError) as error:
        raise WorkspaceError(502, "暂时无法读取文献来源的返回数据") from error


def inverted_abstract(index):
    if not isinstance(index, dict):
        return ""
    positions = {}
    for word, spots in index.items():
        if isinstance(spots, list):
            for position in spots:
                if isinstance(position, int):
                    positions[position] = word
    return " ".join(positions[position] for position in sorted(positions))


def safe_int(value, fallback=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def article_record(provider, raw):
    journal = ""
    topics = []
    citations = 0
    open_access = False
    pmcid = ""
    can_fetch = False
    source_id = ""
    link = ""
    title = ""
    authors = ""
    year = ""
    abstract = ""
    doi = ""

    if provider == "Europe PMC":
        title = raw.get("title")
        authors = raw.get("authorString", "")
        year = raw.get("pubYear", "")
        journal = raw.get("journalTitle") or (
            (raw.get("journalInfo") or {}).get("journal", {}).get("title", ""))
        abstract = raw.get("abstractText", "")
        doi = raw.get("doi")
        source_id = clean(raw.get("id"), 120)
        pmcid = clean(raw.get("pmcid"), 24)
        source = clean(raw.get("source"), 20)
        if not PMCID.fullmatch(pmcid):
            pmcid = ""
        link = (f"https://europepmc.org/articles/{pmcid}" if pmcid else
                f"https://europepmc.org/article/{quote(source, safe='')}/"
                f"{quote(source_id, safe='')}")
        can_fetch = bool(pmcid and raw.get("isOpenAccess") == "Y")
        citations = safe_int(raw.get("citedByCount"))
        open_access = raw.get("isOpenAccess") == "Y"
        keywords = (raw.get("keywordList") or {}).get("keyword", [])
        if isinstance(keywords, dict):
            keywords = [keywords]
        topics = [clean(item, 120) for item in keywords[:8] if item]
    elif provider == "Crossref":
        title = first(raw.get("title"))
        authors = ", ".join(" ".join(filter(None, [person.get("given"), person.get("family")]))
                            for person in raw.get("author", [])[:50])
        year = first(first(raw.get("issued", {}).get("date-parts")))
        journal = first(raw.get("container-title"))
        abstract = raw.get("abstract", "")
        doi = raw.get("DOI")
        source_id = clean(doi, 300)
        citations = safe_int(raw.get("is-referenced-by-count"))
        open_access = bool(raw.get("license"))
        topics = [clean(item, 120) for item in (raw.get("subject") or [])[:8] if item]
    elif provider == "OpenAlex":
        title = raw.get("title") or raw.get("display_name")
        authors = ", ".join(
            (person.get("author") or {}).get("display_name", "")
            for person in (raw.get("authorships") or [])[:50])
        year = raw.get("publication_year", "")
        location = raw.get("primary_location") or {}
        journal = (location.get("source") or {}).get("display_name", "")
        abstract = inverted_abstract(raw.get("abstract_inverted_index"))
        doi = raw.get("doi") or ""
        source_id = str(raw.get("id", "")).rsplit("/", 1)[-1]
        link = location.get("landing_page_url", "") or raw.get("id", "")
        citations = safe_int(raw.get("cited_by_count"))
        open_access = bool((raw.get("open_access") or {}).get("is_oa"))
        topics = [clean(item.get("display_name"), 120)
                  for item in (raw.get("topics") or [])[:8] if item.get("display_name")]
    elif provider == "arXiv":
        title = raw.get("title")
        authors = ", ".join(raw.get("authors") or [])
        year = (raw.get("published") or "")[:4]
        journal = "arXiv"
        abstract = raw.get("summary", "")
        source_id = (raw.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
        source_id = re.sub(r"v\d+$", "", source_id)
        link = raw.get("link") or raw.get("id", "")
        open_access = True
        topics = [clean(item, 120) for item in (raw.get("categories") or [])[:8] if item]

    title = clean(title, 800)
    doi = clean(doi, 300).lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = doi if DOI.fullmatch(doi) else ""
    if not title or not (source_id or doi) or (provider == "Crossref" and not doi):
        return None
    if not link and doi:
        link = "https://doi.org/" + quote(doi, safe="/")
    article_id = sha256((doi or f"{provider}:{source_id}").encode()).hexdigest()[:32]
    return {
        "id": article_id, "title": title, "authors": clean(authors, 1500),
        "year": str(year or ""), "journal": clean(journal, 300),
        "venue": clean(journal, 300), "doi": doi, "provider": provider, "url": link,
        "abstract": clean(abstract, 14000), "pmcid": pmcid, "can_fetch": can_fetch,
        "citation_count": citations, "open_access": bool(open_access),
        "topics": [item for item in topics if item][:8],
    }


def dataset_record(raw):
    meta = raw.get("metadata", {})
    source_id = str(raw.get("id", ""))
    title = clean(meta.get("title"), 800)
    if not source_id.isdecimal() or not title or meta.get("access_right") != "open":
        return None
    if meta.get("resource_type", {}).get("type") != "dataset":
        return None
    license_id = clean((meta.get("license") or {}).get("id"), 80).lower()
    openly_licensed = bool(re.fullmatch(r"cc-(?:zero|by(?:-sa|-nc|-nc-sa|-nd|-nc-nd)?-[1-4]\.0)", license_id))
    doi = clean(meta.get("doi"), 300).lower()
    files = []
    for file in (raw.get("files") or []):
        name, size = file.get("key"), file.get("size")
        checksum = file.get("checksum", "")
        if not isinstance(name, str) or name in {"", ".", ".."} or not isinstance(size, int) or size <= 0:
            continue
        if any(char in name for char in "/\\") or any(ord(char) < 32 for char in name):
            continue
        file_id = sha256(name.encode()).hexdigest()[:24]
        allowed = openly_licensed and size <= MAX_DATA_FILE and bool(re.fullmatch(r"md5:[a-f0-9]{32}", checksum))
        files.append({"id": file_id, "name": name, "size": size, "checksum": checksum, "can_import": allowed})
    return {
        "id": sha256(f"Zenodo:{source_id}".encode()).hexdigest()[:32],
        "title": title, "authors": ", ".join(clean(person.get("name"), 120) for person in meta.get("creators", [])[:30]),
        "year": clean(meta.get("publication_date"), 10)[:4], "journal": "", "doi": doi if DOI.fullmatch(doi) else "",
        "provider": "Zenodo", "url": f"https://zenodo.org/records/{source_id}", "source_id": source_id,
        "abstract": clean(meta.get("description"), 14000), "license": license_id, "files": files, "can_fetch": False,
    }


def parse_fulltext(data):
    # Europe PMC JATS uses UTF-8. Refuse entity definitions before parsing untrusted XML.
    try:
        source = data.decode("utf-8-sig")
        if re.search(r"<!\s*ENTITY", source, re.I) or "\0" in source:
            raise ValueError("Unsupported XML")
        article = ET.fromstring(source)
    except (ValueError, ET.ParseError) as error:
        raise WorkspaceError(502, "暂时无法读取来源提供的全文格式") from error
    license_text = " ".join(" ".join(node.itertext()).strip() for node in article.findall(".//license"))
    license_urls = [OPEN_LICENSE.search(node.attrib.get("{http://www.w3.org/1999/xlink}href", ""))
                    for node in article.findall(".//license") + article.findall(".//license//ext-link")]
    license_url = next((match.group() for match in license_urls if match), "")
    if not license_url:
        match = OPEN_LICENSE.search(license_text)
        license_url = match.group() if match else ""
    if not license_url:
        raise WorkspaceError(422, "未找到可识别的开放许可，请从论文来源查看全文")
    body = article.find("./body")
    if body is None:
        raise WorkspaceError(422, "来源没有返回可读取的正文")
    paragraphs = [" ".join("".join(node.itertext()).split()) for node in body.iter()
                  if node.tag in {"title", "p"}]
    content = "\n\n".join(filter(None, paragraphs))
    if not content:
        raise WorkspaceError(422, "来源没有返回可读取的正文")
    sections = []
    for section in body.findall("./sec"):
        title_node = section.find("./title")
        title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
        texts = [" ".join("".join(node.itertext()).split()) for node in section.findall(".//p")]
        text = "\n\n".join(filter(None, texts))
        if title or text:
            sections.append({"title": title[:160], "text": text[:4000]})
        if len(sections) >= 20:
            break
    return {"text": content, "license": license_url, "license_text": license_text[:2000],
            "sections": sections, "xml": source}


def unpack(row):
    return {**json.loads(row["data"]), "collected_at": row["collected_at"], "has_fulltext": bool(row["has_fulltext"])}


class LiteratureStore:
    def __init__(self, workspace):
        self.workspace = workspace
        self.collecting = Lock()
        with self.workspace.connect(write=True) as conn:
            conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
            self.migrate_kinds(conn)

    @staticmethod
    def migrate_kinds(conn):
        columns = {row[1] for row in conn.execute("PRAGMA table_info(literature_cases)")}
        if "kind" in columns:
            return
        conn.execute("ALTER TABLE literature_cases ADD COLUMN kind TEXT NOT NULL DEFAULT 'article'")
        conn.execute(
            """UPDATE literature_cases SET kind='dataset' WHERE article_id IN (
                   SELECT article_id FROM literature_records WHERE provider='Zenodo')"""
        )

    def list(self, case_code, kind="article", offset=0, limit=None):
        provider, query = case_settings(case_code, kind)
        if type(offset) is not int or offset < 0:
            raise WorkspaceError(400, "分页起点不正确")
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 200):
            raise WorkspaceError(400, "每页数量需要为 1 至 200")
        base_sql = (
            """FROM literature_cases c JOIN literature_articles a ON a.id=c.article_id
               WHERE c.case_code=? AND c.kind=?"""
        )
        with self.workspace.connect() as conn:
            total = conn.execute("SELECT count(*) " + base_sql, (case_code, kind)).fetchone()[0]
            sql = ("SELECT a.data, a.collected_at, a.fulltext IS NOT NULL AS has_fulltext "
                   + base_sql + " ORDER BY a.collected_at DESC, a.rowid DESC")
            params = [case_code, kind]
            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend((limit, offset))
            articles = [unpack(row) for row in conn.execute(sql, params)]
        return {
            "articles": articles, "provider": provider, "default_query": query,
            "total": total, "offset": offset, "limit": limit,
            "has_more": offset + len(articles) < total,
        }

    def collect(self, payload):
        payload = ensure_object(payload)
        case_code = payload.get("case")
        kind = payload.get("kind", "article")
        provider, default_query = case_settings(case_code, kind)
        query = field_text(payload.get("query", ""), "检索词", 180) or default_query
        limit = payload.get("limit", 6)
        if type(limit) is not int or not 1 <= limit <= MAX_RECORDS:
            raise WorkspaceError(400, f"每次采集数量须为 1 至 {MAX_RECORDS}")
        if not self.collecting.acquire(blocking=False):
            raise WorkspaceError(409, "已有文献正在采集，请稍后重试")
        try:
            records = fetch_records(provider, query, limit)[:limit]
            articles = [(dataset_record(raw) if kind == "dataset" else article_record(provider, raw), raw)
                        for raw in records]
            added, usable = 0, set()
            with self.workspace.connect(write=True) as conn:
                for article, raw in articles:
                    if article is None or article["id"] in usable:
                        continue
                    article_id = article["id"]
                    usable.add(article_id)
                    previous = conn.execute("SELECT data FROM literature_articles WHERE id=?", (article_id,)).fetchone()
                    if previous and kind == "article":
                        old = json.loads(previous["data"])
                        if old["can_fetch"] and not article["can_fetch"]:
                            article = {**article, **{key: old[key] for key in ("can_fetch", "pmcid", "url", "provider")}}
                        article["abstract"] = article["abstract"] or old["abstract"]
                    conn.execute(
                        """INSERT INTO literature_articles (id, data) VALUES (?, ?)
                           ON CONFLICT(id) DO UPDATE SET data=excluded.data""",
                        (article_id, json.dumps(article, ensure_ascii=False)),
                    )
                    conn.execute(
                        """INSERT INTO literature_records (article_id, provider, data) VALUES (?, ?, ?)
                           ON CONFLICT(article_id, provider) DO UPDATE SET data=excluded.data""",
                        (article_id, provider, json.dumps(raw, ensure_ascii=False)),
                    )
                    result = conn.execute(
                        "INSERT OR IGNORE INTO literature_cases (case_code, article_id, kind) VALUES (?, ?, ?)",
                        (case_code, article_id, kind),
                    )
                    added += result.rowcount
                    if not result.rowcount:
                        conn.execute(
                            "UPDATE literature_cases SET kind=? WHERE case_code=? AND article_id=?",
                            (kind, case_code, article_id),
                        )
            return {"provider": provider, "query": query, "found": len(usable), "added": added}
        finally:
            self.collecting.release()

    def _store_article(self, conn, case_code, kind, provider, article, raw):
        article_id = article["id"]
        previous = conn.execute(
            "SELECT data FROM literature_articles WHERE id=?", (article_id,),
        ).fetchone()
        if previous and kind == "article":
            old = json.loads(previous["data"])
            if old.get("can_fetch") and not article["can_fetch"]:
                article = {**article, **{key: old[key] for key in
                                         ("can_fetch", "pmcid", "url", "provider")}}
            article["abstract"] = article["abstract"] or old.get("abstract", "")
        conn.execute(
            """INSERT INTO literature_articles (id, data) VALUES (?, ?)
               ON CONFLICT(id) DO UPDATE SET data=excluded.data""",
            (article_id, json.dumps(article, ensure_ascii=False)),
        )
        conn.execute(
            """INSERT INTO literature_records (article_id, provider, data) VALUES (?, ?, ?)
               ON CONFLICT(article_id, provider) DO UPDATE SET data=excluded.data""",
            (article_id, provider, json.dumps(raw, ensure_ascii=False)),
        )
        result = conn.execute(
            "INSERT OR IGNORE INTO literature_cases (case_code, article_id, kind) VALUES (?, ?, ?)",
            (case_code, article_id, kind),
        )
        added = result.rowcount
        if not added:
            conn.execute(
                "UPDATE literature_cases SET kind=? WHERE case_code=? AND article_id=?",
                (kind, case_code, article_id),
            )
        return added

    def expand(self, payload):
        payload = ensure_object(payload)
        case_code = payload.get("case")
        if case_code not in CASE_TOPICS:
            raise WorkspaceError(400, "请选择一个研究案例")
        limit = payload.get("limit_per_query", 4)
        if type(limit) is not int or not 1 <= limit <= 8:
            raise WorkspaceError(400, "每个检索词采集数量须为 1 至 8")
        if not self.collecting.acquire(blocking=False):
            raise WorkspaceError(409, "已有文献正在采集，请稍后重试")
        try:
            jobs = [(provider, query)
                    for query in CASE_TOPICS[case_code]
                    for provider in EXPAND_PROVIDERS[case_code]]
            results = [None] * len(jobs)
            errors = []
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {
                    pool.submit(fetch_records, provider, query, limit): index
                    for index, (provider, query) in enumerate(jobs)
                }
                for future in as_completed(futures):
                    index = futures[future]
                    provider, query = jobs[index]
                    try:
                        results[index] = (provider, query, future.result())
                    except WorkspaceError as error:
                        errors.append(f"{provider} / {query}：{error}")
            errors.sort()
            articles = []
            seen = set()
            provider_counts = {}
            for result in results:
                if result is None:
                    continue
                provider, _query, records = result
                provider_counts[provider] = provider_counts.get(provider, 0) + len(records)
                for raw in records[:limit]:
                    article = article_record(provider, raw)
                    if article and article["id"] not in seen:
                        seen.add(article["id"])
                        articles.append((provider, article, raw))
            added = 0
            with self.workspace.connect(write=True) as conn:
                for provider, article, raw in articles:
                    added += self._store_article(
                        conn, case_code, "article", provider, article, raw)
            return {
                "provider": "、".join(EXPAND_PROVIDERS[case_code]),
                "queries": list(CASE_TOPICS[case_code]),
                "found": len(articles),
                "added": added,
                "provider_counts": provider_counts,
                "errors": errors[:5],
            }
        finally:
            self.collecting.release()

    def article(self, article_id):
        with self.workspace.connect() as conn:
            row = conn.execute(
                "SELECT data, collected_at, fulltext IS NOT NULL AS has_fulltext, fulltext FROM literature_articles WHERE id=?",
                (article_id,),
            ).fetchone()
            imported = {file["file_id"] for file in conn.execute(
                "SELECT file_id FROM literature_data_files WHERE article_id=?", (article_id,),
            )}
        if row is None:
            raise WorkspaceError(404, "找不到这篇文献")
        article = unpack(row)
        if row["fulltext"]:
            fulltext = json.loads(row["fulltext"])
            article["fulltext"] = {key: fulltext.get(key, "") for key in
                                   ("text", "license", "license_text")}
            article["fulltext"]["sections"] = fulltext.get("sections", [])
        for file in article.get("files", []):
            file["imported"] = file["id"] in imported
        return article

    def import_file(self, article_id, file_id):
        dataset = self.article(article_id)
        file = next((item for item in dataset.get("files", []) if item["id"] == file_id), None)
        if file is None:
            raise WorkspaceError(404, "找不到这个数据文件")
        if file["imported"]:
            return dataset
        if not file["can_import"]:
            raise WorkspaceError(422, "这个文件可从数据集来源查看")
        if not self.collecting.acquire(blocking=False):
            raise WorkspaceError(409, "已有采集任务正在运行，请稍后重试")
        try:
            url = f"{ZENODO}/{dataset['source_id']}/files/{quote(file['name'], safe='')}/content"
            data = download(url, file["size"], missing="来源暂未提供这个原始文件")
            checksum = "md5:" + md5(data, usedforsecurity=False).hexdigest()
            if len(data) != file["size"] or checksum != file["checksum"]:
                raise WorkspaceError(502, "文件大小或校验值与来源记录不一致")
            with self.workspace.connect(write=True) as conn:
                conn.execute("INSERT OR IGNORE INTO literature_data_files VALUES (?, ?, ?)", (article_id, file_id, data))
            return self.article(article_id)
        finally:
            self.collecting.release()

    def load_file(self, article_id, file_id):
        dataset = self.article(article_id)
        file = next((item for item in dataset.get("files", []) if item["id"] == file_id), None)
        if not file or not file["imported"]:
            raise WorkspaceError(404, "这个文件尚未入库")
        with self.workspace.connect() as conn:
            row = conn.execute("SELECT content FROM literature_data_files WHERE article_id=? AND file_id=?",
                               (article_id, file_id)).fetchone()
        return file["name"], row["content"]

    def fetch_fulltext(self, article_id):
        article = self.article(article_id)
        if article["has_fulltext"]:
            return article
        if not article["can_fetch"] or not PMCID.fullmatch(article["pmcid"]):
            raise WorkspaceError(422, "这篇文献需要从论文来源查看正文")
        if not self.collecting.acquire(blocking=False):
            raise WorkspaceError(409, "已有文献正在采集，请稍后重试")
        try:
            data = download(f'{EUROPE_PMC}{article["pmcid"]}/fullTextXML', MAX_ARTICLE,
                            missing="来源暂未提供该篇文章的开放全文")
            fulltext = parse_fulltext(data)
            with self.workspace.connect(write=True) as conn:
                conn.execute("UPDATE literature_articles SET fulltext=? WHERE id=?",
                             (json.dumps(fulltext, ensure_ascii=False), article_id))
            return self.article(article_id)
        finally:
            self.collecting.release()

    def export(self, case_code, kind="article"):
        case_settings(case_code, kind)
        with self.workspace.connect() as conn:
            rows = conn.execute(
                """SELECT a.id, a.data, a.collected_at, a.fulltext, r.provider, r.data AS raw
                   FROM literature_cases c JOIN literature_articles a ON a.id=c.article_id
                   JOIN literature_records r ON r.article_id=a.id
                   WHERE c.case_code=? AND c.kind=? ORDER BY a.id, r.provider""",
                (case_code, kind),
            )
            records = {}
            for row in rows:
                if row["id"] not in records:
                    records[row["id"]] = {
                        "article": json.loads(row["data"]), "collected_at": row["collected_at"],
                        "fulltext": json.loads(row["fulltext"]) if row["fulltext"] else None, "raw": {},
                    }
                records[row["id"]]["raw"][row["provider"]] = json.loads(row["raw"])
        return {"case": case_code, "records": list(records.values())}

    @staticmethod
    def _stem(token):
        return token[:-1] if len(token) > 4 and token.endswith("s") else token

    @classmethod
    def _match_count(cls, terms, text):
        tokens = {
            token for token in search_terms(text)
            if re.fullmatch(r"[a-z0-9]{3,}", token) and token not in STOPWORDS
        }
        return len(terms & {cls._stem(token) for token in tokens})

    def related(self, case_code, question):
        aliases = " ".join(term for label, term in FIELD_ALIASES.items() if label in question)
        terms = {
            token for token in search_terms(f"{question} {aliases}")
            if re.fullmatch(r"[a-z0-9]{3,}", token) and token not in STOPWORDS
        }
        terms = {self._stem(token) for token in terms}
        if not terms or case_code not in CASES:
            return []
        scored = []
        for article in self.list(case_code)["articles"]:
            score = 3 * self._match_count(terms, article.get("title", "")) \
                + self._match_count(terms, article.get("abstract", "")) \
                + 2 * self._match_count(terms, " ".join(article.get("topics") or []))
            if score:
                scored.append((score, article))
        ranked = sorted(scored, key=lambda record: record[0], reverse=True)[:10]
        return [{
            "id": article.get("id", ""), "title": article.get("title", ""),
            "url": article.get("url", ""), "doi": article.get("doi", ""),
            "provider": article.get("provider", ""), "year": article.get("year", ""),
            "citation_count": article.get("citation_count", 0),
            "open_access": bool(article.get("open_access")),
            "venue": article.get("venue") or article.get("journal", ""),
        } for _, article in ranked]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "workspace.sqlite3")
    parser.add_argument("--case", required=True, choices=CASES)
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", default=6, type=int)
    parser.add_argument("--kind", default="article", choices=("article", "dataset"))
    args = parser.parse_args()
    try:
        store = LiteratureStore(WorkspaceStore(args.workspace.resolve()))
        result = store.collect({"case": args.case, "kind": args.kind, "query": args.query, "limit": args.limit})
        print(json.dumps(result, ensure_ascii=False))
    except WorkspaceError as error:
        parser.exit(1, str(error) + "\n")
