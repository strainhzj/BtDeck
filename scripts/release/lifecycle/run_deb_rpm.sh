#!/bin/bash
# DEB/RPM 生命周期本地/CI 编排器（release-artifact-equivalence-gate W3 / G6）
# 在有 docker 的宿主上执行；构建 systemd 测试镜像并在其中运行 deb.sh/rpm.sh 四个场景。
#
# 用法：run_deb_rpm.sh [--project-root DIR] [--evidence-dir DIR] [--skip deb|rpm]
# 前置：
#   <root>/dist/BtDeck-v1.0.6-linux-amd64.{deb,rpm}          新制品（build-linux.sh --release）
#   <root>/.release-build-v1.0.5/assets/BtDeck-v1.0.5-linux-amd64.{deb,rpm}  升级基线（本地正式制品）
# fail-closed：任一场景失败整体非零退出。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ROOT="$DEFAULT_ROOT"
EVIDENCE_DIR=""
SKIP=""

while [ $# -gt 0 ]; do
    case "$1" in
        --project-root) ROOT="$(cd "$2" && pwd)"; shift 2 ;;
        --evidence-dir) EVIDENCE_DIR="$2"; shift 2 ;;
        --skip) SKIP="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 2 ;;
    esac
done
EVIDENCE_DIR="${EVIDENCE_DIR:-${ROOT}/release/evidence/w3}"
mkdir -p "$EVIDENCE_DIR"

NEW_DEB="${ROOT}/dist/BtDeck-v1.0.6-linux-amd64.deb"
NEW_RPM="${ROOT}/dist/BtDeck-v1.0.6-linux-amd64.rpm"
OLD_DEB="${ROOT}/.release-build-v1.0.5/assets/BtDeck-v1.0.5-linux-amd64.deb"
OLD_RPM="${ROOT}/.release-build-v1.0.5/assets/BtDeck-v1.0.5-linux-amd64.rpm"

fail() { echo "[FATAL] $1" >&2; exit 2; }

command -v docker >/dev/null 2>&1 || fail "docker 不可用"

build_one() {  # build_one <tag>（heredoc 从 stdin）
    local tag="$1"
    docker build -t "$tag" - || fail "systemd 测试镜像构建失败：$tag"
}

build_sysd_images() {
    echo "[SETUP] 构建 systemd 测试镜像（官方基 + 预装 curl/sqlite/iproute/python3）..."
    # 镜像源加速：默认国内源；CI/网络良好环境可 BTDECK_SKIP_MIRROR=1 走官方源
    if [ "${BTDECK_SKIP_MIRROR:-0}" != "1" ]; then
        build_one w3-debian-sysd <<'EOF'
FROM debian:12
RUN sed -i "s|security.debian.org/debian-security|mirrors.aliyun.com/debian-security|g; s|deb.debian.org|mirrors.aliyun.com|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends systemd curl sqlite3 iproute2 python3 \
    && ln -sf /lib/systemd/systemd /sbin/init \
    && rm -f /etc/machine-id
CMD ["/sbin/init"]
EOF
        # rocky：整体重写 repo 文件（USTC 布局），规避各家镜像 $contentdir 路径差异
        build_one w3-rocky-sysd <<'EOF'
FROM rockylinux:9
RUN rm -f /etc/yum.repos.d/rocky*.repo \
    && printf '[baseos]\nname=Rocky BaseOS\nbaseurl=https://mirrors.ustc.edu.cn/rocky/$releasever/BaseOS/$basearch/os/\ngpgcheck=0\n[appstream]\nname=Rocky AppStream\nbaseurl=https://mirrors.ustc.edu.cn/rocky/$releasever/AppStream/$basearch/os/\ngpgcheck=0\n' > /etc/yum.repos.d/btdeck.repo \
    && dnf -y install systemd sqlite iproute python3 --allowerasing \
    && rm -f /etc/machine-id \
    && systemctl set-default multi-user.target
CMD ["/sbin/init"]
EOF
    else
        build_one w3-debian-sysd <<'EOF'
FROM debian:12
RUN apt-get update && apt-get install -y --no-install-recommends systemd curl sqlite3 iproute2 python3 \
    && ln -sf /lib/systemd/systemd /sbin/init \
    && rm -f /etc/machine-id
CMD ["/sbin/init"]
EOF
        build_one w3-rocky-sysd <<'EOF'
FROM rockylinux:9
RUN dnf -y install systemd sqlite iproute python3 --allowerasing \
    && rm -f /etc/machine-id \
    && systemctl set-default multi-user.target
CMD ["/sbin/init"]
EOF
    fi
}

run_scenario() {
    # run_scenario <name> <image> <driver> <driver-args...>
    local name="$1" image="$2" driver="$3"; shift 3
    echo ""
    echo "=========================================="
    echo "  生命周期场景: ${name}"
    echo "=========================================="
    docker rm -f "w3-${name}" >/dev/null 2>&1
    docker run -d --name "w3-${name}" --privileged --cgroupns=host \
        -v "${ROOT}:/src:ro" "$image" >/dev/null || fail "无法启动 ${name} 容器"
    sleep 8
    docker exec "w3-${name}" systemctl is-system-running >/dev/null 2>&1 \
        || echo "[WARN] ${name}: systemd degraded（容器常见态，继续）"
    docker exec "w3-${name}" bash "/src/scripts/release/lifecycle/${driver}" "$@"
    local rc=$?
    docker cp "w3-${name}:/tmp/report.json" "${EVIDENCE_DIR}/lifecycle-${name}.json" >/dev/null 2>&1 \
        || cp /dev/null "${EVIDENCE_DIR}/lifecycle-${name}.json"
    docker exec "w3-${name}" journalctl -u btdeck --no-pager > "${EVIDENCE_DIR}/lifecycle-${name}.journal.log" 2>&1 || true
    docker logs "w3-${name}" > "${EVIDENCE_DIR}/lifecycle-${name}.container.log" 2>&1
    docker rm -f "w3-${name}" >/dev/null 2>&1
    if [ $rc -ne 0 ]; then
        echo "[FAIL] 场景 ${name} 失败（exit=${rc}）" >&2
        OVERALL=1
    else
        echo "[PASS] 场景 ${name}"
    fi
}

OVERALL=0
build_sysd_images

if [ "$SKIP" != "deb" ]; then
    [ -f "$NEW_DEB" ] || fail "缺少新 DEB：$NEW_DEB"
    [ -f "$OLD_DEB" ] || fail "缺少 v1.0.5 基线 DEB：$OLD_DEB"
    run_scenario deb-fresh   w3-debian-sysd deb.sh --report /tmp/report.json --scenario fresh   --new-deb "/src${NEW_DEB#$ROOT}"
    run_scenario deb-upgrade w3-debian-sysd deb.sh --report /tmp/report.json --scenario upgrade --new-deb "/src${NEW_DEB#$ROOT}" --old-deb "/src${OLD_DEB#$ROOT}"
fi

if [ "$SKIP" != "rpm" ]; then
    [ -f "$NEW_RPM" ] || fail "缺少新 RPM：$NEW_RPM"
    [ -f "$OLD_RPM" ] || fail "缺少 v1.0.5 基线 RPM：$OLD_RPM"
    run_scenario rpm-fresh   w3-rocky-sysd rpm.sh --report /tmp/report.json --scenario fresh   --new-rpm "/src${NEW_RPM#$ROOT}"
    run_scenario rpm-upgrade w3-rocky-sysd rpm.sh --report /tmp/report.json --scenario upgrade --new-rpm "/src${NEW_RPM#$ROOT}" --old-rpm "/src${OLD_RPM#$ROOT}"
fi

echo ""
if [ $OVERALL -eq 0 ]; then
    echo "[PASS] DEB/RPM 生命周期全部场景通过；报告：${EVIDENCE_DIR}"
else
    echo "[FAIL] 存在失败场景；报告：${EVIDENCE_DIR}" >&2
fi
exit $OVERALL
