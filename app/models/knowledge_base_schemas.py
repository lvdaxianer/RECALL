"""
知识库 Retrieval SDK 数据模型

定义知识库、文档录入、chunk 与检索 SDK 的外部契约。

Author: lvdaxianerplus
Date: 2026-06-03
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ALLOWED_DOCUMENT_CONTENT_TYPES = {"text/plain", "text/markdown"}
ALLOWED_DUPLICATE_POLICIES = {"upsert", "reject", "versioned"}


class KnowledgeBaseCreateRequest(BaseModel):
    """知识库创建请求模型。"""

    name: str = Field(..., min_length=1, max_length=120, description="知识库名称")
    description: str = Field("", max_length=1000, description="知识库描述")
    owner_id: str = Field(..., min_length=1, max_length=120, description="所有者 ID")


class KnowledgeBaseUpdateRequest(BaseModel):
    """知识库更新请求模型。"""

    name: str | None = Field(None, min_length=1, max_length=120, description="知识库名称")
    description: str | None = Field(None, max_length=1000, description="知识库描述")
    owner_id: str | None = Field(None, min_length=1, max_length=120, description="所有者 ID")


class KnowledgeBasePublishRequest(BaseModel):
    """知识库发布请求模型。"""

    owner_id: str = Field(..., min_length=1, max_length=120, description="所有者 ID")


class KnowledgeBaseSettings(BaseModel):
    """知识库检索与分块设置模型。"""

    knowledge_base_id: str = Field(..., min_length=1, description="知识库 ID")
    semantic_chunking_enabled: bool = Field(False, description="是否启用 LLM 语义分块规划")
    chunk_size: int = Field(1000, ge=200, le=8000, description="滑动窗口 chunk 大小")
    overlap: int = Field(150, ge=0, description="滑动窗口 overlap 大小")
    top_k_default: int = Field(5, ge=1, le=50, description="默认检索 topK")
    max_heading_depth: int = Field(3, ge=1, le=3, description="Markdown 标题最大分块深度")
    llm_planning_timeout_ms: int = Field(8000, ge=1000, le=30000, description="LLM 规划超时时间")
    updated_at: str = Field(..., description="更新时间")

    @model_validator(mode="after")
    def validate_overlap(self) -> "KnowledgeBaseSettings":
        """校验 overlap 必须小于 chunk_size。"""
        if self.overlap < self.chunk_size:
            return self
        raise ValueError("overlap 必须小于 chunk_size")


class KnowledgeBaseSettingsUpdateRequest(BaseModel):
    """知识库检索与分块设置更新请求模型。"""

    semantic_chunking_enabled: bool | None = Field(None, description="是否启用 LLM 语义分块规划")
    chunk_size: int | None = Field(None, ge=200, le=8000, description="滑动窗口 chunk 大小")
    overlap: int | None = Field(None, ge=0, description="滑动窗口 overlap 大小")
    top_k_default: int | None = Field(None, ge=1, le=50, description="默认检索 topK")
    max_heading_depth: int | None = Field(None, ge=1, le=3, description="Markdown 标题最大分块深度")
    llm_planning_timeout_ms: int | None = Field(None, ge=1000, le=30000, description="LLM 规划超时时间")


class SynonymGroupCreateRequest(BaseModel):
    """同义词组创建请求模型。"""

    knowledge_base_id: str | None = Field(None, description="知识库 ID，空值表示全局")
    canonical: str = Field(..., min_length=1, max_length=120, description="标准词")
    terms: list[str] = Field(..., min_length=1, description="同义词条")
    owner_id: str = Field("default", min_length=1, max_length=120, description="所有者 ID")
    enabled: bool = Field(True, description="是否启用")


class SynonymGroupUpdateRequest(BaseModel):
    """同义词组更新请求模型。"""

    knowledge_base_id: str | None = Field(None, description="知识库 ID，空值表示全局")
    canonical: str | None = Field(None, min_length=1, max_length=120, description="标准词")
    terms: list[str] | None = Field(None, min_length=1, description="同义词条")
    owner_id: str | None = Field(None, min_length=1, max_length=120, description="所有者 ID")
    enabled: bool | None = Field(None, description="是否启用")


class DocumentUploadRequest(BaseModel):
    """纯文本或 Markdown 文档录入请求模型。"""

    knowledge_base_id: str = Field(..., min_length=1, description="知识库 ID")
    name: str = Field(..., min_length=1, max_length=240, description="文档名称")
    content: str = Field(..., min_length=1, description="纯文本或 Markdown 内容")
    content_type: str = Field("text/markdown", description="内容类型")
    owner_id: str = Field("default", min_length=1, max_length=120, description="上传者 ID")
    external_id: str | None = Field(None, max_length=240, description="外部幂等 ID")
    duplicate_policy: str = Field("upsert", description="重复文档处理策略")

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        """校验内容类型只允许纯文本或 Markdown。"""
        if value in ALLOWED_DOCUMENT_CONTENT_TYPES:
            return value
        raise ValueError("只支持纯文本或 Markdown")

    @field_validator("duplicate_policy")
    @classmethod
    def validate_duplicate_policy(cls, value: str) -> str:
        """校验重复文档处理策略。"""
        if value in ALLOWED_DUPLICATE_POLICIES:
            return value
        raise ValueError("重复文档策略仅支持 upsert、reject、versioned")


class DocumentTopicExtractionResult(BaseModel):
    """文档主题树抽取结果。"""

    primary_topic: str = Field(..., min_length=1, max_length=160, description="文档主主题")
    parent_topics: list[str] = Field(default_factory=list, description="上位主题")
    sibling_topics: list[str] = Field(default_factory=list, description="同类主题")
    child_topics: list[str] = Field(default_factory=list, description="下位主题")
    topic_aliases: list[str] = Field(default_factory=list, description="主题别名")
    topic_path: list[str] = Field(default_factory=list, description="从大类到主主题的主题路径")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="抽取置信度")
    evidence: list[str] = Field(default_factory=list, description="抽取依据")


class RetrievalSDKSearchRequest(BaseModel):
    """Retrieval SDK 同步检索请求模型。"""

    input: str = Field(..., min_length=1, description="用户查询")
    knowledge_base_ids: list[str] = Field(default_factory=list, description="知识库过滤 ID 列表")
    top_k: int | None = Field(None, ge=1, le=50, description="返回结果数量")
    use_context: bool = Field(False, description="是否关联最近上下文")
    history_questions: list[str] = Field(default_factory=list, description="最近用户问题")
    query_scope: Literal["local", "global", "hybrid"] | None = Field(None, description="查询范围")
    issue_type: str | None = Field(None, description="问题类型")
    issue_route: dict[str, Any] = Field(default_factory=dict, description="问题类型路由结果")
    issue_filters: dict[str, Any] = Field(default_factory=dict, description="问题类型过滤条件")
    deep_search_enabled: bool = Field(False, description="是否启用 DeepSearch 深度检索")
    stream: bool = Field(False, description="是否请求流式输出")
    temperature: float = Field(0.2, ge=0.0, le=1.0, description="LLM 生成温度")
    user_id: str | None = Field(None, min_length=1, max_length=120, description="聊天用户 ID")
    session_id: str | None = Field(None, min_length=1, max_length=160, description="聊天会话 ID")


class AnswerFeedbackRequest(BaseModel):
    """答案反馈请求。"""

    vote: Literal["like", "dislike"] = Field(..., description="点赞或点踩")
    user_id: str = Field("default", min_length=1, max_length=120, description="反馈用户 ID")


class RetrievalSDKSearchResponse(BaseModel):
    """Retrieval SDK 同步检索响应模型。"""

    request_id: str = Field(..., description="请求 ID")
    query_scope: Literal["local", "global", "hybrid"] = Field(..., description="查询范围")
    route_plan: dict[str, Any] = Field(default_factory=dict, description="检索路由计划")
    issue_type: str = Field("unknown", description="问题类型")
    issue_route: dict[str, Any] = Field(default_factory=dict, description="问题类型路由结果")
    issue_filters: dict[str, Any] = Field(default_factory=dict, description="问题类型过滤条件")
    filters: dict[str, Any] = Field(default_factory=dict, description="检索过滤条件")
    results: list[dict[str, Any]] = Field(default_factory=list, description="检索结果")
    trace: list[dict[str, Any]] = Field(default_factory=list, description="检索追踪")
