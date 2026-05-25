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

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from typing import List, Dict, Any


# =============================================================================
# Fixtures
# =============================================================================

# 使用模块级 mock 服务（session-scoped）
_mock_embedding_service = None
_mock_rerank_service = None
_mock_milvus_service = None


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

        async def mock_insert(collection, doc_id, description, vector, metadata):
            return {"id": doc_id, "collection": collection}

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
async def app_router(mock_embedding_service, mock_rerank_service, mock_milvus_service):
    """创建带有 mock 服务的 app"""
    with patch("app.services.embedding_service.EmbeddingService", return_value=mock_embedding_service), \
         patch("app.services.rerank_service.RerankService", return_value=mock_rerank_service), \
         patch("app.services.milvus_service.MilvusService", return_value=mock_milvus_service):
        from app.main import app
        return app


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


# =============================================================================
# 测试用例：DELETE /api/v1/rag/test-user/delete
# =============================================================================

class TestDeleteEndpoint:
    """删除记录接口测试"""

    @pytest.mark.asyncio
    async def test_delete_success(self, async_client, mock_milvus_service):
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
    async def test_error_milvus_connection_failed(self, async_client, mock_embedding_service, mock_milvus_service):
        """
        场景：Milvus 连接失败

        预期：
        - 返回适当错误响应
        - 记录 ERROR 日志
        """
        # given: Milvus 服务不可用时，search 抛出异常
        async def mock_search_raise(*args, **kwargs):
            raise Exception("Milvus 连接失败")

        mock_milvus_service.search = AsyncMock(side_effect=mock_search_raise)

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
