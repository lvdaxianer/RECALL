"""
语义分块规划服务测试

Author: lvdaxianerplus
Date: 2026-06-05
"""

import pytest

from app.services.semantic_chunk_planning_service import SemanticChunkPlanningService


class FakeLLMService:
    """测试用 LLM 服务。"""

    def __init__(self, response: str):
        """保存响应文本和 prompt。"""
        self.response = response
        self.prompts = []

    async def chat_simple(self, prompt: str, **kwargs):
        """记录 prompt 并返回预设响应。"""
        self.prompts.append(prompt)
        return self.response


@pytest.mark.asyncio
async def test_semantic_planner_groups_adjacent_markdown_sections():
    """有效 LLM JSON 可以把相邻 Markdown section 合为一组。"""
    llm = FakeLLMService('{"groups":[{"section_ids":["s1","s2"]},{"section_ids":["s3"]}]}')
    service = SemanticChunkPlanningService(llm_service=llm)

    result = await service.plan("# A\n正文 A\n## B\n正文 B\n# C\n正文 C")

    assert result["used_fallback"] is False
    assert result["groups"] == [["s1", "s2"], ["s3"]]


@pytest.mark.asyncio
async def test_semantic_planner_invalid_json_returns_fallback():
    """LLM 返回非 JSON 时使用 fallback plan。"""
    service = SemanticChunkPlanningService(llm_service=FakeLLMService("not json"))

    result = await service.plan("# A\n正文 A\n# B\n正文 B")

    assert result["used_fallback"] is True
    assert result["groups"] == [["s1"], ["s2"]]


@pytest.mark.asyncio
async def test_semantic_planner_duplicate_section_returns_fallback():
    """LLM 重复分配 section 时使用 fallback plan。"""
    service = SemanticChunkPlanningService(
        llm_service=FakeLLMService('{"groups":[{"section_ids":["s1","s1"]},{"section_ids":["s2"]}]}'),
    )

    result = await service.plan("# A\n正文 A\n# B\n正文 B")

    assert result["used_fallback"] is True


@pytest.mark.asyncio
async def test_semantic_planner_missing_section_returns_fallback():
    """LLM 漏掉非空 section 时使用 fallback plan。"""
    service = SemanticChunkPlanningService(
        llm_service=FakeLLMService('{"groups":[{"section_ids":["s1"]}]}'),
    )

    result = await service.plan("# A\n正文 A\n# B\n正文 B")

    assert result["used_fallback"] is True


@pytest.mark.asyncio
async def test_semantic_planner_deep_heading_returns_fallback():
    """超过三级标题的 Markdown 不进入语义规划结果。"""
    service = SemanticChunkPlanningService(
        llm_service=FakeLLMService('{"groups":[{"section_ids":["s1"]}]}'),
        max_heading_depth=3,
    )

    result = await service.plan("#### A\n正文 A")

    assert result["used_fallback"] is True


@pytest.mark.asyncio
async def test_semantic_planner_prompt_contains_constraints():
    """语义规划 prompt 必须包含关键安全约束。"""
    llm = FakeLLMService('{"groups":[{"section_ids":["s1"]}]}')
    service = SemanticChunkPlanningService(llm_service=llm)

    await service.plan("# A\n正文 A")

    prompt = llm.prompts[0]
    assert "JSON only" in prompt
    assert "do not rewrite content" in prompt
    assert "max heading depth 3" in prompt
    assert "assign every section once" in prompt
