"""
RAG 删除路由

负责从 Milvus、ES 和内存图索引删除文档。

@author lvdaxianerplus
@date 2026-06-01
"""

import httpx
from fastapi import APIRouter, HTTPException, status

from app.config import Config
from app.models.schemas import DeleteRequest, DeleteResponse
from app.services.es_service import get_es_service
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.milvus_service import MilvusService
from app.utils.logger import rag_delete_logger


router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])
_milvus_service = None


def get_milvus_service() -> MilvusService:
    """获取 Milvus 服务实例"""
    global _milvus_service
    if _milvus_service is None:
        _milvus_service = MilvusService()
    return _milvus_service


@router.delete("/{id}/delete", response_model=DeleteResponse)
async def delete(id: str, request: DeleteRequest):
    """
    删除记录接口

    @param id - 用户ID，用于日志追踪
    @param request - 删除请求
    @returns 删除结果
    """
    rag_delete_logger.info("[RAG删除] 开始删除, userId={}, type={}, id={}", id, request.type, request.id)
    try:
        milvus_service = get_milvus_service()
        success = await milvus_service.delete(collection=request.type, doc_id=request.id)
        await _delete_from_es(request)
        if success:
            _delete_from_graph(request.id)
            return DeleteResponse(code=200, message="success", data=None)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 2002, "message": "记录不存在"}
        )
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        rag_delete_logger.error("[RAG删除] HTTP 服务调用失败, error={}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 500, "message": "删除失败"}
        ) from e
    except Exception as e:
        rag_delete_logger.error("[RAG删除] 删除失败, error={}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 500, "message": "删除失败"}
        ) from e


@router.post("/{id}/delete", response_model=DeleteResponse)
async def delete_via_post(id: str, request: DeleteRequest):
    """
    通过POST方式删除记录

    @param id - 用户ID，用于日志追踪
    @param request - 删除请求
    @returns 删除结果
    """
    return await delete(id, request)


async def _delete_from_es(request: DeleteRequest) -> None:
    """删除 ES 副本，失败时降级"""
    try:
        es_service = get_es_service()
        es_index = Config.ES_SKILL_INDEX if request.type == "skill" else Config.ES_ASSET_INDEX
        await es_service.delete_document(es_index, request.id)
        rag_delete_logger.info("[RAG删除] ES 删除成功, id={}", request.id)
    except Exception as es_error:
        rag_delete_logger.warning("[RAG删除] ES 删除失败（降级）, id={}, error={}", request.id, str(es_error))


def _delete_from_graph(doc_id: str) -> None:
    """删除内存图索引副本，失败时降级"""
    try:
        get_graph_retrieval_service().delete_document(doc_id)
        rag_delete_logger.info("[RAG删除] 图索引删除成功, id={}", doc_id)
    except Exception as graph_error:
        rag_delete_logger.warning("[RAG删除] 图索引删除失败（降级）, id={}, error={}", doc_id, str(graph_error))
