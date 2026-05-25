"""
Milvus 服务模块

管理向量存储和检索

@author lvdaxianerplus
@date 2026-04-14
"""

from typing import List, Dict, Any, Union, Optional
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
from app.config import Config
from app.utils.logger import milvus_logger


class MilvusService:
    """Milvus 服务类"""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: str = None,
        dimension: int = None
    ):
        """
        初始化 Milvus 服务

        @param host - Milvus 主机
        @param port - Milvus 端口
        @param db - Milvus 数据库名
        @param dimension - 向量维度
        """
        self.host = host or Config.MILVUS_HOST
        self.port = port or Config.MILVUS_PORT
        self.db = db or Config.MILVUS_DB
        self.dimension = dimension or Config.EMBEDDING_DIMENSION
        self._client = None
        self._connect()

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
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port,
                db=self.db
            )
            # pymilvus 的 db 参数不总是生效，需要使用 reset_db_name 显式切换数据库
            conn = connections._fetch_handler("default")
            conn.reset_db_name(self.db)
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
        # 验证向量维度
        if len(vector) != self.dimension:
            raise ValueError(f"向量维度错误: 期望 {self.dimension}, 实际 {len(vector)}")

        # 获取带前缀的 collection 名称
        full_collection_name = self._get_full_collection_name(collection)

        # 确保 collection 存在
        await self.create_collection_if_not_exists(full_collection_name, has_features=features is not None)

        # 执行插入
        try:
            coll = Collection(full_collection_name)
            # 将 features 序列化为 JSON 字符串存储
            features_str = str(features) if features else "{}"
            data = [[doc_id], [description], [vector], [str(metadata)], [features_str]]

            result = coll.insert(data)
            coll.flush()

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
        # 参数校验：空列表或超限检查
        if not documents:
            return {"inserted_count": 0}
        if len(documents) > 1000:
            raise ValueError("批量插入数量超过上限 (1000)")

        # 获取带前缀的 collection 名称
        full_collection_name = self._get_full_collection_name(collection)

        # 检查是否有任何文档包含 features
        has_features = any("features" in doc and doc["features"] for doc in documents)

        # 确保 collection 存在
        await self.create_collection_if_not_exists(full_collection_name, has_features=has_features)

        # 执行批量插入
        try:
            data = self._prepare_batch_data(documents)
            coll = Collection(full_collection_name)
            result = coll.insert(data)
            coll.flush()
            return {"inserted_count": result.insert_count}
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
        metadatas = [str(doc.get("metadata", {})) for doc in documents]
        features_list = [str(doc.get("features", {})) for doc in documents]
        return [ids, descriptions, vectors, metadatas, features_list]

    async def search(
        self,
        collection: Union[str, List[str]],
        query_vector: List[float],
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        向量搜索

        @param collection - collection 名称或列表
        @param query_vector - 查询向量
        @param top_k - 返回数量
        @returns 搜索结果
        """
        if isinstance(collection, list):
            # 多 collection 并行搜索
            import asyncio
            tasks = [
                self._search_single(c, query_vector, top_k * 3)
                for c in collection
            ]
            results = await asyncio.gather(*tasks)
            # 合并结果
            merged = []
            for r in results:
                merged.extend(r)
            # 按 score 排序
            merged.sort(key=lambda x: x["score"], reverse=True)
            return merged[:top_k]
        else:
            return await self._search_single(collection, query_vector, top_k * 3)

    async def _search_single(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """单 collection 搜索"""
        # 获取带前缀的 collection 名称
        full_collection_name = self._get_full_collection_name(collection)

        # 确保 collection 存在
        await self.create_collection_if_not_exists(full_collection_name)

        try:
            coll = Collection(full_collection_name)
            coll.load()

            search_params = {"metric_type": "COSINE", "params": {}}
            results = coll.search(
                data=[query_vector],
                anns_field="vector",
                param=search_params,
                limit=top_k,
                output_fields=["id", "description", "metadata", "features"]
            )

            search_results = []
            for hits in results:
                for hit in hits:
                    # 解析 features 字段
                    features_str = hit.entity.get("features", "{}")
                    features = {}
                    try:
                        features = eval(features_str) if features_str else {}
                    except Exception:
                        features = {}

                    search_results.append({
                        "id": hit.entity.get("id"),
                        "description": hit.entity.get("description"),
                        "metadata": eval(hit.entity.get("metadata", "{}")),
                        "features": features,
                        "score": hit.score
                    })

            return search_results

        except Exception as e:
            milvus_logger.error("[Milvus] 搜索失败, error={}", str(e))
            return []

    async def delete(self, collection: str, doc_id: str) -> bool:
        """
        删除记录

        @param collection - collection 名称
        @param doc_id - 文档 ID
        @returns 是否删除成功
        """
        # 获取带前缀的 collection 名称
        full_collection_name = self._get_full_collection_name(collection)

        try:
            if not await self.collection_exists(full_collection_name):
                return False

            coll = Collection(full_collection_name)
            coll.delete(f'id == "{doc_id}"')
            coll.flush()

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
            return utility.has_collection(collection)
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

            # 如果有 features，添加 features 字段
            if has_features:
                fields.append(FieldSchema(name="features", dtype=DataType.VARCHAR, max_length=2000))

            schema = CollectionSchema(fields=fields, description="RAG Collection")
            coll = Collection(name=collection, schema=schema)

            # 创建索引
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            coll.create_index(field_name="vector", index_params=index_params)

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
            connections.connect(
                alias="health_check",
                host=self.host,
                port=self.port,
                db=self.db
            )
            connections.disconnect(alias="health_check")
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
