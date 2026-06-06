"""
RAG 语义优化检索路由模块

定义查询优化和优化检索接口

@author lvdaxianerplus
@date 2026-06-01
"""

import asyncio
import time
import uuid
from typing import Dict, List

from fastapi import APIRouter

from app.config import Config
from app.models.schemas import (
    OptimizeSearchData,
    OptimizeSearchRequest,
    OptimizeSearchResponse,
    RecommendationResult,
    SearchRequest,
    SearchResult,
)
from app.services.rag_search_pipeline_service import get_embedding_service
from app.services.rag_search_pipeline_service import RetrievalContext
from app.services.rag_search_pipeline_service import run_search_pipeline
from app.services.rag_search_pipeline_service import run_search_pipeline_with_profile
from app.services.optimize_history_service import OptimizeHistoryRecordInput, get_optimize_history_service
from app.services.query_optimize_service import get_query_optimize_service
from app.services.retrieval_trace_service import build_query_scope_trace
from app.utils.logger import rag_search_logger


router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


@router.post("/{id}/search/optimize", response_model=OptimizeSearchResponse)
async def optimize_search(id: str, request: OptimizeSearchRequest):
    """
    语义优化检索接口

    @param id - 用户ID
    @param request - 语义优化检索请求
    @returns 优化检索结果
    """
    start_time = time.time()
    request_id = uuid.uuid4().hex
    rag_search_logger.info("[语义优化] 原始查询: {}", request.input)

    original_context_task = asyncio.create_task(_run_original_query_context(id, request))
    optimized_context = await _run_optimized_search_context(id, request, request_id)
    original_context = await original_context_task
    comparison = _build_comparison(
        id,
        request,
        original_context["results"],
        optimized_context,
        start_time
    )
    recommendations = _build_recommendations(
        original_context["results"],
        optimized_context["optimized_results"],
        optimized_context["retrieval_context"]
    )
    optimized_context["recommendations"] = recommendations
    retrieval_strategy = _primary_retrieval_strategy(optimized_context)
    see_trace = _build_see_trace(original_context, optimized_context, comparison)
    _log_optimize_counts(original_context["results"], optimized_context["optimized_results"])

    return OptimizeSearchResponse(
        code=200,
        message="success",
        data=OptimizeSearchData(
            request_id=request_id,
            original_query=request.input,
            optimized_query=optimized_context["optimized_query"],
            intent=optimized_context["optimize_result"].get("intent", ""),
            query_scope=optimized_context["optimize_result"].get("query_scope", "local"),
            route_plan=optimized_context["optimize_result"].get("route_plan", {}),
            issue_type=optimized_context["optimize_result"].get("issue_type", "unknown"),
            issue_route=optimized_context["optimize_result"].get("issue_route", {}),
            issue_filters=retrieval_strategy.get("issue_filters", {}),
            cot_plan=optimized_context["optimize_result"].get("cot_plan", []),
            expanded_queries=optimized_context["expanded_queries"],
            see_trace=see_trace,
            original_results=original_context["results"],
            optimized_results=optimized_context["optimized_results"],
            recommendations=recommendations,
            comparison=comparison,
            fallback_used=optimized_context["optimize_result"].get("fallback_used", False)
        )
    )


async def _run_original_query_pipeline(id: str, request: OptimizeSearchRequest) -> List[SearchResult]:
    """
    执行原始查询检索

    @param id - 用户ID
    @param request - 优化检索请求
    @returns 原始查询检索结果
    """
    original_request = SearchRequest(
        input=request.input,
        type=request.type,
        topK=request.topK,
        threshold=request.threshold,
        enableFeatureBoost=request.enableFeatureBoost
    )
    return await run_search_pipeline(id, original_request)


async def _run_original_query_context(id: str, request: OptimizeSearchRequest) -> dict:
    """
    执行原始查询检索并返回 profile，用于 SEE 展示召回通道状态。

    @param id - 用户ID
    @param request - 优化检索请求
    @returns 原始查询检索结果和 profile
    """
    original_request = SearchRequest(
        input=request.input,
        type=request.type,
        topK=request.topK,
        threshold=request.threshold,
        enableFeatureBoost=request.enableFeatureBoost
    )
    pipeline_result = await run_search_pipeline_with_profile(id, original_request)
    return {
        "results": pipeline_result.results,
        "profile": pipeline_result.profile
    }


async def _run_optimized_search_context(id: str, request: OptimizeSearchRequest, request_id: str) -> dict:
    """
    执行查询优化和优化查询检索

    @param id - 用户ID
    @param request - 优化检索请求
    @returns 优化查询上下文
    """
    optimize_result = await get_query_optimize_service().optimize(request.input)
    optimized_query = optimize_result["optimized_query"]
    expanded_queries = _normalize_optimized_queries(
        optimize_result.get("expanded_queries", []),
        optimized_query
    )
    retrieval_context = _extract_retrieval_context(optimize_result)
    rag_search_logger.info("[语义优化] 优化后查询: {}", optimized_query)
    optimized_results, query_result_counts, query_profiles = await _run_optimized_query_pipeline(
        id=id,
        base_request=request,
        queries=expanded_queries,
        retrieval_context=retrieval_context,
        request_id=request_id,
        query_scope=optimize_result.get("query_scope", "local"),
        route_plan=(optimize_result.get("route_plan") or {}).get("steps", []),
        issue_type=optimize_result.get("issue_type", "unknown"),
    )
    return {
        "optimize_result": optimize_result,
        "optimized_query": optimized_query,
        "expanded_queries": expanded_queries,
        "optimized_results": optimized_results,
        "query_result_counts": query_result_counts,
        "query_profiles": query_profiles,
        "retrieval_context": retrieval_context
    }


def _build_comparison(
    id: str,
    request: OptimizeSearchRequest,
    original_results: List[SearchResult],
    optimized_context: dict,
    start_time: float
) -> dict:
    """
    构建优化检索对比信息

    @param id - 用户ID
    @param request - 优化检索请求
    @param original_results - 原始检索结果
    @param optimized_context - 优化检索上下文
    @param start_time - 请求开始时间
    @returns 对比信息
    """
    comparison = _build_comparison_metrics(original_results, optimized_context["optimized_results"], start_time)
    history_record = get_optimize_history_service().add_record(OptimizeHistoryRecordInput(
        user_id=id,
        original_query=request.input,
        optimized_query=optimized_context["optimized_query"],
        original_count=len(original_results),
        optimized_count=len(optimized_context["optimized_results"]),
        fallback_used=optimized_context["optimize_result"].get("fallback_used", False)
    ))
    comparison["history_id"] = history_record["history_id"]
    return comparison


def _build_comparison_metrics(
    original_results: List[SearchResult],
    optimized_results: List[SearchResult],
    start_time: float
) -> dict:
    """
    构建优化检索对比指标

    @param original_results - 原始检索结果
    @param optimized_results - 优化检索结果
    @param start_time - 请求开始时间
    @returns 对比指标
    """
    return {
        "original_count": len(original_results),
        "optimized_count": len(optimized_results),
        "latency_ms": int((time.time() - start_time) * 1000)
    }


def _build_see_trace(original_context: dict, optimized_context: dict, comparison: dict) -> List[dict]:
    """
    构建 SEE 可视追踪

    @param optimized_context - 优化检索上下文
    @param comparison - 对比指标
    @returns SEE 追踪列表
    """
    optimize_result = optimized_context["optimize_result"]
    see_trace = list(optimize_result.get("see_trace", []))
    see_trace.insert(
        1,
        build_query_scope_trace(
            query_scope=optimize_result.get("query_scope", "local"),
            route_plan=optimize_result.get("route_plan", {}).get("steps", []),
        ),
    )
    see_trace.extend(_build_retrieval_trace_items(original_context, optimized_context, comparison))
    return see_trace


def _build_retrieval_trace_items(original_context: dict, optimized_context: dict, comparison: dict) -> List[dict]:
    """
    构建检索和对比追踪节点

    @param optimized_context - 优化检索上下文
    @param comparison - 对比指标
    @returns 追踪节点列表
    """
    retrieval_strategy = _primary_retrieval_strategy(optimized_context)
    trace_items = [
        {
            "stage": "original_retrieval",
            "summary": "使用原始查询执行混合检索",
            "metrics": {
                "result_count": comparison["original_count"],
                "profile": original_context["profile"]
            }
        },
        {
            "stage": "global_retrieval",
            "summary": "全局检索摘要与证据展开信息",
            "metrics": optimized_context["query_profiles"].get(
                optimized_context["expanded_queries"][0],
                {},
            ).get("retrieval_strategy", {}).get("global_retrieval", {}),
        },
        {
            "stage": "optimized_retrieval",
            "summary": "使用优化查询执行混合检索",
            "metrics": {
                "result_count": comparison["optimized_count"],
                "query_count": len(optimized_context["expanded_queries"]),
                "query_scope": optimized_context["optimize_result"].get("query_scope", "local"),
                "route_plan": optimized_context["optimize_result"].get("route_plan", {}),
                "issue_type": optimized_context["optimize_result"].get("issue_type", "unknown"),
                "issue_filters": retrieval_strategy.get("issue_filters", {}),
                "query_result_counts": optimized_context["query_result_counts"],
                "query_profiles": optimized_context["query_profiles"]
            }
        },
        {
            "stage": "comparison",
            "summary": "对比两次检索结果数量和耗时",
            "metrics": comparison
        }
    ]
    trace_items.insert(2, _build_recommendation_trace_item(optimized_context))
    return trace_items


def _primary_retrieval_strategy(optimized_context: dict) -> dict:
    """读取首个优化查询的检索策略 profile。"""
    expanded_queries = optimized_context.get("expanded_queries") or []
    if not expanded_queries:
        return {}
    query_profile = (optimized_context.get("query_profiles") or {}).get(expanded_queries[0], {})
    return query_profile.get("retrieval_strategy", {}) or {}


def _log_optimize_counts(original_results: List[SearchResult], optimized_results: List[SearchResult]) -> None:
    """
    记录优化检索结果数量

    @param original_results - 原始检索结果
    @param optimized_results - 优化检索结果
    """
    rag_search_logger.info("[语义优化] 第一次检索结果数量: {}", len(original_results))
    rag_search_logger.info("[语义优化] 第二次检索结果数量: {}", len(optimized_results))


def _normalize_optimized_queries(expanded_queries: List[str], optimized_query: str) -> List[str]:
    """
    规范化优化查询列表，保序去重并确保包含 optimized_query

    @param expanded_queries - LLM 返回的扩展查询
    @param optimized_query - 主优化查询
    @returns 可执行的优化查询列表
    """
    queries = [optimized_query, *expanded_queries]
    normalized = []
    seen = set()
    for query in queries:
        if not query:
            continue
        clean_query = str(query).strip()
        if clean_query and clean_query not in seen:
            seen.add(clean_query)
            normalized.append(clean_query)
    limited_queries = (normalized or [optimized_query])[:max(1, Config.RAG_OPTIMIZE_QUERY_LIMIT)]
    return limited_queries


async def _run_optimized_query_pipeline(
    id: str,
    base_request: OptimizeSearchRequest,
    queries: List[str],
    retrieval_context: RetrievalContext | None = None,
    request_id: str | None = None,
    query_scope: str | None = None,
    route_plan: List[str] | None = None,
    issue_type: str | None = None,
) -> tuple[List[SearchResult], Dict[str, int], Dict[str, dict]]:
    """
    使用多个优化查询执行检索并合并结果

    @param id - 用户ID
    @param base_request - 优化检索请求
    @param queries - 优化查询列表
    @returns 合并后的结果和每个查询的结果数
    """
    query_requests = _build_query_requests(base_request, queries, query_scope, route_plan, issue_type)
    prefetched_vectors = await _prefetch_query_vectors(queries)
    pipeline_results = await asyncio.gather(*[
        run_search_pipeline_with_profile(
            id,
            query_request,
            prefetched_query_vector=prefetched_vectors.get(query_request.input),
            retrieval_context=retrieval_context,
            request_id=request_id
        )
        for query_request in query_requests
    ])
    result_lists = [pipeline_result.results for pipeline_result in pipeline_results]

    query_result_counts = {
        queries[index]: len(results)
        for index, results in enumerate(result_lists)
    }
    query_profiles = {
        queries[index]: pipeline_result.profile
        for index, pipeline_result in enumerate(pipeline_results)
    }
    merged_results = _merge_optimized_results(result_lists, base_request.topK)
    return merged_results, query_result_counts, query_profiles


def _extract_retrieval_context(optimize_result: dict) -> RetrievalContext | None:
    """从查询优化 SEE 拆解阶段提取检索策略上下文。"""
    for item in optimize_result.get("see_trace", []) or []:
        if item.get("stage") != "query_decomposition":
            continue
        metrics = item.get("metrics", {}) or {}
        return RetrievalContext(
            query_type=metrics.get("query_type", ""),
            entities=metrics.get("entities", []),
            symptoms=metrics.get("symptoms", []),
            environment_gap=metrics.get("environment_gap", []),
            time_context=metrics.get("time_context", []),
        )
    return None


def _build_recommendations(
    original_results: List[SearchResult],
    optimized_results: List[SearchResult],
    retrieval_context: RetrievalContext | None
) -> List[RecommendationResult]:
    """从原始和优化召回中生成相关推荐。"""
    primary_ids = {
        _result_id(result)
        for result in optimized_results
        if _result_id(result)
    }
    candidates = []
    seen_ids = set()
    for result in [*optimized_results, *original_results]:
        doc_id = _result_id(result)
        if doc_id and doc_id in seen_ids:
            continue
        if doc_id:
            seen_ids.add(doc_id)
        if doc_id and doc_id in primary_ids:
            continue
        recommendation_score, reason = _score_recommendation(result, retrieval_context)
        candidates.append((recommendation_score, result, reason))

    candidates.sort(key=lambda item: item[0], reverse=True)
    top_k = max(0, Config.RAG_RECOMMENDATION_TOP_K)
    recommendations = []
    for score, result, reason in candidates[:top_k]:
        recommendations.append(RecommendationResult(
            metadata=result.metadata,
            description=result.description,
            score=round(max(float(result.score), score), 4),
            features=result.features,
            reason=reason
        ))
    return recommendations


def _score_recommendation(
    result: SearchResult,
    retrieval_context: RetrievalContext | None
) -> tuple[float, str]:
    """计算推荐分并生成推荐原因。"""
    if retrieval_context is None:
        return float(result.score or 0), "与原始问题语义相关"

    terms = [
        *(retrieval_context.entities or []),
        *(retrieval_context.symptoms or []),
        *(retrieval_context.environment_gap or []),
        *(retrieval_context.time_context or []),
    ]
    searchable_text = " ".join([
        result.description,
        str(result.metadata.get("description", "")),
        " ".join(str(tag) for tag in (result.features or {}).get("tags", []) or []),
        str((result.features or {}).get("category", "")),
    ])
    matched_terms = [term for term in terms if term and term in searchable_text]
    score = float(result.score or 0) + min(0.08 * len(matched_terms), 0.32)
    if matched_terms:
        return score, "同属{}类问题，命中 {}".format(
            retrieval_context.query_type or "相关",
            "/".join(matched_terms[:4])
        )
    return score, "与原始问题语义相关"


def _result_id(result: SearchResult) -> str:
    """读取检索结果业务 ID。"""
    return str(result.metadata.get("id") or result.metadata.get("doc_id") or "")


def _build_recommendation_trace_item(optimized_context: dict) -> dict:
    """构建推荐 SEE 追踪节点。"""
    recommendations = optimized_context.get("recommendations", [])
    retrieval_context = optimized_context.get("retrieval_context")
    return {
        "stage": "recommendation",
        "summary": "根据原始和优化召回生成相关推荐",
        "metrics": {
            "recommendation_count": len(recommendations),
            "recommendation_kind": "document",
            "recommendation_budget_ms": Config.RAG_RECOMMENDATION_TIMEOUT_MS,
            "recommendation_source": "optimized_retrieval",
            "top_k": Config.RAG_RECOMMENDATION_TOP_K,
            "query_type": retrieval_context.query_type if retrieval_context else "",
        }
    }


async def _prefetch_query_vectors(queries: List[str]) -> Dict[str, List[float]]:
    """批量预取优化查询向量，减少扩展查询带来的外部 Embedding 调用次数。"""
    if len(queries) <= 1:
        return {}

    try:
        vectors = await get_embedding_service().encode(queries)
    except Exception as e:
        rag_search_logger.warning("[语义优化] 批量预取查询向量失败，降级为逐条向量化, error={}", str(e))
        return {}

    if not _is_prefetched_vector_batch(vectors, len(queries)):
        rag_search_logger.warning("[语义优化] 批量预取查询向量格式异常，降级为逐条向量化")
        return {}

    return {
        query: vector
        for query, vector in zip(queries, vectors)
    }


def _is_prefetched_vector_batch(vectors: object, expected_count: int) -> bool:
    """校验批量向量结果形状。"""
    return (
        isinstance(vectors, list)
        and len(vectors) == expected_count
        and all(isinstance(vector, list) for vector in vectors)
    )


def _build_query_requests(
    base_request: OptimizeSearchRequest,
    queries: List[str],
    query_scope: str | None = None,
    route_plan: List[str] | None = None,
    issue_type: str | None = None,
) -> List[SearchRequest]:
    """
    构建优化查询检索请求

    @param base_request - 优化检索请求
    @param queries - 优化查询列表
    @returns 检索请求列表
    """
    return [
        SearchRequest(
            input=query,
            type=base_request.type,
            topK=base_request.topK,
            threshold=base_request.threshold,
            enableFeatureBoost=base_request.enableFeatureBoost,
            query_scope=query_scope,
            route_plan=route_plan or [],
            issue_type=getattr(base_request, "issue_type", None) or issue_type,
        )
        for query in queries
    ]


def _merge_optimized_results(result_lists: List[List[SearchResult]], top_k: int) -> List[SearchResult]:
    """
    合并多查询结果并按文档 ID 去重

    @param result_lists - 多个查询的检索结果
    @param top_k - 最大返回数量
    @returns 合并后的检索结果
    """
    merged_results = []
    seen_ids = set()
    for results in result_lists:
        for result in results:
            doc_id = result.metadata.get("id") or result.metadata.get("doc_id")
            if doc_id and doc_id in seen_ids:
                continue
            if doc_id:
                seen_ids.add(doc_id)
            merged_results.append(result)
            if len(merged_results) >= (top_k or Config.RERANK_TOP_K):
                return merged_results

    return merged_results
