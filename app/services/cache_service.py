"""
缓存服务模块

提供内存缓存，支持 Redis（可选）

@author lvdaxianerplus
@date 2026-04-16
"""

import hashlib
from typing import Optional, Any, List, Dict
from cachetools import TTLCache
from app.config import Config
from app.services.query_normalization import normalize_query_text
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
        self._rerank_bypass_queries: TTLCache = TTLCache(
            maxsize=Config.RERANK_CACHE_MAX_SIZE,
            ttl=Config.RERANK_CACHE_TTL
        )
        self._rerank_request_lineage: TTLCache = TTLCache(
            maxsize=Config.RERANK_CACHE_MAX_SIZE,
            ttl=Config.RERANK_CACHE_TTL
        )
        self._embedding_stats = self._new_stats()
        self._rerank_stats = self._new_stats()
        self._rerank_bypass_count = 0

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
        return normalize_query_text(query)

    @staticmethod
    def _generate_cache_key(*parts: str) -> str:
        """
        生成缓存 key

        @param parts - key 的各个部分
        @returns MD5 hash 作为 key
        """
        combined = "|".join(parts)
        return hashlib.md5(combined.encode()).hexdigest()

    @staticmethod
    def _new_stats() -> Dict[str, int]:
        """创建缓存计数器。"""
        return {"hits": 0, "misses": 0, "sets": 0}

    @staticmethod
    def _stats_snapshot(stats: Dict[str, int]) -> Dict[str, Any]:
        """输出缓存计数器快照。"""
        hits = stats["hits"]
        misses = stats["misses"]
        total_reads = hits + misses
        return {
            "hits": hits,
            "misses": misses,
            "sets": stats["sets"],
            "hit_rate": round(hits / total_reads, 4) if total_reads else 0.0,
        }

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
            self._embedding_stats["hits"] += 1
            rag_search_logger.debug(f"[缓存] Embedding 命中: key={cache_key[:8]}...")
            return cached
        else:
            self._embedding_stats["misses"] += 1
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
        self._embedding_stats["sets"] += 1
        rag_search_logger.debug(f"[缓存] Embedding 已缓存: key={cache_key[:8]}..., size={len(embedding)}")

    # -------------------------------------------------------------------------
    # Rerank 结果缓存
    # -------------------------------------------------------------------------

    def get_rerank(
        self,
        query: str,
        doc_ids: List[str],
        doc_fingerprints: Optional[List[str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的 Rerank 结果

        @param query - 查询文本
        @param doc_ids - 文档 ID 列表（按候选顺序）
        @param doc_fingerprints - 文档内容指纹列表（按候选顺序）
        @returns 缓存的重排结果，如果未命中返回 None
        """
        normalized = self._normalize_query(query)
        if self.is_rerank_cache_bypassed(query):
            self._rerank_bypass_count += 1
            rag_search_logger.info("[缓存] Rerank 缓存已绕过, query='{}'", query[:80])
            return None
        cache_key = self._build_rerank_cache_key(normalized, doc_ids, doc_fingerprints)

        cached = self._rerank_cache.get(cache_key)
        if cached is not None:
            self._rerank_stats["hits"] += 1
            rag_search_logger.debug(f"[缓存] Rerank 命中: key={cache_key[:8]}...")
            return cached
        else:
            self._rerank_stats["misses"] += 1
            rag_search_logger.debug(f"[缓存] Rerank 未命中: key={cache_key[:8]}...")
            return None

    def set_rerank(
        self,
        query: str,
        doc_ids: List[str],
        results: List[Dict[str, Any]],
        doc_fingerprints: Optional[List[str]] = None,
        request_id: Optional[str] = None
    ) -> None:
        """
        缓存 Rerank 结果

        @param query - 查询文本
        @param doc_ids - 文档 ID 列表
        @param results - 重排结果
        @param doc_fingerprints - 文档内容指纹列表（按候选顺序）
        """
        normalized = self._normalize_query(query)
        if self.is_rerank_cache_bypassed(query):
            self._rerank_bypass_count += 1
            rag_search_logger.info("[缓存] Rerank 缓存写入已绕过, query='{}'", query[:80])
            return
        cache_key = self._build_rerank_cache_key(normalized, doc_ids, doc_fingerprints)
        self._rerank_cache[cache_key] = results
        if request_id:
            self._record_rerank_lineage(request_id, cache_key, query)
        self._rerank_stats["sets"] += 1
        rag_search_logger.debug(f"[缓存] Rerank 已缓存: key={cache_key[:8]}..., count={len(results)}")

    def _build_rerank_cache_key(
        self,
        normalized_query: str,
        doc_ids: List[str],
        doc_fingerprints: Optional[List[str]] = None
    ) -> str:
        """构造顺序敏感、内容敏感的 Rerank 缓存 key。"""
        doc_ids_str = "|".join(doc_ids)
        fingerprints_str = "|".join(doc_fingerprints or [])
        return self._generate_cache_key("rerank", normalized_query, doc_ids_str, fingerprints_str)

    def bypass_rerank_cache(self, query: str, reason: str = "") -> None:
        """
        暂停某个 query 的 Rerank 缓存读写。

        用于用户反馈 bad case 后，避免旧排序结果被反复命中。
        """
        normalized = self._normalize_query(query)
        if not normalized:
            return
        cache_key = self._generate_cache_key("rerank_bypass", normalized)
        self._rerank_bypass_queries[cache_key] = {
            "query": normalized,
            "reason": reason
        }
        rag_search_logger.info("[缓存] Rerank 缓存绕过已登记, query='{}', reason={}", query[:80], reason)

    def is_rerank_cache_bypassed(self, query: str) -> bool:
        """判断某个 query 是否处于 Rerank 缓存绕过窗口。"""
        normalized = self._normalize_query(query)
        if not normalized:
            return False
        cache_key = self._generate_cache_key("rerank_bypass", normalized)
        return cache_key in self._rerank_bypass_queries

    def invalidate_rerank_by_request_id(self, request_id: str) -> Dict[str, Any]:
        """按 request_id 删除关联的 Rerank 缓存并建立 query 绕过。"""
        lineage_items = list(self._rerank_request_lineage.get(request_id, []))
        invalidated = 0
        bypassed_queries = set()
        for item in lineage_items:
            cache_key = item.get("cache_key")
            query = item.get("query", "")
            if cache_key in self._rerank_cache:
                del self._rerank_cache[cache_key]
                invalidated += 1
            if query:
                self.bypass_rerank_cache(query, reason=f"request_invalidate:{request_id}")
                bypassed_queries.add(self._normalize_query(query))

        self._rerank_request_lineage.pop(request_id, None)
        return {
            "request_id": request_id,
            "invalidated": invalidated,
            "bypassed_queries": len(bypassed_queries),
        }

    def _record_rerank_lineage(self, request_id: str, cache_key: str, query: str) -> None:
        """记录 request_id 与 Rerank 缓存 key 的血缘关系。"""
        lineage_items = list(self._rerank_request_lineage.get(request_id, []))
        lineage_items.append({
            "cache_key": cache_key,
            "query": query
        })
        self._rerank_request_lineage[request_id] = lineage_items

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
        self._embedding_stats = self._new_stats()
        rag_search_logger.info(f"[缓存] Embedding 缓存已清空, 条目数={count}")
        return count

    def clear_rerank_cache(self) -> int:
        """
        清空 Rerank 缓存

        @returns 清空的条目数
        """
        count = len(self._rerank_cache)
        self._rerank_cache.clear()
        self._rerank_bypass_queries.clear()
        self._rerank_request_lineage.clear()
        self._rerank_stats = self._new_stats()
        self._rerank_bypass_count = 0
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
                "ttl": Config.EMBEDDING_CACHE_TTL,
                **self._stats_snapshot(self._embedding_stats),
            },
            "rerank_cache": {
                "size": len(self._rerank_cache),
                "max_size": Config.RERANK_CACHE_MAX_SIZE,
                "ttl": Config.RERANK_CACHE_TTL,
                "bypassed_queries": len(self._rerank_bypass_queries),
                "bypasses": self._rerank_bypass_count,
                "lineage_size": len(self._rerank_request_lineage),
                **self._stats_snapshot(self._rerank_stats),
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
