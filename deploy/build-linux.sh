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
    python3 - "$FRONTEND_MANIFEST" "$FRONTEND_DIST" <<'PY' || fail "frontend dist 与唯一构建 manifest 不一致（禁止在制品构建中重建前端）"
import json
import pathlib
import sys

manifest_path, dist_dir = sys.argv[1], pathlib.Path(sys.argv[2])
sys.path.insert(0, str(pathlib.Path("scripts/release").resolve()))
from generate_build_info import build_frontend_asset_manifest  # noqa: E402

stored = json.loads(manifest_path.read_text(encoding="utf-8"))
_, recomputed = build_frontend_asset_manifest(dist_dir)
if stored.get("manifest_sha256") != recomputed:
    print(
        f"[FAIL] frontend manifest mismatch: stored={stored.get('manifest_sha256')} "
        f"recomputed={recomputed}",
        file=sys.stderr,
    )
    sys.exit(1)
PY
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

    # 发布身份随包分发（计划 §4.3：包内 /opt/btdeck/build-info.json 与二进制一致）
    cp "${STAGING_DIR}/build-info.json" "${STAGING_DIR}/source-manifest.json" "${STAGING_DIR}/frontend-asset-manifest.json" "${PKG_STAGING}${INSTALL_DIR}/"

    # 复制 systemd service 文件
    cp "${DEPLOY_DIR}/btdeck.service" "${PKG_STAGING}/etc/systemd/system/"

    # 创建 post-install 脚本
    cat > "${PKG_STAGING}/postinstall.sh" <<'POSTINSTALL'
#!/bin/bash
# 创建 btdeck 用户
if ! id -u btdeck &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false btdeck
fi
# 预创建 systemd ReadWritePaths 声明的目录
# (ProtectSystem=strict 下应用需这些目录可写，否则首次启动写入失败)
mkdir -p /opt/btdeck/config /opt/btdeck/data /opt/btdeck/logs /opt/btdeck/backup /opt/btdeck/torrents
if [ ! -f /opt/btdeck/config/btdeck.env ]; then
    if command -v openssl >/dev/null 2>&1; then
        SECRET_KEY="$(openssl rand -hex 32)"
    else
        SECRET_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
    fi
cat > /opt/btdeck/config/btdeck.env <<EOF
SECRET_KEY=${SECRET_KEY}
# pydantic-settings 对 List[str] 环境变量强制 JSON 解析（逗号分隔会 SettingsError 启动崩溃），
# 必须用 JSON 数组格式（与 desktop_main.py 一致）
ALLOWED_HOSTS=["http://127.0.0.1:5001","http://localhost:5001"]
EOF
    chmod 600 /opt/btdeck/config/btdeck.env
fi
# 设置权限
chown -R btdeck:btdeck /opt/btdeck
# 启用并启动服务
if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable btdeck
    systemctl start btdeck
    echo "BtDeck service started. Visit: http://localhost:5001"
else
    echo "BtDeck installed, but systemd is not active. Start manually with: systemctl start btdeck"
    echo "After start, visit: http://localhost:5001"
fi
POSTINSTALL
    chmod +x "${PKG_STAGING}/postinstall.sh"

    # 创建 pre-remove 脚本
    cat > "${PKG_STAGING}/preremove.sh" <<'PREREMOVE'
#!/bin/bash
systemctl stop btdeck || true
systemctl disable btdeck || true
PREREMOVE
    chmod +x "${PKG_STAGING}/preremove.sh"

    # 构建 .deb
    fpm -s dir --force \
        -t deb \
        -n btdeck \
        -v "${VERSION}" \
        -a "${ARCH}" \
        --description "BtDeck - BitTorrent Management Platform" \
        --url "https://github.com/strainhzj/BtDeck" \
        --license "GPL-3.0" \
        --after-install "${PKG_STAGING}/postinstall.sh" \
        --before-remove "${PKG_STAGING}/preremove.sh" \
        -C "${PKG_STAGING}" \
        --prefix / \
        -p "${DIST_DIR}/BtDeck-v${VERSION}-linux-${ARCH}.deb" \
        etc \
        opt

    # 构建 .rpm
    fpm -s dir --force \
        -t rpm \
        -n btdeck \
        -v "${VERSION}" \
        -a "${ARCH}" \
        --description "BtDeck - BitTorrent Management Platform" \
        --url "https://github.com/strainhzj/BtDeck" \
        --license "GPL-3.0" \
        --after-install "${PKG_STAGING}/postinstall.sh" \
        --before-remove "${PKG_STAGING}/preremove.sh" \
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
