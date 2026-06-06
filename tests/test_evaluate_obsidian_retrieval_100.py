"""
Obsidian 100 案例评测脚本测试

Author: lvdaxianerplus
Date: 2026-06-05
"""

import httpx
import pytest

from scripts.evaluate_obsidian_retrieval_100 import build_default_cases
from scripts.evaluate_obsidian_retrieval_100 import body_has_cache_hit
from scripts.evaluate_obsidian_retrieval_100 import post_with_retries
from scripts.evaluate_obsidian_retrieval_100 import summarize_results


def test_build_default_cases_returns_exactly_100_cases():
    """默认评测集固定为 100 个案例。"""
    cases = build_default_cases()

    assert len(cases) == 100
    assert all(case.query.strip() for case in cases)
    assert all(case.expected_terms for case in cases)


def test_summarize_results_calculates_cache_and_latency_metrics():
    """汇总报告包含缓存命中率和未命中 p95 延迟。"""
    summary = summarize_results([
        {"case_id": "c1", "hit": True, "latency_ms": 100, "cache_hit": True},
        {"case_id": "c2", "hit": False, "latency_ms": 300, "cache_hit": False},
        {"case_id": "c3", "hit": True, "latency_ms": 700, "cache_hit": False},
    ])

    assert summary["case_count"] == 3
    assert summary["hit_rate"] == 0.6667
    assert summary["cache_hit_rate"] == 0.3333
    assert summary["cache_miss_p95_latency_ms"] == 700
    assert summary["targets"]["cache_hit_rate_met"] is False
    assert summary["targets"]["cache_miss_latency_met"] is True


def test_body_has_cache_hit_detects_current_sse_field_name():
    """缓存命中识别兼容当前 SSE 的 answer_cache_hit 字段。"""
    body = 'event: answer.completed\ndata: {"payload":{"answer_cache_hit": true}}\n\n'

    assert body_has_cache_hit(body) is True


@pytest.mark.asyncio
async def test_post_with_retries_recovers_from_transient_read_error():
    """评测请求遇到瞬时读失败时会重试。"""

    class FlakyClient:
        def __init__(self):
            self.calls = 0

        async def post(self, url, json):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ReadError("temporary")
            return httpx.Response(200, text="data: ok", request=httpx.Request("POST", url))

    client = FlakyClient()

    response = await post_with_retries(client, "/stream", {"input": "q"}, attempts=2, delay_seconds=0)

    assert response.text == "data: ok"
    assert client.calls == 2
