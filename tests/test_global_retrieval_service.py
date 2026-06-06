import asyncio

import pytest

from app.services.global_retrieval_service import ESSummaryRetriever
from app.services.global_retrieval_service import GlobalRetrievalService


class FakeRetriever:
    def __init__(self):
        self.calls = []

    async def search_summaries(self, query, top_k, summary_type=None):
        self.calls.append(("summaries", query, top_k, summary_type))
        return [
            {
                "id": "summary:doc-1:section-1",
                "description": "检索架构摘要",
                "metadata": {"parent_id": "doc-1", "section_id": "section-1", "section_title": "检索架构"},
                "score": 0.9,
            }
        ]

    async def search_evidence(self, query, parent_ids, section_ids, top_k):
        self.calls.append(("evidence", query, tuple(parent_ids), tuple(section_ids), top_k))
        return [
            {
                "id": "chunk-1",
                "description": "RRF、Rerank 和 summary-first 的证据 chunk",
                "metadata": {"parent_id": "doc-1", "section_id": "section-1"},
                "score": 0.8,
            }
        ]


@pytest.mark.asyncio
async def test_global_retrieval_runs_summary_first_then_evidence_expansion():
    retriever = FakeRetriever()
    context = await GlobalRetrievalService(retriever=retriever).build_context(
        query="总结 Recall RAG 架构",
        query_scope="global",
        top_k=3,
    )

    assert context["route"] == "summary_first"
    assert context["summaries"][0]["metadata"]["section_title"] == "检索架构"
    assert context["evidence_chunks"][0]["id"] == "chunk-1"
    assert context["parent_context"]["parent_ids"] == ["doc-1"]
    assert context["map_reduce_context"]["map_notes"][0]["parent_id"] == "doc-1"
    assert context["map_reduce_context"]["reduce_prompt_context"]
    assert retriever.calls[0][0] == "summaries"
    assert retriever.calls[1][0] == "evidence"


@pytest.mark.asyncio
async def test_global_retrieval_expands_document_and_section_summaries_separately():
    class MixedScopeRetriever:
        def __init__(self):
            self.calls = []

        async def search_summaries(self, query, top_k, summary_type=None):
            self.calls.append(("summaries", query, top_k, summary_type))
            return [
                {
                    "id": "summary:doc-1",
                    "description": "文档级摘要",
                    "metadata": {"parent_id": "doc-1"},
                    "score": 0.9,
                },
                {
                    "id": "summary:doc-2:section-2",
                    "description": "章节级摘要",
                    "metadata": {"parent_id": "doc-2", "section_id": "section-2"},
                    "score": 0.8,
                },
            ]

        async def search_evidence(self, query, parent_ids, section_ids, top_k):
            self.calls.append(("evidence", tuple(parent_ids), tuple(section_ids), top_k))
            if parent_ids == ["doc-1"] and section_ids == []:
                return [
                    {
                        "id": "chunk-doc-1",
                        "description": "文档级父文档证据",
                        "metadata": {"parent_id": "doc-1"},
                        "score": 0.9,
                    }
                ]
            if parent_ids == ["doc-2"] and section_ids == ["section-2"]:
                return [
                    {
                        "id": "chunk-doc-2-section-2",
                        "description": "章节级证据",
                        "metadata": {"parent_id": "doc-2", "section_id": "section-2"},
                        "score": 0.8,
                    }
                ]
            return []

    retriever = MixedScopeRetriever()

    context = await GlobalRetrievalService(retriever=retriever).build_context(
        query="总结 Recall RAG 架构",
        query_scope="global",
        top_k=3,
    )

    evidence_calls = [call for call in retriever.calls if call[0] == "evidence"]
    assert evidence_calls == [
        ("evidence", ("doc-1",), (), 3),
        ("evidence", ("doc-2",), ("section-2",), 3),
    ]
    assert {chunk["id"] for chunk in context["evidence_chunks"]} == {
        "chunk-doc-1",
        "chunk-doc-2-section-2",
    }


@pytest.mark.asyncio
async def test_global_retrieval_searches_evidence_scopes_concurrently():
    class ConcurrentScopeRetriever:
        def __init__(self):
            self.started = []
            self.both_started = asyncio.Event()

        async def search_summaries(self, query, top_k, summary_type=None):
            return [
                {
                    "id": "summary:doc-1",
                    "description": "文档级摘要",
                    "metadata": {"parent_id": "doc-1"},
                    "score": 0.9,
                },
                {
                    "id": "summary:doc-2:section-2",
                    "description": "章节级摘要",
                    "metadata": {"parent_id": "doc-2", "section_id": "section-2"},
                    "score": 0.8,
                },
            ]

        async def search_evidence(self, query, parent_ids, section_ids, top_k):
            self.started.append((tuple(parent_ids), tuple(section_ids)))
            if len(self.started) == 2:
                self.both_started.set()
            await asyncio.wait_for(self.both_started.wait(), timeout=0.05)
            return [
                {
                    "id": f"chunk:{parent_ids[0]}:{section_ids[0] if section_ids else 'doc'}",
                    "description": "证据",
                    "metadata": {"parent_id": parent_ids[0]},
                    "score": 0.9,
                }
            ]

    retriever = ConcurrentScopeRetriever()

    context = await GlobalRetrievalService(retriever=retriever).build_context(
        query="总结 Recall RAG 架构",
        query_scope="global",
        top_k=3,
    )

    assert len(context["evidence_chunks"]) == 2


def test_build_synthesis_context_is_structured_and_cot_safe():
    service = GlobalRetrievalService(retriever=None)
    context = service.build_synthesis_context(
        query="这个项目整体架构是什么？",
        map_inputs=[
            {
                "source_doc_id": "doc-1",
                "summary": {"description": "项目由 Runtime、Retrieval、SEE 组成。"},
                "evidence_chunks": [
                    {"id": "chunk-1", "description": "Runtime Adapter 负责 HTTP/SSE。"},
                    {"id": "chunk-2", "description": "Retrieval Core 负责 ES、Milvus、Graph。"},
                ],
            }
        ],
    )

    assert context["query"] == "这个项目整体架构是什么？"
    assert context["reduce_instruction"] == "基于每个文档或章节的摘要和证据 chunk 生成全局答案"
    assert context["map_notes"][0]["source_doc_id"] == "doc-1"
    assert context["map_notes"][0]["evidence"][0]["chunk_id"] == "chunk-1"
    assert "private_cot" not in context
    assert "chain_of_thought" not in context


@pytest.mark.asyncio
async def test_es_summary_retriever_searches_summary_documents_with_metadata_filter():
    class FakeES:
        def __init__(self):
            self.calls = []

        async def search_weighted(self, index_name, query, top_k, metadata_filter=None):
            self.calls.append((index_name, query, top_k, metadata_filter))
            return [
                {
                    "id": "summary:doc-1",
                    "description": "项目整体架构摘要",
                    "metadata": {"parent_id": "doc-1", "summary_type": "document", "is_summary": True},
                    "score": 0.9,
                }
            ]

    fake_es = FakeES()
    retriever = ESSummaryRetriever(es_service=fake_es, index_names=["rag_assets"])

    results = await retriever.search_summaries("项目整体架构", top_k=3, summary_type="document")

    assert fake_es.calls == [
        ("rag_assets", "项目整体架构", 3, {"is_summary": True, "summary_type": "document"})
    ]
    assert results[0]["id"] == "summary:doc-1"


@pytest.mark.asyncio
async def test_es_summary_retriever_searches_multiple_indexes_concurrently():
    class FakeES:
        def __init__(self):
            self.started = []
            self.both_started = asyncio.Event()

        async def search_weighted(self, index_name, query, top_k, metadata_filter=None):
            self.started.append(index_name)
            if len(self.started) == 2:
                self.both_started.set()
            await asyncio.wait_for(self.both_started.wait(), timeout=0.05)
            return [
                {
                    "id": f"summary:{index_name}",
                    "description": index_name,
                    "metadata": {"parent_id": index_name, "is_summary": True},
                    "score": 0.9 if index_name == "rag_assets" else 0.8,
                }
            ]

    fake_es = FakeES()
    retriever = ESSummaryRetriever(es_service=fake_es, index_names=["rag_skills", "rag_assets"])

    results = await retriever.search_summaries("项目整体架构", top_k=2)

    assert {item["id"] for item in results} == {"summary:rag_skills", "summary:rag_assets"}
    assert results[0]["id"] == "summary:rag_assets"


def test_es_summary_retriever_merge_keeps_highest_scored_duplicate():
    retriever = ESSummaryRetriever(es_service=None, index_names=[])

    merged = retriever._merge_ranked_results(
        [
            [{"id": "summary:doc-1", "description": "低分旧摘要", "score": 0.3}],
            [{"id": "summary:doc-1", "description": "高分新摘要", "score": 0.9}],
            [{"id": "summary:doc-2", "description": "另一个摘要", "score": 0.8}],
        ],
        top_k=2,
    )

    assert [item["id"] for item in merged] == ["summary:doc-1", "summary:doc-2"]
    assert merged[0]["description"] == "高分新摘要"
    assert merged[0]["score"] == 0.9


@pytest.mark.asyncio
async def test_es_summary_retriever_keeps_other_summary_indexes_when_one_fails():
    class FakeES:
        async def search_weighted(self, index_name, query, top_k, metadata_filter=None):
            if index_name == "rag_skills":
                raise RuntimeError("skills index unavailable")
            return [
                {
                    "id": "summary:asset",
                    "description": "asset 摘要",
                    "metadata": {"parent_id": "doc-asset", "is_summary": True},
                    "score": 0.9,
                }
            ]

    retriever = ESSummaryRetriever(es_service=FakeES(), index_names=["rag_skills", "rag_assets"])

    results = await retriever.search_summaries("项目整体架构", top_k=2)

    assert [item["id"] for item in results] == ["summary:asset"]


@pytest.mark.asyncio
async def test_es_summary_retriever_searches_evidence_by_parent_and_section_scope():
    class FakeES:
        def __init__(self):
            self.calls = []

        async def search_parent_contexts(self, index_name, parent_ids, section_ids=None, limit=20):
            self.calls.append((index_name, tuple(parent_ids), tuple(section_ids or []), limit))
            return [
                {
                    "id": "chunk-1",
                    "description": "证据 chunk",
                    "metadata": {"parent_id": "doc-1", "section_id": "section-1"},
                    "score": 0.8,
                }
            ]

    fake_es = FakeES()
    retriever = ESSummaryRetriever(es_service=fake_es, index_names=["rag_assets"])

    results = await retriever.search_evidence(
        "项目整体架构",
        parent_ids=["doc-1"],
        section_ids=["section-1"],
        top_k=5,
    )

    assert fake_es.calls == [("rag_assets", ("doc-1",), ("section-1",), 5)]
    assert results[0]["id"] == "chunk-1"


@pytest.mark.asyncio
async def test_es_summary_retriever_searches_evidence_indexes_concurrently():
    class FakeES:
        def __init__(self):
            self.started = []
            self.both_started = asyncio.Event()

        async def search_parent_contexts(self, index_name, parent_ids, section_ids=None, limit=20):
            self.started.append(index_name)
            if len(self.started) == 2:
                self.both_started.set()
            await asyncio.wait_for(self.both_started.wait(), timeout=0.05)
            return [
                {
                    "id": f"chunk:{index_name}",
                    "description": index_name,
                    "metadata": {"parent_id": "doc-1", "section_id": "section-1"},
                    "score": 0.9 if index_name == "rag_assets" else 0.7,
                }
            ]

    fake_es = FakeES()
    retriever = ESSummaryRetriever(es_service=fake_es, index_names=["rag_skills", "rag_assets"])

    results = await retriever.search_evidence(
        "项目整体架构",
        parent_ids=["doc-1"],
        section_ids=["section-1"],
        top_k=2,
    )

    assert {item["id"] for item in results} == {"chunk:rag_skills", "chunk:rag_assets"}
    assert results[0]["id"] == "chunk:rag_assets"


@pytest.mark.asyncio
async def test_es_summary_retriever_keeps_other_evidence_indexes_when_one_fails():
    class FakeES:
        async def search_parent_contexts(self, index_name, parent_ids, section_ids=None, limit=20):
            if index_name == "rag_skills":
                raise RuntimeError("skills evidence unavailable")
            return [
                {
                    "id": "chunk:asset",
                    "description": "asset 证据",
                    "metadata": {"parent_id": "doc-1", "section_id": "section-1"},
                    "score": 0.9,
                }
            ]

    retriever = ESSummaryRetriever(es_service=FakeES(), index_names=["rag_skills", "rag_assets"])

    results = await retriever.search_evidence(
        "项目整体架构",
        parent_ids=["doc-1"],
        section_ids=["section-1"],
        top_k=2,
    )

    assert [item["id"] for item in results] == ["chunk:asset"]
