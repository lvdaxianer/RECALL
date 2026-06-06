import pytest

from app.services.session_service import SessionService
from app.services.session_title_service import SessionTitleService


class FakeLLM:
    async def chat_simple(self, prompt, **kwargs):
        return "小程序白屏排查"


@pytest.mark.asyncio
async def test_auto_title_updates_default_session_only():
    """自动标题只更新默认标题会话，不覆盖手动命名。"""
    service = SessionService()
    default_session = service.create_session("u001", title="新的检索会话")
    manual_session = service.create_session("u001", title="手动标题")
    service.update_session_title("u001", manual_session.session_id, "手动标题", source="manual")
    title_service = SessionTitleService(llm_service=FakeLLM())

    await title_service.auto_title_if_needed(service, "u001", default_session.session_id, "小程序上线后白屏", "检查发布配置")
    await title_service.auto_title_if_needed(service, "u001", manual_session.session_id, "登录失败", "检查认证")

    assert service.get_session("u001", default_session.session_id).title == "小程序白屏排查"
    assert service.get_session("u001", default_session.session_id).metadata["title_source"] == "auto"
    assert service.get_session("u001", manual_session.session_id).title == "手动标题"
