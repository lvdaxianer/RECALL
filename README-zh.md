# RAG 知识检索平台

基于 RRF 混合检索（Milvus 向量 + ES BM25）的知识管理平台，支持向量化存储与检索。

## 功能特性

- **混合检索**：RRF 融合向量搜索 + BM25 关键词搜索
- **同义词支持**：ES IK 分词器 + 同义词分析器
- **单条/批量插入**：向量化后双写到 Milvus + ES
- **语义检索**：支持按类型过滤和全量检索
- **结果 Rerank**：重排优化检索结果排序
- **缓存加速**：Query Embedding 缓存 + Rerank 结果缓存
- **日志滚动**：按天滚动，自动压缩
- **特征标签增强**：LLM 自动提取 category 和 tags，支持特征加权检索

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

# Embedding 配置
EMBEDDING_MODEL_NAME=text-embedding-v4
EMBEDDING_API_KEY=your-api-key
EMBEDDING_REQUEST_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings
EMBEDDING_DIMENSION=2048

# Milvus 配置
EMBEDDING_STORE_HOST=localhost:19530
EMBEDDING_STORE_DB_NAME=studio

# Rerank 配置
RERANK_MODEL_NAME=qwen3-rerank
RERANK_API_KEY=your-api-key
RERANK_REQUEST_URL=https://dashscope.aliyuncs.com/compatible-api/v1/reranks

# ES 配置
ES_HOST=localhost:9200
ES_USERNAME=elastic
ES_PASSWORD=elasticuser
ES_SCHEME=http
ES_SKILL_INDEX=rag_skills
ES_ASSET_INDEX=rag_assets

# 缓存配置
EMBEDDING_CACHE_TTL=86400      # Query Embedding 缓存 TTL（秒），默认 24 小时
EMBEDDING_CACHE_MAX_SIZE=1000   # Embedding 缓存最大条数
RERANK_CACHE_TTL=3600          # Rerank 结果缓存 TTL（秒），默认 1 小时
RERANK_CACHE_MAX_SIZE=500       # Rerank 缓存最大条数
RERANK_CACHE_ENABLED=false       # 是否启用 Rerank 缓存，默认关闭

# 日志配置
LOG_DIR=./logs
APP_NAME=app
DEBUG=false
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

### 混合检索流程

```
用户 Query (如 "go语言实践 以及 python 全栈开发")
     │
     ├──→ Embedding 模型向量化
     │
     ├──→ Milvus COSINE 向量搜索 (TopK)
     │
     └──→ ES BM25 全文搜索 (TopK)
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