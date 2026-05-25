"""
Faithfulness 检测模块

检测答案是否有上下文支撑，防止 LLM 幻觉

@author lvdaxianerplus
@date 2026-05-25
"""

import json
from typing import List, Dict, Any, Optional
from app.services.llm_service import get_llm_service
from app.utils.logger import get_logger

faithfulness_logger = get_logger("FaithfulnessChecker")

FAITHFULNESS_PROMPT = """你是一个严格的答案质量评估员。请评估以下答案是否完全基于给定的参考资料。

## 参考资料
{contexts}

## 待评估答案
{answer}

## 评估标准
- 1.0：答案中所有陈述都有参考资料支撑
- 0.7-0.9：大部分陈述有支撑，少量推断
- 0.4-0.6：部分陈述有支撑，存在明显推断
- 0.0-0.3：大量陈述无支撑，存在幻觉

必须严格返回以下 JSON 结构，不要包含任何其他内容：
{{"score": 0.85, "reason": "评估理由"}}"""


class FaithfulnessChecker:
    """
    Faithfulness 检测器

    使用 LLM 评估答案是否忠实于检索到的上下文
    """

    def __init__(self, llm_service=None):
        """
        初始化检测器

        @param llm_service - LLM 服务实例
        """
        self._llm = llm_service

    @property
    def llm(self):
        """懒加载 LLM 服务"""
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def check(
        self,
        answer: str,
        contexts: List[str]
    ) -> Dict[str, Any]:
        """
        检测答案的 Faithfulness 分数

        @param answer - 待检测的答案
        @param contexts - 参考上下文列表
        @returns 包含 score 和 reason 的字典
        @author lvdaxianerplus
        @date 2026-05-25
        """
        faithfulness_logger.info("[FaithfulnessChecker] 开始检测, answer_length={}", len(answer))

        if not answer or not contexts:
            return {"score": 0.0, "reason": "答案或上下文为空"}

        try:
            contexts_text = "\n\n".join(
                f"[{i+1}] {ctx[:500]}" for i, ctx in enumerate(contexts)
            )
            prompt = FAITHFULNESS_PROMPT.format(
                contexts=contexts_text,
                answer=answer[:1000]
            )
            response = await self.llm.chat_simple(
                prompt,
                system="你是一个严格的答案质量评估员，专注于检测答案是否有文献支撑。"
            )
            result = self._parse_response(response)
            faithfulness_logger.info(
                "[FaithfulnessChecker] 检测完成, score={}", result.get("score")
            )
            return result
        except Exception as e:
            faithfulness_logger.error("[FaithfulnessChecker] 检测失败, error={}", str(e))
            # 检测失败时返回中等分数，不阻断流程
            return {"score": 0.5, "reason": f"检测失败: {str(e)}"}

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        解析 LLM 返回的评估结果

        @param response - LLM 返回文本
        @returns 包含 score 和 reason 的字典
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
            score = float(data.get("score", 0.5))
            # 确保分数在 [0, 1] 范围内
            score = max(0.0, min(1.0, score))
            return {"score": score, "reason": data.get("reason", "")}
        except (json.JSONDecodeError, ValueError):
            faithfulness_logger.warning(
                "[FaithfulnessChecker] JSON 解析失败, response='{}'", response[:100]
            )
            return {"score": 0.5, "reason": "解析失败"}


# 全局单例
_checker: Optional[FaithfulnessChecker] = None


def get_faithfulness_checker() -> FaithfulnessChecker:
    """
    获取 Faithfulness 检测器单例

    @returns FaithfulnessChecker 实例
    @author lvdaxianerplus
    @date 2026-05-25
    """
    global _checker
    if _checker is None:
        _checker = FaithfulnessChecker()
    return _checker
