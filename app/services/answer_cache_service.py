"""
Retrieval answer cache service.

Caches trusted answers for normalized questions within a published knowledge-base revision.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.query_normalization import normalize_query_text
from app.services.query_normalization import normalize_query_variants
from app.services.synonym_service import SynonymService


CREATE_ANSWER_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS retrieval_answer_cache (
    cache_key TEXT PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    knowledge_base_ids TEXT NOT NULL,
    kb_revision TEXT NOT NULL,
    top_k INTEGER NOT NULL,
    prompt_version TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    request_id TEXT NOT NULL,
    trust_score INTEGER NOT NULL DEFAULT 0,
    hit_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_FEEDBACK_TABLE = """
CREATE TABLE IF NOT EXISTS retrieval_answer_feedback (
    id TEXT PRIMARY KEY,
    cache_key TEXT,
    request_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    vote TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

CREATE_BYPASS_TABLE = """
CREATE TABLE IF NOT EXISTS retrieval_answer_cache_bypass (
    cache_key TEXT PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

CREATE_REQUEST_TABLE = """
CREATE TABLE IF NOT EXISTS retrieval_answer_cache_request (
    request_id TEXT PRIMARY KEY,
    cache_key TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

PROMPT_VERSION = "retrieval-answer-v5"
DEFAULT_TTL_SECONDS = 3600
DISLIKE_BYPASS_SECONDS = 300


class AnswerCacheService:
    """SQLite-backed answer cache with feedback governance."""

    def __init__(
        self,
        repository: KnowledgeBaseRepository,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        bypass_seconds: int = DISLIKE_BYPASS_SECONDS,
        prompt_version: str = PROMPT_VERSION,
    ):
        """Initialize cache service against the knowledge-base repository database."""
        self.repository = repository
        self.ttl_seconds = ttl_seconds
        self.bypass_seconds = bypass_seconds
        self.prompt_version = prompt_version
        self._initialize_schema()

    def get(
        self,
        input_text: str,
        knowledge_base_ids: list[str],
        top_k: int,
        temperature: float = 0.2,
    ) -> dict[str, Any] | None:
        """Return a cached answer if present, unexpired and not bypassed."""
        key_variants = self.build_cache_key_variants(
            input_text,
            knowledge_base_ids,
            top_k,
            temperature=temperature,
        )
        cache_keys = [item[0] for item in key_variants]
        if any(self._is_key_bypassed(cache_key) for cache_key in cache_keys):
            return None
        now = _utc_now()
        placeholders = ",".join("?" for _ in cache_keys)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT * FROM retrieval_answer_cache
                WHERE cache_key IN ({placeholders}) AND expires_at > ?
                ORDER BY hit_count DESC, updated_at DESC
                LIMIT 1
                """,
                [*cache_keys, now],
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE retrieval_answer_cache
                SET hit_count = hit_count + 1, updated_at = ?
                WHERE cache_key = ?
                """,
                (now, row["cache_key"]),
            )
            updated = connection.execute(
                "SELECT * FROM retrieval_answer_cache WHERE cache_key = ?",
                (row["cache_key"],),
            ).fetchone()
        matched = next(
            (item for item in key_variants if item[0] == updated["cache_key"]),
            (updated["cache_key"], updated["normalized_query"], updated["kb_revision"]),
        )
        return self._row_to_cache(updated, normalized_query=matched[1], kb_revision=matched[2])

    def set(
        self,
        input_text: str,
        knowledge_base_ids: list[str],
        top_k: int,
        answer: str,
        citations: list[dict[str, Any]],
        trace: list[dict[str, Any]],
        request_id: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Store a successful answer for later reuse."""
        cache_key, normalized_query, kb_revision = self.build_cache_key(
            input_text,
            knowledge_base_ids,
            top_k,
            temperature=temperature,
        )
        now = _utc_now()
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).isoformat()
        record = {
            "cache_key": cache_key,
            "normalized_query": normalized_query,
            "knowledge_base_ids": json.dumps(sorted(knowledge_base_ids), ensure_ascii=False),
            "kb_revision": kb_revision,
            "top_k": top_k,
            "prompt_version": self.prompt_version,
            "answer": answer,
            "citations_json": json.dumps(citations, ensure_ascii=False),
            "trace_json": json.dumps(trace, ensure_ascii=False),
            "request_id": request_id,
            "trust_score": 0,
            "hit_count": 0,
            "expires_at": expires_at,
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_answer_cache (
                    cache_key, normalized_query, knowledge_base_ids, kb_revision, top_k, prompt_version,
                    answer, citations_json, trace_json, request_id, trust_score, hit_count,
                    expires_at, created_at, updated_at
                )
                VALUES (
                    :cache_key, :normalized_query, :knowledge_base_ids, :kb_revision, :top_k, :prompt_version,
                    :answer, :citations_json, :trace_json, :request_id, :trust_score, :hit_count,
                    :expires_at, :created_at, :updated_at
                )
                ON CONFLICT(cache_key) DO UPDATE SET
                    answer = excluded.answer,
                    citations_json = excluded.citations_json,
                    trace_json = excluded.trace_json,
                    request_id = excluded.request_id,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                record,
            )
            row = connection.execute(
                "SELECT * FROM retrieval_answer_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            self._bind_request_id(connection, cache_key, request_id)
        return self._row_to_cache(row, normalized_query=normalized_query, kb_revision=kb_revision)

    def record_feedback(self, request_id: str, vote: str, user_id: str = "default") -> dict[str, Any]:
        """Record user feedback and update cache trust or invalidation state."""
        if vote not in {"like", "dislike"}:
            raise ValueError("feedback vote must be like or dislike")
        with self._connect() as connection:
            row = self._find_cache_by_request_id(connection, request_id)
            cache_key = row["cache_key"] if row else None
            connection.execute(
                """
                INSERT INTO retrieval_answer_feedback (id, cache_key, request_id, user_id, vote, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f"fb_{uuid.uuid4().hex}", cache_key, request_id, user_id, vote, _utc_now()),
            )
            if row is None:
                return {"request_id": request_id, "vote": vote, "found": False, "deleted": False}
            if vote == "like":
                connection.execute(
                    """
                    UPDATE retrieval_answer_cache
                    SET trust_score = trust_score + 1, updated_at = ?
                    WHERE cache_key = ?
                    """,
                    (_utc_now(), cache_key),
                )
                updated = connection.execute(
                    "SELECT trust_score FROM retrieval_answer_cache WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
                return {
                    "request_id": request_id,
                    "vote": vote,
                    "found": True,
                    "deleted": False,
                    "trust_score": updated["trust_score"],
                }
            self._bypass_key(connection, row["cache_key"], row["normalized_query"])
            connection.execute("DELETE FROM retrieval_answer_cache WHERE cache_key = ?", (row["cache_key"],))
            connection.execute("DELETE FROM retrieval_answer_cache_request WHERE cache_key = ?", (row["cache_key"],))
            return {"request_id": request_id, "vote": vote, "found": True, "deleted": True}

    def list_records(self, limit: int = 100) -> list[dict[str, Any]]:
        """List cached answers for the management console."""
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("DELETE FROM retrieval_answer_cache WHERE expires_at <= ?", (now,))
            rows = connection.execute(
                """
                SELECT * FROM retrieval_answer_cache
                ORDER BY trust_score DESC, hit_count DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_summary(row) for row in rows]

    def delete(self, cache_key: str) -> dict[str, Any]:
        """Delete a cached answer by key."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM retrieval_answer_cache WHERE cache_key = ?",
                (cache_key,),
            )
            connection.execute("DELETE FROM retrieval_answer_cache_request WHERE cache_key = ?", (cache_key,))
        return {"cache_key": cache_key, "deleted": cursor.rowcount > 0}

    def bind_request_id(self, cache_key: str, request_id: str) -> None:
        """Bind a streamed request id to an existing cache row for later feedback."""
        with self._connect() as connection:
            self._bind_request_id(connection, cache_key, request_id)

    def is_bypassed(
        self,
        input_text: str,
        knowledge_base_ids: list[str],
        top_k: int,
        temperature: float = 0.2,
    ) -> bool:
        """Return whether a normalized cache key is in the dislike bypass window."""
        cache_key, _, _ = self.build_cache_key(
            input_text,
            knowledge_base_ids,
            top_k,
            temperature=temperature,
        )
        return self._is_key_bypassed(cache_key)

    def build_cache_key(
        self,
        input_text: str,
        knowledge_base_ids: list[str],
        top_k: int,
        temperature: float = 0.2,
    ) -> tuple[str, str, str]:
        """Build a stable key from normalized query, KB scope, revision, top_k and prompt version."""
        synonym_query = SynonymService(self.repository).normalize_query(input_text, knowledge_base_ids)
        normalized_query = normalize_answer_query(synonym_query)
        kb_revision = self._knowledge_base_revision(knowledge_base_ids)
        return (
            self._hash_cache_payload(normalized_query, knowledge_base_ids, kb_revision, top_k, temperature),
            normalized_query,
            kb_revision,
        )

    def build_cache_key_variants(
        self,
        input_text: str,
        knowledge_base_ids: list[str],
        top_k: int,
        temperature: float = 0.2,
    ) -> list[tuple[str, str, str]]:
        """构建基础、硬编码和同义词归一化对应的 cache key。"""
        synonym_query = SynonymService(self.repository).normalize_query(input_text, knowledge_base_ids)
        kb_revision = self._knowledge_base_revision(knowledge_base_ids)
        variants = []
        for variant in normalize_query_variants(input_text, synonym_query=synonym_query):
            normalized_variant = normalize_answer_query(variant)
            if normalized_variant and normalized_variant not in variants:
                variants.append(normalized_variant)
        return [
            (
                self._hash_cache_payload(query, knowledge_base_ids, kb_revision, top_k, temperature),
                query,
                kb_revision,
            )
            for query in variants
        ]

    def _hash_cache_payload(
        self,
        normalized_query: str,
        knowledge_base_ids: list[str],
        kb_revision: str,
        top_k: int,
        temperature: float,
    ) -> str:
        """生成答案缓存 key hash。"""
        payload = {
            "normalized_query": normalized_query,
            "knowledge_base_ids": sorted(knowledge_base_ids),
            "kb_revision": kb_revision,
            "top_k": top_k,
            "temperature": round(float(temperature), 2),
            "prompt_version": self.prompt_version,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        ).hexdigest()

    def _knowledge_base_revision(self, knowledge_base_ids: list[str]) -> str:
        records = self.repository.get_knowledge_bases_by_ids(sorted(knowledge_base_ids))
        parts = [f"{record['id']}:{record.get('updated_at', '')}" for record in records]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def _bypass_key(self, connection: sqlite3.Connection, cache_key: str, normalized_query: str) -> None:
        now = _utc_now()
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.bypass_seconds)).isoformat()
        connection.execute(
            """
            INSERT INTO retrieval_answer_cache_bypass (cache_key, normalized_query, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET expires_at = excluded.expires_at
            """,
            (cache_key, normalized_query, expires_at, now),
        )

    def _bind_request_id(self, connection: sqlite3.Connection, cache_key: str, request_id: str) -> None:
        connection.execute(
            """
            INSERT INTO retrieval_answer_cache_request (request_id, cache_key, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET cache_key = excluded.cache_key
            """,
            (request_id, cache_key, _utc_now()),
        )

    def _find_cache_by_request_id(self, connection: sqlite3.Connection, request_id: str) -> sqlite3.Row | None:
        row = connection.execute(
            """
            SELECT cache.*
            FROM retrieval_answer_cache AS cache
            JOIN retrieval_answer_cache_request AS request ON request.cache_key = cache.cache_key
            WHERE request.request_id = ?
            ORDER BY cache.updated_at DESC
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()
        if row is not None:
            return row
        return connection.execute(
            "SELECT * FROM retrieval_answer_cache WHERE request_id = ? ORDER BY updated_at DESC LIMIT 1",
            (request_id,),
        ).fetchone()

    def _is_key_bypassed(self, cache_key: str) -> bool:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("DELETE FROM retrieval_answer_cache_bypass WHERE expires_at <= ?", (now,))
            row = connection.execute(
                "SELECT cache_key FROM retrieval_answer_cache_bypass WHERE cache_key = ? AND expires_at > ?",
                (cache_key, now),
            ).fetchone()
        return row is not None

    def _row_to_cache(
        self,
        row: sqlite3.Row,
        normalized_query: str | None = None,
        kb_revision: str | None = None,
    ) -> dict[str, Any]:
        data = dict(row)
        data["normalized_query"] = normalized_query or data["normalized_query"]
        data["kb_revision"] = kb_revision or data["kb_revision"]
        data["knowledge_base_ids"] = json.loads(data["knowledge_base_ids"])
        data["citations"] = json.loads(data.pop("citations_json"))
        data["trace"] = json.loads(data.pop("trace_json"))
        return data

    def _row_to_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        citations = json.loads(data["citations_json"])
        answer = data["answer"]
        return {
            "cache_key": data["cache_key"],
            "normalized_query": data["normalized_query"],
            "knowledge_base_ids": json.loads(data["knowledge_base_ids"]),
            "top_k": data["top_k"],
            "prompt_version": data["prompt_version"],
            "answer_preview": answer[:160],
            "citation_count": len(citations),
            "request_id": data["request_id"],
            "trust_score": data["trust_score"],
            "hit_count": data["hit_count"],
            "expires_at": data["expires_at"],
            "updated_at": data["updated_at"],
        }

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(CREATE_ANSWER_CACHE_TABLE)
            connection.execute(CREATE_FEEDBACK_TABLE)
            connection.execute(CREATE_BYPASS_TABLE)
            connection.execute(CREATE_REQUEST_TABLE)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.repository.db_path)
        connection.row_factory = sqlite3.Row
        return connection


def normalize_answer_query(query: str) -> str:
    """Normalize conversational question variants for answer-cache reuse."""
    normalized = normalize_query_text(query)
    normalized = re.sub(r"[?？!！。,.，、]+", " ", normalized)
    normalized = re.sub(r"(?i)\bjmm\s+的(?=[\u4e00-\u9fff]|\s)", "jmm ", normalized)
    normalized = re.sub(r"(?<=[\u4e00-\u9fff])作用$", " 作用", normalized)
    normalized = re.sub(r"\b(呢|吗|么|啊|呀|吧|的)\b", " ", normalized)
    normalized = re.sub(r"(?<=[\u4e00-\u9fff])(呢|吗|么|啊|呀|吧)$", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
