from app.services.query_scope_service import QueryScopeService


def test_detects_local_query_scope_for_specific_troubleshooting():
    result = QueryScopeService().detect("小程序上线后白屏怎么排查接口域名配置")

    assert result["query_scope"] == "local"
    assert result["route_plan"]["strategy"] == "local_chunk"


def test_detects_global_query_scope_for_overview_question():
    result = QueryScopeService().detect("请总结这批文档的整体架构和能力缺口")

    assert result["query_scope"] == "global"
    assert result["route_plan"]["strategy"] == "summary_first"
    assert "document_summary" in result["route_plan"]["steps"]


def test_detects_hybrid_query_scope_for_overview_with_evidence():
    result = QueryScopeService().detect("Recall 当前 RAG 能力还缺什么，以及哪些文件能证明？")

    assert result["query_scope"] == "hybrid"
    assert result["route_plan"]["strategy"] == "summary_then_evidence"
    assert "evidence_chunks" in result["route_plan"]["steps"]
