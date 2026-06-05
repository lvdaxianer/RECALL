import httpx
import pytest

from app.services.agent_runtime_client import HttpSseAgentRuntimeClient
from app.services.agent_runtime_client import AgentRuntimeConfigurationError
from app.services.agent_runtime_client import get_agent_runtime_client
from app.services.session_service import SessionService


def _sse_response(status_code: int, body: str) -> httpx.Response:
    """构建 SSE HTTP 响应。"""
    return httpx.Response(
        status_code,
        headers={"content-type": "text/event-stream"},
        content=body.encode("utf-8"),
    )


@pytest.mark.asyncio
async def test_http_sse_runtime_maps_external_events_to_agent_events():
    session_service = SessionService()
    session = session_service.create_session("u001")
    run = session_service.create_run("u001", session.session_id, "小程序上线后白屏", tools=["search_rag"])

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        return _sse_response(
            200,
            '\n'.join([
                "event: answer.delta",
                'data: {"delta":"检查线上域名"}',
                "",
                "event: answer.completed",
                'data: {"answer":"检查线上域名","request_id":"req_001","recommendation_count":2}',
                "",
            ]),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://runtime")
    runtime = HttpSseAgentRuntimeClient(
        session_service=session_service,
        base_url="http://runtime",
        api_key="test-key",
        http_client=client,
    )

    events = [event async for event in runtime.run("u001", session.session_id, run.run_id)]

    assert [event.event for event in events] == ["answer.delta", "answer.completed"]
    assert events[-1].request_id == "req_001"
    assert events[-1].payload["recommendation_count"] == 2
    assert session_service.get_run("u001", session.session_id, run.run_id).status == "completed"


@pytest.mark.asyncio
async def test_http_sse_runtime_accepts_crlf_event_boundaries():
    """真实 SSE 服务常用 CRLF 分隔事件，客户端应按协议兼容解析。"""
    session_service = SessionService()
    session = session_service.create_session("u001")
    run = session_service.create_run("u001", session.session_id, "小程序上线后白屏")

    async def handler(request: httpx.Request) -> httpx.Response:
        return _sse_response(
            200,
            "\r\n".join([
                "event: answer.delta",
                'data: {"delta":"检查线上域名"}',
                "",
                "event: answer.completed",
                'data: {"answer":"检查线上域名","request_id":"req_crlf"}',
                "",
            ]),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://runtime")
    runtime = HttpSseAgentRuntimeClient(
        session_service=session_service,
        base_url="http://runtime",
        http_client=client,
    )

    events = [event async for event in runtime.run("u001", session.session_id, run.run_id)]

    assert [event.event for event in events] == ["answer.delta", "answer.completed"]
    assert events[-1].request_id == "req_crlf"
    assert session_service.get_run("u001", session.session_id, run.run_id).status == "completed"


@pytest.mark.asyncio
async def test_http_sse_runtime_emits_failed_event_for_non_200_response():
    session_service = SessionService()
    session = session_service.create_session("u001")
    run = session_service.create_run("u001", session.session_id, "小程序上线后白屏")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="token=secret unavailable")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://runtime")
    runtime = HttpSseAgentRuntimeClient(
        session_service=session_service,
        base_url="http://runtime",
        api_key="test-key",
        http_client=client,
    )

    events = [event async for event in runtime.run("u001", session.session_id, run.run_id)]

    assert events[-1].event == "request.failed"
    assert events[-1].payload["stage"] == "agent_runtime"
    assert "secret" not in events[-1].payload["message"]
    assert session_service.get_run("u001", session.session_id, run.run_id).status == "failed"


@pytest.mark.asyncio
async def test_http_sse_runtime_emits_failed_event_when_stream_breaks():
    session_service = SessionService()
    session = session_service.create_session("u001")
    run = session_service.create_run("u001", session.session_id, "小程序上线后白屏")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("token=secret timeout")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://runtime")
    runtime = HttpSseAgentRuntimeClient(
        session_service=session_service,
        base_url="http://runtime",
        api_key="test-key",
        http_client=client,
    )

    events = [event async for event in runtime.run("u001", session.session_id, run.run_id)]

    assert events[-1].event == "request.failed"
    assert events[-1].payload["error_code"] == "AGENT_RUNTIME_STREAM_FAILED"
    assert "secret" not in events[-1].payload["message"]


@pytest.mark.asyncio
async def test_http_sse_runtime_uses_runtime_error_hook_payload():
    session_service = SessionService()
    session = session_service.create_session("u001")
    run = session_service.create_run("u001", session.session_id, "小程序上线后白屏")

    class HookService:
        def on_runtime_error(self, error):
            return {
                "stage": "agent_runtime",
                "error_code": "HOOKED_RUNTIME_ERROR",
                "message": "hooked failure",
            }

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://runtime")
    runtime = HttpSseAgentRuntimeClient(
        session_service=session_service,
        base_url="http://runtime",
        http_client=client,
        hook_service=HookService(),
    )

    events = [event async for event in runtime.run("u001", session.session_id, run.run_id)]

    assert events[-1].payload["error_code"] == "HOOKED_RUNTIME_ERROR"


@pytest.mark.asyncio
async def test_http_sse_runtime_close_closes_http_client():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    runtime = HttpSseAgentRuntimeClient(base_url="http://runtime", http_client=client)

    await runtime.close()

    assert client.is_closed


def test_get_agent_runtime_client_uses_http_sse_mode(monkeypatch):
    import app.services.agent_runtime_client as runtime_module

    monkeypatch.setattr(runtime_module.Config, "AGENT_RUNTIME_MODE", "http_sse")
    monkeypatch.setattr(runtime_module.Config, "AGENT_RUNTIME_BASE_URL", "http://runtime")
    monkeypatch.setattr(runtime_module.Config, "AGENT_RUNTIME_API_KEY", "test-key")
    monkeypatch.setattr(runtime_module, "_agent_runtime_client", None)

    client = get_agent_runtime_client()

    assert isinstance(client, HttpSseAgentRuntimeClient)


def test_http_sse_runtime_requires_base_url_when_http_client_is_not_injected():
    """http_sse 模式必须显式配置 base_url，避免启动后才出现不清晰的 URL 错误"""
    with pytest.raises(AgentRuntimeConfigurationError):
        HttpSseAgentRuntimeClient(base_url="")


def test_http_sse_runtime_allows_empty_base_url_when_http_client_is_injected():
    """测试或嵌入场景注入 http_client 时允许省略 base_url"""
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))

    runtime = HttpSseAgentRuntimeClient(base_url="", http_client=client)

    assert runtime.base_url == ""
