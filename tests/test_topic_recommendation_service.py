"""
主题推荐服务测试

Author: lvdaxianerplus
Date: 2026-06-06
"""

import pytest

from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.topic_recommendation_service import TopicRecommendationService
from app.services.topic_taxonomy_service import TopicTaxonomyService


def _seed_topic_documents(repo: KnowledgeBaseRepository) -> tuple[str, dict, dict]:
    kb = repo.create_knowledge_base("KB", "", "owner")
    adapter = repo.upsert_document(kb["id"], "adapter.md", "text/markdown", "owner", 1)
    decorator = repo.upsert_document(kb["id"], "decorator.md", "text/markdown", "owner", 1)
    repo.replace_document_chunks(
        kb["id"],
        adapter["id"],
        [{"chunk_index": 0, "title": "适配器模式", "content": "适配器模式让接口不兼容的类协同工作。"}],
    )
    repo.replace_document_chunks(
        kb["id"],
        decorator["id"],
        [{"chunk_index": 0, "title": "装饰器模式", "content": "装饰器模式也属于结构型设计模式。"}],
    )
    repo.upsert_document_topics(
        knowledge_base_id=kb["id"],
        document_id=adapter["id"],
        primary_topic="适配器模式",
        parent_topics=["结构型模式", "设计模式"],
        sibling_topics=["装饰器模式"],
        child_topics=["Java 适配器模式实现"],
        topic_aliases=["Adapter Pattern", "适配器"],
        topic_path=["Java", "设计模式", "结构型模式", "适配器模式"],
    )
    repo.upsert_document_topics(
        knowledge_base_id=kb["id"],
        document_id=decorator["id"],
        primary_topic="装饰器模式",
        parent_topics=["结构型模式", "设计模式"],
        sibling_topics=["适配器模式"],
        topic_path=["Java", "设计模式", "结构型模式", "装饰器模式"],
    )
    return kb["id"], adapter, decorator


@pytest.mark.asyncio
async def test_topic_recommendation_service_returns_sibling_parent_child_mix(tmp_path):
    """推荐服务返回文档卡和主题导航卡，且不依赖检索期 LLM。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb_id, adapter, decorator = _seed_topic_documents(repo)
    topic_service = TopicTaxonomyService(repository=repo)
    service = TopicRecommendationService(repository=repo, topic_service=topic_service)

    recommendations = await service.build(
        query="适配器模式干啥的",
        retrieval_results=[{"document_id": adapter["id"], "score": 0.99}],
        knowledge_base_ids=[kb_id],
    )

    assert any(item.kind == "document" for item in recommendations)
    assert any(item.kind == "topic" for item in recommendations)
    assert any(item.metadata["document_id"] == decorator["id"] for item in recommendations)
    assert any("结构型模式" in item.topic_path for item in recommendations)
    assert all(item.reason for item in recommendations)


@pytest.mark.asyncio
async def test_topic_recommendation_service_falls_back_to_semantic_results(tmp_path):
    """主题未命中时使用当前检索结果构造轻量文档推荐兜底。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "", "owner")
    service = TopicRecommendationService(repository=repo, topic_service=TopicTaxonomyService(repo))

    recommendations = await service.build(
        query="未知主题",
        retrieval_results=[{
            "document_id": "doc_1",
            "document_name": "guide.md",
            "title": "Guide",
            "description": "相关资料",
            "content": "相关资料正文",
            "score": 0.7,
            "knowledge_base_id": kb["id"],
        }],
        knowledge_base_ids=[kb["id"]],
    )

    assert recommendations[0].kind == "document"
    assert recommendations[0].reason == "与当前检索结果语义相近"
