#!/bin/bash

# ============================================
# BtDeck Linux 构建脚本
# 1. 构建前端
# 2. PyInstaller 打包后端+前端
# 3. fpm 制作 .deb/.rpm 安装包
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
BACKEND_DIR="${PROJECT_DIR}/backend"
DEPLOY_DIR="${PROJECT_DIR}/deploy"
DIST_DIR="${PROJECT_DIR}/dist"

VERSION="1.0.9"
ARCH="amd64"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo "============================================"
echo "  BtDeck Linux Build"
echo "============================================"
echo ""

# 检查工具
check_tool() {
    if ! command -v "$1" &>/dev/null; then
        echo -e "${RED}[ERROR] $1 not found. Install: $2${NC}"
        exit 1
    fi
}

check_tool pyinstaller "pip install pyinstaller"
check_tool npm "https://nodejs.org/"

# 检查 fpm（可选）
if command -v fpm &>/dev/null; then
    BUILD_PACKAGE=1
else
    echo -e "${YELLOW}[WARN] fpm not found. Package build skipped.${NC}"
    echo "       Install: gem install fpm"
    BUILD_PACKAGE=0
fi

# Step 1: 构建前端
echo "[1/3] Building frontend..."
cd "$FRONTEND_DIR"
npm ci --legacy-peer-deps
npm run build
echo -e "${GREEN}[OK] Frontend built${NC}"

# Step 2: PyInstaller 打包
echo "[2/3] Building backend with PyInstaller..."
cd "$PROJECT_DIR"
pyinstaller --clean --noconfirm "${DEPLOY_DIR}/btdeck.spec"
echo -e "${GREEN}[OK] Backend packaged${NC}"

# Step 3: fpm 制作安装包
if [ "$BUILD_PACKAGE" = "1" ]; then
    echo "[3/3] Building Linux packages..."

    mkdir -p "$DIST_DIR"

    INSTALL_DIR="/opt/btdeck"

    # 准备 fpm 输入目录
    PKG_STAGING=$(mktemp -d)
    mkdir -p "${PKG_STAGING}${INSTALL_DIR}"
    mkdir -p "${PKG_STAGING}/etc/systemd/system"

    # 复制可执行文件
    cp "${PROJECT_DIR}/dist/btdeck" "${PKG_STAGING}${INSTALL_DIR}/"
    chmod +x "${PKG_STAGING}${INSTALL_DIR}/btdeck"

    # 复制 systemd service 文件
    cp "${DEPLOY_DIR}/btdeck.service" "${PKG_STAGING}/etc/systemd/system/"

    # 创建 post-install 脚本
    cat > "${PKG_STAGING}/postinstall.sh" <<'POSTINSTALL'
#!/bin/bash
# 创建 btdeck 用户
if ! id -u btdeck &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false btdeck
fi
# 设置权限
chown -R btdeck:btdeck /opt/btdeck
# 启用并启动服务
systemctl daemon-reload
systemctl enable btdeck
systemctl start btdeck
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
    fpm -s dir \
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
        etc \
        opt \
        -p "${DIST_DIR}/BtDeck-v${VERSION}-linux-${ARCH}.deb"

    # 构建 .rpm
    fpm -s dir \
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
        etc \
        opt \
        -p "${DIST_DIR}/BtDeck-v${VERSION}-linux-${ARCH}.rpm"

    # 清理临时目录
    rm -rf "${PKG_STAGING}"

    echo -e "${GREEN}[OK] Packages built at ${DIST_DIR}/${NC}"
else
    echo "[3/3] Skipping package build (fpm not found)"
    echo "       Executable ready at dist/btdeck"
fi

echo ""
echo "============================================"
echo "  Build complete!"
echo "============================================"
