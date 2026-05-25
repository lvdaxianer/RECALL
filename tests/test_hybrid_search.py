"""
RRF 混合搜索模块测试

使用真实数据测试 RRF 融合算法

@author lvdaxianerplus
@date 2026-04-16
"""

import pytest
from app.services.hybrid_search import rrf_fusion, rrf_fusion_with_scores, normalize_scores


class TestRRFFusion:
    """RRF 融合算法测试"""

    def test_rrf_fusion_with_two_result_sets(self):
        """
        测试两路召回结果的融合

        场景：
        - 召回路1: [Doc_A, Doc_B, Doc_C]
        - 召回路2: [Doc_B, Doc_D, Doc_A]

        预期：
        - Doc_A 和 Doc_B 应该排名靠前（两路都有好排名）
        - Doc_D 应该优于 Doc_C（Doc_D 在召回路2排名2，Doc_C 只在召回路1排名3）
        """
        # 召回路1 (向量搜索): [Doc_A, Doc_B, Doc_C]
        results_1 = [
            {"id": "Doc_A", "score": 0.9, "description": "Doc A description"},
            {"id": "Doc_B", "score": 0.8, "description": "Doc B description"},
            {"id": "Doc_C", "score": 0.7, "description": "Doc C description"},
        ]

        # 召回路2 (BM25): [Doc_B, Doc_D, Doc_A]
        results_2 = [
            {"id": "Doc_B", "score": 15.0, "description": "Doc B description"},
            {"id": "Doc_D", "score": 12.0, "description": "Doc D description"},
            {"id": "Doc_A", "score": 10.0, "description": "Doc A description"},
        ]

        # 执行 RRF 融合 (k=60)
        fused = rrf_fusion([results_1, results_2], k=60)

        # 验证结果数量
        assert len(fused) == 4

        # 验证返回的文档 ID
        fused_ids = [r["id"] for r in fused]

        # Doc_A 和 Doc_B 两路都有好排名，应该在前面
        assert fused_ids[0] in ["Doc_A", "Doc_B"]
        assert fused_ids[1] in ["Doc_A", "Doc_B"]

        # Doc_D 只在召回路2出现但排名2，应该优于只在召回路1排名3的 Doc_C
        assert fused_ids.index("Doc_D") < fused_ids.index("Doc_C")

    def test_rrf_fusion_preserves_rrf_score(self):
        """
        测试 RRF 融合后结果包含 rrf_score
        """
        results_1 = [
            {"id": "Doc_A", "score": 0.9},
            {"id": "Doc_B", "score": 0.8},
        ]
        results_2 = [
            {"id": "Doc_B", "score": 15.0},
            {"id": "Doc_A", "score": 10.0},
        ]

        fused = rrf_fusion([results_1, results_2], k=60)

        # 每个结果都应该有 rrf_score
        for item in fused:
            assert "rrf_score" in item
            assert item["rrf_score"] > 0

        # Doc_A 和 Doc_B 的 rrf_score 应该相同（排名相同）
        doc_a_score = next(r["rrf_score"] for r in fused if r["id"] == "Doc_A")
        doc_b_score = next(r["rrf_score"] for r in fused if r["id"] == "Doc_B")
        assert abs(doc_a_score - doc_b_score) < 0.001

    def test_rrf_fusion_with_empty_results(self):
        """
        测试有空结果列表的情况
        """
        results_1 = [
            {"id": "Doc_A", "score": 0.9},
        ]
        results_2 = []

        # 一个空列表不应该导致错误
        fused = rrf_fusion([results_1, results_2], k=60)

        assert len(fused) == 1
        assert fused[0]["id"] == "Doc_A"

    def test_rrf_fusion_with_all_empty_results(self):
        """
        测试所有结果都为空的情况
        """
        fused = rrf_fusion([[], []], k=60)
        assert len(fused) == 0

    def test_rrf_fusion_with_empty_list(self):
        """
        测试空列表的情况
        """
        fused = rrf_fusion([], k=60)
        assert len(fused) == 0

    def test_rrf_k_parameter_effect(self):
        """
        测试不同 k 值对融合结果的影响

        k 值越小，排名靠前的文档优势越明显
        """
        # 召回路1: Doc_A 排第1
        # 召回路2: Doc_B 排第1
        results_1 = [{"id": "Doc_A", "score": 0.9}]
        results_2 = [{"id": "Doc_B", "score": 15.0}]

        # k=0 时排名差距影响最大
        fused_k0 = rrf_fusion([results_1, results_2], k=0)
        # k=60 时平滑处理
        fused_k60 = rrf_fusion([results_1, results_2], k=60)

        # k=0 时第一名的优势更大
        # 1/(0+1) = 1 vs 1/(0+2) = 0.5
        # k=60 时 1/(60+1) ≈ 1/61 vs 1/(60+2) ≈ 1/62，差距很小
        assert fused_k0[0]["id"] == "Doc_A"
        assert fused_k60[0]["id"] == "Doc_A"

    def test_rrf_preserves_description(self):
        """
        测试 RRF 融合保留原始文档信息
        """
        results_1 = [
            {"id": "Doc_A", "score": 0.9, "description": "Description A"},
        ]

        fused = rrf_fusion([results_1], k=60)

        assert fused[0]["description"] == "Description A"

    def test_rrf_with_doc_id_field(self):
        """
        测试使用 doc_id 字段的情况
        """
        results_1 = [
            {"doc_id": "Doc_A", "score": 0.9},
        ]
        results_2 = [
            {"doc_id": "Doc_B", "score": 15.0},
        ]

        # 应该正确处理 doc_id 字段
        fused = rrf_fusion([results_1, results_2], k=60)

        assert len(fused) == 2


class TestRRFFusionWithScores:
    """RRF 融合（保留原始分数）测试"""

    def test_rrf_with_scores_preserves_source_scores(self):
        """
        测试融合后保留各路召回的原始分数
        """
        results_1 = [
            {"id": "Doc_A", "score": 0.9},
            {"id": "Doc_B", "score": 0.8},
        ]
        results_2 = [
            {"id": "Doc_B", "score": 15.0},
            {"id": "Doc_A", "score": 10.0},
        ]

        fused = rrf_fusion_with_scores([results_1, results_2], k=60)

        doc_a = next(r for r in fused if r["id"] == "Doc_A")

        # 应该保留 source_scores
        assert "source_scores" in doc_a
        assert len(doc_a["source_scores"]) == 2


class TestNormalizeScores:
    """分数归一化测试"""

    def test_normalize_scores_basic(self):
        """
        测试基本归一化功能
        """
        results = [
            {"id": "A", "score": 1.0},
            {"id": "B", "score": 0.5},
            {"id": "C", "score": 0.0},
        ]

        normalized = normalize_scores(results)

        # 验证归一化后的分数范围
        assert normalized[0]["normalized_score"] == 1.0  # max
        assert normalized[2]["normalized_score"] == 0.0  # min
        assert 0.0 < normalized[1]["normalized_score"] < 1.0

    def test_normalize_scores_empty(self):
        """
        测试空列表
        """
        normalized = normalize_scores([])
        assert len(normalized) == 0

    def test_normalize_scores_same_values(self):
        """
        测试所有分数相同的情况
        """
        results = [
            {"id": "A", "score": 0.5},
            {"id": "B", "score": 0.5},
        ]

        normalized = normalize_scores(results)

        # 应该不报错，原样返回
        assert len(normalized) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
