"""
快速同义词索引。

Author: lvdaxianerplus
Date: 2026-06-05
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.services.query_normalization import QUERY_CACHE_SYNONYMS


@dataclass
class TrieNode:
    """同义词 Trie 节点。"""

    children: dict[str, "TrieNode"] = field(default_factory=dict)
    canonical: str | None = None


class CompiledSynonymIndex:
    """使用 Trie 进行最长匹配同义词替换。"""

    def __init__(self, root: TrieNode):
        """初始化编译后的同义词索引。"""
        self.root = root

    @classmethod
    def from_groups(cls, groups: list[dict[str, Any]], include_builtin: bool = False) -> "CompiledSynonymIndex":
        """从同义词组构建 Trie 索引。"""
        root = TrieNode()
        for group in groups:
            canonical = str(group.get("canonical", "")).strip()
            terms = [*group.get("terms", []), canonical]
            for term in terms:
                _insert(root, _normalize_text(str(term)), canonical)
        if include_builtin:
            for source, target in QUERY_CACHE_SYNONYMS.items():
                _insert(root, _normalize_text(source), target)
        return cls(root)

    def normalize(self, query: str) -> str:
        """将 query 中命中的同义词替换为 canonical。"""
        text = _normalize_text(query)
        output: list[str] = []
        cursor = 0
        while cursor < len(text):
            canonical, end = self._longest_match(text, cursor)
            if canonical is not None:
                output.append(canonical)
                cursor = end
            else:
                output.append(text[cursor])
                cursor += 1
        return "".join(output).strip()

    def _longest_match(self, text: str, start: int) -> tuple[str | None, int]:
        """返回 start 位置开始的最长匹配。"""
        node = self.root
        best: tuple[str | None, int] = (None, start)
        cursor = start
        while cursor < len(text) and text[cursor] in node.children:
            node = node.children[text[cursor]]
            cursor += 1
            if node.canonical is not None:
                best = (node.canonical, cursor)
        return best


def _insert(root: TrieNode, term: str, canonical: str) -> None:
    """插入一个同义词 term。"""
    if not term:
        return
    node = root
    for char in term:
        node = node.children.setdefault(char, TrieNode())
    if node.canonical is None:
        node.canonical = canonical


def _normalize_text(text: str) -> str:
    """统一大小写和全半角。"""
    return unicodedata.normalize("NFKC", text or "").lower().strip()
