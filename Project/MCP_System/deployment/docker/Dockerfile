# MCP System Dockerfile
# 多阶段构建用于生产环境

# ========================================
# Builder Stage
# ========================================
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY backend/requirements/base.txt backend/requirements/prod.txt ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -r prod.txt


# ========================================
# Production Stage
# ========================================
FROM python:3.11-slim

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN useradd -m -u 1000 mcp && \
    mkdir -p /app/logs /app/storage && \
    chown -R mcp:mcp /app

# 复制已安装的包
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用代码
COPY backend/ ./

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production

# 切换到非 root 用户
USER mcp

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# 暴露端口
EXPOSE 8000 9090

# 启动命令
CMD ["python", "main.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
