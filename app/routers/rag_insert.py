"""
RAG 插入路由

负责单条和批量插入，并维护 Milvus、ES、图索引和重试队列。

@author lvdaxianerplus
@date 2026-06-01
"""

import httpx
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from app.config import Config
from app.models.schemas import APIResponse, BatchInsertRequest, InsertRequest
from app.services.embedding_service import EmbeddingService
from app.services.entity_relation_service import get_entity_relation_service
from app.services.es_service import get_es_service
from app.services.feature_extract_service import get_feature_extract_service
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.milvus_service import MilvusService
from app.services.retry_queue import get_retry_queue
from app.utils.logger import rag_insert_logger


router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])
_embedding_service = None
_milvus_service = None


def get_embedding_service() -> EmbeddingService:
    """获取 Embedding 服务实例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def get_milvus_service() -> MilvusService:
    """获取 Milvus 服务实例"""
    global _milvus_service
    if _milvus_service is None:
        _milvus_service = MilvusService()
    return _milvus_service


@router.post("/{id}/insert", response_model=APIResponse)
async def insert(id: str, request: InsertRequest):
    """
    单条插入接口

    @param id - 用户ID，用于日志追踪
    @param request - 插入请求
    @returns 插入结果
    """
    rag_insert_logger.info(
        "[RAG插入] 开始插入, userId={}, type={}, docId={}",
        id,
        request.metadata.type,
        request.metadata.id
    )
    try:
        features, vector = await _build_single_insert_payload(request)
        result = await _insert_to_milvus(request, vector, features)
        _index_graph_document(request, features)
        await _index_es_document(request, features, id)
        rag_insert_logger.info("[RAG插入] 插入成功, userId={}, docId={}", id, result["id"])
        return APIResponse(
            code=200,
            message="success",
            data={"id": result["id"], "collection": result["collection"], "features": features}
        )
    except httpx.HTTPError as e:
        rag_insert_logger.error("[RAG插入] HTTP 服务调用失败, userId={}, docId={}, error={}", id, request.metadata.id, str(e))
        return _handle_insert_failure(id, request, "HTTP 服务调用失败")
    except Exception as e:
        rag_insert_logger.error("[RAG插入] 插入失败, userId={}, docId={}, error={}", id, request.metadata.id, str(e))
        return _handle_insert_failure(id, request, "插入失败")


@router.post("/{id}/insert/batch", response_model=APIResponse)
async def batch_insert(id: str, request: BatchInsertRequest):
    """
    批量插入接口

    @param id - 用户ID，用于日志追踪
    @param request - 批量插入请求
    @returns 插入结果
    """
    rag_insert_logger.info("[RAG插入] 开始批量插入, userId={}, 数量={}", id, len(request.items))
    try:
        _validate_batch_types(id, request)
        documents, features_list = await _build_batch_documents(request)
        milvus_service = get_milvus_service()
        result = await milvus_service.batch_insert(
            collection=request.items[0].metadata.type,
            documents=documents
        )
        get_graph_retrieval_service().index_documents(documents)
        await _index_es_documents(request, features_list, id)
        return APIResponse(code=200, message="success", data={"inserted_count": result["inserted_count"]})
    except httpx.HTTPError as e:
        rag_insert_logger.error("[RAG插入] HTTP 服务调用失败, error={}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 1002, "message": "Embedding 服务不可用"}
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        rag_insert_logger.error("[RAG插入] 批量插入失败, error={}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 1002, "message": "Embedding 服务不可用"}
        ) from e


async def _build_single_insert_payload(request: InsertRequest) -> tuple[Dict[str, Any], list[float]]:
    """构建单条插入的特征和向量"""
    vector = await get_embedding_service().encode(request.description)
    features = await get_feature_extract_service().extract_features(request.description)
    entity_relations = await get_entity_relation_service().extract(request.description)
    return _merge_entity_relations(features, entity_relations), vector


async def _insert_to_milvus(request: InsertRequest, vector: list[float], features: Dict[str, Any]) -> Dict[str, Any]:
    """写入 Milvus"""
    milvus_service = get_milvus_service()
    return await milvus_service.insert(
        collection=request.metadata.type,
        doc_id=request.metadata.id,
        description=request.description,
        vector=vector,
        metadata=request.metadata.model_dump(),
        features=features
    )


def _index_graph_document(request: InsertRequest, features: Dict[str, Any]) -> None:
    """写入内存图索引"""
    get_graph_retrieval_service().index_document(
        doc_id=request.metadata.id,
        description=request.description,
        metadata=request.metadata.model_dump(),
        features=features
    )


async def _index_es_document(request: InsertRequest, features: Dict[str, Any], user_id: str) -> None:
    """写入 ES 副本，失败时降级"""
    try:
        es_service = get_es_service()
        es_index = Config.ES_SKILL_INDEX if request.metadata.type == "skill" else Config.ES_ASSET_INDEX
        await es_service.index_document(
            index_name=es_index,
            doc_id=request.metadata.id,
            description=request.description,
            metadata=request.metadata.model_dump(),
            features=features
        )
        rag_insert_logger.info("[RAG插入] ES 索引成功, userId={}, docId={}", user_id, request.metadata.id)
    except Exception as es_error:
        rag_insert_logger.warning("[RAG插入] ES 索引失败（降级）, userId={}, docId={}, error={}", user_id, request.metadata.id, str(es_error))


def _handle_insert_failure(user_id: str, request: InsertRequest, reason: str) -> APIResponse:
    """处理插入失败，将任务加入重试队列"""
    task_id = f"{user_id}_{request.metadata.id}_{int(uuid.uuid4().hex[:8], 16)}"
    retry_queue = get_retry_queue()
    retry_queue.add_task(
        task_id=task_id,
        user_id=user_id,
        description=request.description,
        metadata=request.metadata.model_dump()
    )
    rag_insert_logger.info("[RAG插入] 已加入重试队列, userId={}, taskId={}", user_id, task_id)
    return APIResponse(
        code=202,
        message="pending_retry",
        data={
            "id": request.metadata.id,
            "task_id": task_id,
            "status": "pending_retry",
            "reason": reason,
            "retry_count": 0,
            "max_retries": 3
        }
    )


def _merge_entity_relations(features: Dict[str, Any], entity_relations: Dict[str, Any]) -> Dict[str, Any]:
    """将实体关系合并到基础特征中"""
    merged = dict(features or {})
    merged["entities"] = entity_relations.get("entities", []) if entity_relations else []
    merged["relations"] = entity_relations.get("relations", []) if entity_relations else []
    return merged


def _validate_batch_types(user_id: str, request: BatchInsertRequest) -> None:
    """校验批量插入不混合资源类型"""
    item_types = {item.metadata.type for item in request.items}
    if len(item_types) > 1:
        rag_insert_logger.warning("[RAG插入] 批量插入类型不一致, userId={}, types={}", user_id, sorted(item_types))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 1003, "message": "批量插入不支持混合资源类型"}
        )


async def _build_batch_documents(request: BatchInsertRequest) -> tuple[list[dict], list[dict]]:
    """构建批量插入文档和特征列表"""
    descriptions = [item.description for item in request.items]
    vectors = await get_embedding_service().encode(descriptions)
    features_list = await get_feature_extract_service().extract_features_batch(descriptions)
    entity_relations_list = await get_entity_relation_service().extract_batch(descriptions)
    features_list = [
        _merge_entity_relations(features, entity_relations_list[i])
        for i, features in enumerate(features_list)
    ]
    documents = [
        {
            "id": item.metadata.id,
            "description": item.description,
            "vector": vectors[i] if isinstance(vectors[0], list) else vectors,
            "metadata": item.metadata.model_dump(),
            "features": features_list[i]
        }
        for i, item in enumerate(request.items)
    ]
    return documents, features_list


async def _index_es_documents(request: BatchInsertRequest, features_list: list[dict], user_id: str) -> None:
    """批量写入 ES 副本，失败时降级"""
    try:
        es_service = get_es_service()
        es_index = Config.ES_SKILL_INDEX if request.items[0].metadata.type == "skill" else Config.ES_ASSET_INDEX
        await es_service.index_documents(
            index_name=es_index,
            documents=[
                {
                    "doc_id": item.metadata.id,
                    "description": item.description,
                    "metadata": item.metadata.model_dump(),
                    "features": features_list[i]
                }
                for i, item in enumerate(request.items)
            ]
        )
        rag_insert_logger.info("[RAG插入] ES 批量索引成功, userId={}, count={}", user_id, len(request.items))
    except Exception as es_error:
        rag_insert_logger.warning("[RAG插入] ES 批量索引失败（降级）, userId={}, error={}", user_id, str(es_error))
