"""
特征加权服务模块

提供特征过滤和加权功能，用于提升检索质量

@author lvdaxianerplus
@date 2026-04-18
"""

import json
import asyncio
from typing import List, Dict, Any, Optional
from app.services.feature_boost_parser import (
    extract_json,
    parse_batch_relevance_response,
    parse_relevance_response,
)
from app.services.feature_boost_prompts import (
    SEMANTIC_BOOST_BATCH_PROMPT,
    SEMANTIC_BOOST_PROMPT,
)
from app.services.llm_service import LLMService, get_llm_service
from app.utils.logger import get_logger

feature_boost_logger = get_logger("FeatureBoost")

FIXED_BOOST_WEIGHT = 0.05  # 每个命中的标签加 0.05 分

SEMANTIC_CONCURRENCY = 4    # 并发 LLM 调用数量
SEMANTIC_TIMEOUT = 8         # 单次 LLM 调用超时时间（秒）
SEMANTIC_MAX_RESULTS = 5     # 最多评估的结果数量（按固定加权排序取 top）

class FeatureBoostService:
    """特征加权服务类"""

    def __init__(self, llm_service: Optional[LLMService] = None):
        """
        初始化特征加权服务

        @param llm_service - LLM 服务实例，默认使用全局单例
        """
        self._llm_service = llm_service

    @property
    def llm_service(self) -> LLMService:
        """获取 LLM 服务"""
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    def filter_by_features(
        self,
        results: List[Dict[str, Any]],
        min_match_count: int = 1
    ) -> List[Dict[str, Any]]:
        """
        根据特征过滤结果

        @param results - 搜索结果列表
        @param min_match_count - 最少匹配标签数
        @returns 过滤后的结果

        Author: lvdaxianerplus
        Date: 2026-04-18
        """
        if not results:
            return []

        filtered = []
        for result in results:
            features = result.get("features", {})
            tags = features.get("tags", [])

            # 统计匹配的标签数
            match_count = len(tags)
            if match_count >= min_match_count:
                result["_feature_match_count"] = match_count
                filtered.append(result)

        feature_boost_logger.info(
            "[特征过滤] 过滤前={}, 过滤后={}, 最小匹配={}",
            len(results), len(filtered), min_match_count
        )

        return filtered

    def fixed_boost(
        self,
        results: List[Dict[str, Any]],
        weight: float = FIXED_BOOST_WEIGHT
    ) -> List[Dict[str, Any]]:
        """
        固定规则加权

        根据命中的标签数量加权

        @param results - 搜索结果列表
        @param weight - 每个标签的权重
        @returns 加权后的结果

        Author: lvdaxianerplus
        Date: 2026-04-18
        """
        for result in results:
            features = result.get("features", {})
            tags = features.get("tags", [])

            # 统计匹配的标签数
            match_count = len(tags)
            boost = match_count * weight

            # 记录加权分
            result["_fixed_boost"] = boost
            result["_feature_match_count"] = match_count

            # 更新总分
            original_score = result.get("score", 0)
            result["score"] = original_score + boost

        feature_boost_logger.info(
            "[固定加权] 加权结果数量={}, 每标签权重={}",
            len(results), weight
        )

        return results

    def apply_local_tag_rank_feature(
        self,
        query: str,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """基于查询与 tags 的本地 rank feature 做轻量加权。"""
        query_text = query or ""
        boosted = []
        for result in results:
            tags = (result.get("features") or {}).get("tags", []) or []
            matches = [tag for tag in tags if str(tag) and str(tag) in query_text]
            item = result.copy()
            if matches:
                boost = min(0.03 * len(matches), 0.15)
                item["score"] = float(item.get("score", 0.0) or 0.0) + boost
                trace = dict(item.get("score_trace") or {})
                trace["tag_rank_feature"] = round(boost, 6)
                trace["tag_matches"] = matches
                item["score_trace"] = trace
            boosted.append(item)
        return sorted(boosted, key=lambda item: item.get("score", 0.0), reverse=True)

    async def semantic_boost(
        self,
        query: str,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        LLM 语义加权（并发执行）

        使用 asyncio.gather 并发调用 LLM，每个结果独立评估

        @param query - 用户查询
        @param results - 搜索结果列表（已应用固定加权）
        @returns 加权后的结果

        Author: lvdaxianerplus
        Date: 2026-04-18
        """
        if not results or not query:
            return results

        results_with_features = []
        for i, result in enumerate(results):
            features = result.get("features", {})
            if features:
                results_with_features.append((i, result, features))

        if not results_with_features:
            return results

        results_with_features.sort(
            key=lambda x: x[1].get("_fixed_boost", 0),
            reverse=True
        )
        top_results = results_with_features[:SEMANTIC_MAX_RESULTS]

        semaphore = asyncio.Semaphore(SEMANTIC_CONCURRENCY)

        async def evaluate_with_semaphore(
            idx: int,
            result: Dict[str, Any],
            features: Dict[str, Any]
        ) -> tuple:
            """带信号量的评估"""
            async with semaphore:
                try:
                    score = await asyncio.wait_for(
                        self._evaluate_semantic_relevance(query, features),
                        timeout=SEMANTIC_TIMEOUT
                    )
                    return (idx, result, score)
                except asyncio.TimeoutError:
                    feature_boost_logger.warning(
                        "[语义加权] 单次评估超时, id={}",
                        result.get("id", "unknown")
                    )
                    return (idx, result, None)
                except Exception as e:
                    feature_boost_logger.warning(
                        "[语义加权] 单次评估失败, id={}: {}",
                        result.get("id", "unknown"), str(e)
                    )
                    return (idx, result, None)

        tasks = [
            evaluate_with_semaphore(idx, result, features)
            for idx, result, features in top_results
        ]
        eval_results = await asyncio.gather(*tasks)

        success_count = 0
        for idx, result, score in eval_results:
            if score is not None:
                result["_semantic_boost"] = score
                original_score = result.get("score", 0)
                result["score"] = original_score + score
                success_count += 1

        feature_boost_logger.info(
            "[语义加权] 并发评估完成, 成功={}, 评估数={}, 总特征数={}",
            success_count, len(top_results), len(results_with_features)
        )

        return results

    async def _evaluate_semantic_relevance(
        self,
        query: str,
        features: Dict[str, Any]
    ) -> Optional[float]:
        """
        评估查询与单个特征的语义相关性

        @param query - 用户查询
        @param features - 特征字典
        @returns 语义相关分数，失败返回 None
        """
        try:
            prompt = SEMANTIC_BOOST_PROMPT.format(
                query=query,
                features=json.dumps(features, ensure_ascii=False)
            )

            response = await self.llm_service.chat_simple(prompt)
            return parse_relevance_response(response)

        except Exception as e:
            feature_boost_logger.error("[语义评估] 评估失败: {}", str(e))
            return None

    async def _evaluate_semantic_relevance_batch(
        self,
        query: str,
        features_list: List[Dict[str, Any]]
    ) -> List[Optional[float]]:
        """
        批量评估查询与多个特征的语义相关性（一次 LLM 调用）

        @param query - 用户查询
        @param features_list - 特征字典列表
        @returns 语义相关分数列表，失败返回全 None
        """
        try:
            prompt = SEMANTIC_BOOST_BATCH_PROMPT.format(
                query=query,
                features_list=json.dumps(features_list, ensure_ascii=False)
            )

            response = await self.llm_service.chat_simple(prompt)
            return parse_batch_relevance_response(response, len(features_list))

        except Exception as e:
            feature_boost_logger.error("[批量语义评估] 批量评估失败: {}", str(e))
            return [None] * len(features_list)

    def _parse_relevance_response(self, response: str) -> Optional[float]:
        """解析 LLM 语义评估响应"""
        return parse_relevance_response(response)

    def _parse_batch_relevance_response(
        self,
        response: str,
        expected_count: int
    ) -> List[Optional[float]]:
        """解析 LLM 批量语义评估响应"""
        return parse_batch_relevance_response(response, expected_count)

    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 字符串"""
        return extract_json(text)

    async def boost(
        self,
        query: str,
        results: List[Dict[str, Any]],
        enable_fixed: bool = True,
        enable_semantic: bool = True
    ) -> List[Dict[str, Any]]:
        """
        综合加权

        先固定规则加权，再 LLM 语义加权

        @param query - 用户查询
        @param results - 搜索结果列表
        @param enable_fixed - 是否启用固定加权
        @param enable_semantic - 是否启用语义加权
        @returns 加权后的结果

        Author: lvdaxianerplus
        Date: 2026-04-18
        """
        if not results:
            return results

        # 固定规则加权
        if enable_fixed:
            self.fixed_boost(results)

        # LLM 语义加权
        if enable_semantic:
            await self.semantic_boost(query, results)

        # 按分数排序
        results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return results

    async def health_check(self) -> bool:
        """
        健康检查

        @returns LLM 服务是否可用
        """
        try:
            return await self.llm_service.health_check()
        except Exception as e:
            feature_boost_logger.error("[特征加权] 健康检查失败: {}", str(e))
            return False


_feature_boost_service: Optional[FeatureBoostService] = None


def get_feature_boost_service() -> FeatureBoostService:
    """
    获取特征加权服务实例（单例）

    @returns FeatureBoostService 实例
    """
    global _feature_boost_service
    if _feature_boost_service is None:
        _feature_boost_service = FeatureBoostService()
    return _feature_boost_service
