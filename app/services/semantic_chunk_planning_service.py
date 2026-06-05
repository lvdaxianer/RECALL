"""
Markdown 语义分块规划服务

Author: lvdaxianerplus
Date: 2026-06-05
"""

import json
import re
from typing import Any

from app.services.llm_service import get_llm_service


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class SemanticChunkPlanningService:
    """调用 LLM 为 Markdown section 生成语义分组计划。"""

    def __init__(
        self,
        llm_service: Any | None = None,
        max_heading_depth: int = 3,
        timeout_ms: int = 8000,
    ):
        """初始化语义分块规划服务。"""
        self.llm_service = llm_service or get_llm_service()
        self.max_heading_depth = max_heading_depth
        self.timeout_ms = timeout_ms

    async def plan(self, markdown: str) -> dict[str, Any]:
        """为 Markdown 内容生成 section 分组计划，异常时返回 fallback。"""
        sections, has_deep_heading = self.parse_sections(markdown)
        fallback = self._fallback_plan(sections)
        if has_deep_heading or not sections:
            return fallback
        try:
            response = await self.llm_service.chat_simple(self._build_prompt(sections))
            groups = self._parse_response(response, sections)
            return {"used_fallback": False, "sections": sections, "groups": groups, "fallback_reason": None}
        except Exception as exc:
            fallback["fallback_reason"] = str(exc)
            return fallback

    def parse_sections(self, markdown: str) -> tuple[list[dict[str, Any]], bool]:
        """解析 Markdown 为非空 section 列表。"""
        sections: list[dict[str, Any]] = []
        title_path: list[str] = []
        current_title = ""
        current_level = 0
        current_lines: list[str] = []
        has_deep_heading = False
        for line in markdown.splitlines():
            match = HEADING_PATTERN.match(line)
            if match is not None:
                self._append_section(sections, title_path, current_title, current_lines)
                current_level = len(match.group(1))
                current_title = match.group(2).strip()
                has_deep_heading = has_deep_heading or current_level > self.max_heading_depth
                title_path = self._next_title_path(title_path, current_level, current_title)
                current_lines = []
            else:
                current_lines.append(line)
        self._append_section(sections, title_path, current_title, current_lines)
        return sections, has_deep_heading

    def _append_section(
        self,
        sections: list[dict[str, Any]],
        title_path: list[str],
        title: str,
        lines: list[str],
    ) -> None:
        """追加非空正文 section。"""
        content = "\n".join(lines).strip()
        if not content:
            return
        section_id = f"s{len(sections) + 1}"
        sections.append({
            "section_id": section_id,
            "title": title,
            "title_path": list(title_path),
            "content": content,
            "order": len(sections),
        })

    def _next_title_path(self, current_path: list[str], level: int, title: str) -> list[str]:
        """按 heading level 更新标题路径。"""
        next_path = current_path[: max(0, level - 1)]
        next_path.append(title)
        return next_path

    def _build_prompt(self, sections: list[dict[str, Any]]) -> str:
        """构造 LLM 语义分块规划 prompt。"""
        payload = [
            {
                "section_id": section["section_id"],
                "title_path": section["title_path"],
                "order": section["order"],
                "preview": section["content"][:400],
            }
            for section in sections
        ]
        return (
            "Plan semantic Markdown chunk groups. JSON only. "
            "do not rewrite content. max heading depth 3. assign every section once. "
            "Return {\"groups\":[{\"section_ids\":[\"s1\"]}]}.\n"
            f"Sections:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def _parse_response(self, response: str, sections: list[dict[str, Any]]) -> list[list[str]]:
        """解析并校验 LLM 返回的分组 JSON。"""
        payload = json.loads(response)
        groups = [[str(section_id) for section_id in group["section_ids"]] for group in payload["groups"]]
        expected_ids = [section["section_id"] for section in sections]
        flattened = [section_id for group in groups for section_id in group]
        if sorted(flattened) != sorted(expected_ids) or len(flattened) != len(set(flattened)):
            raise ValueError("semantic plan must assign every section once")
        id_to_order = {section["section_id"]: section["order"] for section in sections}
        orders = [id_to_order[section_id] for section_id in flattened]
        if orders != sorted(orders):
            raise ValueError("semantic plan must keep section order")
        return groups

    def _fallback_plan(self, sections: list[dict[str, Any]]) -> dict[str, Any]:
        """构造逐 section fallback plan。"""
        return {
            "used_fallback": True,
            "sections": sections,
            "groups": [[section["section_id"]] for section in sections],
            "fallback_reason": "fallback",
        }
