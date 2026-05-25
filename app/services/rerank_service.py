"""
Rerank 服务模块

调用 qwen3 Rerank API 重排结果，支持缓存

@author lvdaxianerplus
@date 2026-04-14
"""

import httpx
from typing import List, Dict, Any, Optional
from app.config import Config
from app.utils.logger import rerank_logger
from app.services.cache_service import get_cache_service


class RerankService:
    """Rerank 服务类"""

    def __init__(
        self,
        api_key: str = None,
        request_url: str = None,
        model_name: str = None,
        use_cache: bool = None
    ):
        """
        初始化 Rerank 服务

        @param api_key - API 密钥
        @param request_url - 请求 URL
        @param model_name - 模型名称
        @param use_cache - 是否使用缓存，默认使用 Config.RERANK_CACHE_ENABLED
        """
        self.api_key = api_key or Config.RERANK_MODEL_API_KEY
        self.request_url = request_url or Config.RERANK_REQUEST_URL
        self.model_name = model_name or Config.RERANK_MODEL_NAME
        self.use_cache = use_cache if use_cache is not None else Config.RERANK_CACHE_ENABLED
        self._cache = None  # 懒加载

    @property
    def cache(self):
        """懒加载缓存服务"""
        if self._cache is None:
            self._cache = get_cache_service()
        return self._cache

    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        对文档进行重排（支持缓存）

        @param query - 查询文本
        @param documents - 文档列表，每项包含 id、description、score
        @returns 重排后的结果，包含 index 和 score
        """
        if not documents:
            return []

        # 提取 doc_ids 用于缓存 key
        doc_ids = [doc.get("id", "") for doc in documents]

        # 检查缓存
        if self.use_cache:
            cached = self.cache.get_rerank(query, doc_ids)
            if cached is not None:
                rerank_logger.debug("[Rerank] 使用缓存, query={}, doc_ids={}", query[:50], len(doc_ids))
                return cached

        # 调用 API
        try:
            # 构建文档文本
            doc_texts = [
                doc.get("description", "")
                for doc in documents
            ]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.request_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model_name,
                        "query": query,
                        "documents": doc_texts
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()

                rerank_results = result.get("results", [])

                # 缓存结果
                if self.use_cache:
                    self.cache.set_rerank(query, doc_ids, rerank_results)

                return rerank_results

        except httpx.HTTPError as e:
            rerank_logger.error("[Rerank] HTTP 错误, error={}", str(e))
            raise
        except Exception as e:
            rerank_logger.error("[Rerank] 重排失败, error={}", str(e))
            raise

    async def health_check(self) -> bool:
        """
        健康检查

        @returns 服务是否可用
        """
        try:
            await self.rerank("health check", [{"id": "1", "description": "test"}])
            return True
        except Exception as e:
            rerank_logger.error("[Rerank] 健康检查失败, error={}", str(e))
            return False
