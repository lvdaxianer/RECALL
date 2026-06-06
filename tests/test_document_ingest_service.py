"""
文档录入服务测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

from app.services.document_ingest_service import DocumentIngestService
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.markdown_chunk_service import MarkdownChunkService
import pytest


class FakeEmbeddingService:
    """测试用 Embedding 服务。"""

    async def encode(self, texts):
        """按输入数量返回固定向量。"""
        if isinstance(texts, list):
            return [[0.1, 0.2, 0.3] for _ in texts]
        return [0.1, 0.2, 0.3]


class BrokenEmbeddingService:
    """测试用失败 Embedding 服务。"""

    async def encode(self, texts):
        """模拟外部 Embedding 服务拒绝批量输入。"""
        raise RuntimeError("embedding 400")


class FakeESService:
    """测试用 ES 服务。"""

    def __init__(self):
        """记录批量写入文档。"""
        self.documents = []

    async def index_documents(self, index_name, documents):
        """记录 ES 批量写入。"""
        self.documents.extend(documents)
        return len(documents)


class FakeMilvusService:
    """测试用 Milvus 服务。"""

    def __init__(self):
        """记录批量写入文档。"""
        self.documents = []

    async def batch_insert(self, collection, documents):
        """记录 Milvus 批量写入。"""
        self.documents.extend(documents)
        return {"inserted_count": len(documents)}


class RecordingPlanner:
    """记录调用并返回固定语义计划。"""

    def __init__(self, plan=None, should_fail: bool = False):
        """初始化规划结果。"""
        self.calls = 0
        self.plan_payload = plan or {"groups": [["s1", "s2"]]}
        self.should_fail = should_fail

    async def plan(self, markdown: str):
        """记录调用并返回计划或抛错。"""
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("planner failed")
        return self.plan_payload


def test_document_ingest_returns_status_chunk_count_and_doc_id(tmp_path):
    """文档录入返回状态、chunk 数和文档 ID。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("技术知识库", "研发文档", "user-001")
    service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(max_chars=120, overlap=20),
    )

    result = service.ingest_document(
        knowledge_base_id=kb["id"],
        name="架构说明.md",
        content="# 架构\n说明文本",
        content_type="text/markdown",
        owner_id="user-001",
    )

    assert result["status"] == "ready"
    assert result["chunk_count"] >= 1
    assert result["document_name"] == "架构说明.md"
    assert repository.get_knowledge_base(kb["id"])["status"] == "changed"


def test_document_ingest_upserts_by_external_id(tmp_path):
    """同一知识库和 external_id 默认使用 upsert 语义。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("技术知识库", "研发文档", "user-001")
    service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(max_chars=120, overlap=20),
    )

    first = service.ingest_document(kb["id"], "a.md", "# A\n旧内容", "text/markdown", "user-001", "doc-a")
    second = service.ingest_document(kb["id"], "a.md", "# A\n新内容", "text/markdown", "user-001", "doc-a")
    chunks = repository.list_document_chunks(kb["id"], second["id"])

    assert second["id"] == first["id"]
    assert chunks[0]["content"] == "新内容"


@pytest.mark.asyncio
async def test_document_ingest_indexes_chunks_with_kb_metadata(tmp_path):
    """文档录入可将 chunk 写入 ES/Milvus 并携带知识库过滤元数据。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("技术知识库", "研发文档", "user-001")
    es_service = FakeESService()
    milvus_service = FakeMilvusService()
    service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(max_chars=120, overlap=20),
        embedding_service=FakeEmbeddingService(),
        es_service=es_service,
        milvus_service=milvus_service,
    )

    result = await service.ingest_document_async(
        knowledge_base_id=kb["id"],
        name="架构说明.md",
        content="# 架构\n说明文本",
        content_type="text/markdown",
        owner_id="user-001",
    )

    assert result["index_status"] == "indexed"
    assert es_service.documents[0]["metadata"]["knowledge_base_id"] == kb["id"]
    assert es_service.documents[0]["metadata"]["document_id"] == result["id"]
    assert milvus_service.documents[0]["metadata"]["knowledge_base_id"] == kb["id"]
    assert milvus_service.documents[0]["metadata"]["document_id"] == result["id"]


@pytest.mark.asyncio
async def test_parse_queued_document_indexes_and_updates_status(tmp_path):
    """解析 queued 文档后应写入 chunk、索引并更新为 indexed。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("技术知识库", "研发文档", "user-001")
    queued = repository.enqueue_document(
        kb["id"],
        "queued.md",
        "text/markdown",
        "user-001",
        "# 队列\n内容",
        "queued.md",
    )
    claimed = repository.claim_queued_documents(1)[0]
    es_service = FakeESService()
    milvus_service = FakeMilvusService()
    service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(max_chars=120, overlap=20),
        embedding_service=FakeEmbeddingService(),
        es_service=es_service,
        milvus_service=milvus_service,
    )

    parsed = await service.parse_queued_document(claimed)
    chunks = repository.list_document_chunks(kb["id"], queued["id"])

    assert parsed["parse_status"] == "indexed"
    assert parsed["chunk_count"] == 1
    assert chunks[0]["content"] == "内容"
    assert es_service.documents[0]["metadata"]["document_id"] == queued["id"]


@pytest.mark.asyncio
async def test_document_ingest_indexes_overlap_content_but_keeps_display_content(tmp_path):
    """ES/Milvus 写入检索正文，引用展示仍保留干净 content。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("KB", "desc", "u1")
    repository.update_knowledge_base_settings(kb["id"], {"chunk_size": 100, "overlap": 7})
    document = repository.enqueue_document(
        knowledge_base_id=kb["id"],
        document_name="guide.md",
        content_type="text/markdown",
        owner_id="u1",
        raw_content="# A\n第一段上下文ABCDEF\n## B\n第二段正文",
    )
    claimed = repository.claim_queued_documents(1)[0]

    class FakeEmbedding:
        async def encode(self, texts):
            return [[0.1] for _ in texts]

    class FakeES:
        def __init__(self):
            self.documents = []

        async def index_documents(self, index_name, documents):
            self.documents = documents

    class FakeMilvus:
        async def batch_insert(self, collection, documents):
            return None

    es = FakeES()
    service = DocumentIngestService(
        repository,
        MarkdownChunkService(),
        embedding_service=FakeEmbedding(),
        es_service=es,
        milvus_service=FakeMilvus(),
    )

    await service.parse_queued_document(claimed)

    stored_chunks = repository.list_document_chunks(kb["id"], document["id"])
    assert stored_chunks[1]["content"] == "第二段正文"
    assert stored_chunks[1]["indexed_content"].startswith("文ABCDEF\n第二段正文")
    assert es.documents[1]["description"].startswith("文ABCDEF\n第二段正文")
    assert es.documents[1]["content"] == "第二段正文"


@pytest.mark.asyncio
async def test_parse_queued_document_fails_when_embedding_fails(tmp_path):
    """Embedding 失败时应让解析失败，不写入 ES/Milvus 资产索引。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("技术知识库", "研发文档", "user-001")
    queued = repository.enqueue_document(
        kb["id"],
        "queued.md",
        "text/markdown",
        "user-001",
        "# 队列\n内容",
        "queued.md",
    )
    claimed = repository.claim_queued_documents(1)[0]
    es_service = FakeESService()
    milvus_service = FakeMilvusService()
    service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(max_chars=120, overlap=20),
        embedding_service=BrokenEmbeddingService(),
        es_service=es_service,
        milvus_service=milvus_service,
    )

    with pytest.raises(RuntimeError, match="embedding 400"):
        await service.parse_queued_document(claimed)

    updated = repository.get_document(kb["id"], queued["id"])
    assert updated["parse_status"] == "parsed"
    assert es_service.documents == []
    assert milvus_service.documents == []


@pytest.mark.asyncio
async def test_parse_queued_document_skips_planner_when_semantic_disabled(tmp_path):
    """语义分块关闭时解析 queued 文档不调用 planner。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("技术知识库", "研发文档", "user-001")
    repository.update_knowledge_base_settings(kb["id"], {"semantic_chunking_enabled": False})
    queued = repository.enqueue_document(kb["id"], "queued.md", "text/markdown", "user-001", "# A\nabcde", "queued.md")
    claimed = repository.claim_queued_documents(1)[0]
    planner = RecordingPlanner()
    service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(),
        embedding_service=FakeEmbeddingService(),
        es_service=FakeESService(),
        milvus_service=FakeMilvusService(),
        semantic_planner=planner,
    )

    await service.parse_queued_document(claimed)

    assert planner.calls == 0


@pytest.mark.asyncio
async def test_parse_queued_document_uses_semantic_plan_and_kb_settings(tmp_path):
    """语义开启时 planner 影响 chunk，并读取知识库 chunk_size/overlap。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("技术知识库", "研发文档", "user-001")
    repository.update_knowledge_base_settings(
        kb["id"],
        {"semantic_chunking_enabled": True, "chunk_size": 20, "overlap": 0},
    )
    queued = repository.enqueue_document(
        kb["id"],
        "queued.md",
        "text/markdown",
        "user-001",
        "# A\n正文 A\n## B\n正文 B",
        "queued.md",
    )
    claimed = repository.claim_queued_documents(1)[0]
    planner = RecordingPlanner({"groups": [["s1", "s2"]]})
    service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(),
        embedding_service=FakeEmbeddingService(),
        es_service=FakeESService(),
        milvus_service=FakeMilvusService(),
        semantic_planner=planner,
    )

    await service.parse_queued_document(claimed)
    chunks = repository.list_document_chunks(kb["id"], queued["id"])

    assert planner.calls == 1
    assert chunks[0]["title"] == "A / B"
    assert chunks[0]["content"] == "正文 A\n\n正文 B"


@pytest.mark.asyncio
async def test_parse_queued_document_falls_back_when_planner_fails(tmp_path):
    """planner 失败时文档解析应继续使用 Markdown 分块兜底。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("技术知识库", "研发文档", "user-001")
    repository.update_knowledge_base_settings(kb["id"], {"semantic_chunking_enabled": True})
    queued = repository.enqueue_document(
        kb["id"],
        "queued.md",
        "text/markdown",
        "user-001",
        "# A\n正文 A\n## B\n正文 B",
        "queued.md",
    )
    claimed = repository.claim_queued_documents(1)[0]
    planner = RecordingPlanner(should_fail=True)
    service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(),
        embedding_service=FakeEmbeddingService(),
        es_service=FakeESService(),
        milvus_service=FakeMilvusService(),
        semantic_planner=planner,
    )

    await service.parse_queued_document(claimed)
    chunks = repository.list_document_chunks(kb["id"], queued["id"])

    assert planner.calls == 1
    assert [chunk["title"] for chunk in chunks] == ["A", "B"]
