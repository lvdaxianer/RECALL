"""
Milvus 服务测试用例

测试覆盖：
- insert() 单条插入
- batch_insert() 批量插入
- search() 向量搜索
- delete() 删除记录
- collection_exists() collection 检查
- create_collection() collection 创建
- health_check() 健康检查

@author lvdaxianerplus
@date 2026-04-14
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_milvus_client():
    """Mock Milvus 客户端"""
    client = MagicMock()
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.has_collection = AsyncMock(return_value=True)
    client.create_collection = AsyncMock(return_value=True)
    client.insert = AsyncMock(return_value={
        "ids": ["test-id-1"]
    })
    client.search = AsyncMock(return_value=[
        [["0.85", "0.72"]],
        [["skill-001", "skill-002"]]
    ])
    client.delete = AsyncMock(return_value=True)
    return client


@pytest.fixture
def milvus_service(mock_milvus_client):
    """创建 Milvus 服务实例"""
    with patch("pymilvus.connections.connect", new_callable=AsyncMock) as mock_connect:
        from app.services.milvus_service import MilvusService
        service = MilvusService(
            host="localhost",
            port=19530,
            dimension=8192
        )
        # 替换内部客户端
        service._client = mock_milvus_client
        return service


# =============================================================================
# 测试用例：insert()
# =============================================================================

class TestMilvusInsert:
    """Milvus 插入测试"""

    @pytest.mark.asyncio
    async def test_insert_success(self, milvus_service, mock_milvus_client):
        """
        场景：单条插入成功

        预期：
        - 返回插入结果
        - 包含 id 和 collection
        """
        # given: 有效的插入数据
        collection = "skill"
        doc_id = "skill-001"
        description = "用户登录功能"
        vector = [0.1] * 8192
        metadata = {"type": "skill", "id": "skill-001", "description": "登录相关"}

        # when: 调用 insert
        result = await milvus_service.insert(
            collection=collection,
            doc_id=doc_id,
            description=description,
            vector=vector,
            metadata=metadata
        )

        # then: 验证结果
        assert result["id"] == doc_id
        assert result["collection"] == collection

    @pytest.mark.asyncio
    async def test_insert_creates_collection_if_not_exists(self, milvus_service, mock_milvus_client):
        """
        场景：collection 不存在时自动创建

        预期：
        - 调用 create_collection
        """
        # given: collection 不存在
        mock_milvus_client.has_collection = AsyncMock(return_value=False)

        # when: 调用 insert
        await milvus_service.insert(
            collection="new_collection",
            doc_id="doc-1",
            description="test",
            vector=[0.1] * 8192,
            metadata={}
        )

        # then: 验证 create_collection 被调用
        mock_milvus_client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_invalid_dimension(self, milvus_service):
        """
        场景：向量维度不匹配

        预期：
        - 抛出 ValueError
        """
        # given: 错误维度的向量
        wrong_vector = [0.1] * 1024  # 应该是 8192

        # when/then: 调用 insert
        with pytest.raises(ValueError):
            await milvus_service.insert(
                collection="skill",
                doc_id="skill-001",
                description="test",
                vector=wrong_vector,
                metadata={}
            )


# =============================================================================
# 测试用例：batch_insert()
# =============================================================================

class TestMilvusBatchInsert:
    """Milvus 批量插入测试"""

    @pytest.mark.asyncio
    async def test_batch_insert_success(self, milvus_service, mock_milvus_client):
        """
        场景：批量插入成功

        预期：
        - 返回插入数量
        """
        # given: 批量数据
        collection = "skill"
        documents = [
            {
                "id": "skill-001",
                "description": "登录功能",
                "vector": [0.1] * 8192,
                "metadata": {"type": "skill"}
            },
            {
                "id": "skill-002",
                "description": "注册功能",
                "vector": [0.2] * 8192,
                "metadata": {"type": "skill"}
            }
        ]

        # when: 调用 batch_insert
        result = await milvus_service.batch_insert(collection, documents)

        # then: 验证结果
        assert result["inserted_count"] == 2

    @pytest.mark.asyncio
    async def test_batch_insert_empty_list(self, milvus_service):
        """
        场景：空列表

        预期：
        - 返回 inserted_count = 0
        """
        # given: 空列表
        documents = []

        # when: 调用 batch_insert
        result = await milvus_service.batch_insert("skill", documents)

        # then: 验证结果
        assert result["inserted_count"] == 0

    @pytest.mark.asyncio
    async def test_batch_insert_exceeds_limit(self, milvus_service):
        """
        场景：超过 1000 条上限

        预期：
        - 抛出 ValueError
        """
        # given: 超过 1000 条
        documents = [
            {
                "id": f"skill-{i}",
                "description": f"功能{i}",
                "vector": [0.1] * 8192,
                "metadata": {"type": "skill"}
            }
            for i in range(1001)
        ]

        # when/then: 调用 batch_insert
        with pytest.raises(ValueError):
            await milvus_service.batch_insert("skill", documents)


# =============================================================================
# 测试用例：search()
# =============================================================================

class TestMilvusSearch:
    """Milvus 搜索测试"""

    @pytest.mark.asyncio
    async def test_search_success(self, milvus_service, mock_milvus_client):
        """
        场景：搜索成功

        预期：
        - 返回搜索结果列表
        - 每项包含 id、description、metadata、score
        """
        # given: 搜索参数
        collection = "skill"
        query_vector = [0.1] * 8192
        top_k = 20

        # when: 调用 search
        results = await milvus_service.search(collection, query_vector, top_k)

        # then: 验证结果格式
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_collection_not_exists(self, milvus_service, mock_milvus_client):
        """
        场景：collection 不存在

        预期：
        - 自动创建 collection
        - 返回空列表
        """
        # given: collection 不存在
        mock_milvus_client.has_collection = AsyncMock(return_value=False)

        # when: 调用 search
        results = await milvus_service.search("new_collection", [0.1] * 8192, 20)

        # then: 验证 create_collection 被调用
        mock_milvus_client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_multiple_collections(self, milvus_service, mock_milvus_client):
        """
        场景：多 collection 并行搜索

        预期：
        - 返回合并结果
        """
        # given: 多个 collections
        collections = ["skill", "asset"]

        # when: 调用 search
        results = await milvus_service.search(
            collection=collections,  # 支持列表
            query_vector=[0.1] * 8192,
            top_k=20
        )

        # then: 验证结果
        assert isinstance(results, list)


# =============================================================================
# 测试用例：delete()
# =============================================================================

class TestMilvusDelete:
    """Milvus 删除测试"""

    @pytest.mark.asyncio
    async def test_delete_success(self, milvus_service, mock_milvus_client):
        """
        场景：删除成功

        预期：
        - 返回 True
        """
        # given: 删除参数
        collection = "skill"
        doc_id = "skill-001"

        # when: 调用 delete
        result = await milvus_service.delete(collection, doc_id)

        # then: 验证结果
        assert result is True
        mock_milvus_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_collection_not_exists(self, milvus_service, mock_milvus_client):
        """
        场景：collection 不存在

        预期：
        - 返回 False
        """
        # given: collection 不存在
        mock_milvus_client.has_collection = AsyncMock(return_value=False)

        # when: 调用 delete
        result = await milvus_service.delete("non_existent", "doc-1")

        # then: 验证结果
        assert result is False


# =============================================================================
# 测试用例：health_check()
# =============================================================================

class TestMilvusHealthCheck:
    """Milvus 健康检查测试"""

    @pytest.mark.asyncio
    async def test_health_check_success(self, milvus_service, mock_milvus_client):
        """
        场景：健康检查成功

        预期：
        - 返回 True
        """
        # when: 调用 health_check
        result = await milvus_service.health_check()

        # then: 验证结果
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_connection_failed(self, milvus_service, mock_milvus_client):
        """
        场景：连接失败

        预期：
        - 返回 False
        """
        # given: 连接失败
        mock_milvus_client.connect = AsyncMock(side_effect=Exception("Connection failed"))

        # when: 调用 health_check
        result = await milvus_service.health_check()

        # then: 验证结果
        assert result is False


# =============================================================================
# 测试用例：collection 操作
# =============================================================================

class TestMilvusCollection:
    """Collection 操作测试"""

    @pytest.mark.asyncio
    async def test_collection_exists_true(self, milvus_service, mock_milvus_client):
        """
        场景：collection 存在

        预期：
        - 返回 True
        """
        # given: collection 存在
        mock_milvus_client.has_collection = AsyncMock(return_value=True)

        # when: 调用 collection_exists
        result = await milvus_service.collection_exists("skill")

        # then: 验证结果
        assert result is True

    @pytest.mark.asyncio
    async def test_collection_exists_false(self, milvus_service, mock_milvus_client):
        """
        场景：collection 不存在

        预期：
        - 返回 False
        """
        # given: collection 不存在
        mock_milvus_client.has_collection = AsyncMock(return_value=False)

        # when: 调用 collection_exists
        result = await milvus_service.collection_exists("non_existent")

        # then: 验证结果
        assert result is False

    @pytest.mark.asyncio
    async def test_create_collection_success(self, milvus_service, mock_milvus_client):
        """
        场景：创建 collection 成功

        预期：
        - 返回 True
        """
        # given: 新 collection 名称
        collection_name = "new_collection"

        # when: 调用 create_collection
        result = await milvus_service.create_collection(collection_name)

        # then: 验证结果
        assert result is True
        mock_milvus_client.create_collection.assert_called_once()


# =============================================================================
# 测试用例：向量维度验证
# =============================================================================

class TestMilvusDimension:
    """向量维度测试"""

    @pytest.mark.asyncio
    async def test_dimension_validation_success(self, milvus_service):
        """
        场景：正确的向量维度

        预期：
        - 验证通过
        """
        # given: 正确维度
        correct_vector = [0.1] * 8192

        # when/then: 验证通过（不抛异常）
        milvus_service._validate_dimension(correct_vector)

    @pytest.mark.asyncio
    async def test_dimension_validation_failure(self, milvus_service):
        """
        场景：错误的向量维度

        预期：
        - 抛出 ValueError
        """
        # given: 错误维度
        wrong_vector = [0.1] * 1024

        # when/then: 验证失败
        with pytest.raises(ValueError):
            milvus_service._validate_dimension(wrong_vector)
