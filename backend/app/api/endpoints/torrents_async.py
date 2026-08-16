"""
异步版本的种子数据库操作函数

用于定时任务的异步数据库操作，保持与同步版本的API兼容性。
所有函数使用 AsyncSessionLocal 进行异步数据库操作。

核心函数：
- get_torrent_by_hash_async: 通过哈希值获取种子信息
- update_torrent_async: 更新种子信息
- tr_add_torrents_async: Transmission种子同步
- qb_add_torrents_async: qBittorrent种子同步
- sync_add_tracker_async: Tracker信息同步
"""

import asyncio
import os
import uuid
import logging
import json
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Awaitable
from sqlalchemy.exc import OperationalError

from sqlalchemy import select, update, exists
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.exc import SQLAlchemyError

from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo as trackerInfoModel
from qbittorrentapi.exceptions import APIConnectionError, LoginFailed, APIError
from app.core.torrent_file_backup import TorrentFileBackupService
from app.core.path_mapping import PathMappingService
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.core.tracker_mapper import extract_tracker_host, resolve_transmission_tracker_status_code
from app.core.filename_utils import FilenameUtils
from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.services.sync_db_write import WriteStats, bulk_upsert_with_retry, has_torrent_info_changes
from app.services.torrent_metadata import fetch_qb_torrent_details
from app.services.torrent_ratio_values import (
    MISSING_RATIO_VALUE,
    RatioNormalizationStats,
    apply_normalized_ratio_fields,
)
from app.models.torrent_file_backup import TorrentFileBackup
from app.models.setting_templates import DownloaderTypeEnum
from app.core.config import settings

logger = logging.getLogger(__name__)

# 乐观锁最大重试次数
MAX_OPTIMISTIC_LOCK_RETRIES = 3


def _coerce_activity_ts(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(value, str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _safe_parse_timestamp(value: Any) -> Optional[int]:
    """
    安全地解析时间戳值，返回有效的 int 时间戳或 None。

    处理步骤：
    1. 处理 None 值
    2. 尝试将字符串转换为 int
    3. 确保解析的 int 在有效范围内（>0 且 <=2147483647，防止 Year 2038 问题）

    Args:
        value: 原始时间戳值（可能是 None、int、float 或 str）

    Returns:
        Optional[int]: 有效的时间戳 int，或 None（如果验证失败）
    """
    # 1. 处理 None 值
    if value is None:
        return None

    # 2. 尝试转换为 int（处理字符串、float 等类型）
    try:
        timestamp_int = int(value)
    except (TypeError, ValueError):
        return None

    # 3. 验证时间戳范围（>0 且 <=2147483647）
    if timestamp_int <= 0 or timestamp_int > 2147483647:
        return None

    return timestamp_int


def _resolve_legacy_backup_file_path(info_id: str, torrent_name: str) -> Optional[str]:
    backup_dir = os.environ.get("BACKUP_TORRENT_DIR", TorrentFileBackupService.DEFAULT_BACKUP_DIR)
    backup_filename = FilenameUtils.generate_backup_filename(info_id, torrent_name)
    candidate = FilenameUtils.safe_path_join(backup_dir, backup_filename)
    if os.path.exists(candidate):
        return candidate

    # fallback: older naming scheme may only use info_id.torrent
    fallback_filename = f"{info_id}.torrent"
    fallback_candidate = FilenameUtils.safe_path_join(backup_dir, fallback_filename)
    if os.path.exists(fallback_candidate):
        return fallback_candidate
    return None


async def _load_downloader_torrent_save_path(db: AsyncSession, downloader_id: str) -> Optional[str]:
    if not downloader_id:
        return None
    try:
        result = await db.execute(
            select(BtDownloaders.torrent_save_path).where(
                BtDownloaders.downloader_id == downloader_id, BtDownloaders.dr == 0
            )
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


# ==============================================================================
# 重试机制辅助函数
# ==============================================================================


async def _retry_on_db_lock(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 10.0,
    error_context: str = "数据库操作",
    rollback: Optional[Callable[[], Awaitable[None]]] = None,
):
    """
    在数据库锁定时重试操作（指数退避策略）

    Args:
        func: 要执行的异步函数
        max_retries: 最大重试次数（默认3次）
        base_delay: 基础延迟时间（秒，指数增长，默认10秒）
        error_context: 错误上下文描述

    Raises:
        Exception: 重试失败后抛出原始异常

    Example:
        await _retry_on_db_lock(
            lambda: db.execute(stmt),
            max_retries=3,
            error_context="批量插入种子"
        )
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return await func()
        except OperationalError as e:
            last_error = e
            # 检查是否是数据库锁定错误
            if "database is locked" in str(e) or "locked" in str(e).lower():
                if attempt < max_retries - 1:  # 不是最后一次尝试
                    if rollback is not None:
                        await rollback()
                    # 指数退避：10秒, 20秒, 40秒
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"{error_context}失败（数据库锁定），"
                        f"第{attempt + 1}/{max_retries}次重试，"
                        f"等待{delay:.1f}秒后重试..."
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"{error_context}失败：已达最大重试次数（{max_retries}次）")
                # 不是锁定错误，直接抛出
                raise
        except Exception:
            # 其他类型的错误，直接抛出
            raise

    # 所有重试都失败，抛出最后一次的错误
    if last_error:
        raise last_error


# ==============================================================================
# 基础 CRUD 异步函数
# ==============================================================================


async def get_torrent_by_hash_async(
    db: AsyncSession, hash_value: str, downloader_id: Optional[str] = None
) -> Optional[TorrentInfo]:
    """
    通过哈希值获取种子信息（异步版本）

    Args:
        db: 异步数据库会话
        hash_value: 种子哈希值
        downloader_id: 下载器ID（可选，用于限定查询范围）

    Returns:
        种子信息对象或None
    """
    filters = [TorrentInfo.hash == hash_value, TorrentInfo.dr == 0]  # 只查询未删除的记录

    # 如果提供了 downloader_id，则限定查询范围
    if downloader_id is not None:
        filters.append(TorrentInfo.downloader_id == downloader_id)

    result = await db.execute(select(TorrentInfo).filter(*filters))

    # 使用 first() 代替 scalar_one_or_none()，避免多行异常
    # 如果存在多条重复记录（历史遗留问题），返回第一条
    return result.scalars().first()


async def update_torrent_async(
    db: AsyncSession, torrent_id: str, torrent_data: Dict[str, Any], commit: bool = True
) -> Optional[TorrentInfo]:
    """
    更新种子信息（异步版本）

    Args:
        db: 异步数据库会话
        torrent_id: 种子ID
        torrent_data: 更新的种子数据

    Returns:
        更新后的种子信息对象或None（如果未找到）
    """
    # 查询种子
    result = await db.execute(select(TorrentInfo).filter(TorrentInfo.info_id == torrent_id))
    db_torrent = result.scalar_one_or_none()

    if not db_torrent:
        return None

    try:
        normalized_data = dict(torrent_data)
        apply_normalized_ratio_fields(
            normalized_data,
            raw_ratio=torrent_data.get("ratio", MISSING_RATIO_VALUE),
            raw_ratio_limit=torrent_data.get("ratio_limit", MISSING_RATIO_VALUE),
            is_insert=False,
        )
        # 更新对象属性
        for key, value in normalized_data.items():
            if hasattr(db_torrent, key):
                setattr(db_torrent, key, value)
        if commit:
            await db.commit()
            await db.refresh(db_torrent)
        return db_torrent
    except SQLAlchemyError as e:
        await db.rollback()
        raise e


# ==============================================================================
# Tracker 乐观锁异步函数
# ==============================================================================


async def update_tracker_with_optimistic_lock_async(
    db: AsyncSession, tracker_id: str, update_data: Dict[str, Any], max_retries: int = MAX_OPTIMISTIC_LOCK_RETRIES
) -> bool:
    """
    使用乐观锁更新 tracker 记录（异步版本）

    Args:
        db: 异步数据库会话
        tracker_id: tracker 主键
        update_data: 更新数据字典
        max_retries: 最大重试次数（默认3次）

    Returns:
        bool: 更新是否成功
    """
    for attempt in range(max_retries):
        try:
            # 读取当前记录
            result = await db.execute(
                select(trackerInfoModel).filter(trackerInfoModel.tracker_id == tracker_id, trackerInfoModel.dr == 0)
            )
            tracker = result.scalar_one_or_none()

            if tracker is None:
                logger.warning(f"乐观锁更新失败: tracker {tracker_id} 不存在或已删除")
                return False

            old_version = tracker.version

            # 创建新的数据字典副本，避免污染传入的参数
            final_update_data = update_data.copy()
            final_update_data["version"] = old_version + 1

            # 执行更新（带版本检查）
            from sqlalchemy import update

            update_stmt = (
                update(trackerInfoModel)
                .where(
                    trackerInfoModel.tracker_id == tracker_id,
                    trackerInfoModel.version == old_version,
                    trackerInfoModel.dr == 0,
                )
                .values(final_update_data)
            )
            result = await db.execute(update_stmt)

            if result.rowcount > 0:
                await db.commit()
                return True  # 更新成功
            elif attempt < max_retries - 1:
                await db.rollback()
                logger.info(f"乐观锁冲突，第 {attempt + 1} 次重试: tracker_id={tracker_id}")
                await asyncio.sleep(0.01 * (attempt + 1))  # 异步退避等待
                continue  # 重试
            else:
                logger.warning(f"乐观锁重试失败，已达到最大重试次数: tracker_id={tracker_id}")
                return False

        except Exception as e:
            logger.error(f"乐观锁更新异常: {e}, tracker_id={tracker_id}")
            await db.rollback()
            if attempt < max_retries - 1:
                await asyncio.sleep(0.01 * (attempt + 1))
                continue
            else:
                return False

    return False


async def restore_deleted_tracker_async(
    db: AsyncSession,
    torrent_info_id: str,
    tracker_url: str,
    tracker_data: Dict[str, Any],
    current_time: datetime,
    max_retries: int = MAX_OPTIMISTIC_LOCK_RETRIES,
) -> bool:
    """
    恢复已删除的 tracker 记录（dr: 1 -> 0）（异步版本）

    Args:
        db: 异步数据库会话
        torrent_info_id: 种子主键
        tracker_url: tracker URL
        tracker_data: 最新 tracker 数据
        current_time: 当前时间
        max_retries: 最大重试次数（默认3次）

    Returns:
        bool: 恢复是否成功
    """
    for attempt in range(max_retries):
        try:
            # 查找已删除的记录
            result = await db.execute(
                select(trackerInfoModel).filter(
                    trackerInfoModel.torrent_info_id == torrent_info_id,
                    trackerInfoModel.tracker_url == tracker_url,
                    trackerInfoModel.dr == 1,
                )
            )
            deleted_tracker = result.scalar_one_or_none()

            if deleted_tracker is None:
                return False

            # 恢复记录（保留 create_time/create_by，更新其他字段）
            # 使用 get() 并提供默认值，防止 None 写入数据库
            update_data = {
                "dr": 0,
                "tracker_name": tracker_data.get("tracker_name", deleted_tracker.tracker_name),
                "last_announce_succeeded": tracker_data.get("last_announce_succeeded", 0),
                "last_announce_msg": tracker_data.get("last_announce_msg", ""),
                "last_scrape_succeeded": tracker_data.get("last_scrape_succeeded", 0),
                "last_scrape_msg": tracker_data.get("last_scrape_msg", ""),
                "update_time": current_time,
                "update_by": "admin",
                "version": deleted_tracker.version + 1,
            }

            from sqlalchemy import update

            update_stmt = (
                update(trackerInfoModel)
                .where(
                    trackerInfoModel.tracker_id == deleted_tracker.tracker_id,
                    trackerInfoModel.version == deleted_tracker.version,
                    trackerInfoModel.dr == 1,
                )
                .values(update_data)
            )
            result = await db.execute(update_stmt)

            if result.rowcount > 0:
                await db.commit()
                logger.info(f"恢复已删除的 tracker: {tracker_url}")
                return True
            elif attempt < max_retries - 1:
                await db.rollback()
                logger.info(f"恢复 tracker 乐观锁冲突，第 {attempt + 1} 次重试: {tracker_url}")
                await asyncio.sleep(0.01 * (attempt + 1))
                continue
            else:
                logger.warning(f"恢复 tracker 失败（乐观锁重试耗尽）: {tracker_url}")
                return False

        except Exception as e:
            logger.error(f"恢复 tracker 异常: {e}, tracker_url={tracker_url}")
            await db.rollback()
            if attempt < max_retries - 1:
                await asyncio.sleep(0.01 * (attempt + 1))
                continue
            else:
                return False

    return False


async def mark_removed_trackers_async_batch(
    db: AsyncSession, torrent_info_id: str, current_tracker_urls: set, current_time: datetime
) -> None:
    """
    Batch mark removed trackers using a single UPDATE (async).
    """
    try:
        if not torrent_info_id or not isinstance(torrent_info_id, str):
            logger.error(f"Invalid torrent_info_id: {torrent_info_id}")
            return
        if not isinstance(current_time, datetime):
            logger.error(f"Invalid current_time type: {type(current_time)}")
            return
        if not current_tracker_urls:
            logger.warning("current_tracker_urls is empty, skip mark-removed trackers")
            return

        result = await db.execute(
            update(trackerInfoModel)
            .where(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.dr == 0,
                ~trackerInfoModel.tracker_url.in_(current_tracker_urls),
            )
            .values(dr=1, update_time=current_time, update_by="system")
        )

        removed_count = result.rowcount or 0
        if removed_count > 0:
            logger.info(f"Marked {removed_count} removed trackers")

    except Exception as e:
        logger.error(f"Mark removed trackers failed: {e}")
        await db.rollback()


async def mark_removed_trackers_async(
    db: AsyncSession, torrent_info_id: str, current_tracker_urls: set, current_time: datetime
) -> None:
    """
    标记已移除的 tracker 为逻辑删除（异步版本，保留用于向后兼容）

    注意：此函数使用乐观锁，已废弃。请使用 mark_removed_trackers_async_batch 替代。

    Args:
        db: 异步数据库会话
        torrent_info_id: 种子主键
        current_tracker_urls: 下载器中当前的 tracker URL 集合
        current_time: 当前时间
    """
    try:
        # 参数验证
        if not torrent_info_id or not isinstance(torrent_info_id, str):
            logger.error(f"无效的 torrent_info_id: {torrent_info_id}")
            return

        if not isinstance(current_time, datetime):
            logger.error(f"无效的 current_time 类型: {type(current_time)}")
            return

        # 防御性检查：如果 current_tracker_urls 为空，记录警告并跳过
        if not current_tracker_urls:
            logger.warning("current_tracker_urls 为空集合，跳过标记已移除 tracker 的操作")
            return

        # 查询所有活跃的 tracker
        result = await db.execute(
            select(trackerInfoModel).filter(
                trackerInfoModel.torrent_info_id == torrent_info_id, trackerInfoModel.dr == 0
            )
        )
        existing_trackers = result.scalars().all()

        removed_count = 0
        from sqlalchemy import update

        for existing_tracker in existing_trackers:
            if existing_tracker.tracker_url not in current_tracker_urls:
                # 使用乐观锁标记为删除
                update_data = {
                    "dr": 1,
                    "update_time": current_time,
                    "update_by": "system",
                    "version": existing_tracker.version + 1,
                }

                update_stmt = (
                    update(trackerInfoModel)
                    .where(
                        trackerInfoModel.tracker_id == existing_tracker.tracker_id,
                        trackerInfoModel.version == existing_tracker.version,
                        trackerInfoModel.dr == 0,
                    )
                    .values(update_data)
                )
                result = await db.execute(update_stmt)

                if result.rowcount > 0:
                    removed_count += 1
                    logger.info(f"标记已移除的 tracker: {existing_tracker.tracker_url}")
                else:
                    logger.warning(f"标记删除失败（乐观锁冲突）: {existing_tracker.tracker_url}")

        await db.commit()

        if removed_count > 0:
            logger.info(f"共标记 {removed_count} 个已移除的 tracker")

    except Exception as e:
        logger.error(f"标记已移除 tracker 异常: {e}")
        await db.rollback()


async def update_or_restore_tracker_with_retry_async(
    db: AsyncSession, torrent_info_id: str, tracker_url: str, tracker_data: Dict[str, Any], current_time: datetime
) -> bool:
    """
    更新或恢复 tracker 记录（带重试机制）（异步版本）

    逻辑：
    1. 查询是否存在 dr=0 的活跃记录
    2. 如果存在，使用乐观锁更新
    3. 如果不存在，查询是否存在 dr=1 的已删除记录
    4. 如果存在已删除记录，恢复它
    5. 如果都不存在，返回 False（需要添加新记录）

    Args:
        db: 异步数据库会话
        torrent_info_id: 种子主键
        tracker_url: tracker URL
        tracker_data: tracker 数据字典
        current_time: 当前时间

    Returns:
        bool: True 表示已处理（更新或恢复），False 表示需要添加新记录
    """
    try:
        # 参数验证
        if not torrent_info_id or not isinstance(torrent_info_id, str):
            logger.error(f"无效的 torrent_info_id: {torrent_info_id}")
            return False

        if not tracker_url or not isinstance(tracker_url, str):
            logger.error(f"无效的 tracker_url: {tracker_url}")
            return False

        if not isinstance(current_time, datetime):
            logger.error(f"无效的 current_time 类型: {type(current_time)}")
            return False

        if not isinstance(tracker_data, dict):
            logger.error(f"tracker_data 必须是字典类型: {type(tracker_data)}")
            return False

        # 步骤1：查询活跃记录（dr=0）
        result = await db.execute(
            select(trackerInfoModel).filter(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.tracker_url == tracker_url,
                trackerInfoModel.dr == 0,
            )
        )
        # 修复：使用 first() 代替 scalar_one_or_none()
        # 如果存在多条重复记录（历史遗留问题），取第一条
        active_tracker = result.scalars().first()

        if active_tracker is not None:
            # 准备更新数据（保留 create_time/create_by）
            # 修复P3-2: 明确区分"字段不存在"和"字段值为None"
            update_data = {
                "tracker_name": (
                    tracker_data.get("tracker_name")
                    if tracker_data.get("tracker_name") is not None
                    else active_tracker.tracker_name
                ),
                "last_announce_succeeded": (
                    tracker_data.get("last_announce_succeeded")
                    if tracker_data.get("last_announce_succeeded") is not None
                    else active_tracker.last_announce_succeeded
                ),
                "last_announce_msg": (
                    tracker_data.get("last_announce_msg")
                    if tracker_data.get("last_announce_msg") is not None
                    else active_tracker.last_announce_msg
                ),
                "last_scrape_succeeded": (
                    tracker_data.get("last_scrape_succeeded")
                    if tracker_data.get("last_scrape_succeeded") is not None
                    else active_tracker.last_scrape_succeeded
                ),
                "last_scrape_msg": (
                    tracker_data.get("last_scrape_msg")
                    if tracker_data.get("last_scrape_msg") is not None
                    else active_tracker.last_scrape_msg
                ),
                "update_time": current_time,
                "update_by": "admin",
            }

            # 使用乐观锁更新
            success = await update_tracker_with_optimistic_lock_async(db, active_tracker.tracker_id, update_data)

            if success:
                logger.debug(f"更新 tracker 成功: {tracker_url}")
            else:
                logger.warning(f"更新 tracker 失败（重试耗尽）: {tracker_url}")

            return True  # 已处理

        # 步骤2：查询已删除记录（dr=1）
        result = await db.execute(
            select(trackerInfoModel).filter(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.tracker_url == tracker_url,
                trackerInfoModel.dr == 1,
            )
        )
        # 修复：使用 first() 代替 scalar_one_or_none()
        deleted_tracker = result.scalars().first()

        if deleted_tracker is not None:
            # 恢复已删除的记录
            success = await restore_deleted_tracker_async(db, torrent_info_id, tracker_url, tracker_data, current_time)

            if success:
                logger.info(f"恢复 tracker 成功: {tracker_url}")
            else:
                logger.warning(f"恢复 tracker 失败: {tracker_url}")

            return True  # 已处理

        # 步骤3：都不存在，需要添加新记录
        return False

    except Exception as e:
        logger.error(f"update_or_restore_tracker_async 异常: {e}, tracker_url={tracker_url}")
        return False


def extract_tracker_rows_from_torrent(
    torrent_info: Any, torrent_info_id: str, downloader_type: str, current_time: Any
) -> tuple[list[dict], set]:
    """从单个种子的远程数据提取 tracker_rows（纯提取，不写库）。

    阶段 2.5：把 sync_add_tracker_async 内的提取逻辑抽成纯函数，供批量版复用。
    过滤 DHT/PeX/LSD，做字段映射。

    Args:
        torrent_info: 远程下载器返回的种子对象（含 trackers/tracker_stats）。
        torrent_info_id: 关联的 TorrentInfo 主键。
        downloader_type: 'qbittorrent' / 'transmission'。
        current_time: 时间戳（datetime）。

    Returns:
        (tracker_rows, current_tracker_urls)：rows 用于后续 upsert，urls 用于 mark_removed。
    """
    normalized = DownloaderTypeEnum.normalize(downloader_type)
    downloader_type = DownloaderTypeEnum(normalized).to_name()

    current_tracker_urls: set = set()
    tracker_rows: list[dict] = []

    if downloader_type == "qbittorrent":
        try:
            trackers_data = getattr(torrent_info, "trackers", None)
            if callable(trackers_data):
                trackers_data = trackers_data()
            trackers_data = trackers_data or []
        except Exception as e:
            logger.error(f"Failed to get qbittorrent trackers: {str(e)}")
            trackers_data = []

        for tracker in trackers_data:
            try:
                url = tracker.get("url")
                if not url:
                    continue
                url = str(url)
                if "DHT" in url or "PeX" in url or "LSD" in url:
                    continue
                current_tracker_urls.add(url)
                tracker_rows.append(
                    {
                        "tracker_id": str(uuid.uuid4()),
                        "torrent_info_id": torrent_info_id,
                        "tracker_name": url,
                        "tracker_url": url,
                        "tracker_host": extract_tracker_host(url),
                        "last_announce_succeeded": tracker.get("status"),
                        "last_announce_msg": tracker.get("msg"),
                        "last_scrape_succeeded": tracker.get("status"),
                        "last_scrape_msg": tracker.get("msg"),
                        "create_time": current_time,
                        "create_by": "admin",
                        "update_time": current_time,
                        "update_by": "admin",
                        "dr": 0,
                    }
                )
            except Exception as tracker_err:
                logger.error(f"Failed to process tracker [{tracker}]: {str(tracker_err)}")
                continue

    elif downloader_type == "transmission":
        tracker_stats = getattr(torrent_info, "tracker_stats", None) or []
        for tracker_status in tracker_stats:
            tracker_url = None
            try:
                tracker_url = tracker_status.fields.get("announce")
            except Exception:
                tracker_url = None
            if not tracker_url:
                continue
            current_tracker_urls.add(tracker_url)
            tracker_rows.append(
                {
                    "tracker_id": str(uuid.uuid4()),
                    "torrent_info_id": torrent_info_id,
                    "tracker_name": tracker_status.site_name,
                    "tracker_url": tracker_url,
                    "tracker_host": tracker_status.fields.get("host") or extract_tracker_host(tracker_url),
                    "last_announce_succeeded": resolve_transmission_tracker_status_code(tracker_status, "announce"),
                    "last_announce_msg": tracker_status.last_announce_result,
                    "last_scrape_succeeded": resolve_transmission_tracker_status_code(tracker_status, "scrape"),
                    "last_scrape_msg": tracker_status.last_scrape_result,
                    "create_time": current_time,
                    "create_by": "admin",
                    "update_time": current_time,
                    "update_by": "admin",
                    "dr": 0,
                }
            )
    else:
        logger.error(f"Unknown downloader type: '{downloader_type}'")

    return tracker_rows, current_tracker_urls


async def sync_trackers_batch_async(db: AsyncSession, accumulated_rows: list[dict], current_time: Any) -> dict:
    """批量写入 tracker_info（阶段 2.5 P0 核心）。

    与单种子版 sync_add_tracker_async 相比的改进：
    1. 批量 select 旧值（按 torrent_info_id IN (...) 一次性查）。
    2. has_tracker_changes 变更检测，无变化的行跳过 upsert。
    3. 多种子聚合后统一一次 upsert execute（而非每种子一次）。
    4. db_write_scope 串行化写者。
    5. mark_removed 严格按 (info_id, url) 元组语义，禁止扁平化 url 集合。

    严格四步顺序（顺序不可调换，审查1-C6）：
    Step1: 批量软删恢复（dr=1→0）
    Step2: 批量物理删除软删行（DELETE dr=1，避免 upsert 复活）
    Step3: 批量 upsert（变更检测后的行，on_conflict_do_update index_where dr=0）
    Step4: 批量 mark_removed（元组语义取反）

    Args:
        db: 异步数据库会话。
        accumulated_rows: 跨多个种子累计的 tracker_rows（每个 row 是 dict）。
        current_time: 时间戳。

    Returns:
        stats dict：{insert, update, skip, removed}。
    """
    from sqlalchemy import delete, tuple_, text as sa_text
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy import exists as sa_exists
    from app.services.sync_db_write import has_tracker_changes
    from app.tasks.resource_guard import admission_controller

    stats = {"insert": 0, "update": 0, "skip": 0, "removed": 0}
    if not accumulated_rows:
        return stats

    # 收集本批次涉及的 info_id 和 (info_id, url) pairs
    batch_info_ids = list({row["torrent_info_id"] for row in accumulated_rows})
    batch_pairs = {(row["torrent_info_id"], row["tracker_url"]) for row in accumulated_rows}

    # === 批量 select 旧值（变更检测基础）===
    existing_rows = await db.execute(
        select(
            trackerInfoModel.torrent_info_id,
            trackerInfoModel.tracker_url,
            trackerInfoModel.tracker_name,
            trackerInfoModel.tracker_host,
            trackerInfoModel.last_announce_succeeded,
            trackerInfoModel.last_announce_msg,
            trackerInfoModel.last_scrape_succeeded,
            trackerInfoModel.last_scrape_msg,
        )
        .where(trackerInfoModel.torrent_info_id.in_(batch_info_ids))
        .where(trackerInfoModel.dr == 0)
    )
    existing_map = {
        (row.torrent_info_id, row.tracker_url): {
            "tracker_name": row.tracker_name,
            "tracker_host": row.tracker_host,
            "last_announce_succeeded": row.last_announce_succeeded,
            "last_announce_msg": row.last_announce_msg,
            "last_scrape_succeeded": row.last_scrape_succeeded,
            "last_scrape_msg": row.last_scrape_msg,
        }
        for row in existing_rows.all()
    }

    # === 变更检测过滤 ===
    rows_to_upsert = []
    for row in accumulated_rows:
        key = (row["torrent_info_id"], row["tracker_url"])
        existing = existing_map.get(key, {})
        if has_tracker_changes(existing, row):
            rows_to_upsert.append(row)
        else:
            stats["skip"] += 1

    async with admission_controller.db_write_scope():
        # === Step 1: 批量软删恢复（dr=1→0，仅当 url 在 current 且无活跃行）===
        active_tracker = aliased(trackerInfoModel)
        await db.execute(
            update(trackerInfoModel)
            .where(
                trackerInfoModel.torrent_info_id.in_(batch_info_ids),
                trackerInfoModel.dr == 1,
                tuple_(trackerInfoModel.torrent_info_id, trackerInfoModel.tracker_url).in_(list(batch_pairs)),
                ~sa_exists().where(
                    active_tracker.torrent_info_id == trackerInfoModel.torrent_info_id,
                    active_tracker.tracker_url == trackerInfoModel.tracker_url,
                    active_tracker.dr == 0,
                ),
            )
            .values(dr=0, update_time=current_time, update_by="admin")
        )

        # === Step 2: 批量物理删除剩余的软删行（避免 upsert 复活）===
        await db.execute(
            delete(trackerInfoModel).where(
                trackerInfoModel.dr == 1,
                tuple_(trackerInfoModel.torrent_info_id, trackerInfoModel.tracker_url).in_(list(batch_pairs)),
            )
        )

        # === Step 3: 批量 upsert（仅变更检测后的行）===
        if rows_to_upsert:
            stmt = sqlite_insert(trackerInfoModel).values(rows_to_upsert)
            stmt = stmt.on_conflict_do_update(
                index_elements=["torrent_info_id", "tracker_url"],
                index_where=sa_text("dr = 0"),
                set_={
                    "tracker_name": stmt.excluded.tracker_name,
                    "tracker_host": stmt.excluded.tracker_host,
                    "last_announce_succeeded": stmt.excluded.last_announce_succeeded,
                    "last_announce_msg": stmt.excluded.last_announce_msg,
                    "last_scrape_succeeded": stmt.excluded.last_scrape_succeeded,
                    "last_scrape_msg": stmt.excluded.last_scrape_msg,
                    "update_time": current_time,
                    "update_by": "admin",
                },
            )
            await db.execute(stmt)

            # 统计 insert vs update（基于 existing_map）
            for row in rows_to_upsert:
                key = (row["torrent_info_id"], row["tracker_url"])
                if key in existing_map:
                    stats["update"] += 1
                else:
                    stats["insert"] += 1

        # === Step 4: 批量 mark_removed（严格元组语义，禁止扁平化 url）===
        # 把 db 里有但本批次没有的 (info_id, url) 标记 dr=1。
        # 关键：必须用元组 IN 而非 url NOT IN，避免跨种子误删（审查1-C6 必修2）。
        result = await db.execute(
            update(trackerInfoModel)
            .where(
                trackerInfoModel.torrent_info_id.in_(batch_info_ids),
                trackerInfoModel.dr == 0,
                ~tuple_(trackerInfoModel.torrent_info_id, trackerInfoModel.tracker_url).in_(list(batch_pairs)),
            )
            .values(dr=1, update_time=current_time, update_by="system")
        )
        stats["removed"] = result.rowcount or 0

        await db.commit()

    logger.info(
        f"[TRACKER_BATCH] info_ids={len(batch_info_ids)} upsert={len(rows_to_upsert)} "
        f"insert={stats['insert']} update={stats['update']} skip={stats['skip']} removed={stats['removed']}"
    )
    return stats


async def sync_add_tracker_async(
    db: AsyncSession, downloader_type: str, mode: str, torrent_info: Any, torrent_info_id: str
) -> None:
    """
    Sync tracker info with batch upsert and batch updates (async).
    """
    # 使用统一的枚举类方法进行类型标准化
    normalized_type = DownloaderTypeEnum.normalize(downloader_type)
    downloader_type = DownloaderTypeEnum(normalized_type).to_name()

    current_time = datetime.now()
    current_tracker_urls = set()
    tracker_rows = []
    tracker_source = getattr(torrent_info, "_tracker_source", None)
    torrent_hash = getattr(torrent_info, "hash", None) or getattr(torrent_info, "hashString", None)

    if downloader_type == "qbittorrent":
        try:
            trackers_data = getattr(torrent_info, "trackers", None)
            if callable(trackers_data):
                trackers_data = trackers_data()
            trackers_data = trackers_data or []
        except Exception as e:
            logger.error(f"Failed to get qbittorrent trackers: {str(e)}")
            trackers_data = []

        for tracker in trackers_data:
            try:
                url = tracker.get("url")
                if not url:
                    continue
                url = str(url)
                if "DHT" in url or "PeX" in url or "LSD" in url:
                    continue
                current_tracker_urls.add(url)
                tracker_rows.append(
                    {
                        "tracker_id": str(uuid.uuid4()),
                        "torrent_info_id": torrent_info_id,
                        "tracker_name": url,
                        "tracker_url": url,
                        "tracker_host": extract_tracker_host(url),
                        "last_announce_succeeded": tracker.get("status"),
                        "last_announce_msg": tracker.get("msg"),
                        "last_scrape_succeeded": tracker.get("status"),
                        "last_scrape_msg": tracker.get("msg"),
                        "create_time": current_time,
                        "create_by": "admin",
                        "update_time": current_time,
                        "update_by": "admin",
                        "dr": 0,
                    }
                )
            except Exception as tracker_err:
                logger.error(f"Failed to process tracker [{tracker}]: {str(tracker_err)}")
                continue

    elif downloader_type == "transmission":
        tracker_stats = getattr(torrent_info, "tracker_stats", None) or []
        for tracker_status in tracker_stats:
            tracker_url = None
            try:
                tracker_url = tracker_status.fields.get("announce")
            except Exception:
                tracker_url = None
            if not tracker_url:
                continue
            current_tracker_urls.add(tracker_url)
            tracker_rows.append(
                {
                    "tracker_id": str(uuid.uuid4()),
                    "torrent_info_id": torrent_info_id,
                    "tracker_name": tracker_status.site_name,
                    "tracker_url": tracker_url,
                    "tracker_host": tracker_status.fields.get("host") or extract_tracker_host(tracker_url),
                    "last_announce_succeeded": resolve_transmission_tracker_status_code(tracker_status, "announce"),
                    "last_announce_msg": tracker_status.last_announce_result,
                    "last_scrape_succeeded": resolve_transmission_tracker_status_code(tracker_status, "scrape"),
                    "last_scrape_msg": tracker_status.last_scrape_result,
                    "create_time": current_time,
                    "create_by": "admin",
                    "update_time": current_time,
                    "update_by": "admin",
                    "dr": 0,
                }
            )

    else:
        logger.error(f"Unknown downloader type: '{downloader_type}'")
        return

    if not current_tracker_urls:
        logger.warning(
            "Tracker sync skipped: empty current_tracker_urls. "
            f"downloader_type={downloader_type} mode={mode} "
            f"torrent_info_id={torrent_info_id} hash={torrent_hash} "
            f"source={tracker_source}"
        )

    if mode == "update" and current_tracker_urls:
        active_tracker = aliased(trackerInfoModel)
        await db.execute(
            update(trackerInfoModel)
            .where(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.tracker_url.in_(current_tracker_urls),
                trackerInfoModel.dr == 1,
                ~exists().where(
                    active_tracker.torrent_info_id == torrent_info_id,
                    active_tracker.tracker_url == trackerInfoModel.tracker_url,
                    active_tracker.dr == 0,
                ),
            )
            .values(dr=0, update_time=current_time, update_by="admin")
        )

    if tracker_rows:
        # Avoid resurrecting soft-deleted rows during upsert.
        from sqlalchemy import delete, tuple_

        # ✅ P1修复：添加row的None检查，避免AttributeError
        soft_deleted_pairs = {
            (row.get("torrent_info_id"), row.get("tracker_url"))
            for row in tracker_rows
            if row and isinstance(row, dict) and row.get("torrent_info_id") and row.get("tracker_url")
        }

        # ✅ P0修复：移除嵌套事务，由调用者统一管理事务边界
        # 问题：外层 torrent_sync_db_async 已经使用 async with AsyncSessionLocal() as db:
        #      如果这里再使用 async with db.begin() 会导致嵌套事务冲突
        # 解决：直接执行数据库操作，不创建新事务
        if soft_deleted_pairs or tracker_rows:
            # 防御性检查：确保 Session 在事务中
            if not db.in_transaction():
                logger.warning(
                    f"Session not in transaction; caller should manage transaction. "
                    f"torrent_info_id={torrent_info_id}, source={tracker_source}"
                )

            # 删除软删除记录，避免upsert时恢复
            if soft_deleted_pairs:
                await db.execute(
                    delete(trackerInfoModel).where(
                        trackerInfoModel.dr == 1,
                        tuple_(trackerInfoModel.torrent_info_id, trackerInfoModel.tracker_url).in_(
                            list(soft_deleted_pairs)
                        ),
                    )
                )

            # 插入新记录或更新现有记录
            # 使用 index_where 参数指定部分索引的WHERE条件（SQLAlchemy 2.0语法）
            from sqlalchemy import text as sa_text

            stmt = sqlite_insert(trackerInfoModel).values(tracker_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["torrent_info_id", "tracker_url"],
                index_where=sa_text("dr = 0"),  # 指定部分索引的WHERE条件
                set_={
                    "tracker_name": stmt.excluded.tracker_name,
                    "last_announce_succeeded": stmt.excluded.last_announce_succeeded,
                    "last_announce_msg": stmt.excluded.last_announce_msg,
                    "last_scrape_succeeded": stmt.excluded.last_scrape_succeeded,
                    "last_scrape_msg": stmt.excluded.last_scrape_msg,
                    "update_time": current_time,
                    "update_by": "admin",
                    "dr": 0,
                },
            )
            await db.execute(stmt)

    if mode == "update":
        await mark_removed_trackers_async_batch(db, torrent_info_id, current_tracker_urls, current_time)

    # ✅ 修复：移除 commit，由调用者统一管理事务
    # 原因：tr_add_torrents_async 已经在多个地方 commit，如果这里再 commit 会导致：
    # 1. 事务边界混乱
    # 2. Session 状态不一致
    # 3. 可能的 "A transaction is already begun" 错误
    # 解决：让 tr_add_torrents_async 在所有操作完成后统一 commit


def _deduplicate_torrent_lists(
    to_insert: List[Dict[str, Any]], to_update: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    去除待插入/更新列表中的重复 hash（双重保护机制）

    ✅ 修复：防止 API 返回重复数据或内部逻辑错误导致的重复 hash
    ⚠️ 注意：这是第二层保护，第一层是 BaseSyncTask 的下载器级别锁

    Args:
        to_insert: 待插入的种子列表
        to_update: 待更新的种子列表

    Returns:
        (去重后的插入列表, 去重后的更新列表)
    """
    seen_insert = {}  # {(downloader_id, hash): 'insert'}
    seen_update = {}  # {(downloader_id, hash): 'update'}
    deduped_insert = []
    deduped_update = []

    # 去重待插入列表
    for item in to_insert:
        key = (item.get("downloader_id"), item.get("hash"))
        if key not in seen_insert:
            seen_insert[key] = "insert"
            deduped_insert.append(item)
        else:
            logger.warning(
                f"[去重保护] 发现重复插入: {item.get('name')} "
                f"(hash={item.get('hash')}, downloader_id={item.get('downloader_id')})"
            )

    # 去重待更新列表
    for item in to_update:
        key = (item.get("downloader_id"), item.get("hash"))
        if key not in seen_update:
            seen_update[key] = "update"
            deduped_update.append(item)
        else:
            logger.warning(
                f"[去重保护] 发现重复更新: {item.get('name')} "
                f"(hash={item.get('hash')}, downloader_id={item.get('downloader_id')})"
            )

    # 检查插入和更新之间是否有冲突
    conflicts = []
    for key in seen_insert:
        if key in seen_update:
            conflicts.append(key)

    if conflicts:
        conflict_hashes = [str(h) for _, h in conflicts[:3]]
        conflict_preview = ", ".join(conflict_hashes)
        logger.warning(
            f"[去重保护] 发现插入与更新冲突: {len(conflicts)} 个 "
            f"(hash={conflict_preview}{'...' if len(conflicts) > 3 else ''})"
        )
        # 优先保留更新操作，移除插入操作
        deduped_insert = [
            item for item in deduped_insert if (item.get("downloader_id"), item.get("hash")) not in conflicts
        ]
        logger.info("[去重保护] 已保留更新操作，移除冲突的插入操作")

    if len(to_insert) != len(deduped_insert) or len(to_update) != len(deduped_update):
        logger.info(
            f"[去重保护] 去重完成: 插入 {len(to_insert)}→{len(deduped_insert)}, "
            f"更新 {len(to_update)}→{len(deduped_update)}"
        )

    return deduped_insert, deduped_update


async def tr_add_torrents_async(db: AsyncSession, downloaders: List[Any], *, client: Optional[Any] = None) -> None:
    """
    根据transmission的种子数据结构创建插入数据（异步版本）

    性能优化：
    - 批量查询：一次性获取该下载器的所有种子，避免 N+1 查询问题
    - 批量写入：收集所有变更后一次性执行 INSERT/UPDATE
    - 事务合并：从逐个提交改为一次性提交
    - 内存缓存：使用字典快速查找，O(1) 复杂度

    Args:
        db: 异步数据库会话
        downloaders: 下载器对象列表
        client: 来自 app.state.store 的已缓存 Transmission 客户端；缺失时拒绝执行。

    Raises:
        ValueError: 当下载器列表为空时
    """
    # 添加空列表检查，防止IndexError
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return None

    bt_downloader = downloaders[0]
    if client is None:
        raise ValueError(
            f"下载器 {getattr(bt_downloader, 'nickname', bt_downloader.downloader_id)} 缺少缓存客户端，"
            "拒绝在同步路径中自建 Transmission 连接"
        )
    tr_client = client
    downloader_id = str(bt_downloader.downloader_id)
    # 分批获取 Transmission 种子，避免超大响应导致超时
    # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
    base_torrents = await call_downloader_api(
        str(bt_downloader.downloader_id),
        DownloadLane.SYNC,
        tr_client.get_torrents,
        kwargs={"arguments": TR_BASE_FIELDS},
        operation="tr_get_torrents_base",
    )
    torrent_info_list = []
    total = len(base_torrents)

    # 非首次同步时，仅同步最近活跃的种子（降低数据量）
    now_ts = datetime.now().timestamp()
    last_full_ts = _TR_LAST_FULL_SYNC.get(downloader_id, 0)
    force_full_sync = (now_ts - last_full_ts) >= TR_FULL_SYNC_INTERVAL_SECONDS

    if _TR_FULL_SYNC_DONE.get(downloader_id) and not force_full_sync:
        now_ts = datetime.now().timestamp()
        recent_threshold = now_ts - TR_ACTIVE_WINDOW_SECONDS
        active_torrents = []
        for t in base_torrents:
            activity_date = getattr(t, "activity_date", None)
            if activity_date is None and hasattr(t, "activityDate"):
                activity_date = getattr(t, "activityDate", None)
            activity_ts = _coerce_activity_ts(activity_date)
            if activity_ts is None:
                logger.warning(
                    "[TR_INFO] activity_date parse failed; treating as active. "
                    f"value={activity_date!r} type={type(activity_date).__name__} "
                    f"id={getattr(t, 'id', None)} hash={getattr(t, 'hashString', None)}"
                )
                active_torrents.append(t)
                continue
            if activity_ts >= recent_threshold:
                active_torrents.append(t)
        base_torrents = active_torrents
        total = len(base_torrents)

    if total > 0:
        for i in range(0, total, TR_BATCH_SIZE):
            batch = base_torrents[i : i + TR_BATCH_SIZE]
            batch_ids = [t.id for t in batch if hasattr(t, "id")]
            if not batch_ids:
                continue
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            detailed_batch = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                tr_client.get_torrents,
                kwargs={"ids": batch_ids, "arguments": TR_DETAIL_FIELDS},
                operation="tr_get_torrents_detail",
            )
            torrent_info_list.extend(detailed_batch)

    # 标记已完成首次全量同步
    current_time = datetime.now()

    # 初始化备份服务和路径映射服务
    path_mapping_service = None
    if bt_downloader.path_mapping:
        try:
            path_mapping_service = PathMappingService(bt_downloader.path_mapping)
            logger.debug(f"加载路径映射服务成功: {bt_downloader.nickname}")
        except Exception as e:
            logger.warning(f"加载路径映射服务失败: {e}")

    backup_service = TorrentFileBackupService(path_mapping_service=path_mapping_service)

    # ⚡ 性能优化1：批量查询所有已存在的种子
    logger.debug(f"[PERF] 开始批量查询下载器 {bt_downloader.nickname} 的所有种子...")
    batch_query_start = datetime.now()

    result = await db.execute(
        select(
            TorrentInfo.hash,
            TorrentInfo.info_id,
            TorrentInfo.create_time,
            TorrentInfo.progress,
            TorrentInfo.backup_file_path,
            TorrentInfo.downloader_name,  # ✅ 添加：保存原始的 downloader_name
        )
        .filter(TorrentInfo.downloader_id == bt_downloader.downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    existing_torrents_rows = result.all()

    # 构建内存字典：{hash: (info_id, create_time, progress, backup_file_path, downloader_name)}
    existing_torrents_cache = {
        row.hash: (row.info_id, row.create_time, row.progress, row.backup_file_path, row.downloader_name)
        for row in existing_torrents_rows
    }

    batch_query_duration = (datetime.now() - batch_query_start).total_seconds()
    logger.debug(
        f"[PERF] 批量查询完成：查询 {len(existing_torrents_cache)} 个种子，" f"耗时 {batch_query_duration:.3f} 秒"
    )

    # ⚡ 性能优化2：收集所有变更数据（不立即执行数据库操作）
    to_insert = []
    to_update = []
    torrent_info_map = {}

    stats = {"insert_count": 0, "update_count": 0, "skip_count": 0, "error_count": 0}
    ratio_stats = RatioNormalizationStats()

    # 第一阶段：收集数据
    tracker_source = "tr_detailed"
    for torrent_info in torrent_info_list:
        try:
            setattr(torrent_info, "_tracker_source", tracker_source)
        except Exception:
            pass
        cached_data = existing_torrents_cache.get(torrent_info.hashString)

        # 计算进度值
        raw_percent_done = (
            getattr(torrent_info, "percent_done", None) if hasattr(torrent_info, "percent_done") else None
        )
        if raw_percent_done is None:
            new_progress = 0.0
        else:
            try:
                new_progress = float(raw_percent_done) * 100.0
            except (TypeError, ValueError):
                new_progress = 0.0
            new_progress = _normalize_progress_value(new_progress)

        if cached_data is None:
            mode = "insert"
            stats["insert_count"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            update_time = current_time
            progress_value = new_progress
            backup_file_path = None
            cached_downloader_name = None  # ✅ 新增：缓存中没有 downloader_name
        else:
            mode = "update"
            stats["update_count"] += 1
            # ✅ 修复：解包时包含 downloader_name（保持复合主键一致性）
            torrent_info_id, create_time, old_progress_cached, backup_file_path, cached_downloader_name = cached_data

            if create_time is None:
                create_time = current_time
            update_time = current_time

            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats["skip_count"] += 1
                logger.debug(f"进度未变化: {torrent_info.name}, 保留旧值 {old_progress:.2f}%")
            else:
                progress_value = new_progress
                logger.debug(f"进度更新: {torrent_info.name}, {old_progress:.2f}% → {new_progress:.2f}%")

        # 构建种子数据字典
        # ✅ 修复：使用数据库中的原始 downloader_name，避免复合主键不匹配
        # 对于新插入的记录，使用当前的 nickname；对于更新的记录，使用数据库中的原始值
        downloader_name_to_use = cached_downloader_name if cached_downloader_name else bt_downloader.nickname

        torrent_data = {
            "info_id": torrent_info_id,
            "downloader_id": bt_downloader.downloader_id,
            "downloader_name": downloader_name_to_use,  # ✅ 使用原始值保持主键一致
            "torrent_id": torrent_info.id,
            "hash": torrent_info.hashString,
            "name": torrent_info.name,
            "status": TorrentStatusMapper.resolve_transmission_status(torrent_info.status, torrent_info.error),
            "error_reason": TorrentStatusMapper.extract_transmission_error_reason(torrent_info),
            "save_path": torrent_info.download_dir,
            "size": torrent_info.total_size,
            "progress": progress_value,
            "torrent_file": torrent_info.torrent_file,
            "added_date": torrent_info.added_date,
            "completed_date": torrent_info.done_date if torrent_info.done_date else None,
            "tags": ",".join(torrent_info.labels) if hasattr(torrent_info, "labels") and torrent_info.labels else "",
            "category": "",
            "super_seeding": "",
            "enabled": 1,
            "create_time": create_time,
            "create_by": "admin",
            "update_time": update_time,
            "update_by": "admin",
            "backup_file_path": backup_file_path,
            "dr": 0,
        }
        ratio_stats.observe(
            apply_normalized_ratio_fields(
                torrent_data,
                raw_ratio=getattr(torrent_info, "ratio", MISSING_RATIO_VALUE),
                raw_ratio_limit=getattr(torrent_info, "seed_ratio_limit", MISSING_RATIO_VALUE),
                is_insert=mode == "insert",
            )
        )

        # 收集数据
        if mode == "insert":
            to_insert.append(torrent_data)
        else:
            to_update.append(torrent_data)

        # 保存映射关系
        torrent_info_map[torrent_info_id] = {
            "mode": mode,
            "torrent_info": torrent_info,
            "backup_file_path": backup_file_path,
            "torrent_data": torrent_data,
        }

    ratio_stats.log_summary(
        logger,
        context=f"transmission-full:{bt_downloader.downloader_id}",
    )

    # ✅ 第二阶段预处理：去重保护（双重保护机制）
    logger.debug(f"[PERF] 开始去重检查：插入 {len(to_insert)} 个，更新 {len(to_update)} 个...")
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    # 第三阶段：批量执行数据库操作（分批提交，释放锁）
    logger.debug(f"[PERF] 开始批量写入：插入 {len(to_insert)} 个，更新 {len(to_update)} 个...")

    try:
        # ✅ W2-1 写路径收编：自建 500/批 + _retry_on_db_lock 的 _bulk_write_with_retry
        # 迁移到统一 bulk_upsert_with_retry（真实分批提交 + db_write_scope 串行化
        # 写者 + 批级重试；batch_size/重试参数走配置 SYNC_DB_COMMIT_BATCH_SIZE /
        # SYNC_DB_LOCK_RETRY_COUNT），消除旁路写者（P0-01/P0-06）。
        write_stats = await bulk_upsert_with_retry(
            db,
            to_insert,
            to_update,
            model=TorrentInfo,
            label=f"full-sync:{bt_downloader.downloader_id}",
        )
        logger.info(
            f"[{bt_downloader.nickname}] 批量写入成功：插入 {len(to_insert)} 个，"
            f"更新 {len(to_update)} 个（{write_stats.batches} 批提交，{write_stats.retries} 次重试）"
        )

    except Exception as e:
        await db.rollback()
        stats["error_count"] = len(to_insert) + len(to_update)
        error_msg = f"[{bt_downloader.nickname}] 批量写入失败: {str(e)}"
        logger.error(error_msg)

        # ✅ 关键修复：抛出异常，让调用方知道失败
        raise Exception(error_msg) from e

    # ✅ 方案2关键优化：批量写入完成后立即提交外层事务，释放数据库锁
    # 目的：避免在后续的 tracker 同步和备份操作期间持有锁，导致其他下载器同步等待超时
    # 效果：允许其他下载器同步任务立即读取到最新数据，避免"database is locked"错误
    logger.debug("[PERF] 批量写入完成，立即提交外层事务以释放数据库锁...")
    await db.commit()

    # 第三阶段：处理 tracker 同步和备份（独立事务，避免长时间持有锁）
    logger.debug("[PERF] 开始处理 tracker 同步和备份...")
    tracker_backup_start = datetime.now()

    # 收集需要更新的 backup_file_path，最后批量更新
    backup_updates = []

    for torrent_info_id, info in torrent_info_map.items():
        mode = info["mode"]
        torrent_info = info["torrent_info"]
        backup_file_path = info["backup_file_path"]

        try:
            # 🔧 统一类型转换，支持整数和字符串两种格式
            # 数据库存储：0=qBittorrent, 1=Transmission
            # API 字符串：'qbittorrent', 'transmission'
            original_type = bt_downloader.downloader_type
            downloader_type_str = None

            if original_type == "qbittorrent" or original_type == 0 or original_type == "0":
                downloader_type_str = "qbittorrent"
            elif original_type == "transmission" or original_type == 1 or original_type == "1":
                downloader_type_str = "transmission"

            if not downloader_type_str:
                logger.error(f"不支持的下载器类型: {original_type}")
                continue

            # Tracker 同步（使用独立事务）
            await sync_add_tracker_async(db, downloader_type_str, mode, torrent_info, torrent_info_id)

            if not backup_file_path:
                legacy_path = _resolve_legacy_backup_file_path(torrent_info_id, torrent_info.name)
                if legacy_path:
                    backup_file_path = legacy_path
                    backup_updates.append(
                        {"info_id": torrent_info_id, "backup_file_path": legacy_path, "name": torrent_info.name}
                    )

            # 备份种子文件（IO操作，不占用数据库锁）
            if not bt_downloader.torrent_save_path or not bt_downloader.torrent_save_path.strip():
                db_save_path = await _load_downloader_torrent_save_path(db, bt_downloader.downloader_id)
                if db_save_path and db_save_path.strip():
                    bt_downloader.torrent_save_path = db_save_path
                else:
                    continue
            if not bt_downloader.torrent_save_path or not bt_downloader.torrent_save_path.strip():
                continue

            already_backed_up = False
            if backup_file_path and os.path.exists(backup_file_path):
                already_backed_up = True
                logger.debug(f"种子已备份，跳过备份: {torrent_info.name}")

            if not already_backed_up:
                try:
                    backup_result = await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        backup_service.backup_torrent_file,
                        kwargs={
                            "info_id": torrent_info_id,
                            "torrent_hash": torrent_info.hashString,
                            "torrent_name": torrent_info.name,
                            "downloader_type": "transmission",
                            "save_path": torrent_info.download_dir,
                            "downloader_config": {
                                "host": bt_downloader.host,
                                "port": bt_downloader.port,
                                "username": bt_downloader.username,
                                "password": bt_downloader.password,
                                "torrent_file_path": torrent_info.torrent_file,
                                "torrent_save_path": bt_downloader.torrent_save_path,
                            },
                        },
                        operation="tr_backup_torrent_file",
                    )

                    if backup_result["success"]:
                        # ✅ 收集更新，稍后批量处理，避免循环内提交
                        backup_updates.append(
                            {
                                "info_id": torrent_info_id,
                                "backup_file_path": backup_result["backup_file_path"],
                                "name": torrent_info.name,
                            }
                        )

                        # ✅ 集成：同时记录到 torrent_file_backup 表
                        try:
                            # 检查是否已存在相同 info_hash + downloader_id 的记录
                            existing_backup = await db.execute(
                                select(TorrentFileBackup).filter(
                                    TorrentFileBackup.info_hash == torrent_info.hashString,
                                    TorrentFileBackup.downloader_id == bt_downloader.downloader_id,
                                    TorrentFileBackup.is_deleted.is_(False),
                                )
                            )
                            existing_record = existing_backup.scalar_one_or_none()

                            if not existing_record:
                                # 不存在则插入新记录
                                backup_manager = TorrentFileBackupManagerService(db=db)
                                await backup_manager.repository.create(
                                    info_hash=torrent_info.hashString,
                                    file_path=backup_result["backup_file_path"],
                                    file_size=None,  # 可选：如果需要文件大小可以获取
                                    task_name=torrent_info.name,
                                    uploader_id=1,  # 默认管理员ID
                                    downloader_id=bt_downloader.downloader_id,
                                    upload_time=datetime.now(),
                                )
                                await db.commit()
                                logger.info(
                                    f"记录种子备份到数据库: {torrent_info.name} (hash: {torrent_info.hashString[:8]}...)"
                                )
                            else:
                                logger.debug(
                                    f"种子备份记录已存在，跳过: {torrent_info.name} (hash: {torrent_info.hashString[:8]}...)"
                                )
                        except Exception as record_err:
                            # 只记录警告，不影响同步流程
                            logger.warning(
                                f"记录种子备份到数据库失败（不影响同步）: {torrent_info.name}, 错误: {record_err}"
                            )

                except Exception as backup_err:
                    logger.warning(f"种子文件备份异常: {torrent_info.name}, 错误: {backup_err}")

            # ✅ 新增：自动补录历史种子备份记录（无论是否刚刚备份过）
            try:
                # 检查是否已存在相同 info_hash + downloader_id 的记录
                existing_backup = await db.execute(
                    select(TorrentFileBackup).filter(
                        TorrentFileBackup.info_hash == torrent_info.hashString,
                        TorrentFileBackup.downloader_id == bt_downloader.downloader_id,
                        TorrentFileBackup.is_deleted.is_(False),
                    )
                )
                existing_record = existing_backup.scalar_one_or_none()

                if not existing_record and backup_file_path and os.path.exists(backup_file_path):
                    # 获取文件大小
                    file_size = os.path.getsize(backup_file_path)
                    max_size = 10 * 1024 * 1024  # 10MB

                    if file_size > max_size:
                        logger.warning(
                            f"种子文件过大，跳过补录: {torrent_info.name}, "
                            f"文件大小: {file_size / 1024 / 1024:.2f}MB (限制: 10MB)"
                        )
                        # 补录历史数据
                        backup_manager = TorrentFileBackupManagerService(db=db)
                        await backup_manager.repository.create(
                            info_hash=torrent_info.hashString,
                            file_path=backup_file_path,
                            file_size=file_size,
                            task_name=torrent_info.name,
                            uploader_id=1,  # 默认管理员ID
                            downloader_id=bt_downloader.downloader_id,
                            upload_time=info["torrent_data"]["create_time"],  # 使用种子创建时间
                        )
                        await db.commit()
                        logger.info(
                            f"✅ 补录历史种子备份记录: {torrent_info.name} "
                            f"(hash: {torrent_info.hashString[:8]}..., 大小: {file_size / 1024:.2f}KB)"
                        )
                elif existing_record:
                    logger.debug(
                        f"种子备份记录已存在，无需补录: {torrent_info.name} (hash: {torrent_info.hashString[:8]}...)"
                    )

            except Exception as backfill_err:
                # 只记录警告，不影响同步流程
                logger.warning(f"补录历史种子备份失败（不影响同步）: {torrent_info.name}, 错误: {backfill_err}")

        except Exception as e:
            stats["error_count"] += 1
            logger.error(f"处理种子 {torrent_info.name} 时出错: {str(e)}")

    # 批量更新 backup_file_path（一次性提交）
    if backup_updates:
        try:
            for update_data in backup_updates:
                await update_torrent_async(
                    db, update_data["info_id"], {"backup_file_path": update_data["backup_file_path"]}, commit=False
                )
            await db.commit()
            logger.debug(f"批量更新 {len(backup_updates)} 个 backup_file_path 成功")
        except Exception as e:
            logger.error(f"批量更新 backup_file_path 失败: {str(e)}")
            await db.rollback()

    tracker_backup_duration = (datetime.now() - tracker_backup_start).total_seconds()
    logger.debug(f"[PERF] Tracker 同步和备份完成，耗时 {tracker_backup_duration:.3f} 秒")

    # 输出统计信息
    logger.debug(
        f"[PERF] 同步统计："
        f"插入 {stats['insert_count']} 个，"
        f"更新 {stats['update_count']} 个，"
        f"跳过 {stats['skip_count']} 个，"
        f"错误 {stats['error_count']} 个"
    )

    # ✅ 关键修复：提交tracker数据的修改
    # 原因：sync_add_tracker_async中执行的tracker插入/更新操作需要在函数结束前commit
    # 问题：类似于 qb_add_torrents_async，tracker操作在新事务中，但函数结束时未commit
    # 影响：不提交会导致所有 tracker 数据丢失
    try:
        await db.commit()
        logger.info(
            f"[{bt_downloader.nickname}] ✅ Tracker数据批量提交成功（包括 {len(torrent_info_map)} 个种子的tracker信息）"
        )
        logger.debug("[TRACKER_FIX] Transmission Tracker数据批量提交成功")
    except Exception as tracker_commit_err:
        logger.error(f"[{bt_downloader.nickname}] ❌ Tracker数据提交失败: {str(tracker_commit_err)}")
        logger.error(f"[TRACKER_FIX] Transmission Tracker数据提交失败: {str(tracker_commit_err)}")
        await db.rollback()
    else:
        _TR_FULL_SYNC_DONE[downloader_id] = True
        if force_full_sync:
            _TR_LAST_FULL_SYNC[downloader_id] = now_ts


# ==============================================================================
# qBittorrent 种子同步（优化版本）
# ==============================================================================


async def qb_add_torrents_async(db: AsyncSession, downloaders: List[Any], *, client: Optional[Any] = None) -> None:
    """
    根据qbittorrent的种子数据结构创建插入数据（异步版本）

    性能优化：
    - 批量查询：一次性获取该下载器的所有种子，避免 N+1 查询问题
    - 批量写入：收集所有变更后一次性执行 INSERT/UPDATE
    - 事务合并：从逐个提交改为一次性提交
    - 内存缓存：使用字典快速查找，O(1) 复杂度

    Args:
        db: 异步数据库会话
        downloaders: 下载器对象列表
        client: 来自 app.state.store 的已缓存 qBittorrent 客户端；缺失时拒绝执行。

    Raises:
        ValueError: 当下载器列表为空时
    """
    # 添加空列表检查，防止IndexError
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    if client is None:
        raise ValueError(
            f"下载器 {getattr(bt_downloader, 'nickname', bt_downloader.downloader_id)} 缺少缓存客户端，"
            "拒绝在同步路径中自建 qBittorrent 连接"
        )

    downloader_id = str(bt_downloader.downloader_id)
    torrent_info_list = []
    incremental_failed = False
    force_full_sync = False
    pending_rid: Optional[int] = None
    used_sync_maindata = False

    # 周期性全量同步（避免长期只做增量导致数据过期）
    now_ts = datetime.now().timestamp()
    last_full_ts = _QB_LAST_FULL_SYNC.get(downloader_id, 0)
    if now_ts - last_full_ts >= QB_FULL_SYNC_INTERVAL_SECONDS:
        force_full_sync = True

    # qBittorrent 增量同步（使用 sync/maindata 的 rid）
    if QB_USE_INCREMENTAL_SYNC and not force_full_sync:
        last_rid = _QB_SYNC_RID_CACHE.get(downloader_id)
        try:
            if last_rid is None:
                # 首次同步：获取全量 + rid
                # ✅ 通过 downloader_api_runtime 在 sync_lane 专用 executor 调用，避免默认线程池挤占
                sync_data = await call_downloader_api(
                    downloader_id,
                    DownloadLane.SYNC,
                    client.sync_maindata,
                    kwargs={"rid": 0},
                    operation="sync_maindata_init",
                )
                new_rid = int(sync_data.get("rid", 0))
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                used_sync_maindata = True
                if torrent_info_list:
                    await _enrich_qb_torrents_with_trackers(client, torrent_info_list, downloader_id)
                pending_rid = new_rid
                logger.info(
                    f"[QB_SYNC] first full sync: downloader_id={downloader_id}, "
                    f"rid={new_rid}, torrents={len(torrent_info_list)}"
                )
            else:
                # 增量同步：只获取变化的种子
                # ✅ 通过 downloader_api_runtime 在 sync_lane 专用 executor 调用，避免默认线程池挤占
                sync_data = await call_downloader_api(
                    downloader_id,
                    DownloadLane.SYNC,
                    client.sync_maindata,
                    kwargs={"rid": last_rid},
                    operation="sync_maindata_incremental",
                )
                new_rid = int(sync_data.get("rid", last_rid))

                # 处理删除的种子
                removed = sync_data.get("torrents_removed", []) or []
                if removed:
                    await _mark_qb_removed_torrents(db, bt_downloader.downloader_id, removed)

                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                used_sync_maindata = True
                if torrent_info_list:
                    torrent_info_list = await _hydrate_qb_incremental_torrents(
                        client,
                        torrent_info_list,
                        downloader_id,
                        "qb_sync_incremental_details",
                    )
                    await _enrich_qb_torrents_with_trackers(client, torrent_info_list, downloader_id)
                pending_rid = new_rid
                logger.info(
                    f"[QB_SYNC] incremental: downloader_id={downloader_id}, "
                    f"rid={last_rid}->{new_rid}, changed={len(torrent_info_list)}, "
                    f"removed={len(removed)}"
                )
        except APIConnectionError as e:
            # 连接异常：重试后失败再降级
            retry_success = False
            retry_error: Optional[Exception] = None
            for attempt in range(1, 4):
                await asyncio.sleep(2 ** (attempt - 1))
                try:
                    # ✅ 通过 downloader_api_runtime 在 sync_lane 专用 executor 调用，避免默认线程池挤占
                    sync_data = await call_downloader_api(
                        downloader_id,
                        DownloadLane.SYNC,
                        client.sync_maindata,
                        kwargs={"rid": last_rid or 0},
                        operation="sync_maindata_retry",
                    )
                    new_rid = int(sync_data.get("rid", last_rid or 0))
                    removed = sync_data.get("torrents_removed", []) or []
                    if removed:
                        await _mark_qb_removed_torrents(db, bt_downloader.downloader_id, removed)
                    torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                    used_sync_maindata = True
                    if torrent_info_list:
                        if last_rid is not None:
                            torrent_info_list = await _hydrate_qb_incremental_torrents(
                                client,
                                torrent_info_list,
                                downloader_id,
                                "qb_sync_retry_incremental_details",
                            )
                        await _enrich_qb_torrents_with_trackers(client, torrent_info_list, downloader_id)
                    pending_rid = new_rid
                    retry_success = True
                    logger.info(
                        f"[QB_SYNC] retry success: downloader_id={downloader_id}, "
                        f"rid={last_rid}->{new_rid}, changed={len(torrent_info_list)}, "
                        f"removed={len(removed)}"
                    )
                    break
                except APIConnectionError as retry_connection_error:
                    retry_error = retry_connection_error
                    continue
                except LoginFailed:
                    raise
                except Exception as retry_attempt_error:
                    retry_error = retry_attempt_error
                    break
            if not retry_success:
                pending_rid = None
                incremental_failed = True
                logger.error(
                    "[QB_SYNC] retry failed, fallback to batch full sync: %s",
                    retry_error or e,
                )
        except LoginFailed as e:
            logger.error(f"[QB_SYNC] auth failed, abort: {e}")
            raise
        except APIError as e:
            pending_rid = None
            incremental_failed = True
            logger.warning(f"[QB_SYNC] api error, fallback to batch full sync: {e}")
        except Exception as e:
            pending_rid = None
            incremental_failed = True
            logger.warning(f"[QB_SYNC] incremental failed, fallback to batch full sync: {e}")

    # 兜底：分批全量同步，避免单次超大响应
    if force_full_sync or (not QB_USE_INCREMENTAL_SYNC) or incremental_failed:
        # 降级时丢弃任何未完整水合的 delta，只写入全量快照。
        torrent_info_list = []
        offset = 0
        while True:
            # ✅ 通过 downloader_api_runtime 在 sync_lane 专用 executor 调用
            batch = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                client.torrents_info,
                kwargs={
                    "limit": QB_BATCH_SIZE,
                    "offset": offset,
                    "include_trackers": True,
                },
                operation="qb_torrents_info_full_sync",
            )
            if not batch:
                break
            torrent_info_list.extend(batch)
            if len(batch) < QB_BATCH_SIZE:
                break
            offset += QB_BATCH_SIZE
        _QB_LAST_FULL_SYNC[downloader_id] = now_ts
        used_sync_maindata = False
    current_time = datetime.now()

    # 初始化备份服务和路径映射服务
    path_mapping_service = None
    if bt_downloader.path_mapping:
        try:
            path_mapping_service = PathMappingService(bt_downloader.path_mapping)
            logger.debug(f"加载路径映射服务成功: {bt_downloader.nickname}")
        except Exception as e:
            logger.warning(f"加载路径映射服务失败: {e}")

    backup_service = TorrentFileBackupService(path_mapping_service=path_mapping_service)

    # ⚡ 性能优化1：批量查询所有已存在的种子
    logger.debug(f"[PERF] 开始批量查询下载器 {bt_downloader.nickname} 的所有种子...")
    batch_query_start = datetime.now()

    result = await db.execute(
        select(
            TorrentInfo.hash,
            TorrentInfo.info_id,
            TorrentInfo.create_time,
            TorrentInfo.progress,
            TorrentInfo.backup_file_path,
            TorrentInfo.downloader_name,  # ✅ 添加：保存原始的 downloader_name
        )
        .filter(TorrentInfo.downloader_id == bt_downloader.downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    existing_torrents_rows = result.all()

    # 构建内存字典：{hash: (info_id, create_time, progress, backup_file_path, downloader_name)}
    existing_torrents_cache = {
        row.hash: (row.info_id, row.create_time, row.progress, row.backup_file_path, row.downloader_name)
        for row in existing_torrents_rows
    }

    batch_query_duration = (datetime.now() - batch_query_start).total_seconds()
    logger.debug(
        f"[PERF] 批量查询完成：查询 {len(existing_torrents_cache)} 个种子，" f"耗时 {batch_query_duration:.3f} 秒"
    )

    # ⚡ 性能优化2：收集所有变更数据（不立即执行数据库操作）
    to_insert = []  # 待插入的种子数据列表
    to_update = []  # 待更新的种子数据列表
    torrent_info_map = {}  # {info_id: torrent_info} 用于后续处理

    stats = {"insert_count": 0, "update_count": 0, "skip_count": 0, "error_count": 0}
    ratio_stats = RatioNormalizationStats()

    # 第一阶段：收集数据
    tracker_source = "qb_sync_maindata" if used_sync_maindata else "qb_torrents_info"
    for torrent_info in torrent_info_list:
        try:
            setattr(torrent_info, "_tracker_source", tracker_source)
        except Exception:
            pass
        # 使用内存字典查找
        torrent_hash = _qb_get_attr(torrent_info, "hash")
        if not torrent_hash:
            stats["error_count"] += 1
            logger.warning("跳过无hash的qBittorrent种子记录")
            continue
        cached_data = existing_torrents_cache.get(torrent_hash)

        # 计算进度值
        raw_progress = _qb_get_attr(torrent_info, "progress", None)
        if raw_progress is None:
            new_progress = 0.0
        else:
            try:
                progress_value_raw = float(raw_progress)
                if progress_value_raw <= 1.0:
                    scaled_progress = progress_value_raw * 100.0
                elif progress_value_raw > 1000.0:
                    scaled_progress = progress_value_raw / 100.0
                else:
                    scaled_progress = progress_value_raw
                new_progress = _normalize_progress_value(scaled_progress)
            except (TypeError, ValueError):
                new_progress = 0.0

        if cached_data is None:
            # 新种子：插入
            mode = "insert"
            stats["insert_count"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            update_time = current_time
            progress_value = new_progress
            backup_file_path = None
            cached_downloader_name = None  # ✅ 添加：新种子没有缓存的 downloader_name
        else:
            # 已存在种子：更新
            mode = "update"
            stats["update_count"] += 1
            # ✅ 修复：解包时包含 downloader_name（与 Transmission 保持一致）
            torrent_info_id, create_time, old_progress_cached, backup_file_path, cached_downloader_name = cached_data

            if create_time is None:
                create_time = current_time
            update_time = current_time

            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats["skip_count"] += 1
                logger.debug(f"进度未变化: {torrent_info.name}, 保留旧值 {old_progress:.2f}%")
            else:
                progress_value = new_progress
                logger.debug(f"进度更新: {torrent_info.name}, {old_progress:.2f}% → {new_progress:.2f}%")

        # ✅ 修复：使用数据库中的原始 downloader_name，避免复合主键不匹配
        # 对于新插入的记录，使用当前的 nickname；对于更新的记录，使用数据库中的原始值
        downloader_name_to_use = cached_downloader_name if cached_downloader_name else bt_downloader.nickname

        # 构建种子数据字典
        torrent_data = {
            "info_id": torrent_info_id,
            "downloader_id": bt_downloader.downloader_id,
            "downloader_name": downloader_name_to_use,  # ✅ 使用原始值保持主键一致
            "torrent_id": torrent_hash,
            "hash": torrent_hash,
            "name": _qb_get_attr(torrent_info, "name", ""),
            "status": TorrentStatusMapper.convert_qbittorrent_status(_qb_get_attr(torrent_info, "state", "")),
            "save_path": _qb_get_attr(torrent_info, "save_path", ""),
            "size": _qb_get_attr(torrent_info, "total_size", None) or _qb_get_attr(torrent_info, "size", 0),
            "progress": progress_value,
            "torrent_file": "/config/qbittorrent/BT_backup/" + torrent_hash + ".torrent",
            # 使用安全的时间戳解析函数，处理 None、字符串和范围验证
            "added_date": (
                datetime.fromtimestamp(_safe_parse_timestamp(_qb_get_attr(torrent_info, "added_on", 0)))
                if _safe_parse_timestamp(_qb_get_attr(torrent_info, "added_on", 0)) is not None
                else None
            ),
            "completed_date": (
                datetime.fromtimestamp(_safe_parse_timestamp(_qb_get_attr(torrent_info, "completion_on", 0)))
                if _safe_parse_timestamp(_qb_get_attr(torrent_info, "completion_on", 0)) is not None
                else None
            ),
            "tags": _qb_get_attr(torrent_info, "tags", ""),
            "category": _qb_get_attr(torrent_info, "category", ""),
            "super_seeding": _qb_get_attr(torrent_info, "super_seeding", False),
            "enabled": 1,
            "create_time": create_time,
            "create_by": "admin",
            "update_time": update_time,
            "update_by": "admin",
            "backup_file_path": backup_file_path,
            "dr": 0,
        }
        ratio_stats.observe(
            apply_normalized_ratio_fields(
                torrent_data,
                raw_ratio=_qb_get_attr(torrent_info, "ratio", MISSING_RATIO_VALUE),
                raw_ratio_limit=_qb_get_attr(torrent_info, "ratio_limit", MISSING_RATIO_VALUE),
                is_insert=mode == "insert",
            )
        )

        # 收集数据
        if mode == "insert":
            to_insert.append(torrent_data)
        else:  # mode == "update"
            to_update.append(torrent_data)

        # 保存映射关系，用于后续处理
        torrent_info_map[torrent_info_id] = {
            "mode": mode,
            "torrent_info": torrent_info,
            "backup_file_path": backup_file_path,
            "torrent_data": torrent_data,
        }

    ratio_stats.log_summary(
        logger,
        context=f"qbittorrent-full:{bt_downloader.downloader_id}",
    )

    # ✅ 第二阶段预处理：去重保护（双重保护机制）
    logger.debug(f"[PERF] 开始去重检查：插入 {len(to_insert)} 个，更新 {len(to_update)} 个...")
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    # 第三阶段：批量执行数据库操作（分批提交，释放锁）
    logger.debug(f"[PERF] 开始批量写入：插入 {len(to_insert)} 个，更新 {len(to_update)} 个...")

    try:
        # ✅ W2-1 写路径收编：自建 500/批 + _retry_on_db_lock 的 _bulk_write_with_retry
        # 迁移到统一 bulk_upsert_with_retry（真实分批提交 + db_write_scope 串行化
        # 写者 + 批级重试；batch_size/重试参数走配置 SYNC_DB_COMMIT_BATCH_SIZE /
        # SYNC_DB_LOCK_RETRY_COUNT），消除旁路写者（P0-01/P0-06）。
        write_stats = await bulk_upsert_with_retry(
            db,
            to_insert,
            to_update,
            model=TorrentInfo,
            label=f"full-sync:{bt_downloader.downloader_id}",
        )
        logger.info(
            f"[{bt_downloader.nickname}] 批量写入成功：插入 {len(to_insert)} 个，"
            f"更新 {len(to_update)} 个（{write_stats.batches} 批提交，{write_stats.retries} 次重试）"
        )

    except Exception as e:
        await db.rollback()
        stats["error_count"] = len(to_insert) + len(to_update)
        error_msg = f"[{bt_downloader.nickname}] 批量写入失败: {str(e)}"
        logger.error(error_msg)

        # ✅ 关键修复：抛出异常，让调用方知道失败
        raise Exception(error_msg) from e

    # ✅ 方案2关键优化：批量写入完成后立即提交外层事务，释放数据库锁
    # 目的：避免在后续的 tracker 同步和备份操作期间持有锁，导致其他下载器同步等待超时
    # 效果：允许其他下载器同步任务立即读取到最新数据，避免"database is locked"错误
    logger.debug("[PERF] 批量写入完成，立即提交外层事务以释放数据库锁...")
    await db.commit()
    if pending_rid is not None:
        _confirm_qb_sync_rid(downloader_id, pending_rid)

    # 第三阶段：处理 tracker 同步和备份（独立事务，避免长时间持有锁）
    logger.debug("[PERF] 开始处理 tracker 同步和备份...")
    tracker_backup_start = datetime.now()

    # 收集需要更新的 backup_file_path，最后批量更新
    backup_updates = []

    for torrent_info_id, info in torrent_info_map.items():
        mode = info["mode"]
        torrent_info = info["torrent_info"]
        backup_file_path = info["backup_file_path"]

        try:
            # 🔧 统一类型转换，支持整数和字符串两种格式
            # 数据库存储：0=qBittorrent, 1=Transmission
            # API 字符串：'qbittorrent', 'transmission'
            original_type = bt_downloader.downloader_type
            downloader_type_str = None

            if original_type == "qbittorrent" or original_type == 0 or original_type == "0":
                downloader_type_str = "qbittorrent"
            elif original_type == "transmission" or original_type == 1 or original_type == "1":
                downloader_type_str = "transmission"

            if not downloader_type_str:
                logger.error(f"不支持的下载器类型: {original_type}")
                continue

            # Tracker 同步（使用独立事务）
            await sync_add_tracker_async(db, downloader_type_str, mode, torrent_info, torrent_info_id)

            if not backup_file_path:
                legacy_path = _resolve_legacy_backup_file_path(torrent_info_id, torrent_info.name)
                if legacy_path:
                    backup_file_path = legacy_path
                    backup_updates.append(
                        {"info_id": torrent_info_id, "backup_file_path": legacy_path, "name": torrent_info.name}
                    )

            # 备份种子文件（IO操作，不占用数据库锁）
            if not bt_downloader.torrent_save_path or not bt_downloader.torrent_save_path.strip():
                db_save_path = await _load_downloader_torrent_save_path(db, bt_downloader.downloader_id)
                if db_save_path and db_save_path.strip():
                    bt_downloader.torrent_save_path = db_save_path
                else:
                    continue
            if not bt_downloader.torrent_save_path or not bt_downloader.torrent_save_path.strip():
                continue

            already_backed_up = False
            if backup_file_path and os.path.exists(backup_file_path):
                already_backed_up = True
                logger.debug(f"种子已备份，跳过备份: {torrent_info.name}")

            if not already_backed_up:
                try:
                    backup_result = await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        backup_service.backup_torrent_file,
                        kwargs={
                            "info_id": torrent_info_id,
                            "torrent_hash": torrent_info.hash,
                            "torrent_name": torrent_info.name,
                            "downloader_type": "qbittorrent",
                            "save_path": torrent_info.save_path,
                            "downloader_config": {
                                "host": bt_downloader.host,
                                "port": bt_downloader.port,
                                "username": bt_downloader.username,
                                "password": bt_downloader.password,
                                "torrent_save_path": bt_downloader.torrent_save_path,
                            },
                        },
                        operation="qb_backup_torrent_file",
                    )

                    if backup_result["success"]:
                        # ✅ 收集更新，稍后批量处理，避免循环内提交
                        backup_updates.append(
                            {
                                "info_id": torrent_info_id,
                                "backup_file_path": backup_result["backup_file_path"],
                                "name": torrent_info.name,
                            }
                        )

                        # ✅ 集成：同时记录到 torrent_file_backup 表
                        try:
                            # 检查是否已存在相同 info_hash + downloader_id 的记录
                            existing_backup = await db.execute(
                                select(TorrentFileBackup).filter(
                                    TorrentFileBackup.info_hash == torrent_info.hash,
                                    TorrentFileBackup.downloader_id == bt_downloader.downloader_id,
                                    TorrentFileBackup.is_deleted.is_(False),
                                )
                            )
                            existing_record = existing_backup.scalar_one_or_none()

                            if not existing_record:
                                # 不存在则插入新记录
                                backup_manager = TorrentFileBackupManagerService(db=db)
                                await backup_manager.repository.create(
                                    info_hash=torrent_info.hash,
                                    file_path=backup_result["backup_file_path"],
                                    file_size=None,  # 可选：如果需要文件大小可以获取
                                    task_name=torrent_info.name,
                                    uploader_id=1,  # 默认管理员ID
                                    downloader_id=bt_downloader.downloader_id,
                                    upload_time=datetime.now(),
                                )
                                await db.commit()
                                logger.info(
                                    f"记录种子备份到数据库: {torrent_info.name} (hash: {torrent_info.hash[:8]}...)"
                                )
                            else:
                                logger.debug(
                                    f"种子备份记录已存在，跳过: {torrent_info.name} (hash: {torrent_info.hash[:8]}...)"
                                )
                        except Exception as record_err:
                            # 只记录警告，不影响同步流程
                            logger.warning(
                                f"记录种子备份到数据库失败（不影响同步）: {torrent_info.name}, 错误: {record_err}"
                            )

                except Exception as backup_err:
                    logger.warning(f"种子文件备份异常: {torrent_info.name}, 错误: {backup_err}")

            # ✅ 新增：自动补录历史种子备份记录（无论是否刚刚备份过）
            try:
                # 检查是否已存在相同 info_hash + downloader_id 的记录
                existing_backup = await db.execute(
                    select(TorrentFileBackup).filter(
                        TorrentFileBackup.info_hash == torrent_info.hash,
                        TorrentFileBackup.downloader_id == bt_downloader.downloader_id,
                        TorrentFileBackup.is_deleted.is_(False),
                    )
                )
                existing_record = existing_backup.scalar_one_or_none()

                if not existing_record and backup_file_path and os.path.exists(backup_file_path):
                    # 获取文件大小
                    file_size = os.path.getsize(backup_file_path)
                    max_size = 10 * 1024 * 1024  # 10MB

                    if file_size > max_size:
                        logger.warning(
                            f"种子文件过大，跳过补录: {torrent_info.name}, "
                            f"文件大小: {file_size / 1024 / 1024:.2f}MB (限制: 10MB)"
                        )
                        # 补录历史数据
                        backup_manager = TorrentFileBackupManagerService(db=db)
                        await backup_manager.repository.create(
                            info_hash=torrent_info.hash,
                            file_path=backup_file_path,
                            file_size=file_size,
                            task_name=torrent_info.name,
                            uploader_id=1,  # 默认管理员ID
                            downloader_id=bt_downloader.downloader_id,
                            upload_time=info["torrent_data"]["create_time"],  # 使用种子创建时间
                        )
                        await db.commit()
                        logger.info(
                            f"✅ 补录历史种子备份记录: {torrent_info.name} "
                            f"(hash: {torrent_info.hash[:8]}..., 大小: {file_size / 1024:.2f}KB)"
                        )
                elif existing_record:
                    logger.debug(
                        f"种子备份记录已存在，无需补录: {torrent_info.name} (hash: {torrent_info.hash[:8]}...)"
                    )

            except Exception as backfill_err:
                # 只记录警告，不影响同步流程
                logger.warning(f"补录历史种子备份失败（不影响同步）: {torrent_info.name}, 错误: {backfill_err}")

        except Exception as e:
            stats["error_count"] += 1
            logger.error(f"处理种子 {torrent_info.name} 时出错: {str(e)}")

    # 批量更新 backup_file_path（一次性提交）
    if backup_updates:
        try:
            for update_data in backup_updates:
                await update_torrent_async(
                    db, update_data["info_id"], {"backup_file_path": update_data["backup_file_path"]}, commit=False
                )
            await db.commit()
            logger.debug(f"批量更新 {len(backup_updates)} 个 backup_file_path 成功")
        except Exception as e:
            logger.error(f"批量更新 backup_file_path 失败: {str(e)}")
            await db.rollback()

    # ✅ 关键修复：提交tracker数据的修改
    # 原因：sync_add_tracker_async中执行的tracker插入/更新操作需要在函数结束前commit
    # 问题：第1679行commit种子信息后，tracker操作在新事务中，但函数结束时未commit
    try:
        await db.commit()
        logger.info(
            f"[{bt_downloader.nickname}] ✅ Tracker数据批量提交成功（包括 {len(torrent_info_map)} 个种子的tracker信息）"
        )
        logger.debug("[TRACKER_FIX] Tracker数据批量提交成功")
    except Exception as tracker_commit_err:
        logger.error(f"[{bt_downloader.nickname}] ❌ Tracker数据提交失败: {str(tracker_commit_err)}")
        logger.error(f"[TRACKER_FIX] Tracker数据提交失败: {str(tracker_commit_err)}")
        await db.rollback()
    tracker_backup_duration = (datetime.now() - tracker_backup_start).total_seconds()
    logger.debug(f"[PERF] Tracker 同步和备份完成，耗时 {tracker_backup_duration:.3f} 秒")

    # 输出统计信息
    logger.debug(
        f"[PERF] 同步统计："
        f"插入 {stats['insert_count']} 个，"
        f"更新 {stats['update_count']} 个，"
        f"跳过 {stats['skip_count']} 个，"
        f"错误 {stats['error_count']} 个"
    )


# ==============================================================================
# 辅助函数（不需要异步化，纯计算）
# ==============================================================================


def _normalize_progress_value(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return 0.0
    if value_float < 0.0:
        return 0.0
    if value_float > 100.0:
        return 100.0
    return value_float


def convert_transmission_status(transmission_status: str) -> str:
    """
    将Transmission状态转换为通用状态

    注意：此函数保留以向后兼容，建议直接使用 TorrentStatusMapper.convert_transmission_status()
    """
    return TorrentStatusMapper.convert_transmission_status(transmission_status)


# ==============================================================================
# 同步配置（支持环境变量）
# ==============================================================================
QB_BATCH_SIZE = int(os.getenv("QB_BATCH_SIZE", "500"))
TR_BATCH_SIZE = int(os.getenv("TR_BATCH_SIZE", "1000"))
QB_USE_INCREMENTAL_SYNC = os.getenv("QB_USE_INCREMENTAL_SYNC", "true").lower() == "true"
QB_API_TIMEOUT = int(os.getenv("QB_API_TIMEOUT", "60"))
TR_API_TIMEOUT = int(os.getenv("TR_API_TIMEOUT", "60"))
TR_ACTIVE_WINDOW_SECONDS = int(os.getenv("TR_ACTIVE_WINDOW_SECONDS", "43200"))  # 默认12小时（覆盖静种）
QB_FULL_SYNC_INTERVAL_SECONDS = int(os.getenv("QB_FULL_SYNC_INTERVAL_SECONDS", "43200"))
TR_FULL_SYNC_INTERVAL_SECONDS = int(os.getenv("TR_FULL_SYNC_INTERVAL_SECONDS", "43200"))
TR_BASE_FIELDS = [
    "id",
    "hashString",
    "name",
    "status",
    "activityDate",
    "trackerStats",
    "error",
    "errorString",
]
TR_DETAIL_FIELDS = [
    "id",
    "hashString",
    "name",
    "status",
    "activityDate",
    "trackerStats",
    "error",
    "errorString",
    "percentDone",
    "downloadDir",
    "totalSize",
    "torrentFile",
    "addedDate",
    "doneDate",
    "uploadRatio",
    "seedRatioLimit",
    "labels",
]

# qbittorrent 增量同步状态（文件持久化 + 进程内缓存）
_QB_RID_LOCK = threading.Lock()
_QB_SYNC_RID_CACHE: Dict[str, int] = {}
_QB_RID_CACHE_FILE = None


def _get_qb_rid_cache_file() -> Path:
    """获取 QB rid 持久化文件路径"""
    global _QB_RID_CACHE_FILE
    if _QB_RID_CACHE_FILE is None:
        from app.core.config import settings

        _QB_RID_CACHE_FILE = settings.CONFIG_PATH / "qb_rid_cache.json"
    return _QB_RID_CACHE_FILE


def _load_qb_rid_cache() -> Dict[str, int]:
    cache_file = _get_qb_rid_cache_file()
    if not cache_file.exists():
        return {}
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}


def _save_qb_rid_cache(cache: Dict[str, int]) -> None:
    cache_file = _get_qb_rid_cache_file()
    try:
        cache_file.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        # 持久化失败不影响主流程
        pass


def _confirm_qb_sync_rid(downloader_id: str, rid: int) -> None:
    """Confirm a qB sync RID only after its torrent data is durably written."""
    with _QB_RID_LOCK:
        _QB_SYNC_RID_CACHE[downloader_id] = rid
        _save_qb_rid_cache(_QB_SYNC_RID_CACHE)


# 初始化缓存
_QB_SYNC_RID_CACHE = _load_qb_rid_cache()

# Transmission 首次全量同步标记（进程内）
_TR_FULL_SYNC_DONE: Dict[str, bool] = {}
_QB_LAST_FULL_SYNC: Dict[str, float] = {}
_TR_LAST_FULL_SYNC: Dict[str, float] = {}


def _qb_dict_to_objects(torrents_dict: Dict[str, Dict[str, Any]]) -> List[Any]:
    """将 qbittorrent sync/maindata 的 torrents 字典转换为对象列表"""
    torrents = []
    for torrent_hash, data in torrents_dict.items():
        if not isinstance(data, dict):
            continue
        payload = data.copy()
        payload.setdefault("hash", torrent_hash)
        torrents.append(SimpleNamespace(**payload))
    return torrents


def _qb_get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """兼容 qbittorrent 返回对象与字典的字段访问"""
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _qb_set_attr(obj: Any, key: str, value: Any) -> None:
    """在 qB 返回对象/字典上记录内部同步标记。

    qBittorrent API 返回值在不同版本中可能是普通对象或字典。标记仅用于
    区分“本轮远端请求已成功返回（即使 tracker 列表为空）”与“尚未处理/请求失败”，
    从而保证持久化游标不会越过未成功处理的 hash。
    """
    if isinstance(obj, dict):
        obj[key] = value
        return
    try:
        setattr(obj, key, value)
    except Exception:  # noqa: BLE001 - SDK 对象可能禁止动态属性
        logger.debug("无法在 qB 种子对象上记录同步标记: key=%s", key)


async def _hydrate_qb_incremental_torrents(
    client: Any, torrent_info_list: List[Any], downloader_id: str, operation: str, strict: bool = True
) -> List[Any]:
    """Replace partial sync/maindata deltas with complete torrent detail rows.

    Args:
        strict: True（默认）时缺失 hash 抛 RuntimeError（增量语义：防丢变化行）；
            False 时缺失仅记 warning 并保留 maindata 原行（首轮 rid=0 全量快照
            水合用：maindata 之后、torrents/info 之前被删除/失败批次的 hash
            不应让整轮失败降级重拉）。
    """
    requested_hashes: List[str] = []
    for torrent in torrent_info_list:
        torrent_hash = str(_qb_get_attr(torrent, "hash") or "").strip().lower()
        if not torrent_hash:
            raise RuntimeError("qB incremental delta contains a torrent without hash")
        requested_hashes.append(torrent_hash)

    details = await fetch_qb_torrent_details(
        client,
        downloader_id,
        requested_hashes,
        lane=DownloadLane.SYNC,
        operation=operation,
    )
    details_by_hash = {
        str(_qb_get_attr(torrent, "hash") or "").strip().lower(): torrent
        for torrent in details
        if _qb_get_attr(torrent, "hash")
    }
    missing_hashes = sorted(set(requested_hashes) - details_by_hash.keys())
    if missing_hashes:
        if strict:
            preview = ", ".join(missing_hashes[:5])
            raise RuntimeError(
                f"qB incremental detail hydration was incomplete ({len(missing_hashes)} missing: {preview})"
            )
        logger.warning(
            f"qB hydration: {len(missing_hashes)} hashes missing from detail fetch, "
            f"keeping maindata rows (lenient mode)"
        )

    # Preserve sync/maindata order and cardinality while replacing every delta row.
    # Lenient mode 保留缺失 hash 的 maindata 原行，避免快照行数收缩。
    if strict:
        return [details_by_hash[torrent_hash] for torrent_hash in requested_hashes]
    return [
        details_by_hash.get(torrent_hash, torrent_info_list[idx]) for idx, torrent_hash in enumerate(requested_hashes)
    ]


def _parse_qb_tracker_cursor(cursor_value: Optional[str]) -> Optional[str]:
    """解析 qB tracker 续跑游标 JSON，返回 last_hash（W3-1 第二部分）。

    透明字符串格式：{"last_hash": "<hash>"}，存 sync_checkpoints.cursor_value。
    损坏/非 dict/缺 key 一律按无游标处理（从头开始，安全侧：宁可重做不遗漏）。
    """
    if not cursor_value:
        return None
    try:
        data = json.loads(cursor_value)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    last_hash = data.get("last_hash")
    return str(last_hash) if last_hash else None


def _build_qb_tracker_cursor(last_hash: str) -> str:
    """构造 qB tracker 续跑游标 JSON（last_hash = 最后 durable 批的最后 hash）。"""
    return json.dumps({"last_hash": last_hash}, ensure_ascii=False)


def _qb_tracker_cycle_meta(
    partial: bool,
    cursor: Optional[str],
    cycle_complete: bool,
    processed: int,
    total: int,
    budget_reason: Optional[str],
) -> Dict[str, Any]:
    """tracker 续跑/周期观测元数据（W3-1 第二部分）。

    只新增观测 key，不影响既有 status/message/tracker_count/torrent_count 契约。
    """
    return {
        "partial": partial,
        "cursor": cursor,
        "cycle_complete": cycle_complete,
        "cycle_progress": {"processed": processed, "total": total},
        "budget_reason": budget_reason,
    }


async def _enrich_qb_torrents_with_trackers(
    client: Any,
    torrent_info_list: List[Any],
    downloader_id: str,
    concurrency_limit: Optional[int] = None,
    *,
    cursor: Optional[str] = None,
    max_torrents_per_run: Optional[int] = None,
    run_budget_seconds: Optional[float] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Enrich qBittorrent torrents with tracker info after sync/maindata.

    W3-1 有界 worker 队列 + 单轮预算：生产者把 hash 入队、固定 N 个 worker 消费
    拉取，禁止一次性为全部 hash 创建任务对象；10k 级种子时活跃 asyncio 任务数
    ≈ worker_count + 控制任务（生产者 1 + 当前协程），不随 hash 总量增长。
    单轮数量/时间预算到期即停止消费，未消费 hash 留在队列中丢弃（不写 DB）。
    拉取通过 downloader_api_runtime 在 tracker_lane 专用 executor 调用，避免挤占
    默认线程池；单调用超时取 settings.QB_TRACKER_PER_CALL_TIMEOUT。

    W3-1 第二部分（持久化 cursor 续跑）：
    - 待处理 hash 按字典序稳定排序（供游标续跑与调用方批量写入共用同一顺序）；
    - cursor 为 JSON 文本 {"last_hash": ...}，跳过 ≤ last_hash 的已 durable hash，
      只处理游标之后的部分（从上次中断处继续，不重复已提交批次）；
    - 返回值 (new_cursor, budget_reason)：new_cursor = 本轮连续成功拉取前缀中
      最后一个 hash；失败 hash 或预算未消费 hash 都不会被游标越过；
      budget_reason = "count"/"time"/None，供调用方判定 partial 与 cycle complete。

    Args:
        client: qBittorrent 客户端实例
        torrent_info_list: 种子信息列表
        downloader_id: 下载器标识（透传给 downloader_api_runtime 做 per-downloader 限流与日志）
        concurrency_limit: 历史参数（QB_TRACKER_CONCURRENCY 旧语义），自 W3-1 起
            不再控制任务数上限，worker 数一律取 settings.QB_TRACKER_WORKER_COUNT；
            保留仅为签名兼容（调用方均未传值）。
        cursor: 续跑游标 JSON（None 表示从头开始本周期）。
        max_torrents_per_run: 单轮数量预算覆盖（Coordinator record_budget 透传；
            None 回落 settings.QB_TRACKER_MAX_TORRENTS_PER_RUN）。
        run_budget_seconds: 单轮时间预算覆盖（Coordinator deadline 透传；None 回落
            settings.QB_TRACKER_RUN_BUDGET_SECONDS）。

    Returns:
        (new_cursor, budget_reason) 元组；无可处理 hash 时返回 (None, None)。
    """
    if not torrent_info_list:
        return None, None

    info_by_hash = {}
    torrent_hashes = []
    for torrent_info in torrent_info_list:
        torrent_hash = _qb_get_attr(torrent_info, "hash")
        if torrent_hash:
            info_by_hash[torrent_hash] = torrent_info
            torrent_hashes.append(torrent_hash)

    if not torrent_hashes:
        logger.warning("[QB_TRACKER_ENRICH] No valid hashes found")
        return None, None

    # W3-1 第二部分：稳定排序（hash 字典序）+ 跳过 ≤ cursor 的已 durable hash
    torrent_hashes.sort()
    cursor_before = cursor
    last_hash = _parse_qb_tracker_cursor(cursor)
    skipped_count = 0
    if last_hash is not None:
        skipped_count = sum(1 for h in torrent_hashes if h <= last_hash)
        torrent_hashes = [h for h in torrent_hashes if h > last_hash]
    if not torrent_hashes:
        # 游标之后无待处理 hash（全部已 durable）→ 本轮无需拉取
        logger.info(
            f"[QB_TRACKER_ENRICH] 游标之后无待处理 hash，全部已 durable "
            f"(cursor: {cursor_before}, skipped: {skipped_count}, downloader: {downloader_id})"
        )
        return None, None

    worker_count = max(1, settings.QB_TRACKER_WORKER_COUNT)
    # W3-1 第二部分：Coordinator 预算透传覆盖（SyncRequest.deadline/record_budget）；
    # None 时回落配置默认（W3-1a 语义不变）
    max_torrents_per_run = max(
        1, max_torrents_per_run if max_torrents_per_run is not None else settings.QB_TRACKER_MAX_TORRENTS_PER_RUN
    )
    run_budget_seconds = (
        run_budget_seconds if run_budget_seconds is not None else settings.QB_TRACKER_RUN_BUDGET_SECONDS
    )
    per_call_timeout = settings.QB_TRACKER_PER_CALL_TIMEOUT

    enrich_start = datetime.now()
    run_start = time.monotonic()
    logger.info(
        f"[QB_TRACKER_ENRICH] Enriching {len(torrent_hashes)} torrents with tracker info "
        f"(workers: {worker_count}, max_per_run: {max_torrents_per_run}, "
        f"budget_seconds: {run_budget_seconds}, per_call_timeout: {per_call_timeout}, "
        f"downloader: {downloader_id}, cursor_before: {cursor_before or 'None'}, "
        f"skipped_from_cursor: {skipped_count})"
    )

    async def _fetch_single_trackers(torrent_hash: str) -> tuple[str, Any] | None:
        """
        获取单个种子的 tracker 信息（通过 tracker_lane executor，单调用超时预算）

        Returns:
            (torrent_hash, trackers) 元组，失败时返回 None
        """
        try:
            trackers = await call_downloader_api(
                downloader_id,
                DownloadLane.TRACKER,
                client.torrents_trackers,
                args=(torrent_hash,),
                timeout=per_call_timeout,
                operation="qb_fetch_trackers",
            )
            return torrent_hash, trackers
        except Exception as e:
            logger.error(f"[QB_TRACKER_ENRICH] Failed to fetch trackers for {torrent_hash[:16]}...: {e}")
            return None

    # W3-1 有界 worker 队列：队列容量 = worker_count，生产者入队、worker 消费，
    # 活跃任务数恒为 生产者(1) + workers(N) + 当前协程。预算到期即停止生产/消费；
    # 生产者所有 put 均带 wait_for 周期唤醒重查预算，避免预算到期后无人消费时
    # 生产者/哨兵 put 永久阻塞。哨兵（None）用于正常路径下收尾 worker。
    queue: "asyncio.Queue[Optional[str]]" = asyncio.Queue(maxsize=worker_count)
    # 单线程事件循环内共享的可变状态：预算检查 + started 递增为同步原子段，
    # 多个 worker 不会同时越过数量上限（总远程调用数 ≤ max_torrents_per_run）
    state: Dict[str, Any] = {
        "started": 0,  # 已发起远程调用的 hash 数（数量预算判定依据）
        "success_count": 0,
        "failed_count": 0,
        "budget_reason": None,  # "count" | "time" | None
    }

    def _budget_exceeded() -> Optional[str]:
        """拉取前预算检查：返回到期原因，None 表示预算内。"""
        if state["started"] >= max_torrents_per_run:
            return "count"
        if run_budget_seconds > 0 and (time.monotonic() - run_start) >= run_budget_seconds:
            return "time"
        return None

    async def _producer() -> None:
        """把待拉取 hash 依次入队；预算到期即停止生产，结束时逐 worker 放入哨兵。"""
        try:
            index = 0
            while index < len(torrent_hashes):
                if state["budget_reason"] is not None:
                    break
                try:
                    # 有界队列满时最多等 0.5 秒；等待期间若预算到期（workers 退出
                    # 不再消费），重查后立即停止生产，避免生产者永久阻塞在 put
                    await asyncio.wait_for(queue.put(torrent_hashes[index]), timeout=0.5)
                    index += 1
                except asyncio.TimeoutError:
                    continue
        finally:
            # 每个 worker 一个终止哨兵；同样带超时防止预算到期后无人消费
            for _ in range(worker_count):
                try:
                    await asyncio.wait_for(queue.put(None), timeout=0.5)
                except asyncio.TimeoutError:
                    break

    async def _tracker_worker() -> None:
        """消费队列并拉取单个种子 tracker；每次拉取前检查单轮预算。"""
        while True:
            if state["budget_reason"] is not None:
                return
            torrent_hash = await queue.get()
            try:
                if torrent_hash is None:
                    return
                # 出队后、拉取前再次检查预算（出队期间可能有其他 worker 已触发到期）
                if state["budget_reason"] is not None:
                    return
                exceeded = _budget_exceeded()
                if exceeded is not None:
                    state["budget_reason"] = exceeded
                    return
                state["started"] += 1
                current_hash = torrent_hash
                result = await _fetch_single_trackers(current_hash)
                # 处理结果：None（拉取失败/异常）计 failed，成功写回内存对象（不写 DB）
                if result is None:
                    # 记录失败标记；后续写入阶段只消费连续成功的前缀，避免游标越过失败 hash。
                    failed_torrent = info_by_hash.get(current_hash)
                    if failed_torrent is not None:
                        _qb_set_attr(failed_torrent, "_btdeck_tracker_enriched", False)
                    state["failed_count"] += 1
                    continue
                fetched_hash, trackers = result
                torrent_info = info_by_hash.get(fetched_hash)
                if torrent_info:
                    torrent_info.trackers = trackers
                    _qb_set_attr(torrent_info, "_btdeck_tracker_enriched", True)
                    state["success_count"] += 1
                else:
                    logger.warning(f"[QB_TRACKER_ENRICH] Torrent info not found for hash {fetched_hash[:16]}...")
                    state["failed_count"] += 1
            finally:
                queue.task_done()

    # 只创建固定数量的任务：1 个生产者 + worker_count 个 worker（W3-1 禁止全量 create_task）
    producer_task = asyncio.create_task(_producer())
    worker_tasks = [asyncio.create_task(_tracker_worker()) for _ in range(worker_count)]
    await asyncio.gather(producer_task, *worker_tasks)

    success_count = state["success_count"]
    failed_count = state["failed_count"]
    processed_this_run = state["started"]
    budget_reason = state["budget_reason"]
    queue_depth = queue.qsize()
    remote_error_rate = failed_count / processed_this_run if processed_this_run else 0.0
    # W3-1 第二部分：续跑游标只指向连续成功前缀的最后一个 hash。
    # 生产者按排序入队、worker 按 FIFO 消费；失败 hash 后的成功结果不能让游标跨过
    # 失败点，否则下一轮会永久跳过尚未 durable 的记录。
    new_cursor = None
    for torrent_hash in torrent_hashes[:processed_this_run]:
        torrent_info = info_by_hash.get(torrent_hash)
        if _qb_get_attr(torrent_info, "_btdeck_tracker_enriched", None) is not True:
            break
        new_cursor = _build_qb_tracker_cursor(torrent_hash)

    enrich_duration = (datetime.now() - enrich_start).total_seconds()
    logger.info(
        f"[QB_TRACKER_ENRICH] Completed enrichment: {success_count} succeeded, "
        f"{failed_count} failed, {processed_this_run} processed, {len(torrent_hashes)} total "
        f"in {enrich_duration:.3f}s (queue_depth: {queue_depth}, workers_active: {worker_count}, "
        f"processed_this_run: {processed_this_run}, budget_reason: {budget_reason}, "
        f"remote_error_rate: {remote_error_rate:.2%}, cursor_before: {cursor_before or 'None'}, "
        f"cursor_after: {new_cursor or 'None'})"
    )
    return new_cursor, budget_reason


async def _mark_qb_removed_torrents(db: AsyncSession, downloader_id: str, removed_hashes: List[str]) -> WriteStats:
    """标记 qBittorrent 增量同步中被删除的种子（W1-3 统一写治理）。

    变更路径（对照旧旁路写者，消除 db_write_scope 外自建 commit/retry）：
    1. 事务外只读查询待更新 info_id 列表（不 commit、不进 db_write_scope）。
    2. 空变更（removed_hashes 为空或查询无命中）直接返回零值 WriteStats，
       不创建事务、不 commit。
    3. 命中行构造 mapping 后统一走 bulk_upsert_with_retry（统一批大小 +
       db_write_scope 串行化 + 批级重试，锁冲突只重试当前批）。
    4. 查询/写入异常原样上抛（保留统一写入器 ChunkedWriteError/原异常链），
       但先回滚失败事务，保证调用方降级路径能继续复用会话。

    Args:
        db: 异步数据库会话。
        downloader_id: 下载器标识。
        removed_hashes: 增量同步上报的已删除种子 hash 列表。

    Returns:
        WriteStats 写入统计；无变更时返回零值统计（scanned/changed 等全 0）。
    """
    if not removed_hashes:
        return WriteStats()

    try:
        # 事务外计算待更新 ID（只读查询，不 commit）
        result = await db.execute(
            select(TorrentInfo.info_id, TorrentInfo.downloader_name).where(
                TorrentInfo.downloader_id == downloader_id,
                TorrentInfo.hash.in_(removed_hashes),
                TorrentInfo.dr == 0,
            )
        )
        rows = result.all()
        if not rows:
            return WriteStats()

        current_time = datetime.now()
        # TorrentInfo 主键为 (info_id, downloader_id, downloader_name) 三列复合主键，
        # bulk_update_mappings 的 mapping 必须包含全部主键列才能命中更新。
        mappings = [
            {
                "info_id": row.info_id,
                "downloader_id": downloader_id,
                "downloader_name": row.downloader_name,
                "dr": 1,
                "update_time": current_time,
                "update_by": "system",
            }
            for row in rows
        ]
        return await bulk_upsert_with_retry(
            db,
            [],
            mappings,
            model=TorrentInfo,
            label="QB_REMOVED_MARK",
        )
    except Exception:
        # 异常原样上抛（保留统一写入器的 ChunkedWriteError/原异常链），
        # 但先回滚失败事务，保证调用方降级路径（fallback 全量同步）能继续复用会话。
        await db.rollback()
        raise


# ==============================================================================
# 种子信息同步（不含 tracker，用于高频种子信息同步）
# ==============================================================================


# ==============================================================================
# W3-3 第一部分（P1-02）：info-only 现有记录分页读取 + 单轮预算/缓冲上限
# 详见 PLANS/sync-database-blocking-remediation.md W3-3
# ==============================================================================


async def _load_existing_torrent_info_cache_paginated(
    db: AsyncSession,
    downloader_id: Any,
    fields: tuple,
    page_size: int,
    log_prefix: str,
) -> tuple:
    """分页读取现有种子记录并构建 existing_torrents_cache（按 hash 索引）。

    W3-3 第一部分：原来一次 select(...).all() 会把大下载器的完整 ORM 行对象图
    一次性载入内存（峰值内存与下载器规模成正比）。现改为按 hash 稳定排序分页
    读取（每页 page_size 行，offset 翻页），逐页构建同一份 dict cache。

    分页只解决"一次加载"的峰值：缓存结构（hash -> 业务字段 dict）与结果语义
    不变——全部行都在 cache 里，diff（has_torrent_info_changes）照常按 hash
    索引命中。每页读取后 await asyncio.sleep(0) 让出事件循环（批间让行），
    防止长分页循环饿死其他协程。

    Args:
        db: 异步数据库会话。
        downloader_id: 下载器 ID（过滤条件）。
        fields: 需要读取的 TorrentInfo 列表达式元组（首列必须是 hash）。
        page_size: 每页行数（settings.INFO_SYNC_DB_READ_PAGE_SIZE）。
        log_prefix: 日志前缀（[QB_INFO_SYNC]/[TR_INFO_SYNC]）。

    Returns:
        (existing_torrents_cache, page_count) 元组：cache 为 hash -> 业务字段
        dict（供 has_torrent_info_changes 对比），page_count 为实际读取页数
        （观测 yield_count 用）。
    """
    cache: Dict[str, Dict[str, Any]] = {}
    offset = 0
    page_count = 0
    while True:
        result = await db.execute(
            select(*fields)
            .filter(TorrentInfo.downloader_id == downloader_id)
            .filter(TorrentInfo.dr == 0)
            .order_by(TorrentInfo.hash)
            .limit(page_size)
            .offset(offset)
        )
        rows = result.all()
        page_count += 1
        for row in rows:
            # cache 存完整 dict（key=列名），供 has_torrent_info_changes 对比
            cache[row.hash] = {col.key: getattr(row, col.key) for col in fields}
        # 批间让行：每页读取后让出事件循环，防长分页循环饿死其他协程
        await asyncio.sleep(0)
        if len(rows) < page_size:
            break
        offset += page_size
    logger.debug(
        f"{log_prefix} 现有记录分页读取完成: total={len(cache)}, pages={page_count}, " f"page_size={page_size}"
    )
    return cache, page_count


async def _flush_info_write_buffer(
    db: AsyncSession,
    to_insert: List[Dict[str, Any]],
    to_update: List[Dict[str, Any]],
    label: str,
) -> float:
    """缓冲满时把待写行 flush 一批到统一写入器（W3-3 缓冲上限）。

    达到 INFO_SYNC_MAX_BUFFERED_ROWS 时调用：去重（双重保护）→
    bulk_upsert_with_retry（沿用既有治理写入路径）→ 清空缓冲 → 让出事件
    循环（批间让行）。控制逐种子构造/差异计算的待写行内存峰值。

    Args:
        db: 异步数据库会话。
        to_insert: 待插入 mapping 缓冲（flush 后被清空）。
        to_update: 待更新 mapping 缓冲（flush 后被清空）。
        label: 写入日志标签（溯源用）。

    Returns:
        本批写入耗时（秒，观测 phase_ms.write 用）。
    """
    if not to_insert and not to_update:
        return 0.0
    deduped_insert, deduped_update = _deduplicate_torrent_lists(to_insert, to_update)
    write_start = time.monotonic()
    await bulk_upsert_with_retry(
        db,
        deduped_insert,
        deduped_update,
        model=TorrentInfo,
        label=label,
    )
    elapsed = time.monotonic() - write_start
    # flush 后清空缓冲，调用方继续累积下一批
    to_insert.clear()
    to_update.clear()
    # 批间让行：flush 后让出事件循环，防长循环饿死其他协程
    await asyncio.sleep(0)
    return elapsed


def _info_budget_exceeded(
    processed_count: int,
    max_torrents_per_run: int,
    run_start: float,
    run_budget_seconds: float,
) -> Optional[str]:
    """info-only 单轮预算检查（W3-3，参照 W3-1a 的 budget_reason 模式）。

    Args:
        processed_count: 本轮已处理的种子数。
        max_torrents_per_run: 单轮记录数上限（INFO_SYNC_MAX_TORRENTS_PER_RUN）。
        run_start: 本轮开始时间（time.monotonic）。
        run_budget_seconds: 单轮时长上限（INFO_SYNC_RUN_BUDGET_SECONDS，
            0 或负值表示不限时）。

    Returns:
        "count"（数量预算到期）/ "time"（时间预算到期）/ None（预算内）。
    """
    if processed_count >= max_torrents_per_run:
        return "count"
    if run_budget_seconds > 0 and (time.monotonic() - run_start) >= run_budget_seconds:
        return "time"
    return None


def _parse_info_cursor(cursor_value: Optional[str]) -> Optional[str]:
    """解析 info-only 断点游标（与 tracker 游标保持同一 JSON 结构）。"""
    if not cursor_value:
        return None
    try:
        payload = json.loads(cursor_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    last_hash = payload.get("last_hash")
    return str(last_hash) if last_hash else None


def _build_info_cursor(last_hash: str) -> str:
    """构造 info-only 断点游标。"""
    return json.dumps({"last_hash": str(last_hash)}, ensure_ascii=False)


async def _emit_info_progress(callback: Optional[Callable[[str], Awaitable[None]]], last_hash: Optional[str]) -> None:
    """在 info-only 批量写入成功后推进运行期检查点；回调失败不阻断业务写入。"""
    if callback is None or not last_hash:
        return
    try:
        await callback(_build_info_cursor(last_hash))
    except Exception as callback_error:  # noqa: BLE001 - checkpoint 观测不能回滚已提交数据
        logger.warning("info-only 检查点推进失败: %s", callback_error)


async def qb_add_torrents_info_only_async(
    db: AsyncSession,
    downloaders: List[Any],
    client: Optional[Any] = None,
    *,
    cursor: Optional[str] = None,
    progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Optional[Dict[str, Any]]:
    """qBittorrent 种子信息同步（仅同步种子基础信息，不同步 tracker）

    Args:
        db: 异步数据库会话
        downloaders: 下载器对象列表（取第一个）
        client: 来自 app.state.store 的已缓存 qBittorrent 客户端；缺失时拒绝执行。
    """
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return None

    bt_downloader = downloaders[0]
    # 优先复用传入的缓存客户端（来自 app.state.store），避免重复创建连接
    if client is None:
        raise ValueError(
            f"下载器 {getattr(bt_downloader, 'nickname', bt_downloader.downloader_id)} 缺少缓存客户端，"
            "拒绝在 info-only 同步路径中自建 qBittorrent 连接"
        )

    downloader_id = str(bt_downloader.downloader_id)
    cursor_before = cursor
    if cursor_before is None:
        try:
            from app.services.sync_coordinator import get_run_checkpoint  # noqa: PLC0415

            run_checkpoint = get_run_checkpoint(downloader_id, "info")
            if run_checkpoint is not None:
                cursor_before = run_checkpoint.get("cursor")
        except Exception as checkpoint_error:  # noqa: BLE001 - 无活动上下文时从头执行
            logger.debug("读取 info-only 运行期检查点失败: %s", checkpoint_error)
    cursor_last_hash = _parse_info_cursor(cursor_before)
    torrent_info_list = []
    incremental_failed = False
    force_full_sync = False
    pending_rid: Optional[int] = None

    # W3-3 第一部分（P1-02）：资源治理配置——下载器并发（SQLite 默认 1）、
    # 现有记录分页页大小、单轮数量/时间预算、待写行缓冲上限。观测信息随
    # 完成日志输出（downloader_concurrency/phase_ms/rows_buffered/
    # records_per_second/yield_count/budget_reason）
    downloader_concurrency = max(1, settings.INFO_SYNC_DOWNLOADER_CONCURRENCY)
    page_size = max(1, settings.INFO_SYNC_DB_READ_PAGE_SIZE)
    max_torrents_per_run = max(1, settings.INFO_SYNC_MAX_TORRENTS_PER_RUN)
    run_budget_seconds = settings.INFO_SYNC_RUN_BUDGET_SECONDS
    max_buffered_rows = max(1, settings.INFO_SYNC_MAX_BUFFERED_ROWS)
    run_start = time.monotonic()
    budget_reason: Optional[str] = None
    processed_count = 0
    buffered_peak = 0
    yield_count = 0
    # phase_ms 简单分段时间：fetch=远程读取，normalize=现有记录分页加载，
    # diff=逐种子构造+差异计算，write=所有 bulk 写入（含缓冲 flush）
    phase_times = {"fetch": 0.0, "normalize": 0.0, "diff": 0.0, "write": 0.0}
    phase_start = run_start

    now_ts = datetime.now().timestamp()
    last_full_ts = _QB_LAST_FULL_SYNC.get(downloader_id, 0)
    # A persisted cursor means the previous full snapshot stopped before its
    # durable end. Resume that snapshot first; applying an incremental delta
    # to a partial cursor could skip changed hashes that sort before it.
    if cursor_before is not None:
        force_full_sync = True
    if now_ts - last_full_ts >= QB_FULL_SYNC_INTERVAL_SECONDS:
        force_full_sync = True

    if QB_USE_INCREMENTAL_SYNC and not force_full_sync:
        last_rid = _QB_SYNC_RID_CACHE.get(downloader_id)
        try:
            if last_rid is None:
                # ✅ 通过 downloader_api_runtime 在 sync_lane 专用 executor 调用，避免默认线程池挤占
                sync_data = await call_downloader_api(
                    downloader_id,
                    DownloadLane.SYNC,
                    client.sync_maindata,
                    kwargs={"rid": 0},
                    operation="sync_maindata_init",
                )
                new_rid = int(sync_data.get("rid", 0))
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                # 首轮快照宽松水合：从 torrents/info 补齐全量字段（含 added_on），
                # 缺失 hash 不抛错（maindata 之后被删除的种子不应拖垮整轮）
                if torrent_info_list:
                    torrent_info_list = await _hydrate_qb_incremental_torrents(
                        client,
                        torrent_info_list,
                        downloader_id,
                        "qb_info_first_full_details",
                        strict=False,
                    )
                pending_rid = new_rid
                logger.info(
                    f"[QB_INFO_SYNC] first full sync: downloader_id={downloader_id}, rid={new_rid}, torrents={len(torrent_info_list)}"
                )
            else:
                # ✅ 通过 downloader_api_runtime 在 sync_lane 专用 executor 调用，避免默认线程池挤占
                sync_data = await call_downloader_api(
                    downloader_id,
                    DownloadLane.SYNC,
                    client.sync_maindata,
                    kwargs={"rid": last_rid},
                    operation="sync_maindata_incremental",
                )
                new_rid = int(sync_data.get("rid", last_rid))
                removed = sync_data.get("torrents_removed", []) or []
                if removed:
                    await _mark_qb_removed_torrents(db, bt_downloader.downloader_id, removed)
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                if torrent_info_list:
                    torrent_info_list = await _hydrate_qb_incremental_torrents(
                        client,
                        torrent_info_list,
                        downloader_id,
                        "qb_info_incremental_details",
                    )
                pending_rid = new_rid
                logger.info(
                    f"[QB_INFO_SYNC] incremental: downloader_id={downloader_id}, changed={len(torrent_info_list)}, removed={len(removed)}"
                )
        except Exception as e:
            pending_rid = None
            incremental_failed = True
            logger.warning(f"[QB_INFO_SYNC] incremental failed, fallback to batch: {e}")

    if force_full_sync or (not QB_USE_INCREMENTAL_SYNC) or incremental_failed:
        # 降级时丢弃任何未完整水合的 delta，只写入全量快照。
        torrent_info_list = []
        offset = 0
        while True:
            # ✅ 通过 downloader_api_runtime 在 sync_lane 专用 executor 调用
            batch = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                client.torrents_info,
                kwargs={"limit": QB_BATCH_SIZE, "offset": offset},
                operation="qb_torrents_info_only",
            )
            if not batch:
                break
            torrent_info_list.extend(batch)
            if len(batch) < QB_BATCH_SIZE:
                break
            offset += QB_BATCH_SIZE
        _QB_LAST_FULL_SYNC[downloader_id] = now_ts

    # 断点续跑需要稳定顺序；qB 增量与全量响应均按 hash 排序后再处理。
    torrent_info_list.sort(key=lambda torrent: str(_qb_get_attr(torrent, "hash") or ""))
    phase_times["fetch"] = (time.monotonic() - phase_start) * 1000.0
    phase_start = time.monotonic()

    current_time = datetime.now()

    # ✅ W3-3 第一部分：现有记录分页读取（避免一次加载完整 ORM 对象图）。
    # 仍构建 existing_torrents_cache（dict，按 hash 索引——diff 需要内存缓存，
    # 分页只解决"一次加载"的峰值，不改变缓存结构）
    existing_torrents_cache, cache_pages = await _load_existing_torrent_info_cache_paginated(
        db,
        bt_downloader.downloader_id,
        (
            TorrentInfo.hash,
            TorrentInfo.info_id,
            TorrentInfo.create_time,
            TorrentInfo.progress,
            TorrentInfo.name,
            TorrentInfo.size,
            TorrentInfo.status,
            TorrentInfo.ratio,
            TorrentInfo.ratio_limit,
            TorrentInfo.tags,
            TorrentInfo.category,
            TorrentInfo.save_path,
            TorrentInfo.super_seeding,
        ),
        page_size,
        "[QB_INFO_SYNC]",
    )
    phase_times["normalize"] = (time.monotonic() - phase_start) * 1000.0
    yield_count += cache_pages

    to_insert: List[Dict[str, Any]] = []
    to_update: List[Dict[str, Any]] = []
    stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}
    ratio_stats = RatioNormalizationStats()
    pending_torrent_count = sum(
        1
        for torrent in torrent_info_list
        if (torrent_hash := str(_qb_get_attr(torrent, "hash") or ""))
        and (cursor_last_hash is None or torrent_hash > cursor_last_hash)
    )
    last_processed_hash: Optional[str] = None

    phase_start = time.monotonic()
    for torrent_info in torrent_info_list:
        torrent_hash = str(_qb_get_attr(torrent_info, "hash") or "")
        if not torrent_hash or (cursor_last_hash is not None and torrent_hash <= cursor_last_hash):
            continue
        # W3-3 单轮预算检查（数量/时间，参照 W3-1a 的 budget_reason 模式）：
        # 达到即停止处理剩余种子；已缓冲的待写行仍会在收尾时写入（部分成果
        # durable，本轮结果标记 partial + budget_reason）
        if budget_reason is None:
            budget_reason = _info_budget_exceeded(processed_count, max_torrents_per_run, run_start, run_budget_seconds)
        if budget_reason is not None:
            break
        processed_count += 1

        # W3-3 缓冲上限：待写行达到 INFO_SYNC_MAX_BUFFERED_ROWS 先 flush 一批
        # 再继续（控制内存峰值；flush 后清空缓冲并让出事件循环）
        buffered = len(to_insert) + len(to_update)
        if buffered > buffered_peak:
            buffered_peak = buffered
        if buffered >= max_buffered_rows:
            phase_times["write"] += (
                await _flush_info_write_buffer(
                    db,
                    to_insert,
                    to_update,
                    f"[QB_INFO_SYNC] {bt_downloader.nickname} (batch)",
                )
                * 1000.0
            )
            yield_count += 1
            await _emit_info_progress(progress_callback, last_processed_hash)

        cached_row = existing_torrents_cache.get(torrent_hash)
        raw_progress = _qb_get_attr(torrent_info, "progress", None)
        new_progress = (
            _normalize_progress_value(
                float(raw_progress) * 100.0
                if raw_progress and raw_progress <= 1.0
                else (
                    float(raw_progress) / 100.0
                    if raw_progress and raw_progress > 100.0
                    else float(raw_progress) if raw_progress else 0.0
                )
            )
            if raw_progress
            else 0.0
        )

        if cached_row is None:
            stats["insert"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            progress_value = new_progress
        else:
            torrent_info_id = cached_row["info_id"]
            create_time = cached_row["create_time"] or current_time
            # ✅ progress 0.5 阈值：微变化保留旧值（保留现有逻辑，不搬进工具）
            old_progress = _normalize_progress_value(cached_row["progress"])
            progress_value = old_progress if abs(new_progress - old_progress) < 0.5 else new_progress

            torrent_data = {
                "info_id": torrent_info_id,
                "downloader_id": bt_downloader.downloader_id,
                "downloader_name": bt_downloader.nickname,
                "torrent_id": torrent_hash,
                "hash": torrent_hash,
                "name": _qb_get_attr(torrent_info, "name", ""),
                "save_path": _qb_get_attr(torrent_info, "save_path", ""),
                "size": _qb_get_attr(torrent_info, "total_size", None) or _qb_get_attr(torrent_info, "size", 0),
                "progress": progress_value,
                "torrent_file": f"/config/qbittorrent/BT_backup/{torrent_hash}.torrent",
                "status": TorrentStatusMapper.convert_qbittorrent_status(_qb_get_attr(torrent_info, "state", "")),
                "added_date": (
                    datetime.fromtimestamp(_safe_parse_timestamp(_qb_get_attr(torrent_info, "added_on", 0)))
                    if _safe_parse_timestamp(_qb_get_attr(torrent_info, "added_on", 0)) is not None
                    else None
                ),
                "completed_date": (
                    datetime.fromtimestamp(_safe_parse_timestamp(_qb_get_attr(torrent_info, "completion_on", 0)))
                    if _safe_parse_timestamp(_qb_get_attr(torrent_info, "completion_on", 0)) is not None
                    else None
                ),
                "tags": _qb_get_attr(torrent_info, "tags", ""),
                "category": _qb_get_attr(torrent_info, "category", ""),
                "super_seeding": _qb_get_attr(torrent_info, "super_seeding", False),
                "enabled": 1,
                "create_time": create_time,
                "create_by": "admin",
                "update_time": current_time,
                "update_by": "admin",
                "dr": 0,
            }
            ratio_stats.observe(
                apply_normalized_ratio_fields(
                    torrent_data,
                    raw_ratio=_qb_get_attr(torrent_info, "ratio", MISSING_RATIO_VALUE),
                    raw_ratio_limit=_qb_get_attr(torrent_info, "ratio_limit", MISSING_RATIO_VALUE),
                    is_insert=False,
                )
            )

            # ✅ 阶段 2.5：整行变更检测，无变化真正跳过（修正 skip 语义 bug）
            if has_torrent_info_changes(cached_row, torrent_data):
                stats["update"] += 1
                to_update.append(torrent_data)
            else:
                stats["skip"] += 1
            last_processed_hash = torrent_hash
            continue

        # insert 分支
        torrent_data = {
            "info_id": torrent_info_id,
            "downloader_id": bt_downloader.downloader_id,
            "downloader_name": bt_downloader.nickname,
            "torrent_id": torrent_hash,
            "hash": torrent_hash,
            "name": _qb_get_attr(torrent_info, "name", ""),
            "save_path": _qb_get_attr(torrent_info, "save_path", ""),
            "size": _qb_get_attr(torrent_info, "total_size", None) or _qb_get_attr(torrent_info, "size", 0),
            "progress": progress_value,
            "torrent_file": f"/config/qbittorrent/BT_backup/{torrent_hash}.torrent",
            "status": TorrentStatusMapper.convert_qbittorrent_status(_qb_get_attr(torrent_info, "state", "")),
            "added_date": (
                datetime.fromtimestamp(_safe_parse_timestamp(_qb_get_attr(torrent_info, "added_on", 0)))
                if _safe_parse_timestamp(_qb_get_attr(torrent_info, "added_on", 0)) is not None
                else None
            ),
            "completed_date": (
                datetime.fromtimestamp(_safe_parse_timestamp(_qb_get_attr(torrent_info, "completion_on", 0)))
                if _safe_parse_timestamp(_qb_get_attr(torrent_info, "completion_on", 0)) is not None
                else None
            ),
            "tags": _qb_get_attr(torrent_info, "tags", ""),
            "category": _qb_get_attr(torrent_info, "category", ""),
            "super_seeding": _qb_get_attr(torrent_info, "super_seeding", False),
            "enabled": 1,
            "create_time": create_time,
            "create_by": "admin",
            "update_time": current_time,
            "update_by": "admin",
            "dr": 0,
        }
        ratio_stats.observe(
            apply_normalized_ratio_fields(
                torrent_data,
                raw_ratio=_qb_get_attr(torrent_info, "ratio", MISSING_RATIO_VALUE),
                raw_ratio_limit=_qb_get_attr(torrent_info, "ratio_limit", MISSING_RATIO_VALUE),
                is_insert=True,
            )
        )
        to_insert.append(torrent_data)
        last_processed_hash = torrent_hash

    phase_times["diff"] = (time.monotonic() - phase_start) * 1000.0

    ratio_stats.log_summary(
        logger,
        context=f"qbittorrent-info:{bt_downloader.downloader_id}",
    )

    # ✅ 去重保护（双重保护机制）
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    # ✅ 阶段 2.5：用公共 bulk_upsert_with_retry（内含 db_write_scope + retry）
    try:
        write_start = time.monotonic()
        await bulk_upsert_with_retry(
            db,
            to_insert,
            to_update,
            model=TorrentInfo,
            label=f"[QB_INFO_SYNC] {bt_downloader.nickname}",
        )
        phase_times["write"] += (time.monotonic() - write_start) * 1000.0
        cycle_complete = budget_reason is None and processed_count >= pending_torrent_count
        if pending_rid is not None and cycle_complete:
            _confirm_qb_sync_rid(downloader_id, pending_rid)
        await _emit_info_progress(progress_callback, last_processed_hash)
        total_elapsed = time.monotonic() - run_start
        records_per_second = processed_count / total_elapsed if total_elapsed > 0 else 0.0
        logger.info(
            f"[QB_INFO_SYNC] {bt_downloader.nickname} 完成: 插入 {stats['insert']}, "
            f"更新 {stats['update']}, 跳过 {stats['skip']}, "
            f"partial={budget_reason is not None}, budget_reason={budget_reason}, "
            f"downloader_concurrency={downloader_concurrency}, "
            f"phase_ms=fetch={phase_times['fetch']:.1f},normalize={phase_times['normalize']:.1f},"
            f"diff={phase_times['diff']:.1f},write={phase_times['write']:.1f}, "
            f"rows_buffered={buffered_peak}, records_per_second={records_per_second:.1f}, "
            f"yield_count={yield_count}"
        )
        if budget_reason is not None:
            # 单轮预算到期：已处理部分写入完成，本轮结果为 partial（部分成果）
            logger.warning(
                f"[QB_INFO_SYNC] {bt_downloader.nickname} 单轮预算到期 "
                f"(budget_reason={budget_reason})，已处理 {processed_count}/"
                f"{len(torrent_info_list)} 个种子，本轮结果为 partial"
            )
    except Exception as e:
        await db.rollback()
        logger.error(f"[QB_INFO_SYNC] {bt_downloader.nickname} 失败: {e}")
        raise

    if progress_callback is None:
        return None
    cycle_complete = budget_reason is None and processed_count >= pending_torrent_count
    return {
        "cursor": (
            None
            if cycle_complete
            else (_build_info_cursor(last_processed_hash) if last_processed_hash else cursor_before)
        ),
        "cycle_complete": cycle_complete,
        "partial": not cycle_complete,
        "budget_reason": budget_reason,
        "processed": processed_count,
        "total": pending_torrent_count,
    }


async def tr_add_torrents_info_only_async(
    db: AsyncSession,
    downloaders: List[Any],
    client: Optional[Any] = None,
    *,
    cursor: Optional[str] = None,
    progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Optional[Dict[str, Any]]:
    """Transmission 种子信息同步（仅同步种子基础信息，不同步 tracker）

    Args:
        db: 异步数据库会话
        downloaders: 下载器对象列表（取第一个）
        client: 来自 app.state.store 的已缓存 Transmission 客户端；缺失时拒绝执行。
    """
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return None

    bt_downloader = downloaders[0]
    # 优先复用传入的缓存客户端，避免重复创建连接
    if client is None:
        raise ValueError(
            f"下载器 {getattr(bt_downloader, 'nickname', bt_downloader.downloader_id)} 缺少缓存客户端，"
            "拒绝在 info-only 同步路径中自建 Transmission 连接"
        )
    tr_client = client
    downloader_id = str(bt_downloader.downloader_id)
    cursor_before = cursor
    if cursor_before is None:
        try:
            from app.services.sync_coordinator import get_run_checkpoint  # noqa: PLC0415

            run_checkpoint = get_run_checkpoint(downloader_id, "info")
            if run_checkpoint is not None:
                cursor_before = run_checkpoint.get("cursor")
        except Exception as checkpoint_error:  # noqa: BLE001 - 无活动上下文时从头执行
            logger.debug("读取 info-only 运行期检查点失败: %s", checkpoint_error)
    cursor_last_hash = _parse_info_cursor(cursor_before)
    resume_from_cursor = cursor_before is not None

    # W3-3 第一部分（P1-02）：资源治理配置——下载器并发（SQLite 默认 1）、
    # 现有记录分页页大小、单轮数量/时间预算、待写行缓冲上限。观测信息随
    # 完成日志输出（downloader_concurrency/phase_ms/rows_buffered/
    # records_per_second/yield_count/budget_reason）
    downloader_concurrency = max(1, settings.INFO_SYNC_DOWNLOADER_CONCURRENCY)
    page_size = max(1, settings.INFO_SYNC_DB_READ_PAGE_SIZE)
    max_torrents_per_run = max(1, settings.INFO_SYNC_MAX_TORRENTS_PER_RUN)
    run_budget_seconds = settings.INFO_SYNC_RUN_BUDGET_SECONDS
    max_buffered_rows = max(1, settings.INFO_SYNC_MAX_BUFFERED_ROWS)
    run_start = time.monotonic()
    budget_reason: Optional[str] = None
    processed_count = 0
    buffered_peak = 0
    yield_count = 0
    # phase_ms 简单分段时间：fetch=远程读取，normalize=现有记录分页加载，
    # diff=逐种子构造+差异计算，write=所有 bulk 写入（含缓冲 flush）
    phase_times = {"fetch": 0.0, "normalize": 0.0, "diff": 0.0, "write": 0.0}
    phase_start = run_start

    # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
    base_torrents = await call_downloader_api(
        str(bt_downloader.downloader_id),
        DownloadLane.SYNC,
        tr_client.get_torrents,
        kwargs={"arguments": TR_BASE_FIELDS},
        operation="tr_get_torrents_base",
    )
    torrent_info_list = []
    now_ts = datetime.now().timestamp()
    last_full_ts = _TR_LAST_FULL_SYNC.get(downloader_id, 0)
    force_full_sync = (now_ts - last_full_ts) >= TR_FULL_SYNC_INTERVAL_SECONDS or resume_from_cursor

    if _TR_FULL_SYNC_DONE.get(downloader_id) and not force_full_sync:
        recent_threshold = now_ts - TR_ACTIVE_WINDOW_SECONDS
        active_torrents = []
        for t in base_torrents:
            activity_date = getattr(t, "activity_date", None) or getattr(t, "activityDate", None)
            activity_ts = _coerce_activity_ts(activity_date)
            if activity_ts is None:
                logger.warning(
                    "[TR_INFO] activity_date parse failed; treating as active. "
                    f"value={activity_date!r} type={type(activity_date).__name__} "
                    f"id={getattr(t, 'id', None)} hash={getattr(t, 'hashString', None)}"
                )
                active_torrents.append(t)
            elif activity_ts >= recent_threshold:
                active_torrents.append(t)
        base_torrents = active_torrents

    for i in range(0, len(base_torrents), TR_BATCH_SIZE):
        batch = base_torrents[i : i + TR_BATCH_SIZE]
        batch_ids = [t.id for t in batch if hasattr(t, "id")]
        if batch_ids:
            # ✅ 通过 downloader_api_runtime 在 sync_lane 专用 executor 调用
            torrent_info_list.extend(
                await call_downloader_api(
                    downloader_id,
                    DownloadLane.SYNC,
                    tr_client.get_torrents,
                    kwargs={"ids": batch_ids, "arguments": TR_DETAIL_FIELDS},
                    operation="tr_get_torrents_detail",
                )
            )

    # 等本轮预算完整处理后再标记 full sync，避免部分结果导致后续轮次误走 active-only 快照。
    torrent_info_list.sort(key=lambda torrent: str(getattr(torrent, "hashString", "") or ""))

    phase_times["fetch"] = (time.monotonic() - phase_start) * 1000.0
    phase_start = time.monotonic()

    current_time = datetime.now()
    # ✅ W3-3 第一部分：现有记录分页读取（避免一次加载完整 ORM 对象图）。
    # 仍构建 existing_torrents_cache（dict，按 hash 索引——diff 需要内存缓存，
    # 分页只解决"一次加载"的峰值，不改变缓存结构）
    existing_torrents_cache, cache_pages = await _load_existing_torrent_info_cache_paginated(
        db,
        bt_downloader.downloader_id,
        (
            TorrentInfo.hash,
            TorrentInfo.info_id,
            TorrentInfo.create_time,
            TorrentInfo.progress,
            TorrentInfo.name,
            TorrentInfo.size,
            TorrentInfo.status,
            TorrentInfo.error_reason,
            TorrentInfo.ratio,
            TorrentInfo.ratio_limit,
            TorrentInfo.tags,
            TorrentInfo.save_path,
        ),
        page_size,
        "[TR_INFO_SYNC]",
    )
    phase_times["normalize"] = (time.monotonic() - phase_start) * 1000.0
    yield_count += cache_pages

    pending_torrent_count = sum(
        1
        for torrent in torrent_info_list
        if (torrent_hash := str(getattr(torrent, "hashString", "") or ""))
        and (cursor_last_hash is None or torrent_hash > cursor_last_hash)
    )
    last_processed_hash: Optional[str] = None

    to_insert: List[Dict[str, Any]] = []
    to_update: List[Dict[str, Any]] = []
    stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}
    ratio_stats = RatioNormalizationStats()

    phase_start = time.monotonic()
    for torrent_info in torrent_info_list:
        torrent_hash = str(getattr(torrent_info, "hashString", "") or "")
        if not torrent_hash or (cursor_last_hash is not None and torrent_hash <= cursor_last_hash):
            continue
        # W3-3 单轮预算检查（数量/时间，参照 W3-1a 的 budget_reason 模式）：
        # 达到即停止处理剩余种子；已缓冲的待写行仍会在收尾时写入（部分成果
        # durable，本轮结果标记 partial + budget_reason）
        if budget_reason is None:
            budget_reason = _info_budget_exceeded(processed_count, max_torrents_per_run, run_start, run_budget_seconds)
        if budget_reason is not None:
            break
        processed_count += 1

        # W3-3 缓冲上限：待写行达到 INFO_SYNC_MAX_BUFFERED_ROWS 先 flush 一批
        # 再继续（控制内存峰值；flush 后清空缓冲并让出事件循环）
        buffered = len(to_insert) + len(to_update)
        if buffered > buffered_peak:
            buffered_peak = buffered
        if buffered >= max_buffered_rows:
            phase_times["write"] += (
                await _flush_info_write_buffer(
                    db,
                    to_insert,
                    to_update,
                    f"[TR_INFO_SYNC] {bt_downloader.nickname} (batch)",
                )
                * 1000.0
            )
            yield_count += 1
            await _emit_info_progress(progress_callback, last_processed_hash)

        cached_row = existing_torrents_cache.get(torrent_hash)
        raw_percent = getattr(torrent_info, "percent_done", None)
        new_progress = _normalize_progress_value(float(raw_percent) * 100.0 if raw_percent else 0.0)

        if cached_row is None:
            stats["insert"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            progress_value = new_progress
        else:
            torrent_info_id = cached_row["info_id"]
            create_time = cached_row["create_time"] or current_time
            old_progress = _normalize_progress_value(cached_row["progress"])
            progress_value = old_progress if abs(new_progress - old_progress) < 0.5 else new_progress

        torrent_data = {
            "info_id": torrent_info_id,
            "downloader_id": bt_downloader.downloader_id,
            "downloader_name": bt_downloader.nickname,
            "torrent_id": torrent_info.id,
            "hash": torrent_hash,
            "name": torrent_info.name,
            "status": TorrentStatusMapper.resolve_transmission_status(torrent_info.status, torrent_info.error),
            "error_reason": TorrentStatusMapper.extract_transmission_error_reason(torrent_info),
            "save_path": torrent_info.download_dir,
            "size": torrent_info.total_size,
            "progress": progress_value,
            "torrent_file": torrent_info.torrent_file,
            "added_date": torrent_info.added_date,
            "completed_date": torrent_info.done_date if torrent_info.done_date else None,
            "tags": ",".join(torrent_info.labels) if hasattr(torrent_info, "labels") and torrent_info.labels else "",
            "enabled": 1,
            "create_time": create_time,
            "create_by": "admin",
            "update_time": current_time,
            "update_by": "admin",
            "dr": 0,
        }
        ratio_stats.observe(
            apply_normalized_ratio_fields(
                torrent_data,
                raw_ratio=getattr(torrent_info, "ratio", MISSING_RATIO_VALUE),
                raw_ratio_limit=getattr(torrent_info, "seed_ratio_limit", MISSING_RATIO_VALUE),
                is_insert=cached_row is None,
            )
        )

        if cached_row is None:
            to_insert.append(torrent_data)
        else:
            # ✅ 阶段 2.5：整行变更检测，无变化真正跳过（修正 skip 语义 bug）
            if has_torrent_info_changes(cached_row, torrent_data):
                stats["update"] += 1
                to_update.append(torrent_data)
            else:
                stats["skip"] += 1
        last_processed_hash = torrent_hash

    phase_times["diff"] = (time.monotonic() - phase_start) * 1000.0

    ratio_stats.log_summary(
        logger,
        context=f"transmission-info:{bt_downloader.downloader_id}",
    )

    # ✅ 去重保护（双重保护机制）
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    # ✅ 阶段 2.5：用公共 bulk_upsert_with_retry（内含 db_write_scope + retry）
    try:
        write_start = time.monotonic()
        await bulk_upsert_with_retry(
            db,
            to_insert,
            to_update,
            model=TorrentInfo,
            label=f"[TR_INFO_SYNC] {bt_downloader.nickname}",
        )
        phase_times["write"] += (time.monotonic() - write_start) * 1000.0
        total_elapsed = time.monotonic() - run_start
        records_per_second = processed_count / total_elapsed if total_elapsed > 0 else 0.0
        logger.info(
            f"[TR_INFO_SYNC] {bt_downloader.nickname} 完成: 插入 {stats['insert']}, "
            f"更新 {stats['update']}, 跳过 {stats['skip']}, "
            f"partial={budget_reason is not None}, budget_reason={budget_reason}, "
            f"downloader_concurrency={downloader_concurrency}, "
            f"phase_ms=fetch={phase_times['fetch']:.1f},normalize={phase_times['normalize']:.1f},"
            f"diff={phase_times['diff']:.1f},write={phase_times['write']:.1f}, "
            f"rows_buffered={buffered_peak}, records_per_second={records_per_second:.1f}, "
            f"yield_count={yield_count}"
        )
        if budget_reason is not None:
            # 单轮预算到期：已处理部分写入完成，本轮结果为 partial（部分成果）
            logger.warning(
                f"[TR_INFO_SYNC] {bt_downloader.nickname} 单轮预算到期 "
                f"(budget_reason={budget_reason})，已处理 {processed_count}/"
                f"{len(torrent_info_list)} 个种子，本轮结果为 partial"
            )
    except Exception as e:
        await db.rollback()
        logger.error(f"[TR_INFO_SYNC] {bt_downloader.nickname} 失败: {e}")
        raise

    cycle_complete = budget_reason is None and processed_count >= pending_torrent_count
    await _emit_info_progress(progress_callback, last_processed_hash)
    if cycle_complete:
        _TR_FULL_SYNC_DONE[downloader_id] = True
        if force_full_sync:
            _TR_LAST_FULL_SYNC[downloader_id] = now_ts
    if progress_callback is None:
        return None
    return {
        "cursor": (
            None
            if cycle_complete
            else (_build_info_cursor(last_processed_hash) if last_processed_hash else cursor_before)
        ),
        "cycle_complete": cycle_complete,
        "partial": not cycle_complete,
        "budget_reason": budget_reason,
        "processed": processed_count,
        "total": pending_torrent_count,
    }


# ==================== Tracker-Only 同步函数 ====================
# 专用于 TrackerSyncTask，只同步 tracker_info 表，不修改 torrent_info 表


# 分批 commit 的粒度：每处理多少个种子提交一次事务
# 可通过环境变量 TRACKER_ONLY_COMMIT_BATCH 覆盖，默认 1000（权衡：减少提交次数 vs 单次事务锁持有时间）
_TRACKER_ONLY_COMMIT_BATCH = int(os.environ.get("TRACKER_ONLY_COMMIT_BATCH", "1000"))


def _validate_tracker_only_params(downloader: BtDownloaders, client: Any) -> tuple:
    """
    tracker-only 同步函数的公共输入校验。
    返回 (downloader_id, nickname) 或抛出 ValueError。
    """
    if not downloader:
        raise ValueError("downloader 参数为空")
    if not client:
        raise ValueError("client 参数为空")
    downloader_id = getattr(downloader, "downloader_id", None)
    if not downloader_id:
        raise ValueError("downloader_id 为空")
    nickname = getattr(downloader, "nickname", "unknown")
    return downloader_id, nickname


async def _query_hash_to_info_id(
    db: AsyncSession, downloader_id: int, log_prefix: str, nickname: str
) -> Dict[str, int]:
    """从数据库查询 hash -> info_id 映射，返回字典。"""
    query_start = datetime.now()
    result = await db.execute(
        select(TorrentInfo.hash, TorrentInfo.info_id)
        .filter(TorrentInfo.downloader_id == downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    hash_to_info_id = {row.hash: row.info_id for row in result.all()}
    query_duration = (datetime.now() - query_start).total_seconds()
    logger.info(
        f"[{log_prefix}] 查询到 {len(hash_to_info_id)} 个种子映射，"
        f"耗时 {query_duration:.3f}s，downloader={nickname}"
    )
    return hash_to_info_id


async def _batch_commit_tracker_sync(
    db: AsyncSession,
    tracker_count: int,
    tracker_total_rows: int,
    batch_start_count: int,
    batch_start_tracker_rows: int,
    error_count: int,
    log_prefix: str,
    is_final: bool = False,
) -> tuple:
    """
    分批提交或最终提交 tracker 同步结果。
    返回 (tracker_count, tracker_total_rows, error_count) 回退后的值。
    """
    try:
        await db.commit()
        return tracker_count, tracker_total_rows, error_count
    except Exception as commit_err:
        await db.rollback()
        batch_failed = tracker_count - batch_start_count
        error_count += batch_failed
        tracker_count = batch_start_count
        tracker_total_rows = batch_start_tracker_rows
        label = "最终提交失败" if is_final else "分批提交失败"
        logger.error(f"[{log_prefix}] {label}: {commit_err}")
        return tracker_count, tracker_total_rows, error_count


def _build_tracker_only_result(
    client_type: str, nickname: str, tracker_count: int, tracker_total_rows: int, error_count: int, torrent_count: int
) -> Dict[str, Any]:
    """构造 tracker-only 同步的返回结果。"""
    return {
        "status": "success" if error_count == 0 else "partial",
        "message": f"{client_type} {nickname} tracker 同步完成: {tracker_count} 个种子, {tracker_total_rows} 条记录",
        "tracker_count": tracker_count,
        "error_count": error_count,
        "tracker_total_rows": tracker_total_rows,
        "torrent_count": torrent_count,
        "nickname": nickname,
    }


async def _ensure_session_active(db: AsyncSession) -> None:
    """确保数据库 session 处于活跃事务状态（子函数 rollback 后恢复）。"""
    if not db.in_transaction():
        await db.begin()
        return
    # 事务存在但可能处于失败状态，rollback 后依赖 autobegin 恢复
    if not db.is_active:
        await db.rollback()


async def qb_sync_trackers_only_async(
    db: AsyncSession,
    downloader: BtDownloaders,
    client: Any,
    *,
    cursor: Optional[str] = None,
    deadline: Optional[float] = None,
    record_budget: Optional[int] = None,
) -> Dict[str, Any]:
    """
    qBittorrent 专用 Tracker-only 同步

    只从数据库查询种子的 hash->info_id 映射，从下载器获取 tracker 数据，
    调用 sync_add_tracker_async 写入 tracker_info 表。
    不修改 torrent_info 表，不执行种子文件备份。

    W3-1 第二部分（持久化 cursor 续跑 + cycle 语义，叠加在 W3-1a 有界队列与
    单轮预算之上）：
    - 待处理列表按 hash 字典序稳定排序（enrich 与批量写入共用同一顺序）；
    - cursor 为透明 JSON 文本 {"last_hash": "..."}：显式参数优先，缺省时从
      运行期检查点（get_run_checkpoint）读取；跳过 ≤ last_hash 的已 durable hash；
    - 每批 sync_trackers_batch_async durable commit 成功后通过 push_sync_progress
      推进持久化 cursor（滞后语义：cursor 绝不越过未落盘数据）；
    - 第 N 批提交失败 → 停止本轮（cursor 停在最后成功批），重启后从该处续跑；
    - 预算（deadline/record_budget 透传，None 回落配置）到期 → partial=True，
      cursor 停在最后 durable 批的最后 hash；
    - 全部处理完且全部批 commit 成功 → cycle_complete=True + cursor=None
      （下一轮从头开始新周期；last_full_sync_at 由 Coordinator 终态更新）。

    Args:
        db: 异步数据库会话。
        downloader: 下载器 ORM 对象。
        client: qBittorrent 客户端（只从 app.state.store 获取）。
        cursor: 续跑游标 JSON（None 时尝试从运行期检查点上下文读取）。
        deadline: 单轮时间预算覆盖（秒；None 回落 settings.QB_TRACKER_RUN_BUDGET_SECONDS）。
        record_budget: 单轮记录数预算覆盖（None 回落 settings.QB_TRACKER_MAX_TORRENTS_PER_RUN）。

    Returns:
        结果 dict（status/message/tracker_count/error_count/tracker_total_rows/
        torrent_count/nickname 契约不变），附加 W3-1 续跑元数据：
        partial / cursor / cycle_complete / cycle_progress / budget_reason。
    """
    LOG_PREFIX = "QB_TRACKER_ONLY"

    # === 输入校验 ===
    try:
        downloader_id, nickname = _validate_tracker_only_params(downloader, client)
    except ValueError as e:
        return {"status": "failed", "message": str(e), "tracker_count": 0, "torrent_count": 0}

    task_start = datetime.now()

    # W3-1 第二部分：续跑游标优先取显式参数；缺省时从运行期检查点上下文读取
    cursor_before = cursor
    if cursor_before is None:
        try:
            from app.services.sync_coordinator import get_run_checkpoint  # noqa: PLC0415 - 延迟导入防循环

            run_ctx = get_run_checkpoint(downloader_id, "tracker")
            if run_ctx is not None:
                cursor_before = run_ctx.get("cursor")
        except Exception as e:  # noqa: BLE001 - 检查点读取失败按从头处理
            logger.warning(f"[{LOG_PREFIX}] 读取续跑检查点失败: {e}")

    # === 第1步：从数据库查询 hash -> info_id 映射 ===
    hash_to_info_id = await _query_hash_to_info_id(db, downloader_id, LOG_PREFIX, nickname)

    if not hash_to_info_id:
        return {
            **_qb_tracker_cycle_meta(False, None, True, 0, 0, None),
            "status": "success",
            "message": f"下载器 {nickname} 无已同步种子，跳过 tracker 同步",
            "tracker_count": 0,
            "torrent_count": 0,
            "nickname": nickname,
        }

    # === 第2步：全量获取种子列表（不分批，避免分批 offset 导致 tracker 数据不完整） ===
    fetch_start = datetime.now()
    torrent_info_list = await call_downloader_api(
        str(downloader.downloader_id),
        DownloadLane.TRACKER,
        client.torrents_info,
        operation="qb_torrents_info_for_tracker_sync",
    )
    fetch_duration = (datetime.now() - fetch_start).total_seconds()
    logger.info(f"[{LOG_PREFIX}] 全量获取到 {len(torrent_info_list)} 个种子，耗时 {fetch_duration:.3f}s")

    if not torrent_info_list:
        return {
            **_qb_tracker_cycle_meta(False, None, True, 0, 0, None),
            "status": "success",
            "message": f"下载器 {nickname} 无在线种子",
            "tracker_count": 0,
            "torrent_count": 0,
            "nickname": nickname,
        }

    # === 第3步：过滤出数据库中已存在的种子 + 稳定排序（hash 字典序） ===
    existing_torrents = []
    skipped_new = 0
    for t in torrent_info_list:
        t_hash = _qb_get_attr(t, "hash")
        if t_hash and t_hash in hash_to_info_id:
            existing_torrents.append(t)
        else:
            skipped_new += 1
    if skipped_new > 0:
        logger.debug(f"[{LOG_PREFIX}] 跳过 {skipped_new} 个数据库中不存在的种子")
    # W3-1 第二部分：enrich 与批量写入共用同一稳定顺序（续跑游标依赖该顺序）
    existing_torrents.sort(key=lambda t: str(_qb_get_attr(t, "hash") or ""))
    total_torrents = len(existing_torrents)

    if not existing_torrents:
        return {
            **_qb_tracker_cycle_meta(False, None, True, 0, 0, None),
            "status": "success",
            "message": f"下载器 {nickname} 无需同步 tracker 的种子",
            "tracker_count": 0,
            "torrent_count": 0,
            "nickname": nickname,
        }

    # === 第4步：获取 tracker 数据（有界队列 + 单轮预算 + cursor 续跑） ===
    enrich_start = datetime.now()
    _enrich_cursor, budget_reason = await _enrich_qb_torrents_with_trackers(
        client,
        existing_torrents,
        str(downloader.downloader_id),
        max_torrents_per_run=record_budget,
        run_budget_seconds=deadline,
        cursor=cursor_before,
    )
    enrich_duration = (datetime.now() - enrich_start).total_seconds()
    logger.info(f"[{LOG_PREFIX}] 获取 tracker 数据完成，耗时 {enrich_duration:.3f}s")

    # === 第5步：批量写入 tracker_info 表（阶段 2.5 改造 + W3-1 续跑推进） ===
    # 累计多个种子的 tracker_rows，达 batch_size 后统一 upsert + 变更检测 + db_write_scope。
    batch_size = settings.SYNC_DB_COMMIT_BATCH_SIZE  # 默认 200，对齐治理规范
    accumulated_rows: list[dict] = []
    accumulated_info_ids: set = set()
    tracker_count = 0
    tracker_total_rows = 0
    error_count = 0
    batch_stats_total = {"insert": 0, "update": 0, "skip": 0, "removed": 0}
    current_time = datetime.now()
    flush_failed = False  # 某批 durable commit 失败 → 停止本轮，cursor 停在最后成功批
    batch_committed_count = 0
    durable_cursor: Optional[str] = None  # 最后 durable 批的最后 hash 的游标 JSON
    batch_last_hash: Optional[str] = None  # 当前累计批内最后处理的 hash

    # enrich 只会为远端请求成功的对象写入标记。写入阶段只消费从上次
    # durable cursor 开始的“连续成功前缀”，这样即使中间某个 hash 的远端
    # 请求失败，也不会把后续 hash 写入并推进游标越过失败点。
    cursor_last_hash = _parse_qb_tracker_cursor(cursor_before)
    pending_torrent_count = sum(
        1
        for torrent_info in existing_torrents
        if (torrent_hash := str(_qb_get_attr(torrent_info, "hash") or ""))
        and (cursor_last_hash is None or torrent_hash > cursor_last_hash)
    )
    durable_torrents: list[Any] = []
    enrichment_error_count = 0
    for torrent_info in existing_torrents:
        torrent_hash = str(_qb_get_attr(torrent_info, "hash") or "")
        if not torrent_hash or (cursor_last_hash is not None and torrent_hash <= cursor_last_hash):
            continue
        enriched = _qb_get_attr(torrent_info, "_btdeck_tracker_enriched", None)
        if enriched is True:
            durable_torrents.append(torrent_info)
            continue
        if enriched is False:
            enrichment_error_count += 1
        elif budget_reason is None:
            # 没有预算截止却缺少成功标记，说明 enrich 返回的数据无法确认，
            # 按失败处理，避免在不确定时清除周期游标。
            enrichment_error_count += 1
        # 未标记表示本轮预算已停止生产，后续 hash 尚未开始，不能计为错误。
        break

    async def _flush_batch() -> bool:
        """提交当前累计 batch；返回是否真正发生提交（累计行非空且成功）。"""
        nonlocal accumulated_rows, accumulated_info_ids, error_count
        if not accumulated_rows:
            # 远端成功但没有 tracker 行时也要允许推进游标；这不是一次 DB
            # 写入，但该 hash 的结果已经确定且可安全续跑。
            return True
        try:
            stats = await sync_trackers_batch_async(db, accumulated_rows, current_time)
            for k in batch_stats_total:
                batch_stats_total[k] += stats.get(k, 0)
            return True
        except Exception as batch_err:
            error_count += 1
            logger.error(f"[{LOG_PREFIX}] sync_trackers_batch_async 失败: {batch_err}")
            await _ensure_session_active(db)
            return False
        finally:
            # 无论成败都清空累计（失败路径由调用方决定是否停止本轮）
            accumulated_rows = []
            accumulated_info_ids = set()

    async def _push_tracker_cursor(cursor_value: Optional[str]) -> None:
        """批 durable commit 后推进持久化 cursor（W3-1 滞后语义）。

        仅当运行期存在活动检查点上下文（Coordinator 运行中）时真正落库；
        直接调用（无检查点上下文）时由 Coordinator 在下载器级统一推进最终 cursor。
        """
        if cursor_value is None:
            return
        try:
            from app.services.sync_coordinator import push_sync_progress  # noqa: PLC0415 - 延迟导入防循环

            await push_sync_progress(
                downloader_id,
                "tracker",
                cursor=cursor_value,
                detail={"committed": tracker_total_rows, "batches": batch_committed_count},
            )
        except Exception as push_err:  # noqa: BLE001 - 检查点推进失败不阻断写入
            logger.warning(f"[{LOG_PREFIX}] 推进 tracker 检查点失败: {push_err}")

    error_count = enrichment_error_count
    for torrent_info in durable_torrents:
        torrent_hash = _qb_get_attr(torrent_info, "hash")
        if not torrent_hash:
            continue
        info_id = hash_to_info_id.get(torrent_hash)
        if not info_id:
            continue
        try:
            rows, _urls = extract_tracker_rows_from_torrent(torrent_info, info_id, "qbittorrent", current_time)
            accumulated_rows.extend(rows)
            accumulated_info_ids.add(info_id)
            tracker_count += 1
            tracker_total_rows += len(rows)
            batch_last_hash = str(torrent_hash)
        except Exception as e:
            # 提取失败也必须停止当前有序前缀；继续消费后续 hash 会让
            # durable cursor 越过这个未落盘的 hash，重启后永久遗漏。
            error_count += 1
            logger.error(f"[{LOG_PREFIX}] extract_tracker_rows 失败: hash={torrent_hash}, error={e}")
            await _ensure_session_active(db)
            break

        # 累计达 batch_size 行后提交（按 tracker 行数控制，非种子数）
        if len(accumulated_rows) >= batch_size:
            if await _flush_batch():
                batch_committed_count += 1
                if batch_last_hash is not None:
                    durable_cursor = _build_qb_tracker_cursor(batch_last_hash)
                    await _push_tracker_cursor(durable_cursor)
            else:
                flush_failed = True
                break
            batch_last_hash = None

    # 最终提交剩余（仅当本轮未因批失败提前终止）
    if not flush_failed and await _flush_batch():
        batch_committed_count += 1
        if batch_last_hash is not None:
            durable_cursor = _build_qb_tracker_cursor(batch_last_hash)
            await _push_tracker_cursor(durable_cursor)

    # W3-1 第二部分：cycle 语义与观测元数据
    cycle_complete = (
        budget_reason is None
        and not flush_failed
        and error_count == 0
        and len(durable_torrents) == pending_torrent_count
    )
    partial = budget_reason is not None or flush_failed or error_count > 0
    final_cursor: Optional[str] = None if cycle_complete else durable_cursor
    if cycle_complete:
        processed_count = total_torrents
    else:
        durable_last_hash = _parse_qb_tracker_cursor(durable_cursor)
        if durable_last_hash is not None:
            processed_count = sum(
                1 for t in existing_torrents if str(_qb_get_attr(t, "hash") or "") <= durable_last_hash
            )
        else:
            processed_count = 0

    total_duration = (datetime.now() - task_start).total_seconds()
    logger.info(
        f"[{LOG_PREFIX}] {nickname} 完成: "
        f"{tracker_count}/{total_torrents} 个种子, "
        f"{tracker_total_rows} 条 tracker 记录, "
        f"insert={batch_stats_total['insert']} update={batch_stats_total['update']} "
        f"skip={batch_stats_total['skip']} removed={batch_stats_total['removed']}, "
        f"{error_count} 个失败, "
        f"总耗时 {total_duration:.2f}s, "
        f"cursor_before: {cursor_before or 'None'} cursor_after: {final_cursor or 'None'} "
        f"cycle_complete: {cycle_complete} cycle_progress: {processed_count}/{total_torrents} "
        f"budget_reason: {budget_reason} partial: {partial}"
    )

    result_dict = _build_tracker_only_result(
        "qBittorrent", nickname, tracker_count, tracker_total_rows, error_count, total_torrents
    )
    result_dict.update(
        _qb_tracker_cycle_meta(partial, final_cursor, cycle_complete, processed_count, total_torrents, budget_reason)
    )
    return result_dict


async def tr_sync_trackers_only_async(db: AsyncSession, downloader: BtDownloaders, client: Any) -> Dict[str, Any]:
    """
    Transmission 专用 Tracker-only 同步

    Transmission 的 get_torrents(arguments=TR_BASE_FIELDS) 返回中已包含 trackerStats，
    不需要额外 API 调用来获取 tracker 数据，效率远高于 qBittorrent。

    TR 的 tracker_stats 字段名与 QB 不同，sync_add_tracker_async 内部已做字段映射：
    - announce 统计字段 -> 归一化的 last_announce_succeeded 状态码
    - tracker_status.last_announce_result    -> last_announce_msg
    - scrape 统计字段   -> 归一化的 last_scrape_succeeded 状态码
    - tracker_status.last_scrape_result      -> last_scrape_msg
    """
    LOG_PREFIX = "TR_TRACKER_ONLY"

    # === 输入校验 ===
    try:
        downloader_id, nickname = _validate_tracker_only_params(downloader, client)
    except ValueError as e:
        return {"status": "failed", "message": str(e), "tracker_count": 0, "torrent_count": 0}

    task_start = datetime.now()

    # === 第1步：从数据库查询 hash -> info_id 映射 ===
    hash_to_info_id = await _query_hash_to_info_id(db, downloader_id, LOG_PREFIX, nickname)

    if not hash_to_info_id:
        return {
            "status": "success",
            "message": f"下载器 {nickname} 无已同步种子，跳过 tracker 同步",
            "tracker_count": 0,
            "torrent_count": 0,
            "nickname": nickname,
        }

    # === 第2步：从下载器获取种子列表（含 trackerStats） ===
    fetch_start = datetime.now()
    torrent_info_list = await call_downloader_api(
        str(downloader.downloader_id),
        DownloadLane.TRACKER,
        client.get_torrents,
        kwargs={"arguments": TR_BASE_FIELDS},
        operation="tr_get_torrents_for_tracker_sync",
    )
    fetch_duration = (datetime.now() - fetch_start).total_seconds()
    logger.info(f"[{LOG_PREFIX}] 获取到 {len(torrent_info_list)} 个种子（含 trackerStats），耗时 {fetch_duration:.3f}s")

    if not torrent_info_list:
        return {
            "status": "success",
            "message": f"下载器 {nickname} 无在线种子",
            "tracker_count": 0,
            "torrent_count": 0,
            "nickname": nickname,
        }

    # === 第3步：过滤已存在种子并同步 tracker ===
    tracker_count = 0
    tracker_total_rows = 0  # 写入的 tracker 记录总条数（估算值，不含提交失败的部分）
    error_count = 0
    skipped_new = 0
    batch_size = settings.SYNC_DB_COMMIT_BATCH_SIZE
    accumulated_rows: list[dict] = []
    accumulated_info_ids: set = set()
    batch_stats_total = {"insert": 0, "update": 0, "skip": 0, "removed": 0}
    current_time = datetime.now()

    async def _flush_batch_tr() -> None:
        nonlocal accumulated_rows, accumulated_info_ids, error_count
        if not accumulated_rows:
            return
        try:
            stats = await sync_trackers_batch_async(db, accumulated_rows, current_time)
            for k in batch_stats_total:
                batch_stats_total[k] += stats.get(k, 0)
        except Exception as batch_err:
            error_count += 1
            logger.error(f"[{LOG_PREFIX}] sync_trackers_batch_async 失败: {batch_err}")
            await _ensure_session_active(db)
        accumulated_rows = []
        accumulated_info_ids = set()

    for torrent_info in torrent_info_list:
        torrent_hash = getattr(torrent_info, "hashString", None)
        if not torrent_hash:
            continue
        info_id = hash_to_info_id.get(torrent_hash)
        if not info_id:
            skipped_new += 1
            continue

        # 预检：确保 tracker_stats 存在且非空，跳过无 tracker 的种子
        tracker_stats = getattr(torrent_info, "tracker_stats", None) or []
        if not tracker_stats:
            continue

        try:
            rows, _urls = extract_tracker_rows_from_torrent(torrent_info, info_id, "transmission", current_time)
            accumulated_rows.extend(rows)
            accumulated_info_ids.add(info_id)
            tracker_count += 1
            tracker_total_rows += len(rows)
        except Exception as e:
            error_count += 1
            logger.error(f"[{LOG_PREFIX}] extract_tracker_rows 失败: hash={torrent_hash}, error={e}")
            await _ensure_session_active(db)
            continue

        if len(accumulated_rows) >= batch_size:
            await _flush_batch_tr()

    await _flush_batch_tr()

    total_duration = (datetime.now() - task_start).total_seconds()
    if skipped_new > 0:
        logger.debug(f"[{LOG_PREFIX}] 跳过 {skipped_new} 个数据库中不存在的种子")
    logger.info(
        f"[{LOG_PREFIX}] {nickname} 完成: "
        f"{tracker_count}/{tracker_count + skipped_new} 个种子, "
        f"{tracker_total_rows} 条 tracker 记录, "
        f"insert={batch_stats_total['insert']} update={batch_stats_total['update']} "
        f"skip={batch_stats_total['skip']} removed={batch_stats_total['removed']}, "
        f"{error_count} 个失败, "
        f"总耗时 {total_duration:.2f}s"
    )

    return _build_tracker_only_result(
        "Transmission", nickname, tracker_count, tracker_total_rows, error_count, tracker_count + skipped_new
    )
