# BTDeck 前端 Dockerfile（简化版）
# 适用于快速构建和部署

FROM node:18.20.1-slim

LABEL maintainer="BTDeck Team"
LABEL description="BTDeck 前端应用"

# 设置工作目录
WORKDIR /app

# 安装构建依赖（使用阿里云镜像源加速）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
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
RUN npm ci --legacy-peer-deps && npm cache clean --force

# 复制项目文件
COPY . .

# 复制环境配置（如果存在）
RUN if [ -f .env.production ]; then cp .env.production .env; fi

# 暴露端口
EXPOSE 8080

# 启动开发服务（可根据需要修改为 npm run build）
CMD ["npm", "run", "serve"]
