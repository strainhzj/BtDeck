# BTDeck 前端 Dockerfile（简化版）
# 适用于快速构建和部署

# Node 22 线（与 Dockerfile.prod/regression.yml 统一，W0 实测 22.23.2），digest 固定（W1/G2）
FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5

LABEL maintainer="BTDeck Team"
LABEL description="BTDeck 前端应用"

# 镜像源参数化（默认空串 = 走官方源，与改造前行为一致）
# 由 build-and-export-images.bat 通过 --build-arg 注入，构建失败可切换备用源重试
ARG APT_MIRROR=
ARG NPM_REGISTRY=
# 通过 ENV 让所有 npm 命令自动读取 registry（空串时走官方 npmjs.org）
ENV NPM_CONFIG_REGISTRY=${NPM_REGISTRY}

# 设置工作目录
WORKDIR /app

# 安装构建依赖
# 同时替换 deb.debian.org 和 security.debian.org（Bookworm deb822 格式）；APT_MIRROR 为空则跳过
RUN if [ -n "$APT_MIRROR" ]; then \
        sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 设置 node-gyp 使用 Python3
ENV PYTHON=/usr/bin/python3

# 复制 package 文件
COPY package*.json ./

# 安装依赖
# npm registry 由上面的 ENV 自动生效（NPM_REGISTRY 为空时走官方 npmjs.org）
RUN npm ci --legacy-peer-deps && npm cache clean --force

# 复制项目文件
COPY . .

# 复制环境配置（如果存在）
RUN if [ -f .env.production ]; then cp .env.production .env; fi

# 暴露端口
EXPOSE 8080

# 启动开发服务（可根据需要修改为 npm run build）
CMD ["npm", "run", "serve"]
