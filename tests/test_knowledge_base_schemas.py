"""
知识库 Retrieval SDK schema 契约测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

import pytest

from app.models.knowledge_base_schemas import DocumentUploadRequest
from app.models.knowledge_base_schemas import DocumentTopicExtractionResult
from app.models.knowledge_base_schemas import KnowledgeBaseCreateRequest
from app.models.knowledge_base_schemas import KnowledgeBaseSettings
from app.models.knowledge_base_schemas import RetrievalSDKSearchRequest
from app.models.schemas import RecommendationResult


def test_document_upload_request_requires_kb_and_text_content():
    """文档录入请求必须包含知识库 ID，且允许 Markdown 内容。"""
    request = DocumentUploadRequest(
        knowledge_base_id="kb-001",
        name="README.md",
        content="# 标题\n正文",
        content_type="text/markdown",
    )

    assert request.knowledge_base_id == "kb-001"
    assert request.content_type == "text/markdown"


def test_document_upload_request_rejects_binary_content_type():
    """文档录入请求拒绝二进制或解析类内容类型。"""
    with pytest.raises(ValueError):
        DocumentUploadRequest(
            knowledge_base_id="kb-001",
            name="report.pdf",
            content="binary",
            content_type="application/pdf",
        )


def test_retrieval_sdk_search_request_accepts_kb_filters():
    """Retrieval SDK 检索请求支持多知识库过滤。"""
    request = RetrievalSDKSearchRequest(
        input="登录失败怎么排查",
        knowledge_base_ids=["kb-001", "kb-002"],
        top_k=5,
    )

    assert request.knowledge_base_ids == ["kb-001", "kb-002"]


def test_retrieval_sdk_request_accepts_issue_type():
    """Retrieval SDK 检索请求支持问题类型过滤入口。"""
    request = RetrievalSDKSearchRequest(
        input="白屏怎么排查",
        knowledge_base_ids=["kb-001"],
        issue_type="fault",
    )

    assert request.issue_type == "fault"


def test_retrieval_sdk_request_accepts_temperature():
    """聊天检索请求允许控制 LLM 生成温度。"""
    request = RetrievalSDKSearchRequest(
        input="解释一下装饰器",
        knowledge_base_ids=["kb-001"],
        temperature=0.2,
    )

    assert request.temperature == 0.2


def test_retrieval_sdk_request_rejects_temperature_above_one():
    """生成温度限制在 0 到 1。"""
    with pytest.raises(ValueError):
        RetrievalSDKSearchRequest(
            input="解释一下装饰器",
            knowledge_base_ids=["kb-001"],
            temperature=1.5,
        )


def test_knowledge_base_create_request_normalizes_description():
    """知识库创建请求在缺省描述时提供稳定默认值。"""
    request = KnowledgeBaseCreateRequest(name="技术知识库", owner_id="user-001")

    assert request.description == ""


def test_knowledge_base_settings_defaults_to_smaller_chunks_with_more_overlap():
    """知识库默认分块参数兼顾召回粒度和上下文连续性。"""
    settings = KnowledgeBaseSettings(
        knowledge_base_id="kb-001",
        updated_at="2026-06-05T00:00:00Z",
    )

    assert settings.chunk_size == 1000
    assert settings.overlap == 150


def test_knowledge_base_settings_rejects_overlap_not_smaller_than_chunk_size():
    """知识库分块设置要求 overlap 小于 chunk_size。"""
    with pytest.raises(ValueError):
        KnowledgeBaseSettings(
            knowledge_base_id="kb-001",
            chunk_size=500,
            overlap=500,
            updated_at="2026-06-05T00:00:00Z",
        )


def test_knowledge_base_settings_accepts_max_heading_depth_three():
    """知识库分块设置允许最大三级 Markdown 标题。"""
    settings = KnowledgeBaseSettings(
        knowledge_base_id="kb-001",
        max_heading_depth=3,
        updated_at="2026-06-05T00:00:00Z",
    )

    assert settings.max_heading_depth == 3


def test_knowledge_base_settings_rejects_max_heading_depth_four():
    """知识库分块设置拒绝超过三级的标题深度。"""
    with pytest.raises(ValueError):
        KnowledgeBaseSettings(
            knowledge_base_id="kb-001",
            max_heading_depth=4,
            updated_at="2026-06-05T00:00:00Z",
        )


def test_knowledge_base_settings_rejects_zero_top_k_default():
    """知识库分块设置拒绝无效的默认 topK。"""
    with pytest.raises(ValueError):
        KnowledgeBaseSettings(
            knowledge_base_id="kb-001",
            top_k_default=0,
            updated_at="2026-06-05T00:00:00Z",
        )


def test_document_topic_extraction_result_defaults_to_empty_taxonomy_lists():
    """文档主题抽取结果在只给主主题时提供稳定空列表默认值。"""
    result = DocumentTopicExtractionResult(primary_topic="适配器模式")

    assert result.parent_topics == []
    assert result.sibling_topics == []
    assert result.child_topics == []
    assert result.topic_aliases == []
    assert result.topic_path == []
    assert result.confidence == 0.0


def test_recommendation_result_supports_document_and_topic_cards():
    """推荐结果可以表达文档卡片和主题导航卡片。"""
    recommendation = RecommendationResult(
        metadata={"id": "topic-adapter"},
        description="继续了解结构型设计模式",
        score=0.8,
        reason="同属结构型模式",
        kind="topic",
        topic_path=["Java", "设计模式", "结构型模式"],
        follow_up_question="结构型模式里还有哪些常见设计模式？",
    )

    assert recommendation.kind == "topic"
    assert recommendation.topic_path == ["Java", "设计模式", "结构型模式"]
    assert recommendation.follow_up_question == "结构型模式里还有哪些常见设计模式？"
