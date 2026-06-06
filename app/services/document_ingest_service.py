"""
文档录入服务

负责纯文本/Markdown 文档状态机、幂等 upsert 和 chunk 持久化。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from typing import Any

from app.config import Config
from app.models.knowledge_base_schemas import DocumentUploadRequest
from app.services.embedding_service import EmbeddingService
from app.services.es_service import get_es_service
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.markdown_chunk_service import MarkdownChunkService
from app.services.milvus_service import MilvusService
from app.services.semantic_chunk_planning_service import SemanticChunkPlanningService
from app.services.taxonomy_extraction_service import TaxonomyExtractionService
from app.utils.logger import rag_search_logger


class DocumentIngestService:
    """文档录入服务实现。"""

    def __init__(
        self,
        repository: KnowledgeBaseRepository,
        chunk_service: MarkdownChunkService,
        embedding_service: Any | None = None,
        es_service: Any | None = None,
        milvus_service: Any | None = None,
        semantic_planner: Any | None = None,
        taxonomy_extractor: Any | None = None,
    ):
        """初始化文档录入服务。"""
        self.repository = repository
        self.chunk_service = chunk_service
        self.embedding_service = embedding_service
        self.es_service = es_service
        self.milvus_service = milvus_service
        self.semantic_planner = semantic_planner
        self.taxonomy_extractor = taxonomy_extractor

    def ingest_document(
        self,
        knowledge_base_id: str,
        name: str,
        content: str,
        content_type: str,
        owner_id: str,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """录入纯文本或 Markdown 文档并返回回执。"""
        DocumentUploadRequest(
            knowledge_base_id=knowledge_base_id,
            name=name,
            content=content,
            content_type=content_type,
            owner_id=owner_id,
            external_id=external_id,
        )
        self._assert_knowledge_base_owner(knowledge_base_id, owner_id)
        chunks = self.chunk_service.split(content)
        document = self.repository.upsert_document(
            knowledge_base_id=knowledge_base_id,
            document_name=name,
            content_type=content_type,
            owner_id=owner_id,
            chunk_count=len(chunks),
            external_id=external_id,
        )
        self.repository.replace_document_chunks(knowledge_base_id, document["id"], chunks)
        self.repository.mark_knowledge_base_changed(knowledge_base_id)
        return document

    def enqueue_document(
        self,
        knowledge_base_id: str,
        name: str,
        content: str,
        content_type: str,
        owner_id: str,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """接收文档并放入后台解析队列。"""
        DocumentUploadRequest(
            knowledge_base_id=knowledge_base_id,
            name=name,
            content=content,
            content_type=content_type,
            owner_id=owner_id,
            external_id=external_id,
        )
        self._assert_knowledge_base_owner(knowledge_base_id, owner_id)
        document = self.repository.enqueue_document(
            knowledge_base_id=knowledge_base_id,
            document_name=name,
            content_type=content_type,
            owner_id=owner_id,
            raw_content=content,
            external_id=external_id,
        )
        self.repository.mark_knowledge_base_changed(knowledge_base_id)
        return document

    async def ingest_document_async(
        self,
        knowledge_base_id: str,
        name: str,
        content: str,
        content_type: str,
        owner_id: str,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """录入文档并同步写入 ES/Milvus 检索引擎。"""
        document = self.ingest_document(
            knowledge_base_id=knowledge_base_id,
            name=name,
            content=content,
            content_type=content_type,
            owner_id=owner_id,
            external_id=external_id,
        )
        chunks = self.repository.list_document_chunks(knowledge_base_id, document["id"])
        try:
            await self._index_chunks(document, chunks)
            document["index_status"] = "indexed"
        except Exception:
            document["index_status"] = "degraded"
        return document

    async def parse_queued_document(self, document: dict[str, Any]) -> dict[str, Any]:
        """解析已被 worker 认领的 queued 文档并写入检索索引。"""
        content = document.get("raw_content") or ""
        settings = self.repository.get_knowledge_base_settings(document["knowledge_base_id"])
        chunk_service = MarkdownChunkService(
            max_chars=settings["chunk_size"],
            overlap=settings["overlap"],
            max_heading_depth=settings["max_heading_depth"],
        )
        semantic_plan = await self._build_semantic_plan(content, settings)
        chunks = chunk_service.split(content, semantic_plan=semantic_plan)
        self.repository.replace_document_chunks(
            document["knowledge_base_id"],
            document["id"],
            chunks,
        )
        self.repository.mark_document_parsed(
            document["knowledge_base_id"],
            document["id"],
            len(chunks),
        )
        taxonomy = await self._extract_and_store_taxonomy(document, content)
        indexed_chunks = self.repository.list_document_chunks(
            document["knowledge_base_id"],
            document["id"],
        )
        await self._index_chunks(document, indexed_chunks, taxonomy=taxonomy)
        return self.repository.mark_document_indexed(
            document["knowledge_base_id"],
            document["id"],
        )

    async def _build_semantic_plan(
        self,
        content: str,
        settings: dict[str, Any],
    ) -> dict[str, Any] | None:
        """按知识库设置构建语义分块计划，失败时返回 None 走兜底。"""
        if not settings["semantic_chunking_enabled"]:
            return None
        try:
            planner = self._get_semantic_planner(settings)
            return await planner.plan(content)
        except Exception as exc:
            rag_search_logger.warning("[知识库] 语义分块规划失败，使用 Markdown 兜底, error={}", str(exc))
            return None

    async def _extract_and_store_taxonomy(self, document: dict[str, Any], content: str) -> dict[str, Any] | None:
        """抽取并保存主题树，失败时只降级记录日志，不阻塞入库。"""
        try:
            taxonomy = await self._get_taxonomy_extractor().extract(
                title=document["document_name"],
                content=content,
                existing_tags=[document["document_name"]],
            )
            return self.repository.upsert_document_topics(
                knowledge_base_id=document["knowledge_base_id"],
                document_id=document["id"],
                primary_topic=taxonomy.primary_topic,
                parent_topics=taxonomy.parent_topics,
                sibling_topics=taxonomy.sibling_topics,
                child_topics=taxonomy.child_topics,
                topic_aliases=taxonomy.topic_aliases,
                topic_path=taxonomy.topic_path,
                confidence=taxonomy.confidence,
                evidence=taxonomy.evidence,
            )
        except Exception as exc:
            rag_search_logger.warning("[知识库] 主题树抽取失败，继续索引文档, document_id={}, error={}", document.get("id"), str(exc))
            return None

    async def _index_chunks(
        self,
        document: dict[str, Any],
        chunks: list[dict[str, Any]],
        taxonomy: dict[str, Any] | None = None,
    ) -> None:
        """批量写入 chunk 到 ES 和 Milvus。"""
        if not chunks:
            return
        texts = [chunk.get("indexed_content") or chunk["content"] for chunk in chunks]
        vectors = await self._embed_texts_in_batches(texts)
        documents = [
            self._build_index_document(document, chunk, vectors[index], taxonomy=taxonomy)
            for index, chunk in enumerate(chunks)
        ]
        await self._get_es_service().index_documents(Config.ES_ASSET_INDEX, documents)
        await self._get_milvus_service().batch_insert("knowledge_chunk", documents)

    async def _embed_texts_in_batches(self, texts: list[str]) -> list[list[float]]:
        """分批调用 Embedding，避免长文档一次请求过大导致整篇索引失败。"""
        batch_size = max(1, Config.KNOWLEDGE_BASE_EMBEDDING_BATCH_SIZE)
        vectors: list[list[float]] = []
        embedding_service = self._get_embedding_service()
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            batch_vectors = await embedding_service.encode(batch)
            vectors.extend(batch_vectors)
        return vectors

    def _build_index_document(
        self,
        document: dict[str, Any],
        chunk: dict[str, Any],
        vector: list[float],
        taxonomy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构建 ES/Milvus 共用 chunk 索引文档。"""
        index_content = chunk.get("indexed_content") or chunk["content"]
        metadata = {
            "type": "knowledge_chunk",
            "id": chunk["id"],
            "knowledge_base_id": chunk["knowledge_base_id"],
            "document_id": chunk["document_id"],
            "document_name": document["document_name"],
            "chunk_index": chunk["chunk_index"],
            "section_title": chunk.get("title", ""),
            "title": chunk.get("title", ""),
        }
        features = {
            "title": chunk.get("title", ""),
            "tags": [document["document_name"]],
        }
        if taxonomy:
            metadata.update({
                "primary_topic": taxonomy["primary_topic"],
                "topic_path": taxonomy["topic_path"],
            })
            features.update({
                "primary_topic": taxonomy["primary_topic"],
                "parent_topics": taxonomy["parent_topics"],
                "topic_path": taxonomy["topic_path"],
                "topic_aliases": taxonomy["topic_aliases"],
            })
        return {
            "doc_id": chunk["id"],
            "id": chunk["id"],
            "description": index_content,
            "content": chunk["content"],
            "vector": vector,
            "metadata": metadata,
            "features": features,
        }

    def _get_embedding_service(self):
        """获取 Embedding 服务。"""
        if self.embedding_service is None:
            self.embedding_service = EmbeddingService()
        return self.embedding_service

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

    def _get_semantic_planner(self, settings: dict[str, Any]):
        """获取语义分块规划服务。"""
        if self.semantic_planner is None:
            self.semantic_planner = SemanticChunkPlanningService(
                max_heading_depth=settings["max_heading_depth"],
                timeout_ms=settings["llm_planning_timeout_ms"],
            )
        return self.semantic_planner

    def _get_taxonomy_extractor(self):
        """获取主题树抽取服务。"""
        if self.taxonomy_extractor is None:
            self.taxonomy_extractor = TaxonomyExtractionService()
        return self.taxonomy_extractor

    def _assert_knowledge_base_owner(self, knowledge_base_id: str, owner_id: str) -> None:
        """校验文档录入者是否为知识库 owner。"""
        knowledge_base = self.repository.get_knowledge_base(knowledge_base_id)
        if knowledge_base is None:
            raise ValueError("知识库不存在")
        elif knowledge_base["owner_id"] == owner_id:
            return
        else:
            raise PermissionError("无权向该知识库录入文档")
