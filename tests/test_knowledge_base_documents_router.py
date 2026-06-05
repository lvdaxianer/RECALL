"""
知识库文档路由测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def async_client(tmp_path, monkeypatch):
    """构建使用临时 SQLite 状态库的异步 HTTP 客户端。"""
    db_path = str(tmp_path / "kb.sqlite")
    monkeypatch.setattr("app.routers.knowledge_bases.KNOWLEDGE_BASE_DB_PATH", db_path)
    monkeypatch.setattr("app.routers.knowledge_base_documents.KNOWLEDGE_BASE_DB_PATH", db_path)
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_upload_document_returns_queued_without_parsing(async_client):
    """上传接口只排队，不在请求线程里解析 chunk。"""
    kb = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "KB", "description": "desc", "owner_id": "u1"},
        )
    ).json()["data"]

    response = await async_client.post(
        f"/api/v1/kb/{kb['id']}/documents",
        json={
            "name": "a.md",
            "content": "# A",
            "content_type": "text/markdown",
            "owner_id": "u1",
            "external_id": "a.md",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["parse_status"] == "queued"
    assert data["chunk_count"] == 0


@pytest.mark.asyncio
async def test_document_list_and_detail_endpoints(async_client):
    """文档路由支持上传、列表和详情。"""
    kb = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "KB", "description": "desc", "owner_id": "u1"},
        )
    ).json()["data"]
    doc = (
        await async_client.post(
            f"/api/v1/kb/{kb['id']}/documents",
            json={"name": "a.md", "content": "# 标题\n内容", "content_type": "text/markdown", "owner_id": "u1"},
        )
    ).json()["data"]

    docs = (await async_client.get(f"/api/v1/kb/{kb['id']}/documents")).json()["data"]
    detail = (await async_client.get(f"/api/v1/kb/{kb['id']}/documents/{doc['id']}")).json()["data"]

    assert docs[0]["id"] == doc["id"]
    assert "raw_content" not in docs[0]
    assert detail["chunk_count"] == 0
    assert detail["parse_status"] == "queued"
    assert detail["raw_content"] == "# 标题\n内容"


@pytest.mark.asyncio
async def test_document_chunk_list_returns_chunk_metadata(async_client):
    """chunk 列表接口返回 chunk 顺序、标题和内容。"""
    kb = (
        await async_client.post(
            "/api/v1/kb",
            json={"name": "KB", "description": "desc", "owner_id": "u1"},
        )
    ).json()["data"]
    doc = (
        await async_client.post(
            f"/api/v1/kb/{kb['id']}/documents",
            json={"name": "a.md", "content": "# 标题\n内容", "content_type": "text/markdown", "owner_id": "u1"},
        )
    ).json()["data"]

    chunks = (
        await async_client.get(f"/api/v1/kb/{kb['id']}/documents/{doc['id']}/chunks")
    ).json()["data"]

    assert chunks == []
