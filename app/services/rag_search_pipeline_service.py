"""
RAG 检索管线服务

封装混合检索、RRF 融合、Rerank、特征加权和结果构建流程。

@author lvdaxianerplus
@date 2026-06-01
"""

import asyncio
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Dict, List, Optional, Union

import httpx

from app.config import Config
from app.models.schemas import SearchRequest, SearchResult
from app.services.embedding_service import EmbeddingService
from app.services.es_service import get_es_service
from app.services.feature_boost_service import get_feature_boost_service
from app.services.global_retrieval_service import ESSummaryRetriever, GlobalRetrievalService
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.hybrid_search import normalize_final_scores, rrf_fusion
from app.services.issue_filter_service import IssueFilterService
from app.services.milvus_service import MilvusService
from app.services.ragflow_hybrid_score import weighted_hybrid_fusion
from app.services.rerank_service import RerankService
from app.utils.logger import rag_search_logger


_embedding_service = None
_rerank_service = None
_milvus_service = None
_fallbacks_context: ContextVar[Optional[Dict[str, Dict[str, Any]]]] = ContextVar(
    "rag_search_fallbacks",
    default=None
)


@dataclass
class SearchPipelineResult:
    """检索管线结果和诊断信息"""
    results: List[SearchResult]
    profile: Dict[str, Any]


@dataclass
class RetrievalContext:
    """查询拆解上下文，用于按 Query 类型调整本地预排序策略。"""
    query_type: str = ""
    entities: Optional[List[str]] = None
    symptoms: Optional[List[str]] = None
    environment_gap: Optional[List[str]] = None
    time_context: Optional[List[str]] = None


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


async def run_search_pipeline(id: str, request: SearchRequest) -> List[SearchResult]:
    """
    执行 RAG 检索管线

    @param id - 用户ID，用于日志追踪
    @param request - 检索请求
    @returns 检索结果列表
    """
    result = await run_search_pipeline_with_profile(id, request)
    return result.results


async def run_search_pipeline_with_profile(
    id: str,
    request: SearchRequest,
    prefetched_query_vector: Optional[List[float]] = None,
    retrieval_context: Optional[RetrievalContext] = None,
    request_id: Optional[str] = None
) -> SearchPipelineResult:
    """
    执行 RAG 检索管线

    @param id - 用户ID，用于日志追踪
    @param request - 检索请求
    @returns 检索结果和阶段耗时
    """
    rag_search_logger.info("[RAG检索] userId={}, input='{}', type='{}', topK={}, threshold={}",
                           id, request.input, request.type, request.topK, request.threshold)

    es_search_task = None
    graph_search_task = None
    timings: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    total_started = perf_counter()
    try:
        fallbacks = _init_fallbacks()
        fallbacks_token = _fallbacks_context.set(fallbacks)
        collections = _determine_collections(request.type)
        es_indexes = _determine_es_indexes(request.type)
        issue_filters = IssueFilterService().build(getattr(request, "issue_type", None))
        base_es_metadata_filter = _determine_es_metadata_filter(request.type)
        es_metadata_filter = _merge_metadata_filters(base_es_metadata_filter, issue_filters)
        vector_top_k = request.topK or Config.RERANK_TOP_K

        es_search_func = (
            _execute_es_weighted_search
            if Config.RAG_RETRIEVAL_STRATEGY == "ragflow_weighted"
            else _execute_es_bm25_search
        )
        es_search_task = asyncio.create_task(
            _timed("es_bm25", timings, es_search_func, es_indexes, request.input, vector_top_k, es_metadata_filter)
        )
        graph_search_task = asyncio.create_task(
            _timed("graph_search", timings, _execute_graph_search, request.input, request.type, vector_top_k)
        )
        if prefetched_query_vector is not None:
            timings["embedding"] = 0.0
            query_vector = prefetched_query_vector
        else:
            query_vector = await _timed("embedding", timings, _generate_query_vector, request.input)

        if Config.DEBUG:
            rag_search_logger.info(f"[RAG检索] [DEBUG] 查询向量维度={len(query_vector)}, 前5维={query_vector[:5]}")

        vector_results, es_results, graph_results = await asyncio.gather(
            _timed("vector_search", timings, _execute_vector_search, collections, query_vector, vector_top_k),
            es_search_task,
            graph_search_task
        )
        graph_results = _filter_graph_results_by_issue_filters(graph_results, issue_filters)
        global_context = await _timed(
            "global_retrieval",
            timings,
            _maybe_build_global_retrieval_context,
            request,
            es_indexes,
            vector_top_k,
        )
        global_evidence_results = _global_evidence_results(global_context)
        counts.update({
            "vector": len(vector_results),
            "es": len(es_results),
            "graph": len(graph_results),
            "global_evidence": len(global_evidence_results),
        })

        if Config.DEBUG:
            _log_debug_source_results(vector_results, es_results, graph_results)

        fusion_started = perf_counter()
        fused_results = _fuse_search_results(
            vector_results,
            [*es_results, *global_evidence_results],
            graph_results,
            strategy=Config.RAG_RETRIEVAL_STRATEGY,
        )
        timings["fusion"] = _elapsed_ms(fusion_started)
        if fused_results:
            fused_results = await _timed("vector_calibration", timings, _maybe_calibrate_vector_scores, fused_results, query_vector)
        else:
            timings["vector_calibration"] = 0.0
        counts["fused"] = len(fused_results)
        strategy_started = perf_counter()
        retrieval_strategy = _build_retrieval_strategy_profile(
            retrieval_context,
            query_scope=request.query_scope,
            route_plan=request.route_plan,
            issue_type=getattr(request, "issue_type", None),
            issue_filters=issue_filters,
        )
        retrieval_strategy["global_retrieval"] = _summarize_global_retrieval_context(global_context)
        fused_results = apply_retrieval_context_prerank(fused_results, retrieval_context)
        retrieval_strategy["boosted_count"] = sum(1 for result in fused_results if result.get("_context_prerank_boost"))
        timings["retrieval_strategy"] = _elapsed_ms(strategy_started)
        if Config.DEBUG and fused_results:
            rag_search_logger.info(f"[RAG检索] [DEBUG] RRF融合结果全部({len(fused_results)}):")
            for i, r in enumerate(fused_results):
                rag_search_logger.info(f"[RAG检索] [DEBUG] 融合结果{i+1}: id={r.get('id')}, rrf_score={r.get('rrf_score')}")

        rerank_count = _calculate_rerank_candidate_limit(len(fused_results), request.topK)
        rerank_decision = _build_rerank_decision(fused_results, rerank_count, request.topK)
        if Config.RAG_RETRIEVAL_STRATEGY == "ragflow_weighted" and fused_results:
            fused_results = get_feature_boost_service().apply_local_tag_rank_feature(request.input, fused_results)
            fused_results = _attach_weighted_strategy_trace(fused_results, request.input)

        if fused_results and rerank_decision["skipped"]:
            rerank_count = 0
            timings["rerank"] = 0.0
            _reset_unified_scores(fused_results)
            _mark_fallback("rerank", "skipped_confident_rrf_leader")
            rag_search_logger.info("[RAG检索] RRF 第一名高置信，跳过 Rerank")
        elif fused_results:
            fused_results = await _timed("rerank", timings, _rerank_results, request.input, fused_results, request_id)
            if Config.DEBUG:
                rag_search_logger.info(f"[RAG检索] [DEBUG] Rerank后结果数量={len(fused_results)}")
                for i, r in enumerate(fused_results[:3]):
                    rag_search_logger.info(f"[RAG检索] [DEBUG] Rerank结果{i+1}: id={r.get('id')}, score={r.get('score')}")
        else:
            timings["rerank"] = 0.0
        counts["rerank"] = rerank_count

        if request.enableFeatureBoost and fused_results:
            fused_results = await _timed("feature_boost", timings, _boost_features, request.input, fused_results)
        else:
            timings["feature_boost"] = 0.0

        fused_results = await _timed("parent_context", timings, _maybe_enhance_parent_context, fused_results, es_indexes)

        domain_rule_started = perf_counter()
        fused_results = apply_domain_rerank_rules(request.input, fused_results)
        timings["domain_rules"] = _elapsed_ms(domain_rule_started)

        if fused_results:
            normalize_started = perf_counter()
            fused_results = normalize_final_scores(fused_results)
            timings["normalize"] = _elapsed_ms(normalize_started)
            if Config.DEBUG:
                rag_search_logger.info(f"[RAG检索] [DEBUG] 归一化后分数: {[round(r.get('score', 0), 4) for r in fused_results[:3]]}")
        else:
            timings["normalize"] = 0.0

        filter_started = perf_counter()
        filtered_results = _filter_by_threshold(fused_results, request.threshold)
        search_results = _build_search_results(filtered_results)
        timings["filter_build"] = _elapsed_ms(filter_started)
        counts["filtered"] = len(search_results)
        timings["total"] = _elapsed_ms(total_started)
        rag_search_logger.info("[RAG检索] 向量={}条, ES={}条, 图={}条, 融合={}条, Rerank={}条, 过滤后={}条",
                               len(vector_results), len(es_results), len(graph_results), len(fused_results), rerank_count, len(search_results))

        return SearchPipelineResult(
            results=search_results,
            profile={
                "timings_ms": timings,
                "counts": counts,
                "fallbacks": fallbacks,
                "rerank_decision": rerank_decision,
                "retrieval_strategy": retrieval_strategy,
            }
        )

    except httpx.HTTPError as e:
        await _cancel_pending_tasks(es_search_task, graph_search_task)
        rag_search_logger.error("[RAG检索] HTTP 服务调用失败, error={}", str(e))
        timings["total"] = _elapsed_ms(total_started)
        return SearchPipelineResult(
            results=[],
            profile={"timings_ms": timings, "counts": counts, "fallbacks": _current_fallbacks()}
        )
    except Exception as e:
        await _cancel_pending_tasks(es_search_task, graph_search_task)
        rag_search_logger.error("[RAG检索] 检索失败, error={}", str(e))
        timings["total"] = _elapsed_ms(total_started)
        return SearchPipelineResult(
            results=[],
            profile={"timings_ms": timings, "counts": counts, "fallbacks": _current_fallbacks()}
        )
    finally:
        if "fallbacks_token" in locals():
            _fallbacks_context.reset(fallbacks_token)


async def _timed(stage: str, timings: Dict[str, float], func, *args, **kwargs):
    """记录异步阶段耗时"""
    started = perf_counter()
    try:
        return await func(*args, **kwargs)
    finally:
        timings[stage] = _elapsed_ms(started)


def _elapsed_ms(started: float) -> float:
    """计算毫秒耗时"""
    return round((perf_counter() - started) * 1000, 2)


def _init_fallbacks() -> Dict[str, Dict[str, Any]]:
    """初始化检索通道降级状态"""
    return {
        "vector": {"used": False, "reason": ""},
        "es": {"used": False, "reason": ""},
        "graph": {"used": False, "reason": ""},
        "rerank": {"used": False, "reason": ""},
        "parent_context": {"used": False, "reason": ""},
        "global_retrieval": {"used": False, "reason": ""},
    }


def _current_fallbacks() -> Dict[str, Dict[str, Any]]:
    """读取当前请求的降级状态"""
    return _fallbacks_context.get() or _init_fallbacks()


def _mark_fallback(channel: str, reason: str) -> None:
    """标记指定检索通道已降级"""
    fallbacks = _fallbacks_context.get()
    if fallbacks is None:
        return
    fallbacks[channel] = {"used": True, "reason": reason}


async def _cancel_pending_tasks(*tasks) -> None:
    """取消尚未完成的后台检索任务"""
    for task in tasks:
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def _generate_query_vector(query_text: str) -> List[float]:
    """生成查询向量"""
    embedding_service = get_embedding_service()
    rag_search_logger.info("[RAG检索] 开始向量化查询文本...")
    query_vector = await embedding_service.encode(query_text)
    rag_search_logger.info("[RAG检索] 向量化完成, 向量维度={}", len(query_vector))
    return query_vector


def _determine_collections(search_type: str) -> Union[str, List[str]]:
    """确定要搜索的 collections"""
    is_search_all = (search_type == "all")
    collections = ["skill", "asset"] if is_search_all else search_type
    rag_search_logger.info("[RAG检索] 搜索 collections: {}", collections)
    return collections


async def _execute_vector_search(
    collections: Union[str, List[str]],
    query_vector: List[float],
    top_k: int
) -> List[Dict[str, Any]]:
    """执行向量搜索"""
    try:
        milvus_service = get_milvus_service()
        rag_search_logger.info("[RAG检索] 开始向量搜索...")
        search_results_raw = await milvus_service.search(
            collection=collections,
            query_vector=query_vector,
            top_k=top_k or Config.RERANK_TOP_K
        )
        rag_search_logger.info("[RAG检索] 向量搜索完成, 原始结果数量: {}", len(search_results_raw))
        return search_results_raw
    except Exception as e:
        rag_search_logger.warning("[RAG检索] 向量搜索失败（降级）, error={}", str(e))
        _mark_fallback("vector", str(e))
        return []


def _determine_es_indexes(search_type: str) -> List[str]:
    """确定要搜索的 ES 索引列表"""
    if search_type == "all":
        return [Config.ES_SKILL_INDEX, Config.ES_ASSET_INDEX]
    if search_type == "asset":
        return [Config.ES_ASSET_INDEX]
    return [Config.ES_SKILL_INDEX]


def _determine_es_metadata_filter(search_type: str) -> Optional[Dict[str, Any]]:
    """确定 ES metadata 过滤条件"""
    if search_type == "all":
        return None
    return {"type": search_type}


def _merge_metadata_filters(*filters: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    合并多个 metadata filter，后传入的同名字段覆盖前者。

    @param filters - 待合并过滤条件
    @returns 合并后的过滤条件，空过滤返回 None
    @author lvdaxianerplus
    @date 2026-06-04
    """
    merged: Dict[str, Any] = {}
    for item in filters:
        if item:
            merged.update(item)
        else:
            continue
    if merged:
        return merged
    else:
        return None


async def _execute_es_bm25_search(
    es_indexes: List[str],
    query_text: str,
    top_k: int,
    metadata_filter: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """执行 ES BM25 搜索"""
    try:
        es_service = get_es_service()
        rag_search_logger.info("[RAG检索] 开始 ES BM25 搜索, indexes={}...", es_indexes)
        search_tasks = [
            es_service.search(
                index_name=es_index,
                query=query_text,
                top_k=top_k,
                query_lang="auto",
                metadata_filter=metadata_filter
            )
            for es_index in es_indexes
        ]
        result_lists = await asyncio.gather(*search_tasks, return_exceptions=True)
        merged_results = []
        seen_ids = set()
        for results in result_lists:
            for result in results:
                doc_id = result.get("id")
                if doc_id and doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    merged_results.append(result)
        rag_search_logger.info("[RAG检索] ES BM25 搜索完成, 结果数量: {}", len(merged_results))
        return merged_results
    except Exception as e:
        rag_search_logger.warning("[RAG检索] ES BM25 搜索失败: {}", str(e))
        _mark_fallback("es", str(e))
        return []


async def _execute_es_weighted_search(
    es_indexes: List[str],
    query_text: str,
    top_k: int,
    metadata_filter: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """执行 RAGFlow-inspired ES 字段加权搜索。"""
    try:
        es_service = get_es_service()
        rag_search_logger.info("[RAG检索] 开始 ES weighted 搜索, indexes={}...", es_indexes)
        search_tasks = [
            es_service.search_weighted(
                index_name=es_index,
                query=query_text,
                top_k=top_k,
                metadata_filter=metadata_filter
            )
            for es_index in es_indexes
        ]
        result_lists = await asyncio.gather(*search_tasks, return_exceptions=True)
        merged_results = []
        seen_ids = set()
        for results in result_lists:
            for result in results:
                doc_id = result.get("id")
                if doc_id and doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    merged_results.append(result)
        rag_search_logger.info("[RAG检索] ES weighted 搜索完成, 结果数量: {}", len(merged_results))
        return merged_results
    except Exception as e:
        rag_search_logger.warning("[RAG检索] ES weighted 搜索失败: {}", str(e))
        _mark_fallback("es", str(e))
        return []


async def _execute_graph_search(
    query_text: str,
    search_type: str,
    top_k: int
) -> List[Dict[str, Any]]:
    """执行轻量图谱检索"""
    try:
        graph_service = get_graph_retrieval_service()
        graph_results = graph_service.search(
            query_text,
            search_type=search_type,
            top_k=top_k
        )
        rag_search_logger.info("[RAG检索] 图检索完成, 结果数量: {}", len(graph_results))
        return graph_results
    except Exception as e:
        rag_search_logger.warning("[RAG检索] 图检索失败: {}", str(e))
        _mark_fallback("graph", str(e))
        return []


def _filter_graph_results_by_issue_filters(
    graph_results: List[Dict[str, Any]],
    issue_filters: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    对图检索结果应用 issue metadata 后过滤。

    @param graph_results - 图检索候选
    @param issue_filters - 问题类型过滤条件
    @returns 匹配过滤条件的图候选
    @author lvdaxianerplus
    @date 2026-06-04
    """
    if not graph_results or not issue_filters:
        return graph_results
    else:
        return [
            result
            for result in graph_results
            if _metadata_matches_issue_filters(result.get("metadata") or {}, issue_filters)
        ]


def _metadata_matches_issue_filters(metadata: Dict[str, Any], issue_filters: Dict[str, Any]) -> bool:
    """
    判断单条 metadata 是否匹配 issue filters。

    @param metadata - 候选元数据
    @param issue_filters - 问题类型过滤条件
    @returns 全部过滤字段匹配时返回 True
    @author lvdaxianerplus
    @date 2026-06-04
    """
    for key, allowed_values in issue_filters.items():
        if metadata.get(key) in allowed_values:
            continue
        else:
            return False
    return True


async def _maybe_build_global_retrieval_context(
    request: SearchRequest,
    es_indexes: List[str],
    top_k: int,
) -> Dict[str, Any]:
    """按配置为 global/hybrid 查询构建 summary-first context。"""
    if not getattr(Config, "RAG_GLOBAL_RETRIEVAL_ENABLED", False):
        return {}
    if request.query_scope not in {"global", "hybrid"}:
        return {}

    try:
        retriever = _build_es_summary_retriever(es_indexes)
        return await GlobalRetrievalService(retriever=retriever).build_context(
            query=request.input,
            query_scope=request.query_scope or "global",
            top_k=top_k,
        )
    except Exception as e:
        rag_search_logger.warning("[RAG检索] 全局 summary-first 检索失败（降级）, error={}", str(e))
        _mark_fallback("global_retrieval", str(e))
        return {}


def _build_es_summary_retriever(es_indexes: List[str]) -> ESSummaryRetriever:
    """构建 ES summary-first retriever。"""
    return ESSummaryRetriever(es_service=get_es_service(), index_names=es_indexes)


def _global_evidence_results(global_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 global retrieval context 中提取可参与融合的 evidence chunk。"""
    evidence_chunks = global_context.get("evidence_chunks") or []
    enriched = []
    for chunk in evidence_chunks:
        item = chunk.copy()
        trace = dict(item.get("score_trace") or {})
        trace["global_retrieval"] = True
        trace["global_route"] = global_context.get("route", "")
        item["score_trace"] = trace
        enriched.append(item)
    return enriched


def _summarize_global_retrieval_context(global_context: Dict[str, Any]) -> Dict[str, Any]:
    """构建 profile 中的全局检索摘要，不暴露私有推理链。"""
    if not global_context:
        return {"enabled": False}
    map_reduce_context = global_context.get("map_reduce_context") or {}
    return {
        "enabled": True,
        "route": global_context.get("route", ""),
        "summary_count": len(global_context.get("summaries") or []),
        "evidence_count": len(global_context.get("evidence_chunks") or []),
        "map_note_count": len(map_reduce_context.get("map_notes") or []),
    }


def _log_debug_source_results(
    vector_results: List[Dict[str, Any]],
    es_results: List[Dict[str, Any]],
    graph_results: List[Dict[str, Any]]
) -> None:
    """记录各来源检索结果调试信息"""
    rag_search_logger.info(f"[RAG检索] [DEBUG] 向量搜索结果数量={len(vector_results)}")
    for i, r in enumerate(vector_results[:10]):
        rag_search_logger.info(f"[RAG检索] [DEBUG] 向量结果{i+1}: id={r.get('id')}, score={r.get('score')}, description={r.get('description', '')[:50]}")
    rag_search_logger.info(f"[RAG检索] [DEBUG] ES BM25搜索结果数量={len(es_results)}")
    for i, r in enumerate(es_results[:10]):
        rag_search_logger.info(f"[RAG检索] [DEBUG] ES结果{i+1}: id={r.get('id')}, score={r.get('score')}")
    rag_search_logger.info(f"[RAG检索] [DEBUG] 图检索结果数量={len(graph_results)}")


def _fuse_search_results(
    vector_results: List[Dict[str, Any]],
    es_results: List[Dict[str, Any]],
    graph_results: List[Dict[str, Any]],
    strategy: Optional[str] = None
) -> List[Dict[str, Any]]:
    """融合向量、BM25 和图检索结果"""
    if strategy == "ragflow_weighted":
        fused_results = weighted_hybrid_fusion(
            vector_results=vector_results,
            text_results=es_results,
            graph_results=graph_results,
            text_weight=Config.RAG_WEIGHTED_TEXT_WEIGHT,
            vector_weight=Config.RAG_WEIGHTED_VECTOR_WEIGHT,
            graph_weight=Config.RAG_WEIGHTED_GRAPH_WEIGHT,
        )
        rag_search_logger.info("[RAG检索] weighted hybrid 融合完成，融合后数量={}", len(fused_results))
        return fused_results
    if es_results or graph_results:
        fused_results = rrf_fusion([vector_results, es_results, graph_results], k=60)
        rag_search_logger.info(f"[RAG检索] RRF融合完成，融合后数量={len(fused_results)}")
        return fused_results
    rag_search_logger.warning("[RAG检索] ES和图检索不可用，降级为纯向量搜索")
    return vector_results


async def _maybe_calibrate_vector_scores(
    results: List[Dict[str, Any]],
    query_vector: List[float],
) -> List[Dict[str, Any]]:
    """按配置决定是否补充向量校准分数。"""
    if not getattr(Config, "RAG_VECTOR_SCORE_CALIBRATION_ENABLED", False):
        return results

    score_map = await _calibrate_vector_scores(results, query_vector)
    calibrated_results = []
    for result in results:
        item = result.copy()
        doc_id = item.get("id") or item.get("doc_id")
        if doc_id in score_map:
            trace = dict(item.get("score_trace") or {})
            trace["calibrated_vector_score"] = score_map[doc_id]
            item["score_trace"] = trace
        calibrated_results.append(item)
    return calibrated_results


async def _calibrate_vector_scores(
    results: List[Dict[str, Any]],
    query_vector: List[float],
) -> Dict[str, float]:
    """按候选 ID 批量二次查询 Milvus，补齐可比的向量分数。"""
    grouped_doc_ids = _group_result_ids_by_collection(results)
    if not grouped_doc_ids:
        return {}

    try:
        milvus_service = get_milvus_service()
        tasks = [
            milvus_service.score_documents_by_ids(
                collection=collection,
                query_vector=query_vector,
                doc_ids=doc_ids,
            )
            for collection, doc_ids in grouped_doc_ids.items()
        ]
        score_maps = await asyncio.gather(*tasks)
    except Exception as e:
        rag_search_logger.warning("[RAG检索] 向量分数校准失败（降级）, error={}", str(e))
        _mark_fallback("vector", f"calibration_failed: {e}")
        return {}

    merged_scores: Dict[str, float] = {}
    for score_map in score_maps:
        merged_scores.update(score_map)
    return merged_scores


def _group_result_ids_by_collection(results: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """按 metadata.type 将候选 ID 分组为 Milvus collection 批量查询。"""
    grouped: Dict[str, List[str]] = {}
    seen_ids = set()
    for result in results:
        doc_id = result.get("id") or result.get("doc_id")
        metadata = result.get("metadata") or {}
        collection = metadata.get("type")
        if not doc_id or not collection or doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        grouped.setdefault(collection, []).append(doc_id)
    return grouped


async def _maybe_enhance_parent_context(
    results: List[Dict[str, Any]],
    es_indexes: List[str]
) -> List[Dict[str, Any]]:
    """按配置决定是否扩展父 chunk 上下文。"""
    if not getattr(Config, "RAG_PARENT_CONTEXT_ENHANCE_ENABLED", False):
        return results
    context_scopes = _collect_parent_context_scopes(results)
    if not context_scopes:
        return results

    context_map = await _fetch_parent_contexts(
        es_indexes,
        context_scopes=context_scopes,
    )
    if not context_map:
        return results

    return _enhance_results_with_parent_context(results, context_map)


def _enhance_results_with_parent_context(
    results: List[Dict[str, Any]],
    context_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """把命中的父上下文挂回候选结果。"""
    enhanced_results = []
    for result in results:
        metadata = dict(result.get("metadata") or {})
        context = _lookup_parent_context(metadata, context_map)
        if not context:
            enhanced_results.append(result)
            continue
        enhanced_results.append(_build_result_with_parent_context(result, context))
    return enhanced_results


def _build_result_with_parent_context(
    result: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """构造带父上下文的单条候选结果。"""
    item = result.copy()
    item_metadata = dict(item.get("metadata") or {})
    item_metadata["parent_context"] = context
    item["metadata"] = item_metadata
    trace = dict(item.get("score_trace") or {})
    trace["parent_context_expanded"] = True
    trace["parent_context_chunk_count"] = len(context.get("chunks") or [])
    item["score_trace"] = trace
    return item


def _collect_parent_context_scopes(results: List[Dict[str, Any]]) -> List[Dict[str, List[str]]]:
    """构建父上下文扩展 scope，避免章节过滤串扰文档级父上下文。"""
    document_parent_ids = _collect_document_parent_ids(results)
    section_scopes = _collect_section_parent_scopes(results)
    scopes = _build_parent_context_scopes(document_parent_ids, section_scopes)
    return scopes


def _collect_document_parent_ids(results: List[Dict[str, Any]]) -> List[str]:
    """收集文档级父上下文 parent_id。"""
    document_parent_ids = []
    seen_document_parents = set()
    for result in results:
        metadata = result.get("metadata") or {}
        parent_id = metadata.get("parent_id")
        section_id = metadata.get("section_id")
        if not parent_id or section_id:
            continue
        if parent_id not in seen_document_parents:
            seen_document_parents.add(parent_id)
            document_parent_ids.append(parent_id)
    return document_parent_ids


def _collect_section_parent_scopes(results: List[Dict[str, Any]]) -> Dict[tuple[str, str], Dict[str, List[str]]]:
    """收集章节级父上下文 scope。"""
    section_scopes: Dict[tuple[str, str], Dict[str, List[str]]] = {}
    for result in results:
        metadata = result.get("metadata") or {}
        parent_id = metadata.get("parent_id")
        section_id = metadata.get("section_id")
        if not parent_id or not section_id:
            continue
        section_scopes.setdefault(
            (parent_id, section_id),
            {"parent_ids": [parent_id], "section_ids": [section_id]},
        )
    return section_scopes


def _build_parent_context_scopes(
    document_parent_ids: List[str],
    section_scopes: Dict[tuple[str, str], Dict[str, List[str]]],
) -> List[Dict[str, List[str]]]:
    """组装文档级和章节级 scope 列表。"""
    scopes = _build_document_parent_scopes(document_parent_ids)
    scopes.extend(section_scopes.values())
    return scopes


def _build_document_parent_scopes(document_parent_ids: List[str]) -> List[Dict[str, List[str]]]:
    """构建文档级 scope 列表。"""
    if not document_parent_ids:
        return []
    return [{"parent_ids": document_parent_ids, "section_ids": []}]


async def _fetch_parent_contexts(
    es_indexes: List[str],
    context_scopes: List[Dict[str, List[str]]],
) -> Dict[str, Dict[str, Any]]:
    """批量读取父/章节上下文，并按 parent/section 组合聚合。"""
    if not es_indexes or not context_scopes:
        return {}
    search_tasks = _build_parent_context_search_tasks(es_indexes, context_scopes)
    result_lists = await asyncio.gather(*search_tasks, return_exceptions=True)
    return _group_parent_context_results(result_lists)


def _build_parent_context_search_tasks(
    es_indexes: List[str],
    context_scopes: List[Dict[str, List[str]]],
) -> List[Any]:
    """构建父上下文查询任务列表。"""
    es_service = get_es_service()
    tasks = []
    for es_index in es_indexes:
        for scope in context_scopes:
            tasks.append(
                es_service.search_parent_contexts(
                    index_name=es_index,
                    parent_ids=scope["parent_ids"],
                    section_ids=scope["section_ids"],
                    limit=max(Config.RAG_RERANK_CANDIDATE_LIMIT, len(scope["parent_ids"]) * 3),
                )
            )
    return tasks


def _group_parent_context_results(result_lists: List[Any]) -> Dict[str, Dict[str, Any]]:
    """聚合父上下文查询结果，跳过失败 scope。"""
    grouped: Dict[str, Dict[str, Any]] = {}
    for results in result_lists:
        if isinstance(results, Exception):
            rag_search_logger.warning(
                "[RAG检索] 父上下文单个 scope 扩展失败（已跳过）, error={}",
                str(results),
            )
            _mark_fallback("parent_context_scope", str(results))
            continue
        _merge_parent_context_chunks(grouped, results)
    return grouped


def _merge_parent_context_chunks(
    grouped: Dict[str, Dict[str, Any]],
    chunks: List[Dict[str, Any]],
) -> None:
    """把单个 scope 的 chunk 合并进聚合结果。"""
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        parent_id = metadata.get("parent_id")
        if not parent_id:
            continue
        section_id = metadata.get("section_id") or ""
        key = _parent_context_key(parent_id, section_id)
        context = grouped.setdefault(
            key,
            {
                "parent_id": parent_id,
                "section_id": section_id or None,
                "section_title": metadata.get("section_title", ""),
                "chunks": [],
            }
        )
        context["chunks"].append({
            "id": chunk.get("id"),
            "description": chunk.get("description", ""),
            "score": chunk.get("score", 0),
        })


def _lookup_parent_context(
    metadata: Dict[str, Any],
    context_map: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """按候选 metadata 找到最精确的父/章节上下文。"""
    parent_id = metadata.get("parent_id")
    if not parent_id:
        return None
    section_id = metadata.get("section_id") or ""
    return (
        context_map.get(_parent_context_key(parent_id, section_id))
        or context_map.get(_parent_context_key(parent_id, ""))
    )


def _parent_context_key(parent_id: str, section_id: str) -> str:
    """构建父/章节上下文 map key。"""
    return f"{parent_id}::{section_id}"


def apply_retrieval_context_prerank(
    results: List[Dict[str, Any]],
    retrieval_context: Optional[RetrievalContext] = None
) -> List[Dict[str, Any]]:
    """根据查询拆解上下文做轻量本地预排序，减少 Rerank 前误排。"""
    if not results or not retrieval_context or retrieval_context.query_type != "troubleshooting":
        return results

    terms = _build_context_terms(retrieval_context)
    if not terms:
        return results

    adjusted_results = []
    for result in results:
        adjusted_results.append(_apply_context_prerank_to_result(result, terms))

    adjusted_results.sort(key=_get_rank_score, reverse=True)
    return adjusted_results


def _apply_context_prerank_to_result(
    result: Dict[str, Any],
    terms: List[str],
) -> Dict[str, Any]:
    """把上下文预排序加权应用到单条候选结果。"""
    searchable_text = _build_result_searchable_text(result)
    matched_terms = [term for term in terms if term and term in searchable_text]
    if not matched_terms:
        return result
    boosted_result = result.copy()
    boost = round(min(0.03 * len(matched_terms), 0.15), 4)
    boosted_result["_context_prerank_boost"] = boost
    boosted_result["_context_prerank_matches"] = matched_terms
    boosted_result["score"] = result.get("score", result.get("rrf_score", 0)) + boost
    if "rrf_score" in boosted_result:
        boosted_result["rrf_score"] = result.get("rrf_score", 0) + boost
    return boosted_result


def _build_context_terms(retrieval_context: RetrievalContext) -> List[str]:
    """构建用于本地预排序的上下文词。"""
    terms = []
    for values in [
        retrieval_context.entities or [],
        retrieval_context.symptoms or [],
        retrieval_context.environment_gap or [],
        retrieval_context.time_context or [],
    ]:
        terms.extend(str(value) for value in values if value)
    return terms


def _build_result_searchable_text(result: Dict[str, Any]) -> str:
    """拼接候选可检索文本。"""
    metadata = result.get("metadata", {}) or {}
    features = result.get("features", {}) or {}
    tags = " ".join(str(tag) for tag in features.get("tags", []) or [])
    category = str(features.get("category", ""))
    return " ".join([
        str(result.get("description", "")),
        str(metadata.get("description", "")),
        str(metadata.get("id", "")),
        category,
        tags,
    ])


def _build_retrieval_strategy_profile(
    retrieval_context: Optional[RetrievalContext],
    query_scope: Optional[str] = None,
    route_plan: Optional[List[str]] = None,
    issue_type: Optional[str] = None,
    issue_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建检索策略诊断信息。"""
    base_profile = _build_base_retrieval_strategy_profile(query_scope, route_plan, issue_type, issue_filters)
    if retrieval_context is None:
        return base_profile
    return _build_retrieval_strategy_context_profile(retrieval_context, base_profile)


def _build_base_retrieval_strategy_profile(
    query_scope: Optional[str],
    route_plan: Optional[List[str]],
    issue_type: Optional[str] = None,
    issue_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建无上下文时的检索策略摘要。"""
    return {
        "applied": False,
        "query_type": "",
        "strategy": Config.RAG_RETRIEVAL_STRATEGY,
        "query_scope": query_scope or "local",
        "route_plan": route_plan or ["chunk_retrieval", "rerank"],
        "issue_type": issue_type or "unknown",
        "issue_filters": issue_filters or {},
    }


def _build_retrieval_strategy_context_profile(
    retrieval_context: RetrievalContext,
    base_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """在基础摘要上补充查询上下文信息。"""
    profile = dict(base_profile)
    profile.update({
        "applied": retrieval_context.query_type == "troubleshooting",
        "query_type": retrieval_context.query_type,
        "entities": retrieval_context.entities or [],
        "symptoms": retrieval_context.symptoms or [],
        "environment_gap": retrieval_context.environment_gap or [],
        "time_context": retrieval_context.time_context or [],
        "context_strategy": "context_prerank" if retrieval_context.query_type == "troubleshooting" else "default",
    })
    return profile


async def _rerank_results(
    query_text: str,
    results: List[Dict[str, Any]],
    request_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """对搜索结果进行 Rerank 重排"""
    rerank_service = get_rerank_service()
    try:
        rerank_candidates = _prepare_rerank_candidates(results)
        rerank_results = await _call_rerank_service(
            rerank_service,
            query_text,
            rerank_candidates,
            request_id,
        )
        _merge_rerank_scores(results, rerank_candidates, rerank_results)
    except httpx.HTTPError as e:
        rag_search_logger.warning("[RAG检索] Rerank HTTP 调用失败，使用原始分数, error={}", str(e))
        _mark_fallback("rerank", str(e))

    return results


def _prepare_rerank_candidates(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """准备送入远程 Rerank 的候选列表。"""
    candidate_limit = max(1, Config.RAG_RERANK_CANDIDATE_LIMIT)
    rerank_candidates = results[:candidate_limit]
    _reset_unified_scores(results)
    rag_search_logger.info(
        "[RAG检索] 开始 Rerank 重排, 候选数量: {}/{}",
        len(rerank_candidates),
        len(results)
    )
    return rerank_candidates


async def _call_rerank_service(
    rerank_service: RerankService,
    query_text: str,
    rerank_candidates: List[Dict[str, Any]],
    request_id: Optional[str],
) -> List[Dict[str, Any]]:
    """调用远程 Rerank 服务并返回结果。"""
    rerank_results = await rerank_service.rerank(query_text, rerank_candidates, request_id=request_id)
    rag_search_logger.info("[RAG检索] Rerank 完成, 返回数量: {}", len(rerank_results))
    return rerank_results


def _merge_rerank_scores(
    results: List[Dict[str, Any]],
    rerank_candidates: List[Dict[str, Any]],
    rerank_results: List[Dict[str, Any]],
) -> None:
    """把 Rerank 分数合并回原始结果。"""
    for r in rerank_results:
        idx = r.get("index")
        if idx is not None and idx < len(rerank_candidates):
            results[idx]["score"] = r.get("relevance_score", results[idx]["score"])
    rag_search_logger.info("[RAG检索] Rerank 分数已合并到结果")


def _reset_unified_scores(results: List[Dict[str, Any]]) -> None:
    """将未重排候选分数统一回融合分数尺度，避免原始向量分数污染最终排序。"""
    for result in results:
        if "rrf_score" in result:
            result["score"] = result["rrf_score"]


def _calculate_rerank_candidate_limit(total_candidates: int, top_k: Optional[int]) -> int:
    """计算 provider-safe 的 Rerank 候选数上限。"""
    configured = max(1, Config.RAG_RERANK_CANDIDATE_LIMIT)
    provider_safe = max(1, Config.RAG_RERANK_PROVIDER_SAFE_LIMIT)
    requested = max(1, top_k or configured)
    return min(total_candidates, configured, provider_safe, requested)


def _build_rerank_decision(
    results: List[Dict[str, Any]],
    candidate_count: int,
    request_top_k: Optional[int] = None,
) -> Dict[str, Any]:
    """构建 Rerank 决策诊断信息，用于 SEE 和评测调参。"""
    first_score = _get_rank_score(results[0]) if results else 0.0
    second_score = _get_rank_score(results[1]) if len(results) > 1 else 0.0
    score_gap = round(first_score - second_score, 6)
    skip_enabled = Config.RAG_RERANK_SKIP_CONFIDENT_ENABLED
    skipped = bool(skip_enabled and len(results) >= 2 and score_gap >= Config.RAG_RERANK_SKIP_MIN_GAP)
    return {
        "skipped": skipped,
        "reason": "confident_rrf_leader" if skipped else "",
        "candidate_count": 0 if skipped else candidate_count,
        "score_gap": score_gap,
        "top1_score": round(first_score, 6),
        "top2_score": round(second_score, 6),
        "threshold": Config.RAG_RERANK_SKIP_MIN_GAP,
        "skip_enabled": skip_enabled,
        "cap_policy": {
            "configured_limit": Config.RAG_RERANK_CANDIDATE_LIMIT,
            "provider_safe_limit": Config.RAG_RERANK_PROVIDER_SAFE_LIMIT,
            "requested_top_k": request_top_k,
        },
    }


def _get_rank_score(result: Dict[str, Any]) -> float:
    """读取用于 Rerank skip 判断的排序分数。"""
    return float(result.get("rrf_score", result.get("score", 0)) or 0)


def _should_skip_rerank_for_confident_leader(results: List[Dict[str, Any]]) -> bool:
    """RRF 第一名明显领先时跳过远程 Rerank。"""
    return _build_rerank_decision(
        results,
        _calculate_rerank_candidate_limit(len(results), Config.RAG_RERANK_TOP_K),
        Config.RAG_RERANK_TOP_K,
    )["skipped"]


async def _boost_features(query_text: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """执行特征加权"""
    feature_boost_service = get_feature_boost_service()
    if Config.RAG_RETRIEVAL_STRATEGY == "ragflow_weighted":
        results = feature_boost_service.apply_local_tag_rank_feature(query_text, results)
    boosted_results = await feature_boost_service.boost(
        query=query_text,
        results=results,
        enable_fixed=True,
        enable_semantic=True
    )
    rag_search_logger.info(f"[RAG检索] 特征加权完成, 结果数量={len(boosted_results)}")

    if Config.DEBUG:
        for i, r in enumerate(boosted_results[:3]):
            rag_search_logger.info(
                f"[RAG检索] [DEBUG] 特征加权结果{i+1}: id={r.get('id')}, "
                f"score={r.get('score')}, match_count={r.get('_feature_match_count', 0)}, "
                f"fixed_boost={r.get('_fixed_boost', 0)}, semantic_boost={r.get('_semantic_boost', 'N/A')}"
            )
    return boosted_results


def apply_domain_rerank_rules(query_text: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    应用轻量领域精排规则

    用于修正高相似候选之间的稳定误排，不依赖额外 LLM 调用。
    """
    if not _should_apply_domain_rerank_rules(query_text, results):
        return results

    approval_terms = ["申请表", "法人", "缺失材料", "材料预审", "预审", "经营范围"]
    expiry_terms = ["到期", "年检", "续办", "提醒"]

    adjusted_results = []
    for result in results:
        adjusted_results.append(_apply_domain_rerank_boost(result, approval_terms, expiry_terms))

    adjusted_results.sort(key=lambda item: item.get("score", 0), reverse=True)
    return adjusted_results


def _should_apply_domain_rerank_rules(query_text: str, results: List[Dict[str, Any]]) -> bool:
    """判断是否需要应用领域精排规则。"""
    if not query_text or not results:
        return False
    query = query_text.lower()
    approval_terms = ["申请表", "法人", "缺失材料", "材料预审", "预审", "经营范围"]
    return any(term in query for term in approval_terms)


def _apply_domain_rerank_boost(
    result: Dict[str, Any],
    approval_terms: List[str],
    expiry_terms: List[str],
) -> Dict[str, Any]:
    """对单条结果应用领域精排加权。"""
    description = str(result.get("description", ""))
    features = result.get("features", {}) or {}
    tags_text = " ".join(str(tag) for tag in features.get("tags", []) or [])
    searchable_text = f"{description} {tags_text}"
    boost = 0.0
    if "行政审批" in searchable_text or "材料预审" in searchable_text:
        boost += 0.08
    if any(term in searchable_text for term in approval_terms):
        boost += 0.04
    if any(term in searchable_text for term in expiry_terms) and not any(term in searchable_text for term in ["申请表", "法人", "缺失材料"]):
        boost -= 0.04
    if not boost:
        return result
    boosted_result = result.copy()
    boosted_result["_domain_rule_boost"] = round(boost, 4)
    boosted_result["score"] = result.get("score", 0) + boost
    return boosted_result


def _filter_by_threshold(results: List[Dict[str, Any]], threshold: Optional[float] = None) -> List[Dict[str, Any]]:
    """过滤低于阈值的结果"""
    effective_threshold = threshold if threshold is not None else Config.RERANK_THRESHOLD
    rag_search_logger.info("[RAG检索] 阈值过滤: threshold={}", effective_threshold)
    filtered_results = [
        r for r in results
        if r.get("score", 0) >= effective_threshold
    ]
    rag_search_logger.info("[RAG检索] 阈值过滤后: {} -> {}", len(results), len(filtered_results))
    return filtered_results


def _build_search_results(filtered_results: List[Dict[str, Any]]) -> List[SearchResult]:
    """构建检索响应结果"""
    return [
        SearchResult(
            metadata=r["metadata"],
            description=r["description"],
            score=r["score"],
            features=r.get("features"),
            score_trace=r.get("score_trace")
        )
        for r in filtered_results
    ]


def _attach_weighted_strategy_trace(
    results: List[Dict[str, Any]],
    query_text: str,
) -> List[Dict[str, Any]]:
    """补充 weighted strategy 的标签命中 trace。"""
    if not results:
        return results
    enriched_results = []
    for result in results:
        item = result.copy()
        tags = (item.get("features") or {}).get("tags", []) or []
        matches = [tag for tag in tags if str(tag) and str(tag) in (query_text or "")]
        trace = dict(item.get("score_trace") or {})
        trace["weighted_strategy"] = Config.RAG_RETRIEVAL_STRATEGY
        trace["query_contains_tags"] = bool(matches)
        trace["query_tag_matches"] = matches
        item["score_trace"] = trace
        enriched_results.append(item)
    return enriched_results
