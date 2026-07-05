#!/bin/bash

# ============================================
# BTDeck Docker 镜像本地构建脚本
# 仅构建本地镜像，不推送至镜像仓库
#
# 镜像标签：
#   btdeck-backend:latest   / btdeck-backend:<version>
#   btdeck-frontend:latest  / btdeck-frontend:<version>
#
# <version> 自动从 feature_list.json 中最新的 features[].id 读取
# ============================================

set -euo pipefail

# ---------- 配置 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FEATURE_LIST="${SCRIPT_DIR}/feature_list.json"

BACKEND_IMAGE="btdeck-backend"
FRONTEND_IMAGE="btdeck-frontend"

# ---------- 颜色输出 ----------
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

print_success() { echo -e "${GREEN}[OK] $1${NC}"; }
print_info()    { echo -e "${BLUE}[INFO] $1${NC}"; }
print_warn()    { echo -e "${YELLOW}[WARN] $1${NC}"; }
print_error()   { echo -e "${RED}[ERROR] $1${NC}"; }

# ---------- 前置检查 ----------

# 检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        exit 1
    fi
    print_success "Docker 已安装"
}

# 检查工作目录是否为仓库根（包含 backend/ 与 frontend/）
check_workdir() {
    if [[ ! -d "${SCRIPT_DIR}/backend" || ! -d "${SCRIPT_DIR}/frontend" ]]; then
        print_error "未在仓库根目录找到 backend/ 或 frontend/，请确认脚本位于仓库根目录"
        exit 1
    fi
}

# 从 feature_list.json 读取最新已发布版本号
# 策略：在 features[] 中筛选 status=done 且 id 形如 v1.0.5 的语义化版本，取最大者
# 这样可避免误选 status=pending 的未来版本（如 v1.1.0）
resolve_version() {
    if [[ ! -f "${FEATURE_LIST}" ]]; then
        print_warn "未找到 feature_list.json，将仅打 :latest 标签"
        VERSION=""
        return
    fi
    # 探测可用的 python：优先 python3，但在 Windows 上 python3 可能是
    # Microsoft Store 别名（无执行权限），因此逐个验证可用性后回退
    local PY=""
    for candidate in python3 python; do
        if command -v "${candidate}" &> /dev/null \
           && "${candidate}" --version &> /dev/null; then
            PY="$(command -v "${candidate}")"
            break
        fi
    done
    if [[ -z "${PY}" ]]; then
        print_warn "未找到可用的 python，无法解析版本号，将仅打 :latest 标签"
        VERSION=""
        return
    fi
    VERSION="$("${PY}" - <<'PY' "${FEATURE_LIST}"
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)
def parse_ver(fid):
    if not fid.startswith('v'):
        return None
    parts = fid[1:].split('.')
    if len(parts) != 3:
        return None
    try:
        return tuple(int(x) for x in parts)
    except ValueError:
        return None
done = []
for feat in data.get('features', []):
    if feat.get('status') != 'done':
        continue
    v = parse_ver(feat.get('id', ''))
    if v is not None:
        done.append(v)
if not done:
    sys.exit(0)
print('v' + '.'.join(str(x) for x in max(done)))
PY
)"
    if [[ -z "${VERSION}" ]]; then
        print_warn "feature_list.json 中没有 status=done 的语义化版本，将仅打 :latest 标签"
    else
        print_info "解析到版本号：${VERSION}"
    fi
}

# ---------- 构建逻辑 ----------

# 为给定镜像构造 -t 标签参数（始终包含 :latest，VERSION 非空时追加 :<version>）
build_tags() {
    local image="$1"
    local tags=("-t" "${image}:latest")
    if [[ -n "${VERSION}" ]]; then
        tags+=("-t" "${image}:${VERSION}")
    fi
    printf '%s\n' "${tags[@]}"
}

# 构建后端镜像
build_backend() {
    print_info "构建后端镜像..."
    local tags
    mapfile -t tags < <(build_tags "${BACKEND_IMAGE}")

    docker build \
        "${tags[@]}" \
        "${SCRIPT_DIR}/backend"

    print_success "后端镜像构建完成"
}

# 构建前端镜像
build_frontend() {
    print_info "构建前端镜像..."
    local tags
    mapfile -t tags < <(build_tags "${FRONTEND_IMAGE}")

    docker build \
        -f "${SCRIPT_DIR}/frontend/Dockerfile.prod" \
        "${tags[@]}" \
        "${SCRIPT_DIR}/frontend"

    print_success "前端镜像构建完成"
}

# ---------- 主流程 ----------

main() {
    check_workdir
    check_docker
    resolve_version
    echo ""
    echo "=========================================="
    echo "  BTDeck Docker 镜像本地构建"
    [[ -n "${VERSION}" ]] && echo "  Version: ${VERSION}"
    echo "=========================================="
    echo ""

    build_backend
    echo ""
    build_frontend
    echo ""

    echo "=========================================="
    print_success "全部镜像构建完成（本地）"
    echo ""
    echo "镜像："
    echo "  - ${BACKEND_IMAGE}:latest"
    [[ -n "${VERSION}" ]] && echo "  - ${BACKEND_IMAGE}:${VERSION}"
    echo "  - ${FRONTEND_IMAGE}:latest"
    [[ -n "${VERSION}" ]] && echo "  - ${FRONTEND_IMAGE}:${VERSION}"
    echo ""
    echo "启动：docker compose up -d"
    echo "=========================================="
}

main "$@"
