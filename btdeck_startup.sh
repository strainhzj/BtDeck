#!/bin/bash
# btdeck_startup.sh - BTDeck 后端启动脚本（简化版）
# 专为 Docker 容器环境设计

set -e  # 遇到错误立即退出

# 配置区
PROJECT_DIR="/app"
APP_MODULE="app.main:app"
PORT=5001
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/logs}"
WORKERS=${WORKERS:-1}  # Docker环境通常设置为1

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查日志目录
ensure_log_dir() {
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR" || {
            log_warn "无法创建日志目录，日志输出到控制台"
            LOG_DIR="/dev"
        }
    fi

    # 测试写权限
    if [ "$LOG_DIR" != "/dev" ]; then
        if ! touch "$LOG_DIR/.write_test" 2>/dev/null; then
            log_warn "日志目录无写权限，日志输出到控制台"
            LOG_DIR="/dev"
        else
            rm -f "$LOG_DIR/.write_test"
        fi
    fi
}

# 初始化数据库
init_database() {
    log_info "初始化数据库..."
    cd "$PROJECT_DIR"

    # 初始化配置文件
    python -c "from app.database import init_config_file; init_config_file();" 2>/dev/null || true

    # 执行数据库迁移
    log_info "执行数据库迁移..."
    alembic upgrade head || {
        log_error "数据库迁移失败！"
        exit 1
    }

    log_info "数据库初始化完成"
}

# 启动服务
start_server() {
    log_info "正在启动 BTDeck 后端服务..."
    log_info "端口: $PORT"
    log_info "工作进程: $WORKERS"

    # 设置环境变量
    export PYTHONPATH=$PROJECT_DIR:$PYTHONPATH

    # 使用 uvicorn 启动
    exec uvicorn "$APP_MODULE" \
        --host 0.0.0.0 \
        --port $PORT \
        --workers $WORKERS \
        --loop asyncio \
        --log-level info
}

# 主流程
main() {
    log_info "========================================"
    log_info "BTDeck 后端服务启动中..."
    log_info "========================================"

    ensure_log_dir
    init_database
    start_server
}

# 执行主流程
main
