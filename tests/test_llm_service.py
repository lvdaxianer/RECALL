"""
LLM service tests.
"""

from dataclasses import dataclass

import pytest

from app.services.llm_service import LLMService


@dataclass
class FakeChunk:
    """Minimal LangChain-like streaming chunk."""

    content: str


class FakeStreamingClient:
    """Fake ChatOpenAI client that records streaming messages."""

    def __init__(self):
        self.messages = []

    async def astream(self, messages, **kwargs):
        self.messages = messages
        yield FakeChunk("第一段")
        yield FakeChunk("")
        yield FakeChunk("第二段")


@pytest.mark.asyncio
async def test_llm_service_stream_chat_simple_yields_text_chunks():
    """stream_chat_simple 应透传非空文本增量并支持 system prompt。"""
    service = LLMService.__new__(LLMService)
    service._client = FakeStreamingClient()

    chunks = [chunk async for chunk in service.stream_chat_simple("用户问题", system="系统提示")]

    assert chunks == ["第一段", "第二段"]
    assert [message.content for message in service._client.messages] == ["系统提示", "用户问题"]
