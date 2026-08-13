"""同名同大小种子只读排查服务。

该服务用于发现名称和大小完全一致、但 InfoHash 不同的种子任务，并在同一
分组内标记任务状态或 Tracker 状态异常。候选组、错误组和分页均在数据库中
完成；只为当前页加载成员与 Tracker 明细，避免全量数据进入应用内存。

安全约束：响应只包含 Tracker 主机名，不返回包含 passkey/authkey 的完整 URL；
错误消息中的 URL 查询参数和常见敏感参数也会被脱敏。
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Literal, Mapping, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.downloader.models import BtDownloaders
from app.enums.tracker_status import get_tracker_status_text
from app.services.deletion_task_manager import build_active_deletion_exclusion
from app.torrents.models import TorrentInfo, TrackerInfo, TrackerKeywordConfig

InspectionMode = Literal["all", "errors"]

_FAILED_TRACKER_STATES = frozenset({3, 4})
_URL_PATTERN = re.compile(r"(?P<url>(?:https?|udp)://[^\s<>'\"]+)", re.IGNORECASE)
_SENSITIVE_PARAMETER_PATTERN = re.compile(r"(?i)\b(passkey|authkey|api[_-]?key|token|secret)=([^\s&;]+)")


def _chunks(values: Sequence[str], size: int = 500) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_status(value: Any) -> str:
    return _normalized_text(value).lower()


def _state_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_failed_tracker_state(value: Any) -> bool:
    return _state_value(value) in _FAILED_TRACKER_STATES


def _safe_url_without_query(raw_url: str) -> str:
    """保留 URL 的 scheme/host/path，删除用户信息、查询参数和 fragment。"""
    trailing = ""
    candidate = raw_url
    while candidate and candidate[-1] in ".,;:!?)]}":
        trailing = candidate[-1] + trailing
        candidate = candidate[:-1]

    try:
        parsed = urlsplit(candidate)
        if not parsed.hostname:
            return "[已隐藏 Tracker URL]" + trailing
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, "", "", "")) + trailing
    except (ValueError, TypeError):
        return "[已隐藏 Tracker URL]" + trailing


def sanitize_inspection_message(value: Any) -> str:
    """脱敏并限制排查消息长度，避免 Tracker 凭据出现在查询响应中。"""
    message = _normalized_text(value)
    if not message:
        return ""
    message = _URL_PATTERN.sub(lambda match: _safe_url_without_query(match.group("url")), message)
    message = _SENSITIVE_PARAMETER_PATTERN.sub(lambda match: f"{match.group(1)}=***", message)
    return message[:1000]


def _safe_tracker_host(tracker: TrackerInfo) -> str:
    raw_value = _normalized_text(tracker.tracker_host) or _normalized_text(tracker.tracker_url)
    if not raw_value:
        return "未知 Tracker"

    try:
        parsed = urlsplit(raw_value if "://" in raw_value else f"//{raw_value}")
        if parsed.hostname:
            return parsed.hostname.lower()[:256]
    except (ValueError, TypeError):
        pass
    return "未知 Tracker"


def _matches_failure_keyword(message: Any, failure_keywords: Sequence[str]) -> bool:
    normalized_message = _normalized_status(message)
    return any(keyword in normalized_message for keyword in failure_keywords)


def _tracker_issue_types(tracker: TrackerInfo, failure_keywords: Sequence[str]) -> List[str]:
    issue_types: List[str] = []
    if _normalized_status(tracker.status) == "error":
        issue_types.append("tracker_status")
    if _is_failed_tracker_state(tracker.last_announce_succeeded):
        issue_types.append("announce")
    if _is_failed_tracker_state(tracker.last_scrape_succeeded):
        issue_types.append("scrape")
    if "announce" not in issue_types and _matches_failure_keyword(tracker.last_announce_msg, failure_keywords):
        issue_types.append("announce")
    if "scrape" not in issue_types and _matches_failure_keyword(tracker.last_scrape_msg, failure_keywords):
        issue_types.append("scrape")
    return issue_types


def _display_tracker_state(value: Any, downloader_type: int) -> str:
    state = _state_value(value)
    if state is None:
        return ""
    downloader_type_name = "transmission" if downloader_type == 1 else "qbittorrent"
    return get_tracker_status_text(state, downloader_type_name)


def _tracker_issue_payload(
    tracker: TrackerInfo,
    downloader_type: int,
    failure_keywords: Sequence[str],
) -> Dict[str, Any] | None:
    issue_types = _tracker_issue_types(tracker, failure_keywords)
    if not issue_types:
        return None
    return {
        "tracker_name": sanitize_inspection_message(tracker.tracker_name),
        "tracker_host": _safe_tracker_host(tracker),
        "issue_types": issue_types,
        "announce_status": _display_tracker_state(tracker.last_announce_succeeded, downloader_type),
        "announce_message": sanitize_inspection_message(tracker.last_announce_msg),
        "scrape_status": _display_tracker_state(tracker.last_scrape_succeeded, downloader_type),
        "scrape_message": sanitize_inspection_message(tracker.last_scrape_msg),
        "status_message": sanitize_inspection_message(tracker.msg),
    }


def _failure_keyword_match_expression() -> Any:
    """判断 Tracker 最新消息是否命中启用的失败关键词。"""
    normalized_keyword = func.lower(func.trim(TrackerKeywordConfig.keyword))
    return (
        select(TrackerKeywordConfig.keyword_id)
        .where(
            TrackerKeywordConfig.dr == 0,
            TrackerKeywordConfig.enabled.is_(True),
            TrackerKeywordConfig.keyword_type == "failed",
            func.length(func.trim(TrackerKeywordConfig.keyword)) > 0,
            or_(
                func.instr(
                    func.lower(func.coalesce(TrackerInfo.last_announce_msg, "")),
                    normalized_keyword,
                )
                > 0,
                func.instr(
                    func.lower(func.coalesce(TrackerInfo.last_scrape_msg, "")),
                    normalized_keyword,
                )
                > 0,
            ),
        )
        .correlate(TrackerInfo)
        .exists()
    )


def _tracker_error_exists_expression() -> Any:
    return (
        select(TrackerInfo.tracker_id)
        .where(
            TrackerInfo.torrent_info_id == TorrentInfo.info_id,
            TrackerInfo.dr == 0,
            or_(
                func.lower(func.trim(func.coalesce(TrackerInfo.status, ""))) == "error",
                TrackerInfo.last_announce_succeeded.in_(tuple(_FAILED_TRACKER_STATES)),
                TrackerInfo.last_scrape_succeeded.in_(tuple(_FAILED_TRACKER_STATES)),
                _failure_keyword_match_expression(),
            ),
        )
        .correlate(TorrentInfo)
        .exists()
    )


def _torrent_error_expression() -> Any:
    return or_(
        func.lower(func.trim(func.coalesce(TorrentInfo.status, ""))) == "error",
        func.length(func.trim(func.coalesce(TorrentInfo.error_reason, ""))) > 0,
        TorrentInfo.has_tracker_error.is_(True),
        _tracker_error_exists_expression(),
    )


def _base_conditions() -> List[Any]:
    conditions: List[Any] = [
        TorrentInfo.dr == 0,
        TorrentInfo.deleted_at.is_(None),
        TorrentInfo.name.isnot(None),
        func.length(func.trim(TorrentInfo.name)) > 0,
        TorrentInfo.size.isnot(None),
        TorrentInfo.size > 0,
        TorrentInfo.hash.isnot(None),
        func.length(func.trim(TorrentInfo.hash)) > 0,
    ]
    active_deletion_exclusion = build_active_deletion_exclusion(TorrentInfo.info_id)
    if active_deletion_exclusion is not None:
        conditions.append(active_deletion_exclusion)
    return conditions


def _candidate_groups_subquery() -> Any:
    normalized_hash = func.lower(func.trim(TorrentInfo.hash))
    error_expression = _torrent_error_expression()
    return (
        select(
            TorrentInfo.name.label("name"),
            TorrentInfo.size.label("size"),
            func.count().label("copy_count"),
            func.count(func.distinct(normalized_hash)).label("distinct_hash_count"),
            func.count(func.distinct(TorrentInfo.downloader_id)).label("downloader_count"),
            func.sum(case((error_expression, 1), else_=0)).label("error_count"),
            func.max(TorrentInfo.update_time).label("last_updated_at"),
        )
        .where(*_base_conditions())
        .group_by(TorrentInfo.name, TorrentInfo.size)
        .having(func.count(func.distinct(normalized_hash)) >= 2)
        .subquery()
    )


def _group_key(name: str, size: Any) -> str:
    size_key = format(float(size), ".17g") if size is not None else ""
    return hashlib.sha256(f"{name}\0{size_key}".encode("utf-8")).hexdigest()[:20]


def _load_trackers(db: Session, info_ids: Sequence[str]) -> Mapping[str, List[TrackerInfo]]:
    tracker_map: Dict[str, List[TrackerInfo]] = defaultdict(list)
    for info_id_chunk in _chunks(list(dict.fromkeys(info_ids))):
        trackers = (
            db.query(TrackerInfo)
            .filter(TrackerInfo.dr == 0, TrackerInfo.torrent_info_id.in_(info_id_chunk))
            .order_by(TrackerInfo.tracker_name.asc(), TrackerInfo.tracker_id.asc())
            .all()
        )
        for tracker in trackers:
            tracker_map[str(tracker.torrent_info_id)].append(tracker)
    return tracker_map


def _load_downloader_types(db: Session, downloader_ids: Sequence[str]) -> Mapping[str, int]:
    downloader_types: Dict[str, int] = {}
    for downloader_id_chunk in _chunks(list(dict.fromkeys(downloader_ids))):
        rows = (
            db.query(BtDownloaders.downloader_id, BtDownloaders.downloader_type)
            .filter(BtDownloaders.dr == 0, BtDownloaders.downloader_id.in_(downloader_id_chunk))
            .all()
        )
        for downloader_id, downloader_type in rows:
            downloader_types[str(downloader_id)] = int(downloader_type or 0)
    return downloader_types


def _load_failure_keywords(db: Session) -> List[str]:
    rows = (
        db.query(TrackerKeywordConfig.keyword)
        .filter(
            TrackerKeywordConfig.dr == 0,
            TrackerKeywordConfig.enabled.is_(True),
            TrackerKeywordConfig.keyword_type == "failed",
            func.length(func.trim(TrackerKeywordConfig.keyword)) > 0,
        )
        .order_by(TrackerKeywordConfig.priority.desc(), TrackerKeywordConfig.keyword.asc())
        .all()
    )
    return list(dict.fromkeys(_normalized_status(row.keyword) for row in rows if _normalized_text(row.keyword)))


def _item_payload(
    torrent: TorrentInfo,
    trackers: Sequence[TrackerInfo],
    downloader_type: int,
    failure_keywords: Sequence[str],
) -> Dict[str, Any]:
    tracker_hosts = sorted({_safe_tracker_host(tracker) for tracker in trackers})
    tracker_issues = [
        issue
        for tracker in trackers
        if (issue := _tracker_issue_payload(tracker, downloader_type, failure_keywords)) is not None
    ]

    error_types: List[str] = []
    if _normalized_status(torrent.status) == "error":
        error_types.append("torrent_status")
    if _normalized_text(torrent.error_reason):
        error_types.append("error_reason")
    if bool(torrent.has_tracker_error):
        error_types.append("tracker_aggregate")
    if tracker_issues:
        error_types.append("tracker_detail")

    return {
        "info_id": str(torrent.info_id),
        "downloader_id": str(torrent.downloader_id),
        "downloader_name": _normalized_text(torrent.downloader_name),
        "hash": _normalized_text(torrent.hash),
        "status": _normalized_text(torrent.status),
        "error_reason": sanitize_inspection_message(torrent.error_reason),
        "has_tracker_error": bool(torrent.has_tracker_error),
        "is_error": bool(error_types),
        "error_types": error_types,
        "tracker_hosts": tracker_hosts,
        "tracker_issues": tracker_issues,
        "updated_at": torrent.update_time.isoformat() if torrent.update_time else None,
    }


def inspect_same_content_torrents(
    db: Session,
    *,
    mode: InspectionMode,
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    """查询同名同大小候选组，并按模式返回完整成员或仅错误成员。"""
    groups = _candidate_groups_subquery()

    summary_row = (
        db.query(
            func.count().label("candidate_group_count"),
            func.coalesce(func.sum(groups.c.copy_count), 0).label("candidate_torrent_count"),
            func.coalesce(func.sum(case((groups.c.error_count > 0, 1), else_=0)), 0).label("error_group_count"),
            func.coalesce(func.sum(groups.c.error_count), 0).label("error_torrent_count"),
        )
        .select_from(groups)
        .one()
    )

    group_query = db.query(
        groups.c.name,
        groups.c.size,
        groups.c.copy_count,
        groups.c.distinct_hash_count,
        groups.c.downloader_count,
        groups.c.error_count,
        groups.c.last_updated_at,
    )
    if mode == "errors":
        group_query = group_query.filter(groups.c.error_count > 0)

    total = group_query.count()
    group_rows = (
        group_query.order_by(
            groups.c.error_count.desc(),
            func.lower(groups.c.name).asc(),
            groups.c.size.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    if not group_rows:
        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "list": [],
            "summary": {
                "candidate_group_count": int(summary_row.candidate_group_count or 0),
                "candidate_torrent_count": int(summary_row.candidate_torrent_count or 0),
                "error_group_count": int(summary_row.error_group_count or 0),
                "error_torrent_count": int(summary_row.error_torrent_count or 0),
            },
        }

    page_group_conditions = [and_(TorrentInfo.name == row.name, TorrentInfo.size == row.size) for row in group_rows]
    member_query = db.query(TorrentInfo).filter(*_base_conditions(), or_(*page_group_conditions))
    if mode == "errors":
        member_query = member_query.filter(_torrent_error_expression())
    members = member_query.order_by(
        func.lower(TorrentInfo.name).asc(),
        TorrentInfo.size.desc(),
        func.lower(TorrentInfo.downloader_name).asc(),
        TorrentInfo.info_id.asc(),
    ).all()

    info_ids = [str(torrent.info_id) for torrent in members]
    downloader_ids = [str(torrent.downloader_id) for torrent in members]
    tracker_map = _load_trackers(db, info_ids)
    downloader_types = _load_downloader_types(db, downloader_ids)
    failure_keywords = _load_failure_keywords(db)

    item_map: Dict[Tuple[str, float], List[Dict[str, Any]]] = defaultdict(list)
    for torrent in members:
        item = _item_payload(
            torrent,
            tracker_map.get(str(torrent.info_id), []),
            downloader_types.get(str(torrent.downloader_id), 0),
            failure_keywords,
        )
        # SQL 与 Python 使用相同判错条件；此过滤同时防御并发更新造成的瞬时漂移。
        if mode == "errors" and not item["is_error"]:
            continue
        item_map[(str(torrent.name), float(torrent.size))].append(item)

    result_groups: List[Dict[str, Any]] = []
    for row in group_rows:
        items = item_map.get((str(row.name), float(row.size)), [])
        tracker_hosts = sorted({host for item in items for host in item["tracker_hosts"]})
        result_groups.append(
            {
                "group_key": _group_key(str(row.name), row.size),
                "name": str(row.name),
                "size": row.size,
                "copy_count": int(row.copy_count or 0),
                "distinct_hash_count": int(row.distinct_hash_count or 0),
                "downloader_count": int(row.downloader_count or 0),
                "error_count": int(row.error_count or 0),
                "tracker_hosts": tracker_hosts,
                "last_updated_at": row.last_updated_at.isoformat() if row.last_updated_at else None,
                "items": items,
            }
        )

    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "list": result_groups,
        "summary": {
            "candidate_group_count": int(summary_row.candidate_group_count or 0),
            "candidate_torrent_count": int(summary_row.candidate_torrent_count or 0),
            "error_group_count": int(summary_row.error_group_count or 0),
            "error_torrent_count": int(summary_row.error_torrent_count or 0),
        },
    }
