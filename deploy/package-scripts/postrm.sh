#!/bin/bash
# BtDeck DEB postrm（fpm --after-remove；仅 DEB 使用）
# 语义：
#   remove  —— 程序文件已由 dpkg 移除；数据/配置默认保留（G6 卸载语义）
#   purge   —— 显式清除数据与配置（用户主动执行 apt purge 才触发）
#   upgrade/failed-upgrade —— 无动作
# BTDECK_PREFIX：测试注入前缀（打包运行不设置，即真实绝对路径）。
set -e
PREFIX="${BTDECK_PREFIX:-}"

case "$1" in
    purge)
        echo "BtDeck purge: removing data and config under ${PREFIX}/opt/btdeck"
        systemctl stop btdeck 2>/dev/null || true
        rm -rf "${PREFIX}/opt/btdeck/config" "${PREFIX}/opt/btdeck/data" "${PREFIX}/opt/btdeck/logs" \
            "${PREFIX}/opt/btdeck/backup" "${PREFIX}/opt/btdeck/torrents"
        rm -f "${PREFIX}/etc/systemd/system/btdeck.service"
        systemctl daemon-reload 2>/dev/null || true
        ;;
    remove|upgrade|failed-upgrade|disappear)
        ;;
    *)
        echo "btdeck postrm called with unknown argument \`$1'" >&2
        exit 1
        ;;
esac
