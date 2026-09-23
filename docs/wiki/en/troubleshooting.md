# Troubleshooting

Record the product version, deployment method, time, and relevant logs before investigating. Do not delete the database or the whole `data` directory as a first response.

## The page is unavailable or returns 502

1. Use `docker compose ps` to confirm that both frontend and backend are running.
2. Read `docker compose logs --tail=200 backend` and check `/health/ready`.
3. If the backend restarts repeatedly, check `DEV`, `SECRET_KEY`, `ALLOWED_HOSTS`, and configuration-directory permissions.
4. If only the frontend is stale, rebuild the frontend image and clear browser/PWA cache.

## Backend stops during migration

Keep the original logs and a database backup. Check that the configuration directory is writable, disk space is available, and no other process is holding the SQLite file. Do not replace the existing database with an empty one to bypass a migration.

## A downloader cannot connect

- Test the downloader address from the backend environment, not only from a browser.
- Check the qBittorrent or Transmission Web API, port, HTTPS, and authentication settings.
- Make sure `localhost` does not refer to the wrong machine or container.
- Review the downloader capability result and structured backend error code; never paste tokens or passwords from logs into a ticket.

## Login, TOTP, or session problems

Check that the server, phone, and TOTP clock are reasonably synchronized. Changing a password invalidates old device sessions. For multi-tab inconsistencies, refresh all tabs before checking browser-console and backend authentication logs.

## Orphan scan or deletion problems

Verify scan roots, downloader path mappings, and permissions first. Review confidence, ignore-list entries, previews, and quarantine records; take extra care with hard links, duplicate copies, and network paths. File-system operations may be disabled in Android on-device server mode.

## Android cannot connect to its local server

Read the stage shown by the wizard: directory preparation, migration, import, bind, or health check. 32-bit devices do not support on-device server mode. LAN access requires the explicit switch and an address and dynamic port reachable from the phone.

## Sharing diagnostics

Share the version, health results, redacted log excerpts, and reproduction steps. When `/health/diagnosis` is available, inspect the export and remove domains, usernames, paths, and secrets before sharing it.

