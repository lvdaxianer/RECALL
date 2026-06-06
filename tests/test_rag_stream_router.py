import json
import time
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.models.schemas import SearchResult
from app.services.rag_search_pipeline_service import SearchPipelineResult
from app.routers.rag_stream import _run_optimized_stream_search


@pytest.fixture
def app_router():
    """加载包含 RAG stream 路由的 FastAPI app。"""
    from app.main import app

    return app


@pytest_asyncio.fixture
async def async_client(app_router):
    """构建异步 HTTP 客户端。"""
    transport = ASGITransport(app=app_router)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_optimize_stream_returns_ordered_sse_events(async_client, monkeypatch):
    async def fake_optimize(query):
        return {
            "intent": "troubleshooting",
            "optimized_query": "小程序 上线 白屏 本地正常",
            "cot_plan": ["识别上线后白屏", "对比本地与线上差异"],
            "expanded_queries": ["小程序 上线 白屏", "小程序 本地正常 线上白屏"],
            "query_scope": "local",
            "route_plan": {"strategy": "local_chunk", "steps": ["chunk_retrieval"]},
            "see_trace": [
                {
                    "stage": "query_decomposition",
                    "summary": "拆解故障查询",
                    "metrics": {"query_type": "troubleshooting"},
                }
            ],
            "fallback_used": False,
        }

    async def fake_pipeline(user_id, request, prefetched_query_vector=None, retrieval_context=None, request_id=None):
        result = SearchPipelineResult(
            results=[
                SearchResult(
                    metadata={"id": request.input, "type": "skill"},
                    description=request.input,
                    score=0.88,
                )
            ],
            profile={
                "counts": {"filtered": 1, "rerank": 1},
                "timings_ms": {"total": 1.0, "rerank": 0.0},
                "fallbacks": {},
                "rerank_decision": {"skipped": True, "reason": "no_candidates"},
            },
        )
        return result

    monkeypatch.setattr("app.routers.rag_stream.get_query_optimize_service", lambda: AsyncMock(optimize=fake_optimize))
    monkeypatch.setattr("app.routers.rag_stream.run_search_pipeline_with_profile", fake_pipeline)

    response = await async_client.post(
        "/api/v1/rag/u001/search/optimize/stream",
        json={"input": "小程序上线后白屏了，之前本地开发都正常", "type": "all", "topK": 5},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: request.created" in body
    assert "event: query.decomposition" in body
    assert "event: retrieval_strategy" in body
    assert "event: retrieval.optimized.completed" in body
    assert "event: answer.completed" in body

    payloads = []
    for block in body.strip().split("\n\n"):
        data_line = next(line for line in block.splitlines() if line.startswith("data: "))
        payloads.append(json.loads(data_line.removeprefix("data: ")))

    assert [item["sequence"] for item in payloads] == sorted(item["sequence"] for item in payloads)
    assert payloads[0]["request_id"]
    assert payloads[1]["payload"]["cot_plan"] == ["识别上线后白屏", "对比本地与线上差异"]
    assert payloads[1]["payload"]["query_scope"] == "local"
    assert payloads[1]["payload"]["route_plan"]["strategy"] == "local_chunk"
    strategy_payload = next(item["payload"] for item in payloads if item["event"] == "retrieval_strategy")
    assert strategy_payload["strategy"] == "local_chunk"
    assert strategy_payload["query_scope"] == "local"
    optimized_payload = next(item["payload"] for item in payloads if item["event"] == "retrieval.optimized.completed")
    assert optimized_payload["result_ids"]


@pytest.mark.asyncio
async def test_run_optimized_stream_search_calls_pipeline_once_per_query(monkeypatch):
    calls = []

    async def fake_pipeline(user_id, request, prefetched_query_vector=None, retrieval_context=None, request_id=None):
        calls.append(request.input)
        return SearchPipelineResult(
            results=[
                SearchResult(
                    metadata={"id": request.input, "type": "skill"},
                    description=request.input,
                    score=0.8,
                )
            ],
            profile={"counts": {"filtered": 1}, "fallbacks": {}},
        )

    monkeypatch.setattr("app.routers.rag_stream.run_search_pipeline_with_profile", fake_pipeline)

    result = await _run_optimized_stream_search(
        user_id="u001",
        request=type("Request", (), {
            "type": "skill",
            "topK": 5,
            "threshold": 0,
            "enableFeatureBoost": False,
        })(),
        request_id="req-1",
        queries=["query-a", "query-b"],
        retrieval_context=None,
        query_scope="local",
        route_plan=["chunk_retrieval"],
    )

    assert calls == ["query-a", "query-b"]
    assert result["query_result_counts"] == {"query-a": 1, "query-b": 1}


@pytest.mark.asyncio
async def test_optimize_stream_emits_failed_event_when_optimizer_fails(async_client, monkeypatch):
    async def fake_optimize(query):
        raise RuntimeError("optimizer failed with token=secret")

    monkeypatch.setattr("app.routers.rag_stream.get_query_optimize_service", lambda: AsyncMock(optimize=fake_optimize))

    response = await async_client.post(
        "/api/v1/rag/u001/search/optimize/stream",
        json={"input": "小程序上线后白屏了，之前本地开发都正常", "type": "all", "topK": 5},
    )

    assert response.status_code == 200
    assert "event: request.failed" in response.text
    data_line = response.text.strip().split("\n\n")[-1].split("data: ", 1)[1]
    payload = json.loads(data_line)["payload"]
    assert payload["stage"] == "query.optimize"
    assert "secret" not in payload["message"]


@pytest.mark.asyncio
async def test_optimize_stream_emits_answer_completed_before_slow_recommendations(async_client, monkeypatch):
    """优化检索流不应因为慢推荐而延迟 answer.completed。"""
    async def fake_optimize(query):
        return {
            "intent": "design-pattern",
            "optimized_query": "适配器模式",
            "expanded_queries": ["适配器模式"],
            "query_scope": "local",
            "route_plan": {"strategy": "local_chunk", "steps": ["chunk_retrieval"]},
            "see_trace": [],
            "fallback_used": False,
        }

    async def fake_pipeline(user_id, request, prefetched_query_vector=None, retrieval_context=None, request_id=None):
        return SearchPipelineResult(
            results=[
                SearchResult(
                    metadata={"id": request.input, "type": "skill"},
                    description=request.input,
                    score=0.88,
                )
            ],
            profile={"counts": {"filtered": 1}, "fallbacks": {}, "rerank_decision": {"skipped": True}},
        )

    def slow_recommendations(*args, **kwargs):
        time.sleep(0.05)
        return []

    monkeypatch.setattr("app.routers.rag_stream.get_query_optimize_service", lambda: AsyncMock(optimize=fake_optimize))
    monkeypatch.setattr("app.routers.rag_stream.run_search_pipeline_with_profile", fake_pipeline)
    monkeypatch.setattr("app.routers.rag_stream._build_recommendations", slow_recommendations)
    monkeypatch.setattr("app.routers.rag_stream.Config.RAG_RECOMMENDATION_TIMEOUT_MS", 1, raising=False)

    response = await async_client.post(
        "/api/v1/rag/u001/search/optimize/stream",
        json={"input": "适配器模式干啥的", "type": "all", "topK": 5},
    )
    events = [
        json.loads(block.split("data: ", 1)[1])["event"]
        for block in response.text.strip().split("\n\n")
        if "data: " in block
    ]

    assert events.index("answer.completed") < events.index("recommendation.skipped")
