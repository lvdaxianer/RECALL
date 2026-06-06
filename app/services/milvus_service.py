"""
Milvus 服务模块

管理向量存储和检索

@author lvdaxianerplus
@date 2026-04-14
"""

from typing import List, Dict, Any, Union
from pymilvus import CollectionSchema, DataType, FieldSchema, MilvusClient
from app.config import Config
from app.services.milvus_serialization import dump_stored_dict, parse_stored_dict
from app.utils.logger import milvus_logger


class MilvusService:
    """Milvus 服务类"""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
        db: str = None,
        dimension: int = None
    ):
        """
        初始化 Milvus 服务

        @param host - Milvus 主机
        @param port - Milvus 端口
        @param username - Milvus 用户名
        @param password - Milvus 密码
        @param db - Milvus 数据库名
        @param dimension - 向量维度
        """
        self.host = host or Config.MILVUS_HOST
        self.port = port or Config.MILVUS_PORT
        self.username = username if username is not None else Config.MILVUS_USERNAME
        self.password = password if password is not None else Config.MILVUS_PASSWORD
        self.db = db or Config.MILVUS_DB
        self.dimension = dimension or Config.EMBEDDING_DIMENSION
        self._client = None
        self._loaded_collections = set()
        self._connect()

    def _client_kwargs(self) -> Dict[str, Any]:
        """
        构建 MilvusClient 连接参数

        @returns Milvus 连接参数
        """
        kwargs = {
            "uri": f"http://{self.host}:{self.port}",
        }
        if self.username:
            kwargs["user"] = self.username
            kwargs["password"] = self.password
        return kwargs

    def _get_full_collection_name(self, collection: str) -> str:
        """
        获取带前缀的 collection 名称

        Milvus collections 是全局的，不按数据库隔离。
        为了区分不同项目的数据，使用 db 前缀作为 collection 名称的前缀。

        @param collection - 原始 collection 名称
        @returns 带前缀的 collection 名称
        """
        return f"{self.db}_{collection}"

    def _connect(self):
        """建立 Milvus 连接"""
        try:
            self._client = MilvusClient(**self._client_kwargs())
        except Exception as e:
            milvus_logger.error("[Milvus] 连接失败, error={}", str(e))
            raise

    async def insert(
        self,
        collection: str,
        doc_id: str,
        description: str,
        vector: List[float],
        metadata: Dict[str, Any],
        features: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        插入单条记录

        @param collection - collection 名称
        @param doc_id - 文档 ID
        @param description - 描述文本
        @param vector - 向量
        @param metadata - 元数据
        @param features - 特征标签
        @returns 插入结果
        """
        if len(vector) != self.dimension:
            raise ValueError(f"向量维度错误: 期望 {self.dimension}, 实际 {len(vector)}")

        full_collection_name = self._get_full_collection_name(collection)
        await self.create_collection_if_not_exists(full_collection_name, has_features=features is not None)

        try:
            features_str = dump_stored_dict(features)
            metadata_str = dump_stored_dict(metadata)
            self._client.insert(
                collection_name=full_collection_name,
                data=[{
                    "id": doc_id,
                    "description": description,
                    "vector": vector,
                    "metadata": metadata_str,
                    "features": features_str,
                }]
            )
            self._flush_collection(full_collection_name)
            self._load_collection_once(full_collection_name)

            milvus_logger.info("[Milvus] 插入成功, doc_id={}, has_features={}", doc_id, features is not None)

            return {"id": doc_id, "collection": full_collection_name, "features": features}

        except Exception as e:
            milvus_logger.error("[Milvus] 插入失败, doc_id={}, error={}", doc_id, str(e))
            raise

    async def batch_insert(
        self,
        collection: str,
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量插入记录

        @param collection - collection 名称
        @param documents - 文档列表
        @returns 插入结果
        """
        if not documents:
            return {"inserted_count": 0}
        if len(documents) > 1000:
            raise ValueError("批量插入数量超过上限 (1000)")

        full_collection_name = self._get_full_collection_name(collection)
        has_features = any("features" in doc and doc["features"] for doc in documents)
        await self.create_collection_if_not_exists(full_collection_name, has_features=has_features)

        try:
            data = self._prepare_batch_rows(documents)
            result = self._client.insert(collection_name=full_collection_name, data=data)
            self._flush_collection(full_collection_name)
            self._load_collection_once(full_collection_name)
            return {"inserted_count": self._extract_insert_count(result, len(documents))}
        except Exception as e:
            milvus_logger.error("[Milvus] 批量插入失败, error={}", str(e))
            raise

    def _prepare_batch_data(self, documents: List[Dict[str, Any]]) -> List[List]:
        """
        准备批量插入数据

        @param documents - 文档列表
        @returns 批量插入数据格式
        """
        ids = [doc["id"] for doc in documents]
        descriptions = [doc["description"] for doc in documents]
        vectors = [doc["vector"] for doc in documents]
        metadatas = [
            dump_stored_dict(doc.get("metadata", {}))
            for doc in documents
        ]
        features_list = [
            dump_stored_dict(doc.get("features", {}))
            for doc in documents
        ]
        return [ids, descriptions, vectors, metadatas, features_list]

    def _prepare_batch_rows(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """准备 MilvusClient 批量插入行数据。"""
        return [
            {
                "id": doc["id"],
                "description": doc["description"],
                "vector": doc["vector"],
                "metadata": dump_stored_dict(doc.get("metadata", {})),
                "features": dump_stored_dict(doc.get("features", {})),
            }
            for doc in documents
        ]

    async def search(
        self,
        collection: Union[str, List[str]],
        query_vector: List[float],
        top_k: int = 20,
        metadata_filter: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """
        向量搜索

        @param collection - collection 名称或列表
        @param query_vector - 查询向量
        @param top_k - 返回数量
        @returns 搜索结果
        """
        if isinstance(collection, list):
            import asyncio
            tasks = [
                self._search_single(c, query_vector, top_k * 3, metadata_filter)
                for c in collection
            ]
            results = await asyncio.gather(*tasks)
            merged = []
            for r in results:
                merged.extend(r)
            merged.sort(key=lambda x: x["score"], reverse=True)
            return merged[:top_k]
        else:
            return await self._search_single(collection, query_vector, top_k * 3, metadata_filter)

    async def _search_single(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int,
        metadata_filter: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """单 collection 搜索"""
        full_collection_name = self._get_full_collection_name(collection)
        await self.create_collection_if_not_exists(full_collection_name)

        try:
            return self._search_loaded_collection(full_collection_name, query_vector, top_k, metadata_filter)

        except Exception as e:
            milvus_logger.warning("[Milvus] 搜索失败，尝试重连重试一次, error={}", str(e))
            try:
                self._reconnect()
                await self.create_collection_if_not_exists(full_collection_name)
                return self._search_loaded_collection(full_collection_name, query_vector, top_k, metadata_filter)
            except Exception as retry_error:
                milvus_logger.error("[Milvus] 搜索重试失败, error={}", str(retry_error))
                return []

    async def score_documents_by_ids(
        self,
        collection: str,
        query_vector: List[float],
        doc_ids: List[str],
    ) -> Dict[str, float]:
        """按 ID 批量获取候选相对查询向量的 Milvus 分数。"""
        if not doc_ids:
            return {}

        full_collection_name = self._get_full_collection_name(collection)
        await self.create_collection_if_not_exists(full_collection_name)
        self._load_collection_once(full_collection_name)

        results = self._client.search(
            collection_name=full_collection_name,
            data=[query_vector],
            anns_field="vector",
            search_params={"metric_type": "COSINE", "params": {}},
            limit=len(doc_ids),
            filter=self._build_id_filter(doc_ids),
            output_fields=["id"],
        )
        scores: Dict[str, float] = {}
        for hits in results:
            for hit in hits:
                doc_id = self._extract_hit_id(hit)
                if doc_id:
                    scores[doc_id] = float(hit.get("distance", hit.get("score", 0)) if isinstance(hit, dict) else hit.score)
        return scores

    async def delete(self, collection: str, doc_id: str) -> bool:
        """
        删除记录

        @param collection - collection 名称
        @param doc_id - 文档 ID
        @returns 是否删除成功
        """
        full_collection_name = self._get_full_collection_name(collection)

        try:
            if not await self.collection_exists(full_collection_name):
                return False

            self._client.delete(collection_name=full_collection_name, filter=f'id == "{doc_id}"')
            self._flush_collection(full_collection_name)

            return True

        except Exception as e:
            milvus_logger.error("[Milvus] 删除失败, error={}", str(e))
            return False

    async def collection_exists(self, collection: str) -> bool:
        """
        检查 collection 是否存在

        @param collection - collection 名称（已带前缀）
        @returns 是否存在
        """
        try:
            return self._client.has_collection(collection)
        except Exception:
            return False

    async def create_collection_if_not_exists(self, collection: str, has_features: bool = False):
        """如果 collection 不存在则创建"""
        if not await self.collection_exists(collection):
            await self.create_collection(collection, has_features=has_features)

    async def create_collection(self, collection: str, has_features: bool = False) -> bool:
        """
        创建 collection

        @param collection - collection 名称（已带前缀）
        @param has_features - 是否包含 features 字段
        @returns 是否创建成功
        """
        try:
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=256, is_primary=True),
                FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=10000),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self.dimension),
                FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=5000)
            ]

            if has_features:
                fields.append(FieldSchema(name="features", dtype=DataType.VARCHAR, max_length=2000))

            schema = CollectionSchema(fields=fields, description="RAG Collection")

            index_params = MilvusClient.prepare_index_params(
                field_name="vector",
                index_type="IVF_FLAT",
                metric_type="COSINE",
                params={"nlist": 128},
            )
            self._client.create_collection(
                collection_name=collection,
                schema=schema,
                index_params=index_params,
            )
            self._loaded_collections.discard(collection)

            milvus_logger.info("[Milvus] Collection 创建成功, name={}, has_features={}", collection, has_features)

            return True

        except Exception as e:
            milvus_logger.error("[Milvus] Collection 创建失败, error={}", str(e))
            raise

    async def health_check(self) -> bool:
        """
        健康检查

        @returns 服务是否可用
        """
        try:
            self._client.has_collection("__health_check__")
            return True
        except Exception:
            return False

    def _validate_dimension(self, vector: List[float]) -> None:
        """
        验证向量维度

        @param vector - 向量数据
        @raises ValueError - 当向量维度不匹配时抛出

        Author: lvdaxianerplus
        Date: 2026-04-14
        """
        if len(vector) != self.dimension:
            raise ValueError(f"向量维度错误: 期望 {self.dimension}, 实际 {len(vector)}")

    def _load_collection_once(self, collection: str) -> None:
        """
        按服务实例缓存已 load 的 collection，避免每次查询重复加载。

        @param collection - 带前缀的 collection 名称
        """
        if collection in self._loaded_collections:
            return
        self._client.load_collection(collection)
        self._loaded_collections.add(collection)

    def _reconnect(self) -> None:
        """重建 MilvusClient 连接，并清空实例级 collection load 缓存。"""
        self._connect()
        self._loaded_collections.clear()

    def _search_loaded_collection(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int,
        metadata_filter: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """执行已确认 collection 的 Milvus 搜索。"""
        self._load_collection_once(collection)
        search_params = {"metric_type": "COSINE", "params": {}}
        filter_expression = self._build_metadata_filter(metadata_filter)
        results = self._client.search(
            collection_name=collection,
            data=[query_vector],
            anns_field="vector",
            search_params=search_params,
            limit=top_k,
            output_fields=self._build_search_output_fields(),
            filter=filter_expression,
        )

        search_results = []
        for hits in results:
            for hit in hits:
                search_results.append(self._parse_search_hit(hit))
        return search_results

    def _flush_collection(self, collection: str) -> None:
        """MilvusClient flush 兼容封装。"""
        flush = getattr(self._client, "flush", None)
        if callable(flush):
            flush(collection)

    def _extract_insert_count(self, result: Any, fallback_count: int) -> int:
        """从 MilvusClient 插入结果中提取数量。"""
        if isinstance(result, dict):
            return result.get("insert_count") or result.get("inserted_count") or fallback_count
        return getattr(result, "insert_count", fallback_count)

    def _parse_search_hit(self, hit: Any) -> Dict[str, Any]:
        """解析 MilvusClient 搜索结果。"""
        if isinstance(hit, dict):
            entity = hit.get("entity", {}) or {}
            return {
                "id": entity.get("id", hit.get("id")),
                "description": entity.get("description", ""),
                "metadata": parse_stored_dict(entity.get("metadata", "{}")),
                "features": parse_stored_dict(entity.get("features", "{}")),
                "score": hit.get("distance", hit.get("score", 0)),
            }

        entity = hit.entity
        return {
            "id": entity.get("id"),
            "description": entity.get("description"),
            "metadata": parse_stored_dict(entity.get("metadata", "{}")),
            "features": parse_stored_dict(entity.get("features", "{}")),
            "score": hit.score
        }

    def _build_search_output_fields(self) -> List[str]:
        """构建搜索输出字段，不包含 embedding/vector。"""
        return ["id", "description", "metadata", "features"]

    def _build_id_filter(self, doc_ids: List[str]) -> str:
        """构建 Milvus id 批量过滤表达式。"""
        quoted_ids = ", ".join(f'"{doc_id}"' for doc_id in doc_ids)
        return f"id in [{quoted_ids}]"

    def _build_metadata_filter(self, metadata_filter: Dict[str, Any] | None) -> str:
        """构建 Milvus metadata 字符串过滤表达式。"""
        if not metadata_filter:
            return ""

        clauses: List[str] = []
        knowledge_base_ids = metadata_filter.get("knowledge_base_ids") or []
        if knowledge_base_ids:
            kb_clauses = [
                self._metadata_like_clause("knowledge_base_id", kb_id)
                for kb_id in knowledge_base_ids
            ]
            clauses.append(f"({' or '.join(kb_clauses)})")
        document_id = metadata_filter.get("document_id")
        if document_id:
            clauses.append(self._metadata_like_clause("document_id", document_id))
        return " and ".join(clauses)

    def _metadata_like_clause(self, key: str, value: str) -> str:
        """构建单个 metadata like 子句。"""
        compact_pattern = f'%\\"{key}\\":\\"{value}\\"%'
        spaced_pattern = f'%\\"{key}\\": \\"{value}\\"%'
        return f'(metadata like "{compact_pattern}" or metadata like "{spaced_pattern}")'

    def _extract_hit_id(self, hit: Any) -> str:
        """从 Milvus hit 中提取文档 ID。"""
        if isinstance(hit, dict):
            entity = hit.get("entity", {}) or {}
            return entity.get("id") or hit.get("id")
        return hit.entity.get("id")
