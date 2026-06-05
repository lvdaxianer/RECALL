"""
问题类型路由服务测试。

@author lvdaxianerplus
@date 2026-06-04
"""

from app.services.issue_routing_service import IssueRoutingService


def test_detect_fault_issue_type():
    """故障现象查询应识别为 fault。"""
    result = IssueRoutingService().detect("小程序上线后白屏，本地正常，怎么排查")

    assert result["issue_type"] == "fault"
    assert result["confidence"] in {"high", "medium"}
    assert "白屏" in result["matched_terms"]


def test_detect_ticket_issue_type():
    """工单处理状态查询应识别为 ticket。"""
    result = IssueRoutingService().detect("客户反馈工单一直没有派单，帮我看处理状态")

    assert result["issue_type"] == "ticket"
    assert "工单" in result["matched_terms"]


def test_detect_consult_issue_type():
    """能力咨询查询应识别为 consult。"""
    result = IssueRoutingService().detect("这个系统支持哪些门禁能力")

    assert result["issue_type"] == "consult"


def test_unknown_when_no_rule_matches():
    """无规则命中时应低置信返回 unknown。"""
    result = IssueRoutingService().detect("随便聊一下")

    assert result["issue_type"] == "unknown"
    assert result["confidence"] == "low"
