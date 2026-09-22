#!/bin/bash

# ============================================
# BtDeck Windows 构建脚本（deploy/build-windows.bat 的 Linux 移植版）
#
# PyInstaller 无法跨平台编译，Windows EXE 必须由 Windows Python 产出。本脚本用
# wine 容器（btdeck-windows-builder，wine + 官方 Windows Python 3.11 + 预下载
# Windows 轮子库）在 Linux 上完成全部 Windows 制品构建；安装器（Inno Setup）
# 经 deploy/iscc 包装脚本在 btdeck-iscc 容器内编译。步骤、参数与 .bat 一一对应。
#
# 用法:
#   deploy/build-windows.sh [--release]
#
# 模式（与 .bat 一致，release-artifact-equivalence-gate W2）:
#   默认（dev）: 自建前端、--allow-dirty 生成身份、安装器缺失仅告警跳过
#   --release  : 必须消费 scripts/release/build_frontend.py 的唯一前端构建
#               （dist 与 manifest 哈希一致）、工作区必须干净、
#               安装器缺失或失败即非零退出（fail-closed）
#
# 环境变量覆盖:
#   BTDECK_WINDOWS_BUILDER_IMAGE  构建容器镜像名（默认 btdeck-windows-builder:latest）
#   BTDECK_ISCC_IMAGE             Inno Setup 容器镜像名（默认 btdeck-iscc:latest）
#   BTDECK_USE_SYSTEM_PYTHON=1    跳过 venv，直接使用容器内全局 Python（对应 .bat 同名开关）
#   BTDECK_SKIP_INSTALLER=1       跳过安装器构建（dev 排障用）
#
# 执行位置说明（与 .bat 的差异仅在"在哪里跑"，步骤与判定不变）:
#   venv/pip/PyInstaller  -> btdeck-windows-builder 容器（wine，唯一能产 Windows EXE 的环节）
#   版本检查/前端消费/身份生成/制品验证 -> 宿主 Python（平台无关脚本，避免 wine 噪音）
#   Inno Setup            -> btdeck-iscc 容器（经 deploy/iscc 包装脚本）
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
DEPLOY_DIR="${PROJECT_DIR}/deploy"
DIST_DIR="${PROJECT_DIR}/dist"
NSSM_PATH="${DEPLOY_DIR}/nssm.exe"
PACKAGE_REQUIREMENTS="${DEPLOY_DIR}/requirements-windows-package.txt"
PACKAGE_VENV="${PROJECT_DIR}/.venv-packaging"
FRONTEND_MANIFEST="${PROJECT_DIR}/release/build/frontend/frontend-asset-manifest.json"
STAGING_DIR="${PROJECT_DIR}/release/build/windows-exe"
BUILDER_IMAGE="${BTDECK_WINDOWS_BUILDER_IMAGE:-btdeck-windows-builder:latest}"
ISCC_IMAGE="${BTDECK_ISCC_IMAGE:-btdeck-iscc:latest}"

RELEASE_MODE=0
for arg in "$@"; do
    case "$arg" in
        --release) RELEASE_MODE=1 ;;
        *)
            echo "[ERROR] Unknown argument: $arg (supported: --release)"
            exit 2
            ;;
    esac
done

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; BLUE=$'\033[0;34m'; NC=$'\033[0m'
info()  { echo "${BLUE}[INFO] $*${NC}"; }
ok()    { echo "${GREEN}[OK] $*${NC}"; }
warn()  { echo "${YELLOW}[WARN] $*${NC}"; }
err()   { echo "${RED}[ERROR] $*${NC}" >&2; }
fail()  { err "$*"; exit 1; }

echo "============================================"
echo "  BtDeck Windows Build (mode: $([ "$RELEASE_MODE" = "1" && echo RELEASE || echo dev))"
echo "============================================"
echo

# ---------- 前置检查 ----------
if [ ! -f "$NSSM_PATH" ]; then
    fail "NSSM not found. Expected: $NSSM_PATH (download win64 from https://nssm.cc/download)"
fi
ok "NSSM found: $NSSM_PATH"

command -v docker >/dev/null 2>&1 || fail "docker not found. Install Docker (the Windows toolchain runs in wine containers)."
ok "docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)"

command -v python3 >/dev/null 2>&1 || fail "python3 not found."
PYTHON_CMD="$(command -v python3)"
ok "python3: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"

if [ "$RELEASE_MODE" != "1" ]; then
    command -v npm >/dev/null 2>&1 || fail "npm not found (dev mode builds the frontend). Install Node.js or use --release."
    ok "npm: $(command -v npm)"
fi

ensure_image() {
    local image="$1" dockerfile="$2" context="$3"
    if docker image inspect "$image" >/dev/null 2>&1; then
        ok "image exists: $image"
        return 0
    fi
    info "building image: $image (first time only)"
    docker build -t "$image" -f "$dockerfile" "$context" >/dev/null \
        || fail "failed to build $image from $dockerfile"
    ok "image built: $image"
}

ensure_image "$BUILDER_IMAGE" \
    "${DEPLOY_DIR}/docker/windows-builder/Dockerfile" "$PROJECT_DIR"

# 在 wine 容器内执行一段脚本（仓库挂载到 /work；pip 走阿里云源 + 自带 certifi）
run_in_builder() {
    docker run --rm \
        -v "$PROJECT_DIR":/work -w /work \
        -e PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
        "$BUILDER_IMAGE" \
        bash -c "$1"
}

# ---------- 打包 venv 与依赖（容器内；对应 .bat venv/pip 两段式） ----------
if [ "${BTDECK_USE_SYSTEM_PYTHON:-0}" = "1" ]; then
    warn "BTDECK_USE_SYSTEM_PYTHON=1: using the container's global Python (no venv)"
    ok "packaging python: container global (winpython)"
    ok "packaging pyinstaller: container global"
else
    [ -f "$PACKAGE_REQUIREMENTS" ] || fail "Packaging requirements not found: $PACKAGE_REQUIREMENTS"
    if [ ! -f "${PACKAGE_VENV}/Scripts/python.exe" ]; then
        info "creating packaging venv (in container): ${PACKAGE_VENV}"
        run_in_builder "winpython -m venv /work/.venv-packaging" \
            || fail "failed to create packaging venv"
    fi
    info "installing packaging dependencies (two-step: hash-verified lock + windows extras, offline wheels)"
    run_in_builder "wine /work/.venv-packaging/Scripts/python.exe -m pip install --upgrade pip setuptools wheel \
        && wine /work/.venv-packaging/Scripts/python.exe -m pip install -r /work/backend/requirements-lock.txt \
        && wine /work/.venv-packaging/Scripts/python.exe -m pip install -r /work/deploy/requirements-windows-package.txt" \
        || fail "failed to install packaging dependencies (offline wheel set incomplete?)"
    ok "packaging python: ${PACKAGE_VENV}/Scripts/python.exe (wine)"
    ok "packaging pyinstaller: ${PACKAGE_VENV}/Scripts/python.exe -m PyInstaller (wine)"
fi

# ---------- Inno Setup 可用性（release 强制） ----------
BUILD_INSTALLER=1
if ! docker image inspect "$ISCC_IMAGE" >/dev/null 2>&1; then
    ensure_image "$ISCC_IMAGE" "${DEPLOY_DIR}/docker/iscc/Dockerfile" "${DEPLOY_DIR}/docker/iscc" || true
fi
if ! docker image inspect "$ISCC_IMAGE" >/dev/null 2>&1; then
    if [ "$RELEASE_MODE" = "1" ]; then
        fail "release mode requires the Inno Setup image $ISCC_IMAGE (fail-closed). Build: docker build -t $ISCC_IMAGE -f ${DEPLOY_DIR}/docker/iscc/Dockerfile ${DEPLOY_DIR}/docker/iscc"
    fi
    warn "Inno Setup image $ISCC_IMAGE unavailable. Continuing without installer build..."
    BUILD_INSTALLER=0
else
    ok "Inno Setup image: $ISCC_IMAGE"
fi
if [ "${BTDECK_SKIP_INSTALLER:-0}" = "1" ]; then
    warn "BTDECK_SKIP_INSTALLER=1: installer build skipped"
    BUILD_INSTALLER=0
fi

# ---------- Step 1: 前端（dev 自建；release 消费唯一构建） ----------
if [ "$RELEASE_MODE" = "1" ]; then
    info "[1/4] Consuming prebuilt frontend - single build..."
    [ -f "$FRONTEND_MANIFEST" ] || fail "release mode requires: python3 scripts/release/build_frontend.py (unique frontend build + manifest)"
    "$PYTHON_CMD" "${PROJECT_DIR}/scripts/release/check_prebuilt_frontend.py" "$FRONTEND_MANIFEST" "${FRONTEND_DIR}/dist" \
        || fail "frontend dist does not match the single-build manifest; rebuilding inside artifact builds is forbidden"
    ok "frontend dist matches single-build manifest"
else
    info "[1/4] Building frontend (dev mode)..."
    ( cd "$FRONTEND_DIR" && npm ci --legacy-peer-deps && npm run build ) \
        || fail "frontend build failed"
    ok "Frontend built"
fi

# ---------- Step 2: 生成发布身份（build-info + source/frontend manifest；G1/G5） ----------
info "[2/4] Generating release identity..."
GEN_ARGS=(--artifact-kind windows-exe --output-dir "$STAGING_DIR")
if [ "$RELEASE_MODE" != "1" ]; then
    GEN_ARGS+=(--allow-dirty)
fi
"$PYTHON_CMD" "${PROJECT_DIR}/scripts/release/generate_build_info.py" "${GEN_ARGS[@]}" \
    || fail "release identity generation failed (release mode requires a clean worktree and six-way version consistency)"

# ---------- Step 3: PyInstaller 打包（容器内 wine） ----------
info "[3/4] Building backend with PyInstaller (in wine container)..."
if [ "${BTDECK_USE_SYSTEM_PYTHON:-0}" = "1" ]; then
    run_in_builder "winpython -m PyInstaller --clean --noconfirm /work/deploy/btdeck-windows.spec" \
        || fail "PyInstaller build failed"
else
    run_in_builder "wine /work/.venv-packaging/Scripts/python.exe -m PyInstaller --clean --noconfirm /work/deploy/btdeck-windows.spec" \
        || fail "PyInstaller build failed"
fi
[ -f "${DIST_DIR}/btdeck.exe" ] || fail "PyInstaller did not produce dist/btdeck.exe"
ok "Backend packaged: ${DIST_DIR}/btdeck.exe"

# ---------- Step 4: 内容级验证（G5）+ 体积分析（容器内运行：需要 PyInstaller 归档读取库） ----------
info "[VERIFY] Checking package contents..."
run_in_builder "wine /work/.venv-packaging/Scripts/python.exe /work/deploy/verify-package.py --project-root /work --artifact /work/dist/btdeck.exe" \
    || fail "Package verification failed"
ok "Package verification passed"

info "[ANALYZE] Package size summary..."
run_in_builder "wine /work/.venv-packaging/Scripts/python.exe /work/deploy/analyze-package-size.py --exe /work/dist/btdeck.exe --top 15" \
    || warn "Package size analysis failed"

# ---------- Step 5: Inno Setup 安装器（btdeck-iscc 容器，经包装脚本） ----------
if [ "$BUILD_INSTALLER" = "1" ]; then
    info "[4/4] Building Windows installer (Inno Setup in container)..."
    mkdir -p "$DIST_DIR"
    # 注意：必须传相对路径（相对仓库根=/work 容器 cwd）——绝对 POSIX 路径
    # 以 / 开头会被 ISCC 解析为选项前缀（如 /s）导致 Invalid option
    BTDECK_ISCC_IMAGE="$ISCC_IMAGE" "${DEPLOY_DIR}/iscc" deploy/btdeck.iss \
        || {
            if [ "$RELEASE_MODE" = "1" ]; then
                fail "Inno Setup build failed in release mode - failing the build"
            fi
            warn "Inno Setup build failed, but executable is ready at dist/btdeck.exe"
        }
    ok "Installer built at ${DIST_DIR}/"
else
    info "[4/4] Skipping installer build"
    info "      Executable ready at dist/btdeck.exe"
fi

echo
echo "============================================"
echo "  Build complete!"
echo "============================================"
echo "  dist/btdeck.exe$([ "$BUILD_INSTALLER" = "1" ] && echo " + BtDeck-v*-windows-x64-setup.exe")"
exit 0
