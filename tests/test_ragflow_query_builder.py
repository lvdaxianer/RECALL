from app.services.ragflow_query_builder import build_query_should_clauses
from app.services.ragflow_query_builder import build_weighted_es_query
from app.services.ragflow_query_builder import normalize_weighted_query


def test_normalize_weighted_query_cleans_parser_sensitive_chars():
    assert normalize_weighted_query("小程序（上线后）白屏？？") == "小程序 上线后 白屏"


def test_normalize_weighted_query_lowercases_and_compacts_spaces():
    assert normalize_weighted_query("  MiniProgram   WHITE  Screen  ") == "miniprogram white screen"


def test_build_weighted_es_query_uses_ragflow_field_boosts():
    body = build_weighted_es_query("小程序上线后白屏", top_k=20)
    should = body["query"]["bool"]["should"]
    multi_match = should[0]["multi_match"]

    assert body["size"] == 20
    assert "important_kwd^30" in multi_match["fields"]
    assert "important_tks^20" in multi_match["fields"]
    assert "question_tks^20" in multi_match["fields"]
    assert "title_tks^10" in multi_match["fields"]
    assert "content_ltks^2" in multi_match["fields"]
    assert multi_match["minimum_should_match"] == "60%"


def test_build_weighted_es_query_preserves_metadata_filter():
    body = build_weighted_es_query(
        "小程序白屏",
        top_k=5,
        metadata_filter={"type": "skill"},
    )

    filters = body["query"]["bool"]["filter"]
    assert {"term": {"metadata.type.keyword": "skill"}} in filters


def test_build_weighted_es_query_uses_raw_metadata_field_for_boolean_filters():
    """布尔 metadata 过滤不应走 .keyword，否则真实 ES summary filter 无法命中"""
    body = build_weighted_es_query(
        "项目整体架构",
        top_k=5,
        metadata_filter={"is_summary": True, "summary_type": "document"},
    )

    filters = body["query"]["bool"]["filter"]
    assert {"term": {"metadata.is_summary": True}} in filters
    assert {"term": {"metadata.summary_type.keyword": "document"}} in filters


def test_build_weighted_es_query_adds_phrase_proximity_boost():
    body = build_weighted_es_query("小程序 上线后 白屏", top_k=10)
    should = body["query"]["bool"]["should"]

    assert any("match_phrase" in clause for clause in should)
    phrase_clause = next(clause["match_phrase"] for clause in should if "match_phrase" in clause)
    assert phrase_clause["content_ltks"]["query"] == "小程序 上线后 白屏"
    assert phrase_clause["content_ltks"]["slop"] == 2
    assert phrase_clause["content_ltks"]["boost"] == 1.5


def test_build_query_should_clauses_adds_phrase_clause_for_multiword_query():
    clauses = build_query_should_clauses("小程序 上线后 白屏")

    assert len(clauses) == 2
    assert "multi_match" in clauses[0]
    assert "match_phrase" in clauses[1]
