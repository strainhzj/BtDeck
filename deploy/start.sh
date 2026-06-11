#!/bin/bash

# ============================================
# BtDeck Docker 一键启动脚本 (Linux/macOS)
# ============================================

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 检查 Docker
check_docker() {
    if ! command -v docker &>/dev/null; then
        echo -e "${RED}Docker not installed. Install: https://docs.docker.com/get-docker/${NC}"
        exit 1
    fi
    if ! docker info &>/dev/null 2>&1; then
        echo -e "${RED}Docker is not running. Please start Docker first.${NC}"
        exit 1
    fi
}

# 检查 Docker Compose
check_compose() {
    if docker compose version &>/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &>/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
    else
        echo -e "${RED}Docker Compose not installed.${NC}"
        exit 1
    fi
}

start() {
    echo -e "${GREEN}Starting BtDeck...${NC}"
    check_docker
    check_compose

    cd "$PROJECT_DIR"
    $COMPOSE_CMD up -d --build

    echo ""
    echo -e "${GREEN}BtDeck started!${NC}"
    echo "Visit: http://localhost:${BTDECK_PORT:-8080}"
}

stop() {
    check_docker
    check_compose

    cd "$PROJECT_DIR"
    echo "Stopping BtDeck..."
    $COMPOSE_CMD down
    echo -e "${GREEN}BtDeck stopped.${NC}"
}

status() {
    check_docker
    check_compose

    cd "$PROJECT_DIR"
    $COMPOSE_CMD ps
}

logs() {
    check_docker
    check_compose

    cd "$PROJECT_DIR"
    $COMPOSE_CMD logs -f --tail=100
}

case "${1:-start}" in
    start)   start   ;;
    stop)    stop    ;;
    restart) stop && start ;;
    status)  status  ;;
    logs)    logs    ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
