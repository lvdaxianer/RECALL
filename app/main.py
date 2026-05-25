"""
FastAPI 入口模块

@author lvdaxianerplus
@date 2026-04-14
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件（覆盖已存在的环境变量）
load_dotenv(override=True)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import rag
from app.routers import query as query_router
from app.models.schemas import HealthResponse
from app.services.milvus_service import MilvusService
from app.services.embedding_service import EmbeddingService
from app.services.rerank_service import RerankService
from app.services.es_service import get_es_service
from app.config import Config
from app.utils.logger import milvus_logger, embedding_logger, rerank_logger, rag_search_logger
from app.subscribers import start_delete_subscriber, stop_delete_subscriber

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    启动时初始化 ES 索引和 RAG 删除订阅器
    """
    # 启动时创建 ES 索引
    try:
        es = get_es_service()
        if es.is_connected():
            await es.create_index_if_not_exists(Config.ES_SKILL_INDEX)
            await es.create_index_if_not_exists(Config.ES_ASSET_INDEX)
            rag_search_logger.info("[Startup] ES 索引初始化完成")
        else:
            rag_search_logger.warning("[Startup] ES 未连接，跳过索引初始化")
    except Exception as e:
        rag_search_logger.warning("[Startup] ES 索引初始化失败: {}", str(e))

    # 启动 RAG 删除订阅器
    try:
        await start_delete_subscriber()
        rag_search_logger.info("[Startup] RAG 删除订阅器已启动")
    except Exception as e:
        rag_search_logger.warning("[Startup] RAG 删除订阅器启动失败: {}", str(e))

    yield

    # 关闭时停止订阅器
    try:
        await stop_delete_subscriber()
        rag_search_logger.info("[Shutdown] RAG 删除订阅器已停止")
    except Exception as e:
        rag_search_logger.warning("[Shutdown] RAG 删除订阅器停止失败: {}", str(e))


# 创建 FastAPI 应用
app = FastAPI(
    title="RAG 知识检索平台",
    description="基于 RAG 技术的知识检索平台 API",
    version="1.0.0",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# 注册路由
app.include_router(rag.router)
app.include_router(query_router.router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    健康检查接口

    @returns 服务健康状态
    """
    # 检查各服务状态
    services_status = {
        "milvus": "unknown",
        "embedding": "unknown",
        "rerank": "unknown"
    }

    # 检查 Milvus
    try:
        milvus = MilvusService()
        if await milvus.health_check():
            services_status["milvus"] = "connected"
        else:
            services_status["milvus"] = "disconnected"
    except Exception as e:
        milvus_logger.error("[Milvus] 健康检查失败, error={}", str(e))
        services_status["milvus"] = "disconnected"

    # 检查 Embedding
    try:
        embedding = EmbeddingService()
        if await embedding.health_check():
            services_status["embedding"] = "available"
        else:
            services_status["embedding"] = "unavailable"
    except Exception as e:
        embedding_logger.error("[Embedding] 健康检查失败, error={}", str(e))
        services_status["embedding"] = "unavailable"

    # 检查 Rerank
    try:
        rerank = RerankService()
        if await rerank.health_check():
            services_status["rerank"] = "available"
        else:
            services_status["rerank"] = "unavailable"
    except Exception as e:
        rerank_logger.error("[Rerank] 健康检查失败, error={}", str(e))
        services_status["rerank"] = "unavailable"

    # 检查 ES
    try:
        es = get_es_service()
        if es.is_connected():
            services_status["elasticsearch"] = "connected"
        else:
            services_status["elasticsearch"] = "disconnected"
    except Exception as e:
        rag_search_logger.error("[ES] 健康检查失败, error={}", str(e))
        services_status["elasticsearch"] = "disconnected"

    # 确定总体状态
    if all(v == "connected" or v == "available" for v in services_status.values()):
        status = "healthy"
    elif services_status["milvus"] == "disconnected":
        status = "unhealthy"
    else:
        status = "degraded"

    return HealthResponse(
        status=status,
        services=services_status
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
