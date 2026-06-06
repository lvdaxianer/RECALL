# Recall 启动指南

## 方式 A：一键脚本（推荐）

```bash
./start.sh                 # 完整：venv + pip + npm + 后端 + 前端
./start.sh install        # 仅装依赖
./start.sh backend        # 仅起后端（uvicorn :8000）
./start.sh frontend       # 仅起前端（vite :5173）
./start.sh stop           # 停掉所有后台进程
./start.sh docker         # docker-compose 拉起整套
```

依赖：
- Python 3.10+（脚本自动创建 `.venv`）
- pnpm 或 npm（脚本自动选其一）
- Docker / Docker Compose（仅 `docker` 子命令需要）

日志与 PID：
- 后端日志：`var/backend.log`（PID 写入 `var/backend.pid`）
- 前端日志：`var/frontend.log`（PID 写入 `var/frontend.pid`）

停止时按 PID 文件清理。如端口被占可 `PORT_BACKEND=9000 ./start.sh`。

## 🔥 热更新（默认开启）

| 服务 | 触发方式 | 生效内容 |
|------|----------|----------|
| 前端 Vite HMR | 编辑 `web/src/**` 任一文件 | 浏览器自动热替换（无刷新） |
| 后端 uvicorn --reload | 编辑 `app/**` 任一 `.py` 文件 | 服务自动重启并重新加载 |

### 后端热更新细节

- 仅监控 `app/` 目录 + `*.py` 文件（用 `--reload-dir app --reload-include '*.py'`）
- 自动排除 `.venv/ var/ __pycache__/ data/ tests/` 等无关目录
- 触发时机：保存 `.py` 文件后 1-2 秒内重启
- 重启过程中 SSE 流会断开，前端会自动重连

### 前端热更新细节

- Vite HMR 通过 WebSocket 在 5173 端口通讯
- 仅监控 `web/src/**` + `web/index.html` + 配置文件
- 自动排除 `node_modules/ dist/ .git/` 等无关目录
- 触发时机：保存文件后浏览器立即热替换
- 编辑 `.tsx` 组件时，React 状态默认保留；编辑样式（CSS/Tailwind）即时生效
- 错误时浏览器右上角弹出覆盖层（`hmr.overlay: true`）

### 验证热更新

```bash
# 后端
echo "# test" >> app/main.py     # 观察 var/backend.log 出现 "Detected change"
                                  # 以及 "Watcher stopped" → "Watcher started"

# 前端
echo "// test" >> web/src/main.tsx # 浏览器 console 立即出现 [vite] hmr update
```

## 方式 B：手动

### 后端（FastAPI）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # 然后编辑填 API keys
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端服务：`http://localhost:8000`
- Swagger UI：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`

### 前端（Vite + React）

```bash
cd web
pnpm install              # 或 npm install
pnpm dev                  # 或 npm run dev
```

前端服务：`http://localhost:5173`
- 右上角"打开 Recall 助手"按钮 → 弹出聊天抽屉
- KB 列表 → 详情页 → 文档上传 / chunk 详情 / 分块配置

### 测试

```bash
# 后端
pytest

# 前端
cd web && pnpm test
```

## 方式 C：Docker

```bash
docker compose up -d
docker compose ps
docker compose logs -f rag-api
```

需要 `.env` 提前配置 `MODEL_API_KEY` / `EMBEDDING_API_KEY` 等。

## 关键端口

| 服务 | 端口 | 备注 |
|------|------|------|
| 前端 Vite | 5173 | 静态 SPA |
| 后端 FastAPI | 8000 | SSE 流式检索 |
| Milvus | 19530 | 仅 Docker |
| Elasticsearch | 9200 | 仅 Docker |

## 关键环境变量

```bash
# 后端
MODEL_NAME=qwen3.6-plus
MODEL_API_KEY=sk-xxx
EMBEDDING_MODEL_NAME=text-embedding-v4
EMBEDDING_DIMENSION=2048
RAG_RUNTIME_MODE=local          # local / http_sse

# 前端（开发时通常无需配置）
VITE_API_BASE=/api              # 反代到后端（开发用 vite proxy）
```

## 常见问题

**Q：首次启动报错 "ModuleNotFoundError"？**
A：先跑 `./start.sh install`；脚本会自动建 `.venv` 并装 `requirements.txt`。

**Q：前端能开但 SSE 流式不工作？**
A：检查 `web/vite.config.ts` 的 `server.proxy` 是否把 `/api` 反代到 `http://localhost:8000`。

**Q：Milvus / ES 启动失败？**
A：用 `./start.sh docker` 走容器；本地启动需要单独跑 Milvus standalone + ES。
