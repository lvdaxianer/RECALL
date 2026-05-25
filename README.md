# RAG Knowledge Retrieval Platform

Hybrid search platform using RRF fusion (Milvus vector + ES BM25) for semantic knowledge management.

## Features

- **Hybrid Search**: RRF fusion of Milvus vector search + ES BM25 keyword search
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