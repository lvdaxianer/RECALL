"""
查询改写模块

将用户原始问题改写为更适合文档检索的形式，并生成语义等价变体

@author lvdaxianerplus
@date 2026-05-25
"""

import json
from typing import Optional
from app.services.llm_service import get_llm_service
from app.utils.logger import get_logger

rewriter_logger = get_logger("QueryRewriter")

REWRITE_PROMPT = """将用户问题改写为更适合文档检索的形式：
1. 展开缩写和代词
2. 补充隐含的上下文
3. 生成 3 个语义等价的变体

原始问题：{query}

必须严格返回以下 JSON 结构，不要包含任何其他内容：
{{"rewritten": "改写后的问题", "variants": ["变体1", "变体2", "变体3"]}}"""


class QueryRewriter:
    """
    查询改写器

    使用 LLM 将原始查询改写为更适合检索的形式，并生成语义等价变体
    """

    def __init__(self, llm_service=None):
        """
        初始化查询改写器

        @param llm_service - LLM 服务实例，默认使用全局单例
        """
        self._llm = llm_service

    @property
    def llm(self):
        """懒加载 LLM 服务"""
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def rewrite(self, query: str) -> dict:
        """
        改写查询

        @param query - 原始查询文本
        @returns 包含 rewritten 和 variants 的字典
        @author lvdaxianerplus
        @date 2026-05-25
        """
        rewriter_logger.info("[QueryRewriter] 开始改写查询, query='{}'", query[:80])

        try:
            prompt = REWRITE_PROMPT.format(query=query)
            response = await self.llm.chat_simple(prompt, system="你是一个专业的信息检索查询优化助手。")
            result = self._parse_response(response)
            rewriter_logger.info("[QueryRewriter] 改写完成, rewritten='{}'", result.get("rewritten", "")[:80])
            return result
        except Exception as e:
            rewriter_logger.warning("[QueryRewriter] 改写失败，使用原始查询, error={}", str(e))
            return {"rewritten": query, "variants": []}

    def _parse_response(self, response: str) -> dict:
        """
        解析 LLM 返回的 JSON

        @param response - LLM 返回文本
        @returns 解析后的字典
        @author lvdaxianerplus
        @date 2026-05-25
        """
        # 尝试提取 JSON 块
        text = response.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

        try:
            data = json.loads(text)
            return {
                "rewritten": data.get("rewritten", ""),
                "variants": data.get("variants", [])
            }
        except json.JSONDecodeError:
            rewriter_logger.warning("[QueryRewriter] JSON 解析失败, response='{}'", response[:100])
            return {"rewritten": "", "variants": []}


# 全局单例
_rewriter: Optional[QueryRewriter] = None


def get_query_rewriter() -> QueryRewriter:
    """
    获取查询改写器单例

    @returns QueryRewriter 实例
    @author lvdaxianerplus
    @date 2026-05-25
    """
    global _rewriter
    if _rewriter is None:
        _rewriter = QueryRewriter()
    return _rewriter
