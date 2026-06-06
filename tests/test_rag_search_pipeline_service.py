"""
RAG 检索管线服务测试
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import SearchRequest
from app.services.rag_search_pipeline_service import apply_domain_rerank_rules
from app.services.rag_search_pipeline_service import run_search_pipeline_with_profile
from app.services.rag_search_pipeline_service import RetrievalContext
from app.services.rag_search_pipeline_service import _rerank_results


@pytest.mark.asyncio
async def test_pipeline_skips_vector_score_calibration_by_default(monkeypatch):
    """默认关闭向量分数校准时，不调用校准实现且保持结果对象不变"""
    import app.services.rag_search_pipeline_service as pipeline

    monkeypatch.setattr(pipeline.Config, "RAG_VECTOR_SCORE_CALIBRATION_ENABLED", False, raising=False)
    calibrate = AsyncMock(return_value={})
    monkeypatch.setattr(pipeline, "_calibrate_vector_scores", calibrate, raising=False)

    results = [{"id": "doc-1", "score": 0.8}]
    output = await pipeline._maybe_calibrate_vector_scores(results, [0.1, 0.2])

    assert output == results
    assert calibrate.await_count == 0


@pytest.mark.asyncio
async def test_calibrate_vector_scores_batches_candidates_by_collection(monkeypatch):
    """向量分数校准按 collection 分组批量二次打分，不逐条远程调用"""
    import app.services.rag_search_pipeline_service as pipeline

    milvus_service = MagicMock()
    milvus_service.score_documents_by_ids = AsyncMock(side_effect=[
        {"skill-1": 0.91, "skill-2": 0.73},
        {"asset-1": 0.68},
    ])
    monkeypatch.setattr(pipeline, "get_milvus_service", lambda: milvus_service)

    results = [
        {"id": "skill-1", "metadata": {"type": "skill"}},
        {"id": "skill-2", "metadata": {"type": "skill"}},
        {"id": "asset-1", "metadata": {"type": "asset"}},
        {"id": "no-type", "metadata": {}},
    ]

    scores = await pipeline._calibrate_vector_scores(results, [0.1, 0.2])

    assert milvus_service.score_documents_by_ids.await_count == 2
    assert milvus_service.score_documents_by_ids.await_args_list[0].kwargs == {
        "collection": "skill",
        "query_vector": [0.1, 0.2],
        "doc_ids": ["skill-1", "skill-2"],
    }
    assert milvus_service.score_documents_by_ids.await_args_list[1].kwargs == {
        "collection": "asset",
        "query_vector": [0.1, 0.2],
        "doc_ids": ["asset-1"],
    }
    assert scores == {"skill-1": 0.91, "skill-2": 0.73, "asset-1": 0.68}


@pytest.mark.asyncio
async def test_pipeline_calibrates_fused_results_before_rerank_when_enabled(monkeypatch):
    """开启向量分数校准时，Rerank 前候选包含校准 trace"""
    import app.services.rag_search_pipeline_service as pipeline

    calibrated = [{
        "id": "doc-1",
        "description": "小程序白屏处理",
        "metadata": {"id": "doc-1", "type": "skill"},
        "score": 0.8,
        "score_trace": {"calibrated_vector_score": 0.73},
    }]
    maybe_calibrate = AsyncMock(return_value=calibrated)
    rerank = AsyncMock(side_effect=lambda query, results, request_id=None: results)

    monkeypatch.setattr(pipeline.Config, "RAG_VECTOR_SCORE_CALIBRATION_ENABLED", True, raising=False)
    monkeypatch.setattr(pipeline, "_generate_query_vector", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(pipeline, "_execute_vector_search", AsyncMock(return_value=[{
        "id": "doc-1",
        "description": "小程序白屏处理",
        "metadata": {"id": "doc-1", "type": "skill"},
        "score": 0.8,
    }]))
    monkeypatch.setattr(pipeline, "_execute_es_bm25_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_graph_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_maybe_calibrate_vector_scores", maybe_calibrate)
    monkeypatch.setattr(pipeline, "_rerank_results", rerank)

    result = await pipeline.run_search_pipeline_with_profile(
        "u001",
        SearchRequest(input="小程序白屏", type="skill", topK=5, threshold=0),
    )

    assert maybe_calibrate.await_count == 1
    assert rerank.await_args.args[1][0]["score_trace"]["calibrated_vector_score"] == 0.73
    assert result.results[0].score_trace["calibrated_vector_score"] == 0.73


@pytest.mark.asyncio
async def test_parent_context_enhance_noops_when_disabled(monkeypatch):
    """默认关闭父 chunk 上下文增强时，保持候选列表不变"""
    import app.services.rag_search_pipeline_service as pipeline

    monkeypatch.setattr(pipeline.Config, "RAG_PARENT_CONTEXT_ENHANCE_ENABLED", False, raising=False)
    results = [{"id": "chunk-1", "metadata": {"parent_id": "doc-1"}}]

    assert await pipeline._maybe_enhance_parent_context(results, ["rag_assets"]) == results


@pytest.mark.asyncio
async def test_parent_context_enhance_attaches_batch_fetched_section_context(monkeypatch):
    """开启父 chunk 上下文增强时，批量补充父文档/章节上下文并记录 trace"""
    import app.services.rag_search_pipeline_service as pipeline

    monkeypatch.setattr(pipeline.Config, "RAG_PARENT_CONTEXT_ENHANCE_ENABLED", True, raising=False)
    fetch_contexts = AsyncMock(return_value={
        "doc-1::section-1": {
            "parent_id": "doc-1",
            "section_id": "section-1",
            "section_title": "检索架构",
            "chunks": [
                {"id": "chunk-parent", "description": "父章节说明检索整体架构"},
                {"id": "chunk-1", "description": "当前命中 chunk"},
            ],
        }
    })
    monkeypatch.setattr(pipeline, "_fetch_parent_contexts", fetch_contexts, raising=False)

    results = [{
        "id": "chunk-1",
        "description": "当前命中 chunk",
        "metadata": {
            "id": "chunk-1",
            "type": "asset",
            "parent_id": "doc-1",
            "section_id": "section-1",
            "section_title": "检索架构",
        },
        "score": 0.8,
        "score_trace": {"strategy": "ragflow_weighted"},
    }]

    enhanced = await pipeline._maybe_enhance_parent_context(results, ["rag_assets"])

    fetch_contexts.assert_awaited_once_with(
        ["rag_assets"],
        context_scopes=[{"parent_ids": ["doc-1"], "section_ids": ["section-1"]}],
    )
    assert enhanced[0]["metadata"]["parent_context"]["section_title"] == "检索架构"
    assert enhanced[0]["metadata"]["parent_context"]["chunks"][0]["id"] == "chunk-parent"
    assert enhanced[0]["score_trace"]["parent_context_expanded"] is True
    assert enhanced[0]["score_trace"]["parent_context_chunk_count"] == 2


def test_enhance_results_with_parent_context_attaches_metadata_and_trace():
    """父上下文增强 helper 应只改命中项并补充 trace"""
    import app.services.rag_search_pipeline_service as pipeline

    results = [{
        "id": "chunk-1",
        "description": "当前命中 chunk",
        "metadata": {"parent_id": "doc-1", "section_id": "section-1"},
        "score_trace": {"strategy": "ragflow_weighted"},
    }]
    context_map = {
        "doc-1::section-1": {
            "parent_id": "doc-1",
            "section_id": "section-1",
            "section_title": "检索架构",
            "chunks": [{"id": "chunk-parent"}],
        }
    }

    enhanced = pipeline._enhance_results_with_parent_context(results, context_map)

    assert enhanced[0]["metadata"]["parent_context"]["section_title"] == "检索架构"
    assert enhanced[0]["score_trace"]["parent_context_expanded"] is True
    assert enhanced[0]["score_trace"]["parent_context_chunk_count"] == 1


def test_build_result_with_parent_context_creates_new_enhanced_item():
    """单条结果增强 helper 应返回新对象并保留原始结果不变"""
    import app.services.rag_search_pipeline_service as pipeline

    result = {
        "id": "chunk-1",
        "metadata": {"parent_id": "doc-1", "section_id": "section-1"},
        "score_trace": {"strategy": "ragflow_weighted"},
    }
    context = {
        "parent_id": "doc-1",
        "section_id": "section-1",
        "section_title": "检索架构",
        "chunks": [{"id": "chunk-parent"}],
    }

    enhanced = pipeline._build_result_with_parent_context(result, context)

    assert enhanced is not result
    assert enhanced["metadata"]["parent_context"]["section_title"] == "检索架构"
    assert enhanced["score_trace"]["parent_context_chunk_count"] == 1
    assert "parent_context" not in result["metadata"]


@pytest.mark.asyncio
async def test_parent_context_fetches_document_and_section_scopes_separately(monkeypatch):
    """父上下文扩展不应让章节过滤误伤文档级父上下文"""
    import app.services.rag_search_pipeline_service as pipeline

    class FakeES:
        def __init__(self):
            self.calls = []

        async def search_parent_contexts(self, index_name, parent_ids, section_ids=None, limit=20):
            self.calls.append((index_name, tuple(parent_ids), tuple(section_ids or []), limit))
            if parent_ids == ["doc-1"] and not section_ids:
                return [{
                    "id": "chunk-doc-1",
                    "description": "doc-1 父上下文",
                    "metadata": {"parent_id": "doc-1"},
                    "score": 0.9,
                }]
            if parent_ids == ["doc-2"] and section_ids == ["section-2"]:
                return [{
                    "id": "chunk-doc-2-section-2",
                    "description": "doc-2 section-2 父上下文",
                    "metadata": {"parent_id": "doc-2", "section_id": "section-2"},
                    "score": 0.8,
                }]
            return []

    fake_es = FakeES()
    monkeypatch.setattr(pipeline, "get_es_service", lambda: fake_es)

    contexts = await pipeline._fetch_parent_contexts(
        ["rag_assets"],
        context_scopes=[
            {"parent_ids": ["doc-1"], "section_ids": []},
            {"parent_ids": ["doc-2"], "section_ids": ["section-2"]},
        ],
    )

    assert fake_es.calls == [
        ("rag_assets", ("doc-1",), (), 6),
        ("rag_assets", ("doc-2",), ("section-2",), 6),
    ]
    assert contexts["doc-1::"]["chunks"][0]["id"] == "chunk-doc-1"
    assert contexts["doc-2::section-2"]["chunks"][0]["id"] == "chunk-doc-2-section-2"


@pytest.mark.asyncio
async def test_parent_context_keeps_successful_scope_when_another_scope_fails(monkeypatch):
    """父上下文某个 scope 查询失败时保留其它成功 scope 的上下文"""
    import app.services.rag_search_pipeline_service as pipeline

    class FakeES:
        async def search_parent_contexts(self, index_name, parent_ids, section_ids=None, limit=20):
            if parent_ids == ["doc-1"]:
                raise RuntimeError("doc-1 context unavailable")
            return [{
                "id": "chunk-doc-2-section-2",
                "description": "doc-2 section-2 父上下文",
                "metadata": {"parent_id": "doc-2", "section_id": "section-2"},
                "score": 0.8,
            }]

    monkeypatch.setattr(pipeline, "get_es_service", lambda: FakeES())

    contexts = await pipeline._fetch_parent_contexts(
        ["rag_assets"],
        context_scopes=[
            {"parent_ids": ["doc-1"], "section_ids": []},
            {"parent_ids": ["doc-2"], "section_ids": ["section-2"]},
        ],
    )

    assert "doc-1::" not in contexts
    assert contexts["doc-2::section-2"]["chunks"][0]["id"] == "chunk-doc-2-section-2"


def test_parent_context_grouping_skips_failed_scope_results():
    """父上下文聚合应跳过失败 scope，并保留成功 scope 的 chunk"""
    import app.services.rag_search_pipeline_service as pipeline

    grouped = pipeline._group_parent_context_results([
        [{
            "id": "chunk-doc-1",
            "description": "doc-1 父上下文",
            "metadata": {"parent_id": "doc-1"},
            "score": 0.9,
        }],
        RuntimeError("scope unavailable"),
        [{
            "id": "chunk-doc-2",
            "description": "doc-2 section-2 父上下文",
            "metadata": {"parent_id": "doc-2", "section_id": "section-2"},
            "score": 0.8,
        }],
    ])

    assert grouped["doc-1::"]["chunks"][0]["id"] == "chunk-doc-1"
    assert grouped["doc-2::section-2"]["chunks"][0]["id"] == "chunk-doc-2"


def test_collect_parent_context_scopes_groups_document_and_section_scopes():
    """父上下文 scope 收集应拆分文档级和章节级 scope"""
    import app.services.rag_search_pipeline_service as pipeline

    scopes = pipeline._collect_parent_context_scopes([
        {"metadata": {"parent_id": "doc-1"}},
        {"metadata": {"parent_id": "doc-1"}},
        {"metadata": {"parent_id": "doc-2", "section_id": "section-2"}},
        {"metadata": {"parent_id": "doc-2", "section_id": "section-2"}},
    ])

    assert scopes == [
        {"parent_ids": ["doc-1"], "section_ids": []},
        {"parent_ids": ["doc-2"], "section_ids": ["section-2"]},
    ]


def test_build_parent_context_scopes_keeps_document_scope_first():
    """组装 scope 时应先返回文档级 scope，再返回章节级 scope"""
    import app.services.rag_search_pipeline_service as pipeline

    scopes = pipeline._build_parent_context_scopes(
        ["doc-1", "doc-2"],
        {
            ("doc-3", "section-3"): {"parent_ids": ["doc-3"], "section_ids": ["section-3"]},
            ("doc-4", "section-4"): {"parent_ids": ["doc-4"], "section_ids": ["section-4"]},
        },
    )

    assert scopes[0] == {"parent_ids": ["doc-1", "doc-2"], "section_ids": []}
    assert scopes[1]["parent_ids"] == ["doc-3"]
    assert scopes[2]["section_ids"] == ["section-4"]


@pytest.mark.asyncio
async def test_fetch_parent_contexts_returns_empty_map_for_empty_inputs():
    """空索引或空 scope 时应直接返回空上下文映射"""
    import app.services.rag_search_pipeline_service as pipeline

    assert await pipeline._fetch_parent_contexts([], [{"parent_ids": ["doc-1"], "section_ids": []}]) == {}
    assert await pipeline._fetch_parent_contexts(["rag_assets"], []) == {}


@pytest.mark.asyncio
async def test_pipeline_uses_weighted_es_when_strategy_enabled(monkeypatch):
    import app.services.rag_search_pipeline_service as pipeline

    monkeypatch.setattr(pipeline.Config, "RAG_RETRIEVAL_STRATEGY", "ragflow_weighted")
    monkeypatch.setattr(pipeline, "_generate_query_vector", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(pipeline, "_execute_vector_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_graph_search", AsyncMock(return_value=[]))
    weighted = AsyncMock(return_value=[
        {
            "id": "skill-white-screen",
            "description": "小程序上线后白屏",
            "metadata": {"type": "skill", "id": "skill-white-screen"},
            "score": 12.3,
            "source_scores": {"text": 12.3},
        }
    ])
    monkeypatch.setattr(pipeline, "_execute_es_weighted_search", weighted, raising=False)
    monkeypatch.setattr(pipeline, "_rerank_results", AsyncMock(side_effect=lambda query, results, request_id=None: results))

    result = await pipeline.run_search_pipeline_with_profile(
        "u001",
        SearchRequest(input="小程序上线后白屏", type="skill", topK=5, threshold=0),
    )

    assert weighted.await_count == 1
    assert result.profile["retrieval_strategy"]["strategy"] == "ragflow_weighted"


@pytest.mark.asyncio
async def test_pipeline_weighted_strategy_returns_score_trace(monkeypatch):
    import app.services.rag_search_pipeline_service as pipeline

    monkeypatch.setattr(pipeline.Config, "RAG_RETRIEVAL_STRATEGY", "ragflow_weighted")
    monkeypatch.setattr(pipeline, "_generate_query_vector", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(pipeline, "_execute_vector_search", AsyncMock(return_value=[
        {"id": "doc-1", "score": 0.9, "description": "小程序白屏", "metadata": {"id": "doc-1", "type": "skill"}}
    ]))
    monkeypatch.setattr(pipeline, "_execute_es_weighted_search", AsyncMock(return_value=[
        {"id": "doc-1", "score": 12.0, "description": "小程序白屏", "metadata": {"id": "doc-1", "type": "skill"}}
    ]), raising=False)
    monkeypatch.setattr(pipeline, "_execute_graph_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_rerank_results", AsyncMock(side_effect=lambda query, results, request_id=None: results))

    result = await pipeline.run_search_pipeline_with_profile(
        "u001",
        SearchRequest(input="小程序白屏", type="skill", topK=5, threshold=0),
    )

    assert result.results[0].score_trace["strategy"] == "ragflow_weighted"
    assert result.profile["retrieval_strategy"]["strategy"] == "ragflow_weighted"


@pytest.mark.asyncio
async def test_pipeline_profile_includes_rerank_cap_policy(monkeypatch):
    import app.services.rag_search_pipeline_service as pipeline

    monkeypatch.setattr(pipeline.Config, "RAG_RERANK_CANDIDATE_LIMIT", 64, raising=False)
    monkeypatch.setattr(pipeline.Config, "RAG_RERANK_PROVIDER_SAFE_LIMIT", 64, raising=False)
    monkeypatch.setattr(pipeline, "_generate_query_vector", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(pipeline, "_execute_vector_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_es_bm25_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_graph_search", AsyncMock(return_value=[]))

    result = await pipeline.run_search_pipeline_with_profile(
        "u001",
        SearchRequest(input="无结果查询", type="skill", topK=5),
    )

    cap_policy = result.profile["rerank_decision"]["cap_policy"]
    assert cap_policy["configured_limit"] == 64
    assert cap_policy["provider_safe_limit"] == 64
    assert cap_policy["requested_top_k"] == 5


@pytest.mark.asyncio
async def test_weighted_pipeline_applies_tag_rank_feature(monkeypatch):
    import app.services.rag_search_pipeline_service as pipeline

    monkeypatch.setattr(pipeline.Config, "RAG_RETRIEVAL_STRATEGY", "ragflow_weighted")
    monkeypatch.setattr(pipeline, "_generate_query_vector", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(pipeline, "_execute_vector_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_graph_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_es_weighted_search", AsyncMock(return_value=[
        {"id": "doc-a", "score": 1, "description": "小程序白屏", "metadata": {"id": "doc-a", "type": "skill"}, "features": {"tags": ["小程序"]}},
        {"id": "doc-b", "score": 1, "description": "门禁", "metadata": {"id": "doc-b", "type": "skill"}, "features": {"tags": ["门禁"]}},
    ]))
    monkeypatch.setattr(pipeline, "_rerank_results", AsyncMock(side_effect=lambda query, results, request_id=None: results))

    result = await pipeline.run_search_pipeline_with_profile(
        "u001",
        SearchRequest(input="小程序上线后白屏", type="skill", topK=2),
    )

    assert result.results[0].metadata["id"] == "doc-a"
    assert result.results[0].score_trace["tag_rank_feature"] > 0


@pytest.mark.asyncio
async def test_run_search_pipeline_with_profile_returns_stage_timings():
    """带 profile 的检索返回阶段耗时，便于定位 p95 延迟来源"""
    embedding_service = MagicMock()
    embedding_service.encode = AsyncMock(return_value=[0.1, 0.2])

    milvus_service = MagicMock()
    milvus_service.search = AsyncMock(return_value=[
        {
            "id": "skill-001",
            "description": "行政审批材料预审",
            "metadata": {"type": "skill", "id": "skill-001"},
            "score": 0.9,
        }
    ])

    es_service = MagicMock()
    es_service.search = AsyncMock(return_value=[])

    graph_service = MagicMock()
    graph_service.search = MagicMock(return_value=[])

    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(return_value=[{"index": 0, "relevance_score": 0.95}])

    with (
        patch("app.services.rag_search_pipeline_service.get_embedding_service", return_value=embedding_service),
        patch("app.services.rag_search_pipeline_service.get_milvus_service", return_value=milvus_service),
        patch("app.services.rag_search_pipeline_service.get_es_service", return_value=es_service),
        patch("app.services.rag_search_pipeline_service.get_graph_retrieval_service", return_value=graph_service),
        patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service),
    ):
        result = await run_search_pipeline_with_profile(
            "test-user",
            SearchRequest(input="审批材料预审", type="skill", topK=5, threshold=0)
        )

    assert len(result.results) == 1
    assert set(result.profile["timings_ms"]) >= {
        "embedding",
        "vector_search",
        "es_bm25",
        "graph_search",
        "fusion",
        "rerank",
        "normalize",
        "filter_build",
        "total",
    }
    assert result.profile["counts"] == {
        "vector": 1,
        "es": 0,
        "graph": 0,
        "global_evidence": 0,
        "fused": 1,
        "rerank": 1,
        "filtered": 1,
    }
    assert result.profile["rerank_decision"]["skipped"] is False
    assert result.profile["rerank_decision"]["candidate_count"] == 1


@pytest.mark.asyncio
async def test_run_search_pipeline_profile_counts_limited_rerank_candidates(monkeypatch):
    """profile 中的 rerank 数量记录实际送远程重排的候选数"""
    monkeypatch.setattr(
        "app.services.rag_search_pipeline_service.Config.RAG_RERANK_CANDIDATE_LIMIT",
        2,
        raising=False,
    )
    embedding_service = MagicMock()
    embedding_service.encode = AsyncMock(return_value=[0.1, 0.2])
    milvus_service = MagicMock()
    milvus_service.search = AsyncMock(return_value=[
        {
            "id": f"skill-{i}",
            "description": f"候选 {i}",
            "metadata": {"type": "skill", "id": f"skill-{i}"},
            "score": 0.9 - i * 0.01,
        }
        for i in range(4)
    ])
    es_service = MagicMock()
    es_service.search = AsyncMock(return_value=[])
    graph_service = MagicMock()
    graph_service.search = MagicMock(return_value=[])
    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(return_value=[
        {"index": 0, "relevance_score": 0.95},
        {"index": 1, "relevance_score": 0.85},
    ])

    with (
        patch("app.services.rag_search_pipeline_service.get_embedding_service", return_value=embedding_service),
        patch("app.services.rag_search_pipeline_service.get_milvus_service", return_value=milvus_service),
        patch("app.services.rag_search_pipeline_service.get_es_service", return_value=es_service),
        patch("app.services.rag_search_pipeline_service.get_graph_retrieval_service", return_value=graph_service),
        patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service),
    ):
        result = await run_search_pipeline_with_profile(
            "test-user",
            SearchRequest(input="候选", type="skill", topK=4, threshold=0)
        )

    assert result.profile["counts"]["fused"] == 4
    assert result.profile["counts"]["rerank"] == 2
    assert result.profile["rerank_decision"]["candidate_count"] == 2


@pytest.mark.asyncio
async def test_run_search_pipeline_skips_rerank_for_confident_rrf_leader(monkeypatch):
    """RRF 第一名明显领先时跳过远程 Rerank，降低外部重排耗时"""
    monkeypatch.setattr(
        "app.services.rag_search_pipeline_service.Config.RAG_RERANK_SKIP_CONFIDENT_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.rag_search_pipeline_service.Config.RAG_RERANK_SKIP_MIN_GAP",
        0.01,
        raising=False,
    )
    embedding_service = MagicMock()
    embedding_service.encode = AsyncMock(return_value=[0.1, 0.2])
    milvus_service = MagicMock()
    milvus_service.search = AsyncMock(return_value=[
        {
            "id": "skill-leader",
            "description": "高置信第一名",
            "metadata": {"type": "skill", "id": "skill-leader"},
            "score": 0.9,
        }
    ])
    es_service = MagicMock()
    es_service.search = AsyncMock(return_value=[
        {
            "id": "skill-leader",
            "description": "高置信第一名",
            "metadata": {"type": "skill", "id": "skill-leader"},
            "score": 9.0,
        },
        {
            "id": "skill-runner",
            "description": "第二名",
            "metadata": {"type": "skill", "id": "skill-runner"},
            "score": 1.0,
        },
    ])
    graph_service = MagicMock()
    graph_service.search = MagicMock(return_value=[])
    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock()

    with (
        patch("app.services.rag_search_pipeline_service.get_embedding_service", return_value=embedding_service),
        patch("app.services.rag_search_pipeline_service.get_milvus_service", return_value=milvus_service),
        patch("app.services.rag_search_pipeline_service.get_es_service", return_value=es_service),
        patch("app.services.rag_search_pipeline_service.get_graph_retrieval_service", return_value=graph_service),
        patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service),
    ):
        result = await run_search_pipeline_with_profile(
            "test-user",
            SearchRequest(input="高置信第一名", type="skill", topK=5, threshold=0)
        )

    rerank_service.rerank.assert_not_called()
    assert result.profile["counts"]["rerank"] == 0
    assert result.profile["fallbacks"]["rerank"]["used"] is True
    assert result.profile["fallbacks"]["rerank"]["reason"] == "skipped_confident_rrf_leader"
    assert result.profile["rerank_decision"]["skipped"] is True
    assert result.profile["rerank_decision"]["reason"] == "confident_rrf_leader"
    assert result.profile["rerank_decision"]["score_gap"] >= 0.01
    assert result.results[0].metadata["id"] == "skill-leader"


@pytest.mark.asyncio
async def test_run_search_pipeline_uses_prefetched_query_vector():
    """传入预取查询向量时复用该向量，避免重复调用 Embedding 服务"""
    embedding_service = MagicMock()
    embedding_service.encode = AsyncMock(side_effect=AssertionError("embedding should be prefetched"))

    milvus_service = MagicMock()
    milvus_service.search = AsyncMock(return_value=[
        {
            "id": "skill-prefetch",
            "description": "预取向量命中的能力",
            "metadata": {"type": "skill", "id": "skill-prefetch"},
            "score": 0.9,
        }
    ])
    es_service = MagicMock()
    es_service.search = AsyncMock(return_value=[])
    graph_service = MagicMock()
    graph_service.search = MagicMock(return_value=[])
    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(return_value=[{"index": 0, "relevance_score": 0.95}])

    with (
        patch("app.services.rag_search_pipeline_service.get_embedding_service", return_value=embedding_service),
        patch("app.services.rag_search_pipeline_service.get_milvus_service", return_value=milvus_service),
        patch("app.services.rag_search_pipeline_service.get_es_service", return_value=es_service),
        patch("app.services.rag_search_pipeline_service.get_graph_retrieval_service", return_value=graph_service),
        patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service),
    ):
        result = await run_search_pipeline_with_profile(
            "test-user",
            SearchRequest(input="预取向量", type="skill", topK=5, threshold=0),
            prefetched_query_vector=[0.3, 0.4],
        )

    embedding_service.encode.assert_not_called()
    milvus_service.search.assert_awaited_once()
    assert milvus_service.search.await_args.kwargs["query_vector"] == [0.3, 0.4]
    assert result.profile["timings_ms"]["embedding"] == 0.0
    assert result.profile["counts"]["vector"] == 1


@pytest.mark.asyncio
async def test_run_search_pipeline_applies_troubleshooting_context_prerank(monkeypatch):
    """故障类查询上下文在 Rerank 前提升命中故障现象和环境差异的候选"""
    monkeypatch.setattr(
        "app.services.rag_search_pipeline_service.Config.RAG_RERANK_SKIP_CONFIDENT_ENABLED",
        False,
        raising=False,
    )
    embedding_service = MagicMock()
    embedding_service.encode = AsyncMock(return_value=[0.1, 0.2])
    milvus_service = MagicMock()
    milvus_service.search = AsyncMock(return_value=[])
    es_service = MagicMock()
    es_service.search = AsyncMock(return_value=[
        {
            "id": "skill-generic",
            "description": "小程序常规发布流程说明",
            "metadata": {"type": "skill", "id": "skill-generic"},
            "score": 9.0,
        },
        {
            "id": "skill-white-screen",
            "description": "小程序上线后白屏，本地正常时检查接口域名、分包加载和资源路径",
            "metadata": {"type": "skill", "id": "skill-white-screen"},
            "score": 8.0,
        },
    ])
    graph_service = MagicMock()
    graph_service.search = MagicMock(return_value=[])
    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(return_value=[
        {"index": 0, "relevance_score": 0.95},
        {"index": 1, "relevance_score": 0.5},
    ])
    retrieval_context = RetrievalContext(
        query_type="troubleshooting",
        entities=["小程序"],
        symptoms=["白屏"],
        environment_gap=["本地正常", "生产环境异常"],
        time_context=["上线后"],
    )

    with (
        patch("app.services.rag_search_pipeline_service.get_embedding_service", return_value=embedding_service),
        patch("app.services.rag_search_pipeline_service.get_milvus_service", return_value=milvus_service),
        patch("app.services.rag_search_pipeline_service.get_es_service", return_value=es_service),
        patch("app.services.rag_search_pipeline_service.get_graph_retrieval_service", return_value=graph_service),
        patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service),
    ):
        result = await run_search_pipeline_with_profile(
            "test-user",
            SearchRequest(input="小程序上线后白屏", type="skill", topK=5, threshold=0),
            retrieval_context=retrieval_context,
        )

    sent_candidates = rerank_service.rerank.await_args.args[1]
    assert sent_candidates[0]["id"] == "skill-white-screen"
    assert sent_candidates[0]["_context_prerank_boost"] > 0
    assert result.profile["retrieval_strategy"]["query_type"] == "troubleshooting"
    assert result.profile["retrieval_strategy"]["applied"] is True


def test_apply_retrieval_context_prerank_boosts_matching_result_without_mutating_original():
    """单条结果的上下文预排序增强应返回新对象并保留原始结果"""
    import app.services.rag_search_pipeline_service as pipeline

    result = {
        "id": "skill-white-screen",
        "description": "小程序上线后白屏，本地正常时检查接口域名、分包加载和资源路径",
        "metadata": {"type": "skill", "id": "skill-white-screen"},
        "score": 8.0,
    }
    context = RetrievalContext(
        query_type="troubleshooting",
        entities=["小程序"],
        symptoms=["白屏"],
        environment_gap=["本地正常", "生产环境异常"],
        time_context=["上线后"],
    )

    boosted = pipeline._apply_context_prerank_to_result(result, ["小程序", "白屏", "本地正常", "上线后"])

    assert boosted is not result
    assert boosted["_context_prerank_boost"] > 0
    assert "_context_prerank_boost" not in result


def test_build_retrieval_strategy_profile_uses_local_defaults_without_context():
    """检索策略 profile 在无上下文时应返回 local 默认路由摘要"""
    import app.services.rag_search_pipeline_service as pipeline

    profile = pipeline._build_retrieval_strategy_profile(None)

    assert profile["applied"] is False
    assert profile["query_type"] == ""
    assert profile["query_scope"] == "local"
    assert profile["route_plan"] == ["chunk_retrieval", "rerank"]


def test_retrieval_strategy_profile_includes_issue_type():
    """检索策略 profile 应暴露 issue_type 和 issue_filters。"""
    import app.services.rag_search_pipeline_service as pipeline

    profile = pipeline._build_retrieval_strategy_profile(
        retrieval_context=None,
        query_scope="local",
        route_plan=["chunk_retrieval"],
        issue_type="fault",
        issue_filters={"issue_type": ["fault"]},
    )

    assert profile["issue_type"] == "fault"
    assert profile["issue_filters"]["issue_type"] == ["fault"]


def test_merge_metadata_filters_combines_type_and_issue_filters():
    """ES metadata filter 应合并资源类型和问题类型过滤条件。"""
    import app.services.rag_search_pipeline_service as pipeline

    filters = pipeline._merge_metadata_filters(
        {"type": "skill"},
        {"issue_type": ["fault"], "source_type": ["runbook"]},
    )

    assert filters == {
        "type": "skill",
        "issue_type": ["fault"],
        "source_type": ["runbook"],
    }


def test_filter_graph_results_by_issue_filters_keeps_matching_metadata():
    """图检索结果应按 issue filters 做候选裁剪。"""
    import app.services.rag_search_pipeline_service as pipeline

    results = [
        {
            "id": "fault-runbook",
            "metadata": {"issue_type": "fault", "source_type": "runbook"},
            "score": 0.8,
        },
        {
            "id": "consult-faq",
            "metadata": {"issue_type": "consult", "source_type": "faq"},
            "score": 0.7,
        },
    ]

    filtered = pipeline._filter_graph_results_by_issue_filters(
        results,
        {"issue_type": ["fault"], "source_type": ["runbook", "known_issue"]},
    )

    assert [item["id"] for item in filtered] == ["fault-runbook"]


@pytest.mark.asyncio
async def test_pipeline_profile_records_global_query_scope(monkeypatch):
    import app.services.rag_search_pipeline_service as pipeline

    monkeypatch.setattr(pipeline, "_generate_query_vector", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(pipeline, "_execute_vector_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_es_bm25_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_graph_search", AsyncMock(return_value=[]))

    result = await pipeline.run_search_pipeline_with_profile(
        "u001",
        SearchRequest(
            input="这个项目整体架构是什么？",
            type="asset",
            topK=5,
            query_scope="global",
            route_plan=[
                "summary_retrieval",
                "section_expansion",
                "evidence_chunk_retrieval",
                "map_reduce_synthesis",
            ],
        ),
    )

    assert result.profile["retrieval_strategy"]["query_scope"] == "global"
    assert result.profile["retrieval_strategy"]["route_plan"][0] == "summary_retrieval"


@pytest.mark.asyncio
async def test_pipeline_global_scope_adds_summary_first_evidence_when_enabled(monkeypatch):
    import app.services.rag_search_pipeline_service as pipeline

    class FakeGlobalRetrievalService:
        def __init__(self, retriever):
            self.retriever = retriever

        async def build_context(self, query, query_scope, top_k):
            return {
                "route": "summary_first",
                "summaries": [{"id": "summary:doc-1", "metadata": {"parent_id": "doc-1"}}],
                "evidence_chunks": [
                    {
                        "id": "chunk-global",
                        "description": "summary-first 证据 chunk",
                        "metadata": {"id": "chunk-global", "type": "asset", "parent_id": "doc-1"},
                        "score": 0.82,
                    }
                ],
                "map_reduce_context": {"map_notes": [{"parent_id": "doc-1"}]},
            }

    monkeypatch.setattr(pipeline.Config, "RAG_GLOBAL_RETRIEVAL_ENABLED", True, raising=False)
    monkeypatch.setattr(pipeline, "_generate_query_vector", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(pipeline, "_execute_vector_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_es_bm25_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_execute_graph_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "GlobalRetrievalService", FakeGlobalRetrievalService, raising=False)
    monkeypatch.setattr(pipeline, "_build_es_summary_retriever", lambda indexes: object(), raising=False)
    monkeypatch.setattr(pipeline, "_rerank_results", AsyncMock(side_effect=lambda query, results, request_id=None: results))

    result = await pipeline.run_search_pipeline_with_profile(
        "u001",
        SearchRequest(
            input="这个项目整体架构是什么？",
            type="asset",
            topK=5,
            threshold=0,
            query_scope="global",
            route_plan=["summary_retrieval", "evidence_chunk_retrieval", "map_reduce_synthesis"],
        ),
    )

    assert result.results[0].metadata["id"] == "chunk-global"
    assert result.profile["counts"]["global_evidence"] == 1
    assert result.profile["retrieval_strategy"]["global_retrieval"]["route"] == "summary_first"
    assert result.profile["retrieval_strategy"]["global_retrieval"]["summary_count"] == 1


@pytest.mark.asyncio
async def test_run_search_pipeline_keeps_keyword_results_when_vector_search_fails():
    """向量检索失败时保留 ES 和图检索结果，避免外部服务抖动导致整体空召回"""
    embedding_service = MagicMock()
    embedding_service.encode = AsyncMock(return_value=[0.1, 0.2])

    milvus_service = MagicMock()
    milvus_service.search = AsyncMock(side_effect=RuntimeError("milvus unavailable"))

    es_service = MagicMock()
    es_service.search = AsyncMock(return_value=[
        {
            "id": "skill-es",
            "description": "ES 命中的行政审批材料预审能力",
            "metadata": {"type": "skill", "id": "skill-es"},
            "score": 7.2,
        }
    ])

    graph_service = MagicMock()
    graph_service.search = MagicMock(return_value=[
        {
            "id": "skill-graph",
            "description": "图检索命中的审批材料能力",
            "metadata": {"type": "skill", "id": "skill-graph"},
            "score": 0.6,
        }
    ])

    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(return_value=[
        {"index": 0, "relevance_score": 0.9},
        {"index": 1, "relevance_score": 0.7},
    ])

    with (
        patch("app.services.rag_search_pipeline_service.get_embedding_service", return_value=embedding_service),
        patch("app.services.rag_search_pipeline_service.get_milvus_service", return_value=milvus_service),
        patch("app.services.rag_search_pipeline_service.get_es_service", return_value=es_service),
        patch("app.services.rag_search_pipeline_service.get_graph_retrieval_service", return_value=graph_service),
        patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service),
    ):
        result = await run_search_pipeline_with_profile(
            "test-user",
            SearchRequest(input="审批材料预审", type="skill", topK=5, threshold=0)
        )

    returned_ids = {item.metadata["id"] for item in result.results}
    assert returned_ids == {"skill-es", "skill-graph"}
    assert result.profile["counts"]["vector"] == 0
    assert result.profile["counts"]["es"] == 1
    assert result.profile["counts"]["graph"] == 1
    assert result.profile["fallbacks"]["vector"]["used"] is True
    assert result.profile["fallbacks"]["vector"]["reason"] == "milvus unavailable"
    assert result.profile["fallbacks"]["es"]["used"] is False
    assert result.profile["fallbacks"]["graph"]["used"] is False


@pytest.mark.asyncio
async def test_run_search_pipeline_profile_marks_no_fallbacks_when_all_channels_work():
    """profile 显示各召回通道未降级，便于 SEE 和监控区分正常慢查询与故障降级"""
    embedding_service = MagicMock()
    embedding_service.encode = AsyncMock(return_value=[0.1, 0.2])

    milvus_service = MagicMock()
    milvus_service.search = AsyncMock(return_value=[
        {
            "id": "skill-vector",
            "description": "向量命中的登录能力",
            "metadata": {"type": "skill", "id": "skill-vector"},
            "score": 0.8,
        }
    ])

    es_service = MagicMock()
    es_service.search = AsyncMock(return_value=[])
    graph_service = MagicMock()
    graph_service.search = MagicMock(return_value=[])
    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(return_value=[{"index": 0, "relevance_score": 0.9}])

    with (
        patch("app.services.rag_search_pipeline_service.get_embedding_service", return_value=embedding_service),
        patch("app.services.rag_search_pipeline_service.get_milvus_service", return_value=milvus_service),
        patch("app.services.rag_search_pipeline_service.get_es_service", return_value=es_service),
        patch("app.services.rag_search_pipeline_service.get_graph_retrieval_service", return_value=graph_service),
        patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service),
    ):
        result = await run_search_pipeline_with_profile(
            "test-user",
            SearchRequest(input="登录能力", type="skill", topK=5, threshold=0)
        )

    assert len(result.results) == 1
    expected_fallbacks = {
        "vector": {"used": False, "reason": ""},
        "es": {"used": False, "reason": ""},
        "graph": {"used": False, "reason": ""},
        "rerank": {"used": False, "reason": ""},
        "parent_context": {"used": False, "reason": ""},
        "global_retrieval": {"used": False, "reason": ""},
    }
    assert result.profile["fallbacks"] == expected_fallbacks


def test_domain_rerank_rules_match_only_approval_queries():
    """领域精排规则只应作用于审批相关查询"""
    import app.services.rag_search_pipeline_service as pipeline

    results = [{"id": "x", "description": "证照到期提醒", "metadata": {}, "features": {}, "score": 0.5}]

    assert pipeline._should_apply_domain_rerank_rules("普通故障排查", results) is False
    assert pipeline._should_apply_domain_rerank_rules("证照申请表预审", results) is True
    assert pipeline._should_apply_domain_rerank_rules("", results) is False
    assert pipeline._should_apply_domain_rerank_rules("证照申请表预审", []) is False


def test_apply_domain_rerank_boost_to_single_result():
    """单条结果的领域精排加权应返回新对象并保留原结果"""
    import app.services.rag_search_pipeline_service as pipeline

    result = {
        "id": "gov_approval",
        "description": "行政审批材料预审，校验证照、申请表、法人信息、经营范围和缺失材料清单。",
        "metadata": {"type": "skill"},
        "features": {"tags": ["行政审批", "材料预审", "证照", "法人"]},
        "score": 0.89,
    }

    boosted = pipeline._apply_domain_rerank_boost(result, ["申请表", "法人", "缺失材料", "材料预审", "预审", "经营范围"], ["到期", "年检", "续办", "提醒"])

    assert boosted is not result
    assert boosted["_domain_rule_boost"] > 0
    assert "_domain_rule_boost" not in result


def test_apply_domain_rerank_rules_prefers_approval_precheck_over_license_expiry():
    """政务材料预审查询应优先行政审批材料预审，而不是证照到期提醒"""
    results = [
        {
            "id": "gov_license",
            "description": "证照到期提醒能力，管理企业许可证、人员资质、年检周期和续办材料通知。",
            "metadata": {"type": "skill"},
            "features": {"tags": ["证照", "到期", "年检", "续办"]},
            "score": 0.90,
        },
        {
            "id": "gov_approval",
            "description": "行政审批材料预审，校验证照、申请表、法人信息、经营范围和缺失材料清单。",
            "metadata": {"type": "skill"},
            "features": {"tags": ["行政审批", "材料预审", "证照", "法人"]},
            "score": 0.89,
        },
    ]

    reranked = apply_domain_rerank_rules(
        "政务大厅想自动检查申请表、证照、法人信息和缺失材料，用哪个能力？",
        results,
    )

    assert reranked[0]["id"] == "gov_approval"
    assert reranked[0]["_domain_rule_boost"] > 0


@pytest.mark.asyncio
async def test_rerank_results_limits_remote_candidates(monkeypatch):
    """Rerank 远程调用只处理配置数量内的候选，避免融合候选过多拖慢检索"""
    monkeypatch.setattr(
        "app.services.rag_search_pipeline_service.Config.RAG_RERANK_CANDIDATE_LIMIT",
        3,
        raising=False,
    )
    results = [
        {
            "id": f"doc-{i}",
            "description": f"候选 {i}",
            "metadata": {"id": f"doc-{i}"},
            "score": 0.5,
        }
        for i in range(5)
    ]
    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(return_value=[
        {"index": 0, "relevance_score": 0.9},
        {"index": 1, "relevance_score": 0.8},
        {"index": 2, "relevance_score": 0.7},
    ])

    with patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service):
        reranked = await _rerank_results("查询", results)

    rerank_service.rerank.assert_awaited_once()
    sent_candidates = rerank_service.rerank.await_args.args[1]
    assert len(sent_candidates) == 3
    assert len(reranked) == 5
    assert reranked[0]["score"] == 0.9
    assert reranked[3]["score"] == 0.5


@pytest.mark.asyncio
async def test_rerank_results_rescales_unreranked_candidates(monkeypatch):
    """未送入 Rerank 的候选回落到 RRF 分数，避免原始向量高分污染最终排序"""
    monkeypatch.setattr(
        "app.services.rag_search_pipeline_service.Config.RAG_RERANK_CANDIDATE_LIMIT",
        2,
        raising=False,
    )
    results = [
        {
            "id": "reranked-good",
            "description": "高相关候选",
            "metadata": {"id": "reranked-good"},
            "score": 0.3,
            "rrf_score": 0.04,
        },
        {
            "id": "reranked-ok",
            "description": "一般相关候选",
            "metadata": {"id": "reranked-ok"},
            "score": 0.2,
            "rrf_score": 0.03,
        },
        {
            "id": "tail-vector-high",
            "description": "未重排尾部候选",
            "metadata": {"id": "tail-vector-high"},
            "score": 9.0,
            "rrf_score": 0.01,
        },
    ]
    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(return_value=[
        {"index": 0, "relevance_score": 0.8},
        {"index": 1, "relevance_score": 0.4},
    ])

    with patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service):
        reranked = await _rerank_results("查询", results)

    assert reranked[0]["score"] == 0.8
    assert reranked[1]["score"] == 0.4
    assert reranked[2]["score"] == 0.01


@pytest.mark.asyncio
async def test_rerank_results_propagates_programming_errors(monkeypatch):
    """Rerank 逻辑中的编程错误不应被吞掉为降级"""
    import app.services.rag_search_pipeline_service as pipeline

    rerank_service = MagicMock()
    rerank_service.rerank = AsyncMock(side_effect=ValueError("bad rerank payload"))

    with patch("app.services.rag_search_pipeline_service.get_rerank_service", return_value=rerank_service):
        with pytest.raises(ValueError):
            await pipeline._rerank_results(
                "查询",
                [{"id": "doc-1", "description": "候选", "metadata": {"id": "doc-1"}, "score": 0.5}],
            )
