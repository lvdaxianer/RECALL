"""
Retrieval SDK 流式路由测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

import asyncio
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.models.knowledge_base_schemas import RetrievalSDKSearchRequest
from app.routers.retrieval_stream import _stream_cached_answer, _stream_retrieval_events
from app.routers.retrieval_stream import _store_answer_cache
from app.services.answer_cache_service import AnswerCacheService
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.markdown_chunk_service import MarkdownChunkService


@pytest_asyncio.fixture
async def async_client(tmp_path, monkeypatch):
    """构建使用临时 SQLite 状态库的异步 HTTP 客户端。"""
    db_path = str(tmp_path / "kb.sqlite")
    monkeypatch.setattr("app.routers.knowledge_bases.KNOWLEDGE_BASE_DB_PATH", db_path)
    monkeypatch.setattr("app.routers.knowledge_base_documents.KNOWLEDGE_BASE_DB_PATH", db_path)
    monkeypatch.setattr("app.routers.retrieval_sdk.KNOWLEDGE_BASE_DB_PATH", db_path)
    monkeypatch.setattr("app.routers.retrieval_stream.KNOWLEDGE_BASE_DB_PATH", db_path)
    monkeypatch.setattr("app.services.session_service.Config.RAG_STATE_DB_PATH", str(tmp_path / "sessions.sqlite"))
    monkeypatch.setattr("app.services.session_service._session_service", None)
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_retrieval_sdk_search_endpoint_filters_kbs(async_client):
    """同步检索接口支持知识库多选过滤。"""
    kb = (
        await async_client.post("/api/v1/kb", json={"name": "KB", "description": "desc", "owner_id": "u1"})
    ).json()["data"]
    await async_client.post(
        f"/api/v1/kb/{kb['id']}/documents",
        json={"name": "a.md", "content": "# 标题\n检索能力抽象为 SDK", "content_type": "text/markdown", "owner_id": "u1"},
    )
    await async_client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": "u1"})
    _parse_queued_documents_for_test(kb["id"])

    response = await async_client.post(
        "/api/v1/retrieval/search",
        json={"input": "检索 SDK", "knowledge_base_ids": [kb["id"]], "top_k": 5},
    )

    assert response.status_code == 200
    assert response.json()["data"]["filters"]["knowledge_base_ids"] == [kb["id"]]
    assert response.json()["data"]["results"][0]["knowledge_base_id"] == kb["id"]


@pytest.mark.asyncio
async def test_retrieval_sdk_search_rejects_unpublished_kb(async_client):
    """同步检索拒绝未发布知识库，避免聊天绕过前端禁用。"""
    kb = (
        await async_client.post("/api/v1/kb", json={"name": "KB", "description": "desc", "owner_id": "u1"})
    ).json()["data"]

    response = await async_client.post(
        "/api/v1/retrieval/search",
        json={"input": "检索 SDK", "knowledge_base_ids": [kb["id"]], "top_k": 5},
    )

    assert response.status_code == 400
    assert "已发布" in response.text


@pytest.mark.asyncio
async def test_retrieval_stream_endpoint_returns_ordered_sse(async_client):
    """流式检索接口返回有序 SSE 事件和最终结果。"""
    kb = (
        await async_client.post("/api/v1/kb", json={"name": "KB", "description": "desc", "owner_id": "u1"})
    ).json()["data"]
    await async_client.post(
        f"/api/v1/kb/{kb['id']}/documents",
        json={"name": "a.md", "content": "# 标题\n检索能力支持流式输出", "content_type": "text/markdown", "owner_id": "u1"},
    )
    await async_client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": "u1"})
    _parse_queued_documents_for_test(kb["id"])

    response = await async_client.post(
        "/api/v1/retrieval/search/stream",
        json={"input": "检索能力 流式", "knowledge_base_ids": [kb["id"]], "top_k": 5},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: request.created" in response.text
    assert "event: retrieval.trace" in response.text
    assert "event: answer.delta" in response.text
    assert "event: answer.completed" in response.text

    payloads = []
    for block in response.text.strip().split("\n\n"):
        data_line = next(line for line in block.splitlines() if line.startswith("data: "))
        payloads.append(json.loads(data_line.removeprefix("data: ")))

    assert [item["sequence"] for item in payloads] == sorted(item["sequence"] for item in payloads)


@pytest.mark.asyncio
async def test_retrieval_stream_persists_chat_run_history(async_client):
    """流式聊天检索携带 session 后保存用户问题和助手答案。"""
    session = (
        await async_client.post("/api/v1/agent/default/sessions", json={"title": "ES 过滤调试"})
    ).json()["data"]
    kb = (
        await async_client.post("/api/v1/kb", json={"name": "KB", "description": "desc", "owner_id": "u1"})
    ).json()["data"]
    await async_client.post(
        f"/api/v1/kb/{kb['id']}/documents",
        json={"name": "a.md", "content": "# 标题\n检索能力支持会话历史", "content_type": "text/markdown", "owner_id": "u1"},
    )
    await async_client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": "u1"})
    _parse_queued_documents_for_test(kb["id"])

    response = await async_client.post(
        "/api/v1/retrieval/search/stream",
        json={
            "input": "检索能力 会话历史",
            "knowledge_base_ids": [kb["id"]],
            "top_k": 5,
            "user_id": "default",
            "session_id": session["session_id"],
        },
    )
    runs_response = await async_client.get(f"/api/v1/agent/default/sessions/{session['session_id']}/runs")

    assert response.status_code == 200
    run = runs_response.json()["data"][0]
    assert run["input"] == "检索能力 会话历史"
    assert run["status"] == "completed"
    assert "会话历史" in run["answer"]


@pytest.mark.asyncio
async def test_retrieval_stream_persists_trace_and_delta_events(async_client):
    """流式聊天检索保存 trace 和 delta，供历史消息恢复引用细节。"""
    session = (
        await async_client.post("/api/v1/agent/default/sessions", json={"title": "Trace 调试"})
    ).json()["data"]
    kb = (
        await async_client.post("/api/v1/kb", json={"name": "KB", "description": "desc", "owner_id": "u1"})
    ).json()["data"]
    await async_client.post(
        f"/api/v1/kb/{kb['id']}/documents",
        json={"name": "trace.md", "content": "# Trace\n检索链路需要 score trace", "content_type": "text/markdown", "owner_id": "u1"},
    )
    await async_client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": "u1"})
    _parse_queued_documents_for_test(kb["id"])

    await async_client.post(
        "/api/v1/retrieval/search/stream",
        json={
            "input": "检索链路 trace",
            "knowledge_base_ids": [kb["id"]],
            "top_k": 5,
            "user_id": "default",
            "session_id": session["session_id"],
        },
    )
    runs = (await async_client.get(f"/api/v1/agent/default/sessions/{session['session_id']}/runs")).json()["data"]
    events_response = await async_client.get(
        f"/api/v1/agent/default/sessions/{session['session_id']}/events?run_id={runs[0]['run_id']}"
    )

    event_names = [item["event"] for item in events_response.json()["data"]]
    assert "retrieval.trace" in event_names
    assert "answer.delta" in event_names
    assert "answer.completed" in event_names


@pytest.mark.asyncio
async def test_retrieval_stream_summarizes_knowledge_base_overview_instead_of_echoing_chunks(async_client):
    """知识库概览问题应汇总主题，不应原样输出 chunk 路径或文档内示例问答。"""
    kb = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "Obsidian Note", "description": "AI 笔记", "owner_id": "u1"},
        )
    ).json()["data"]
    await async_client.post(
        f"/api/v1/kb/{kb['id']}/documents",
        json={
            "name": "笔记/AI/扩展知识/微调/00.为什么需要微调以及与知识库的区别.md",
            "content": (
                "# 为什么需要微调以及与知识库的区别\n"
                "本文主要讲解微调、知识库、RAG、知识截止日期以及模型如何基于外部资料回答。\n\n"
                "```text\n"
                "用户问：请介绍一下 iPhone 16 的新功能\n"
                "模型答：很抱歉，我的知识截止到 2023 年 4 月，无法提供 iPhone 16 信息。\n"
                "```\n"
                "## 微调 vs 知识库\n"
                "微调用于让模型学习任务风格，知识库用于提供可更新的事实资料。"
            ),
            "content_type": "text/markdown",
            "owner_id": "u1",
        },
    )
    await async_client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": "u1"})
    _parse_queued_documents_for_test(kb["id"])

    response = await async_client.post(
        "/api/v1/retrieval/search/stream",
        json={"input": "这个知识库主要包含什么？", "knowledge_base_ids": [kb["id"]], "top_k": 5},
    )

    assert response.status_code == 200
    assert "微调" in response.text
    assert "知识库" in response.text
    assert "RAG" in response.text
    assert "iPhone 16" not in response.text
    assert "用户问：" not in response.text
    assert "笔记/AI/扩展知识" not in response.text


@pytest.mark.asyncio
async def test_retrieval_stream_yields_request_event_before_retrieval_and_generation():
    """SSE 应先输出 request.created，避免等检索/LLM 完成后整段出现。"""
    class FakeRetrievalService:
        def __init__(self):
            self.called = False

        async def search_with_engines(self, **kwargs):
            self.called = True
            return {
                "request_id": kwargs["request_id"],
                "results": [],
                "trace": [],
            }

    class FakeAnswerService:
        def __init__(self):
            self.called = False

        async def synthesize(self, query, results):
            self.called = True
            return {"answer": "没有内容", "deltas": [{"text": "没有内容", "chunk_id": ""}]}

    retrieval_service = FakeRetrievalService()
    answer_service = FakeAnswerService()
    events = _stream_retrieval_events(
        RetrievalSDKSearchRequest(
            input="这个知识库主要包含什么？",
            knowledge_base_ids=["kb-001"],
            top_k=5,
        ),
        run_id=None,
        retrieval_service=retrieval_service,
        answer_service=answer_service,
        request_id="req-test",
    )

    first_event = await anext(events)

    assert "event: request.created" in first_event
    assert retrieval_service.called is False


@pytest.mark.asyncio
async def test_retrieval_stream_yields_public_progress_before_expensive_retrieval():
    """SSE 应在检索耗时阶段输出公开进度，让前端展示可感知的处理中状态。"""
    class FakeRetrievalService:
        def __init__(self):
            self.called = False

        async def search_with_engines(self, **kwargs):
            self.called = True
            return {
                "request_id": kwargs["request_id"],
                "results": [],
                "trace": [],
            }

    class FakeAnswerService:
        def __init__(self):
            self.called = False

        async def synthesize(self, query, results):
            self.called = True
            return {"answer": "没有内容", "deltas": [{"text": "没有内容", "chunk_id": ""}]}

    retrieval_service = FakeRetrievalService()
    answer_service = FakeAnswerService()
    events = _stream_retrieval_events(
        RetrievalSDKSearchRequest(
            input="Redis 为什么慢？",
            knowledge_base_ids=["kb-001"],
            top_k=5,
        ),
        run_id=None,
        retrieval_service=retrieval_service,
        answer_service=answer_service,
        request_id="req-progress",
    )

    await anext(events)
    second_event = await anext(events)

    assert "event: retrieval.progress" in second_event
    assert "正在判断这个问题适合怎么查" in second_event
    assert retrieval_service.called is False


@pytest.mark.asyncio
async def test_retrieval_stream_trace_contains_stage_duration_metrics():
    """流式聊天 trace 应展示检索和答案生成阶段耗时。"""
    class FakeRetrievalService:
        async def search_with_engines(self, **kwargs):
            return {
                "request_id": kwargs["request_id"],
                "results": [{"chunk_id": "c1", "content": "证据", "score": 1}],
                "trace": [{"stage": "candidate_scoring", "summary": "候选排序", "metrics": {"engine": "fake"}}],
            }

    class FakeAnswerService:
        async def stream_synthesize(self, query, results, temperature=0.2):
            yield {"text": "回答", "chunk_id": "c1"}

    events = [
        event
        async for event in _stream_retrieval_events(
            RetrievalSDKSearchRequest(input="检索", knowledge_base_ids=["kb-001"], top_k=5),
            run_id=None,
            retrieval_service=FakeRetrievalService(),
            answer_service=FakeAnswerService(),
            answer_cache=None,
            request_id="req-duration",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]
    trace_payload = _event_payload(events, "retrieval.trace")
    completed_payload = _event_payload(events, "answer.completed")

    trace_items = trace_payload["trace"]
    assert trace_items[0]["metrics"]["duration_ms"] >= 0
    assert completed_payload["duration_ms"] >= 0
    assert completed_payload["stage_durations_ms"]["retrieval"] >= 0
    assert completed_payload["stage_durations_ms"]["answer_generation"] >= 0


@pytest.mark.asyncio
async def test_cached_retrieval_stream_trace_contains_cache_duration_metrics():
    """答案缓存命中时也应在 Trace 中展示缓存读取耗时。"""
    cached = {
        "answer": "缓存回答",
        "citations": [{"chunk_id": "c1"}],
        "trace": [],
        "cache_key": "cache-1",
        "normalized_query": "检索",
        "hit_count": 1,
        "trust_score": 0,
        "expires_at": "2099-01-01T00:00:00+00:00",
    }

    events = [
        event
        async for event in _stream_cached_answer(
            RetrievalSDKSearchRequest(input="检索", knowledge_base_ids=["kb-001"], top_k=5),
            run_id=None,
            request_id="req-cache-duration",
            cached=cached,
            delta_sleep=lambda seconds: _noop_sleep(),
            sequence=2,
            stage_durations={"answer_cache": 1.2},
            total_duration_ms=1.5,
        )
    ]

    trace_payload = _event_payload(events, "retrieval.trace")
    completed_payload = _event_payload(events, "answer.completed")
    assert trace_payload["trace"][-1]["metrics"]["duration_ms"] == 1.2
    assert completed_payload["duration_ms"] == 1.5
    assert completed_payload["stage_durations_ms"]["answer_cache"] == 1.2


@pytest.mark.asyncio
async def test_retrieval_stream_emits_plain_chinese_progress_summaries():
    """SSE progress 主文案应是用户能看懂的大白话。"""
    class FakeRetrievalService:
        async def search_with_engines(self, **kwargs):
            return {
                "request_id": kwargs["request_id"],
                "results": [],
                "trace": [{
                    "stage": "candidate_scoring",
                    "summary": "technical",
                    "metrics": {"engine": "es_milvus_rerank"},
                }],
            }

    class FakeAnswerService:
        async def stream_synthesize(self, query, results):
            yield {"text": "没有内容", "chunk_id": ""}

    text = "".join([
        event async for event in _stream_retrieval_events(
            RetrievalSDKSearchRequest(input="RAG 是什么？", knowledge_base_ids=["kb-001"], top_k=5),
            run_id=None,
            retrieval_service=FakeRetrievalService(),
            answer_service=FakeAnswerService(),
            request_id="req-see",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ])

    assert "收到问题" in text
    assert "正在判断这个问题适合怎么查" in text
    assert "正在从选中的知识库里查找相关资料" in text
    assert "正在把候选资料按相关性重新排序" in text
    assert "已找到可用资料，正在整理回答" in text


@pytest.mark.asyncio
async def test_retrieval_stream_paces_answer_delta_events():
    """答案 delta 之间应经过异步节奏控制，避免前端看起来整段瞬间出现。"""
    class FakeRetrievalService:
        async def search_with_engines(self, **kwargs):
            return {
                "request_id": kwargs["request_id"],
                "results": [],
                "trace": [],
            }

    class FakeAnswerService:
        async def synthesize(self, query, results):
            return {
                "answer": "第一段第二段第三段",
                "deltas": [
                    {"text": "第一段", "chunk_id": ""},
                    {"text": "第二段", "chunk_id": ""},
                    {"text": "第三段", "chunk_id": ""},
                ],
            }

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    delta_events = []
    async for event in _stream_retrieval_events(
        RetrievalSDKSearchRequest(
            input="这个知识库主要包含什么？",
            knowledge_base_ids=["kb-001"],
            top_k=5,
        ),
        run_id=None,
        retrieval_service=FakeRetrievalService(),
        answer_service=FakeAnswerService(),
        request_id="req-paced",
        delta_sleep=fake_sleep,
    ):
        if "event: answer.delta" in event:
            delta_events.append(event)

    assert len(delta_events) == 3
    assert sleep_calls == [0.024, 0.024]


@pytest.mark.asyncio
async def test_retrieval_stream_emits_answer_completed_before_slow_recommendations(monkeypatch):
    """推荐很慢时 answer.completed 仍应先输出，推荐随后超时降级。"""
    class FakeRetrievalService:
        async def search_with_engines(self, **kwargs):
            return {
                "request_id": kwargs["request_id"],
                "results": [{"chunk_id": "c1", "document_id": "doc-1", "content": "证据", "score": 1}],
                "trace": [],
            }

    class FakeAnswerService:
        async def stream_synthesize(self, query, results, temperature=0.2):
            yield {"text": "回答", "chunk_id": "c1"}

    class SlowRecommendationService:
        async def build(self, **kwargs):
            await asyncio.sleep(0.5)
            return []

    monkeypatch.setattr("app.routers.retrieval_stream.Config.RAG_RECOMMENDATION_TIMEOUT_MS", 1, raising=False)
    monkeypatch.setattr(
        "app.routers.retrieval_stream._get_topic_recommendation_service",
        lambda: SlowRecommendationService(),
    )

    events = [
        event async for event in _stream_retrieval_events(
            RetrievalSDKSearchRequest(input="适配器模式干啥的", knowledge_base_ids=["kb-001"], top_k=5),
            run_id=None,
            retrieval_service=FakeRetrievalService(),
            answer_service=FakeAnswerService(),
            answer_cache=None,
            request_id="req-rec",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]
    event_names = [_event_name(event) for event in events]

    assert event_names.index("answer.completed") < event_names.index("recommendation.skipped")


def test_store_answer_cache_skips_empty_or_no_retrieval_result_answers():
    """无检索命中或空答案不写入答案缓存。"""
    class RecordingAnswerCache:
        def __init__(self):
            self.calls = []

        def set(self, **kwargs):
            self.calls.append(kwargs)

    answer_cache = RecordingAnswerCache()

    _store_answer_cache(
        answer_cache=answer_cache,
        request=RetrievalSDKSearchRequest(input="适配器模式干啥的", knowledge_base_ids=["kb-001"], top_k=5),
        result={"request_id": "req-empty", "results": [], "trace": []},
        answer="",
        retrieval_query="适配器模式干啥的",
        top_k=5,
    )

    assert answer_cache.calls == []


@pytest.mark.asyncio
async def test_retrieval_stream_passes_issue_type_to_sdk():
    """流式检索应把请求中的 issue_type 透传给 Retrieval SDK。"""
    class FakeRetrievalService:
        def __init__(self):
            self.issue_type = None

        async def search_with_engines(self, **kwargs):
            self.issue_type = kwargs.get("issue_type")
            return {
                "request_id": kwargs["request_id"],
                "results": [],
                "trace": [],
            }

    class FakeAnswerService:
        async def synthesize(self, query, results):
            return {"answer": "没有内容", "deltas": [{"text": "没有内容", "chunk_id": ""}]}

    retrieval_service = FakeRetrievalService()
    async for _ in _stream_retrieval_events(
        RetrievalSDKSearchRequest(
            input="白屏怎么排查",
            knowledge_base_ids=["kb-001"],
            top_k=5,
            issue_type="fault",
        ),
        run_id=None,
        retrieval_service=retrieval_service,
        answer_service=FakeAnswerService(),
        request_id="req-issue-type",
        delta_sleep=lambda seconds: _noop_sleep(),
    ):
        pass

    assert retrieval_service.issue_type == "fault"


@pytest.mark.asyncio
async def test_retrieval_stream_passes_top_k_and_context_query_to_sdk():
    """流式检索应透传 topK 并按开关构建上下文检索 query。"""
    class FakeRetrievalService:
        def __init__(self):
            self.kwargs = {}

        def resolve_top_k(self, top_k, knowledge_base_ids):
            return top_k or 8

        def build_retrieval_query(self, input_text, use_context=False, history_questions=None):
            if not use_context:
                return input_text
            return "；".join([*(history_questions or [])[-3:], input_text])

        async def search_with_engines(self, **kwargs):
            self.kwargs = kwargs
            return {
                "request_id": kwargs["request_id"],
                "results": [],
                "trace": [],
            }

    class FakeAnswerService:
        async def stream_synthesize(self, query, results):
            yield {"text": "没有内容", "chunk_id": ""}

    retrieval_service = FakeRetrievalService()
    async for _ in _stream_retrieval_events(
        RetrievalSDKSearchRequest(
            input="当前问题",
            knowledge_base_ids=["kb-001"],
            top_k=10,
            use_context=True,
            history_questions=["第一问", "第二问", "第三问", "第四问"],
        ),
        run_id=None,
        retrieval_service=retrieval_service,
        answer_service=FakeAnswerService(),
        request_id="req-context",
        delta_sleep=lambda seconds: _noop_sleep(),
    ):
        pass

    assert retrieval_service.kwargs["top_k"] == 10
    assert retrieval_service.kwargs["input"] == "第二问；第三问；第四问；当前问题"


@pytest.mark.asyncio
async def test_deep_search_stream_emits_visible_plan_and_step_hits():
    """DeepSearch 应公开展示拆分问题和每一步命中摘要。"""
    class FakeRetrievalService:
        def build_retrieval_query(self, input_text, use_context=False, history_questions=None):
            return input_text

        async def deep_search_with_engines(self, **kwargs):
            return {
                "request_id": kwargs["request_id"],
                "results": [{"chunk_id": "chunk-build", "document_name": "release.md", "title": "发布配置", "content": "检查发布配置"}],
                "trace": [{"stage": "candidate_scoring", "summary": "最终合并排序", "metrics": {"engine": "deep_search_rerank"}}],
                "deep_search": {
                    "intent": "排查小程序上线后白屏",
                    "cot_plan": ["识别故障现象", "拆分检索方向"],
                    "sub_questions": ["是否是构建或发布配置导致白屏？", "是否是接口域名导致白屏？"],
                    "steps": [
                        {
                            "index": 1,
                            "sub_question": "是否是构建或发布配置导致白屏？",
                            "hit_count": 1,
                            "top_hits": [{"chunk_id": "chunk-build", "title": "发布配置", "score": 0.91}],
                        },
                        {
                            "index": 2,
                            "sub_question": "是否是接口域名导致白屏？",
                            "hit_count": 0,
                            "top_hits": [],
                        },
                    ],
                },
            }

    class FakeAnswerService:
        async def stream_synthesize(self, query, results, temperature=0.2):
            yield {"text": "检查发布配置。", "chunk_id": "chunk-build"}

    events = [
        event async for event in _stream_retrieval_events(
            RetrievalSDKSearchRequest(
                input="小程序上线后白屏，本地正常",
                knowledge_base_ids=["kb-001"],
                top_k=5,
                deep_search_enabled=True,
            ),
            run_id=None,
            retrieval_service=FakeRetrievalService(),
            answer_service=FakeAnswerService(),
            request_id="req-deep",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]

    text = "".join(events)
    assert "event: deep_search.plan" in text
    assert "event: deep_search.step" in text
    assert "深度检索会拆分问题并多轮检索，可能需要更久" in text
    assert "是否是构建或发布配置导致白屏？" in text
    assert "发布配置" in text
    assert "完整私有推理链" not in text


@pytest.mark.asyncio
async def test_deep_search_stream_skips_normal_answer_cache(tmp_path):
    """DeepSearch 不应命中普通检索答案缓存，避免用户勾选后复用浅检索结果。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    answer_cache = AnswerCacheService(repository, ttl_seconds=3600)
    answer_cache.set(
        input_text="JMM 访问策略",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        answer="普通缓存答案",
        citations=[{"chunk_id": "chunk-cache"}],
        trace=[],
        request_id="req-cache",
        temperature=0.2,
    )

    class FakeRetrievalService:
        def __init__(self):
            self.calls = 0

        def build_retrieval_query(self, input_text, use_context=False, history_questions=None):
            return input_text

        async def deep_search_with_engines(self, **kwargs):
            self.calls += 1
            return {
                "request_id": kwargs["request_id"],
                "results": [{"chunk_id": "chunk-deep", "document_name": "jmm.md", "title": "JMM", "content": "深度证据"}],
                "trace": [],
                "deep_search": {
                    "intent": "JMM 访问策略",
                    "cot_plan": ["拆分访问策略问题"],
                    "sub_questions": ["JMM 访问策略是什么？"],
                    "steps": [{"index": 1, "sub_question": "JMM 访问策略是什么？", "hit_count": 1, "top_hits": []}],
                },
            }

    class FakeAnswerService:
        async def stream_synthesize(self, query, results, temperature=0.2):
            yield {"text": "DeepSearch 新答案", "chunk_id": "chunk-deep"}

    retrieval_service = FakeRetrievalService()
    events = [
        event async for event in _stream_retrieval_events(
            RetrievalSDKSearchRequest(
                input="JMM 访问策略",
                knowledge_base_ids=[kb["id"]],
                top_k=5,
                deep_search_enabled=True,
            ),
            run_id=None,
            retrieval_service=retrieval_service,
            answer_service=FakeAnswerService(),
            answer_cache=answer_cache,
            request_id="req-deep-cache",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]

    assert retrieval_service.calls == 1
    assert not any("answer_cache_hit" in event for event in events)
    assert any("DeepSearch 新答案" in event for event in events)


@pytest.mark.asyncio
async def test_retrieval_stream_yields_answer_deltas_from_streaming_synthesis():
    """路由应消费流式合成增量，不能等待完整 synthesize 后再拆分输出。"""
    class FakeRetrievalService:
        async def search_with_engines(self, **kwargs):
            return {
                "request_id": kwargs["request_id"],
                "results": [{"chunk_id": "chunk-1", "document_name": "guide.md", "title": "RAG", "content": "RAG"}],
                "trace": [],
            }

    class FakeStreamingAnswerService:
        async def synthesize(self, query, results):
            raise AssertionError("stream route should use stream_synthesize")

        async def stream_synthesize(self, query, results):
            yield {"text": "第一段", "chunk_id": "chunk-1"}
            yield {"text": "第二段", "chunk_id": "chunk-1"}

    events = []
    async for event in _stream_retrieval_events(
        RetrievalSDKSearchRequest(
            input="RAG 是什么？",
            knowledge_base_ids=["kb-001"],
            top_k=5,
        ),
        run_id=None,
        retrieval_service=FakeRetrievalService(),
        answer_service=FakeStreamingAnswerService(),
        request_id="req-streaming",
        delta_sleep=lambda seconds: _noop_sleep(),
    ):
        events.append(event)

    delta_events = [event for event in events if "event: answer.delta" in event]
    assert len(delta_events) == 2
    assert "第一段" in delta_events[0]
    assert "第二段" in delta_events[1]


@pytest.mark.asyncio
async def test_retrieval_stream_filters_unrelated_answer_sources():
    """具体问题的答案生成和引用来源不应带出无关命中。"""
    class FakeRetrievalService:
        async def search_with_engines(self, **kwargs):
            return {
                "request_id": kwargs["request_id"],
                "results": [
                    {"chunk_id": "chunk-jmm", "document_name": "jmm.md", "title": "Java 内存模型（JMM）", "content": ""},
                    {"chunk_id": "chunk-mmap", "document_name": "linux.md", "title": "mmap 原理", "content": "mmap 是 Linux 内存映射机制。"},
                    {"chunk_id": "chunk-redis", "document_name": "redis.md", "title": "Redis 过期键删除策略", "content": "Redis 过期键删除策略。"},
                ],
                "trace": [],
            }

    class FakeAnswerService:
        def __init__(self):
            self.received_results = []

        async def stream_synthesize(self, query, results):
            self.received_results = results
            yield {"text": "现有资料只有 JMM 标题，无法回答访问策略细节。", "chunk_id": "chunk-jmm"}

    answer_service = FakeAnswerService()
    events = [
        event async for event in _stream_retrieval_events(
            RetrievalSDKSearchRequest(input="JMM 访问策略是啥", knowledge_base_ids=["kb-001"], top_k=5),
            run_id=None,
            retrieval_service=FakeRetrievalService(),
            answer_service=answer_service,
            request_id="req-filter",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]

    completed_event = next(event for event in events if "event: answer.completed" in event)
    assert [result["chunk_id"] for result in answer_service.received_results] == ["chunk-jmm"]
    assert "chunk-jmm" in completed_event
    assert "chunk-mmap" not in completed_event
    assert "chunk-redis" not in completed_event


@pytest.mark.asyncio
async def test_retrieval_stream_reuses_cached_answer_for_normalized_question(tmp_path):
    """相同归一化问题命中答案缓存时不重复检索和合成。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    answer_cache = AnswerCacheService(repository, ttl_seconds=3600)

    class FakeRetrievalService:
        def __init__(self):
            self.calls = 0

        async def search_with_engines(self, **kwargs):
            self.calls += 1
            return {
                "request_id": kwargs["request_id"],
                "results": [{"chunk_id": "chunk-1", "document_name": "jmm.md", "title": "JMM", "content": "JMM"}],
                "trace": [{"stage": "candidate_scoring", "summary": "fresh"}],
            }

    class FakeAnswerService:
        def __init__(self):
            self.calls = 0

        async def stream_synthesize(self, query, results):
            self.calls += 1
            yield {"text": "JMM 缓存答案", "chunk_id": "chunk-1"}

    retrieval_service = FakeRetrievalService()
    answer_service = FakeAnswerService()
    first_request = RetrievalSDKSearchRequest(
        input="JMM 的访问策略是啥？",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
    )
    second_request = RetrievalSDKSearchRequest(
        input="jmm 访问策略是啥呢",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
    )

    async for _ in _stream_retrieval_events(
        first_request,
        run_id=None,
        retrieval_service=retrieval_service,
        answer_service=answer_service,
        answer_cache=answer_cache,
        request_id="req-first",
        delta_sleep=lambda seconds: _noop_sleep(),
    ):
        pass
    second_events = [
        event async for event in _stream_retrieval_events(
            second_request,
            run_id=None,
            retrieval_service=retrieval_service,
            answer_service=answer_service,
            answer_cache=answer_cache,
            request_id="req-second",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]

    assert retrieval_service.calls == 1
    assert answer_service.calls == 1
    assert any("answer_cache_hit" in event for event in second_events)
    assert any("JMM 缓存答案" in event for event in second_events)


@pytest.mark.asyncio
async def test_cached_retrieval_stream_still_emits_recommendations(monkeypatch, tmp_path):
    """答案缓存命中时也应在完成事件后补发推荐事件。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    answer_cache = AnswerCacheService(repository, ttl_seconds=3600)
    answer_cache.set(
        input_text="适配器模式干啥的",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        answer="适配器模式用于解决接口不兼容问题。",
        citations=[{
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "document_name": "适配器模式.md",
            "title": "模式定义",
            "content": "适配器模式用于解决接口不兼容问题。",
        }],
        trace=[],
        request_id="req-seed",
        temperature=0.2,
    )

    class FakeRetrievalService:
        async def search_with_engines(self, **kwargs):
            raise AssertionError("缓存命中时不应再次检索")

    class FakeAnswerService:
        async def stream_synthesize(self, query, results):
            raise AssertionError("缓存命中时不应再次生成答案")

    class FastRecommendationService:
        async def build(self, **kwargs):
            return [{
                "metadata": {"id": "doc-2", "document_name": "六边形架构详解.md"},
                "description": "继续看端口与适配器架构。",
                "score": 0.91,
                "features": {"category": "topic_document", "tags": ["软件工程", "系统架构设计"]},
                "reason": "上位主题资料",
                "kind": "document",
                "topic_path": ["软件工程", "系统架构设计", "端口与适配器架构"],
            }]

    monkeypatch.setattr(
        "app.routers.retrieval_stream._get_topic_recommendation_service",
        lambda: FastRecommendationService(),
    )

    events = [
        event async for event in _stream_retrieval_events(
            RetrievalSDKSearchRequest(input="适配器模式干啥的", knowledge_base_ids=[kb["id"]], top_k=5),
            run_id=None,
            retrieval_service=FakeRetrievalService(),
            answer_service=FakeAnswerService(),
            answer_cache=answer_cache,
            request_id="req-cache-reco",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]
    event_names = [_event_name(event) for event in events]

    assert "recommendation.completed" in event_names
    assert event_names.index("answer.completed") < event_names.index("recommendation.completed")


@pytest.mark.asyncio
async def test_dislike_on_cache_hit_request_id_bypasses_next_stream(tmp_path):
    """点踩缓存命中的新 request_id 后，下一次同义问题必须重新检索。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    answer_cache = AnswerCacheService(repository, ttl_seconds=3600)

    class FakeRetrievalService:
        def __init__(self):
            self.calls = 0

        async def search_with_engines(self, **kwargs):
            self.calls += 1
            return {
                "request_id": kwargs["request_id"],
                "results": [{"chunk_id": "chunk-1", "document_name": "jmm.md", "title": "JMM", "content": "JMM"}],
                "trace": [{"stage": "candidate_scoring", "summary": f"fresh-{self.calls}"}],
            }

    class FakeAnswerService:
        async def stream_synthesize(self, query, results):
            yield {"text": "JMM 重新生成答案", "chunk_id": "chunk-1"}

    retrieval_service = FakeRetrievalService()
    answer_service = FakeAnswerService()
    first_request = RetrievalSDKSearchRequest(input="JMM 的访问策略是啥？", knowledge_base_ids=[kb["id"]], top_k=5)
    second_request = RetrievalSDKSearchRequest(input="jmm 访问策略是啥呢", knowledge_base_ids=[kb["id"]], top_k=5)

    async for _ in _stream_retrieval_events(
        first_request,
        run_id=None,
        retrieval_service=retrieval_service,
        answer_service=answer_service,
        answer_cache=answer_cache,
        request_id="req-first",
        delta_sleep=lambda seconds: _noop_sleep(),
    ):
        pass
    second_events = [
        event async for event in _stream_retrieval_events(
            second_request,
            run_id=None,
            retrieval_service=retrieval_service,
            answer_service=answer_service,
            answer_cache=answer_cache,
            request_id="req-cache-hit",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]
    feedback = answer_cache.record_feedback("req-cache-hit", "dislike", user_id="default")
    third_events = [
        event async for event in _stream_retrieval_events(
            second_request,
            run_id=None,
            retrieval_service=retrieval_service,
            answer_service=answer_service,
            answer_cache=answer_cache,
            request_id="req-third",
            delta_sleep=lambda seconds: _noop_sleep(),
        )
    ]

    assert any("answer_cache_hit" in event for event in second_events)
    assert feedback["deleted"] is True
    assert retrieval_service.calls == 2
    assert not any("answer_cache_hit" in event for event in third_events)


@pytest.mark.asyncio
async def test_retrieval_answer_feedback_dislike_invalidates_cache(async_client):
    """点踩会删除答案缓存，下一次同问题重新检索。"""
    kb = (
        await async_client.post("/api/v1/kb", json={"name": "KB", "description": "desc", "owner_id": "u1"})
    ).json()["data"]
    await async_client.post(
        f"/api/v1/kb/{kb['id']}/documents",
        json={"name": "jmm.md", "content": "# JMM\nJMM 访问策略", "content_type": "text/markdown", "owner_id": "u1"},
    )
    await async_client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": "u1"})
    _parse_queued_documents_for_test(kb["id"])

    first = await async_client.post(
        "/api/v1/retrieval/search/stream",
        json={"input": "JMM 的访问策略是啥？", "knowledge_base_ids": [kb["id"]], "top_k": 5},
    )
    request_id = _last_request_id(first.text)
    feedback = await async_client.post(
        f"/api/v1/retrieval/answers/{request_id}/feedback",
        json={"vote": "dislike", "user_id": "default"},
    )
    second = await async_client.post(
        "/api/v1/retrieval/search/stream",
        json={"input": "jmm 访问策略是啥呢", "knowledge_base_ids": [kb["id"]], "top_k": 5},
    )

    assert feedback.status_code == 200
    assert feedback.json()["data"]["deleted"] is True
    assert "answer_cache_hit" not in second.text


@pytest.mark.asyncio
async def test_answer_cache_management_lists_and_deletes_entries(async_client):
    """Answer Cache 管理接口支持列表和删除。"""
    kb = (
        await async_client.post("/api/v1/kb", json={"name": "KB", "description": "desc", "owner_id": "u1"})
    ).json()["data"]
    await async_client.post(
        f"/api/v1/kb/{kb['id']}/documents",
        json={"name": "jmm.md", "content": "# JMM\nJMM 访问策略", "content_type": "text/markdown", "owner_id": "u1"},
    )
    await async_client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": "u1"})
    _parse_queued_documents_for_test(kb["id"])
    await async_client.post(
        "/api/v1/retrieval/search/stream",
        json={"input": "JMM 的访问策略是啥？", "knowledge_base_ids": [kb["id"]], "top_k": 5},
    )

    list_response = await async_client.get("/api/v1/retrieval/answers/cache")
    cache_key = list_response.json()["data"]["items"][0]["cache_key"]
    delete_response = await async_client.delete(f"/api/v1/retrieval/answers/cache/{cache_key}")
    empty_response = await async_client.get("/api/v1/retrieval/answers/cache")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["normalized_query"] == "jmm 访问策略是啥"
    assert delete_response.json()["data"]["deleted"] is True
    assert empty_response.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_retrieval_stream_passes_temperature_to_answer_service():
    """流式问答应把 temperature 透传给答案生成服务。"""
    class FakeRetrievalService:
        async def search_with_engines(self, **kwargs):
            return {
                "request_id": kwargs["request_id"],
                "results": [{"chunk_id": "c1", "content": "证据", "score": 1}],
                "trace": [],
            }

    class FakeAnswerService:
        def __init__(self):
            self.temperature = None

        async def stream_synthesize(self, query, results, temperature=0.2):
            self.temperature = temperature
            yield {"text": "回答", "chunk_id": "c1"}

    answer_service = FakeAnswerService()
    async for _ in _stream_retrieval_events(
        RetrievalSDKSearchRequest(
            input="解释一下装饰器",
            knowledge_base_ids=["kb-001"],
            top_k=5,
            temperature=0.7,
        ),
        run_id=None,
        retrieval_service=FakeRetrievalService(),
        answer_service=answer_service,
        answer_cache=None,
        request_id="req-temp",
        delta_sleep=lambda seconds: _noop_sleep(),
    ):
        pass

    assert answer_service.temperature == 0.7


async def _noop_sleep() -> None:
    return None


def _event_payload(events: list[str], event_name: str) -> dict:
    """从 SSE 文本事件列表中提取指定事件 payload。"""
    for event in events:
        if f"event: {event_name}" not in event:
            continue
        data_line = next(line for line in event.splitlines() if line.startswith("data: "))
        return json.loads(data_line.removeprefix("data: "))["payload"]
    raise AssertionError(f"event not found: {event_name}")


def _event_name(event: str) -> str:
    """从 SSE 文本事件中提取 event 名称。"""
    return next(line for line in event.splitlines() if line.startswith("event: ")).removeprefix("event: ")


def _last_request_id(sse_text: str) -> str:
    request_ids = []
    for block in sse_text.strip().split("\n\n"):
        data_line = next((line for line in block.splitlines() if line.startswith("data: ")), "")
        if not data_line:
            continue
        payload = json.loads(data_line.removeprefix("data: "))
        if payload.get("request_id"):
            request_ids.append(payload["request_id"])
    return request_ids[-1]


def _parse_queued_documents_for_test(kb_id: str) -> None:
    """在 ASGITransport 测试中同步解析 queued 文档。"""
    import app.routers.retrieval_stream as retrieval_stream_router

    repository = KnowledgeBaseRepository(retrieval_stream_router.KNOWLEDGE_BASE_DB_PATH)
    chunk_service = MarkdownChunkService(max_chars=120, overlap=20)
    for document in repository.list_documents(kb_id):
        if document.get("parse_status") == "queued":
            detail = repository.get_document(kb_id, document["id"])
            chunks = chunk_service.split(detail["raw_content"])
            repository.replace_document_chunks(kb_id, document["id"], chunks)
            repository.mark_document_parsed(kb_id, document["id"], len(chunks))
            repository.mark_document_indexed(kb_id, document["id"])
