"""
RAG 缓存管理路由

提供缓存统计与手动清理接口。

@author lvdaxianerplus
@date 2026-06-01
"""

from fastapi import APIRouter

from app.models.schemas import APIResponse
from app.services.cache_service import get_cache_service
from app.utils.logger import rag_search_logger


router = APIRouter(prefix="/api/v1/rag/cache", tags=["RAG"])


@router.post("/reset", response_model=APIResponse)
async def reset_cache():
    """
    重置所有缓存

    @returns 重置结果
    """
    cache_service = get_cache_service()
    result = cache_service.clear_all()
    rag_search_logger.info("[缓存] 手动重置缓存, result={}", result)
    return APIResponse(code=200, message="缓存已重置", data=result)


@router.get("/stats", response_model=APIResponse)
async def get_cache_stats():
    """
    获取缓存统计信息

    @returns 缓存统计
    """
    cache_service = get_cache_service()
    stats = cache_service.get_stats()
    return APIResponse(code=200, message="success", data=stats)


@router.post("/rerank/invalidate-by-request/{request_id}", response_model=APIResponse)
async def invalidate_rerank_cache_by_request(request_id: str):
    """
    按 request_id 撤销关联的 Rerank 缓存

    @param request_id - 优化检索响应中的 request_id
    @returns 撤销统计
    """
    cache_service = get_cache_service()
    result = cache_service.invalidate_rerank_by_request_id(request_id)
    rag_search_logger.info("[缓存] 按 request_id 撤销 Rerank 缓存, result={}", result)
    return APIResponse(code=200, message="Rerank 缓存已撤销", data=result)
