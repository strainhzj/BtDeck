#!/bin/bash
# BtDeck DEB postinst（fpm --after-install；RPM 由 fpm 自动适配安装/升级场景）
# 语义（release-artifact-equivalence-gate W3 / G6，修复 R11）：
#   - 首次安装与升级共用：确保用户/目录/env；SECRET_KEY 仅在缺失时生成（重装/升级不重置）
#   - daemon-reload + enable；服务未运行则启动（升级路径：preupd 已 stop，此处拉起）
#   - 不依赖 $1 区分场景：幂等操作本身覆盖 install/upgrade 两态
set -e

# 创建 btdeck 系统用户
if ! id -u btdeck &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false btdeck
fi

# 预创建 systemd ReadWritePaths 声明的目录
# (ProtectSystem=strict 下应用需这些目录可写，否则首次启动写入失败)
mkdir -p /opt/btdeck/config /opt/btdeck/data /opt/btdeck/logs /opt/btdeck/backup /opt/btdeck/torrents

if [ ! -f /opt/btdeck/config/btdeck.env ]; then
    # 兜底链：openssl → coreutils(/dev/urandom)。不用 python3——最小化系统（W3 容器实测）
    # 可能没有 openssl/python3，coreutils 的 head/od/tr 必在。
    if command -v openssl >/dev/null 2>&1; then
        SECRET_KEY="$(openssl rand -hex 32)"
    else
        SECRET_KEY="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    fi
cat > /opt/btdeck/config/btdeck.env <<EOF
SECRET_KEY=${SECRET_KEY}
# pydantic-settings 对 List[str] 环境变量强制 JSON 解析（逗号分隔会 SettingsError 启动崩溃），
# 必须用 JSON 数组格式（与 desktop_main.py 一致）
ALLOWED_HOSTS=["http://127.0.0.1:5001","http://localhost:5001"]
EOF
    chmod 600 /opt/btdeck/config/btdeck.env
fi

# 设置权限
chown -R btdeck:btdeck /opt/btdeck

# 启用并启动服务（幂等：升级/重装后重启到新二进制，不产生重复实例）
# degraded 是容器内 systemd 常见正常态，必须与 running 同等接受，
# 否则容器/最小化环境下 postinst 会静默跳过 enable+start（W3 实测拦截）
# RPM 升级时序 %post(新)先于 %preun(旧)：此时服务仍是旧进程（持旧 inode，
# serving 旧版本健康契约），必须 restart 才切换到新二进制；"未运行才启动"
# 会让 RPM 升级后继续跑旧版本（W3 CI 第八轮实测拦截）
if command -v systemctl >/dev/null 2>&1 \
    && systemctl is-system-running 2>/dev/null | grep -qE '^(running|degraded)$'; then
    systemctl daemon-reload
    systemctl enable btdeck
    if systemctl is-active --quiet btdeck; then
        systemctl restart btdeck
    else
        systemctl start btdeck
    fi
    echo "BtDeck service started. Visit: http://localhost:5001"
else
    echo "BtDeck installed, but systemd is not active. Start manually with: systemctl start btdeck"
    echo "After start, visit: http://localhost:5001"
fi
