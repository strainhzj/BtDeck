#!/bin/bash
# BtDeck 卸载/升级前置脚本（fpm --before-remove；DEB/RPM 共用）
# 语义（R11 修复核心）：
#   DEB  prerm $1 ∈ {remove|upgrade|deconfigure|failed-upgrade}
#   RPM  %preun $1 ∈ {0|1|2}（0=最终卸载；1/2=升级仍有实例保留）
#   → 升级路径只 stop（保留 enabled，安装侧 postinst 重新拉起）；
#     卸载路径 stop + disable。
#   未知/空参数按卸载保守处理（等价旧行为）。
set -e

is_remove=1
case "${1:-}" in
    upgrade|deconfigure|1|2)
        is_remove=0
        ;;
esac

systemctl stop btdeck || true
if [ "$is_remove" = "1" ]; then
    systemctl disable btdeck || true
fi
