"""
特征语义加权响应解析工具
"""

import json
import re
from typing import List, Optional

from app.utils.logger import get_logger


feature_boost_parser_logger = get_logger("FeatureBoostParser")


def parse_relevance_response(response: str) -> Optional[float]:
    """解析单条语义评估响应"""
    try:
        json_str = extract_json(response)
        if json_str:
            data = json.loads(json_str)
            score = data.get("relevanceScore")
            if score is not None:
                return _clamp_score(score)
    except Exception as e:
        feature_boost_parser_logger.error("[语义评估] JSON 解析失败: {}", str(e))

    return None


def parse_batch_relevance_response(response: str, expected_count: int) -> List[Optional[float]]:
    """解析批量语义评估响应"""
    try:
        json_str = extract_json(response)
        if json_str:
            data = json.loads(json_str)
            if isinstance(data, list):
                return _build_batch_scores(data, expected_count)
    except Exception as e:
        feature_boost_parser_logger.error("[批量语义评估] JSON 解析失败: {}", str(e))

    return [None] * expected_count


def extract_json(text: str) -> Optional[str]:
    """从文本中提取 JSON 字符串"""
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'(\{.*\})'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            potential_json = match.group(1)
            try:
                json.loads(potential_json)
                return potential_json
            except Exception:
                continue

    return None


def _build_batch_scores(data: list, expected_count: int) -> List[Optional[float]]:
    """按 index 整理批量响应分数"""
    sorted_data = sorted(data, key=lambda x: x.get("index", 0))
    scores = []
    for item in sorted_data:
        score = item.get("relevanceScore")
        scores.append(_clamp_score(score) if score is not None else None)
    if len(scores) >= expected_count:
        return scores[:expected_count]
    return scores + [None] * (expected_count - len(scores))


def _clamp_score(score) -> float:
    """将分数限制在 0-1 范围内"""
    return max(0.0, min(1.0, float(score)))
