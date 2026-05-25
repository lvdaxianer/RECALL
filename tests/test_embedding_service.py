"""
Embedding 服务测试用例

测试覆盖：
- encode() 单文本向量化
- encode() 批量向量化
- health_check() 健康检查
- 异常处理

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
    client.post = AsyncMock(return_value=AsyncMock(
        status_code=200,
        json=AsyncMock(return_value={
            "data": [{
                "embedding": [0.1] * 8192
            }]
        })
    ))
    return client


@pytest.fixture
def embedding_service(mock_http_client):
    """创建 Embedding 服务实例"""
    with patch("httpx.AsyncClient", return_value=mock_http_client):
        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService(
            api_key="test_key",
            request_url="https://api.test.com/v1/embeddings",
            model_name="test-model",
            dimension=8192
        )
        return service


# =============================================================================
# 测试用例：encode() 单文本
# =============================================================================

class TestEmbeddingEncode:
    """Embedding 编码测试"""

    @pytest.mark.asyncio
    async def test_encode_single_text_success(self, embedding_service, mock_http_client):
        """
        场景：单文本编码成功

        预期：
        - 返回向量列表
        - 向量维度正确
        """
        # given: 文本输入
        text = "用户登录功能"

        # when: 调用 encode
        result = await embedding_service.encode(text)

        # then: 验证结果
        assert isinstance(result, list)
        assert len(result) == 8192
        assert all(isinstance(x, float) for x in result)

    @pytest.mark.asyncio
    async def test_encode_multiple_texts_success(self, embedding_service, mock_http_client):
        """
        场景：多文本编码成功

        预期：
        - 返回向量列表的列表
        - 每个向量维度正确
        """
        # given: 多文本输入
        texts = ["用户登录功能", "用户注册功能", "密码找回"]

        # when: 调用 encode
        result = await embedding_service.encode(texts)

        # then: 验证结果
        assert isinstance(result, list)
        assert len(result) == 3
        for vec in result:
            assert len(vec) == 8192

    @pytest.mark.asyncio
    async def test_encode_empty_text(self, embedding_service):
        """
        场景：空文本

        预期：
        - 抛出 ValueError
        """
        # given: 空文本
        text = ""

        # when/then: 调用 encode
        with pytest.raises(ValueError):
            await embedding_service.encode(text)

    @pytest.mark.asyncio
    async def test_encode_http_error(self, embedding_service, mock_http_client):
        """
        场景：HTTP 请求失败

        预期：
        - 抛出异常
        - 记录 ERROR 日志
        """
        # given: HTTP 错误
        mock_http_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))

        # when/then: 调用 encode
        with pytest.raises(httpx.HTTPError):
            await embedding_service.encode("test text")

    @pytest.mark.asyncio
    async def test_encode_api_error_response(self, embedding_service, mock_http_client):
        """
        场景：API 返回错误响应

        预期：
        - 抛出异常
        - 记录 ERROR 日志
        """
        # given: API 错误响应
        error_response = AsyncMock()
        error_response.status_code = 500
        error_response.json = AsyncMock(return_value={"error": "Internal error"})
        mock_http_client.post = AsyncMock(return_value=error_response)

        # when/then: 调用 encode
        with pytest.raises(Exception):
            await embedding_service.encode("test text")


# =============================================================================
# 测试用例：health_check()
# =============================================================================

class TestEmbeddingHealthCheck:
    """Embedding 健康检查测试"""

    @pytest.mark.asyncio
    async def test_health_check_success(self, embedding_service, mock_http_client):
        """
        场景：健康检查成功

        预期：
        - 返回 True
        """
        # given: 正常响应
        mock_http_client.post = AsyncMock(return_value=AsyncMock(
            status_code=200,
            json=AsyncMock(return_value={"data": [{"embedding": [0.1] * 128}]})
        ))

        # when: 调用 health_check
        result = await embedding_service.health_check()

        # then: 验证结果
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, embedding_service, mock_http_client):
        """
        场景：健康检查失败

        预期：
        - 返回 False
        """
        # given: 连接失败
        mock_http_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))

        # when: 调用 health_check
        result = await embedding_service.health_check()

        # then: 验证结果
        assert result is False


# =============================================================================
# 测试用例：配置验证
# =============================================================================

class TestEmbeddingConfig:
    """Embedding 配置测试"""

    def test_config_loading_from_env(self):
        """
        场景：从环境变量加载配置

        预期：
        - 配置正确加载
        """
        # given: 设置环境变量
        with patch.dict("os.environ", {
            "EMBEDDING_MODEL_NAME": "test-model",
            "EMBEDDING_MODEL_API_KEY": "test_key",
            "EMBEDDING_REQUEST_URL": "https://api.test.com/v1/embeddings",
            "EMBEDDING_DIMENSION": "8192"
        }):
            from app.services.embedding_service import EmbeddingService
            service = EmbeddingService()

            # then: 验证配置
            assert service.model_name == "test-model"
            assert service.dimension == 8192

    def test_config_default_dimension(self):
        """
        场景：默认向量维度

        预期：
        - dimension 默认 8192
        """
        # given: 未设置维度
        with patch.dict("os.environ", {}, clear=True):
            from app.services.embedding_service import EmbeddingService
            service = EmbeddingService(
                api_key="test",
                request_url="http://test.com",
                model_name="test"
            )

            # then: 验证默认值
            assert service.dimension == 8192
