"""
应用启动图谱重建测试

@author lvdaxianerplus
@date 2026-06-01
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Config
from app.main import _close_model_http_clients
from app.main import _rebuild_graph_index_on_startup


@pytest.mark.asyncio
async def test_startup_graph_rebuild_is_disabled_by_default(monkeypatch):
    """默认关闭启动图谱重建，避免启动强依赖 ES 数据读取"""
    monkeypatch.setattr(Config, "RAG_GRAPH_REBUILD_ON_STARTUP", False)
    es_service = MagicMock()
    es_service.list_documents = AsyncMock(return_value=[])
    graph_service = MagicMock()

    result = await _rebuild_graph_index_on_startup(es_service, graph_service)

    assert result is None
    es_service.list_documents.assert_not_called()
    graph_service.rebuild.assert_not_called()


@pytest.mark.asyncio
async def test_startup_graph_rebuild_loads_skill_and_asset_documents(monkeypatch):
    """开启启动图谱重建后，从 ES skill/asset 索引恢复内存图谱"""
    monkeypatch.setattr(Config, "RAG_GRAPH_REBUILD_ON_STARTUP", True)
    monkeypatch.setattr(Config, "RAG_GRAPH_REBUILD_LIMIT", 10)
    monkeypatch.setattr(Config, "ES_SKILL_INDEX", "rag_skills")
    monkeypatch.setattr(Config, "ES_ASSET_INDEX", "rag_assets")
    es_service = MagicMock()
    es_service.list_documents = AsyncMock(side_effect=[
        [{"id": "skill-1", "description": "JWT 登录", "metadata": {"type": "skill"}, "features": {}}],
        [{"id": "asset-1", "description": "登录素材", "metadata": {"type": "asset"}, "features": {}}],
    ])
    graph_service = MagicMock()
    graph_service.rebuild = MagicMock(return_value={"document_count": 2})

    result = await _rebuild_graph_index_on_startup(es_service, graph_service)

    assert result == {"document_count": 2}
    assert es_service.list_documents.await_count == 2
    es_service.list_documents.assert_any_await("rag_skills", limit=10)
    es_service.list_documents.assert_any_await("rag_assets", limit=10)
    graph_service.rebuild.assert_called_once_with([
        {"id": "skill-1", "description": "JWT 登录", "metadata": {"type": "skill"}, "features": {}},
        {"id": "asset-1", "description": "登录素材", "metadata": {"type": "asset"}, "features": {}},
    ])


@pytest.mark.asyncio
async def test_shutdown_closes_reused_model_http_clients(monkeypatch):
    """应用关闭时释放已复用的 Embedding/Rerank HTTP 客户端连接池"""
    search_embedding = MagicMock()
    search_embedding.close = AsyncMock()
    insert_embedding = MagicMock()
    insert_embedding.close = AsyncMock()
    rerank = MagicMock()
    rerank.close = AsyncMock()

    import app.routers.rag_insert as rag_insert
    import app.services.rag_search_pipeline_service as search_pipeline

    monkeypatch.setattr(search_pipeline, "_embedding_service", search_embedding)
    monkeypatch.setattr(search_pipeline, "_rerank_service", rerank)
    monkeypatch.setattr(rag_insert, "_embedding_service", insert_embedding)

    await _close_model_http_clients()

    search_embedding.close.assert_awaited_once()
    insert_embedding.close.assert_awaited_once()
    rerank.close.assert_awaited_once()
