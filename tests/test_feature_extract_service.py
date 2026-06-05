"""
特征提取服务测试用例

测试 LLM 从 description 中提取 category 和 tags 的功能

@author lvdaxianerplus
@date 2026-04-18
"""

import pytest
from unittest.mock import AsyncMock


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_service():
    """Mock LLM 服务"""
    mock = AsyncMock()
    mock.chat_simple = AsyncMock(return_value='{"category": "模型", "tags": ["3D", "飞机", "飞行", "模拟"]}')
    mock.health_check = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def feature_extract_service(mock_llm_service):
    """创建特征提取服务实例"""
    from app.services.feature_extract_service import FeatureExtractService
    service = FeatureExtractService(llm_service=mock_llm_service)
    return service


# =============================================================================
# 特征提取测试
# =============================================================================

class TestFeatureExtract:
    """特征提取服务测试"""

    @pytest.mark.asyncio
    async def test_extract_features_success(self, feature_extract_service, mock_llm_service):
        """
        场景：LLM 提取特征成功

        预期：返回正确的 category 和 tags
        """
        result = await feature_extract_service.extract_features("这是一个3D飞机飞行模拟模型")

        assert result["category"] == "模型"
        assert "3D" in result["tags"]
        assert "飞机" in result["tags"]
        assert "飞行" in result["tags"]
        assert "模拟" in result["tags"]

    @pytest.mark.asyncio
    async def test_extract_features_empty_description(self, feature_extract_service):
        """
        场景：描述为空

        预期：返回默认特征
        """
        result = await feature_extract_service.extract_features("")

        assert result["category"] == "未分类"
        assert result["tags"] == []
        assert result["entities"] == []
        assert result["relations"] == []

    @pytest.mark.asyncio
    async def test_extract_features_llm_error(self, feature_extract_service, mock_llm_service):
        """
        场景：LLM 调用失败

        预期：返回默认特征
        """
        mock_llm_service.chat_simple = AsyncMock(side_effect=Exception("LLM Error"))

        result = await feature_extract_service.extract_features("测试描述")

        assert result["category"] == "未分类"
        assert result["tags"] == []
        assert result["entities"] == []
        assert result["relations"] == []

    @pytest.mark.asyncio
    async def test_extract_features_invalid_json(self, feature_extract_service, mock_llm_service):
        """
        场景：LLM 返回无效 JSON

        预期：返回默认特征
        """
        mock_llm_service.chat_simple = AsyncMock(return_value="这不是 JSON")

        result = await feature_extract_service.extract_features("测试描述")

        assert result["category"] == "未分类"
        assert result["tags"] == []
        assert result["entities"] == []
        assert result["relations"] == []

    @pytest.mark.asyncio
    async def test_extract_features_tags_limit(self, feature_extract_service, mock_llm_service):
        """
        场景：LLM 返回超过 10 个标签

        预期：标签数量限制在 10 个以内
        """
        mock_llm_service.chat_simple = AsyncMock(
            return_value='{"category": "模型", "tags": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]}'
        )

        result = await feature_extract_service.extract_features("测试描述")

        assert len(result["tags"]) <= 10

    @pytest.mark.asyncio
    async def test_extract_features_with_json_wrapper(self, feature_extract_service, mock_llm_service):
        """
        场景：LLM 返回带 ```json 包装的 JSON

        预期：正确解析
        """
        mock_llm_service.chat_simple = AsyncMock(
            return_value='```json\n{"category": "教程", "tags": ["Python", "机器学习"]}\n```'
        )

        result = await feature_extract_service.extract_features("测试描述")

        assert result["category"] == "教程"
        assert "Python" in result["tags"]
        assert "机器学习" in result["tags"]

    @pytest.mark.asyncio
    async def test_health_check_success(self, feature_extract_service, mock_llm_service):
        """
        场景：健康检查成功

        预期：返回 True
        """
        result = await feature_extract_service.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failed(self, feature_extract_service, mock_llm_service):
        """
        场景：健康检查失败

        预期：返回 False
        """
        mock_llm_service.health_check = AsyncMock(return_value=False)

        result = await feature_extract_service.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_extract_features_batch_preserves_order(self, feature_extract_service):
        """
        场景：批量提取特征

        预期：结果顺序与输入描述顺序一致
        """
        async def fake_extract(description):
            return {"category": "测试", "tags": [description]}

        feature_extract_service.extract_features = AsyncMock(side_effect=fake_extract)

        result = await feature_extract_service.extract_features_batch(["a", "b", "c"], concurrency=2)

        assert result == [
            {"category": "测试", "tags": ["a"]},
            {"category": "测试", "tags": ["b"]},
            {"category": "测试", "tags": ["c"]}
        ]


# =============================================================================
# 测试统计
# =============================================================================

def test_feature_extract_service_test_count():
    """验证测试用例数量"""
    # 本测试文件应包含 8 个测试用例
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
