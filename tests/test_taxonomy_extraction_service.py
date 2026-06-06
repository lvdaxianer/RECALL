"""
主题树抽取服务测试

Author: lvdaxianerplus
Date: 2026-06-06
"""

import pytest

import app.services.taxonomy_extraction_service as taxonomy_module
from app.services.taxonomy_extraction_service import TaxonomyExtractionService


class FakeLLMService:
    """测试用 LLM 服务。"""

    def __init__(self, response: str):
        """保存响应文本和 prompt。"""
        self.response = response
        self.prompts = []

    async def chat_simple(self, prompt: str, **kwargs):
        """记录 prompt 并返回预设响应。"""
        self.prompts.append((prompt, kwargs))
        return self.response


@pytest.mark.asyncio
async def test_taxonomy_extractor_returns_canonical_topic_structure():
    """有效 LLM JSON 会被解析为标准主题树结构。"""
    llm = FakeLLMService(
        """
        {
          "primary_topic": "适配器模式",
          "parent_topics": ["结构型模式", "设计模式"],
          "sibling_topics": ["装饰器模式"],
          "child_topics": ["Java 适配器模式实现"],
          "topic_aliases": ["Adapter Pattern", "适配器"],
          "topic_path": ["Java", "设计模式", "结构型模式", "适配器模式"],
          "confidence": 0.92,
          "evidence": ["标题命中", "章节标题命中"]
        }
        """
    )
    service = TaxonomyExtractionService(llm_service=llm)

    result = await service.extract(
        title="适配器模式干啥的",
        content="# 适配器模式\n## Java 示例\n正文",
        existing_tags=["设计模式"],
    )

    assert result.primary_topic == "适配器模式"
    assert "结构型模式" in result.parent_topics
    assert "Adapter Pattern" in result.topic_aliases
    assert result.topic_path[-1] == "适配器模式"
    assert "primary_topic" in llm.prompts[0][0]


@pytest.mark.asyncio
async def test_taxonomy_extractor_falls_back_without_blocking_on_bad_json():
    """LLM 返回坏 JSON 时使用标题和已有标签构造确定性兜底主题。"""
    service = TaxonomyExtractionService(llm_service=FakeLLMService("not json"))

    result = await service.extract(
        title="适配器模式干啥的",
        content="# 适配器模式\n正文",
        existing_tags=["设计模式"],
    )

    assert result.primary_topic == "适配器模式干啥的"
    assert result.parent_topics == ["设计模式"]
    assert result.topic_path == ["设计模式", "适配器模式干啥的"]
    assert result.confidence == 0.2


@pytest.mark.asyncio
async def test_taxonomy_extractor_falls_back_when_llm_initialization_fails(monkeypatch):
    """LLM 初始化不可用时也应返回确定性主题兜底，不影响入库。"""
    def broken_llm_service():
        raise RuntimeError("missing model config")

    monkeypatch.setattr(taxonomy_module, "get_llm_service", broken_llm_service)
    service = TaxonomyExtractionService()

    result = await service.extract(
        title="知识库怎么分块",
        content="# 知识库分块\n正文",
        existing_tags=["RAG"],
    )

    assert result.primary_topic == "知识库怎么分块"
    assert result.parent_topics == ["RAG"]
    assert result.topic_path == ["RAG", "知识库怎么分块"]
