from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.schemas import SearchResult
from app.services.agent_tool_registry import AgentToolRegistry
from app.services.rag_search_pipeline_service import SearchPipelineResult


@pytest.mark.asyncio
async def test_optimize_query_tool_returns_cot_plan(monkeypatch):
    optimizer = AsyncMock()
    optimizer.optimize.return_value = {
        "intent": "troubleshooting",
        "optimized_query": "小程序 上线 白屏",
        "cot_plan": ["识别白屏现象"],
        "expanded_queries": ["小程序 上线 白屏"],
    }
    registry = AgentToolRegistry(query_optimize_service=optimizer)

    result = await registry.call("optimize_query", {"input": "小程序上线后白屏"}, user_id="u001")

    assert result["intent"] == "troubleshooting"
    assert result["cot_plan"] == ["识别白屏现象"]


@pytest.mark.asyncio
async def test_invalidate_rerank_cache_tool_calls_cache_service():
    cache = AsyncMock()
    cache.invalidate_rerank_by_request_id.return_value = {"request_id": "req_001", "invalidated": 1}
    registry = AgentToolRegistry(cache_service=cache)

    result = await registry.call("invalidate_rerank_cache", {"request_id": "req_001"}, user_id="u001")

    assert result["invalidated"] == 1
    cache.invalidate_rerank_by_request_id.assert_called_once_with("req_001")


@pytest.mark.asyncio
async def test_search_rag_tool_returns_request_id_and_result_count(monkeypatch):
    async def fake_pipeline(user_id, request, prefetched_query_vector=None, retrieval_context=None, request_id=None):
        return SearchPipelineResult(
            results=[
                SearchResult(metadata={"id": "doc-1"}, description="白屏排查", score=0.9),
                SearchResult(metadata={"id": "doc-2"}, description="域名检查", score=0.8),
            ],
            profile={"counts": {"filtered": 2}},
        )

    monkeypatch.setattr("app.services.agent_tool_registry.run_search_pipeline_with_profile", fake_pipeline)
    registry = AgentToolRegistry()

    result = await registry.call("search_rag", {"input": "小程序上线后白屏"}, user_id="u001")

    assert result["request_id"].startswith("req_")
    assert result["result_count"] == 2
    assert result["recommendation_count"] == 0


def test_record_bad_case_tool_reuses_evaluation_service():
    evaluation_service = MagicMock()
    evaluation_service.add_record.return_value = {"record_id": "eval_001"}
    registry = AgentToolRegistry(evaluation_service=evaluation_service)

    result = registry.call_sync(
        "record_bad_case",
        {
            "query": "小程序上线后白屏",
            "optimized_query": "小程序 上线 白屏",
            "retrieved_ids": ["doc-1"],
            "miss_reason": "rerank_error",
            "human_label": "bad",
        },
        user_id="u001",
    )

    assert result["record_id"] == "eval_001"
    assert result["rerank_cache_invalidation"] == {}
    evaluation_service.add_record.assert_called_once()


@pytest.mark.asyncio
async def test_explain_graph_tool_returns_graph_matches():
    graph_service = MagicMock()
    graph_service.explain.return_value = {
        "query": "JWT 登录认证",
        "search_type": "skill",
        "top_k": 3,
        "matched_entities": ["jwt"],
        "matched_relation_terms": ["登录认证"],
        "result_count": 1,
        "matches": [{"id": "skill-jwt", "match_type": "entity"}],
    }
    registry = AgentToolRegistry(graph_service=graph_service)

    result = await registry.call(
        "explain_graph",
        {"query": "JWT 登录认证", "type": "skill", "topK": 3},
        user_id="u001",
    )

    assert result["matches"][0]["id"] == "skill-jwt"
    assert result["matched_entities"] == ["jwt"]
    graph_service.explain.assert_called_once_with("JWT 登录认证", search_type="skill", top_k=3)


@pytest.mark.asyncio
async def test_get_cache_stats_tool_returns_cache_service_stats():
    cache = MagicMock()
    cache.get_stats.return_value = {"embedding_cache": {"hits": 1}}
    registry = AgentToolRegistry(cache_service=cache)

    result = await registry.call("get_cache_stats", {}, user_id="u001")

    assert result == {"embedding_cache": {"hits": 1}}
    cache.get_stats.assert_called_once()


@pytest.mark.asyncio
async def test_get_evaluation_summary_tool_returns_user_summary():
    evaluation_service = MagicMock()
    evaluation_service.summary_user_records.return_value = {"total_count": 2}
    registry = AgentToolRegistry(evaluation_service=evaluation_service)

    result = await registry.call("get_evaluation_summary", {}, user_id="u001")

    assert result == {"total_count": 2}
    evaluation_service.summary_user_records.assert_called_once_with("u001")


@pytest.mark.asyncio
async def test_tool_registry_calls_before_and_after_hooks(monkeypatch):
    optimizer = AsyncMock()
    optimizer.optimize.return_value = {"intent": "troubleshooting", "cot_plan": []}
    hooks = MagicMock()
    hooks.before_tool_call.return_value = {"started_at": "2026-06-02T10:00:00Z"}
    hooks.after_tool_call.return_value = {"duration_ms": 1}
    registry = AgentToolRegistry(query_optimize_service=optimizer, hook_service=hooks)

    await registry.call("optimize_query", {"input": "小程序上线后白屏"}, user_id="u001")

    hooks.before_tool_call.assert_called_once_with("optimize_query", {"input": "小程序上线后白屏"})
    hooks.after_tool_call.assert_called_once()


def test_record_bad_case_with_request_id_invalidates_rerank_cache():
    evaluation_service = MagicMock()
    evaluation_service.add_record.return_value = {"record_id": "eval_001"}
    cache = MagicMock()
    cache.invalidate_rerank_by_request_id.return_value = {"invalidated": 1}
    registry = AgentToolRegistry(cache_service=cache, evaluation_service=evaluation_service)

    result = registry.call_sync(
        "record_bad_case",
        {
            "query": "小程序上线后白屏",
            "retrieved_ids": ["doc-1"],
            "miss_reason": "rerank_error",
            "human_label": "bad",
            "request_id": "req_001",
        },
        user_id="u001",
    )

    assert result["rerank_cache_invalidation"] == {"invalidated": 1}
    cache.invalidate_rerank_by_request_id.assert_called_once_with("req_001")


@pytest.mark.asyncio
async def test_bad_feedback_api_reuses_record_bad_case_tool(monkeypatch):
    """SEE 页面 Bad feedback API 复用 Agent 工具并保留 request_id 撤销能力"""
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async def fake_call(tool_name, arguments, user_id):
        assert tool_name == "record_bad_case"
        assert user_id == "u001"
        assert arguments["request_id"] == "req_001"
        return {
            "record_id": "eval_001",
            "rerank_cache_invalidation": {"request_id": "req_001", "invalidated": 1},
        }

    registry = AsyncMock()
    registry.call.side_effect = fake_call
    monkeypatch.setattr("app.routers.rag_insights.get_agent_tool_registry", lambda: registry)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rag/u001/feedback/bad-case",
            json={
                "query": "小程序上线后白屏",
                "retrieved_ids": ["doc-1"],
                "miss_reason": "rerank_error",
                "human_label": "bad",
                "request_id": "req_001",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["record_id"] == "eval_001"
    registry.call.assert_called_once()
