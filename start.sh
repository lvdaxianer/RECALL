#!/usr/bin/env bash
# Recall RAG 平台一键启动脚本
# 同时拉起后端 (FastAPI :8000) 和前端 (Vite :5173)。
#
# 用法：
#   ./start.sh           # 完整流程：venv + 装包 + 后端 + 前端
#   ./start.sh backend   # 只启动后端
#   ./start.sh frontend  # 只启动前端
#   ./start.sh install   # 只装依赖（venv + npm install）
#   ./start.sh stop      # 停掉所有后台进程
#   ./start.sh docker    # 用 docker-compose 拉起整套
#
# 进程 PID 写入 var/ 目录，stop 时按 PID 清理。
# 环境变量从 .env 加载（若存在）。

set -euo pipefail

# ===== 路径与常量 =====
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
VAR_DIR="$ROOT_DIR/var"
BACKEND_LOG="$VAR_DIR/backend.log"
FRONTEND_LOG="$VAR_DIR/frontend.log"
BACKEND_PID_FILE="$VAR_DIR/backend.pid"
FRONTEND_PID_FILE="$VAR_DIR/frontend.pid"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT_BACKEND="${PORT_BACKEND:-8000}"
PORT_FRONTEND="${PORT_FRONTEND:-5178}"

# 加载 .env（如有）
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

mkdir -p "$VAR_DIR"

# ===== 辅助函数 =====
log()  { printf '\033[1;36m[start.sh]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[start.sh]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[start.sh]\033[0m %s\n' "$*" >&2; }

is_running() {
  local pid_file="$1"
  [ -f "$pid_file" ] || return 1
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

stop_pid() {
  local name="$1" pid_file="$2"
  if is_running "$pid_file"; then
    local pid
    pid="$(cat "$pid_file")"
    log "停止 $name (pid=$pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pid_file"
  else
    log "$name 未运行"
  fi
}

ensure_venv() {
  if [ ! -d "$ROOT_DIR/.venv" ]; then
    log "创建 Python 虚拟环境 .venv"
    "$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
  fi
}

install_deps() {
  ensure_venv
  log "安装后端依赖（pip）"
  "$ROOT_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
  "$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/requirements.txt"
  log "安装前端依赖（pnpm/npm）"
  if command -v pnpm >/dev/null 2>&1; then
    (cd "$ROOT_DIR/web" && pnpm install)
  else
    (cd "$ROOT_DIR/web" && npm install)
  fi
}

start_backend() {
  stop_pid "backend" "$BACKEND_PID_FILE"
  ensure_venv
  log "启动后端 FastAPI (uvicorn + 热重载) :$PORT_BACKEND → $BACKEND_LOG"
  # 仅监控 app/ scripts/ requirements.txt 等源码目录
  # 排除 .venv/ var/ __pycache__/ data/ tests/ 等无关目录
  (
    cd "$ROOT_DIR"
    nohup "$ROOT_DIR/.venv/bin/python" -m uvicorn app.main:app \
      --host 0.0.0.0 --port "$PORT_BACKEND" --reload \
      --reload-dir app \
      --reload-include '*.py' \
      --reload-exclude 'var/*' \
      > "$BACKEND_LOG" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
  )
  sleep 2
  if is_running "$BACKEND_PID_FILE"; then
    log "后端已启动 pid=$(cat "$BACKEND_PID_FILE")"
  else
    err "后端启动失败，查看日志：$BACKEND_LOG"
    tail -30 "$BACKEND_LOG" >&2 || true
    return 1
  fi
}

start_frontend() {
  stop_pid "frontend" "$FRONTEND_PID_FILE"
  log "启动前端 Vite :$PORT_FRONTEND → $FRONTEND_LOG"
  # 清掉陈旧的 deps 缓存（避免新增文件解析不到）
  rm -rf "$ROOT_DIR/web/node_modules/.vite/deps"
  local pkg_cmd="npm"
  command -v pnpm >/dev/null 2>&1 && pkg_cmd="pnpm"
  (
    cd "$ROOT_DIR/web"
    nohup "$pkg_cmd" run dev -- --host 0.0.0.0 --port "$PORT_FRONTEND" \
      > "$FRONTEND_LOG" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
  )
  sleep 3
  if is_running "$FRONTEND_PID_FILE"; then
    log "前端已启动 pid=$(cat "$FRONTEND_PID_FILE")"
  else
    err "前端启动失败，查看日志：$FRONTEND_LOG"
    tail -30 "$FRONTEND_LOG" >&2 || true
    return 1
  fi
}

start_docker() {
  log "使用 docker-compose 拉起整套"
  if ! command -v docker >/dev/null 2>&1; then
    err "docker 未安装"
    return 1
  fi
  (cd "$ROOT_DIR" && docker compose up -d)
}

# ===== 主入口 =====
case "${1:-all}" in
  install)   install_deps ;;
  backend)   start_backend ;;
  frontend)  start_frontend ;;
  stop)
    stop_pid "frontend" "$FRONTEND_PID_FILE"
    stop_pid "backend"  "$BACKEND_PID_FILE"
    ;;
  docker)    start_docker ;;
  all|*)
    install_deps
    start_backend
    start_frontend
    log "全部就绪 → http://localhost:$PORT_FRONTEND  (后端 :$PORT_BACKEND)"
    log "日志：tail -f $BACKEND_LOG $FRONTEND_LOG"
    log "停止：./start.sh stop"
    ;;
esac
