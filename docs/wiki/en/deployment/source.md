# Source deployment

Source deployment is intended for development, debugging, and contribution. Use Docker or a release-gated artifact for production.

## Toolchain

| Component | Baseline |
| --- | --- |
| Python | 3.12+ |
| Node.js | 22.23.2 (22.x) |
| npm | 10.9.8 |
| Backend | FastAPI + SQLAlchemy + SQLite |
| Frontend | Vue 2.6 + TypeScript + Element UI |

Install dependencies from the repository lock files and `package-lock.json`. Do not commit virtual environments, `node_modules`, or local databases.

## Start the backend

```bash
cd backend
python -m venv .venv
# Activate .venv, then run:
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001
```

The backend applies migrations and prepares initial data at startup. The database path comes from configuration; use a separate database for experiments so temporary schema changes do not affect a normal development instance.

## Start the frontend

```bash
cd frontend
npm ci
npm run serve
```

For a production-build check:

```bash
npm run typecheck
npm run lint
npm run build
```

The frontend development server normally runs at `http://localhost:8080`; API documentation is at `http://localhost:5001/docs`. If the frontend cannot reach the API, check the API base URL and `/health/ready` first.

## Tests and environment checks

The repository provides a lightweight root check:

```bash
./init.sh --ci
```

Run backend tests with `pytest` from `backend/` and frontend tests with `npm run test:unit`. Wiki-only changes do not require the full test suite, but changes to deployment examples or startup commands should be rechecked with the affected command.

## Development boundaries

- The API envelope, error codes, and pagination fields are stable contracts.
- Downloader connections must reuse the application cache; do not create a new client for every request.
- The current frontend baseline is Vue 2 with Options API/class-component code; Vue 3 composition syntax is not the project baseline.
- Database schema changes are managed through Alembic migrations only.

