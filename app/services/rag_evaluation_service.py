"""
RAG 检索评测记录服务

保存用户最近的检索评测与 bad case 归因记录。

@author lvdaxianerplus
@date 2026-05-31
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import json
import sqlite3
import uuid

from app.config import Config
from app.services.cache_service import get_cache_service


VALID_MISS_REASONS = {
    "intent_error",
    "recall_miss",
    "rerank_error",
    "generation_error",
    "stale_knowledge",
    "unknown"
}


@dataclass(frozen=True)
class RagEvaluationRecordInput:
    """
    RAG 检索评测记录输入

    @author lvdaxianerplus
    @date 2026-06-02
    """
    user_id: str
    query: str
    optimized_query: Optional[str]
    retrieved_ids: List[str]
    miss_reason: str
    human_label: Optional[str]
    request_id: Optional[str] = None
    retrieval_strategy: str = ""
    latency_ms: int = 0


class RagEvaluationService:
    """RAG 检索评测记录服务"""

    def __init__(
        self,
        max_items_per_user: int = 500,
        db_path: Optional[str] = None,
        cache_service=None
    ):
        """初始化评测记录服务"""
        self.max_items_per_user = max_items_per_user
        self.db_path = db_path
        self.cache_service = cache_service
        self._records: Dict[str, List[dict]] = {}
        if self.db_path:
            self._init_db()

    def add_record(self, record_input: RagEvaluationRecordInput) -> dict:
        """
        添加评测记录

        @param record_input - 评测记录输入
        @returns 评测记录
        """
        if record_input.miss_reason not in VALID_MISS_REASONS:
            raise ValueError(f"invalid miss_reason: {record_input.miss_reason}")

        record = {
            "record_id": uuid.uuid4().hex,
            "user_id": record_input.user_id,
            "query": record_input.query,
            "optimized_query": record_input.optimized_query,
            "retrieved_ids": list(record_input.retrieved_ids),
            "miss_reason": record_input.miss_reason,
            "human_label": record_input.human_label,
            "request_id": record_input.request_id,
            "retrieval_strategy": record_input.retrieval_strategy,
            "latency_ms": record_input.latency_ms,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        user_records = self._records.setdefault(record_input.user_id, [])
        user_records.insert(0, record)
        del user_records[self.max_items_per_user:]
        if self.db_path:
            self._save_record(record)
            self._trim_user_records(record_input.user_id)
        self._protect_against_bad_rerank_cache(record_input)
        return record

    def record_case(
        self,
        query: str,
        optimized_query: Optional[str],
        retrieved_ids: List[str],
        miss_reason: str,
        human_label: Optional[str],
        user_id: str = "default",
        request_id: Optional[str] = None,
        retrieval_strategy: str = "",
        latency_ms: int = 0,
    ) -> dict:
        """记录一次检索评测 case，兼容脚本和 API 直接调用。"""
        return self.add_record(RagEvaluationRecordInput(
            user_id=user_id,
            query=query,
            optimized_query=optimized_query,
            retrieved_ids=retrieved_ids,
            miss_reason=miss_reason,
            human_label=human_label,
            request_id=request_id,
            retrieval_strategy=retrieval_strategy,
            latency_ms=latency_ms,
        ))

    def list_user_records(self, user_id: str) -> List[dict]:
        """
        获取用户评测记录

        @param user_id - 用户ID
        @returns 评测记录列表
        """
        if self.db_path:
            return self._list_user_records_from_db(user_id)
        return list(self._records.get(user_id, []))

    def summary_user_records(self, user_id: str) -> dict:
        """
        汇总用户评测记录

        @param user_id - 用户ID
        @returns bad case 原因和人工标签分布
        """
        records = self.list_user_records(user_id)
        miss_reason_counts = self._count_field(records, "miss_reason")
        human_label_counts = self._count_field(records, "human_label")
        return {
            "total_count": len(records),
            "miss_reason_counts": miss_reason_counts,
            "human_label_counts": human_label_counts,
            "latest_created_at": records[0]["created_at"] if records else None
        }

    def _init_db(self) -> None:
        """初始化 SQLite 表结构"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_evaluation_records (
                    record_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    optimized_query TEXT,
                    retrieved_ids TEXT NOT NULL,
                    miss_reason TEXT NOT NULL,
                    human_label TEXT,
                    request_id TEXT,
                    retrieval_strategy TEXT DEFAULT '',
                    latency_ms INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "request_id", "TEXT")
            self._ensure_column(conn, "retrieval_strategy", "TEXT DEFAULT ''")
            self._ensure_column(conn, "latency_ms", "INTEGER DEFAULT 0")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_evaluation_user_created "
                "ON rag_evaluation_records(user_id, created_at DESC)"
            )

    def _ensure_column(self, conn: sqlite3.Connection, column_name: str, column_spec: str) -> None:
        """兼容旧 SQLite 表，缺列时按需迁移。"""
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(rag_evaluation_records)").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE rag_evaluation_records ADD COLUMN {column_name} {column_spec}")

    def _save_record(self, record: dict) -> None:
        """保存评测记录到 SQLite"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO rag_evaluation_records (
                    record_id, user_id, query, optimized_query, retrieved_ids,
                    miss_reason, human_label, request_id, retrieval_strategy,
                    latency_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["record_id"],
                    record["user_id"],
                    record["query"],
                    record["optimized_query"],
                    json.dumps(record["retrieved_ids"], ensure_ascii=False),
                    record["miss_reason"],
                    record["human_label"],
                    record["request_id"],
                    record["retrieval_strategy"],
                    record["latency_ms"],
                    record["created_at"]
                )
            )

    def _trim_user_records(self, user_id: str) -> None:
        """按用户上限裁剪旧评测记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                DELETE FROM rag_evaluation_records
                WHERE user_id = ?
                  AND record_id NOT IN (
                    SELECT record_id FROM rag_evaluation_records
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                  )
                """,
                (user_id, user_id, self.max_items_per_user)
            )

    def _list_user_records_from_db(self, user_id: str) -> List[dict]:
        """从 SQLite 读取用户评测记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM rag_evaluation_records
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, self.max_items_per_user)
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def _row_to_record(self, row: sqlite3.Row) -> dict:
        """将 SQLite 行转换为 API 记录"""
        return {
            "record_id": row["record_id"],
            "user_id": row["user_id"],
            "query": row["query"],
            "optimized_query": row["optimized_query"],
            "retrieved_ids": json.loads(row["retrieved_ids"] or "[]"),
            "miss_reason": row["miss_reason"],
            "human_label": row["human_label"],
            "request_id": row["request_id"],
            "retrieval_strategy": row["retrieval_strategy"],
            "latency_ms": row["latency_ms"],
            "created_at": row["created_at"]
        }

    def _count_field(self, records: List[dict], field_name: str) -> Dict[str, int]:
        """统计记录中指定字段的非空值分布"""
        counts: Dict[str, int] = {}
        for record in records:
            value = record.get(field_name)
            if value:
                counts[value] = counts.get(value, 0) + 1
        return counts

    def _protect_against_bad_rerank_cache(self, record_input: RagEvaluationRecordInput) -> None:
        """bad case 反馈后绕过相关 query 的 Rerank 缓存。"""
        if not self._is_bad_feedback(record_input):
            return
        cache_service = self.cache_service or get_cache_service()
        cache_service.bypass_rerank_cache(record_input.query, reason=self._feedback_reason(record_input))
        if record_input.optimized_query:
            cache_service.bypass_rerank_cache(record_input.optimized_query, reason=self._feedback_reason(record_input))

    def _is_bad_feedback(self, record_input: RagEvaluationRecordInput) -> bool:
        """判断评测记录是否代表用户不满意。"""
        bad_label = (record_input.human_label or "").lower() in {"bad", "poor", "incorrect", "不满意", "错误"}
        bad_reason = record_input.miss_reason in {
            "intent_error",
            "recall_miss",
            "rerank_error",
            "generation_error",
            "stale_knowledge",
        }
        return bad_label or bad_reason

    def _feedback_reason(self, record_input: RagEvaluationRecordInput) -> str:
        """构造缓存绕过原因。"""
        if record_input.human_label:
            return f"feedback:{record_input.human_label}"
        return f"miss_reason:{record_input.miss_reason}"


_evaluation_service: Optional[RagEvaluationService] = None


def get_rag_evaluation_service() -> RagEvaluationService:
    """获取 RAG 检索评测记录服务单例"""
    global _evaluation_service
    if _evaluation_service is None:
        _evaluation_service = RagEvaluationService(db_path=Config.RAG_STATE_DB_PATH or None)
    return _evaluation_service
