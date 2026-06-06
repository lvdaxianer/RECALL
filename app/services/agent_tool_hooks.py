"""
Agent 工具调用 Hook 服务

记录工具调用前后摘要，提供 bad feedback 和 runtime error 的统一 hook 数据。

@author lvdaxianerplus
@date 2026-06-03
"""

from datetime import datetime, timezone
from time import perf_counter
from typing import Any

REDACTED_VALUE = "[REDACTED]"
RUNTIME_ERROR_CODE = "AGENT_RUNTIME_STREAM_FAILED"
SENSITIVE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
}


class AgentToolHookService:
    """Agent 工具调用 Hook 服务。"""

    def before_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """生成工具调用前摘要。"""
        return {
            "tool_name": tool_name,
            "arguments": _redact_sensitive_values(arguments),
            "started_at": _now_iso(),
            "started_perf": perf_counter(),
        }

    def after_tool_call(
        self,
        tool_name: str,
        result: dict[str, Any],
        started_at: str,
        started_perf: float | None = None,
    ) -> dict[str, Any]:
        """生成工具调用后摘要。"""
        duration_ms = _duration_ms(started_perf)
        return {
            "tool_name": tool_name,
            "started_at": started_at,
            "duration_ms": duration_ms,
            "request_id": result.get("request_id"),
            "result_count": result.get("result_count", 0),
            "recommendation_count": result.get("recommendation_count", 0),
        }

    def on_bad_feedback(self, request_id: str | None, invalidation: dict[str, Any] | None) -> dict[str, Any]:
        """生成 bad feedback hook 摘要。"""
        return {
            "request_id": request_id,
            "rerank_cache_invalidation": invalidation or {},
        }

    def on_runtime_error(self, error: Exception) -> dict[str, Any]:
        """生成 runtime error 事件 payload。"""
        return {
            "stage": "agent_runtime",
            "error_code": RUNTIME_ERROR_CODE,
            "message": "Agent Runtime 执行失败",
        }


def _duration_ms(started_perf: float | None) -> float:
    """计算 hook 耗时。"""
    if started_perf is None:
        return 0.0
    else:
        return round((perf_counter() - started_perf) * 1000, 2)


def _now_iso() -> str:
    """生成 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _redact_sensitive_values(value: Any) -> Any:
    """递归脱敏敏感字段。"""
    if isinstance(value, dict):
        return {
            key: _redact_by_key(key, nested_value)
            for key, nested_value in value.items()
        }
    elif isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    else:
        return value


def _redact_by_key(key: str, value: Any) -> Any:
    """按字段名脱敏。"""
    if key.lower() in SENSITIVE_FIELD_NAMES:
        return REDACTED_VALUE
    else:
        return _redact_sensitive_values(value)


_agent_tool_hook_service: AgentToolHookService | None = None


def get_agent_tool_hook_service() -> AgentToolHookService:
    """获取全局 AgentToolHookService。"""
    global _agent_tool_hook_service
    if _agent_tool_hook_service is None:
        _agent_tool_hook_service = AgentToolHookService()
    else:
        pass
    return _agent_tool_hook_service
