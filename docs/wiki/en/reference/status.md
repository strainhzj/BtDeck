# Project status

This page records the BtDeck state checked while writing the Wiki. It was updated on **2026-09-23**; re-check the release configuration and health endpoint before publishing a release.

## Release baseline

| Item | Status |
| --- | --- |
| Current product version | v1.0.6 |
| v1.0.6 release date | 2026-09-21 |
| Current development milestone | v1.0.6 |
| Next direction | v1.1.0 automated operations (planned) |
| Backend baseline | Python 3.12, FastAPI, SQLAlchemy, SQLite |
| Frontend baseline | Vue 2.6, TypeScript, Element UI, Vuex |
| Android client | Dual-mode; version name is defined in `android/app/build.gradle.kts` |

The only product-version source is `release/release-config.json`. Version numbers in `feature_list.json` and `PLANS/` may be internal milestones and must not be treated as release versions.

## Shipped in v1.0.6

- Android companion and on-device server modes.
- Mobile Web, PWA, gestures, pull-to-refresh, and bounded infinite loading.
- Desktop Chinese/English switching, stable error codes, and localized templates and notifications.
- Torrent file and peer details, Tracker-domain matches, and per-downloader Tracker batch actions.
- Query templates, orphan-file quarantine and recovery, and the MCP service capability and key control surface.
- Version and build-provenance governance for Windows, Linux, and Docker artifacts.

## Recent validation record

The repository progress log records a full validation on 2026-09-22 covering backend pytest, mypy, black, and flake8, plus frontend typecheck, lint, build, and the full Jest suite: 5249 backend tests passed and 125 frontend suites/1844 tests passed. This is development-repository evidence and does not replace release revalidation.

## Not yet covered by the first Wiki pass

The complete API reference, page-by-page screenshots, cross-version upgrade drills, and real-downloader compatibility matrix still need verification in deployment environments. When a page disagrees with observed behavior, prefer the current health endpoint, capability matrix, and release notes, then update this source.

