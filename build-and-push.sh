#!/bin/bash

# ============================================
# BTDeck Docker 镜像构建和推送脚本
# 版本: v1.0.9
# 用户: strainthomas
# ============================================

set -e

# 配置变量
DOCKER_USERNAME="strainthomas"
VERSION="v1.0.9"
BACKEND_IMAGE="${DOCKER_USERNAME}/btdeck-backend"
FRONTEND_IMAGE="${DOCKER_USERNAME}/btdeck-frontend"

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# 检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker not installed"
        exit 1
    fi
    print_success "Docker installed"
}

# 检查是否登录 Docker Hub
check_docker_login() {
    print_info "Checking Docker Hub login..."
    if ! docker info | grep -q "Username: ${DOCKER_USERNAME}"; then
        print_info "Please login to Docker Hub (username: ${DOCKER_USERNAME})"
        docker login
    else
        print_success "Already logged in to Docker Hub"
    fi
}

# 构建后端镜像
build_backend() {
    print_info "Building backend image..."
    cd backend

    docker build \
        -t ${BACKEND_IMAGE}:latest \
        -t ${BACKEND_IMAGE}:${VERSION} \
        .

    print_success "Backend image built"
    cd ..
}

# 推送后端镜像
push_backend() {
    print_info "Pushing backend image..."

    docker push ${BACKEND_IMAGE}:latest
    print_success "Backend image (latest) pushed"

    docker push ${BACKEND_IMAGE}:${VERSION}
    print_success "Backend image (${VERSION}) pushed"
}

# 构建前端镜像
build_frontend() {
    print_info "Building frontend image..."
    cd frontend

    docker build \
        -f Dockerfile.prod \
        -t ${FRONTEND_IMAGE}:latest \
        -t ${FRONTEND_IMAGE}:${VERSION} \
        .

    print_success "Frontend image built"
    cd ..
}

# 推送前端镜像
push_frontend() {
    print_info "Pushing frontend image..."

    docker push ${FRONTEND_IMAGE}:latest
    print_success "Frontend image (latest) pushed"

    docker push ${FRONTEND_IMAGE}:${VERSION}
    print_success "Frontend image (${VERSION}) pushed"
}

# 主函数
main() {
    echo "=========================================="
    echo "  BTDeck Docker Image Build & Push"
    echo "  Version: ${VERSION}"
    echo "  User: ${DOCKER_USERNAME}"
    echo "=========================================="
    echo ""

    check_docker
    check_docker_login
    echo ""

    build_backend
    push_backend
    echo ""

    build_frontend
    push_frontend
    echo ""

    echo "=========================================="
    print_success "All images built and pushed!"
    echo ""
    echo "Images:"
    echo "  - ${BACKEND_IMAGE}:latest"
    echo "  - ${BACKEND_IMAGE}:${VERSION}"
    echo "  - ${FRONTEND_IMAGE}:latest"
    echo "  - ${FRONTEND_IMAGE}:${VERSION}"
    echo "=========================================="
}

main
