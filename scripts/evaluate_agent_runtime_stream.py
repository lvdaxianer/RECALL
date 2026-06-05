#!/usr/bin/env python
"""
Agent Runtime SSE 流式评测脚本。

统计首事件延迟、总耗时、事件数量和断流次数，报告写入 reports/rag_eval。
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

REPORT_KIND_AGENT_STREAM = "agent-stream"
REPORTS_DIR = PROJECT_ROOT / "reports" / "rag_eval"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_USER_ID = "agent_eval"
DEFAULT_INPUT = "我的小程序上线后白屏了，之前本地开发都正常，帮我分析并给排查步骤"
DEFAULT_TOOLS = ["optimize_query", "search_rag"]
ANSWER_COMPLETED_EVENT = "answer.completed"


@dataclass
class StreamMetrics:
    """Agent Runtime SSE 流统计指标。"""

    first_event_latency_ms: float
    total_latency_ms: float
    event_count: int
    disconnect_count: int
    run_id: str = ""


async def _collect_stream_metrics(response: Any) -> StreamMetrics:
    """从 SSE 响应对象收集流式评测指标。"""
    started = time.perf_counter()
    first_event_latency_ms = 0.0
    event_count = 0
    has_completed = False
    run_id = ""
    async for block in _iter_sse_blocks(response):
        event_count += 1
        payload = _parse_event_payload(block)
        if event_count == 1:
            first_event_latency_ms = _elapsed_ms(started)
        else:
            pass
        if not run_id:
            run_id = str(payload.get("run_id") or "")
        else:
            pass
        if _parse_event_name(block) == ANSWER_COMPLETED_EVENT:
            has_completed = True
        else:
            pass
    total_latency_ms = _elapsed_ms(started)
    return StreamMetrics(
        first_event_latency_ms=first_event_latency_ms,
        total_latency_ms=total_latency_ms,
        event_count=event_count,
        disconnect_count=0 if has_completed else 1,
        run_id=run_id,
    )


async def _iter_sse_blocks(response: Any) -> AsyncIterator[str]:
    """按 SSE 空行切分响应文本。"""
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
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


def _parse_event_name(block: str) -> str:
    """解析 SSE block 中的 event 名称。"""
    for line in block.splitlines():
        if line.startswith("event:"):
            return line.removeprefix("event:").strip()
        else:
            pass
    return ""


def _parse_event_payload(block: str) -> dict[str, Any]:
    """解析 SSE block 中的 JSON data。"""
    data_lines = [
        line.removeprefix("data:").strip()
        for line in block.splitlines()
        if line.startswith("data:")
    ]
    if not data_lines:
        return {}
    try:
        payload = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _build_agent_stream_report(
    metrics: StreamMetrics,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    """构造 Agent stream 评测报告。"""
    return {
        "kind": REPORT_KIND_AGENT_STREAM,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target": {
            "user_id": user_id,
            "session_id": session_id,
            "run_id": metrics.run_id,
        },
        "metrics": asdict(metrics),
    }


def _build_stream_report_path(timestamp: str) -> Path:
    """构造 Agent stream Phase E 报告路径。"""
    return REPORTS_DIR / f"{timestamp}-{REPORT_KIND_AGENT_STREAM}.json"


def _elapsed_ms(started: float) -> float:
    """计算毫秒耗时。"""
    return round((time.perf_counter() - started) * 1000, 2)


async def _create_session(client: httpx.AsyncClient, user_id: str) -> str:
    """创建 Agent session 并返回 session_id。"""
    response = await client.post(f"/api/v1/agent/{user_id}/sessions", json={"title": "Agent stream 评测"})
    response.raise_for_status()
    return response.json()["data"]["session_id"]


async def _evaluate_stream(
    base_url: str,
    user_id: str,
    input_text: str,
    tools: list[str],
) -> dict[str, Any]:
    """调用 Agent Runtime SSE 接口并生成评测报告。"""
    async with httpx.AsyncClient(base_url=base_url, timeout=None) as client:
        session_id = await _create_session(client, user_id)
        async with client.stream(
            "POST",
            f"/api/v1/agent/{user_id}/sessions/{session_id}/runs",
            json={"input": input_text, "stream": True, "tools": tools},
        ) as response:
            response.raise_for_status()
            metrics = await _collect_stream_metrics(response)
    return _build_agent_stream_report(metrics, user_id=user_id, session_id=session_id)


async def main() -> None:
    """执行 Agent Runtime SSE 流式评测。"""
    parser = argparse.ArgumentParser(description="Agent Runtime SSE 流式评测")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Recall API base URL")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="评测用户 ID")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Agent 输入")
    parser.add_argument("--tools", nargs="*", default=DEFAULT_TOOLS, help="允许调用的工具")
    args = parser.parse_args()

    report = await _evaluate_stream(args.base_url.rstrip("/"), args.user_id, args.input, args.tools)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _build_stream_report_path(timestamp)
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    output_path.write_text(report_json, encoding="utf-8")
    print(report_json)
    print(f"report_path={output_path}")


if __name__ == "__main__":
    asyncio.run(main())
