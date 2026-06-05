"""
轻量图谱检索服务

基于插入时抽取的 entities/relations 维护内存图索引，提供 LightRAG-lite
local/global 检索雏形。

@author lvdaxianerplus
@date 2026-05-31
"""

from typing import Any, Dict, List, Optional, Set


class GraphRetrievalService:
    """轻量图谱检索服务"""

    def __init__(self):
        """初始化内存图索引"""
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._entity_to_docs: Dict[str, Set[str]] = {}
        self._relation_terms_to_docs: Dict[str, Set[str]] = {}

    def index_document(
        self,
        doc_id: str,
        description: str,
        metadata: Dict[str, Any],
        features: Dict[str, Any]
    ) -> None:
        """
        索引单个文档的实体关系

        @param doc_id - 文档业务 ID
        @param description - 文档描述
        @param metadata - 文档元数据
        @param features - 包含 entities/relations 的特征
        """
        if doc_id in self._documents:
            self._remove_doc_from_index(self._entity_to_docs, doc_id)
            self._remove_doc_from_index(self._relation_terms_to_docs, doc_id)

        document = {
            "id": doc_id,
            "description": description,
            "metadata": metadata,
            "features": features,
            "score": 0.6
        }
        self._documents[doc_id] = document

        for entity in features.get("entities", []) or []:
            name = str(entity.get("name", "")).strip()
            if name:
                self._entity_to_docs.setdefault(name.lower(), set()).add(doc_id)

        for relation in features.get("relations", []) or []:
            source = str(relation.get("source", "")).strip()
            target = str(relation.get("target", "")).strip()
            relation_name = str(relation.get("relation", "")).strip()
            for term in [source, target, relation_name]:
                if term:
                    self._relation_terms_to_docs.setdefault(term.lower(), set()).add(doc_id)

    def index_documents(self, documents: List[Dict[str, Any]]) -> int:
        """
        批量索引文档实体关系

        @param documents - 文档列表
        @returns 索引数量
        """
        for document in documents:
            self.index_document(
                doc_id=document["id"],
                description=document["description"],
                metadata=document["metadata"],
                features=document.get("features", {})
            )
        return len(documents)

    def rebuild(self, documents: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        使用文档列表重建内存图索引

        @param documents - 文档列表
        @returns 重建后的索引统计
        """
        self._documents.clear()
        self._entity_to_docs.clear()
        self._relation_terms_to_docs.clear()
        self.index_documents(documents)
        return self.stats()

    def delete_document(self, doc_id: str) -> bool:
        """
        从图索引删除单个文档

        @param doc_id - 文档业务 ID
        @returns 是否删除成功
        """
        if doc_id not in self._documents:
            return False

        del self._documents[doc_id]
        self._remove_doc_from_index(self._entity_to_docs, doc_id)
        self._remove_doc_from_index(self._relation_terms_to_docs, doc_id)
        return True

    def search(self, query: str, search_type: str = "all", top_k: int = 20) -> List[Dict[str, Any]]:
        """
        基于实体关系执行轻量图检索

        @param query - 查询文本
        @param search_type - 资源类型
        @param top_k - 返回数量
        @returns 图检索结果
        """
        query_lower = query.lower()
        scored_docs: Dict[str, Dict[str, Any]] = {}

        for entity, doc_ids in self._entity_to_docs.items():
            if entity and entity in query_lower:
                self._add_matches(scored_docs, doc_ids, score=0.7, match_type="entity")

        for term, doc_ids in self._relation_terms_to_docs.items():
            if term and term in query_lower:
                self._add_matches(scored_docs, doc_ids, score=0.6, match_type="relation")

        results = []
        for doc_id, match in scored_docs.items():
            document = self._documents.get(doc_id)
            if not document or not self._matches_type(document, search_type):
                continue
            results.append({
                **document,
                "score": match["score"],
                "_graph_match_type": match["match_type"]
            })

        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return results[:top_k]

    def stats(self) -> Dict[str, int]:
        """
        获取图索引统计

        @returns 图索引规模
        """
        return {
            "document_count": len(self._documents),
            "entity_count": len(self._entity_to_docs),
            "relation_term_count": len(self._relation_terms_to_docs)
        }

    def explain(self, query: str, search_type: str = "all", top_k: int = 20) -> Dict[str, Any]:
        """
        解释一次图检索命中

        @param query - 查询文本
        @param search_type - 资源类型
        @param top_k - 返回数量
        @returns 图检索解释信息
        """
        query_lower = query.lower()
        matched_entities = [
            entity
            for entity in self._entity_to_docs
            if entity and entity in query_lower
        ]
        matched_relation_terms = [
            term
            for term in self._relation_terms_to_docs
            if term and term in query_lower
        ]
        results = self.search(query, search_type=search_type, top_k=top_k)
        return {
            "query": query,
            "search_type": search_type,
            "top_k": top_k,
            "matched_entities": matched_entities,
            "matched_relation_terms": matched_relation_terms,
            "result_count": len(results),
            "matches": [
                {
                    "id": item["id"],
                    "match_type": item.get("_graph_match_type"),
                    "score": item.get("score", 0),
                    "description": item.get("description", ""),
                    "metadata": item.get("metadata", {})
                }
                for item in results
            ]
        }

    def _add_matches(
        self,
        scored_docs: Dict[str, Dict[str, Any]],
        doc_ids: Set[str],
        score: float,
        match_type: str
    ) -> None:
        """添加或更新匹配文档分数"""
        for doc_id in doc_ids:
            current = scored_docs.get(doc_id)
            if current is None or score > current["score"]:
                scored_docs[doc_id] = {"score": score, "match_type": match_type}

    def _matches_type(self, document: Dict[str, Any], search_type: str) -> bool:
        """检查文档类型是否匹配查询类型"""
        if search_type == "all":
            return True
        return document.get("metadata", {}).get("type") == search_type

    def _remove_doc_from_index(self, index: Dict[str, Set[str]], doc_id: str) -> None:
        """从倒排索引中删除文档引用，并清理空词项"""
        empty_terms = []
        for term, doc_ids in index.items():
            doc_ids.discard(doc_id)
            if not doc_ids:
                empty_terms.append(term)

        for term in empty_terms:
            del index[term]


_graph_retrieval_service: Optional[GraphRetrievalService] = None


def get_graph_retrieval_service() -> GraphRetrievalService:
    """获取轻量图谱检索服务单例"""
    global _graph_retrieval_service
    if _graph_retrieval_service is None:
        _graph_retrieval_service = GraphRetrievalService()
    return _graph_retrieval_service
