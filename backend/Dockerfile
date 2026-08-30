# BTDeck 后端 Dockerfile
# 多阶段构建：builder 编译 wheel，runtime 仅装运行时依赖
# 设计目标：镜像精简（<550MB），不含 dev/test 工具、不含本地数据库与缓存

# ============================================
# 阶段1: builder - 编译所有依赖的 wheel
# ============================================
# 基础镜像 digest 固定（release-artifact-equivalence-gate W1/G2）：
# python:3.11-slim @ sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6
FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6 AS builder

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
# 同时替换 deb.debian.org 和 security.debian.org（Bookworm/Trixie deb822 格式）；
# APT_MIRROR 传 host-only 形态（如 mirrors.aliyun.com，apt 走 HTTP）。
# security 源必须先按最长路径映射到 <mirror>/debian-security，否则 404 会导致整个 update 失败。
# APT_MIRROR 为空则跳过
RUN if [ -n "$APT_MIRROR" ]; then \
        sed -i "s|security.debian.org/debian-security|${APT_MIRROR}/debian-security|g; s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单（requirements.txt 为直接依赖源，lock 为唯一安装输入）
COPY requirements.txt requirements-lock.txt ./

# 升级打包工具，并将锁定的全部依赖编译为 wheel 到 /build/wheels
# wheel 离线安装可让 runtime 阶段无需 gcc/联网
# pip 镜像源由上面的 ENV 自动生效（PIP_INDEX_URL 为空时走官方 PyPI）
# --require-hashes：锁内全量 ==+哈希，任何文件与哈希不符即失败（G2 fail-closed）
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip wheel --no-cache-dir --wheel-dir=/build/wheels --require-hashes -r requirements-lock.txt

# ============================================
# 阶段2: runtime - 生产运行时
# ============================================
# digest 同 builder 阶段（python:3.11-slim）
FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6

LABEL maintainer="BTDeck Team"
LABEL description="BTDeck 后端服务 - FastAPI + Python 3.11"

# OCI 身份标签（G1/G10）：正式构建由 build-images.sh / release-gate 注入
# --build-arg OCI_VERSION=1.0.6 OCI_REVISION=<40位SHA> OCI_CREATED=<RFC3339>
# 本地未注入时为空串；W2 严格构建模式会校验非空
ARG OCI_VERSION=""
ARG OCI_REVISION=""
ARG OCI_CREATED=""
ARG OCI_SOURCE="https://github.com/strainhzj/BtDeck"
LABEL org.opencontainers.image.title="BtDeck backend" \
      org.opencontainers.image.description="BTDeck 后端服务 - FastAPI + Python 3.11" \
      org.opencontainers.image.version="${OCI_VERSION}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.created="${OCI_CREATED}" \
      org.opencontainers.image.source="${OCI_SOURCE}"

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
# APT_MIRROR 为 host-only 形态；security 源路径映射同 builder 阶段说明
RUN if [ -n "$APT_MIRROR" ]; then \
        sed -i "s|security.debian.org/debian-security|${APT_MIRROR}/debian-security|g; s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
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
# 锁文件内嵌 --hash 行时 pip 会自动启用哈希校验模式；sdist 构建出的 wheel
# （gmssl/ping3/bencodepy 等无二进制轮子）哈希必然不同于 PyPI 源哈希而误杀。
# 因此运行时安装改用去哈希的 pins（版本全部 == 精确锁定）：
#   完整性锚点 = builder 阶段 pip wheel --require-hashes 的下载校验；
#   端到端一致性 = 本步 pip check + W2 从镜像真实环境 pip freeze 与锁逐包比对。
COPY requirements-lock.txt /tmp/requirements-lock.txt
COPY --from=builder /build/wheels /tmp/wheels
RUN sed -e '/^[[:space:]]*--hash/d' -e 's/[[:space:]]*\\$//' /tmp/requirements-lock.txt \
        | grep -E '^[A-Za-z0-9]' > /tmp/pins.txt \
    && pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r /tmp/pins.txt \
    && pip check \
    && rm -rf /tmp/wheels /tmp/requirements-lock.txt /tmp/pins.txt

# 创建必要的目录并设置权限
RUN mkdir -p /app/logs /app/config /app/data && \
    chown -R appuser:appgroup /app/logs /app/config /app/data

# 复制应用代码（用 --chown 一步完成拷贝+属主设置，避免后续 chown -R 制造重复层）
COPY --chown=appuser:appgroup . .

# 发布身份（W2/G1）：由 build-images.sh 生成并复制进构建上下文；
# backend/app/core/build_info.py 的候选路径包含 /app/build-info.json
COPY --chown=appuser:appgroup build-info.json /app/build-info.json

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
