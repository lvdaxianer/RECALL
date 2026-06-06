"""
ES Service 集成测试

使用真实 ES 进行测试

@author lvdaxianerplus
@date 2026-04-16
"""

import pytest
import asyncio
import socket
from unittest.mock import MagicMock, patch
import httpx
from elastic_transport import ApiResponseMeta, HttpHeaders, NodeConfig
from elasticsearch import UnsupportedProductError
from app.services.es_service import ESService
from app.services.es_index_config import build_index_body_with_ik, build_index_body_without_ik
from app.config import Config


def get_es_service():
    """获取 ES Service 实例，失败时返回 None"""
    try:
        return ESService()
    except Exception:
        return None


def is_es_available():
    """检查 ES 是否可用"""
    service = get_es_service()
    if service is None:
        return False
    try:
        return service.is_connected()
    except Exception:
        return False


def _skip_when_es_unavailable():
    """ES 不可用时跳过真实集成测试"""
    if not _can_connect_es_quickly():
        pytest.skip("ES 服务不可用，跳过集成测试")
    service = get_es_service()
    if service is None:
        pytest.skip("ES 服务不可用，跳过集成测试")
    try:
        if service.is_connected():
            return service
        else:
            pytest.skip("ES 服务不可用，跳过集成测试")
    except Exception:
        pytest.skip("ES 服务不可用，跳过集成测试")


def _can_connect_es_quickly() -> bool:
    """短超时探测 ES 端口，避免集成测试长时间阻塞。"""
    host, port = _es_host_and_port()
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _es_host_and_port() -> tuple[str, int]:
    """解析 ES host 和 port。"""
    host_parts = Config.ES_HOST.split(":", 1)
    if len(host_parts) == 2:
        return host_parts[0], int(host_parts[1])
    else:
        return Config.ES_HOST, 9200


def make_unsupported_product_error():
    """构造 ES 9.x 客户端产品校验失败异常"""
    meta = ApiResponseMeta(
        status=200,
        http_version="1.1",
        headers=HttpHeaders({}),
        duration=0.01,
        node=NodeConfig("http", "localhost", 9200)
    )
    return UnsupportedProductError("unsupported", meta, {})


def test_es_index_mapping_contains_ragflow_compatible_fields():
    """IK 和 standard mapping 都声明 RAGFlow-compatible 富字段"""
    for body in [build_index_body_with_ik(), build_index_body_without_ik()]:
        props = body["mappings"]["properties"]
        assert "title_tks" in props
        assert "important_kwd" in props
        assert "important_tks" in props
        assert "question_tks" in props
        assert "content_ltks" in props
        assert "content_sm_ltks" in props


# 标记为集成测试
pytestmark = pytest.mark.integration


class TestESServiceLanguageDetection:
    """ES 语言检测测试（不需要真实 ES 连接）"""

    @pytest.fixture(autouse=True)
    def mock_es_client(self):
        """避免非集成单测创建真实 ES 客户端"""
        with patch("app.services.es_service.Elasticsearch", autospec=True) as mock_client:
            yield mock_client

    def test_es_client_uses_verify_certs_config(self, mock_es_client, monkeypatch):
        """ES 客户端证书校验开关来自配置"""
        monkeypatch.setattr(Config, "ES_VERIFY_CERTS", True)

        ESService()

        assert mock_es_client.call_args.kwargs["verify_certs"] is True

    def test_is_connected_falls_back_to_http_client_for_unsupported_product(self, mock_es_client):
        """ES 9.x 客户端遇到 ES 7.10 兼容服务时降级到 HTTP 客户端"""
        mock_client = mock_es_client.return_value
        mock_client.ping.return_value = False
        mock_client.info.side_effect = make_unsupported_product_error()

        with patch("app.services.es_service.ESHttpCompatClient") as http_client:
            http_client.return_value.ping.return_value = True

            service = ESService()
            assert service.is_connected() is True
            assert service.client is http_client.return_value

    @pytest.mark.asyncio
    async def test_search_ensures_http_compat_client_before_request(self, mock_es_client):
        """搜索前自动确认 ES 兼容客户端，避免遗漏 is_connected 调用"""
        mock_client = mock_es_client.return_value
        mock_client.ping.return_value = False
        mock_client.info.side_effect = make_unsupported_product_error()

        with patch("app.services.es_service.ESHttpCompatClient") as http_client:
            http_client.return_value.ping.return_value = True
            http_client.return_value.search.return_value = {"hits": {"hits": []}}

            service = ESService()
            result = await service.search("rag_skills", "默认规则", 5)

            assert result == []
            assert service.client is http_client.return_value
            http_client.return_value.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_filters_by_metadata_type(self):
        """搜索支持按 metadata.type 过滤，避免跨类型和历史评测数据污染召回"""
        service = ESService()
        service.client.search = MagicMock(return_value={"hits": {"hits": []}})

        await service.search("rag_skills", "证照材料", 5, metadata_filter={"type": "skill"})

        body = service.client.search.call_args.kwargs["body"]
        assert body["query"] == {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": "证照材料",
                        "fields": ["description", "description_en"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                },
                "filter": [
                    {"term": {"metadata.type.keyword": "skill"}}
                ]
            }
        }

    @pytest.mark.asyncio
    async def test_search_filters_boolean_metadata_without_keyword_suffix(self):
        """布尔 metadata 过滤使用原字段，支持 summary-first 的 is_summary filter"""
        service = ESService()
        service.client.search = MagicMock(return_value={"hits": {"hits": []}})

        await service.search(
            "rag_assets",
            "项目整体架构",
            5,
            metadata_filter={"is_summary": True, "summary_type": "document"},
        )

        filters = service.client.search.call_args.kwargs["body"]["query"]["bool"]["filter"]
        assert {"term": {"metadata.is_summary": True}} in filters
        assert {"term": {"metadata.summary_type.keyword": "document"}} in filters

    @pytest.mark.asyncio
    async def test_search_filters_knowledge_base_metadata(self):
        """搜索支持按 knowledge_base_id 和 document_id 过滤。"""
        service = ESService()
        service.client.search = MagicMock(return_value={"hits": {"hits": []}})

        await service.search(
            "rag_assets",
            "检索 SDK",
            5,
            metadata_filter={"knowledge_base_id": "kb-001", "document_id": "doc-001"},
        )

        filters = service.client.search.call_args.kwargs["body"]["query"]["bool"]["filter"]
        assert {"term": {"metadata.knowledge_base_id.keyword": "kb-001"}} in filters
        assert {"term": {"metadata.document_id.keyword": "doc-001"}} in filters

    @pytest.mark.asyncio
    async def test_search_weighted_uses_ragflow_query_builder(self):
        """weighted search 使用 RAGFlow-inspired query body 并保留文本原始分"""
        service = ESService()
        captured = {}

        class FakeClient:
            def search(self, index, body):
                captured["index"] = index
                captured["body"] = body
                return {
                    "hits": {
                        "hits": [
                            {
                                "_id": "skill-white-screen",
                                "_score": 12.3,
                                "_source": {
                                    "description": "小程序上线后白屏",
                                    "metadata": {"type": "skill", "id": "skill-white-screen"},
                                    "features": {"tags": ["小程序"]},
                                },
                            }
                        ]
                    }
                }

            def ping(self):
                return True

        service.client = FakeClient()
        service._connected = True

        results = await service.search_weighted(
            index_name="rag_skills",
            query="小程序（上线后）白屏",
            top_k=5,
            metadata_filter={"type": "skill"},
        )

        assert captured["index"] == "rag_skills"
        assert captured["body"]["size"] == 5
        assert captured["body"]["query"]["bool"]["should"][0]["multi_match"]["query"] == "小程序 上线后 白屏"
        assert results[0]["score"] == 12.3
        assert results[0]["source_scores"]["text"] == 12.3

    @pytest.mark.asyncio
    async def test_search_parent_contexts_batches_parent_and_section_filters(self):
        """父/章节上下文查询使用 terms 批量过滤，避免按候选逐条请求 ES"""
        service = ESService()
        captured = {}

        class FakeClient:
            def search(self, index, body):
                captured["index"] = index
                captured["body"] = body
                return {
                    "hits": {
                        "hits": [
                            {
                                "_id": "chunk-parent",
                                "_score": 1.0,
                                "_source": {
                                    "description": "父章节说明",
                                    "metadata": {
                                        "type": "asset",
                                        "id": "chunk-parent",
                                        "parent_id": "doc-1",
                                        "section_id": "section-1",
                                        "section_title": "检索架构",
                                    },
                                    "features": {"tags": ["架构"]},
                                },
                            }
                        ]
                    }
                }

            def ping(self):
                return True

        service.client = FakeClient()

        results = await service.search_parent_contexts(
            index_name="rag_assets",
            parent_ids=["doc-1", "doc-2"],
            section_ids=["section-1"],
            limit=8,
        )

        assert captured["index"] == "rag_assets"
        assert captured["body"] == {
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {"metadata.parent_id.keyword": ["doc-1", "doc-2"]}},
                        {"terms": {"metadata.section_id.keyword": ["section-1"]}},
                    ]
                }
            },
            "size": 8,
        }
        assert results == [
            {
                "id": "chunk-parent",
                "score": 1.0,
                "description": "父章节说明",
                "metadata": {
                    "type": "asset",
                    "id": "chunk-parent",
                    "parent_id": "doc-1",
                    "section_id": "section-1",
                    "section_title": "检索架构",
                },
                "features": {"tags": ["架构"]},
            }
        ]

    def test_detect_chinese(self):
        """测试中文检测"""
        service = ESService()
        assert service._contains_chinese("Pinia 是 Vue 的状态管理库")
        assert service._contains_chinese("你好世界")
        assert service._contains_chinese("状态管理")

    def test_detect_english_only(self):
        """测试纯英文检测"""
        service = ESService()
        assert not service._contains_chinese("Pinia is Vue's state management")
        assert not service._contains_chinese("Hello World")

    def test_detect_mixed(self):
        """测试中英混合"""
        service = ESService()
        assert service._contains_chinese("Pinia 状态管理")
        assert service._contains_chinese("Vue3状态管理")

    def test_detect_language(self):
        """测试语言检测"""
        service = ESService()
        assert service._detect_language("Pinia 是 Vue 的状态管理库") == "zh"
        assert service._detect_language("Pinia is Vue's state management") == "en"

    def test_build_document_body_includes_ragflow_compatible_fields(self):
        """ES 文档体写入 RAGFlow-compatible 富字段，支持后续字段加权检索"""
        service = ESService()
        body = service._build_document_body(
            doc_id="skill-white-screen",
            description="小程序上线后白屏 本地开发正常",
            metadata={"type": "skill", "id": "skill-white-screen", "description": "小程序白屏排查"},
            features={
                "category": "小程序故障",
                "tags": ["小程序", "白屏", "生产环境"],
                "questions": ["小程序上线后为什么白屏"],
                "title": "小程序白屏排查",
            },
        )

        assert body["title_tks"] == "小程序白屏排查"
        assert body["important_kwd"] == ["小程序故障", "小程序", "白屏", "生产环境"]
        assert body["important_tks"] == "小程序故障 小程序 白屏 生产环境"
        assert body["question_tks"] == "小程序上线后为什么白屏"
        assert body["content_ltks"] == "小程序上线后白屏 本地开发正常"
        assert body["content_sm_ltks"] == "小程序上线后白屏 本地开发正常"

    def test_build_document_body_preserves_parent_and_section_metadata(self):
        """ES 文档体保留父文档和章节字段，供后续父子 chunk 扩展使用"""
        service = ESService()
        body = service._build_document_body(
            doc_id="chunk-1",
            description="支付失败排查正文",
            metadata={
                "type": "asset",
                "id": "chunk-1",
                "description": "支付失败",
                "parent_id": "doc-1",
                "section_title": "支付问题",
            },
            features={},
        )

        assert body["parent_id"] == "doc-1"
        assert body["section_title"] == "支付问题"

    def test_build_document_body_preserves_knowledge_base_metadata(self):
        """ES 文档体保留知识库过滤元数据。"""
        service = ESService()
        body = service._build_document_body(
            doc_id="chunk-001",
            description="检索 SDK 文档",
            metadata={
                "type": "knowledge_chunk",
                "id": "chunk-001",
                "knowledge_base_id": "kb-001",
                "document_id": "doc-001",
                "chunk_index": 0,
            },
        )

        assert body["metadata"]["knowledge_base_id"] == "kb-001"
        assert body["metadata"]["document_id"] == "doc-001"

    @pytest.mark.asyncio
    async def test_index_documents_uses_bulk_api(self):
        """测试批量索引 helper 使用 ES bulk API"""
        service = ESService()
        documents = [
            {
                "doc_id": "doc-1",
                "description": "登录功能",
                "metadata": {"type": "skill"},
                "features": {"category": "功能", "tags": ["登录"]}
            },
            {
                "doc_id": "doc-2",
                "description": "注册功能",
                "metadata": {"type": "skill"},
                "features": {"category": "功能", "tags": ["注册"]}
            }
        ]

        with patch("elasticsearch.helpers.bulk", return_value=(2, [])) as bulk_mock:
            result = await service.index_documents("rag_skills", documents)

        assert result == 2
        bulk_mock.assert_called_once()
        actions = list(bulk_mock.call_args.args[1])
        assert [(action["_id"], action["_index"], action["_op_type"]) for action in actions] == [
            ("doc-1", "rag_skills", "index"),
            ("doc-2", "rag_skills", "index"),
        ]
        assert actions[0]["_source"] | {
            "id": "doc-1",
            "description": "登录功能",
            "lang": "zh",
            "metadata": {"type": "skill"},
            "features": {"category": "功能", "tags": ["登录"]},
        } == actions[0]["_source"]
        assert actions[1]["_source"] | {
            "id": "doc-2",
            "description": "注册功能",
            "lang": "zh",
            "metadata": {"type": "skill"},
            "features": {"category": "功能", "tags": ["注册"]},
        } == actions[1]["_source"]

    @pytest.mark.asyncio
    async def test_index_documents_uses_loop_with_http_compat_client(self):
        """HTTP 兼容客户端不走官方 helpers.bulk，逐条写入"""
        service = ESService()
        service.client = MagicMock()
        service._using_http_compat = True
        documents = [
            {
                "doc_id": "doc-1",
                "description": "登录功能",
                "metadata": {"type": "skill"}
            },
            {
                "doc_id": "doc-2",
                "description": "注册功能",
                "metadata": {"type": "skill"}
            }
        ]

        with patch("elasticsearch.helpers.bulk") as bulk_mock:
            result = await service.index_documents("rag_skills", documents)

        assert result == 2
        bulk_mock.assert_not_called()
        assert service.client.index.call_count == 2

    @pytest.mark.asyncio
    async def test_create_index_falls_back_when_ik_synonym_mapping_fails(self):
        """IK 可用但同义词配置不可用时降级创建 standard 索引"""
        service = ESService()
        service.client = MagicMock()
        service.client.indices.exists.return_value = False
        service.client.indices.analyze.return_value = {"tokens": [{"token": "测试"}]}
        request = httpx.Request("PUT", "http://es/rag_skills")
        response = httpx.Response(400, request=request, json={"error": "synonyms.txt missing"})
        service.client.indices.create.side_effect = [
            httpx.HTTPStatusError("bad mapping", request=request, response=response),
            {"acknowledged": True}
        ]

        await service.create_index_if_not_exists("rag_skills")

        assert service.client.indices.create.call_count == 2
        fallback_body = service.client.indices.create.call_args.kwargs["body"]
        assert fallback_body["settings"]["index"]["max_ngram_diff"] == 2
        assert fallback_body["mappings"]["properties"]["description"]["analyzer"] == "default"

    @pytest.mark.asyncio
    async def test_list_documents_returns_normalized_documents(self):
        """测试列出文档时统一 description/metadata/features 结构"""
        service = ESService()
        service.client = MagicMock()
        service.client.search = MagicMock(return_value={
            "hits": {
                "hits": [
                    {
                        "_id": "doc-1",
                        "_source": {
                            "description": "JWT 登录认证能力",
                            "metadata": {"type": "skill", "id": "doc-1"},
                            "features": {"entities": [{"name": "JWT"}], "relations": []}
                        }
                    },
                    {
                        "_id": "doc-2",
                        "_source": {
                            "description_en": "Login asset",
                            "metadata": {"type": "asset", "id": "doc-2"}
                        }
                    }
                ]
            }
        })

        result = await service.list_documents("rag_skills", limit=10)

        assert result == [
            {
                "id": "doc-1",
                "description": "JWT 登录认证能力",
                "metadata": {"type": "skill", "id": "doc-1"},
                "features": {"entities": [{"name": "JWT"}], "relations": []}
            },
            {
                "id": "doc-2",
                "description": "Login asset",
                "metadata": {"type": "asset", "id": "doc-2"},
                "features": {}
            }
        ]
        service.client.search.assert_called_once()


class TestESServiceIntegration:
    """ES 集成测试（需要真实 ES）"""

    @pytest.fixture
    def service(self):
        """获取 ES Service 实例"""
        return _skip_when_es_unavailable()

    @pytest.fixture
    def index_name(self):
        """测试索引名称"""
        return "test_rag_hybrid_search"

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, service, index_name):
        """每个测试前创建索引，测试后删除"""
        # 清理可能存在的旧索引
        try:
            service.client.indices.delete(index=index_name, ignore=[404])
        except Exception:
            pass
        yield
        # 清理测试索引
        try:
            service.client.indices.delete(index=index_name, ignore=[404])
        except Exception:
            pass

    def test_create_index(self, service, index_name):
        """测试创建索引"""
        async def run_test():
            await service.create_index_if_not_exists(index_name)
            assert service.client.indices.exists(index=index_name)

        asyncio.run(run_test())

    def test_index_and_search_chinese_doc(self, service, index_name):
        """测试索引中文文档并搜索"""

        async def run_test():
            # 1. 创建索引
            await service.create_index_if_not_exists(index_name)

            # 2. 索引文档
            await service.index_document(
                index_name=index_name,
                doc_id="doc_001",
                description="Pinia 是 Vue 的状态管理库",
                metadata={"type": "skill"},
                lang="zh"
            )
            service.client.indices.refresh(index=index_name)

            # 3. 搜索
            results = await service.search(
                index_name=index_name,
                query="Pinia",
                top_k=5,
                query_lang="auto"
            )

            # 4. 验证
            assert len(results) > 0
            assert results[0]["id"] == "doc_001"

            # 5. 验证描述字段存在
            assert "description" in results[0]

        asyncio.run(run_test())

    def test_index_and_search_multiple_docs(self, service, index_name):
        """测试索引多个文档并搜索"""

        async def run_test():
            # 1. 创建索引
            await service.create_index_if_not_exists(index_name)

            # 2. 索引多个文档
            docs = [
                ("doc_001", "Pinia 是 Vue3 推荐的状态管理库", "zh"),
                ("doc_002", "Vuex 是 Vue2 使用的状态管理库", "zh"),
                ("doc_003", "API 接口文档管理系统", "zh"),
                ("doc_004", "React Hooks 状态管理", "zh"),
            ]

            for doc_id, desc, lang in docs:
                await service.index_document(
                    index_name=index_name,
                    doc_id=doc_id,
                    description=desc,
                    metadata={"type": "skill"},
                    lang=lang
                )

            service.client.indices.refresh(index=index_name)

            # 3. 搜索状态管理
            results = await service.search(
                index_name=index_name,
                query="状态管理",
                top_k=5,
                query_lang="auto"
            )

            # 4. 验证
            assert len(results) >= 2  # 应该返回多个结果

        asyncio.run(run_test())

    def test_delete_document(self, service, index_name):
        """测试删除文档"""

        async def run_test():
            # 1. 创建索引并插入文档
            await service.create_index_if_not_exists(index_name)
            await service.index_document(
                index_name=index_name,
                doc_id="doc_to_delete",
                description="将被删除的文档",
                metadata={"type": "test"},
                lang="zh"
            )
            service.client.indices.refresh(index=index_name)

            # 2. 验证文档存在
            assert service.client.exists(index=index_name, id="doc_to_delete")

            # 3. 删除文档
            success = await service.delete_document(index_name, "doc_to_delete")
            assert success is True

            # 4. 刷新并验证文档不存在
            service.client.indices.refresh(index=index_name)
            assert not service.client.exists(index=index_name, id="doc_to_delete")

        asyncio.run(run_test())

    def test_search_with_top_k(self, service, index_name):
        """测试 top_k 参数"""

        async def run_test():
            # 1. 创建索引并插入文档
            await service.create_index_if_not_exists(index_name)
            for i in range(10):
                await service.index_document(
                    index_name=index_name,
                    doc_id=f"doc_{i}",
                    description=f"测试文档 {i}",
                    metadata={"type": "test"},
                    lang="zh"
                )
            service.client.indices.refresh(index=index_name)

            # 2. 限制返回数量
            results = await service.search(
                index_name=index_name,
                query="测试",
                top_k=3,
                query_lang="auto"
            )

            # 3. 验证
            assert len(results) <= 3

        asyncio.run(run_test())


class TestESServiceEndToEnd:
    """端到端测试"""

    @pytest.fixture
    def service(self):
        return _skip_when_es_unavailable()

    @pytest.fixture
    def index_name(self):
        return "test_e2e"

    def test_full_workflow(self, service, index_name):
        """完整工作流：创建索引 -> 插入 -> 搜索 -> 删除"""

        async def run_test():
            # 清理
            try:
                service.client.indices.delete(index=index_name, ignore=[404])
            except Exception:
                pass

            # 1. 创建索引
            await service.create_index_if_not_exists(index_name)
            assert service.client.indices.exists(index=index_name)

            # 2. 插入数据
            test_data = [
                ("skill_001", "Pinia 是 Vue3 的状态管理库", "skill", "zh"),
                ("skill_002", "Vuex 是 Vue2 的状态管理库", "skill", "zh"),
                ("skill_003", "React Hooks 用于状态管理", "skill", "zh"),
            ]

            for doc_id, desc, doc_type, lang in test_data:
                await service.index_document(
                    index_name=index_name,
                    doc_id=doc_id,
                    description=desc,
                    metadata={"type": doc_type},
                    lang=lang
                )

            service.client.indices.refresh(index=index_name)

            # 3. 搜索 Pinia
            results = await service.search(
                index_name=index_name,
                query="Pinia",
                top_k=5,
                query_lang="auto"
            )
            assert len(results) > 0
            assert any("Pinia" in r.get("description", "") for r in results)

            # 4. 清理
            service.client.indices.delete(index=index_name)

        asyncio.run(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
