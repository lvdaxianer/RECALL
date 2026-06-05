"""
特征提取服务模块

使用 LLM 从 description 中自动提取 category 和 tags

@author lvdaxianerplus
@date 2026-04-18
"""

import json
import asyncio
from typing import Dict, Any, Optional, List
from app.services.llm_service import LLMService, get_llm_service
from app.utils.logger import get_logger

# 日志器
feature_extract_logger = get_logger("FeatureExtract")

# 特征提取提示词
FEATURE_EXTRACT_PROMPT = """你是一个特征提取助手。请从给定的描述文本中提取特征信息。

## 输出格式
必须严格返回以下 JSON 结构，不要包含任何其他内容：
{{
  "category": "分类名称",
  "tags": ["标签1", "标签2", "标签3"]
}}

## category 分类规则
- 从以下常见分类中选择一个最合适的：模型、教程、工具、文档、素材、示例、配置、脚本、API、组件、插件、框架、库、数据集、报告、指南、参考
- 如果都不合适，选择描述内容所属的主要领域

## tags 提取规则
- 提取 3-10 个关键词
- 优先提取：技术栈、功能主题、文件格式、应用领域、难易程度
- 使用简洁的名词/动词，避免长句
- 用中文提取

## 示例

输入：这是一个React组件库，包含按钮、输入框、弹窗等常用UI组件，支持主题定制
输出：{{"category": "组件", "tags": ["React", "UI组件", "主题定制", "按钮", "输入框", "弹窗"]}}

输入：Python机器学习教程，讲解scikit-learn的基本用法，包括回归、分类、聚类算法
输出：{{"category": "教程", "tags": ["Python", "机器学习", "scikit-learn", "回归", "分类", "聚类"]}}

## 待提取描述
{description}

## 输出
"""


class FeatureExtractService:
    """
    特征提取服务类

    使用 LLM 从描述文本中提取 category 和 tags
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        """
        初始化特征提取服务

        @param llm_service - LLM 服务实例，默认使用全局单例
        """
        self._llm_service = llm_service

    @property
    def llm_service(self) -> LLMService:
        """获取 LLM 服务"""
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    async def extract_features(self, description: str) -> Dict[str, Any]:
        """
        从描述文本中提取特征

        @param description - 描述文本
        @returns 特征字典，包含 category 和 tags

        Author: lvdaxianerplus
        Date: 2026-04-18
        """
        # 参数校验
        if not description or not description.strip():
            feature_extract_logger.warning("[特征提取] 描述为空，返回默认特征")
            return self._get_default_features()

        try:
            # 构建提示词
            prompt = FEATURE_EXTRACT_PROMPT.format(description=description)

            # 调用 LLM
            feature_extract_logger.info("[特征提取] 开始提取, 描述长度={}", len(description))
            response = await self.llm_service.chat_simple(prompt)

            # 解析响应
            features = self._parse_llm_response(response)

            if features:
                feature_extract_logger.info(
                    "[特征提取] 提取成功, category={}, tags数量={}",
                    features.get("category"),
                    len(features.get("tags", []))
                )
            else:
                feature_extract_logger.warning("[特征提取] 解析失败，使用默认特征")
                features = self._get_default_features()

            return features

        except Exception as e:
            feature_extract_logger.error("[特征提取] 提取失败: {}", str(e))
            return self._get_default_features()

    async def extract_features_batch(self, descriptions: List[str], concurrency: int = 10) -> List[Dict[str, Any]]:
        """
        批量提取特征

        @param descriptions - 描述文本列表
        @param concurrency - 最大并发数
        @returns 特征列表，顺序与输入一致
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(description: str) -> Dict[str, Any]:
            """在并发窗口内提取单条特征"""
            async with semaphore:
                return await self.extract_features(description)

        return await asyncio.gather(*(run_one(description) for description in descriptions))

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        解析 LLM 响应

        @param response - LLM 原始响应
        @returns 特征字典，解析失败返回 None
        """
        try:
            # 尝试提取 JSON
            json_str = self._extract_json(response)
            if json_str:
                features = json.loads(json_str)
                # 验证格式
                if "category" in features and "tags" in features:
                    # 确保 tags 是列表
                    if isinstance(features["tags"], list):
                        # 限制 tags 数量最多 10 个
                        features["tags"] = features["tags"][:10]
                        return features
        except Exception as e:
            feature_extract_logger.error("[特征提取] JSON 解析失败: {}", str(e))

        return None

    def _extract_json(self, text: str) -> Optional[str]:
        """
        从文本中提取 JSON 字符串

        @param text - 原始文本
        @returns JSON 字符串
        """
        # 尝试直接解析
        try:
            json.loads(text)
            return text
        except Exception:
            pass

        # 尝试查找 JSON 块
        import re
        # 匹配 ```json ... ``` 或 ``` ... ```
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

    def _get_default_features(self) -> Dict[str, Any]:
        """
        获取默认特征

        @returns 默认特征字典
        """
        return {
            "category": "未分类",
            "tags": [],
            "entities": [],
            "relations": []
        }

    async def health_check(self) -> bool:
        """
        健康检查

        @returns LLM 服务是否可用
        """
        try:
            return await self.llm_service.health_check()
        except Exception as e:
            feature_extract_logger.error("[特征提取] 健康检查失败: {}", str(e))
            return False


# 全局单例
_feature_extract_service: Optional[FeatureExtractService] = None


def get_feature_extract_service() -> FeatureExtractService:
    """
    获取特征提取服务实例（单例）

    @returns FeatureExtractService 实例
    """
    global _feature_extract_service
    if _feature_extract_service is None:
        _feature_extract_service = FeatureExtractService()
    return _feature_extract_service
