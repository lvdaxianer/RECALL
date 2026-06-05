"""
SSE 事件序列化服务

把 AgentEvent 转成 text/event-stream 兼容格式。

@author lvdaxianerplus
@date 2026-06-02
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.agent_schemas import AgentEvent

REDACTED_VALUE = "[REDACTED]"
SENSITIVE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
}


def build_event(
    event: str,
    user_id: str,
    sequence: int,
    payload: Optional[dict[str, Any]] = None,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> AgentEvent:
    """构建标准 SSE/SEE 事件。"""
    return AgentEvent(
        event_id=f"evt_{uuid.uuid4().hex}",
        event=event,
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
        request_id=request_id,
        sequence=sequence,
        payload=payload or {},
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def encode_sse_event(event: AgentEvent) -> str:
    """序列化为 SSE 文本块。"""
    data = event.model_dump()
    data["payload"] = _redact_sensitive_values(data.get("payload", {}))
    return (
        f"event: {event.event}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _redact_sensitive_values(value: Any) -> Any:
    """递归脱敏 dict/list 中的敏感字段。"""
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
    """按字段名判断是否需要脱敏。"""
    normalized_key = key.lower()
    if normalized_key in SENSITIVE_FIELD_NAMES:
        return REDACTED_VALUE
    else:
        return _redact_sensitive_values(value)
