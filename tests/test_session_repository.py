import sqlite3

from app.models.agent_schemas import AgentEvent, AgentRun, AgentSession
from app.services.session_repository import SessionRepository


def _make_session(session_id: str = "sess_001", user_id: str = "u001") -> AgentSession:
    """构造测试 session。"""
    return AgentSession(
        session_id=session_id,
        user_id=user_id,
        runtime_id=f"local:{user_id}:{session_id}",
        title="白屏排查",
        created_at="2026-06-02T10:00:00Z",
        updated_at="2026-06-02T10:00:00Z",
    )


def _make_run(run_id: str = "run_001", session_id: str = "sess_001", user_id: str = "u001") -> AgentRun:
    """构造测试 run。"""
    return AgentRun(
        run_id=run_id,
        user_id=user_id,
        session_id=session_id,
        input="小程序上线后白屏",
        status="queued",
        tools=["optimize_query"],
        created_at="2026-06-02T10:00:00Z",
        updated_at="2026-06-02T10:00:00Z",
    )


def _make_event(sequence: int, event_id: str, event: str = "answer.delta") -> AgentEvent:
    """构造测试 event。"""
    return AgentEvent(
        event_id=event_id,
        event=event,
        user_id="u001",
        session_id="sess_001",
        run_id="run_001",
        request_id="req_001",
        sequence=sequence,
        payload={"sequence": sequence},
        created_at="2026-06-02T10:00:00Z",
    )


def test_repository_persists_session_run_and_events_across_instances(tmp_path):
    db_path = tmp_path / "agent_sessions.sqlite3"
    repository = SessionRepository(str(db_path), max_events_per_run=10)
    session = _make_session()
    run = _make_run()
    first = _make_event(1, "evt_001", "run.created")
    second = _make_event(2, "evt_002", "answer.completed")

    repository.save_session(session)
    repository.save_run(run)
    repository.append_event(first)
    repository.append_event(second)

    restored = SessionRepository(str(db_path), max_events_per_run=10)

    assert restored.get_session("u001", "sess_001") == session
    assert restored.get_run("u001", "sess_001", "run_001") == run
    assert [event.event_id for event in restored.list_events("u001", "sess_001", "run_001")] == [
        "evt_001",
        "evt_002",
    ]


def test_repository_rejects_cross_user_reads(tmp_path):
    repository = SessionRepository(str(tmp_path / "agent_sessions.sqlite3"))
    repository.save_session(_make_session())

    assert repository.get_session("u002", "sess_001") is None


def test_repository_lists_sessions_and_runs_by_user(tmp_path):
    repository = SessionRepository(str(tmp_path / "agent_sessions.sqlite3"))
    first = _make_session("sess_001", "u001")
    second = _make_session("sess_002", "u001")
    other = _make_session("sess_003", "u002")
    repository.save_session(first)
    repository.save_session(second)
    repository.save_session(other)
    repository.save_run(_make_run("run_001", "sess_001", "u001"))
    repository.save_run(_make_run("run_002", "sess_001", "u001"))

    sessions = repository.list_sessions("u001")
    runs = repository.list_runs("u001", "sess_001")

    assert [session.session_id for session in sessions] == ["sess_002", "sess_001"]
    assert [run.run_id for run in runs] == ["run_002", "run_001"]


def test_repository_lists_events_after_event_id(tmp_path):
    repository = SessionRepository(str(tmp_path / "agent_sessions.sqlite3"), max_events_per_run=10)
    repository.save_session(_make_session())
    repository.save_run(_make_run())
    repository.append_event(_make_event(1, "evt_001"))
    repository.append_event(_make_event(2, "evt_002"))
    repository.append_event(_make_event(3, "evt_003"))

    events = repository.list_events("u001", "sess_001", "run_001", after_event_id="evt_001")

    assert [event.event_id for event in events] == ["evt_002", "evt_003"]


def test_repository_trims_old_events_and_keeps_latest_sequence(tmp_path):
    repository = SessionRepository(str(tmp_path / "agent_sessions.sqlite3"), max_events_per_run=2)
    repository.save_session(_make_session())
    repository.save_run(_make_run())

    repository.append_event(_make_event(1, "evt_001"))
    repository.append_event(_make_event(2, "evt_002"))
    repository.append_event(_make_event(3, "evt_003"))

    events = repository.list_events("u001", "sess_001", "run_001")

    assert [event.event_id for event in events] == ["evt_002", "evt_003"]
    assert repository.next_event_sequence("u001", "sess_001", "run_001") == 4


def test_repository_creates_indexes(tmp_path):
    db_path = tmp_path / "agent_sessions.sqlite3"
    SessionRepository(str(db_path))

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_agent_%'"
        ).fetchall()

    assert {row[0] for row in rows} >= {
        "idx_agent_sessions_user",
        "idx_agent_runs_user_session",
        "idx_agent_events_run_sequence",
    }
