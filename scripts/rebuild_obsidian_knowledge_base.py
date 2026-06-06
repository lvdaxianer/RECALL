#!/usr/bin/env python
"""
清空并重建 Obsidian 知识库。

Author: lvdaxianerplus
Date: 2026-06-05
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Config

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}
TERMINAL_PARSE_STATUSES = {"indexed", "failed"}


@dataclass(frozen=True)
class ObsidianDocument:
    """待录入的 Obsidian 文档。"""

    path: Path
    relative_path: str
    content: str


def collect_obsidian_documents(root: Path) -> list[ObsidianDocument]:
    """递归收集每个非空可解析文档。"""
    documents: list[ObsidianDocument] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            continue
        documents.append(
            ObsidianDocument(
                path=path,
                relative_path=path.relative_to(root).as_posix(),
                content=content,
            )
        )
    return documents


async def clear_and_rebuild(
    base_url: str,
    source_dir: Path,
    owner_id: str,
    kb_name: str,
    kb_description: str,
    wait_timeout_seconds: float = 600,
    fast_reset_db_path: Path | None = None,
) -> dict[str, Any]:
    """清空现有知识库并全量录入 Obsidian 文档。"""
    documents = collect_obsidian_documents(source_dir)
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        if fast_reset_db_path is not None:
            fast_local_reset(fast_reset_db_path)
        else:
            existing = await client.get("/api/v1/kb", params={"owner_id": owner_id})
            existing.raise_for_status()
            for kb in existing.json().get("data", []):
                if kb.get("status") != "deleted":
                    deleted = await client.delete(f"/api/v1/kb/{kb['id']}", params={"owner_id": owner_id})
                    deleted.raise_for_status()

        created = await client.post(
            "/api/v1/kb",
            json={"name": kb_name, "description": kb_description, "owner_id": owner_id},
        )
        created.raise_for_status()
        kb = created.json()["data"]

        for document in documents:
            response = await client.post(
                f"/api/v1/kb/{kb['id']}/documents",
                json={
                    "name": document.relative_path,
                    "content": document.content,
                    "content_type": "text/markdown",
                    "owner_id": owner_id,
                    "external_id": document.relative_path,
                },
            )
            response.raise_for_status()

        published = await client.post(f"/api/v1/kb/{kb['id']}/publish", json={"owner_id": owner_id})
        published.raise_for_status()
        stats = await wait_for_documents_done(client, kb["id"], timeout_seconds=wait_timeout_seconds)
    return {
        "knowledge_base_id": kb["id"],
        "document_count": len(documents),
        "parse_stats": stats,
    }


def fast_local_reset(db_path: Path) -> None:
    """直接清空知识库 SQLite 表，用于大规模评测重建。"""
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as connection:
        for table_name in [
            "knowledge_base_chunks",
            "knowledge_base_documents",
            "knowledge_base_settings",
            "synonym_groups",
            "retrieval_answer_cache",
            "retrieval_answer_feedback",
            "retrieval_answer_cache_bypass",
            "retrieval_answer_cache_request",
            "knowledge_bases",
        ]:
            if _table_exists(connection, table_name):
                connection.execute(f"DELETE FROM {table_name}")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """判断 SQLite 表是否存在。"""
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


async def wait_for_documents_done(
    client: httpx.AsyncClient,
    knowledge_base_id: str,
    timeout_seconds: float,
) -> dict[str, int]:
    """等待文档全部进入 indexed/failed。"""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        payload = await get_json_with_retries(client, f"/api/v1/kb/{knowledge_base_id}/documents")
        documents = payload.get("data", [])
        stats: dict[str, int] = {}
        for document in documents:
            status = document.get("parse_status", document.get("status", "unknown"))
            stats[status] = stats.get(status, 0) + 1
        unfinished = [
            document
            for document in documents
            if document.get("parse_status", document.get("status")) not in TERMINAL_PARSE_STATUSES
        ]
        if not unfinished:
            return stats
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"文档解析未完成: {stats}")
        await asyncio.sleep(2)


async def get_json_with_retries(
    client: httpx.AsyncClient,
    url: str,
    attempts: int = 3,
    delay_seconds: float = 1.0,
) -> dict[str, Any]:
    """GET JSON，遇到瞬时网络错误时重试。"""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, httpx.ReadError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(delay_seconds)
    raise RuntimeError("unreachable") from last_error


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--source-dir", default="/Users/lvdaxianer/workspace/my/project/obsidian.note")
    parser.add_argument("--owner-id", default="default")
    parser.add_argument("--kb-name", default="Obsidian Note 全量重建")
    parser.add_argument("--kb-description", default="从 obsidian.note 全量重新录入的知识库")
    parser.add_argument("--wait-timeout-seconds", type=float, default=600)
    parser.add_argument("--fast-local-reset", action="store_true")
    parser.add_argument("--db-path", default=Config.KNOWLEDGE_BASE_DB_PATH)
    return parser


async def async_main() -> dict[str, Any]:
    """异步主入口。"""
    args = build_parser().parse_args()
    return await clear_and_rebuild(
        base_url=args.base_url,
        source_dir=Path(args.source_dir),
        owner_id=args.owner_id,
        kb_name=args.kb_name,
        kb_description=args.kb_description,
        wait_timeout_seconds=args.wait_timeout_seconds,
        fast_reset_db_path=Path(args.db_path) if args.fast_local_reset else None,
    )


def main() -> None:
    """CLI 入口。"""
    print(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
