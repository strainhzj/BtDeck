#!/bin/bash
# Docker 生命周期驱动（release-artifact-equivalence-gate task .7 / G6/G7）
# 在有 docker + docker compose 的宿主上执行（本地或 CI）。
#
# 场景链（fail-closed，任一失败非零退出）：
#   1. v1.0.5 组合上线（tag 重建镜像，reconstructed 语义）→ 健康 1.0.5 → 植入卷 marker
#   2. 重复 compose up -d → 容器不被 recreate（幂等）
#   3. restart → force-recreate → 卷数据保留
#   4. 升级到 v1.0.6 组合（换镜像 up）→ 容器 recreate → 健康 1.0.6（build.gitSha 暴露）→
#      marker 保留、Alembic head 推进且单 head
#   5. 同 digest 组合重复 up → 不 recreate
#   6. down → up（同 v1.0.6）→ 数据仍保留
# 用法：docker.sh --project-root DIR [--evidence-dir DIR]
# 前置：btdeck-backend:v1.0.6 / btdeck-frontend:v1.0.6 已由 build-images.sh --release 产出；
#       v1.0.5 后端镜像由本脚本从 git tag v1.0.5 重建（reconstructed=true，只能证明卷升级路径）。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ROOT="$DEFAULT_ROOT"
EVIDENCE_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --project-root) ROOT="$(cd "$2" && pwd)"; shift 2 ;;
        --evidence-dir) EVIDENCE_DIR="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 2 ;;
    esac
done
EVIDENCE_DIR="${EVIDENCE_DIR:-${ROOT}/release/evidence/w3}"
mkdir -p "$EVIDENCE_DIR"
REPORT="${EVIDENCE_DIR}/lifecycle-docker.json"

PHASES=()
FAILED=0
phase() {
    PHASES+=("{\"name\": \"$1\", \"status\": \"$2\"${3:+, \"details\": \"$3\"}}")
    [ "$2" = PASS ] && echo "[PHASE-PASS] $1" || { FAILED=1; echo "[PHASE-FAIL] $1: $3" >&2; }
}

WORKDIR="$(mktemp -d)"
ID_V105=""
ID_V106=""
HEAD_BEFORE="none"
HEAD_AFTER="none"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.test.yml"
BACKEND_V105="btdeck-backend:v1.0.5-w3fixture"
BACKEND_V106="btdeck-backend:v1.0.6"
FRONTEND_V106="btdeck-frontend:v1.0.6"

up() { (cd "$WORKDIR" && BTDECK_BACKEND_IMAGE="$1" BTDECK_FRONTEND_IMAGE="$FRONTEND_V106" \
    docker compose -f "$COMPOSE_FILE" -p w3life up -d); }
backend_exec() { docker exec w3-life-backend sh -c "$1"; }
backend_health() {  # backend_health <version-substr> <max-sec>
    local i=0
    while [ $i -lt $(($2 / 5)) ]; do
        body="$(backend_exec "curl -fsS http://localhost:5001/health/live" 2>/dev/null || true)"
        case "$body" in
            *"\"version\":\"$1\""*) return 0 ;;
        esac
        sleep 5; i=$((i + 1))
    done
    return 1
}
container_id() { docker ps -q --filter name=w3-life-backend; }

# ---------- 0) v1.0.5 夹具镜像（tag 重建，reconstructed） ----------
echo "[SETUP] 从 tag v1.0.5 重建后端夹具镜像（reconstructed）..."
if git -C "$ROOT" rev-parse v1.0.5^{commit} >/dev/null 2>&1; then
    ARCHIVE_DIR="${WORKDIR}/v105-src"
    mkdir -p "$ARCHIVE_DIR"
    if git -C "$ROOT" archive --format=tar v1.0.5 | tar -xf - -C "$ARCHIVE_DIR" \
        && docker build -q -t "$BACKEND_V105" \
            --build-arg PIP_INDEX_URL="${BTDECK_PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}" \
            "${ARCHIVE_DIR}/backend" >/dev/null; then
        phase "v105_fixture_image" PASS "reconstructed from tag v1.0.5"
    else
        phase "v105_fixture_image" FAIL "tag 重建镜像失败"
    fi
else
    phase "v105_fixture_image" FAIL "git tag v1.0.5 不存在"
fi

docker image inspect "$BACKEND_V106" >/dev/null 2>&1 || phase "v106_images_present" FAIL "缺少 $BACKEND_V106（先运行 build-images.sh --release）"
docker image inspect "$FRONTEND_V106" >/dev/null 2>&1 || phase "v106_images_present" FAIL "缺少 $FRONTEND_V106"
docker image inspect "$BACKEND_V106" >/dev/null 2>&1 && docker image inspect "$FRONTEND_V106" >/dev/null 2>&1 \
    && phase "v106_images_present" PASS

# ---------- 1) v1.0.5 上线 + marker ----------
if up "$BACKEND_V105"; then
    docker logs w3-life-backend > "${EVIDENCE_DIR}/lifecycle-docker.v105-backend.log" 2>&1 || true
fi
if up "$BACKEND_V105" && backend_health 1.0.5 420; then
    HEAD_BEFORE="$(backend_exec "python -c \"import sqlite3,glob; p=(glob.glob('/app/config/app.db')+glob.glob('/app/data/app.db')); print(sqlite3.connect(p[0]).execute('select version_num from alembic_version').fetchone()[0] if p else 'none')\"" 2>/dev/null || echo none)"
    backend_exec "echo w3-docker-marker > /app/data/w3-marker.txt"
    ID_V105="$(container_id)"
    phase "v105_up_healthy" PASS "head=${HEAD_BEFORE}"
else
    phase "v105_up_healthy" FAIL "v1.0.5 组合未就绪"
fi

# ---------- 2) 重复 up 幂等 ----------
up "$BACKEND_V105" >/dev/null 2>&1
if [ "$(container_id)" = "$ID_V105" ] && backend_health 1.0.5 60; then
    phase "repeat_up_no_recreate" PASS
else
    phase "repeat_up_no_recreate" FAIL "重复 up 触发了 recreate 或失联"
fi

# ---------- 3) restart + force-recreate 数据保留 ----------
(cd "$WORKDIR" && docker compose -f "$COMPOSE_FILE" -p w3life restart btdeck-backend >/dev/null 2>&1)
backend_health 1.0.5 120 || true
(cd "$WORKDIR" && docker compose -f "$COMPOSE_FILE" -p w3life up -d --force-recreate btdeck-backend >/dev/null 2>&1)
if backend_health 1.0.5 240 && backend_exec "test -f /app/data/w3-marker.txt"; then
    phase "restart_and_recreate_keep_volume" PASS
else
    phase "restart_and_recreate_keep_volume" FAIL "recreate 后失联或 marker 丢失"
fi

# ---------- 4) 升级到 v1.0.6 ----------
GIT_SHA_106="$(docker image inspect "$BACKEND_V106" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null || true)"
up "$BACKEND_V106" >/dev/null 2>&1
sleep 3
ID_V106="$(container_id)"
if backend_health 1.0.6 240 \
    && backend_exec "test -f /app/data/w3-marker.txt" \
    && backend_exec "curl -fsS http://localhost:5001/health/ready" >/dev/null 2>&1; then
    BUILD_BLOCK="$(backend_exec "curl -fsS http://localhost:5001/health/live" 2>/dev/null)"
    HEAD_AFTER="$(backend_exec "python -c \"import sqlite3,glob; p=(glob.glob('/app/config/app.db')+glob.glob('/app/data/app.db')); c=sqlite3.connect(p[0]); r=c.execute('select count(*),min(version_num) from alembic_version').fetchone(); print(r[0],r[1]) if p else print('none')\"" 2>/dev/null || echo none)"
    if echo "$BUILD_BLOCK" | grep -q '"status": "ok"' && [ -n "$GIT_SHA_106" ] && echo "$BUILD_BLOCK" | grep -q "$GIT_SHA_106"; then
        phase "upgrade_to_v106" PASS "head: ${HEAD_BEFORE} → $(echo "$HEAD_AFTER" | awk '{print $2}')"
    else
        phase "upgrade_to_v106" FAIL "健康 1.0.6 但 build 身份不匹配（label=${GIT_SHA_106:0:12}; live=${BUILD_BLOCK:0:160}）"
    fi
else
    phase "upgrade_to_v106" FAIL "v1.0.6 未就绪或 marker 丢失"
fi
if [ "$(echo "$HEAD_AFTER" | awk '{print $1}')" = "1" ]; then
    phase "alembic_single_head_after_upgrade" PASS "$HEAD_AFTER"
else
    phase "alembic_single_head_after_upgrade" FAIL "head=$HEAD_AFTER"
fi

# ---------- 5) 同组合重复 up 不 recreate ----------
up "$BACKEND_V106" >/dev/null 2>&1
if [ "$(container_id)" = "$ID_V106" ]; then
    phase "same_digest_up_no_recreate" PASS
else
    phase "same_digest_up_no_recreate" FAIL "同镜像 up 触发 recreate"
fi

# ---------- 6) down + up 数据保留 ----------
(cd "$WORKDIR" && docker compose -f "$COMPOSE_FILE" -p w3life down >/dev/null 2>&1)
up "$BACKEND_V106" >/dev/null 2>&1
if backend_health 1.0.6 240 && backend_exec "test -f /app/data/w3-marker.txt"; then
    phase "down_up_keeps_volume" PASS
else
    phase "down_up_keeps_volume" FAIL "down/up 后数据丢失"
fi

# ---------- 收尾 ----------
(cd "$WORKDIR" && docker compose -f "$COMPOSE_FILE" -p w3life down -v >/dev/null 2>&1)
rm -rf "$WORKDIR"

VERDICT=PASS; [ $FAILED = 1 ] && VERDICT=FAIL
cat > "$REPORT" <<EOF
{
  "schema_version": 1,
  "scenario": "docker-lifecycle",
  "executed_at": "$(date -u +%FT%TZ)",
  "verdict": "${VERDICT}",
  "phases": [
    $(printf '    %s\n' "${PHASES[@]}" | paste -sd, - | sed 's/,$//')
  ]
}
EOF
echo "report: $REPORT (verdict=${VERDICT})"
[ "$VERDICT" = PASS ]
