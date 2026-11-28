"""Search public literature APIs when the local knowledge base has no sufficient answer."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from urllib.error import HTTPError, URLError

from literature import WorkspaceError, article_record, fetch_records
from model_providers import ModelError, generate
from search import search_terms


QUERY_PROMPT = (
    "你是科研文献检索助手。把用户问题转换成 1 至 3 个简洁的英文文献检索查询，"
    "保留研究对象、任务、方法和领域关键词。只输出 JSON："
    '{"queries":["query one","query two"]}。不要解释，不要输出代码块。'
)
PROVIDERS = ("OpenAlex", "Crossref", "arXiv")
PER_PROVIDER = 4
MAX_RESULTS = 6


def parse_queries(text, fallback):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if 0 <= start < end else {}
    except (ValueError, RecursionError):
        data = {}
    queries = []
    if isinstance(data, dict) and isinstance(data.get("queries"), list):
        for item in data["queries"]:
            if isinstance(item, str) and item.strip():
                queries.append(item.strip()[:180])
    return queries[:3] or [fallback[:180]]


def query_terms(question, queries):
    terms = set()
    for text in [question] + queries:
        terms.update(
            term for term in search_terms(text)
            if len(term) >= 2 and re.fullmatch(r"[a-z0-9㐀-鿿-]+", term)
        )
    return terms


def score_article(article, terms):
    text = " ".join([
        article.get("title", ""), article.get("abstract", ""),
        " ".join(article.get("topics") or []),
    ]).casefold()
    return sum(1 for term in terms if term in text)


def search_external_literature(question, profile):
    """Return unverified public literature metadata, never local evidence."""
    if not profile:
        return {"queries": [], "sources": [], "errors": []}
    fallback = question.strip()[:180]
    try:
        raw_queries, _ = generate(profile, QUERY_PROMPT, question)
        queries = parse_queries(raw_queries, fallback)
    except ModelError:
        queries = [fallback]
    terms = query_terms(question, queries)
    jobs = [(provider, query) for query in queries[:2] for provider in PROVIDERS]
    collected = []
    errors = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(fetch_records, provider, query, PER_PROVIDER): (provider, query)
            for provider, query in jobs
        }
        for future in as_completed(futures):
            provider, query = futures[future]
            try:
                records = future.result()
            except (WorkspaceError, HTTPError, URLError, OSError) as error:
                errors.append(f"{provider} / {query}：{error}"[:300])
                continue
            for raw in records[:PER_PROVIDER]:
                article = article_record(provider, raw)
                if article:
                    collected.append((provider, article))
    deduped = {}
    for provider, article in collected:
        key = article.get("doi") or article.get("id")
        if key and key not in deduped:
            deduped[key] = (provider, article)
    ranked = sorted(
        deduped.values(),
        key=lambda item: (
            -score_article(item[1], terms),
            item[1].get("citation_count", 0),
            item[1].get("title", ""),
        ),
    )
    sources = []
    for index, (provider, article) in enumerate(ranked[:MAX_RESULTS], 1):
        source = {
            "id": f"EXT-{index}",
            "title": article.get("title", ""),
            "authors": article.get("authors", ""),
            "year": article.get("year", ""),
            "venue": article.get("venue") or article.get("journal", ""),
            "doi": article.get("doi", ""),
            "url": article.get("url", ""),
            "provider": provider,
            "abstract": (article.get("abstract") or "")[:1200],
        }
        if source["title"] and source["url"]:
            sources.append(source)
    return {"queries": queries, "sources": sources, "errors": errors[:5]}
