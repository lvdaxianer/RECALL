"""
Retrieval SDK 服务测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

from app.services.document_ingest_service import DocumentIngestService
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.markdown_chunk_service import MarkdownChunkService
from app.services.retrieval_sdk_service import RetrievalSDKService
import pytest


class FakeEmbeddingService:
    """测试用 Embedding 服务。"""

    def __init__(self):
        """记录调用次数。"""
        self.calls = 0

    async def encode(self, text):
        """返回固定向量。"""
        self.calls += 1
        return [0.1, 0.2, 0.3]


class FakeESService:
    """测试用 ES 服务。"""

    def __init__(self):
        """记录过滤条件。"""
        self.filters = []

    async def search(self, index_name, query, top_k, query_lang="auto", metadata_filter=None):
        """返回带知识库元数据的 ES 命中。"""
        self.filters.append(metadata_filter)
        return [
            {
                "id": "chunk-es",
                "description": "ES 检索命中",
                "score": 2.0,
                "metadata": {
                    "knowledge_base_id": "kb-001",
                    "document_id": "doc-001",
                    "chunk_index": 0,
                    "document_name": "es.md",
                    "section_title": "ES",
                },
                "features": {},
                "source_scores": {"text": 2.0},
            }
        ]


class RecordingQueryESService:
    """记录传入查询文本的 ES 服务。"""

    def __init__(self, kb_id: str):
        """初始化记录和知识库 ID。"""
        self.kb_id = kb_id
        self.queries = []

    async def search(self, index_name, query, top_k, query_lang="auto", metadata_filter=None):
        """记录查询并返回空结果。"""
        self.queries.append(query)
        return []


class RecordingQueryEmbeddingService:
    """记录传入查询文本的 Embedding 服务。"""

    def __init__(self):
        """初始化调用记录。"""
        self.queries = []

    async def encode(self, text):
        """记录查询并返回固定向量。"""
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class FakeMilvusService:
    """测试用 Milvus 服务。"""

    def __init__(self):
        """记录过滤条件。"""
        self.filters = []

    async def search(self, collection, query_vector, top_k=20, metadata_filter=None):
        """返回带知识库元数据的向量命中。"""
        self.filters.append(metadata_filter)
        return [
            {
                "id": "chunk-vector",
                "description": "Milvus 向量命中",
                "score": 0.9,
                "metadata": {
                    "knowledge_base_id": "kb-001",
                    "document_id": "doc-002",
                    "chunk_index": 1,
                    "document_name": "vector.md",
                    "section_title": "Vector",
                },
                "features": {},
            }
        ]


class FakeRerankService:
    """测试用 Rerank 服务。"""

    async def rerank(self, query, documents, request_id=None):
        """反转候选顺序，证明 SDK 应用 rerank 分数。"""
        return [{"index": 1, "score": 0.98}, {"index": 0, "score": 0.75}]


class WrongKnowledgeBaseESService:
    """返回错知识库命中的 ES 服务。"""

    async def search(self, index_name, query, top_k, query_lang="auto", metadata_filter=None):
        """模拟 ES 过滤失效返回其它知识库结果。"""
        return [{
            "id": "wrong-es",
            "description": "错误知识库命中",
            "score": 9.0,
            "metadata": {"knowledge_base_id": "kb-other", "document_name": "wrong.md"},
        }]


class EmptyMilvusService:
    """不返回向量命中的 Milvus 服务。"""

    async def search(self, collection, query_vector, top_k=20, metadata_filter=None):
        """模拟向量召回为空。"""
        return []


class IdentityRerankService:
    """按原候选顺序返回分数的 Rerank 服务。"""

    async def rerank(self, query, documents, request_id=None):
        """保持候选顺序，便于断言降级结果。"""
        return [{"index": index, "score": 1.0 - index * 0.01} for index, _ in enumerate(documents)]


class RecordingRerankService:
    """记录传入候选文本的 Rerank 服务。"""

    def __init__(self):
        """初始化调用记录。"""
        self.documents = []

    async def rerank(self, query, documents, request_id=None):
        """记录候选并保持原顺序。"""
        self.documents = documents
        return [{"index": index, "score": 1.0 - index * 0.01} for index, _ in enumerate(documents)]


class FailingRerankService:
    """模拟 Rerank provider 失败。"""

    async def rerank(self, query, documents, request_id=None):
        """始终抛出异常。"""
        raise RuntimeError("provider returned 400")


class WeakSameKnowledgeBaseESService:
    """返回同知识库弱语义候选的 ES 服务。"""

    def __init__(self, kb_id: str):
        """记录知识库 ID。"""
        self.kb_id = kb_id

    async def search(self, index_name, query, top_k, query_lang="auto", metadata_filter=None):
        """模拟引擎返回同库但不精确的候选。"""
        return [{
            "id": "weak-es",
            "description": "泛化候选",
            "score": 0.2,
            "metadata": {"knowledge_base_id": self.kb_id, "document_name": "weak.md"},
        }]


def test_retrieval_sdk_returns_scope_and_route_plan(tmp_path):
    """SDK 返回 query scope、route_plan 和知识库过滤信息。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    first_kb = repository.create_knowledge_base("研发知识库", "研发文档", "u1")
    second_kb = repository.create_knowledge_base("产品知识库", "产品文档", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(first_kb["id"], "arch.md", "# 架构\n整体架构包含检索和流式输出", "text/markdown", "u1")
    ingest.ingest_document(second_kb["id"], "login.md", "# 登录\n登录失败排查密码配置", "text/markdown", "u1")
    sdk = RetrievalSDKService(repository)

    result = sdk.search(
        input="整体架构有哪些能力缺口",
        knowledge_base_ids=[first_kb["id"], second_kb["id"]],
        top_k=5,
    )

    assert result["query_scope"] in {"global", "hybrid"}
    assert result["route_plan"]["steps"]
    assert result["filters"]["knowledge_base_ids"] == [first_kb["id"], second_kb["id"]]


def test_retrieval_sdk_trace_includes_issue_type(tmp_path):
    """SDK 检索结果应包含问题类型、过滤条件和 trace 可观测信息。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("故障库", "故障文档", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(kb["id"], "fault.md", "# 白屏\n小程序白屏怎么排查", "text/markdown", "u1")
    sdk = RetrievalSDKService(repository)

    result = sdk.search("小程序白屏怎么排查", [kb["id"]], top_k=5)

    assert result["query_scope"] == "local"
    assert result["issue_type"] == "fault"
    assert result["filters"]["issue_type"] == ["fault"]
    assert result["trace"][1]["metrics"]["issue_filters"]["issue_type"] == ["fault"]


def test_retrieval_sdk_uses_kb_default_top_k_when_missing(tmp_path):
    """未显式传 topK 时使用选中知识库设置里的默认 topK。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("KB", "desc", "u1")
    repository.update_knowledge_base_settings(kb["id"], {"top_k_default": 8})
    sdk = RetrievalSDKService(repository)

    assert sdk.resolve_top_k(None, [kb["id"]]) == 8
    assert sdk.resolve_top_k(3, [kb["id"]]) == 3


def test_retrieval_sdk_builds_context_query_from_recent_questions(tmp_path):
    """开启上下文时合并最近三个非空且去重的问题，并把当前问题放最后。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    sdk = RetrievalSDKService(repository)

    query = sdk.build_retrieval_query(
        "当前问题",
        use_context=True,
        history_questions=["旧问题", "", "重复问题", "重复问题", "最近问题"],
    )

    assert query == "重复问题；最近问题；当前问题"
    assert sdk.build_retrieval_query("当前问题", use_context=False, history_questions=["旧问题"]) == "当前问题"


def test_retrieval_sdk_caps_context_query_length(tmp_path):
    """上下文检索 query 最长限制为 300 字符。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    sdk = RetrievalSDKService(repository)

    query = sdk.build_retrieval_query(
        "当前问题" * 80,
        use_context=True,
        history_questions=["历史问题" * 80],
    )

    assert len(query) == 300


def test_retrieval_sdk_filters_results_by_knowledge_base(tmp_path):
    """SDK 检索结果只来自勾选的知识库。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    first_kb = repository.create_knowledge_base("研发知识库", "研发文档", "u1")
    second_kb = repository.create_knowledge_base("产品知识库", "产品文档", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(first_kb["id"], "arch.md", "# 架构\n检索 SDK 支持 score trace", "text/markdown", "u1")
    ingest.ingest_document(second_kb["id"], "login.md", "# 登录\n检索 SDK 不应该返回这里", "text/markdown", "u1")
    sdk = RetrievalSDKService(repository)

    result = sdk.search(input="检索 SDK score trace", knowledge_base_ids=[first_kb["id"]], top_k=5)

    assert result["results"]
    assert {item["knowledge_base_id"] for item in result["results"]} == {first_kb["id"]}
    assert result["results"][0]["score_trace"]["term_overlap"] >= 1


def test_retrieval_sdk_scores_mixed_language_document_names(tmp_path):
    """SDK 应用文档名和混合中英文 token 命中，优先召回 Obsidian 标题型笔记。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Obsidian", "笔记", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(
        kb["id"],
        "笔记/Java/中间件/Zookeeper/知识点/12.Zookeeper实现Master选举.md",
        "# Zookeeper实现Master选举\n临时节点实现分布式选主",
        "text/markdown",
        "u1",
    )
    ingest.ingest_document(
        kb["id"],
        "笔记/Java/中间件/Kafka/07.Kafka Leader选举过程详解.md",
        "# Kafka Leader选举过程详解\nZooKeeper 版本的 Leader 选举流程",
        "text/markdown",
        "u1",
    )
    sdk = RetrievalSDKService(repository)

    result = sdk.search("12 Zookeeper Master 选举", [kb["id"]], top_k=5)

    assert result["results"][0]["document_name"].endswith("12.Zookeeper实现Master选举.md")
    assert result["results"][0]["score_trace"]["document_name_overlap"] >= 3


@pytest.mark.asyncio
async def test_retrieval_sdk_passes_kb_filters_to_es_milvus_and_rerank(tmp_path):
    """SDK 引擎路径把知识库过滤下传给 ES/Milvus，并保留 Rerank score trace。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    es_service = FakeESService()
    milvus_service = FakeMilvusService()
    sdk = RetrievalSDKService(
        repository,
        es_service=es_service,
        milvus_service=milvus_service,
        embedding_service=FakeEmbeddingService(),
        rerank_service=FakeRerankService(),
    )

    result = await sdk.search_with_engines(
        input="检索 SDK",
        knowledge_base_ids=["kb-001"],
        top_k=5,
        request_id="req-test",
    )

    assert es_service.filters == [{"knowledge_base_id": "kb-001"}]
    assert milvus_service.filters == [{"knowledge_base_ids": ["kb-001"]}]
    assert result["results"][0]["chunk_id"] == "chunk-vector"
    assert result["results"][0]["score_trace"]["rerank_score"] == 0.98
    assert result["trace"][1]["metrics"]["engine"] == "es_milvus_rerank"


@pytest.mark.asyncio
async def test_retrieval_sdk_passes_issue_filters_to_es_milvus(tmp_path):
    """SDK 引擎路径应把问题类型过滤合并下传给 ES/Milvus。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    es_service = FakeESService()
    milvus_service = FakeMilvusService()
    sdk = RetrievalSDKService(
        repository,
        es_service=es_service,
        milvus_service=milvus_service,
        embedding_service=FakeEmbeddingService(),
        rerank_service=FakeRerankService(),
    )

    result = await sdk.search_with_engines(
        input="小程序白屏怎么排查",
        knowledge_base_ids=["kb-001"],
        top_k=5,
        request_id="req-test",
    )

    assert es_service.filters[0]["knowledge_base_id"] == "kb-001"
    assert es_service.filters[0]["issue_type"] == ["fault"]
    assert milvus_service.filters[0]["knowledge_base_ids"] == ["kb-001"]
    assert milvus_service.filters[0]["source_type"]
    assert result["issue_type"] == "fault"


@pytest.mark.asyncio
async def test_retrieval_sdk_uses_synonym_normalized_query_for_engines(tmp_path):
    """SDK 引擎路径应使用 DB 同义词归一后的 query 召回 ES/Milvus。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Python", "notes", "u1")
    repository.create_synonym_group(kb["id"], "职责", ["能负责啥"], "u1")
    es_service = RecordingQueryESService(kb["id"])
    embedding_service = RecordingQueryEmbeddingService()
    sdk = RetrievalSDKService(
        repository,
        es_service=es_service,
        milvus_service=EmptyMilvusService(),
        embedding_service=embedding_service,
        rerank_service=FakeRerankService(),
    )

    result = await sdk.search_with_engines(
        input="装饰器能负责啥",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        request_id="req-test",
    )

    assert es_service.queries == ["装饰器职责"]
    assert embedding_service.queries == ["装饰器职责"]
    assert result["trace"][1]["metrics"]["normalized_query"] == "装饰器职责"


@pytest.mark.asyncio
async def test_retrieval_sdk_skips_engines_for_confident_local_title_match(tmp_path):
    """本地标题/文档名高置信命中时直接返回，避免外部 Rerank 误排标题型笔记。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Obsidian", "笔记", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(
        kb["id"],
        "笔记/Java/中间件/Zookeeper/知识点/12.Zookeeper实现Master选举.md",
        "# Zookeeper实现Master选举\n临时节点实现分布式选主",
        "text/markdown",
        "u1",
    )
    embedding = FakeEmbeddingService()
    es_service = FakeESService()
    sdk = RetrievalSDKService(
        repository,
        es_service=es_service,
        milvus_service=EmptyMilvusService(),
        embedding_service=embedding,
        rerank_service=FakeRerankService(),
    )

    result = await sdk.search_with_engines("12 Zookeeper Master 选举", [kb["id"]], top_k=5, request_id="req-test")

    assert result["results"][0]["document_name"].endswith("12.Zookeeper实现Master选举.md")
    assert result["trace"][1]["metrics"]["engine"] == "sqlite_confident_title"
    assert result["trace"][1]["metrics"]["rerank_skipped"] is True
    assert embedding.calls == 0
    assert es_service.filters == []


@pytest.mark.asyncio
async def test_retrieval_sdk_confident_local_match_does_not_tokenize_chunk_body(tmp_path, monkeypatch):
    """高置信标题/文档名命中时不扫描正文 token，降低大知识库标题检索延迟。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Obsidian", "笔记", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(
        kb["id"],
        "笔记/Java/线程/并发编程/03.线程状态.md",
        "# 线程状态\n这是一个很长正文，标题已经足够命中，不应该为了高置信判断扫描正文 token",
        "text/markdown",
        "u1",
    )
    seen_texts = []
    from app.services import retrieval_sdk_service as retrieval_module

    original_tokenize = retrieval_module._tokenize

    def recording_tokenize(text):
        seen_texts.append(text)
        return original_tokenize(text)

    monkeypatch.setattr(retrieval_module, "_tokenize", recording_tokenize)
    sdk = RetrievalSDKService(
        repository,
        es_service=FakeESService(),
        milvus_service=EmptyMilvusService(),
        embedding_service=FakeEmbeddingService(),
        rerank_service=FakeRerankService(),
    )

    result = await sdk.search_with_engines("03 线程状态 线程状态", [kb["id"]], top_k=5, request_id="req-test")

    assert result["trace"][1]["metrics"]["engine"] == "sqlite_confident_title"
    assert not any("很长正文" in text for text in seen_texts)


@pytest.mark.asyncio
async def test_retrieval_sdk_confident_local_gap_ignores_same_document_chunks(tmp_path):
    """高置信判断按文档聚合领先差距，同文档多个 chunk 不应阻止快速路径。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Obsidian", "笔记", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(
        kb["id"],
        "笔记/Java/中间件/Zookeeper/知识点/12.Zookeeper实现Master选举.md",
        "# Zookeeper实现Master选举\n## Zookeeper实现Master选举\n## Master选举概述\n临时节点选主",
        "text/markdown",
        "u1",
    )
    ingest.ingest_document(
        kb["id"],
        "笔记/Java/中间件/Kafka/07.Kafka Leader选举过程详解.md",
        "# Kafka Leader选举过程详解\nZooKeeper 版本 Leader 选举",
        "text/markdown",
        "u1",
    )
    sdk = RetrievalSDKService(
        repository,
        es_service=FakeESService(),
        milvus_service=EmptyMilvusService(),
        embedding_service=FakeEmbeddingService(),
        rerank_service=FakeRerankService(),
    )

    result = await sdk.search_with_engines("12 Zookeeper Master 选举", [kb["id"]], top_k=5, request_id="req-test")

    assert result["trace"][1]["metrics"]["engine"] == "sqlite_confident_title"
    assert result["results"][0]["document_name"].endswith("12.Zookeeper实现Master选举.md")


@pytest.mark.asyncio
async def test_retrieval_sdk_falls_back_to_local_chunks_when_engines_return_wrong_kb(tmp_path):
    """引擎返回错知识库结果时，SDK 降级检索当前知识库本地 chunk。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Obsidian", "笔记", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(kb["id"], "redis.md", "# Redis 性能调优\n慢查询和内存优化", "text/markdown", "u1")
    sdk = RetrievalSDKService(
        repository,
        es_service=WrongKnowledgeBaseESService(),
        milvus_service=EmptyMilvusService(),
        embedding_service=FakeEmbeddingService(),
        rerank_service=IdentityRerankService(),
    )

    result = await sdk.search_with_engines("Redis 性能调优", [kb["id"]], top_k=5, request_id="req-test")

    assert result["results"]
    assert {item["knowledge_base_id"] for item in result["results"]} == {kb["id"]}
    assert result["results"][0]["document_name"] == "redis.md"
    assert result["trace"][1]["metrics"]["local_candidates_enabled"] is True


@pytest.mark.asyncio
async def test_retrieval_sdk_promotes_local_title_matches_before_rerank(tmp_path):
    """SDK 将本地标题精确候选并入 rerank 前窗口，避免标题型笔记被语义召回淹没。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Obsidian", "笔记", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(kb["id"], "18.Redis性能调优详解.md", "# Redis性能调优详解\n慢查询和内存优化", "text/markdown", "u1")
    sdk = RetrievalSDKService(
        repository,
        es_service=WeakSameKnowledgeBaseESService(kb["id"]),
        milvus_service=EmptyMilvusService(),
        embedding_service=FakeEmbeddingService(),
        rerank_service=IdentityRerankService(),
    )

    result = await sdk.search_with_engines("Redis 性能调优", [kb["id"]], top_k=5, request_id="req-test")

    assert result["results"][0]["document_name"] == "18.Redis性能调优详解.md"
    assert result["results"][0]["score_trace"]["strategy"] == "local_title_document_name"
    assert result["trace"][1]["metrics"]["engine"] == "sqlite_confident_title"


@pytest.mark.asyncio
async def test_retrieval_sdk_supplies_local_candidate_text_to_rerank(tmp_path):
    """本地候选进入 Rerank 前应填充 description，避免 provider 收到空文档。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Obsidian", "笔记", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(kb["id"], "redis.md", "# Redis 性能调优\n慢查询和内存优化", "text/markdown", "u1")
    rerank = RecordingRerankService()
    sdk = RetrievalSDKService(
        repository,
        es_service=WeakSameKnowledgeBaseESService(kb["id"]),
        milvus_service=EmptyMilvusService(),
        embedding_service=FakeEmbeddingService(),
        rerank_service=rerank,
    )

    await sdk.search_with_engines("慢查询 内存优化", [kb["id"]], top_k=5, request_id="req-test")

    local_candidate = next(item for item in rerank.documents if item["document_name"] == "redis.md")
    assert "慢查询" in local_candidate["description"]


@pytest.mark.asyncio
async def test_retrieval_sdk_keeps_fused_candidates_when_rerank_fails(tmp_path):
    """Rerank 失败时保留已融合候选，避免整条链路降级后丢掉精确标题候选。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Obsidian", "笔记", "u1")
    ingest = DocumentIngestService(repository, MarkdownChunkService(max_chars=120, overlap=20))
    ingest.ingest_document(kb["id"], "18.Redis性能调优详解.md", "# Redis性能调优详解\n慢查询和内存优化", "text/markdown", "u1")
    sdk = RetrievalSDKService(
        repository,
        es_service=WeakSameKnowledgeBaseESService(kb["id"]),
        milvus_service=EmptyMilvusService(),
        embedding_service=FakeEmbeddingService(),
        rerank_service=FailingRerankService(),
    )

    result = await sdk.search_with_engines("慢查询 内存优化", [kb["id"]], top_k=5, request_id="req-test")

    assert result["results"][0]["document_name"] == "18.Redis性能调优详解.md"
    assert result["trace"][1]["metrics"]["engine"] == "es_milvus_fused_rerank_failed"
    assert result["trace"][1]["metrics"]["rerank_failed"] is True
