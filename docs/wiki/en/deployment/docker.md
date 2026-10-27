# Docker deployment

The Docker Compose deployment contains a FastAPI backend and an Nginx frontend. Compose defaults to the v1.0.6 image tag while retaining the local source-build configuration.

## Start and update

```bash
cp .env.example .env
docker compose up -d --build
```

When using published images:

```bash
docker compose pull
docker compose up -d
```

Read the release notes before upgrading and back up `data/backend/config`. Startup applies Alembic migrations; the backend refuses to continue with an incomplete schema.

## Persistent data

Compose maps backend data into the project directory:

| Host directory | Container directory | Purpose |
| --- | --- | --- |
| `data/backend/data` | `/app/data` | Torrent and business data |
| `data/backend/logs` | `/app/logs` | Backend logs |
| `data/backend/config` | `/app/config` | SQLite database, configuration, and migration state |
| `data/backend/backup` | `/app/backup` | Backup files |

These directories contain sensitive business data. Restrict host permissions and keep them out of Git and public downloads.

## Production security

Set the following in `.env` before public or cross-network deployment:

```dotenv
DEV=false
SECRET_KEY=replace-with-a-strong-random-value
ALLOWED_HOSTS=https://your-domain.example
DEBUG=false
```

The backend refuses to start if `DEV=false`, `SECRET_KEY`, or `ALLOWED_HOSTS` is missing. Put a TLS reverse proxy in front of the service; see `deploy/nginx-tls.conf.example`. Plain HTTP exposes login credentials and tokens to network sniffing.

## Ports and networking

- The frontend exposes `${BTDECK_PORT:-8080}` on the host and port 80 in the container.
- The backend listens on 5001 inside the Compose network and is not mapped to the host by default.
- The backend provides WebSocket support; development uses port 5002, while production routing is handled by the frontend Nginx configuration.
- The backend uses SQLite and an in-process scheduler. Keep one worker; multiple workers break database locking, resource admission, and scheduler uniqueness.

## Maintenance commands

```bash
docker compose ps
docker compose logs --tail=200 backend
docker compose restart backend
docker compose down
```

`docker compose down` does not remove the bind-mounted data directories. Do not use volume-deleting options unless you have confirmed a recoverable backup and intend to remove the data.

