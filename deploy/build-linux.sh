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
PACKAGE_REQUIREMENTS="${DEPLOY_DIR}/requirements-linux-package.txt"
PACKAGE_VENV="${PROJECT_DIR}/.venv-packaging-linux"
PACKAGE_PYTHON="${PACKAGE_VENV}/bin/python"
PACKAGE_PYINSTALLER="${PACKAGE_VENV}/bin/pyinstaller"
PACKAGE_PYTHON_VERSION="${BTDECK_PACKAGE_PYTHON_VERSION:-3.11}"

VERSION="1.0.5"
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

check_tool npm "https://nodejs.org/"
check_tool node "https://nodejs.org/"

if [ ! -f "$PACKAGE_REQUIREMENTS" ]; then
    echo -e "${RED}[ERROR] Packaging requirements not found: ${PACKAGE_REQUIREMENTS}${NC}"
    exit 1
fi

if [ ! -x "$PACKAGE_PYTHON" ]; then
    echo "[SETUP] Creating packaging venv: ${PACKAGE_VENV}"
    if command -v uv &>/dev/null; then
        UV_LINK_MODE="${UV_LINK_MODE:-copy}" uv venv --seed --python "$PACKAGE_PYTHON_VERSION" "$PACKAGE_VENV"
    elif command -v python3 &>/dev/null; then
        python3 -m venv "$PACKAGE_VENV" || {
            echo -e "${RED}[ERROR] Failed to create venv with python3.${NC}"
            echo "        Install python3-venv/python3-pip, or install uv and retry."
            exit 1
        }
    else
        echo -e "${RED}[ERROR] python3 not found. Install Python 3.11+ or uv.${NC}"
        exit 1
    fi
fi

echo "[SETUP] Installing packaging dependencies..."
"$PACKAGE_PYTHON" -m pip install --upgrade pip setuptools wheel
"$PACKAGE_PYTHON" -m pip install --prefer-binary -r "$PACKAGE_REQUIREMENTS"

echo -e "${GREEN}[OK] packaging python: ${PACKAGE_PYTHON}${NC}"
"$PACKAGE_PYTHON" --version
echo -e "${GREEN}[OK] packaging pyinstaller: ${PACKAGE_PYINSTALLER}${NC}"

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
"$PACKAGE_PYINSTALLER" --clean --noconfirm "${DEPLOY_DIR}/btdeck.spec"
echo -e "${GREEN}[OK] Backend packaged${NC}"

echo "[VERIFY] Checking package contents..."
"$PACKAGE_PYTHON" "${DEPLOY_DIR}/verify-package.py" --project-root "$PROJECT_DIR" --exe "${DIST_DIR}/btdeck"
echo -e "${GREEN}[OK] Package verification passed${NC}"

echo "[ANALYZE] Package size summary..."
"$PACKAGE_PYTHON" "${DEPLOY_DIR}/analyze-package-size.py" --exe "${DIST_DIR}/btdeck" --top 15 || true

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
    echo "[3/3] Skipping package build (fpm not found)"
    echo "       Executable ready at dist/btdeck"
fi

echo ""
echo "============================================"
echo "  Build complete!"
echo "============================================"
