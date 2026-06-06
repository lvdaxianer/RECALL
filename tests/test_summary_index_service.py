from app.services.summary_index_service import SummaryIndexService


def test_build_document_summary_payload_uses_metadata_or_features_summary():
    payload = SummaryIndexService().build_document_summary_payload(
        doc_id="doc-1",
        description="完整正文较长",
        metadata={"type": "asset", "id": "doc-1", "summary": "文档级摘要"},
        features={"tags": ["RAG", "检索"]},
    )

    assert payload["summary_type"] == "document"
    assert payload["summary_text"] == "文档级摘要"
    assert payload["metadata"]["parent_id"] == "doc-1"
    assert payload["metadata"]["summary_type"] == "document"
    assert payload["metadata"]["is_summary"] is True
    assert payload["important_kwd"] == ["RAG", "检索"]


def test_build_section_summary_payload_preserves_parent_and_section_fields():
    payload = SummaryIndexService().build_section_summary_payload(
        doc_id="doc-1",
        section_id="section-1",
        section_title="检索架构",
        summary_text="先摘要后证据召回",
        metadata={"type": "asset"},
    )

    assert payload["summary_type"] == "section"
    assert payload["metadata"]["parent_id"] == "doc-1"
    assert payload["metadata"]["section_id"] == "section-1"
    assert payload["metadata"]["section_title"] == "检索架构"
    assert payload["metadata"]["summary_type"] == "section"
    assert payload["metadata"]["is_summary"] is True
    assert payload["title_tks"] == "检索架构"
