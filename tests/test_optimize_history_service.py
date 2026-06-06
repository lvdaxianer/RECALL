"""
语义优化历史记录服务测试

@author lvdaxianerplus
@date 2026-05-31
"""

from app.services.optimize_history_service import OptimizeHistoryRecordInput, OptimizeHistoryService


def make_history_input(
    user_id: str = "user-a",
    original_query: str = "登录失败",
    optimized_query: str = "登录失败原因排查",
    original_count: int = 1,
    optimized_count: int = 2,
    fallback_used: bool = False
) -> OptimizeHistoryRecordInput:
    """构建语义优化历史记录输入"""
    return OptimizeHistoryRecordInput(
        user_id=user_id,
        original_query=original_query,
        optimized_query=optimized_query,
        original_count=original_count,
        optimized_count=optimized_count,
        fallback_used=fallback_used
    )


def test_add_and_list_user_history():
    """新增历史记录后可按用户倒序查询"""
    service = OptimizeHistoryService(max_items_per_user=3)
    record = service.add_record(make_history_input())

    records = service.list_user_records("user-a")

    assert len(records) == 1
    assert records[0]["history_id"] == record["history_id"]
    assert records[0]["optimized_count"] == 2


def test_history_isolated_by_user():
    """不同用户的历史记录互相隔离"""
    service = OptimizeHistoryService(max_items_per_user=3)
    service.add_record(make_history_input(
        user_id="user-a",
        original_query="a",
        optimized_query="a1",
        original_count=0,
        optimized_count=1
    ))
    service.add_record(make_history_input(
        user_id="user-b",
        original_query="b",
        optimized_query="b1",
        original_count=0,
        optimized_count=1
    ))

    assert len(service.list_user_records("user-a")) == 1
    assert service.list_user_records("user-a")[0]["user_id"] == "user-a"


def test_history_max_items_eviction():
    """超过用户历史上限时淘汰最旧记录"""
    service = OptimizeHistoryService(max_items_per_user=2)
    service.add_record(make_history_input(
        original_query="q1",
        optimized_query="q1",
        original_count=0,
        optimized_count=0
    ))
    second = service.add_record(make_history_input(
        original_query="q2",
        optimized_query="q2",
        original_count=0,
        optimized_count=0
    ))
    third = service.add_record(make_history_input(
        original_query="q3",
        optimized_query="q3",
        original_count=0,
        optimized_count=0
    ))

    records = service.list_user_records("user-a")

    assert [item["history_id"] for item in records] == [
        third["history_id"],
        second["history_id"]
    ]


def test_history_persists_records_when_db_path_is_provided(tmp_path):
    """配置 SQLite 路径后，历史记录可跨服务实例读取"""
    db_path = tmp_path / "rag_state.sqlite3"
    service = OptimizeHistoryService(max_items_per_user=3, db_path=str(db_path))
    record = service.add_record(make_history_input())

    restored_service = OptimizeHistoryService(max_items_per_user=3, db_path=str(db_path))
    records = restored_service.list_user_records("user-a")
    detail = restored_service.get_record("user-a", record["history_id"])

    assert records[0]["history_id"] == record["history_id"]
    assert detail["optimized_query"] == "登录失败原因排查"


def test_history_service_creates_db_parent_directory(tmp_path):
    """SQLite 父目录不存在时会自动创建"""
    db_path = tmp_path / "nested" / "state" / "rag_state.sqlite3"

    OptimizeHistoryService(max_items_per_user=3, db_path=str(db_path))

    assert db_path.exists()
