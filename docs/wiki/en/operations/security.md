# Security configuration

BtDeck can run on a trusted LAN or behind a reverse proxy for cross-network access. Complete this page before exposing it publicly.

## Required production variables

```dotenv
DEV=false
SECRET_KEY=replace-with-a-strong-random-value
ALLOWED_HOSTS=https://your-domain.example
DEBUG=false
```

With `DEV=false`, the backend refuses to start without `SECRET_KEY` or `ALLOWED_HOSTS`. Do not place `SECRET_KEY` in the Wiki, image tags, logs, or Git; generate it with Python's `secrets` module.

## TLS and access boundaries

The default Compose file maps only the frontend port to the host. In production, terminate TLS in Nginx, Caddy, or another reverse proxy and forward to the frontend container. See `deploy/nginx-tls.conf.example` and expose management ports only to required networks.

Plain HTTP exposes login credentials and tokens and is not a public deployment strategy. Set `ALLOWED_HOSTS` to the real origins instead of using an unnecessarily broad wildcard.

## Accounts and two-factor authentication

BtDeck uses JWT sessions and TOTP two-factor authentication. Change the initialized password immediately after the first sign-in; changing a password signs out other devices. Use distinct passwords for different environments and protect the TOTP seed and recovery process.

## Data and backups

The SQLite database, configuration, downloader credentials, audit records, and backup files are sensitive. Restrict permissions on bind-mounted directories and back them up regularly. Before restoring, stop writes, preserve the original backup, and verify the migration version and filesystem paths.

## Runtime parameters

- Keep one backend worker to preserve SQLite locking, resource admission, and scheduler consistency.
- The default timezone is UTC. Scheduled jobs follow the application's Asia/Shanghai trigger rule while logs and API timestamps follow the common time contract.
- Keep `DEBUG` disabled in production to avoid exposing tracebacks.

