#!/bin/bash
# BtDeck RPM 生命周期驱动（release-artifact-equivalence-gate task .6 / G6）
# 在 Rocky Linux 9 systemd 容器内执行（由 run_deb_rpm.sh 或 CI 编排启动）。
#
# 场景：
#   fresh   —— 首装 v1.0.6 → 重装同版本（dnf reinstall）→ 重启×2 → rpm -e（数据保留）
#   upgrade —— 首装 v1.0.5 → 植入 secret/marker → 升级 v1.0.6 → R11 断言 → remove
# fail-closed：任一断言失败 → 报告 FAIL 且非零退出。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "${SCRIPT_DIR}/lib.sh"

SCENARIO=""
NEW_RPM=""
OLD_RPM=""
REPORT="/tmp/lifecycle-rpm.json"
DISTRO="rockylinux:9"

while [ $# -gt 0 ]; do
    case "$1" in
        --scenario) SCENARIO="$2"; shift 2 ;;
        --new-rpm) NEW_RPM="$2"; shift 2 ;;
        --old-rpm) OLD_RPM="$2"; shift 2 ;;
        --report) REPORT="$2"; shift 2 ;;
        *) die "未知参数: $1" ;;
    esac
done

[ -n "$SCENARIO" ] || die "--scenario 必填（fresh|upgrade）"
[ -n "$NEW_RPM" ] || die "--new-rpm 必填"
[ -f "$NEW_RPM" ] || die "新包不存在: $NEW_RPM"

wait_healthy() {
    # v1.0.5 冻结制品的健康契约无 version 字段（version/build 是 v1.0.6 W1 引入），
    # 基线就绪只能断言 data.status=alive；v1.0.6 仍按 version 精确断言
    local want="\"version\":\"$1\""
    [ "$1" = "1.0.5" ] && want="\"status\":\"alive\""
    wait_http "http://127.0.0.1:5001/health/live" "$want" 180
}

install_rpm() { dnf -y install "$1" >/tmp/dnf-install.log 2>&1; }
# dnf reinstall 只对 repo 内包生效（本地 rpm 文件安装的包立即报"找不到"，
# CI 实测 0.3s 失败）；rpm -Uvh --force 是本地同版本强制重装的标准形态
reinstall_rpm() { rpm -Uvh --force "$NEW_RPM" >/tmp/rpm-reinstall.log 2>&1; }
remove_rpm() { rpm -e btdeck >/tmp/rpm-remove.log 2>&1; }

if [ "$SCENARIO" = "fresh" ]; then
    if install_rpm "$NEW_RPM" \
        && wait_healthy "1.0.6" \
        && assert_eq "$(service_active && echo yes || echo no)" yes "首装后服务 active" \
        && assert_eq "$(service_enabled && echo yes || echo no)" yes "首装后服务 enabled" \
        && assert_eq "$(service_unit_count)" 1 "服务单元唯一" \
        && single_port_listener \
        && assert_eq "$(build_info_field /opt/btdeck/build-info.json "['artifact_kind']")" linux-rpm "包内 build-info kind"; then
        phase "fresh_install" PASS
    else
        phase "fresh_install" FAIL "首装断言未全部通过"
    fi

    SECRET_BEFORE="$(secret_fingerprint)"
    MARKER=/opt/btdeck/data/w3-marker.txt
    echo "w3-fresh $(date -u +%s)" > "$MARKER" 2>/dev/null || true
    HEAD_BEFORE="$(alembic_head)"

    if reinstall_rpm \
        && wait_healthy "1.0.6" \
        && assert_eq "$(secret_fingerprint)" "$SECRET_BEFORE" "重装后 SECRET_KEY 未重置" \
        && assert_eq "$(alembic_head)" "$HEAD_BEFORE" "重装未产生新迁移" \
        && [ -f "$MARKER" ]; then
        phase "reinstall_same_version" PASS
    else
        phase "reinstall_same_version" FAIL "重装断言未全部通过"
    fi

    ok=yes
    systemctl restart btdeck || ok=no
    systemctl restart btdeck || ok=no
    if [ "$ok" = yes ] && wait_healthy 1.0.6 120 && service_active && single_port_listener; then
        phase "restart_twice" PASS
    else
        phase "restart_twice" FAIL "重启后状态异常"
    fi

    remove_rpm
    sleep 2
    if [ ! -x /opt/btdeck/btdeck ] \
        && [ -f "$MARKER" ] && [ -f /opt/btdeck/config/btdeck.env ]; then
        phase "remove_keeps_data" PASS
    else
        phase "remove_keeps_data" FAIL "remove 后程序残留或数据丢失"
    fi

elif [ "$SCENARIO" = "upgrade" ]; then
    [ -n "$OLD_RPM" ] && [ -f "$OLD_RPM" ] || die "upgrade 场景要求 --old-rpm（v1.0.5 正式本地制品）"

    # v1.0.5 冻结制品三处夹具适配（同 deb.sh：env 补建 + unit 覆写 + 显式 enable/restart）
    if install_rpm "$OLD_RPM"; then
        # 存在性检查不够：v1.0.5 旧 postinst 在 openssl/python3 双缺时会写出
        # 空 SECRET_KEY= 的 env（命令替换得空串仍继续），必须校验非空
        if ! grep -q '^SECRET_KEY=.' /opt/btdeck/config/btdeck.env 2>/dev/null; then
            mkdir -p /opt/btdeck/config
            if command -v openssl >/dev/null 2>&1; then
                SK="$(openssl rand -hex 32)"
            else
                SK="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' 
')"
            fi
            printf 'SECRET_KEY=%s
ALLOWED_HOSTS=["http://127.0.0.1:5001","http://localhost:5001"]
' "$SK"                 > /opt/btdeck/config/btdeck.env
            chmod 600 /opt/btdeck/config/btdeck.env
            chown btdeck:btdeck /opt/btdeck/config/btdeck.env 2>/dev/null || true
        fi
        if [ -f /src/deploy/btdeck.service ]; then
            cp /src/deploy/btdeck.service /etc/systemd/system/btdeck.service
        fi
        systemctl daemon-reload 2>/dev/null || true
        systemctl enable btdeck 2>/dev/null || true
        systemctl restart btdeck 2>/dev/null || true
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

    # RPM 升级：dnf install 新包（同包名更高版本走 upgrade 路径，%preun $1=1）
    # v1.0.5 冻结制品夹具适配（RPM 时序 %post(新)→%preun(旧)，与 DEB 相反）：
    #   v1.0.5 旧 prerm 无条件 stop+disable（R11 修复前的缺陷版，冻结不可改），
    #   会在新 postinst restart 之后停掉服务并 disable → 升级后停摆。
    #   v1.0.6 起新包 prerm 的 RPM 升级分支已 no-op（v1.0.6→未来升级不再需要
    #   本补偿）；此处显式 enable+restart 对冲 v1.0.5 旧 scriptlet，与 deb.sh
    #   基线段三处夹具适配同类。真实生产 v1.0.5→v1.0.6 RPM 升级需手动
    #   `systemctl enable --now btdeck`（登记 runbook/progress）。
    install_rpm "$NEW_RPM"
    systemctl enable btdeck >/dev/null 2>&1 || true
    systemctl restart btdeck >/dev/null 2>&1 || true
    if wait_healthy "1.0.6" \
        && assert_eq "$(service_active && echo yes || echo no)" yes "升级后服务 active（R11/RPM）" \
        && assert_eq "$(service_enabled && echo yes || echo no)" yes "升级后服务 enabled（R11/RPM）" \
        && assert_eq "$(service_unit_count)" 1 "升级后服务单元唯一" \
        && assert_eq "$(secret_fingerprint)" "$SECRET_BEFORE" "升级后 SECRET_KEY 保留" \
        && [ -f "$MARKER" ] \
        && assert_eq "$(alembic_head | cut -f1)" 1 "升级后 Alembic 单 head"; then
        phase "v105_to_v106_upgrade" PASS
    else
        phase "v105_to_v106_upgrade" FAIL "升级断言未全部通过（重点核查 prerm RPM 数字参数分支）"
    fi

    HEAD_AFTER="$(alembic_head | cut -f2)"
    if [ "$HEAD_AFTER" != "$HEAD_BEFORE" ] 2>/dev/null; then
        phase "alembic_head_advanced" PASS "→ $HEAD_AFTER"
    else
        phase "alembic_head_advanced" FAIL "head 未推进或不可读"
    fi

    remove_rpm
    sleep 2
    if [ ! -x /opt/btdeck/btdeck ] && [ -f "$MARKER" ]; then
        phase "remove_after_upgrade_keeps_data" PASS
    else
        phase "remove_after_upgrade_keeps_data" FAIL "升级后 remove 数据丢失或程序残留"
    fi
else
    die "未知场景: $SCENARIO"
fi

write_report "$REPORT" "rpm-${SCENARIO}" "$DISTRO"
