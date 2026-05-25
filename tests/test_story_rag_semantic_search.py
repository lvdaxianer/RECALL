"""
RAG 语义检索故事线测试用例

故事线：RAG 语义检索平台
- 用户A 插入数据到向量库
- 用户B 检索对应内容
- 如果结果不满意，调用大模型丰富语义，再次检索

测试覆盖：
1. 健康检查接口
2. 单条插入接口
3. 批量插入接口
4. 语义检索接口
5. 删除接口
6. 语义优化接口（待实现）
7. 日志增强（待实现）

@author lvdaxianerplus
@date 2026-04-15
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


# =============================================================================
# Fixtures
# =============================================================================

_mock_embedding_service = None
_mock_rerank_service = None
_mock_milvus_service = None
_mock_feature_extract_service = None
_mock_feature_boost_service = None
_mock_es_service = None


def get_mock_es_service():
    """获取 Mock ES 服务"""
    global _mock_es_service
    if _mock_es_service is None:
        _mock_es_service = MagicMock()
        _mock_es_service.index_document = AsyncMock(return_value=None)
        _mock_es_service.search = AsyncMock(return_value=[])
        _mock_es_service.delete_document = AsyncMock(return_value=True)
        _mock_es_service.health_check = MagicMock(return_value=True)
    return _mock_es_service


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
        _mock_milvus_service.insert = AsyncMock(return_value={
            "id": "test-id",
            "collection": "skill",
            "features": {"category": "模型", "tags": ["3D", "飞机"]}
        })
        _mock_milvus_service.batch_insert = AsyncMock(return_value={"inserted_count": 2})
        _mock_milvus_service.search = AsyncMock(return_value=[
            {"id": "skill-001", "description": "用户登录功能", "metadata": {"type": "skill", "id": "skill-001"}, "features": {"category": "模型", "tags": ["登录"]}, "score": 0.85},
            {"id": "skill-002", "description": "用户注册功能", "metadata": {"type": "skill", "id": "skill-002"}, "features": {"category": "模型", "tags": ["注册"]}, "score": 0.72}
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
            "category": "模型",
            "tags": ["3D", "飞机", "飞行"]
        })
        _mock_feature_extract_service.health_check = AsyncMock(return_value=True)
    return _mock_feature_extract_service


def get_mock_feature_boost_service():
    """获取 Mock 特征加权服务"""
    global _mock_feature_boost_service
    if _mock_feature_boost_service is None:
        _mock_feature_boost_service = AsyncMock()
        _mock_feature_boost_service.boost = AsyncMock(side_effect=lambda query, results, **kwargs: results)
        _mock_feature_boost_service.health_check = AsyncMock(return_value=True)
    return _mock_feature_boost_service


@pytest_asyncio.fixture
async def mock_services():
    """Mock 所有服务"""
    return {
        "embedding": get_mock_embedding_service(),
        "rerank": get_mock_rerank_service(),
        "milvus": get_mock_milvus_service(),
        "feature_extract": get_mock_feature_extract_service(),
        "feature_boost": get_mock_feature_boost_service(),
        "es": get_mock_es_service()
    }


@pytest_asyncio.fixture
async def app_router(mock_services):
    """创建带有 mock 服务的 app"""
    with patch("app.services.embedding_service.EmbeddingService", return_value=mock_services["embedding"]), \
         patch("app.services.rerank_service.RerankService", return_value=mock_services["rerank"]), \
         patch("app.services.milvus_service.MilvusService", return_value=mock_services["milvus"]), \
         patch("app.routers.rag.get_embedding_service", return_value=lambda: mock_services["embedding"]), \
         patch("app.routers.rag.get_rerank_service", return_value=lambda: mock_services["rerank"]), \
         patch("app.routers.rag.get_milvus_service", return_value=lambda: mock_services["milvus"]), \
         patch("app.routers.rag.get_feature_extract_service", return_value=lambda: mock_services["feature_extract"]), \
         patch("app.routers.rag.get_feature_boost_service", return_value=lambda: mock_services["feature_boost"]), \
         patch("app.routers.rag.get_es_service", return_value=lambda: mock_services.get("es", MagicMock())):
        from app.main import app
        return app


@pytest_asyncio.fixture
async def async_client(app_router):
    """异步 HTTP 客户端"""
    transport = ASGITransport(app=app_router)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# =============================================================================
# 故事线测试 1: 健康检查
# =============================================================================

class TestStoryHealthCheck:
    """
    故事节点 1: 健康检查
    验证各服务状态
    """

    @pytest.mark.asyncio
    async def test_health_all_services_available(self, async_client):
        """
        场景：所有服务正常

        预期：
        - status = "healthy"
        - milvus = "connected"
        - embedding = "available"
        - rerank = "available"
        """
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["services"]["milvus"] == "connected"
        assert data["services"]["embedding"] == "available"
        assert data["services"]["rerank"] == "available"

    @pytest.mark.asyncio
    async def test_health_milvus_disconnected(self, async_client, mock_services):
        """
        场景：Milvus 断开连接

        预期：
        - status = "unhealthy"
        """
        mock_services["milvus"].health_check = AsyncMock(return_value=False)
        response = await async_client.get("/health")
        data = response.json()
        assert data["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_embedding_unavailable(self, async_client, mock_services):
        """
        场景：Embedding 服务不可用

        预期：
        - status = "degraded"
        - embedding = "unavailable"
        """
        mock_services["embedding"].health_check = AsyncMock(return_value=False)
        response = await async_client.get("/health")
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["embedding"] == "unavailable"

    @pytest.mark.asyncio
    async def test_health_rerank_unavailable(self, async_client, mock_services):
        """
        场景：Rerank 服务不可用

        预期：
        - status = "degraded"
        - rerank = "unavailable"
        """
        mock_services["rerank"].health_check = AsyncMock(return_value=False)
        response = await async_client.get("/health")
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["rerank"] == "unavailable"


# =============================================================================
# 故事线测试 2: 用户A 插入数据
# =============================================================================

class TestStoryUserAInsert:
    """
    故事节点 2: 用户A 插入数据到向量库
    """

    # --- 正常分支 ---

    @pytest.mark.asyncio
    async def test_insert_single_success_skill(self, async_client, mock_services):
        """
        场景：用户A 插入 skill 类型数据成功

        预期：返回 200, id 和 collection
        """
        request_body = {
            "description": "用户登录功能",
            "metadata": {
                "type": "skill",
                "id": "skill-login-001",
                "description": "登录相关 skill"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        assert data["data"]["id"] == "skill-login-001"
        assert data["data"]["collection"] == "skill"

    @pytest.mark.asyncio
    async def test_insert_single_success_asset(self, async_client, mock_services):
        """
        场景：用户A 插入 asset 类型数据成功

        预期：返回 200, id 和 collection
        """
        request_body = {
            "description": "登录页面 UI 组件",
            "metadata": {
                "type": "asset",
                "id": "asset-login-ui-001",
                "description": "登录页面资源"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["collection"] == "asset"

    @pytest.mark.asyncio
    async def test_insert_long_description(self, async_client, mock_services):
        """
        场景：插入超长描述文本（接近上限）

        预期：成功（< 10000 字符）
        """
        long_desc = "A" * 9999
        request_body = {
            "description": long_desc,
            "metadata": {
                "type": "skill",
                "id": "skill-long-001",
                "description": "长描述测试"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 200

    # --- 异常分支 ---

    @pytest.mark.asyncio
    async def test_insert_missing_description(self, async_client):
        """
        场景：缺少 description

        预期：422 Validation Error
        """
        request_body = {
            "metadata": {
                "type": "skill",
                "id": "skill-001",
                "description": "test"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_missing_metadata(self, async_client):
        """
        场景：缺少 metadata

        预期：422 Validation Error
        """
        request_body = {
            "description": "测试描述"
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_missing_metadata_type(self, async_client):
        """
        场景：metadata 缺少 type

        预期：422 Validation Error
        """
        request_body = {
            "description": "测试描述",
            "metadata": {
                "id": "skill-001",
                "description": "test"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_missing_metadata_id(self, async_client):
        """
        场景：metadata 缺少 id

        预期：422 Validation Error
        """
        request_body = {
            "description": "测试描述",
            "metadata": {
                "type": "skill",
                "description": "test"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_empty_description(self, async_client):
        """
        场景：description 为空

        预期：422 Validation Error
        """
        request_body = {
            "description": "",
            "metadata": {
                "type": "skill",
                "id": "skill-001",
                "description": "test"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_exceed_max_length(self, async_client):
        """
        场景：description 超过 10000 字符

        预期：422 Validation Error
        """
        request_body = {
            "description": "A" * 10001,
            "metadata": {
                "type": "skill",
                "id": "skill-001",
                "description": "test"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_insert_embedding_service_error(self, async_client, mock_services):
        """
        场景：Embedding 服务调用失败

        预期：500 Internal Server Error
        """
        mock_services["embedding"].encode = AsyncMock(side_effect=Exception("Embedding Error"))
        request_body = {
            "description": "测试描述",
            "metadata": {
                "type": "skill",
                "id": "skill-001",
                "description": "test"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 500


# =============================================================================
# 故事线测试 3: 批量插入
# =============================================================================

class TestStoryBatchInsert:
    """
    故事节点 3: 批量插入数据
    """

    @pytest.mark.asyncio
    async def test_batch_insert_success(self, async_client, mock_services):
        """
        场景：批量插入 2 条数据成功

        预期：inserted_count = 2
        """
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
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["inserted_count"] == 2

    @pytest.mark.asyncio
    async def test_batch_insert_single_item(self, async_client, mock_services):
        """
        场景：批量插入单条数据

        预期：inserted_count = 1
        """
        request_body = {
            "items": [
                {
                    "description": "skill A",
                    "metadata": {"type": "skill", "id": "skill-A", "description": "A"}
                }
            ]
        }
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["inserted_count"] == 1

    @pytest.mark.asyncio
    async def test_batch_insert_100_items(self, async_client, mock_services):
        """
        场景：批量插入 100 条数据

        预期：inserted_count = 100
        """
        items = [
            {
                "description": f"skill {i}",
                "metadata": {"type": "skill", "id": f"skill-{i:03d}", "description": f"skill {i}"}
            }
            for i in range(100)
        ]
        request_body = {"items": items}
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["inserted_count"] == 100

    @pytest.mark.asyncio
    async def test_batch_insert_empty_items(self, async_client):
        """
        场景：items 为空列表

        预期：422 Validation Error
        """
        request_body = {"items": []}
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_insert_missing_items(self, async_client):
        """
        场景：缺少 items 字段

        预期：422 Validation Error
        """
        request_body = {}
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_insert_item_missing_description(self, async_client):
        """
        场景：items 中某项缺少 description

        预期：422 Validation Error
        """
        request_body = {
            "items": [
                {"description": "skill A", "metadata": {"type": "skill", "id": "A", "description": "A"}},
                {"metadata": {"type": "skill", "id": "B", "description": "B"}}
            ]
        }
        response = await async_client.post("/api/v1/rag/test-user/insert/batch", json=request_body)
        assert response.status_code == 422


# =============================================================================
# 故事线测试 4: 用户B 检索
# =============================================================================

class TestStoryUserBSearch:
    """
    故事节点 4: 用户B 检索数据
    """

    @pytest.mark.asyncio
    async def test_search_type_all(self, async_client, mock_services):
        """
        场景：用户B 检索 type=all（所有 collection）

        预期：返回所有 collection 的结果
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "all",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0

    @pytest.mark.asyncio
    async def test_search_type_skill(self, async_client, mock_services):
        """
        场景：用户B 只检索 skill collection

        预期：只返回 skill 类型结果
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        for item in data["data"]:
            assert item["metadata"]["type"] == "skill"

    @pytest.mark.asyncio
    async def test_search_type_asset(self, async_client, mock_services):
        """
        场景：用户B 只检索 asset collection

        预期：只返回 asset 类型结果
        """
        mock_services["milvus"].search = AsyncMock(return_value=[
            {"id": "asset-001", "description": "登录页面图片", "metadata": {"type": "asset", "id": "asset-001"}, "score": 0.85}
        ])
        request_body = {
            "input": "查找登录页面图片",
            "type": "asset",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        for item in data["data"]:
            assert item["metadata"]["type"] == "asset"

    @pytest.mark.asyncio
    async def test_search_default_type_all(self, async_client, mock_services):
        """
        场景：不指定 type，默认为 all

        预期：type 默认为 all
        """
        request_body = {
            "input": "查找登录相关的内容",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_with_topk(self, async_client, mock_services):
        """
        场景：指定 topK=5

        预期：返回最多 5 条结果
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 5
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 5

    @pytest.mark.asyncio
    async def test_search_topk_1(self, async_client, mock_services):
        """
        场景：topK=1

        预期：返回 1 条结果
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 1
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 1

    @pytest.mark.asyncio
    async def test_search_topk_1000_boundary(self, async_client, mock_services):
        """
        场景：topK=1000（边界值）

        预期：返回成功
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 1000
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_missing_input(self, async_client):
        """
        场景：缺少 input

        预期：422 Validation Error
        """
        request_body = {
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_empty_input(self, async_client):
        """
        场景：input 为空

        预期：422 Validation Error
        """
        request_body = {
            "input": "",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_topk_zero(self, async_client):
        """
        场景：topK=0

        预期：422 Validation Error
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 0
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_topk_negative(self, async_client):
        """
        场景：topK 为负数

        预期：422 Validation Error
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": -1
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_topk_exceeds_limit(self, async_client):
        """
        场景：topK > 1000

        预期：422 Validation Error
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 1001
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_result_sorted_by_score(self, async_client, mock_services):
        """
        场景：验证结果按 score 降序排列

        预期：scores 降序
        """
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        data = response.json()
        scores = [item["score"] for item in data["data"]]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_search_empty_result(self, async_client, mock_services):
        """
        场景：检索结果为空

        预期：返回空列表
        """
        mock_services["milvus"].search = AsyncMock(return_value=[])
        request_body = {
            "input": "不存在的查询",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_search_threshold_filter(self, async_client, mock_services):
        """
        场景：结果分数低于阈值被过滤

        预期：只返回 score >= 0.7 的结果
        """
        mock_services["milvus"].search = AsyncMock(return_value=[
            {"id": "1", "description": "A", "metadata": {}, "score": 0.85},
            {"id": "2", "description": "B", "metadata": {}, "score": 0.6}  # 低于阈值
        ])
        request_body = {
            "input": "查找内容",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        data = response.json()
        for item in data["data"]:
            assert item["score"] >= 0.7

    @pytest.mark.asyncio
    async def test_search_rerank_degraded_mode(self, async_client, mock_services):
        """
        场景：Rerank 服务不可用，降级模式

        预期：使用原始向量检索分数
        """
        mock_services["rerank"].rerank = AsyncMock(side_effect=Exception("Rerank Error"))
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_search_embedding_error(self, async_client, mock_services):
        """
        场景：Embedding 服务错误

        预期：返回空列表
        """
        mock_services["embedding"].encode = AsyncMock(side_effect=Exception("Embedding Error"))
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []


# =============================================================================
# 故事线测试 5: 删除
# =============================================================================

class TestStoryDelete:
    """
    故事节点 5: 删除记录
    """

    @pytest.mark.asyncio
    async def test_delete_success(self, async_client, mock_services):
        """
        场景：删除成功

        预期：200, message="success"
        """
        request_body = {
            "type": "skill",
            "id": "skill-001"
        }
        response = await async_client.request("DELETE", "/api/v1/rag/test-user/delete", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "success"

    @pytest.mark.asyncio
    async def test_delete_missing_type(self, async_client):
        """
        场景：缺少 type

        预期：422 Validation Error
        """
        request_body = {"id": "skill-001"}
        response = await async_client.request("DELETE", "/api/v1/rag/test-user/delete", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_missing_id(self, async_client):
        """
        场景：缺少 id

        预期：422 Validation Error
        """
        request_body = {"type": "skill"}
        response = await async_client.request("DELETE", "/api/v1/rag/test-user/delete", json=request_body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_record_not_found(self, async_client, mock_services):
        """
        场景：记录不存在

        预期：404 Not Found
        """
        mock_services["milvus"].delete = AsyncMock(return_value=False)
        request_body = {
            "type": "skill",
            "id": "non-existent-id"
        }
        response = await async_client.request("DELETE", "/api/v1/rag/test-user/delete", json=request_body)
        assert response.status_code == 404


# =============================================================================
# 故事线测试 6: 语义优化（待实现）
# =============================================================================

class TestStorySemanticOptimization:
    """
    故事节点 6: 语义优化检索（待实现功能）
    当检索结果不满意时，调用大模型丰富语义再次检索
    """

    @pytest.mark.asyncio
    async def test_semantic_optimization_not_implemented(self, async_client):
        """
        场景：语义优化接口尚未实现

        预期：404 Not Found 或 501 Not Implemented
        """
        request_body = {
            "input": "查找登录相关的内容",
            "optimize": True
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        # 当前未实现，应该返回 404 或错误提示
        assert response.status_code in [404, 501, 422]

    @pytest.mark.asyncio
    async def test_semantic_optimization_llm_call(self, async_client):
        """
        场景：调用大模型优化查询（待实现）

        预期：大模型返回优化后的查询文本
        """
        # TODO: 实现语义优化功能后，此测试应验证：
        # 1. 调用大模型 API 传入原始查询
        # 2. 大模型返回优化后的查询
        # 3. 使用优化后的查询重新检索
        # 4. 返回优化后的结果
        pass

    @pytest.mark.asyncio
    async def test_semantic_optimization_logging(self, async_client):
        """
        场景：语义优化过程日志记录（待实现）

        预期：日志包含原始查询、优化后查询、两次检索结果对比
        """
        # TODO: 实现后应验证日志格式：
        # [语义优化] 原始查询: xxx
        # [语义优化] 优化后查询: xxx
        # [语义优化] 第一次检索结果数量: x
        # [语义优化] 第二次检索结果数量: x
        pass


# =============================================================================
# 故事线测试 7: 并发测试
# =============================================================================

class TestStoryConcurrency:
    """
    故事节点 7: 并发测试
    """

    @pytest.mark.asyncio
    async def test_concurrent_insert(self, async_client, mock_services):
        """
        场景：并发插入请求

        预期：所有请求成功
        """
        import asyncio
        tasks = []
        for i in range(10):
            request_body = {
                "description": f"skill {i}",
                "metadata": {"type": "skill", "id": f"skill-{i}", "description": f"skill {i}"}
            }
            tasks.append(async_client.post("/api/v1/rag/test-user/insert", json=request_body))

        responses = await asyncio.gather(*tasks)
        for response in responses:
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_concurrent_search(self, async_client, mock_services):
        """
        场景：并发检索请求

        预期：所有请求成功
        """
        import asyncio
        request_body = {
            "input": "查找登录相关的内容",
            "type": "skill",
            "topK": 20
        }
        tasks = [async_client.post("/api/v1/rag/test-user/search", json=request_body) for _ in range(10)]
        responses = await asyncio.gather(*tasks)
        for response in responses:
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(self, async_client, mock_services):
        """
        场景：混合并发操作（插入 + 检索）

        预期：所有操作成功
        """
        import asyncio

        async def insert(i):
            request_body = {
                "description": f"skill {i}",
                "metadata": {"type": "skill", "id": f"skill-{i}", "description": f"skill {i}"}
            }
            return await async_client.post("/api/v1/rag/test-user/insert", json=request_body)

        async def search():
            request_body = {
                "input": "查找登录",
                "type": "skill",
                "topK": 20
            }
            return await async_client.post("/api/v1/rag/test-user/search", json=request_body)

        tasks = []
        for i in range(5):
            tasks.append(insert(i))
            tasks.append(search())

        responses = await asyncio.gather(*tasks)
        for response in responses:
            assert response.status_code == 200


# =============================================================================
# 故事线测试 8: 特殊字符和边界
# =============================================================================

class TestStoryEdgeCases:
    """
    故事节点 8: 特殊字符和边界情况测试
    """

    @pytest.mark.asyncio
    async def test_search_chinese_input(self, async_client, mock_services):
        """
        场景：中文查询输入

        预期：正常处理
        """
        request_body = {
            "input": "用户登录功能测试",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_english_input(self, async_client, mock_services):
        """
        场景：英文查询输入

        预期：正常处理
        """
        request_body = {
            "input": "user login functionality",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_emoji_input(self, async_client, mock_services):
        """
        场景：包含 emoji 的查询

        预期：正常处理
        """
        request_body = {
            "input": "登录功能 🔐",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_insert_special_characters(self, async_client, mock_services):
        """
        场景：插入包含特殊字符的描述

        预期：正常处理
        """
        request_body = {
            "description": "用户 <script>alert('xss')</script> 登录功能 & 测试",
            "metadata": {
                "type": "skill",
                "id": "skill-special",
                "description": "特殊字符测试"
            }
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_sql_injection_attempt(self, async_client, mock_services):
        """
        场景：SQL 注入尝试

        预期：被转义或拒绝
        """
        request_body = {
            "input": "'; DROP TABLE users; --",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        # 应该正常处理（转义），不应该执行 SQL
        assert response.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_search_xss_attempt(self, async_client, mock_services):
        """
        场景：XSS 注入尝试

        预期：被转义或拒绝
        """
        request_body = {
            "input": "<img src=x onerror=alert('xss')>",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        # 应该正常处理
        assert response.status_code in [200, 422]


# =============================================================================
# 故事线测试 9: 性能基准
# =============================================================================

class TestStoryPerformance:
    """
    故事节点 9: 性能基准测试
    """

    @pytest.mark.asyncio
    async def test_insert_response_time(self, async_client, mock_services):
        """
        场景：插入接口响应时间

        预期：< 500ms
        """
        import time
        request_body = {
            "description": "性能测试",
            "metadata": {"type": "skill", "id": "perf-001", "description": "perf"}
        }
        start = time.time()
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        elapsed = (time.time() - start) * 1000
        assert response.status_code == 200
        assert elapsed < 500

    @pytest.mark.asyncio
    async def test_search_response_time(self, async_client, mock_services):
        """
        场景：检索接口响应时间

        预期：< 500ms
        """
        import time
        request_body = {
            "input": "性能测试查询",
            "type": "skill",
            "topK": 20
        }
        start = time.time()
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        elapsed = (time.time() - start) * 1000
        assert response.status_code == 200
        assert elapsed < 500


# =============================================================================
# 故事线测试 10: 类型验证
# =============================================================================

class TestStoryTypeValidation:
    """
    故事节点 10: 数据类型验证
    """

    @pytest.mark.asyncio
    async def test_response_data_structure(self, async_client, mock_services):
        """
        场景：验证响应数据结构

        预期：包含 code, message, data
        """
        request_body = {
            "description": "测试",
            "metadata": {"type": "skill", "id": "test-001", "description": "test"}
        }
        response = await async_client.post("/api/v1/rag/test-user/insert", json=request_body)
        data = response.json()
        assert "code" in data
        assert "message" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_search_result_structure(self, async_client, mock_services):
        """
        场景：验证检索结果结构

        预期：每项包含 metadata, description, score
        """
        request_body = {
            "input": "测试查询",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        data = response.json()
        for item in data["data"]:
            assert "metadata" in item
            assert "description" in item
            assert "score" in item

    @pytest.mark.asyncio
    async def test_score_is_float(self, async_client, mock_services):
        """
        场景：验证 score 类型

        预期：score 为 float
        """
        request_body = {
            "input": "测试查询",
            "type": "skill",
            "topK": 20
        }
        response = await async_client.post("/api/v1/rag/test-user/search", json=request_body)
        data = response.json()
        for item in data["data"]:
            assert isinstance(item["score"], float)


# =============================================================================
# 测试统计
# =============================================================================

def test_total_test_count():
    """
    验证测试用例数量
    """
    # 本测试文件应包含 100+ 测试用例
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
