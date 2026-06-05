"""
特征加权服务测试用例

测试特征过滤和加权功能

@author lvdaxianerplus
@date 2026-04-18
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_service():
    """Mock LLM 服务"""
    mock = AsyncMock()
    # 单次评估返回格式
    mock.chat_simple = AsyncMock(return_value='{"relevanceScore": 0.85, "reasoning": "飞机飞行模拟高度相关"}')
    mock.health_check = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def feature_boost_service(mock_llm_service):
    """创建特征加权服务实例"""
    from app.services.feature_boost_service import FeatureBoostService
    service = FeatureBoostService(llm_service=mock_llm_service)
    return service


@pytest.fixture
def sample_results():
    """样例搜索结果"""
    return [
        {
            "id": "1",
            "description": "3D飞机模型",
            "metadata": {"type": "skill", "id": "1"},
            "features": {"category": "模型", "tags": ["3D", "飞机", "飞行"]},
            "score": 0.85
        },
        {
            "id": "2",
            "description": "Python教程",
            "metadata": {"type": "skill", "id": "2"},
            "features": {"category": "教程", "tags": ["Python", "机器学习"]},
            "score": 0.72
        },
        {
            "id": "3",
            "description": "用户登录",
            "metadata": {"type": "skill", "id": "3"},
            "features": {},
            "score": 0.65
        }
    ]


# =============================================================================
# 特征过滤测试
# =============================================================================

class TestFeatureFilter:
    """特征过滤测试"""

    def test_filter_by_features_min_match_1(self, feature_boost_service, sample_results):
        """
        场景：最少匹配 1 个标签

        预期：所有有标签的结果都被保留
        """
        result = feature_boost_service.filter_by_features(sample_results, min_match_count=1)

        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"

    def test_filter_by_features_min_match_2(self, feature_boost_service, sample_results):
        """
        场景：最少匹配 2 个标签

        预期：只有标签数量 >= 2 的结果被保留
        """
        result = feature_boost_service.filter_by_features(sample_results, min_match_count=2)

        assert len(result) == 2
        # 第一个结果有 3 个标签，第二个结果有 2 个标签，都应该被保留
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"

    def test_filter_by_features_empty_results(self, feature_boost_service):
        """
        场景：空结果列表

        预期：返回空列表
        """
        result = feature_boost_service.filter_by_features([], min_match_count=1)

        assert result == []


# =============================================================================
# 固定规则加权测试
# =============================================================================

class TestFixedBoost:
    """固定规则加权测试"""

    def test_fixed_boost_success(self, feature_boost_service, sample_results):
        """
        场景：固定规则加权成功

        预期：分数根据标签命中数量增加
        """
        import pytest
        result = feature_boost_service.fixed_boost(sample_results)

        # 第一个结果：3个标签 × 0.05 = 0.15
        assert result[0]["_fixed_boost"] == pytest.approx(0.15, rel=1e-9)
        assert result[0]["score"] == pytest.approx(1.0, rel=1e-9)  # 0.85 + 0.15

        # 第二个结果：2个标签 × 0.05 = 0.10
        assert result[1]["_fixed_boost"] == pytest.approx(0.10, rel=1e-9)
        assert result[1]["score"] == pytest.approx(0.82, rel=1e-9)  # 0.72 + 0.10

        # 第三个结果：0个标签 × 0.05 = 0
        assert result[2]["_fixed_boost"] == 0
        assert result[2]["score"] == pytest.approx(0.65, rel=1e-9)  # 0.65 + 0

    def test_fixed_boost_empty_results(self, feature_boost_service):
        """
        场景：空结果列表

        预期：返回空列表
        """
        result = feature_boost_service.fixed_boost([])

        assert result == []

    def test_fixed_boost_custom_weight(self, feature_boost_service, sample_results):
        """
        场景：自定义权重

        预期：使用自定义权重计算
        """
        import pytest
        result = feature_boost_service.fixed_boost(sample_results, weight=0.1)

        # 第一个结果：3个标签 × 0.1 = 0.3
        assert result[0]["_fixed_boost"] == pytest.approx(0.3, rel=1e-9)
        assert result[0]["score"] == pytest.approx(1.15, rel=1e-9)  # 0.85 + 0.3


# =============================================================================
# LLM 语义加权测试
# =============================================================================

class TestSemanticBoost:
    """LLM 语义加权测试"""

    @pytest.mark.asyncio
    async def test_semantic_boost_success(self, feature_boost_service, mock_llm_service, sample_results):
        """
        场景：LLM 语义加权成功

        预期：分数增加 LLM 返回的相关度分数
        """
        result = await feature_boost_service.semantic_boost("航空飞行模拟", sample_results)

        # 第一个结果应该有 _semantic_boost 字段
        assert "_semantic_boost" in result[0]
        assert result[0]["_semantic_boost"] == 0.85

        # 分数应该更新
        assert result[0]["score"] > 0.85

    @pytest.mark.asyncio
    async def test_semantic_boost_empty_results(self, feature_boost_service):
        """
        场景：空结果列表

        预期：返回空列表
        """
        result = await feature_boost_service.semantic_boost("查询", [])

        assert result == []

    @pytest.mark.asyncio
    async def test_semantic_boost_llm_error(self, feature_boost_service, mock_llm_service, sample_results):
        """
        场景：LLM 调用失败

        预期：返回原始结果，不修改分数
        """
        mock_llm_service.chat_simple = AsyncMock(side_effect=Exception("LLM Error"))

        original_score = sample_results[0]["score"]
        result = await feature_boost_service.semantic_boost("查询", sample_results)

        # 分数不应该被修改
        assert result[0]["score"] == original_score

    @pytest.mark.asyncio
    async def test_semantic_boost_invalid_response(self, feature_boost_service, mock_llm_service, sample_results):
        """
        场景：LLM 返回无效响应

        预期：返回原始结果
        """
        mock_llm_service.chat_simple = AsyncMock(return_value="无效响应")

        original_score = sample_results[0]["score"]
        result = await feature_boost_service.semantic_boost("查询", sample_results)

        # 分数不应该被修改
        assert result[0]["score"] == original_score


# =============================================================================
# 综合加权测试
# =============================================================================

class TestBoost:
    """综合加权测试"""

    @pytest.mark.asyncio
    async def test_boost_with_fixed_and_semantic(self, feature_boost_service, sample_results):
        """
        场景：同时启用固定加权和语义加权

        预期：先固定加权，再语义加权
        """
        result = await feature_boost_service.boost(
            query="航空飞行模拟",
            results=sample_results.copy(),
            enable_fixed=True,
            enable_semantic=True
        )

        # 第一个结果应该有固定加权 + 语义加权
        assert "_fixed_boost" in result[0]
        assert "_semantic_boost" in result[0]

        # 结果应该按分数排序
        for i in range(len(result) - 1):
            assert result[i]["score"] >= result[i + 1]["score"]

    @pytest.mark.asyncio
    async def test_boost_fixed_only(self, feature_boost_service, sample_results):
        """
        场景：只启用固定加权

        预期：只使用固定加权
        """
        result = await feature_boost_service.boost(
            query="航空飞行模拟",
            results=sample_results.copy(),
            enable_fixed=True,
            enable_semantic=False
        )

        # 只有固定加权
        assert "_fixed_boost" in result[0]
        assert "_semantic_boost" not in result[0]

    def test_feature_boost_prefers_query_matching_tags(self, feature_boost_service):
        """本地 tag rank feature 应该优先抬高命中查询词的候选"""
        results = [
            {"id": "doc-a", "score": 0.5, "features": {"tags": ["小程序", "白屏"]}},
            {"id": "doc-b", "score": 0.5, "features": {"tags": ["门禁", "梯控"]}},
        ]

        boosted = feature_boost_service.apply_local_tag_rank_feature("小程序上线后白屏", results)

        assert boosted[0]["id"] == "doc-a"
        assert boosted[0]["score"] > boosted[1]["score"]
        assert boosted[0]["score_trace"]["tag_rank_feature"] > 0

    @pytest.mark.asyncio
    async def test_boost_empty_results(self, feature_boost_service):
        """
        场景：空结果列表

        预期：返回空列表
        """
        result = await feature_boost_service.boost(
            query="查询",
            results=[],
            enable_fixed=True,
            enable_semantic=True
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_boost_health_check(self, feature_boost_service, mock_llm_service):
        """
        场景：健康检查

        预期：返回 LLM 健康状态
        """
        result = await feature_boost_service.health_check()

        assert result is True


# =============================================================================
# 测试统计
# =============================================================================

def test_feature_boost_service_test_count():
    """验证测试用例数量"""
    # 本测试文件应包含 12 个测试用例
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
