"""种子 VO 组装与转换（服务层共享，feature mcp-service-capabilities W4/G4）。

从 ``app/api/endpoints/torrent_helpers.py`` 原样迁移（分层债收尾第二笔）：
高级搜索服务（AdvancedSearchService）与列表端点共用的 VO 转换族——
单/带 Tracker/批量三种转换、SQLite 绑定变量安全批大小与域名筛选行级谓词。
服务层不得依赖 HTTP endpoint 层（G0/G4 口径），HTTP 端点改为正向依赖本模块。

迁移纪律：函数体与 torrent_helpers 原实现逐字一致（含注释），仅归属变化；
``_RELATED_PREFETCH_BATCH_SIZE`` 常量随迁，测试打桩目标改为本模块。
"""

import logging
import sqlite3
from datetime import datetime  # noqa: F401 - cast 占位字符串引用
from typing import Dict, List, Optional, Sequence, cast

from sqlalchemy.orm import Session

from app.core.tracker_keyword_map import load_active_keyword_map
from app.core.tracker_status_policy import FAILED_DISPLAY_TEXT, tracker_display_failed
from app.models.setting_templates import DownloaderTypeEnum
from app.torrents.models import TorrentInfo as torrentInfoModel
from app.torrents.models import TrackerInfo
from app.torrents.responseVO import TorrentInfoVO
from app.torrents.trackerVO import TrackerInfoVO

logger = logging.getLogger(__name__)


def tracker_row_matches_domains(
    tracker_host: Optional[str], tracker_url: Optional[str], domains: Optional[List[str]]
) -> Optional[str]:
    """判断单个 tracker 行是否命中域名筛选，返回命中的域名（无命中返回 None）。

    与 ``get_torrent_infos`` 内 SQL 侧的 8 个域名匹配条件一一对应（均按小写、
    字面量比较；SQL 侧 like 已加 autoescape，``_``/``%`` 均为字面量），两侧
    口径必须同步修改并由回归测试保证一致。
    """
    if not domains:
        return None
    host_lower = (tracker_host or "").lower()
    url_lower = (tracker_url or "").lower()
    for domain in domains:
        domain_lower = (domain or "").lower()
        if not domain_lower:
            continue
        if (
            host_lower == domain_lower
            or host_lower.startswith(f"{domain_lower}:")
            or url_lower == domain_lower
            or url_lower.startswith(f"{domain_lower}/")
            or url_lower.startswith(f"{domain_lower}:")
            or url_lower.endswith(f"://{domain_lower}")
            or f"://{domain_lower}/" in url_lower
            or f"://{domain_lower}:" in url_lower
        ):
            return domain_lower
    return None


def convert_to_vo(torrent: torrentInfoModel) -> TorrentInfoVO:
    """将数据库模型转换为VO对象"""
    # 将datetime对象转换为时间戳
    added_timestamp = int(torrent.added_date.timestamp()) if torrent.added_date else None
    completed_timestamp = int(torrent.completed_date.timestamp()) if torrent.completed_date else None

    return TorrentInfoVO(
        info_id=torrent.info_id,
        downloader_id=torrent.downloader_id,
        downloader_name=torrent.downloader_name,
        torrent_id=torrent.torrent_id,
        hash=torrent.hash,
        name=torrent.name,
        save_path=torrent.save_path,
        size=int(torrent.size) if torrent.size is not None else None,
        status=torrent.status,
        error_reason=torrent.error_reason,
        has_tracker_error=torrent.has_tracker_error,
        torrent_file=torrent.torrent_file,
        auxiliary_seed_count=torrent.auxiliary_seed_count or 1,
        added_date=cast("datetime", added_timestamp) if added_timestamp is not None else None,
        completed_date=cast("datetime", completed_timestamp) if completed_timestamp is not None else None,
        ratio=torrent.ratio,
        ratio_limit=torrent.ratio_limit,
        tags=torrent.tags,
        category=torrent.category,
        super_seeding=torrent.super_seeding,
        enabled=torrent.enabled,
    )


def convert_to_vo_with_trackers(
    db: Session,
    torrent: torrentInfoModel,
    *,
    trackers: Optional[List[TrackerInfo]] = None,
    downloader_type: Optional[str] = None,
    tracker_keyword_map: Optional[Dict[str, str]] = None,
    requested_tracker_domains: Optional[List[str]] = None,
) -> TorrentInfoVO:
    """将数据库模型转换为VO对象，包含tracker信息"""
    prefetched_downloader_type = downloader_type
    # 保持datetime对象不变，让 Pydantic 序列化时自动转换为 ISO 8601 格式

    # 导入枚举类
    from app.enums.tracker_status import QBittorrentTrackerStatus, TransmissionTrackerStatus

    # 查询关联的tracker信息
    # 🔧 修复：使用 torrent.hash 查询 tracker，因为 tracker 表的 torrent_info_id 字段存储的是 hash
    if trackers is None:
        trackers = (
            db.query(TrackerInfo)
            .filter(
                TrackerInfo.torrent_info_id == torrent.info_id, TrackerInfo.dr == 0
            )  # 只查询未逻辑删除的tracker数据
            .all()
        )

    # 生成tracker_info数组（新结构）
    tracker_info_list = []

    # 生成原有字符串字段（保持向后兼容）
    tracker_names = []
    tracker_urls = []
    last_announce_succeededs = []
    last_announce_msgs = []
    last_scrape_succeededs = []

    # 确定下载器类型（用于状态映射）
    # 根据 downloader_id 查询下载器类型
    downloader_type = "qbittorrent"  # 默认为 qBittorrent
    downloader_type = prefetched_downloader_type or downloader_type
    try:
        from app.downloader.models import BtDownloaders

        downloader = (
            db.query(BtDownloaders.downloader_type).filter(BtDownloaders.downloader_id == torrent.downloader_id).first()
            if prefetched_downloader_type is None
            else None
        )
        if downloader:
            # 从 Row 对象中正确提取整数值
            # SQLAlchemy 查询单列返回 Row 对象，需要通过列名或索引访问
            if hasattr(downloader, "downloader_type"):
                # Row 对象：通过列名访问
                downloader_type_raw = downloader.downloader_type
            elif isinstance(downloader, (tuple, list)) and len(downloader) > 0:
                # 元组或列表：通过索引访问
                downloader_type_raw = downloader[0]
            else:
                # 其他情况：直接使用（兼容旧代码）
                downloader_type_raw = downloader
            # 使用统一的枚举类方法进行类型转换
            downloader_type_int = DownloaderTypeEnum.normalize(downloader_type_raw)
            downloader_type = DownloaderTypeEnum(downloader_type_int).to_name()
    except Exception as e:
        logger.warning(f"无法查询下载器类型，使用默认值 qBittorrent: {e}")

    for tracker in trackers:
        # 将数字状态转换为中文状态
        announce_status_raw = tracker.last_announce_succeeded
        scrape_status_raw = tracker.last_scrape_succeeded

        # 映射 announce 状态
        if announce_status_raw is not None:
            try:
                announce_status_int = int(announce_status_raw)
                if downloader_type == "qbittorrent":
                    announce_status_text = QBittorrentTrackerStatus.get_display_text(announce_status_int)
                else:  # transmission
                    announce_status_text = TransmissionTrackerStatus.get_display_text(announce_status_int)
            except (ValueError, TypeError):
                # 如果无法转换为整数，保持原样
                announce_status_text = str(announce_status_raw)
        else:
            announce_status_text = None

        # 展示对齐判定：Transmission 对「HTTP 200 + failure reason」上报成功
        # 布尔（落库状态码 2=工作中），但消息已被判定任务按失败池判错。按同一
        # 关键词口径覆写，避免显示"✓工作中"却命中 error 筛选（tracker_keyword_map
        # 为 None/空时不覆写，保持调用方旧语义）。
        if tracker_display_failed(
            announce_status_raw,
            tracker.last_announce_msg,
            tracker_keyword_map or {},
            downloader_type,
        ):
            announce_status_text = FAILED_DISPLAY_TEXT

        # 映射 scrape 状态
        if scrape_status_raw is not None:
            try:
                scrape_status_int = int(scrape_status_raw)
                if downloader_type == "qbittorrent":
                    scrape_status_text = QBittorrentTrackerStatus.get_display_text(scrape_status_int)
                else:  # transmission
                    scrape_status_text = TransmissionTrackerStatus.get_display_text(scrape_status_int)
            except (ValueError, TypeError):
                # 如果无法转换为整数，保持原样
                scrape_status_text = str(scrape_status_raw)
        else:
            scrape_status_text = None

        # scrape 列同口径独立覆写（只看 scrape 消息与 scrape 状态码）。
        if tracker_display_failed(
            scrape_status_raw,
            tracker.last_scrape_msg,
            tracker_keyword_map or {},
            downloader_type,
        ):
            scrape_status_text = FAILED_DISPLAY_TEXT

        # 构建tracker_info对象数组；requested_tracker_domains 非空时按同一口径
        # 标记命中筛选的 tracker 行（tracker_row_matches_domains 与 SQL 条件同口径）。
        tracker_vo = TrackerInfoVO(
            tracker_id=tracker.tracker_id,
            tracker_name=tracker.tracker_name,
            tracker_url=tracker.tracker_url,
            last_announce_succeeded=announce_status_text,  # 返回中文状态
            last_announce_msg=tracker.last_announce_msg,
            last_scrape_succeeded=scrape_status_text,  # 返回中文状态
            last_scrape_msg=tracker.last_scrape_msg,
            matched_domain=(
                tracker_row_matches_domains(tracker.tracker_host, tracker.tracker_url, requested_tracker_domains)
                if requested_tracker_domains
                else None
            ),
        )
        tracker_info_list.append(tracker_vo)

        # 构建原有字符串字段（保持向后兼容）
        tracker_names.append(tracker.tracker_name or "")
        tracker_urls.append(tracker.tracker_url or "")
        last_announce_succeededs.append(announce_status_text or "")
        last_announce_msgs.append(tracker.last_announce_msg or "")
        last_scrape_succeededs.append(scrape_status_text or "")

    # 将数组转换为以;分隔的字符串（保持向后兼容）
    tracker_name_str = ";".join(tracker_names) if tracker_names else ""
    tracker_url_str = ";".join(tracker_urls) if tracker_urls else ""
    last_announce_succeeded_str = ";".join(last_announce_succeededs) if last_announce_succeededs else ""
    last_announce_msg_str = ";".join(last_announce_msgs) if last_announce_msgs else ""
    last_scrape_succeeded_str = ";".join(last_scrape_succeededs) if last_scrape_succeededs else ""

    return TorrentInfoVO(
        info_id=torrent.info_id,
        downloader_id=torrent.downloader_id,
        downloader_name=torrent.downloader_name,
        torrent_id=torrent.torrent_id,
        hash=torrent.hash,
        name=torrent.name,
        save_path=torrent.save_path,
        size=int(torrent.size) if torrent.size is not None else None,
        status=torrent.status,
        error_reason=torrent.error_reason,
        has_tracker_error=torrent.has_tracker_error,
        progress=torrent.progress,
        torrent_file=torrent.torrent_file,
        auxiliary_seed_count=torrent.auxiliary_seed_count or 1,
        added_date=torrent.added_date,  # 保持 datetime 对象，让 Pydantic 自动序列化为 ISO 8601
        completed_date=torrent.completed_date,  # 保持 datetime 对象，让 Pydantic 自动序列化为 ISO 8601
        ratio=torrent.ratio,
        ratio_limit=torrent.ratio_limit,
        tags=torrent.tags,
        category=torrent.category,
        super_seeding=torrent.super_seeding,
        enabled=torrent.enabled,
        tracker_name=tracker_name_str,
        tracker_url=tracker_url_str,
        last_announce_succeeded=last_announce_succeeded_str,
        last_announce_msg=last_announce_msg_str,
        last_scrape_succeeded=last_scrape_succeeded_str,
        tracker_info=tracker_info_list,
    )


_RELATED_PREFETCH_BATCH_SIZE = 500


def _safe_related_prefetch_batch_size(db: Session, requested: int) -> int:
    """Honor a lowered SQLite bind limit while retaining the normal batch size."""
    if requested <= 0:
        raise ValueError("batch_size must be greater than zero")
    try:
        if db.get_bind().dialect.name != "sqlite":
            return requested
        connection_fairy = db.connection().connection
        driver_connection = getattr(connection_fairy, "driver_connection", connection_fairy)
        variable_limit = driver_connection.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)
        # Tracker queries also bind ``dr == 0``; reserve one variable for it.
        return min(requested, max(1, variable_limit - 1))
    except (AttributeError, TypeError, ValueError, sqlite3.Error):
        return requested


def convert_to_vos_with_trackers(
    db: Session,
    torrents: Sequence[torrentInfoModel],
    *,
    batch_size: Optional[int] = None,
    requested_tracker_domains: Optional[List[str]] = None,
) -> List[TorrentInfoVO]:
    """Convert torrent rows with bounded batched related-data prefetching."""
    torrent_list = list(torrents)
    if not torrent_list:
        return []

    # 每次列表转换只加载一次关键词池，供展示覆写与判定任务同口径。
    tracker_keyword_map = load_active_keyword_map(db)

    requested_batch_size = batch_size if batch_size is not None else _RELATED_PREFETCH_BATCH_SIZE
    effective_batch_size = _safe_related_prefetch_batch_size(db, requested_batch_size)

    tracker_map: Dict[str, List[TrackerInfo]] = {}
    info_ids = list(dict.fromkeys(str(torrent.info_id) for torrent in torrent_list if torrent.info_id is not None))
    for start in range(0, len(info_ids), effective_batch_size):
        info_id_batch = info_ids[start : start + effective_batch_size]
        trackers = (
            db.query(TrackerInfo)
            .filter(
                TrackerInfo.torrent_info_id.in_(info_id_batch),
                TrackerInfo.dr == 0,
            )
            .all()
        )
        for tracker in trackers:
            tracker_map.setdefault(str(tracker.torrent_info_id), []).append(tracker)

    from app.downloader.models import BtDownloaders

    downloader_type_map: Dict[str, str] = {}
    downloader_ids = list(
        dict.fromkeys(str(torrent.downloader_id) for torrent in torrent_list if torrent.downloader_id is not None)
    )
    try:
        for start in range(0, len(downloader_ids), effective_batch_size):
            downloader_id_batch = downloader_ids[start : start + effective_batch_size]
            rows = (
                db.query(
                    BtDownloaders.downloader_id,
                    BtDownloaders.downloader_type,
                )
                .filter(BtDownloaders.downloader_id.in_(downloader_id_batch))
                .all()
            )
            for row in rows:
                downloader_id = str(row.downloader_id)
                try:
                    downloader_type_int = DownloaderTypeEnum.normalize(row.downloader_type)
                    downloader_type_map[downloader_id] = DownloaderTypeEnum(downloader_type_int).to_name()
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "无法转换下载器 %s 的类型，使用 qBittorrent: %s",
                        downloader_id,
                        exc,
                    )
    except Exception as exc:
        # Preserve the legacy fallback when the downloader table is unavailable.
        logger.warning("批量查询下载器类型失败，使用 qBittorrent: %s", exc)

    return [
        convert_to_vo_with_trackers(
            db,
            torrent,
            trackers=tracker_map.get(str(torrent.info_id), []),
            downloader_type=downloader_type_map.get(str(torrent.downloader_id), "qbittorrent"),
            tracker_keyword_map=tracker_keyword_map,
            requested_tracker_domains=requested_tracker_domains,
        )
        for torrent in torrent_list
    ]
