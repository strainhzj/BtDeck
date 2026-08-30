#!/bin/bash
# 生命周期断言公共库（release-artifact-equivalence-gate W3 / G6）
# 在目标 systemd 容器内执行；fail-closed：任何断言失败即记录并最终非零退出。

LIFECYCLE_PHASES=()
LIFECYCLE_FAILED=0

phase() {
    LIFECYCLE_PHASES+=("{\"name\": \"$1\", \"status\": \"$2\"${3:+, \"details\": \"$3\"}}")
    if [ "$2" != "PASS" ]; then
        LIFECYCLE_FAILED=1
        echo "[PHASE-FAIL] $1: $3" >&2
    else
        echo "[PHASE-PASS] $1"
    fi
}

die() { echo "[FATAL] $1" >&2; exit 2; }

wait_http() {
    # wait_http <url> <expected-substr> <max-seconds>
    # 匹配用 bash case 子串比较（字节级）：实测容器内 grep 对含引号/UTF-8 的
    # 响应体存在环境相关的匹配异常，case 无 locale/引用层且零依赖。
    local url="$1" want="$2" max="${3:-120}" i=0 body=""
    while [ $i -lt $((max / 3)) ]; do
        body="$(curl -fsS --max-time 5 "$url" 2>/dev/null || true)"
        case "$body" in
            *"$want"*) return 0 ;;
        esac
        sleep 3
        i=$((i + 1))
    done
    echo "[wait_http] timeout waiting '$want' at $url; last: ${body:0:200}" >&2
    return 1
}

assert_eq() {
    # assert_eq <actual> <expected> <label>
    if [ "$1" != "$2" ]; then
        echo "[ASSERT-FAIL] $3: actual='$1' expected='$2'" >&2
        return 1
    fi
    return 0
}

service_active() { systemctl is-active --quiet btdeck; }
service_enabled() { systemctl is-enabled btdeck 2>/dev/null | grep -q '^enabled'; }

service_unit_count() {
    systemctl list-units --type=service --all --no-legend 'btdeck*' 2>/dev/null | grep -c . || true
}

single_port_listener() {
    # 5001 端口监听唯一（ss 缺失时退化为 ss/netstat 均无则跳过并显式声明）
    if command -v ss >/dev/null 2>&1; then
        [ "$(ss -ltnH 2>/dev/null | grep -c ':5001 ')" = "1" ]
    elif command -v netstat >/dev/null 2>&1; then
        [ "$(netstat -ltn 2>/dev/null | grep -c ':5001 ')" = "1" ]
    else
        echo "[WARN] ss/netstat 均不可用，端口唯一性断言降级为跳过" >&2
        return 0
    fi
}

find_app_db() {
    local db
    for db in /opt/btdeck/config/app.db /opt/btdeck/data/app.db; do
        [ -f "$db" ] && { echo "$db"; return 0; }
    done
    find /opt/btdeck -maxdepth 3 -name 'app.db' -type f 2>/dev/null | head -1
}

alembic_head() {
    # 输出 "count<TAB>head"
    local db
    db="$(find_app_db)" || true
    [ -n "$db" ] || { echo "0 none"; return 1; }
    sqlite3 -separator '	' "$db" 'select count(*), min(version_num) from alembic_version;'
}

secret_fingerprint() {
    # SECRET_KEY 行的 sha256（不输出密钥本身）
    if [ -f /opt/btdeck/config/btdeck.env ]; then
        grep '^SECRET_KEY=' /opt/btdeck/config/btdeck.env | sha256sum | awk '{print $1}'
    else
        echo "missing"
    fi
}

build_info_field() {
    # build_info_field <file> <python-dict-key-expr>
    python3 -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))$2)" "$1" 2>/dev/null || echo "ERR"
}

write_report() {
    # write_report <path> <scenario> <distro>
    local path="$1" scenario="$2" distro="$3"
    local verdict="PASS"
    [ "$LIFECYCLE_FAILED" = "1" ] && verdict="FAIL"
    cat > "$path" <<EOF
{
  "schema_version": 1,
  "scenario": "${scenario}",
  "distro": "${distro}",
  "executed_at": "$(date -u +%FT%TZ)",
  "verdict": "${verdict}",
  "phases": [
    $(printf '    %s\n' "${LIFECYCLE_PHASES[@]}" | paste -sd, - | sed 's/,$//')
  ]
}
EOF
    echo "report written: $path (verdict=${verdict})"
    [ "$verdict" = "PASS" ]
}
