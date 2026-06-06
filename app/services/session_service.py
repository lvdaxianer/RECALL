"""
Agent Session 生命周期服务

第一阶段使用内存存储，后续可替换为 SQLite、Redis 或数据库。

@author lvdaxianerplus
@date 2026-06-02
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import Config
from app.models.agent_schemas import AgentEvent, AgentRun, AgentSession
from app.services.session_repository import SessionRepository

DEFAULT_MAX_EVENTS_PER_RUN = 500


class SessionNotFoundError(ValueError):
    """会话或执行不存在，或不属于当前用户。"""


def _now_iso() -> str:
    """生成 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


class SessionService:
    """内存版 Agent 会话服务"""

    def __init__(
        self,
        max_events_per_run: int = DEFAULT_MAX_EVENTS_PER_RUN,
        repository: Optional[SessionRepository] = None,
    ):
        self.max_events_per_run = max_events_per_run
        self.repository = repository
        self._sessions: dict[str, AgentSession] = {}
        self._runs: dict[str, AgentRun] = {}
        self._events: dict[str, list[AgentEvent]] = {}
        self._event_sequences: dict[str, int] = {}

    def create_session(
        self,
        user_id: str,
        title: Optional[str] = None,
        runtime: str = "local",
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentSession:
        """创建归属于指定用户的 Agent 会话。"""
        created_at = _now_iso()
        session_id = f"sess_{uuid.uuid4().hex}"
        session = AgentSession(
            session_id=session_id,
            user_id=user_id,
            runtime_id=f"{runtime}:{user_id}:{session_id}",
            title=title,
            metadata=metadata or {},
            created_at=created_at,
            updated_at=created_at,
        )
        if self.repository is not None:
            self.repository.save_session(session)
        else:
            self._sessions[self._session_key(user_id, session_id)] = session
        return session

    def get_session(self, user_id: str, session_id: str) -> AgentSession:
        """按用户和会话 ID 获取会话。"""
        session = self._get_session_or_none(user_id, session_id)
        if session is None:
            raise SessionNotFoundError(f"session not found: {session_id}")
        else:
            return session

    def list_sessions(self, user_id: str) -> list[AgentSession]:
        """列出指定用户的 sessions。"""
        if self.repository is not None:
            return self.repository.list_sessions(user_id)
        else:
            sessions = [
                session
                for session in self._sessions.values()
                if session.user_id == user_id
            ]
            return sorted(
                sessions,
                key=lambda session: (session.updated_at, session.created_at, session.session_id),
                reverse=True,
            )

    def create_run(
        self,
        user_id: str,
        session_id: str,
        input_text: str,
        tools: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentRun:
        """创建一次 Agent run 并绑定到会话。"""
        self.get_session(user_id, session_id)
        created_at = _now_iso()
        run_id = f"run_{uuid.uuid4().hex}"
        run = AgentRun(
            run_id=run_id,
            user_id=user_id,
            session_id=session_id,
            input=input_text,
            status="queued",
            tools=tools or [],
            metadata=metadata or {},
            created_at=created_at,
            updated_at=created_at,
        )
        if self.repository is not None:
            self.repository.save_run(run)
        else:
            self._runs[self._run_key(user_id, session_id, run_id)] = run
            self._event_sequences[self._run_key(user_id, session_id, run_id)] = 0
        return run

    def get_run(self, user_id: str, session_id: str, run_id: str) -> AgentRun:
        """按用户、会话和 run ID 获取执行记录。"""
        self.get_session(user_id, session_id)
        run = self._get_run_or_none(user_id, session_id, run_id)
        if run is None:
            raise SessionNotFoundError(f"run not found: {run_id}")
        else:
            return run

    def list_runs(self, user_id: str, session_id: str) -> list[AgentRun]:
        """列出指定 session 下的 runs。"""
        self.get_session(user_id, session_id)
        if self.repository is not None:
            return self.repository.list_runs(user_id, session_id)
        else:
            runs = [
                run
                for run in self._runs.values()
                if run.user_id == user_id and run.session_id == session_id
            ]
            return sorted(runs, key=lambda run: (run.created_at, run.run_id), reverse=True)

    def update_run(self, user_id: str, session_id: str, run_id: str, **changes: Any) -> AgentRun:
        """更新 run 状态或结果字段。"""
        run = self.get_run(user_id, session_id, run_id)
        data = run.model_dump()
        data.update(changes)
        data["updated_at"] = _now_iso()
        updated = AgentRun(**data)
        if self.repository is not None:
            self.repository.save_run(updated)
        else:
            self._runs[self._run_key(user_id, session_id, run_id)] = updated
        return updated

    def append_event(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        event: str,
        payload: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> AgentEvent:
        """追加 run 事件并维护单调序号。"""
        self.get_run(user_id, session_id, run_id)
        key = self._run_key(user_id, session_id, run_id)
        sequence = self._next_event_sequence(user_id, session_id, run_id, key)
        agent_event = AgentEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            event=event,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            request_id=request_id,
            sequence=sequence,
            payload=payload or {},
            created_at=_now_iso(),
        )
        if self.repository is not None:
            self.repository.append_event(agent_event)
        else:
            events = self._events.setdefault(key, [])
            events.append(agent_event)
            del events[:-self.max_events_per_run]
        return agent_event

    def list_events(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        after_event_id: Optional[str] = None,
    ) -> list[AgentEvent]:
        """列出 run 事件，支持按事件 ID 断点续传。"""
        self.get_run(user_id, session_id, run_id)
        if self.repository is not None:
            return self.repository.list_events(user_id, session_id, run_id, after_event_id)
        else:
            events = list(self._events.get(self._run_key(user_id, session_id, run_id), []))
            if after_event_id is None:
                return events
            else:
                return self._list_events_after(events, after_event_id)

    @staticmethod
    def _list_events_after(events: list[AgentEvent], after_event_id: str) -> list[AgentEvent]:
        """返回指定事件之后的事件列表。"""
        for index, event in enumerate(events):
            if event.event_id == after_event_id:
                return events[index + 1:]
            else:
                continue
        return events

    def _next_event_sequence(self, user_id: str, session_id: str, run_id: str, key: str) -> int:
        """递增并返回 run 级事件序号。"""
        if self.repository is not None:
            return self.repository.next_event_sequence(user_id, session_id, run_id)
        else:
            next_sequence = self._event_sequences.get(key, 0) + 1
            self._event_sequences[key] = next_sequence
            return next_sequence

    def _get_session_or_none(self, user_id: str, session_id: str) -> Optional[AgentSession]:
        """读取 session，支持 repository 或内存存储。"""
        if self.repository is not None:
            return self.repository.get_session(user_id, session_id)
        else:
            return self._sessions.get(self._session_key(user_id, session_id))

    def _get_run_or_none(self, user_id: str, session_id: str, run_id: str) -> Optional[AgentRun]:
        """读取 run，支持 repository 或内存存储。"""
        if self.repository is not None:
            return self.repository.get_run(user_id, session_id, run_id)
        else:
            return self._runs.get(self._run_key(user_id, session_id, run_id))

    @staticmethod
    def _session_key(user_id: str, session_id: str) -> str:
        """构造用户隔离的 session key。"""
        return f"{user_id}:{session_id}"

    @staticmethod
    def _run_key(user_id: str, session_id: str, run_id: str) -> str:
        """构造用户隔离的 run key。"""
        return f"{user_id}:{session_id}:{run_id}"


_session_service: Optional[SessionService] = None


def get_session_service() -> SessionService:
    """获取全局内存 SessionService 实例。"""
    global _session_service
    if _session_service is None:
        _session_service = _build_session_service()
    else:
        pass
    return _session_service


def _build_session_service() -> SessionService:
    """按配置构建 SessionService。"""
    if Config.RAG_STATE_DB_PATH:
        repository = SessionRepository(
            Config.RAG_STATE_DB_PATH,
            max_events_per_run=DEFAULT_MAX_EVENTS_PER_RUN,
        )
        return SessionService(repository=repository)
    else:
        return SessionService()
