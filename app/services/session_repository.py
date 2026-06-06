"""
Agent Session SQLite Repository

持久化 session、run 和 event，支持断点续传和事件裁剪。

@author lvdaxianerplus
@date 2026-06-03
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

from app.models.agent_schemas import AgentEvent, AgentRun, AgentSession

DEFAULT_REPOSITORY_MAX_EVENTS = 500


class SessionRepository:
    """SQLite 版 Agent session/run/event 仓储。"""

    def __init__(self, db_path: str, max_events_per_run: int = DEFAULT_REPOSITORY_MAX_EVENTS):
        self.db_path = db_path
        self.max_events_per_run = max_events_per_run
        self._init_db()

    def save_session(self, session: AgentSession) -> AgentSession:
        """保存或更新 session。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_sessions (
                    session_id, user_id, runtime_id, title, status, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.user_id,
                    session.runtime_id,
                    session.title,
                    session.status,
                    _to_json(session.metadata),
                    session.created_at,
                    session.updated_at,
                ),
            )
        return session

    def get_session(self, user_id: str, session_id: str) -> Optional[AgentSession]:
        """读取指定用户的 session。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()
        if row is None:
            return None
        else:
            return _row_to_session(row)

    def list_sessions(self, user_id: str) -> list[AgentSession]:
        """列出指定用户的 sessions。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_sessions
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC, session_id DESC
                """,
                (user_id,),
            ).fetchall()
        return [_row_to_session(row) for row in rows]

    def save_run(self, run: AgentRun) -> AgentRun:
        """保存或更新 run。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_runs (
                    run_id, user_id, session_id, request_id, input, status,
                    tools, answer, error, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.user_id,
                    run.session_id,
                    run.request_id,
                    run.input,
                    run.status,
                    _to_json(run.tools),
                    run.answer,
                    _to_json(run.error),
                    _to_json(run.metadata),
                    run.created_at,
                    run.updated_at,
                ),
            )
        return run

    def get_run(self, user_id: str, session_id: str, run_id: str) -> Optional[AgentRun]:
        """读取指定用户和 session 下的 run。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_runs
                WHERE user_id = ? AND session_id = ? AND run_id = ?
                """,
                (user_id, session_id, run_id),
            ).fetchone()
        if row is None:
            return None
        else:
            return _row_to_run(row)

    def list_runs(self, user_id: str, session_id: str) -> list[AgentRun]:
        """列出指定用户和 session 下的 runs。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_runs
                WHERE user_id = ? AND session_id = ?
                ORDER BY created_at DESC, run_id DESC
                """,
                (user_id, session_id),
            ).fetchall()
        return [_row_to_run(row) for row in rows]

    def append_event(self, event: AgentEvent) -> AgentEvent:
        """追加事件并裁剪旧事件。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_events (
                    event_id, event, user_id, session_id, run_id, request_id, sequence, payload, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event,
                    event.user_id,
                    event.session_id,
                    event.run_id,
                    event.request_id,
                    event.sequence,
                    _to_json(event.payload),
                    event.created_at,
                ),
            )
            self._trim_events(conn, event.user_id, event.session_id or "", event.run_id or "")
        return event

    def list_events(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        after_event_id: Optional[str] = None,
    ) -> list[AgentEvent]:
        """按 sequence 列出事件，支持 after_event_id。"""
        after_sequence = self._find_event_sequence(user_id, session_id, run_id, after_event_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_events
                WHERE user_id = ? AND session_id = ? AND run_id = ? AND sequence > ?
                ORDER BY sequence ASC
                """,
                (user_id, session_id, run_id, after_sequence),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def next_event_sequence(self, user_id: str, session_id: str, run_id: str) -> int:
        """读取下一条事件序号。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS max_sequence
                FROM agent_events
                WHERE user_id = ? AND session_id = ? AND run_id = ?
                """,
                (user_id, session_id, run_id),
            ).fetchone()
        return int(row["max_sequence"]) + 1

    def _init_db(self) -> None:
        """初始化 SQLite 表和索引。"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._create_tables(conn)
            self._create_indexes(conn)

    def _connect(self) -> sqlite3.Connection:
        """创建 SQLite 连接。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """创建 repository 表结构。"""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                runtime_id TEXT NOT NULL,
                title TEXT,
                status TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                request_id TEXT,
                input TEXT NOT NULL,
                status TEXT NOT NULL,
                tools TEXT NOT NULL,
                answer TEXT,
                error TEXT,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_events (
                event_id TEXT PRIMARY KEY,
                event TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                request_id TEXT,
                sequence INTEGER NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """创建查询索引。"""
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_sessions_user ON agent_sessions(user_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_user_session "
            "ON agent_runs(user_id, session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_events_run_sequence "
            "ON agent_events(user_id, session_id, run_id, sequence)"
        )

    def _trim_events(self, conn: sqlite3.Connection, user_id: str, session_id: str, run_id: str) -> None:
        """按 run 裁剪旧事件。"""
        conn.execute(
            """
            DELETE FROM agent_events
            WHERE user_id = ? AND session_id = ? AND run_id = ?
              AND event_id NOT IN (
                SELECT event_id FROM agent_events
                WHERE user_id = ? AND session_id = ? AND run_id = ?
                ORDER BY sequence DESC
                LIMIT ?
              )
            """,
            (user_id, session_id, run_id, user_id, session_id, run_id, self.max_events_per_run),
        )

    def _find_event_sequence(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        event_id: Optional[str],
    ) -> int:
        """按 event_id 查找断点 sequence。"""
        if event_id is None:
            return 0
        else:
            pass
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sequence FROM agent_events
                WHERE user_id = ? AND session_id = ? AND run_id = ? AND event_id = ?
                """,
                (user_id, session_id, run_id, event_id),
            ).fetchone()
        if row is None:
            return 0
        else:
            return int(row["sequence"])


def _to_json(value) -> str:
    """序列化 JSON 字段。"""
    return json.dumps(value, ensure_ascii=False)


def _from_json(value: Optional[str], default):
    """反序列化 JSON 字段。"""
    if value is None:
        return default
    else:
        return json.loads(value)


def _row_to_session(row: sqlite3.Row) -> AgentSession:
    """转换 session row。"""
    return AgentSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        runtime_id=row["runtime_id"],
        title=row["title"],
        status=row["status"],
        metadata=_from_json(row["metadata"], {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_run(row: sqlite3.Row) -> AgentRun:
    """转换 run row。"""
    return AgentRun(
        run_id=row["run_id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        request_id=row["request_id"],
        input=row["input"],
        status=row["status"],
        tools=_from_json(row["tools"], []),
        answer=row["answer"],
        error=_from_json(row["error"], None),
        metadata=_from_json(row["metadata"], {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_event(row: sqlite3.Row) -> AgentEvent:
    """转换 event row。"""
    return AgentEvent(
        event_id=row["event_id"],
        event=row["event"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        run_id=row["run_id"],
        request_id=row["request_id"],
        sequence=row["sequence"],
        payload=_from_json(row["payload"], {}),
        created_at=row["created_at"],
    )
