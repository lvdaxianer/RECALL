"""
文档后台解析 worker 测试

Author: lvdaxianerplus
Date: 2026-06-05
"""

import pytest
import asyncio

from app.services.document_parse_worker import DocumentParseWorker
from app.services.knowledge_base_repository import KnowledgeBaseRepository


class FakeIngestService:
    """测试用解析服务。"""

    def __init__(self, repository):
        self.repository = repository

    async def parse_queued_document(self, document):
        """把原文作为一个 chunk 写入并标记 indexed。"""
        chunks = [{"chunk_index": 0, "title": "A", "content": document["raw_content"]}]
        self.repository.replace_document_chunks(
            document["knowledge_base_id"],
            document["id"],
            chunks,
        )
        self.repository.mark_document_parsed(
            document["knowledge_base_id"],
            document["id"],
            len(chunks),
        )
        return self.repository.mark_document_indexed(
            document["knowledge_base_id"],
            document["id"],
        )


@pytest.mark.asyncio
async def test_document_parse_worker_claims_and_processes_queued_documents(tmp_path):
    """worker 认领 queued 文档并完成解析状态流转。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    doc = repo.enqueue_document(kb["id"], "a.md", "text/markdown", "u1", "# A", "a.md")
    worker = DocumentParseWorker(repo, FakeIngestService(repo), batch_size=5, concurrency=2)

    processed = await worker.run_once()

    assert processed == 1
    updated = repo.get_document(kb["id"], doc["id"])
    assert updated["parse_status"] == "indexed"
    assert updated["chunk_count"] == 1


@pytest.mark.asyncio
async def test_document_parse_worker_marks_failure(tmp_path):
    """worker 捕获解析异常并标记 failed。"""

    class BrokenIngestService:
        async def parse_queued_document(self, document):
            raise RuntimeError("boom")

    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    doc = repo.enqueue_document(kb["id"], "broken.md", "text/markdown", "u1", "# Broken", "broken.md")
    worker = DocumentParseWorker(repo, BrokenIngestService(), batch_size=5, concurrency=2, max_attempts=1)

    processed = await worker.run_once()

    assert processed == 1
    updated = repo.get_document(kb["id"], doc["id"])
    assert updated["parse_status"] == "failed"
    assert "boom" in updated["parse_error"]


@pytest.mark.asyncio
async def test_document_parse_worker_does_not_retry_embedding_failures(tmp_path):
    """Embedding 失败属于索引硬失败，应直接标记 failed 并告知原因。"""

    class BrokenEmbeddingIngestService:
        async def parse_queued_document(self, document):
            raise RuntimeError("embedding 400")

    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    doc = repo.enqueue_document(kb["id"], "broken.md", "text/markdown", "u1", "# Broken", "broken.md")
    worker = DocumentParseWorker(repo, BrokenEmbeddingIngestService(), batch_size=5, concurrency=2)

    processed = await worker.run_once()

    assert processed == 1
    updated = repo.get_document(kb["id"], doc["id"])
    assert updated["parse_status"] == "failed"
    assert updated["parse_attempts"] == 1
    assert "embedding 400" in updated["parse_error"]


@pytest.mark.asyncio
async def test_document_parse_worker_retries_three_times_then_marks_failed(tmp_path):
    """worker 前两次失败重新入队，第三次失败后标记 failed。"""

    class BrokenIngestService:
        async def parse_queued_document(self, document):
            raise RuntimeError("parse exploded")

    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    doc = repo.enqueue_document(kb["id"], "broken.md", "text/markdown", "u1", "# Broken", "broken.md")
    worker = DocumentParseWorker(repo, BrokenIngestService(), batch_size=5, concurrency=2)

    first_processed = await worker.run_once()
    first = repo.get_document(kb["id"], doc["id"])

    assert first_processed == 1
    assert first["parse_status"] == "queued"
    assert first["parse_attempts"] == 1

    second_processed = await worker.run_once()
    second = repo.get_document(kb["id"], doc["id"])

    assert second_processed == 1
    assert second["parse_status"] == "queued"
    assert second["parse_attempts"] == 2

    third_processed = await worker.run_once()
    third = repo.get_document(kb["id"], doc["id"])

    assert third_processed == 1
    assert third["parse_status"] == "failed"
    assert third["parse_attempts"] == 3
    assert "parse exploded" in third["parse_error"]


@pytest.mark.asyncio
async def test_document_parse_worker_respects_concurrency_limit(tmp_path):
    """worker 同时解析文档数不能超过配置的 concurrency。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    for index in range(5):
        repo.enqueue_document(
            knowledge_base_id=kb["id"],
            document_name=f"{index}.md",
            content_type="text/markdown",
            owner_id="u1",
            raw_content="content",
        )

    class SlowIngest:
        def __init__(self):
            self.running = 0
            self.max_running = 0

        async def parse_queued_document(self, document):
            self.running += 1
            self.max_running = max(self.max_running, self.running)
            await asyncio.sleep(0.01)
            self.running -= 1
            return document

    ingest = SlowIngest()
    worker = DocumentParseWorker(repo, ingest, batch_size=5, concurrency=2)

    parsed_count = await worker.run_once()

    assert parsed_count == 5
    assert ingest.max_running == 2
