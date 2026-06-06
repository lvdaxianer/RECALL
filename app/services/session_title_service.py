"""
Session title generation service.

Generates short chat session titles after the first completed answer.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.llm_service import get_llm_service
from app.services.session_service import SessionNotFoundError, SessionService


DEFAULT_SESSION_TITLE = "新的检索会话"
TITLE_PROMPT = """
请为下面的知识库问答会话生成一个简洁中文标题。

要求：
1. 8 到 18 个中文字符为主。
2. 不要标点符号。
3. 不要使用“新的检索会话”。
4. 只输出标题本身。

用户问题：{question}
助手回答：{answer}
"""


class SessionTitleService:
    """Generate and update session titles."""

    def __init__(self, llm_service: Any | None = None):
        self._llm_service = llm_service

    async def auto_title_if_needed(
        self,
        session_service: SessionService,
        user_id: str,
        session_id: str,
        question: str,
        answer: str,
    ) -> None:
        """Generate a title only for unnamed/default sessions."""
        try:
            session = session_service.get_session(user_id, session_id)
        except SessionNotFoundError:
            return
        if session.metadata.get("title_source") == "manual":
            return
        if session.title and session.title != DEFAULT_SESSION_TITLE:
            return
        title = await self.generate_title(question, answer)
        if title:
            session_service.update_session_title(user_id, session_id, title, source="auto")

    async def generate_title(self, question: str, answer: str) -> str:
        """Generate a short title with LLM and fallback to question summary."""
        try:
            raw = await self._get_llm_service().chat_simple(
                TITLE_PROMPT.format(question=question[:500], answer=answer[:800]),
                system="你是会话标题生成器，只输出短中文标题。",
                temperature=0.2,
            )
            title = _sanitize_title(raw)
            if title:
                return title
        except Exception:
            pass
        return _fallback_title(question)

    def _get_llm_service(self):
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service


def _sanitize_title(value: str) -> str:
    """Clean generated title."""
    title = re.sub(r"[\"'“”‘’《》<>#`*_。，、：:；;！？!?()\[\]{}]", "", value).strip()
    title = re.sub(r"\s+", "", title)
    if not title or title == DEFAULT_SESSION_TITLE:
        return ""
    return title[:18]


def _fallback_title(question: str) -> str:
    """Fallback title from user question."""
    title = _sanitize_title(question)
    if not title:
        return "知识库问题排查"
    return title[:18]


_session_title_service: SessionTitleService | None = None


def get_session_title_service() -> SessionTitleService:
    """Return global title service."""
    global _session_title_service
    if _session_title_service is None:
        _session_title_service = SessionTitleService()
    return _session_title_service
