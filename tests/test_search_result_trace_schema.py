from app.models.schemas import SearchResult


def test_search_result_accepts_optional_score_trace():
    result = SearchResult(
        metadata={"id": "doc-1", "type": "skill", "description": "小程序白屏排查"},
        description="小程序上线后白屏排查",
        score=0.91,
        score_trace={
            "strategy": "ragflow_weighted",
            "text_score": 0.8,
            "vector_score": 0.9,
            "graph_score": 0.2,
            "final_score": 0.91,
        },
    )

    assert result.score_trace["strategy"] == "ragflow_weighted"


def test_search_result_legacy_payload_still_valid():
    result = SearchResult(
        metadata={"id": "doc-1", "type": "skill", "description": "小程序白屏排查"},
        description="小程序上线后白屏排查",
        score=0.91,
    )

    assert result.score_trace is None
