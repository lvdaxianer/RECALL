"""
Dockerfile for RAG Knowledge Retrieval Platform

@author lvdaxianerplus
@date 2026-04-16
"""

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# 创建日志目录
RUN mkdir -p logs

# 暴露端口
EXPOSE 8000

# 环境变量（可在 docker-compose 或运行时覆盖）
ENV PYTHONUNBUFFERED=1
ENV DEBUG=false

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]