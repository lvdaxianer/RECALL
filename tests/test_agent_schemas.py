from pydantic import ValidationError

from app.models.agent_schemas import (
    AgentEvent,
    AgentRun,
    AgentSession,
    AgentToolCall,
    SandboxProfile,
)


def test_agent_session_requires_user_and_runtime():
    session = AgentSession(
        session_id="sess_001",
        user_id="u001",
        runtime_id="local:u001:sess_001",
        title="白屏排查",
        created_at="2026-06-02T10:00:00Z",
        updated_at="2026-06-02T10:00:00Z",
    )

    assert session.status == "active"
    assert session.metadata == {}


def test_agent_run_status_is_validated():
    run = AgentRun(
        run_id="run_001",
        user_id="u001",
        session_id="sess_001",
        input="小程序上线后白屏",
        status="running",
        created_at="2026-06-02T10:00:00Z",
        updated_at="2026-06-02T10:00:00Z",
    )

    assert run.tools == []
    assert run.request_id is None


def test_agent_run_rejects_unknown_status():
    try:
        AgentRun(
            run_id="run_001",
            user_id="u001",
            session_id="sess_001",
            input="小程序上线后白屏",
            status="unknown",
            created_at="2026-06-02T10:00:00Z",
            updated_at="2026-06-02T10:00:00Z",
        )
    except ValidationError as exc:
        assert "status" in str(exc)
    else:
        raise AssertionError("expected ValidationError")


def test_agent_event_defaults_payload():
    event = AgentEvent(
        event_id="evt_001",
        event="request.created",
        user_id="u001",
        sequence=1,
        created_at="2026-06-02T10:00:00Z",
    )

    assert event.payload == {}
    assert event.session_id is None


def test_tool_call_and_sandbox_profile_models():
    tool_call = AgentToolCall(
        tool_call_id="tool_001",
        run_id="run_001",
        tool_name="search_rag",
        status="completed",
    )
    profile = SandboxProfile(
        user_id="u001",
        session_id="sess_001",
        runtime_id="local:u001:sess_001",
        namespace="rag-agent:u001:sess_001",
        memory_path="var/agent_profiles/u001/sess_001/memory",
        config_path="var/agent_profiles/u001/sess_001/config",
        cache_namespace="u001:sess_001",
    )

    assert tool_call.arguments == {}
    assert profile.namespace == "rag-agent:u001:sess_001"
