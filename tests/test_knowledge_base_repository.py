"""
知识库 SQLite 仓储测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

import pytest

from app.services.knowledge_base_repository import KnowledgeBaseRepository


def test_repository_can_create_and_list_knowledge_bases(tmp_path):
    """仓储可以创建并按 owner 列出知识库。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))

    created = repo.create_knowledge_base(
        name="技术知识库",
        description="研发文档集合",
        owner_id="user-001",
    )

    assert created["name"] == "技术知识库"
    assert created["status"] == "draft"
    assert repo.list_knowledge_bases(owner_id="user-001")[0]["id"] == created["id"]


def test_repository_creates_default_settings_with_knowledge_base(tmp_path):
    """创建知识库时同步创建默认分块与检索设置。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    created = repo.create_knowledge_base("技术知识库", "研发文档集合", "user-001")

    settings = repo.get_knowledge_base_settings(created["id"])

    assert settings["knowledge_base_id"] == created["id"]
    assert settings["semantic_chunking_enabled"] is False
    assert settings["chunk_size"] == 1000
    assert settings["overlap"] == 150
    assert settings["top_k_default"] == 5
    assert settings["max_heading_depth"] == 3
    assert settings["llm_planning_timeout_ms"] == 8000


def test_repository_updates_only_requested_settings_fields(tmp_path):
    """更新知识库设置时只覆盖请求字段。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    created = repo.create_knowledge_base("技术知识库", "研发文档集合", "user-001")

    updated = repo.update_knowledge_base_settings(created["id"], {"overlap": 240})

    assert updated["overlap"] == 240
    assert updated["chunk_size"] == 1000
    assert updated["top_k_default"] == 5


def test_repository_settings_requires_existing_knowledge_base(tmp_path):
    """读取缺失知识库设置时沿用仓储不存在异常。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))

    with pytest.raises(ValueError):
        repo.get_knowledge_base_settings("missing")


def test_repository_can_update_and_soft_delete_knowledge_base(tmp_path):
    """仓储支持更新描述和软删除知识库。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    created = repo.create_knowledge_base(
        name="产品知识库",
        description="产品文档",
        owner_id="user-001",
    )

    updated = repo.update_knowledge_base(created["id"], description="更新后的描述")
    deleted = repo.delete_knowledge_base(created["id"])

    assert updated["description"] == "更新后的描述"
    assert deleted["status"] == "deleted"


def test_repository_delete_knowledge_base_cascades_documents_and_chunks(tmp_path):
    """删除知识库时同步删除该库下文档和 chunk。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    created = repo.create_knowledge_base(
        name="产品知识库",
        description="产品文档",
        owner_id="user-001",
    )
    document = repo.upsert_document(
        knowledge_base_id=created["id"],
        document_name="guide.md",
        content_type="text/markdown",
        owner_id="user-001",
        chunk_count=2,
        external_id="guide",
    )
    repo.replace_document_chunks(
        created["id"],
        document["id"],
        [
            {"chunk_index": 0, "title": "A", "content": "第一段"},
            {"chunk_index": 1, "title": "B", "content": "第二段"},
        ],
    )

    deleted = repo.delete_knowledge_base(created["id"])

    assert deleted["status"] == "deleted"
    assert deleted["deleted_document_count"] == 1
    assert deleted["deleted_chunk_count"] == 2
    assert repo.list_documents(created["id"]) == []
    assert repo.list_document_chunks(created["id"], document["id"]) == []


def test_repository_persists_indexed_content_separately_from_display_content(tmp_path):
    """chunk 展示正文和检索索引正文可以分开保存。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("技术知识库", "研发文档集合", "user-001")
    document = repo.upsert_document(
        knowledge_base_id=kb["id"],
        document_name="guide.md",
        content_type="text/markdown",
        owner_id="user-001",
        chunk_count=1,
    )

    repo.replace_document_chunks(
        kb["id"],
        document["id"],
        [{
            "chunk_index": 0,
            "title": "标题",
            "content": "展示正文",
            "indexed_content": "上一段尾部\n展示正文",
        }],
    )

    chunk = repo.list_document_chunks(kb["id"], document["id"])[0]
    assert chunk["content"] == "展示正文"
    assert chunk["indexed_content"] == "上一段尾部\n展示正文"


def test_repository_tracks_release_status(tmp_path):
    """仓储支持知识库发版状态流转。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    created = repo.create_knowledge_base(
        name="发布知识库",
        description="发布流转",
        owner_id="user-001",
    )

    changed = repo.mark_knowledge_base_changed(created["id"])
    publishing = repo.update_knowledge_base_status(created["id"], "publishing")
    published = repo.update_knowledge_base_status(created["id"], "published")

    assert changed["status"] == "changed"
    assert publishing["status"] == "publishing"
    assert published["status"] == "published"


def test_repository_can_get_knowledge_bases_by_ids(tmp_path):
    """仓储支持按 ID 批量读取知识库，缺失 ID 不返回。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    first = repo.create_knowledge_base("第一知识库", "desc", "user-001")
    second = repo.create_knowledge_base("第二知识库", "desc", "user-001")

    records = repo.get_knowledge_bases_by_ids([first["id"], "missing", second["id"]])

    assert [item["id"] for item in records] == [first["id"], second["id"]]


def test_repository_queues_document_with_raw_content_and_parse_status(tmp_path):
    """文档上传先进入解析队列并保留原文。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")

    document = repo.enqueue_document(
        knowledge_base_id=kb["id"],
        document_name="a.md",
        content_type="text/markdown",
        owner_id="u1",
        raw_content="# A",
        external_id="a.md",
    )

    assert document["parse_status"] == "queued"
    assert document["status"] == "queued"
    assert document["chunk_count"] == 0
    assert document["raw_content"] == "# A"
    assert document["parse_attempts"] == 0
    assert document["parse_error"] is None


def test_repository_list_documents_excludes_raw_content(tmp_path):
    """文档列表不返回原文大字段，避免状态轮询变慢。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    document = repo.enqueue_document(kb["id"], "a.md", "text/markdown", "u1", "# A", "a.md")

    listed = repo.list_documents(kb["id"])
    detail = repo.get_document(kb["id"], document["id"])

    assert "raw_content" not in listed[0]
    assert detail["raw_content"] == "# A"


def test_repository_claims_queued_documents_once(tmp_path):
    """worker 原子认领 queued 文档，避免并发重复解析。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    repo.enqueue_document(kb["id"], "a.md", "text/markdown", "u1", "# A", "a.md")

    first_claim = repo.claim_queued_documents(limit=10)
    second_claim = repo.claim_queued_documents(limit=10)

    assert len(first_claim) == 1
    assert first_claim[0]["parse_status"] == "processing"
    assert first_claim[0]["status"] == "processing"
    assert second_claim == []
    assert repo.get_document(kb["id"], first_claim[0]["id"])["parse_attempts"] == 1


def test_repository_marks_document_failed_or_requeued(tmp_path):
    """解析失败可重回队列，达到上限后进入 failed。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    doc = repo.enqueue_document(kb["id"], "a.md", "text/markdown", "u1", "# A", "a.md")
    claimed = repo.claim_queued_documents(limit=1)[0]

    requeued = repo.mark_document_failed(kb["id"], claimed["id"], "temporary", retryable=True)
    claimed_again = repo.claim_queued_documents(limit=1)[0]
    failed = repo.mark_document_failed(kb["id"], claimed_again["id"], "boom", retryable=False)

    assert requeued["parse_status"] == "queued"
    assert failed["parse_status"] == "failed"
    assert failed["parse_error"] == "boom"
    assert repo.get_document(kb["id"], doc["id"])["parse_attempts"] == 2


def test_repository_persists_document_topics_and_topic_edges(tmp_path):
    """仓储保存文档主题事实表，并维护可检索的主题节点和边。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "", "owner")
    document = repo.upsert_document(
        knowledge_base_id=kb["id"],
        document_name="adapter.md",
        content_type="text/markdown",
        owner_id="owner",
        chunk_count=1,
        external_id="adapter.md",
    )

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
        evidence=["标题命中", "章节标题命中"],
    )

    record = repo.get_document_topics(kb["id"], document["id"])
    assert record["primary_topic"] == "适配器模式"
    assert record["topic_path"] == ["Java", "设计模式", "结构型模式", "适配器模式"]
    assert record["topic_aliases"] == ["Adapter Pattern", "适配器"]
    nodes = repo.list_topic_nodes(kb["id"])
    assert {node["canonical_topic"] for node in nodes} >= {"适配器模式", "结构型模式", "设计模式"}
    same_topic_docs = repo.find_documents_by_topic(kb["id"], "适配器模式", relation_type="same")
    parent_topic_docs = repo.find_documents_by_topic(kb["id"], "结构型模式", relation_type="parent")
    assert same_topic_docs[0]["document_id"] == document["id"]
    assert parent_topic_docs[0]["document_id"] == document["id"]
