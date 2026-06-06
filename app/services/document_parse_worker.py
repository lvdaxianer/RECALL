"""
文档后台解析 worker

Author: lvdaxianerplus
Date: 2026-06-05
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.knowledge_base_repository import KnowledgeBaseRepository


class DocumentParseWorker:
    """认领 queued 文档并以有界并发执行解析。"""

    def __init__(
        self,
        repository: KnowledgeBaseRepository,
        ingest_service: Any,
        batch_size: int = 10,
        concurrency: int = 3,
        max_attempts: int = 3,
    ):
        """初始化 worker。"""
        self.repository = repository
        self.ingest_service = ingest_service
        self.batch_size = batch_size
        self.concurrency = concurrency
        self.max_attempts = max_attempts

    async def run_once(self, knowledge_base_id: str | None = None) -> int:
        """执行一轮 queued 文档解析。"""
        documents = self.repository.claim_queued_documents(
            self.batch_size,
            knowledge_base_id=knowledge_base_id,
        )
        if not documents:
            return 0
        semaphore = asyncio.Semaphore(self.concurrency)
        await asyncio.gather(
            *(self._process_one(document, semaphore) for document in documents)
        )
        return len(documents)

    async def _process_one(
        self,
        document: dict[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> None:
        """解析单个文档并处理失败重试。"""
        async with semaphore:
            try:
                await self.ingest_service.parse_queued_document(document)
            except Exception as exc:
                self.repository.mark_document_failed(
                    document["knowledge_base_id"],
                    document["id"],
                    str(exc),
                    retryable=_is_retryable_error(exc) and document.get("parse_attempts", 0) < self.max_attempts,
                )


def _is_retryable_error(exc: Exception) -> bool:
    """判断解析错误是否适合重试。"""
    message = str(exc).lower()
    return "embedding" not in message
