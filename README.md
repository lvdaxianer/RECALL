# RAG Knowledge Retrieval Platform

Hybrid search platform using RRF fusion (Milvus vector + ES BM25 + LightRAG-lite graph retrieval) for semantic knowledge management.

## Features

- **Hybrid Search**: RRF fusion of Milvus vector search + ES BM25 keyword search + LightRAG-lite graph retrieval
- **Synonym Support**: ES IK tokenizer + synonym analyzer
- **Single/Batch Insert**: Vectorize and dual-write to Milvus + ES
- **Semantic Search**: Filter by type or search all
- **Rerank**: Optimize search result ranking
- **Caching**: Query Embedding cache + Rerank result cache
- **Log Rotation**: Daily rotation with automatic compression

## Tech Stack

- **FastAPI** - Web framework
- **Milvus** - Vector database
- **Elasticsearch** - BM25 full-text search
- **DashScope API** - Alibaba Cloud LLM/Embedding/Rerank

## Quick Start

### 1. Docker (Recommended)

```bash
# Start all services (Milvus + ES + RAG API)
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f rag-api
```

### 2. Local Development

```bash
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Optional state persistence:

```bash
# Persist optimization history and evaluation records
RAG_STATE_DB_PATH=./data/rag_state.sqlite3
```

Rerank latency tuning:

```bash
# Maximum fused candidates sent to the external rerank service
RAG_RERANK_CANDIDATE_LIMIT=6
# Skip external rerank when the RRF leader is clearly ahead
RAG_RERANK_SKIP_CONFIDENT_ENABLED=true
RAG_RERANK_SKIP_MIN_GAP=0.018
# Maximum normalized expanded queries executed by optimized retrieval
RAG_OPTIMIZE_QUERY_LIMIT=2
# Number of related recommendations returned by optimized search
RAG_RECOMMENDATION_TOP_K=3
# Query optimization cache TTL and size
QUERY_OPTIMIZE_CACHE_TTL=3600
QUERY_OPTIMIZE_CACHE_MAX_SIZE=500
# Enable high-confidence local query optimization rules before LLM optimization
QUERY_OPTIMIZE_FAST_RULES_ENABLED=true
# Optional custom prompt template for query optimization. Use {query} as placeholder.
QUERY_OPTIMIZE_PROMPT_PATH=./prompts/query_optimize_prompt.txt
# Optional JSON rules for deterministic query decomposition and fast optimization
QUERY_OPTIMIZE_RULES_PATH=./config/query_optimize_rules.json

# Agent Runtime mode: local or http_sse
AGENT_RUNTIME_MODE=local
# Required when AGENT_RUNTIME_MODE=http_sse
AGENT_RUNTIME_BASE_URL=
AGENT_RUNTIME_API_KEY=
AGENT_RUNTIME_CONNECT_TIMEOUT=5
AGENT_RUNTIME_READ_TIMEOUT=60
```

Query optimization cache keys use a conservative local normalizer before the
normalized-cache lookup: Unicode NFKC normalization, punctuation/whitespace
folding, lowercase ASCII, and high-confidence business synonyms such as
`电梯权限 -> 梯控` and `车闸 -> 车辆道闸`. SEE cache-hit metrics include
`cache_hit_type` (`exact` or `normalized`) and `normalized_query`.
Embedding cache stores only the query vector representation, so bad answers do
not normally require clearing it. Rerank cache stores ordering decisions for a
specific query and candidate set; when an evaluation record is submitted with a
bad label or bad-case miss reason, the matching query enters a Rerank-cache
bypass window for the cache TTL so stale ordering is not reused.
`QUERY_OPTIMIZE_PROMPT_PATH` configures the visible retrieval-plan prompt for
`intent`, `cot_plan`, `optimized_query`, and `expanded_queries`; `cot_plan`
must remain a concise plan summary, not private chain-of-thought.
`QUERY_OPTIMIZE_RULES_PATH` can provide deterministic rules for common
troubleshooting queries before calling the LLM. A matched rule adds a
`query_decomposition` SEE stage and can also generate a structured normalized
cache key such as `type:troubleshooting entity:小程序 symptom:白屏`.
Optimized search also returns `recommendations`: related candidates selected
from original and optimized retrieval results, with a short `reason`. In the
first version this is a local recommendation layer, not a separate retrieval
service.
Each optimized search response includes a `request_id`. If a user marks a
specific response as unsatisfactory, call:

```bash
POST /api/v1/rag/cache/rerank/invalidate-by-request/{request_id}
```

This removes only the Rerank cache entries created by that request and puts the
related query into the Rerank-cache bypass window. Embedding cache is preserved.

Example rule file:

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

Milvus authentication:

```bash
EMBEDDING_STORE_HOST=localhost:19530
EMBEDDING_STORE_USERNAME=your-milvus-username
EMBEDDING_STORE_PASSWORD=your-milvus-password
EMBEDDING_STORE_DB_NAME=studio
```

## API Endpoints

### Health Check

```bash
GET /health
```

Response:
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

### Insert Data

```bash
# Single insert (dual-write to Milvus + ES)
POST /api/v1/rag/{userId}/insert
Content-Type: application/json

{
  "description": "Pinia is Vue's state management library",
  "metadata": {
    "type": "skill",
    "id": "skill-pinia",
    "name": "pinia",
    "description": "Pinia state management"
  }
}
```

The returned `features` object includes the original `category` and `tags`,
plus LightRAG-lite structural fields:

```json
{
  "category": "Authentication",
  "tags": ["Login", "JWT"],
  "entities": [{"name": "JWT", "type": "Technical component"}],
  "relations": [{"source": "JWT", "target": "Login auth", "relation": "used_for"}]
}
```

### Hybrid Search

```bash
# RRF Hybrid Search (vector + BM25 + Rerank)
POST /api/v1/rag/{userId}/search
Content-Type: application/json

{
  "input": "Vue state management",
  "type": "skill",
  "topK": 5,
  "threshold": 0.7
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| input | string | Yes | Query text |
| type | string | No | Search type: `skill`, `asset`, or `all` (default: all) |
| topK | int | No | Number of results (default: 20) |
| threshold | float | No | Similarity threshold (default: 0.7) |

### Optimized Semantic Search

```bash
# CoT retrieval plan + SEE search trace
POST /api/v1/rag/{userId}/search/optimize
Content-Type: application/json

{
  "input": "Find login-related content",
  "type": "skill",
  "topK": 5,
  "threshold": 0.7,
  "enableFeatureBoost": true
}
```

The response includes `original_query`, `optimized_query`, `intent`,
`cot_plan`, `expanded_queries`, `see_trace`, `original_results`,
`optimized_results`, `comparison`, and `fallback_used`. `cot_plan` is a
concise retrieval plan summary, not the model's private chain-of-thought.
The optimized retrieval stage executes up to `RAG_OPTIMIZE_QUERY_LIMIT`
normalized `expanded_queries` and merges duplicate results. `see_trace`
exposes visible search stages, including `query_count`, per-query result
counts, per-query profiles, fallback status, and `optimize_cache` cache-hit
events for inspection.

### RAG SSE Stream and SEE Timeline

```bash
POST /api/v1/rag/{userId}/search/optimize/stream
Content-Type: application/json

{
  "input": "Mini program shows a white screen after release, local development is fine",
  "type": "all",
  "topK": 5,
  "enableFeatureBoost": false
}
```

The stream returns ordered Server-Sent Events such as `request.created`,
`query.decomposition`, `retrieval.original.completed`,
`retrieval.optimized.completed`, `rerank.completed`,
`recommendation.completed`, and `answer.completed`. Each stream has a
`request_id`; `query.decomposition.payload.cot_plan` is only a visible
retrieval-plan summary, not private chain-of-thought.

The built-in SEE page is available at:

```bash
GET /see/timeline
```

It can run the RAG SSE endpoint, display retrieval stages, show `request_id`,
call `POST /api/v1/rag/cache/rerank/invalidate-by-request/{request_id}`, and
submit bad feedback through:

```bash
POST /api/v1/rag/{userId}/feedback/bad-case
```

The feedback route reuses the Agent tool `record_bad_case`; when `request_id`
is present it also invalidates the related Rerank cache lineage.

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

The first runtime mode is local/noop and exposes RAG capabilities as Agent
tools: `optimize_query`, `search_rag`, `invalidate_rerank_cache`,
`record_bad_case`, `get_cache_stats`, and `get_evaluation_summary`. Run
events can be streamed or replayed from the events endpoint; cross-user
session and run reads are rejected by the session service. Runtime operations
expose local/noop health, stop, and idle cleanup controls for operational
checks before a real process or container provider is connected.

### Optimization History

```bash
GET /api/v1/rag/{userId}/search/optimize/history
GET /api/v1/rag/{userId}/search/optimize/history/{historyId}
```

### Evaluation Records

```bash
POST /api/v1/rag/{userId}/evaluation/records
Content-Type: application/json

{
  "query": "Login failed",
  "optimized_query": "Login failure troubleshooting",
  "retrieved_ids": ["skill-001"],
  "miss_reason": "recall_miss",
  "human_label": "bad"
}

GET /api/v1/rag/{userId}/evaluation/records
GET /api/v1/rag/{userId}/evaluation/records/summary
```

Supported `miss_reason` values: `intent_error`, `recall_miss`,
`rerank_error`, `generation_error`, `stale_knowledge`, and `unknown`.
The summary endpoint returns total records, miss reason distribution, human
label distribution, and the latest record time.

### Evaluation Scripts

```bash
# Fixed 50-industry dataset report
python scripts/evaluate_rag_industry50.py --repeat 1

# Random 100 cold-start speed report
python scripts/evaluate_rag_random100.py --disable-cache

# Agent Runtime SSE first-event and stream stability report
python scripts/evaluate_agent_runtime_stream.py --base-url http://127.0.0.1:8000
```

Reports are written to `reports/rag_eval/YYYYMMDD-HHMMSS-*.json` and include
`recall@1`, `recall@3`, `recall@5`, mean/p50/p95 latency, and stage latency
for embedding, ES, Milvus, graph, and rerank where available.

### Graph Retrieval Debugging

```bash
GET /api/v1/rag/graph/stats
POST /api/v1/rag/graph/rebuild?limit=1000
GET /api/v1/rag/{userId}/graph/explain?query=JWT%20login&type=skill&topK=5
```

The explain response includes `matched_entities`, `matched_relation_terms`,
`matches`, and `result_count` for debugging graph recall behavior. The rebuild
route restores the in-memory graph index from the ES skill/asset indexes.
Set `RAG_GRAPH_REBUILD_ON_STARTUP=true` to run the same rebuild during startup;
`RAG_GRAPH_REBUILD_LIMIT` controls the per-index document limit.

### Delete Data

```bash
# Delete (removes from both Milvus and ES)
DELETE /api/v1/rag/{userId}/delete?type=skill&id=skill-pinia
```

### Cache Management

```bash
# Reset all caches
POST /api/v1/rag/cache/reset

# Get cache statistics
GET /api/v1/rag/cache/stats
```

## Retrieval SDK and Knowledge Bases

Recall now exposes a Retrieval SDK surface for productized knowledge-base
search. It keeps the existing `/api/v1/rag/{userId}/search/optimize`,
Rerank request-id invalidation, SEE/SSE, recommendations, and `cot_plan`
summary output compatible.

Supported ingestion is intentionally limited to plain text and Markdown:

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

`/api/v1/retrieval/search` accepts `input`, `knowledge_base_ids`, and `top_k`.
The response includes `query_scope`, `route_plan`, selected KB filters,
candidate `score_trace`, and SEE-safe trace summaries. The stream endpoint
returns `request.created`, `retrieval.trace`, `answer.delta`, and
`answer.completed` SSE events.

### Frontend Console

The React + TypeScript + Vite console lives under `web/` and uses a white,
work-focused theme:

```bash
pnpm --dir web install
pnpm --dir web dev
pnpm --dir web test
pnpm --dir web build
```

The console includes knowledge-base management, Markdown document entry,
document/chunk surfaces, knowledge-base multi-select search, streaming output,
and trace display. Async UI states are modeled as loading, empty, error,
retrying, streaming, and success states.

## Architecture

### Hybrid Search Flow

```
User Query
     │
     ├──→ Milvus COSINE Search (TopK×3)
     │
     └──→ ES BM25 Search (TopK×3)
                    │
                    ↓ RRF Fusion (k=60)
              Fusion Score Ranking
                    │
                    ↓
              Rerank
                    │
                    ↓
               Results
```

### RRF Formula

```
RRF_score(d) = Σ 1 / (k + rank_i(d))

k = 60 (fusion constant, higher = smoother)
```

## Project Structure

```
app/
├── config.py              # Configuration
├── main.py                # FastAPI entry point
├── models/
│   └── schemas.py         # Pydantic models
├── routers/
│   └── rag.py             # RAG routes
├── services/
│   ├── cache_service.py       # Cache service (LRU + TTL)
│   ├── embedding_service.py   # Embedding service
│   ├── es_service.py         # ES BM25 search
│   ├── hybrid_search.py       # RRF fusion
│   ├── milvus_service.py     # Vector storage
│   ├── rerank_service.py     # Rerank service
│   ├── llm_service.py         # LLM service
│   └── retry_queue.py        # Retry queue
└── utils/
    ├── logger.py             # Logging utilities
    └── log_rotation.py       # Log rotation

scripts/
├── import_skills.py              # Import skills data
└── recreate_es_index_with_synonyms.py  # Recreate ES index

tests/                       # Tests
Dockerfile                   # Docker image
docker-compose.yml           # Docker Compose
```

## Testing

```bash
pytest tests/ -v
```

## License

MIT
