"""
文档解析定时调度器测试

Author: lvdaxianerplus
Date: 2026-06-05
"""

import asyncio

import pytest

from app.services.document_parse_scheduler import DocumentParseScheduler


class FakeWorker:
    """记录 run_once 调用次数的 worker。"""

    def __init__(self):
        self.calls = 0

    async def run_once(self):
        self.calls += 1
        return 0


@pytest.mark.asyncio
async def test_document_parse_scheduler_runs_worker_until_stopped():
    """scheduler 周期性触发 worker，直到 stop。"""
    worker = FakeWorker()
    scheduler = DocumentParseScheduler(worker, interval_seconds=0.01)

    task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.03)
    await scheduler.stop()
    await task

    assert worker.calls >= 1


@pytest.mark.asyncio
async def test_document_parse_scheduler_does_not_overlap_ticks():
    """上一轮未结束时不启动重叠解析。"""

    class SlowWorker:
        def __init__(self):
            self.running = False
            self.overlapped = False

        async def run_once(self):
            if self.running:
                self.overlapped = True
            self.running = True
            await asyncio.sleep(0.03)
            self.running = False
            return 1

    worker = SlowWorker()
    scheduler = DocumentParseScheduler(worker, interval_seconds=0.01)

    task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.05)
    await scheduler.stop()
    await task

    assert worker.overlapped is False
