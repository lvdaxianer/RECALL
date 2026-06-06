"""
Retrieval SDK 同步检索路由

提供知识库多选过滤检索 API。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.config import Config
from app.models.knowledge_base_schemas import RetrievalSDKSearchRequest
from app.models.schemas import APIResponse
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.retrieval_sdk_service import RetrievalSDKService


router = APIRouter(prefix="/api/v1/retrieval", tags=["RetrievalSDK"])
KNOWLEDGE_BASE_DB_PATH = Config.KNOWLEDGE_BASE_DB_PATH or str(Path("data") / "knowledge_base.sqlite")


@router.post("/search", response_model=APIResponse)
async def search(request: RetrievalSDKSearchRequest):
    """
    知识库过滤检索

    @param request - Retrieval SDK 检索请求
    @returns 检索结果和 trace
    """
    _assert_published_knowledge_bases(request.knowledge_base_ids)
    service = _get_retrieval_sdk_service()
    top_k = service.resolve_top_k(request.top_k, request.knowledge_base_ids)
    retrieval_query = service.build_retrieval_query(
        request.input,
        use_context=request.use_context,
        history_questions=request.history_questions,
    )
    result = await service.search_with_engines(
        input=retrieval_query,
        knowledge_base_ids=request.knowledge_base_ids,
        top_k=top_k,
        issue_type=request.issue_type,
    )
    return APIResponse(code=200, message="success", data=result)


def _get_retrieval_sdk_service() -> RetrievalSDKService:
    """构建 Retrieval SDK 服务。"""
    return RetrievalSDKService(KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH))


def _assert_published_knowledge_bases(knowledge_base_ids: list[str]) -> None:
    """校验检索请求只使用已发布知识库。"""
    repository = KnowledgeBaseRepository(KNOWLEDGE_BASE_DB_PATH)
    records = repository.get_knowledge_bases_by_ids(knowledge_base_ids)
    published_ids = {record["id"] for record in records if record.get("status") == "published"}
    invalid = [kb_id for kb_id in knowledge_base_ids if kb_id not in published_ids]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "聊天检索只能选择已发布知识库", "knowledge_base_ids": invalid},
        )
