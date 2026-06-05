"""
RAG 重试队列路由

提供重试任务列表和状态查询接口。

@author lvdaxianerplus
@date 2026-06-01
"""

from fastapi import APIRouter, HTTPException, status

from app.models.schemas import APIResponse
from app.services.retry_queue import get_retry_queue


router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


@router.get("/{id}/retry/tasks")
async def get_retry_tasks(id: str):
    """
    获取用户所有待处理的重试任务

    @param id - 用户ID
    @returns 待处理任务列表
    """
    retry_queue = get_retry_queue()
    pending_tasks = retry_queue.get_user_pending_tasks(id)
    failed_tasks = retry_queue.get_user_failed_tasks(id)
    return APIResponse(
        code=200,
        message="success",
        data={
            "pending": pending_tasks,
            "failed": failed_tasks,
            "queue_size": retry_queue.queue_size,
            "failed_count": retry_queue.failed_count
        }
    )


@router.get("/{id}/retry/tasks/{task_id}")
async def get_retry_task_status(id: str, task_id: str):
    """
    获取特定重试任务的状态

    @param id - 用户ID
    @param task_id - 任务ID
    @returns 任务状态
    """
    retry_queue = get_retry_queue()
    task_status = retry_queue.get_task_status(task_id)
    if task_status is None or task_status.get("user_id") != id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 404, "message": "任务不存在"}
        )
    return APIResponse(code=200, message="success", data=task_status)
