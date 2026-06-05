"""
SEE 时间线页面路由测试
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def async_client():
    """构建异步 HTTP 客户端。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_see_timeline_page_exposes_phase_f_controls(async_client):
    """SEE 时间线页面包含检索、阶段展示、撤销缓存和 Bad feedback 控件"""
    response = await async_client.get("/see/timeline")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "SEE Timeline" in html
    assert "data-event=\"request.created\"" in html
    assert "data-event=\"query.decomposition\"" in html
    assert "data-event=\"rerank.completed\"" in html
    assert "data-event=\"recommendation.completed\"" in html
    assert "/api/v1/rag/{user_id}/search/optimize/stream" in html
    assert "/api/v1/rag/cache/rerank/invalidate-by-request/" in html
    assert "/api/v1/rag/{user_id}/feedback/bad-case" in html
    assert "/api/v1/agent/{user_id}/sessions" in html
    assert "/api/v1/agent/{user_id}/sessions/{session_id}/events" in html


@pytest.mark.asyncio
async def test_see_timeline_static_asset_is_served(async_client):
    """SEE 时间线静态 JS 能被 FastAPI 挂载访问"""
    response = await async_client.get("/static/see-timeline.js")

    assert response.status_code == 200
    assert "EventSource" not in response.text
    assert "fetch(" in response.text
    assert "replaySelectedRun" in response.text
    assert "renderTimelineEvent" in response.text
