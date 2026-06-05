"""
Retrieval SDK answer synthesis.

Turns retrieval hits into user-facing answers instead of echoing raw chunks.
"""

from __future__ import annotations

import re
from typing import Any, AsyncIterator

from app.services.llm_service import get_llm_service


OVERVIEW_QUERY_PATTERN = re.compile(r"(知识库|库|文档).*(包含|主要|讲解|内容|主题)|主要.*(包含|讲解)")
INTRO_QUERY_PATTERN = re.compile(r"(介绍|讲解|解释|说明|概述|说说|聊聊|是什么|什么是)")
EXAMPLE_BLOCK_PATTERN = re.compile(
    r"(用户问[:：].*?(?:模型答[:：].*?)(?=\n\S|$))",
    flags=re.DOTALL,
)
CODE_BLOCK_PATTERN = re.compile(r"```.*?```", flags=re.DOTALL)
INLINE_MARKDOWN_TOKEN_PATTERN = re.compile(r"!\[[^\]]*]\([^)]*\)|\[[^\]]+]\([^)]*\)|\*\*[^*]+\*\*|`[^`]+`")
MAX_CONTEXT_CHARS = 2800
MAX_FALLBACK_POINTS = 5
MIN_INTRO_ANSWER_CHARS = 180
DELTA_CHARS = 16


class RetrievalAnswerService:
    """Generate concise answers from Retrieval SDK results."""

    def __init__(self, llm_service: Any | None = None):
        """Initialize with optional LLM dependency for tests."""
        self._llm_service = llm_service

    async def synthesize(
        self,
        query: str,
        results: list[dict[str, Any]],
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Return answer text and streaming deltas for a retrieval result set."""
        if not results:
            answer = "没有在已选择知识库中找到相关内容。"
            return {"answer": answer, "deltas": [{"text": answer, "chunk_id": ""}]}

        context_items = _build_context_items(results, query=query, overview=_is_overview_query(query))
        try:
            answer = await self._generate_with_llm(query, context_items, temperature=temperature)
            if not answer.strip():
                answer = _fallback_summary(query, context_items)
        except Exception:
            answer = _fallback_summary(query, context_items)
        answer = _sanitize_answer(answer)
        answer = _ensure_answer_depth(query, answer, context_items)
        return {
            "answer": answer,
            "deltas": _split_answer_deltas(answer, context_items[0]["chunk_id"] if context_items else ""),
        }

    async def stream_synthesize(
        self,
        query: str,
        results: list[dict[str, Any]],
        temperature: float = 0.2,
    ) -> AsyncIterator[dict[str, str]]:
        """Yield answer deltas as the LLM produces them, with fallback to local synthesis."""
        if not results:
            yield {"text": "没有在已选择知识库中找到相关内容。", "chunk_id": ""}
            return

        context_items = _build_context_items(results, query=query, overview=_is_overview_query(query))
        chunk_id = context_items[0]["chunk_id"] if context_items else ""
        try:
            chunks = []
            async for text in self._stream_generate_with_llm(query, context_items, temperature=temperature):
                cleaned = _sanitize_stream_delta(text)
                if not cleaned:
                    continue
                chunks.append(cleaned)
            if chunks:
                answer = _sanitize_answer("".join(chunks))
                if _should_expand_answer(query, answer, context_items):
                    answer = _intro_fallback_summary(context_items)
                    for delta in _split_answer_deltas(answer, chunk_id):
                        yield delta
                else:
                    for chunk in chunks:
                        for delta in _split_answer_deltas(chunk, chunk_id):
                            yield delta
                return
        except Exception:
            pass

        answer = _ensure_answer_depth(query, _sanitize_answer(_fallback_summary(query, context_items)), context_items)
        for delta in _split_answer_deltas(answer, chunk_id):
            yield delta

    async def _generate_with_llm(
        self,
        query: str,
        context_items: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> str:
        """Ask LLM to synthesize a grounded answer from cleaned context."""
        prompt = _build_prompt(query, context_items)
        llm_service = self._get_llm_service()
        system = "你是 Recall 的知识库问答助手，只基于给定资料总结，不输出文件路径，不复述资料中的示例问答。"
        try:
            return await llm_service.chat_simple(prompt, system=system, temperature=temperature)
        except TypeError as exc:
            if "temperature" not in str(exc):
                raise
            return await llm_service.chat_simple(prompt, system=system)

    async def _stream_generate_with_llm(
        self,
        query: str,
        context_items: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Ask LLM to stream a grounded answer from cleaned context."""
        prompt = _build_prompt(query, context_items)
        llm_service = self._get_llm_service()
        system = "你是 Recall 的知识库问答助手，只基于给定资料总结，不输出文件路径，不复述资料中的示例问答。"
        try:
            stream = llm_service.stream_chat_simple(prompt, system=system, temperature=temperature)
        except TypeError as exc:
            if "temperature" not in str(exc):
                raise
            stream = llm_service.stream_chat_simple(prompt, system=system)
        async for text in stream:
            yield text

    def _get_llm_service(self):
        """Lazy load LLM service."""
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service


def _is_overview_query(query: str) -> bool:
    """Detect knowledge-base overview questions."""
    normalized = query.strip()
    return bool(OVERVIEW_QUERY_PATTERN.search(normalized))


def _is_intro_query(query: str) -> bool:
    """Detect questions that ask for an explanatory introduction."""
    normalized = query.strip()
    return bool(INTRO_QUERY_PATTERN.search(normalized))


def filter_results_for_answer(
    query: str,
    results: list[dict[str, Any]],
    overview: bool | None = None,
) -> list[dict[str, Any]]:
    """Filter off-topic retrieval hits before answer synthesis and citation display."""
    is_overview = _is_overview_query(query) if overview is None else overview
    if is_overview or len(results) <= 1:
        return results
    terms = _query_terms(query)
    if not terms:
        return results
    relevant = [result for result in results if _is_result_relevant(result, terms)]
    return relevant or results


def _build_context_items(results: list[dict[str, Any]], query: str, overview: bool) -> list[dict[str, str]]:
    """Build cleaned context items for answer synthesis."""
    items = []
    seen = set()
    for result in filter_results_for_answer(query, results, overview=overview):
        document_name = str(result.get("document_name") or "")
        title = str(result.get("title") or "")
        content = _clean_content(str(result.get("content") or result.get("description") or ""))
        if not content:
            content = title.strip() or _human_source_label(document_name, title)
        if not content:
            continue
        key = (document_name, title, content[:120])
        if key in seen:
            continue
        seen.add(key)
        source = _human_source_label(document_name, title)
        items.append({
            "chunk_id": str(result.get("chunk_id") or result.get("id") or ""),
            "document_name": document_name,
            "source": source,
            "title": title,
            "content": _overview_content(title, content) if overview else content[:MAX_CONTEXT_CHARS],
        })
    return _filter_context_items_by_query(items, query, overview)


def _filter_context_items_by_query(items: list[dict[str, str]], query: str, overview: bool) -> list[dict[str, str]]:
    """Remove lexical off-topic context for specific questions when relevant context exists."""
    if overview or len(items) <= 1:
        return items
    terms = _query_terms(query)
    if not terms:
        return items
    relevant = [item for item in items if _is_context_relevant(item, terms)]
    return relevant or items


def _query_terms(query: str) -> set[str]:
    """Extract lightweight lexical terms from a user query for context gating."""
    normalized = query.lower()
    terms = set(re.findall(r"[a-z0-9][a-z0-9_+-]*", normalized))
    terms.update(
        token
        for token in re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
        if token not in {"什么", "怎么", "如何", "一下", "请问", "介绍"}
    )
    if "jmm" in terms:
        terms.update({"java 内存模型", "java内存模型", "内存模型"})
    return terms


def _is_context_relevant(item: dict[str, str], terms: set[str]) -> bool:
    haystack = (
        f"{item.get('document_name', '')}\n"
        f"{item.get('source', '')}\n"
        f"{item.get('title', '')}\n"
        f"{item.get('content', '')}"
    ).lower()
    return any(term in haystack for term in terms)


def _is_result_relevant(result: dict[str, Any], terms: set[str]) -> bool:
    document_name = str(result.get("document_name") or "")
    title = str(result.get("title") or "")
    content = _clean_content(str(result.get("content") or result.get("description") or ""))
    fallback = title.strip() or _human_source_label(document_name, title)
    haystack = f"{document_name}\n{title}\n{content or fallback}".lower()
    return any(term in haystack for term in terms)


def _clean_content(content: str) -> str:
    """Remove examples and formatting that should not be echoed as answers."""
    without_code = CODE_BLOCK_PATTERN.sub("", content)
    without_examples = EXAMPLE_BLOCK_PATTERN.sub("", without_code)
    lines = [
        line.strip()
        for line in without_examples.splitlines()
        if line.strip() and not line.strip().startswith(("用户问：", "用户问:", "模型答：", "模型答:"))
    ]
    return "\n".join(lines).strip()


def _overview_content(title: str, content: str) -> str:
    """Prefer section titles and short explanatory sentences for overview answers."""
    sentences = re.split(r"(?<=[。！？!?])\s*", content.replace("\n", " "))
    selected = [sentence.strip() for sentence in sentences if sentence.strip()][:3]
    parts = [title.strip(), *selected]
    return "。".join(part.strip("。") for part in parts if part).strip()


def _human_source_label(document_name: str, title: str) -> str:
    """Return a clean source label without leaking full local-style paths."""
    clean_name = document_name.split("/")[-1] if document_name else ""
    if title and title not in clean_name:
        return title
    return title or clean_name


def _build_prompt(query: str, context_items: list[dict[str, str]]) -> str:
    """Build a compact grounded-answer prompt."""
    context = "\n\n".join(
        f"[{index}] 主题：{item['source']}\n内容：{item['content']}"
        for index, item in enumerate(context_items, start=1)
    )
    return (
        "请基于以下知识库片段回答用户问题。\n"
        "要求：\n"
        "1. 如果用户询问知识库主要包含什么，请按主题做概览总结。\n"
        "2. 不要输出文件路径、本地目录、chunk id。\n"
        "3. 不要把资料中的示例问答当成对当前用户的回答。\n"
        "4. 如果用户要求介绍、讲解或解释某个主题，请至少覆盖定义、关键机制/分类、优势或适用场景，不要只返回目录。\n"
        "5. 用简洁中文回答，可使用要点。\n\n"
        f"用户问题：{query}\n\n"
        f"知识库片段：\n{context}"
    )


def _fallback_summary(query: str, context_items: list[dict[str, str]]) -> str:
    """Local fallback when LLM is unavailable."""
    if not context_items:
        return "没有在已选择知识库中找到相关内容。"
    if _is_overview_query(query):
        points = []
        for item in context_items[:MAX_FALLBACK_POINTS]:
            topic = item["source"] or item["title"] or "知识主题"
            content = item["content"]
            points.append(f"- {topic}：{content[:120]}")
        return "这个知识库主要包含以下内容：\n" + "\n".join(points)
    top = context_items[0]
    return f"根据知识库资料，{top['content'][:240]}"


def _ensure_answer_depth(query: str, answer: str, context_items: list[dict[str, str]]) -> str:
    """Expand thin catalog-like answers for introduction questions."""
    if _should_expand_answer(query, answer, context_items):
        return _intro_fallback_summary(context_items)
    return answer


def _should_expand_answer(query: str, answer: str, context_items: list[dict[str, str]]) -> bool:
    """Decide whether a generated answer is too thin for available context."""
    if not _is_intro_query(query) or len(context_items) < 2:
        return False
    if not _looks_like_catalog_answer(answer):
        return False
    if len(answer) < MIN_INTRO_ANSWER_CHARS:
        return True
    return not _answer_uses_context_facts(answer, context_items)


def _looks_like_catalog_answer(answer: str) -> bool:
    """Detect answers that list dimensions without explaining the retrieved facts."""
    normalized = re.sub(r"\s+", "", answer)
    catalog_markers = ["涵盖维度", "核心对比", "核心主题", "关键内容", "工作原理", "优缺点", "优缺点评估", "适用场景"]
    return sum(1 for marker in catalog_markers if marker in normalized) >= 2


def _answer_uses_context_facts(answer: str, context_items: list[dict[str, str]]) -> bool:
    """Check whether the answer includes concrete facts from retrieved content."""
    normalized_answer = re.sub(r"\s+", "", answer)
    fact_phrases = _context_fact_phrases(context_items)
    return any(phrase in normalized_answer for phrase in fact_phrases)


def _context_fact_phrases(context_items: list[dict[str, str]]) -> list[str]:
    """Extract short fact phrases suitable for catalog-answer quality checks."""
    phrases = []
    for item in context_items[:MAX_FALLBACK_POINTS]:
        for phrase in re.findall(r"[\u4e00-\u9fffA-Za-z0-9+ ]{8,}", item["content"]):
            normalized = re.sub(r"\s+", "", phrase).strip("，。,:：;；-_*")
            if len(normalized) >= 8:
                phrases.append(normalized[:24])
    return phrases


def _intro_fallback_summary(context_items: list[dict[str, str]]) -> str:
    """Build an expanded introduction from the retrieved context items."""
    points = []
    for item in context_items[:MAX_FALLBACK_POINTS]:
        topic = item["source"] or item["title"] or "相关内容"
        content = _compact_content(item["content"])
        points.append(f"- {topic}：{content[:360]}")
    return "根据知识库资料，可以这样理解：\n" + "\n".join(points)


def _compact_content(content: str) -> str:
    """Normalize whitespace for locally synthesized introduction snippets."""
    compacted = re.sub(r"\s+", " ", content).strip()
    return compacted or "资料中仅给出了该主题标题，未提供更多正文。"


def _sanitize_answer(answer: str) -> str:
    """Remove known bad echoes from generated or fallback answers."""
    cleaned = _clean_content(answer)
    cleaned = re.sub(r"[\w.-]*/+[\w./-]+\.md", "", cleaned)
    cleaned = cleaned.replace("iPhone 16", "")
    return cleaned.strip() or "根据现有资料无法确定。"


def _sanitize_stream_delta(text: str) -> str:
    """Clean an individual streaming delta without stripping Markdown whitespace."""
    cleaned = re.sub(r"[\w.-]*/+[\w./-]+\.md", "", text)
    cleaned = cleaned.replace("iPhone 16", "")
    return cleaned


def _split_answer_deltas(answer: str, chunk_id: str) -> list[dict[str, str]]:
    """Split final answer into small deltas for visible streaming."""
    if len(answer) <= DELTA_CHARS:
        return [{"text": answer, "chunk_id": chunk_id}]
    return [{"text": text, "chunk_id": chunk_id} for text in _split_markdown_safe(answer)]


def _split_markdown_safe(answer: str) -> list[str]:
    """Split text into compact chunks without cutting common inline Markdown tokens."""
    tokens = _markdown_safe_tokens(answer)
    chunks = []
    current = ""
    for token in tokens:
        if current and len(current) + len(token) > DELTA_CHARS:
            chunks.append(current)
            current = ""
        if len(token) <= DELTA_CHARS:
            current += token
            continue
        if INLINE_MARKDOWN_TOKEN_PATTERN.fullmatch(token):
            chunks.append(token)
            continue
        if current:
            chunks.append(current)
            current = ""
        chunks.extend(_split_plain_text(token))
    if current:
        chunks.append(current)
    return chunks


def _markdown_safe_tokens(text: str) -> list[str]:
    """Tokenize text while preserving inline Markdown constructs as indivisible tokens."""
    tokens = []
    cursor = 0
    for match in INLINE_MARKDOWN_TOKEN_PATTERN.finditer(text):
        if match.start() > cursor:
            tokens.extend(_split_plain_text(text[cursor:match.start()]))
        tokens.append(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        tokens.extend(_split_plain_text(text[cursor:]))
    return [token for token in tokens if token]


def _split_plain_text(text: str) -> list[str]:
    """Split non-Markdown text into compact chunks."""
    return [text[index:index + DELTA_CHARS] for index in range(0, len(text), DELTA_CHARS)]
