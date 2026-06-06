"""
RAG 检索评测记录服务测试

@author lvdaxianerplus
@date 2026-05-31
"""

import pytest

from app.services.rag_evaluation_service import (
    RagEvaluationRecordInput,
    RagEvaluationService,
    VALID_MISS_REASONS
)


def make_evaluation_input(
    user_id: str = "user-a",
    query: str = "登录失败",
    optimized_query: str = None,
    retrieved_ids: list[str] = None,
    miss_reason: str = "unknown",
    human_label: str = None
) -> RagEvaluationRecordInput:
    """构建 RAG 评测记录输入"""
    return RagEvaluationRecordInput(
        user_id=user_id,
        query=query,
        optimized_query=optimized_query,
        retrieved_ids=retrieved_ids or [],
        miss_reason=miss_reason,
        human_label=human_label
    )


def test_add_and_list_evaluation_records_newest_first():
    """新增评测记录后按用户倒序查询"""
    service = RagEvaluationService(max_items_per_user=3)
    first = service.add_record(make_evaluation_input(
        optimized_query="登录失败原因排查",
        retrieved_ids=["skill-1"],
        miss_reason="recall_miss",
        human_label="bad"
    ))
    second = service.add_record(make_evaluation_input(
        query="注册失败",
        retrieved_ids=["skill-2"],
        human_label="good"
    ))

    records = service.list_user_records("user-a")

    assert [item["record_id"] for item in records] == [
        second["record_id"],
        first["record_id"]
    ]
    assert records[0]["human_label"] == "good"


def test_evaluation_records_are_isolated_by_user():
    """不同用户的评测记录互相隔离"""
    service = RagEvaluationService()
    service.add_record(make_evaluation_input(user_id="user-a", query="a"))
    service.add_record(make_evaluation_input(user_id="user-b", query="b"))

    records = service.list_user_records("user-a")

    assert len(records) == 1
    assert records[0]["user_id"] == "user-a"


def test_invalid_miss_reason_is_rejected():
    """非法 miss reason 会被拒绝"""
    service = RagEvaluationService()

    with pytest.raises(ValueError):
        service.add_record(make_evaluation_input(miss_reason="bad_reason"))


def test_valid_miss_reasons_cover_bad_case_types():
    """miss reason 白名单覆盖常见 bad case 类型"""
    assert {
        "intent_error",
        "recall_miss",
        "rerank_error",
        "generation_error",
        "stale_knowledge",
        "unknown"
    }.issubset(VALID_MISS_REASONS)


def test_evaluation_records_persist_when_db_path_is_provided(tmp_path):
    """配置 SQLite 路径后，评测记录可跨服务实例读取"""
    db_path = tmp_path / "rag_state.sqlite3"
    service = RagEvaluationService(max_items_per_user=3, db_path=str(db_path))
    record = service.add_record(make_evaluation_input(
        optimized_query="登录失败原因排查",
        retrieved_ids=["skill-1", "skill-2"],
        miss_reason="recall_miss",
        human_label="bad"
    ))

    restored_service = RagEvaluationService(max_items_per_user=3, db_path=str(db_path))
    records = restored_service.list_user_records("user-a")

    assert records[0]["record_id"] == record["record_id"]
    assert records[0]["retrieved_ids"] == ["skill-1", "skill-2"]


def test_evaluation_record_accepts_retrieval_strategy_and_latency(tmp_path):
    """评测记录可保存检索策略和端到端延迟，便于对比 RRF 与 weighted 策略"""
    db_path = tmp_path / "eval.sqlite3"
    service = RagEvaluationService(db_path=str(db_path))
    record = service.record_case(
        user_id="user-a",
        query="小程序上线后白屏",
        optimized_query="小程序上线后白屏 本地正常 生产环境异常",
        retrieved_ids=["skill-white-screen"],
        miss_reason="unknown",
        human_label="hit",
        request_id="req-001",
        retrieval_strategy="ragflow_weighted",
        latency_ms=123,
    )

    restored = RagEvaluationService(db_path=str(db_path)).list_user_records("user-a")

    assert record["retrieval_strategy"] == "ragflow_weighted"
    assert record["latency_ms"] == 123
    assert record["request_id"] == "req-001"
    assert restored[0]["retrieval_strategy"] == "ragflow_weighted"
    assert restored[0]["latency_ms"] == 123


def test_evaluation_service_creates_db_parent_directory(tmp_path):
    """SQLite 父目录不存在时会自动创建"""
    db_path = tmp_path / "nested" / "state" / "rag_state.sqlite3"

    RagEvaluationService(max_items_per_user=3, db_path=str(db_path))

    assert db_path.exists()


def test_summary_user_records_counts_bad_case_distribution():
    """汇总用户评测记录时统计 bad case 原因和人工标签分布"""
    service = RagEvaluationService()
    service.add_record(make_evaluation_input(
        query="登录失败",
        retrieved_ids=["skill-1"],
        miss_reason="recall_miss",
        human_label="bad"
    ))
    service.add_record(make_evaluation_input(
        query="注册失败",
        retrieved_ids=["skill-2"],
        miss_reason="recall_miss",
        human_label="bad"
    ))
    latest = service.add_record(make_evaluation_input(
        query="支付超时",
        miss_reason="rerank_error",
        human_label="good"
    ))
    service.add_record(make_evaluation_input(user_id="user-b", query="隔离数据", human_label="bad"))

    summary = service.summary_user_records("user-a")

    assert summary == {
        "total_count": 3,
        "miss_reason_counts": {
            "recall_miss": 2,
            "rerank_error": 1
        },
        "human_label_counts": {
            "bad": 2,
            "good": 1
        },
        "latest_created_at": latest["created_at"]
    }


def test_summary_user_records_reads_from_sqlite(tmp_path):
    """配置 SQLite 路径后，汇总统计从持久化记录读取"""
    db_path = tmp_path / "rag_state.sqlite3"
    service = RagEvaluationService(db_path=str(db_path))
    service.add_record(make_evaluation_input(query="登录失败", miss_reason="intent_error", human_label="bad"))
    service.add_record(make_evaluation_input(query="注册失败", miss_reason="intent_error", human_label="bad"))

    restored_service = RagEvaluationService(db_path=str(db_path))
    summary = restored_service.summary_user_records("user-a")

    assert summary["total_count"] == 2
    assert summary["miss_reason_counts"] == {"intent_error": 2}
    assert summary["human_label_counts"] == {"bad": 2}
    assert summary["latest_created_at"]


def test_bad_feedback_invalidates_rerank_cache_only():
    """人工 bad 反馈会绕过对应 query 的 Rerank 缓存，但不清 Embedding 缓存"""
    from app.services.cache_service import CacheService

    cache = CacheService()
    service = RagEvaluationService(cache_service=cache)
    cache.set_embedding("小程序上线后白屏", [0.1, 0.2])
    cache.set_rerank(
        "小程序上线后白屏",
        ["doc-1"],
        [{"index": 0, "score": 0.1}],
        doc_fingerprints=["小程序上线后白屏排查"],
    )

    service.add_record(make_evaluation_input(
        query="小程序上线后白屏",
        retrieved_ids=["doc-1"],
        miss_reason="rerank_error",
        human_label="bad"
    ))

    assert cache.get_rerank(
        "小程序上线后白屏",
        ["doc-1"],
        doc_fingerprints=["小程序上线后白屏排查"],
    ) is None
    assert cache.get_embedding("小程序上线后白屏") == [0.1, 0.2]
