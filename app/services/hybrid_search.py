"""
RRF 混合搜索模块

提供 Reciprocal Rank Fusion 融合排序功能

@author lvdaxianerplus
@date 2026-04-16
"""

from typing import List, Dict, Any
from collections import defaultdict


def rrf_fusion(
    results_list: List[List[Dict[str, Any]]],
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    RRF (Reciprocal Rank Fusion) 融合多路召回结果

    核心公式：RRF_score(d) = Σ 1 / (k + rank_i(d))

    @param results_list - 多路召回结果列表，每一路结果是按排名排序的文档列表
    @param k - 融合常数，越大越平滑（默认60）
    @returns 融合后的结果列表（按 RRF 分数降序）
    """
    if not results_list:
        return []

    # 检查是否所有结果都为空
    all_empty = all(len(results) == 0 for results in results_list)
    if all_empty:
        return []

    scores = defaultdict(float)
    doc_map = {}

    # 遍历每一路召回结果
    for results in results_list:
        if not results:
            continue
        # 遍历该路召回的每个文档（按排名顺序）
        for rank, item in enumerate(results):
            doc_id = item.get("id") or item.get("doc_id")
            if doc_id is None:
                continue

            # RRF 公式：累加排名倒数
            scores[doc_id] += 1.0 / (k + rank + 1)

            # 保留文档信息
            if doc_id not in doc_map:
                doc_map[doc_id] = item

    # 按 RRF 分数降序排序
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # 构建结果列表，保留原始文档信息和 RRF 分数
    fused_results = []
    for doc_id, rrf_score in sorted_items:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = rrf_score
        fused_results.append(doc)

    return fused_results


def rrf_fusion_with_scores(
    results_list: List[List[Dict[str, Any]]],
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    RRF 融合（保留原始分数）

    与 rrf_fusion 相同，但保留原始分数用于调试

    @param results_list - 多路召回结果列表
    @param k - 融合常数
    @returns 融合后的结果列表
    """
    if not results_list:
        return []

    scores = defaultdict(float)
    doc_map = {}

    for results in results_list:
        if not results:
            continue
        for rank, item in enumerate(results):
            doc_id = item.get("id") or item.get("doc_id")
            if doc_id is None:
                continue

            scores[doc_id] += 1.0 / (k + rank + 1)

            if doc_id not in doc_map:
                doc_map[doc_id] = {
                    **item,
                    "source_scores": []
                }
            # 记录该文档在各路召回中的分数和排名
            doc_map[doc_id]["source_scores"].append({
                "rank": rank + 1,
                "score": item.get("score", 0)
            })

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    fused_results = []
    for doc_id, rrf_score in sorted_items:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = rrf_score
        fused_results.append(doc)

    return fused_results


def normalize_scores(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将结果中的原始分数归一化到 [0, 1] 范围

    @param results - 结果列表
    @returns 归一化后的结果
    """
    if not results:
        return results

    min_score = min(r.get("score", 0) for r in results)
    max_score = max(r.get("score", 0) for r in results)

    score_range = max_score - min_score
    if score_range == 0:
        # 所有分数相同，直接返回
        return results

    return [
        {**r, "normalized_score": (r.get("score", 0) - min_score) / score_range}
        for r in results
    ]


def normalize_final_scores(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将最终分数归一化到 [0, 1] 范围（替换 score 字段）

    用于搜索流程最后阶段的分数归一化，确保返回给用户的分数在 [0,1] 范围内

    @param results - 搜索结果列表
    @returns 归一化后的结果
    """
    if not results:
        return results

    scores = [r.get("score", 0) for r in results]
    min_score = min(scores)
    max_score = max(scores)

    score_range = max_score - min_score

    # DEBUG日志
    from app.utils.logger import rag_search_logger
    rag_search_logger.debug(
        "[归一化] 原始分数: min={}, max={}, range={}, 前3={}",
        min_score, max_score, score_range, scores[:3]
    )

    if score_range == 0:
        return [{**r, "score": 1.0} for r in results]

    return [
        {**r, "score": (r.get("score", 0) - min_score) / score_range}
        for r in results
    ]
