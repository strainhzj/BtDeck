"""Torrent metadata hydration using cached downloader clients.

The database remains the source for duplicate detection and tracker history.  When a
row was written from a partial downloader delta, this module fills its display
metadata from the already cached qBittorrent/Transmission connection without
opening a second connection or writing to the database.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.core.torrent_status_mapper import TorrentStatusMapper
from app.models.setting_templates import DownloaderTypeEnum
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

logger = logging.getLogger(__name__)

TorrentMetadataKey = Tuple[str, str]

_QB_DETAIL_BATCH_SIZE = 100
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
    status = (
        TorrentStatusMapper.convert_qbittorrent_status(raw_state) if raw_state else None
    )
    return _without_none(
        {
            "torrent_id": torrent_hash,
            "hash": torrent_hash,
            "name": _text(_read_value(torrent, "name")),
            "save_path": _text(_read_value(torrent, "save_path")),
            "size": _integer(_read_value(torrent, "total_size", "size")),
            "status": status,
            "state": raw_state,
            "progress": _progress(
                _read_value(torrent, "progress"), fraction_scale=True
            ),
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
    status = (
        TorrentStatusMapper.convert_transmission_status(raw_status)
        if raw_status
        else None
    )
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
            "progress": _progress(
                _read_value(torrent, "percent_done", "percentDone"), fraction_scale=True
            ),
            "torrent_file": _text(_read_value(torrent, "torrent_file", "torrentFile")),
            "added_date": _datetime_value(
                _read_value(torrent, "added_date", "addedDate")
            ),
            "completed_date": _datetime_value(
                _read_value(torrent, "done_date", "doneDate")
            ),
            "ratio": _decimal_text(
                _read_value(torrent, "ratio", "upload_ratio", "uploadRatio")
            ),
            "ratio_limit": _decimal_text(
                _read_value(torrent, "seed_ratio_limit", "seedRatioLimit")
            ),
            "tags": _tag_text(_read_value(torrent, "labels")),
            "category": "",
            "super_seeding": "",
            "enabled": True,
            "download_speed": _integer(
                _read_value(torrent, "rate_download", "rateDownload")
            ),
            "upload_speed": _integer(_read_value(torrent, "rate_upload", "rateUpload")),
            "peers": _integer(
                _read_value(torrent, "peers_connected", "peersConnected")
            ),
            "seeds": _integer(
                _read_value(torrent, "peers_sending_to_us", "peersSendingToUs")
            ),
        }
    )


def torrent_record_needs_metadata(torrent: Any) -> bool:
    """Return True when a DB row lacks fields required by the torrent list."""
    name = _text(_read_value(torrent, "name"))
    save_path = _text(_read_value(torrent, "save_path"))
    status = _text(_read_value(torrent, "status"))
    size = _integer(_read_value(torrent, "size"))
    added_date = _read_value(torrent, "added_date")
    return not name or not save_path or not status or not size or added_date is None


async def fetch_qb_torrent_details(
    client: Any,
    downloader_id: str,
    torrent_hashes: Sequence[str],
    *,
    lane: DownloadLane,
    operation: str,
) -> List[Any]:
    """Fetch complete qBittorrent rows for hashes in bounded batches."""
    hashes = list(
        dict.fromkeys(
            value for value in (_normalized_hash(h) for h in torrent_hashes) if value
        )
    )
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
        result = await call_downloader_api(
            downloader_id,
            lane,
            method,
            kwargs={"torrent_hashes": batch},
            operation=operation,
        )
        if result:
            details.extend(list(result))
    return details


def _resolve_downloader_type(
    cached_downloader: Any, configured_type: Optional[str]
) -> Optional[str]:
    if configured_type in {"qbittorrent", "transmission"}:
        return configured_type
    try:
        normalized = DownloaderTypeEnum.normalize(
            _read_value(cached_downloader, "downloader_type")
        )
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
    records_by_downloader: Dict[str, List[Any]] = defaultdict(list)
    for torrent in torrent_records:
        downloader_id = _text(_read_value(torrent, "downloader_id"))
        torrent_hash = _normalized_hash(_read_value(torrent, "hash"))
        if downloader_id and torrent_hash and torrent_record_needs_metadata(torrent):
            records_by_downloader[downloader_id].append(torrent)

    store = getattr(getattr(app, "state", None), "store", None)
    if not records_by_downloader or store is None:
        return {}

    try:
        cached_downloaders = await store.get_snapshot()
    except Exception as exc:  # noqa: BLE001 - metadata hydration must remain best-effort
        logger.warning("duplicate metadata cache snapshot failed: %s", exc)
        return {}

    cache_by_id = {
        str(downloader_id): downloader
        for downloader in cached_downloaders or []
        if (downloader_id := _read_value(downloader, "downloader_id")) is not None
    }

    async def _fetch_one(
        downloader_id: str, records: List[Any]
    ) -> Dict[TorrentMetadataKey, Dict[str, Any]]:
        cached = cache_by_id.get(downloader_id)
        client = _read_value(cached, "client") if cached is not None else None
        if (
            cached is None
            or client is None
            or (_integer(_read_value(cached, "fail_time")) or 0) > 0
        ):
            return {}

        hashes = list(
            dict.fromkeys(
                value
                for value in (
                    _normalized_hash(_read_value(item, "hash")) for item in records
                )
                if value
            )
        )
        downloader_type = _resolve_downloader_type(
            cached, downloader_types.get(downloader_id)
        )
        try:
            if downloader_type == "qbittorrent":
                live_torrents = await fetch_qb_torrent_details(
                    client,
                    downloader_id,
                    hashes,
                    lane=DownloadLane.INTERACTIVE,
                    operation="duplicate_qb_metadata",
                )
                mapper = map_qb_torrent_metadata
            elif downloader_type == "transmission":
                method = getattr(client, "get_torrents", None)
                if method is None:
                    return {}
                live_torrents = await call_downloader_api(
                    downloader_id,
                    DownloadLane.INTERACTIVE,
                    method,
                    kwargs={"ids": hashes, "arguments": _TR_METADATA_FIELDS},
                    operation="duplicate_tr_metadata",
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
            mapped = mapper(live_torrent)
            torrent_hash = _normalized_hash(mapped.get("hash"))
            if torrent_hash:
                metadata[(downloader_id, torrent_hash)] = mapped
        return metadata

    results = await asyncio.gather(
        *(
            _fetch_one(downloader_id, records)
            for downloader_id, records in records_by_downloader.items()
        )
    )
    metadata: Dict[TorrentMetadataKey, Dict[str, Any]] = {}
    for result in results:
        metadata.update(result)
    return metadata
