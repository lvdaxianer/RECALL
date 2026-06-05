"""
Weighted hybrid score fusion with per-channel score trace.
"""

from typing import Any, Dict, List


def _normalize_by_id(results: List[Dict[str, Any]]) -> Dict[str, float]:
    if not results:
        return {}
    scores = [float(item.get("score", 0.0) or 0.0) for item in results]
    min_score = min(scores)
    max_score = max(scores)
    spread = max_score - min_score
    normalized = {}
    for item in results:
        doc_id = item.get("id") or item.get("doc_id")
        if not doc_id:
            continue
        score = float(item.get("score", 0.0) or 0.0)
        normalized[doc_id] = 1.0 if spread == 0 else (score - min_score) / spread
    return normalized


def weighted_hybrid_fusion(
    vector_results: List[Dict[str, Any]],
    text_results: List[Dict[str, Any]],
    graph_results: List[Dict[str, Any]],
    text_weight: float,
    vector_weight: float,
    graph_weight: float,
) -> List[Dict[str, Any]]:
    doc_map: Dict[str, Dict[str, Any]] = {}
    for source in [text_results, vector_results, graph_results]:
        for item in source:
            doc_id = item.get("id") or item.get("doc_id")
            if doc_id and doc_id not in doc_map:
                doc_map[doc_id] = item.copy()

    text_scores = _normalize_by_id(text_results)
    vector_scores = _normalize_by_id(vector_results)
    graph_scores = _normalize_by_id(graph_results)
    fused = []
    for doc_id, item in doc_map.items():
        text_score = text_scores.get(doc_id, 0.0)
        vector_score = vector_scores.get(doc_id, 0.0)
        graph_score = graph_scores.get(doc_id, 0.0)
        final_score = (
            text_score * text_weight
            + vector_score * vector_weight
            + graph_score * graph_weight
        )
        enriched = item.copy()
        enriched["score"] = round(final_score, 6)
        enriched["score_trace"] = {
            "strategy": "ragflow_weighted",
            "text_score": round(text_score, 6),
            "vector_score": round(vector_score, 6),
            "graph_score": round(graph_score, 6),
            "text_weight": text_weight,
            "vector_weight": vector_weight,
            "graph_weight": graph_weight,
            "final_score": round(final_score, 6),
        }
        fused.append(enriched)
    return sorted(fused, key=lambda item: item.get("score", 0.0), reverse=True)
