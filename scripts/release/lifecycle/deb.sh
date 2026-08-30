#!/bin/bash
# BtDeck DEB 生命周期驱动（release-artifact-equivalence-gate task .6 / G6）
# 在 Debian 12 systemd 容器内执行（由 run_deb_rpm.sh 或 CI 编排启动）。
#
# 场景：
#   fresh   —— 首装 v1.0.6 → 重装同版本 → 重启×2 → remove（数据保留）→ purge（数据清除）
#   upgrade —— 首装 v1.0.5（正式本地制品）→ 植入 secret/marker → 升级 v1.0.6 →
#              R11 断言（enabled+active）→ secret/marker/alembic 断言 → remove
# 任一断言失败 → 报告 FAIL 且非零退出（fail-closed）。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "${SCRIPT_DIR}/lib.sh"

SCENARIO=""
NEW_DEB=""
OLD_DEB=""
REPORT="/tmp/lifecycle-deb.json"
DISTRO="debian:12"

while [ $# -gt 0 ]; do
    case "$1" in
        --scenario) SCENARIO="$2"; shift 2 ;;
        --new-deb) NEW_DEB="$2"; shift 2 ;;
        --old-deb) OLD_DEB="$2"; shift 2 ;;
        --report) REPORT="$2"; shift 2 ;;
        *) die "未知参数: $1" ;;
    esac
done

[ -n "$SCENARIO" ] || die "--scenario 必填（fresh|upgrade）"
[ -n "$NEW_DEB" ] || die "--new-deb 必填"
[ -f "$NEW_DEB" ] || die "新包不存在: $NEW_DEB"

wait_healthy() {  # wait_healthy <version-substr>
    wait_http "http://127.0.0.1:5001/health/live" "\"version\": \"$1\"" 180
}

install_deb() { dpkg -i "$1" >/tmp/dpkg-install.log 2>&1; }

remove_deb() { dpkg -r btdeck >/tmp/dpkg-remove.log 2>&1; }
purge_deb() { dpkg -P btdeck >/tmp/dpkg-purge.log 2>&1; }

if [ "$SCENARIO" = "fresh" ]; then
    # ---- 首装 ----
    if install_deb "$NEW_DEB" \
        && wait_healthy "1.0.6" \
        && assert_eq "$(service_active && echo yes || echo no)" yes "首装后服务 active" \
        && assert_eq "$(service_enabled && echo yes || echo no)" yes "首装后服务 enabled" \
        && assert_eq "$(service_unit_count)" 1 "服务单元唯一" \
        && single_port_listener \
        && assert_eq "$(build_info_field /opt/btdeck/build-info.json "['artifact_kind']")" linux-deb "包内 build-info kind" \
        && assert_eq "$(build_info_field /opt/btdeck/build-info.json "['product_version']")" 1.0.6 "包内 build-info 版本"; then
        phase "fresh_install" PASS
    else
        phase "fresh_install" FAIL "首装断言未全部通过（见 stderr）"
    fi

    SECRET_BEFORE="$(secret_fingerprint)"
    MARKER=/opt/btdeck/data/w3-marker.txt
    echo "w3-fresh $(date -u +%s)" > "$MARKER" 2>/dev/null || true
    HEAD_BEFORE="$(alembic_head)"

    # ---- 同版本重装 ----
    if install_deb "$NEW_DEB" \
        && wait_healthy "1.0.6" \
        && assert_eq "$(secret_fingerprint)" "$SECRET_BEFORE" "重装后 SECRET_KEY 未重置" \
        && assert_eq "$(service_unit_count)" 1 "重装后服务单元唯一" \
        && assert_eq "$(alembic_head)" "$HEAD_BEFORE" "重装未产生新迁移" \
        && [ -f "$MARKER" ]; then
        phase "reinstall_same_version" PASS
    else
        phase "reinstall_same_version" FAIL "重装断言未全部通过"
    fi

    # ---- 重启×2 ----
    ok=yes
    systemctl restart btdeck || ok=no
    systemctl restart btdeck || ok=no
    if [ "$ok" = yes ] && service_active && single_port_listener \
        && assert_eq "$(systemctl show -p MainPID --value btdeck | grep -c .)" 1 "单主进程"; then
        phase "restart_twice" PASS
    else
        phase "restart_twice" FAIL "重启后状态异常"
    fi

    # ---- remove：程序移除、数据保留 ----
    remove_deb
    sleep 2
    if [ ! -x /opt/btdeck/btdeck ] && ! systemctl list-unit-files 2>/dev/null | grep -q '^btdeck[[:space:]].*enabled' \
        && [ -f "$MARKER" ] && [ -f /opt/btdeck/config/btdeck.env ]; then
        phase "remove_keeps_data" PASS
    else
        phase "remove_keeps_data" FAIL "remove 后程序/服务残留或数据丢失"
    fi

    # ---- purge：数据清除 ----
    purge_deb
    sleep 1
    if [ ! -e /opt/btdeck/config/btdeck.env ] && [ ! -e "$MARKER" ] && [ ! -d /opt/btdeck/data ]; then
        phase "purge_removes_data" PASS
    else
        phase "purge_removes_data" FAIL "purge 后数据残留"
    fi

elif [ "$SCENARIO" = "upgrade" ]; then
    [ -n "$OLD_DEB" ] && [ -f "$OLD_DEB" ] || die "upgrade 场景要求 --old-deb（v1.0.5 正式本地制品）"

    # ---- v1.0.5 基线 ----
    # v1.0.5 冻结制品的 postinst 守卫不接受容器 degraded 态，需显式启动（夹具侧适配，仅基线阶段）
    if install_deb "$OLD_DEB"; then
        systemctl start btdeck 2>/dev/null || true
        systemctl enable btdeck 2>/dev/null || true
    fi
    if wait_healthy "1.0.5"; then
        phase "v105_baseline_install" PASS
    else
        phase "v105_baseline_install" FAIL "v1.0.5 基线安装/健康失败"
    fi

    SECRET_BEFORE="$(secret_fingerprint)"
    HEAD_BEFORE="$(alembic_head)"
    MARKER=/opt/btdeck/data/w3-upg-marker.txt
    echo "w3-upgrade $(date -u +%s)" > "$MARKER" 2>/dev/null || true

    # ---- 升级到 v1.0.6（R11 核心：enabled+active）----
    if install_deb "$NEW_DEB" \
        && wait_healthy "1.0.6" \
        && assert_eq "$(service_active && echo yes || echo no)" yes "升级后服务 active（R11）" \
        && assert_eq "$(service_enabled && echo yes || echo no)" yes "升级后服务 enabled（R11）" \
        && assert_eq "$(service_unit_count)" 1 "升级后服务单元唯一" \
        && single_port_listener \
        && assert_eq "$(secret_fingerprint)" "$SECRET_BEFORE" "升级后 SECRET_KEY 保留" \
        && [ -f "$MARKER" ] \
        && assert_eq "$(alembic_head | cut -f1)" 1 "升级后 Alembic 单 head"; then
        phase "v105_to_v106_upgrade" PASS
    else
        phase "v105_to_v106_upgrade" FAIL "升级断言未全部通过（重点核查 prerm 升级分支）"
    fi

    HEAD_AFTER="$(alembic_head | cut -f2)"
    if [ "$HEAD_AFTER" != "$HEAD_BEFORE" ] 2>/dev/null; then
        phase "alembic_head_advanced" PASS "v1.0.5 head: $(echo "$HEAD_BEFORE" | cut -f2) → v1.0.6 head: $HEAD_AFTER"
    else
        phase "alembic_head_advanced" FAIL "升级前后 head 未推进或不可读（before='$HEAD_BEFORE' after='$HEAD_AFTER'）"
    fi

    # ---- remove：升级后卸载仍保留数据 ----
    remove_deb
    sleep 2
    if [ ! -x /opt/btdeck/btdeck ] && [ -f "$MARKER" ] && [ -f /opt/btdeck/config/btdeck.env ]; then
        phase "remove_after_upgrade_keeps_data" PASS
    else
        phase "remove_after_upgrade_keeps_data" FAIL "升级后 remove 数据丢失或程序残留"
    fi
else
    die "未知场景: $SCENARIO"
fi

write_report "$REPORT" "deb-${SCENARIO}" "$DISTRO"
