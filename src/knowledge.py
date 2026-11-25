"""Case presets, concept mappings, and evidence for the local prototype."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from search import COMMON_TERMS, SYNONYMS, search, search_terms


CONFIG_PATH = Path(__file__).resolve().with_name("knowledge_config.json")


@dataclass(frozen=True)
class Mapping:
    keywords: tuple[str, ...]
    source: str
    target: str
    relation: str
    explanation: str
    entry_ids: tuple[str, ...]


@dataclass(frozen=True)
class CoverageTask:
    key: str
    label: str
    keywords: tuple[str, ...]
    target: int


def _config_text(value, label, *, optional=False):
    if value is None and optional:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{CONFIG_PATH.name}：{label} 需要非空文本")
    return value.strip()


def _config_list(value, label):
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise RuntimeError(f"{CONFIG_PATH.name}：{label} 需要非空字符串列表")
    return tuple(item.strip() for item in value)


def load_config(path=CONFIG_PATH):
    """Load case presets and concept mappings from the editable JSON file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(f"无法读取 {path}：{error}") from error
    except ValueError as error:
        raise RuntimeError(f"{path} 不是有效的 JSON：{error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), dict) \
            or not isinstance(raw.get("mappings"), dict):
        raise RuntimeError(f"{path} 需要包含 cases 和 mappings 两个对象")

    cases = {}
    for code, item in raw["cases"].items():
        if not isinstance(code, str) or not code.strip() or not isinstance(item, dict):
            raise RuntimeError(f"{path}：案例 {code!r} 格式不正确")
        entry = {
            "label": _config_text(item.get("label"), f"{code}.label"),
            "discipline": _config_text(item.get("discipline"), f"{code}.discipline", optional=True),
        }
        for mode in ("method", "concept"):
            if mode in item:
                entry[mode] = _config_text(item[mode], f"{code}.{mode}")
        cases[code] = entry

    paper_links = raw.get("paper_links", {})
    if not isinstance(paper_links, dict) or not all(
        isinstance(title, str) and title.strip() and isinstance(arxiv_id, str) and arxiv_id.strip()
        for title, arxiv_id in paper_links.items()
    ):
        raise RuntimeError(f"{path}：paper_links 需要标题到 arXiv 编号的映射")

    mappings = {}
    for code, items in raw["mappings"].items():
        if not isinstance(items, list):
            raise RuntimeError(f"{path}：{code} 的 mappings 需要列表")
        parsed = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise RuntimeError(f"{path}：{code}[{index}] 格式不正确")
            parsed.append(Mapping(
                _config_list(item.get("keywords"), f"{code}[{index}].keywords"),
                _config_text(item.get("source"), f"{code}[{index}].source"),
                _config_text(item.get("target"), f"{code}[{index}].target"),
                _config_text(item.get("relation"), f"{code}[{index}].relation"),
                _config_text(item.get("explanation"), f"{code}[{index}].explanation"),
                _config_list(item.get("entry_ids"), f"{code}[{index}].entry_ids"),
            ))
        mappings[code] = tuple(parsed)

    coverage_raw = raw.get("coverage", {})
    if not isinstance(coverage_raw, dict):
        raise RuntimeError(f"{path}：coverage 需要按案例组织的对象")
    coverage = {}
    for code, items in coverage_raw.items():
        if code not in cases:
            raise RuntimeError(f"{path}：coverage 中的案例 {code!r} 不在 cases 中")
        if not isinstance(items, list) or not items:
            raise RuntimeError(f"{path}：{code} 的 coverage 需要非空列表")
        parsed = []
        keys = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise RuntimeError(f"{path}：{code}.coverage[{index}] 格式不正确")
            key = _config_text(item.get("key"), f"{code}.coverage[{index}].key")
            if key in keys:
                raise RuntimeError(f"{path}：{code}.coverage 的 key {key!r} 重复")
            keys.add(key)
            target = item.get("target", 1)
            if type(target) is not int or not 1 <= target <= 20:
                raise RuntimeError(f"{path}：{code}.coverage[{index}].target 需要 1 至 20 的整数")
            parsed.append(CoverageTask(
                key,
                _config_text(item.get("label"), f"{code}.coverage[{index}].label"),
                _config_list(item.get("keywords"), f"{code}.coverage[{index}].keywords"),
                target,
            ))
        coverage[code] = tuple(parsed)
    for code in cases:
        if code not in coverage:
            raise RuntimeError(f"{path}：coverage 缺少案例 {code!r} 的任务清单")
    return cases, mappings, paper_links, coverage


CASE_PRESETS, MAPPINGS, PAPER_LINKS, COVERAGE = load_config()


def mapping_matches(mapping, folded):
    """Return keywords present in the folded question; ASCII keywords match whole words."""
    return {
        keyword for keyword in mapping.keywords
        if (re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", folded)
            if keyword.isascii() else keyword.casefold() in folded)
    }


SOURCE_URL = re.compile(r"https?://[^\s<>，。；、）】」』？！“”‘’《》]+")
METHOD_FIELDS = ("entry_id", "concept", "method", "scenario", "rationale", "conditions", "limitations")


def case_catalog(entries):
    cases = {}
    for entry in entries:
        code = entry["case_code"]
        if code not in cases:
            preset = CASE_PRESETS.get(code, {})
            cases[code] = {
                "code": code,
                "label": preset.get("label", entry["case_name"]),
                "discipline": preset.get("discipline", ""),
                "examples": {mode: preset[mode] for mode in ("method", "concept") if mode in preset},
                "count": 0,
            }
        cases[code]["count"] += 1
    order = list(CASE_PRESETS)
    return sorted(cases.values(), key=lambda case: (
        order.index(case["code"]) if case["code"] in order else len(order),
        case["code"],
    ))


COVERAGE_FIELDS = ("scenario", "concept", "method", "rationale", "conditions", "limitations")


def coverage_keyword_matches(keyword, text):
    keyword = keyword.casefold().strip()
    if not keyword:
        return False
    if keyword.isascii():
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text))
    return keyword in text


def coverage_value(entry, field):
    try:
        value = entry[field]
    except (KeyError, IndexError):
        value = ""
    return str(value or "")


def coverage_report(entries, case_code=None):
    """Count knowledge entries per research task and expose under-covered tasks."""
    grouped = {}
    for entry in entries:
        grouped.setdefault(entry["case_code"], []).append(entry)
    reports = []
    for code, preset in CASE_PRESETS.items():
        if case_code and code != case_code:
            continue
        tasks_config = COVERAGE.get(code, ())
        if not tasks_config:
            continue
        case_entries = grouped.get(code, [])
        texts = {
            entry["entry_id"]: " ".join(
                coverage_value(entry, field) for field in COVERAGE_FIELDS).casefold()
            for entry in case_entries
        }
        tasks = []
        for task in tasks_config:
            matched = sorted(
                entry["entry_id"] for entry in case_entries
                if any(coverage_keyword_matches(keyword, texts[entry["entry_id"]])
                       for keyword in task.keywords)
            )
            count = len(matched)
            gap = max(0, task.target - count)
            tasks.append({
                "key": task.key, "label": task.label, "count": count,
                "target": task.target, "gap": gap,
                "status": "gap" if count == 0 else ("thin" if gap else "covered"),
                "entry_ids": matched,
            })
        target_total = sum(task["target"] for task in tasks)
        covered_units = sum(min(task["count"], task["target"]) for task in tasks)
        reports.append({
            "code": code, "label": preset["label"],
            "discipline": preset.get("discipline", ""),
            "entries": len(case_entries), "tasks": tasks,
            "gaps": [task for task in tasks if task["gap"]],
            "covered": sum(1 for task in tasks if task["status"] == "covered"),
            "total": len(tasks),
            "coverage": round(covered_units / target_total, 3) if target_total else 0,
        })
    all_tasks = [task for report in reports for task in report["tasks"]]
    target_total = sum(task["target"] for task in all_tasks)
    return {
        "cases": reports,
        "totals": {
            "cases": len(reports),
            "entries": sum(report["entries"] for report in reports),
            "tasks": len(all_tasks),
            "gaps": sum(len(report["gaps"]) for report in reports),
            "coverage": round(
                sum(min(task["count"], task["target"]) for task in all_tasks)
                / target_total, 3) if target_total else 0,
        },
    }


def align_concepts(question, entries, case_code):
    by_id = {entry["entry_id"]: entry for entry in entries}
    folded = question.casefold()
    scored = []
    evidence = {}
    for order, mapping in enumerate(MAPPINGS.get(case_code, ())):
        if not all(entry_id in by_id for entry_id in mapping.entry_ids):
            continue
        cited = any(f"[{entry_id}]" in question for entry_id in mapping.entry_ids)
        matches = mapping_matches(mapping, folded)
        if not cited and not matches:
            continue
        # Rank the strongest keyword matches first so the lead card is the best fit.
        scored.append((-(len(matches) + (1 if cited else 0)), order, mapping))
        evidence.update((entry_id, by_id[entry_id]) for entry_id in mapping.entry_ids)
    scored.sort(key=lambda item: (item[0], item[1]))
    mappings = [{
        "source": mapping.source,
        "target": mapping.target,
        "relation": mapping.relation,
        "explanation": mapping.explanation,
        "entry_ids": mapping.entry_ids,
    } for _, _, mapping in scored]
    return mappings, list(evidence.values())


def recommend(question, entries, limit=3):
    matches = search(question, entries, limit=limit)
    return [{field: entry[field] for field in METHOD_FIELDS} for entry in matches], matches


ROUTING_COMMON = COMMON_TERMS | set(
    "任务 计算 统计 学习 内容 答案 区别 关系 对应 告诉 举例 介绍 推荐 例子 写作 方式 使用 选择 适合 方案 训练 实验 "
    "流程 步骤 思路 教程 定义 原理 工具 准确 精度 风险 评估 处理 帮我 比较 说明 分析 时间 变化 输出 适用 "
    "想知 知道 一下 这个 那个 有哪 哪些 可用 基础 一般 什么 默认 the and how what for can with".split()
)
CONCEPT_INTENT = re.compile(r"对应|是什么|什么意思|有何区别|有什么区别|同一个|概念|区别|\bwhat is\b|\bdifference\b", re.I)
FOLLOW_UP = re.compile(
    r"^(?:那|它|这个|这种|上面|上述|其中|刚才|前面|这些|该方法|该模型|继续|再(?:说|讲|解释|分析|比较|简化|补充)|"
    r"换成|改成|用表格|总结一下|what about|how about|could you elaborate|make it|summari[sz]e)"
    r"|(?:前一条|上一个|上一版|第[一二三123]种|第[一二三123]个|前者|后者|用表格|整理成表格)", re.I,
)
TOPIC_RESET = re.compile(r"^(?:换个话题|另外一个问题|说点别的|新问题|new topic)\s*[：:,，。]?", re.I)
ORDINAL = re.compile(r"第([一二三123])(?:种|个|项)")


def follow_up_scope(question, entries, recent):
    if not recent or TOPIC_RESET.search(question) or not FOLLOW_UP.search(question):
        return None
    previous = recent[-1]
    response = previous.get("response") or {}
    case = response.get("retrieval_case") or previous.get("caseCode")
    results = response.get("results") or []
    if not results or not any(entry["case_code"] == case for entry in entries):
        return None
    ordinal = ORDINAL.search(question)
    if ordinal and response.get("source") == "local":
        index = "一二三".find(ordinal.group(1)) if not ordinal.group(1).isdigit() else int(ordinal.group(1)) - 1
        if 0 <= index < len(results):
            item = results[index]
            target = item.get("entry_id") or " ".join(item.get("entry_ids", []))
            if target:
                query = " ".join(f"[{entry_id}]" for entry_id in target.split())
                return case, response["mode"], query + "\n" + question
    anchors = [item.get("method") or item.get("source") for item in results]
    return case, response["mode"], "\n".join((previous.get("question", ""), " ".join(filter(None, anchors)), question))


def automatic_scope(question, entries, preferred, recent):
    inherited = follow_up_scope(question, entries, recent)
    folded = question.casefold()
    terms = search_terms(question) - ROUTING_COMMON
    for concept, aliases in SYNONYMS.items():
        if any(alias.casefold() in folded for alias in aliases):
            terms |= search_terms(concept) - ROUTING_COMMON
    scores = {}
    for entry in entries:
        exact = terms & (search_terms(entry["method"]) | search_terms(entry["concept"]))
        related = terms & search_terms(entry["scenario"])
        score = 3 * len(exact) + len(related - exact)
        if score >= 4 or any(term.isascii() and len(term) >= 3 for term in exact):
            code = entry["case_code"]
            scores[code] = max(score, scores.get(code, 0))
    for code in {entry["case_code"] for entry in entries}:
        for mapping in MAPPINGS.get(code, ()):
            matches = mapping_matches(mapping, folded)
            if matches:
                scores[code] = max(4 + 2 * len(matches), scores.get(code, 0))
    if scores:
        case = max(scores, key=lambda code: (scores[code], code == (inherited[0] if inherited else preferred)))
        if inherited and (case == inherited[0] or scores[case] < 6):
            return inherited
        return case, "concept" if CONCEPT_INTENT.search(question) else "method", question
    return inherited


def reference(entry):
    evidence = entry["evidence"].strip()
    links = []
    for match in SOURCE_URL.finditer(evidence):
        url = match[0].rstrip("。，；、）】。")
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.hostname and not parsed.username and url not in links:
            links.append(url)
    return {"entry_id": entry["entry_id"], "text": evidence, "links": links}
