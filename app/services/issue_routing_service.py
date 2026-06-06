"""
RAG 查询问题类型路由服务。

在检索前把 query 分诊为稳定的业务 issue_type，便于后续尽早裁剪候选池。

@author lvdaxianerplus
@date 2026-06-04
"""

from __future__ import annotations

import re
from typing import Any

from app.services.query_normalization import normalize_query_text

ISSUE_TYPES = {"fault", "consult", "ticket", "policy", "solution", "faq", "unknown"}


class IssueRoutingService:
    """
    规则优先的问题类型路由器。

    @author lvdaxianerplus
    @date 2026-06-04
    """

    ISSUE_RULES: dict[str, tuple[str, ...]] = {
        "fault": ("报错", "异常", "失败", "白屏", "不生效", "无法", "崩溃", "超时", "告警", "排查", "修复"),
        "ticket": ("工单", "单号", "派单", "处理状态", "客户反馈", "投诉", "跟进", "审批"),
        "consult": ("怎么用", "如何使用", "支持哪些", "支持什么", "能不能", "介绍", "区别", "是什么"),
        "policy": ("规范", "制度", "权限", "限制", "流程", "SOP", "口径", "要求"),
        "solution": ("方案", "架构", "集成", "设计", "最佳实践", "建设建议", "路线"),
        "faq": ("FAQ", "常见问题", "问答", "标准答复"),
    }

    def detect(self, query: str) -> dict[str, Any]:
        """
        根据确定性规则识别 query 的问题类型。

        @param query - 用户原始查询
        @returns 包含 issue_type、confidence、matched_terms、reason 的路由结果
        @author lvdaxianerplus
        @date 2026-06-04
        """
        compact_query = self._compact(query)
        for issue_type, terms in self.ISSUE_RULES.items():
            matched_terms = [term for term in terms if self._contains(compact_query, term)]
            if matched_terms:
                return self._known_result(issue_type, matched_terms)
            else:
                continue
        return self._unknown_result()

    def _contains(self, compact_query: str, term: str) -> bool:
        """
        判断归一化后的查询是否包含归一化关键词。

        @param compact_query - 已去除空白的归一化查询
        @param term - 待匹配关键词
        @returns 命中返回 True，否则返回 False
        @author lvdaxianerplus
        @date 2026-06-04
        """
        compact_term = self._compact(term)
        if compact_term:
            return compact_term in compact_query
        else:
            return False

    def _compact(self, text: str) -> str:
        """
        归一化文本并移除空白字符，提升中英文混排命中稳定性。

        @param text - 原始文本
        @returns 可用于包含匹配的紧凑文本
        @author lvdaxianerplus
        @date 2026-06-04
        """
        return re.sub(r"\s+", "", normalize_query_text(text or ""))

    def _known_result(self, issue_type: str, matched_terms: list[str]) -> dict[str, Any]:
        """
        构造已命中问题类型的结果。

        @param issue_type - 命中的问题类型
        @param matched_terms - 命中的关键词列表
        @returns 路由结果字典
        @author lvdaxianerplus
        @date 2026-06-04
        """
        confidence = "high" if len(matched_terms) >= 2 else "medium"
        return {
            "issue_type": issue_type,
            "confidence": confidence,
            "matched_terms": matched_terms,
            "reason": f"命中 {issue_type} 问题关键词",
        }

    def _unknown_result(self) -> dict[str, Any]:
        """
        构造未命中规则时的低置信兜底结果。

        @returns unknown 路由结果字典
        @author lvdaxianerplus
        @date 2026-06-04
        """
        return {
            "issue_type": "unknown",
            "confidence": "low",
            "matched_terms": [],
            "reason": "未命中问题类型规则",
        }
