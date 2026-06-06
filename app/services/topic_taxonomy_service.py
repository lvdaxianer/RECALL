"""
确定性主题解析服务

检索路径使用，禁止调用 LLM。

Author: lvdaxianerplus
Date: 2026-06-06
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.knowledge_base_repository import KnowledgeBaseRepository


TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")


@dataclass
class ResolvedTopic:
    """查询命中的主题结构。"""

    knowledge_base_id: str = ""
    primary_topic: str = ""
    parent_topics: list[str] = field(default_factory=list)
    sibling_topics: list[str] = field(default_factory=list)
    child_topics: list[str] = field(default_factory=list)
    topic_aliases: list[str] = field(default_factory=list)
    topic_path: list[str] = field(default_factory=list)
    matched_aliases: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def matched(self) -> bool:
        """是否命中主题。"""
        return bool(self.primary_topic)


class TopicTaxonomyService:
    """基于已持久化主题表解析查询主题。"""

    def __init__(self, repository: KnowledgeBaseRepository):
        """初始化主题解析服务。"""
        self.repository = repository
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def resolve_query_topics(self, query: str, knowledge_base_ids: list[str]) -> ResolvedTopic:
        """使用别名、标准主题和 topic_path 前缀解析查询主题。"""
        normalized_query = _normalize_text(query)
        best: tuple[float, dict[str, Any], list[str], str] | None = None
        for knowledge_base_id in knowledge_base_ids:
            for record in self._load_topics(knowledge_base_id):
                score, matched_aliases, match_kind = self._score_record(record, normalized_query)
                if score <= 0:
                    continue
                if best is None or score > best[0]:
                    best = (score, record, matched_aliases, match_kind)
        if best is None:
            return ResolvedTopic()
        score, record, matched_aliases, _ = best
        return ResolvedTopic(
            knowledge_base_id=record["knowledge_base_id"],
            primary_topic=record["primary_topic"],
            parent_topics=list(record["parent_topics"]),
            sibling_topics=list(record["sibling_topics"]),
            child_topics=list(record["child_topics"]),
            topic_aliases=list(record["topic_aliases"]),
            topic_path=list(record["topic_path"]),
            matched_aliases=matched_aliases,
            confidence=min(score, 1.0),
        )

    def _load_topics(self, knowledge_base_id: str) -> list[dict[str, Any]]:
        """读取并缓存单知识库主题事实。"""
        if knowledge_base_id not in self._cache:
            self._cache[knowledge_base_id] = self.repository.list_document_topics(knowledge_base_id)
        return self._cache[knowledge_base_id]

    def _score_record(self, record: dict[str, Any], normalized_query: str) -> tuple[float, list[str], str]:
        """给主题事实打确定性匹配分。"""
        aliases = [record["primary_topic"], *record["topic_aliases"]]
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if normalized_alias and normalized_alias in normalized_query:
                return 1.0 if alias == record["primary_topic"] else 0.92, [alias], "alias"
        path_text = _normalize_text(" ".join(record["topic_path"]))
        path_prefixes = [_normalize_text(" ".join(record["topic_path"][:index])) for index in range(1, len(record["topic_path"]))]
        for prefix in sorted(path_prefixes, key=len, reverse=True):
            if prefix and prefix in normalized_query:
                return 0.74, [record["primary_topic"]], "path_prefix"
        query_tokens = set(TOKEN_PATTERN.findall(normalized_query))
        path_tokens = set(TOKEN_PATTERN.findall(path_text))
        if query_tokens and len(query_tokens & path_tokens) >= min(2, len(query_tokens)):
            return 0.5, [record["primary_topic"]], "path_tokens"
        return 0.0, [], ""


def _normalize_text(text: str) -> str:
    """归一化主题匹配文本。"""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(text or "").lower())
