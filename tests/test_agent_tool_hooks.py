from app.services.agent_tool_hooks import AgentToolHookService


def test_hook_service_records_before_and_after_tool_call():
    hooks = AgentToolHookService()

    started = hooks.before_tool_call("search_rag", {"input": "小程序上线后白屏", "api_key": "secret"})
    completed = hooks.after_tool_call(
        "search_rag",
        {"request_id": "req_001", "result_count": 2, "recommendation_count": 1},
        started_at=started["started_at"],
    )

    assert started["tool_name"] == "search_rag"
    assert started["arguments"]["api_key"] == "[REDACTED]"
    assert completed["tool_name"] == "search_rag"
    assert completed["request_id"] == "req_001"
    assert completed["result_count"] == 2
    assert completed["duration_ms"] >= 0


def test_runtime_error_hook_returns_failed_payload_without_secret():
    hooks = AgentToolHookService()

    payload = hooks.on_runtime_error(RuntimeError("token=secret failed"))

    assert payload["stage"] == "agent_runtime"
    assert payload["error_code"] == "AGENT_RUNTIME_STREAM_FAILED"
    assert "secret" not in payload["message"]
