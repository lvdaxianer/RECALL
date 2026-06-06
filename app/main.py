"""
FastAPI 入口模块

@author lvdaxianerplus
@date 2026-04-14
"""

from dotenv import load_dotenv

# 加载 .env 文件（覆盖已存在的环境变量）
load_dotenv(override=True)

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routers import agent_runtime
from app.routers import knowledge_bases
from app.routers import knowledge_base_documents
from app.routers import rag
from app.routers import rag_cache
from app.routers import rag_delete
from app.routers import rag_insights
from app.routers import rag_insert
from app.routers import rag_optimize
from app.routers import rag_retry
from app.routers import rag_stream
from app.routers import retrieval_sdk
from app.routers import retrieval_stream
from app.routers import see_timeline
from app.routers import synonyms
from app.routers import query as query_router
from app.models.schemas import HealthResponse
from app.services.milvus_service import MilvusService
from app.services.embedding_service import EmbeddingService
from app.services.rerank_service import RerankService
from app.services import rag_search_pipeline_service
from app.routers import rag_insert as rag_insert_router
from app.services.agent_runtime_client import get_agent_runtime_client
from app.services.document_ingest_service import DocumentIngestService
from app.services.document_parse_scheduler import DocumentParseScheduler
from app.services.document_parse_worker import DocumentParseWorker
from app.services.es_service import get_es_service
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.markdown_chunk_service import MarkdownChunkService
from app.config import Config
from app.utils.logger import milvus_logger, embedding_logger, rerank_logger, rag_search_logger
from app.subscribers import start_delete_subscriber, stop_delete_subscriber


async def _rebuild_graph_index_on_startup(es_service, graph_service):
    """
    按配置在启动时重建内存图谱索引

    @param es_service - ES 服务
    @param graph_service - 图谱检索服务
    @returns 重建统计，未开启时返回 None
    """
    if not Config.RAG_GRAPH_REBUILD_ON_STARTUP:
        rag_search_logger.info("[Startup] 启动图谱重建未开启")
        return None

    documents = await _load_graph_rebuild_documents(es_service)
    stats_data = graph_service.rebuild(documents)
    _log_graph_rebuild_result(documents, stats_data)
    return stats_data


async def _load_graph_rebuild_documents(es_service):
    """
    从 ES 读取启动重建需要的文档

    @param es_service - ES 服务
    @returns skill 和 asset 文档列表
    """
    documents = []
    for index_name in [Config.ES_SKILL_INDEX, Config.ES_ASSET_INDEX]:
        index_documents = await es_service.list_documents(
            index_name,
            limit=Config.RAG_GRAPH_REBUILD_LIMIT
        )
        documents.extend(index_documents)
    return documents


def _log_graph_rebuild_result(documents, stats_data) -> None:
    """
    记录启动图谱重建结果

    @param documents - 参与重建的文档
    @param stats_data - 图谱重建统计
    """
    rag_search_logger.info(
        "[Startup] 图谱索引重建完成, indexed_count={}, stats={}",
        len(documents),
        stats_data
    )


async def _close_model_http_clients() -> None:
    """关闭已创建的模型 HTTP 客户端连接池"""
    services = [
        rag_search_pipeline_service._embedding_service,
        rag_search_pipeline_service._rerank_service,
        rag_insert_router._embedding_service,
    ]
    for service in services:
        if service is not None and hasattr(service, "close"):
            await service.close()


async def _close_agent_runtime_client() -> None:
    """关闭 Agent Runtime 客户端连接池"""
    runtime_client = get_agent_runtime_client()
    if hasattr(runtime_client, "close"):
        await runtime_client.close()
    else:
        pass


def _build_document_parse_scheduler() -> DocumentParseScheduler:
    """构建知识库文档后台解析调度器。"""
    repository = KnowledgeBaseRepository(Config.KNOWLEDGE_BASE_DB_PATH)
    ingest_service = DocumentIngestService(
        repository=repository,
        chunk_service=MarkdownChunkService(),
    )
    worker = DocumentParseWorker(
        repository=repository,
        ingest_service=ingest_service,
        batch_size=Config.DOCUMENT_PARSE_BATCH_SIZE,
        concurrency=Config.DOCUMENT_PARSE_CONCURRENCY,
        max_attempts=Config.DOCUMENT_PARSE_WORKER_MAX_ATTEMPTS,
    )
    return DocumentParseScheduler(
        worker,
        interval_seconds=Config.DOCUMENT_PARSE_INTERVAL_SECONDS,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    启动时初始化 ES 索引和 RAG 删除订阅器
    """
    document_parse_scheduler = None
    document_parse_scheduler_task = None

    # 启动时创建 ES 索引
    try:
        es = get_es_service()
        if es.is_connected():
            await es.create_index_if_not_exists(Config.ES_SKILL_INDEX)
            await es.create_index_if_not_exists(Config.ES_ASSET_INDEX)
            rag_search_logger.info("[Startup] ES 索引初始化完成")
            await _rebuild_graph_index_on_startup(es, get_graph_retrieval_service())
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

    try:
        if Config.DOCUMENT_PARSE_WORKER_ENABLED:
            document_parse_scheduler = _build_document_parse_scheduler()
            document_parse_scheduler_task = asyncio.create_task(document_parse_scheduler.start())
            rag_search_logger.info("[Startup] 文档解析调度器已启动")
    except Exception as e:
        rag_search_logger.warning("[Startup] 文档解析调度器启动失败: {}", str(e))

    yield

    if document_parse_scheduler is not None:
        try:
            await document_parse_scheduler.stop()
            if document_parse_scheduler_task is not None:
                await document_parse_scheduler_task
            rag_search_logger.info("[Shutdown] 文档解析调度器已停止")
        except Exception as e:
            rag_search_logger.warning("[Shutdown] 文档解析调度器停止失败: {}", str(e))

    # 关闭时停止订阅器
    try:
        await stop_delete_subscriber()
        rag_search_logger.info("[Shutdown] RAG 删除订阅器已停止")
    except Exception as e:
        rag_search_logger.warning("[Shutdown] RAG 删除订阅器停止失败: {}", str(e))

    try:
        await _close_model_http_clients()
        rag_search_logger.info("[Shutdown] 模型 HTTP 客户端连接池已关闭")
    except Exception as e:
        rag_search_logger.warning("[Shutdown] 模型 HTTP 客户端连接池关闭失败: {}", str(e))

    try:
        await _close_agent_runtime_client()
        rag_search_logger.info("[Shutdown] Agent Runtime 客户端连接池已关闭")
    except Exception as e:
        rag_search_logger.warning("[Shutdown] Agent Runtime 客户端连接池关闭失败: {}", str(e))


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

STATIC_DIR = Path(__file__).resolve().parent / "static"

# 注册路由
app.include_router(agent_runtime.router)
app.include_router(knowledge_bases.router)
app.include_router(knowledge_base_documents.router)
app.include_router(rag.router)
app.include_router(rag_cache.router)
app.include_router(rag_delete.router)
app.include_router(rag_insights.router)
app.include_router(rag_insert.router)
app.include_router(rag_optimize.router)
app.include_router(rag_retry.router)
app.include_router(rag_stream.router)
app.include_router(retrieval_sdk.router)
app.include_router(retrieval_stream.router)
app.include_router(see_timeline.router)
app.include_router(synonyms.router)
app.include_router(query_router.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    embedding = None
    try:
        embedding = EmbeddingService()
        if await embedding.health_check():
            services_status["embedding"] = "available"
        else:
            services_status["embedding"] = "unavailable"
    except Exception as e:
        embedding_logger.error("[Embedding] 健康检查失败, error={}", str(e))
        services_status["embedding"] = "unavailable"
    finally:
        if embedding is not None:
            await embedding.close()

    # 检查 Rerank
    rerank = None
    try:
        rerank = RerankService()
        if await rerank.health_check():
            services_status["rerank"] = "available"
        else:
            services_status["rerank"] = "unavailable"
    except Exception as e:
        rerank_logger.error("[Rerank] 健康检查失败, error={}", str(e))
        services_status["rerank"] = "unavailable"
    finally:
        if rerank is not None:
            await rerank.close()

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
