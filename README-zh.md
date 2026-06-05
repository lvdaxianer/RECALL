# RAG 知识检索平台

基于 RRF 混合检索（Milvus 向量 + ES BM25）的知识管理平台，支持向量化存储与检索。

## 功能特性

- **混合检索**：RRF 融合向量搜索 + BM25 关键词搜索 + 轻量图谱检索
- **同义词支持**：ES IK 分词器 + 同义词分析器
- **单条/批量插入**：向量化后双写到 Milvus + ES
- **语义检索**：支持按类型过滤和全量检索
- **结果 Rerank**：重排优化检索结果排序
- **缓存加速**：Query Embedding 缓存 + Rerank 结果缓存
- **日志滚动**：按天滚动，自动压缩
- **特征标签增强**：LLM 自动提取 category、tags、entities、relations，支持特征加权和图检索

## 技术栈

- **FastAPI** - Web 框架
- **Milvus** - 向量数据库
- **Elasticsearch** - BM25 全文搜索
- **DashScope API** - 阿里云 LLM/Embedding/Rerank 服务

## 快速开始

### 1. Docker 部署（推荐）

```bash
# 启动所有服务（Milvus + ES + RAG API）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f rag-api
```

### 2. 本地开发

#### 安装依赖

```bash
pip install -r requirements.txt
```

#### 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 配置 API Key
```

#### 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API 接口

### 健康检查

```bash
GET /health
```

返回示例：
```json
{
  "status": "healthy",
  "services": {
    "milvus": "connected",
    "embedding": "available",
    "rerank": "available",
    "elasticsearch": "connected"
  }
}
```

### 插入数据

```bash
# 单条插入（双写到 Milvus + ES）
POST /api/v1/rag/{userId}/insert
Content-Type: application/json

{
  "description": "Pinia 是 Vue3 推荐的状态管理库",
  "metadata": {
    "type": "skill",
    "id": "skill-pinia",
    "name": "pinia",
    "description": "Pinia 状态管理"
  }
}
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "skill-pinia",
    "collection": "skill",
    "features": {
      "category": "状态管理",
      "tags": ["Vue3", "Pinia", "状态管理", "JavaScript"]
    }
  }
}
```

```bash
# 批量插入
POST /api/v1/rag/{userId}/insert/batch
Content-Type: application/json

{
  "items": [
    {
      "description": "描述1",
      "metadata": {"type": "skill", "id": "id1", "description": "desc1"}
    }
  ]
}
```

### 混合检索

```bash
# RRF 混合检索（向量 + BM25 + Rerank）
POST /api/v1/rag/{userId}/search
Content-Type: application/json

{
  "input": "Vue 状态管理",
  "type": "skill",
  "topK": 5,
  "threshold": 0.7,
  "enableFeatureBoost": true
}
```

**参数说明：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| input | string | 是 | 查询文本 |
| type | string | 否 | 搜索类型：`skill`、`asset` 或 `all`（默认 all） |
| topK | int | 否 | 返回数量（默认 20） |
| threshold | float | 否 | 相似度阈值（默认 0.7） |
| enableFeatureBoost | bool | 否 | 是否启用特征加权（默认 false） |

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "metadata": {
        "type": "skill",
        "id": "skill-pinia",
        "name": "pinia",
        "description": "Pinia 状态管理"
      },
      "description": "Pinia 是 Vue3 推荐的状态管理库",
      "score": 0.92,
      "features": {
        "category": "状态管理",
        "tags": ["Vue3", "Pinia", "状态管理", "JavaScript"]
      }
    }
  ]
}
```

**特征加权说明：**

当 `enableFeatureBoost=true` 时：
- 固定规则加权：命中的标签数 × 0.05
- LLM 语义加权：评估查询与标签的语义相关性（0-1）
- 综合分数 = 向量分数 + 固定加权 + 语义加权

插入时的 `features` 已扩展为 LightRAG-lite 基础结构：

```json
{
  "category": "认证",
  "tags": ["登录", "JWT"],
  "entities": [{"name": "JWT", "type": "技术组件"}],
  "relations": [{"source": "JWT", "target": "登录认证", "relation": "用于"}]
}
```

### RAGFlow-inspired 检索策略

默认策略仍为 `RAG_RETRIEVAL_STRATEGY=rrf`，保持现有 RRF 融合行为不变。需要灰度字段加权混合检索时，可设置 `RAG_RETRIEVAL_STRATEGY=ragflow_weighted`。

该策略会使用标题、重要标签、问题表达和正文内容的字段权重召回，再与向量检索、图检索进行加权融合。全局或混合问题会通过 `query_scope` 与 `route_plan` 暴露 summary-first 路由，例如先走 summary 检索、section 展开，再回到 evidence chunk 取证。接口仍只输出 `cot_plan` 检索计划摘要，不输出完整私有 CoT。

### 语义优化检索

```bash
# CoT 检索计划 + SEE 查询过程追踪
POST /api/v1/rag/{userId}/search/optimize
Content-Type: application/json

{
  "input": "查找登录相关内容",
  "type": "skill",
  "topK": 5,
  "threshold": 0.7,
  "enableFeatureBoost": true
}
```

**响应字段：**

| 字段 | 说明 |
|------|------|
| original_query | 原始查询 |
| optimized_query | LLM 优化后的查询 |
| intent | 识别出的查询意图 |
| cot_plan | 可解释的检索计划摘要，不返回完整私有推理链 |
| expanded_queries | 扩展查询列表，优化检索阶段按 `RAG_OPTIMIZE_QUERY_LIMIT` 上限执行并合并去重 |
| see_trace | SEE 查询过程追踪，包含意图识别、原始检索、优化多查询检索、对比指标 |
| original_results | 原始查询结果 |
| optimized_results | 优化查询结果 |
| comparison | 两次检索结果数量、耗时和历史记录 ID |
| fallback_used | 是否因优化失败降级使用原始查询 |

`see_trace` 的 `optimized_retrieval.metrics` 会返回 `query_count` 和
`query_result_counts`、`query_profiles`，用于观察每个扩展查询的命中情况、
阶段耗时和降级状态；查询优化缓存命中时会追加 `optimize_cache` 阶段。

### RAG SSE 流式检索与 SEE Timeline

```bash
POST /api/v1/rag/{userId}/search/optimize/stream
Content-Type: application/json

{
  "input": "小程序上线后白屏了，之前本地开发都正常",
  "type": "all",
  "topK": 5,
  "enableFeatureBoost": false
}
```

流式接口按顺序返回 SSE 事件，包括 `request.created`、
`query.decomposition`、`retrieval.original.completed`、
`retrieval.optimized.completed`、`rerank.completed`、
`recommendation.completed` 和 `answer.completed`。每次流式检索都会生成
`request_id`；`query.decomposition.payload.cot_plan` 只表示可解释检索计划摘要，
不会输出完整私有推理链。

内置 SEE 页面：

```bash
GET /see/timeline
```

该页面可以发起 RAG SSE 检索、展示检索阶段、显示 `request_id`，并调用：

```bash
POST /api/v1/rag/cache/rerank/invalidate-by-request/{request_id}
POST /api/v1/rag/{userId}/feedback/bad-case
```

Bad feedback 入口复用 Agent 工具 `record_bad_case`；请求中带 `request_id`
时会同步撤销关联的 Rerank 缓存血缘，避免错误排序长期固化。

### Agent Runtime API

```bash
POST /api/v1/agent/{userId}/sessions
GET /api/v1/agent/{userId}/sessions
POST /api/v1/agent/{userId}/sessions/{sessionId}/runs
GET /api/v1/agent/{userId}/sessions/{sessionId}/runs
GET /api/v1/agent/{userId}/sessions/{sessionId}/events?run_id={runId}
GET /api/v1/agent/runtimes/{runtimeId}/health
POST /api/v1/agent/runtimes/{runtimeId}/stop
POST /api/v1/agent/runtimes/cleanup
```

当前 Runtime 默认是 local/noop 模式，用来跑通 session、run、事件流和工具调用。
已注册工具包括 `optimize_query`、`search_rag`、`invalidate_rerank_cache`、
`record_bad_case`、`get_cache_stats` 和 `get_evaluation_summary`。run 事件既可
SSE 输出，也可通过 events 接口回放；Session Service 会按 `user_id` 隔离，
跨用户读取 session/run 会失败。Runtime 运维接口提供 local/noop 模式下的
健康检查、停止和空闲清理能力，便于后续接入真实进程或容器 provider 前做运维验证。

### 语义优化历史

```bash
# 获取用户语义优化历史
GET /api/v1/rag/{userId}/search/optimize/history

# 获取单条语义优化历史
GET /api/v1/rag/{userId}/search/optimize/history/{historyId}
```

### 检索评测记录

```bash
# 记录一次检索效果或 bad case 归因
POST /api/v1/rag/{userId}/evaluation/records
Content-Type: application/json

{
  "query": "登录失败",
  "optimized_query": "登录失败原因排查",
  "retrieved_ids": ["skill-001"],
  "miss_reason": "recall_miss",
  "human_label": "bad"
}

# 查看用户评测记录
GET /api/v1/rag/{userId}/evaluation/records

# 查看用户评测汇总
GET /api/v1/rag/{userId}/evaluation/records/summary
```

`miss_reason` 支持：`intent_error`、`recall_miss`、`rerank_error`、
`generation_error`、`stale_knowledge`、`unknown`。
汇总接口返回总记录数、miss reason 分布、人工标签分布和最新记录时间。

### 评测脚本

```bash
# 固定 50 行业数据集准确率评测
python scripts/evaluate_rag_industry50.py --repeat 1

# 100 条随机查询冷启动速度评测
python scripts/evaluate_rag_random100.py --disable-cache

# Agent Runtime SSE 首包与稳定性评测
python scripts/evaluate_agent_runtime_stream.py --base-url http://127.0.0.1:8000
```

报告会写入 `reports/rag_eval/YYYYMMDD-HHMMSS-*.json`，包含 `recall@1`、
`recall@3`、`recall@5`、mean/p50/p95 延迟，以及 embedding、ES、Milvus、
graph、rerank 等阶段耗时。

### 图检索调试

```bash
# 查看当前内存图索引规模
GET /api/v1/rag/graph/stats

# 从 ES 重建内存图索引（服务重启后可用）
POST /api/v1/rag/graph/rebuild?limit=1000

# 查看某次查询的图命中解释
GET /api/v1/rag/{userId}/graph/explain?query=JWT登录&type=skill&topK=5
```

解释结果包含 `matched_entities`、`matched_relation_terms`、`matches` 和
`result_count`，用于排查图检索召回原因。重建接口会从 ES 的 skill/asset
索引读取文档，恢复内存图索引。
如需服务启动时自动恢复内存图索引，可设置
`RAG_GRAPH_REBUILD_ON_STARTUP=true`；`RAG_GRAPH_REBUILD_LIMIT` 控制每个 ES
索引读取的文档上限。

### 删除数据

```bash
# 删除（从 Milvus 和 ES 同时删除）
DELETE /api/v1/rag/{userId}/delete?type=skill&id=skill-pinia
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": null
}
```

### 重试任务

```bash
# 获取用户所有重试任务
GET /api/v1/rag/{userId}/retry/tasks

# 获取特定任务状态
GET /api/v1/rag/{userId}/retry/tasks/{taskId}
```

### 缓存管理

```bash
# 重置所有缓存（Embedding + Rerank）
POST /api/v1/rag/cache/reset

# 获取缓存统计
GET /api/v1/rag/cache/stats
```

**缓存统计响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "embedding_cache": {
      "size": 10,
      "max_size": 1000,
      "ttl": 86400
    },
    "rerank_cache": {
      "size": 5,
      "max_size": 500,
      "ttl": 3600
    }
  }
}
```

## API 响应格式

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

| code | 含义 |
|------|------|
| 200 | 成功 |
| 202 | 请求已接受（插入失败进入重试队列） |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

## 配置说明

### 环境变量

```bash
# LLM 模型配置
MODEL_NAME=qwen3.6-plus
MODEL_API_KEY=your-api-key
MODEL_REQUEST_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_ENABLE_THINKING=false

# Embedding 配置
EMBEDDING_MODEL_NAME=text-embedding-v4
EMBEDDING_MODEL_API_KEY=your-api-key
EMBEDDING_MODEL_REQUEST_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings
EMBEDDING_DIMENSION=2048

# Milvus 配置
EMBEDDING_STORE_HOST=localhost:19530
EMBEDDING_STORE_USERNAME=your-milvus-username
EMBEDDING_STORE_PASSWORD=your-milvus-password
EMBEDDING_STORE_DB_NAME=studio

# Rerank 配置
RERANK_MODEL_NAME=qwen3-rerank
RERANK_MODEL_API_KEY=your-api-key
RERANK_MODEL_REQUEST_URL=https://dashscope.aliyuncs.com/compatible-api/v1/reranks

# ES 配置
ES_HOST=localhost:9200
ES_USERNAME=elastic
ES_PASSWORD=elasticuser
ES_SCHEME=http
ES_VERIFY_CERTS=false  # 本地自签证书可关闭；生产建议 true
ES_SKILL_INDEX=rag_skills
ES_ASSET_INDEX=rag_assets

# RAG 配置
RERANK_TOP_K=20
RAG_RERANK_CANDIDATE_LIMIT=6   # 送入 Rerank 的最大融合候选数，用于控制外部重排延迟
RAG_RERANK_SKIP_CONFIDENT_ENABLED=true # RRF 第一名明显领先时跳过外部 Rerank
RAG_RERANK_SKIP_MIN_GAP=0.018   # 跳过 Rerank 所需的 RRF 分差阈值
RAG_OPTIMIZE_QUERY_LIMIT=2     # 优化检索最多执行的扩展查询数，用于控制端到端延迟
RAG_RECOMMENDATION_TOP_K=3     # 优化检索返回的相关推荐数量
RERANK_THRESHOLD=0.7
RAG_STATE_DB_PATH=./data/rag_state.sqlite3  # 可选：持久化优化历史和评测记录

# 缓存配置
EMBEDDING_CACHE_TTL=86400      # Query Embedding 缓存 TTL（秒），默认 24 小时
EMBEDDING_CACHE_MAX_SIZE=1000   # Embedding 缓存最大条数
RERANK_CACHE_TTL=3600          # Rerank 结果缓存 TTL（秒），默认 1 小时
RERANK_CACHE_MAX_SIZE=500       # Rerank 缓存最大条数
RERANK_CACHE_ENABLED=false       # 是否启用 Rerank 缓存，默认关闭
QUERY_OPTIMIZE_CACHE_TTL=3600   # 查询优化结果缓存 TTL（秒），默认 1 小时
QUERY_OPTIMIZE_CACHE_MAX_SIZE=500 # 查询优化缓存最大条数
QUERY_OPTIMIZE_FAST_RULES_ENABLED=true # 是否启用高置信本地快速规则，命中后跳过 LLM 查询优化
QUERY_OPTIMIZE_PROMPT_PATH=./prompts/query_optimize_prompt.txt # 可选：查询优化 Prompt 模板文件，使用 {query} 占位
QUERY_OPTIMIZE_RULES_PATH=./config/query_optimize_rules.json # 可选：查询拆解和快速优化 JSON 规则

# Agent Runtime 配置：local 或 http_sse
AGENT_RUNTIME_MODE=local
# AGENT_RUNTIME_MODE=http_sse 时填写真实 Runtime 地址和密钥
AGENT_RUNTIME_BASE_URL=
AGENT_RUNTIME_API_KEY=
AGENT_RUNTIME_CONNECT_TIMEOUT=5
AGENT_RUNTIME_READ_TIMEOUT=60

# 日志配置
LOG_DIR=./logs
APP_NAME=app
DEBUG=false
```

查询优化缓存会先尝试原始 query 精确命中，再尝试归一化 query 命中。
归一化规则包括 Unicode NFKC、标点/空白折叠、英文小写，以及少量高置信
业务同义词（例如 `电梯权限 -> 梯控`、`车闸 -> 车辆道闸`）。SEE 的
`optimize_cache.metrics` 会返回 `cache_hit_type`（`exact` 或
`normalized`）和 `normalized_query`，便于排查缓存命中来源。
Embedding 缓存只保存 query 的向量表达，本身不是答案或排序判断，所以一次
回答不满意通常不需要清它。Rerank 缓存保存的是某个 query + 候选集合下的
排序结果，更接近“结果类缓存”；当提交评测记录且 `human_label=bad` 或
`miss_reason` 属于 bad case 时，对应 query 会进入 Rerank 缓存绕过窗口，
在缓存 TTL 内不读取也不写入旧排序，避免错误排序被反复命中。
每次优化检索响应会返回 `request_id`。如果用户对某次响应不满意，可主动调用：

```bash
POST /api/v1/rag/cache/rerank/invalidate-by-request/{request_id}
```

该接口只删除该 request 关联的 Rerank 缓存，并把相关 query 放入 Rerank
缓存绕过窗口；Embedding 缓存会保留。
`QUERY_OPTIMIZE_PROMPT_PATH` 用于配置可见的检索计划生成规则，影响
`intent`、`cot_plan`、`optimized_query` 和 `expanded_queries`；其中
`cot_plan` 仍应保持为简短检索计划摘要，不输出完整私有推理链。
`QUERY_OPTIMIZE_RULES_PATH` 可在调用 LLM 前配置确定性的故障类拆解规则。
命中后 SEE 会追加 `query_decomposition` 阶段，并可生成结构化归一化缓存 key，
例如 `type:troubleshooting entity:小程序 symptom:白屏`。
优化检索接口会额外返回 `recommendations`：从原始召回和优化召回候选中选出
相关推荐，并附带简短 `reason`。第一版是本地推荐层，不额外发起独立推荐召回。

规则文件示例：

```json
{
  "rules": [
    {
      "name": "mini_program_white_screen_after_release",
      "query_type": "troubleshooting",
      "triggers": ["小程序"],
      "synonym_triggers": [
        ["上线后", "发布后", "线上"],
        ["本地正常", "本地开发正常", "本地没问题"],
        ["白屏", "页面空白"]
      ],
      "intent": "排查小程序生产环境上线后白屏问题",
      "cot_plan": [
        "识别故障现象：小程序白屏",
        "区分环境差异：本地开发正常，生产环境异常"
      ],
      "optimized_query": "小程序上线后白屏 本地正常 生产环境异常 排查",
      "expanded_queries": [
        "小程序上线后白屏 本地开发正常 生产环境异常",
        "微信小程序 发布后白屏 构建配置 接口域名 资源加载"
      ],
      "decomposition": {
        "entities": ["小程序"],
        "symptoms": ["白屏"],
        "environment_gap": ["本地正常", "生产环境异常"],
        "time_context": ["上线后"]
      }
    }
  ]
}
```

## 项目结构

```
app/
├── config.py              # 配置管理
├── main.py                # FastAPI 应用入口
├── models/
│   └── schemas.py        # Pydantic 模型
├── routers/
│   └── rag.py             # RAG 路由
├── services/
│   ├── cache_service.py       # 缓存服务（内存 LRU + TTL）
│   ├── embedding_service.py   # 向量化服务
│   ├── es_service.py         # ES BM25 搜索
│   ├── hybrid_search.py       # RRF 融合
│   ├── milvus_service.py     # 向量存储
│   ├── rerank_service.py     # 重排序
│   ├── llm_service.py         # LLM 服务
│   ├── retry_queue.py        # 重试队列
│   ├── feature_extract_service.py  # LLM 特征提取
│   └── feature_boost_service.py   # 特征加权服务
└── utils/
    ├── logger.py             # 日志工具
    └── log_rotation.py        # 日志滚动

scripts/
├── import_skills.py              # 导入 skills 数据
└── recreate_es_index_with_synonyms.py  # 重建 ES 索引（同义词）

tests/                       # 测试
Dockerfile                   # Docker 镜像
docker-compose.yml           # Docker Compose 配置
```

## 架构说明

## Retrieval SDK 与知识库

Recall 新增 Retrieval SDK 产品化入口，用于知识库管理、纯文本/Markdown
文档录入、文档列表、chunk 明细、知识库多选检索和流式输出。该入口保持现有
`/api/v1/rag/{userId}/search/optimize`、Rerank request_id 撤销、SEE/SSE、
recommendations 和 `cot_plan` 摘要输出兼容。

当前录入边界只支持纯文本和 Markdown，不做 PDF、OCR、Office 等文档解析器：

```bash
POST /api/v1/kb
GET /api/v1/kb?owner_id=user-001
PATCH /api/v1/kb/{kb_id}
DELETE /api/v1/kb/{kb_id}?owner_id=user-001

POST /api/v1/kb/{kb_id}/documents
GET /api/v1/kb/{kb_id}/documents
GET /api/v1/kb/{kb_id}/documents/{document_id}
GET /api/v1/kb/{kb_id}/documents/{document_id}/chunks

POST /api/v1/retrieval/search
POST /api/v1/retrieval/search/stream
```

`/api/v1/retrieval/search` 接收 `input`、`knowledge_base_ids` 和 `top_k`，
返回 `query_scope`、`route_plan`、知识库过滤条件、候选级 `score_trace`
和 SEE 安全 trace。流式接口输出 `request.created`、`retrieval.trace`、
`answer.delta`、`answer.completed` 事件。

### 前端控制台

React + TypeScript + Vite 控制台位于 `web/`，采用白色、简洁、工作台风格：

```bash
pnpm --dir web install
pnpm --dir web dev
pnpm --dir web test
pnpm --dir web build
```

控制台包含知识库管理、Markdown 文档录入、文档/chunk 展示、知识库多选检索、
流式输出和 trace 展示。异步交互覆盖 loading、empty、error、retrying、
streaming 和 success 状态。

### 混合检索流程

```
用户 Query (如 "go语言实践 以及 python 全栈开发")
     │
     ├──→ Embedding 模型向量化
     │
     ├──→ Milvus COSINE 向量搜索 (TopK)
     │
     ├──→ ES BM25 全文搜索 (TopK)
     │
     └──→ LightRAG-lite 图检索 (TopK)
                    │
                    ↓ RRF 融合 (k=60)
              多路召回结果排序
                    │
                    ↓ 特征加权（可选）
              固定加权：命中标签 × 0.05
              LLM 语义加权：语义相关性评估（并发执行）
                    │
                    ↓
              Rerank 重排（语义重排序）
                    │
                    ↓
              归一化分数到 [0,1] 范围
                    │
                    ↓
              threshold 阈值过滤
                    │
                    ↓
               返回结果
```

### RRF 融合公式

```
RRF_score(d) = Σ 1 / (k + rank_i(d))

k = 60（融合常数，越大越平滑）
```

### 检索参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| input | string | 是 | 查询文本 |
| type | string | 否 | 搜索类型：`skill`、`asset` 或 `all`（默认 all） |
| topK | int | 否 | 返回数量（默认 20） |
| threshold | float | 否 | 相似度阈值（默认 0.7），归一化后分数 ≥ threshold 才返回 |
| enableFeatureBoost | bool | 否 | 是否启用特征加权（默认 false） |

### 分数说明

检索结果中的 `score` 字段经过以下处理：

1. **原始分数来源**：
   - 向量搜索：Milvus COSINE 相似度（0~1+，可达 4+）
   - ES BM25：关键词匹配分数（0~20+）
   - RRF 融合：排名融合分数（0.01~0.03）

2. **特征加权**（enableFeatureBoost=true）：
   - 固定加权：命中标签数 × 0.05
   - LLM 语义加权：0~1（评估查询与标签的语义相关性）

3. **Rerank 重排**：DashScope Rerank API 返回 `relevance_score`（0~1）

4. **最终归一化**：所有分数归一化到 [0,1] 范围，确保 threshold 比较一致性

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_hybrid_search.py -v
pytest tests/test_es_service.py -v
```

## License

MIT
