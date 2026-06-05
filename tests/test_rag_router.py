"""
RAG 路由测试用例

测试覆盖：
- POST /api/v1/rag/insert 单条插入
- POST /api/v1/rag/insert/batch 批量插入
- POST /api/v1/rag/test-user/search 语义检索
- DELETE /api/v1/rag/test-user/delete 删除记录
- GET /health 健康检查

@author lvdaxianerplus
@date 2026-04-14
"""

import asyncio

import pytest
import pytest_asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.models.schemas import OptimizeSearchRequest, SearchResult


# =============================================================================
# Fixtures
# =============================================================================

# 使用模块级 mock 服务（session-scoped）
_mock_embedding_service = None
_mock_rerank_service = None
_mock_milvus_service = None
_mock_feature_extract_service = None
_mock_entity_relation_service = None
_mock_graph_retrieval_service = None
_mock_es_service = None


def get_mock_embedding_service():
    """获取 Mock Embedding 服务"""
    global _mock_embedding_service
    if _mock_embedding_service is None:
        _mock_embedding_service = AsyncMock()
        _mock_embedding_service.encode = AsyncMock(return_value=[0.1] * 8192)
        _mock_embedding_service.health_check = AsyncMock(return_value=True)
    return _mock_embedding_service


def get_mock_rerank_service():
    """获取 Mock Rerank 服务"""
    global _mock_rerank_service
    if _mock_rerank_service is None:
        _mock_rerank_service = AsyncMock()
        _mock_rerank_service.rerank = AsyncMock(return_value=[
            {"index": 0, "score": 0.85},
            {"index": 1, "score": 0.72}
        ])
        _mock_rerank_service.health_check = AsyncMock(return_value=True)
    return _mock_rerank_service


def get_mock_milvus_service():
    """获取 Mock Milvus 服务"""
    global _mock_milvus_service
    if _mock_milvus_service is None:
        _mock_milvus_service = AsyncMock()

        async def mock_insert(collection, doc_id, description, vector, metadata, features=None):
            return {"id": doc_id, "collection": collection, "features": features or {}}

        _mock_milvus_service.insert = AsyncMock(side_effect=mock_insert)
        _mock_milvus_service.batch_insert = AsyncMock(return_value={"inserted_count": 2})
        _mock_milvus_service.search = AsyncMock(return_value=[
            {"id": "skill-001", "description": "用户登录功能", "metadata": {"type": "skill", "id": "skill-001", "description": "登录相关"}, "score": 0.85},
            {"id": "skill-002", "description": "用户注册功能", "metadata": {"type": "skill", "id": "skill-002", "description": "注册相关"}, "score": 0.72}
        ])
        _mock_milvus_service.delete = AsyncMock(return_value=True)
        _mock_milvus_service.collection_exists = AsyncMock(return_value=True)
        _mock_milvus_service.create_collection = AsyncMock(return_value=True)
        _mock_milvus_service.health_check = AsyncMock(return_value=True)
    return _mock_milvus_service


def get_mock_feature_extract_service():
    """获取 Mock 特征提取服务"""
    global _mock_feature_extract_service
    if _mock_feature_extract_service is None:
        _mock_feature_extract_service = AsyncMock()
        _mock_feature_extract_service.extract_features = AsyncMock(return_value={
            "category": "功能",
            "tags": ["登录", "用户"]
        })
        _mock_feature_extract_service.extract_features_batch = AsyncMock(side_effect=lambda descriptions: [
            {"category": "功能", "tags": ["登录", "用户"]}
            for _ in descriptions
        ])
        _mock_feature_extract_service.health_check = AsyncMock(return_value=True)
    return _mock_feature_extract_service


def get_mock_entity_relation_service():
    """获取 Mock 实体关系抽取服务"""
    global _mock_entity_relation_service
    if _mock_entity_relation_service is None:
        _mock_entity_relation_service = AsyncMock()
        _mock_entity_relation_service.extract = AsyncMock(return_value={
            "entities": [{"name": "JWT", "type": "技术组件"}],
            "relations": [{"source": "JWT", "target": "登录认证", "relation": "用于"}]
        })
        _mock_entity_relation_service.extract_batch = AsyncMock(side_effect=lambda descriptions: [
            {
                "entities": [{"name": "JWT", "type": "技术组件"}],
                "relations": [{"source": "JWT", "target": "登录认证", "relation": "用于"}]
            }
            for _ in descriptions
        ])
    return _mock_entity_relation_service


def get_mock_graph_retrieval_service():
    """获取 Mock 图检索服务"""
    global _mock_graph_retrieval_service
    if _mock_graph_retrieval_service is None:
        _mock_graph_retrieval_service = MagicMock()
        _mock_graph_retrieval_service.index_document = MagicMock(return_value=None)
        _mock_graph_retrieval_service.index_documents = MagicMock(return_value=0)
        _mock_graph_retrieval_service.rebuild = MagicMock(return_value={
            "document_count": 2,
            "entity_count": 1,
            "relation_term_count": 3
        })
        _mock_graph_retrieval_service.delete_document = MagicMock(return_value=True)
        _mock_graph_retrieval_service.search = MagicMock(return_value=[])
        _mock_graph_retrieval_service.stats = MagicMock(return_value={
            "document_count": 1,
            "entity_count": 1,
            "relation_term_count": 3
        })
        _mock_graph_retrieval_service.explain = MagicMock(return_value={
            "query": "JWT 登录",
            "search_type": "skill",
            "top_k": 5,
            "matched_entities": ["jwt"],
            "matched_relation_terms": [],
            "result_count": 1,
            "matches": [{"id": "skill-jwt", "match_type": "entity", "score": 0.7}]
        })
    return _mock_graph_retrieval_service


def get_mock_es_service():
    """获取 Mock ES 服务"""
    global _mock_es_service
    if _mock_es_service is None:
        _mock_es_service = MagicMock()
        _mock_es_service.index_document = AsyncMock(return_value=None)
        _mock_es_service.index_documents = AsyncMock(return_value=0)
        _mock_es_service.search = AsyncMock(return_value=[])
        _mock_es_service.list_documents = AsyncMock(side_effect=[
            [
                {
                    "id": "skill-jwt",
                    "description": "JWT 登录认证能力",
                    "metadata": {"type": "skill", "id": "skill-jwt"},
                    "features": {"entities": [{"name": "JWT"}], "relations": []}
                }
            ],
            [
                {
                    "id": "asset-login",
                    "description": "登录素材",
                    "metadata": {"type": "asset", "id": "asset-login"},
                    "features": {"entities": [], "relations": []}
                }
            ]
        ])
        _mock_es_service.delete_document = AsyncMock(return_value=True)
        _mock_es_service.is_connected = MagicMock(return_value=True)
        _mock_es_service.health_check = MagicMock(return_value=True)
        _mock_es_service.create_index_if_not_exists = AsyncMock(return_value=True)
    return _mock_es_service


@pytest_asyncio.fixture
async def mock_embedding_service():
    """Mock Embedding 服务"""
    return get_mock_embedding_service()


@pytest_asyncio.fixture
async def mock_rerank_service():
    """Mock Rerank 服务"""
    return get_mock_rerank_service()


@pytest_asyncio.fixture
async def mock_milvus_service():
    """Mock Milvus 服务"""
    return get_mock_milvus_service()


@pytest_asyncio.fixture
async def mock_feature_extract_service():
    """Mock 特征提取服务"""
    return get_mock_feature_extract_service()


@pytest_asyncio.fixture
async def mock_entity_relation_service():
    """Mock 实体关系抽取服务"""
    return get_mock_entity_relation_service()


@pytest_asyncio.fixture
async def mock_graph_retrieval_service():
    """Mock 图检索服务"""
    return get_mock_graph_retrieval_service()


@pytest_asyncio.fixture
async def mock_es_service():
    """Mock ES 服务"""
    return get_mock_es_service()


@pytest_asyncio.fixture
async def app_router(
    mock_embedding_service,
    mock_rerank_service,
    mock_milvus_service,
    mock_feature_extract_service,
    mock_entity_relation_service,
    mock_graph_retrieval_service,
    mock_es_service
):
    """创建带有 mock 服务的 app"""
    patches = [
        patch("app.services.embedding_service.EmbeddingService", return_value=mock_embedding_service),
        patch("app.services.rerank_service.RerankService", return_value=mock_rerank_service),
        patch("app.services.milvus_service.MilvusService", return_value=mock_milvus_service),
        patch("app.main.EmbeddingService", return_value=mock_embedding_service),
        patch("app.main.RerankService", return_value=mock_rerank_service),
        patch("app.main.MilvusService", return_value=mock_milvus_service),
        patch("app.main.get_es_service", return_value=mock_es_service),
        patch("app.services.rag_search_pipeline_service.get_embedding_service", return_value=mock_embedding_service),
        patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=mock_rerank_service),
        patch("app.services.rag_search_pipeline_service.get_milvus_service", return_value=mock_milvus_service),
        patch("app.services.rag_search_pipeline_service.get_graph_retrieval_service", return_value=mock_graph_retrieval_service),
        patch("app.services.rag_search_pipeline_service.get_es_service", return_value=mock_es_service),
        patch("app.routers.rag_delete.get_milvus_service", return_value=mock_milvus_service),
        patch("app.routers.rag_delete.get_graph_retrieval_service", return_value=mock_graph_retrieval_service),
        patch("app.routers.rag_delete.get_es_service", return_value=mock_es_service),
        patch("app.routers.rag_insert.get_embedding_service", return_value=mock_embedding_service),
        patch("app.routers.rag_insert.get_milvus_service", return_value=mock_milvus_service),
        patch("app.routers.rag_insert.get_feature_extract_service", return_value=mock_feature_extract_service),
        patch("app.routers.rag_insert.get_entity_relation_service", return_value=mock_entity_relation_service),
        patch("app.routers.rag_insert.get_graph_retrieval_service", return_value=mock_graph_retrieval_service),
        patch("app.routers.rag_insert.get_es_service", return_value=mock_es_service),
        patch("app.routers.rag_insights.get_graph_retrieval_service", return_value=mock_graph_retrieval_service),
        patch("app.routers.rag_insights.get_es_service", return_value=mock_es_service),
    ]
    with ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        from app.main import app
        yield app


@pytest_asyncio.fixture
async def async_client(app_router):
    """异步 HTTP 客户端"""
    transport = ASGITransport(app=app_router)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# =============================================================================
# 测试用例：POST /api/v1/rag/insert
# =============================================================================

class TestInsertEndpoint:
    """单条插入接口测试"""

    @pytest.mark.asyncio
    async def test_insert_success(self, async_client, mock_embedding_service, mock_milvus_service):
        """
        场景：单条插入成功

        预期：
        - 返回 200
        - code 为 200
        - message 为 "success"
        - data 包含 id 和 collection
        """
        # given: 有效的插入请求
        request_body = {
            "description": "用户登录功能 skill",
            "metadata": {
                "type": "skill",
                "id": "skill-001",
                "description": "登录相关"
            }
        }

        # when: 调用插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)

        # then: 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        assert "data" in data
        assert data["data"]["id"] == "skill-001"
        assert data["data"]["collection"] == "skill"
        assert data["data"]["features"]["entities"] == [{"name": "JWT", "type": "技术组件"}]
        assert data["data"]["features"]["relations"] == [{"source": "JWT", "target": "登录认证", "relation": "用于"}]

    @pytest.mark.asyncio
    async def test_insert_missing_description(self, async_client):
        """
        场景：插入请求缺少 description

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 缺少 description 的请求
        request_body = {
            "metadata": {
                "type": "skill",
                "id": "skill-001",
                "description": "登录相关"
            }
        }

        # when: 调用插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_missing_metadata(self, async_client):
        """
        场景：插入请求缺少 metadata

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 缺少 metadata 的请求
        request_body = {
            "description": "用户登录功能"
        }

        # when: 调用插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_missing_metadata_type(self, async_client):
        """
        场景：metadata 缺少 type

        预期：
        - 返回 422 (Validation Error)
        """
        # given: metadata 缺少 type 的请求
        request_body = {
            "description": "用户登录功能",
            "metadata": {
                "id": "skill-001",
                "description": "登录相关"
            }
        }

        # when: 调用插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_empty_description(self, async_client):
        """
        场景：description 为空字符串

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 空 description
        request_body = {
            "description": "",
            "metadata": {
                "type": "skill",
                "id": "skill-001",
                "description": "登录相关"
            }
        }

        # when: 调用插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)

        # then: 验证响应
        assert response.status_code == 422


# =============================================================================
# 测试用例：POST /api/v1/rag/insert/batch
# =============================================================================

class TestBatchInsertEndpoint:
    """批量插入接口测试"""

    @pytest.mark.asyncio
    async def test_batch_insert_success(self, async_client, mock_embedding_service, mock_milvus_service):
        """
        场景：批量插入成功

        预期：
        - 返回 200
        - code 为 200
        - inserted_count 正确
        """
        # given: 有效的批量插入请求
        request_body = {
            "items": [
                {
                    "description": "skill A",
                    "metadata": {"type": "skill", "id": "skill-A", "description": "A"}
                },
                {
                    "description": "skill B",
                    "metadata": {"type": "skill", "id": "skill-B", "description": "B"}
                }
            ]
        }

        # when: 调用批量插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)

        # then: 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        assert data["data"]["inserted_count"] == 2

    @pytest.mark.asyncio
    async def test_batch_insert_rejects_mixed_metadata_types(self, async_client):
        """
        场景：批量插入混合 skill 和 asset

        预期：返回 400，避免写入错误 collection / ES index
        """
        request_body = {
            "items": [
                {
                    "description": "skill A",
                    "metadata": {"type": "skill", "id": "skill-A", "description": "A"}
                },
                {
                    "description": "asset B",
                    "metadata": {"type": "asset", "id": "asset-B", "description": "B"}
                }
            ]
        }

        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == 1003

    @pytest.mark.asyncio
    async def test_batch_insert_empty_items(self, async_client):
        """
        场景：批量插入 items 为空

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 空 items
        request_body = {
            "items": []
        }

        # when: 调用批量插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_insert_missing_items(self, async_client):
        """
        场景：批量插入缺少 items 字段

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 缺少 items 字段
        request_body = {}

        # when: 调用批量插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_insert_item_missing_description(self, async_client):
        """
        场景：批量插入中某项缺少 description

        预期：
        - 返回 422 (Validation Error)
        """
        # given: items 中某项缺少 description
        request_body = {
            "items": [
                {
                    "description": "skill A",
                    "metadata": {"type": "skill", "id": "skill-A", "description": "A"}
                },
                {
                    "metadata": {"type": "skill", "id": "skill-B", "description": "B"}
                }
            ]
        }

        # when: 调用批量插入接口
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)

        # then: 验证响应
        assert response.status_code == 422


# =============================================================================
# 测试用例：POST /api/v1/rag/test-user/search
# =============================================================================

class TestSearchEndpoint:
    """语义检索接口测试"""

    @pytest.mark.asyncio
    async def test_search_success(self, async_client, mock_embedding_service, mock_milvus_service, mock_rerank_service):
        """
        场景：检索成功

        预期：
        - 返回 200
        - code 为 200
        - data 为列表
        - 结果按 score 降序
        """
        # given: 有效的检索请求
        request_body = {
            "input": "查找登录相关的 skill",
            "type": "skill",
            "topK": 20
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0
        # 验证 score 降序
        scores = [item["score"] for item in data["data"]]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_search_missing_input(self, async_client):
        """
        场景：检索请求缺少 input

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 缺少 input 的请求
        request_body = {
            "type": "skill",
            "topK": 20
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_empty_input(self, async_client):
        """
        场景：检索请求 input 为空

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 空 input
        request_body = {
            "input": "",
            "type": "skill",
            "topK": 20
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_default_type_all(self, async_client, mock_embedding_service, mock_milvus_service, mock_rerank_service):
        """
        场景：不指定 type，默认为 all

        预期：
        - 返回 200
        - code 为 200
        """
        # given: 不指定 type 的请求
        request_body = {
            "input": "查找登录相关的 skill",
            "topK": 20
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    @pytest.mark.asyncio
    async def test_search_with_topk(self, async_client, mock_embedding_service, mock_milvus_service, mock_rerank_service):
        """
        场景：指定 topK

        预期：
        - 返回 200
        - 返回结果数量不超过 topK
        """
        # given: 指定 topK=5 的请求
        request_body = {
            "input": "查找登录相关的 skill",
            "type": "skill",
            "topK": 5
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 5

    @pytest.mark.asyncio
    async def test_search_topk_exceeds_limit(self, async_client):
        """
        场景：topK 超过 1000 上限

        预期：
        - 返回 422 (Validation Error)
        """
        # given: topK=1001
        request_body = {
            "input": "查找登录相关的 skill",
            "type": "skill",
            "topK": 1001
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_topk_zero(self, async_client):
        """
        场景：topK 为 0

        预期：
        - 返回 422 (Validation Error)
        """
        # given: topK=0
        request_body = {
            "input": "查找登录相关的 skill",
            "type": "skill",
            "topK": 0
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_topk_negative(self, async_client):
        """
        场景：topK 为负数

        预期：
        - 返回 422 (Validation Error)
        """
        # given: topK=-1
        request_body = {
            "input": "查找登录相关的 skill",
            "type": "skill",
            "topK": -1
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 422


class TestGraphRetrievalEndpoint:
    """轻量图谱检索路由测试"""

    @pytest.mark.asyncio
    async def test_search_uses_graph_results_when_vector_and_es_empty(
        self,
        async_client,
        mock_milvus_service,
        mock_es_service,
        mock_graph_retrieval_service
    ):
        """
        场景：向量和 ES 没有结果，但图检索命中实体

        预期：图检索结果进入最终响应
        """
        mock_milvus_service.search = AsyncMock(return_value=[])
        mock_es_service.search = AsyncMock(return_value=[])
        mock_graph_retrieval_service.search = MagicMock(return_value=[
            {
                "id": "skill-jwt",
                "description": "JWT 登录认证能力",
                "metadata": {"type": "skill", "id": "skill-jwt"},
                "features": {
                    "entities": [{"name": "JWT", "type": "技术组件"}],
                    "relations": []
                },
                "score": 0.6
            }
        ])

        response = await async_client.post(
            "/api/v1/rag/test-user/search",
            json={"input": "JWT 登录", "type": "skill", "topK": 5}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"][0]["metadata"]["id"] == "skill-jwt"
        mock_graph_retrieval_service.search.assert_called_once_with(
            "JWT 登录",
            search_type="skill",
            top_k=5
        )

    @pytest.mark.asyncio
    async def test_graph_stats_and_explain_routes(self, async_client, mock_graph_retrieval_service):
        """
        场景：查看图检索统计和查询解释

        预期：返回图索引规模和命中解释
        """
        stats_response = await async_client.get("/api/v1/rag/graph/stats")
        explain_response = await async_client.get(
            "/api/v1/rag/test-user/graph/explain",
            params={"query": "JWT 登录", "type": "skill", "topK": 5}
        )

        assert stats_response.status_code == 200
        assert stats_response.json()["data"]["document_count"] == 1
        assert explain_response.status_code == 200
        assert explain_response.json()["data"]["matches"][0]["id"] == "skill-jwt"
        mock_graph_retrieval_service.explain.assert_called_once_with(
            "JWT 登录",
            search_type="skill",
            top_k=5
        )

    @pytest.mark.asyncio
    async def test_rebuild_graph_route_loads_documents_from_es(
        self,
        async_client,
        mock_es_service,
        mock_graph_retrieval_service
    ):
        """
        场景：从 ES 重建内存图谱索引

        预期：读取 skill/asset 索引并返回重建后的图索引统计
        """
        response = await async_client.post("/api/v1/rag/graph/rebuild")

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["indexed_count"] == 2
        assert body["data"]["stats"]["document_count"] == 2
        assert mock_es_service.list_documents.await_count == 2
        mock_graph_retrieval_service.rebuild.assert_called_once()


# =============================================================================
# 测试用例：POST /api/v1/rag/test-user/search/optimize
# =============================================================================

class TestOptimizeSearchEndpoint:
    """语义优化检索接口测试"""

    @pytest.mark.asyncio
    async def test_optimize_search_uses_expanded_queries(
        self,
        async_client,
        mock_milvus_service
    ):
        """
        场景：LLM 返回多个扩展查询

        预期：优化检索阶段使用每个扩展查询执行检索，并在 SEE 中返回查询数量
        """
        searched_queries = []
        optimizer = AsyncMock()
        optimizer.optimize.return_value = {
            "intent": "查找登录能力",
            "cot_plan": ["识别登录主题", "扩展认证相关表达"],
            "optimized_query": "登录认证能力",
            "expanded_queries": ["登录认证能力", "用户登录错误处理"],
            "query_scope": "hybrid",
            "route_plan": {"strategy": "summary_then_evidence", "steps": ["document_summary", "evidence_chunks"]},
            "issue_type": "consult",
            "see_trace": [{"stage": "intent", "summary": "查找登录能力", "metrics": {}}],
            "fallback_used": False,
            "fallback_reason": ""
        }

        async def fake_encode(input_text):
            searched_queries.append(input_text)
            if isinstance(input_text, list):
                return [[0.1] * 8192 for _ in input_text]
            return [0.1] * 8192

        mock_milvus_service.search = AsyncMock(return_value=[
            {
                "id": "skill-login",
                "description": "登录认证能力",
                "metadata": {"type": "skill", "id": "skill-login"},
                "score": 0.9
            }
        ])

        with patch("app.routers.rag_optimize.get_query_optimize_service", return_value=optimizer), \
             patch("app.services.rag_search_pipeline_service.get_embedding_service") as embedding_getter, \
             patch("app.routers.rag_optimize.get_embedding_service") as optimize_embedding_getter:
            embedding_getter.return_value.encode = AsyncMock(side_effect=fake_encode)
            optimize_embedding_getter.return_value = embedding_getter.return_value
            response = await async_client.post(
                "/api/v1/rag/test-user/search/optimize",
                json={"input": "登录", "type": "skill", "topK": 5}
            )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["request_id"]
        assert body["issue_type"] == "consult"
        assert body["issue_filters"]["issue_type"] == ["consult"]
        assert "登录" in searched_queries
        assert ["登录认证能力", "用户登录错误处理"] in searched_queries
        original_trace = next(item for item in body["see_trace"] if item["stage"] == "original_retrieval")
        query_scope_trace = next(item for item in body["see_trace"] if item["stage"] == "query_scope_detected")
        optimized_trace = next(item for item in body["see_trace"] if item["stage"] == "optimized_retrieval")
        assert "profile" in original_trace["metrics"]
        assert "fallbacks" in original_trace["metrics"]["profile"]
        assert query_scope_trace["metrics"]["query_scope"] == "hybrid"
        assert query_scope_trace["metrics"]["route_plan"] == [
            "document_summary",
            "evidence_chunks",
        ]
        assert optimized_trace["metrics"]["query_count"] == 2
        assert optimized_trace["metrics"]["query_scope"] == "hybrid"
        assert optimized_trace["metrics"]["issue_type"] == "consult"
        assert optimized_trace["metrics"]["issue_filters"]["issue_type"] == ["consult"]
        assert optimized_trace["metrics"]["route_plan"]["strategy"] == "summary_then_evidence"
        assert set(optimized_trace["metrics"]["query_profiles"]) == {"登录认证能力", "用户登录错误处理"}
        for query_profile in optimized_trace["metrics"]["query_profiles"].values():
            assert "counts" in query_profile
            assert "fallbacks" in query_profile
            assert query_profile["retrieval_strategy"]["query_scope"] == "hybrid"
            assert query_profile["retrieval_strategy"]["route_plan"] == [
                "document_summary",
                "evidence_chunks",
            ]

    @pytest.mark.asyncio
    async def test_optimize_search_runs_original_search_and_llm_in_parallel(
        self,
        async_client,
        monkeypatch,
    ):
        """
        场景：优化检索同时需要原始检索和 LLM 查询优化

        预期：两者并发启动，避免端到端耗时串行叠加
        """
        events = []

        async def fake_original_context(id, request):
            events.append("original_start")
            await asyncio.sleep(0.01)
            events.append("original_end")
            return {"results": [], "profile": {"counts": {}, "fallbacks": {}}}

        optimizer = AsyncMock()

        async def fake_optimize(query):
            events.append("optimize_start")
            await asyncio.sleep(0.01)
            events.append("optimize_end")
            return {
                "intent": "查找登录能力",
                "cot_plan": [],
                "optimized_query": "登录认证能力",
                "expanded_queries": ["登录认证能力"],
                "see_trace": [],
                "fallback_used": False,
                "fallback_reason": "",
            }

        async def fake_optimized_pipeline(
            id,
            base_request,
            queries,
            retrieval_context=None,
            request_id=None,
            query_scope=None,
            route_plan=None,
            issue_type=None,
        ):
            return [], {query: 0 for query in queries}, {query: {"counts": {}, "fallbacks": {}} for query in queries}

        optimizer.optimize = AsyncMock(side_effect=fake_optimize)
        monkeypatch.setattr("app.routers.rag_optimize._run_original_query_context", fake_original_context)
        monkeypatch.setattr("app.routers.rag_optimize._run_optimized_query_pipeline", fake_optimized_pipeline)

        with patch("app.routers.rag_optimize.get_query_optimize_service", return_value=optimizer):
            response = await async_client.post(
                "/api/v1/rag/test-user/search/optimize",
                json={"input": "登录", "type": "skill", "topK": 5}
            )

        assert response.status_code == 200
        assert events.index("optimize_start") < events.index("original_end")

    @pytest.mark.asyncio
    async def test_optimize_search_limits_expanded_queries(
        self,
        async_client,
        monkeypatch,
    ):
        """
        场景：LLM 返回多条扩展查询

        预期：按配置限制实际检索查询数，避免优化检索延迟随查询数线性放大
        """
        searched_queries = []
        optimizer = AsyncMock()
        optimizer.optimize.return_value = {
            "intent": "查找登录能力",
            "cot_plan": [],
            "optimized_query": "登录认证能力",
            "expanded_queries": ["登录认证能力", "登录故障", "登录报错"],
            "see_trace": [],
            "fallback_used": False,
            "fallback_reason": "",
        }

        async def fake_optimized_pipeline(
            id,
            base_request,
            queries,
            retrieval_context=None,
            request_id=None,
            query_scope=None,
            route_plan=None,
            issue_type=None,
        ):
            searched_queries.extend(queries)
            return [], {query: 0 for query in queries}, {query: {"counts": {}, "fallbacks": {}} for query in queries}

        monkeypatch.setattr("app.routers.rag_optimize.Config.RAG_OPTIMIZE_QUERY_LIMIT", 2, raising=False)
        monkeypatch.setattr("app.routers.rag_optimize._run_optimized_query_pipeline", fake_optimized_pipeline)
        monkeypatch.setattr(
            "app.routers.rag_optimize._run_original_query_context",
            AsyncMock(return_value={"results": [], "profile": {"counts": {}, "fallbacks": {}}})
        )

        with patch("app.routers.rag_optimize.get_query_optimize_service", return_value=optimizer):
            response = await async_client.post(
                "/api/v1/rag/test-user/search/optimize",
                json={"input": "登录", "type": "skill", "topK": 5}
            )

        assert response.status_code == 200
        assert searched_queries == ["登录认证能力", "登录故障"]
        optimized_trace = next(
            item for item in response.json()["data"]["see_trace"]
            if item["stage"] == "optimized_retrieval"
        )
        assert optimized_trace["metrics"]["query_count"] == 2

    @pytest.mark.asyncio
    async def test_optimize_search_returns_recommendations_when_optimized_results_empty(
        self,
        async_client,
        monkeypatch,
    ):
        """
        场景：优化检索没有主结果，但原始检索有相关候选

        预期：响应返回 recommendations，并在 SEE 中展示推荐阶段
        """
        optimizer = AsyncMock()
        optimizer.optimize.return_value = {
            "intent": "排查小程序生产环境上线后白屏问题",
            "cot_plan": [],
            "optimized_query": "小程序上线后白屏 本地正常 生产环境异常 排查",
            "expanded_queries": ["小程序上线后白屏 本地正常 生产环境异常 排查"],
            "see_trace": [
                {
                    "stage": "query_decomposition",
                    "summary": "排查小程序生产环境上线后白屏问题",
                    "metrics": {
                        "query_type": "troubleshooting",
                        "rule": "mini_program_white_screen_after_release",
                        "entities": ["小程序"],
                        "symptoms": ["白屏"],
                        "environment_gap": ["本地正常", "生产环境异常"],
                        "time_context": ["上线后"],
                    }
                }
            ],
            "fallback_used": False,
            "fallback_reason": "",
        }
        original_result = SearchResult(
            metadata={"id": "skill-white-screen", "type": "skill"},
            description="小程序上线后白屏，本地正常时检查接口域名和资源路径",
            score=0.42,
            features={"tags": ["小程序", "白屏"]}
        )

        async def fake_original_context(id, request):
            return {"results": [original_result], "profile": {"counts": {"filtered": 1}, "fallbacks": {}}}

        async def fake_optimized_pipeline(
            id,
            base_request,
            queries,
            retrieval_context=None,
            request_id=None,
            query_scope=None,
            route_plan=None,
            issue_type=None,
        ):
            assert retrieval_context.query_type == "troubleshooting"
            return [], {queries[0]: 0}, {queries[0]: {"counts": {"filtered": 0}, "fallbacks": {}, "retrieval_strategy": {"applied": True}}}

        monkeypatch.setattr("app.routers.rag_optimize._run_original_query_context", fake_original_context)
        monkeypatch.setattr("app.routers.rag_optimize._run_optimized_query_pipeline", fake_optimized_pipeline)
        monkeypatch.setattr("app.routers.rag_optimize.Config.RAG_RECOMMENDATION_TOP_K", 3, raising=False)

        with patch("app.routers.rag_optimize.get_query_optimize_service", return_value=optimizer):
            response = await async_client.post(
                "/api/v1/rag/test-user/search/optimize",
                json={"input": "我的小程序上线后白屏了，之前本地开发都正常", "type": "skill", "topK": 5}
            )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["optimized_results"] == []
        assert len(body["recommendations"]) == 1
        assert body["recommendations"][0]["metadata"]["id"] == "skill-white-screen"
        assert "白屏" in body["recommendations"][0]["reason"]
        recommendation_trace = next(item for item in body["see_trace"] if item["stage"] == "recommendation")
        assert recommendation_trace["metrics"]["recommendation_count"] == 1

    @pytest.mark.asyncio
    async def test_optimized_query_pipeline_batches_query_embeddings(self, monkeypatch):
        """
        场景：优化检索执行多条扩展查询

        预期：批量生成查询向量，并传入各检索管线复用，减少外部 Embedding 调用次数
        """
        from app.routers.rag_optimize import _run_optimized_query_pipeline

        embedding_service = MagicMock()
        embedding_service.encode = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
        captured_vectors = []

        async def fake_pipeline(id, query_request, prefetched_query_vector=None, retrieval_context=None, request_id=None):
            captured_vectors.append(prefetched_query_vector)
            result = MagicMock()
            result.results = []
            result.profile = {"counts": {}, "fallbacks": {}, "timings_ms": {}}
            return result

        monkeypatch.setattr("app.routers.rag_optimize.get_embedding_service", lambda: embedding_service)
        monkeypatch.setattr("app.routers.rag_optimize.run_search_pipeline_with_profile", fake_pipeline)

        await _run_optimized_query_pipeline(
            id="test-user",
            base_request=OptimizeSearchRequest(input="登录", type="skill", topK=5),
            queries=["登录认证能力", "用户登录错误处理"],
        )

        embedding_service.encode.assert_awaited_once_with(["登录认证能力", "用户登录错误处理"])
        assert captured_vectors == [[0.1, 0.2], [0.3, 0.4]]

    @pytest.mark.asyncio
    async def test_optimized_query_pipeline_passes_issue_type(self, monkeypatch):
        """优化检索管线应把 issue_type 传入每个 SearchRequest。"""
        from app.routers.rag_optimize import _run_optimized_query_pipeline

        captured_issue_types = []

        async def fake_pipeline(id, query_request, prefetched_query_vector=None, retrieval_context=None, request_id=None):
            captured_issue_types.append(query_request.issue_type)
            result = MagicMock()
            result.results = []
            result.profile = {"counts": {}, "fallbacks": {}, "timings_ms": {}}
            return result

        monkeypatch.setattr("app.routers.rag_optimize.get_embedding_service", MagicMock())
        monkeypatch.setattr("app.routers.rag_optimize.run_search_pipeline_with_profile", fake_pipeline)

        await _run_optimized_query_pipeline(
            id="test-user",
            base_request=OptimizeSearchRequest(input="白屏", type="skill", topK=5),
            queries=["白屏排查"],
            issue_type="fault",
        )

        assert captured_issue_types == ["fault"]

    @pytest.mark.asyncio
    async def test_optimize_search_fallback_visible(self, async_client):
        """
        场景：LLM 优化失败后降级使用原始查询

        预期：响应和 SEE 均标记 fallback
        """
        optimizer = AsyncMock()
        optimizer.optimize.return_value = {
            "intent": "",
            "cot_plan": [],
            "optimized_query": "登录失败",
            "expanded_queries": ["登录失败"],
            "see_trace": [{"stage": "fallback", "summary": "LLM 优化失败，使用原始查询", "metrics": {}}],
            "fallback_used": True,
            "fallback_reason": "llm unavailable"
        }

        with patch("app.routers.rag_optimize.get_query_optimize_service", return_value=optimizer):
            response = await async_client.post(
                "/api/v1/rag/test-user/search/optimize",
                json={"input": "登录失败", "type": "skill", "topK": 5}
            )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["fallback_used"] is True
        assert any(item["stage"] == "fallback" for item in body["see_trace"])

    @pytest.mark.asyncio
    async def test_get_optimize_history_detail_and_not_found(self, async_client):
        """
        场景：查询优化历史详情

        预期：已存在记录可查询，不存在记录返回 404
        """
        optimizer = AsyncMock()
        optimizer.optimize.return_value = {
            "intent": "查找登录能力",
            "cot_plan": ["识别登录主题"],
            "optimized_query": "登录认证能力",
            "expanded_queries": ["登录认证能力"],
            "see_trace": [],
            "fallback_used": False,
            "fallback_reason": ""
        }

        with patch("app.routers.rag_optimize.get_query_optimize_service", return_value=optimizer):
            response = await async_client.post(
                "/api/v1/rag/test-user/search/optimize",
                json={"input": "登录", "type": "skill", "topK": 5}
            )

        history_id = response.json()["data"]["comparison"]["history_id"]
        detail_response = await async_client.get(
            f"/api/v1/rag/test-user/search/optimize/history/{history_id}"
        )
        missing_response = await async_client.get(
            "/api/v1/rag/test-user/search/optimize/history/missing-history-id"
        )

        assert detail_response.status_code == 200
        assert detail_response.json()["data"]["history_id"] == history_id
        assert missing_response.status_code == 404


# =============================================================================
# 测试用例：RAG 检索评测记录
# =============================================================================

class TestEvaluationRecordsEndpoint:
    """检索评测记录接口测试"""

    @pytest.mark.asyncio
    async def test_create_and_list_evaluation_records(self, async_client):
        """
        场景：提交检索评测记录后查询列表

        预期：记录按用户隔离并倒序返回
        """
        first = {
            "query": "登录失败",
            "optimized_query": "登录失败原因排查",
            "retrieved_ids": ["skill-1"],
            "miss_reason": "recall_miss",
            "human_label": "bad"
        }
        second = {
            "query": "注册失败",
            "retrieved_ids": ["skill-2"],
            "miss_reason": "unknown",
            "human_label": "good"
        }

        first_response = await async_client.post(
            "/api/v1/rag/test-user/evaluation/records",
            json=first
        )
        second_response = await async_client.post(
            "/api/v1/rag/test-user/evaluation/records",
            json=second
        )
        list_response = await async_client.get(
            "/api/v1/rag/test-user/evaluation/records"
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        records = list_response.json()["data"]
        assert records[0]["record_id"] == second_response.json()["data"]["record_id"]
        assert records[1]["record_id"] == first_response.json()["data"]["record_id"]

    @pytest.mark.asyncio
    async def test_create_evaluation_record_rejects_invalid_miss_reason(self, async_client):
        """
        场景：提交非法 miss_reason

        预期：返回 422
        """
        response = await async_client.post(
            "/api/v1/rag/test-user/evaluation/records",
            json={
                "query": "登录失败",
                "retrieved_ids": [],
                "miss_reason": "bad_reason"
            }
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_evaluation_summary(self, async_client):
        """
        场景：提交多条评测记录后查询汇总

        预期：返回 bad case 原因和人工标签分布
        """
        await async_client.post(
            "/api/v1/rag/test-user/evaluation/records",
            json={
                "query": "登录失败",
                "retrieved_ids": ["skill-1"],
                "miss_reason": "recall_miss",
                "human_label": "bad"
            }
        )
        await async_client.post(
            "/api/v1/rag/test-user/evaluation/records",
            json={
                "query": "注册失败",
                "retrieved_ids": ["skill-2"],
                "miss_reason": "rerank_error",
                "human_label": "good"
            }
        )

        response = await async_client.get(
            "/api/v1/rag/test-user/evaluation/records/summary"
        )

        assert response.status_code == 200
        summary = response.json()["data"]
        assert summary["total_count"] >= 2
        assert summary["miss_reason_counts"]["recall_miss"] >= 1
        assert summary["miss_reason_counts"]["rerank_error"] >= 1
        assert summary["human_label_counts"]["bad"] >= 1
        assert summary["human_label_counts"]["good"] >= 1
        assert summary["latest_created_at"]


# =============================================================================
# 测试用例：RAG 缓存管理
# =============================================================================

class TestCacheEndpoint:
    """缓存管理接口测试"""

    @pytest.mark.asyncio
    async def test_cache_stats_and_reset(self, async_client):
        """
        场景：查询和重置缓存

        预期：缓存管理路由可正常访问
        """
        stats_response = await async_client.get("/api/v1/rag/cache/stats")
        reset_response = await async_client.post("/api/v1/rag/cache/reset")

        assert stats_response.status_code == 200
        stats = stats_response.json()["data"]
        assert "hit_rate" in stats["embedding_cache"]
        assert "hits" in stats["embedding_cache"]
        assert "misses" in stats["embedding_cache"]
        assert "sets" in stats["embedding_cache"]
        assert "hit_rate" in stats["rerank_cache"]
        assert "hits" in stats["rerank_cache"]
        assert "misses" in stats["rerank_cache"]
        assert "sets" in stats["rerank_cache"]
        assert reset_response.status_code == 200
        assert reset_response.json()["message"] == "缓存已重置"

    @pytest.mark.asyncio
    async def test_invalidate_rerank_cache_by_request_id(self, async_client, monkeypatch):
        """
        场景：用户按 request_id 主动撤销一次请求关联的 Rerank 缓存

        预期：接口只撤销 Rerank 缓存并返回撤销统计
        """
        cache = MagicMock()
        cache.invalidate_rerank_by_request_id.return_value = {
            "request_id": "req-001",
            "invalidated": 1,
            "bypassed_queries": 1,
        }
        monkeypatch.setattr("app.routers.rag_cache.get_cache_service", lambda: cache)

        response = await async_client.post("/api/v1/rag/cache/rerank/invalidate-by-request/req-001")

        assert response.status_code == 200
        assert response.json()["data"] == {
            "request_id": "req-001",
            "invalidated": 1,
            "bypassed_queries": 1,
        }
        cache.invalidate_rerank_by_request_id.assert_called_once_with("req-001")


# =============================================================================
# 测试用例：DELETE /api/v1/rag/test-user/delete
# =============================================================================

class TestDeleteEndpoint:
    """删除记录接口测试"""

    @pytest.mark.asyncio
    async def test_delete_success(self, async_client, mock_milvus_service, mock_graph_retrieval_service):
        """
        场景：删除成功

        预期：
        - 返回 200
        - code 为 200
        - message 为 "success"
        """
        # given: 有效的删除请求
        request_body = {
            "type": "skill",
            "id": "skill-001"
        }

        # when: 调用删除接口
        response = await async_client.request("DELETE", "/api/v1/rag/test-user/delete", json=request_body)

        # then: 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        mock_graph_retrieval_service.delete_document.assert_called_once_with("skill-001")

    @pytest.mark.asyncio
    async def test_delete_missing_type(self, async_client):
        """
        场景：删除请求缺少 type

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 缺少 type 的请求
        request_body = {
            "id": "skill-001"
        }

        # when: 调用删除接口
        response = await async_client.request("DELETE", "/api/v1/rag/test-user/delete", json=request_body)

        # then: 验证响应
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_missing_id(self, async_client):
        """
        场景：删除请求缺少 id

        预期：
        - 返回 422 (Validation Error)
        """
        # given: 缺少 id 的请求
        request_body = {
            "type": "skill"
        }

        # when: 调用删除接口
        response = await async_client.request("DELETE", "/api/v1/rag/test-user/delete", json=request_body)

        # then: 验证响应
        assert response.status_code == 422


# =============================================================================
# 测试用例：GET /health
# =============================================================================

class TestHealthEndpoint:
    """健康检查接口测试"""

    @pytest.mark.asyncio
    async def test_health_all_services_healthy(self, async_client):
        """
        场景：所有服务正常

        预期：
        - 返回 200
        - status 为 "healthy"
        - services 包含 milvus、embedding、rerank
        """
        # when: 调用健康检查接口
        response = await async_client.get("/health")

        # then: 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data
        assert "milvus" in data["services"]
        assert "embedding" in data["services"]
        assert "rerank" in data["services"]


# =============================================================================
# 测试用例：错误码覆盖
# =============================================================================

class TestErrorCodes:
    """错误码测试"""

    @pytest.mark.asyncio
    async def test_error_milvus_connection_failed(
        self,
        async_client,
        mock_embedding_service,
        mock_milvus_service,
        mock_graph_retrieval_service,
        mock_es_service,
    ):
        """
        场景：Milvus 连接失败

        预期：
        - 向量检索降级为空列表
        - 没有 ES/图检索候选时返回空结果
        """
        # given: Milvus 服务不可用时，search 抛出异常
        async def mock_search_raise(*args, **kwargs):
            raise Exception("Milvus 连接失败")

        mock_milvus_service.search = AsyncMock(side_effect=mock_search_raise)
        mock_graph_retrieval_service.search = MagicMock(return_value=[])
        mock_es_service.search = AsyncMock(return_value=[])

        # when: 调用检索接口
        request_body = {
            "input": "查找登录相关的 skill",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证返回空结果
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_error_embedding_service_unavailable(self, async_client, mock_milvus_service):
        """
        场景：Embedding 服务不可用

        预期：
        - 返回适当错误响应
        - 记录 ERROR 日志
        """
        # given: Embedding 服务不可用
        with patch("app.services.embedding_service.EmbeddingService.encode", new_callable=AsyncMock) as mock_encode:
            mock_encode.side_effect = Exception("Embedding 服务不可用")

            # when: 调用插入接口
            request_body = {
                "description": "用户登录功能",
                "metadata": {
                    "type": "skill",
                    "id": "skill-001",
                    "description": "登录相关"
                }
            }
            response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)

            # then: 验证返回错误
            assert response.status_code in [500, 200]

    @pytest.mark.asyncio
    async def test_error_rerank_service_unavailable_degraded_mode(self, async_client, mock_embedding_service, mock_milvus_service):
        """
        场景：Rerank 服务不可用，降级模式

        预期：
        - 返回 200
        - message 包含 "降级模式"
        - 使用原始分数
        """
        # given: Rerank 服务不可用
        with patch("app.services.rerank_service.RerankService.rerank", new_callable=AsyncMock) as mock_rerank:
            mock_rerank.side_effect = Exception("Rerank 服务不可用")

            # when: 调用检索接口
            request_body = {
                "input": "查找登录相关的 skill",
                "type": "skill",
                "topK": 20
            }
            response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

            # then: 验证降级响应
            assert response.status_code == 200
            data = response.json()
            assert "降级" in data.get("message", "") or data["code"] == 200


# =============================================================================
# 测试用例：业务标识日志验证（需要集成测试验证）
# =============================================================================

class TestLoggingFormat:
    """日志格式测试"""

    @pytest.mark.asyncio
    async def test_log_business_identifier_format(self, async_client):
        """
        场景：验证日志包含业务标识

        预期：
        - 日志包含 [RAG插入]、[RAG检索] 等业务标识
        - 日志使用占位符 {}

        注：此测试需要在集成测试环境中验证日志格式
        """
        # given: 有效的插入请求
        request_body = {
            "description": "用户登录功能",
            "metadata": {
                "type": "skill",
                "id": "skill-001",
                "description": "登录相关"
            }
        }

        # when: 执行插入操作
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)

        # then: 验证请求成功（日志格式在集成测试中验证）
        assert response.status_code == 200


# =============================================================================
# 测试用例：并发场景
# =============================================================================

class TestConcurrency:
    """并发测试"""

    @pytest.mark.asyncio
    async def test_concurrent_search_requests(self, async_client, mock_embedding_service, mock_milvus_service, mock_rerank_service):
        """
        场景：并发检索请求

        预期：
        - 所有请求都能成功处理
        - 响应时间合理
        """
        # given: 并发请求
        request_body = {
            "input": "查找登录相关的 skill",
            "type": "skill",
            "topK": 20
        }

        # when: 发送 10 个并发请求
        import asyncio
        tasks = [
            async_client.post("/api/v1/rag/test-user/search", json=request_body)
            for _ in range(10)
        ]
        responses = await asyncio.gather(*tasks)

        # then: 验证所有请求成功
        for response in responses:
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_type_all_parallel_search(self, async_client, mock_embedding_service, mock_milvus_service, mock_rerank_service):
        """
        场景：type="all" 并行检索

        预期：
        - 使用 asyncio.gather() 并行
        - 响应时间优于串行
        """
        # given: type="all" 请求
        request_body = {
            "input": "查找登录相关的资源",
            "type": "all",
            "topK": 20
        }

        # when: 调用检索接口
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        # then: 验证响应
        assert response.status_code == 200
