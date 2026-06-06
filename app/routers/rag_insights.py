"""
RAG 观测与诊断路由

包含语义优化历史、检索评测记录和图检索调试接口。

@author lvdaxianerplus
@date 2026-06-01
"""

from fastapi import APIRouter, HTTPException, status

from app.config import Config
from app.models.schemas import APIResponse, EvaluationRecordRequest
from app.services.agent_tool_registry import get_agent_tool_registry
from app.services.es_service import get_es_service
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.optimize_history_service import get_optimize_history_service
from app.services.rag_evaluation_service import RagEvaluationRecordInput, get_rag_evaluation_service


router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


@router.get("/{id}/search/optimize/history", response_model=APIResponse)
async def list_optimize_history(id: str):
    """
    获取语义优化历史记录

    @param id - 用户ID
    @returns 历史记录列表
    """
    records = get_optimize_history_service().list_user_records(id)
    return APIResponse(code=200, message="success", data=records)


@router.get("/{id}/search/optimize/history/{history_id}", response_model=APIResponse)
async def get_optimize_history(id: str, history_id: str):
    """
    获取单条语义优化历史记录

    @param id - 用户ID
    @param history_id - 历史记录ID
    @returns 历史记录
    """
    record = get_optimize_history_service().get_record(id, history_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 404, "message": "历史记录不存在"}
        )
    return APIResponse(code=200, message="success", data=record)


@router.post("/{id}/evaluation/records", response_model=APIResponse)
async def create_evaluation_record(id: str, request: EvaluationRecordRequest):
    """
    创建检索评测记录

    @param id - 用户ID
    @param request - 检索评测记录请求
    @returns 新增的评测记录
    """
    record = get_rag_evaluation_service().add_record(RagEvaluationRecordInput(
        user_id=id,
        query=request.query,
        optimized_query=request.optimized_query,
        retrieved_ids=request.retrieved_ids,
        miss_reason=request.miss_reason,
        human_label=request.human_label
    ))
    return APIResponse(code=200, message="success", data=record)


@router.post("/{id}/feedback/bad-case", response_model=APIResponse)
async def create_bad_case_feedback(id: str, request: EvaluationRecordRequest):
    """
    创建 Bad feedback 并复用 Agent 工具治理缓存

    @param id - 用户ID
    @param request - 检索评测记录请求
    @returns 新增评测记录和缓存撤销结果
    """
    result = await get_agent_tool_registry().call(
        "record_bad_case",
        request.model_dump(exclude_none=True),
        user_id=id,
    )
    return APIResponse(code=200, message="success", data=result)


@router.get("/{id}/evaluation/records", response_model=APIResponse)
async def list_evaluation_records(id: str):
    """
    获取用户检索评测记录

    @param id - 用户ID
    @returns 评测记录列表
    """
    records = get_rag_evaluation_service().list_user_records(id)
    return APIResponse(code=200, message="success", data=records)


@router.get("/{id}/evaluation/records/summary", response_model=APIResponse)
async def get_evaluation_summary(id: str):
    """
    获取用户检索评测汇总

    @param id - 用户ID
    @returns bad case 原因和人工标签分布
    """
    summary = get_rag_evaluation_service().summary_user_records(id)
    return APIResponse(code=200, message="success", data=summary)


@router.get("/graph/stats", response_model=APIResponse)
async def get_graph_stats():
    """
    获取轻量图谱索引统计

    @returns 图索引规模
    """
    stats_data = get_graph_retrieval_service().stats()
    return APIResponse(code=200, message="success", data=stats_data)


@router.post("/graph/rebuild", response_model=APIResponse)
async def rebuild_graph_index(limit: int = 1000):
    """
    从 ES 重建轻量图谱索引

    @param limit - 每个 ES 索引读取的文档数量上限
    @returns 重建结果
    """
    es_service = get_es_service()
    documents = []
    for index_name in [Config.ES_SKILL_INDEX, Config.ES_ASSET_INDEX]:
        documents.extend(await es_service.list_documents(index_name, limit=limit))
    stats_data = get_graph_retrieval_service().rebuild(documents)
    return APIResponse(
        code=200,
        message="success",
        data={"indexed_count": len(documents), "stats": stats_data}
    )


@router.get("/{id}/graph/explain", response_model=APIResponse)
async def explain_graph_search(
    id: str,
    query: str,
    type: str = "all",
    topK: int = 20
):
    """
    查看一次图检索的命中解释

    @param id - 用户ID
    @param query - 查询文本
    @param type - 资源类型
    @param topK - 返回数量
    @returns 图检索解释信息
    """
    explain_data = get_graph_retrieval_service().explain(
        query,
        search_type=type,
        top_k=topK
    )
    return APIResponse(code=200, message="success", data=explain_data)
