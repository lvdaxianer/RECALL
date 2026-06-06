"""
RAG 检索路由模块

定义 RAG 搜索接口路由。

@author lvdaxianerplus
@date 2026-04-14
"""

from fastapi import APIRouter

from app.models.schemas import SearchRequest, SearchResponse
from app.services.rag_search_pipeline_service import run_search_pipeline


router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


@router.post("/{id}/search", response_model=SearchResponse)
async def search(id: str, request: SearchRequest):
    """
    混合检索接口（RRF + 向量 + BM25）

    @param id - 用户ID，用于日志追踪
    @param request - 检索请求
    @returns 检索结果

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    search_results = await run_search_pipeline(id, request)
    return SearchResponse(
        code=200,
        message="success",
        data=search_results
    )
