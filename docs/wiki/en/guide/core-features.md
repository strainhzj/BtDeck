# Core features

BtDeck organizes its pages around “downloader → torrent → file → task”. Capabilities differ between downloaders; the server capability check controls which actions are shown.

## Downloader management

The Downloader page can add qBittorrent or Transmission, test connections, synchronize, manage settings, and inspect capabilities. Common settings include the address, port, HTTPS, credentials, download-path mappings, speed schedules, and tags.

After a connection succeeds, BtDeck caches the downloader client and synchronizes torrents and Tracker state on schedule. When a downloader is temporarily offline, the UI keeps the necessary state and synchronizes again after recovery.

## Torrent management

The torrent list supports multi-downloader and multi-status filters, Tracker-error badges, remembered column widths, batch operations, and live speeds. Torrent details include files, peers, and Tracker data with fuzzy search.

When adding a torrent:

- Keep “skip verification” off for new data.
- Enable it for qBittorrent only when existing data is complete and you explicitly want to seed it immediately.
- Transmission does not expose an equivalent skip-verification parameter; the UI follows the downloader capability.

Deletion is separated into risk levels. The recycle bin and quarantine provide recovery points for reversible operations. Confirm the path, downloader, and backup state before permanent deletion.

## Search and query templates

Both simple and advanced search conditions can be saved as query templates. Built-in templates cover common filters; user and system templates have different edit and permission rules. A template stores query conditions and does not copy or move torrent files.

## Trackers and tasks

Tracker pages provide keywords, tests, reannounce operations, message records, and batch actions. Scheduled tasks cover synchronization and maintenance work; the task page reports running state, results, timeouts, and cancellation.

## Orphan files and recycle bin

An orphan file exists on disk but is not referenced by a torrent in the current downloaders. Scan results include confidence, status, and ignore-list information, with quarantine and recovery workflows. Scanning, deletion, and purge can affect real files; review the preview and path first.

## Notifications, audit, and integrations

- The notification center shows release notices and system messages.
- Audit logs record sensitive operations, their results, and required context.
- MCP exposes a controlled capability catalog and a service-key control surface; read the deployment security requirements before enabling it.
- MoviePilot integration links instances and organization history; the protocol version must match the peer.

