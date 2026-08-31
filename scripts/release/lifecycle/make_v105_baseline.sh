#!/bin/bash
# v1.0.5 升级基线重建（release-artifact-equivalence-gate W3 / 计划 §9）
# 在 w2-linux-builder 容器内执行（/src = 仓库挂载，需 git 与 fpm）。
# 产出 /src/.release-build-v1.0.5/assets/BtDeck-v1.0.5-linux-amd64.{deb,rpm}
#
# 语义：reconstructed=true —— 从 tag v1.0.5（29c6f6f）重建，只证明升级路径，
# 不冒充正式历史制品（本地如有正式 assets，外部编排会优先使用并跳过本脚本）。
set -euo pipefail

SRC="/src"
# 容器内 git 需声明挂载目录安全（Runner uid 与容器 root 不同）
git config --global --add safe.directory "${SRC}" || true
OUT="${SRC}/.release-build-v1.0.5/assets"
V105_SHA="$(git -C "${SRC}" rev-parse v1.0.5^{commit})" || { echo "[FATAL] tag v1.0.5 不存在"; exit 2; }

WORK="$(mktemp -d)"
git -C "${SRC}" archive --format=tar v1.0.5 | tar -xf - -C "${WORK}"
cd "${WORK}"

echo "[1/4] v1.0.5 前端构建（tag 时代自含流程）..."
(cd frontend && npm ci --legacy-peer-deps >/dev/null 2>&1 && npm run build >/dev/null 2>&1) \
    || { echo "[FATAL] v1.0.5 前端构建失败"; exit 1; }

echo "[2/4] v1.0.5 发布身份占位（tag 无 release 工具链）..."
python3 - <<PY
import json, pathlib
info = {
    "schema_version": 1, "product_version": "1.0.5",
    "git_sha": "${V105_SHA}", "git_tag": "v1.0.5",
    "source_date_epoch": 0, "build_id": None, "artifact_kind": "linux-binary",
    "target_os": "linux", "target_arch": "amd64", "python_version": "3.11",
    "node_version": None, "alembic_head": "975dad435c03",
    "frontend_manifest_sha256": "0" * 64, "source_manifest_sha256": "0" * 64,
    "dependency_manifest_sha256": None, "dirty": False,
    "reconstructed": True,
}
out = pathlib.Path("release/build/linux-binary")
out.mkdir(parents=True, exist_ok=True)
(out / "build-info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
(out / "source-manifest.json").write_text("{}\n", encoding="utf-8")
(out / "frontend-asset-manifest.json").write_text("{}\n", encoding="utf-8")
PY

echo "[3/4] v1.0.5 PyInstaller 打包..."
python3 -m venv /tmp/v105-venv >/dev/null
/tmp/v105-venv/bin/pip install -q --prefer-binary -r deploy/requirements-linux-package.txt
# tag 时代的 spec 没有 staging 要求，但 datas 需要 release/ 三件套——用 spec 缺省查找位放入
mkdir -p release
cp release/build/linux-binary/*.json release/ 2>/dev/null || true
BTDECK_RELEASE_STAGING="${WORK}/release" /tmp/v105-venv/bin/pyinstaller --clean --noconfirm \
    --distpath dist --workpath /tmp/v105-pyi deploy/btdeck.spec

echo "[4/4] fpm 打包 v1.0.5 基线（结构对齐 v1.0.6：同 service+scriptlets）..."
mkdir -p "${OUT}"
STAGING="$(mktemp -d)"
mkdir -p "${STAGING}/opt/btdeck" "${STAGING}/etc/systemd/system"
cp dist/btdeck "${STAGING}/opt/btdeck/"
chmod +x "${STAGING}/opt/btdeck/btdeck"
cp deploy/btdeck.service "${STAGING}/etc/systemd/system/"
cp release/build/linux-binary/*.json "${STAGING}/opt/btdeck/"
# v1.0.5 tag 无 package-scripts；用仓库当前的（升级语义修正属于 v1.0.6 侧验证点）
if [ -d "${SRC}/deploy/package-scripts" ]; then
    cp "${SRC}/deploy/package-scripts/"*.sh "${STAGING}/"
    POSTINST="--after-install ${STAGING}/postinst.sh"
    PRERM="--before-remove ${STAGING}/prerm.sh"
    POSTRM="--after-remove ${STAGING}/postrm.sh"
else
    POSTINST=""; PRERM=""; POSTRM=""
fi
fpm -s dir --force -t deb -n btdeck -v 1.0.5 -a amd64 \
    --description "BtDeck - BitTorrent Management Platform (reconstructed baseline)" \
    $POSTINST $PRERM $POSTRM -C "${STAGING}" --prefix / \
    -p "${OUT}/BtDeck-v1.0.5-linux-amd64.deb" etc opt
fpm -s dir --force -t rpm -n btdeck -v 1.0.5 -a amd64 \
    --description "BtDeck - BitTorrent Management Platform (reconstructed baseline)" \
    $POSTINST $PRERM -C "${STAGING}" --prefix / \
    -p "${OUT}/BtDeck-v1.0.5-linux-amd64.rpm" etc opt

echo "[OK] v1.0.5 基线产出："
ls -la "${OUT}"
