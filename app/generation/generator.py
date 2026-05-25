"""
答案生成模块

基于检索到的上下文，使用 LLM 生成带引用溯源的答案

@author lvdaxianerplus
@date 2026-05-25
"""

from typing import List, Dict, Any, Optional
from app.services.llm_service import get_llm_service
from app.generation.citation_builder import build_context_with_citations, build_citation_list
from app.utils.logger import get_logger

generator_logger = get_logger("Generator")

GENERATION_PROMPT = """你是一个严谨的知识问答助手。请严格基于以下参考资料回答问题。

## 参考资料
{context_with_citations}

## 问题
{query}

## 回答要求
1. 只使用参考资料中的信息，不要添加额外知识
2. 每个关键陈述必须标注来源，格式：[来源编号]，例如 [1] 或 [2]
3. 如果参考资料不足以回答问题，明确说明"根据现有资料无法确定"
4. 不要推测或猜测

## 回答
"""


class Generator:
    """
    答案生成器

    基于检索上下文生成带引用溯源的答案
    """

    def __init__(self, llm_service=None):
        """
        初始化生成器

        @param llm_service - LLM 服务实例
        """
        self._llm = llm_service

    @property
    def llm(self):
        """懒加载 LLM 服务"""
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def generate(
        self,
        query: str,
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        生成答案

        @param query - 用户问题
        @param chunks - 检索到的 chunk 列表
        @returns 包含 answer 和 citations 的字典
        @author lvdaxianerplus
        @date 2026-05-25
        """
        generator_logger.info("[Generator] 开始生成答案, query='{}', chunks={}", query[:80], len(chunks))

        # 构建带引用编号的上下文
        context_with_citations = build_context_with_citations(chunks)
        citations = build_citation_list(chunks)

        # 调用 LLM 生成答案
        try:
            prompt = GENERATION_PROMPT.format(
                context_with_citations=context_with_citations,
                query=query
            )
            answer = await self.llm.chat_simple(
                prompt,
                system="你是一个严谨的知识问答助手，只基于提供的参考资料回答问题。"
            )
            generator_logger.info("[Generator] 生成完成, answer_length={}", len(answer))
        except Exception as e:
            generator_logger.error("[Generator] 生成失败, error={}", str(e))
            answer = "生成答案时发生错误，请稍后重试。"

        return {
            "answer": answer.strip(),
            "citations": citations,
            "context_used": len(chunks)
        }


# 全局单例
_generator: Optional[Generator] = None


def get_generator() -> Generator:
    """
    获取生成器单例

    @returns Generator 实例
    @author lvdaxianerplus
    @date 2026-05-25
    """
    global _generator
    if _generator is None:
        _generator = Generator()
    return _generator
