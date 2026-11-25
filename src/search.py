"""从跨学科科研知识库中检索最多三条相关记录。"""

import argparse
from collections import Counter
from contextlib import closing
from math import log
from pathlib import Path
import re
import sqlite3
import unicodedata


DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "knowledge-base.sqlite3"
TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+(?:[-_][a-z0-9]+)*\+*")
COMMON_TERMS = {
    "什么", "怎么", "如何", "方法", "模型", "数据", "问题", "研究", "可以", "需要", "进行",
    "影响", "因素", "结果", "解释",
}
SYNONYMS = {
    "分割": ("勾出", "勾画", "画出", "描出", "掩膜", "像素轮廓", "标出边界", "segmentation", "segment"),
    "目标检测": ("定位", "边界框", "框出", "detection", "bounding box"),
    "图像分类": ("分类", "良恶性", "类型识别", "分级", "classification"),
    "再生数": ("传播强度", "传给几个人", "传给多少人", "传染给几个人", "传染给多少人", "传染几个人",
             "reproduction number", "reproduction", "rt"),
    "时间序列预测": ("病例数预测", "发病趋势", "forecast", "forecasting", "arima", "time series"),
    "干预评估": ("干预", "政策", "停课", "口罩", "措施效果", "intervention"),
    "时空聚集": ("空间聚集", "热点区域", "高风险区域", "cluster", "spatial cluster"),
    "违约概率": ("还不上", "不还款", "无法还款", "不能按时还款", "还款风险",
             "default probability", "credit risk"),
    "病例报告延迟": ("迟报", "补报", "reporting delay", "nowcasting"),
    "异常检测": ("反常交易", "可疑交易", "anomaly", "fraud"),
    "风险传染": ("关联网络", "机构关系", "交易网络", "contagion"),
    "压力测试": ("极端情景", "情景分析", "stress test"),
}
SEARCH_FIELDS = {
    "rationale": 1,
    "scenario": 3,
    "concept": 4,
    "method": 4,
    "entry_id": 6,
}


def search_terms(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    terms = set()
    for token in TOKEN_PATTERN.findall(normalized):
        if token.isascii():
            if not token.isdecimal():
                terms.add(token)
        elif len(token) == 1:
            terms.add(token)
        else:
            terms.update(token[i:i + 2] for i in range(len(token) - 1))
    return terms - COMMON_TERMS


BM25_K1 = 1.2
BM25_B = 0.55


def search(question, entries, limit=3):
    terms = search_terms(question)
    folded = unicodedata.normalize("NFKC", question).casefold()
    expanded_terms = {
        term
        for concept, aliases in SYNONYMS.items()
        if any(alias.casefold() in folded for alias in aliases)
        for term in search_terms(concept)
    }
    terms.update(expanded_terms)

    # Weighted term frequencies let a field that contains a term several times
    # contribute more, while the field weights still keep method/concept ahead.
    documents = []
    for entry in entries:
        weighted = Counter()
        for field, weight in SEARCH_FIELDS.items():
            for term in search_terms(entry[field]):
                weighted[term] += weight
        documents.append(weighted)

    frequency = Counter(term for document in documents for term in document)
    relevance = {
        term: log(1 + (len(documents) - frequency[term] + 0.5)
                  / (frequency[term] + 0.5))
        * (1.4 if term in expanded_terms else 1)
        for term in terms
    }
    lengths = [sum(document.values()) for document in documents]
    average = sum(lengths) / len(lengths) if lengths else 1

    ranked = []
    for entry, document, length in zip(entries, documents, lengths):
        matched = terms & document.keys()
        if not matched:
            continue
        norm = 1 - BM25_B + BM25_B * length / average
        score = sum(
            relevance[term] * document[term] * (BM25_K1 + 1)
            / (document[term] + BM25_K1 * norm)
            for term in matched
        )
        focus = matched & (search_terms(entry["method"]) | search_terms(entry["concept"]))
        if len(focus) > 1:
            score += 0.7 * (len(focus) - 1)
        method = unicodedata.normalize("NFKC", entry["method"]).casefold().strip()
        if len(method) >= 3 and method in folded:
            score += 4
        ranked.append((score, entry))
    ranked.sort(key=lambda result: (-result[0], result[1]["entry_id"]))
    if not ranked:
        return []
    cutoff = ranked[0][0] * 0.35
    # Keep method diversity: a second record with the same method only appears
    # when there are not enough distinct methods above the relevance cutoff.
    chosen = []
    seen_methods = set()
    for score, entry in ranked:
        if score < cutoff:
            break
        method = re.sub(r"[\s\-_/]+", "", entry["method"]).casefold()
        if method and method in seen_methods:
            continue
        chosen.append(entry)
        if method:
            seen_methods.add(method)
        if len(chosen) >= limit:
            break
    return chosen


def print_entry(entry, rank):
    print(f"\n{rank}. [{entry['entry_id']}] {entry['method']}  （{entry['case_name']}）")
    print(f"   研究场景  {entry['scenario']}")
    print(f"   关联概念  {entry['concept']}")
    print(f"   推荐依据  {entry['rationale']}")
    print(f"   适用条件  {entry['conditions']}")
    print(f"   局限与注意事项  {entry['limitations']}")
    print(f"   参考文献与证据\n{entry['evidence']}")
    print(f"   源表与原始行\n{entry['source_row']}")


def load_entries(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("""
            SELECT e.*, c.name AS case_name
            FROM knowledge_entries AS e
            JOIN cases AS c USING (case_code)
        """).fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", help="要检索的研究问题")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 数据库文件路径")
    args = parser.parse_args()

    try:
        question = args.question if args.question is not None else input("请输入研究问题：")
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, "\n未收到研究问题。\n")
    if not question.strip():
        parser.error("请输入研究问题。")

    try:
        entries = load_entries(args.db)
    except sqlite3.Error as error:
        parser.exit(1, f"读取数据库失败（{args.db}）：{error}\n")

    matches = search(question, entries)
    if matches:
        for rank, entry in enumerate(matches, 1):
            print_entry(entry, rank)
    else:
        print("知识库里没有检索到匹配条目。可以补充研究对象、数据类型或想得到的结果。")


if __name__ == "__main__":
    main()
