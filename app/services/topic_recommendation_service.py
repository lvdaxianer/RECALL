"""
主题相关推荐服务

检索路径使用，候选来自主题事实表和当前检索结果，不调用 LLM。

Author: lvdaxianerplus
Date: 2026-06-06
"""

from __future__ import annotations

from typing import Any

from app.config import Config
from app.models.schemas import RecommendationResult
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.topic_taxonomy_service import ResolvedTopic, TopicTaxonomyService


class TopicRecommendationService:
    """构建文档推荐和主题导航推荐。"""

    def __init__(
        self,
        repository: KnowledgeBaseRepository,
        topic_service: TopicTaxonomyService | None = None,
        top_k: int | None = None,
    ):
        """初始化推荐服务。"""
        self.repository = repository
        self.topic_service = topic_service or TopicTaxonomyService(repository)
        self.top_k = top_k if top_k is not None else Config.RAG_RECOMMENDATION_TOP_K

    async def build(
        self,
        query: str,
        retrieval_results: list[dict[str, Any]],
        knowledge_base_ids: list[str],
    ) -> list[RecommendationResult]:
        """生成混合推荐卡片。"""
        resolved = self.topic_service.resolve_query_topics(query, knowledge_base_ids)
        cards: list[RecommendationResult] = []
        seen_keys: set[str] = set()
        if resolved.matched:
            for relation_type, reason in [
                ("same", "同主题资料"),
                ("sibling", "同类主题资料"),
                ("parent", "上位主题资料"),
                ("child", "下位主题资料"),
            ]:
                for record in self._related_documents(resolved, relation_type):
                    key = f"doc:{record['document_id']}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    cards.append(_document_card(record, reason))
                    if len(cards) >= self.top_k:
                        break
                if len(cards) >= self.top_k:
                    break
            cards.extend(self._topic_navigation_cards(resolved, seen_keys))
        if not cards:
            cards.extend(_semantic_fallback_cards(retrieval_results, self.top_k))
        return cards[: max(0, self.top_k)]

    def _related_documents(self, resolved: ResolvedTopic, relation_type: str) -> list[dict[str, Any]]:
        """按关系读取相关文档。"""
        if relation_type == "same":
            topics = [resolved.primary_topic]
        elif relation_type == "sibling":
            topics = resolved.sibling_topics
        elif relation_type == "parent":
            topics = resolved.parent_topics
        elif relation_type == "child":
            topics = resolved.child_topics
        else:
            topics = []
        records: list[dict[str, Any]] = []
        seen_docs: set[str] = set()
        for topic in topics:
            for record in self.repository.find_documents_by_topic(
                resolved.knowledge_base_id,
                topic,
                relation_type=relation_type,
                limit=self.top_k,
            ):
                if record["document_id"] in seen_docs:
                    continue
                seen_docs.add(record["document_id"])
                records.append(record)
        return records

    def _topic_navigation_cards(self, resolved: ResolvedTopic, seen_keys: set[str]) -> list[RecommendationResult]:
        """构造主题导航卡。"""
        cards: list[RecommendationResult] = []
        navigation_targets = [
            ("parent", resolved.parent_topics[-1:] or resolved.parent_topics, "继续了解{}的整体脉络"),
            ("sibling", resolved.sibling_topics[:1], "对比{}和当前主题的区别"),
            ("child", resolved.child_topics[:1], "深入看看{}的具体实现"),
        ]
        for relation, topics, question_template in navigation_targets:
            for topic in topics:
                key = f"topic:{relation}:{topic}"
                if not topic or key in seen_keys:
                    continue
                seen_keys.add(key)
                cards.append(RecommendationResult(
                    metadata={"id": key, "topic": topic, "relation": relation},
                    description=question_template.format(topic),
                    score=0.66,
                    features={"category": "topic_navigation", "tags": [topic]},
                    reason=_topic_reason(relation),
                    kind="topic",
                    topic_path=_topic_path_for_card(resolved, topic),
                    follow_up_question=question_template.format(topic),
                ))
        return cards


def _document_card(record: dict[str, Any], reason: str) -> RecommendationResult:
    """把文档主题事实转成推荐文档卡。"""
    return RecommendationResult(
        metadata={
            "id": record["document_id"],
            "document_id": record["document_id"],
            "knowledge_base_id": record["knowledge_base_id"],
            "document_name": record.get("document_name", ""),
        },
        description=record.get("document_name") or record["primary_topic"],
        score=max(0.6, float(record.get("confidence", 0.0))),
        features={
            "category": "topic_document",
            "tags": [record["primary_topic"], *record.get("parent_topics", [])],
        },
        reason=reason,
        kind="document",
        topic_path=list(record.get("topic_path") or []),
    )


def _semantic_fallback_cards(retrieval_results: list[dict[str, Any]], top_k: int) -> list[RecommendationResult]:
    """主题未命中时从当前检索结果构造兜底文档推荐。"""
    cards: list[RecommendationResult] = []
    seen_docs: set[str] = set()
    for result in retrieval_results:
        document_id = str(result.get("document_id") or result.get("id") or result.get("chunk_id") or "")
        if not document_id or document_id in seen_docs:
            continue
        seen_docs.add(document_id)
        cards.append(RecommendationResult(
            metadata={
                "id": document_id,
                "document_id": document_id,
                "knowledge_base_id": result.get("knowledge_base_id", ""),
                "document_name": result.get("document_name", ""),
            },
            description=result.get("description") or result.get("content") or result.get("title") or "",
            score=float(result.get("score", 0.0)),
            features={"category": "semantic_fallback", "tags": [result.get("title", "")]},
            reason="与当前检索结果语义相近",
            kind="document",
        ))
        if len(cards) >= top_k:
            break
    return cards


def _topic_reason(relation: str) -> str:
    """主题导航推荐原因。"""
    if relation == "parent":
        return "上位主题可帮助建立整体框架"
    if relation == "sibling":
        return "同类主题适合对比学习"
    if relation == "child":
        return "下位主题适合继续深入"
    return "相关主题可继续探索"


def _topic_path_for_card(resolved: ResolvedTopic, topic: str) -> list[str]:
    """为主题导航卡构造路径。"""
    if topic in resolved.topic_path:
        return resolved.topic_path[: resolved.topic_path.index(topic) + 1]
    return [*resolved.topic_path, topic] if resolved.topic_path else [topic]
