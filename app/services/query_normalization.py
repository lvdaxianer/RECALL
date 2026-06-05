"""
查询归一化工具

用于查询优化、Embedding 和 Rerank 缓存 key，提升标点、空白和业务同义词变体的命中率。
"""

import re
import unicodedata


QUERY_CACHE_SYNONYMS = {
    "人脸识别门禁": "人脸门禁",
    "电梯权限": "梯控",
    "电梯联动": "梯控",
    "车辆道闸": "车辆道闸",
    "车闸": "车辆道闸",
    "有什么作用": "作用",
    "有啥作用": "作用",
    "干啥用的": "作用",
    "干什么用的": "作用",
    "用来干嘛": "作用",
    "用来做什么": "作用",
    "用途": "作用",
    "是干嘛的": "作用",
}


def normalize_query_text(query: str, synonym_groups: list[dict] | None = None) -> str:
    """
    归一化查询文本，适合构造缓存 key。

    处理内容：
    - 全角/半角统一
    - 大小写统一
    - 业务同义词归一
    - 标点符号移除
    - 连续空白压缩
    """
    normalized = unicodedata.normalize("NFKC", query or "").lower().strip()
    for group in synonym_groups or []:
        terms = [str(term).lower() for term in group.get("terms", [])]
        for source in sorted(terms, key=len, reverse=True):
            normalized = normalized.replace(source, str(group.get("canonical", "")).lower())
    for source, target in sorted(QUERY_CACHE_SYNONYMS.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalized.replace(source.lower(), target.lower())
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_query_variants(query: str, synonym_query: str | None = None) -> list[str]:
    """返回基础、硬编码和同义词归一化后的去重 query 变体。"""
    base = normalize_query_text(query, synonym_groups=[])
    builtin = normalize_query_text(query)
    synonym = normalize_query_text(synonym_query or query)
    variants = []
    for item in [base, builtin, synonym]:
        if item and item not in variants:
            variants.append(item)
    return variants
