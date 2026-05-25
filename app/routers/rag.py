"""
RAG 路由模块

定义 RAG 接口路由

@author lvdaxianerplus
@date 2026-04-14
"""

from fastapi import APIRouter, HTTPException, status
from typing import List, Union, Dict, Any, Optional
import asyncio
import httpx
import uuid
from app.models.schemas import (
    InsertRequest,
    InsertResponse,
    BatchInsertRequest,
    BatchInsertResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    DeleteRequest,
    DeleteResponse,
    APIResponse
)
from app.services.embedding_service import EmbeddingService
from app.services.rerank_service import RerankService
from app.services.milvus_service import MilvusService
from app.services.es_service import get_es_service
from app.services.hybrid_search import rrf_fusion, normalize_final_scores
from app.services.retry_queue import get_retry_queue
from app.services.feature_extract_service import get_feature_extract_service
from app.services.feature_boost_service import get_feature_boost_service
from app.config import Config
from app.utils.logger import (
    rag_insert_logger,
    rag_search_logger,
    rag_delete_logger
)

# 创建路由
router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])

# 服务实例（懒加载）
_embedding_service = None
_rerank_service = None
_milvus_service = None


def get_embedding_service() -> EmbeddingService:
    """获取 Embedding 服务实例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def get_rerank_service() -> RerankService:
    """获取 Rerank 服务实例"""
    global _rerank_service
    if _rerank_service is None:
        _rerank_service = RerankService()
    return _rerank_service


def get_milvus_service() -> MilvusService:
    """获取 Milvus 服务实例"""
    global _milvus_service
    if _milvus_service is None:
        _milvus_service = MilvusService()
    return _milvus_service


# =============================================================================
# 插入接口
# =============================================================================

@router.post("/{id}/insert", response_model=APIResponse)
async def insert(id: str, request: InsertRequest):
    """
    单条插入接口

    插入失败时自动加入重试队列

    @param id - 用户ID，用于日志追踪
    @param request - 插入请求
    @returns 插入结果

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    rag_insert_logger.info("[RAG插入] 开始插入, userId={}, type={}, docId={}",
                          id, request.metadata.type, request.metadata.id)

    try:
        # Step 1: 获取向量
        embedding_service = get_embedding_service()
        vector = await embedding_service.encode(request.description)

        # Step 2: 提取特征（同步调用 LLM）
        feature_extract_service = get_feature_extract_service()
        features = await feature_extract_service.extract_features(request.description)
        rag_insert_logger.info("[RAG插入] 特征提取完成, userId={}, docId={}, category={}",
                              id, request.metadata.id, features.get("category"))

        # Step 3: 插入 Milvus
        milvus_service = get_milvus_service()
        result = await milvus_service.insert(
            collection=request.metadata.type,
            doc_id=request.metadata.id,
            description=request.description,
            vector=vector,
            metadata=request.metadata.model_dump(),
            features=features
        )

        # Step 4: 双写 ES（降级：ES 失败不影响主流程）
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
            rag_insert_logger.info("[RAG插入] ES 索引成功, userId={}, docId={}", id, request.metadata.id)
        except Exception as es_error:
            rag_insert_logger.warning("[RAG插入] ES 索引失败（降级）, userId={}, docId={}, error={}",
                                   id, request.metadata.id, str(es_error))

        rag_insert_logger.info("[RAG插入] 插入成功, userId={}, docId={}", id, result["id"])

        return APIResponse(
            code=200,
            message="success",
            data={
                "id": result["id"],
                "collection": result["collection"],
                "features": features
            }
        )

    except httpx.HTTPError as e:
        # Embedding 或 Milvus HTTP 调用失败，加入重试队列
        rag_insert_logger.error("[RAG插入] HTTP 服务调用失败, userId={}, docId={}, error={}",
                              id, request.metadata.id, str(e))
        return _handle_insert_failure(
            id, request, str(e), "HTTP 服务调用失败"
        )
    except Exception as e:
        # 其他未知异常，加入重试队列
        rag_insert_logger.error("[RAG插入] 插入失败, userId={}, docId={}, error={}",
                              id, request.metadata.id, str(e))
        return _handle_insert_failure(
            id, request, str(e), "插入失败"
        )


def _handle_insert_failure(
    user_id: str,
    request: InsertRequest,
    error_message: str,
    reason: str
) -> APIResponse:
    """
    处理插入失败，将任务加入重试队列

    @param user_id - 用户ID
    @param request - 插入请求
    @param error_message - 错误信息
    @param reason - 失败原因
    @returns 带有重试任务信息的响应
    """
    # 生成任务ID
    task_id = f"{user_id}_{request.metadata.id}_{int(uuid.uuid4().hex[:8], 16)}"

    # 添加到重试队列
    retry_queue = get_retry_queue()
    retry_queue.add_task(
        task_id=task_id,
        user_id=user_id,
        description=request.description,
        metadata=request.metadata.model_dump()
    )

    rag_insert_logger.info("[RAG插入] 已加入重试队列, userId={}, taskId={}", user_id, task_id)

    return APIResponse(
        code=202,  # Accepted - 请求已接受但处理中
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


@router.post("/{id}/insert/batch", response_model=APIResponse)
async def batch_insert(id: str, request: BatchInsertRequest):
    """
    批量插入接口

    @param id - 用户ID，用于日志追踪
    @param request - 批量插入请求
    @returns 插入结果

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    rag_insert_logger.info("[RAG插入] 开始批量插入, userId={}, 数量={}", id, len(request.items))

    try:
        # 批量获取向量
        embedding_service = get_embedding_service()
        descriptions = [item.description for item in request.items]
        vectors = await embedding_service.encode(descriptions)

        # 批量提取特征（LLM 调用）
        feature_extract_service = get_feature_extract_service()
        features_list = []
        for desc in descriptions:
            features = await feature_extract_service.extract_features(desc)
            features_list.append(features)

        # 构建文档（使用列表推导式批量处理）
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

        # 批量插入
        milvus_service = get_milvus_service()
        result = await milvus_service.batch_insert(
            collection=request.items[0].metadata.type,
            documents=documents
        )

        # 双写 ES（降级：ES 失败不影响主流程）
        try:
            es_service = get_es_service()
            es_index = Config.ES_SKILL_INDEX if request.items[0].metadata.type == "skill" else Config.ES_ASSET_INDEX
            for i, item in enumerate(request.items):
                await es_service.index_document(
                    index_name=es_index,
                    doc_id=item.metadata.id,
                    description=item.description,
                    metadata=item.metadata.model_dump(),
                    features=features_list[i]
                )
            rag_insert_logger.info("[RAG插入] ES 批量索引成功, userId={}, count={}", id, len(request.items))
        except Exception as es_error:
            rag_insert_logger.warning("[RAG插入] ES 批量索引失败（降级）, userId={}, error={}",
                                   id, str(es_error))

        rag_insert_logger.info("[RAG插入] 批量插入成功, userId={}, inserted_count={}", id, result["inserted_count"])

        return APIResponse(
            code=200,
            message="success",
            data={
                "inserted_count": result["inserted_count"]
            }
        )

    except httpx.HTTPError as e:
        # Embedding 或 Milvus HTTP 调用失败
        rag_insert_logger.error("[RAG插入] HTTP 服务调用失败, error={}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 1002, "message": "Embedding 服务不可用"}
        ) from e
    except Exception as e:
        # 其他未知异常
        rag_insert_logger.error("[RAG插入] 批量插入失败, error={}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 1002, "message": "Embedding 服务不可用"}
        ) from e


# =============================================================================
# 检索接口
# =============================================================================

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
    rag_search_logger.info("[RAG检索] userId={}, input='{}', type='{}', topK={}, threshold={}",
                          id, request.input, request.type, request.topK, request.threshold)

    try:
        # Step 1: 确定 collections 和 ES 索引
        collections = _determine_collections(request.type)
        es_index = _determine_es_index(request.type)
        vector_top_k = request.topK or Config.RERANK_TOP_K

        # Step 2: 并行执行 - Embedding 和 ES BM25 搜索
        # 注意：Milvus 向量搜索依赖 query_vector，所以需要先完成 Embedding
        embedding_task = _generate_query_vector(request.input)
        es_search_task = _execute_es_bm25_search(es_index, request.input, vector_top_k)

        # 等待 Embedding 完成，获取 query_vector
        query_vector = await embedding_task

        # DEBUG: 打印查询向量
        if Config.DEBUG:
            rag_search_logger.info(f"[RAG检索] [DEBUG] 查询向量维度={len(query_vector)}, 前5维={query_vector[:5]}")

        # 同时执行 Milvus 向量搜索和 ES BM25 搜索
        vector_results, es_results = await asyncio.gather(
            _execute_vector_search(collections, query_vector, vector_top_k),
            es_search_task
        )

        # DEBUG: 打印向量搜索结果
        if Config.DEBUG:
            rag_search_logger.info(f"[RAG检索] [DEBUG] 向量搜索结果数量={len(vector_results)}")
            for i, r in enumerate(vector_results[:10]):
                rag_search_logger.info(f"[RAG检索] [DEBUG] 向量结果{i+1}: id={r.get('id')}, score={r.get('score')}, description={r.get('description', '')[:50]}")

        # DEBUG: 打印 ES BM25 搜索结果
        if Config.DEBUG:
            rag_search_logger.info(f"[RAG检索] [DEBUG] ES BM25搜索结果数量={len(es_results)}")
            for i, r in enumerate(es_results[:10]):
                rag_search_logger.info(f"[RAG检索] [DEBUG] ES结果{i+1}: id={r.get('id')}, score={r.get('score')}")

        # Step 6: RRF 融合
        if es_results:
            fused_results = rrf_fusion([vector_results, es_results], k=60)
            rag_search_logger.info(f"[RAG检索] RRF融合完成，融合后数量={len(fused_results)}")
        else:
            # ES 不可用，降级为纯向量搜索
            fused_results = vector_results
            rag_search_logger.warning(f"[RAG检索] ES不可用，降级为纯向量搜索")

        # DEBUG: 打印融合结果
        if Config.DEBUG and fused_results:
            rag_search_logger.info(f"[RAG检索] [DEBUG] RRF融合结果全部({len(fused_results)}):")
            for i, r in enumerate(fused_results):
                rag_search_logger.info(f"[RAG检索] [DEBUG] 融合结果{i+1}: id={r.get('id')}, rrf_score={r.get('rrf_score')}")

        # Step 7: 特征加权（在 RRF 之后、Rerank 之前）
        # Step 7: Rerank 重排
        rerank_count = len(fused_results)
        if fused_results:
            fused_results = await _rerank_results(request.input, fused_results)

            # DEBUG: 打印重排序结果
            if Config.DEBUG:
                rag_search_logger.info(f"[RAG检索] [DEBUG] Rerank后结果数量={len(fused_results)}")
                for i, r in enumerate(fused_results[:3]):
                    rag_search_logger.info(f"[RAG检索] [DEBUG] Rerank结果{i+1}: id={r.get('id')}, score={r.get('score')}")

        # Step 8: 特征加权（在 Rerank 之后）
        if request.enableFeatureBoost and fused_results:
            feature_boost_service = get_feature_boost_service()
            fused_results = await feature_boost_service.boost(
                query=request.input,
                results=fused_results,
                enable_fixed=True,
                enable_semantic=True
            )
            rag_search_logger.info(f"[RAG检索] 特征加权完成, 结果数量={len(fused_results)}")

            # DEBUG: 打印特征加权结果
            if Config.DEBUG:
                for i, r in enumerate(fused_results[:3]):
                    rag_search_logger.info(
                        f"[RAG检索] [DEBUG] 特征加权结果{i+1}: id={r.get('id')}, "
                        f"score={r.get('score')}, match_count={r.get('_feature_match_count', 0)}, "
                        f"fixed_boost={r.get('_fixed_boost', 0)}, semantic_boost={r.get('_semantic_boost', 'N/A')}"
                    )

        # Step 8.5: 归一化分数到 [0, 1]
        if fused_results:
            fused_results = normalize_final_scores(fused_results)
            if Config.DEBUG:
                rag_search_logger.info(f"[RAG检索] [DEBUG] 归一化后分数: {[round(r.get('score', 0), 4) for r in fused_results[:3]]}")

        # Step 9: 阈值过滤
        filtered_results = _filter_by_threshold(fused_results, request.threshold)

        # Step 10: 构建响应
        search_results = _build_search_results(filtered_results)

        rag_search_logger.info("[RAG检索] 向量={}条, ES={}条, 融合={}条, Rerank={}条, 过滤后={}条",
                              len(vector_results), len(es_results), len(fused_results), rerank_count, len(search_results))

        return SearchResponse(
            code=200,
            message="success",
            data=search_results
        )

    except httpx.HTTPError as e:
        # Embedding 或 Milvus HTTP 调用失败，降级返回空结果
        rag_search_logger.error("[RAG检索] HTTP 服务调用失败, error={}", str(e))
        return SearchResponse(code=200, message="success", data=[])
    except Exception as e:
        # 其他未知异常，降级返回空结果
        rag_search_logger.error("[RAG检索] 检索失败, error={}", str(e))
        return SearchResponse(code=200, message="success", data=[])


async def _generate_query_vector(query_text: str) -> List[float]:
    """
    生成查询向量

    @param query_text - 查询文本
    @returns 查询向量

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    embedding_service = get_embedding_service()
    rag_search_logger.info("[RAG检索] 开始向量化查询文本...")
    query_vector = await embedding_service.encode(query_text)
    rag_search_logger.info("[RAG检索] 向量化完成, 向量维度={}", len(query_vector))
    return query_vector


def _determine_collections(search_type: str) -> List[str]:
    """
    确定要搜索的 collections

    @param search_type - 搜索类型（"all" 或具体类型如 "skill"）
    @returns 要搜索的 collection 列表

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    # 如果 type 是 "all"，搜索所有 collection；否则只搜索指定类型
    is_search_all = (search_type == "all")
    collections = ["skill", "asset"] if is_search_all else search_type
    rag_search_logger.info("[RAG检索] 搜索 collections: {}", collections)
    return collections


async def _execute_vector_search(
    collections: Union[str, List[str]],
    query_vector: List[float],
    top_k: int
) -> List[Dict[str, Any]]:
    """
    执行向量搜索

    @param collections - collection 名称或列表
    @param query_vector - 查询向量
    @param top_k - 返回数量
    @returns 搜索结果列表

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    milvus_service = get_milvus_service()
    rag_search_logger.info("[RAG检索] 开始向量搜索...")
    search_results_raw = await milvus_service.search(
        collection=collections,
        query_vector=query_vector,
        top_k=top_k or Config.RERANK_TOP_K
    )
    rag_search_logger.info("[RAG检索] 向量搜索完成, 原始结果数量: {}", len(search_results_raw))
    return search_results_raw


def _determine_es_index(search_type: str) -> str:
    """
    确定要搜索的 ES 索引

    @param search_type - 搜索类型（"all"、"skill" 或 "asset"）
    @returns ES 索引名称

    Author: lvdaxianerplus
    Date: 2026-04-16
    """
    if search_type == "all":
        # 搜索全部时使用 skill 索引（可根据需求扩展）
        return Config.ES_SKILL_INDEX
    elif search_type == "asset":
        return Config.ES_ASSET_INDEX
    else:
        # 默认使用 skill 索引
        return Config.ES_SKILL_INDEX


async def _execute_es_bm25_search(
    es_index: str,
    query_text: str,
    top_k: int
) -> List[Dict[str, Any]]:
    """
    执行 ES BM25 搜索

    @param es_index - ES 索引名称
    @param query_text - 查询文本
    @param top_k - 返回数量
    @returns BM25 搜索结果列表

    Author: lvdaxianerplus
    Date: 2026-04-16
    """
    try:
        es_service = get_es_service()
        rag_search_logger.info(f"[RAG检索] 开始 ES BM25 搜索, index={es_index}...")
        es_results = await es_service.search(
            index_name=es_index,
            query=query_text,
            top_k=top_k,
            query_lang="auto"
        )
        rag_search_logger.info(f"[RAG检索] ES BM25 搜索完成, 结果数量: {len(es_results)}")
        return es_results
    except Exception as e:
        rag_search_logger.warning(f"[RAG检索] ES BM25 搜索失败: {e}")
        return []


async def _rerank_results(
    query_text: str,
    results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    对搜索结果进行 Rerank 重排

    @param query_text - 查询文本
    @param results - 原始搜索结果
    @returns 重排后的结果（如重排失败则返回原始结果）

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    # 当有搜索结果时，尝试进行 Rerank 重排
    # Rerank 失败时降级使用原始分数
    rerank_service = get_rerank_service()
    try:
        rag_search_logger.info("[RAG检索] 开始 Rerank 重排, 待重排数量: {}", len(results))
        rerank_results = await rerank_service.rerank(query_text, results)
        rag_search_logger.info("[RAG检索] Rerank 完成, 返回数量: {}", len(rerank_results))
        # 合并 Rerank 分数到结果（按 index 映射）
        for r in rerank_results:
            idx = r.get("index")
            if idx is not None and idx < len(results):
                results[idx]["score"] = r.get("relevance_score", results[idx]["score"])
        rag_search_logger.info("[RAG检索] Rerank 分数已合并到结果")
    except httpx.HTTPError as e:
        # Rerank HTTP 调用失败，使用原始分数
        rag_search_logger.warning("[RAG检索] Rerank HTTP 调用失败，使用原始分数, error={}", str(e))
    except Exception as e:
        # 其他 Rerank 异常，使用原始分数
        rag_search_logger.warning("[RAG检索] Rerank 不可用，使用原始分数, error={}", str(e))

    return results


def _filter_by_threshold(results: List[Dict[str, Any]], threshold: float = None) -> List[Dict[str, Any]]:
    """
    过滤低于阈值的结果

    @param results - 搜索结果列表
    @param threshold - 相似度阈值，默认使用配置值
    @returns 过滤后的结果列表

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    # 如果请求中未指定阈值，使用配置默认值
    effective_threshold = threshold if threshold is not None else Config.RERANK_THRESHOLD
    rag_search_logger.info("[RAG检索] 阈值过滤: threshold={}", effective_threshold)
    filtered_results = [
        r for r in results
        if r.get("score", 0) >= effective_threshold
    ]
    rag_search_logger.info("[RAG检索] 阈值过滤后: {} -> {}", len(results), len(filtered_results))
    return filtered_results


def _build_search_results(filtered_results: List[Dict[str, Any]]) -> List[SearchResult]:
    """
    构建检索响应结果

    @param filtered_results - 过滤后的搜索结果
    @returns SearchResult 列表

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    return [
        SearchResult(
            metadata=r["metadata"],
            description=r["description"],
            score=r["score"],
            features=r.get("features")
        )
        for r in filtered_results
    ]


# =============================================================================
# 删除接口
# =============================================================================

@router.delete("/{id}/delete", response_model=DeleteResponse)
async def delete(id: str, request: DeleteRequest):
    """
    删除记录接口

    @param id - 用户ID，用于日志追踪
    @param request - 删除请求
    @returns 删除结果

    Author: lvdaxianerplus
    Date: 2026-04-14
    """
    rag_delete_logger.info("[RAG删除] 开始删除, userId={}, type={}, id={}", id, request.type, request.id)

    try:
        milvus_service = get_milvus_service()
        success = await milvus_service.delete(
            collection=request.type,
            doc_id=request.id
        )

        # 双写 ES 删除（降级：ES 失败不影响主流程）
        try:
            es_service = get_es_service()
            es_index = Config.ES_SKILL_INDEX if request.type == "skill" else Config.ES_ASSET_INDEX
            await es_service.delete_document(es_index, request.id)
            rag_delete_logger.info("[RAG删除] ES 删除成功, id={}", request.id)
        except Exception as es_error:
            rag_delete_logger.warning("[RAG删除] ES 删除失败（降级）, id={}, error={}",
                                   request.id, str(es_error))

        # 删除成功时返回成功响应
        if success:
            rag_delete_logger.info("[RAG删除] 删除成功, id={}", request.id)
            return DeleteResponse(
                code=200,
                message="success",
                data=None
            )
        else:
            # 删除失败时返回 404
            rag_delete_logger.warning("[RAG删除] 记录不存在, id={}", request.id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": 2002, "message": "记录不存在"}
            )

    except HTTPException:
        raise
    except httpx.HTTPError as e:
        # Milvus HTTP 调用失败
        rag_delete_logger.error("[RAG删除] HTTP 服务调用失败, error={}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 500, "message": "删除失败"}
        ) from e
    except Exception as e:
        # 其他未知异常
        rag_delete_logger.error("[RAG删除] 删除失败, error={}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 500, "message": "删除失败"}
        ) from e


@router.post("/{id}/delete", response_model=DeleteResponse)
async def delete_via_post(id: str, request: DeleteRequest):
    """
    通过POST方式删除记录（HTTP降级调用）

    Java HttpClient不支持带body的DELETE请求，因此提供POST替代接口

    @param id - 用户ID，用于日志追踪
    @param request - 删除请求
    @returns 删除结果
    """
    return await delete(id, request)


# =============================================================================
# 重试队列接口
# =============================================================================

@router.get("/{id}/retry/tasks")
async def get_retry_tasks(id: str):
    """
    获取用户所有待处理的重试任务

    @param id - 用户ID
    @returns 待处理任务列表
    """
    retry_queue = get_retry_queue()
    pending_tasks = retry_queue.get_user_pending_tasks(id)
    failed_tasks = retry_queue.get_user_failed_tasks(id)

    return APIResponse(
        code=200,
        message="success",
        data={
            "pending": pending_tasks,
            "failed": failed_tasks,
            "queue_size": retry_queue.queue_size,
            "failed_count": retry_queue.failed_count
        }
    )


@router.get("/{id}/retry/tasks/{task_id}")
async def get_retry_task_status(id: str, task_id: str):
    """
    获取特定重试任务的状态

    @param id - 用户ID
    @param task_id - 任务ID
    @returns 任务状态
    """
    retry_queue = get_retry_queue()
    task_status = retry_queue.get_task_status(task_id)

    # 验证任务存在且属于该用户
    if task_status is None or task_status.get("user_id") != id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 404, "message": "任务不存在"}
        )

    return APIResponse(
        code=200,
        message="success",
        data=task_status
    )


# =============================================================================
# 缓存管理接口
# =============================================================================

@router.post("/cache/reset", response_model=APIResponse)
async def reset_cache():
    """
    重置所有缓存

    清空 Embedding 缓存和 Rerank 缓存

    @returns 重置结果
    """
    from app.services.cache_service import get_cache_service

    cache_service = get_cache_service()
    result = cache_service.clear_all()

    rag_search_logger.info("[缓存] 手动重置缓存, result={}", result)

    return APIResponse(
        code=200,
        message="缓存已重置",
        data=result
    )


@router.get("/cache/stats", response_model=APIResponse)
async def get_cache_stats():
    """
    获取缓存统计信息

    @returns 缓存统计
    """
    from app.services.cache_service import get_cache_service

    cache_service = get_cache_service()
    stats = cache_service.get_stats()

    return APIResponse(
        code=200,
        message="success",
        data=stats
    )
