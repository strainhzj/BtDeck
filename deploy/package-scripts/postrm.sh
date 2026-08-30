#!/bin/bash
# BtDeck DEB postrm（fpm --after-remove；仅 DEB 使用）
# 语义：
#   remove  —— 程序文件已由 dpkg 移除；数据/配置默认保留（G6 卸载语义）
#   purge   —— 显式清除数据与配置（用户主动执行 apt purge 才触发）
#   upgrade/failed-upgrade —— 无动作
set -e
case "$1" in
    purge)
        echo "BtDeck purge: removing data and config under /opt/btdeck"
        systemctl stop btdeck 2>/dev/null || true
        rm -rf /opt/btdeck/config /opt/btdeck/data /opt/btdeck/logs /opt/btdeck/backup /opt/btdeck/torrents
        rm -f /etc/systemd/system/btdeck.service
        systemctl daemon-reload 2>/dev/null || true
        ;;
    remove|upgrade|failed-upgrade|disappear)
        ;;
    *)
        echo "btdeck postrm called with unknown argument \`$1'" >&2
        exit 1
        ;;
esac
