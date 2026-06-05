"""
同义词管理路由

Author: lvdaxianerplus
Date: 2026-06-05
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

from app.config import Config
from app.models.knowledge_base_schemas import SynonymGroupCreateRequest
from app.models.knowledge_base_schemas import SynonymGroupUpdateRequest
from app.models.schemas import APIResponse
from app.services.knowledge_base_repository import KnowledgeBaseRepository


router = APIRouter(prefix="/api/v1/synonyms", tags=["Synonyms"])
KNOWLEDGE_BASE_DB_PATH = Config.KNOWLEDGE_BASE_DB_PATH or str(Path("data") / "knowledge_base.sqlite")


@router.get("", response_model=APIResponse)
async def list_synonym_groups(knowledge_base_id: str | None = Query(default=None)):
    """
    列出同义词组

    @param knowledge_base_id - 可选知识库 ID
    @returns 同义词组列表
    """
    data = _get_repository().list_synonym_groups(knowledge_base_id=knowledge_base_id)
    return APIResponse(code=200, message="success", data=data)


@router.post("", response_model=APIResponse)
async def create_synonym_group(request: SynonymGroupCreateRequest):
    """
    创建同义词组

    @param request - 同义词组创建请求
    @returns 创建后的同义词组
    """
    data = _get_repository().create_synonym_group(
        knowledge_base_id=request.knowledge_base_id,
        canonical=request.canonical,
        terms=request.terms,
        owner_id=request.owner_id,
        enabled=request.enabled,
    )
    return APIResponse(code=200, message="success", data=data)


@router.patch("/{group_id}", response_model=APIResponse)
async def update_synonym_group(group_id: str, request: SynonymGroupUpdateRequest):
    """
    更新同义词组

    @param group_id - 同义词组 ID
    @param request - 同义词组更新请求
    @returns 更新后的同义词组
    """
    try:
        data = _get_repository().update_synonym_group(
            group_id,
            request.model_dump(exclude_none=True),
        )
        return APIResponse(code=200, message="success", data=data)
    except ValueError as exc:
        raise _not_found(str(exc)) from exc


@router.delete("/{group_id}", response_model=APIResponse)
async def delete_synonym_group(group_id: str):
    """
    删除同义词组

    @param group_id - 同义词组 ID
    @returns 删除的同义词组 ID
    """
    try:
        data = _get_repository().delete_synonym_group(group_id)
        return APIResponse(code=200, message="success", data=data)
    except ValueError as exc:
        raise _not_found(str(exc)) from exc


def _get_repository() -> KnowledgeBaseRepository:
    """构建知识库仓储。"""
    return KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH)


def _not_found(message: str) -> HTTPException:
    """构建 404 响应异常。"""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": 404, "message": message},
    )
