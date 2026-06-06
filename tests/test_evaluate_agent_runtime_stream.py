"""
Agent Runtime SSE 流评测脚本测试
"""

import asyncio

from scripts.evaluate_agent_runtime_stream import StreamMetrics
from scripts.evaluate_agent_runtime_stream import _build_agent_stream_report
from scripts.evaluate_agent_runtime_stream import _build_stream_report_path
from scripts.evaluate_agent_runtime_stream import _collect_stream_metrics


class FakeResponse:
    """测试用 SSE 响应。"""

    def __init__(self, chunks):
        self.chunks = chunks

    async def aiter_text(self):
        """按测试数据输出 SSE chunk。"""
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk


def test_collect_stream_metrics_counts_events_and_disconnects():
    """Agent stream 评测统计首包延迟、事件数量和断流次数"""
    response = FakeResponse([
        "event: run.created\ndata: {}\n\n",
        "event: answer.delta\ndata: {\"delta\":\"A\"}\n\n",
        "event: answer.completed\ndata: {\"answer\":\"A\"}\n\n",
    ])

    metrics = asyncio.run(_collect_stream_metrics(response))

    assert metrics.event_count == 3
    assert metrics.disconnect_count == 0
    assert metrics.first_event_latency_ms >= 0
    assert metrics.total_latency_ms >= metrics.first_event_latency_ms


def test_collect_stream_metrics_extracts_run_id_from_event_data():
    """Agent stream 评测从 SSE data 中提取 run_id，便于报告回放定位"""
    response = FakeResponse([
        "event: run.created\ndata: {\"run_id\":\"run_001\"}\n\n",
        "event: answer.completed\ndata: {\"answer\":\"A\"}\n\n",
    ])

    metrics = asyncio.run(_collect_stream_metrics(response))

    assert metrics.run_id == "run_001"


def test_collect_stream_metrics_marks_stream_disconnect():
    """没有 answer.completed 的 SSE 流视为断流，方便评测稳定性"""
    response = FakeResponse(["event: run.created\ndata: {}\n\n"])

    metrics = asyncio.run(_collect_stream_metrics(response))

    assert metrics.event_count == 1
    assert metrics.disconnect_count == 1


def test_build_agent_stream_report_contains_phase_e_metrics():
    """Agent stream 报告包含 Phase E 要求的核心指标"""
    metrics = StreamMetrics(
        first_event_latency_ms=12.0,
        total_latency_ms=88.0,
        event_count=5,
        disconnect_count=0,
        run_id="run_001",
    )

    report = _build_agent_stream_report(metrics, user_id="u001", session_id="sess_001")

    assert report["metrics"]["first_event_latency_ms"] == 12.0
    assert report["metrics"]["total_latency_ms"] == 88.0
    assert report["metrics"]["event_count"] == 5
    assert report["metrics"]["disconnect_count"] == 0
    assert report["target"]["session_id"] == "sess_001"


def test_build_stream_report_path_uses_reports_directory():
    """Agent stream 报告写入 reports/rag_eval 的时间戳 JSON 文件"""
    output_path = _build_stream_report_path(timestamp="20260603-120102")

    assert output_path.parts[-3:] == ("reports", "rag_eval", "20260603-120102-agent-stream.json")
