"""
Build document and section summary payloads for summary-first retrieval.
"""

from typing import Any, Dict, Optional


class SummaryIndexService:
    """Constructs summary index payloads without calling external models."""

    def build_summary_payload(
        self,
        doc_id: str,
        summary_id: str,
        summary: str,
        level: str,
        metadata: Dict[str, Any],
        section_id: Optional[str] = None,
        section_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a backward-compatible summary payload for document or section summaries."""
        if level not in {"document", "section"}:
            raise ValueError("summary level must be 'document' or 'section'")
        if level == "section":
            return self._build_section_payload(doc_id, summary_id, summary, metadata, section_id, section_title)
        return self._build_document_payload(doc_id, summary_id, summary, metadata)

    def build_document_summary_payload(
        self,
        doc_id: str,
        description: str,
        metadata: Dict[str, Any],
        features: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        features = features or {}
        summary_text = metadata.get("summary") or features.get("summary") or description
        title = metadata.get("title") or metadata.get("description") or doc_id
        enriched_metadata = dict(metadata)
        enriched_metadata.setdefault("parent_id", doc_id)
        enriched_metadata["summary_type"] = "document"
        enriched_metadata["is_summary"] = True
        return self._payload(
            doc_id=f"summary:{doc_id}",
            summary_type="document",
            summary_text=summary_text,
            metadata=enriched_metadata,
            title=title,
            tags=features.get("tags", []),
        )

    def _build_document_payload(
        self,
        doc_id: str,
        summary_id: str,
        summary: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a simplified document summary payload for compatibility with older callers."""
        enriched_metadata = dict(metadata or {})
        enriched_metadata.update({
            "parent_id": doc_id,
            "source_doc_id": doc_id,
            "summary_level": "document",
            "summary_id": summary_id,
            "summary_type": "document",
            "is_summary": True,
        })
        return {
            "doc_id": summary_id,
            "id": summary_id,
            "description": summary,
            "metadata": enriched_metadata,
            "features": {
                "category": "summary",
                "tags": ["summary", "document"],
                "title": enriched_metadata.get("title") or doc_id,
            },
            "title_tks": enriched_metadata.get("title") or doc_id,
            "title_sm_tks": enriched_metadata.get("title") or doc_id,
            "important_kwd": ["summary", "document"],
            "important_tks": "summary document",
            "question_tks": enriched_metadata.get("title") or summary,
            "content_ltks": summary,
            "content_sm_ltks": summary,
        }

    def _build_section_payload(
        self,
        doc_id: str,
        summary_id: str,
        summary: str,
        metadata: Dict[str, Any],
        section_id: Optional[str],
        section_title: Optional[str],
    ) -> Dict[str, Any]:
        """Build a simplified section summary payload for compatibility with older callers."""
        enriched_metadata = dict(metadata or {})
        enriched_metadata.update({
            "parent_id": doc_id,
            "source_doc_id": doc_id,
            "summary_level": "section",
            "summary_id": summary_id,
            "summary_type": "section",
            "is_summary": True,
        })
        if section_id:
            enriched_metadata["section_id"] = section_id
        if section_title:
            enriched_metadata["section_title"] = section_title
        return {
            "doc_id": summary_id,
            "id": summary_id,
            "description": summary,
            "metadata": enriched_metadata,
            "features": {
                "category": "summary",
                "tags": ["summary", "section"],
                "title": section_title or summary_id,
            },
            "title_tks": section_title or summary_id,
            "title_sm_tks": section_title or summary_id,
            "important_kwd": ["summary", "section"],
            "important_tks": "summary section",
            "question_tks": section_title or summary,
            "content_ltks": summary,
            "content_sm_ltks": summary,
        }

    def build_section_summary_payload(
        self,
        doc_id: str,
        section_id: str,
        section_title: str,
        summary_text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        enriched_metadata = dict(metadata or {})
        enriched_metadata.update({
            "parent_id": doc_id,
            "section_id": section_id,
            "section_title": section_title,
            "summary_type": "section",
            "is_summary": True,
        })
        return self._payload(
            doc_id=f"summary:{doc_id}:{section_id}",
            summary_type="section",
            summary_text=summary_text,
            metadata=enriched_metadata,
            title=section_title,
            tags=[],
        )

    def _payload(
        self,
        doc_id: str,
        summary_type: str,
        summary_text: str,
        metadata: Dict[str, Any],
        title: str,
        tags: list[Any],
    ) -> Dict[str, Any]:
        important_kwd = [str(tag) for tag in tags if tag]
        return {
            "id": doc_id,
            "summary_type": summary_type,
            "summary_text": summary_text,
            "description": summary_text,
            "metadata": metadata,
            "title_tks": title,
            "title_sm_tks": title,
            "important_kwd": important_kwd,
            "important_tks": " ".join(important_kwd),
            "question_tks": "",
            "content_ltks": summary_text,
            "content_sm_ltks": summary_text,
        }
