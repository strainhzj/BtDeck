# BTDeck 后端 Dockerfile
# 基于 Python 3.11-slim，多阶段构建优化镜像大小

FROM python:3.11-slim

# 设置标签
LABEL maintainer="BTDeck Team"
LABEL description="BTDeck 后端服务 - FastAPI + Python 3.11"

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_DIR=/app/logs \
    CONFIG_DIR=/app/config \
    TZ=Asia/Shanghai \
    # 使用清华镜像源加速pip下载
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    # 增加pip超时时间
    PIP_DEFAULT_TIMEOUT=300

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    curl \
    # 数据库迁移工具
    alembic \
    # 清理缓存
    && rm -rf /var/lib/apt/lists/* \
    # 创建非特权用户
    && groupadd -g 1001 appgroup \
    && useradd -u 1001 -g 1001 -m -d /home/appuser -s /bin/bash appuser

# 创建必要的目录并设置权限
RUN mkdir -p /app/logs /app/config /app/data && \
    chown -R appuser:appgroup /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir uvicorn[standard]

# 复制应用代码
COPY . .

# 设置启动脚本权限
RUN chmod +x /app/btdeck_startup.sh && \
    chown -R appuser:appgroup /app

# 切换到非特权用户
USER appuser

# 暴露端口
EXPOSE 5001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5001/docs || exit 1

# 启动命令
CMD ["/app/btdeck_startup.sh"]
