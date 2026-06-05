"""
Agent Runtime 数据模型

定义 session、run、tool call、SSE event 和 sandbox profile 的 API 契约。

@author lvdaxianerplus
@date 2026-06-02
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AgentSession(BaseModel):
    """Agent 会话模型"""

    session_id: str = Field(..., description="会话 ID")
    user_id: str = Field(..., description="用户 ID")
    runtime_id: str = Field(..., description="运行环境 ID")
    title: Optional[str] = Field(None, description="会话标题")
    status: Literal["active", "closed"] = Field("active", description="会话状态")
    metadata: dict[str, Any] = Field(default_factory=dict, description="调用方元数据")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class AgentRun(BaseModel):
    """Agent 单次执行模型"""

    run_id: str = Field(..., description="执行 ID")
    user_id: str = Field(..., description="用户 ID")
    session_id: str = Field(..., description="会话 ID")
    request_id: Optional[str] = Field(None, description="关联 RAG request_id")
    input: str = Field(..., description="用户输入")
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = Field(
        ...,
        description="执行状态",
    )
    tools: list[str] = Field(default_factory=list, description="允许调用的工具")
    answer: Optional[str] = Field(None, description="最终答案")
    error: Optional[dict[str, Any]] = Field(None, description="错误信息")
    metadata: dict[str, Any] = Field(default_factory=dict, description="调用方元数据")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class AgentToolCall(BaseModel):
    """Agent 工具调用模型"""

    tool_call_id: str = Field(..., description="工具调用 ID")
    run_id: str = Field(..., description="执行 ID")
    tool_name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    status: Literal["running", "completed", "failed"] = Field(..., description="调用状态")
    result_summary: dict[str, Any] = Field(default_factory=dict, description="结果摘要")
    duration_ms: Optional[float] = Field(None, description="调用耗时")


class AgentEvent(BaseModel):
    """Agent/RAG SSE 事件模型"""

    event_id: str = Field(..., description="事件 ID")
    event: str = Field(..., description="事件类型")
    user_id: str = Field(..., description="用户 ID")
    session_id: Optional[str] = Field(None, description="会话 ID")
    run_id: Optional[str] = Field(None, description="执行 ID")
    request_id: Optional[str] = Field(None, description="RAG 请求 ID")
    sequence: int = Field(..., description="事件序号", ge=1)
    payload: dict[str, Any] = Field(default_factory=dict, description="事件负载")
    created_at: str = Field(..., description="创建时间")


class SandboxProfile(BaseModel):
    """用户隔离运行配置"""

    user_id: str = Field(..., description="用户 ID")
    session_id: Optional[str] = Field(None, description="会话 ID")
    runtime_id: str = Field(..., description="运行环境 ID")
    namespace: str = Field(..., description="隔离命名空间")
    memory_path: str = Field(..., description="记忆目录")
    config_path: str = Field(..., description="配置目录")
    cache_namespace: str = Field(..., description="缓存命名空间")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
