"""
同义词归一化服务

Author: lvdaxianerplus
Date: 2026-06-05
"""

import re
from typing import Any

from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.synonym_index_service import CompiledSynonymIndex


class SynonymService:
    """按知识库范围将查询同义词归一到 canonical。"""

    def __init__(self, repository: KnowledgeBaseRepository):
        """初始化同义词服务。"""
        self.repository = repository
        self._index_cache: dict[tuple[tuple[str, ...], str], CompiledSynonymIndex] = {}

    def normalize_query(
        self,
        query: str,
        knowledge_base_ids: list[str] | None = None,
    ) -> str:
        """按 scoped 优先、global 兜底的顺序快速归一化查询。"""
        if not query:
            return ""
        index = self._get_index(knowledge_base_ids or [])
        return re.sub(r"\s+", " ", index.normalize(query)).strip()

    def _get_index(self, knowledge_base_ids: list[str]) -> CompiledSynonymIndex:
        """读取或构建同义词编译索引。"""
        scope = tuple(sorted(set(knowledge_base_ids)))
        revision = self.repository.get_synonym_revision(list(scope))
        cache_key = (scope, revision)
        if cache_key not in self._index_cache:
            self._index_cache[cache_key] = CompiledSynonymIndex.from_groups(
                self._load_groups(list(scope)),
                include_builtin=True,
            )
        return self._index_cache[cache_key]

    def _load_groups(self, knowledge_base_ids: list[str]) -> list[dict[str, Any]]:
        """加载启用的 scoped 和 global 同义词组。"""
        scoped_groups: list[dict[str, Any]] = []
        for knowledge_base_id in knowledge_base_ids:
            groups = self.repository.list_synonym_groups(
                knowledge_base_id=knowledge_base_id,
                include_global=False,
                enabled_only=True,
            )
            scoped_groups.extend(groups)
        global_groups = [
            group
            for group in self.repository.list_synonym_groups(enabled_only=True)
            if group["knowledge_base_id"] is None
        ]
        return scoped_groups + global_groups
