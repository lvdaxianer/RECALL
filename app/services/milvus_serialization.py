"""
Milvus 字段序列化工具

负责结构化字段的 JSON 序列化和历史字符串格式兼容解析。
"""

import ast
import json
from typing import Any, Dict


def dump_stored_dict(value: Dict[str, Any] | None) -> str:
    """将字典序列化为 Milvus VARCHAR 可存储的 JSON 字符串"""
    return json.dumps(value or {}, ensure_ascii=False)


def parse_stored_dict(value: Any) -> Dict[str, Any]:
    """
    安全解析 Milvus 中存储的字典字符串

    兼容新 JSON 格式和历史 str(dict) 格式，不执行任意表达式。
    """
    if isinstance(value, dict):
        return value
    if not value:
        return {}

    text = str(value)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return {}

    return parsed if isinstance(parsed, dict) else {}
