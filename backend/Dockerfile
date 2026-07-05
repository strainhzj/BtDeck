# BTDeck 后端 Dockerfile
# 多阶段构建：builder 编译 wheel，runtime 仅装运行时依赖
# 设计目标：镜像精简（<550MB），不含 dev/test 工具、不含本地数据库与缓存

# ============================================
# 阶段1: builder - 编译所有依赖的 wheel
# ============================================
FROM python:3.11-slim AS builder

LABEL maintainer="BTDeck Team"
LABEL description="BTDeck 后端构建阶段 - wheel 编译"

WORKDIR /build

# 安装编译工具链（仅 builder，不进 runtime）
# gcc/build-essential: 编译 C 扩展；libffi-dev: bcrypt/cryptography 头文件；libssl-dev: SSL 头文件
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单
COPY requirements.txt .

# 升级打包工具，并将所有依赖编译为 wheel 到 /build/wheels
# wheel 离线安装可让 runtime 阶段无需 gcc/联网
ENV PIP_DEFAULT_TIMEOUT=300
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements.txt

# ============================================
# 阶段2: runtime - 生产运行时
# ============================================
FROM python:3.11-slim

LABEL maintainer="BTDeck Team"
LABEL description="BTDeck 后端服务 - FastAPI + Python 3.11"

# 设置环境变量
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_DIR=/app/logs \
    CONFIG_DIR=/app/config \
    TZ=Asia/Shanghai

# 安装运行时系统依赖（最小集）
# curl: 健康检查；tzdata: 时区数据
# 创建非特权用户 appuser (uid=1001)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && groupadd -g 1001 appgroup \
    && useradd -u 1001 -g 1001 -m -d /home/appuser -s /bin/bash appuser

WORKDIR /app

# 离线安装 wheel（不联网，不依赖 builder 镜像）
# 用 -r requirements.txt 让 pip 自解析依赖与 extras，避免手动构造包名列表的歧义
COPY requirements.txt /tmp/requirements.txt
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels \
    -r /tmp/requirements.txt \
    && rm -rf /tmp/wheels /tmp/requirements.txt

# 创建必要的目录并设置权限
RUN mkdir -p /app/logs /app/config /app/data && \
    chown -R appuser:appgroup /app/logs /app/config /app/data

# 复制应用代码（用 --chown 一步完成拷贝+属主设置，避免后续 chown -R 制造重复层）
COPY --chown=appuser:appgroup . .

# 转换启动脚本的 CRLF→LF（防止 Windows 行尾导致 shebang 失效：exec ... no such file）
# 并设置可执行权限
RUN sed -i 's/\r$//' /app/btdeck_startup.sh && chmod +x /app/btdeck_startup.sh

# 切换到非特权用户
USER appuser

# 暴露端口
EXPOSE 5001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5001/docs || exit 1

# 启动命令
CMD ["/app/btdeck_startup.sh"]
