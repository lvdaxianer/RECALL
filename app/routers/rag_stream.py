"""
RAG 流式优化检索路由

将查询优化和检索过程以 SSE 事件形式输出。

@author lvdaxianerplus
@date 2026-06-02
"""

import asyncio
import uuid
from dataclasses import asdict
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import OptimizeSearchRequest, SearchRequest, SearchResult
from app.routers.rag_optimize import _build_recommendations
from app.routers.rag_optimize import _extract_retrieval_context
from app.routers.rag_optimize import _merge_optimized_results
from app.routers.rag_optimize import _normalize_optimized_queries
from app.services.query_optimize_service import get_query_optimize_service
from app.services.rag_search_pipeline_service import RetrievalContext
from app.services.rag_search_pipeline_service import SearchPipelineResult
from app.services.rag_search_pipeline_service import run_search_pipeline_with_profile
from app.services.retrieval_trace_service import build_query_scope_trace
from app.services.retrieval_trace_service import build_retrieval_strategy_trace
from app.services.sse_event_service import build_event, encode_sse_event

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])
RAG_STREAM_FAILED_CODE = "RAG_STREAM_FAILED"
RAG_STREAM_FAILED_MESSAGE = "优化检索流执行失败，已结束当前请求"


@router.post("/{user_id}/search/optimize/stream")
async def optimize_search_stream(user_id: str, request: OptimizeSearchRequest):
    """
    流式语义优化检索接口

    @param user_id - 用户 ID
    @param request - 语义优化检索请求
    @returns SSE 流式事件响应
    """
    request_id = f"req_{uuid.uuid4().hex}"

    async def event_generator() -> AsyncIterator[str]:
        state = {"sequence": 1}

        try:
            async for event in _generate_optimize_events(user_id, request, request_id, state):
                yield event
        except Exception:
            yield _failed_event(user_id, request_id, "query.optimize", state["sequence"])

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _generate_optimize_events(
    user_id: str,
    request: OptimizeSearchRequest,
    request_id: str,
    state: dict[str, int],
) -> AsyncIterator[str]:
    """按固定顺序生成优化检索 SSE 事件。"""
    yield _emit(state, "request.created", user_id, request_id, _request_payload(request))

    optimize_result = await get_query_optimize_service().optimize(request.input)
    optimized_query = optimize_result.get("optimized_query", request.input)
    expanded_queries = _normalize_optimized_queries(
        optimize_result.get("expanded_queries", []),
        optimized_query,
    )
    retrieval_context = _extract_retrieval_context(optimize_result)
    yield _emit(
        state,
        "query.decomposition",
        user_id,
        request_id,
        _query_payload(optimize_result, expanded_queries, retrieval_context),
    )
    yield _emit(
        state,
        "retrieval_strategy",
        user_id,
        request_id,
        _retrieval_strategy_payload(optimize_result),
    )

    yield _emit(state, "retrieval.original.started", user_id, request_id, {"query": request.input})
    original_result = await _run_original_stream_search(user_id, request, request_id)
    yield _emit(
        state,
        "retrieval.original.completed",
        user_id,
        request_id,
        {"result_count": len(original_result.results), "profile": original_result.profile},
    )

    yield _emit(state, "retrieval.optimized.started", user_id, request_id, {"queries": expanded_queries})
    optimized_result = await _run_optimized_stream_search(
        user_id,
        request,
        request_id,
        expanded_queries,
        retrieval_context,
        query_scope=optimize_result.get("query_scope", "local"),
        route_plan=(optimize_result.get("route_plan") or {}).get("steps", []),
    )
    yield _emit(state, "retrieval.optimized.completed", user_id, request_id, _optimized_payload(optimized_result))
    yield _emit(state, "rerank.completed", user_id, request_id, _rerank_payload(optimized_result["query_profiles"]))

    recommendations = _build_recommendations(
        original_result.results,
        optimized_result["results"],
        retrieval_context,
    )
    yield _emit(state, "recommendation.completed", user_id, request_id, _recommendation_payload(recommendations))
    yield _emit(
        state,
        "answer.completed",
        user_id,
        request_id,
        {
            "request_id": request_id,
            "result_count": len(optimized_result["results"]),
            "recommendation_count": len(recommendations),
        },
    )


async def _run_original_stream_search(
    user_id: str,
    request: OptimizeSearchRequest,
    request_id: str,
) -> SearchPipelineResult:
    """执行原始查询检索。"""
    return await run_search_pipeline_with_profile(
        user_id,
        _build_search_request(request, request.input),
        request_id=request_id,
    )


async def _run_optimized_stream_search(
    user_id: str,
    request: OptimizeSearchRequest,
    request_id: str,
    queries: list[str],
    retrieval_context: RetrievalContext | None,
    query_scope: str | None = None,
    route_plan: list[str] | None = None,
) -> dict:
    """并发执行优化查询检索并合并结果。"""
    query_requests = [
        _build_search_request(request, query, query_scope=query_scope, route_plan=route_plan)
        for query in queries
    ]
    pipeline_results = await asyncio.gather(*[
        run_search_pipeline_with_profile(
            user_id,
            query_request,
            retrieval_context=retrieval_context,
            request_id=request_id,
        )
        for query_request in query_requests
    ])
    result_lists = [pipeline_result.results for pipeline_result in pipeline_results]
    return {
        "results": _merge_optimized_results(result_lists, request.topK),
        "query_result_counts": _query_result_counts(queries, result_lists),
        "query_profiles": _query_profiles(queries, pipeline_results),
    }


def _emit(state: dict[str, int], event_name: str, user_id: str, request_id: str, payload: dict) -> str:
    """构建并编码一条 SSE 事件。"""
    event = build_event(
        event=event_name,
        user_id=user_id,
        request_id=request_id,
        sequence=state["sequence"],
        payload=payload,
    )
    state["sequence"] += 1
    return encode_sse_event(event)


def _failed_event(user_id: str, request_id: str, stage: str, sequence: int) -> str:
    """构建失败事件，避免向客户端输出 traceback 或敏感异常内容。"""
    return encode_sse_event(
        build_event(
            event="request.failed",
            user_id=user_id,
            request_id=request_id,
            sequence=sequence,
            payload={
                "stage": stage,
                "error_code": RAG_STREAM_FAILED_CODE,
                "message": RAG_STREAM_FAILED_MESSAGE,
                "fallback_used": True,
            },
        )
    )


def _request_payload(request: OptimizeSearchRequest) -> dict:
    """构建请求创建事件负载。"""
    return {"input": request.input, "type": request.type, "topK": request.topK}


def _query_payload(
    optimize_result: dict,
    expanded_queries: list[str],
    retrieval_context: RetrievalContext | None,
) -> dict:
    """构建查询拆解事件负载。"""
    return {
        "intent": optimize_result.get("intent", ""),
        "cot_plan": optimize_result.get("cot_plan", []),
        "expanded_queries": expanded_queries,
        "query_scope": optimize_result.get("query_scope", "local"),
        "route_plan": optimize_result.get("route_plan", {}),
        "retrieval_context": asdict(retrieval_context) if retrieval_context is not None else {},
        "fallback_used": optimize_result.get("fallback_used", False),
    }


def _build_search_request(
    base_request: OptimizeSearchRequest,
    query: str,
    query_scope: str | None = None,
    route_plan: list[str] | None = None,
) -> SearchRequest:
    """由优化检索请求构建普通检索请求。"""
    return SearchRequest(
        input=query,
        type=base_request.type,
        topK=base_request.topK,
        threshold=base_request.threshold,
        enableFeatureBoost=base_request.enableFeatureBoost,
        query_scope=query_scope,
        route_plan=route_plan or [],
    )


def _query_result_counts(queries: list[str], result_lists: list[list[SearchResult]]) -> dict[str, int]:
    """构建每个优化查询的结果数量。"""
    return {
        query: len(result_lists[index])
        for index, query in enumerate(queries)
    }


def _query_profiles(queries: list[str], pipeline_results: list[SearchPipelineResult]) -> dict[str, dict]:
    """构建每个优化查询的检索 profile。"""
    return {
        query: pipeline_result.profile
        for query, pipeline_result in zip(queries, pipeline_results)
    }


def _optimized_payload(optimized_result: dict) -> dict:
    """构建优化检索完成事件负载。"""
    return {
        "result_count": len(optimized_result["results"]),
        "result_ids": _result_ids(optimized_result["results"]),
        "query_result_counts": optimized_result["query_result_counts"],
        "query_profiles": optimized_result["query_profiles"],
    }


def _retrieval_strategy_payload(optimize_result: dict) -> dict:
    """构建 retrieval strategy 事件负载。"""
    route_plan = optimize_result.get("route_plan", {}) or {}
    summary_trace = build_query_scope_trace(
        query_scope=optimize_result.get("query_scope", "local"),
        route_plan=route_plan.get("steps", []),
    )
    strategy_trace = build_retrieval_strategy_trace(
        strategy=route_plan.get("strategy", "rrf"),
        weights={
            "text": 0.35,
            "vector": 0.55,
            "graph": 0.10,
        },
        candidate_count=0,
        rerank_cap=0,
    )
    return {
        "query_scope": summary_trace["metrics"]["query_scope"],
        "route_plan": summary_trace["metrics"]["route_plan"],
        "summary": summary_trace["summary"],
        "strategy_summary": strategy_trace["summary"],
        "strategy": strategy_trace["metrics"]["strategy"],
    }


def _result_ids(results: list[SearchResult]) -> list[str]:
    """提取检索结果业务 ID。"""
    return [
        item.metadata.get("id") or item.metadata.get("doc_id")
        for item in results
        if item.metadata.get("id") or item.metadata.get("doc_id")
    ]


def _rerank_payload(query_profiles: dict[str, dict]) -> dict:
    """构建 Rerank 完成事件负载。"""
    last_profile = next(reversed(query_profiles.values()), {})
    decision = last_profile.get("rerank_decision", {})
    return {
        "candidate_count": last_profile.get("counts", {}).get("rerank", 0),
        "skipped": decision.get("skipped", False),
        "reason": decision.get("reason", ""),
        "timings_ms": last_profile.get("timings_ms", {}),
    }


def _recommendation_payload(recommendations: list[SearchResult]) -> dict:
    """构建推荐完成事件负载。"""
    return {
        "recommendation_count": len(recommendations),
        "recommended_ids": [
            item.metadata.get("id") or item.metadata.get("doc_id")
            for item in recommendations
        ],
    }
