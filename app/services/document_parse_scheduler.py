"""
文档解析定时调度器

Author: lvdaxianerplus
Date: 2026-06-05
"""

from __future__ import annotations

import asyncio
from typing import Any


class DocumentParseScheduler:
    """周期性运行文档解析 worker，不重叠执行 tick。"""

    def __init__(self, worker: Any, interval_seconds: float = 2.0):
        """初始化调度器。"""
        self.worker = worker
        self.interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """启动调度循环。"""
        while not self._stop_event.is_set():
            await self.worker.run_once()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def stop(self) -> None:
        """请求停止调度循环。"""
        self._stop_event.set()
