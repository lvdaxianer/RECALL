from app.services.ragflow_hybrid_score import weighted_hybrid_fusion


def test_weighted_hybrid_fusion_combines_text_vector_graph_scores():
    vector = [{"id": "doc-1", "score": 0.9, "description": "A", "metadata": {"id": "doc-1"}}]
    text = [{"id": "doc-1", "score": 12.0, "description": "A", "metadata": {"id": "doc-1"}}]
    graph = [{"id": "doc-1", "score": 0.5, "description": "A", "metadata": {"id": "doc-1"}}]

    fused = weighted_hybrid_fusion(
        vector_results=vector,
        text_results=text,
        graph_results=graph,
        text_weight=0.35,
        vector_weight=0.55,
        graph_weight=0.10,
    )

    assert fused[0]["id"] == "doc-1"
    assert 0.0 <= fused[0]["score"] <= 1.0
    assert fused[0]["score_trace"]["text_score"] == 1.0
    assert fused[0]["score_trace"]["vector_score"] == 1.0
    assert fused[0]["score_trace"]["graph_score"] == 1.0
    assert fused[0]["score_trace"]["strategy"] == "ragflow_weighted"


def test_weighted_hybrid_fusion_keeps_docs_missing_one_channel():
    fused = weighted_hybrid_fusion(
        vector_results=[],
        text_results=[{"id": "doc-1", "score": 2.0, "description": "A", "metadata": {"id": "doc-1"}}],
        graph_results=[],
        text_weight=0.35,
        vector_weight=0.55,
        graph_weight=0.10,
    )

    assert fused[0]["id"] == "doc-1"
    assert fused[0]["score_trace"]["vector_score"] == 0.0
