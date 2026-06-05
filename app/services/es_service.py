"""
ES Service 模块

提供 Elasticsearch BM25 全文搜索功能

@author lvdaxianerplus
@date 2026-04-16
"""

from typing import List, Dict, Any, Optional
import httpx
from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import (
    ConnectionError as ESConnectionError,
    NotFoundError,
    UnsupportedProductError
)
from app.config import Config
from app.services.es_http_compat_client import ESHttpCompatClient
from app.services.es_index_config import (
    build_index_body_with_ik,
    build_index_body_without_ik
)
from app.services.ragflow_query_builder import build_weighted_es_query
from app.services.ragflow_query_builder import metadata_filter_field
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
        self.base_url = f"{Config.ES_SCHEME}://{host}:{port}"

        self.client = Elasticsearch(
            hosts=[{"host": host, "port": int(port), "scheme": Config.ES_SCHEME}],
            basic_auth=(Config.ES_USERNAME, Config.ES_PASSWORD),
            verify_certs=Config.ES_VERIFY_CERTS,
            request_timeout=30
        )
        self._connected = False
        self._using_http_compat = False

    def _switch_to_http_compat_client(self) -> bool:
        """切换到 HTTP 兼容客户端。"""
        rag_search_logger.warning("[ES] 官方客户端产品校验失败，切换 HTTP 兼容客户端")
        self.client = ESHttpCompatClient(
            base_url=self.base_url,
            username=Config.ES_USERNAME,
            password=Config.ES_PASSWORD
        )
        self._using_http_compat = True
        return self.client.ping()

    def _ensure_compatible_client(self) -> None:
        """确保当前客户端可用于真实 ES 服务。"""
        if self._using_http_compat:
            return
        try:
            if not self.client.ping():
                self.client.info()
        except UnsupportedProductError:
            self._switch_to_http_compat_client()

    def is_connected(self) -> bool:
        """
        检查 ES 连接是否正常

        @returns 连接状态
        """
        try:
            if self.client.ping():
                return True
            self.client.info()
            return True
        except UnsupportedProductError:
            return self._switch_to_http_compat_client()
        except (ESConnectionError, httpx.HTTPError):
            return False

    async def create_index_if_not_exists(self, index_name: str):
        """
        创建 BM25 索引（如果不存在）

        优先使用 IK 中文分词器，如果 IK 不可用则降级使用 standard 分词器

        @param index_name - 索引名称
        """
        self._ensure_compatible_client()
        if self.client.indices.exists(index=index_name):
            rag_search_logger.info("[ES] 索引已存在: {}", index_name)
            return

        # 检查是否有 IK 分词器
        has_ik = self._check_ik_analyzer()

        if has_ik:
            rag_search_logger.info("[ES] 使用 IK 中文分词器创建索引: {}", index_name)
            index_body = build_index_body_with_ik()
        else:
            rag_search_logger.warning("[ES] IK 分词器不可用，降级使用 standard 分词器: {}", index_name)
            index_body = build_index_body_without_ik()

        try:
            self.client.indices.create(index=index_name, body=index_body)
        except Exception:
            if not has_ik:
                raise
            rag_search_logger.warning("[ES] IK 同义词索引创建失败，降级使用 standard 分词器: {}", index_name)
            self.client.indices.create(index=index_name, body=build_index_body_without_ik())
        rag_search_logger.info("[ES] 索引创建成功: {}", index_name)

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
        self._ensure_compatible_client()
        doc_body = self._build_document_body(doc_id, description, metadata, lang, features)
        self.client.index(
            index=index_name,
            id=doc_id,
            body=doc_body
        )
        rag_search_logger.debug("[ES] 文档索引成功: {}, has_features={}", doc_id, features is not None)

    async def index_documents(self, index_name: str, documents: List[Dict[str, Any]]) -> int:
        """
        批量索引文档

        @param index_name - 索引名称
        @param documents - 文档列表
        @returns 成功写入数量
        """
        if not documents:
            return 0

        self._ensure_compatible_client()
        if self._using_http_compat:
            for document in documents:
                await self.index_document(
                    index_name=index_name,
                    doc_id=document["doc_id"],
                    description=document["description"],
                    metadata=document["metadata"],
                    lang=document.get("lang", "zh"),
                    features=document.get("features")
                )
            return len(documents)

        actions = [
            {
                "_op_type": "index",
                "_index": index_name,
                "_id": document["doc_id"],
                "_source": self._build_document_body(
                    doc_id=document["doc_id"],
                    description=document["description"],
                    metadata=document["metadata"],
                    lang=document.get("lang", "zh"),
                    features=document.get("features")
                )
            }
            for document in documents
        ]
        success_count, _ = helpers.bulk(self.client, actions)
        rag_search_logger.debug("[ES] 批量索引成功: index={}, count={}", index_name, success_count)
        return success_count

    def _build_document_body(
        self,
        doc_id: str,
        description: str,
        metadata: Dict[str, Any],
        lang: str = "zh",
        features: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构建 ES 文档体

        @param doc_id - 文档ID
        @param description - 文档描述
        @param metadata - 元数据
        @param lang - 语言类型
        @param features - 特征标签
        @returns ES 文档体
        """
        doc_body = {"id": doc_id, "metadata": metadata}
        if lang == "zh":
            doc_body["description"] = description
            doc_body["lang"] = "zh"
        else:
            doc_body["description_en"] = description
            doc_body["lang"] = "en"

        if features:
            doc_body["features"] = features
        if metadata.get("parent_id"):
            doc_body["parent_id"] = metadata["parent_id"]
        if metadata.get("section_title"):
            doc_body["section_title"] = metadata["section_title"]
        doc_body.update(self._build_ragflow_compatible_fields(description, metadata, features))
        return doc_body

    def _build_ragflow_compatible_fields(
        self,
        description: str,
        metadata: Dict[str, Any],
        features: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """构建兼容 RAGFlow 字段权重查询的富字段。"""
        features = features or {}
        title = features.get("title") or metadata.get("title") or metadata.get("description") or ""
        category = features.get("category")
        tags = features.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        important_keywords = [value for value in [category, *tags] if value]
        questions = features.get("questions") or []
        if not isinstance(questions, list):
            questions = [str(questions)]

        return {
            "title_tks": title,
            "title_sm_tks": title,
            "important_kwd": important_keywords,
            "important_tks": " ".join(important_keywords),
            "question_tks": " ".join(str(question) for question in questions if question),
            "content_ltks": description,
            "content_sm_ltks": description,
            "content_with_weight": description,
        }

    async def search(
        self,
        index_name: str,
        query: str,
        top_k: int,
        query_lang: str = "auto",
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        BM25 搜索

        同时搜索 description 和 description_en 字段，确保跨语言召回

        @param index_name - 索引名称
        @param query - 查询文本
        @param top_k - 返回数量
        @param query_lang - 查询语言，"zh"、"en" 或 "auto"（当前未使用，保留扩展）
        @param metadata_filter - metadata 字段过滤条件
        @returns 搜索结果列表
        """
        # 同时搜索 description 和 description_en 两个字段
        # 以确保无论查询是中文还是英文，都能召回对应语言存储的文档
        query_body: Dict[str, Any] = {
            "multi_match": {
                "query": query,
                "fields": ["description", "description_en"],
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        }
        if metadata_filter:
            query_body = {
                "bool": {
                    "must": query_body,
                    "filter": self._build_metadata_filters(metadata_filter)
                }
            }
        body = {
            "query": query_body,
            "size": top_k
        }

        try:
            self._ensure_compatible_client()
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
            rag_search_logger.error("[ES] 连接失败: {}", str(e))
            raise
        except Exception as e:
            rag_search_logger.error("[ES] 搜索失败: {}", str(e))
            raise

    async def search_weighted(
        self,
        index_name: str,
        query: str,
        top_k: int,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """执行 RAGFlow-inspired 字段加权文本搜索。"""
        body = build_weighted_es_query(query, top_k, metadata_filter)
        try:
            self._ensure_compatible_client()
            result = self.client.search(index=index_name, body=body)
            hits = result.get("hits", {}).get("hits", [])
            return [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "description": hit["_source"].get("description") or hit["_source"].get("description_en", ""),
                    "metadata": hit["_source"].get("metadata", {}),
                    "features": hit["_source"].get("features", {}),
                    "source_scores": {"text": hit["_score"]},
                }
                for hit in hits
            ]
        except ESConnectionError as e:
            rag_search_logger.error("[ES] weighted 搜索连接失败: {}", str(e))
            raise
        except Exception as e:
            rag_search_logger.error("[ES] weighted 搜索失败: {}", str(e))
            raise

    async def search_parent_contexts(
        self,
        index_name: str,
        parent_ids: List[str],
        section_ids: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """按父文档/章节批量读取上下文 chunk。"""
        filters: List[Dict[str, Any]] = []
        if parent_ids:
            filters.append({"terms": {"metadata.parent_id.keyword": parent_ids}})
        if section_ids:
            filters.append({"terms": {"metadata.section_id.keyword": section_ids}})
        if not filters:
            return []

        body = {
            "query": {
                "bool": {
                    "filter": filters
                }
            },
            "size": limit
        }

        try:
            self._ensure_compatible_client()
            result = self.client.search(index=index_name, body=body)
            hits = result.get("hits", {}).get("hits", [])
            return [
                {
                    "id": hit["_id"],
                    "score": hit.get("_score", 0),
                    "description": hit["_source"].get("description") or hit["_source"].get("description_en", ""),
                    "metadata": hit["_source"].get("metadata", {}),
                    "features": hit["_source"].get("features", {})
                }
                for hit in hits
            ]
        except NotFoundError:
            rag_search_logger.warning("[ES] 索引不存在，无法读取父上下文: {}", index_name)
            return []
        except ESConnectionError as e:
            rag_search_logger.error("[ES] 父上下文查询连接失败: {}", str(e))
            raise
        except Exception as e:
            rag_search_logger.error("[ES] 父上下文查询失败: {}", str(e))
            raise

    def _build_metadata_filters(self, metadata_filter: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        构建 metadata 字段过滤条件

        @param metadata_filter - metadata 字段过滤键值
        @returns ES bool.filter 条件列表
        """
        filters = []
        for key, value in metadata_filter.items():
            if value is None:
                continue
            filters.append({"term": {metadata_filter_field(key, value): value}})
        return filters

    async def list_documents(self, index_name: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        列出索引内文档

        用于从 ES 重建轻量图谱索引。

        @param index_name - 索引名称
        @param limit - 返回数量上限
        @returns 标准化文档列表
        """
        body = {
            "query": {"match_all": {}},
            "size": limit
        }

        try:
            self._ensure_compatible_client()
            result = self.client.search(index=index_name, body=body)
            hits = result.get("hits", {}).get("hits", [])
            return [
                {
                    "id": hit["_id"],
                    "description": hit["_source"].get("description") or hit["_source"].get("description_en", ""),
                    "metadata": hit["_source"].get("metadata", {}),
                    "features": hit["_source"].get("features", {})
                }
                for hit in hits
            ]
        except NotFoundError:
            rag_search_logger.warning("[ES] 索引不存在，无法列出文档: {}", index_name)
            return []
        except ESConnectionError as e:
            rag_search_logger.error("[ES] 连接失败: {}", str(e))
            raise
        except Exception as e:
            rag_search_logger.error("[ES] 列出文档失败: {}", str(e))
            raise

    async def delete_document(self, index_name: str, doc_id: str) -> bool:
        """
        删除文档

        @param index_name - 索引名称
        @param doc_id - 文档ID
        @returns 是否删除成功
        """
        try:
            self._ensure_compatible_client()
            self.client.delete(index=index_name, id=doc_id)
            rag_search_logger.debug("[ES] 文档删除成功: {}", doc_id)
            return True
        except NotFoundError:
            rag_search_logger.warning("[ES] 文档不存在: {}", doc_id)
            return False
        except Exception as e:
            rag_search_logger.error("[ES] 删除失败: {}", str(e))
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
