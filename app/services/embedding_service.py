"""
Embedding 服务模块

调用 qwen3 API 生成向量，支持缓存

@author lvdaxianerplus
@date 2026-04-14
"""

import httpx
from typing import List, Union, Optional
from app.config import Config
from app.utils.logger import embedding_logger
from app.services.cache_service import get_cache_service


class EmbeddingService:
    """Embedding 服务类"""

    def __init__(
        self,
        api_key: str = None,
        request_url: str = None,
        model_name: str = None,
        dimension: int = None,
        use_cache: bool = True
    ):
        """
        初始化 Embedding 服务

        @param api_key - API 密钥
        @param request_url - 请求 URL
        @param model_name - 模型名称
        @param dimension - 向量维度
        @param use_cache - 是否使用缓存
        """
        self.api_key = api_key or Config.EMBEDDING_MODEL_API_KEY
        self.request_url = request_url or Config.EMBEDDING_REQUEST_URL
        self.model_name = model_name or Config.EMBEDDING_MODEL_NAME
        self.dimension = dimension or Config.EMBEDDING_DIMENSION
        self.use_cache = use_cache
        self._cache = None  # 懒加载

    @property
    def cache(self):
        """懒加载缓存服务"""
        if self._cache is None:
            self._cache = get_cache_service()
        return self._cache

    async def encode(self, texts: Union[str, List[str]]) -> List[float]:
        """
        将文本转换为向量（支持缓存）

        @param texts - 单个文本或文本列表
        @returns 向量列表
        """
        if isinstance(texts, str):
            texts = [texts]

        # 单文本查询优先检查缓存
        if self.use_cache and len(texts) == 1:
            cached = self.cache.get_embedding(texts[0])
            if cached is not None:
                embedding_logger.debug("[Embedding] 使用缓存, query={}", texts[0][:50])
                return cached

        # 调用 API
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.request_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model_name,
                        "input": texts,
                        "dimensions": self.dimension  # 指定返回维度
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()

                embeddings = result["data"][0]["embedding"]
                embedding_logger.info("[Embedding] 向量化完成, 向量维度={}", len(embeddings))

                # 缓存单文本结果
                if self.use_cache and len(texts) == 1:
                    self.cache.set_embedding(texts[0], embeddings)

                return embeddings

        except httpx.HTTPError as e:
            embedding_logger.error("[Embedding] HTTP 错误, error={}", str(e))
            raise
        except Exception as e:
            embedding_logger.error("[Embedding] 向量化失败, error={}", str(e))
            raise

    async def health_check(self) -> bool:
        """
        健康检查

        @returns 服务是否可用
        """
        try:
            await self.encode("health check")
            return True
        except Exception as e:
            embedding_logger.error("[Embedding] 健康检查失败, error={}", str(e))
            return False
