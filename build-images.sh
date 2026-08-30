#!/bin/bash

# ============================================
# BTDeck Docker 镜像本地构建脚本
# 仅构建本地镜像，不推送至镜像仓库
#
# 模式（release-artifact-equivalence-gate W2）：
#   默认（dev）  ：frontend/Dockerfile.prod 内自建前端（历史行为），
#                  身份生成用 --allow-dirty，latest+version 双标签
#   --release    ：消费 scripts/release/build_frontend.py 的唯一前端构建
#                  （frontend/Dockerfile.release + 组装上下文，不在镜像内
#                  重建前端）、六处版本一致、OCI label 构建后强校验、
#                  记录镜像 digest 到 release/build/docker-images.txt
#
# 镜像标签：
#   btdeck-backend:latest   / btdeck-backend:<version>
#   btdeck-frontend:latest  / btdeck-frontend:<version>
#   latest 仅本地便利标签（计划 §0.5），发布身份以 digest/版本标签为准
# ============================================

set -euo pipefail

# ---------- 配置 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FEATURE_LIST="${SCRIPT_DIR}/feature_list.json"
PROJECT_DIR="${SCRIPT_DIR}"
GEN_ROOT="${PROJECT_DIR}/release/build"

BACKEND_IMAGE="btdeck-backend"
FRONTEND_IMAGE="btdeck-frontend"

RELEASE_MODE=0
for arg in "$@"; do
    case "$arg" in
        --release) RELEASE_MODE=1 ;;
        *)
            echo "[ERROR] 未知参数: $arg（支持: --release）"
            exit 2
            ;;
    esac
done

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

fail() { print_error "$1"; exit 1; }

# ---------- 前置检查 ----------

check_docker() {
    command -v docker &> /dev/null || fail "Docker 未安装"
    print_success "Docker 已安装"
}

check_workdir() {
    [[ -d "${SCRIPT_DIR}/backend" && -d "${SCRIPT_DIR}/frontend" ]] \
        || fail "未在仓库根目录找到 backend/ 或 frontend/"
}

resolve_python() {
    for candidate in python3 python; do
        if command -v "${candidate}" &> /dev/null && "${candidate}" --version &> /dev/null; then
            PY="$(command -v "${candidate}")"
            return 0
        fi
    done
    fail "未找到可用的 python（生成发布身份需要）"
}

# 从 feature_list.json 读取版本号（回退策略与历史行为一致）
resolve_version() {
    if [[ ! -f "${FEATURE_LIST}" ]]; then
        print_warn "未找到 feature_list.json，将仅打 :latest 标签"
        VERSION=""
        return
    fi
    # 相对路径传给原生 python（Git-Bash 下 /c/... 形式 Windows python 无法打开）
    VERSION="$(cd "${SCRIPT_DIR}" && "${PY}" - <<'PYEOF' feature_list.json
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)
release = data.get('release_version')
if release:
    print('v' + str(release).lstrip('v'))
    sys.exit(0)
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
PYEOF
)"
    if [[ -z "${VERSION}" ]]; then
        [[ "${RELEASE_MODE}" = "1" ]] && fail "release 模式无法解析版本号（feature_list.release_version）"
        print_warn "feature_list.json 中没有可用版本，将仅打 :latest 标签"
    else
        print_info "解析到版本号：${VERSION}"
    fi
}

# ---------- 发布身份 ----------

generate_identity() {
    local kind="$1"
    local out="release/build/${kind}"
    local node_arg=""
    local meta="release/build/frontend/frontend-build-meta.json"
    if [[ -f "$meta" ]]; then
        node_arg="--node-version $("${PY}" -c "import json;print(json.load(open(r'${meta}',encoding='utf-8'))['toolchain']['node'])" 2>/dev/null || true)"
    fi
    local args="--artifact-kind ${kind} --output-dir ${out} ${node_arg}"
    if [[ "${RELEASE_MODE}" != "1" ]]; then
        args="${args} --allow-dirty"
    fi
    # shellcheck disable=SC2086
    "${PY}" scripts/release/generate_build_info.py ${args} \
        || fail "生成 ${kind} 发布身份失败（release 模式要求干净工作区+六处版本一致）"
}

read_identity() {
    # 读取 docker-backend 身份作为两镜像共享的 SHA/版本锚点（相对路径，见 generate_identity 注释）
    "${PY}" - release/build/docker-backend/build-info.json <<'PYEOF'
import json, sys
from datetime import datetime, timezone

info = json.load(open(sys.argv[1], encoding='utf-8'))
created = datetime.fromtimestamp(int(info["source_date_epoch"]), tz=timezone.utc).isoformat().replace("+00:00", "Z")
print(info["product_version"].lstrip("v"))
print(info["git_sha"])
print(created)
PYEOF
}

verify_labels() {
    local image="$1" expect_version="$2" expect_revision="$3"
    local got_version got_revision
    got_version="$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$image")"
    got_revision="$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")"
    if [[ "${got_version}" != "${expect_version}" || "${got_revision}" != "${expect_revision}" ]]; then
        fail "OCI label 校验失败（${image}）：version=${got_version:-<empty>} revision=${got_revision:-<empty>}"
    fi
    print_success "OCI labels verified: ${image} (v${expect_version} @${expect_revision:0:12})"
}

record_images() {
    : > "${GEN_ROOT}/docker-images.txt"
    for image in "${BACKEND_IMAGE}:${VERSION}" "${FRONTEND_IMAGE}:${VERSION}"; do
        docker inspect --format "${image} {{.Id}}" "$image" >> "${GEN_ROOT}/docker-images.txt"
    done
    print_success "镜像 ID 已记录：${GEN_ROOT}/docker-images.txt（registry digest 于推送/晋级时补记，W5）"
}

# ---------- 主流程 ----------

main() {
    check_workdir
    check_docker
    resolve_python
    resolve_version
    cd "${PROJECT_DIR}"

    echo ""
    echo "=========================================="
    echo "  BTDeck Docker 镜像构建（mode: $([[ "${RELEASE_MODE}" = "1" ]] && echo RELEASE || echo dev)）"
    [[ -n "${VERSION}" ]] && echo "  Version: ${VERSION}"
    echo "=========================================="
    echo ""

    # Step 1: 版本一致性 + 发布身份
    "${PY}" scripts/release/generate_build_info.py --check-versions \
        || fail "六处版本声明不一致"
    generate_identity docker-backend
    generate_identity docker-frontend

    mapfile -t IDENTITY < <(read_identity | tr -d '')
    OCI_VERSION="${IDENTITY[0]}"
    OCI_REVISION="${IDENTITY[1]}"
    OCI_CREATED="${IDENTITY[2]}"
    print_info "identity: v${OCI_VERSION} @${OCI_REVISION:0:12} created=${OCI_CREATED}"

    # Step 2: 组装上下文 / build args（相对路径：Git-Bash 下 /c/... 形式
    # Windows docker/python CLI 均无法消费，脚本已在 PROJECT_DIR 下执行）
    cp release/build/docker-backend/build-info.json backend/build-info.json
    local backend_tags=(-t "${BACKEND_IMAGE}:latest")
    [[ -n "${VERSION}" ]] && backend_tags+=(-t "${BACKEND_IMAGE}:${VERSION}")
    local backend_ctx="backend"
    local backend_file="backend/Dockerfile"

    local frontend_tags frontend_ctx frontend_file
    if [[ "${RELEASE_MODE}" = "1" ]]; then
        # 唯一前端构建：校验一致性后组装独立上下文（绕开 frontend/.dockerignore 的 dist/ 排除）
        "${PY}" scripts/release/check_prebuilt_frontend.py \
            "release/build/frontend/frontend-asset-manifest.json" "frontend/dist" \
            || fail "frontend dist 与唯一构建 manifest 不一致；请先运行 scripts/release/build_frontend.py"
        frontend_ctx="release/build/frontend-ctx"
        rm -rf "${frontend_ctx}"
        mkdir -p "${frontend_ctx}"
        cp -r frontend/dist "${frontend_ctx}/dist"
        cp release/build/docker-frontend/build-info.json "${frontend_ctx}/build-info.json"
        cp frontend/nginx.conf "${frontend_ctx}/nginx.conf"
        frontend_file="frontend/Dockerfile.release"
    else
        cp release/build/docker-frontend/build-info.json frontend/build-info.json
        frontend_ctx="frontend"
        frontend_file="frontend/Dockerfile.prod"
    fi
    frontend_tags=(-t "${FRONTEND_IMAGE}:latest")
    [[ -n "${VERSION}" ]] && frontend_tags+=(-t "${FRONTEND_IMAGE}:${VERSION}")

    local oci_args=(
        --build-arg OCI_VERSION="${OCI_VERSION}"
        --build-arg OCI_REVISION="${OCI_REVISION}"
        --build-arg OCI_CREATED="${OCI_CREATED}"
    )
    # 可选镜像源透传（本机慢网环境；CI 不设置即走官方源）
    [[ -n "${BTDECK_APT_MIRROR:-}" ]] && oci_args+=(--build-arg APT_MIRROR="${BTDECK_APT_MIRROR}")
    [[ -n "${BTDECK_PIP_INDEX_URL:-}" ]] && oci_args+=(--build-arg PIP_INDEX_URL="${BTDECK_PIP_INDEX_URL}")
    [[ -n "${BTDECK_NPM_REGISTRY:-}" ]] && oci_args+=(--build-arg NPM_REGISTRY="${BTDECK_NPM_REGISTRY}")

    # Step 3: 构建
    print_info "构建后端镜像..."
    docker build "${oci_args[@]}" "${backend_tags[@]}" -f "${backend_ctx}/Dockerfile" "${backend_ctx}"
    print_success "后端镜像构建完成"

    print_info "构建前端镜像..."
    docker build "${oci_args[@]}" "${frontend_tags[@]}" -f "${frontend_file}" "${frontend_ctx}"
    print_success "前端镜像构建完成"

    # Step 4: label 校验（fail-closed；dev 身份同样携带真实 SHA）
    local version_tag="${VERSION}"  # 镜像 tag 携带 v 前缀（与 OCI label 的裸版本区分）
    verify_labels "${BACKEND_IMAGE}:${version_tag:-latest}" "${OCI_VERSION}" "${OCI_REVISION}"
    verify_labels "${FRONTEND_IMAGE}:${version_tag:-latest}" "${OCI_VERSION}" "${OCI_REVISION}"

    # Step 5: 记录
    if [[ -n "${VERSION}" ]]; then
        record_images
    fi

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
