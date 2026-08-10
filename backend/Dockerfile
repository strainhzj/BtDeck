# BTDeck 后端 Dockerfile
# 多阶段构建：builder 编译 wheel，runtime 仅装运行时依赖
# 设计目标：镜像精简（<550MB），不含 dev/test 工具、不含本地数据库与缓存

# ============================================
# 阶段1: builder - 编译所有依赖的 wheel
# ============================================
FROM python:3.11-slim AS builder

LABEL maintainer="BTDeck Team"
LABEL description="BTDeck 后端构建阶段 - wheel 编译"

# 镜像源参数化（默认空串 = 走官方源，与改造前行为一致）
# 由 build-and-export-images.bat 通过 --build-arg 注入，构建失败可切换备用源重试
ARG APT_MIRROR=
ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=
# 通过 ENV 让本阶段所有 pip 命令（含 pip install --upgrade）自动读取镜像源
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

WORKDIR /build

# 安装编译工具链（仅 builder，不进 runtime）
# gcc/build-essential: 编译 C 扩展；libffi-dev: bcrypt/cryptography 头文件；libssl-dev: SSL 头文件
# 同时替换 deb.debian.org 和 security.debian.org（Bookworm deb822 格式）；APT_MIRROR 为空则跳过
RUN if [ -n "$APT_MIRROR" ]; then \
        sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
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
# pip 镜像源由上面的 ENV 自动生效（PIP_INDEX_URL 为空时走官方 PyPI）
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements.txt

# ============================================
# 阶段2: runtime - 生产运行时
# ============================================
FROM python:3.11-slim

LABEL maintainer="BTDeck Team"
LABEL description="BTDeck 后端服务 - FastAPI + Python 3.11"

# runtime 阶段只重新声明 APT_MIRROR（离线装 wheel 不需要 PIP_*）
# 注意：ARG 不能跨 FROM 继承，必须在本阶段重新声明才能在 sed 中使用
ARG APT_MIRROR=

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
RUN if [ -n "$APT_MIRROR" ]; then \
        sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
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
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD curl -f http://localhost:5001/health/ready || exit 1

# 启动命令
CMD ["/app/btdeck_startup.sh"]
