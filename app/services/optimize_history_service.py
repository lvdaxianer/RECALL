"""
语义优化历史记录服务

保存用户最近的语义优化检索记录。

@author lvdaxianerplus
@date 2026-05-31
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import sqlite3
import uuid

from app.config import Config


@dataclass(frozen=True)
class OptimizeHistoryRecordInput:
    """
    语义优化历史记录输入

    @author lvdaxianerplus
    @date 2026-06-02
    """
    user_id: str
    original_query: str
    optimized_query: str
    original_count: int
    optimized_count: int
    fallback_used: bool


class OptimizeHistoryService:
    """语义优化历史记录服务"""

    def __init__(self, max_items_per_user: int = 100, db_path: Optional[str] = None):
        """初始化历史记录服务"""
        self.max_items_per_user = max_items_per_user
        self.db_path = db_path
        self._records: Dict[str, List[dict]] = {}
        if self.db_path:
            self._init_db()

    def add_record(self, record_input: OptimizeHistoryRecordInput) -> dict:
        """
        添加历史记录

        @param record_input - 历史记录输入
        @returns 历史记录
        """
        record = {
            "history_id": uuid.uuid4().hex,
            "user_id": record_input.user_id,
            "original_query": record_input.original_query,
            "optimized_query": record_input.optimized_query,
            "original_count": record_input.original_count,
            "optimized_count": record_input.optimized_count,
            "fallback_used": record_input.fallback_used,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        user_records = self._records.setdefault(record_input.user_id, [])
        user_records.insert(0, record)
        del user_records[self.max_items_per_user:]
        if self.db_path:
            self._save_record(record)
            self._trim_user_records(record_input.user_id)
        return record

    def list_user_records(self, user_id: str) -> List[dict]:
        """
        获取用户历史记录

        @param user_id - 用户ID
        @returns 历史记录列表
        """
        if self.db_path:
            return self._list_user_records_from_db(user_id)
        return list(self._records.get(user_id, []))

    def get_record(self, user_id: str, history_id: str) -> Optional[dict]:
        """
        获取单条用户历史记录

        @param user_id - 用户ID
        @param history_id - 历史记录ID
        @returns 历史记录，不存在返回 None
        """
        if self.db_path:
            return self._get_record_from_db(user_id, history_id)
        for record in self._records.get(user_id, []):
            if record["history_id"] == history_id:
                return record
        return None

    def _init_db(self) -> None:
        """初始化 SQLite 表结构"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS optimize_history (
                    history_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    original_query TEXT NOT NULL,
                    optimized_query TEXT NOT NULL,
                    original_count INTEGER NOT NULL,
                    optimized_count INTEGER NOT NULL,
                    fallback_used INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_optimize_history_user_created "
                "ON optimize_history(user_id, created_at DESC)"
            )

    def _save_record(self, record: dict) -> None:
        """保存历史记录到 SQLite"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO optimize_history (
                    history_id, user_id, original_query, optimized_query,
                    original_count, optimized_count, fallback_used, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["history_id"],
                    record["user_id"],
                    record["original_query"],
                    record["optimized_query"],
                    record["original_count"],
                    record["optimized_count"],
                    1 if record["fallback_used"] else 0,
                    record["created_at"]
                )
            )

    def _trim_user_records(self, user_id: str) -> None:
        """按用户上限裁剪旧历史记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                DELETE FROM optimize_history
                WHERE user_id = ?
                  AND history_id NOT IN (
                    SELECT history_id FROM optimize_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                  )
                """,
                (user_id, user_id, self.max_items_per_user)
            )

    def _list_user_records_from_db(self, user_id: str) -> List[dict]:
        """从 SQLite 读取用户历史记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM optimize_history
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, self.max_items_per_user)
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def _get_record_from_db(self, user_id: str, history_id: str) -> Optional[dict]:
        """从 SQLite 读取单条历史记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM optimize_history
                WHERE user_id = ? AND history_id = ?
                """,
                (user_id, history_id)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def _row_to_record(self, row: sqlite3.Row) -> dict:
        """将 SQLite 行转换为 API 记录"""
        return {
            "history_id": row["history_id"],
            "user_id": row["user_id"],
            "original_query": row["original_query"],
            "optimized_query": row["optimized_query"],
            "original_count": row["original_count"],
            "optimized_count": row["optimized_count"],
            "fallback_used": bool(row["fallback_used"]),
            "created_at": row["created_at"]
        }


_history_service: Optional[OptimizeHistoryService] = None


def get_optimize_history_service() -> OptimizeHistoryService:
    """获取语义优化历史服务单例"""
    global _history_service
    if _history_service is None:
        _history_service = OptimizeHistoryService(db_path=Config.RAG_STATE_DB_PATH or None)
    return _history_service
