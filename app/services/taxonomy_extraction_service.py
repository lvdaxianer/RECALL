"""
文档主题树抽取服务

只在文档写入/解析路径调用 LLM；检索路径不得依赖本服务。

Author: lvdaxianerplus
Date: 2026-06-06
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.models.knowledge_base_schemas import DocumentTopicExtractionResult
from app.services.llm_service import get_llm_service


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$", flags=re.MULTILINE)
MAX_CONTENT_PREVIEW_CHARS = 6000


class TaxonomyExtractionService:
    """调用 LLM 为文档抽取标准主题树标签。"""

    def __init__(self, llm_service: Any | None = None):
        """初始化主题抽取服务。"""
        self.llm_service = llm_service

    async def extract(
        self,
        title: str,
        content: str,
        existing_tags: list[str] | None = None,
    ) -> DocumentTopicExtractionResult:
        """抽取文档主题；失败时返回确定性兜底结果。"""
        fallback = self._fallback(title, content, existing_tags)
        try:
            response = await self._get_llm_service().chat_simple(
                self._build_prompt(title, content, existing_tags),
                system="你是 Recall 的文档主题树标注器。只输出 JSON，不要输出解释文字。",
                temperature=0.1,
            )
            data = _extract_json_object(response)
            return self._parse_result(data, fallback)
        except Exception:
            return fallback

    def _get_llm_service(self):
        """懒加载 LLM 服务，确保初始化失败也能走 fallback。"""
        if self.llm_service is None:
            self.llm_service = get_llm_service()
        return self.llm_service

    def _build_prompt(self, title: str, content: str, existing_tags: list[str] | None) -> str:
        """构造主题抽取 prompt。"""
        headings = HEADING_PATTERN.findall(content)
        heading_titles = [heading.strip() for _, heading in headings[:30]]
        payload = {
            "title": title,
            "existing_tags": existing_tags or [],
            "heading_titles": heading_titles,
            "content_preview": content[:MAX_CONTENT_PREVIEW_CHARS],
        }
        return (
            "请为这篇知识库文档抽取可用于推荐召回的主题树标签。\n"
            "要求：只输出 JSON；不要编造不存在的专有名词；主题要短且可复用；"
            "parent_topics 从近到远或从具体上位到更大类均可，但 topic_path 必须从大类到 primary_topic。\n"
            "JSON 字段必须包含：primary_topic, parent_topics, sibling_topics, child_topics, "
            "topic_aliases, topic_path, confidence, evidence。\n"
            f"文档信息：\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def _parse_result(
        self,
        data: dict[str, Any],
        fallback: DocumentTopicExtractionResult,
    ) -> DocumentTopicExtractionResult:
        """解析并规范化 LLM JSON。"""
        primary_topic = _clean_text(data.get("primary_topic")) or fallback.primary_topic
        parent_topics = _clean_list(data.get("parent_topics"))
        sibling_topics = _clean_list(data.get("sibling_topics"))
        child_topics = _clean_list(data.get("child_topics"))
        topic_aliases = _clean_list(data.get("topic_aliases"))
        topic_path = _clean_list(data.get("topic_path"))
        if not topic_path:
            topic_path = [*parent_topics, primary_topic] if parent_topics else [primary_topic]
        elif topic_path[-1] != primary_topic:
            topic_path.append(primary_topic)
        return DocumentTopicExtractionResult(
            primary_topic=primary_topic,
            parent_topics=parent_topics,
            sibling_topics=sibling_topics,
            child_topics=child_topics,
            topic_aliases=topic_aliases,
            topic_path=topic_path,
            confidence=_clean_confidence(data.get("confidence"), fallback.confidence),
            evidence=_clean_list(data.get("evidence")),
        )

    def _fallback(
        self,
        title: str,
        content: str,
        existing_tags: list[str] | None,
    ) -> DocumentTopicExtractionResult:
        """用标题、一级标题和已有标签构造确定性兜底主题。"""
        primary_topic = _clean_text(title) or _first_heading(content) or "未分类主题"
        parents = _clean_list(existing_tags)
        return DocumentTopicExtractionResult(
            primary_topic=primary_topic,
            parent_topics=parents,
            topic_path=[*parents, primary_topic] if parents else [primary_topic],
            confidence=0.2,
            evidence=["fallback:title_or_heading"],
        )


def _extract_json_object(response: str) -> dict[str, Any]:
    """从模型响应中提取 JSON object。"""
    text = response.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _clean_text(value: Any) -> str:
    """清理单个主题文本。"""
    return str(value or "").strip()[:160]


def _clean_list(value: Any) -> list[str]:
    """清理、去重字符串列表。"""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _clean_confidence(value: Any, fallback: float) -> float:
    """清理置信度字段。"""
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return fallback


def _first_heading(content: str) -> str:
    """读取第一条 Markdown 标题。"""
    match = HEADING_PATTERN.search(content)
    return match.group(2).strip() if match else ""
