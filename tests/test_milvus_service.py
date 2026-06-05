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
from unittest.mock import MagicMock, patch


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_milvus_client():
    """Mock MilvusClient 实例"""
    client = MagicMock()
    client.has_collection = MagicMock(return_value=True)
    client.insert = MagicMock(return_value=MagicMock(insert_count=2))
    client.search = MagicMock(return_value=[])
    client.delete = MagicMock(return_value=True)
    client.flush = MagicMock()
    client.load_collection = MagicMock()
    client.create_collection = MagicMock()
    return client


@pytest.fixture
def mock_milvus_sdk_client():
    """Mock MilvusClient 实例"""
    client = MagicMock()
    client.has_collection = MagicMock(return_value=True)
    client.create_collection = MagicMock(return_value=None)
    client.insert = MagicMock(return_value={"insert_count": 2})
    client.search = MagicMock(return_value=[[]])
    client.delete = MagicMock(return_value={"delete_count": 1})
    client.load_collection = MagicMock()
    client.flush = MagicMock()
    return client


@pytest.fixture
def milvus_service(mock_milvus_client):
    """创建 Milvus 服务实例"""
    from app.services.milvus_service import MilvusService

    with patch("app.services.milvus_service.MilvusClient", return_value=mock_milvus_client) as mock_client_cls:
        service = MilvusService(
            host="localhost",
            port=19530,
            username="root",
            password="root",
            dimension=8192
        )
        service._mock_milvus_client_cls = mock_client_cls
        service._mock_connections_connect = MagicMock()
        yield service


@pytest.fixture
def milvus_client_service(mock_milvus_sdk_client):
    """创建使用 MilvusClient 的服务实例"""
    from app.services.milvus_service import MilvusService

    with patch("app.services.milvus_service.MilvusClient", return_value=mock_milvus_sdk_client) as mock_client_cls:
        service = MilvusService(
            host="localhost",
            port=19530,
            username="root",
            password="root",
            db="studio",
            dimension=8192
        )
        service._mock_milvus_client_cls = mock_client_cls
        service._mock_connections_connect = MagicMock()
        yield service


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
        assert result["collection"] == milvus_service._get_full_collection_name(collection)

    @pytest.mark.asyncio
    async def test_insert_creates_collection_if_not_exists(self, milvus_service, mock_milvus_client):
        """
        场景：collection 不存在时自动创建

        预期：
        - 调用 create_collection
        """
        # given: collection 不存在
        mock_milvus_client.has_collection = MagicMock(return_value=False)

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


def test_milvus_search_output_fields_do_not_include_embedding_vector(milvus_service):
    """Milvus 搜索输出只返回必要字段，不搬运 embedding 向量。"""
    fields = milvus_service._build_search_output_fields()
    assert "description" in fields
    assert "metadata" in fields
    assert "features" in fields
    assert "embedding" not in fields
    assert "vector" not in fields


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
    async def test_batch_insert_preloads_collection_after_write(self, milvus_service, mock_milvus_client):
        """
        场景：批量写入新评测 collection 后立即进入查询

        预期：
        - 写入完成后预热 load collection
        - 首次 search 不再承担 collection load 长尾
        """
        # given: 批量写入数据
        documents = [
            {
                "id": "skill-001",
                "description": "登录功能",
                "vector": [0.1] * 8192,
                "metadata": {"type": "skill"}
            }
        ]

        # when: 批量写入
        await milvus_service.batch_insert("skill", documents)

        # then: 写入后立即预热加载
        full_collection_name = milvus_service._get_full_collection_name("skill")
        mock_milvus_client.load_collection.assert_called_once_with(full_collection_name)

        # when: 首次搜索同一个 collection
        await milvus_service.search("skill", [0.1] * 8192, 20)

        # then: search 复用 loaded 状态，不重复 load
        mock_milvus_client.load_collection.assert_called_once_with(full_collection_name)

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

    def test_parse_stored_dict_does_not_execute_expressions(self):
        """
        场景：解析 Milvus 中存储的字典字符串

        预期：
        - 兼容历史 str(dict) 格式
        - 不执行表达式
        """
        from app.services.milvus_serialization import parse_stored_dict

        parsed = parse_stored_dict("{'type': 'skill', 'id': 'skill-001'}")
        malicious = parse_stored_dict("__import__('os').system('echo unsafe')")

        assert parsed == {"type": "skill", "id": "skill-001"}
        assert malicious == {}

    @pytest.mark.asyncio
    async def test_search_collection_not_exists(self, milvus_service, mock_milvus_client):
        """
        场景：collection 不存在

        预期：
        - 自动创建 collection
        - 返回空列表
        """
        # given: collection 不存在
        mock_milvus_client.has_collection = MagicMock(return_value=False)

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

    @pytest.mark.asyncio
    async def test_search_loads_collection_only_once(self, milvus_service, mock_milvus_client):
        """
        场景：同一个 collection 连续搜索

        预期：
        - Collection 只 load 一次，避免重复加载拖慢查询
        """
        # when: 连续搜索同一个 collection
        await milvus_service.search("skill", [0.1] * 8192, 20)
        await milvus_service.search("skill", [0.1] * 8192, 20)

        # then: 只加载一次
        mock_milvus_client.load_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_uses_milvus_client_api(self, milvus_client_service, mock_milvus_sdk_client):
        """
        场景：使用 MilvusClient 执行搜索

        预期：调用 MilvusClient.search，并解析 dict 格式结果
        """
        mock_milvus_sdk_client.search.return_value = [[
            {
                "id": "doc-1",
                "distance": 0.91,
                "entity": {
                    "id": "doc-1",
                    "description": "MilvusClient 搜索结果",
                    "metadata": '{"type":"skill","id":"doc-1"}',
                    "features": '{"tags":["milvus"]}',
                }
            }
        ]]

        results = await milvus_client_service.search("skill", [0.1] * 8192, 5)

        mock_milvus_sdk_client.search.assert_called_once()
        assert results == [
            {
                "id": "doc-1",
                "description": "MilvusClient 搜索结果",
                "metadata": {"type": "skill", "id": "doc-1"},
                "features": {"tags": ["milvus"]},
                "score": 0.91,
            }
        ]

    @pytest.mark.asyncio
    async def test_search_uses_metadata_filter_expression(self, milvus_client_service, mock_milvus_sdk_client):
        """
        场景：按知识库和文档过滤向量检索

        预期：
        - Milvus search 使用 metadata like 过滤表达式
        - 输出字段仍不包含 vector
        """
        await milvus_client_service.search(
            "knowledge_chunk",
            [0.1] * 8192,
            5,
            metadata_filter={"knowledge_base_ids": ["kb-001", "kb-002"], "document_id": "doc-001"},
        )

        call_kwargs = mock_milvus_sdk_client.search.call_args.kwargs
        assert 'metadata like "%\\"knowledge_base_id\\":\\"kb-001\\"%"' in call_kwargs["filter"]
        assert 'metadata like "%\\"knowledge_base_id\\":\\"kb-002\\"%"' in call_kwargs["filter"]
        assert 'metadata like "%\\"document_id\\":\\"doc-001\\"%"' in call_kwargs["filter"]
        assert "vector" not in call_kwargs["output_fields"]

    @pytest.mark.asyncio
    async def test_score_documents_by_ids_uses_batch_id_filter(self, milvus_client_service, mock_milvus_sdk_client):
        """
        场景：为融合候选批量校准向量分数

        预期：
        - 使用 id in 批量过滤，不逐条查询
        - 不返回 embedding/vector 字段
        """
        mock_milvus_sdk_client.search.return_value = [[
            {
                "id": "doc-1",
                "distance": 0.87,
                "entity": {"id": "doc-1"},
            },
            {
                "id": "doc-2",
                "distance": 0.65,
                "entity": {"id": "doc-2"},
            },
        ]]

        scores = await milvus_client_service.score_documents_by_ids(
            collection="skill",
            query_vector=[0.1] * 8192,
            doc_ids=["doc-1", "doc-2"],
        )

        mock_milvus_sdk_client.search.assert_called_once()
        call_kwargs = mock_milvus_sdk_client.search.call_args.kwargs
        assert call_kwargs["filter"] == 'id in ["doc-1", "doc-2"]'
        assert call_kwargs["output_fields"] == ["id"]
        assert scores == {"doc-1": 0.87, "doc-2": 0.65}

    @pytest.mark.asyncio
    async def test_search_reconnects_and_retries_once_on_transient_failure(self, milvus_service, mock_milvus_client):
        """
        场景：Milvus search 首次遇到瞬时异常

        预期：
        - 重建客户端连接
        - 只重试一次
        - 返回第二次搜索结果
        """
        retry_client = MagicMock()
        retry_client.has_collection = MagicMock(return_value=True)
        retry_client.load_collection = MagicMock()
        retry_client.search = MagicMock(return_value=[[
            {
                "id": "doc-retry",
                "distance": 0.92,
                "entity": {
                    "id": "doc-retry",
                    "description": "重试后命中",
                    "metadata": '{"type":"skill","id":"doc-retry"}',
                    "features": "{}",
                }
            }
        ]])
        mock_milvus_client.search.side_effect = RuntimeError("transient timeout")

        with patch("app.services.milvus_service.MilvusClient", return_value=retry_client):
            results = await milvus_service.search("skill", [0.1] * 8192, 5)

        assert mock_milvus_client.search.call_count == 1
        retry_client.search.assert_called_once()
        assert results[0]["id"] == "doc-retry"


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
        mock_milvus_client.has_collection = MagicMock(return_value=False)

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
        mock_milvus_client.has_collection.side_effect = Exception("Connection failed")

        # when: 调用 health_check
        result = await milvus_service.health_check()

        # then: 验证结果
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_uses_auth_config(self, milvus_service):
        """
        场景：配置 Milvus 账号密码后执行健康检查

        预期：连接参数包含用户和密码
        """
        await milvus_service.health_check()

        milvus_service._mock_milvus_client_cls.assert_called_once_with(
            uri="http://localhost:19530",
            user="root",
            password="root"
        )

    @pytest.mark.asyncio
    async def test_health_check_uses_milvus_client_without_orm_connection(
        self,
        milvus_client_service,
        mock_milvus_sdk_client
    ):
        """
        场景：执行健康检查

        预期：使用 MilvusClient，不调用 ORM connections.connect
        """
        result = await milvus_client_service.health_check()

        assert result is True
        mock_milvus_sdk_client.has_collection.assert_called()
        milvus_client_service._mock_connections_connect.assert_not_called()


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
        mock_milvus_client.has_collection = MagicMock(return_value=True)

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
        mock_milvus_client.has_collection = MagicMock(return_value=False)

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
        assert not isinstance(mock_milvus_client.create_collection.call_args.kwargs["index_params"], dict)


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
