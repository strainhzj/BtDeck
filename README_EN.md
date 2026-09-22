# BtDeck - BitTorrent Management Platform

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.11+-brightgreen)](https://python.org/)
[![Vue](https://img.shields.io/badge/vue-2.6.12-brightgreen)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-green)](https://fastapi.tiangolo.com/)

[简体中文](./README.md) | **English**

A full-stack web application for unified management of multiple BitTorrent clients (qBittorrent, Transmission).

## Core Features

- **Unified multi-downloader management** - Supports qBittorrent and Transmission
- **Real-time status monitoring** - WebSocket live push of download speeds and states
- **Advanced search & query templates** - Save frequently used search conditions as one-click templates, with built-in system presets
- **Orphan file management** - Automatically identify disk-hogging files that belong to no downloader; confidence badges, ignore lists, and a quarantine zone make accidental deletions recoverable
- **Tracker anomaly detection** - A "Tracker error" tag on the torrent list instantly flags torrents whose tracker reporting failed, with error details one click away
- **Secure authentication** - JWT + TOTP two-factor verification
- **Notification center** - Version update notices and system messages
- **Data encryption** - Sensitive data encrypted with the SM4 cipher
- **One-click deployment** - Docker / Windows installer / Linux packages

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+ / FastAPI / SQLAlchemy / SQLite |
| Frontend | Vue 2.6.12 / TypeScript / Element UI / Vuex |
| Deployment | Docker Compose / PyInstaller / Inno Setup / fpm |

## Quick Start

### Docker Deployment (Recommended)

```bash
git clone https://github.com/strainhzj/BtDeck.git
cd BtDeck
docker compose up -d --build
```

Visit http://localhost:8080

> **First login**: default credentials `admin` / `admin`; the system will force a password change.
> **Security hardening** (mandatory for public/cross-network deployments): copy `.env.example` to `.env` and, per the comments, set the triple `DEV=false` + `SECRET_KEY` + `ALLOWED_HOSTS` (the container refuses to start if any is missing), and enable TLS — see `deploy/nginx-tls.conf.example` (with the default plain-HTTP deployment, login credentials and tokens travel in cleartext and can be sniffed).

### Development Environment

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001

# Frontend
cd frontend
npm install
npm run serve
```

| Service | Address |
|------|------|
| Frontend | http://localhost:8080 |
| API | http://localhost:5001 |
| API docs | http://localhost:5001/docs |
| WebSocket | ws://localhost:5002 |

## Code Roadmap

This project maintains a **progressively disclosed multi-file code roadmap** under `docs/roadmap/` for quickly locating module responsibilities, call relationships, and architecture conventions (read-only index; no source changes).

- **Entry**: [docs/roadmap/README.md](./docs/roadmap/README.md) ⇄ [CLAUDE.md](./CLAUDE.md) / [AGENTS.md](./AGENTS.md) (Chinese)
- **Three layers**: ① module routing (root README) → ② branch file lists (per-branch READMEs) → ③ source-file method-signature details (single-file .md)
- **Cross-cutting perspectives** (call chains / conventions / risks / test coverage): [docs/roadmap/perspectives/](./docs/roadmap/perspectives/)
- **Coverage**: backend (api/services/core/models/tasks, 8 branches) + frontend (entry/api/views/store, 6 branches) + deploy + tests
- **Layer-3 sample**: [torrent_crud.py roadmap](./docs/roadmap/backend/api/endpoints/torrent_crud.md) (remaining source files to be added incrementally per "mode B")

## Project Structure

```
BtDeck/
├── backend/                  # FastAPI backend
│   ├── app/
│   │   ├── api/             # API routes
│   │   ├── models/          # Database models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── services/        # Business logic
│   │   └── main.py          # Application entry
│   ├── alembic/             # Database migrations
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # Vue.js frontend
│   ├── src/
│   │   ├── api/             # API clients
│   │   ├── components/      # Components
│   │   ├── router/          # Router
│   │   ├── store/           # Vuex state management
│   │   └── views/           # Pages
│   ├── Dockerfile.prod
│   └── package.json
├── deploy/                   # Deployment & packaging
│   ├── btdeck.spec          # PyInstaller config
│   ├── btdeck.iss           # Inno Setup (Windows)
│   ├── build-linux.sh       # Linux build script
│   ├── build-windows.bat    # Windows build script
│   ├── build-android.bat    # Android APK build script
│   └── btdeck.service       # systemd service
├── build-packages.bat        # Unified entry: Windows EXE + Android APK
├── docker-compose.yml        # Full-stack Docker deployment
├── CLAUDE.md                 # Development guide (Chinese)
├── AGENTS.md                 # Full-stack workflow routing (Chinese)
└── docs/
    └── roadmap/              # Code roadmap (three-layer progressive disclosure)
```

## Package Building

### Windows EXE / Installer

```bat
deploy\build-windows.bat
```

Always produces the portable `dist\btdeck.exe`; when Inno Setup is installed and `ISCC` is available, it additionally produces `dist\BtDeck-v1.0.6-windows-x64-setup.exe`.

### Android APK

```bat
deploy\build-android.bat
```

By default runs JVM unit tests and produces two debug APKs in `android\dist\`: the strict build `btdeck-companion-0.2.5-strict-debug.apk` and the LAN cleartext test build `btdeck-companion-0.2.5-lan-cleartext-debug.apk`. To build a single variant, use `deploy\build-android.bat --strict-only` or `--lan-only`.

### Unified EXE + APK Build

```bat
build-packages.bat
```

You can also select targets with `build-packages.bat --windows`, `--android`, `--android-strict-only`, or `--android-lan-only`.

### Linux

```bash
cd deploy
chmod +x build-linux.sh
./build-linux.sh
```

Produces `dist/BtDeck-v1.0.6-linux-amd64.deb` and `.rpm`

### Docker Images

```bash
./build-images.sh
```

Builds local images only (`btdeck-backend:latest` / `btdeck-frontend:latest`, version read automatically from `feature_list.json`) without pushing to a registry. Run `docker compose up -d` afterwards to start.

## Version History

| Version | Theme | Release Date | Status |
|------|------|----------|------|
| v1.0.4 | Real-time speed monitoring + notification center + active torrent filtering | 2026-06-05 | Released |
| v1.0.5 | Orphan file management + query templates + security hardening + many fixes | 2026-08-21 | Released |
| v1.0.6 | Android client + full mobile web + desktop bilingual (CN/EN) + release engineering hardening | 2026-09-21 | Released |
| v1.1.0 | Automated operations | - | Planned |

> The product release number is sourced solely from [`release/release-config.json`](./release/release-config.json) (six places including `backend/app/version.py` are enforced consistent by release gates). The v1.0.x numbers in `feature_list.json` and `PLANS/` are internal milestone numbers, independent of release numbers (the v1.0.5 release packaged milestone v1.0.5 query templates, v1.0.6 orphan file management, v1.0.9 one-click deployment, and all fixes from 2026-06~08; the v1.0.6 release packaged milestone v1.0.6 dual-mode client, desktop-bilingual-20260918, and all fixes from 2026-08~09).

### v1.0.6 Highlights (2026-09-21)

- **Android client (new)** - A brand-new BtDeck Android app: in "companion mode" it connects to and manages a remote BtDeck server (connection wizard, health probing, credential memory, session restore, certificate-fingerprint pinning against MITM); switch to "on-device server mode" to run the full backend and frontend directly on the phone, start/stop anytime without a computer (ready in ~3–5 seconds after warm-up optimization); fully mobile UI with in-app file picking, back navigation, and branded visuals
- **Mobile web** - Phone browsers automatically enter the new mobile UI: dashboard, torrent list & details, downloader monitoring, tracker keywords, query templates, recycle bin, audit logs, orphan files, and system settings are all mobilized; PWA install, gestures (swipeable tabs, drawer gestures), pull-to-refresh, infinite scrolling, and empty-state guidance; advanced search rebuilt with native mobile interactions (summary card + bottom-sheet condition editor)
- **Desktop bilingual (Chinese/English)** - The desktop web fully supports Chinese/English switching (login page and top-bar toggles, automatic browser-language detection with preference memory); query template presets, notification events, and form validation errors are localized; backend API errors now use stable error codes (reasonCode) + fixed messages, consistent and readable in both languages, with raw exceptions logged only
- **Performance & stability** - Memory governance at scale: 100k-torrent sync peak memory down from ~270MB to 36MB, tracker reannounce down to 5MB from full load; Android on-device server steady-state memory down from 2.2GB to 400–700MB; cron-task timeout force-kill, true cancellation, and downloader-level circuit breakers; fixed stalling-torrent status oscillation, occasional bulk-add database lockups, terminal-state list refresh loops, runaway mobile infinite loading, and service startup crashes on Western-locale Windows
- **Packages & deployment** - All four artifact types (Windows EXE/installer, DEB, RPM, Docker images) share unified version numbers and build provenance, queryable via the health endpoint; the single Linux binary supports both Debian 12 and Rocky Linux 9, and DEB/RPM upgrades no longer interrupt service; unified Python 3.11 / Node 22 toolchain with hash-pinned dependencies; established a release gate system (version consistency, artifact equivalence, install lifecycle, SBOM security scanning)
- **Operations & troubleshooting** - New fault-diagnosis export (`/health/diagnosis`) for one-click runtime snapshots; Docker images standardized on UTC timezone and build-identity labels; BtDeck brand icons across installers and the Android app
- **Torrent management enhancements** - Torrent details gain Files/Peers tabs (sorting and fuzzy search); tracker domain filter hit highlighting; mobile support for seed count badges, single-torrent transfer, save-path changes, per-downloader tracker batch operations, a "skip verification" option when adding torrents, and one-tap notification mark-all-read

> The complete changelog is maintained in [`backend/app/version.py`](./backend/app/version.py); see also [GitHub Release v1.0.6](https://github.com/strainhzj/BtDeck/releases/tag/v1.0.6). This upgrade includes 3 database schema changes (query-template/settings-template preset keys, orphan-scan self-healing migration) that run automatically on first startup.

### v1.0.5 Highlights (2026-08-21)

- **Orphan file management** - Automatically finds files hogging disk space that belong to no downloader; searchable by name, size, and status; confidence badges and ignore lists help judge deletability; duplicate copies located and removed in one click; suspicious files are deferred and quarantined before deletion — viewable and recoverable if deleted by mistake
- **Query templates** - Save frequently used simple/advanced search conditions as one-click templates; built-in system presets; template management page with filtering, editing, and deletion
- **Torrent list enhancements** - New "Tracker error" tag with detailed error reasons; freely draggable column widths (both classic/grouped modes) with automatic memory; filter by multiple downloaders and multiple status combinations simultaneously
- **Security hardening** - Fixed multiple account and login vulnerabilities; consistent login state across multiple tabs; other devices automatically signed out after a password change
- **Performance & stability** - Optimized data writes during simultaneous multi-downloader sync; automatic cache cleanup after long downloader downtime; smoother list loading with large torrent counts; comprehensive automated test system established
- **Installation & deployment** - New Windows / Linux desktop installers with standalone-window operation; fixed startup failures in some environments after installation; Docker deployment supports custom image registries
- **Bug fixes** - qBittorrent download/seed status swap, seeding statistics errors, Transmission tracker info loss during sync, recycle-bin cleanup failures on network paths, new torrents showing "unknown" status, and more

> The complete changelog is maintained in [`backend/app/version.py`](./backend/app/version.py); see also [GitHub Release v1.0.5](https://github.com/strainhzj/BtDeck/releases/tag/v1.0.5). This upgrade involves database schema changes that run automatically on first startup.

See [PLANS/](./PLANS/) for details.

## Development Documentation

- [CLAUDE.md](./CLAUDE.md) - Full-stack development guide (Chinese)
- [backend/CLAUDE.md](./backend/CLAUDE.md) - Backend development conventions (Chinese)
- [frontend/CLAUDE.md](./frontend/CLAUDE.md) - Frontend development conventions (Chinese)

## License

[GNU General Public License v3.0](./LICENSE)
