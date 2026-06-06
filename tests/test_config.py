"""
配置模块测试用例

测试覆盖：
- 新规范环境变量优先级
"""

import os

from app.config import _get_env_preferred


def test_model_specific_embedding_and_rerank_urls_take_precedence(monkeypatch):
    """
    场景：新旧 URL 环境变量同时存在

    预期：
    - 优先读取 EMBEDDING_MODEL_REQUEST_URL
    - 优先读取 RERANK_MODEL_REQUEST_URL
    """
    env = {
        "EMBEDDING_MODEL_REQUEST_URL": "https://new.example.com/embeddings",
        "EMBEDDING_REQUEST_URL": "https://old.example.com/embeddings",
        "RERANK_MODEL_REQUEST_URL": "https://new.example.com/reranks",
        "RERANK_REQUEST_URL": "https://old.example.com/reranks",
    }

    def fake_getenv(name, default=None):
        return env.get(name, default)

    monkeypatch.setattr(os, "getenv", fake_getenv)

    assert _get_env_preferred(
        "EMBEDDING_MODEL_REQUEST_URL",
        "EMBEDDING_REQUEST_URL"
    ) == "https://new.example.com/embeddings"
    assert _get_env_preferred(
        "RERANK_MODEL_REQUEST_URL",
        "RERANK_REQUEST_URL"
    ) == "https://new.example.com/reranks"


def test_optimize_query_limit_defaults_to_two():
    """优化检索默认只跑 2 条查询，控制端到端延迟"""
    from app.config import Config

    assert Config.RAG_OPTIMIZE_QUERY_LIMIT == 2


def test_rerank_skip_min_gap_defaults_to_conservative_real_eval_value():
    """默认 Rerank 跳过阈值使用真实 50 行业评测验证过的保守值"""
    from app.config import Config

    assert Config.RAG_RERANK_SKIP_MIN_GAP == 0.018


def test_rerank_candidate_limit_defaults_to_real_eval_latency_value():
    """默认 Rerank 候选数使用真实 50 行业评测验证过的低延迟值"""
    from app.config import Config

    assert Config.RAG_RERANK_CANDIDATE_LIMIT == 6


def test_recommendation_top_k_defaults_to_three():
    """优化检索默认返回 3 条相关推荐"""
    from app.config import Config

    assert Config.RAG_RECOMMENDATION_TOP_K == 3


def test_recommendation_timeout_defaults_to_small_budget():
    """推荐生成默认使用很小的独立超时预算，避免拖慢主回答。"""
    from app.config import Config

    assert 50 <= Config.RAG_RECOMMENDATION_TIMEOUT_MS <= 250


def test_stream_delta_delay_is_configurable():
    """流式答案 delta pacing 使用配置项控制。"""
    from app.config import Config

    assert 0.0 <= Config.STREAM_DELTA_DELAY_SECONDS <= 0.1


def test_ragflow_inspired_retrieval_defaults_are_safe():
    """RAGFlow-inspired 检索策略默认保持现有 RRF 主路径"""
    from app.config import Config

    assert Config.RAG_RETRIEVAL_STRATEGY in {"rrf", "ragflow_weighted"}
    assert Config.RAG_RETRIEVAL_STRATEGY == "rrf"
    assert 0.0 <= Config.RAG_WEIGHTED_VECTOR_WEIGHT <= 1.0
    assert 0.0 <= Config.RAG_WEIGHTED_TEXT_WEIGHT <= 1.0
    assert Config.RAG_RERANK_PROVIDER_SAFE_LIMIT == 64


def test_vector_score_calibration_disabled_by_default():
    """向量分数校准接口默认关闭，避免影响现有检索排序"""
    from app.config import Config

    assert Config.RAG_VECTOR_SCORE_CALIBRATION_ENABLED is False


def test_parent_context_enhance_is_disabled_by_default():
    """父 chunk 上下文增强默认关闭，保持现有检索结果兼容"""
    from app.config import Config

    assert Config.RAG_PARENT_CONTEXT_ENHANCE_ENABLED is False


def test_global_retrieval_route_is_disabled_by_default():
    """summary-first 全局检索路由默认关闭，避免改变现有 chunk 检索路径"""
    from app.config import Config

    assert Config.RAG_GLOBAL_RETRIEVAL_ENABLED is False


def test_document_parse_worker_defaults_are_enabled_and_bounded():
    """文档解析 worker 默认开启，并使用有界批量/并发。"""
    from app.config import Config

    assert Config.DOCUMENT_PARSE_WORKER_ENABLED is True
    assert Config.DOCUMENT_PARSE_WORKER_INTERVAL_SECONDS == 2.0
    assert Config.DOCUMENT_PARSE_WORKER_BATCH_SIZE == 10
    assert Config.DOCUMENT_PARSE_WORKER_CONCURRENCY == 3
    assert Config.DOCUMENT_PARSE_WORKER_MAX_ATTEMPTS == 3


def test_config_exposes_document_parse_worker_tuning():
    """文档解析 worker 的批量和并发参数可配置。"""
    from app.config import Config

    assert Config.DOCUMENT_PARSE_BATCH_SIZE == 10
    assert Config.DOCUMENT_PARSE_CONCURRENCY == 3
    assert Config.DOCUMENT_PARSE_INTERVAL_SECONDS == 2.0
