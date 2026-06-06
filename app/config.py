"""
配置加载模块

从环境变量读取所有配置

@author lvdaxianerplus
@date 2026-04-14
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件（覆盖已存在的环境变量）
load_dotenv(override=True)


def _get_env_preferred(primary: str, fallback: str, default: str = "") -> str:
    """优先读取 primary 环境变量，缺失时兼容 fallback。"""
    return os.getenv(primary, os.getenv(fallback, default))


class Config:
    """配置类"""

    # LLM 模型配置（用于语义优化）
    MODEL_NAME: str = os.getenv("MODEL_NAME", "")
    MODEL_API_KEY: str = os.getenv("MODEL_API_KEY", "")
    MODEL_REQUEST_URL: str = os.getenv("MODEL_REQUEST_URL", "")
    MODEL_ENABLE_THINKING: bool = os.getenv("MODEL_ENABLE_THINKING", "false").lower() == "true"

    # Embedding 配置
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "")
    EMBEDDING_MODEL_API_KEY: str = os.getenv("EMBEDDING_MODEL_API_KEY", os.getenv("EMBEDDING_API_KEY", ""))
    EMBEDDING_REQUEST_URL: str = _get_env_preferred(
        "EMBEDDING_MODEL_REQUEST_URL",
        "EMBEDDING_REQUEST_URL"
    )
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "8192"))

    # Rerank 配置
    RERANK_MODEL_NAME: str = os.getenv("RERANK_MODEL_NAME", "")
    RERANK_MODEL_API_KEY: str = os.getenv("RERANK_MODEL_API_KEY", os.getenv("RERANK_API_KEY", ""))
    RERANK_REQUEST_URL: str = _get_env_preferred(
        "RERANK_MODEL_REQUEST_URL",
        "RERANK_REQUEST_URL"
    )

    # ES 配置
    ES_HOST: str = os.getenv("ES_HOST", "localhost:9200")
    ES_USERNAME: str = os.getenv("ES_USERNAME", "elastic")
    ES_PASSWORD: str = os.getenv("ES_PASSWORD", "elastic")
    ES_SCHEME: str = os.getenv("ES_SCHEME", "http")
    ES_VERIFY_CERTS: bool = os.getenv("ES_VERIFY_CERTS", "true").lower() == "true"
    ES_SKILL_INDEX: str = os.getenv("ES_SKILL_INDEX", "rag_skills")
    ES_ASSET_INDEX: str = os.getenv("ES_ASSET_INDEX", "rag_assets")

    # Milvus / Embedding Store 配置
    # EMBEDDING_STORE_HOST 格式: "host:port"
    _store_host: str = os.getenv("EMBEDDING_STORE_HOST", "localhost:19530")
    EMBEDDING_STORE_USERNAME: str = os.getenv("EMBEDDING_STORE_USERNAME", "")
    EMBEDDING_STORE_PASSWORD: str = os.getenv("EMBEDDING_STORE_PASSWORD", "")

    # Redis 配置（用于订阅删除事件）
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    _host_parts: list = _store_host.split(":")
    MILVUS_HOST: str = _host_parts[0] if len(_host_parts) > 0 else "localhost"
    MILVUS_PORT: int = int(_host_parts[1]) if len(_host_parts) > 1 else 19530
    MILVUS_USERNAME: str = EMBEDDING_STORE_USERNAME
    MILVUS_PASSWORD: str = EMBEDDING_STORE_PASSWORD
    MILVUS_DB: str = os.getenv("EMBEDDING_STORE_DB_NAME", "default")

    # RAG 配置
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "20"))
    RAG_RERANK_CANDIDATE_LIMIT: int = int(os.getenv("RAG_RERANK_CANDIDATE_LIMIT", "6"))
    RAG_RERANK_SKIP_CONFIDENT_ENABLED: bool = os.getenv("RAG_RERANK_SKIP_CONFIDENT_ENABLED", "true").lower() == "true"
    RAG_RERANK_SKIP_MIN_GAP: float = float(os.getenv("RAG_RERANK_SKIP_MIN_GAP", "0.018"))
    RAG_OPTIMIZE_QUERY_LIMIT: int = int(os.getenv("RAG_OPTIMIZE_QUERY_LIMIT", "2"))
    RAG_RECOMMENDATION_TOP_K: int = int(os.getenv("RAG_RECOMMENDATION_TOP_K", "3"))
    RAG_RECOMMENDATION_TIMEOUT_MS: int = int(os.getenv("RAG_RECOMMENDATION_TIMEOUT_MS", "180"))
    STREAM_DELTA_DELAY_SECONDS: float = float(os.getenv("STREAM_DELTA_DELAY_SECONDS", "0.024"))
    KNOWLEDGE_BASE_EMBEDDING_BATCH_SIZE: int = int(os.getenv("KNOWLEDGE_BASE_EMBEDDING_BATCH_SIZE", "8"))
    RERANK_THRESHOLD: float = float(os.getenv("RERANK_THRESHOLD", "0.7"))
    RAG_STATE_DB_PATH: str = os.getenv("RAG_STATE_DB_PATH", "")
    RAG_GRAPH_REBUILD_ON_STARTUP: bool = os.getenv("RAG_GRAPH_REBUILD_ON_STARTUP", "false").lower() == "true"
    RAG_GRAPH_REBUILD_LIMIT: int = int(os.getenv("RAG_GRAPH_REBUILD_LIMIT", "1000"))
    RAG_RETRIEVAL_STRATEGY: str = os.getenv("RAG_RETRIEVAL_STRATEGY", "rrf")
    RAG_WEIGHTED_TEXT_WEIGHT: float = float(os.getenv("RAG_WEIGHTED_TEXT_WEIGHT", "0.35"))
    RAG_WEIGHTED_VECTOR_WEIGHT: float = float(os.getenv("RAG_WEIGHTED_VECTOR_WEIGHT", "0.55"))
    RAG_WEIGHTED_GRAPH_WEIGHT: float = float(os.getenv("RAG_WEIGHTED_GRAPH_WEIGHT", "0.10"))
    RAG_RERANK_PROVIDER_SAFE_LIMIT: int = int(os.getenv("RAG_RERANK_PROVIDER_SAFE_LIMIT", "64"))
    RAG_WEIGHTED_QUERY_MIN_SHOULD_MATCH: str = os.getenv("RAG_WEIGHTED_QUERY_MIN_SHOULD_MATCH", "60%")
    RAG_VECTOR_SCORE_CALIBRATION_ENABLED: bool = os.getenv("RAG_VECTOR_SCORE_CALIBRATION_ENABLED", "false").lower() == "true"
    RAG_PARENT_CONTEXT_ENHANCE_ENABLED: bool = os.getenv("RAG_PARENT_CONTEXT_ENHANCE_ENABLED", "false").lower() == "true"
    RAG_GLOBAL_RETRIEVAL_ENABLED: bool = os.getenv("RAG_GLOBAL_RETRIEVAL_ENABLED", "false").lower() == "true"
    KNOWLEDGE_BASE_DB_PATH: str = os.getenv("KNOWLEDGE_BASE_DB_PATH", "./data/knowledge_base.sqlite")
    DOCUMENT_PARSE_WORKER_ENABLED: bool = os.getenv("DOCUMENT_PARSE_WORKER_ENABLED", "true").lower() == "true"
    DOCUMENT_PARSE_BATCH_SIZE: int = int(os.getenv("DOCUMENT_PARSE_BATCH_SIZE", "10"))
    DOCUMENT_PARSE_CONCURRENCY: int = int(os.getenv("DOCUMENT_PARSE_CONCURRENCY", "3"))
    DOCUMENT_PARSE_INTERVAL_SECONDS: float = float(os.getenv("DOCUMENT_PARSE_INTERVAL_SECONDS", "2.0"))
    DOCUMENT_PARSE_WORKER_INTERVAL_SECONDS: float = float(
        os.getenv("DOCUMENT_PARSE_WORKER_INTERVAL_SECONDS", str(DOCUMENT_PARSE_INTERVAL_SECONDS)),
    )
    DOCUMENT_PARSE_WORKER_BATCH_SIZE: int = int(
        os.getenv("DOCUMENT_PARSE_WORKER_BATCH_SIZE", str(DOCUMENT_PARSE_BATCH_SIZE)),
    )
    DOCUMENT_PARSE_WORKER_CONCURRENCY: int = int(
        os.getenv("DOCUMENT_PARSE_WORKER_CONCURRENCY", str(DOCUMENT_PARSE_CONCURRENCY)),
    )
    DOCUMENT_PARSE_WORKER_MAX_ATTEMPTS: int = int(os.getenv("DOCUMENT_PARSE_WORKER_MAX_ATTEMPTS", "3"))

    # Agent Runtime 配置
    AGENT_RUNTIME_MODE: str = os.getenv("AGENT_RUNTIME_MODE", "local")
    AGENT_RUNTIME_BASE_URL: str = os.getenv("AGENT_RUNTIME_BASE_URL", "")
    AGENT_RUNTIME_API_KEY: str = os.getenv("AGENT_RUNTIME_API_KEY", "")
    AGENT_RUNTIME_CONNECT_TIMEOUT: float = float(os.getenv("AGENT_RUNTIME_CONNECT_TIMEOUT", "5"))
    AGENT_RUNTIME_READ_TIMEOUT: float = float(os.getenv("AGENT_RUNTIME_READ_TIMEOUT", "60"))

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
    QUERY_OPTIMIZE_CACHE_TTL: int = int(os.getenv("QUERY_OPTIMIZE_CACHE_TTL", "3600"))
    QUERY_OPTIMIZE_CACHE_MAX_SIZE: int = int(os.getenv("QUERY_OPTIMIZE_CACHE_MAX_SIZE", "500"))
    QUERY_OPTIMIZE_FAST_RULES_ENABLED: bool = os.getenv("QUERY_OPTIMIZE_FAST_RULES_ENABLED", "true").lower() == "true"
    QUERY_OPTIMIZE_PROMPT_PATH: str = os.getenv("QUERY_OPTIMIZE_PROMPT_PATH", "")
    QUERY_OPTIMIZE_RULES_PATH: str = os.getenv("QUERY_OPTIMIZE_RULES_PATH", "")

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
                "enable_thinking": cls.MODEL_ENABLE_THINKING,
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
                "username": cls.MILVUS_USERNAME,
                "db": cls.MILVUS_DB,
            },
            "rag": {
                "top_k": cls.RERANK_TOP_K,
                "rerank_candidate_limit": cls.RAG_RERANK_CANDIDATE_LIMIT,
                "rerank_skip_confident_enabled": cls.RAG_RERANK_SKIP_CONFIDENT_ENABLED,
                "rerank_skip_min_gap": cls.RAG_RERANK_SKIP_MIN_GAP,
                "optimize_query_limit": cls.RAG_OPTIMIZE_QUERY_LIMIT,
                "threshold": cls.RERANK_THRESHOLD,
                "retrieval_strategy": cls.RAG_RETRIEVAL_STRATEGY,
                "weighted_text_weight": cls.RAG_WEIGHTED_TEXT_WEIGHT,
                "weighted_vector_weight": cls.RAG_WEIGHTED_VECTOR_WEIGHT,
                "weighted_graph_weight": cls.RAG_WEIGHTED_GRAPH_WEIGHT,
                "rerank_provider_safe_limit": cls.RAG_RERANK_PROVIDER_SAFE_LIMIT,
                "vector_score_calibration_enabled": cls.RAG_VECTOR_SCORE_CALIBRATION_ENABLED,
                "parent_context_enhance_enabled": cls.RAG_PARENT_CONTEXT_ENHANCE_ENABLED,
                "global_retrieval_enabled": cls.RAG_GLOBAL_RETRIEVAL_ENABLED,
                "knowledge_base_db_path": cls.KNOWLEDGE_BASE_DB_PATH,
                "document_parse_worker_enabled": cls.DOCUMENT_PARSE_WORKER_ENABLED,
                "document_parse_worker_interval_seconds": cls.DOCUMENT_PARSE_WORKER_INTERVAL_SECONDS,
                "document_parse_worker_batch_size": cls.DOCUMENT_PARSE_WORKER_BATCH_SIZE,
                "document_parse_worker_concurrency": cls.DOCUMENT_PARSE_WORKER_CONCURRENCY,
                "document_parse_worker_max_attempts": cls.DOCUMENT_PARSE_WORKER_MAX_ATTEMPTS,
            },
            "agent_runtime": {
                "mode": cls.AGENT_RUNTIME_MODE,
                "base_url": cls.AGENT_RUNTIME_BASE_URL,
                "connect_timeout": cls.AGENT_RUNTIME_CONNECT_TIMEOUT,
                "read_timeout": cls.AGENT_RUNTIME_READ_TIMEOUT,
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
