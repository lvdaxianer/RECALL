"""
实体关系抽取服务测试

@author lvdaxianerplus
@date 2026-05-31
"""

import pytest
from unittest.mock import AsyncMock

from app.services.entity_relation_service import EntityRelationService


@pytest.mark.asyncio
async def test_extract_entities_relations_success_json():
    """LLM 返回结构化 JSON 时解析实体和关系"""
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '{"entities":[{"name":"JWT","type":"技术组件"}],'
        '"relations":[{"source":"JWT","target":"登录认证","relation":"用于"}]}'
    )
    service = EntityRelationService(llm_service=llm)

    result = await service.extract("JWT 用于登录认证")

    assert result["entities"] == [{"name": "JWT", "type": "技术组件"}]
    assert result["relations"] == [{"source": "JWT", "target": "登录认证", "relation": "用于"}]


@pytest.mark.asyncio
async def test_extract_entities_relations_invalid_json_fallback():
    """LLM 返回非 JSON 时降级为空实体关系"""
    llm = AsyncMock()
    llm.chat_simple.return_value = "not-json"
    service = EntityRelationService(llm_service=llm)

    result = await service.extract("JWT 用于登录认证")

    assert result == {"entities": [], "relations": []}


@pytest.mark.asyncio
async def test_extract_entities_relations_limits_items():
    """实体和关系数量会被限制，避免写入过大特征"""
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '{"entities":['
        + ",".join([f'{{"name":"E{i}","type":"类型"}}' for i in range(20)])
        + '],"relations":['
        + ",".join([f'{{"source":"E{i}","target":"T{i}","relation":"关联"}}' for i in range(20)])
        + "]} "
    )
    service = EntityRelationService(llm_service=llm)

    result = await service.extract("很多实体关系")

    assert len(result["entities"]) == 10
    assert len(result["relations"]) == 10
