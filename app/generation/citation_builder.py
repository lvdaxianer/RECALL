"""
引用溯源构建模块

将检索到的 chunks 格式化为带编号引用的上下文，供 LLM 生成时引用

@author lvdaxianerplus
@date 2026-05-25
"""

from typing import List, Dict, Any


def build_context_with_citations(chunks: List[Dict[str, Any]]) -> str:
    """
    将 chunks 构建为带引用编号的上下文字符串

    @param chunks - chunk 列表，每项含 description、metadata
    @returns 格式化的上下文字符串
    @author lvdaxianerplus
    @date 2026-05-25
    """
    if not chunks:
        return "（无可用参考资料）"

    lines = []
    for i, chunk in enumerate(chunks, start=1):
        source = _extract_source_label(chunk, i)
        content = chunk.get("description", "").strip()
        lines.append(f"[{i}] {source}\n{content}")

    return "\n\n".join(lines)


def build_citation_list(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    构建引用列表，供响应体返回给调用方

    @param chunks - chunk 列表
    @returns 引用列表，每项含 index、chunk_id、source、content、relevance_score
    @author lvdaxianerplus
    @date 2026-05-25
    """
    citations = []
    for i, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {})
        citations.append({
            "index": i,
            "chunk_id": metadata.get("id", ""),
            "source": metadata.get("source", metadata.get("id", f"来源{i}")),
            "page": metadata.get("page"),
            "section": metadata.get("section"),
            "content": chunk.get("description", "")[:200],
            "relevance_score": round(chunk.get("score", 0), 4)
        })
    return citations


def _extract_source_label(chunk: Dict[str, Any], index: int) -> str:
    """
    从 chunk 元数据中提取来源标签

    @param chunk - chunk 数据
    @param index - 引用编号
    @returns 来源标签字符串
    @author lvdaxianerplus
    @date 2026-05-25
    """
    metadata = chunk.get("metadata", {})
    source = metadata.get("source", "")
    page = metadata.get("page")
    section = metadata.get("section", "")

    # 优先使用 source 字段
    if source:
        label = source
        if page:
            label += f", 第{page}页"
        if section:
            label += f", {section}"
        return label

    # 降级使用 id
    doc_id = metadata.get("id", f"文档{index}")
    return doc_id
