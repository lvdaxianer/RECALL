"""
问题类型过滤服务测试。

@author lvdaxianerplus
@date 2026-06-04
"""

from app.services.issue_filter_service import IssueFilterService


def test_fault_filters():
    """fault 问题应生成故障知识源过滤条件。"""
    filters = IssueFilterService().build("fault")

    assert filters["issue_type"] == ["fault"]
    assert "runbook" in filters["source_type"]
    assert "incident_postmortem" in filters["source_type"]


def test_unknown_filters_are_empty():
    """unknown 问题不应强行裁剪候选池。"""
    filters = IssueFilterService().build("unknown")

    assert filters == {}
