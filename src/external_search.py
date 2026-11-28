"""Search public literature APIs when the local knowledge base has no sufficient answer."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from urllib.error import HTTPError, URLError

from literature import WorkspaceError, article_record, fetch_records
from model_providers import ModelError, generate
from search import search_terms


QUERY_PROMPT = (
    "你是科研文献检索助手。先判断用户输入是不是值得检索公开文献的专业问题。"
    "只排除问候、感谢、寒暄、纯数字、乱码、天气等日常闲聊。"
    "询问计算机、算法、统计、医学、金融、工程等专业概念、术语或方法时，"
    "即使只是“是什么”“有什么用”，也必须标记 research 为 true 并生成检索查询。"
    "只有当 research 为 true 时，才把问题转换成 1 至 3 个简洁的英文文献检索查询，"
    "保留研究对象、任务、方法和领域关键词。只输出 JSON："
    '{"research":true,"queries":["query one","query two"]}。'
    "如果不需要检索，输出 {\"research\":false,\"queries\":[]}。不要解释，不要输出代码块。"
)
TECHNICAL_HINT = re.compile(
    r"算法|模型|方法|统计|医学|影像|分割|金融|风险|计算机|数据|网络|预测|分类|回归|"
    r"优化|复杂度|编程|深度学习|机器学习|\b(?:bfs|dfs|prim|kruskal|dijkstra|"
    r"transformer|python|sql)\b",
    re.I,
)
PROVIDERS = ("OpenAlex", "Crossref", "arXiv")
PER_PROVIDER = 4
MAX_RESULTS = 6


def parse_plan(text, fallback):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if 0 <= start < end else {}
    except (ValueError, RecursionError):
        data = {}
    if isinstance(data, dict) and data.get("research") is False:
        return {"research": False, "queries": []}
    queries = []
    if isinstance(data, dict) and isinstance(data.get("queries"), list):
        for item in data["queries"]:
            if isinstance(item, str) and item.strip():
                queries.append(item.strip()[:180])
    return {
        "research": True,
        "queries": queries[:3] or [fallback[:180]],
    }


def parse_queries(text, fallback):
    return parse_plan(text, fallback)["queries"]


def looks_like_research(question):
    text = question.strip()
    if len(text) < 2:
        return False
    return bool(re.search(r"[a-z㐀-鿿]", text, re.I))


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
    if not profile or not looks_like_research(question):
        return {"research": False, "queries": [], "sources": [], "errors": []}
    fallback = question.strip()[:180]
    try:
        raw_queries, _ = generate(profile, QUERY_PROMPT, question)
        plan = parse_plan(raw_queries, fallback)
    except ModelError:
        plan = {"research": True, "queries": [fallback]}
    if not plan["research"]:
        if not TECHNICAL_HINT.search(question):
            return {"research": False, "queries": [], "sources": [], "errors": []}
        plan = {"research": True, "queries": [fallback]}
    queries = plan["queries"]
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
        (
            (provider, article)
            for provider, article in deduped.values()
            if score_article(article, terms) > 0
        ),
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
    return {"research": True, "queries": queries, "sources": sources, "errors": errors[:5]}
