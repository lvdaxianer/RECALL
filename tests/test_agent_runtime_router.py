import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.session_service import SessionService


class FakeRuntimeClient:
    """测试用本地 Runtime，避免调用外部模型。"""

    def __init__(self, session_service):
        self.session_service = session_service

    async def run(self, user_id, session_id, run_id):
        self.session_service.update_run(user_id, session_id, run_id, status="running")
        yield self.session_service.append_event(user_id, session_id, run_id, "run.created", {"status": "running"})
        self.session_service.update_run(user_id, session_id, run_id, status="completed", answer="检查域名")
        yield self.session_service.append_event(user_id, session_id, run_id, "answer.completed", {"answer": "检查域名"})


class FakeSandboxService:
    """测试用 SandboxService。"""

    def __init__(self):
        self.profiles = []

    def build_profile(self, user_id, session_id, runtime="local"):
        from app.models.agent_schemas import SandboxProfile

        profile = SandboxProfile(
            user_id=user_id,
            session_id=session_id,
            runtime_id=f"{runtime}:{user_id}:{session_id}",
            namespace=f"rag-agent:{user_id}:{session_id}",
            memory_path=f"var/agent_profiles/{user_id}/{session_id}/memory",
            config_path=f"var/agent_profiles/{user_id}/{session_id}/config",
            cache_namespace=f"{user_id}:{session_id}",
        )
        self.profiles.append(profile)
        return profile

    def ensure_profile_directories(self, profile):
        return profile


class FakeRuntimeOrchestrator:
    """测试用 RuntimeOrchestrator。"""

    def __init__(self):
        self.runtime_ids = []
        self.statuses = {}

    def ensure_runtime(self, profile):
        self.runtime_ids.append(profile.runtime_id)
        self.statuses[profile.runtime_id] = "running"
        return {"runtime_id": profile.runtime_id, "status": "running"}

    def health_check(self, runtime_id):
        return {"runtime_id": runtime_id, "status": self.statuses.get(runtime_id, "not_found")}

    def stop_runtime(self, runtime_id):
        self.statuses[runtime_id] = "stopped"
        return {"runtime_id": runtime_id, "status": "stopped"}

    def cleanup_idle_runtimes(self):
        return {"stopped_count": 0}


@pytest.fixture
def app_router(monkeypatch):
    """加载包含 Agent Runtime 路由的 FastAPI app，并隔离全局 session 服务。"""
    service = SessionService()
    sandbox = FakeSandboxService()
    orchestrator = FakeRuntimeOrchestrator()
    monkeypatch.setattr("app.routers.agent_runtime.get_session_service", lambda: service)
    monkeypatch.setattr("app.routers.agent_runtime.get_agent_runtime_client", lambda: FakeRuntimeClient(service))
    monkeypatch.setattr("app.routers.agent_runtime.get_sandbox_service", lambda: sandbox)
    monkeypatch.setattr("app.routers.agent_runtime.get_runtime_orchestrator", lambda: orchestrator)
    from app.main import app

    app.state.fake_sandbox = sandbox
    app.state.fake_orchestrator = orchestrator
    return app


@pytest_asyncio.fixture
async def async_client(app_router):
    """构建异步 HTTP 客户端。"""
    transport = ASGITransport(app=app_router)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_create_agent_session(async_client):
    response = await async_client.post(
        "/api/v1/agent/u001/sessions",
        json={"title": "白屏排查", "runtime": "local", "metadata": {"source": "test"}},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user_id"] == "u001"
    assert data["session_id"].startswith("sess_")
    assert data["runtime_id"].startswith("local:u001:")


@pytest.mark.asyncio
async def test_list_agent_sessions_and_runs(async_client):
    first = await async_client.post("/api/v1/agent/u001/sessions", json={"title": "白屏排查"})
    await async_client.post("/api/v1/agent/u001/sessions", json={"title": "登录排查"})
    session_id = first.json()["data"]["session_id"]
    run_response = await async_client.post(
        f"/api/v1/agent/u001/sessions/{session_id}/runs",
        json={"input": "小程序上线后白屏", "stream": False, "tools": ["optimize_query"]},
    )

    sessions_response = await async_client.get("/api/v1/agent/u001/sessions")
    runs_response = await async_client.get(f"/api/v1/agent/u001/sessions/{session_id}/runs")

    assert sessions_response.status_code == 200
    assert [item["title"] for item in sessions_response.json()["data"]] == ["登录排查", "白屏排查"]
    assert runs_response.status_code == 200
    assert runs_response.json()["data"][0]["run_id"] == run_response.json()["data"]["run_id"]


@pytest.mark.asyncio
async def test_create_agent_session_ensures_runtime_profile(async_client, app_router):
    response = await async_client.post(
        "/api/v1/agent/u001/sessions",
        json={"title": "白屏排查", "runtime": "local"},
    )

    session_id = response.json()["data"]["session_id"]

    assert app_router.state.fake_sandbox.profiles[0].session_id == session_id
    assert app_router.state.fake_orchestrator.runtime_ids[0].endswith(session_id)


@pytest.mark.asyncio
async def test_update_agent_session_title(async_client):
    """Agent session 支持手动改名。"""
    session_response = await async_client.post(
        "/api/v1/agent/u001/sessions",
        json={"title": "新的检索会话", "runtime": "local"},
    )
    session_id = session_response.json()["data"]["session_id"]

    response = await async_client.patch(
        f"/api/v1/agent/u001/sessions/{session_id}",
        json={"title": "小程序白屏排查"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"] == "小程序白屏排查"
    assert data["metadata"]["title_source"] == "manual"


@pytest.mark.asyncio
async def test_runtime_health_stop_and_cleanup(async_client):
    session_response = await async_client.post(
        "/api/v1/agent/u001/sessions",
        json={"title": "白屏排查", "runtime": "local"},
    )
    runtime_id = session_response.json()["data"]["runtime_id"]

    health_response = await async_client.get(f"/api/v1/agent/runtimes/{runtime_id}/health")
    stop_response = await async_client.post(f"/api/v1/agent/runtimes/{runtime_id}/stop")
    cleanup_response = await async_client.post("/api/v1/agent/runtimes/cleanup")

    assert health_response.status_code == 200
    assert health_response.json()["data"]["status"] == "running"
    assert stop_response.status_code == 200
    assert stop_response.json()["data"]["status"] == "stopped"
    assert cleanup_response.status_code == 200
    assert cleanup_response.json()["data"] == {"stopped_count": 0}


@pytest.mark.asyncio
async def test_create_agent_run_streams_events(async_client):
    session_response = await async_client.post("/api/v1/agent/u001/sessions", json={"title": "白屏排查"})
    session_id = session_response.json()["data"]["session_id"]

    response = await async_client.post(
        f"/api/v1/agent/u001/sessions/{session_id}/runs",
        json={"input": "小程序上线后白屏", "stream": True, "tools": ["optimize_query"]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: run.created" in response.text
    assert "event: answer.completed" in response.text


@pytest.mark.asyncio
async def test_list_agent_events(async_client):
    session_response = await async_client.post("/api/v1/agent/u001/sessions", json={"title": "白屏排查"})
    session_id = session_response.json()["data"]["session_id"]
    run_response = await async_client.post(
        f"/api/v1/agent/u001/sessions/{session_id}/runs",
        json={"input": "小程序上线后白屏", "stream": False, "tools": ["optimize_query"]},
    )
    run_id = run_response.json()["data"]["run_id"]

    events_response = await async_client.get(f"/api/v1/agent/u001/sessions/{session_id}/events?run_id={run_id}")

    assert events_response.status_code == 200
    assert isinstance(events_response.json()["data"], list)
