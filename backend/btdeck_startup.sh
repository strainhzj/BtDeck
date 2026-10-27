#!/bin/bash
# btdeck_startup.sh - BTDeck 后端启动脚本（简化版）
# 专为 Docker 容器环境设计
#
# ⚠️ SQLite 单 Worker 启动约束（W2-4 / P0-06）：
# 不能通过启动多个 SQLite Worker 缓解接口卡顿！
# resource_guard 与 Python 信号量均为进程内对象，多 Worker 会使锁与资源准入失效，
# 且每个 Worker 都可能各自启动 scheduler，导致定时任务重复执行。
# 本脚本在启动前做 fail-fast 校验（规则与 app/core/startup_guard.py 保持一致，改动需同步两边）。

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

# ==== 单 Worker 启动约束（W2-4 / P0-06 + v1.0.8 契约 §1，fail-fast）====
# 解析后端类型：DB_TYPE 环境变量优先（v1.0.8 唯一方言判据，契约 §2.1）；
# DB_TYPE 未设时兼容旧 DATABASE_URL scheme 判别（废弃路径）；均未设按默认 SQLite 文件库。
detect_backend_type() {
    local db_type="${DB_TYPE:-}"
    db_type="${db_type,,}"  # 转小写
    case "$db_type" in
        postgresql | postgres | pg) echo "postgres" ;;
        sqlite) echo "sqlite" ;;
        *)
            local url="${DATABASE_URL:-}"
            case "$url" in
                sqlite* | sqlite3*) echo "sqlite" ;;
                postgres* | postgresql*) echo "postgres" ;;
                mysql* | mariadb*) echo "mysql" ;;
                "") echo "sqlite" ;;  # 未配置即默认 SQLite 文件库
                *) echo "other" ;;
            esac
            ;;
    esac
}

# 启动前 fail-fast：SQLite 后端 + WORKERS != 1 直接拒绝启动。
# 注意：不能通过启动多个 SQLite Worker 缓解接口卡顿。
check_worker_config() {
    local backend
    backend=$(detect_backend_type)
    if [ "$backend" = "sqlite" ] && [ "$WORKERS" -ne 1 ]; then
        log_error "========================================"
        log_error "启动约束校验失败：SQLite 后端禁止多 Worker 启动"
        log_error "当前 DB_TYPE=${DB_TYPE:-<未设置，默认 SQLite>}，WORKERS=$WORKERS"
        log_error "SQLite 文件库的写锁治理与资源准入（db_write_scope / 信号量）均为进程内对象，"
        log_error "多 Worker 会使锁与准入失效并放大写锁争用，且各进程都会各自启动 scheduler；"
        log_error "不能通过启动多个 SQLite Worker 缓解接口卡顿。请将 WORKERS 改为 1 后重启。"
        log_error "========================================"
        exit 1
    fi
    # v1.0.8 契约 §1：PG 单实例单 worker 交付边界，多 worker fail-fast
    if [ "$backend" = "postgres" ] && [ "$WORKERS" -ne 1 ]; then
        log_error "========================================"
        log_error "启动约束校验失败：PostgreSQL 后端当前仅支持单 Worker"
        log_error "当前 DB_TYPE=$DB_TYPE，WORKERS=$WORKERS"
        log_error "v1.0.8 交付边界为单应用实例单 worker（docs/postgresql-contract.md §1）："
        log_error "scheduler Leader 选举与多实例写入治理未实现，多 Worker 会重复执行定时任务。"
        log_error "请将 WORKERS 改为 1 后重启；多实例扩展另行立项。"
        log_error "========================================"
        exit 1
    fi
}

# 启动服务
start_server() {
    log_info "正在启动 BTDeck 后端服务..."
    log_info "端口: $PORT"
    log_info "工作进程: $WORKERS"

    # 设置环境变量
    export PYTHONPATH=$PROJECT_DIR:$PYTHONPATH

    # 使用 uvicorn 启动。log-level 读 LOG_LEVEL 环境变量（默认 info），
    # uvicorn 要求小写（critical/error/warning/info/debug/trace），此处统一转小写。
    LOG_LEVEL_LOWER="${LOG_LEVEL:-info}"
    LOG_LEVEL_LOWER="${LOG_LEVEL_LOWER,,}"  # bash 参数扩展：转小写
    exec uvicorn "$APP_MODULE" \
        --host 0.0.0.0 \
        --port $PORT \
        --workers $WORKERS \
        --loop asyncio \
        --log-level "$LOG_LEVEL_LOWER"
}

# 主流程
main() {
    log_info "========================================"
    log_info "BTDeck 后端服务启动中..."
    log_info "========================================"

    ensure_log_dir
    # 四轨治理后：shell 层只负责环境准备 + 启动 uvicorn。
    # 配置初始化(init_config_file)、数据库迁移(migrate_database)、seed(init_db)
    # 全部由 FastAPI lifespan 统一负责，避免重复执行。
    # W2-4：启动前执行 SQLite 单 Worker 约束校验（fail-fast）
    check_worker_config
    start_server
}

# 执行主流程
main
