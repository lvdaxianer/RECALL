"""
知识库文档路由

提供纯文本/Markdown 文档录入、文档列表、详情与 chunk 列表 API。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import Config
from app.models.schemas import APIResponse
from app.services.document_ingest_service import DocumentIngestService
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.markdown_chunk_service import MarkdownChunkService


router = APIRouter(prefix="/api/v1/kb", tags=["KnowledgeBaseDocuments"])
KNOWLEDGE_BASE_DB_PATH = Config.KNOWLEDGE_BASE_DB_PATH or str(Path("data") / "knowledge_base.sqlite")


class DocumentUploadBody(BaseModel):
    """路径版文档上传请求体。"""

    name: str = Field(..., min_length=1, max_length=240, description="文档名称")
    content: str = Field(..., min_length=1, description="纯文本或 Markdown 内容")
    content_type: str = Field("text/markdown", description="内容类型")
    owner_id: str = Field("default", min_length=1, max_length=120, description="上传者 ID")
    external_id: str | None = Field(None, max_length=240, description="外部幂等 ID")


@router.post("/{kb_id}/documents", response_model=APIResponse)
async def upload_document(kb_id: str, request: DocumentUploadBody):
    """
    上传纯文本或 Markdown 文档

    @param kb_id - 知识库 ID
    @param request - 文档录入请求
    @returns 文档录入回执
    """
    try:
        data = _get_document_ingest_service().enqueue_document(
            knowledge_base_id=kb_id,
            name=request.name,
            content=request.content,
            content_type=request.content_type,
            owner_id=request.owner_id,
            external_id=request.external_id,
        )
        return APIResponse(code=200, message="success", data=data)
    except PermissionError as exc:
        raise _forbidden(str(exc)) from exc
    except ValueError as exc:
        raise _bad_request(str(exc)) from exc


@router.get("/{kb_id}/documents", response_model=APIResponse)
async def list_documents(kb_id: str):
    """
    列出知识库文档

    @param kb_id - 知识库 ID
    @returns 文档列表
    """
    repository = _get_repository()
    return APIResponse(code=200, message="success", data=repository.list_documents(kb_id))


@router.get("/{kb_id}/documents/{document_id}", response_model=APIResponse)
async def get_document(kb_id: str, document_id: str):
    """
    获取文档详情

    @param kb_id - 知识库 ID
    @param document_id - 文档 ID
    @returns 文档详情
    """
    document = _get_repository().get_document(kb_id, document_id)
    if document is not None:
        return APIResponse(code=200, message="success", data=document)
    else:
        raise _not_found("文档不存在")


@router.get("/{kb_id}/documents/{document_id}/chunks", response_model=APIResponse)
async def list_document_chunks(kb_id: str, document_id: str):
    """
    列出文档 chunk

    @param kb_id - 知识库 ID
    @param document_id - 文档 ID
    @returns chunk 列表
    """
    return APIResponse(
        code=200,
        message="success",
        data=_get_repository().list_document_chunks(kb_id, document_id),
    )


def _get_document_ingest_service() -> DocumentIngestService:
    """构建文档录入服务。"""
    return DocumentIngestService(
        repository=_get_repository(),
        chunk_service=MarkdownChunkService(),
    )


def _get_repository() -> KnowledgeBaseRepository:
    """构建知识库仓储。"""
    return KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH)


def _bad_request(message: str) -> HTTPException:
    """构建 400 响应异常。"""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": 400, "message": message},
    )


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
