"""
RAG 问题类型路由最小评测集。

@author lvdaxianerplus
@date 2026-06-04
"""

import json
from pathlib import Path

from app.services.issue_routing_service import IssueRoutingService


def test_issue_routing_fixture_cases():
    """最小金标集中的常见问题类型应稳定分类。"""
    cases = json.loads(Path("tests/fixtures/rag_issue_routing_cases.json").read_text(encoding="utf-8"))
    service = IssueRoutingService()
    mismatches = []

    for case in cases:
        result = service.detect(case["query"])
        if result["issue_type"] != case["issue_type"]:
            mismatches.append((case["query"], case["issue_type"], result["issue_type"]))
        else:
            continue

    assert mismatches == []
