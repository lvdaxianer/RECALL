"""
RAG random100 评测脚本测试
"""

from scripts.evaluate_rag_random100 import _build_cache_settings
from scripts.evaluate_rag_random100 import _build_random100_report_path
from scripts.evaluate_rag_random100 import build_parser
from scripts.evaluate_rag_random100 import configure_cache_pipeline


def test_evaluate_script_supports_strategy_argument():
    """random100 评测支持指定 RRF 或 RAGFlow-inspired 策略"""
    parser = build_parser()
    args = parser.parse_args(["--strategy", "ragflow_weighted", "--query-count", "5"])

    assert args.strategy == "ragflow_weighted"
    assert args.query_count == 5


def test_evaluate_script_supports_limit_argument():
    """random100 评测兼容计划文档中的 --limit 参数"""
    parser = build_parser()
    args = parser.parse_args(["--strategy", "ragflow_weighted", "--limit", "20"])

    assert args.strategy == "ragflow_weighted"
    assert args.limit == 20


def test_configure_cache_pipeline_enables_rerank_cache(monkeypatch):
    """启用缓存评测时同时打开 Rerank 缓存配置，避免报告和实际链路不一致"""
    import scripts.evaluate_rag_random100 as random100

    class FakeEmbeddingService:
        def __init__(self, use_cache):
            self.use_cache = use_cache

    class FakeRerankService:
        def __init__(self, use_cache):
            self.use_cache = use_cache

    monkeypatch.setattr(random100, "EmbeddingService", FakeEmbeddingService)
    monkeypatch.setattr(random100, "RerankService", FakeRerankService)
    monkeypatch.setattr(random100.Config, "RERANK_CACHE_ENABLED", False)

    configure_cache_pipeline()

    assert random100.Config.RERANK_CACHE_ENABLED is True
    assert random100.rag_search_pipeline_service._embedding_service.use_cache is True
    assert random100.rag_search_pipeline_service._rerank_service.use_cache is True


def test_build_cache_settings_defaults_to_cache_enabled():
    """random100 默认允许缓存，只有显式 --disable-cache 才关闭缓存链路"""
    settings = _build_cache_settings(disable_cache=False)

    assert settings["embedding_cache_enabled"] is True
    assert settings["rerank_cache_enabled"] is True


def test_build_cache_settings_can_disable_all_model_caches():
    """random100 支持 --disable-cache，用于冷启动速度评测"""
    settings = _build_cache_settings(disable_cache=True)

    assert settings["embedding_cache_enabled"] is False
    assert settings["rerank_cache_enabled"] is False


def test_build_random100_report_path_uses_reports_directory():
    """random100 报告写入 reports/rag_eval 的时间戳 JSON 文件"""
    output_path = _build_random100_report_path(timestamp="20260603-120102")

    assert output_path.parts[-3:] == ("reports", "rag_eval", "20260603-120102-random100.json")
