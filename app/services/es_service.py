"""
ES Service 模块

提供 Elasticsearch BM25 全文搜索功能

@author lvdaxianerplus
@date 2026-04-16
"""

from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError as ESConnectionError, NotFoundError
from app.config import Config
from app.utils.logger import rag_search_logger


class ESService:
    """
    ES 服务类

    提供 BM25 全文搜索、文档索引、删除等功能
    """

    def __init__(self):
        """
        初始化 ES 客户端
        """
        # 解析 host 和 port
        es_host = Config.ES_HOST
        if ":" in es_host:
            host, port = es_host.split(":")
        else:
            host = es_host
            port = 9200

        self.client = Elasticsearch(
            hosts=[{"host": host, "port": int(port), "scheme": Config.ES_SCHEME}],
            basic_auth=(Config.ES_USERNAME, Config.ES_PASSWORD),
            verify_certs=False,
            request_timeout=30
        )
        self._connected = False

    def is_connected(self) -> bool:
        """
        检查 ES 连接是否正常

        @returns 连接状态
        """
        try:
            return self.client.ping()
        except ESConnectionError:
            return False

    async def create_index_if_not_exists(self, index_name: str):
        """
        创建 BM25 索引（如果不存在）

        优先使用 IK 中文分词器，如果 IK 不可用则降级使用 standard 分词器

        @param index_name - 索引名称
        """
        if self.client.indices.exists(index=index_name):
            rag_search_logger.info(f"[ES] 索引已存在: {index_name}")
            return

        # 检查是否有 IK 分词器
        has_ik = self._check_ik_analyzer()

        if has_ik:
            rag_search_logger.info(f"[ES] 使用 IK 中文分词器创建索引: {index_name}")
            index_body = self._build_index_body_with_ik()
        else:
            rag_search_logger.warning(f"[ES] IK 分词器不可用，降级使用 standard 分词器: {index_name}")
            index_body = self._build_index_body_without_ik()

        self.client.indices.create(index=index_name, body=index_body)
        rag_search_logger.info(f"[ES] 索引创建成功: {index_name}")

    def _check_ik_analyzer(self) -> bool:
        """
        检查 IK 分词器是否可用

        @returns IK 分词器是否可用
        """
        try:
            # 尝试分析一个中文句子
            result = self.client.indices.analyze(
                body={"text": "测试中文分词", "analyzer": "ik_max_word"}
            )
            return True
        except Exception:
            return False

    def _build_index_body_with_ik(self) -> dict:
        """
        构建使用 IK 分词器的索引配置

        使用本地同义词文件（synonyms.txt）

        @returns 索引配置
        """
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "filter": {
                        "synonym_filter": {
                            "type": "synonym",
                            "synonyms_path": "synonyms.txt",
                            "updateable": True
                        }
                    },
                    "analyzer": {
                        "ik_max_word": {
                            "type": "custom",
                            "tokenizer": "ik_max_word",
                            "filter": ["lowercase"]
                        },
                        "ik_smart_synonym": {
                            "type": "custom",
                            "tokenizer": "ik_smart",
                            "filter": ["lowercase", "synonym_filter"]
                        },
                        "ik_max_word_synonym": {
                            "type": "custom",
                            "tokenizer": "ik_max_word",
                            "filter": ["lowercase", "synonym_filter"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "description": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart_synonym"
                    },
                    "description_en": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_max_word_synonym"
                    },
                    "collection": {"type": "keyword"},
                    "features": {"type": "object", "enabled": True},
                    "vector_id": {"type": "keyword"},
                    "metadata": {"type": "object", "enabled": True}
                }
            }
        }

    def _build_index_body_without_ik(self) -> dict:
        """
        构建不使用 IK 分词器的索引配置（降级方案）

        使用 ngram 和 standard 分词器作为替代

        @returns 索引配置
        """
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "default": {
                            "type": "standard",
                            "stopwords": "_english_"
                        },
                        "ngram_analyzer": {
                            "type": "custom",
                            "tokenizer": "ngram_tokenizer",
                            "filter": ["lowercase"]
                        }
                    },
                    "tokenizer": {
                        "ngram_tokenizer": {
                            "type": "ngram",
                            "min_gram": 2,
                            "max_gram": 4,
                            "token_chars": ["letter", "digit"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "description": {
                        "type": "text",
                        "analyzer": "default"
                    },
                    "description_en": {
                        "type": "text",
                        "analyzer": "default"
                    },
                    "lang": {"type": "keyword"},
                    "metadata": {
                        "type": "object",
                        "enabled": True
                    },
                    "features": {
                        "type": "object",
                        "enabled": True
                    }
                }
            }
        }

    async def index_document(
        self,
        index_name: str,
        doc_id: str,
        description: str,
        metadata: Dict[str, Any],
        lang: str = "zh",
        features: Dict[str, Any] = None
    ):
        """
        索引单个文档

        @param index_name - 索引名称
        @param doc_id - 文档ID
        @param description - 文档描述
        @param metadata - 元数据
        @param lang - 语言类型，"zh" 或 "en"
        @param features - 特征标签
        """
        # 根据语言选择存储字段
        doc_body = {
            "id": doc_id,
            "metadata": metadata
        }

        if lang == "zh":
            doc_body["description"] = description
            doc_body["lang"] = "zh"
        else:
            doc_body["description_en"] = description
            doc_body["lang"] = "en"

        # 添加 features
        if features:
            doc_body["features"] = features

        self.client.index(
            index=index_name,
            id=doc_id,
            body=doc_body
        )
        rag_search_logger.debug(f"[ES] 文档索引成功: {doc_id}, has_features={features is not None}")

    async def search(
        self,
        index_name: str,
        query: str,
        top_k: int,
        query_lang: str = "auto"
    ) -> List[Dict[str, Any]]:
        """
        BM25 搜索

        同时搜索 description 和 description_en 字段，确保跨语言召回

        @param index_name - 索引名称
        @param query - 查询文本
        @param top_k - 返回数量
        @param query_lang - 查询语言，"zh"、"en" 或 "auto"（当前未使用，保留扩展）
        @returns 搜索结果列表
        """
        # 同时搜索 description 和 description_en 两个字段
        # 以确保无论查询是中文还是英文，都能召回对应语言存储的文档
        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["description", "description_en"],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            },
            "size": top_k
        }

        try:
            result = self.client.search(index=index_name, body=body)
            hits = result.get("hits", {}).get("hits", [])

            return [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "description": hit["_source"].get("description") or hit["_source"].get("description_en", ""),
                    "metadata": hit["_source"].get("metadata", {}),
                    "features": hit["_source"].get("features", {})
                }
                for hit in hits
            ]
        except ESConnectionError as e:
            rag_search_logger.error(f"[ES] 连接失败: {e}")
            raise
        except Exception as e:
            rag_search_logger.error(f"[ES] 搜索失败: {e}")
            raise

    async def delete_document(self, index_name: str, doc_id: str) -> bool:
        """
        删除文档

        @param index_name - 索引名称
        @param doc_id - 文档ID
        @returns 是否删除成功
        """
        try:
            self.client.delete(index=index_name, id=doc_id)
            rag_search_logger.debug(f"[ES] 文档删除成功: {doc_id}")
            return True
        except NotFoundError:
            rag_search_logger.warning(f"[ES] 文档不存在: {doc_id}")
            return False
        except Exception as e:
            rag_search_logger.error(f"[ES] 删除失败: {e}")
            raise

    def _detect_language(self, text: str) -> str:
        """
        简单语言检测

        @param text - 待检测文本
        @returns "zh" 或 "en"
        """
        if self._contains_chinese(text):
            return "zh"
        return "en"

    def _contains_chinese(self, text: str) -> bool:
        """
        检查是否包含中文

        @param text - 待检查文本
        @returns 是否包含中文
        """
        return any("\u4e00" <= char <= "\u9fff" for char in text)


# 全局单例
_es_service: Optional[ESService] = None


def get_es_service() -> ESService:
    """
    获取 ES 服务单例

    @returns ESService 实例
    """
    global _es_service
    if _es_service is None:
        _es_service = ESService()
    return _es_service
