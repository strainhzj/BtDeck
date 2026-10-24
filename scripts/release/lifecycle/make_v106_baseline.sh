#!/bin/bash
# v1.0.6 升级基线重建（v1.0.7 发布门禁 W3 / 沿 make_v105_baseline.sh 先例）
# 在 w2-linux-builder 容器内执行（/src = 仓库挂载，需 git 与 fpm）。
# 产出 /src/.release-build-v1.0.6/assets/BtDeck-v1.0.6-linux-amd64.{deb,rpm}
#
# 语义：reconstructed=true —— 从 tag v1.0.6（59c1c66）重建，只证明升级路径，
# 不冒充正式历史制品（本地如有正式 assets，外部编排会优先使用并跳过本脚本）。
# 与 v1.0.5 基线的差异：v1.0.6 tag 自带完整 release 工具链（build-linux.sh
# --release 会执行六处版本一致性校验并生成真实 build-info/source-manifest），
# 因此无需占位身份，直接跑官方构建脚本产出带真实身份的基线制品。
set -euo pipefail

SRC="/src"
# 容器内 git 需声明挂载目录安全（Runner uid 与容器 root 不同）
git config --global --add safe.directory "${SRC}" || true
OUT="${SRC}/.release-build-v1.0.6/assets"
V106_SHA="$(git -C "${SRC}" rev-parse v1.0.6^{commit})" || { echo "[FATAL] tag v1.0.6 不存在"; exit 2; }

WORK="$(mktemp -d)"
git -C "${SRC}" archive --format=tar v1.0.6 | tar -xf - -C "${WORK}"
cd "${WORK}"

echo "[1/3] v1.0.6 前端构建（tag 自含流程，Node 22 兼容性已被 w0-node-matrix 探针实证）..."
(cd frontend && npm ci --legacy-peer-deps >/dev/null 2>&1 && npm run build >/dev/null 2>&1) \
    || { echo "[FATAL] v1.0.6 前端构建失败"; exit 1; }

echo "[2/3] v1.0.6 官方打包（build-linux.sh --release：版本校验 + 真实 build-info + PyInstaller + fpm）..."
bash deploy/build-linux.sh --release

echo "[3/3] 收集基线制品..."
mkdir -p "${OUT}"
cp dist/BtDeck-v1.0.6-linux-amd64.deb dist/BtDeck-v1.0.6-linux-amd64.rpm "${OUT}/"

echo "[OK] v1.0.6 基线产出（reconstructed from ${V106_SHA:0:12}）："
ls -la "${OUT}"
