"""
重试队列模块

当插入操作失败时，将请求放入重试队列，自动重试

@author lvdaxianerplus
@date 2026-04-15
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from app.utils.logger import get_logger

# 日志器
retry_queue_logger = get_logger("重试队列")

# 配置常量
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"       # 待处理
    RETRYING = "retrying"    # 重试中
    FAILED = "failed"        # 永久失败
    SUCCESS = "success"      # 成功（仅用于历史记录）


@dataclass
class RetryTask:
    """重试任务"""
    task_id: str                    # 任务唯一标识
    user_id: str                    # 用户ID
    description: str                # 描述文本
    metadata: Dict[str, Any]        # 元数据
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0           # 已重试次数
    max_retries: int = MAX_RETRIES  # 最大重试次数
    created_at: float = field(default_factory=time.time)  # 创建时间
    last_retry_at: Optional[float] = None  # 最后重试时间
    error_message: Optional[str] = None  # 错误信息
    inserted_id: Optional[str] = None  # 插入成功后的文档ID


class RetryQueue:
    """重试队列

    管理插入失败任务的重试逻辑
    """

    def __init__(self, max_retries: int = MAX_RETRIES, retry_delay: int = RETRY_DELAY_SECONDS):
        """
        初始化重试队列

        @param max_retries - 最大重试次数
        @param retry_delay - 重试间隔（秒）
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._queue: Dict[str, RetryTask] = {}  # task_id -> RetryTask
        self._processing = False
        self._lock = asyncio.Lock()

    def add_task(
        self,
        task_id: str,
        user_id: str,
        description: str,
        metadata: Dict[str, Any]
    ) -> RetryTask:
        """
        添加任务到重试队列

        @param task_id - 任务ID
        @param user_id - 用户ID
        @param description - 描述文本
        @param metadata - 元数据
        @returns RetryTask 实例
        """
        task = RetryTask(
            task_id=task_id,
            user_id=user_id,
            description=description,
            metadata=metadata
        )
        self._queue[task_id] = task
        retry_queue_logger.info(
            "[重试队列] 添加任务, taskId={}, userId={}, description={}",
            task_id, user_id, description[:50]
        )
        return task

    async def execute_with_retry(
        self,
        task: RetryTask,
        insert_func
    ) -> bool:
        """
        执行插入并自动重试

        @param task - 重试任务
        @param insert_func - 插入函数，签名: async def func(description, metadata) -> dict
        @returns 是否成功
        """
        task.status = TaskStatus.RETRYING
        task.retry_count += 1
        task.last_retry_at = time.time()

        try:
            retry_queue_logger.info(
                "[重试队列] 执行插入, taskId={}, retry={}/{}",
                task.task_id, task.retry_count, task.max_retries
            )

            # 调用插入函数
            result = await insert_func(task.description, task.metadata)

            # 成功
            task.status = TaskStatus.SUCCESS
            task.inserted_id = result.get("id")
            retry_queue_logger.info(
                "[重试队列] 插入成功, taskId={}, docId={}",
                task.task_id, task.inserted_id
            )
            return True

        except Exception as e:
            task.error_message = str(e)
            retry_queue_logger.warning(
                "[重试队列] 插入失败, taskId={}, retry={}/{}, error={}",
                task.task_id, task.retry_count, task.max_retries, str(e)
            )

            # 判断是否需要重试
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.PENDING
                return False
            else:
                task.status = TaskStatus.FAILED
                retry_queue_logger.error(
                    "[重试队列] 插入永久失败, taskId={}, error={}",
                    task.task_id, str(e)
                )
                return False

    async def process_queue(self, insert_func) -> None:
        """
        处理队列中的所有任务

        @param insert_func - 插入函数
        """
        async with self._lock:
            if self._processing:
                return
            self._processing = True

        try:
            pending_tasks = [
                task for task in self._queue.values()
                if task.status in (TaskStatus.PENDING, TaskStatus.RETRYING)
            ]

            for task in pending_tasks:
                # 检查是否需要等待（距离上次重试时间）
                if task.last_retry_at:
                    elapsed = time.time() - task.last_retry_at
                    if elapsed < self.retry_delay:
                        continue

                await self.execute_with_retry(task, insert_func)

                # 重试间隔
                await asyncio.sleep(0.5)

        finally:
            async with self._lock:
                self._processing = False

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态

        @param task_id - 任务ID
        @returns 任务状态信息，不存在返回 None
        """
        task = self._queue.get(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "user_id": task.user_id,
            "status": task.status.value,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "created_at": datetime.fromtimestamp(task.created_at).isoformat(),
            "last_retry_at": datetime.fromtimestamp(task.last_retry_at).isoformat() if task.last_retry_at else None,
            "error_message": task.error_message,
            "inserted_id": task.inserted_id
        }

    def get_user_failed_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户所有失败的任务

        @param user_id - 用户ID
        @returns 失败任务列表
        """
        return [
            self.get_task_status(task.task_id)
            for task in self._queue.values()
            if task.user_id == user_id and task.status == TaskStatus.FAILED
        ]

    def get_user_pending_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户所有待处理的任务

        @param user_id - 用户ID
        @returns 待处理任务列表
        """
        return [
            self.get_task_status(task.task_id)
            for task in self._queue.values()
            if task.user_id == user_id and task.status in (TaskStatus.PENDING, TaskStatus.RETRYING)
        ]

    def clear_succeeded(self) -> int:
        """
        清理已成功的任务

        @returns 清理的任务数量
        """
        succeeded = [
            task_id for task_id, task in self._queue.items()
            if task.status == TaskStatus.SUCCESS
        ]
        for task_id in succeeded:
            del self._queue[task_id]
        return len(succeeded)

    @property
    def queue_size(self) -> int:
        """获取队列大小（仅计算 pending 和 retrying）"""
        return sum(
            1 for task in self._queue.values()
            if task.status in (TaskStatus.PENDING, TaskStatus.RETRYING)
        )

    @property
    def failed_count(self) -> int:
        """获取失败任务数量"""
        return sum(
            1 for task in self._queue.values()
            if task.status == TaskStatus.FAILED
        )


# 全局队列实例
_retry_queue: Optional[RetryQueue] = None


def get_retry_queue() -> RetryQueue:
    """
    获取重试队列实例

    @returns RetryQueue 实例
    """
    global _retry_queue
    if _retry_queue is None:
        _retry_queue = RetryQueue()
    return _retry_queue
