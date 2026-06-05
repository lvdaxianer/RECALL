"""
Query scope detection for local, global, and hybrid retrieval routes.
"""


class QueryScopeService:
    """Deterministic query scope detector used before retrieval routing."""

    GLOBAL_TERMS = ("总结", "整体", "概览", "全局", "架构", "盘点", "趋势", "共性", "能力缺口", "缺什么")
    EVIDENCE_TERMS = ("证明", "证据", "哪些文件", "引用", "出处", "依据")

    def detect(self, query: str) -> dict:
        text = query or ""
        has_global = any(term in text for term in self.GLOBAL_TERMS)
        has_evidence = any(term in text for term in self.EVIDENCE_TERMS)

        if has_global and has_evidence:
            return self._result(
                query_scope="hybrid",
                reason="问题同时需要全局定位和局部证据",
                strategy="summary_then_evidence",
                steps=["document_summary", "section_summary", "evidence_chunks", "parent_context"],
            )
        if has_global:
            return self._result(
                query_scope="global",
                reason="问题需要跨文档或跨章节汇总",
                strategy="summary_first",
                steps=["document_summary", "section_summary", "map_reduce_context"],
            )
        return self._result(
            query_scope="local",
            reason="问题聚焦具体事实、故障或配置",
            strategy="local_chunk",
            steps=["chunk_retrieval", "rerank", "answer_context"],
        )

    def _result(self, query_scope: str, reason: str, strategy: str, steps: list[str]) -> dict:
        return {
            "query_scope": query_scope,
            "reason": reason,
            "route_plan": {
                "strategy": strategy,
                "steps": steps,
            },
        }
