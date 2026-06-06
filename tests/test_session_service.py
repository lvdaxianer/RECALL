import pytest

from app.services.session_service import SessionNotFoundError, SessionService
from app.services.session_repository import SessionRepository


def test_create_session_is_isolated_by_user():
    service = SessionService()

    first = service.create_session("u001", title="白屏排查")
    second = service.create_session("u002", title="登录排查")

    assert first.user_id == "u001"
    assert second.user_id == "u002"
    assert first.session_id != second.session_id
    assert first.runtime_id.startswith("local:u001:")


def test_get_session_rejects_cross_user_access():
    service = SessionService()
    session = service.create_session("u001")

    with pytest.raises(SessionNotFoundError):
        service.get_session("u002", session.session_id)


def test_create_run_records_run_under_session():
    service = SessionService()
    session = service.create_session("u001")

    run = service.create_run(
        user_id="u001",
        session_id=session.session_id,
        input_text="小程序上线后白屏",
        tools=["optimize_query", "search_rag"],
        metadata={"client_request_id": "web-001"},
    )

    assert run.status == "queued"
    assert run.tools == ["optimize_query", "search_rag"]
    assert service.get_run("u001", session.session_id, run.run_id).input == "小程序上线后白屏"


def test_list_sessions_and_runs_are_user_scoped():
    service = SessionService()
    first = service.create_session("u001", title="白屏排查")
    second = service.create_session("u001", title="登录排查")
    service.create_session("u002", title="其他用户")
    run = service.create_run("u001", first.session_id, "小程序上线后白屏")

    sessions = service.list_sessions("u001")
    runs = service.list_runs("u001", first.session_id)

    assert [session.session_id for session in sessions] == [second.session_id, first.session_id]
    assert [item.run_id for item in runs] == [run.run_id]


def test_append_and_list_events_are_ordered():
    service = SessionService()
    session = service.create_session("u001")
    run = service.create_run("u001", session.session_id, "白屏")

    first = service.append_event("u001", session.session_id, run.run_id, "run.created", {"status": "running"})
    second = service.append_event("u001", session.session_id, run.run_id, "answer.completed", {"answer": "检查域名"})

    events = service.list_events("u001", session.session_id, run.run_id)

    assert [event.event_id for event in events] == [first.event_id, second.event_id]
    assert [event.sequence for event in events] == [1, 2]


def test_list_events_after_event_id_returns_following_events():
    service = SessionService()
    session = service.create_session("u001")
    run = service.create_run("u001", session.session_id, "白屏")
    first = service.append_event("u001", session.session_id, run.run_id, "run.created")
    second = service.append_event("u001", session.session_id, run.run_id, "answer.delta")

    events = service.list_events("u001", session.session_id, run.run_id, after_event_id=first.event_id)

    assert [event.event_id for event in events] == [second.event_id]


def test_update_run_keeps_ownership_and_sets_answer():
    service = SessionService()
    session = service.create_session("u001")
    run = service.create_run("u001", session.session_id, "白屏")

    updated = service.update_run("u001", session.session_id, run.run_id, status="completed", answer="检查域名")

    assert updated.status == "completed"
    assert updated.answer == "检查域名"


def test_event_sequence_stays_monotonic_after_trimming():
    service = SessionService(max_events_per_run=1)
    session = service.create_session("u001")
    run = service.create_run("u001", session.session_id, "白屏")

    service.append_event("u001", session.session_id, run.run_id, "run.created")
    service.append_event("u001", session.session_id, run.run_id, "answer.delta")
    latest = service.append_event("u001", session.session_id, run.run_id, "answer.completed")

    assert latest.sequence == 3
    assert service.list_events("u001", session.session_id, run.run_id)[0].sequence == 3


def test_session_service_persists_state_when_repository_is_provided(tmp_path):
    repository = SessionRepository(str(tmp_path / "agent_sessions.sqlite3"), max_events_per_run=10)
    service = SessionService(repository=repository)
    session = service.create_session("u001", title="白屏排查")
    run = service.create_run("u001", session.session_id, "小程序上线后白屏", tools=["search_rag"])
    event = service.append_event(
        "u001",
        session.session_id,
        run.run_id,
        "answer.completed",
        {"answer": "检查域名"},
        request_id="req_001",
    )

    restored_service = SessionService(repository=SessionRepository(str(tmp_path / "agent_sessions.sqlite3")))

    restored_run = restored_service.get_run("u001", session.session_id, run.run_id)
    restored_events = restored_service.list_events("u001", session.session_id, run.run_id)

    assert restored_service.get_session("u001", session.session_id).title == "白屏排查"
    assert restored_run.tools == ["search_rag"]
    assert restored_events[0].event_id == event.event_id


def test_session_service_repository_sequence_continues_after_restart(tmp_path):
    db_path = tmp_path / "agent_sessions.sqlite3"
    first_service = SessionService(repository=SessionRepository(str(db_path), max_events_per_run=2))
    session = first_service.create_session("u001")
    run = first_service.create_run("u001", session.session_id, "白屏")
    first_service.append_event("u001", session.session_id, run.run_id, "run.created")
    first_service.append_event("u001", session.session_id, run.run_id, "answer.delta")

    second_service = SessionService(repository=SessionRepository(str(db_path), max_events_per_run=2))
    event = second_service.append_event("u001", session.session_id, run.run_id, "answer.completed")

    assert event.sequence == 3


def test_get_session_service_uses_repository_when_state_db_path_is_configured(tmp_path, monkeypatch):
    import app.services.session_service as session_module

    db_path = tmp_path / "agent_sessions.sqlite3"
    monkeypatch.setattr(session_module.Config, "RAG_STATE_DB_PATH", str(db_path))
    monkeypatch.setattr(session_module, "_session_service", None)

    service = session_module.get_session_service()

    assert service.repository is not None


def test_get_session_service_uses_memory_when_state_db_path_is_empty(monkeypatch):
    import app.services.session_service as session_module

    monkeypatch.setattr(session_module.Config, "RAG_STATE_DB_PATH", "")
    monkeypatch.setattr(session_module, "_session_service", None)

    service = session_module.get_session_service()

    assert service.repository is None
