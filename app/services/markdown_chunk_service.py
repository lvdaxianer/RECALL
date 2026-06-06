"""
Markdown 与纯文本 chunk 切分服务

保留 Markdown 标题层级和 chunk 顺序，不承担 PDF/OCR/Office 解析职责。

Author: lvdaxianerplus
Date: 2026-06-03
"""

import re
from typing import Any


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class MarkdownChunkService:
    """Markdown 与纯文本切分服务。"""

    def __init__(self, max_chars: int = 1200, overlap: int = 120, max_heading_depth: int = 3):
        """初始化切分参数。"""
        self.max_chars = max_chars
        self.overlap = overlap
        self.max_heading_depth = max_heading_depth

    def split(self, content: str, semantic_plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """将纯文本或 Markdown 切分为有序 chunk。"""
        text = content.strip()
        if not text:
            return []
        else:
            sections = self._split_sections(text)
            if semantic_plan:
                planned_chunks = self._build_semantic_chunks(sections, semantic_plan)
                if planned_chunks:
                    return planned_chunks
                else:
                    return self._build_chunks(sections)
            return self._build_chunks(sections)

    def _split_sections(self, text: str) -> list[dict[str, str]]:
        """按 Markdown 标题切分段落。"""
        sections: list[dict[str, str]] = []
        current_title = ""
        current_lines: list[str] = []
        for line in text.splitlines():
            match = HEADING_PATTERN.match(line)
            if match is not None and len(match.group(1)) <= self.max_heading_depth:
                self._append_section(sections, current_title, current_lines)
                current_title = match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)
        self._append_section(sections, current_title, current_lines)
        return sections

    def _append_section(
        self,
        sections: list[dict[str, str]],
        title: str,
        lines: list[str],
    ) -> None:
        """追加非空章节。"""
        body = "\n".join(lines).strip()
        if title or body:
            sections.append({"section_id": f"s{len(sections) + 1}", "title": title, "content": body})
        else:
            return

    def _build_chunks(self, sections: list[dict[str, str]]) -> list[dict[str, Any]]:
        """将章节转换为 chunk 列表。"""
        chunks: list[dict[str, Any]] = []
        for section in sections:
            body_chunks = self._split_long_text(section["content"])
            for body in body_chunks:
                chunks.append({
                    "chunk_index": len(chunks),
                    "title": section["title"],
                    "content": body,
                })
        return self._with_index_overlap(chunks)

    def _build_semantic_chunks(
        self,
        sections: list[dict[str, str]],
        semantic_plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """按语义计划合并 section 并构建 chunk。"""
        section_map = {section["section_id"]: section for section in sections}
        chunks: list[dict[str, Any]] = []
        for group in semantic_plan.get("groups", []):
            group_sections = [section_map.get(section_id) for section_id in group]
            if any(section is None for section in group_sections):
                return []
            titles = [section["title"] for section in group_sections if section and section["title"]]
            content = "\n\n".join(section["content"].strip() for section in group_sections if section)
            if len(content) > self.max_chars:
                body_chunks = [
                    body
                    for section in group_sections
                    if section
                    for body in self._split_long_text(section["content"])
                ]
            else:
                body_chunks = self._split_long_text(content)
            for body in body_chunks:
                chunks.append({
                    "chunk_index": len(chunks),
                    "title": " / ".join(titles),
                    "content": body,
                })
        return self._with_index_overlap([chunk for chunk in chunks if chunk["content"].strip()])

    def _with_index_overlap(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """为最终 chunk 列表补齐检索专用 overlap。"""
        if self.overlap <= 0:
            return [{**chunk, "indexed_content": chunk["content"]} for chunk in chunks]
        indexed_chunks = []
        for index, chunk in enumerate(chunks):
            content = chunk["content"].strip()
            previous_content = chunks[index - 1]["content"].strip() if index > 0 else ""
            next_content = chunks[index + 1]["content"].strip() if index + 1 < len(chunks) else ""
            prefix = previous_content[-self.overlap:].strip()
            suffix = next_content[:self.overlap].strip()
            parts = [part for part in [prefix, content, suffix] if part]
            indexed_content = "\n".join(parts).strip()
            indexed_chunks.append({**chunk, "indexed_content": indexed_content})
        return indexed_chunks

    def _split_long_text(self, text: str) -> list[str]:
        """按最大字符数切分长文本。"""
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.max_chars:
            return [text]
        else:
            return self._window_chunks(text)

    def _window_chunks(self, text: str) -> list[str]:
        """使用滑动窗口切分长文本。"""
        chunks: list[str] = []
        start = 0
        step = max(1, self.max_chars - self.overlap)
        while start < len(text):
            chunks.append(text[start:start + self.max_chars].strip())
            start += step
        return [chunk for chunk in chunks if chunk]
