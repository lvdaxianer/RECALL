#!/usr/bin/env python
"""
导出一次真实 RAG 优化检索 SEE 样例。

默认复用 data/rag_eval_industry50_last.json 中的 run_id/eval_type，避免重复写入评测数据。
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Config
from app.models.schemas import SearchRequest, SearchResult
from app.services.query_optimize_service import get_query_optimize_service
from app.services.rag_search_pipeline_service import get_embedding_service
from app.services.rag_search_pipeline_service import run_search_pipeline_with_profile
from scripts.evaluate_rag_industry50 import DOCS
from scripts.evaluate_rag_industry50 import _build_features
from app.services.graph_retrieval_service import get_graph_retrieval_service


def load_last_eval_context(default_query: str) -> Dict[str, str]:
    """读取最近一次行业评测上下文。"""
    report_path = PROJECT_ROOT / "data" / "rag_eval_industry50_last.json"
    if not report_path.exists():
        return {"run_id": "", "eval_type": "skill", "query": default_query}

    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "run_id": report.get("run_id", ""),
        "eval_type": report.get("eval_type", "skill"),
        "query": default_query,
    }


def rebuild_graph_for_eval(run_id: str, eval_type: str) -> None:
    """用行业评测数据重建内存图索引。"""
    if not run_id or not eval_type:
        return

    graph_documents = [
        {
            "id": f"{run_id}_{doc['slug']}",
            "description": doc["description"],
            "metadata": {
                "type": eval_type,
                "id": f"{run_id}_{doc['slug']}",
                "description": doc["description"],
                "industry": doc["industry"],
                "title": doc["title"],
                "run_id": run_id,
                "expected_slug": doc["slug"],
            },
            "features": _build_features(doc),
        }
        for doc in DOCS
    ]
    get_graph_retrieval_service().rebuild(graph_documents)


async def run_query_with_profile(
    user_id: str,
    query: str,
    search_type: str,
    top_k: int,
    prefetched_query_vector: List[float] = None,
) -> Dict[str, Any]:
    """执行一次检索并返回结果和 profile。"""
    pipeline_result = await run_search_pipeline_with_profile(
        user_id,
        SearchRequest(
            input=query,
            type=search_type,
            topK=top_k,
            threshold=0,
            enableFeatureBoost=False,
        ),
        prefetched_query_vector=prefetched_query_vector,
    )
    return {
        "results": serialize_results(pipeline_result.results),
        "profile": pipeline_result.profile,
    }


async def run_optimized_queries(
    user_id: str,
    queries: List[str],
    search_type: str,
    top_k: int,
) -> Dict[str, Any]:
    """执行多个优化查询并合并 profile。"""
    prefetched_vectors = await prefetch_query_vectors(queries)
    contexts = await asyncio.gather(*[
        run_query_with_profile(
            user_id,
            query,
            search_type,
            top_k,
            prefetched_query_vector=prefetched_vectors.get(query),
        )
        for query in queries
    ])
    query_result_counts = {
        queries[index]: len(context["results"])
        for index, context in enumerate(contexts)
    }
    query_profiles = {
        queries[index]: context["profile"]
        for index, context in enumerate(contexts)
    }
    return {
        "results": merge_serialized_results([context["results"] for context in contexts], top_k),
        "query_result_counts": query_result_counts,
        "query_profiles": query_profiles,
    }


async def prefetch_query_vectors(queries: List[str]) -> Dict[str, List[float]]:
    """批量预取优化查询向量。"""
    if len(queries) <= 1:
        return {}
    try:
        vectors = await get_embedding_service().encode(queries)
    except Exception:
        return {}
    if not is_prefetched_vector_batch(vectors, len(queries)):
        return {}
    return {
        query: vector
        for query, vector in zip(queries, vectors)
    }


def is_prefetched_vector_batch(vectors: object, expected_count: int) -> bool:
    """校验批量向量结果形状。"""
    return (
        isinstance(vectors, list)
        and len(vectors) == expected_count
        and all(isinstance(vector, list) for vector in vectors)
    )


def serialize_results(results: List[SearchResult]) -> List[Dict[str, Any]]:
    """序列化检索结果，控制输出体积。"""
    serialized = []
    for result in results:
        serialized.append({
            "id": result.metadata.get("id"),
            "title": result.metadata.get("title"),
            "industry": result.metadata.get("industry"),
            "description": result.description,
            "score": result.score,
        })
    return serialized


def merge_serialized_results(result_lists: List[List[Dict[str, Any]]], top_k: int) -> List[Dict[str, Any]]:
    """按 id 去重合并多查询结果。"""
    merged = []
    seen_ids = set()
    for results in result_lists:
        for result in results:
            doc_id = result.get("id")
            if doc_id in seen_ids:
                continue
            if doc_id:
                seen_ids.add(doc_id)
            merged.append(result)
            if len(merged) >= top_k:
                return merged
    return merged


def normalize_queries(expanded_queries: List[str], optimized_query: str) -> List[str]:
    """规范化优化查询列表。"""
    queries = [optimized_query, *expanded_queries]
    normalized = []
    seen = set()
    for query in queries:
        clean_query = str(query or "").strip()
        if clean_query and clean_query not in seen:
            seen.add(clean_query)
            normalized.append(clean_query)
    return (normalized or [optimized_query])[:max(1, Config.RAG_OPTIMIZE_QUERY_LIMIT)]


def build_comparison(original_context: Dict[str, Any], optimized_context: Dict[str, Any], latency_ms: float) -> Dict[str, Any]:
    """构建原始检索与优化检索对比指标。"""
    return {
        "original_count": len(original_context["results"]),
        "optimized_count": len(optimized_context["results"]),
        "latency_ms": round(latency_ms, 2),
    }


def build_retrieval_trace_items(
    original_context: Dict[str, Any],
    optimized_context: Dict[str, Any],
    comparison: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """构建 SEE 检索阶段追踪节点。"""
    return [
        {
            "stage": "original_retrieval",
            "summary": "使用原始查询执行混合检索",
            "metrics": {
                "result_count": comparison["original_count"],
                "profile": original_context["profile"],
            },
        },
        {
            "stage": "optimized_retrieval",
            "summary": "使用优化查询执行混合检索",
            "metrics": {
                "result_count": comparison["optimized_count"],
                "query_count": len(optimized_context["expanded_queries"]),
                "query_result_counts": optimized_context["query_result_counts"],
                "query_profiles": optimized_context["query_profiles"],
            },
        },
        {
            "stage": "comparison",
            "summary": "对比两次检索结果数量和耗时",
            "metrics": comparison,
        },
    ]


async def collect_retrieval_contexts(original_task, optimized_task):
    """并发等待原始检索和优化检索上下文。"""
    original_context, optimized_query_context = await asyncio.gather(
        original_task,
        optimized_task,
    )
    return original_context, optimized_query_context


async def export_sample(args) -> Dict[str, Any]:
    """导出 SEE 样例。"""
    context = load_last_eval_context(args.query)
    run_id = args.run_id or context["run_id"]
    search_type = args.eval_type or context["eval_type"]
    rebuild_graph_for_eval(run_id, search_type)

    started = time.perf_counter()
    original_task = asyncio.create_task(
        run_query_with_profile(args.user_id, args.query, search_type, args.top_k)
    )
    optimize_result = await get_query_optimize_service().optimize(args.query)
    optimized_query = optimize_result["optimized_query"]
    expanded_queries = normalize_queries(
        optimize_result.get("expanded_queries", []),
        optimized_query,
    )
    optimized_task = asyncio.create_task(
        run_optimized_queries(args.user_id, expanded_queries, search_type, args.top_k)
    )

    original_context, optimized_query_context = await collect_retrieval_contexts(
        original_task,
        optimized_task,
    )
    optimized_context = {
        "results": optimized_query_context["results"],
        "expanded_queries": expanded_queries,
        "query_result_counts": optimized_query_context["query_result_counts"],
        "query_profiles": optimized_query_context["query_profiles"],
    }
    comparison = build_comparison(
        original_context,
        optimized_context,
        latency_ms=(time.perf_counter() - started) * 1000,
    )
    see_trace = list(optimize_result.get("see_trace", []))
    see_trace.extend(build_retrieval_trace_items(original_context, optimized_context, comparison))

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "type": search_type,
        "query": args.query,
        "optimized_query": optimized_query,
        "intent": optimize_result.get("intent", ""),
        "cot_plan": optimize_result.get("cot_plan", []),
        "expanded_queries": expanded_queries,
        "fallback_used": optimize_result.get("fallback_used", False),
        "fallback_reason": optimize_result.get("fallback_reason", ""),
        "see_trace": see_trace,
        "original_results": original_context["results"],
        "optimized_results": optimized_context["results"],
        "comparison": comparison,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="导出一次真实 RAG 优化检索 SEE 样例")
    parser.add_argument("--query", default="社区要做人脸门禁、访客预约、电梯权限和车辆道闸联动，应该命中哪个文档？")
    parser.add_argument("--run-id", default="", help="复用已有行业评测 run_id")
    parser.add_argument("--eval-type", default="", help="复用已有行业评测 collection type")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--user-id", default="see_sample")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "data" / "rag_see_sample_last.json"))
    args = parser.parse_args()

    Config.DEBUG = False
    sample = await export_sample(args)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(sample, ensure_ascii=False, indent=2))
    print(f"report_path={output_path}")


if __name__ == "__main__":
    asyncio.run(main())
