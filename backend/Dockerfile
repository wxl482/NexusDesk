# ==============================================================================
# NexusDesk Backend Dockerfile
# 生产级 Python 3.11 容器镜像构建文件
# ==============================================================================

FROM python:3.11-slim

# 设置工作目录与核心环境变量
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    KMP_DUPLICATE_LIB_OK=TRUE \
    OMP_NUM_THREADS=1 \
    HF_ENDPOINT=https://hf-mirror.com

# 安装系统级依赖与编译工具 (支持 C 扩展包如 psycopg, lxml 等编译与健康探针 curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖描述文件，充分利用 Docker 镜像层缓存
COPY requirements.txt .

# 安装 Python 核心依赖
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 复制后端应用源码
COPY . .

# 确保运行时数据目录与日志目录存在
RUN mkdir -p data/chroma data/milvus data/backups data/workspace logs

# 暴露 FastAPI 服务端口
EXPOSE 8000

# 容器健康检查
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动服务
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
