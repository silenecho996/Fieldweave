"""Whitelisted crawler for public method documentation pages."""

import argparse
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from workspace_store import WorkspaceError


CONFIG_PATH = Path(__file__).resolve().with_name("method_docs_config.json")
SKIP_TAGS = {
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "svg", "canvas", "iframe",
}
BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "li", "dt", "dd",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "tr", "br",
}
MAX_TEXT = 50_000
CASE_CODES = {"MED", "EPI", "FIN"}


def load_config(path=CONFIG_PATH):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(f"无法读取 {path}：{error}") from error
    except ValueError as error:
        raise RuntimeError(f"{path} 不是有效的 JSON：{error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("sources"), dict):
        raise RuntimeError(f"{path} 需要包含 sources 对象")
    user_agent = raw.get("user_agent")
    if not isinstance(user_agent, str) or not user_agent.strip():
        raise RuntimeError(f"{path}：user_agent 需要非空文本")
    max_bytes = raw.get("max_bytes", 2_000_000)
    if type(max_bytes) is not int or not 10_000 <= max_bytes <= 10_000_000:
        raise RuntimeError(f"{path}：max_bytes 需要在 10000 至 10000000 之间")
    delay = raw.get("delay_seconds", 0.6)
    if not isinstance(delay, (int, float)) or isinstance(delay, bool) or not 0 <= delay <= 10:
        raise RuntimeError(f"{path}：delay_seconds 需要在 0 至 10 之间")
    sources = {}
    for key, item in raw["sources"].items():
        if not isinstance(key, str) or not key or not isinstance(item, dict):
            raise RuntimeError(f"{path}：来源 {key!r} 格式不正确")
        label = item.get("label")
        domain = item.get("domain")
        seed = item.get("seed")
        prefix = item.get("path_prefix")
        pages = item.get("max_pages", 4)
        default_case = item.get("default_case")
        if not all(isinstance(value, str) and value.strip()
                   for value in (label, domain, seed, prefix)):
            raise RuntimeError(f"{path}：来源 {key} 的 label/domain/seed/path_prefix 不能为空")
        if default_case not in CASE_CODES:
            raise RuntimeError(f"{path}：来源 {key} 的 default_case 需要是 MED、EPI 或 FIN")
        seed_parts = urlsplit(seed)
        if seed_parts.scheme != "https" or seed_parts.hostname != domain:
            raise RuntimeError(f"{path}：来源 {key} 的 seed 必须使用对应 HTTPS 域名")
        if not prefix.startswith("/"):
            raise RuntimeError(f"{path}：来源 {key} 的 path_prefix 需要以 / 开头")
        if type(pages) is not int or not 1 <= pages <= 30:
            raise RuntimeError(f"{path}：来源 {key} 的 max_pages 需要 1 至 30")
        sources[key] = {
            "label": label.strip(), "domain": domain.strip(),
            "seed": seed.strip(), "path_prefix": prefix,
            "max_pages": pages, "default_case": default_case,
        }
    return {"user_agent": user_agent.strip(), "max_bytes": max_bytes,
            "delay_seconds": float(delay), "sources": sources}


CONFIG = load_config()
SOURCES = CONFIG["sources"]


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.main_parts = []
        self.title_parts = []
        self.links = []
        self._skip_depth = 0
        self._main_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "main":
            self._main_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
            if self._main_depth:
                self.main_parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
            if self._main_depth:
                self.main_parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag == "main" and self._main_depth:
            self._main_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
            if self._main_depth:
                self.main_parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.parts.append(data)
        if self._main_depth:
            self.main_parts.append(data)


def clean_text(parts):
    return " ".join("".join(parts).split())


def normalize_url(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return ""
    path = parts.path or "/"
    return urlunsplit(("https", parts.netloc.lower(), path, "", ""))


def allowed_url(url, source):
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.hostname == source["domain"]
        and parts.path.startswith(source["path_prefix"])
        and not parts.username
        and not parts.password
    )


def robots_decision(url, user_agent):
    parts = urlsplit(url)
    robots_url = urlunsplit(("https", parts.netloc, "/robots.txt", "", ""))
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except (OSError, HTTPError, URLError):
        return False, "无法读取 robots.txt"
    if not parser.can_fetch(user_agent, url):
        return False, "robots.txt 禁止采集"
    return True, ""


def fetch_html(url, *, max_bytes, user_agent):
    request = Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise WorkspaceError(422, "来源不是 HTML 文档")
            charset = response.headers.get_content_charset() or "utf-8"
            data = response.read(max_bytes + 1)
    except HTTPError as error:
        error.close()
        raise WorkspaceError(502, f"来源返回 HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise WorkspaceError(502, "暂时无法连接方法文档来源") from error
    if len(data) > max_bytes:
        raise WorkspaceError(502, "方法文档页面超过单次处理上限")
    return data.decode(charset, errors="replace")


def document_id(url):
    return sha256(url.encode("utf-8")).hexdigest()[:32]


def source_list():
    return [{
        "key": key, "label": source["label"], "domain": source["domain"],
        "seed": source["seed"], "max_pages": source["max_pages"],
        "default_case": source["default_case"],
    } for key, source in SOURCES.items()]


def crawl_source(source_key, *, fetcher=None, robots=None, sleeper=None, max_pages=None):
    if source_key not in SOURCES:
        raise WorkspaceError(400, "请选择已配置的方法文档来源")
    source = SOURCES[source_key]
    limit = source["max_pages"] if max_pages is None else max_pages
    if type(limit) is not int or not 1 <= limit <= 20:
        raise WorkspaceError(400, "采集页数需要为 1 至 20")
    fetcher = fetcher or (lambda url: fetch_html(
        url, max_bytes=CONFIG["max_bytes"], user_agent=CONFIG["user_agent"]))
    robots = robots or (lambda url: robots_decision(url, CONFIG["user_agent"]))
    sleeper = sleeper or time.sleep
    seed = normalize_url(source["seed"])
    if not allowed_url(seed, source):
        raise WorkspaceError(400, "方法文档种子地址不在允许范围内")
    queue = [seed]
    seen = set()
    documents = []
    errors = []
    while queue and len(documents) < limit:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not allowed_url(url, source):
            continue
        allowed, reason = robots(url)
        if not allowed:
            errors.append(f"{url}：{reason}")
            continue
        try:
            html = fetcher(url)
        except WorkspaceError as error:
            errors.append(f"{url}：{error}")
            continue
        parser = DocumentParser()
        try:
            parser.feed(html)
            parser.close()
        except (ValueError, AssertionError):
            errors.append(f"{url}：HTML 无法解析")
            continue
        main_text = clean_text(parser.main_parts)
        text = main_text if len(main_text) >= 200 else clean_text(parser.parts)
        if len(text) < 200:
            errors.append(f"{url}：正文过短，已跳过")
            continue
        title = clean_text(parser.title_parts) or url
        documents.append({
            "id": document_id(url), "source": source_key,
            "source_label": source["label"], "url": url,
            "title": title[:500], "text": text[:MAX_TEXT],
        })
        for href in parser.links:
            linked = normalize_url(urljoin(url, href))
            if linked and allowed_url(linked, source) and linked not in seen:
                if len(queue) < 80:
                    queue.append(linked)
        if queue and len(documents) < limit:
            sleeper(CONFIG["delay_seconds"])
    return {
        "source": source_key, "label": source["label"],
        "found": len(documents), "documents": documents, "errors": errors[:8],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=sorted(SOURCES))
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()
    result = crawl_source(args.source, max_pages=args.max_pages)
    for document in result["documents"]:
        document["text"] = document["text"][:300] + "…"
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
