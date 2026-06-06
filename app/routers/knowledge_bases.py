"""
知识库管理路由

提供知识库创建、列表、详情、更新和软删除 API。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

from app.config import Config
from app.models.knowledge_base_schemas import KnowledgeBaseCreateRequest
from app.models.knowledge_base_schemas import KnowledgeBasePublishRequest
from app.models.knowledge_base_schemas import KnowledgeBaseSettings
from app.models.knowledge_base_schemas import KnowledgeBaseSettingsUpdateRequest
from app.models.knowledge_base_schemas import KnowledgeBaseUpdateRequest
from app.models.schemas import APIResponse
from app.services.document_ingest_service import DocumentIngestService
from app.services.document_parse_worker import DocumentParseWorker
from app.services.embedding_service import EmbeddingService
from app.services.es_service import get_es_service
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.markdown_chunk_service import MarkdownChunkService
from app.services.milvus_service import MilvusService


router = APIRouter(prefix="/api/v1/kb", tags=["KnowledgeBase"])
KNOWLEDGE_BASE_DB_PATH = Config.KNOWLEDGE_BASE_DB_PATH or str(Path("data") / "knowledge_base.sqlite")


@router.post("", response_model=APIResponse)
async def create_knowledge_base(request: KnowledgeBaseCreateRequest):
    """
    创建知识库

    @param request - 知识库创建请求
    @returns 创建后的知识库
    """
    service = _get_knowledge_base_service()
    created = service.create_knowledge_base(
        name=request.name,
        description=request.description,
        owner_id=request.owner_id,
    )
    return APIResponse(code=200, message="success", data=created)


@router.get("", response_model=APIResponse)
async def list_knowledge_bases(owner_id: str | None = Query(default=None)):
    """
    列出知识库

    @param owner_id - 可选所有者 ID
    @returns 知识库列表
    """
    service = _get_knowledge_base_service()
    return APIResponse(
        code=200,
        message="success",
        data=service.list_knowledge_bases(owner_id=owner_id),
    )


@router.get("/{kb_id}", response_model=APIResponse)
async def get_knowledge_base(kb_id: str):
    """
    获取知识库详情

    @param kb_id - 知识库 ID
    @returns 知识库详情
    """
    try:
        data = _get_knowledge_base_service().get_knowledge_base(kb_id)
        return APIResponse(code=200, message="success", data=data)
    except ValueError as exc:
        raise _not_found(str(exc)) from exc


@router.get("/{kb_id}/settings", response_model=APIResponse)
async def get_knowledge_base_settings(kb_id: str):
    """
    获取知识库分块与检索设置

    @param kb_id - 知识库 ID
    @returns 知识库设置
    """
    try:
        data = _get_repository().get_knowledge_base_settings(kb_id)
        return APIResponse(code=200, message="success", data=data)
    except ValueError as exc:
        raise _not_found(str(exc)) from exc


@router.patch("/{kb_id}/settings", response_model=APIResponse)
async def update_knowledge_base_settings(
    kb_id: str,
    request: KnowledgeBaseSettingsUpdateRequest,
):
    """
    更新知识库分块与检索设置

    @param kb_id - 知识库 ID
    @param request - 设置更新请求
    @returns 更新后的知识库设置
    """
    try:
        repository = _get_repository()
        current = repository.get_knowledge_base_settings(kb_id)
        updates = request.model_dump(exclude_none=True)
        KnowledgeBaseSettings(**{**current, **updates})
        data = repository.update_knowledge_base_settings(kb_id, updates)
        return APIResponse(code=200, message="success", data=data)
    except ValueError as exc:
        if "知识库不存在" in str(exc):
            raise _not_found(str(exc)) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": 422, "message": str(exc)},
        ) from exc


@router.patch("/{kb_id}", response_model=APIResponse)
async def update_knowledge_base(kb_id: str, request: KnowledgeBaseUpdateRequest):
    """
    更新知识库

    @param kb_id - 知识库 ID
    @param request - 知识库更新请求
    @returns 更新后的知识库
    """
    if request.owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "owner_id 必填"},
        )
    else:
        try:
            data = _get_knowledge_base_service().update_knowledge_base(
                kb_id=kb_id,
                owner_id=request.owner_id,
                name=request.name,
                description=request.description,
            )
            return APIResponse(code=200, message="success", data=data)
        except PermissionError as exc:
            raise _forbidden(str(exc)) from exc
        except ValueError as exc:
            raise _not_found(str(exc)) from exc


@router.post("/{kb_id}/publish", response_model=APIResponse)
async def publish_knowledge_base(kb_id: str, request: KnowledgeBasePublishRequest):
    """
    发布知识库

    @param kb_id - 知识库 ID
    @param request - 发布请求
    @returns 发布后的知识库
    """
    try:
        data = _get_knowledge_base_service().publish_knowledge_base(
            kb_id=kb_id,
            owner_id=request.owner_id,
        )
        return APIResponse(code=200, message="success", data=data)
    except PermissionError as exc:
        raise _forbidden(str(exc)) from exc
    except ValueError as exc:
        raise _not_found(str(exc)) from exc


@router.delete("/{kb_id}", response_model=APIResponse)
async def delete_knowledge_base(kb_id: str, owner_id: str = Query(...)):
    """
    删除知识库

    @param kb_id - 知识库 ID
    @param owner_id - 所有者 ID
    @returns 删除后的知识库
    """
    try:
        repository = _get_repository()
        chunk_ids = [chunk["id"] for chunk in repository.search_chunks([kb_id])]
        data = KnowledgeBaseService(repository).delete_knowledge_base(
            kb_id=kb_id,
            owner_id=owner_id,
        )
        data["external_cleanup"] = await _cleanup_external_indexes(chunk_ids)
        return APIResponse(code=200, message="success", data=data)
    except PermissionError as exc:
        raise _forbidden(str(exc)) from exc
    except ValueError as exc:
        raise _not_found(str(exc)) from exc


def _get_knowledge_base_service() -> KnowledgeBaseService:
    """构建知识库服务实例。"""
    return KnowledgeBaseService(_get_repository())


def _get_repository() -> KnowledgeBaseRepository:
    """构建知识库仓储实例。"""
    return KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH)


async def _process_queued_documents_for_publish(kb_id: str) -> None:
    """发布前尽力处理当前知识库已排队文档，保证发布后可检索。"""
    repository = _get_repository()
    ingest_service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(),
        embedding_service=EmbeddingService(),
        es_service=get_es_service(),
        milvus_service=MilvusService(),
    )
    worker = DocumentParseWorker(
        repository=repository,
        ingest_service=ingest_service,
        batch_size=Config.DOCUMENT_PARSE_WORKER_BATCH_SIZE,
        concurrency=Config.DOCUMENT_PARSE_WORKER_CONCURRENCY,
        max_attempts=Config.DOCUMENT_PARSE_WORKER_MAX_ATTEMPTS,
    )
    while True:
        processed = await worker.run_once(knowledge_base_id=kb_id)
        if processed == 0:
            return


async def _cleanup_external_indexes(chunk_ids: list[str]) -> dict[str, int]:
    """尽力清理外部检索索引，避免外部服务异常阻断知识库删除。"""
    stats = {
        "requested": len(chunk_ids),
        "es_deleted": 0,
        "milvus_deleted": 0,
        "graph_deleted": 0,
    }
    if not chunk_ids:
        return stats
    try:
        es_service = get_es_service()
    except Exception:
        es_service = None
    try:
        milvus_service = MilvusService()
    except Exception:
        milvus_service = None
    try:
        graph_service = get_graph_retrieval_service()
    except Exception:
        graph_service = None
    for chunk_id in chunk_ids:
        try:
            if es_service is not None and await es_service.delete_document(Config.ES_ASSET_INDEX, chunk_id):
                stats["es_deleted"] += 1
        except Exception:
            pass
        try:
            if milvus_service is not None and await milvus_service.delete("knowledge_chunk", chunk_id):
                stats["milvus_deleted"] += 1
        except Exception:
            pass
        try:
            if graph_service is not None and graph_service.delete_document(chunk_id):
                stats["graph_deleted"] += 1
        except Exception:
            pass
    return stats


def _not_found(message: str) -> HTTPException:
    """构建 404 响应异常。"""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": 404, "message": message},
    )


def _forbidden(message: str) -> HTTPException:
    """构建 403 响应异常。"""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": 403, "message": message},
    )
