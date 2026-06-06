"""
Pydantic 数据模型

定义请求和响应的数据模型

@author lvdaxianerplus
@date 2026-04-14
"""

from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, Field


# =============================================================================
# 元数据模型
# =============================================================================

class Metadata(BaseModel):
    """元数据模型"""
    type: str = Field(..., description="资源类型，决定存储到哪个 collection")
    id: str = Field(..., description="业务唯一标识")
    description: str = Field(..., description="资源描述")


# =============================================================================
# 插入请求模型
# =============================================================================

class InsertRequest(BaseModel):
    """单条插入请求模型"""
    description: str = Field(..., description="需要向量化的描述文本", min_length=1, max_length=10000)
    metadata: Metadata = Field(..., description="附加元信息")


class InsertItem(BaseModel):
    """批量插入单项"""
    description: str = Field(..., description="需要向量化的描述文本", min_length=1, max_length=10000)
    metadata: Metadata = Field(..., description="附加元信息")


class BatchInsertRequest(BaseModel):
    """批量插入请求模型"""
    items: List[InsertItem] = Field(..., description="批量插入项列表", min_length=1, max_length=1000)


# =============================================================================
# 检索请求模型
# =============================================================================

class SearchRequest(BaseModel):
    """检索请求模型"""
    input: str = Field(..., description="用户语义输入", min_length=1)
    type: Optional[str] = Field("all", description="资源类型，默认 all")
    topK: Optional[int] = Field(20, description="返回数量，默认 20", ge=1, le=1000)
    threshold: Optional[float] = Field(None, description="相似度阈值，默认使用配置值", ge=0.0, le=1.0)
    enableFeatureBoost: Optional[bool] = Field(False, description="是否启用特征加权")
    query_scope: Optional[Literal["local", "global", "hybrid"]] = Field(None, description="查询范围识别结果")
    route_plan: List[str] = Field(default_factory=list, description="检索路由计划摘要")
    issue_type: Optional[str] = Field(None, description="问题类型")
    issue_route: Dict[str, Any] = Field(default_factory=dict, description="问题类型路由结果")
    issue_filters: Dict[str, Any] = Field(default_factory=dict, description="问题类型过滤条件")


# =============================================================================
# 删除请求模型
# =============================================================================

class DeleteRequest(BaseModel):
    """删除请求模型"""
    type: str = Field(..., description="资源类型")
    id: str = Field(..., description="业务唯一标识")


# =============================================================================
# 响应模型
# =============================================================================

class InsertResponse(BaseModel):
    """单条插入响应模型"""
    id: str = Field(..., description="插入成功的业务 ID")
    collection: str = Field(..., description="所属 collection 名称")
    features: Optional[dict] = Field(None, description="提取的特征标签，包含 category 和 tags")


class BatchInsertResponse(BaseModel):
    """批量插入响应模型"""
    inserted_count: int = Field(..., description="成功插入的数量")


class SearchResult(BaseModel):
    """检索结果项"""
    metadata: dict = Field(..., description="原始 metadata 信息")
    description: str = Field(..., description="原始描述文本")
    score: float = Field(..., description="Rerank 分数")
    features: Optional[dict] = Field(None, description="特征标签，包含 category 和 tags")
    score_trace: Optional[dict] = Field(None, description="候选级检索分数追踪")


class RecommendationResult(SearchResult):
    """推荐结果项"""
    reason: str = Field("", description="推荐原因")
    kind: Literal["document", "topic"] = Field("document", description="推荐类型")
    topic_path: List[str] = Field(default_factory=list, description="主题路径")
    follow_up_question: Optional[str] = Field(None, description="建议继续追问的问题")


class SearchResponse(BaseModel):
    """检索响应模型"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="状态消息")
    data: List[SearchResult] = Field(default_factory=list, description="结果列表")


class OptimizeSearchRequest(BaseModel):
    """语义优化检索请求模型"""
    input: str = Field(..., description="原始用户查询", min_length=1)
    type: Optional[str] = Field("all", description="资源类型，默认 all")
    topK: Optional[int] = Field(20, description="返回数量，默认 20", ge=1, le=1000)
    threshold: Optional[float] = Field(None, description="相似度阈值", ge=0.0, le=1.0)
    enableFeatureBoost: Optional[bool] = Field(False, description="是否启用特征加权")


class OptimizeSearchData(BaseModel):
    """语义优化检索响应数据模型"""
    request_id: str = Field(..., description="本次优化检索请求 ID，可用于撤销该请求关联的 Rerank 缓存")
    original_query: str = Field(..., description="原始查询")
    optimized_query: str = Field(..., description="优化后查询")
    intent: Optional[str] = Field(None, description="识别出的查询意图")
    query_scope: Optional[Literal["local", "global", "hybrid"]] = Field(None, description="查询范围识别结果")
    route_plan: Dict[str, Any] = Field(default_factory=dict, description="检索路由计划摘要")
    issue_type: Optional[str] = Field(None, description="问题类型")
    issue_route: Dict[str, Any] = Field(default_factory=dict, description="问题类型路由结果")
    issue_filters: Dict[str, Any] = Field(default_factory=dict, description="问题类型过滤条件")
    cot_plan: List[str] = Field(default_factory=list, description="CoT 风格的可解释检索计划摘要")
    expanded_queries: List[str] = Field(default_factory=list, description="扩展查询列表")
    see_trace: List[dict] = Field(default_factory=list, description="SEE 可视化查询过程追踪")
    original_results: List[SearchResult] = Field(default_factory=list, description="原始查询结果")
    optimized_results: List[SearchResult] = Field(default_factory=list, description="优化后查询结果")
    recommendations: List[RecommendationResult] = Field(default_factory=list, description="相关推荐结果")
    comparison: dict = Field(default_factory=dict, description="两次检索对比")
    fallback_used: bool = Field(False, description="是否使用降级结果")


class OptimizeSearchResponse(BaseModel):
    """语义优化检索响应模型"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="状态消息")
    data: OptimizeSearchData = Field(..., description="优化检索数据")


class EvaluationRecordRequest(BaseModel):
    """检索评测记录请求模型"""
    query: str = Field(..., description="原始查询", min_length=1)
    optimized_query: Optional[str] = Field(None, description="优化后的查询")
    retrieved_ids: List[str] = Field(default_factory=list, description="检索返回的业务 ID 列表")
    miss_reason: Literal[
        "intent_error",
        "recall_miss",
        "rerank_error",
        "generation_error",
        "stale_knowledge",
        "unknown"
    ] = Field("unknown", description="未命中或效果差原因")
    human_label: Optional[str] = Field(None, description="人工评测标签")
    request_id: Optional[str] = Field(None, description="关联优化检索 request_id")


class DeleteResponse(BaseModel):
    """删除响应模型"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="状态消息")
    data: Optional[dict] = Field(None, description="删除结果")


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str = Field(..., description="服务状态")
    services: dict = Field(..., description="各服务状态")


# =============================================================================
# API 响应包装
# =============================================================================

class APIResponse(BaseModel):
    """通用 API 响应"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="状态消息")
    data: Optional[Any] = Field(None, description="响应数据")


# =============================================================================
# 高精度 RAG 问答模型
# =============================================================================

class QueryFilters(BaseModel):
    """查询过滤条件"""
    doc_type: Optional[str] = Field(None, description="文档类型过滤")
    date_range: Optional[dict] = Field(None, description="时间范围过滤")
    department: Optional[str] = Field(None, description="部门过滤")


class QueryOptions(BaseModel):
    """查询选项"""
    use_hyde: Optional[bool] = Field(False, description="是否启用 HyDE")
    use_rewrite: Optional[bool] = Field(True, description="是否启用查询改写")
    use_decompose: Optional[bool] = Field(False, description="是否启用问题分解")
    use_validation: Optional[bool] = Field(True, description="是否启用 Faithfulness 验证")
    top_k: Optional[int] = Field(5, description="最终返回的 chunk 数量", ge=1, le=20)
    rerank_threshold: Optional[float] = Field(0.3, description="Rerank 阈值", ge=0.0, le=1.0)
    search_type: Optional[str] = Field("all", description="检索类型")


class QueryRequest(BaseModel):
    """高精度 RAG 问答请求"""
    query: str = Field(..., description="用户问题", min_length=1)
    filters: Optional[QueryFilters] = Field(None, description="过滤条件")
    options: Optional[QueryOptions] = Field(None, description="查询选项")


class CitationItem(BaseModel):
    """引用项"""
    index: int = Field(..., description="引用编号")
    chunk_id: str = Field(..., description="chunk ID")
    source: str = Field(..., description="来源文档")
    page: Optional[int] = Field(None, description="页码")
    section: Optional[str] = Field(None, description="章节")
    content: str = Field(..., description="原文片段（前200字）")
    relevance_score: float = Field(..., description="相关性分数")


class QueryResponse(BaseModel):
    """高精度 RAG 问答响应"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="状态消息")
    answer: str = Field(..., description="生成的答案")
    citations: List[CitationItem] = Field(default_factory=list, description="引用列表")
    faithfulness_score: Optional[float] = Field(None, description="答案忠实度分数")
    latency_ms: Optional[int] = Field(None, description="端到端延迟（毫秒）")
