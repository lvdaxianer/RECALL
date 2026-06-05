#!/usr/bin/env python
"""
Obsidian 知识库 100 案例检索评测。

Author: lvdaxianerplus
Date: 2026-06-05
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

CACHE_HIT_RATE_TARGET = 0.6
CACHE_MISS_P95_TARGET_MS = 5000


@dataclass(frozen=True)
class EvaluationCase:
    """单个检索评测案例。"""

    case_id: str
    query: str
    expected_terms: list[str]
    category: str


def build_default_cases() -> list[EvaluationCase]:
    """构建固定 100 案例，用于端到端回归。"""
    seeds = [
        ("concept", "解释一下什么是装饰器", ["装饰器"]),
        ("concept", "装饰器干啥用的", ["装饰器", "作用"]),
        ("howto", "知识库怎么分块", ["分块"]),
        ("howto", "RAG 检索流程怎么做", ["RAG", "检索"]),
        ("fault", "检索结果不准确怎么排查", ["检索"]),
        ("policy", "知识库分块有什么规范", ["分块"]),
        ("concept", "什么是向量检索", ["向量", "检索"]),
        ("concept", "微调和知识库有什么区别", ["微调", "知识库"]),
        ("howto", "如何提高缓存命中率", ["缓存"]),
        ("fault", "为什么回答没有引用来源", ["引用"]),
    ]
    cases: list[EvaluationCase] = []
    for index in range(100):
        category, query, expected_terms = seeds[index % len(seeds)]
        cases.append(
            EvaluationCase(
                case_id=f"obsidian-{index + 1:03d}",
                query=query,
                expected_terms=expected_terms,
                category=category,
            )
        )
    return cases


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总命中率、缓存命中率和缓存未命中延迟。"""
    if not results:
        return {
            "case_count": 0,
            "hit_rate": 0,
            "cache_hit_rate": 0,
            "avg_latency_ms": 0,
            "cache_miss_p95_latency_ms": 0,
            "targets": {
                "cache_hit_rate_met": False,
                "cache_miss_latency_met": False,
            },
            "misses": [],
        }
    latencies = [float(item["latency_ms"]) for item in results]
    cache_miss_latencies = [
        float(item["latency_ms"])
        for item in results
        if not item.get("cache_hit", False)
    ]
    cache_miss_p95 = _percentile(cache_miss_latencies, 95) if cache_miss_latencies else 0
    cache_hit_rate = sum(1 for item in results if item.get("cache_hit", False)) / len(results)
    return {
        "case_count": len(results),
        "hit_rate": round(sum(1 for item in results if item["hit"]) / len(results), 4),
        "cache_hit_rate": round(cache_hit_rate, 4),
        "avg_latency_ms": round(statistics.mean(latencies), 2),
        "cache_miss_p95_latency_ms": round(cache_miss_p95, 2),
        "targets": {
            "cache_hit_rate_met": cache_hit_rate >= CACHE_HIT_RATE_TARGET,
            "cache_miss_latency_met": cache_miss_p95 <= CACHE_MISS_P95_TARGET_MS,
        },
        "misses": [item for item in results if not item["hit"]],
    }


async def evaluate(
    base_url: str,
    knowledge_base_id: str,
    top_k: int,
    output_dir: Path,
    warmup: bool = True,
) -> Path:
    """执行 100 案例检索评测并写入报告。"""
    cases = build_default_cases()
    if warmup:
        await _run_cases(base_url, knowledge_base_id, top_k, cases)
    results = await _run_cases(base_url, knowledge_base_id, top_k, cases)
    report = {
        "created_at": datetime.now().isoformat(),
        "knowledge_base_id": knowledge_base_id,
        "top_k": top_k,
        "summary": summarize_results(results),
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"obsidian-retrieval-100-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


async def _run_cases(
    base_url: str,
    knowledge_base_id: str,
    top_k: int,
    cases: list[EvaluationCase],
) -> list[dict[str, Any]]:
    """执行一轮 case。"""
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        for case in cases:
            started = time.perf_counter()
            response = await post_with_retries(
                client,
                "/api/v1/retrieval/search/stream",
                {
                    "input": case.query,
                    "knowledge_base_ids": [knowledge_base_id],
                    "top_k": top_k,
                    "use_context": False,
                },
            )
            response.raise_for_status()
            latency_ms = (time.perf_counter() - started) * 1000
            body = response.text
            results.append({
                **asdict(case),
                "hit": any(term in body for term in case.expected_terms),
                "cache_hit": body_has_cache_hit(body),
                "latency_ms": round(latency_ms, 2),
            })
    return results


def body_has_cache_hit(body: str) -> bool:
    """识别当前和旧版 SSE 中的答案缓存命中标记。"""
    compact = body.replace(" ", "")
    return (
        "answer.cache.hit" in body
        or '"cache_hit":true' in compact
        or '"answer_cache_hit":true' in compact
    )


async def post_with_retries(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    attempts: int = 3,
    delay_seconds: float = 1.0,
) -> httpx.Response:
    """POST 请求，遇到瞬时网络错误时重试。"""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response
        except (httpx.HTTPError, httpx.ReadError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(delay_seconds)
    raise RuntimeError("unreachable") from last_error


def _percentile(values: list[float], percentile: int) -> float:
    """计算 nearest-rank percentile。"""
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((percentile / 100) * len(ordered) + 0.5) - 1))
    return ordered[index]


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--knowledge-base-id", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", default="docs/superpowers/reports")
    parser.add_argument("--no-warmup", action="store_true")
    return parser


async def async_main() -> Path:
    """异步 CLI 主入口。"""
    args = build_parser().parse_args()
    return await evaluate(
        base_url=args.base_url,
        knowledge_base_id=args.knowledge_base_id,
        top_k=args.top_k,
        output_dir=Path(args.output_dir),
        warmup=not args.no_warmup,
    )


def main() -> None:
    """CLI 入口。"""
    print(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
