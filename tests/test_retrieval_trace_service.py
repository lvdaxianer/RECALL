from app.services.retrieval_trace_service import (
    build_candidate_score_trace,
    build_issue_type_trace,
    build_query_scope_trace,
    build_retrieval_strategy_trace,
)


def test_build_query_scope_trace_for_global_query():
    trace = build_query_scope_trace(
        query_scope="global",
        route_plan=[
            "summary_retrieval",
            "section_expansion",
            "evidence_chunk_retrieval",
            "map_reduce_synthesis",
        ],
    )

    assert trace["stage"] == "query_scope_detected"
    assert trace["summary"] == "识别为全局问题，采用摘要优先的层级检索"
    assert trace["metrics"]["query_scope"] == "global"
    assert trace["metrics"]["route_plan"] == [
        "summary_retrieval",
        "section_expansion",
        "evidence_chunk_retrieval",
        "map_reduce_synthesis",
    ]
    assert "private_cot" not in trace


def test_build_retrieval_strategy_trace_exposes_summary_only():
    trace = build_retrieval_strategy_trace(
        strategy="ragflow_weighted",
        weights={"text": 0.35, "vector": 0.55, "graph": 0.10},
        candidate_count=32,
        rerank_cap=16,
    )

    assert trace["stage"] == "retrieval_strategy"
    assert trace["summary"] == "使用字段加权全文检索、向量检索和图检索进行混合召回"
    assert trace["metrics"]["strategy"] == "ragflow_weighted"
    assert trace["metrics"]["weights"] == {"text": 0.35, "vector": 0.55, "graph": 0.10}
    assert "private_cot" not in trace
    assert "chain_of_thought" not in trace


def test_build_issue_type_trace_exposes_filters():
    """问题类型 trace 应暴露 issue_type 和过滤条件。"""
    trace = build_issue_type_trace(
        issue_route={
            "issue_type": "fault",
            "confidence": "medium",
            "matched_terms": ["白屏"],
            "reason": "命中 fault 问题关键词",
        },
        issue_filters={"issue_type": ["fault"], "source_type": ["runbook"]},
    )

    assert trace["stage"] == "issue_type_detected"
    assert trace["metrics"]["issue_type"] == "fault"
    assert trace["metrics"]["confidence"] == "medium"
    assert trace["metrics"]["issue_filters"]["source_type"] == ["runbook"]


def test_build_candidate_score_trace_keeps_sensitive_content_out():
    trace = build_candidate_score_trace(
        candidate={
            "id": "doc-1",
            "description": "小程序白屏排查",
            "metadata": {"id": "doc-1", "token": "secret-token"},
        },
        score_trace={
            "strategy": "ragflow_weighted",
            "text_score": 1.0,
            "vector_score": 0.5,
            "graph_score": 0.0,
            "final_score": 0.78,
            "token": "secret-token",
        },
        stage="rerank",
    )

    assert trace["stage"] == "candidate_score"
    assert trace["summary"] == "候选得分追踪"
    assert trace["metrics"]["candidate_id"] == "doc-1"
    assert trace["metrics"]["strategy"] == "ragflow_weighted"
    assert trace["metrics"]["score_trace"]["token"] == "[REDACTED]"
    assert trace["metrics"]["candidate"]["metadata"]["token"] == "[REDACTED]"
