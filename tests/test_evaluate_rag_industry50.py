"""
RAG industry50 评测脚本测试
"""

from scripts.evaluate_rag_industry50 import build_parser


def test_evaluate_industry50_script_supports_limit_argument():
    """industry50 评测支持计划文档中的 --limit 参数"""
    parser = build_parser()
    args = parser.parse_args(["--strategy", "ragflow_weighted", "--limit", "50"])

    assert args.strategy == "ragflow_weighted"
    assert args.limit == 50
