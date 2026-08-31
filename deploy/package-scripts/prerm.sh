#!/bin/bash
# BtDeck 卸载/升级前置脚本（fpm --before-remove；DEB/RPM 共用）
# 语义（R11 + W3 CI 第八轮 RPM 时序修正）：
#   DEB  prerm $1 ∈ {remove|upgrade|deconfigure|failed-upgrade}
#   RPM  %preun $1 ∈ {0|1|2}（0=最终卸载；1/2=升级仍有实例保留）
#   → 升级路径：
#     DEB 时序 prerm(旧)→postinst(新)：stop 是安全的，postinst 会重新拉起；
#     RPM 时序 %post(新)→%preun(旧)：本脚本的 stop 会停掉 postinst 刚拉起的
#     新服务（CI 实测：v1.0.5→v1.0.6 升级后 3 分钟无健康响应），故 RPM 升级
#     分支必须 no-op，服务全权交给新包 postinst 管理。
#   卸载路径 stop + disable。
#   未知/空参数按卸载保守处理（等价旧行为）。
set -e

case "${1:-}" in
    # RPM 升级仍有实例保留：no-op（时序上 postinst 已 restart，此处 stop 反而停摆）
    1|2)
        exit 0
        ;;
    # DEB 升级：只 stop 保留 enabled，安装侧 postinst 重新拉起
    upgrade|deconfigure)
        systemctl stop btdeck || true
        ;;
    # 卸载（DEB remove / RPM 0）与未知参数：stop + disable
    *)
        systemctl stop btdeck || true
        systemctl disable btdeck || true
        ;;
esac
