# Quick start

This guide starts BtDeck with Docker. For a first deployment, validate it on your LAN before adding a domain and TLS.

## Prerequisites

- Docker Engine and Docker Compose v2.
- A network path from the BtDeck containers to each downloader's Web API.
- A strong random `SECRET_KEY` and the domain or address that should be allowed in production.

## Start with Docker

Run this from the repository root:

```bash
git clone https://github.com/strainhzj/BtDeck.git
cd BtDeck
cp .env.example .env
docker compose up -d --build
```

Open `http://localhost:8080`. Change the host port with `BTDECK_PORT` in `.env`.

The first startup prepares the configuration directory and runs database migrations. After signing in, change the initialized password immediately and run a connection test for every downloader. This Wiki never stores initial passwords, secrets, or real addresses.

Inspect the containers:

```bash
docker compose ps
docker compose logs -f backend
```

The backend readiness check inside its container is `http://localhost:5001/health/ready`; the frontend health check is `/health`. The frontend waits for the backend health check before starting.

## Run from source

Source development uses Python 3.12+, Node.js 22.23.2 (22.x), and npm. Start the backend and frontend separately:

```bash
# Backend
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001
```

In another terminal:

```bash
cd frontend
npm ci
npm run serve
```

Development addresses:

| Service | Address |
| --- | --- |
| Frontend | `http://localhost:8080` |
| API | `http://localhost:5001` |
| API docs | `http://localhost:5001/docs` |
| WebSocket | `ws://localhost:5002` |

The application runs migrations on startup. Keep a single backend worker with SQLite; do not scale it by adding workers.

## First verification

1. Open the frontend and complete sign-in and the password change flow.
2. Add qBittorrent or Transmission in the Downloader page using an address reachable from the backend.
3. Run the connection test and wait for the first synchronization.
4. Confirm that the dashboard shows the downloader online, torrent counts, and speeds.
5. Configure query templates, notifications, and mobile access after the basic path works.

If step 2 fails, check that the downloader Web API is enabled, that the container can resolve its address, and that the backend log contains a structured error code.

