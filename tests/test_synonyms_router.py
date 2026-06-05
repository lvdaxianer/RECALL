"""
同义词 CRUD 路由测试

Author: lvdaxianerplus
Date: 2026-06-05
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def async_client(tmp_path, monkeypatch):
    """构建使用临时 SQLite 状态库的异步 HTTP 客户端。"""
    monkeypatch.setattr(
        "app.routers.synonyms.KNOWLEDGE_BASE_DB_PATH",
        str(tmp_path / "kb.sqlite"),
        raising=False,
    )
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_synonyms_router_creates_lists_updates_and_deletes_group(async_client):
    """同义词路由支持创建、列表、禁用和删除。"""
    created_response = await async_client.post(
        "/api/v1/synonyms",
        json={
            "knowledge_base_id": None,
            "canonical": "作用",
            "terms": ["干啥用的", "有什么作用"],
            "owner_id": "u1",
        },
    )
    created = created_response.json()["data"]

    listed_response = await async_client.get("/api/v1/synonyms")
    patched_response = await async_client.patch(
        f"/api/v1/synonyms/{created['id']}",
        json={"enabled": False},
    )
    deleted_response = await async_client.delete(f"/api/v1/synonyms/{created['id']}")

    assert created_response.status_code == 200
    assert created["canonical"] == "作用"
    assert created["terms"] == ["干啥用的", "有什么作用"]
    assert listed_response.json()["data"][0]["id"] == created["id"]
    assert patched_response.json()["data"]["enabled"] is False
    assert deleted_response.json()["data"]["id"] == created["id"]
