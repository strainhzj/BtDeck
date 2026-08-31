#!/bin/bash

# ============================================
# BtDeck Linux 构建脚本
# 1.（release 模式）校验并消费唯一前端构建
# 2. 生成 build-info/source/frontend manifest（G1/G5）
# 3. PyInstaller 打包后端+前端+发布身份
# 4. fpm 制作 .deb/.rpm 安装包
#
# 模式（release-artifact-equivalence-gate W2）：
#   默认（dev）   ：自建前端、--allow-dirty 生成身份、fpm 缺失仅告警跳过
#   --release     ：必须消费 scripts/release/build_frontend.py 的唯一前端构建
#                   （dist 与 manifest 哈希一致）、工作区必须干净、
#                   fpm/任一制品/验证缺失即非零退出（fail-closed）
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
BACKEND_DIR="${PROJECT_DIR}/backend"
DEPLOY_DIR="${PROJECT_DIR}/deploy"
DIST_DIR="${PROJECT_DIR}/dist"
PACKAGE_REQUIREMENTS="${DEPLOY_DIR}/requirements-linux-package.txt"
PACKAGE_VENV="${PROJECT_DIR}/.venv-packaging-linux"
PACKAGE_PYTHON="${PACKAGE_VENV}/bin/python"
PACKAGE_PYINSTALLER="${PACKAGE_VENV}/bin/pyinstaller"
PACKAGE_PYTHON_VERSION="${BTDECK_PACKAGE_PYTHON_VERSION:-3.11}"

# 产品版本唯一输入：release/release-config.json（candidate.product_version），
# 本变量必须与之一致（版本一致性检查强制）
VERSION="1.0.6"
ARCH="amd64"

FRONTEND_DIST="${FRONTEND_DIR}/dist"
FRONTEND_MANIFEST="${PROJECT_DIR}/release/build/frontend/frontend-asset-manifest.json"
STAGING_DIR="${PROJECT_DIR}/release/build/linux-binary"

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

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

fail() { echo -e "${RED}[ERROR] $1${NC}"; exit 1; }

echo "============================================"
echo "  BtDeck Linux Build (mode: $([ "$RELEASE_MODE" = "1" ] && echo RELEASE || echo dev))"
echo "============================================"
echo ""

# 检查工具
check_tool() {
    if ! command -v "$1" &>/dev/null; then
        echo -e "${RED}[ERROR] $1 not found. Install: $2${NC}"
        exit 1
    fi
}

check_tool npm "https://nodejs.org/"
check_tool node "https://nodejs.org/"
check_tool python3 "https://www.python.org/"

if [ ! -f "$PACKAGE_REQUIREMENTS" ]; then
    fail "Packaging requirements not found: ${PACKAGE_REQUIREMENTS}"
fi

if [ ! -x "$PACKAGE_PYTHON" ]; then
    echo "[SETUP] Creating packaging venv: ${PACKAGE_VENV}"
    if command -v uv &>/dev/null; then
        UV_LINK_MODE="${UV_LINK_MODE:-copy}" uv venv --seed --python "$PACKAGE_PYTHON_VERSION" "$PACKAGE_VENV"
    else
        python3 -m venv "$PACKAGE_VENV" || fail "Failed to create venv with python3 (install python3-venv/python3-pip, or install uv and retry)"
    fi
fi

echo "[SETUP] Installing packaging dependencies (two-step: hash-verified lock + linux extras)..."
"$PACKAGE_PYTHON" -m pip install --upgrade pip setuptools wheel
"$PACKAGE_PYTHON" -m pip install --prefer-binary --require-hashes -r "${PROJECT_DIR}/backend/requirements-lock.txt"
"$PACKAGE_PYTHON" -m pip install --prefer-binary -r "$PACKAGE_REQUIREMENTS"

echo -e "${GREEN}[OK] packaging python: ${PACKAGE_PYTHON}${NC}"
"$PACKAGE_PYTHON" --version
echo -e "${GREEN}[OK] packaging pyinstaller: ${PACKAGE_PYINSTALLER}${NC}"

# 检查 fpm
if command -v fpm &>/dev/null; then
    BUILD_PACKAGE=1
else
    if [ "$RELEASE_MODE" = "1" ]; then
        fail "release 模式要求 fpm（gem install fpm 或在构建容器内提供）；不允许跳过打包"
    fi
    echo -e "${YELLOW}[WARN] fpm not found. Package build skipped (dev mode).${NC}"
    BUILD_PACKAGE=0
fi

# Step 0: 版本一致性（G1，fail-closed）
echo "[0/5] Version consistency check..."
cd "$PROJECT_DIR"
python3 scripts/release/generate_build_info.py --check-versions || fail "版本声明不一致（六处必须等于 release-config）"

# Step 1: 前端
if [ "$RELEASE_MODE" = "1" ]; then
    echo "[1/5] Consuming prebuilt frontend (single build)..."
    [ -f "$FRONTEND_MANIFEST" ] || fail "release 模式要求先运行 python scripts/release/build_frontend.py 生成唯一前端构建与 manifest"
    [ -f "${FRONTEND_DIST}/index.html" ] || fail "frontend/dist 缺失 index.html"
    python3 scripts/release/check_prebuilt_frontend.py "$FRONTEND_MANIFEST" "$FRONTEND_DIST" \
        || fail "frontend dist 与唯一构建 manifest 不一致（禁止在制品构建中重建前端）"
    echo -e "${GREEN}[OK] frontend dist matches single-build manifest${NC}"
else
    echo "[1/5] Building frontend (dev mode)..."
    cd "$FRONTEND_DIR"
    npm ci --legacy-peer-deps
    npm run build
    cd "$PROJECT_DIR"
fi

# Step 2: 生成发布身份（build-info + source/frontend manifest）
echo "[2/5] Generating release identity..."
GEN_ARGS="--artifact-kind linux-binary --output-dir ${STAGING_DIR} --node-version $(node -v | tr -d v)"
if [ "$RELEASE_MODE" != "1" ]; then
    GEN_ARGS="$GEN_ARGS --allow-dirty"
fi
python3 scripts/release/generate_build_info.py $GEN_ARGS || fail "生成发布身份失败（release 模式要求干净工作区）"

# Step 3: PyInstaller 打包
echo "[3/5] Building backend with PyInstaller..."
cd "$PROJECT_DIR"
"$PACKAGE_PYINSTALLER" --clean --noconfirm "${DEPLOY_DIR}/btdeck.spec"
echo -e "${GREEN}[OK] Backend packaged${NC}"

# Step 4: 内容级验证（G5，fail-closed；dev 构建同样包含发布身份，故无宽松分支）
echo "[4/5] Verifying package contents..."
"$PACKAGE_PYTHON" "${DEPLOY_DIR}/verify-package.py" --project-root "$PROJECT_DIR" --exe "${DIST_DIR}/btdeck"
echo -e "${GREEN}[OK] Package verification passed${NC}"

echo "[ANALYZE] Package size summary..."
"$PACKAGE_PYTHON" "${DEPLOY_DIR}/analyze-package-size.py" --exe "${DIST_DIR}/btdeck" --top 15 || true

# Step 5: fpm 制作安装包
if [ "$BUILD_PACKAGE" = "1" ]; then
    echo "[5/5] Building Linux packages..."

    mkdir -p "$DIST_DIR"

    INSTALL_DIR="/opt/btdeck"

    PKG_STAGING=$(mktemp -d)
    mkdir -p "${PKG_STAGING}${INSTALL_DIR}"
    mkdir -p "${PKG_STAGING}/etc/systemd/system"

    # 复制可执行文件
    cp "${DIST_DIR}/btdeck" "${PKG_STAGING}${INSTALL_DIR}/"
    chmod +x "${PKG_STAGING}${INSTALL_DIR}/btdeck"

    # 发布身份随包分发（计划 §4.3/§158：包内 /opt/btdeck/build-info.json 与二进制
    # 身份一致，唯 artifact_kind 为包型（linux-deb/linux-rpm）；二进制内嵌身份保持
    # linux-binary 中间制品语义。W3 生命周期断言包内 kind 必须是包型。
    cp "${STAGING_DIR}/build-info.json" "${STAGING_DIR}/source-manifest.json" "${STAGING_DIR}/frontend-asset-manifest.json" "${PKG_STAGING}${INSTALL_DIR}/"

    # 包内身份按包型改写 artifact_kind（就地单字段改写，其余字段与二进制逐字节一致；
    # 不重跑 generate_build_info.py——重跑会重算 build_id 等派生字段造成身份漂移）
    retag_build_info() {
        python3 - "$1" "${PKG_STAGING}${INSTALL_DIR}/build-info.json" <<'PYEOF' || fail "包内 build-info retag 失败（kind=$1）"
import json, sys

kind, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    before = json.load(f)
assert before["artifact_kind"] in ("linux-binary", "linux-deb", "linux-rpm"), f"retag 源 kind 异常：{before['artifact_kind']!r}"
info = dict(before, artifact_kind=kind)
with open(path, "w", encoding="utf-8", newline="\n") as f:
    json.dump(info, f, indent=2, sort_keys=True)
    f.write("\n")
with open(path, encoding="utf-8") as f:
    after = json.load(f)
stripped = lambda d: {k: v for k, v in d.items() if k != "artifact_kind"}
assert after["artifact_kind"] == kind and stripped(after) == stripped(before), "retag 后非 kind 字段发生漂移"
print(f"[OK] 包内 build-info retag: linux-binary -> {kind}")
PYEOF
    }
    retag_build_info linux-deb

    # 复制 systemd service 文件
    cp "${DEPLOY_DIR}/btdeck.service" "${PKG_STAGING}/etc/systemd/system/"

    # maintainer scripts（W3/G6，R11 修复）：语义见 deploy/package-scripts/ 注释
    # DEB: postinst + prerm(智能分支) + postrm(purge 清数据)；RPM 不传 postrm（%postun 数字参数不兼容）
    cp "${DEPLOY_DIR}/package-scripts/postinst.sh" "${PKG_STAGING}/postinst.sh"
    cp "${DEPLOY_DIR}/package-scripts/prerm.sh" "${PKG_STAGING}/prerm.sh"
    cp "${DEPLOY_DIR}/package-scripts/postrm.sh" "${PKG_STAGING}/postrm.sh"
    chmod +x "${PKG_STAGING}"/*.sh

    # 构建 .deb
    fpm -s dir --force \
        -t deb \
        -n btdeck \
        -v "${VERSION}" \
        -a "${ARCH}" \
        --description "BtDeck - BitTorrent Management Platform" \
        --url "https://github.com/strainhzj/BtDeck" \
        --license "GPL-3.0" \
        --after-install "${PKG_STAGING}/postinst.sh" \
        --before-remove "${PKG_STAGING}/prerm.sh" \
        --after-remove "${PKG_STAGING}/postrm.sh" \
        -C "${PKG_STAGING}" \
        --prefix / \
        -p "${DIST_DIR}/BtDeck-v${VERSION}-linux-${ARCH}.deb" \
        etc \
        opt

    # 构建 .rpm
    retag_build_info linux-rpm
    fpm -s dir --force \
        -t rpm \
        -n btdeck \
        -v "${VERSION}" \
        -a "${ARCH}" \
        --description "BtDeck - BitTorrent Management Platform" \
        --url "https://github.com/strainhzj/BtDeck" \
        --license "GPL-3.0" \
        --after-install "${PKG_STAGING}/postinst.sh" \
        --before-remove "${PKG_STAGING}/prerm.sh" \
        -C "${PKG_STAGING}" \
        --prefix / \
        -p "${DIST_DIR}/BtDeck-v${VERSION}-linux-${ARCH}.rpm" \
        etc \
        opt

    # 清理临时目录
    rm -rf "${PKG_STAGING}"

    echo -e "${GREEN}[OK] Packages built at ${DIST_DIR}/${NC}"
else
    echo "[5/5] Skipping package build (fpm not found, dev mode)"
    echo "       Executable ready at dist/btdeck"
fi

echo ""
echo "============================================"
echo "  Build complete!"
echo "============================================"
