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
        self._client = None  # 懒加载，复用连接池

    @property
    def cache(self):
        """懒加载缓存服务"""
        if self._cache is None:
            self._cache = get_cache_service()
        return self._cache

    @property
    def client(self) -> httpx.AsyncClient:
        """懒加载 HTTP 客户端，复用连接池降低模型调用延迟"""
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        """关闭 HTTP 客户端连接池"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def calculate_candidate_limit(self, total_candidates: int, top_k: Optional[int]) -> int:
        """计算 provider-safe 的 Rerank 候选数上限。"""
        configured = max(1, Config.RAG_RERANK_CANDIDATE_LIMIT)
        provider_safe = max(1, Config.RAG_RERANK_PROVIDER_SAFE_LIMIT)
        requested = max(1, top_k or configured)
        return min(total_candidates, configured, provider_safe, requested)

    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        request_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        对文档进行重排（支持缓存）

        @param query - 查询文本
        @param documents - 文档列表，每项包含 id、description、score
        @returns 重排后的结果，包含 index 和 score
        """
        if not documents:
            return []

        # 提取 doc_ids 和内容指纹用于缓存 key。
        # Rerank 返回 index，缓存必须同时对候选顺序和候选内容敏感。
        doc_ids = [doc.get("id", "") for doc in documents]
        doc_fingerprints = [doc.get("description", "") for doc in documents]
        cache_bypassed = self.use_cache and self.cache.is_rerank_cache_bypassed(query)

        # 检查缓存
        if self.use_cache and not cache_bypassed:
            cached = self.cache.get_rerank(query, doc_ids, doc_fingerprints=doc_fingerprints)
            if cached is not None:
                rerank_logger.debug("[Rerank] 使用缓存, query={}, doc_ids={}", query[:50], len(doc_ids))
                return cached

        # 调用 API
        try:
            # 构建文档文本
            candidate_limit = self.calculate_candidate_limit(len(documents), len(documents))
            doc_texts = [
                doc.get("description", "")
                for doc in documents[:candidate_limit]
            ]

            response = await self.client.post(
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
            if self.use_cache and not cache_bypassed:
                self.cache.set_rerank(
                    query,
                    doc_ids[:candidate_limit],
                    rerank_results,
                    doc_fingerprints=doc_fingerprints[:candidate_limit],
                    request_id=request_id
                )
            elif cache_bypassed:
                rerank_logger.info("[Rerank] 跳过缓存写入, query={}", query[:50])

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
