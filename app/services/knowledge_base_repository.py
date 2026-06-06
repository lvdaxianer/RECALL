"""
知识库 SQLite 仓储

提供知识库、文档和 chunk 的轻量持久化能力。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from __future__ import annotations

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CREATE_KB_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_DOCUMENT_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_base_documents (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL,
    document_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    external_id TEXT,
    status TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    raw_content TEXT,
    parse_status TEXT NOT NULL DEFAULT 'queued',
    parse_attempts INTEGER NOT NULL DEFAULT 0,
    parse_error TEXT,
    queued_at TEXT,
    processing_started_at TEXT,
    parsed_at TEXT,
    indexed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(knowledge_base_id, external_id)
)
"""

CREATE_CHUNK_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_base_chunks (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    indexed_content TEXT,
    token_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(document_id, chunk_index)
)
"""

CREATE_KB_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_base_settings (
    knowledge_base_id TEXT PRIMARY KEY,
    semantic_chunking_enabled INTEGER NOT NULL DEFAULT 0,
    chunk_size INTEGER NOT NULL DEFAULT 1000,
    overlap INTEGER NOT NULL DEFAULT 150,
    top_k_default INTEGER NOT NULL DEFAULT 5,
    max_heading_depth INTEGER NOT NULL DEFAULT 3,
    llm_planning_timeout_ms INTEGER NOT NULL DEFAULT 8000,
    updated_at TEXT NOT NULL
)
"""

CREATE_SYNONYM_GROUP_TABLE = """
CREATE TABLE IF NOT EXISTS synonym_groups (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT,
    canonical TEXT NOT NULL,
    terms_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    owner_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_DOCUMENT_TOPIC_TABLE = """
CREATE TABLE IF NOT EXISTS document_topics (
    document_id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL,
    primary_topic TEXT NOT NULL,
    parent_topics_json TEXT NOT NULL,
    sibling_topics_json TEXT NOT NULL,
    child_topics_json TEXT NOT NULL,
    topic_aliases_json TEXT NOT NULL,
    topic_path_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_json TEXT NOT NULL,
    extraction_status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_TOPIC_NODE_TABLE = """
CREATE TABLE IF NOT EXISTS topic_nodes (
    knowledge_base_id TEXT NOT NULL,
    canonical_topic TEXT NOT NULL,
    normalized_topic TEXT NOT NULL,
    parent_topic TEXT,
    aliases_json TEXT NOT NULL,
    doc_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (knowledge_base_id, normalized_topic)
)
"""

CREATE_TOPIC_EDGE_TABLE = """
CREATE TABLE IF NOT EXISTS topic_edges (
    knowledge_base_id TEXT NOT NULL,
    parent_topic TEXT NOT NULL,
    child_topic TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    doc_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (knowledge_base_id, parent_topic, child_topic, edge_type)
)
"""

KB_SETTINGS_FIELDS = {
    "semantic_chunking_enabled",
    "chunk_size",
    "overlap",
    "top_k_default",
    "max_heading_depth",
    "llm_planning_timeout_ms",
}

SYNONYM_GROUP_FIELDS = {"knowledge_base_id", "canonical", "terms", "enabled", "owner_id"}


class KnowledgeBaseRepository:
    """知识库 SQLite 仓储实现。"""

    def __init__(self, db_path: str):
        """初始化仓储并确保表结构存在。"""
        self.db_path = db_path
        self._ensure_parent_dir()
        self._initialize_schema()

    def create_knowledge_base(self, name: str, description: str, owner_id: str) -> dict[str, Any]:
        """创建知识库并返回完整记录。"""
        kb_id = f"kb_{uuid.uuid4().hex}"
        now = _utc_now()
        record = {
            "id": kb_id,
            "name": name,
            "description": description,
            "owner_id": owner_id,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_bases (id, name, description, owner_id, status, created_at, updated_at)
                VALUES (:id, :name, :description, :owner_id, :status, :created_at, :updated_at)
                """,
                record,
            )
            self._create_default_settings(connection, kb_id, now)
        return record

    def list_knowledge_bases(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        """列出知识库，传入 owner_id 时按归属过滤。"""
        with self._connect() as connection:
            if owner_id is None:
                rows = connection.execute(
                    "SELECT * FROM knowledge_bases ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM knowledge_bases WHERE owner_id = ? ORDER BY created_at DESC",
                    (owner_id,),
                ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_knowledge_base(self, kb_id: str) -> dict[str, Any] | None:
        """按 ID 读取知识库，不存在时返回 None。"""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_bases WHERE id = ?",
                (kb_id,),
            ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def get_knowledge_bases_by_ids(self, kb_ids: list[str]) -> list[dict[str, Any]]:
        """按 ID 批量读取知识库，按传入顺序返回存在的记录。"""
        if not kb_ids:
            return []
        placeholders = ",".join("?" for _ in kb_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM knowledge_bases WHERE id IN ({placeholders})",
                kb_ids,
            ).fetchall()
        records = {_row_to_dict(row)["id"]: _row_to_dict(row) for row in rows}
        return [records[kb_id] for kb_id in kb_ids if kb_id in records]

    def update_knowledge_base(
        self,
        kb_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """更新知识库名称或描述并返回最新记录。"""
        current = self._require_knowledge_base(kb_id)
        updated = {
            "id": kb_id,
            "name": name if name is not None else current["name"],
            "description": description if description is not None else current["description"],
            "updated_at": _utc_now(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_bases
                SET name = :name, description = :description, updated_at = :updated_at
                WHERE id = :id
                """,
                updated,
            )
        return self._require_knowledge_base(kb_id)

    def update_knowledge_base_status(self, kb_id: str, status: str) -> dict[str, Any]:
        """更新知识库状态并返回最新记录。"""
        self._require_knowledge_base(kb_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE knowledge_bases SET status = ?, updated_at = ? WHERE id = ?",
                (status, _utc_now(), kb_id),
            )
        return self._require_knowledge_base(kb_id)

    def get_knowledge_base_settings(self, knowledge_base_id: str) -> dict[str, Any]:
        """读取知识库分块与检索设置。"""
        self._require_knowledge_base(knowledge_base_id)
        with self._connect() as connection:
            self._ensure_default_settings(connection, knowledge_base_id)
            row = connection.execute(
                "SELECT * FROM knowledge_base_settings WHERE knowledge_base_id = ?",
                (knowledge_base_id,),
            ).fetchone()
        return _settings_row_to_dict(row)

    def update_knowledge_base_settings(
        self,
        knowledge_base_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """局部更新知识库分块与检索设置。"""
        self._require_knowledge_base(knowledge_base_id)
        clean_updates = {key: value for key, value in updates.items() if key in KB_SETTINGS_FIELDS}
        if not clean_updates:
            return self.get_knowledge_base_settings(knowledge_base_id)
        now = _utc_now()
        assignments = ", ".join(f"{key} = :{key}" for key in clean_updates)
        params = {
            **clean_updates,
            "knowledge_base_id": knowledge_base_id,
            "updated_at": now,
        }
        with self._connect() as connection:
            self._ensure_default_settings(connection, knowledge_base_id)
            connection.execute(
                f"""
                UPDATE knowledge_base_settings
                SET {assignments}, updated_at = :updated_at
                WHERE knowledge_base_id = :knowledge_base_id
                """,
                params,
            )
        return self.get_knowledge_base_settings(knowledge_base_id)

    def create_synonym_group(
        self,
        knowledge_base_id: str | None,
        canonical: str,
        terms: list[str],
        owner_id: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """创建同义词组。"""
        now = _utc_now()
        record = {
            "id": f"syn_{uuid.uuid4().hex}",
            "knowledge_base_id": knowledge_base_id,
            "canonical": canonical.strip(),
            "terms_json": json.dumps(_normalize_terms(terms), ensure_ascii=False),
            "enabled": 1 if enabled else 0,
            "owner_id": owner_id,
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO synonym_groups
                    (id, knowledge_base_id, canonical, terms_json, enabled, owner_id, created_at, updated_at)
                VALUES
                    (:id, :knowledge_base_id, :canonical, :terms_json, :enabled, :owner_id, :created_at, :updated_at)
                """,
                record,
            )
        return self.get_synonym_group(record["id"])

    def get_synonym_group(self, group_id: str) -> dict[str, Any] | None:
        """按 ID 读取同义词组。"""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM synonym_groups WHERE id = ?",
                (group_id,),
            ).fetchone()
        return _synonym_row_to_dict(row) if row is not None else None

    def list_synonym_groups(
        self,
        knowledge_base_id: str | None = None,
        include_global: bool = True,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        """列出同义词组，可按知识库范围过滤。"""
        where_clauses: list[str] = []
        params: list[Any] = []
        if knowledge_base_id is not None:
            if include_global:
                where_clauses.append("(knowledge_base_id = ? OR knowledge_base_id IS NULL)")
            else:
                where_clauses.append("knowledge_base_id = ?")
            params.append(knowledge_base_id)
        elif not include_global:
            where_clauses.append("knowledge_base_id IS NOT NULL")
        else:
            pass
        if enabled_only:
            where_clauses.append("enabled = 1")
        else:
            pass
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM synonym_groups {where_sql} ORDER BY created_at DESC",
                params,
            ).fetchall()
        return [_synonym_row_to_dict(row) for row in rows]

    def get_synonym_revision(self, knowledge_base_ids: list[str]) -> str:
        """返回同义词作用域 revision，用于编译索引缓存。"""
        scoped_ids = sorted(set(knowledge_base_ids))
        placeholders = ",".join("?" for _ in scoped_ids)
        if scoped_ids:
            where_sql = f"knowledge_base_id IS NULL OR knowledge_base_id IN ({placeholders})"
            params = scoped_ids
        else:
            where_sql = "knowledge_base_id IS NULL"
            params = []
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS total, COALESCE(MAX(updated_at), '') AS max_updated_at
                FROM synonym_groups
                WHERE enabled = 1 AND ({where_sql})
                """,
                params,
            ).fetchone()
        return f"{row['total']}:{row['max_updated_at']}"

    def update_synonym_group(
        self,
        group_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """局部更新同义词组。"""
        current = self.get_synonym_group(group_id)
        if current is None:
            raise ValueError("同义词组不存在")
        clean_updates = {key: value for key, value in updates.items() if key in SYNONYM_GROUP_FIELDS}
        if not clean_updates:
            return current
        if "terms" in clean_updates:
            clean_updates["terms_json"] = json.dumps(_normalize_terms(clean_updates.pop("terms")), ensure_ascii=False)
        else:
            pass
        if "canonical" in clean_updates:
            clean_updates["canonical"] = str(clean_updates["canonical"]).strip()
        else:
            pass
        if "enabled" in clean_updates:
            clean_updates["enabled"] = 1 if clean_updates["enabled"] else 0
        else:
            pass
        clean_updates["updated_at"] = _utc_now()
        clean_updates["id"] = group_id
        assignments = ", ".join(f"{key} = :{key}" for key in clean_updates if key != "id")
        with self._connect() as connection:
            connection.execute(
                f"UPDATE synonym_groups SET {assignments} WHERE id = :id",
                clean_updates,
            )
        return self.get_synonym_group(group_id)

    def delete_synonym_group(self, group_id: str) -> dict[str, Any]:
        """删除同义词组并返回删除 ID。"""
        if self.get_synonym_group(group_id) is None:
            raise ValueError("同义词组不存在")
        with self._connect() as connection:
            connection.execute("DELETE FROM synonym_groups WHERE id = ?", (group_id,))
        return {"id": group_id}

    def mark_knowledge_base_changed(self, kb_id: str) -> dict[str, Any]:
        """标记知识库存在未发布变更。"""
        current = self._require_knowledge_base(kb_id)
        if current["status"] in {"deleted", "archived"}:
            return current
        return self.update_knowledge_base_status(kb_id, "changed")

    def upsert_document_topics(
        self,
        knowledge_base_id: str,
        document_id: str,
        primary_topic: str,
        parent_topics: list[str] | None = None,
        sibling_topics: list[str] | None = None,
        child_topics: list[str] | None = None,
        topic_aliases: list[str] | None = None,
        topic_path: list[str] | None = None,
        confidence: float = 0.0,
        evidence: list[str] | None = None,
        extraction_status: str = "ready",
    ) -> dict[str, Any]:
        """保存文档主题抽取结果，并重建该知识库的主题索引。"""
        self._require_knowledge_base(knowledge_base_id)
        document = self.get_document(knowledge_base_id, document_id)
        if document is None:
            raise ValueError("文档不存在")
        normalized_primary = str(primary_topic).strip()
        if not normalized_primary:
            raise ValueError("主主题不能为空")
        now = _utc_now()
        record = {
            "document_id": document_id,
            "knowledge_base_id": knowledge_base_id,
            "primary_topic": normalized_primary,
            "parent_topics_json": _json_list(parent_topics),
            "sibling_topics_json": _json_list(sibling_topics),
            "child_topics_json": _json_list(child_topics),
            "topic_aliases_json": _json_list(topic_aliases),
            "topic_path_json": _json_list(topic_path),
            "confidence": max(0.0, min(float(confidence), 1.0)),
            "evidence_json": _json_list(evidence),
            "extraction_status": extraction_status or "ready",
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_topics
                    (document_id, knowledge_base_id, primary_topic, parent_topics_json, sibling_topics_json,
                     child_topics_json, topic_aliases_json, topic_path_json, confidence, evidence_json,
                     extraction_status, created_at, updated_at)
                VALUES
                    (:document_id, :knowledge_base_id, :primary_topic, :parent_topics_json, :sibling_topics_json,
                     :child_topics_json, :topic_aliases_json, :topic_path_json, :confidence, :evidence_json,
                     :extraction_status, :created_at, :updated_at)
                ON CONFLICT(document_id) DO UPDATE SET
                    knowledge_base_id = excluded.knowledge_base_id,
                    primary_topic = excluded.primary_topic,
                    parent_topics_json = excluded.parent_topics_json,
                    sibling_topics_json = excluded.sibling_topics_json,
                    child_topics_json = excluded.child_topics_json,
                    topic_aliases_json = excluded.topic_aliases_json,
                    topic_path_json = excluded.topic_path_json,
                    confidence = excluded.confidence,
                    evidence_json = excluded.evidence_json,
                    extraction_status = excluded.extraction_status,
                    updated_at = excluded.updated_at
                """,
                record,
            )
            self._rebuild_topic_index(connection, knowledge_base_id)
        result = self.get_document_topics(knowledge_base_id, document_id)
        if result is None:
            raise ValueError("主题保存失败")
        return result

    def get_document_topics(self, knowledge_base_id: str, document_id: str) -> dict[str, Any] | None:
        """读取文档主题抽取结果。"""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM document_topics
                WHERE knowledge_base_id = ? AND document_id = ?
                """,
                (knowledge_base_id, document_id),
            ).fetchone()
        return _document_topic_row_to_dict(row) if row is not None else None

    def list_document_topics(self, knowledge_base_id: str) -> list[dict[str, Any]]:
        """列出知识库下所有文档主题事实。"""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    dt.*,
                    d.document_name,
                    d.status AS document_status,
                    d.updated_at AS document_updated_at
                FROM document_topics dt
                JOIN knowledge_base_documents d ON d.id = dt.document_id
                WHERE dt.knowledge_base_id = ?
                ORDER BY dt.updated_at DESC
                """,
                (knowledge_base_id,),
            ).fetchall()
        return [_document_topic_row_to_dict(row) for row in rows]

    def list_topic_nodes(self, knowledge_base_id: str, prefix: str | None = None) -> list[dict[str, Any]]:
        """列出主题节点，可按标准化主题前缀过滤。"""
        normalized_prefix = _normalize_topic(prefix or "")
        with self._connect() as connection:
            if normalized_prefix:
                rows = connection.execute(
                    """
                    SELECT * FROM topic_nodes
                    WHERE knowledge_base_id = ? AND normalized_topic LIKE ?
                    ORDER BY doc_count DESC, canonical_topic ASC
                    """,
                    (knowledge_base_id, f"{normalized_prefix}%"),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM topic_nodes
                    WHERE knowledge_base_id = ?
                    ORDER BY doc_count DESC, canonical_topic ASC
                    """,
                    (knowledge_base_id,),
                ).fetchall()
        return [_topic_node_row_to_dict(row) for row in rows]

    def upsert_topic_node(
        self,
        knowledge_base_id: str,
        canonical_topic: str,
        parent_topic: str | None = None,
        aliases: list[str] | None = None,
        doc_count: int = 0,
    ) -> dict[str, Any]:
        """显式写入或更新主题节点。"""
        now = _utc_now()
        normalized_topic = _normalize_topic(canonical_topic)
        if not normalized_topic:
            raise ValueError("主题不能为空")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO topic_nodes
                    (knowledge_base_id, canonical_topic, normalized_topic, parent_topic, aliases_json, doc_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(knowledge_base_id, normalized_topic) DO UPDATE SET
                    canonical_topic = excluded.canonical_topic,
                    parent_topic = excluded.parent_topic,
                    aliases_json = excluded.aliases_json,
                    doc_count = excluded.doc_count,
                    updated_at = excluded.updated_at
                """,
                (
                    knowledge_base_id,
                    canonical_topic.strip(),
                    normalized_topic,
                    parent_topic,
                    _json_list(aliases),
                    max(0, int(doc_count)),
                    now,
                ),
            )
        nodes = self.list_topic_nodes(knowledge_base_id)
        return next(node for node in nodes if node["normalized_topic"] == normalized_topic)

    def upsert_topic_edge(
        self,
        knowledge_base_id: str,
        parent_topic: str,
        child_topic: str,
        edge_type: str,
        doc_count: int = 0,
    ) -> dict[str, Any]:
        """显式写入或更新主题关系边。"""
        now = _utc_now()
        if not parent_topic.strip() or not child_topic.strip():
            raise ValueError("主题边两端不能为空")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO topic_edges
                    (knowledge_base_id, parent_topic, child_topic, edge_type, doc_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(knowledge_base_id, parent_topic, child_topic, edge_type) DO UPDATE SET
                    doc_count = excluded.doc_count,
                    updated_at = excluded.updated_at
                """,
                (
                    knowledge_base_id,
                    parent_topic.strip(),
                    child_topic.strip(),
                    edge_type,
                    max(0, int(doc_count)),
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM topic_edges
                WHERE knowledge_base_id = ? AND parent_topic = ? AND child_topic = ? AND edge_type = ?
                """,
                (knowledge_base_id, parent_topic.strip(), child_topic.strip(), edge_type),
            ).fetchone()
        return _row_to_dict(row)

    def find_documents_by_topic(
        self,
        knowledge_base_id: str,
        topic: str,
        relation_type: str = "same",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """按主题关系查找文档，不依赖 LLM。"""
        normalized = _normalize_topic(topic)
        if not normalized or limit <= 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    dt.*,
                    d.document_name,
                    d.status AS document_status,
                    d.updated_at AS document_updated_at
                FROM document_topics dt
                JOIN knowledge_base_documents d ON d.id = dt.document_id
                WHERE dt.knowledge_base_id = ?
                ORDER BY dt.updated_at DESC
                """,
                (knowledge_base_id,),
            ).fetchall()
        matches = []
        for row in rows:
            record = _document_topic_row_to_dict(row)
            if _document_topic_matches(record, normalized, relation_type):
                matches.append(record)
            if len(matches) >= limit:
                break
        return matches

    def delete_knowledge_base(self, kb_id: str) -> dict[str, Any]:
        """软删除知识库并级联删除该库下文档和 chunk。"""
        self._require_knowledge_base(kb_id)
        now = _utc_now()
        with self._connect() as connection:
            document_count = connection.execute(
                "SELECT COUNT(*) AS count FROM knowledge_base_documents WHERE knowledge_base_id = ?",
                (kb_id,),
            ).fetchone()["count"]
            chunk_count = connection.execute(
                "SELECT COUNT(*) AS count FROM knowledge_base_chunks WHERE knowledge_base_id = ?",
                (kb_id,),
            ).fetchone()["count"]
            connection.execute(
                "DELETE FROM knowledge_base_chunks WHERE knowledge_base_id = ?",
                (kb_id,),
            )
            connection.execute(
                "DELETE FROM document_topics WHERE knowledge_base_id = ?",
                (kb_id,),
            )
            connection.execute(
                "DELETE FROM topic_nodes WHERE knowledge_base_id = ?",
                (kb_id,),
            )
            connection.execute(
                "DELETE FROM topic_edges WHERE knowledge_base_id = ?",
                (kb_id,),
            )
            connection.execute(
                "DELETE FROM knowledge_base_documents WHERE knowledge_base_id = ?",
                (kb_id,),
            )
            connection.execute(
                "UPDATE knowledge_bases SET status = ?, updated_at = ? WHERE id = ?",
                ("deleted", now, kb_id),
            )
        deleted = self._require_knowledge_base(kb_id)
        deleted["deleted_document_count"] = document_count
        deleted["deleted_chunk_count"] = chunk_count
        return deleted

    def upsert_document(
        self,
        knowledge_base_id: str,
        document_name: str,
        content_type: str,
        owner_id: str,
        chunk_count: int,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """创建或更新文档记录。"""
        current = self.get_document_by_external_id(knowledge_base_id, external_id)
        if current is None:
            return self._create_document(
                knowledge_base_id,
                document_name,
                content_type,
                owner_id,
                chunk_count,
                external_id,
            )
        else:
            return self._update_document(
                current["id"],
                document_name,
                content_type,
                chunk_count,
            )

    def enqueue_document(
        self,
        knowledge_base_id: str,
        document_name: str,
        content_type: str,
        owner_id: str,
        raw_content: str,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """创建或更新待后台解析的文档记录。"""
        current = self.get_document_by_external_id(knowledge_base_id, external_id)
        now = _utc_now()
        if current is None:
            record = {
                "id": f"doc_{uuid.uuid4().hex}",
                "knowledge_base_id": knowledge_base_id,
                "document_name": document_name,
                "content_type": content_type,
                "owner_id": owner_id,
                "external_id": external_id,
                "status": "queued",
                "chunk_count": 0,
                "raw_content": raw_content,
                "parse_status": "queued",
                "parse_attempts": 0,
                "parse_error": None,
                "queued_at": now,
                "processing_started_at": None,
                "parsed_at": None,
                "indexed_at": None,
                "created_at": now,
                "updated_at": now,
            }
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO knowledge_base_documents
                        (id, knowledge_base_id, document_name, content_type, owner_id, external_id, status,
                         chunk_count, raw_content, parse_status, parse_attempts, parse_error, queued_at,
                         processing_started_at, parsed_at, indexed_at, created_at, updated_at)
                    VALUES
                        (:id, :knowledge_base_id, :document_name, :content_type, :owner_id, :external_id, :status,
                         :chunk_count, :raw_content, :parse_status, :parse_attempts, :parse_error, :queued_at,
                         :processing_started_at, :parsed_at, :indexed_at, :created_at, :updated_at)
                    """,
                    record,
                )
            return record

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_base_documents
                SET document_name = ?, content_type = ?, owner_id = ?, raw_content = ?,
                    status = ?, parse_status = ?, chunk_count = ?, parse_error = ?,
                    queued_at = ?, processing_started_at = NULL, parsed_at = NULL, indexed_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    document_name,
                    content_type,
                    owner_id,
                    raw_content,
                    "queued",
                    "queued",
                    0,
                    None,
                    now,
                    now,
                    current["id"],
                ),
            )
            connection.execute(
                "DELETE FROM knowledge_base_chunks WHERE document_id = ?",
                (current["id"],),
            )
        return self.get_document(knowledge_base_id, current["id"])

    def claim_queued_documents(
        self,
        limit: int,
        knowledge_base_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """原子认领待解析文档，避免并发 worker 重复处理。"""
        if limit <= 0:
            return []
        now = _utc_now()
        with self._connect() as connection:
            where_clause = "parse_status = ?"
            params: list[Any] = ["queued"]
            if knowledge_base_id is not None:
                where_clause += " AND knowledge_base_id = ?"
                params.append(knowledge_base_id)
            params.append(limit)
            rows = connection.execute(
                f"""
                SELECT * FROM knowledge_base_documents
                WHERE {where_clause}
                ORDER BY queued_at ASC, created_at ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                result = connection.execute(
                    """
                    UPDATE knowledge_base_documents
                    SET parse_status = ?, status = ?, parse_attempts = parse_attempts + 1,
                        processing_started_at = ?, updated_at = ?
                    WHERE id = ? AND parse_status = ?
                    """,
                    ("processing", "processing", now, now, row["id"], "queued"),
                )
                if result.rowcount == 1:
                    claimed_row = connection.execute(
                        "SELECT * FROM knowledge_base_documents WHERE id = ?",
                        (row["id"],),
                    ).fetchone()
                    claimed.append(_row_to_dict(claimed_row))
        return claimed

    def mark_document_parsed(
        self,
        knowledge_base_id: str,
        document_id: str,
        chunk_count: int,
    ) -> dict[str, Any]:
        """标记文档 chunk 已解析入库。"""
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_base_documents
                SET parse_status = ?, status = ?, chunk_count = ?, parsed_at = ?, updated_at = ?
                WHERE knowledge_base_id = ? AND id = ?
                """,
                ("parsed", "parsed", chunk_count, now, now, knowledge_base_id, document_id),
            )
        return self.get_document(knowledge_base_id, document_id)

    def mark_document_indexed(self, knowledge_base_id: str, document_id: str) -> dict[str, Any]:
        """标记文档已完成检索索引。"""
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_base_documents
                SET parse_status = ?, status = ?, indexed_at = ?, updated_at = ?
                WHERE knowledge_base_id = ? AND id = ?
                """,
                ("indexed", "indexed", now, now, knowledge_base_id, document_id),
            )
        return self.get_document(knowledge_base_id, document_id)

    def mark_document_failed(
        self,
        knowledge_base_id: str,
        document_id: str,
        error: str,
        retryable: bool,
    ) -> dict[str, Any]:
        """标记解析失败，必要时重新入队。"""
        now = _utc_now()
        next_status = "queued" if retryable else "failed"
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_base_documents
                SET parse_status = ?, status = ?, parse_error = ?, queued_at = ?, updated_at = ?
                WHERE knowledge_base_id = ? AND id = ?
                """,
                (
                    next_status,
                    next_status,
                    error,
                    now if retryable else None,
                    now,
                    knowledge_base_id,
                    document_id,
                ),
            )
        return self.get_document(knowledge_base_id, document_id)

    def list_documents(self, knowledge_base_id: str) -> list[dict[str, Any]]:
        """按知识库列出文档。"""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    knowledge_base_id,
                    document_name,
                    content_type,
                    owner_id,
                    external_id,
                    status,
                    chunk_count,
                    parse_status,
                    parse_attempts,
                    parse_error,
                    queued_at,
                    processing_started_at,
                    parsed_at,
                    indexed_at,
                    created_at,
                    updated_at
                FROM knowledge_base_documents
                WHERE knowledge_base_id = ?
                ORDER BY updated_at DESC
                """,
                (knowledge_base_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_document(self, knowledge_base_id: str, document_id: str) -> dict[str, Any] | None:
        """按知识库和文档 ID 获取文档。"""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM knowledge_base_documents
                WHERE knowledge_base_id = ? AND id = ?
                """,
                (knowledge_base_id, document_id),
            ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def get_document_by_external_id(
        self,
        knowledge_base_id: str,
        external_id: str | None,
    ) -> dict[str, Any] | None:
        """按 external_id 获取文档，缺省 external_id 时不匹配。"""
        if external_id is None:
            return None
        else:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM knowledge_base_documents
                    WHERE knowledge_base_id = ? AND external_id = ?
                    """,
                    (knowledge_base_id, external_id),
                ).fetchone()
            return _row_to_dict(row) if row is not None else None

    def replace_document_chunks(
        self,
        knowledge_base_id: str,
        document_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """批量替换文档 chunk。"""
        now = _utc_now()
        records = [
            {
                "id": f"chunk_{uuid.uuid4().hex}",
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "chunk_index": chunk["chunk_index"],
                "title": chunk.get("title", ""),
                "content": chunk["content"],
                "indexed_content": chunk.get("indexed_content") or chunk["content"],
                "token_count": len(chunk["content"]),
                "created_at": now,
            }
            for chunk in chunks
        ]
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM knowledge_base_chunks WHERE document_id = ?",
                (document_id,),
            )
            connection.executemany(
                """
                INSERT INTO knowledge_base_chunks
                    (id, knowledge_base_id, document_id, chunk_index, title, content, indexed_content, token_count, created_at)
                VALUES
                    (:id, :knowledge_base_id, :document_id, :chunk_index, :title, :content, :indexed_content, :token_count, :created_at)
                """,
                records,
            )
        return records

    def list_document_chunks(self, knowledge_base_id: str, document_id: str) -> list[dict[str, Any]]:
        """列出文档 chunk。"""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM knowledge_base_chunks
                WHERE knowledge_base_id = ? AND document_id = ?
                ORDER BY chunk_index ASC
                """,
                (knowledge_base_id, document_id),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def search_chunks(self, knowledge_base_ids: list[str]) -> list[dict[str, Any]]:
        """按知识库批量读取可检索 chunk。"""
        if not knowledge_base_ids:
            return []
        else:
            placeholders = ",".join("?" for _ in knowledge_base_ids)
            query = f"""
                SELECT c.*, d.document_name
                FROM knowledge_base_chunks c
                JOIN knowledge_base_documents d ON d.id = c.document_id
                WHERE c.knowledge_base_id IN ({placeholders})
                ORDER BY c.created_at DESC, c.chunk_index ASC
            """
            with self._connect() as connection:
                rows = connection.execute(query, knowledge_base_ids).fetchall()
            return [_row_to_dict(row) for row in rows]

    def _require_knowledge_base(self, kb_id: str) -> dict[str, Any]:
        """读取知识库，不存在时抛出 ValueError。"""
        record = self.get_knowledge_base(kb_id)
        if record is not None:
            return record
        raise ValueError("知识库不存在")

    def _ensure_parent_dir(self) -> None:
        """确保 SQLite 文件父目录存在。"""
        parent = Path(self.db_path).expanduser().resolve().parent
        parent.mkdir(parents=True, exist_ok=True)

    def _initialize_schema(self) -> None:
        """初始化知识库表结构。"""
        with self._connect() as connection:
            connection.execute(CREATE_KB_TABLE)
            connection.execute(CREATE_DOCUMENT_TABLE)
            connection.execute(CREATE_CHUNK_TABLE)
            connection.execute(CREATE_KB_SETTINGS_TABLE)
            connection.execute(CREATE_SYNONYM_GROUP_TABLE)
            connection.execute(CREATE_DOCUMENT_TOPIC_TABLE)
            connection.execute(CREATE_TOPIC_NODE_TABLE)
            connection.execute(CREATE_TOPIC_EDGE_TABLE)
            _ensure_column(connection, "knowledge_base_documents", "raw_content", "TEXT")
            _ensure_column(connection, "knowledge_base_documents", "parse_status", "TEXT NOT NULL DEFAULT 'queued'")
            _ensure_column(connection, "knowledge_base_documents", "parse_attempts", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(connection, "knowledge_base_documents", "parse_error", "TEXT")
            _ensure_column(connection, "knowledge_base_documents", "queued_at", "TEXT")
            _ensure_column(connection, "knowledge_base_documents", "processing_started_at", "TEXT")
            _ensure_column(connection, "knowledge_base_documents", "parsed_at", "TEXT")
            _ensure_column(connection, "knowledge_base_documents", "indexed_at", "TEXT")
            _ensure_column(connection, "knowledge_base_chunks", "indexed_content", "TEXT")

    def _rebuild_topic_index(self, connection: sqlite3.Connection, knowledge_base_id: str) -> None:
        """基于文档主题事实表重建主题节点和边，避免增量计数漂移。"""
        rows = connection.execute(
            "SELECT * FROM document_topics WHERE knowledge_base_id = ?",
            (knowledge_base_id,),
        ).fetchall()
        node_map: dict[str, dict[str, Any]] = {}
        edge_counts: dict[tuple[str, str, str], int] = {}
        for row in rows:
            record = _document_topic_row_to_dict(row)
            primary_topic = record["primary_topic"]
            topic_path = record["topic_path"] or [*record["parent_topics"], primary_topic]
            all_topics = [*topic_path, *record["sibling_topics"], *record["child_topics"]]
            for topic in _normalize_terms(all_topics):
                normalized = _normalize_topic(topic)
                node = node_map.setdefault(
                    normalized,
                    {
                        "knowledge_base_id": knowledge_base_id,
                        "canonical_topic": topic,
                        "normalized_topic": normalized,
                        "parent_topic": _parent_for_topic(topic, topic_path),
                        "aliases": [],
                        "doc_ids": set(),
                    },
                )
                if topic == primary_topic:
                    node["aliases"] = _normalize_terms([*node["aliases"], *record["topic_aliases"]])
                node["doc_ids"].add(record["document_id"])
            for parent, child in zip(topic_path, topic_path[1:]):
                edge_counts[(parent, child, "parent_child")] = edge_counts.get((parent, child, "parent_child"), 0) + 1
            for parent in record["parent_topics"]:
                edge_counts[(parent, primary_topic, "parent")] = edge_counts.get((parent, primary_topic, "parent"), 0) + 1
            for child in record["child_topics"]:
                edge_counts[(primary_topic, child, "child")] = edge_counts.get((primary_topic, child, "child"), 0) + 1
            for sibling in record["sibling_topics"]:
                edge_counts[(primary_topic, sibling, "sibling")] = edge_counts.get((primary_topic, sibling, "sibling"), 0) + 1
        now = _utc_now()
        connection.execute("DELETE FROM topic_nodes WHERE knowledge_base_id = ?", (knowledge_base_id,))
        connection.execute("DELETE FROM topic_edges WHERE knowledge_base_id = ?", (knowledge_base_id,))
        connection.executemany(
            """
            INSERT INTO topic_nodes
                (knowledge_base_id, canonical_topic, normalized_topic, parent_topic, aliases_json, doc_count, updated_at)
            VALUES
                (:knowledge_base_id, :canonical_topic, :normalized_topic, :parent_topic, :aliases_json, :doc_count, :updated_at)
            """,
            [
                {
                    "knowledge_base_id": node["knowledge_base_id"],
                    "canonical_topic": node["canonical_topic"],
                    "normalized_topic": node["normalized_topic"],
                    "parent_topic": node["parent_topic"],
                    "aliases_json": json.dumps(node["aliases"], ensure_ascii=False),
                    "doc_count": len(node["doc_ids"]),
                    "updated_at": now,
                }
                for node in node_map.values()
            ],
        )
        connection.executemany(
            """
            INSERT INTO topic_edges
                (knowledge_base_id, parent_topic, child_topic, edge_type, doc_count, updated_at)
            VALUES
                (:knowledge_base_id, :parent_topic, :child_topic, :edge_type, :doc_count, :updated_at)
            """,
            [
                {
                    "knowledge_base_id": knowledge_base_id,
                    "parent_topic": parent,
                    "child_topic": child,
                    "edge_type": edge_type,
                    "doc_count": count,
                    "updated_at": now,
                }
                for (parent, child, edge_type), count in edge_counts.items()
            ],
        )

    def _create_default_settings(
        self,
        connection: sqlite3.Connection,
        knowledge_base_id: str,
        now: str,
    ) -> None:
        """为知识库创建默认分块与检索设置。"""
        connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_base_settings
                (knowledge_base_id, semantic_chunking_enabled, chunk_size, overlap,
                 top_k_default, max_heading_depth, llm_planning_timeout_ms, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (knowledge_base_id, 0, 1000, 150, 5, 3, 8000, now),
        )

    def _ensure_default_settings(
        self,
        connection: sqlite3.Connection,
        knowledge_base_id: str,
    ) -> None:
        """补齐历史知识库缺失的默认设置。"""
        self._create_default_settings(connection, knowledge_base_id, _utc_now())

    def _connect(self) -> sqlite3.Connection:
        """创建启用 Row 工厂的 SQLite 连接。"""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_document(
        self,
        knowledge_base_id: str,
        document_name: str,
        content_type: str,
        owner_id: str,
        chunk_count: int,
        external_id: str | None,
    ) -> dict[str, Any]:
        """创建文档记录。"""
        now = _utc_now()
        record = {
            "id": f"doc_{uuid.uuid4().hex}",
            "knowledge_base_id": knowledge_base_id,
            "document_name": document_name,
            "content_type": content_type,
            "owner_id": owner_id,
            "external_id": external_id,
            "status": "ready",
            "chunk_count": chunk_count,
            "raw_content": None,
            "parse_status": "indexed",
            "parse_attempts": 0,
            "parse_error": None,
            "queued_at": now,
            "processing_started_at": now,
            "parsed_at": now,
            "indexed_at": now,
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_base_documents
                    (id, knowledge_base_id, document_name, content_type, owner_id, external_id, status,
                     chunk_count, raw_content, parse_status, parse_attempts, parse_error, queued_at,
                     processing_started_at, parsed_at, indexed_at, created_at, updated_at)
                VALUES
                    (:id, :knowledge_base_id, :document_name, :content_type, :owner_id, :external_id, :status,
                     :chunk_count, :raw_content, :parse_status, :parse_attempts, :parse_error, :queued_at,
                     :processing_started_at, :parsed_at, :indexed_at, :created_at, :updated_at)
                """,
                record,
            )
        return record

    def _update_document(
        self,
        document_id: str,
        document_name: str,
        content_type: str,
        chunk_count: int,
    ) -> dict[str, Any]:
        """更新文档记录。"""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_base_documents
                SET document_name = ?, content_type = ?, chunk_count = ?, status = ?,
                    parse_status = ?, parsed_at = ?, indexed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (document_name, content_type, chunk_count, "ready", "indexed", _utc_now(), _utc_now(), _utc_now(), document_id),
            )
            row = connection.execute(
                "SELECT * FROM knowledge_base_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        return _row_to_dict(row)


def _utc_now() -> str:
    """返回 ISO 格式 UTC 时间。"""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """将 SQLite Row 转为普通字典。"""
    return dict(row)


def _settings_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """将知识库设置 Row 转为外部字典。"""
    record = dict(row)
    record["semantic_chunking_enabled"] = bool(record["semantic_chunking_enabled"])
    return record


def _synonym_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """将同义词组 Row 转为外部字典。"""
    record = dict(row)
    record["terms"] = json.loads(record.pop("terms_json"))
    record["enabled"] = bool(record["enabled"])
    return record


def _document_topic_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """将文档主题 Row 转为外部字典。"""
    record = dict(row)
    for field in [
        "parent_topics",
        "sibling_topics",
        "child_topics",
        "topic_aliases",
        "topic_path",
        "evidence",
    ]:
        json_field = f"{field}_json"
        record[field] = json.loads(record.pop(json_field, "[]") or "[]")
    return record


def _topic_node_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """将主题节点 Row 转为外部字典。"""
    record = dict(row)
    record["aliases"] = json.loads(record.pop("aliases_json", "[]") or "[]")
    return record


def _normalize_terms(terms: list[str]) -> list[str]:
    """裁剪并去重同义词条。"""
    normalized_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in terms:
        normalized = str(term).strip()
        if normalized and normalized not in seen_terms:
            normalized_terms.append(normalized)
            seen_terms.add(normalized)
        else:
            pass
    return normalized_terms


def _json_list(value: list[str] | None) -> str:
    """规范化字符串列表并序列化为 JSON。"""
    return json.dumps(_normalize_terms(value or []), ensure_ascii=False)


def _normalize_topic(topic: str) -> str:
    """主题归一化，用于读路径确定性匹配。"""
    return "".join(str(topic).strip().lower().split())


def _parent_for_topic(topic: str, topic_path: list[str]) -> str | None:
    """从主题路径中读取某主题的直接父主题。"""
    for index, item in enumerate(topic_path):
        if item == topic and index > 0:
            return topic_path[index - 1]
    return None


def _document_topic_matches(record: dict[str, Any], normalized_topic: str, relation_type: str) -> bool:
    """判断文档主题是否匹配指定关系。"""
    if relation_type == "same":
        candidates = [record["primary_topic"], *record["topic_aliases"]]
    elif relation_type == "parent":
        candidates = [*record["parent_topics"], *record["topic_path"][:-1]]
    elif relation_type == "child":
        candidates = record["child_topics"]
    elif relation_type == "sibling":
        candidates = record["sibling_topics"]
    else:
        candidates = [
            record["primary_topic"],
            *record["parent_topics"],
            *record["sibling_topics"],
            *record["child_topics"],
            *record["topic_aliases"],
            *record["topic_path"],
        ]
    return any(_normalize_topic(candidate) == normalized_topic for candidate in candidates)


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    """为已有 SQLite 表补充新增字段。"""
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )
