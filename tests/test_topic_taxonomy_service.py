"""
确定性主题解析服务测试

Author: lvdaxianerplus
Date: 2026-06-06
"""

from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.topic_taxonomy_service import TopicTaxonomyService


def test_topic_taxonomy_service_resolves_query_without_llm(tmp_path):
    """检索期主题解析只依赖已落库的主题节点、别名和路径。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "", "owner")
    document = repo.upsert_document(kb["id"], "adapter.md", "text/markdown", "owner", 1)
    repo.upsert_document_topics(
        knowledge_base_id=kb["id"],
        document_id=document["id"],
        primary_topic="适配器模式",
        parent_topics=["结构型模式", "设计模式"],
        sibling_topics=["装饰器模式"],
        child_topics=["Java 适配器模式实现"],
        topic_aliases=["Adapter Pattern", "适配器"],
        topic_path=["Java", "设计模式", "结构型模式", "适配器模式"],
        confidence=0.92,
    )
    service = TopicTaxonomyService(repository=repo)

    result = service.resolve_query_topics("适配器模式干啥的", knowledge_base_ids=[kb["id"]])

    assert result.primary_topic == "适配器模式"
    assert result.parent_topics == ["结构型模式", "设计模式"]
    assert result.matched_aliases == ["适配器模式"]
    assert result.knowledge_base_id == kb["id"]


def test_topic_taxonomy_service_matches_alias_and_topic_path_prefix(tmp_path):
    """查询命中别名或路径前缀时也能解析到同一个标准主题。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "", "owner")
    document = repo.upsert_document(kb["id"], "adapter.md", "text/markdown", "owner", 1)
    repo.upsert_document_topics(
        knowledge_base_id=kb["id"],
        document_id=document["id"],
        primary_topic="适配器模式",
        parent_topics=["结构型模式", "设计模式"],
        topic_aliases=["Adapter Pattern", "适配器"],
        topic_path=["Java", "设计模式", "结构型模式", "适配器模式"],
    )
    service = TopicTaxonomyService(repository=repo)

    alias_result = service.resolve_query_topics("Adapter Pattern 怎么实现", [kb["id"]])
    path_result = service.resolve_query_topics("Java 设计模式 结构型模式", [kb["id"]])

    assert alias_result.primary_topic == "适配器模式"
    assert path_result.primary_topic == "适配器模式"
