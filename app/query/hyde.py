"""
HyDE（假设文档嵌入）模块

生成假设答案并用其向量代替原始查询向量，提升语义漂移场景下的召回率

@author lvdaxianerplus
@date 2026-05-25
"""

from typing import List, Optional
from app.services.llm_service import get_llm_service
from app.services.embedding_service import EmbeddingService
from app.utils.logger import get_logger

hyde_logger = get_logger("HyDE")

HYDE_PROMPT = """请根据以下问题，生成一段假设性的答案文档。
这段文档应该像是从知识库中检索到的真实文档片段，包含可能回答该问题的关键信息。
不需要完全准确，重点是覆盖相关的术语和概念。

问题：{query}

请直接输出假设文档内容，不要包含任何前缀或解释："""


class HyDE:
    """
    假设文档嵌入（Hypothetical Document Embeddings）

    原始 Query → LLM 生成假设答案 → 对假设答案做 Embedding → 用该向量检索
    适用于问题与文档表述差异大的场景
    """

    def __init__(self, llm_service=None, embedding_service: Optional[EmbeddingService] = None):
        """
        初始化 HyDE

        @param llm_service - LLM 服务实例
        @param embedding_service - Embedding 服务实例
        """
        self._llm = llm_service
        self._embedding = embedding_service

    @property
    def llm(self):
        """懒加载 LLM 服务"""
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    @property
    def embedding(self):
        """懒加载 Embedding 服务"""
        if self._embedding is None:
            self._embedding = EmbeddingService()
        return self._embedding

    async def generate_vector(self, query: str) -> List[float]:
        """
        生成 HyDE 向量

        先用 LLM 生成假设答案，再对假设答案做 Embedding

        @param query - 原始查询文本
        @returns 假设文档的向量
        @author lvdaxianerplus
        @date 2026-05-25
        """
        hyde_logger.info("[HyDE] 开始生成假设文档, query='{}'", query[:80])

        try:
            # 生成假设答案
            hypothetical_doc = await self._generate_hypothetical_doc(query)
            hyde_logger.info("[HyDE] 假设文档生成完成, length={}", len(hypothetical_doc))

            # 对假设答案做 Embedding
            vector = await self.embedding.encode(hypothetical_doc)
            hyde_logger.info("[HyDE] 向量化完成, dim={}", len(vector))
            return vector

        except Exception as e:
            hyde_logger.warning("[HyDE] 生成失败，降级使用原始查询向量, error={}", str(e))
            # 降级：直接对原始查询做 Embedding
            return await self.embedding.encode(query)

    async def _generate_hypothetical_doc(self, query: str) -> str:
        """
        使用 LLM 生成假设文档

        @param query - 原始查询
        @returns 假设文档文本
        @author lvdaxianerplus
        @date 2026-05-25
        """
        prompt = HYDE_PROMPT.format(query=query)
        response = await self.llm.chat_simple(
            prompt,
            system="你是一个知识库文档生成助手，擅长生成与问题相关的文档片段。"
        )
        return response.strip()


# 全局单例
_hyde: Optional[HyDE] = None


def get_hyde() -> HyDE:
    """
    获取 HyDE 单例

    @returns HyDE 实例
    @author lvdaxianerplus
    @date 2026-05-25
    """
    global _hyde
    if _hyde is None:
        _hyde = HyDE()
    return _hyde
