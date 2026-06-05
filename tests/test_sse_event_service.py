import json

from app.models.agent_schemas import AgentEvent
from app.services.sse_event_service import build_event, encode_sse_event


def test_encode_sse_event_uses_event_name_and_json_data():
    event = AgentEvent(
        event_id="evt_001",
        event="request.created",
        user_id="u001",
        request_id="req_001",
        sequence=1,
        payload={"input": "白屏"},
        created_at="2026-06-02T10:00:00Z",
    )

    encoded = encode_sse_event(event)

    assert encoded.startswith("event: request.created\n")
    assert encoded.endswith("\n\n")
    data_line = encoded.split("data: ", 1)[1].strip()
    data = json.loads(data_line)
    assert data["event_id"] == "evt_001"
    assert data["payload"]["input"] == "白屏"


def test_build_event_fills_common_fields():
    event = build_event(
        event="query.decomposition",
        user_id="u001",
        sequence=2,
        payload={"intent": "troubleshooting"},
        request_id="req_001",
    )

    assert event.event_id.startswith("evt_")
    assert event.created_at
    assert event.request_id == "req_001"


def test_encode_sse_event_redacts_sensitive_payload_fields():
    event = build_event(
        event="agent.tool_call.started",
        user_id="u001",
        sequence=1,
        payload={
            "api_key": "secret",
            "nested": {"token": "secret-token", "safe": "visible"},
            "password": "hidden",
        },
    )

    data_line = encode_sse_event(event).split("data: ", 1)[1].strip()
    data = json.loads(data_line)

    assert data["payload"]["api_key"] == "[REDACTED]"
    assert data["payload"]["password"] == "[REDACTED]"
    assert data["payload"]["nested"]["token"] == "[REDACTED]"
    assert data["payload"]["nested"]["safe"] == "visible"
