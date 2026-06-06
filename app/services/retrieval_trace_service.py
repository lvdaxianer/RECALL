"""
Retrieval trace shaping helpers.

This module centralizes SEE/SSE-friendly summaries for retrieval routing and
candidate scoring while avoiding leakage of private reasoning.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional


REDACTED_VALUE = "[REDACTED]"


def build_query_scope_trace(query_scope: str, route_plan: list[str]) -> Dict[str, Any]:
    """Build a SEE-safe trace entry for query scope detection."""
    summary_by_scope = {
        "global": "识别为全局问题，采用摘要优先的层级检索",
        "hybrid": "识别为混合问题，先摘要定位再检索证据 chunk",
        "local": "识别为局部问题，采用 chunk 检索与重排",
    }
    scope = query_scope or "local"
    return {
        "stage": "query_scope_detected",
        "summary": summary_by_scope.get(scope, summary_by_scope["local"]),
        "metrics": {
            "query_scope": scope,
            "route_plan": route_plan or _default_route_plan(scope),
        },
    }


def build_retrieval_strategy_trace(
    strategy: str,
    weights: Dict[str, float],
    candidate_count: int,
    rerank_cap: int,
) -> Dict[str, Any]:
    """Build a summary-only trace entry for retrieval strategy selection."""
    summary = "使用字段加权全文检索、向量检索和图检索进行混合召回"
    if strategy == "rrf":
        summary = "使用 RRF 融合全文、向量和图检索结果"
    return {
        "stage": "retrieval_strategy",
        "summary": summary,
        "metrics": {
            "strategy": strategy,
            "weights": weights,
            "candidate_count": candidate_count,
            "rerank_cap": rerank_cap,
        },
    }


def build_issue_type_trace(issue_route: dict[str, Any], issue_filters: dict[str, Any]) -> Dict[str, Any]:
    """Build a SEE-safe trace entry for issue type routing."""
    return {
        "stage": "issue_type_detected",
        "summary": issue_route.get("reason", "识别问题类型"),
        "metrics": _redact_sensitive_values({
            "issue_type": issue_route.get("issue_type", "unknown"),
            "confidence": issue_route.get("confidence", "low"),
            "matched_terms": issue_route.get("matched_terms", []),
            "issue_filters": issue_filters,
        }),
    }


def _default_route_plan(scope: str) -> list[str]:
    """Return a stable fallback route plan for SEE payloads."""
    if scope == "global":
        return ["summary_retrieval", "section_expansion", "evidence_chunk_retrieval", "map_reduce_synthesis"]
    if scope == "hybrid":
        return ["summary_retrieval", "section_expansion", "evidence_chunk_retrieval", "map_reduce_synthesis"]
    return ["chunk_retrieval", "rerank", "answer_context"]


def build_candidate_score_trace(
    candidate: Mapping[str, Any],
    score_trace: Optional[Mapping[str, Any]] = None,
    stage: str = "candidate_score",
) -> Dict[str, Any]:
    """Build a redacted candidate-level score trace for SEE/SSE payloads."""
    trace = _redact_sensitive_values(score_trace or {})
    candidate_copy = _redact_sensitive_values(dict(candidate))
    candidate_id = _candidate_id(candidate_copy)
    strategy = str(trace.get("strategy", ""))
    return {
        "stage": "candidate_score",
        "summary": "候选得分追踪",
        "metrics": {
            "source_stage": stage,
            "candidate_id": candidate_id,
            "strategy": strategy,
            "candidate": candidate_copy,
            "score_trace": trace,
        },
    }


def build_stage_summary(
    stage: str,
    summary: str,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a generic SEE stage summary."""
    return {
        "stage": stage,
        "summary": summary,
        "metrics": _redact_sensitive_values(metrics or {}),
    }


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    metadata = candidate.get("metadata") or {}
    return str(candidate.get("id") or metadata.get("id") or metadata.get("doc_id") or "")


def _redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_by_key(key, nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    return value


def _redact_by_key(key: str, value: Any) -> Any:
    normalized_key = key.lower()
    if normalized_key in {"api_key", "apikey", "authorization", "password", "secret", "token"}:
        return REDACTED_VALUE
    return _redact_sensitive_values(value)
