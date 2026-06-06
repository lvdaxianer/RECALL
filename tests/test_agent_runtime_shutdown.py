import pytest

from app.main import _close_agent_runtime_client


class CloseAwareRuntimeClient:
    """测试用 Runtime Client。"""

    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_close_agent_runtime_client_calls_runtime_close(monkeypatch):
    runtime_client = CloseAwareRuntimeClient()
    monkeypatch.setattr("app.main.get_agent_runtime_client", lambda: runtime_client)

    await _close_agent_runtime_client()

    assert runtime_client.closed is True
