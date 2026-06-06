"""
Summary-first retrieval orchestration for global and hybrid questions.
"""

import asyncio
from typing import Any, Dict, List, Optional


class ESSummaryRetriever:
    """ES-backed retriever for summary-first global retrieval."""

    def __init__(self, es_service, index_names: List[str]):
        self.es_service = es_service
        self.index_names = index_names

    async def search_summaries(
        self,
        query: str,
        top_k: int,
        summary_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        metadata_filter: Dict[str, Any] = {"is_summary": True}
        if summary_type:
            metadata_filter["summary_type"] = summary_type

        raw_results = await asyncio.gather(*[
            self.es_service.search_weighted(
                index_name=index_name,
                query=query,
                top_k=top_k,
                metadata_filter=metadata_filter,
            )
            for index_name in self.index_names
        ], return_exceptions=True)
        result_lists = self._successful_result_lists(raw_results)
        return self._merge_ranked_results(result_lists, top_k)

    async def search_evidence(
        self,
        query: str,
        parent_ids: List[str],
        section_ids: List[str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if not parent_ids:
            return []

        raw_results = await asyncio.gather(*[
            self.es_service.search_parent_contexts(
                index_name=index_name,
                parent_ids=parent_ids,
                section_ids=section_ids,
                limit=top_k,
            )
            for index_name in self.index_names
        ], return_exceptions=True)
        result_lists = self._successful_result_lists(raw_results)
        return self._merge_ranked_results(result_lists, top_k)

    def _successful_result_lists(self, raw_results: List[Any]) -> List[List[Dict[str, Any]]]:
        """Drop failed index results while keeping successful summary/evidence hits."""
        return [
            result
            for result in raw_results
            if isinstance(result, list)
        ]

    def _merge_ranked_results(
        self,
        result_lists: List[List[Dict[str, Any]]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Merge multi-index ES results by id, preserving highest scores."""
        keyed_results: Dict[str, Dict[str, Any]] = {}
        anonymous_results = []
        for index_results in result_lists:
            for result in index_results:
                result_id = result.get("id")
                if not result_id:
                    anonymous_results.append(result)
                    continue
                current = keyed_results.get(result_id)
                if current is None or result.get("score", 0) > current.get("score", 0):
                    keyed_results[result_id] = result
        results = [*keyed_results.values(), *anonymous_results]
        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return results[:top_k]


class GlobalRetrievalService:
    """Builds structured context for summary-first retrieval."""

    def __init__(self, retriever):
        self.retriever = retriever

    async def build_context(self, query: str, query_scope: str, top_k: int) -> Dict[str, Any]:
        route = "summary_then_evidence" if query_scope == "hybrid" else "summary_first"
        route_plan = self._route_plan(query_scope)
        summaries = await self.retriever.search_summaries(query, top_k=top_k, summary_type=None)
        parent_ids = self._unique_metadata_values(summaries, "parent_id")
        section_ids = self._unique_metadata_values(summaries, "section_id")
        evidence_chunks = await self._search_evidence_by_summary_scope(query, summaries, top_k)
        map_inputs = self._build_map_inputs(summaries, evidence_chunks)
        return {
            "route": route,
            "route_plan": route_plan,
            "query_scope": query_scope or "global",
            "summaries": summaries,
            "evidence_chunks": evidence_chunks,
            "parent_context": {
                "parent_ids": parent_ids,
                "section_ids": section_ids,
            },
            "map_inputs": map_inputs,
            "map_reduce_context": self._build_map_reduce_context(summaries, evidence_chunks),
            "synthesis_context": self.build_synthesis_context(query, map_inputs),
        }

    def _route_plan(self, query_scope: str) -> List[str]:
        """Build a deterministic route plan for SEE/debug output."""
        if query_scope == "hybrid":
            return ["summary_retrieval", "section_expansion", "evidence_chunk_retrieval", "map_reduce_synthesis"]
        return ["summary_retrieval", "section_expansion", "evidence_chunk_retrieval", "map_reduce_synthesis"]

    async def _search_evidence_by_summary_scope(
        self,
        query: str,
        summaries: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Expand evidence without letting section filters leak across document summaries."""
        evidence_results = []
        seen_ids = set()
        raw_scope_results = await asyncio.gather(*[
            self.retriever.search_evidence(
                query,
                parent_ids=scope["parent_ids"],
                section_ids=scope["section_ids"],
                top_k=top_k,
            )
            for scope in self._evidence_scopes(summaries)
        ], return_exceptions=True)
        for chunks in self._successful_result_lists(raw_scope_results):
            for chunk in chunks:
                chunk_id = chunk.get("id")
                if chunk_id and chunk_id in seen_ids:
                    continue
                if chunk_id:
                    seen_ids.add(chunk_id)
                evidence_results.append(chunk)
        evidence_results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return evidence_results[:top_k]

    def _evidence_scopes(self, summaries: List[Dict[str, Any]]) -> List[Dict[str, List[str]]]:
        """Build document-level and section-level evidence scopes from summaries."""
        document_parent_ids = []
        section_scopes: Dict[tuple[str, str], Dict[str, List[str]]] = {}
        seen_document_parents = set()
        for summary in summaries:
            metadata = summary.get("metadata") or {}
            parent_id = metadata.get("parent_id")
            section_id = metadata.get("section_id")
            if not parent_id:
                continue
            if section_id:
                section_scopes.setdefault(
                    (parent_id, section_id),
                    {"parent_ids": [parent_id], "section_ids": [section_id]},
                )
                continue
            if parent_id not in seen_document_parents:
                seen_document_parents.add(parent_id)
                document_parent_ids.append(parent_id)

        scopes = []
        if document_parent_ids:
            scopes.append({"parent_ids": document_parent_ids, "section_ids": []})
        scopes.extend(section_scopes.values())
        return scopes

    def _successful_result_lists(self, raw_results: List[Any]) -> List[List[Dict[str, Any]]]:
        """Drop failed scope results while keeping successful evidence hits."""
        return [
            result
            for result in raw_results
            if isinstance(result, list)
        ]

    def _unique_metadata_values(self, results: List[Dict[str, Any]], key: str) -> List[str]:
        values = []
        seen = set()
        for result in results:
            value = (result.get("metadata") or {}).get(key)
            if value and value not in seen:
                seen.add(value)
                values.append(value)
        return values

    def _build_map_reduce_context(
        self,
        summaries: List[Dict[str, Any]],
        evidence_chunks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        map_notes = []
        for summary in summaries:
            metadata = summary.get("metadata") or {}
            parent_id = metadata.get("parent_id")
            section_id = metadata.get("section_id")
            evidence = [
                chunk.get("description", "")
                for chunk in evidence_chunks
                if self._same_scope(chunk.get("metadata") or {}, parent_id, section_id)
            ]
            map_notes.append({
                "parent_id": parent_id,
                "section_id": section_id,
                "section_title": metadata.get("section_title", ""),
                "summary": summary.get("description", ""),
                "evidence": evidence,
            })
        return {
            "map_notes": map_notes,
            "reduce_prompt_context": "\n".join(
                note["summary"] for note in map_notes if note.get("summary")
            ),
        }

    def _build_map_inputs(
        self,
        summaries: List[Dict[str, Any]],
        evidence_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        inputs = []
        for summary in summaries:
            metadata = summary.get("metadata") or {}
            parent_id = metadata.get("parent_id")
            section_id = metadata.get("section_id")
            evidence = [
                chunk
                for chunk in evidence_chunks
                if self._same_scope(chunk.get("metadata") or {}, parent_id, section_id)
            ]
            inputs.append({
                "source_doc_id": parent_id,
                "section_id": section_id,
                "summary": summary,
                "evidence_chunks": evidence,
            })
        return inputs

    def build_synthesis_context(
        self,
        query: str,
        map_inputs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build structured map-reduce input without exposing private reasoning."""
        map_notes = []
        for item in map_inputs:
            evidence = [
                {
                    "chunk_id": chunk.get("id"),
                    "content": chunk.get("description", ""),
                }
                for chunk in item.get("evidence_chunks", [])
            ]
            map_notes.append({
                "source_doc_id": item.get("source_doc_id"),
                "section_id": item.get("section_id"),
                "summary": (item.get("summary") or {}).get("description", ""),
                "evidence": evidence,
            })
        return {
            "query": query,
            "reduce_instruction": "基于每个文档或章节的摘要和证据 chunk 生成全局答案",
            "route_plan": ["summary_retrieval", "section_expansion", "evidence_chunk_retrieval", "map_reduce_synthesis"],
            "map_notes": map_notes,
        }

    def _same_scope(
        self,
        metadata: Dict[str, Any],
        parent_id: Optional[str],
        section_id: Optional[str],
    ) -> bool:
        if parent_id and metadata.get("parent_id") != parent_id:
            return False
        if section_id and metadata.get("section_id") != section_id:
            return False
        return True
