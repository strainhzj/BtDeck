#!/bin/sh

# Deploy pre-built BtDeck images without letting Compose abort while the
# backend is still completing its startup reconciliation.
set -eu

REMOTE_COMPOSE="${BTDECK_REMOTE_COMPOSE:-}"
if [ -z "$REMOTE_COMPOSE" ]; then
    for candidate in docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
        if [ -f "$candidate" ]; then
            REMOTE_COMPOSE="$candidate"
            break
        fi
    done
fi

if [ -z "$REMOTE_COMPOSE" ] || [ ! -f "$REMOTE_COMPOSE" ]; then
    echo "[ERROR] Remote compose file not found."
    echo "[INFO] Current directory:"
    pwd
    echo "[INFO] Expected one of: docker-compose.yml docker-compose.yaml compose.yml compose.yaml"
    echo "[INFO] Or pass --compose /path/to/docker-compose.yml"
    ls -la
    exit 1
fi

if docker compose version >/dev/null 2>&1; then
    compose() {
        docker compose -f "$REMOTE_COMPOSE" "$@"
    }
elif command -v docker-compose >/dev/null 2>&1; then
    compose() {
        docker-compose -f "$REMOTE_COMPOSE" "$@"
    }
else
    echo "[ERROR] Docker Compose is not installed on remote host."
    echo "For Unraid, install the Docker Compose Manager plugin or install docker compose manually."
    exit 1
fi

echo "[INFO] Using remote compose file: $REMOTE_COMPOSE"
compose down || true

echo "[INFO] Removing old tagged BtDeck images"
docker image rm btdeck-backend:latest btdeck-frontend:latest >/dev/null 2>&1 || true
docker load -i btdeck-backend.latest.tar
docker load -i btdeck-frontend.latest.tar

# Start only the backend first.  The remote compose file has a
# service_healthy dependency for frontend, but Compose can return an error
# before a slow backend becomes healthy.  Polling the container state keeps
# the deployment decision under our control.
compose up -d --no-build backend

health="starting"
attempt=0
max_attempts="${BTDECK_BACKEND_HEALTH_ATTEMPTS:-30}"
echo "[INFO] Waiting up to $((max_attempts * 10)) seconds for btdeck-backend to become healthy"
while [ "$attempt" -lt "$max_attempts" ]; do
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' btdeck-backend 2>/dev/null || true)"
    if [ "$health" = "healthy" ]; then
        echo "[OK] btdeck-backend is healthy"
        break
    fi

    attempt=$((attempt + 1))
    if [ "$health" = "unhealthy" ]; then
        echo "[WARN] btdeck-backend is still unhealthy ($attempt/$max_attempts)"
    else
        echo "[INFO] btdeck-backend health=$health ($attempt/$max_attempts)"
    fi
    sleep 10
done

if [ "$health" != "healthy" ]; then
    echo "[ERROR] btdeck-backend did not become healthy within the deployment timeout."
    docker inspect --format '{{json .State.Health}}' btdeck-backend 2>/dev/null || true
    echo "[INFO] Inspect startup details with: docker logs --tail 200 btdeck-backend"
    exit 1
fi

compose up -d --no-build frontend
compose ps
docker image prune -f >/dev/null 2>&1 || true
