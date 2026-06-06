"""
Embedding 服务模块

调用 qwen3 API 生成向量，支持缓存

@author lvdaxianerplus
@date 2026-04-14
"""

import httpx
from typing import List, Union
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

    async def encode(self, texts: Union[str, List[str]]) -> List[float]:
        """
        将文本转换为向量（支持缓存）

        @param texts - 单个文本或文本列表
        @returns 向量列表
        """
        is_single_text = isinstance(texts, str)
        if is_single_text:
            texts = [texts]
        if not texts or any(not text or not text.strip() for text in texts):
            raise ValueError("文本不能为空")

        # 单文本查询优先检查缓存
        if self.use_cache and len(texts) == 1:
            cached = self.cache.get_embedding(texts[0])
            if cached is not None:
                embedding_logger.debug("[Embedding] 使用缓存, query={}", texts[0][:50])
                return cached

        # 调用 API
        try:
            response = await self.client.post(
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

            embeddings = [item["embedding"] for item in result["data"]]
            first_embedding = embeddings[0] if embeddings else []
            embedding_logger.info("[Embedding] 向量化完成, 向量维度={}", len(first_embedding))

            # 缓存单文本结果
            if self.use_cache and len(texts) == 1:
                self.cache.set_embedding(texts[0], first_embedding)

            return first_embedding if is_single_text else embeddings

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
