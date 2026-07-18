"""Torrent metadata hydration using cached downloader clients.

The database remains the source for duplicate detection and tracker history.  When a
row was written from a partial downloader delta, this module fills its display
metadata from the already cached qBittorrent/Transmission connection without
opening a second connection or writing to the database.
"""

import asyncio
import logging
import time
from collections import OrderedDict, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from qbittorrentapi.exceptions import LoginFailed

from app.core.torrent_status_mapper import TorrentStatusMapper
from app.models.setting_templates import DownloaderTypeEnum
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

logger = logging.getLogger(__name__)

TorrentMetadataKey = Tuple[str, str]
TorrentMetadataCacheEntry = Tuple[float, Dict[str, Any]]
TorrentMetadataCache = OrderedDict[TorrentMetadataKey, TorrentMetadataCacheEntry]
TorrentMetadataCursorScope = Tuple[int, int, Optional[TorrentMetadataKey], Optional[TorrentMetadataKey]]
TorrentMetadataCursorState = OrderedDict[TorrentMetadataCursorScope, TorrentMetadataKey]

_QB_DETAIL_BATCH_SIZE = 100
_TR_DETAIL_BATCH_SIZE = 100
_LIVE_METADATA_MAX_RECORDS = 2000
_LIVE_METADATA_MAX_DOWNLOADERS = 20
_LIVE_METADATA_CACHE_TTL_SECONDS = 30.0
_LIVE_METADATA_CACHE_MAX_ENTRIES = 10000
_LIVE_METADATA_CURSOR_MAX_SCOPES = 128
_METADATA_CACHE_STATE_KEY = "_duplicate_torrent_metadata_cache"
_METADATA_CURSOR_STATE_KEY = "_duplicate_torrent_metadata_cursor"
_TR_METADATA_FIELDS = [
    "id",
    "hashString",
    "name",
    "status",
    "percentDone",
    "downloadDir",
    "totalSize",
    "torrentFile",
    "addedDate",
    "doneDate",
    "uploadRatio",
    "seedRatioLimit",
    "labels",
    "rateDownload",
    "rateUpload",
    "peersConnected",
    "peersSendingToUs",
]


def _read_value(source: Any, *names: str) -> Any:
    """Read a field from SDK dictionaries or attribute-based torrent objects."""
    for name in names:
        if isinstance(source, Mapping) and name in source:
            value = source[name]
            if value is not None:
                return value

        try:
            value = getattr(source, name)
        except (AttributeError, KeyError):
            pass
        else:
            if value is not None:
                return value

        getter = getattr(source, "get", None)
        if callable(getter):
            try:
                value = getter(name, None)
            except TypeError:
                try:
                    value = getter(name)
                except (AttributeError, KeyError, TypeError):
                    continue
            if value is not None:
                return value
    return None


def _normalized_hash(value: Any) -> str:
    return str(value or "").strip().lower()


def _text(value: Any, *, allow_empty: bool = False) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    result = str(value).strip()
    if not result and not allow_empty:
        return None
    return result


def _integer(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _decimal_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return str(value)


def _datetime_value(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            value = float(stripped)
        except ValueError:
            try:
                return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            except ValueError:
                return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(timestamp)
    except (OSError, OverflowError, ValueError):
        return None


def _progress(value: Any, *, fraction_scale: bool) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if fraction_scale and 0.0 <= result <= 1.0:
        result *= 100.0
    elif result > 1000.0:
        result /= 100.0
    return max(0.0, min(result, 100.0))


def _tag_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _without_none(values: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def map_qb_torrent_metadata(torrent: Any) -> Dict[str, Any]:
    """Convert a qBittorrent torrent payload to duplicate-response fields."""
    torrent_hash = _text(_read_value(torrent, "hash"))
    raw_state = _text(_read_value(torrent, "state"))
    status = TorrentStatusMapper.convert_qbittorrent_status(raw_state) if raw_state else None
    return _without_none(
        {
            "torrent_id": torrent_hash,
            "hash": torrent_hash,
            "name": _text(_read_value(torrent, "name")),
            "save_path": _text(_read_value(torrent, "save_path")),
            "size": _integer(_read_value(torrent, "total_size", "size")),
            "status": status,
            "state": raw_state,
            "progress": _progress(_read_value(torrent, "progress"), fraction_scale=True),
            "added_date": _datetime_value(_read_value(torrent, "added_on")),
            "completed_date": _datetime_value(_read_value(torrent, "completion_on")),
            "ratio": _decimal_text(_read_value(torrent, "ratio")),
            "ratio_limit": _decimal_text(_read_value(torrent, "ratio_limit")),
            "tags": _tag_text(_read_value(torrent, "tags")),
            "category": _text(_read_value(torrent, "category"), allow_empty=True),
            "super_seeding": _read_value(torrent, "super_seeding"),
            "enabled": True,
            "download_speed": _integer(_read_value(torrent, "dlspeed")),
            "upload_speed": _integer(_read_value(torrent, "upspeed")),
            "peers": _integer(_read_value(torrent, "num_leechs")),
            "seeds": _integer(_read_value(torrent, "num_seeds")),
        }
    )


def map_transmission_torrent_metadata(torrent: Any) -> Dict[str, Any]:
    """Convert a Transmission torrent payload to duplicate-response fields."""
    torrent_hash = _text(_read_value(torrent, "hash_string", "hashString", "hash"))
    raw_status = _text(_read_value(torrent, "status"))
    status = TorrentStatusMapper.convert_transmission_status(raw_status) if raw_status else None
    torrent_id = _read_value(torrent, "id")
    return _without_none(
        {
            "torrent_id": str(torrent_id) if torrent_id is not None else None,
            "hash": torrent_hash,
            "name": _text(_read_value(torrent, "name")),
            "save_path": _text(_read_value(torrent, "download_dir", "downloadDir")),
            "size": _integer(_read_value(torrent, "total_size", "totalSize")),
            "status": status,
            "state": raw_status,
            "progress": _progress(_read_value(torrent, "percent_done", "percentDone"), fraction_scale=True),
            "torrent_file": _text(_read_value(torrent, "torrent_file", "torrentFile")),
            "added_date": _datetime_value(_read_value(torrent, "added_date", "addedDate")),
            "completed_date": _datetime_value(_read_value(torrent, "done_date", "doneDate")),
            "ratio": _decimal_text(_read_value(torrent, "ratio", "upload_ratio", "uploadRatio")),
            "ratio_limit": _decimal_text(_read_value(torrent, "seed_ratio_limit", "seedRatioLimit")),
            "tags": _tag_text(_read_value(torrent, "labels")),
            "category": "",
            "super_seeding": "",
            "enabled": True,
            "download_speed": _integer(_read_value(torrent, "rate_download", "rateDownload")),
            "upload_speed": _integer(_read_value(torrent, "rate_upload", "rateUpload")),
            "peers": _integer(_read_value(torrent, "peers_connected", "peersConnected")),
            "seeds": _integer(_read_value(torrent, "peers_sending_to_us", "peersSendingToUs")),
        }
    )


def _torrent_record_missing_core_metadata(torrent: Any) -> bool:
    name = _text(_read_value(torrent, "name"))
    save_path = _text(_read_value(torrent, "save_path"))
    status = _text(_read_value(torrent, "status"))
    size = _integer(_read_value(torrent, "size"))
    added_date = _read_value(torrent, "added_date")
    return not name or not save_path or not status or size is None or size <= 0 or added_date is None


def torrent_record_needs_metadata(torrent: Any) -> bool:
    """Return True when a DB row contains incomplete persisted metadata.

    Empty tags/categories and zero progress/ratio/counters are valid values, so
    only ``None`` marks those fields as missing.  Live-only fields are included;
    the bounded candidate set plus the short TTL positive/negative cache below
    prevents them from creating unbounded downloader traffic.
    """
    if _torrent_record_missing_core_metadata(torrent):
        return True
    return any(
        _read_value(torrent, field) is None
        for field in (
            "torrent_id",
            "progress",
            "ratio",
            "ratio_limit",
            "tags",
            "category",
            "super_seeding",
            "enabled",
            "state",
            "download_speed",
            "upload_speed",
            "peers",
            "seeds",
        )
    )


def _metadata_cache(app: Any) -> TorrentMetadataCache:
    """Return the bounded per-application hydration cache."""
    state = getattr(app, "state", None)
    if state is None:
        return OrderedDict()
    cache = getattr(state, _METADATA_CACHE_STATE_KEY, None)
    if not isinstance(cache, OrderedDict):
        cache = OrderedDict()
        setattr(state, _METADATA_CACHE_STATE_KEY, cache)
    return cache


def _get_cached_metadata(app: Any, key: TorrentMetadataKey) -> Optional[Dict[str, Any]]:
    cache = _metadata_cache(app)
    cached = cache.get(key)
    if cached is None:
        return None
    expires_at, metadata = cached
    if expires_at <= time.monotonic():
        cache.pop(key, None)
        return None
    cache.move_to_end(key)
    return dict(metadata)


def _store_cached_metadata(app: Any, key: TorrentMetadataKey, metadata: Dict[str, Any]) -> None:
    cache = _metadata_cache(app)
    cache[key] = (
        time.monotonic() + _LIVE_METADATA_CACHE_TTL_SECONDS,
        dict(metadata),
    )
    cache.move_to_end(key)
    while len(cache) > _LIVE_METADATA_CACHE_MAX_ENTRIES:
        cache.popitem(last=False)


def _metadata_cursor_state(app: Any) -> TorrentMetadataCursorState:
    """Return bounded per-application cursors for capped hydration pages."""
    state = getattr(app, "state", None)
    if state is None:
        return OrderedDict()
    cursors = getattr(state, _METADATA_CURSOR_STATE_KEY, None)
    if not isinstance(cursors, OrderedDict):
        cursors = OrderedDict()
        setattr(state, _METADATA_CURSOR_STATE_KEY, cursors)
    return cursors


def _metadata_cursor_scope(
    ordered_keys: Sequence[TorrentMetadataKey],
) -> TorrentMetadataCursorScope:
    """Build a small process-local identity for an ordered candidate page."""
    if not ordered_keys:
        return (0, 0, None, None)
    return (
        len(ordered_keys),
        hash(tuple(ordered_keys)),
        ordered_keys[0],
        ordered_keys[-1],
    )


def _rotated_metadata_keys(
    app: Any, ordered_keys: Sequence[TorrentMetadataKey]
) -> Tuple[TorrentMetadataCursorScope, List[TorrentMetadataKey]]:
    """Start a capped scan at the page's saved next candidate."""
    scope = _metadata_cursor_scope(ordered_keys)
    cursors = _metadata_cursor_state(app)
    next_key = cursors.get(scope)
    if next_key is None:
        return scope, list(ordered_keys)
    try:
        start = ordered_keys.index(next_key)
    except ValueError:
        start = 0
    cursors.move_to_end(scope)
    return scope, list(ordered_keys[start:]) + list(ordered_keys[:start])


def _advance_metadata_cursor(
    app: Any,
    scope: TorrentMetadataCursorScope,
    ordered_keys: Sequence[TorrentMetadataKey],
    last_selected_key: Optional[TorrentMetadataKey],
) -> None:
    """Remember the item after the last capped selection without retaining pages."""
    if not ordered_keys or last_selected_key is None:
        return
    try:
        selected_index = ordered_keys.index(last_selected_key)
    except ValueError:
        return
    cursors = _metadata_cursor_state(app)
    cursors[scope] = ordered_keys[(selected_index + 1) % len(ordered_keys)]
    cursors.move_to_end(scope)
    while len(cursors) > _LIVE_METADATA_CURSOR_MAX_SCOPES:
        cursors.popitem(last=False)


async def fetch_qb_torrent_details(
    client: Any,
    downloader_id: str,
    torrent_hashes: Sequence[str],
    *,
    lane: DownloadLane,
    operation: str,
    failed_hashes: Optional[set[str]] = None,
) -> List[Any]:
    """Fetch qBittorrent rows in isolated batches, retaining successful ones."""
    hashes = list(dict.fromkeys(value for value in (_normalized_hash(h) for h in torrent_hashes) if value))
    if not hashes:
        return []

    method = getattr(client, "torrents_info", None)
    if method is None:
        torrents_api = getattr(client, "torrents", None)
        method = getattr(torrents_api, "info", None)
    if method is None:
        raise AttributeError("qBittorrent client does not expose torrents_info")

    details: List[Any] = []
    for start in range(0, len(hashes), _QB_DETAIL_BATCH_SIZE):
        batch = hashes[start : start + _QB_DETAIL_BATCH_SIZE]
        try:
            result = await call_downloader_api(
                downloader_id,
                lane,
                method,
                kwargs={"torrent_hashes": batch},
                operation=operation,
            )
            if result:
                details.extend(list(result))
        except LoginFailed:
            raise
        except Exception as exc:  # noqa: BLE001 - isolate one downloader batch
            if failed_hashes is not None:
                failed_hashes.update(batch)
            logger.warning(
                "qB metadata batch failed for downloader %s (offset=%s size=%s): %s",
                downloader_id,
                start,
                len(batch),
                exc,
            )
    return details


def _resolve_downloader_type(cached_downloader: Any, configured_type: Optional[str]) -> Optional[str]:
    if configured_type in {"qbittorrent", "transmission"}:
        return configured_type
    try:
        normalized = DownloaderTypeEnum.normalize(_read_value(cached_downloader, "downloader_type"))
    except (TypeError, ValueError):
        return None
    return DownloaderTypeEnum(normalized).to_name()


async def fetch_live_torrent_metadata(
    app: Any,
    torrent_records: Iterable[Any],
    downloader_types: Dict[str, str],
) -> Dict[TorrentMetadataKey, Dict[str, Any]]:
    """Fetch missing metadata with clients from ``app.state.store``.

    Failures are intentionally best-effort: duplicate detection is still useful
    while a downloader is temporarily offline, so the caller can retain DB data.
    """
    cached_metadata: Dict[TorrentMetadataKey, Dict[str, Any]] = {}
    core_candidate_keys: List[TorrentMetadataKey] = []
    optional_candidate_keys: List[TorrentMetadataKey] = []
    uncached_candidates: Dict[TorrentMetadataKey, Any] = {}
    seen_candidates = set()
    for torrent in torrent_records:
        downloader_id = _text(_read_value(torrent, "downloader_id"))
        torrent_hash = _normalized_hash(_read_value(torrent, "hash"))
        if not downloader_id or not torrent_hash or not torrent_record_needs_metadata(torrent):
            continue
        key = (downloader_id, torrent_hash)
        if key in seen_candidates:
            continue
        seen_candidates.add(key)
        target_keys = core_candidate_keys if _torrent_record_missing_core_metadata(torrent) else optional_candidate_keys
        target_keys.append(key)
        cached = _get_cached_metadata(app, key)
        if cached is not None:
            cached_metadata[key] = cached
            continue
        uncached_candidates[key] = torrent

    # One very large page must not monopolize the interactive downloader lane.
    # Prioritize rows missing core display data, then cap the total hashes and
    # downloader groups.  With 100-item batches this produces at most roughly 40
    # remote calls per request even in the most fragmented allowed case.
    records_by_downloader: Dict[str, List[Any]] = defaultdict(list)
    selected_records = 0
    last_selected_key: Optional[TorrentMetadataKey] = None
    ordered_candidate_keys = core_candidate_keys + optional_candidate_keys
    cursor_scope, rotated_candidate_keys = _rotated_metadata_keys(app, ordered_candidate_keys)
    for key in rotated_candidate_keys:
        torrent = uncached_candidates.get(key)
        if torrent is None:
            continue
        downloader_id, _torrent_hash = key
        if selected_records >= _LIVE_METADATA_MAX_RECORDS:
            continue
        if downloader_id not in records_by_downloader and len(records_by_downloader) >= _LIVE_METADATA_MAX_DOWNLOADERS:
            continue
        records_by_downloader[downloader_id].append(torrent)
        selected_records += 1
        last_selected_key = key

    _advance_metadata_cursor(
        app,
        cursor_scope,
        ordered_candidate_keys,
        last_selected_key,
    )
    skipped_records = len(uncached_candidates) - selected_records

    if skipped_records:
        logger.info(
            "duplicate metadata hydration capped: selected=%s skipped=%s downloaders=%s",
            selected_records,
            skipped_records,
            len(records_by_downloader),
        )

    store = getattr(getattr(app, "state", None), "store", None)
    if not records_by_downloader or store is None:
        return cached_metadata

    try:
        cached_downloaders = await store.get_snapshot()
    except Exception as exc:  # noqa: BLE001 - metadata hydration must remain best-effort
        logger.warning("duplicate metadata cache snapshot failed: %s", exc)
        return cached_metadata

    cache_by_id = {
        str(downloader_id): downloader
        for downloader in cached_downloaders or []
        if (downloader_id := _read_value(downloader, "downloader_id")) is not None
    }

    async def _fetch_one(downloader_id: str, records: List[Any]) -> Dict[TorrentMetadataKey, Dict[str, Any]]:
        cached = cache_by_id.get(downloader_id)
        client = _read_value(cached, "client") if cached is not None else None
        if cached is None or client is None or (_integer(_read_value(cached, "fail_time")) or 0) > 0:
            return {}

        hashes = list(
            dict.fromkeys(value for value in (_normalized_hash(_read_value(item, "hash")) for item in records) if value)
        )
        downloader_type = _resolve_downloader_type(cached, downloader_types.get(downloader_id))
        failed_hashes: set[str] = set()
        try:
            if downloader_type == "qbittorrent":
                live_torrents = await fetch_qb_torrent_details(
                    client,
                    downloader_id,
                    hashes,
                    lane=DownloadLane.INTERACTIVE,
                    operation="duplicate_qb_metadata",
                    failed_hashes=failed_hashes,
                )
                mapper = map_qb_torrent_metadata
            elif downloader_type == "transmission":
                method = getattr(client, "get_torrents", None)
                if method is None:
                    return {}
                live_torrents = []
                for start in range(0, len(hashes), _TR_DETAIL_BATCH_SIZE):
                    batch = hashes[start : start + _TR_DETAIL_BATCH_SIZE]
                    try:
                        result = await call_downloader_api(
                            downloader_id,
                            DownloadLane.INTERACTIVE,
                            method,
                            kwargs={"ids": batch, "arguments": _TR_METADATA_FIELDS},
                            operation="duplicate_tr_metadata",
                        )
                        if result:
                            live_torrents.extend(list(result))
                    except Exception as exc:  # noqa: BLE001 - isolate one batch
                        failed_hashes.update(batch)
                        logger.warning(
                            "Transmission metadata batch failed for downloader %s " "(offset=%s size=%s): %s",
                            downloader_id,
                            start,
                            len(batch),
                            exc,
                        )
                mapper = map_transmission_torrent_metadata
            else:
                return {}
        except Exception as exc:  # noqa: BLE001 - keep the DB-only duplicate result available
            logger.warning(
                "duplicate metadata fetch failed for downloader %s: %s",
                downloader_id,
                exc,
            )
            return {}

        metadata: Dict[TorrentMetadataKey, Dict[str, Any]] = {}
        for live_torrent in live_torrents or []:
            try:
                mapped = mapper(live_torrent)
                torrent_hash = _normalized_hash(mapped.get("hash"))
            except Exception as exc:  # noqa: BLE001 - isolate malformed SDK rows
                logger.warning(
                    "duplicate metadata mapping failed for downloader %s: %s",
                    downloader_id,
                    exc,
                )
                continue
            if torrent_hash:
                key = (downloader_id, torrent_hash)
                metadata[key] = mapped
                _store_cached_metadata(app, key, mapped)
        # Cache a short-lived miss as well.  Some SDKs legitimately omit a hash
        # from a partial response; retrying that same miss on every page refresh
        # would otherwise create an unbounded hydration loop.
        for torrent_hash in hashes:
            key = (downloader_id, torrent_hash)
            if key not in metadata and torrent_hash not in failed_hashes:
                _store_cached_metadata(app, key, {})
        return metadata

    results = await asyncio.gather(
        *(_fetch_one(downloader_id, records) for downloader_id, records in records_by_downloader.items())
    )
    metadata = dict(cached_metadata)
    for result in results:
        metadata.update(result)
    return metadata
