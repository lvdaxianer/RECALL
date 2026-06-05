from unittest.mock import AsyncMock

import pytest

from app.services.agent_runtime_client import LocalAgentRuntimeClient
from app.services.session_service import SessionService


@pytest.mark.asyncio
async def test_local_runtime_emits_tool_and_answer_events():
    session_service = SessionService()
    session = session_service.create_session("u001")
    run = session_service.create_run("u001", session.session_id, "小程序上线后白屏", tools=["optimize_query"])
    registry = AsyncMock()
    registry.call.return_value = {
        "intent": "troubleshooting",
        "cot_plan": ["识别白屏现象"],
        "expanded_queries": ["小程序 上线 白屏"],
    }
    client = LocalAgentRuntimeClient(session_service=session_service, tool_registry=registry)

    events = [event async for event in client.run("u001", session.session_id, run.run_id)]

    assert [event.event for event in events] == [
        "run.created",
        "agent.tool_call.started",
        "query.decomposition",
        "agent.tool_call.completed",
        "answer.delta",
        "answer.completed",
    ]


@pytest.mark.asyncio
async def test_local_runtime_can_emit_search_request_id_and_recommendation_count():
    session_service = SessionService()
    session = session_service.create_session("u001")
    run = session_service.create_run(
        "u001",
        session.session_id,
        "小程序上线后白屏",
        tools=["optimize_query", "search_rag"],
    )
    registry = AsyncMock()
    registry.call.side_effect = [
        {
            "intent": "troubleshooting",
            "cot_plan": ["识别白屏现象"],
            "expanded_queries": ["小程序 上线 白屏"],
        },
        {
            "request_id": "req_001",
            "result_count": 2,
            "recommendation_count": 1,
            "results": [],
            "profile": {},
        },
    ]
    client = LocalAgentRuntimeClient(session_service=session_service, tool_registry=registry)

    events = [event async for event in client.run("u001", session.session_id, run.run_id)]

    completed = events[-1]
    assert completed.event == "answer.completed"
    assert completed.request_id == "req_001"
    assert completed.payload["recommendation_count"] == 1
