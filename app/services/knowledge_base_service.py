"""
知识库领域服务

封装知识库 CRUD 与归属校验，路由层不直接操作仓储细节。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from __future__ import annotations

from typing import Any

from app.services.knowledge_base_repository import KnowledgeBaseRepository


class KnowledgeBaseService:
    """知识库领域服务实现。"""

    def __init__(self, repository: KnowledgeBaseRepository):
        """初始化知识库服务。"""
        self.repository = repository

    def create_knowledge_base(self, name: str, description: str, owner_id: str) -> dict[str, Any]:
        """创建知识库。"""
        return self.repository.create_knowledge_base(
            name=name.strip(),
            description=description.strip(),
            owner_id=owner_id.strip(),
        )

    def list_knowledge_bases(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        """按 owner_id 列出知识库。"""
        return self.repository.list_knowledge_bases(owner_id=owner_id)

    def get_knowledge_base(self, kb_id: str) -> dict[str, Any]:
        """读取知识库详情。"""
        return self._require_knowledge_base(kb_id)

    def update_knowledge_base(
        self,
        kb_id: str,
        owner_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """校验 owner 后更新知识库。"""
        knowledge_base = self._require_knowledge_base(kb_id)
        self.assert_owner_can_mutate(knowledge_base, owner_id)
        return self.repository.update_knowledge_base(
            kb_id=kb_id,
            name=name,
            description=description,
        )

    def publish_knowledge_base(self, kb_id: str, owner_id: str) -> dict[str, Any]:
        """校验 owner 后发布知识库。"""
        knowledge_base = self._require_knowledge_base(kb_id)
        self.assert_owner_can_mutate(knowledge_base, owner_id)
        return self.repository.update_knowledge_base_status(kb_id, "published")

    def delete_knowledge_base(self, kb_id: str, owner_id: str) -> dict[str, Any]:
        """校验 owner 后软删除知识库。"""
        knowledge_base = self._require_knowledge_base(kb_id)
        self.assert_owner_can_mutate(knowledge_base, owner_id)
        return self.repository.delete_knowledge_base(kb_id)

    def assert_owner_can_mutate(self, knowledge_base: dict[str, Any], owner_id: str) -> None:
        """校验 owner 是否允许修改知识库。"""
        if knowledge_base["owner_id"] == owner_id:
            return
        else:
            raise PermissionError("无权操作该知识库")

    def _require_knowledge_base(self, kb_id: str) -> dict[str, Any]:
        """读取知识库，不存在时抛出 ValueError。"""
        knowledge_base = self.repository.get_knowledge_base(kb_id)
        if knowledge_base is not None:
            return knowledge_base
        else:
            raise ValueError("知识库不存在")
