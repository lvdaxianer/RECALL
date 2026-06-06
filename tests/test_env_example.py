"""
.env.example 配置模板测试
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_env_example_documents_agent_runtime_settings():
    """环境模板包含真实 Agent Runtime 接入所需配置"""
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AGENT_RUNTIME_MODE=local" in content
    assert "AGENT_RUNTIME_BASE_URL=" in content
    assert "AGENT_RUNTIME_API_KEY=" in content
    assert "AGENT_RUNTIME_CONNECT_TIMEOUT=5" in content
    assert "AGENT_RUNTIME_READ_TIMEOUT=60" in content


def test_env_example_documents_rerank_cache_toggle():
    """环境模板暴露 Rerank 缓存开关，便于启用 request_id 撤销链路"""
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "RERANK_CACHE_ENABLED=false" in content


def test_env_example_documents_ragflow_inspired_retrieval_settings():
    """环境模板记录 RAGFlow-inspired 检索灰度配置"""
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "RAG_RETRIEVAL_STRATEGY=" in content
    assert "RAG_WEIGHTED_TEXT_WEIGHT=" in content
    assert "RAG_WEIGHTED_VECTOR_WEIGHT=" in content
    assert "RAG_WEIGHTED_GRAPH_WEIGHT=" in content
    assert "RAG_RERANK_PROVIDER_SAFE_LIMIT=" in content


def test_env_example_documents_disabled_retrieval_extension_toggles():
    """环境模板暴露默认关闭的检索扩展开关，便于灰度和回滚"""
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "RAG_VECTOR_SCORE_CALIBRATION_ENABLED=false" in content
    assert "RAG_PARENT_CONTEXT_ENHANCE_ENABLED=false" in content
    assert "RAG_GLOBAL_RETRIEVAL_ENABLED=false" in content


def test_gitignore_excludes_generated_rag_eval_reports():
    """评测报告是运行产物，应避免污染未跟踪文件列表"""
    content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "reports/" in content


def test_gitignore_allows_ragflow_retrieval_plan_tracking():
    """RAGFlow 检索迁移计划是交付证据，应从 docs 忽略规则中放行"""
    content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "!docs/superpowers/plans/2026-06-03-ragflow-retrieval-optimization-study-and-migration-plan.md" in content
