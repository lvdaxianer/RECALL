"""
Agent 工具注册表

把 RAG 能力暴露给 Agent Runtime 调用。

@author lvdaxianerplus
@date 2026-06-02
"""

import uuid
from inspect import isawaitable
from typing import Any, Optional

from app.models.schemas import EvaluationRecordRequest, SearchRequest
from app.services.agent_tool_hooks import get_agent_tool_hook_service
from app.services.cache_service import get_cache_service
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.query_optimize_service import get_query_optimize_service
from app.services.rag_evaluation_service import RagEvaluationRecordInput
from app.services.rag_evaluation_service import get_rag_evaluation_service
from app.services.rag_search_pipeline_service import run_search_pipeline_with_profile

TOOL_OPTIMIZE_QUERY = "optimize_query"
TOOL_SEARCH_RAG = "search_rag"
TOOL_EXPLAIN_GRAPH = "explain_graph"
TOOL_INVALIDATE_RERANK_CACHE = "invalidate_rerank_cache"
TOOL_RECORD_BAD_CASE = "record_bad_case"
TOOL_GET_CACHE_STATS = "get_cache_stats"
TOOL_GET_EVALUATION_SUMMARY = "get_evaluation_summary"
SYNC_TOOL_NAMES = {
    TOOL_INVALIDATE_RERANK_CACHE,
    TOOL_RECORD_BAD_CASE,
    TOOL_EXPLAIN_GRAPH,
    TOOL_GET_CACHE_STATS,
    TOOL_GET_EVALUATION_SUMMARY,
}


class UnknownAgentToolError(ValueError):
    """未知 Agent 工具。"""


class AgentToolRegistry:
    """RAG Agent 工具注册表。"""

    def __init__(
        self,
        query_optimize_service=None,
        cache_service=None,
        evaluation_service=None,
        graph_service=None,
        hook_service=None,
    ):
        self.query_optimize_service = query_optimize_service or get_query_optimize_service()
        self.cache_service = cache_service or get_cache_service()
        self.evaluation_service = evaluation_service or get_rag_evaluation_service()
        self.graph_service = graph_service or get_graph_retrieval_service()
        self.hook_service = hook_service or get_agent_tool_hook_service()

    async def call(self, tool_name: str, arguments: dict[str, Any], user_id: str) -> dict[str, Any]:
        """异步调用 Agent 工具。"""
        hook_context = self.hook_service.before_tool_call(tool_name, arguments)
        if tool_name == TOOL_OPTIMIZE_QUERY:
            result = await self._optimize_query(arguments)
        elif tool_name == TOOL_SEARCH_RAG:
            result = await self._search_rag(arguments, user_id)
        elif tool_name in SYNC_TOOL_NAMES:
            result = self.call_sync(tool_name, arguments, user_id)
            if isawaitable(result):
                result = await result
            else:
                pass
        else:
            raise UnknownAgentToolError(f"unknown tool: {tool_name}")
        self.hook_service.after_tool_call(
            tool_name,
            result,
            started_at=hook_context["started_at"],
            started_perf=hook_context.get("started_perf"),
        )
        return result

    def call_sync(self, tool_name: str, arguments: dict[str, Any], user_id: str) -> dict[str, Any]:
        """同步调用无需 await 的 Agent 工具。"""
        if tool_name == TOOL_INVALIDATE_RERANK_CACHE:
            return self._invalidate_rerank_cache(arguments)
        elif tool_name == TOOL_RECORD_BAD_CASE:
            return self._record_bad_case(arguments, user_id)
        elif tool_name == TOOL_EXPLAIN_GRAPH:
            return self._explain_graph(arguments)
        elif tool_name == TOOL_GET_CACHE_STATS:
            return self._get_cache_stats()
        elif tool_name == TOOL_GET_EVALUATION_SUMMARY:
            return self._get_evaluation_summary(user_id)
        else:
            raise UnknownAgentToolError(f"unknown sync tool: {tool_name}")

    async def _optimize_query(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行查询优化工具。"""
        return await self.query_optimize_service.optimize(arguments["input"])

    async def _search_rag(self, arguments: dict[str, Any], user_id: str) -> dict[str, Any]:
        """执行 RAG 检索工具。"""
        request_id = arguments.get("request_id") or f"req_{uuid.uuid4().hex}"
        result = await run_search_pipeline_with_profile(
            user_id,
            _build_search_request(arguments),
            request_id=request_id,
        )
        return {
            "request_id": request_id,
            "result_count": len(result.results),
            "recommendation_count": 0,
            "results": [item.model_dump() for item in result.results],
            "profile": result.profile,
        }

    def _invalidate_rerank_cache(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """按 request_id 撤销 Rerank 缓存。"""
        return self.cache_service.invalidate_rerank_by_request_id(arguments["request_id"])

    def _record_bad_case(self, arguments: dict[str, Any], user_id: str) -> dict[str, Any]:
        """记录 bad case 评测反馈。"""
        request = EvaluationRecordRequest(**arguments)
        record = self.evaluation_service.add_record(
            RagEvaluationRecordInput(
                user_id=user_id,
                query=request.query,
                optimized_query=request.optimized_query,
                retrieved_ids=request.retrieved_ids,
                miss_reason=request.miss_reason,
                human_label=request.human_label,
            )
        )
        request_id = arguments.get("request_id")
        if request_id:
            invalidation = self.cache_service.invalidate_rerank_by_request_id(request_id)
        else:
            invalidation = {}
        record["bad_feedback_hook"] = self.hook_service.on_bad_feedback(request_id, invalidation)
        record["rerank_cache_invalidation"] = invalidation
        return record

    def _explain_graph(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """解释图检索命中的实体、关系和候选文档。"""
        query = arguments.get("query") or arguments.get("input") or ""
        return self.graph_service.explain(
            query,
            search_type=arguments.get("type", "all"),
            top_k=arguments.get("topK", 20),
        )

    def _get_cache_stats(self) -> dict[str, Any]:
        """返回缓存统计。"""
        return self.cache_service.get_stats()

    def _get_evaluation_summary(self, user_id: str) -> dict[str, Any]:
        """返回用户评测汇总。"""
        return self.evaluation_service.summary_user_records(user_id)


def _build_search_request(arguments: dict[str, Any]) -> SearchRequest:
    """从工具参数构建 RAG SearchRequest。"""
    return SearchRequest(
        input=arguments["input"],
        type=arguments.get("type", "all"),
        topK=arguments.get("topK", 20),
        threshold=arguments.get("threshold"),
        enableFeatureBoost=arguments.get("enableFeatureBoost", False),
    )


_agent_tool_registry: Optional[AgentToolRegistry] = None


def get_agent_tool_registry() -> AgentToolRegistry:
    """获取全局 AgentToolRegistry 实例。"""
    global _agent_tool_registry
    if _agent_tool_registry is None:
        _agent_tool_registry = AgentToolRegistry()
    else:
        pass
    return _agent_tool_registry
