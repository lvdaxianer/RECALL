"""
Agent Runtime Client

第一阶段提供 LocalAgentRuntimeClient；后续扩展 HTTP/SSE 远程 Runtime。

@author lvdaxianerplus
@date 2026-06-02
"""

import json
from typing import AsyncIterator, Optional

import httpx

from app.config import Config
from app.models.agent_schemas import AgentEvent, AgentRun
from app.services.agent_tool_hooks import get_agent_tool_hook_service
from app.services.agent_tool_registry import TOOL_OPTIMIZE_QUERY, TOOL_SEARCH_RAG
from app.services.agent_tool_registry import get_agent_tool_registry
from app.services.session_service import SessionService, get_session_service

DEFAULT_ANSWER = "已完成检索计划拆解，可继续结合候选资料排查问题。"
AGENT_RUNTIME_MODE_HTTP_SSE = "http_sse"
AGENT_RUNTIME_STATUS_FAILED = "failed"
AGENT_RUNTIME_STATUS_COMPLETED = "completed"
AGENT_RUNTIME_FAILED_CODE = "AGENT_RUNTIME_STREAM_FAILED"
AGENT_RUNTIME_FAILED_MESSAGE = "Agent Runtime 流式调用失败"
AGENT_RUNTIME_ENDPOINT = "/runs"


class AgentRuntimeConfigurationError(ValueError):
    """Agent Runtime 配置错误。"""


class LocalAgentRuntimeClient:
    """本地模拟 Agent Runtime，用于跑通 API 和事件协议。"""

    def __init__(self, session_service: Optional[SessionService] = None, tool_registry=None):
        self.session_service = session_service or get_session_service()
        self.tool_registry = tool_registry or get_agent_tool_registry()

    async def run(self, user_id: str, session_id: str, run_id: str) -> AsyncIterator[AgentEvent]:
        """执行本地 Agent run 并流式产出事件。"""
        run = self.session_service.update_run(user_id, session_id, run_id, status="running")
        yield self.session_service.append_event(user_id, session_id, run_id, "run.created", {"status": "running"})

        started_event, optimize_result = await self._run_optimize_tool(user_id, session_id, run)
        yield started_event
        yield self._append_decomposition_event(user_id, session_id, run_id, optimize_result)
        yield self._append_tool_completed_event(user_id, session_id, run_id, TOOL_OPTIMIZE_QUERY, optimize_result)

        search_result = None
        if TOOL_SEARCH_RAG in run.tools:
            async for event in self._run_search_tool(user_id, session_id, run):
                if event.event == "agent.tool_call.completed":
                    search_result = event.payload.get("_tool_result")
                    event.payload.pop("_tool_result", None)
                else:
                    pass
                yield event
        else:
            pass

        answer = self._build_answer(search_result)
        yield self.session_service.append_event(user_id, session_id, run_id, "answer.delta", {"delta": answer})
        self.session_service.update_run(user_id, session_id, run_id, status="completed", answer=answer)
        yield self._append_answer_completed_event(user_id, session_id, run_id, answer, search_result)

    async def _run_optimize_tool(self, user_id: str, session_id: str, run: AgentRun) -> tuple[AgentEvent, dict]:
        """调用查询优化工具并产出 started 事件。"""
        event = self.session_service.append_event(
            user_id,
            session_id,
            run.run_id,
            "agent.tool_call.started",
            {"tool_name": TOOL_OPTIMIZE_QUERY, "arguments": {"input": run.input}},
        )
        result = await self.tool_registry.call(TOOL_OPTIMIZE_QUERY, {"input": run.input}, user_id=user_id)
        return event, result

    async def _run_search_tool(self, user_id: str, session_id: str, run: AgentRun) -> AsyncIterator[AgentEvent]:
        """调用 RAG 检索工具并产出 started/completed 事件。"""
        yield self.session_service.append_event(
            user_id,
            session_id,
            run.run_id,
            "agent.tool_call.started",
            {"tool_name": TOOL_SEARCH_RAG, "arguments": {"input": run.input}},
        )
        search_result = await self.tool_registry.call(TOOL_SEARCH_RAG, {"input": run.input}, user_id=user_id)
        yield self.session_service.append_event(
            user_id,
            session_id,
            run.run_id,
            "agent.tool_call.completed",
            {
                "tool_name": TOOL_SEARCH_RAG,
                "summary": {
                    "result_count": search_result.get("result_count", 0),
                    "recommendation_count": search_result.get("recommendation_count", 0),
                },
                "_tool_result": search_result,
            },
            request_id=search_result.get("request_id"),
        )

    def _append_decomposition_event(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        optimize_result: dict,
    ) -> AgentEvent:
        """追加 query.decomposition 事件。"""
        return self.session_service.append_event(
            user_id,
            session_id,
            run_id,
            "query.decomposition",
            {
                "intent": optimize_result.get("intent"),
                "cot_plan": optimize_result.get("cot_plan", []),
                "expanded_queries": optimize_result.get("expanded_queries", []),
            },
        )

    def _append_tool_completed_event(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        tool_name: str,
        optimize_result: dict,
    ) -> AgentEvent:
        """追加工具完成事件。"""
        return self.session_service.append_event(
            user_id,
            session_id,
            run_id,
            "agent.tool_call.completed",
            {"tool_name": tool_name, "summary": {"intent": optimize_result.get("intent")}},
        )

    def _append_answer_completed_event(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        answer: str,
        search_result: Optional[dict],
    ) -> AgentEvent:
        """追加答案完成事件并携带检索 request_id。"""
        request_id = search_result.get("request_id") if search_result else None
        recommendation_count = search_result.get("recommendation_count", 0) if search_result else 0
        return self.session_service.append_event(
            user_id,
            session_id,
            run_id,
            "answer.completed",
            {"answer": answer, "recommendation_count": recommendation_count},
            request_id=request_id,
        )

    @staticmethod
    def _build_answer(search_result: Optional[dict]) -> str:
        """根据检索结果构造本地模拟答案。"""
        if search_result is None:
            return DEFAULT_ANSWER
        else:
            return "已完成 RAG 检索，可优先检查线上资源路径、业务域名、接口域名和控制台报错。"

    async def close(self) -> None:
        """关闭本地 Runtime 资源。"""
        return None


class HttpSseAgentRuntimeClient:
    """HTTP/SSE Agent Runtime 客户端。"""

    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        hook_service=None,
    ):
        self.session_service = session_service or get_session_service()
        self.base_url = (base_url if base_url is not None else Config.AGENT_RUNTIME_BASE_URL).rstrip("/")
        if not self.base_url and http_client is None:
            raise AgentRuntimeConfigurationError("AGENT_RUNTIME_BASE_URL is required for http_sse runtime")
        else:
            pass
        self.api_key = api_key if api_key is not None else Config.AGENT_RUNTIME_API_KEY
        self.http_client = http_client or self._build_http_client()
        self.hook_service = hook_service or get_agent_tool_hook_service()

    async def run(self, user_id: str, session_id: str, run_id: str) -> AsyncIterator[AgentEvent]:
        """调用远程 HTTP/SSE Runtime 并映射为内部事件。"""
        run = self.session_service.update_run(user_id, session_id, run_id, status="running")
        try:
            response = await self.http_client.post(
                AGENT_RUNTIME_ENDPOINT,
                json=self._request_payload(user_id, session_id, run),
                headers=self._headers(),
            )
            if response.status_code == 200:
                async for event in self._events_from_response(user_id, session_id, run_id, response):
                    yield event
            else:
                yield self._append_failed_event(user_id, session_id, run_id, None)
        except httpx.HTTPError as error:
            yield self._append_failed_event(user_id, session_id, run_id, error)

    async def close(self) -> None:
        """关闭 HTTP 客户端连接池。"""
        await self.http_client.aclose()

    def _build_http_client(self) -> httpx.AsyncClient:
        """构建带超时配置的 HTTP client。"""
        timeout = httpx.Timeout(
            connect=Config.AGENT_RUNTIME_CONNECT_TIMEOUT,
            read=Config.AGENT_RUNTIME_READ_TIMEOUT,
            write=Config.AGENT_RUNTIME_CONNECT_TIMEOUT,
            pool=Config.AGENT_RUNTIME_CONNECT_TIMEOUT,
        )
        return httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        """构造远程 Runtime 请求头。"""
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        else:
            return {}

    @staticmethod
    def _request_payload(user_id: str, session_id: str, run: AgentRun) -> dict:
        """构造远程 Runtime 请求体。"""
        return {
            "user_id": user_id,
            "session_id": session_id,
            "run_id": run.run_id,
            "input": run.input,
            "tools": run.tools,
            "metadata": run.metadata,
        }

    async def _events_from_response(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        response: httpx.Response,
    ) -> AsyncIterator[AgentEvent]:
        """解析远程 SSE 响应并追加内部事件。"""
        async for block in self._iter_sse_blocks(response):
            event_name, payload = _parse_sse_block(block)
            if event_name:
                event = self._append_runtime_event(user_id, session_id, run_id, event_name, payload)
                yield event
            else:
                pass
        self._mark_completed_if_needed(user_id, session_id, run_id)

    async def _iter_sse_blocks(self, response: httpx.Response) -> AsyncIterator[str]:
        """按 SSE 空行切分远程响应。"""
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += _normalize_sse_newlines(chunk)
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                if block.strip():
                    yield block
                else:
                    pass
        if buffer.strip():
            yield buffer
        else:
            pass

    def _append_runtime_event(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        event_name: str,
        payload: dict,
    ) -> AgentEvent:
        """追加远程 Runtime 映射后的事件。"""
        request_id = payload.get("request_id")
        event = self.session_service.append_event(
            user_id,
            session_id,
            run_id,
            event_name,
            payload,
            request_id=request_id,
        )
        if event_name == "answer.completed":
            self.session_service.update_run(
                user_id,
                session_id,
                run_id,
                status=AGENT_RUNTIME_STATUS_COMPLETED,
                answer=payload.get("answer"),
                request_id=request_id,
            )
        else:
            pass
        return event

    def _mark_completed_if_needed(self, user_id: str, session_id: str, run_id: str) -> None:
        """远程流结束后补齐完成状态。"""
        run = self.session_service.get_run(user_id, session_id, run_id)
        if run.status == "running":
            self.session_service.update_run(user_id, session_id, run_id, status=AGENT_RUNTIME_STATUS_COMPLETED)
        else:
            pass

    def _append_failed_event(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        error: Exception | None,
    ) -> AgentEvent:
        """追加远程 Runtime 失败事件。"""
        payload = self.hook_service.on_runtime_error(error or RuntimeError(AGENT_RUNTIME_FAILED_MESSAGE))
        self.session_service.update_run(
            user_id,
            session_id,
            run_id,
            status=AGENT_RUNTIME_STATUS_FAILED,
            error={"stage": payload["stage"], "error_code": payload["error_code"]},
        )
        return self.session_service.append_event(
            user_id,
            session_id,
            run_id,
            "request.failed",
            payload,
        )


def _parse_sse_block(block: str) -> tuple[str, dict]:
    """解析单个 SSE block。"""
    event_name = ""
    data_lines = []
    for line in block.splitlines():
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
        else:
            pass
    return event_name, _parse_sse_data(data_lines)


def _normalize_sse_newlines(text: str) -> str:
    """兼容 LF/CRLF/CR 分隔的 SSE 流。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_sse_data(data_lines: list[str]) -> dict:
    """解析 SSE data JSON。"""
    if not data_lines:
        return {}
    raw_data = "\n".join(data_lines)
    try:
        parsed = json.loads(raw_data)
    except json.JSONDecodeError:
        return {"delta": raw_data}
    if isinstance(parsed, dict):
        return parsed
    else:
        return {"data": parsed}


_agent_runtime_client: Optional[LocalAgentRuntimeClient | HttpSseAgentRuntimeClient] = None


def get_agent_runtime_client() -> LocalAgentRuntimeClient | HttpSseAgentRuntimeClient:
    """获取全局 Agent Runtime Client 实例。"""
    global _agent_runtime_client
    if _agent_runtime_client is None:
        _agent_runtime_client = _build_agent_runtime_client()
    else:
        pass
    return _agent_runtime_client


def _build_agent_runtime_client() -> LocalAgentRuntimeClient | HttpSseAgentRuntimeClient:
    """按配置构建 Agent Runtime Client。"""
    if Config.AGENT_RUNTIME_MODE == AGENT_RUNTIME_MODE_HTTP_SSE:
        return HttpSseAgentRuntimeClient()
    else:
        return LocalAgentRuntimeClient()
