"""
RAG Delete Subscriber

Subscribes to Redis 'rag:delete' channel and deletes records from
Milvus and Elasticsearch when a delete event is received.

Usage:
    This subscriber should be started as a background task alongside
    the FastAPI application.

@author lvdaxianerplus
@date 2026-04-18
"""

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as redis

from app.config import Config
from app.services.milvus_service import MilvusService
from app.services.es_service import get_es_service

logger = logging.getLogger(__name__)

CHANNEL = "rag:delete"


class RagDeleteSubscriber:

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.milvus_service = MilvusService()
        self.running = False

    async def start(self):
        """
        Start the Redis subscription and listen for delete events.
        """
        redis_url = self._build_redis_url()
        self.redis_client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        try:
            await self.redis_client.ping()
            logger.info(f"[RAG删除订阅] Redis连接成功: {redis_url}")
        except Exception as e:
            logger.error(f"[RAG删除订阅] Redis连接失败: {e}")
            raise

        self.running = True
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(CHANNEL)
        logger.info(f"[RAG删除订阅] 已订阅频道: {CHANNEL}")

        try:
            async for message in pubsub.listen():
                if not self.running:
                    break
                if message["type"] == "message":
                    await self._handle_message(message["data"])
        except asyncio.CancelledError:
            logger.info("[RAG删除订阅] 订阅被取消")
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await self.redis_client.close()
            logger.info("[RAG删除订阅] Redis连接已关闭")

    async def stop(self):
        """
        Stop the subscription gracefully.
        """
        self.running = False
        if self.redis_client:
            await self.redis_client.aclose()

    async def _handle_message(self, data: str):
        """
        Handle a delete event message.

        @param data JSON string with 'type' and 'id' fields
        """
        try:
            payload = json.loads(data)
            doc_type = payload.get("type")
            doc_id = payload.get("id")

            if not doc_type or not doc_id:
                logger.warning(f"[RAG删除订阅] 消息格式错误，缺少字段: {data}")
                return

            logger.info(f"[RAG删除订阅] 收到删除事件: type={doc_type}, id={doc_id}")

            # Delete from Milvus
            milvus_success = await self.milvus_service.delete(
                collection=doc_type,
                doc_id=doc_id,
            )
            if milvus_success:
                logger.info(f"[RAG删除订阅] Milvus删除成功: type={doc_type}, id={doc_id}")
            else:
                logger.warning(f"[RAG删除订阅] Milvus删除失败或记录不存在: type={doc_type}, id={doc_id}")

            # Delete from ES (best-effort, non-blocking)
            try:
                es_service = get_es_service()
                es_index = Config.ES_SKILL_INDEX if doc_type == "skill" else Config.ES_ASSET_INDEX
                await es_service.delete_document(es_index, doc_id)
                logger.info(f"[RAG删除订阅] ES删除成功: type={doc_type}, id={doc_id}")
            except Exception as es_error:
                logger.warning(f"[RAG删除订阅] ES删除失败（降级）: type={doc_type}, id={doc_id}, error={es_error}")

        except json.JSONDecodeError as e:
            logger.error(f"[RAG删除订阅] JSON解析失败: {e}, data={data}")
        except Exception as e:
            logger.error(f"[RAG删除订阅] 处理消息异常: {e}, data={data}")

    def _build_redis_url(self) -> str:
        """
        Build Redis connection URL from config.

        @returns Redis URL
        """
        password_part = f":{Config.REDIS_PASSWORD}@" if Config.REDIS_PASSWORD else ""
        return f"redis://{password_part}{Config.REDIS_HOST}:{Config.REDIS_PORT}/{Config.REDIS_DB}"


# Global subscriber instance for lifecycle management
_subscriber: Optional[RagDeleteSubscriber] = None
_background_task: Optional[asyncio.Task] = None


async def start_delete_subscriber():
    """
    Start the delete subscriber as a background task.
    Should be called when the FastAPI app starts.
    """
    global _subscriber, _background_task

    subscriber = RagDeleteSubscriber()

    async def run():
        try:
            await subscriber.start()
        except Exception as e:
            logger.error(f"[RAG删除订阅] 订阅异常退出: {e}")

    _background_task = asyncio.create_task(run())
    _subscriber = subscriber
    logger.info("[RAG删除订阅] 订阅任务已启动")


async def stop_delete_subscriber():
    """
    Stop the delete subscriber gracefully.
    Should be called when the FastAPI app shuts down.
    """
    global _subscriber, _background_task

    if _subscriber:
        await _subscriber.stop()
    if _background_task:
        _background_task.cancel()
        try:
            await _background_task
        except asyncio.CancelledError:
            pass
    logger.info("[RAG删除订阅] 订阅已停止")
