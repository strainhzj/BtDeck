# Mobile and Android

v1.0.6 provides both mobile Web and an Android client with two operating modes. Mobile pages share backend capabilities with desktop pages while adapting navigation and actions for touch screens.

## Mobile Web

Phone browsers enter the mobile UI, which covers the dashboard, torrent list and details, downloaders, Tracker keywords, recycle bin, audit logs, orphan files, and settings. The mobile experience includes:

- PWA installation;
- swipeable tabs, drawer gestures, and pull-to-refresh;
- bounded append loading for torrent and notification lists;
- a mobile advanced-search flow with a bottom-sheet condition editor.

If an update still shows old pages, close the old PWA window, clear the site cache, and reopen it. Do not delete backend data to solve a frontend cache issue.

## Android companion mode

Companion mode connects to an existing BtDeck server. Create a server profile, enter its URL, username, and credentials, and run a health check. The app loads the server's own frontend in a WebView and can store encrypted credentials for session recovery.

Self-signed HTTPS requires explicit SHA-256 certificate-fingerprint trust. The app does not unconditionally accept arbitrary certificates.

## Android on-device server mode

On-device server mode runs the BtDeck backend and frontend in the phone's private directory and opens it through a local profile. It prefers the previous dynamic port and reports startup stages for directory preparation, migration, import, bind, and health checks.

Only 64-bit ABIs are supported: `arm64-v8a` and `x86_64`. 32-bit devices cannot install or run the on-device server.

The LAN switch is off by default. Enabling it displays the cleartext and LAN-exposure risk; public HTTP addresses are rejected. File-system, path-mapping, orphan-file, torrent-backup, seed-transfer, and high-risk deletion capabilities may be disabled in on-device server mode by the capability matrix. Follow the runtime capability result.

## When a connection fails

1. Confirm that the server URL is reachable from the phone; do not use the computer's `localhost` address.
2. Check `/health/live` and `/health/ready`.
3. Complete certificate-fingerprint trust before retrying a self-signed HTTPS check.
4. In on-device mode, check the ABI, service notification, startup stage, and dynamic port.

