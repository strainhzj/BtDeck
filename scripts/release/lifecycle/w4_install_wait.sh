#!/bin/bash
# W4 制品实例安装+健康等待脚本（release-artifact-equivalence-gate task .8 / G8）。
# 由 w4-contract CI job 在容器内执行：
#   bash w4_install_wait.sh <pkg-path>
# 设计约束：
#   - 安装命令不作为参数传入（"dpkg -i" 整串会成单命令名 → command not found
#     127，CI 第三轮实测）；按包文件后缀在脚本内分支。
#   - 等待逻辑必须脚本文件化——docker exec 的嵌套引号转义链在 workflow YAML
#     内不可靠（CI 首两轮实测 8 秒即挂无输出，与 W3 windows.ps1 教训同型）。
set -e

pkg="$1"
case "$pkg" in
    *.deb) dpkg -i "$pkg" >/tmp/install.log 2>&1 ;;
    *.rpm) dnf -y install "$pkg" >/tmp/install.log 2>&1 ;;
    *) echo "unknown package type: $pkg"; exit 2 ;;
esac

for i in $(seq 1 60); do
    body=$(curl -fsS --max-time 5 http://127.0.0.1:5001/health/live 2>/dev/null || true)
    case "$body" in
        *'"version":"1.0.6"'*) exit 0 ;;
    esac
    sleep 3
done

echo 'service not healthy'
tail -5 /tmp/install.log 2>/dev/null
exit 1
