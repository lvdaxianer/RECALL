"""
Retrieval SDK 服务

以 SDK 门面统一知识库过滤、query scope、route plan、summary-first trace 和候选 score trace。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from __future__ import annotations

import re
import uuid
import asyncio
from typing import Any

from app.config import Config
from app.services.embedding_service import EmbeddingService
from app.services.es_service import get_es_service
from app.services.issue_filter_service import IssueFilterService
from app.services.issue_routing_service import IssueRoutingService
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.milvus_service import MilvusService
from app.services.query_scope_service import QueryScopeService
from app.services.rerank_service import RerankService
from app.services.retrieval_trace_service import build_stage_summary
from app.services.synonym_service import SynonymService


TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")
TOKEN_PART_PATTERN = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+")
ENGINE_CANDIDATE_MULTIPLIER = 8
RERANK_DOCUMENT_MAX_CHARS = 1800
CONFIDENT_LOCAL_MIN_SIGNAL = 3
CONFIDENT_LOCAL_MIN_GAP = 2.0
CONTEXT_QUERY_MAX_CHARS = 300
CONTEXT_HISTORY_LIMIT = 3


class RetrievalSDKService:
    """Retrieval SDK 门面服务。"""

    def __init__(
        self,
        repository: KnowledgeBaseRepository,
        scope_service: QueryScopeService | None = None,
        es_service: Any | None = None,
        milvus_service: Any | None = None,
        embedding_service: Any | None = None,
        rerank_service: Any | None = None,
    ):
        """初始化 Retrieval SDK 服务。"""
        self.repository = repository
        self.scope_service = scope_service or QueryScopeService()
        self.es_service = es_service
        self.milvus_service = milvus_service
        self.embedding_service = embedding_service
        self.rerank_service = rerank_service
        self.issue_routing_service = IssueRoutingService()
        self.issue_filter_service = IssueFilterService()

    def search(
        self,
        input: str,
        knowledge_base_ids: list[str],
        top_k: int = 10,
        issue_type: str | None = None,
    ) -> dict[str, Any]:
        """执行知识库过滤检索并返回 trace。"""
        scope_result = self.scope_service.detect(input)
        issue_route, issue_filters = self._build_issue_context(input, issue_type)
        normalized_query = self._normalize_retrieval_query(input, knowledge_base_ids)
        candidates = self._score_candidates(normalized_query, knowledge_base_ids)
        results = candidates[:top_k]
        request_id = f"req_{uuid.uuid4().hex}"
        return {
            "request_id": request_id,
            "query_scope": scope_result["query_scope"],
            "route_plan": scope_result["route_plan"],
            "issue_type": issue_route["issue_type"],
            "issue_route": issue_route,
            "issue_filters": issue_filters,
            "filters": _build_sdk_filters(knowledge_base_ids, issue_filters),
            "results": results,
            "trace": self._build_trace(scope_result, issue_route, issue_filters, results, knowledge_base_ids, normalized_query),
        }

    def resolve_top_k(self, top_k: int | None, knowledge_base_ids: list[str]) -> int:
        """解析请求 topK，缺省时读取首个知识库默认 topK。"""
        if top_k is not None:
            return top_k
        for knowledge_base_id in knowledge_base_ids:
            try:
                return int(self.repository.get_knowledge_base_settings(knowledge_base_id)["top_k_default"])
            except ValueError:
                continue
        return 5

    def build_retrieval_query(
        self,
        input_text: str,
        use_context: bool = False,
        history_questions: list[str] | None = None,
    ) -> str:
        """根据开关组合最近问题和当前问题。"""
        if not use_context:
            return input_text
        questions = []
        seen = set()
        for question in (history_questions or [])[-CONTEXT_HISTORY_LIMIT:]:
            normalized = question.strip()
            if normalized and normalized not in seen:
                questions.append(normalized)
                seen.add(normalized)
        current = input_text.strip()
        if current:
            questions.append(current)
        return "；".join(questions)[:CONTEXT_QUERY_MAX_CHARS]

    async def search_with_engines(
        self,
        input: str,
        knowledge_base_ids: list[str],
        top_k: int = 10,
        request_id: str | None = None,
        issue_type: str | None = None,
    ) -> dict[str, Any]:
        """使用 ES、Milvus 和 Rerank 执行知识库过滤检索。"""
        scope_result = self.scope_service.detect(input)
        issue_route, issue_filters = self._build_issue_context(input, issue_type)
        normalized_query = self._normalize_retrieval_query(input, knowledge_base_ids)
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        try:
            query_terms = _tokenize(normalized_query)
            title_candidates = self._score_title_candidates(query_terms, knowledge_base_ids)
            confident_results = _confident_local_results(title_candidates, top_k)
            if confident_results is not None:
                return {
                    "request_id": request_id,
                    "query_scope": scope_result["query_scope"],
                    "route_plan": scope_result["route_plan"],
                    "issue_type": issue_route["issue_type"],
                    "issue_route": issue_route,
                    "issue_filters": issue_filters,
                    "filters": _build_sdk_filters(knowledge_base_ids, issue_filters),
                    "results": confident_results,
                    "trace": self._build_confident_local_trace(
                        scope_result,
                        issue_route,
                        issue_filters,
                        confident_results,
                        knowledge_base_ids,
                        normalized_query,
                    ),
                }
            local_candidates = self._score_candidates(normalized_query, knowledge_base_ids, query_terms=query_terms)
            candidates = await self._retrieve_engine_candidates(normalized_query, knowledge_base_ids, top_k, issue_filters)
            candidates = _filter_candidates_by_knowledge_base(candidates, knowledge_base_ids)
            candidates = _merge_sdk_candidates(candidates, local_candidates)
            if not candidates:
                fallback = self.search(
                    input=input,
                    knowledge_base_ids=knowledge_base_ids,
                    top_k=top_k,
                    issue_type=issue_route["issue_type"],
                )
                fallback["request_id"] = request_id
                fallback["trace"][1]["metrics"]["engine"] = "sqlite_keyword"
                fallback["trace"][1]["summary"] = "ES/Milvus 未召回当前知识库，已降级到本地 chunk 检索"
                return fallback
            results = await self._rerank_candidates(normalized_query, candidates, top_k, request_id)
            return {
                "request_id": request_id,
                "query_scope": scope_result["query_scope"],
                "route_plan": scope_result["route_plan"],
                "issue_type": issue_route["issue_type"],
                "issue_route": issue_route,
                "issue_filters": issue_filters,
                "filters": _build_sdk_filters(knowledge_base_ids, issue_filters),
                "results": results,
                "trace": self._build_engine_trace(scope_result, issue_route, issue_filters, results, knowledge_base_ids, normalized_query),
            }
        except Exception:
            fallback = self.search(
                input=input,
                knowledge_base_ids=knowledge_base_ids,
                top_k=top_k,
                issue_type=issue_route["issue_type"],
            )
            fallback["request_id"] = request_id
            fallback["trace"].append(build_stage_summary(
                stage="engine_fallback",
                summary="ES/Milvus/Rerank 检索失败，已降级到本地 chunk 检索",
                metrics={"engine": "sqlite_keyword"},
            ))
            return fallback

    async def _retrieve_engine_candidates(
        self,
        query: str,
        knowledge_base_ids: list[str],
        top_k: int,
        issue_filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """并行执行 ES 和 Milvus 知识库过滤检索。"""
        query_vector = await self._get_embedding_service().encode(query)
        es_filter = _merge_filter_dicts(_single_or_terms_filter("knowledge_base_id", knowledge_base_ids), issue_filters)
        milvus_filter = _merge_filter_dicts({"knowledge_base_ids": knowledge_base_ids}, issue_filters)
        candidate_limit = max(top_k, top_k * ENGINE_CANDIDATE_MULTIPLIER)
        es_service = self._get_es_service()
        milvus_service = self._get_milvus_service()
        es_task = es_service.search(
            Config.ES_ASSET_INDEX,
            query,
            candidate_limit,
            metadata_filter=es_filter,
        )
        vector_task = milvus_service.search(
            "knowledge_chunk",
            query_vector,
            candidate_limit,
            metadata_filter=milvus_filter,
        )
        es_results, vector_results = await asyncio.gather(es_task, vector_task)
        return _merge_engine_results(es_results, vector_results)

    async def _rerank_candidates(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
        request_id: str,
    ) -> list[dict[str, Any]]:
        """对候选执行 Rerank 并保留 score trace。"""
        if not candidates:
            return []
        candidates = [_prepare_rerank_candidate(candidate) for candidate in candidates]
        try:
            rerank_results = await self._get_rerank_service().rerank(query, candidates, request_id=request_id)
        except Exception:
            return [_mark_rerank_failed(candidate) for candidate in candidates[:top_k]]
        reranked = []
        for rank_result in rerank_results:
            index = rank_result.get("index", 0)
            if index >= len(candidates):
                continue
            item = candidates[index].copy()
            trace = dict(item.get("score_trace") or {})
            trace["rerank_score"] = rank_result.get("score", rank_result.get("relevance_score", 0))
            item["score_trace"] = trace
            item["score"] = trace["rerank_score"]
            reranked.append(item)
        return reranked[:top_k]

    def _build_engine_trace(
        self,
        scope_result: dict[str, Any],
        issue_route: dict[str, Any],
        issue_filters: dict[str, Any],
        results: list[dict[str, Any]],
        knowledge_base_ids: list[str],
        normalized_query: str,
    ) -> list[dict[str, Any]]:
        """构建引擎路径 trace。"""
        trace = self._build_trace(scope_result, issue_route, issue_filters, results, knowledge_base_ids, normalized_query)
        trace[1]["metrics"]["local_candidates_enabled"] = True
        rerank_failed = any((result.get("score_trace") or {}).get("rerank_failed") for result in results)
        if rerank_failed:
            trace[1]["metrics"]["engine"] = "es_milvus_fused_rerank_failed"
            trace[1]["metrics"]["rerank_failed"] = True
            trace[1]["summary"] = "Rerank 失败，已保留 ES/Milvus 与本地精确候选融合排序"
        else:
            trace[1]["metrics"]["engine"] = "es_milvus_rerank"
            trace[1]["summary"] = "按知识库过滤 ES/Milvus 候选并执行 Rerank"
        return trace

    def _build_confident_local_trace(
        self,
        scope_result: dict[str, Any],
        issue_route: dict[str, Any],
        issue_filters: dict[str, Any],
        results: list[dict[str, Any]],
        knowledge_base_ids: list[str],
        normalized_query: str,
    ) -> list[dict[str, Any]]:
        """构建本地高置信命中 trace。"""
        trace = self._build_trace(scope_result, issue_route, issue_filters, results, knowledge_base_ids, normalized_query)
        trace[1]["metrics"]["engine"] = "sqlite_confident_title"
        trace[1]["metrics"]["rerank_skipped"] = True
        trace[1]["metrics"]["local_candidates_enabled"] = True
        trace[1]["summary"] = "本地标题/文档名高置信命中，已跳过外部 Rerank"
        return trace

    def _get_es_service(self):
        """获取 ES 服务。"""
        if self.es_service is None:
            self.es_service = get_es_service()
        return self.es_service

    def _get_milvus_service(self):
        """获取 Milvus 服务。"""
        if self.milvus_service is None:
            self.milvus_service = MilvusService()
        return self.milvus_service

    def _get_embedding_service(self):
        """获取 Embedding 服务。"""
        if self.embedding_service is None:
            self.embedding_service = EmbeddingService()
        return self.embedding_service

    def _get_rerank_service(self):
        """获取 Rerank 服务。"""
        if self.rerank_service is None:
            self.rerank_service = RerankService()
        return self.rerank_service

    def _score_candidates(
        self,
        query: str,
        knowledge_base_ids: list[str],
        query_terms: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """按关键词重叠为本地 chunk 生成可解释分数。"""
        query_terms = query_terms or _tokenize(query)
        chunks = self.repository.search_chunks(knowledge_base_ids)
        scored = [self._score_chunk(chunk, query_terms) for chunk in chunks]
        filtered = [
            item
            for item in scored
            if (
                item["score_trace"]["term_overlap"] > 0
                or item["score_trace"]["title_overlap"] > 0
                or item["score_trace"]["document_name_overlap"] > 0
            )
        ]
        return sorted(filtered, key=lambda item: item["score"], reverse=True)

    def _score_title_candidates(self, query_terms: set[str], knowledge_base_ids: list[str]) -> list[dict[str, Any]]:
        """仅按标题和文档名生成轻量候选，用于高置信快速路径。"""
        chunks = self.repository.search_chunks(knowledge_base_ids)
        scored = [self._score_chunk_title(chunk, query_terms) for chunk in chunks]
        filtered = [
            item
            for item in scored
            if item["score_trace"]["title_overlap"] > 0 or item["score_trace"]["document_name_overlap"] > 0
        ]
        return sorted(filtered, key=lambda item: item["score"], reverse=True)

    def _score_chunk(self, chunk: dict[str, Any], query_terms: set[str]) -> dict[str, Any]:
        """计算单个 chunk 的检索分数。"""
        content_terms = _tokenize(chunk["content"])
        title_terms = _tokenize(chunk.get("title", ""))
        document_name_terms = _tokenize(chunk.get("document_name", ""))
        term_overlap = len(query_terms & content_terms)
        title_overlap = len(query_terms & title_terms)
        document_name_overlap = len(query_terms & document_name_terms)
        score = term_overlap + title_overlap * 1.5 + document_name_overlap * 2.0
        return {
            "chunk_id": chunk["id"],
            "knowledge_base_id": chunk["knowledge_base_id"],
            "document_id": chunk["document_id"],
            "document_name": chunk.get("document_name", ""),
            "chunk_index": chunk["chunk_index"],
            "title": chunk.get("title", ""),
            "content": chunk["content"],
            "description": _candidate_text(chunk.get("title", ""), chunk["content"]),
            "score": round(float(score), 4),
            "score_trace": {
                "strategy": "local_keyword_overlap",
                "term_overlap": term_overlap,
                "title_overlap": title_overlap,
                "document_name_overlap": document_name_overlap,
                "content_length": len(chunk["content"]),
            },
        }

    def _score_chunk_title(self, chunk: dict[str, Any], query_terms: set[str]) -> dict[str, Any]:
        """计算标题/文档名轻量分数，不解析正文。"""
        title_terms = _tokenize(chunk.get("title", ""))
        document_name_terms = _tokenize(chunk.get("document_name", ""))
        title_overlap = len(query_terms & title_terms)
        document_name_overlap = len(query_terms & document_name_terms)
        score = title_overlap * 1.5 + document_name_overlap * 2.0
        return {
            "chunk_id": chunk["id"],
            "knowledge_base_id": chunk["knowledge_base_id"],
            "document_id": chunk["document_id"],
            "document_name": chunk.get("document_name", ""),
            "chunk_index": chunk["chunk_index"],
            "title": chunk.get("title", ""),
            "content": chunk["content"],
            "description": _candidate_text(chunk.get("title", ""), chunk["content"]),
            "score": round(float(score), 4),
            "score_trace": {
                "strategy": "local_title_document_name",
                "term_overlap": 0,
                "title_overlap": title_overlap,
                "document_name_overlap": document_name_overlap,
                "content_length": len(chunk["content"]),
            },
        }

    def _build_trace(
        self,
        scope_result: dict[str, Any],
        issue_route: dict[str, Any],
        issue_filters: dict[str, Any],
        results: list[dict[str, Any]],
        knowledge_base_ids: list[str],
        normalized_query: str | None = None,
    ) -> list[dict[str, Any]]:
        """构建 SEE/SSE 安全 trace。"""
        return [
            build_stage_summary(
                stage="query_scope",
                summary=scope_result["reason"],
                metrics={
                    "query_scope": scope_result["query_scope"],
                    "route_plan": scope_result["route_plan"],
                    "knowledge_base_ids": knowledge_base_ids,
                },
            ),
            build_stage_summary(
                stage="candidate_scoring",
                summary="按知识库过滤 chunk 并生成候选级 score trace",
                metrics={
                    "candidate_count": len(results),
                    "issue_type": issue_route["issue_type"],
                    "issue_filters": issue_filters,
                    "normalized_query": normalized_query,
                },
            ),
        ]

    def _build_issue_context(self, query: str, issue_type: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """构建 issue route 和 issue filters。"""
        if issue_type:
            issue_route = {
                "issue_type": issue_type,
                "confidence": "high",
                "matched_terms": [],
                "reason": "请求显式指定问题类型",
            }
        else:
            issue_route = self.issue_routing_service.detect(query)
        issue_filters = self.issue_filter_service.build(issue_route["issue_type"])
        return issue_route, issue_filters

    def _normalize_retrieval_query(self, query: str, knowledge_base_ids: list[str]) -> str:
        """按同义词设置归一化检索召回 query。"""
        return SynonymService(self.repository).normalize_query(query, knowledge_base_ids)


def _tokenize(text: str) -> set[str]:
    """将中英文文本切为粗粒度词集合。"""
    normalized = text.lower()
    tokens: set[str] = set()
    for match in TOKEN_PATTERN.finditer(normalized):
        token = match.group(0)
        tokens.add(token)
        parts = {part.group(0) for part in TOKEN_PART_PATTERN.finditer(token)}
        tokens.update(parts)
        if _contains_cjk(token):
            tokens.update(_char_ngrams(token, 2))
            tokens.update(_char_ngrams(token, 3))
        for part in parts:
            if _contains_cjk(part):
                tokens.update(_char_ngrams(part, 2))
                tokens.update(_char_ngrams(part, 3))
    return tokens


def _contains_cjk(text: str) -> bool:
    """判断文本是否包含中文字符。"""
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _char_ngrams(text: str, size: int) -> set[str]:
    """生成中文字符 ngram，提高标题型短查询召回。"""
    if len(text) < size:
        return set()
    return {text[index:index + size] for index in range(0, len(text) - size + 1)}


def _single_or_terms_filter(key: str, values: list[str]) -> dict[str, Any]:
    """把知识库列表转换为 ES metadata filter。"""
    if len(values) == 1:
        return {key: values[0]}
    return {f"{key}s": values}


def _build_sdk_filters(knowledge_base_ids: list[str], issue_filters: dict[str, Any]) -> dict[str, Any]:
    """构建 SDK 响应中的统一过滤条件。"""
    return _merge_filter_dicts({"knowledge_base_ids": knowledge_base_ids}, issue_filters)


def _merge_filter_dicts(base_filter: dict[str, Any], extra_filter: dict[str, Any] | None) -> dict[str, Any]:
    """合并过滤条件，保留显式空字典语义。"""
    merged = dict(base_filter)
    if extra_filter:
        merged.update(extra_filter)
    else:
        pass
    return merged


def _merge_engine_results(es_results: list[dict[str, Any]], vector_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并 ES/Milvus 候选并生成统一结果结构。"""
    merged: dict[str, dict[str, Any]] = {}
    for result in es_results:
        item = _to_sdk_candidate(result, "es")
        merged[item["chunk_id"]] = item
    for result in vector_results:
        item = _to_sdk_candidate(result, "milvus")
        if item["chunk_id"] in merged:
            merged[item["chunk_id"]]["score_trace"]["vector_score"] = result.get("score", 0)
        else:
            merged[item["chunk_id"]] = item
    return sorted(merged.values(), key=lambda item: item["score"], reverse=True)


def _merge_sdk_candidates(
    engine_candidates: list[dict[str, Any]],
    local_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """合并引擎候选与本地精确候选，优先保留更高分候选。"""
    merged = {candidate["chunk_id"]: candidate for candidate in engine_candidates}
    for candidate in local_candidates:
        current = merged.get(candidate["chunk_id"])
        if current is None or candidate["score"] > current["score"]:
            merged[candidate["chunk_id"]] = candidate
    return sorted(merged.values(), key=lambda item: item["score"], reverse=True)


def _filter_candidates_by_knowledge_base(
    candidates: list[dict[str, Any]],
    knowledge_base_ids: list[str],
) -> list[dict[str, Any]]:
    """对引擎候选做知识库二次过滤，避免外部引擎过滤失效污染结果。"""
    allowed = set(knowledge_base_ids)
    return [candidate for candidate in candidates if candidate.get("knowledge_base_id") in allowed]


def _prepare_rerank_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """补齐并截断 Rerank 输入文本，避免本地候选以空文档进入 provider。"""
    prepared = candidate.copy()
    description = prepared.get("description") or _candidate_text(
        str(prepared.get("title", "")),
        str(prepared.get("content", "")),
    )
    prepared["description"] = description[:RERANK_DOCUMENT_MAX_CHARS]
    return prepared


def _candidate_text(title: str, content: str) -> str:
    """组合标题与正文，作为检索和 Rerank 统一候选文本。"""
    parts = [part.strip() for part in [title, content] if part and part.strip()]
    return "\n".join(parts)


def _mark_rerank_failed(candidate: dict[str, Any]) -> dict[str, Any]:
    """标记 Rerank 失败但保留候选原始融合分数。"""
    marked = candidate.copy()
    trace = dict(marked.get("score_trace") or {})
    trace["rerank_failed"] = True
    marked["score_trace"] = trace
    return marked


def _confident_local_results(
    candidates: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]] | None:
    """识别本地标题/文档名高置信候选。"""
    if not candidates:
        return None
    best = candidates[0]
    best_trace = best.get("score_trace") or {}
    best_signal = best_trace.get("title_overlap", 0) + best_trace.get("document_name_overlap", 0)
    second_score = _highest_other_document_score(candidates, best.get("document_id", ""))
    score_gap = best["score"] - second_score
    if best_signal >= CONFIDENT_LOCAL_MIN_SIGNAL and score_gap >= CONFIDENT_LOCAL_MIN_GAP:
        return candidates[:top_k]
    return None


def _highest_other_document_score(candidates: list[dict[str, Any]], document_id: str) -> float:
    """返回其它文档最高分，避免同文档多 chunk 稀释高置信判断。"""
    for candidate in candidates:
        if candidate.get("document_id") != document_id:
            return float(candidate.get("score", 0))
    return 0.0


def _to_sdk_candidate(result: dict[str, Any], source: str) -> dict[str, Any]:
    """把检索引擎结果转换为 SDK 候选结构。"""
    metadata = result.get("metadata") or {}
    score = float(result.get("score", 0))
    trace_key = "text_score" if source == "es" else "vector_score"
    return {
        "id": result.get("id", ""),
        "chunk_id": result.get("id", ""),
        "knowledge_base_id": metadata.get("knowledge_base_id", ""),
        "document_id": metadata.get("document_id", ""),
        "document_name": metadata.get("document_name", metadata.get("title", "")),
        "chunk_index": metadata.get("chunk_index", 0),
        "title": metadata.get("section_title", metadata.get("title", "")),
        "content": result.get("description", ""),
        "description": result.get("description", ""),
        "score": score,
        "score_trace": {
            "strategy": "es_milvus_rerank",
            "source": source,
            trace_key: score,
        },
    }
