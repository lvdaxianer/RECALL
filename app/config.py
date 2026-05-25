"""
配置加载模块

从环境变量读取所有配置

@author lvdaxianerplus
@date 2026-04-14
"""

import os
from typing import Optional
from dotenv import load_dotenv

# 加载 .env 文件（覆盖已存在的环境变量）
load_dotenv(override=True)


class Config:
    """配置类"""

    # LLM 模型配置（用于语义优化）
    MODEL_NAME: str = os.getenv("MODEL_NAME", "")
    MODEL_API_KEY: str = os.getenv("MODEL_API_KEY", "")
    MODEL_REQUEST_URL: str = os.getenv("MODEL_REQUEST_URL", "")

    # Embedding 配置
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "")
    EMBEDDING_MODEL_API_KEY: str = os.getenv("EMBEDDING_MODEL_API_KEY", "")
    EMBEDDING_REQUEST_URL: str = os.getenv("EMBEDDING_REQUEST_URL", "")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "8192"))

    # Rerank 配置
    RERANK_MODEL_NAME: str = os.getenv("RERANK_MODEL_NAME", "")
    RERANK_MODEL_API_KEY: str = os.getenv("RERANK_MODEL_API_KEY", "")
    RERANK_REQUEST_URL: str = os.getenv("RERANK_REQUEST_URL", "")

    # ES 配置
    ES_HOST: str = os.getenv("ES_HOST", "localhost:9200")
    ES_USERNAME: str = os.getenv("ES_USERNAME", "elastic")
    ES_PASSWORD: str = os.getenv("ES_PASSWORD", "elastic")
    ES_SCHEME: str = os.getenv("ES_SCHEME", "http")
    ES_SKILL_INDEX: str = os.getenv("ES_SKILL_INDEX", "rag_skills")
    ES_ASSET_INDEX: str = os.getenv("ES_ASSET_INDEX", "rag_assets")

    # Milvus / Embedding Store 配置
    # EMBEDDING_STORE_HOST 格式: "host:port"
    _store_host: str = os.getenv("EMBEDDING_STORE_HOST", "localhost:19530")

    # Redis 配置（用于订阅删除事件）
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    _host_parts: list = _store_host.split(":")
    MILVUS_HOST: str = _host_parts[0] if len(_host_parts) > 0 else "localhost"
    MILVUS_PORT: int = int(_host_parts[1]) if len(_host_parts) > 1 else 19530
    MILVUS_DB: str = os.getenv("EMBEDDING_STORE_DB_NAME", "default")

    # RAG 配置
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "20"))
    RERANK_THRESHOLD: float = float(os.getenv("RERANK_THRESHOLD", "0.7"))

    # 高精度 RAG 问答配置
    QUERY_TOP_K: int = int(os.getenv("QUERY_TOP_K", "5"))
    QUERY_RERANK_THRESHOLD: float = float(os.getenv("QUERY_RERANK_THRESHOLD", "0.3"))
    FAITHFULNESS_THRESHOLD: float = float(os.getenv("FAITHFULNESS_THRESHOLD", "0.7"))
    QUERY_USE_HYDE: bool = os.getenv("QUERY_USE_HYDE", "false").lower() == "true"
    QUERY_USE_REWRITE: bool = os.getenv("QUERY_USE_REWRITE", "true").lower() == "true"
    QUERY_USE_DECOMPOSE: bool = os.getenv("QUERY_USE_DECOMPOSE", "false").lower() == "true"
    QUERY_USE_VALIDATION: bool = os.getenv("QUERY_USE_VALIDATION", "true").lower() == "true"

    # 缓存配置
    EMBEDDING_CACHE_TTL: int = int(os.getenv("EMBEDDING_CACHE_TTL", "86400"))      # 24 小时
    EMBEDDING_CACHE_MAX_SIZE: int = int(os.getenv("EMBEDDING_CACHE_MAX_SIZE", "1000"))  # LRU 上限
    RERANK_CACHE_TTL: int = int(os.getenv("RERANK_CACHE_TTL", "3600"))              # 1 小时
    RERANK_CACHE_MAX_SIZE: int = int(os.getenv("RERANK_CACHE_MAX_SIZE", "500"))      # LRU 上限
    RERANK_CACHE_ENABLED: bool = os.getenv("RERANK_CACHE_ENABLED", "false").lower() == "true"  # 默认关闭

    # DEBUG 配置
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # 日志滚动配置
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")
    APP_NAME: str = os.getenv("APP_NAME", "app")
    LOG_RETENTION_DAYS: int = int(os.getenv("LOG_RETENTION_DAYS", "30"))
    LOG_COMPRESS_TIME: str = os.getenv("LOG_COMPRESS_TIME", "00:05")

    @classmethod
    def get_config(cls) -> dict:
        """获取完整配置"""
        return {
            "llm": {
                "model_name": cls.MODEL_NAME,
                "api_key": cls.MODEL_API_KEY,
                "request_url": cls.MODEL_REQUEST_URL,
            },
            "embedding": {
                "model_name": cls.EMBEDDING_MODEL_NAME,
                "api_key": cls.EMBEDDING_MODEL_API_KEY,
                "request_url": cls.EMBEDDING_REQUEST_URL,
                "dimension": cls.EMBEDDING_DIMENSION,
            },
            "rerank": {
                "model_name": cls.RERANK_MODEL_NAME,
                "api_key": cls.RERANK_MODEL_API_KEY,
                "request_url": cls.RERANK_REQUEST_URL,
            },
            "milvus": {
                "host": cls.MILVUS_HOST,
                "port": cls.MILVUS_PORT,
                "db": cls.MILVUS_DB,
            },
            "rag": {
                "top_k": cls.RERANK_TOP_K,
                "threshold": cls.RERANK_THRESHOLD,
            },
            "log_rotation": {
                "log_dir": cls.LOG_DIR,
                "app_name": cls.APP_NAME,
                "retention_days": cls.LOG_RETENTION_DAYS,
                "compress_time": cls.LOG_COMPRESS_TIME,
            }
        }


def get_config() -> Config:
    """获取配置实例"""
    return Config
