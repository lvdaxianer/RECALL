"""
Obsidian 知识库重建脚本测试

Author: lvdaxianerplus
Date: 2026-06-05
"""

import httpx
import pytest

from scripts.rebuild_obsidian_knowledge_base import collect_obsidian_documents
from scripts.rebuild_obsidian_knowledge_base import fast_local_reset
from scripts.rebuild_obsidian_knowledge_base import get_json_with_retries


def test_collect_obsidian_documents_includes_every_supported_file(tmp_path):
    """递归收集每个非空 Markdown/TXT 文档。"""
    (tmp_path / "a.md").write_text("# A", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.markdown").write_text("# B", encoding="utf-8")
    (nested / "c.txt").write_text("C", encoding="utf-8")
    (tmp_path / "ignore.png").write_bytes(b"png")

    docs = collect_obsidian_documents(tmp_path)

    assert [doc.relative_path for doc in docs] == ["a.md", "nested/b.markdown", "nested/c.txt"]
    assert [doc.content for doc in docs] == ["# A", "# B", "C"]


def test_collect_obsidian_documents_skips_empty_documents(tmp_path):
    """空文档不进入录入队列。"""
    (tmp_path / "empty.md").write_text("   \n", encoding="utf-8")
    (tmp_path / "valid.md").write_text("正文", encoding="utf-8")

    docs = collect_obsidian_documents(tmp_path)

    assert [doc.relative_path for doc in docs] == ["valid.md"]


def test_fast_local_reset_clears_sqlite_tables(tmp_path):
    """快速重建模式直接清理本地知识库表，避免逐 chunk API 删除超时。"""
    db_path = tmp_path / "kb.sqlite"
    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE knowledge_bases (id TEXT)")
        connection.execute("CREATE TABLE knowledge_base_documents (id TEXT)")
        connection.execute("CREATE TABLE knowledge_base_chunks (id TEXT)")
        connection.execute("CREATE TABLE document_topics (document_id TEXT)")
        connection.execute("CREATE TABLE topic_nodes (knowledge_base_id TEXT)")
        connection.execute("CREATE TABLE topic_edges (knowledge_base_id TEXT)")
        connection.execute("INSERT INTO knowledge_bases VALUES ('kb-1')")
        connection.execute("INSERT INTO knowledge_base_documents VALUES ('doc-1')")
        connection.execute("INSERT INTO knowledge_base_chunks VALUES ('chunk-1')")
        connection.execute("INSERT INTO document_topics VALUES ('doc-1')")
        connection.execute("INSERT INTO topic_nodes VALUES ('kb-1')")
        connection.execute("INSERT INTO topic_edges VALUES ('kb-1')")

    fast_local_reset(db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM knowledge_bases").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM knowledge_base_documents").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM knowledge_base_chunks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM document_topics").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM topic_nodes").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM topic_edges").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_get_json_with_retries_recovers_from_transient_read_error():
    """状态轮询遇到瞬时读失败时会重试。"""

    class FlakyClient:
        def __init__(self):
            self.calls = 0

        async def get(self, url):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ReadError("temporary")
            return httpx.Response(200, json={"data": []}, request=httpx.Request("GET", url))

    client = FlakyClient()

    payload = await get_json_with_retries(client, "/documents", attempts=2, delay_seconds=0)

    assert payload == {"data": []}
    assert client.calls == 2
