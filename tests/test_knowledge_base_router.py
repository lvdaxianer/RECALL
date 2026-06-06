"""
知识库 CRUD 路由测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def async_client(tmp_path, monkeypatch):
    """构建使用临时 SQLite 状态库的异步 HTTP 客户端。"""
    monkeypatch.setattr(
        "app.routers.knowledge_bases.KNOWLEDGE_BASE_DB_PATH",
        str(tmp_path / "kb.sqlite"),
    )
    monkeypatch.setattr(
        "app.routers.knowledge_base_documents.KNOWLEDGE_BASE_DB_PATH",
        str(tmp_path / "kb.sqlite"),
    )
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_create_list_update_delete_knowledge_base(async_client):
    """知识库路由支持创建、列表、更新和软删除。"""
    created_response = await async_client.post(
        "/api/v1/kb",
        json={"name": "产品知识库", "description": "产品文档", "owner_id": "user-001"},
    )
    created = created_response.json()["data"]

    listing_response = await async_client.get("/api/v1/kb?owner_id=user-001")
    updated_response = await async_client.patch(
        f"/api/v1/kb/{created['id']}",
        json={"description": "更新后的描述", "owner_id": "user-001"},
    )
    deleted_response = await async_client.delete(f"/api/v1/kb/{created['id']}?owner_id=user-001")

    assert created_response.status_code == 200
    assert created["name"] == "产品知识库"
    assert listing_response.json()["data"][0]["id"] == created["id"]
    assert updated_response.json()["data"]["description"] == "更新后的描述"
    assert deleted_response.json()["data"]["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_knowledge_base_removes_queued_documents(async_client):
    """删除知识库时路由同步删除该库下排队文档。"""
    kb = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "KB", "description": "desc", "owner_id": "u1"},
        )
    ).json()["data"]
    document = (
        await async_client.post(
            f"/api/v1/kb/{kb['id']}/documents",
            json={"name": "a.md", "content": "# A\n正文", "content_type": "text/markdown", "owner_id": "u1"},
        )
    ).json()["data"]

    deleted_response = await async_client.delete(f"/api/v1/kb/{kb['id']}?owner_id=u1")
    documents_response = await async_client.get(f"/api/v1/kb/{kb['id']}/documents")
    chunks_response = await async_client.get(f"/api/v1/kb/{kb['id']}/documents/{document['id']}/chunks")

    deleted = deleted_response.json()["data"]
    assert deleted_response.status_code == 200
    assert deleted["deleted_document_count"] == 1
    assert deleted["deleted_chunk_count"] == 0
    assert documents_response.json()["data"] == []
    assert chunks_response.json()["data"] == []


@pytest.mark.asyncio
async def test_delete_knowledge_base_cleans_external_indexes(async_client, monkeypatch):
    """删除知识库时同步清理 ES、Milvus 和 LightRAG-lite 图索引中的 chunk。"""
    deleted_es_ids = []
    deleted_milvus_ids = []
    deleted_graph_ids = []

    class FakeESService:
        async def delete_document(self, index_name, doc_id):
            deleted_es_ids.append((index_name, doc_id))
            return True

    class FakeMilvusService:
        async def delete(self, collection, doc_id):
            deleted_milvus_ids.append((collection, doc_id))
            return True

    class FakeGraphService:
        def delete_document(self, doc_id):
            deleted_graph_ids.append(doc_id)
            return True

    monkeypatch.setattr("app.routers.knowledge_bases.get_es_service", lambda: FakeESService(), raising=False)
    monkeypatch.setattr("app.routers.knowledge_bases.MilvusService", lambda: FakeMilvusService(), raising=False)
    monkeypatch.setattr(
        "app.routers.knowledge_bases.get_graph_retrieval_service",
        lambda: FakeGraphService(),
        raising=False,
    )

    kb = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "KB", "description": "desc", "owner_id": "u1"},
        )
    ).json()["data"]
    document = (
        await async_client.post(
            f"/api/v1/kb/{kb['id']}/documents",
            json={"name": "a.md", "content": "# A\n正文", "content_type": "text/markdown", "owner_id": "u1"},
        )
    ).json()["data"]
    chunks = (
        await async_client.get(f"/api/v1/kb/{kb['id']}/documents/{document['id']}/chunks")
    ).json()["data"]

    response = await async_client.delete(f"/api/v1/kb/{kb['id']}?owner_id=u1")

    chunk_ids = [chunk["id"] for chunk in chunks]
    assert response.status_code == 200
    assert [doc_id for _, doc_id in deleted_es_ids] == chunk_ids
    assert [doc_id for _, doc_id in deleted_milvus_ids] == chunk_ids
    assert deleted_graph_ids == chunk_ids


@pytest.mark.asyncio
async def test_publish_knowledge_base_marks_it_available(async_client):
    """知识库发布接口返回已发布状态。"""
    created = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "产品知识库", "description": "产品文档", "owner_id": "user-001"},
        )
    ).json()["data"]

    response = await async_client.post(f"/api/v1/kb/{created['id']}/publish", json={"owner_id": "user-001"})

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "published"


@pytest.mark.asyncio
async def test_publish_knowledge_base_keeps_queued_documents_for_worker(async_client, monkeypatch):
    """发布知识库不应在请求线程同步解析大量文档。"""

    class FakeESService:
        async def index_documents(self, index_name, documents):
            return len(documents)

    class FakeMilvusService:
        async def batch_insert(self, collection, documents):
            return {"inserted_count": len(documents)}

    class FakeEmbeddingService:
        async def encode(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr("app.routers.knowledge_bases.get_es_service", lambda: FakeESService(), raising=False)
    monkeypatch.setattr("app.routers.knowledge_bases.MilvusService", lambda: FakeMilvusService(), raising=False)
    monkeypatch.setattr("app.routers.knowledge_bases.EmbeddingService", lambda: FakeEmbeddingService(), raising=False)

    kb = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "KB", "description": "desc", "owner_id": "u1"},
        )
    ).json()["data"]
    document = (
        await async_client.post(
            f"/api/v1/kb/{kb['id']}/documents",
            json={"name": "a.md", "content": "# A\n正文", "content_type": "text/markdown", "owner_id": "u1"},
        )
    ).json()["data"]

    response = await async_client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": "u1"})
    detail = (
        await async_client.get(f"/api/v1/kb/{kb['id']}/documents/{document['id']}")
    ).json()["data"]

    assert response.status_code == 200
    assert detail["parse_status"] in {"queued", "processing", "indexed"}


@pytest.mark.asyncio
async def test_update_knowledge_base_rejects_non_owner(async_client):
    """知识库更新路由拒绝非 owner 请求。"""
    created = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "产品知识库", "description": "产品文档", "owner_id": "user-001"},
        )
    ).json()["data"]

    response = await async_client.patch(
        f"/api/v1/kb/{created['id']}",
        json={"description": "越权修改", "owner_id": "user-002"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_knowledge_base_settings_returns_defaults(async_client):
    """知识库设置路由返回默认分块与检索设置。"""
    created = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "产品知识库", "description": "产品文档", "owner_id": "user-001"},
        )
    ).json()["data"]

    response = await async_client.get(f"/api/v1/kb/{created['id']}/settings")

    settings = response.json()["data"]
    assert response.status_code == 200
    assert settings["knowledge_base_id"] == created["id"]
    assert settings["chunk_size"] == 1000
    assert settings["overlap"] == 150
    assert settings["top_k_default"] == 5


@pytest.mark.asyncio
async def test_patch_knowledge_base_settings_updates_overlap(async_client):
    """知识库设置路由支持局部更新 overlap。"""
    created = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "产品知识库", "description": "产品文档", "owner_id": "user-001"},
        )
    ).json()["data"]

    response = await async_client.patch(
        f"/api/v1/kb/{created['id']}/settings",
        json={"overlap": 240},
    )

    settings = response.json()["data"]
    assert response.status_code == 200
    assert settings["overlap"] == 240
    assert settings["chunk_size"] == 1000


@pytest.mark.asyncio
async def test_patch_knowledge_base_settings_rejects_invalid_overlap(async_client):
    """知识库设置路由拒绝 overlap 不小于 chunk_size。"""
    created = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "产品知识库", "description": "产品文档", "owner_id": "user-001"},
        )
    ).json()["data"]

    response = await async_client.patch(
        f"/api/v1/kb/{created['id']}/settings",
        json={"chunk_size": 500, "overlap": 500},
    )

    assert response.status_code == 422
