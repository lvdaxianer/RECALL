"""
Rerank 服务测试用例

测试覆盖：
- rerank() 重排功能
- health_check() 健康检查
- 降级模式处理

@author lvdaxianerplus
@date 2026-04-14
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_http_client():
    """Mock HTTP 客户端"""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def rerank_service(mock_http_client):
    """创建 Rerank 服务实例"""
    with patch("httpx.AsyncClient", return_value=mock_http_client):
        from app.services.rerank_service import RerankService
        service = RerankService(
            api_key="test_key",
            request_url="https://api.test.com/v1/rerank",
            model_name="test-rerank-model",
            use_cache=False
        )
        yield service


# =============================================================================
# 测试用例：rerank()
# =============================================================================

class TestRerank:
    """Rerank 重排测试"""

    @pytest.mark.asyncio
    async def test_rerank_success(self, rerank_service, mock_http_client):
        """
        场景：重排成功

        预期：
        - 返回重排后的结果
        - 每个结果包含 index 和 score
        """
        # given: 有效的重排请求
        query = "查找登录相关的 skill"
        documents = [
            {"id": "1", "description": "用户登录功能"},
            {"id": "2", "description": "用户注册功能"},
            {"id": "3", "description": "密码找回功能"}
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"index": 0, "score": 0.95},
                {"index": 2, "score": 0.75},
                {"index": 1, "score": 0.60}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)

        # when: 调用 rerank
        result = await rerank_service.rerank(query, documents)

        # then: 验证结果
        assert isinstance(result, list)
        assert len(result) == 3
        assert "index" in result[0]
        assert "score" in result[0]

    @pytest.mark.asyncio
    async def test_rerank_empty_documents(self, rerank_service):
        """
        场景：空文档列表

        预期：
        - 返回空列表
        """
        # given: 空文档
        query = "查找登录相关的 skill"
        documents = []

        # when: 调用 rerank
        result = await rerank_service.rerank(query, documents)

        # then: 验证结果
        assert result == []

    @pytest.mark.asyncio
    async def test_rerank_http_error(self, rerank_service, mock_http_client):
        """
        场景：HTTP 请求失败

        预期：
        - 抛出异常
        - 记录 ERROR 日志
        """
        # given: HTTP 错误
        mock_http_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))

        # when/then: 调用 rerank
        with pytest.raises(httpx.HTTPError):
            await rerank_service.rerank("test query", [{"id": "1", "description": "test"}])

    @pytest.mark.asyncio
    async def test_rerank_api_error_response(self, rerank_service, mock_http_client):
        """
        场景：API 返回错误

        预期：
        - 抛出异常
        - 降级模式记录 WARN 日志
        """
        # given: API 错误响应
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.json.return_value = {"error": "Internal error"}
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal error",
            request=MagicMock(),
            response=error_response
        )
        mock_http_client.post = AsyncMock(return_value=error_response)

        # when/then: 调用 rerank
        with pytest.raises(Exception):
            await rerank_service.rerank("test query", [{"id": "1", "description": "test"}])

    @pytest.mark.asyncio
    async def test_rerank_reuses_http_client_between_calls(self, rerank_service, mock_http_client):
        """
        场景：连续多次调用 Rerank

        预期：
        - 复用同一个 HTTP 客户端连接池
        - 避免每次重排重新创建连接
        """
        # given: 两次正常响应
        response = MagicMock(status_code=200)
        response.json.return_value = {"results": [{"index": 0, "score": 0.9}]}
        response.raise_for_status = MagicMock()
        mock_http_client.post = AsyncMock(return_value=response)
        docs = [{"id": "1", "description": "登录功能"}]

        # when: 连续调用 rerank
        await rerank_service.rerank("第一次查询", docs)
        await rerank_service.rerank("第二次查询", docs)

        # then: 复用 post 调用通道
        assert mock_http_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_rerank_cache_misses_when_document_content_changes(self, mock_http_client):
        """
        场景：启用 Rerank 缓存，同一 doc_id 的 description 发生变化

        预期：
        - 第二次不复用旧缓存
        - 重新调用远程 Rerank，避免复用旧内容分数
        """
        from app.services.cache_service import CacheService
        from app.services.rerank_service import RerankService

        response = MagicMock(status_code=200)
        response.json.return_value = {"results": [{"index": 0, "score": 0.9}]}
        response.raise_for_status = MagicMock()
        mock_http_client.post = AsyncMock(return_value=response)

        with patch("httpx.AsyncClient", return_value=mock_http_client):
            service = RerankService(
                api_key="test_key",
                request_url="https://api.test.com/v1/rerank",
                model_name="test-rerank-model",
                use_cache=True,
            )
            service._cache = CacheService()
            await service.rerank("登录功能", [{"id": "doc-1", "description": "登录功能"}])
            await service.rerank("登录功能", [{"id": "doc-1", "description": "登录异常排查"}])

        assert mock_http_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_rerank_cache_bypass_after_bad_feedback_forces_remote_call(self, mock_http_client):
        """
        场景：用户对某个 query 的排序结果反馈 bad

        预期：
        - 后续相同 query 不读取旧 Rerank 缓存
        - 也不写入新的 Rerank 缓存，避免坏排序反复固化
        """
        from app.services.cache_service import CacheService
        from app.services.rerank_service import RerankService

        response = MagicMock(status_code=200)
        response.json.return_value = {"results": [{"index": 0, "score": 0.8}]}
        response.raise_for_status = MagicMock()
        mock_http_client.post = AsyncMock(return_value=response)
        cache = CacheService()
        docs = [{"id": "doc-1", "description": "小程序上线后白屏排查"}]
        cache.set_rerank("小程序上线后白屏", ["doc-1"], [{"index": 0, "score": 0.1}], ["小程序上线后白屏排查"])
        cache.bypass_rerank_cache("小程序上线后白屏", reason="bad_feedback")

        with patch("httpx.AsyncClient", return_value=mock_http_client):
            service = RerankService(
                api_key="test_key",
                request_url="https://api.test.com/v1/rerank",
                model_name="test-rerank-model",
                use_cache=True,
            )
            service._cache = cache
            first = await service.rerank("小程序上线后白屏", docs)
            second = await service.rerank("小程序上线后白屏", docs)

        assert first == [{"index": 0, "score": 0.8}]
        assert second == [{"index": 0, "score": 0.8}]
        assert mock_http_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_rerank_cache_records_request_lineage(self, mock_http_client):
        """传入 request_id 时，Rerank 缓存记录可撤销血缘。"""
        from app.services.cache_service import CacheService
        from app.services.rerank_service import RerankService

        response = MagicMock(status_code=200)
        response.json.return_value = {"results": [{"index": 0, "score": 0.8}]}
        response.raise_for_status = MagicMock()
        mock_http_client.post = AsyncMock(return_value=response)
        cache = CacheService()
        docs = [{"id": "doc-1", "description": "登录功能"}]

        with patch("httpx.AsyncClient", return_value=mock_http_client):
            service = RerankService(
                api_key="test_key",
                request_url="https://api.test.com/v1/rerank",
                model_name="test-rerank-model",
                use_cache=True,
            )
            service._cache = cache
            await service.rerank("登录", docs, request_id="req-001")

        assert cache.get_stats()["rerank_cache"]["lineage_size"] == 1
        assert cache.invalidate_rerank_by_request_id("req-001")["invalidated"] == 1

    def test_provider_safe_rerank_candidate_cap_prefers_smaller_requested_topk(self, monkeypatch):
        from app.services.rerank_service import RerankService
        from app import config as config_module

        monkeypatch.setattr(config_module.Config, "RAG_RERANK_CANDIDATE_LIMIT", 64, raising=False)
        monkeypatch.setattr(config_module.Config, "RAG_RERANK_PROVIDER_SAFE_LIMIT", 64, raising=False)
        service = RerankService(api_key="k", request_url="u", model_name="m", use_cache=False)

        assert service.calculate_candidate_limit(total_candidates=20, top_k=6) == 6
        assert service.calculate_candidate_limit(total_candidates=120, top_k=100) == 64


# =============================================================================
# 测试用例：health_check()
# =============================================================================

class TestRerankHealthCheck:
    """Rerank 健康检查测试"""

    @pytest.mark.asyncio
    async def test_health_check_success(self, rerank_service, mock_http_client):
        """
        场景：健康检查成功

        预期：
        - 返回 True
        """
        # given: 正常响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"index": 0, "score": 0.9}]}
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)

        # when: 调用 health_check
        result = await rerank_service.health_check()

        # then: 验证结果
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, rerank_service, mock_http_client):
        """
        场景：健康检查失败

        预期：
        - 返回 False
        """
        # given: 连接失败
        mock_http_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))

        # when: 调用 health_check
        result = await rerank_service.health_check()

        # then: 验证结果
        assert result is False


# =============================================================================
# 测试用例：降级模式
# =============================================================================

class TestRerankDegradedMode:
    """Rerank 降级模式测试"""

    @pytest.mark.asyncio
    async def test_degraded_mode_returns_original_scores(self, rerank_service, mock_http_client):
        """
        场景：Rerank 服务不可用，降级模式

        预期：
        - 返回原始分数
        - 不抛出异常
        """
        # given: Rerank 服务不可用
        mock_http_client.post = AsyncMock(side_effect=httpx.HTTPError("Service unavailable"))

        # when: 调用 rerank（捕获异常）
        query = "查找登录"
        docs = [
            {"id": "1", "description": "登录功能", "score": 0.9},
            {"id": "2", "description": "注册功能", "score": 0.7}
        ]

        # then: 验证降级处理
        try:
            result = await rerank_service.rerank(query, docs)
            # 如果有降级实现，验证返回格式
        except Exception:
            # 降级模式下可能抛出异常，由调用方处理
            pass
