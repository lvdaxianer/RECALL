"""
Agent Runtime API 路由

提供 session、run 和事件回放接口。

@author lvdaxianerplus
@date 2026-06-02
"""

from typing import Any, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.models.schemas import APIResponse
from app.services.agent_runtime_client import get_agent_runtime_client
from app.services.runtime_orchestrator import get_runtime_orchestrator
from app.services.sandbox_service import get_sandbox_service
from app.services.session_service import get_session_service
from app.services.sse_event_service import encode_sse_event

router = APIRouter(prefix="/api/v1/agent", tags=["Agent Runtime"])


class CreateSessionRequest(BaseModel):
    """创建 Agent Session 请求。"""

    title: Optional[str] = Field(None, description="会话标题")
    runtime: str = Field("local", description="运行环境类型")
    metadata: dict[str, Any] = Field(default_factory=dict, description="调用方元数据")


class CreateRunRequest(BaseModel):
    """创建 Agent Run 请求。"""

    input: str = Field(..., min_length=1, description="用户输入")
    stream: bool = Field(True, description="是否使用 SSE 流式返回")
    tools: list[str] = Field(default_factory=list, description="允许工具")
    metadata: dict[str, Any] = Field(default_factory=dict, description="调用方元数据")


class UpdateSessionRequest(BaseModel):
    """更新 Agent Session 请求。"""

    title: Optional[str] = Field(None, min_length=1, max_length=80, description="会话标题")


@router.get("/runtimes/{runtime_id}/health", response_model=APIResponse)
async def get_runtime_health(runtime_id: str):
    """
    检查 runtime 健康状态

    @param runtime_id - Runtime ID
    @returns runtime 状态
    """
    return APIResponse(data=get_runtime_orchestrator().health_check(runtime_id))


@router.post("/runtimes/{runtime_id}/stop", response_model=APIResponse)
async def stop_runtime(runtime_id: str):
    """
    停止 runtime

    @param runtime_id - Runtime ID
    @returns 停止结果
    """
    return APIResponse(data=get_runtime_orchestrator().stop_runtime(runtime_id))


@router.post("/runtimes/cleanup", response_model=APIResponse)
async def cleanup_idle_runtimes():
    """
    清理空闲 runtime

    @returns 清理结果
    """
    return APIResponse(data=get_runtime_orchestrator().cleanup_idle_runtimes())


@router.post("/{user_id}/sessions", response_model=APIResponse)
async def create_session(user_id: str, request: CreateSessionRequest):
    """
    创建 Agent session

    @param user_id - 用户 ID
    @param request - 创建 session 请求
    @returns session 数据
    """
    session = get_session_service().create_session(
        user_id=user_id,
        title=request.title,
        runtime=request.runtime,
        metadata=request.metadata,
    )
    _ensure_session_runtime(user_id, session.session_id, request.runtime)
    return APIResponse(data=session.model_dump())


@router.get("/{user_id}/sessions", response_model=APIResponse)
async def list_sessions(user_id: str):
    """
    列出 Agent sessions

    @param user_id - 用户 ID
    @returns session 列表
    """
    sessions = get_session_service().list_sessions(user_id)
    return APIResponse(data=[session.model_dump() for session in sessions])


@router.patch("/{user_id}/sessions/{session_id}", response_model=APIResponse)
async def update_session(user_id: str, session_id: str, request: UpdateSessionRequest):
    """
    更新 Agent session 元数据。

    @param user_id - 用户 ID
    @param session_id - 会话 ID
    @param request - 更新请求
    @returns session 数据
    """
    session_service = get_session_service()
    session = session_service.get_session(user_id, session_id)
    if request.title is not None:
        session = session_service.update_session_title(user_id, session_id, request.title, source="manual")
    return APIResponse(data=session.model_dump())


@router.post("/{user_id}/sessions/{session_id}/runs")
async def create_run(user_id: str, session_id: str, request: CreateRunRequest):
    """
    创建并执行 Agent run

    @param user_id - 用户 ID
    @param session_id - 会话 ID
    @param request - 创建 run 请求
    @returns SSE 流或完成后的 run 数据
    """
    session_service = get_session_service()
    run = session_service.create_run(
        user_id=user_id,
        session_id=session_id,
        input_text=request.input,
        tools=request.tools,
        metadata=request.metadata,
    )
    if request.stream:
        return _stream_run_response(user_id, session_id, run.run_id)
    else:
        await _drain_run(user_id, session_id, run.run_id)
        completed = session_service.get_run(user_id, session_id, run.run_id)
        return APIResponse(data=completed.model_dump())


@router.get("/{user_id}/sessions/{session_id}/runs", response_model=APIResponse)
async def list_runs(user_id: str, session_id: str):
    """
    列出 Agent runs

    @param user_id - 用户 ID
    @param session_id - 会话 ID
    @returns run 列表
    """
    runs = get_session_service().list_runs(user_id, session_id)
    return APIResponse(data=[run.model_dump() for run in runs])


@router.get("/{user_id}/sessions/{session_id}/events", response_model=APIResponse)
async def list_events(
    user_id: str,
    session_id: str,
    run_id: str = Query(...),
    after_event_id: Optional[str] = Query(None),
):
    """
    查询 Agent run 事件

    @param user_id - 用户 ID
    @param session_id - 会话 ID
    @param run_id - 执行 ID
    @param after_event_id - 断点事件 ID
    @returns 事件列表
    """
    events = get_session_service().list_events(user_id, session_id, run_id, after_event_id)
    return APIResponse(data=[event.model_dump() for event in events])


def _stream_run_response(user_id: str, session_id: str, run_id: str) -> StreamingResponse:
    """构造 Agent run SSE 响应。"""

    async def stream_events():
        async for event in get_agent_runtime_client().run(user_id, session_id, run_id):
            yield encode_sse_event(event)

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _ensure_session_runtime(user_id: str, session_id: str, runtime: str) -> None:
    """为 session 准备 sandbox profile 和 local runtime。"""
    sandbox_service = get_sandbox_service()
    profile = sandbox_service.build_profile(user_id=user_id, session_id=session_id, runtime=runtime)
    ensured_profile = sandbox_service.ensure_profile_directories(profile)
    get_runtime_orchestrator().ensure_runtime(ensured_profile)


async def _drain_run(user_id: str, session_id: str, run_id: str) -> None:
    """执行 run 并消费所有事件。"""
    async for _ in get_agent_runtime_client().run(user_id, session_id, run_id):
        pass
