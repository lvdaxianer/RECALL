"""
幻觉过滤模块

对生成的答案进行 Faithfulness 检测，低分时触发重新生成

@author lvdaxianerplus
@date 2026-05-25
"""

from typing import List, Dict, Any, Optional, Callable, Awaitable
from app.validation.faithfulness_checker import get_faithfulness_checker
from app.utils.logger import get_logger

hallucination_logger = get_logger("HallucinationFilter")

# Faithfulness 阈值
FAITHFULNESS_THRESHOLD = 0.7
# 最大重试次数
MAX_RETRIES = 2

STRICT_SYSTEM_PROMPT = """你是一个极其严谨的知识问答助手。
你必须严格基于参考资料回答，每个陈述都必须有明确的来源支撑。
如果参考资料不足以回答，必须明确说明"根据现有资料无法确定"。
绝对不允许推测、猜测或添加参考资料之外的信息。"""


class HallucinationFilter:
    """
    幻觉过滤器

    检测答案 Faithfulness，低分时使用更严格的 Prompt 重新生成
    """

    def __init__(self, faithfulness_checker=None):
        """
        初始化幻觉过滤器

        @param faithfulness_checker - Faithfulness 检测器实例
        """
        self._checker = faithfulness_checker

    @property
    def checker(self):
        """懒加载 Faithfulness 检测器"""
        if self._checker is None:
            self._checker = get_faithfulness_checker()
        return self._checker

    async def filter(
        self,
        answer: str,
        contexts: List[str],
        regenerate_fn: Optional[Callable[[str], Awaitable[str]]] = None,
        strict_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        过滤幻觉答案

        @param answer - 原始生成的答案
        @param contexts - 参考上下文列表
        @param regenerate_fn - 重新生成函数，接收 system_prompt 返回新答案
        @param strict_prompt - 严格模式的 system prompt
        @returns 包含 answer、faithfulness_score、retries 的字典
        @author lvdaxianerplus
        @date 2026-05-25
        """
        current_answer = answer
        retries = 0

        # 首次检测
        result = await self.checker.check(current_answer, contexts)
        score = result.get("score", 0.5)

        hallucination_logger.info(
            "[HallucinationFilter] 初始 Faithfulness 分数={}", score
        )

        # 分数达标，直接返回
        if score >= FAITHFULNESS_THRESHOLD:
            return {
                "answer": current_answer,
                "faithfulness_score": score,
                "retries": 0,
                "passed": True
            }

        # 分数不达标，尝试重新生成
        if regenerate_fn is not None:
            system = strict_prompt or STRICT_SYSTEM_PROMPT
            while retries < MAX_RETRIES and score < FAITHFULNESS_THRESHOLD:
                retries += 1
                hallucination_logger.warning(
                    "[HallucinationFilter] 分数不达标({})，第{}次重新生成", score, retries
                )
                try:
                    current_answer = await regenerate_fn(system)
                    result = await self.checker.check(current_answer, contexts)
                    score = result.get("score", 0.5)
                    hallucination_logger.info(
                        "[HallucinationFilter] 第{}次重生成后分数={}", retries, score
                    )
                except Exception as e:
                    hallucination_logger.error(
                        "[HallucinationFilter] 重新生成失败, error={}", str(e)
                    )
                    break

        # 仍不达标，返回兜底答案
        if score < FAITHFULNESS_THRESHOLD:
            hallucination_logger.warning(
                "[HallucinationFilter] {}次重试后仍不达标(score={})，返回兜底答案", retries, score
            )
            return {
                "answer": "根据现有资料无法确定，请提供更多相关信息。",
                "faithfulness_score": score,
                "retries": retries,
                "passed": False
            }

        return {
            "answer": current_answer,
            "faithfulness_score": score,
            "retries": retries,
            "passed": True
        }


# 全局单例
_filter: Optional[HallucinationFilter] = None


def get_hallucination_filter() -> HallucinationFilter:
    """
    获取幻觉过滤器单例

    @returns HallucinationFilter 实例
    @author lvdaxianerplus
    @date 2026-05-25
    """
    global _filter
    if _filter is None:
        _filter = HallucinationFilter()
    return _filter
