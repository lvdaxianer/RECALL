"""
实体关系抽取服务

使用 LLM 从描述文本中抽取轻量实体和关系，作为 LightRAG-lite 的结构化基础。

@author lvdaxianerplus
@date 2026-05-31
"""

import asyncio
import json
import re
from typing import Dict, List, Optional

from app.services.llm_service import LLMService, get_llm_service
from app.utils.logger import get_logger

entity_relation_logger = get_logger("EntityRelation")

ENTITY_RELATION_PROMPT = """你是一个实体关系抽取助手。请从给定描述中抽取关键实体和实体关系。

要求：
1. 只抽取文本明确提到或强相关的实体，不要编造。
2. 实体数量 0-10 个，关系数量 0-10 个。
3. 关系必须连接已抽取或文本明确出现的实体。
4. 只输出 JSON，不要输出解释。

输出格式：
{{
  "entities": [{{"name": "实体名称", "type": "实体类型"}}],
  "relations": [{{"source": "源实体", "target": "目标实体", "relation": "关系"}}]
}}

描述：
{description}
"""


class EntityRelationService:
    """实体关系抽取服务"""

    def __init__(self, llm_service: Optional[LLMService] = None):
        """初始化实体关系抽取服务"""
        self._llm_service = llm_service

    @property
    def llm_service(self) -> LLMService:
        """获取 LLM 服务"""
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    async def extract(self, description: str) -> Dict[str, List[dict]]:
        """
        从描述中抽取实体和关系

        @param description - 描述文本
        @returns 实体和关系列表
        """
        if not description or not description.strip():
            return self._empty_result()

        try:
            prompt = ENTITY_RELATION_PROMPT.format(description=description)
            entity_relation_logger.info("[实体关系] 开始抽取, 描述长度={}", len(description))
            response = await self.llm_service.chat_simple(prompt)
            result = self._parse_response(response)
            if result is None:
                entity_relation_logger.warning("[实体关系] 解析失败，使用空实体关系")
                return self._empty_result()
            entity_relation_logger.info(
                "[实体关系] 抽取成功, entities={}, relations={}",
                len(result["entities"]),
                len(result["relations"])
            )
            return result
        except Exception as e:
            entity_relation_logger.error("[实体关系] 抽取失败: {}", str(e))
            return self._empty_result()

    async def extract_batch(self, descriptions: List[str], concurrency: int = 10) -> List[Dict[str, List[dict]]]:
        """
        批量抽取实体关系

        @param descriptions - 描述文本列表
        @param concurrency - 最大并发数
        @returns 实体关系列表，顺序与输入一致
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(description: str) -> Dict[str, List[dict]]:
            async with semaphore:
                return await self.extract(description)

        return await asyncio.gather(*(run_one(description) for description in descriptions))

    def _parse_response(self, response: str) -> Optional[Dict[str, List[dict]]]:
        """解析 LLM 响应"""
        try:
            json_str = self._extract_json(response)
            if not json_str:
                return None
            data = json.loads(json_str)
            entities = data.get("entities", [])
            relations = data.get("relations", [])
            if not isinstance(entities, list) or not isinstance(relations, list):
                return None
            return {
                "entities": [item for item in entities if isinstance(item, dict)][:10],
                "relations": [item for item in relations if isinstance(item, dict)][:10]
            }
        except Exception as e:
            entity_relation_logger.error("[实体关系] JSON 解析失败: {}", str(e))
            return None

    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 字符串"""
        try:
            json.loads(text)
            return text
        except Exception:
            pass

        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{.*\})'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                potential_json = match.group(1)
                try:
                    json.loads(potential_json)
                    return potential_json
                except Exception:
                    continue
        return None

    def _empty_result(self) -> Dict[str, List[dict]]:
        """返回空实体关系"""
        return {"entities": [], "relations": []}


_entity_relation_service: Optional[EntityRelationService] = None


def get_entity_relation_service() -> EntityRelationService:
    """获取实体关系抽取服务单例"""
    global _entity_relation_service
    if _entity_relation_service is None:
        _entity_relation_service = EntityRelationService()
    return _entity_relation_service
