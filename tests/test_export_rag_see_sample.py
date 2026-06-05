"""
RAG SEE 样例导出脚本测试
"""

import asyncio

from scripts.export_rag_see_sample import build_comparison
from scripts.export_rag_see_sample import build_retrieval_trace_items
from scripts.export_rag_see_sample import collect_retrieval_contexts
from scripts.export_rag_see_sample import is_prefetched_vector_batch
from scripts.export_rag_see_sample import normalize_queries
from scripts.evaluate_rag_industry50 import _prewarm_external_clients
from scripts.evaluate_rag_industry50 import _evaluate_queries
from scripts.evaluate_rag_industry50 import _build_report_path
from scripts.evaluate_rag_industry50 import _metric_summary
from scripts.evaluate_rag_industry50 import _rerank_decision_summary


def test_build_retrieval_trace_items_includes_profiles():
    """SEE 检索节点包含 profile，便于查看阶段耗时、召回数量和降级状态"""
    original_context = {
        "results": [{"id": "doc-1"}],
        "profile": {
            "counts": {"vector": 1, "es": 0, "graph": 0},
            "fallbacks": {"vector": {"used": False, "reason": ""}},
        },
    }
    optimized_context = {
        "results": [{"id": "doc-1"}],
        "expanded_queries": ["登录能力", "登录故障"],
        "query_result_counts": {"登录能力": 1, "登录故障": 1},
        "query_profiles": {
            "登录能力": {"counts": {"vector": 1}, "fallbacks": {}},
            "登录故障": {"counts": {"vector": 1}, "fallbacks": {}},
        },
    }
    comparison = build_comparison(original_context, optimized_context, latency_ms=123.4)

    trace_items = build_retrieval_trace_items(original_context, optimized_context, comparison)

    original_trace = next(item for item in trace_items if item["stage"] == "original_retrieval")
    optimized_trace = next(item for item in trace_items if item["stage"] == "optimized_retrieval")
    assert original_trace["metrics"]["profile"]["counts"]["vector"] == 1
    assert set(optimized_trace["metrics"]["query_profiles"]) == {"登录能力", "登录故障"}
    assert trace_items[-1]["metrics"]["latency_ms"] == 123.4


def test_normalize_queries_respects_optimize_query_limit(monkeypatch):
    """SEE 导出脚本同样限制优化查询数，避免样例导出比真实接口更慢"""
    monkeypatch.setattr("scripts.export_rag_see_sample.Config.RAG_OPTIMIZE_QUERY_LIMIT", 2, raising=False)

    queries = normalize_queries(
        ["登录能力", "登录故障", "登录报错"],
        "登录能力",
    )

    assert queries == ["登录能力", "登录故障"]


def test_collect_retrieval_contexts_waits_for_tasks_concurrently():
    """SEE 导出脚本并发等待原始检索和优化检索，避免样例导出耗时被串行放大"""
    events = []

    async def original():
        events.append("original_start")
        await asyncio.sleep(0.01)
        events.append("original_end")
        return {"results": [], "profile": {}}

    async def optimized():
        events.append("optimized_start")
        await asyncio.sleep(0.01)
        events.append("optimized_end")
        return {"results": [], "query_result_counts": {}, "query_profiles": {}}

    async def run():
        return await collect_retrieval_contexts(
            asyncio.create_task(original()),
            asyncio.create_task(optimized()),
        )

    original_context, optimized_context = asyncio.run(run())

    assert original_context["results"] == []
    assert optimized_context["results"] == []
    assert events.index("optimized_start") < events.index("original_end")


def test_is_prefetched_vector_batch_rejects_flat_vector():
    """批量预取向量必须是二维列表，避免异常形状被拆成 float 传入检索管线"""
    assert is_prefetched_vector_batch([[0.1, 0.2], [0.3, 0.4]], 2) is True
    assert is_prefetched_vector_batch([0.1, 0.2], 2) is False


def test_rerank_decision_summary_counts_skips_and_score_gaps():
    """行业评测汇总 Rerank 决策，便于调参跳过阈值"""
    query_profiles = [
        {
            "profile": {
                "rerank_decision": {
                    "skipped": True,
                    "score_gap": 0.03,
                    "candidate_count": 0,
                },
                "counts": {"rerank": 0},
            }
        },
        {
            "profile": {
                "rerank_decision": {
                    "skipped": False,
                    "score_gap": 0.01,
                    "candidate_count": 12,
                },
                "counts": {"rerank": 12},
            }
        },
    ]

    summary = _rerank_decision_summary(query_profiles)

    assert summary["query_count"] == 2
    assert summary["skip_count"] == 1
    assert summary["skip_rate"] == 0.5
    assert summary["candidate_count"]["avg"] == 6
    assert summary["score_gap"]["max"] == 0.03


def test_prewarm_external_clients_records_es_compatibility_latency(monkeypatch):
    """行业评测查询前预热 ES 兼容客户端，避免首条查询承担产品校验切换耗时"""
    class FakeESService:
        def __init__(self):
            self.called = False

        def is_connected(self):
            self.called = True
            return True

    fake_es = FakeESService()
    monkeypatch.setattr("scripts.evaluate_rag_industry50.get_es_service", lambda: fake_es)

    prewarm = _prewarm_external_clients()

    assert fake_es.called is True
    assert prewarm["elasticsearch"]["connected"] is True
    assert prewarm["elasticsearch"]["latency_ms"] >= 0


def test_evaluate_queries_repeat_returns_runs_with_cache_stats(monkeypatch):
    """行业评测支持重复查询轮次，用于观察 Embedding/Rerank 缓存收益"""
    calls = []

    async def fake_once(run_id, eval_type):
        calls.append((run_id, eval_type))
        return {
            "query_count": 1,
            "top1_accuracy": 1.0,
            "mrr": 1.0,
            "latency_ms": {"avg": 10},
            "stage_latency_ms": {},
            "rerank_decision_summary": {},
            "query_profiles": [],
            "per_industry_avg_ms": {},
            "rank_distribution": {"1": 1},
            "non_top1": [],
            "misses": [],
        }

    class FakeCache:
        def get_stats(self):
            return {
                "embedding_cache": {"hits": 1, "misses": 0, "sets": 1, "hit_rate": 1.0},
                "rerank_cache": {"hits": 1, "misses": 0, "sets": 1, "hit_rate": 1.0},
            }

    monkeypatch.setattr("scripts.evaluate_rag_industry50._evaluate_query_once", fake_once)
    monkeypatch.setattr("scripts.evaluate_rag_industry50.get_cache_service", lambda: FakeCache())

    summary = asyncio.run(_evaluate_queries("run-1", "eval-type", repeat=2))

    assert len(calls) == 2
    assert len(summary["runs"]) == 2
    assert summary["runs"][1]["run_index"] == 2
    assert summary["runs"][1]["cache_stats"]["rerank_cache"]["hit_rate"] == 1.0


def test_metric_summary_exposes_recall_aliases_and_stage_latency():
    """评测报告暴露 Phase E 统一指标，便于横向比较准确率和阶段耗时"""
    evaluation = {
        "top1_accuracy": 0.8,
        "top3_recall": 0.9,
        "top5_recall": 0.96,
        "latency_ms": {"avg": 120.5, "p50": 100.0, "p95": 240.0},
        "stage_latency_ms": {
            "embedding": {"avg": 20.0},
            "es_bm25": {"avg": 30.0},
            "vector_search": {"avg": 40.0},
            "graph_search": {"avg": 10.0},
            "rerank": {"avg": 15.0},
        },
    }

    metrics = _metric_summary(evaluation)

    assert metrics["recall@1"] == 0.8
    assert metrics["recall@3"] == 0.9
    assert metrics["recall@5"] == 0.96
    assert metrics["mean_latency_ms"] == 120.5
    assert metrics["p50_latency_ms"] == 100.0
    assert metrics["p95_latency_ms"] == 240.0
    assert metrics["embedding_latency_ms"] == 20.0
    assert metrics["es_latency_ms"] == 30.0
    assert metrics["milvus_latency_ms"] == 40.0
    assert metrics["graph_latency_ms"] == 10.0
    assert metrics["rerank_latency_ms"] == 15.0


def test_build_report_path_writes_under_reports_rag_eval():
    """评测报告路径固定到 reports/rag_eval，避免覆盖 data 中的 last 快照"""
    output_path = _build_report_path("industry50", timestamp="20260603-120102")

    assert output_path.parts[-3:] == ("reports", "rag_eval", "20260603-120102-industry50.json")
