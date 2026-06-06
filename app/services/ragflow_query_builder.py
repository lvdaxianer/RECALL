"""
RAGFlow-inspired Elasticsearch query builder.

Only builds query bodies; it does not call Elasticsearch.
"""

import re
from typing import Any, Dict, Optional

from app.config import Config


_PARSER_SENSITIVE_RE = re.compile(r"[ :|\r\n\t,，。？?/`!！&^%()\[\]{}<>*~'\"\\（）]+")

RAGFLOW_WEIGHTED_FIELDS = [
    "important_kwd^30",
    "important_tks^20",
    "question_tks^20",
    "title_tks^10",
    "title_sm_tks^5",
    "content_ltks^2",
    "content_sm_ltks",
    "description",
    "description_en",
]


def normalize_weighted_query(query: str) -> str:
    """Clean characters that query parsers can misread."""
    text = (query or "").lower()
    text = _PARSER_SENSITIVE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_metadata_filters(metadata_filter: Optional[Dict[str, Any]]) -> list[Dict[str, Any]]:
    if not metadata_filter:
        return []
    return [
        {"term": {metadata_filter_field(key, value): value}}
        for key, value in metadata_filter.items()
        if value is not None
    ]


def metadata_filter_field(key: str, value: Any) -> str:
    """Use keyword fields for strings and raw fields for typed metadata."""
    if isinstance(value, str):
        return f"metadata.{key}.keyword"
    return f"metadata.{key}"


def build_weighted_es_query(
    query: str,
    top_k: int,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_query = normalize_weighted_query(query)
    query_body = _build_query_body(normalized_query, metadata_filter)
    return {"query": query_body, "size": top_k}


def build_query_should_clauses(query: str) -> list[Dict[str, Any]]:
    """Build the weighted should clauses for a normalized query."""
    clauses: list[Dict[str, Any]] = [
        {
            "multi_match": {
                "query": query,
                "fields": RAGFLOW_WEIGHTED_FIELDS,
                "type": "best_fields",
                "minimum_should_match": Config.RAG_WEIGHTED_QUERY_MIN_SHOULD_MATCH,
            }
        }
    ]
    if len(query.split()) >= 2:
        clauses.append(
            {
                "match_phrase": {
                    "content_ltks": {
                        "query": query,
                        "slop": 2,
                        "boost": 1.5,
                    }
                }
            }
        )
    return clauses


def _build_query_body(
    normalized_query: str,
    metadata_filter: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the final ES query body from clauses and filters."""
    query_body: Dict[str, Any] = {
        "bool": {
            "should": build_query_should_clauses(normalized_query),
            "minimum_should_match": 1,
        }
    }
    filters = build_metadata_filters(metadata_filter)
    if filters:
        query_body["bool"]["filter"] = filters
    return query_body
