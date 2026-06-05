"""
Markdown 与纯文本 chunk 切分测试

Author: lvdaxianerplus
Date: 2026-06-03
"""

from app.services.markdown_chunk_service import MarkdownChunkService


def test_markdown_chunking_preserves_headings_and_order():
    """Markdown 切分保留标题和 chunk 顺序。"""
    service = MarkdownChunkService(max_chars=120, overlap=20)
    chunks = service.split("# A\n第一段。\n## B\n第二段。")

    assert chunks[0]["title"] == "A"
    assert chunks[1]["title"] == "B"
    assert chunks[0]["chunk_index"] == 0


def test_plain_text_chunking_returns_single_untitled_chunk():
    """纯文本切分返回无标题 chunk。"""
    service = MarkdownChunkService(max_chars=120, overlap=20)
    chunks = service.split("第一段。\n第二段。")

    assert chunks[0]["title"] == ""
    assert chunks[0]["content"] == "第一段。\n第二段。"


def test_markdown_chunking_drops_empty_chunks():
    """只有标题或空白内容的 section 不应产生空 chunk。"""
    service = MarkdownChunkService(max_chars=120, overlap=20)
    chunks = service.split("# 空标题\n\n## 有内容\n正文\n\n## 只有空白\n   ")

    assert chunks == [{"chunk_index": 0, "title": "有内容", "content": "正文", "indexed_content": "正文"}]


def test_markdown_chunking_respects_chunk_size():
    """长文本切分应遵守 chunk_size。"""
    service = MarkdownChunkService(max_chars=5, overlap=0)
    chunks = service.split("abcdefghij")

    assert [chunk["content"] for chunk in chunks] == ["abcde", "fghij"]


def test_markdown_chunking_respects_overlap():
    """滑动窗口切分应保留 overlap。"""
    service = MarkdownChunkService(max_chars=5, overlap=2)
    chunks = service.split("abcdefgh")

    assert [chunk["content"] for chunk in chunks] == ["abcde", "defgh", "gh"]


def test_markdown_chunking_adds_overlap_to_indexed_content_between_heading_chunks():
    """标题分块后也要为检索索引补齐前文 overlap。"""
    service = MarkdownChunkService(max_chars=100, overlap=7)

    chunks = service.split("# A\n第一段上下文ABCDEF\n## B\n第二段正文")

    assert chunks[0]["content"] == "第一段上下文ABCDEF"
    assert chunks[0]["indexed_content"] == "第一段上下文ABCDEF"
    assert chunks[1]["content"] == "第二段正文"
    assert chunks[1]["indexed_content"].startswith("文ABCDEF\n第二段正文")


def test_markdown_chunking_adds_overlap_after_semantic_groups():
    """语义计划合并后的相邻 chunk 也要补齐检索 overlap。"""
    service = MarkdownChunkService(max_chars=100, overlap=5)
    plan = {"groups": [["s1"], ["s2"]]}

    chunks = service.split("# A\n语义组一ABCDE\n# B\n语义组二正文", semantic_plan=plan)

    assert chunks[1]["content"] == "语义组二正文"
    assert chunks[1]["indexed_content"].startswith("ABCDE\n语义组二正文")


def test_markdown_chunking_groups_sections_by_semantic_plan():
    """语义计划可以按顺序合并 section。"""
    service = MarkdownChunkService(max_chars=120, overlap=0)
    plan = {"groups": [["s1", "s2"], ["s3"]]}
    chunks = service.split("# A\n正文 A\n## B\n正文 B\n# C\n正文 C", semantic_plan=plan)

    assert chunks[0]["title"] == "A / B"
    assert chunks[0]["content"] == "正文 A\n\n正文 B"
    assert chunks[1]["title"] == "C"


def test_markdown_chunking_splits_oversized_semantic_group_by_window():
    """过大的语义分组继续按滑动窗口兜底切分。"""
    service = MarkdownChunkService(max_chars=5, overlap=0)
    plan = {"groups": [["s1", "s2"]]}
    chunks = service.split("# A\nabcde\n## B\nfghij", semantic_plan=plan)

    assert [chunk["content"] for chunk in chunks] == ["abcde", "fghij"]


def test_markdown_chunking_ignores_deep_headings_as_boundaries():
    """超过配置深度的标题不作为结构边界。"""
    service = MarkdownChunkService(max_chars=120, overlap=0, max_heading_depth=2)
    chunks = service.split("# A\n正文 A\n### B\n正文 B")

    assert len(chunks) == 1
    assert chunks[0]["title"] == "A"
    assert "### B" in chunks[0]["content"]
