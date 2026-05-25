"""
上下文压缩模块

去除冗余内容，保留关键信息，控制 Token 消耗

@author lvdaxianerplus
@date 2026-05-25
"""

from typing import List, Dict, Any, Optional
from app.utils.logger import get_logger

context_logger = get_logger("ContextCompressor")

# 单个 chunk 最大字符数（约 512 tokens）
MAX_CHUNK_CHARS = 2000
# 上下文总字符上限（约 4096 tokens）
MAX_TOTAL_CHARS = 8000


class ContextCompressor:
    """
    上下文压缩器

    对检索到的 chunks 进行去重、截断，控制送入 LLM 的 Token 总量
    """

    def compress(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        max_total_chars: int = MAX_TOTAL_CHARS
    ) -> List[Dict[str, Any]]:
        """
        压缩上下文

        @param chunks - 检索到的 chunk 列表，每项含 description、metadata、score
        @param query - 原始查询（保留用于未来语义压缩扩展）
        @param max_total_chars - 总字符上限
        @returns 压缩后的 chunk 列表
        @author lvdaxianerplus
        @date 2026-05-25
        """
        if not chunks:
            return []

        # 去重（按 description 内容去重）
        deduplicated = self._deduplicate(chunks)

        # 截断过长的单个 chunk
        truncated = self._truncate_chunks(deduplicated)

        # 按总字符数限制
        compressed = self._limit_total_chars(truncated, max_total_chars)

        context_logger.info(
            "[ContextCompressor] 压缩完成: {} -> {} chunks, 总字符数={}",
            len(chunks), len(compressed),
            sum(len(c.get("description", "")) for c in compressed)
        )
        return compressed

    def _deduplicate(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        按内容去重，保留分数最高的版本

        @param chunks - 原始 chunk 列表
        @returns 去重后的列表
        @author lvdaxianerplus
        @date 2026-05-25
        """
        seen_content = {}
        for chunk in chunks:
            content = chunk.get("description", "").strip()
            # 用前 100 字符作为去重 key（避免轻微差异导致漏判）
            key = content[:100]
            if key not in seen_content:
                seen_content[key] = chunk
            else:
                # 保留分数更高的
                existing_score = seen_content[key].get("score", 0)
                current_score = chunk.get("score", 0)
                if current_score > existing_score:
                    seen_content[key] = chunk

        return list(seen_content.values())

    def _truncate_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        截断过长的单个 chunk

        @param chunks - chunk 列表
        @returns 截断后的列表
        @author lvdaxianerplus
        @date 2026-05-25
        """
        result = []
        for chunk in chunks:
            content = chunk.get("description", "")
            if len(content) > MAX_CHUNK_CHARS:
                chunk = {**chunk, "description": content[:MAX_CHUNK_CHARS] + "..."}
            result.append(chunk)
        return result

    def _limit_total_chars(
        self,
        chunks: List[Dict[str, Any]],
        max_total_chars: int
    ) -> List[Dict[str, Any]]:
        """
        按总字符数限制，优先保留高分 chunk

        @param chunks - chunk 列表（已按分数降序排列）
        @param max_total_chars - 总字符上限
        @returns 限制后的列表
        @author lvdaxianerplus
        @date 2026-05-25
        """
        result = []
        total_chars = 0
        for chunk in chunks:
            content_len = len(chunk.get("description", ""))
            if total_chars + content_len > max_total_chars:
                break
            result.append(chunk)
            total_chars += content_len
        return result


# 全局单例
_compressor: Optional[ContextCompressor] = None


def get_context_compressor() -> ContextCompressor:
    """
    获取上下文压缩器单例

    @returns ContextCompressor 实例
    @author lvdaxianerplus
    @date 2026-05-25
    """
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressor()
    return _compressor
