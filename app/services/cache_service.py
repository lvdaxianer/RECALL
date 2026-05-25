"""
缓存服务模块

提供内存缓存，支持 Redis（可选）

@author lvdaxianerplus
@date 2026-04-16
"""

import hashlib
import json
from typing import Optional, Any, List, Dict
from cachetools import TTLCache
from app.config import Config
from app.utils.logger import rag_search_logger


class CacheService:
    """
    缓存服务类

    支持内存缓存，Redis 作为可选扩展（当前实现为纯内存缓存）
    """

    def __init__(self):
        """
        初始化缓存服务
        """
        # Query Embedding 缓存
        self._embedding_cache: TTLCache = TTLCache(
            maxsize=Config.EMBEDDING_CACHE_MAX_SIZE,
            ttl=Config.EMBEDDING_CACHE_TTL
        )

        # Rerank 结果缓存
        self._rerank_cache: TTLCache = TTLCache(
            maxsize=Config.RERANK_CACHE_MAX_SIZE,
            ttl=Config.RERANK_CACHE_TTL
        )

        rag_search_logger.info(
            "[缓存] 初始化完成, embedding_ttl={}s, rerank_ttl={}s",
            Config.EMBEDDING_CACHE_TTL,
            Config.RERANK_CACHE_TTL
        )

    @staticmethod
    def _normalize_query(query: str) -> str:
        """
        归一化查询文本

        @param query - 原始查询
        @returns 归一化后的查询
        """
        return query.strip().lower()

    @staticmethod
    def _generate_cache_key(*parts: str) -> str:
        """
        生成缓存 key

        @param parts - key 的各个部分
        @returns MD5 hash 作为 key
        """
        combined = "|".join(parts)
        return hashlib.md5(combined.encode()).hexdigest()

    # -------------------------------------------------------------------------
    # Query Embedding 缓存
    # -------------------------------------------------------------------------

    def get_embedding(self, query: str) -> Optional[List[float]]:
        """
        获取缓存的 query embedding

        @param query - 查询文本
        @returns 缓存的向量，如果未命中返回 None
        """
        normalized = self._normalize_query(query)
        cache_key = self._generate_cache_key("embed", normalized)

        cached = self._embedding_cache.get(cache_key)
        if cached is not None:
            rag_search_logger.debug(f"[缓存] Embedding 命中: key={cache_key[:8]}...")
            return cached
        else:
            rag_search_logger.debug(f"[缓存] Embedding 未命中: key={cache_key[:8]}...")
            return None

    def set_embedding(self, query: str, embedding: List[float]) -> None:
        """
        缓存 query embedding

        @param query - 查询文本
        @param embedding - 向量
        """
        normalized = self._normalize_query(query)
        cache_key = self._generate_cache_key("embed", normalized)
        self._embedding_cache[cache_key] = embedding
        rag_search_logger.debug(f"[缓存] Embedding 已缓存: key={cache_key[:8]}..., size={len(embedding)}")

    # -------------------------------------------------------------------------
    # Rerank 结果缓存
    # -------------------------------------------------------------------------

    def get_rerank(self, query: str, doc_ids: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的 Rerank 结果

        @param query - 查询文本
        @param doc_ids - 文档 ID 列表（排序后的）
        @returns 缓存的重排结果，如果未命中返回 None
        """
        normalized = self._normalize_query(query)
        doc_ids_str = "|".join(sorted(doc_ids))
        cache_key = self._generate_cache_key("rerank", normalized, doc_ids_str)

        cached = self._rerank_cache.get(cache_key)
        if cached is not None:
            rag_search_logger.debug(f"[缓存] Rerank 命中: key={cache_key[:8]}...")
            return cached
        else:
            rag_search_logger.debug(f"[缓存] Rerank 未命中: key={cache_key[:8]}...")
            return None

    def set_rerank(
        self,
        query: str,
        doc_ids: List[str],
        results: List[Dict[str, Any]]
    ) -> None:
        """
        缓存 Rerank 结果

        @param query - 查询文本
        @param doc_ids - 文档 ID 列表
        @param results - 重排结果
        """
        normalized = self._normalize_query(query)
        doc_ids_str = "|".join(sorted(doc_ids))
        cache_key = self._generate_cache_key("rerank", normalized, doc_ids_str)
        self._rerank_cache[cache_key] = results
        rag_search_logger.debug(f"[缓存] Rerank 已缓存: key={cache_key[:8]}..., count={len(results)}")

    # -------------------------------------------------------------------------
    # 缓存管理
    # -------------------------------------------------------------------------

    def clear_embedding_cache(self) -> int:
        """
        清空 Embedding 缓存

        @returns 清空的条目数
        """
        count = len(self._embedding_cache)
        self._embedding_cache.clear()
        rag_search_logger.info(f"[缓存] Embedding 缓存已清空, 条目数={count}")
        return count

    def clear_rerank_cache(self) -> int:
        """
        清空 Rerank 缓存

        @returns 清空的条目数
        """
        count = len(self._rerank_cache)
        self._rerank_cache.clear()
        rag_search_logger.info(f"[缓存] Rerank 缓存已清空, 条目数={count}")
        return count

    def clear_all(self) -> Dict[str, int]:
        """
        清空所有缓存

        @returns 清空统计
        """
        embed_count = self.clear_embedding_cache()
        rerank_count = self.clear_rerank_cache()
        return {
            "embedding_cache_cleared": embed_count,
            "rerank_cache_cleared": rerank_count
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        @returns 缓存统计
        """
        return {
            "embedding_cache": {
                "size": len(self._embedding_cache),
                "max_size": Config.EMBEDDING_CACHE_MAX_SIZE,
                "ttl": Config.EMBEDDING_CACHE_TTL
            },
            "rerank_cache": {
                "size": len(self._rerank_cache),
                "max_size": Config.RERANK_CACHE_MAX_SIZE,
                "ttl": Config.RERANK_CACHE_TTL
            }
        }


# 全局单例
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """
    获取缓存服务单例

    @returns CacheService 实例
    """
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service