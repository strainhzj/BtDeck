# BtDeck Wiki

[简体中文](../zh/index.md)

BtDeck is a full-stack BitTorrent management platform for qBittorrent and Transmission. It provides a web console, live status monitoring, search and query templates, Tracker operations, a recycle bin, orphan-file workflows, and mobile Web and Android clients with two operating modes.

This Wiki uses **v1.0.6** as its content baseline. Actual availability depends on the platform, downloader capabilities, and deployment configuration.

## Start here

- [Quick start](./quick-start.md): launch BtDeck for the first time.
- [Docker deployment](./deployment/docker.md): the recommended deployment path.
- [Source deployment](./deployment/source.md): local development and debugging.
- [Core features](./guide/core-features.md): understand the main pages and safety boundaries.
- [Mobile and Android](./guide/mobile-and-android.md): mobile Web, companion mode, and on-device server mode.
- [Security configuration](./operations/security.md): required before public exposure.
- [Troubleshooting](./troubleshooting.md): start with health checks and logs.

## What BtDeck can do

| Goal | Entry points |
| --- | --- |
| Manage multiple downloaders | Downloader management, connection tests, capability checks, setting templates |
| Manage torrents | Add, search, batch operations, tags, transfer, backup, tiered deletion |
| Observe runtime state | Dashboard, live speeds, Tracker state, notification center |
| Reclaim disk space | Orphan-file scan, ignore list, quarantine, and recycle bin |
| Automate work | Scheduled tasks, query templates, MCP capabilities |
| Use a phone | Mobile Web/PWA or the Android dual-mode client |

## Deployment options

| Option | Best for | Main entry |
| --- | --- | --- |
| Docker Compose | Long-running servers, NAS, home labs, or cloud hosts | [Docker deployment](./deployment/docker.md) |
| Source checkout | Development, debugging, and contribution | [Source deployment](./deployment/source.md) |
| Windows/Linux artifacts | Running without maintaining Python/Node locally | The repository `deploy/` and release notes |
| Android | Remote companion or on-device server | [Mobile and Android](./guide/mobile-and-android.md) |

## Version note

The product version comes from the repository's `release/release-config.json`. “Supported” statements in this Wiki describe the v1.0.6 release; roadmap items do not automatically represent shipped features.

