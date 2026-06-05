"""
README 中的 Agent Runtime 与 SEE 文档覆盖测试
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_readme_documents_agent_runtime_and_see_timeline():
    """英文 README 覆盖新增 Agent Runtime、SSE、SEE 与评测入口"""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "POST /api/v1/rag/{userId}/search/optimize/stream" in readme
    assert "POST /api/v1/agent/{userId}/sessions" in readme
    assert "POST /api/v1/agent/{userId}/sessions/{sessionId}/runs" in readme
    assert "GET /api/v1/agent/{userId}/sessions/{sessionId}/events" in readme
    assert "GET /api/v1/agent/runtimes/{runtimeId}/health" in readme
    assert "POST /api/v1/agent/runtimes/{runtimeId}/stop" in readme
    assert "POST /api/v1/agent/runtimes/cleanup" in readme
    assert "GET /see/timeline" in readme
    assert "POST /api/v1/rag/{userId}/feedback/bad-case" in readme
    assert "scripts/evaluate_agent_runtime_stream.py" in readme
    assert "--disable-cache" in readme


def test_readme_zh_documents_agent_runtime_and_see_timeline():
    """中文 README 覆盖新增 Agent Runtime、SSE、SEE 与评测入口"""
    readme = (PROJECT_ROOT / "README-zh.md").read_text(encoding="utf-8")

    assert "POST /api/v1/rag/{userId}/search/optimize/stream" in readme
    assert "POST /api/v1/agent/{userId}/sessions" in readme
    assert "POST /api/v1/agent/{userId}/sessions/{sessionId}/runs" in readme
    assert "GET /api/v1/agent/{userId}/sessions/{sessionId}/events" in readme
    assert "GET /api/v1/agent/runtimes/{runtimeId}/health" in readme
    assert "POST /api/v1/agent/runtimes/{runtimeId}/stop" in readme
    assert "POST /api/v1/agent/runtimes/cleanup" in readme
    assert "GET /see/timeline" in readme
    assert "POST /api/v1/rag/{userId}/feedback/bad-case" in readme
    assert "scripts/evaluate_agent_runtime_stream.py" in readme
    assert "--disable-cache" in readme


def test_readme_documents_ragflow_inspired_retrieval_strategy():
    """中文 README 记录 RAGFlow-inspired 检索策略与 CoT 输出边界"""
    content = (PROJECT_ROOT / "README-zh.md").read_text(encoding="utf-8")

    assert "RAG_RETRIEVAL_STRATEGY" in content
    assert "ragflow_weighted" in content
    assert "cot_plan" in content
    assert "不输出完整私有 CoT" in content
