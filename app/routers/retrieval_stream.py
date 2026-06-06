"""
Retrieval SDK 流式检索路由

以 SSE 形式输出检索 trace、答案增量和完成事件。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from pathlib import Path
import asyncio
import re
import time
from typing import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import Config
from app.models.knowledge_base_schemas import AnswerFeedbackRequest, RetrievalSDKSearchRequest
from app.models.schemas import APIResponse
from app.services.answer_cache_service import AnswerCacheService
from app.services.cache_service import get_cache_service
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.retrieval_answer_service import RetrievalAnswerService, filter_results_for_answer
from app.services.retrieval_sdk_service import RetrievalSDKService
from app.services.session_title_service import get_session_title_service
from app.services.session_service import SessionNotFoundError, get_session_service
from app.services.sse_event_service import build_event, encode_sse_event
from app.services.topic_recommendation_service import TopicRecommendationService


router = APIRouter(prefix="/api/v1/retrieval", tags=["RetrievalSDK"])
KNOWLEDGE_BASE_DB_PATH = Config.KNOWLEDGE_BASE_DB_PATH or str(Path("data") / "knowledge_base.sqlite")
CACHED_ANSWER_DELTA_CHARS = 16
REQUEST_RECEIVED_SUMMARY = "收到问题"
QUERY_SCOPE_PROGRESS_SUMMARY = "正在判断这个问题适合怎么查"
RETRIEVAL_PROGRESS_SUMMARY = "正在从选中的知识库里查找相关资料"
RERANK_PROGRESS_SUMMARY = "正在把候选资料按相关性重新排序"
ANSWER_GENERATION_PROGRESS_SUMMARY = "已找到可用资料，正在整理回答"
DEEP_SEARCH_PROGRESS_SUMMARY = "深度检索会拆分问题并多轮检索，可能需要更久"
EXAMPLE_BLOCK_PATTERN = re.compile(r"(用户问[:：].*?(?:模型答[:：].*?)(?=\n\S|$))", flags=re.DOTALL)
CODE_BLOCK_PATTERN = re.compile(r"```.*?```", flags=re.DOTALL)


@router.post("/search/stream")
async def search_stream(request: RetrievalSDKSearchRequest):
    """
    流式知识库检索

    @param request - Retrieval SDK 检索请求
    @returns SSE 流式响应
    """
    _assert_published_knowledge_bases(request.knowledge_base_ids)
    run_id = _create_chat_run(request)
    return StreamingResponse(
        _stream_retrieval_events(
            request,
            run_id,
            retrieval_service=_get_retrieval_sdk_service(),
            answer_service=_get_retrieval_answer_service(),
            answer_cache=_get_answer_cache_service(),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/answers/{request_id}/feedback", response_model=APIResponse)
async def answer_feedback(request_id: str, request: AnswerFeedbackRequest):
    """
    记录答案反馈。

    点赞提升答案缓存信任权重；点踩立即删除答案缓存并绕过短期复用。
    """
    result = _get_answer_cache_service().record_feedback(request_id, request.vote, user_id=request.user_id)
    if request.vote == "dislike":
        get_cache_service().invalidate_rerank_by_request_id(request_id)
    return APIResponse(code=200, message="success", data=result)


@router.get("/answers/cache", response_model=APIResponse)
async def list_answer_cache():
    """列出答案缓存，用于系统管理台。"""
    items = _get_answer_cache_service().list_records()
    return APIResponse(code=200, message="success", data={"items": items, "total": len(items)})


@router.delete("/answers/cache/{cache_key}", response_model=APIResponse)
async def delete_answer_cache(cache_key: str):
    """手动删除指定答案缓存。"""
    result = _get_answer_cache_service().delete(cache_key)
    return APIResponse(code=200, message="success", data=result)


async def _stream_retrieval_events(
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
    retrieval_service: RetrievalSDKService,
    answer_service: RetrievalAnswerService,
    answer_cache: AnswerCacheService | None = None,
    request_id: str | None = None,
    delta_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[str]:
    """Stream request event before expensive retrieval and answer synthesis."""
    request_id = request_id or f"req_{__import__('uuid').uuid4().hex}"
    total_started = time.perf_counter()
    stage_durations: dict[str, float] = {}
    top_k = _resolve_request_top_k(retrieval_service, request)
    retrieval_query = _build_request_retrieval_query(retrieval_service, request)
    sequence = 1
    yield _encode("request.created", sequence, request_id, {"input": request.input, "summary": REQUEST_RECEIVED_SUMMARY})
    sequence += 1
    yield _encode(
        "retrieval.progress",
        sequence,
        request_id,
        {
            "stage": "query_scope",
            "summary": QUERY_SCOPE_PROGRESS_SUMMARY,
        },
    )
    cache_started = time.perf_counter()
    cached = (
        answer_cache.get(retrieval_query, request.knowledge_base_ids, top_k, temperature=request.temperature)
        if answer_cache and not request.deep_search_enabled
        else None
    )
    stage_durations["answer_cache"] = _elapsed_ms(cache_started)
    if cached is not None:
        if answer_cache is not None:
            answer_cache.bind_request_id(cached["cache_key"], request_id)
        recommendation_task = _start_recommendation_task(request, cached["citations"])
        async for event in _stream_cached_answer(
            request,
            run_id,
            request_id,
            cached,
            delta_sleep,
            sequence,
            stage_durations=stage_durations,
            total_duration_ms=_elapsed_ms(total_started),
            recommendation_task=recommendation_task,
        ):
            yield event
        return
    sequence += 1
    yield _encode(
        "retrieval.progress",
        sequence,
        request_id,
        {
            "stage": "deep_search_planning" if request.deep_search_enabled else "retrieval",
            "summary": DEEP_SEARCH_PROGRESS_SUMMARY if request.deep_search_enabled else RETRIEVAL_PROGRESS_SUMMARY,
        },
    )
    retrieval_started = time.perf_counter()
    result = await _run_retrieval_search(retrieval_service, request, retrieval_query, top_k, request_id)
    stage_durations["retrieval"] = _elapsed_ms(retrieval_started)
    result = {
        **result,
        "trace": _with_trace_duration(_public_retrieval_trace(result.get("trace", [])), stage_durations["retrieval"]),
    }
    if request.deep_search_enabled:
        sequence, deep_search_events = _build_deep_search_events(request, run_id, result, request_id, sequence)
        for event in deep_search_events:
            yield event
    answer_results = filter_results_for_answer(request.input, result["results"])
    answer_result = {**result, "results": answer_results}
    recommendation_task = _start_recommendation_task(request, answer_results)
    sequence += 1
    yield _encode("retrieval.trace", sequence, result["request_id"], {"trace": result["trace"]})
    _persist_chat_trace_event(request, run_id, result)
    sequence += 1
    yield _encode(
        "retrieval.progress",
        sequence,
        result["request_id"],
        {
            "stage": "answer_generation",
            "summary": ANSWER_GENERATION_PROGRESS_SUMMARY,
        },
    )
    answer_deltas = []
    answer_started = time.perf_counter()
    async for delta in _iter_answer_deltas(
        answer_service,
        request.input,
        answer_results,
        temperature=request.temperature,
    ):
        if answer_deltas:
            await delta_sleep(Config.STREAM_DELTA_DELAY_SECONDS)
        answer_deltas.append(delta)
        sequence += 1
        _persist_chat_delta_event(request, run_id, answer_result, delta)
        yield _encode("answer.delta", sequence, result["request_id"], delta)
    stage_durations["answer_generation"] = _elapsed_ms(answer_started)
    answer = "".join(str(delta.get("text", "")) for delta in answer_deltas)
    _persist_chat_completed_event(request, run_id, answer_result, answer)
    _store_answer_cache(answer_cache, request, answer_result, answer, retrieval_query, top_k)
    sequence += 1
    yield _encode(
        "answer.completed",
        sequence,
        result["request_id"],
        {
            "duration_ms": _elapsed_ms(total_started),
            "stage_durations_ms": stage_durations,
            "result_count": len(answer_results),
            "results": _citation_results(answer_results),
        },
    )
    sequence += 1
    yield await _finish_recommendation_event(
        recommendation_task,
        sequence,
        result["request_id"],
        request,
        run_id,
    )


def _elapsed_ms(started: float) -> float:
    """计算阶段毫秒耗时。"""
    return round((time.perf_counter() - started) * 1000, 3)


async def _run_retrieval_search(
    retrieval_service: RetrievalSDKService,
    request: RetrievalSDKSearchRequest,
    retrieval_query: str,
    top_k: int,
    request_id: str,
) -> dict:
    """按请求开关执行普通检索或 DeepSearch。"""
    if request.deep_search_enabled and hasattr(retrieval_service, "deep_search_with_engines"):
        return await retrieval_service.deep_search_with_engines(
            input=retrieval_query,
            knowledge_base_ids=request.knowledge_base_ids,
            top_k=top_k,
            request_id=request_id,
            issue_type=request.issue_type,
        )
    return await retrieval_service.search_with_engines(
        input=retrieval_query,
        knowledge_base_ids=request.knowledge_base_ids,
        top_k=top_k,
        request_id=request_id,
        issue_type=request.issue_type,
    )


def _build_deep_search_events(
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
    result: dict,
    request_id: str,
    sequence: int,
) -> tuple[int, list[str]]:
    """把 DeepSearch 公开计划和步骤写入 SSE 与会话事件。"""
    events: list[str] = []
    deep_search = result.get("deep_search") if isinstance(result.get("deep_search"), dict) else {}
    if not deep_search:
        return sequence, events
    plan_payload = {
        "intent": deep_search.get("intent", ""),
        "cot_plan": deep_search.get("cot_plan", []),
        "sub_questions": deep_search.get("sub_questions", []),
    }
    sequence += 1
    events.append(_encode("deep_search.plan", sequence, request_id, plan_payload))
    _persist_chat_named_event(request, run_id, "deep_search.plan", plan_payload, request_id)
    for step in deep_search.get("steps", []) or []:
        sequence += 1
        events.append(_encode("deep_search.step", sequence, request_id, step))
        _persist_chat_named_event(request, run_id, "deep_search.step", step, request_id)
    return sequence, events


def _with_trace_duration(trace: list[dict], duration_ms: float) -> list[dict]:
    """为公开检索 trace 补充检索阶段耗时。"""
    return [
        {
            **item,
            "metrics": {**(item.get("metrics") if isinstance(item.get("metrics"), dict) else {}), "duration_ms": duration_ms},
        }
        for item in trace
    ]


def _start_recommendation_task(
    request: RetrievalSDKSearchRequest,
    answer_results: list[dict],
) -> asyncio.Task:
    """启动非阻塞推荐任务，不让推荐影响主答案生成。"""
    return asyncio.create_task(
        _get_topic_recommendation_service().build(
            query=request.input,
            retrieval_results=answer_results,
            knowledge_base_ids=request.knowledge_base_ids,
        )
    )


async def _finish_recommendation_event(
    recommendation_task: asyncio.Task,
    sequence: int,
    request_id: str,
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
) -> str:
    """在答案完成后用独立预算收尾推荐事件。"""
    timeout_seconds = max(0, Config.RAG_RECOMMENDATION_TIMEOUT_MS) / 1000
    try:
        recommendations = await asyncio.wait_for(asyncio.shield(recommendation_task), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        payload = {
            "recommendation_count": 0,
            "recommendation_budget_ms": Config.RAG_RECOMMENDATION_TIMEOUT_MS,
            "recommendation_source": "topic_taxonomy",
            "reason": "recommendation_timeout",
        }
        _persist_chat_named_event(request, run_id, "recommendation.skipped", payload, request_id)
        return _encode("recommendation.skipped", sequence, request_id, payload)
    except Exception:
        payload = {
            "recommendation_count": 0,
            "recommendation_budget_ms": Config.RAG_RECOMMENDATION_TIMEOUT_MS,
            "recommendation_source": "topic_taxonomy",
            "reason": "recommendation_failed",
        }
        _persist_chat_named_event(request, run_id, "recommendation.skipped", payload, request_id)
        return _encode("recommendation.skipped", sequence, request_id, payload)

    payload = _recommendation_payload(recommendations)
    _persist_chat_named_event(request, run_id, "recommendation.completed", payload, request_id)
    return _encode("recommendation.completed", sequence, request_id, payload)


def _recommendation_payload(recommendations: list) -> dict:
    """构建推荐完成事件负载，包含混合卡片详情。"""
    items = [
        _safe_recommendation_item(item.model_dump() if hasattr(item, "model_dump") else dict(item))
        for item in recommendations
    ]
    return {
        "recommendation_count": len(items),
        "recommendation_kind": "mixed",
        "recommendation_budget_ms": Config.RAG_RECOMMENDATION_TIMEOUT_MS,
        "recommendation_source": "topic_taxonomy",
        "recommendations": items,
        "recommended_ids": [
            item.get("metadata", {}).get("id") or item.get("metadata", {}).get("doc_id")
            for item in items
        ],
    }


def _safe_recommendation_item(item: dict) -> dict:
    """清洗推荐卡片文本，避免绕过引用片段清理。"""
    safe_item = dict(item)
    description = safe_item.get("description")
    if isinstance(description, str):
        safe_item["description"] = _safe_citation_snippet(description)
    metadata = safe_item.get("metadata")
    if isinstance(metadata, dict):
        safe_metadata = dict(metadata)
        document_name = safe_metadata.get("document_name")
        if isinstance(document_name, str):
            safe_metadata["document_name"] = _display_document_name(document_name)
        safe_item["metadata"] = safe_metadata
    return safe_item


def _resolve_request_top_k(retrieval_service: RetrievalSDKService, request: RetrievalSDKSearchRequest) -> int:
    """解析请求 topK，并兼容测试 fake service。"""
    resolver = getattr(retrieval_service, "resolve_top_k", None)
    if callable(resolver):
        return resolver(request.top_k, request.knowledge_base_ids)
    return request.top_k or 5


def _build_request_retrieval_query(
    retrieval_service: RetrievalSDKService,
    request: RetrievalSDKSearchRequest,
) -> str:
    """构建检索 query，并兼容测试 fake service。"""
    builder = getattr(retrieval_service, "build_retrieval_query", None)
    if callable(builder):
        return builder(
            request.input,
            use_context=request.use_context,
            history_questions=request.history_questions,
        )
    if not request.use_context:
        return request.input
    return "；".join([*request.history_questions[-3:], request.input])[:300]


async def _stream_cached_answer(
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
    request_id: str,
    cached: dict,
    delta_sleep: Callable[[float], Awaitable[None]],
    sequence: int,
    stage_durations: dict[str, float] | None = None,
    total_duration_ms: float | None = None,
    recommendation_task: asyncio.Task | None = None,
) -> AsyncIterator[str]:
    """Emit cached answer as SSE while preserving streaming shape."""
    trace = _cached_trace(cached)
    if stage_durations and trace:
        cache_duration = stage_durations.get("answer_cache")
        if cache_duration is not None:
            trace = _with_trace_duration(trace, cache_duration)
    sequence += 1
    result = {
        "request_id": request_id,
        "trace": trace,
        "results": cached["citations"],
    }
    yield _encode("retrieval.trace", sequence, request_id, {"trace": trace})
    _persist_chat_trace_event(request, run_id, result)
    deltas = _split_cached_answer(cached["answer"], cached["citations"])
    for index, delta in enumerate(deltas):
        if index > 0:
            await delta_sleep(Config.STREAM_DELTA_DELAY_SECONDS)
        sequence += 1
        _persist_chat_delta_event(request, run_id, result, delta)
        yield _encode("answer.delta", sequence, request_id, delta)
    _persist_chat_completed_event(request, run_id, result, cached["answer"])
    sequence += 1
    yield _encode(
        "answer.completed",
        sequence,
        request_id,
        {
            "answer_cache_hit": True,
            "cache_key": cached["cache_key"],
            "normalized_query": cached["normalized_query"],
            "duration_ms": total_duration_ms,
            "stage_durations_ms": stage_durations or {},
            "result_count": len(cached["citations"]),
            "results": cached["citations"],
        },
    )
    if recommendation_task is not None:
        sequence += 1
        yield await _finish_recommendation_event(
            recommendation_task,
            sequence,
            request_id,
            request,
            run_id,
        )


def _cached_trace(cached: dict) -> list[dict]:
    trace = _public_retrieval_trace(list(cached.get("trace") or []))
    trace.append({
        "stage": "answer_cache",
        "summary": "命中答案缓存，跳过检索和答案生成",
        "metrics": {
            "answer_cache_hit": True,
            "normalized_query": cached.get("normalized_query", ""),
            "hit_count": cached.get("hit_count", 0),
            "trust_score": cached.get("trust_score", 0),
            "ttl_expires_at": cached.get("expires_at", ""),
        },
    })
    return trace


def _public_retrieval_trace(trace: list[dict]) -> list[dict]:
    """将技术 trace 摘要转换为 SEE 面板可展示的大白话。"""
    return [_public_trace_item(item) for item in trace]


def _public_trace_item(item: dict) -> dict:
    """转换单个 trace item，并保留原始 metrics 供调试查看。"""
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    engine = str(metrics.get("engine", ""))
    should_explain_rerank = item.get("stage") == "candidate_scoring" and "rerank" in engine
    return {**item, "summary": RERANK_PROGRESS_SUMMARY} if should_explain_rerank else item


def _split_cached_answer(answer: str, citations: list[dict]) -> list[dict]:
    chunk_id = str(citations[0].get("chunk_id", "")) if citations else ""
    if len(answer) <= CACHED_ANSWER_DELTA_CHARS:
        return [{"text": answer, "chunk_id": chunk_id}]
    return [
        {"text": answer[index:index + CACHED_ANSWER_DELTA_CHARS], "chunk_id": chunk_id}
        for index in range(0, len(answer), CACHED_ANSWER_DELTA_CHARS)
    ]


def _store_answer_cache(
    answer_cache: AnswerCacheService | None,
    request: RetrievalSDKSearchRequest,
    result: dict,
    answer: str,
    retrieval_query: str | None = None,
    top_k: int | None = None,
) -> None:
    """Store useful successful answers; skip empty/no-result answers unless later explicitly liked."""
    if request.deep_search_enabled:
        return
    if answer_cache is None or not answer.strip() or not result.get("results"):
        return
    answer_cache.set(
        input_text=retrieval_query or request.input,
        knowledge_base_ids=request.knowledge_base_ids,
        top_k=top_k or request.top_k or 5,
        answer=answer,
        citations=_citation_results(result["results"]),
        trace=result.get("trace", []),
        request_id=result["request_id"],
        temperature=request.temperature,
    )


async def _iter_answer_deltas(
    answer_service: RetrievalAnswerService,
    query: str,
    results: list[dict],
    temperature: float = 0.2,
) -> AsyncIterator[dict]:
    """优先消费流式答案接口，兼容旧的完整合成接口。"""
    if hasattr(answer_service, "stream_synthesize"):
        try:
            stream = answer_service.stream_synthesize(query, results, temperature=temperature)
        except TypeError as exc:
            if "temperature" not in str(exc):
                raise
            stream = answer_service.stream_synthesize(query, results)
        async for delta in stream:
            yield delta
        return
    try:
        answer_result = await answer_service.synthesize(query, results, temperature=temperature)
    except TypeError as exc:
        if "temperature" not in str(exc):
            raise
        answer_result = await answer_service.synthesize(query, results)
    for delta in answer_result["deltas"]:
        yield delta


def _encode(event_name: str, sequence: int, request_id: str, payload: dict) -> str:
    """编码单个 SSE 事件。"""
    return encode_sse_event(
        build_event(
            event=event_name,
            user_id="retrieval-sdk",
            request_id=request_id,
            sequence=sequence,
            payload=payload,
        )
    )


def _citation_results(results: list[dict]) -> list[dict]:
    """返回前端引用需要的安全字段，避免把原始正文和路径塞进聊天输出。"""
    return [
        {
            "chunk_id": item.get("chunk_id", ""),
            "document_name": _display_document_name(str(item.get("document_name", ""))),
            "title": item.get("title", ""),
            "content": _safe_citation_snippet(str(item.get("content", ""))),
            "snippet": _safe_citation_snippet(str(item.get("snippet", ""))),
            "score": item.get("score", 0),
            "score_trace": item.get("score_trace", {}),
        }
        for item in results
    ]


def _safe_citation_snippet(content: str) -> str:
    """清理引用片段，避免把示例问答和本地路径泄露到 SSE。"""
    cleaned = CODE_BLOCK_PATTERN.sub("", content)
    cleaned = EXAMPLE_BLOCK_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"[\w.-]*/+[\w./-]+\.md", "", cleaned)
    cleaned = cleaned.replace("iPhone 16", "")
    lines = [
        line.strip()
        for line in cleaned.splitlines()
        if line.strip() and not line.strip().startswith(("用户问：", "用户问:", "模型答：", "模型答:"))
    ]
    return "\n".join(lines).strip()[:360]


def _display_document_name(document_name: str) -> str:
    """仅展示文件名，避免泄露本地/Obsidian 路径。"""
    return document_name.split("/")[-1] if document_name else ""


def _get_retrieval_sdk_service() -> RetrievalSDKService:
    """构建 Retrieval SDK 服务。"""
    return RetrievalSDKService(KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH))


def _get_retrieval_answer_service() -> RetrievalAnswerService:
    """构建 Retrieval SDK 答案生成服务。"""
    return RetrievalAnswerService()


def _get_answer_cache_service() -> AnswerCacheService:
    """构建答案缓存服务。"""
    return AnswerCacheService(KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH))


def _get_topic_recommendation_service() -> TopicRecommendationService:
    """构建主题推荐服务。"""
    return TopicRecommendationService(KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH))


def _create_chat_run(request: RetrievalSDKSearchRequest) -> str | None:
    """请求携带 session 时创建聊天 run。"""
    if not request.user_id or not request.session_id:
        return None
    try:
        run = get_session_service().create_run(
            user_id=request.user_id,
            session_id=request.session_id,
            input_text=request.input,
            tools=["retrieval.search.stream"],
            metadata={"knowledge_base_ids": request.knowledge_base_ids, "top_k": request.top_k},
        )
        get_session_service().append_event(
            request.user_id,
            request.session_id,
            run.run_id,
            "run.created",
            {"status": "running"},
        )
        get_session_service().update_run(request.user_id, request.session_id, run.run_id, status="running")
        return run.run_id
    except SessionNotFoundError:
        return None


def _persist_chat_stream_events(
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
    result: dict,
    answer_deltas: list[dict],
    answer: str,
) -> None:
    """请求携带 session 时保存聊天 trace、delta 和最终答案。"""
    if not request.user_id or not request.session_id or run_id is None:
        return
    service = get_session_service()
    service.append_event(
        request.user_id,
        request.session_id,
        run_id,
        "retrieval.trace",
        {"trace": result["trace"]},
        request_id=result["request_id"],
    )
    for delta in answer_deltas:
        service.append_event(
            request.user_id,
            request.session_id,
            run_id,
            "answer.delta",
            delta,
            request_id=result["request_id"],
        )
    service.append_event(
        request.user_id,
        request.session_id,
        run_id,
        "answer.completed",
        {"answer": answer},
        request_id=result["request_id"],
    )
    service.update_run(
        request.user_id,
        request.session_id,
        run_id,
        request_id=result["request_id"],
        status="completed",
        answer=answer,
    )


def _schedule_session_auto_title(request: RetrievalSDKSearchRequest, answer: str) -> None:
    """后台生成默认会话标题，不阻塞 SSE 完成事件。"""
    if not request.user_id or not request.session_id:
        return
    try:
        asyncio.create_task(
            get_session_title_service().auto_title_if_needed(
                get_session_service(),
                request.user_id,
                request.session_id,
                request.input,
                answer,
            )
        )
    except RuntimeError:
        pass


def _persist_chat_trace_event(
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
    result: dict,
) -> None:
    """请求携带 session 时保存检索 trace。"""
    if not request.user_id or not request.session_id or run_id is None:
        return
    get_session_service().append_event(
        request.user_id,
        request.session_id,
        run_id,
        "retrieval.trace",
        {"trace": result["trace"]},
        request_id=result["request_id"],
    )


def _persist_chat_named_event(
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
    event_name: str,
    payload: dict,
    request_id: str,
) -> None:
    """请求携带 session 时保存指定聊天事件。"""
    if not request.user_id or not request.session_id or run_id is None:
        return
    get_session_service().append_event(
        request.user_id,
        request.session_id,
        run_id,
        event_name,
        payload,
        request_id=request_id,
    )


def _persist_chat_delta_event(
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
    result: dict,
    delta: dict,
) -> None:
    """请求携带 session 时保存单个实时 delta。"""
    if not request.user_id or not request.session_id or run_id is None:
        return
    get_session_service().append_event(
        request.user_id,
        request.session_id,
        run_id,
        "answer.delta",
        delta,
        request_id=result["request_id"],
    )


def _persist_chat_completed_event(
    request: RetrievalSDKSearchRequest,
    run_id: str | None,
    result: dict,
    answer: str,
) -> None:
    """请求携带 session 时保存最终答案并更新 run。"""
    if not request.user_id or not request.session_id or run_id is None:
        return
    service = get_session_service()
    service.append_event(
        request.user_id,
        request.session_id,
        run_id,
        "answer.completed",
        {"answer": answer, "results": _citation_results(result["results"])},
        request_id=result["request_id"],
    )
    service.update_run(
        request.user_id,
        request.session_id,
        run_id,
        request_id=result["request_id"],
        status="completed",
        answer=answer,
    )
    _schedule_session_auto_title(request, answer)


def _assert_published_knowledge_bases(knowledge_base_ids: list[str]) -> None:
    """校验流式检索请求只使用已发布知识库。"""
    repository = KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH)
    records = repository.get_knowledge_bases_by_ids(knowledge_base_ids)
    published_ids = {record["id"] for record in records if record.get("status") == "published"}
    invalid = [kb_id for kb_id in knowledge_base_ids if kb_id not in published_ids]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "聊天检索只能选择已发布知识库", "knowledge_base_ids": invalid},
        )
