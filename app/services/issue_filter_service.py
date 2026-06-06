"""
问题类型过滤条件构造服务。

把 issue_type 转成 ES/Milvus/Graph 可消费的 metadata 过滤策略。

@author lvdaxianerplus
@date 2026-06-04
"""

from __future__ import annotations

from typing import Any


class IssueFilterService:
    """
    根据问题类型构造候选池裁剪过滤条件。

    @author lvdaxianerplus
    @date 2026-06-04
    """

    SOURCE_TYPES: dict[str, list[str]] = {
        "fault": ["fault_case", "runbook", "incident_postmortem", "known_issue"],
        "consult": ["faq", "manual", "product_intro", "best_practice"],
        "ticket": ["ticket", "ticket_summary", "customer_case"],
        "policy": ["policy", "process", "permission_doc"],
        "solution": ["solution", "architecture", "integration_doc"],
        "faq": ["faq", "qa_pair"],
    }

    def build(self, issue_type: str | None) -> dict[str, Any]:
        """
        构造已知 issue_type 的 metadata 过滤条件。

        @param issue_type - 问题类型
        @returns 可合并进检索链路的过滤条件
        @author lvdaxianerplus
        @date 2026-06-04
        """
        if not issue_type or issue_type == "unknown":
            return {}
        else:
            source_types = self.SOURCE_TYPES.get(issue_type)
        if not source_types:
            return {}
        else:
            return {
                "issue_type": [issue_type],
                "source_type": source_types,
            }
