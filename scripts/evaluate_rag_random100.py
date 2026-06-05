#!/usr/bin/env python
"""
100 条随机模拟数据 RAG 冷启动评测脚本。

目标：
- 插入 100 条随机但可复现的业务数据
- 使用不重复随机查询测试真实 RAG 链路
- 禁用 Embedding/Rerank 缓存，观察不走缓存时的查询速度
"""

import argparse
import asyncio
import json
import random
import sys
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Config
from app.models.schemas import SearchRequest
from app.services.embedding_service import EmbeddingService
from app.services.es_service import get_es_service
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.milvus_service import MilvusService
from app.services.rerank_service import RerankService
from app.services.rag_evaluation_service import get_rag_evaluation_service
from app.services import rag_search_pipeline_service
from app.services.rag_search_pipeline_service import run_search_pipeline_with_profile
from scripts.evaluate_rag_industry50 import _encode_in_batches
from scripts.evaluate_rag_industry50 import _latency_summary
from scripts.evaluate_rag_industry50 import _metric_summary
from scripts.evaluate_rag_industry50 import _prewarm_external_clients
from scripts.evaluate_rag_industry50 import _rerank_decision_summary

REPORT_KIND_RANDOM100 = "random100"
REPORTS_DIR = PROJECT_ROOT / "reports" / "rag_eval"
LAST_REPORT_PATH = PROJECT_ROOT / "data" / "rag_eval_random100_last.json"

INDUSTRIES = ["金融", "医疗", "制造", "零售", "物流", "教育", "能源", "政务", "房地产", "农业"]
SCENARIOS = ["风控", "监测", "调度", "质检", "推荐", "预警", "审核", "排产", "溯源", "对账"]
SIGNALS = ["发票", "温度", "库存", "订单", "轨迹", "告警", "工单", "图像", "合同", "传感器"]
OBJECTS = ["客户", "设备", "车辆", "门店", "病历", "课程", "电表", "项目", "地块", "供应商"]
OUTPUTS = ["评分", "报告", "策略", "清单", "任务", "建议", "看板", "预测", "分级", "工单"]


def build_random_docs(seed: int, count: int) -> List[Dict[str, Any]]:
    """生成随机但可复现的评测文档。"""
    rng = random.Random(seed)
    docs = []
    for index in range(count):
        industry = rng.choice(INDUSTRIES)
        scenario = rng.choice(SCENARIOS)
        signal = rng.choice(SIGNALS)
        obj = rng.choice(OBJECTS)
        output = rng.choice(OUTPUTS)
        nonce = f"R{seed % 1000:03d}{index:03d}"
        title = f"{industry}{scenario}{obj}{nonce}"
        description = (
            f"{title}能力，融合{signal}、{obj}状态、历史{scenario}记录和实时告警，"
            f"输出{output}并支持负责人闭环跟踪。唯一识别码 {nonce}。"
        )
        query = f"需要根据{signal}和{obj}状态做{scenario}并输出{output}，唯一识别码是{nonce}，应该命中哪个能力？"
        docs.append({
            "industry": industry,
            "slug": f"random_{index:03d}",
            "title": title,
            "description": description,
            "query": query,
            "keywords": [industry, scenario, signal, obj, output, nonce],
            "nonce": nonce,
        })
    return docs


def build_features(doc: Dict[str, Any]) -> Dict[str, Any]:
    """构造轻量 features，避免评测依赖额外 LLM 抽取。"""
    return {
        "category": doc["industry"],
        "tags": doc["keywords"],
        "entities": [
            {"name": doc["industry"], "type": "行业"},
            {"name": doc["nonce"], "type": "随机识别码"},
            {"name": doc["title"], "type": "能力"},
        ],
        "relations": [
            {"source": doc["industry"], "relation": "包含能力", "target": doc["title"]},
            {"source": doc["title"], "relation": "识别码", "target": doc["nonce"]},
        ],
    }


async def insert_dataset(run_id: str, eval_type: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """向 Milvus、ES 和图索引写入随机数据。"""
    embedding_service = EmbeddingService(use_cache=False)
    milvus_service = MilvusService()
    es_service = get_es_service()

    await es_service.create_index_if_not_exists(Config.ES_SKILL_INDEX)

    started = time.perf_counter()
    vectors = await _encode_in_batches(embedding_service, [doc["description"] for doc in docs], batch_size=10)
    milvus_documents = []
    es_documents = []

    for index, doc in enumerate(docs):
        doc_id = f"{run_id}_{doc['slug']}"
        features = build_features(doc)
        metadata = {
            "type": eval_type,
            "id": doc_id,
            "description": doc["description"],
            "industry": doc["industry"],
            "title": doc["title"],
            "run_id": run_id,
            "expected_slug": doc["slug"],
        }
        milvus_documents.append({
            "id": doc_id,
            "description": doc["description"],
            "vector": vectors[index],
            "metadata": metadata,
            "features": features,
        })
        es_documents.append({
            "doc_id": doc_id,
            "description": doc["description"],
            "metadata": metadata,
            "features": features,
        })

    milvus_result = await milvus_service.batch_insert(eval_type, milvus_documents)
    get_graph_retrieval_service().index_documents(milvus_documents)
    es_count = await es_service.index_documents(Config.ES_SKILL_INDEX, es_documents)
    if getattr(es_service.client, "indices", None) is not None:
        with suppress(Exception):
            es_service.client.indices.refresh(index=Config.ES_SKILL_INDEX)

    return {
        "milvus_inserted": milvus_result.get("inserted_count", 0),
        "es_indexed": es_count,
        "ingest_ms": round((time.perf_counter() - started) * 1000, 2),
    }


async def evaluate_queries(
    run_id: str,
    eval_type: str,
    docs: List[Dict[str, Any]],
    query_count: int,
    seed: int,
    disable_cache: bool = False,
) -> Dict[str, Any]:
    """执行不走缓存的随机查询评测。"""
    if disable_cache:
        configure_no_cache_pipeline()
    else:
        configure_cache_pipeline()
    rng = random.Random(seed + 99)
    sampled_docs = rng.sample(docs, min(query_count, len(docs)))
    get_graph_retrieval_service().rebuild([
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
            "features": build_features(doc),
        }
        for doc in docs
    ])

    latencies = []
    ranks = []
    misses = []
    stage_timings: Dict[str, List[float]] = {}
    query_profiles = []

    for doc in sampled_docs:
        expected_id = f"{run_id}_{doc['slug']}"
        started = time.perf_counter()
        pipeline_result = await run_search_pipeline_with_profile(
            "random100_eval",
            SearchRequest(
                input=doc["query"],
                type=eval_type,
                topK=10,
                threshold=0,
                enableFeatureBoost=False,
            ),
        )
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        for stage, stage_ms in pipeline_result.profile.get("timings_ms", {}).items():
            stage_timings.setdefault(stage, []).append(stage_ms)

        result_ids = [item.metadata.get("id") for item in pipeline_result.results]
        rank = result_ids.index(expected_id) + 1 if expected_id in result_ids else 0
        ranks.append(rank)
        if rank == 0:
            misses.append({
                "expected_id": expected_id,
                "query": doc["query"],
                "top_ids": result_ids[:10],
            })
        get_rag_evaluation_service().record_case(
            query=doc["query"],
            optimized_query=doc["query"],
            retrieved_ids=result_ids[:10],
            miss_reason="unknown" if rank else "recall_miss",
            human_label="hit" if rank else "miss",
            user_id="random100_eval",
            request_id=expected_id,
            retrieval_strategy=Config.RAG_RETRIEVAL_STRATEGY,
            latency_ms=round(latency_ms, 2),
        )
        query_profiles.append({
            "slug": doc["slug"],
            "query": doc["query"],
            "expected_id": expected_id,
            "latency_ms": round(latency_ms, 2),
            "rank": rank,
            "profile": pipeline_result.profile,
        })

    total = len(ranks)
    return {
        "query_count": total,
        "top1_accuracy": round(sum(1 for rank in ranks if rank == 1) / total, 4),
        "top3_recall": round(sum(1 for rank in ranks if 1 <= rank <= 3) / total, 4),
        "top5_recall": round(sum(1 for rank in ranks if 1 <= rank <= 5) / total, 4),
        "top10_recall": round(sum(1 for rank in ranks if 1 <= rank <= 10) / total, 4),
        "mrr": round(sum((1 / rank) if rank else 0 for rank in ranks) / total, 4),
        "latency_ms": _latency_summary(latencies),
        "stage_latency_ms": {
            stage: _latency_summary(values)
            for stage, values in sorted(stage_timings.items())
            if values
        },
        "rerank_decision_summary": _rerank_decision_summary(query_profiles),
        "cache_stats": rag_search_pipeline_service.get_embedding_service().cache.get_stats(),
        "rank_distribution": {
            str(rank): sum(1 for item in ranks if item == rank)
            for rank in sorted(set(ranks))
        },
        "misses": misses,
        "query_profiles": query_profiles,
    }


def configure_no_cache_pipeline() -> None:
    """强制检索管线使用不带缓存的模型客户端。"""
    Config.RERANK_CACHE_ENABLED = False
    rag_search_pipeline_service._embedding_service = EmbeddingService(use_cache=False)
    rag_search_pipeline_service._rerank_service = RerankService(use_cache=False)


def configure_cache_pipeline() -> None:
    """使用默认缓存策略重建检索管线模型客户端。"""
    Config.RERANK_CACHE_ENABLED = True
    rag_search_pipeline_service._embedding_service = EmbeddingService(use_cache=True)
    rag_search_pipeline_service._rerank_service = RerankService(use_cache=Config.RERANK_CACHE_ENABLED)


def _build_cache_settings(disable_cache: bool) -> Dict[str, bool]:
    """构造 random100 缓存设置。"""
    cache_enabled = not disable_cache
    return {
        "embedding_cache_enabled": cache_enabled,
        "rerank_cache_enabled": cache_enabled,
    }


def _build_random100_report_path(timestamp: str) -> Path:
    """构造 random100 Phase E 报告路径。"""
    return REPORTS_DIR / f"{timestamp}-{REPORT_KIND_RANDOM100}.json"


def build_parser() -> argparse.ArgumentParser:
    """构造 random100 评测命令行参数。"""
    parser = argparse.ArgumentParser(description="100 条随机模拟数据 RAG 冷启动评测")
    parser.add_argument("--doc-count", type=int, default=100, help="插入文档数量")
    parser.add_argument("--query-count", type=int, default=100, help="随机查询数量")
    parser.add_argument("--seed", type=int, default=20260602, help="随机种子")
    parser.add_argument("--skip-ingest", action="store_true", help="跳过写入，复用 run-id/eval-type")
    parser.add_argument("--run-id", default="", help="复用已有 run_id")
    parser.add_argument("--eval-type", default="", help="复用已有 eval_type")
    parser.add_argument("--disable-cache", action="store_true", help="禁用 Embedding/Rerank 缓存做冷启动评测")
    parser.add_argument("--strategy", choices=["rrf", "ragflow_weighted"], default=Config.RAG_RETRIEVAL_STRATEGY)
    parser.add_argument("--limit", type=int, default=0, help="同时限制随机文档和查询数量")
    return parser


async def main() -> None:
    args = build_parser().parse_args()

    Config.DEBUG = False
    Config.RAG_RETRIEVAL_STRATEGY = args.strategy
    cache_settings = _build_cache_settings(args.disable_cache)
    if args.disable_cache:
        configure_no_cache_pipeline()
    else:
        configure_cache_pipeline()

    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = args.run_id or f"recall_eval_random100_{run_timestamp}"
    eval_type = args.eval_type or f"eval_random100_{run_timestamp}"
    doc_count = max(1, args.limit) if args.limit else args.doc_count
    query_count = min(args.limit, doc_count) if args.limit else args.query_count
    docs = build_random_docs(args.seed, doc_count)

    print("RAG 100 条随机数据冷启动评测开始")
    print(f"run_id={run_id}")
    print(f"eval_type={eval_type}")
    print(f"doc_count={len(docs)}")
    print(f"query_count={min(query_count, len(docs))}")
    print(f"cache_enabled={str(not args.disable_cache).lower()}")
    print(f"retrieval_strategy={args.strategy}")

    ingest = {"skipped": True} if args.skip_ingest else await insert_dataset(run_id, eval_type, docs)
    prewarm = _prewarm_external_clients()
    evaluation = await evaluate_queries(
        run_id,
        eval_type,
        docs,
        query_count,
        args.seed,
        disable_cache=args.disable_cache,
    )
    report = {
        "run_id": run_id,
        "eval_type": eval_type,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "settings": {
            "limit": args.limit,
            "doc_count": len(docs),
            "query_count": min(query_count, len(docs)),
            "seed": args.seed,
            "retrieval_strategy": args.strategy,
            **cache_settings,
            "rerank_candidate_limit": Config.RAG_RERANK_CANDIDATE_LIMIT,
        },
        "metrics": _metric_summary(evaluation),
        "ingest": ingest,
        "prewarm": prewarm,
        "evaluation": evaluation,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _build_random100_report_path(report_timestamp)
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    output_path.write_text(report_json, encoding="utf-8")
    LAST_REPORT_PATH.parent.mkdir(exist_ok=True)
    LAST_REPORT_PATH.write_text(report_json, encoding="utf-8")
    print(report_json)
    print(f"report_path={output_path}")


if __name__ == "__main__":
    asyncio.run(main())
