"""
知识库领域服务测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

import pytest

from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.knowledge_base_service import KnowledgeBaseService


def test_service_create_list_update_delete_knowledge_base(tmp_path):
    """服务支持创建、列表、更新和软删除知识库。"""
    service = KnowledgeBaseService(KnowledgeBaseRepository(str(tmp_path / "kb.sqlite")))

    created = service.create_knowledge_base(
        name="产品知识库",
        description="产品文档",
        owner_id="user-001",
    )
    listing = service.list_knowledge_bases(owner_id="user-001")
    updated = service.update_knowledge_base(
        kb_id=created["id"],
        owner_id="user-001",
        description="更新后的描述",
    )
    deleted = service.delete_knowledge_base(kb_id=created["id"], owner_id="user-001")

    assert listing[0]["id"] == created["id"]
    assert updated["description"] == "更新后的描述"
    assert deleted["status"] == "deleted"


def test_service_publish_requires_owner_and_marks_published(tmp_path):
    """服务发布知识库时校验 owner 并返回已发布状态。"""
    service = KnowledgeBaseService(KnowledgeBaseRepository(str(tmp_path / "kb.sqlite")))
    created = service.create_knowledge_base(
        name="产品知识库",
        description="产品文档",
        owner_id="user-001",
    )

    published = service.publish_knowledge_base(kb_id=created["id"], owner_id="user-001")

    assert published["status"] == "published"


def test_service_rejects_non_owner_mutation(tmp_path):
    """非 owner 不能修改知识库。"""
    service = KnowledgeBaseService(KnowledgeBaseRepository(str(tmp_path / "kb.sqlite")))
    created = service.create_knowledge_base(
        name="产品知识库",
        description="产品文档",
        owner_id="user-001",
    )

    with pytest.raises(PermissionError):
        service.update_knowledge_base(
            kb_id=created["id"],
            owner_id="user-002",
            description="越权修改",
        )
