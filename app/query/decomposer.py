"""
问题分解模块

将复杂问题分解为多个子问题，分别检索后合并结果

@author lvdaxianerplus
@date 2026-05-25
"""

import json
from typing import List, Optional
from app.services.llm_service import get_llm_service
from app.utils.logger import get_logger

decomposer_logger = get_logger("QueryDecomposer")

DECOMPOSE_PROMPT = """判断以下问题是否需要分解为多个子问题来检索。

如果问题包含多个独立的查询点（如比较多个对象、询问多个方面），请分解为子问题。
如果问题简单明确，直接返回原问题作为唯一子问题。

问题：{query}

必须严格返回以下 JSON 结构，不要包含任何其他内容：
{{"sub_questions": ["子问题1", "子问题2"]}}

最多分解为 4 个子问题。"""


class QueryDecomposer:
    """
    查询分解器

    将复杂的多跳问题分解为多个独立子问题，分别检索后合并
    """

    def __init__(self, llm_service=None):
        """
        初始化查询分解器

        @param llm_service - LLM 服务实例
        """
        self._llm = llm_service

    @property
    def llm(self):
        """懒加载 LLM 服务"""
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def decompose(self, query: str) -> List[str]:
        """
        分解查询为子问题列表

        @param query - 原始查询文本
        @returns 子问题列表（简单问题返回包含原问题的单元素列表）
        @author lvdaxianerplus
        @date 2026-05-25
        """
        decomposer_logger.info("[QueryDecomposer] 开始分解查询, query='{}'", query[:80])

        try:
            prompt = DECOMPOSE_PROMPT.format(query=query)
            response = await self.llm.chat_simple(
                prompt,
                system="你是一个专业的问题分析助手，擅长将复杂问题拆解为独立的检索子问题。"
            )
            sub_questions = self._parse_response(response, query)
            decomposer_logger.info("[QueryDecomposer] 分解完成, 子问题数量={}", len(sub_questions))
            return sub_questions
        except Exception as e:
            decomposer_logger.warning("[QueryDecomposer] 分解失败，使用原始查询, error={}", str(e))
            return [query]

    def _parse_response(self, response: str, original_query: str) -> List[str]:
        """
        解析 LLM 返回的子问题列表

        @param response - LLM 返回文本
        @param original_query - 原始查询（解析失败时的降级值）
        @returns 子问题列表
        @author lvdaxianerplus
        @date 2026-05-25
        """
        text = response.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

        try:
            data = json.loads(text)
            sub_questions = data.get("sub_questions", [])
            # 过滤空字符串，最多保留 4 个
            sub_questions = [q.strip() for q in sub_questions if q.strip()][:4]
            return sub_questions if sub_questions else [original_query]
        except json.JSONDecodeError:
            decomposer_logger.warning("[QueryDecomposer] JSON 解析失败, response='{}'", response[:100])
            return [original_query]


# 全局单例
_decomposer: Optional[QueryDecomposer] = None


def get_query_decomposer() -> QueryDecomposer:
    """
    获取查询分解器单例

    @returns QueryDecomposer 实例
    @author lvdaxianerplus
    @date 2026-05-25
    """
    global _decomposer
    if _decomposer is None:
        _decomposer = QueryDecomposer()
    return _decomposer
