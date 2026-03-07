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
import os
import json
import threading
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

from app.database import AsyncSessionLocal
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo as trackerInfoModel
from qbittorrentapi import Client as qbClient
from qbittorrentapi.exceptions import APIConnectionError, LoginFailed, APIError
from transmission_rpc import Client as trClient, TransmissionError
from app.core.torrent_file_backup import TorrentFileBackupService
from app.core.path_mapping import PathMappingService
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.core.filename_utils import FilenameUtils
from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService
from app.models.torrent_file_backup import TorrentFileBackup
from app.models.setting_templates import DownloaderTypeEnum
import json

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

def _resolve_legacy_backup_file_path(info_id: str, torrent_name: str) -> Optional[str]:
    backup_dir = os.environ.get(
        'BACKUP_TORRENT_DIR',
        TorrentFileBackupService.DEFAULT_BACKUP_DIR
    )
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
                BtDownloaders.downloader_id == downloader_id,
                BtDownloaders.dr == 0
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
    base_delay: float = 1.0,
    error_context: str = "数据库操作",
    rollback: Optional[Callable[[], Awaitable[None]]] = None
):
    """
    在数据库锁定时重试操作（指数退避策略）

    Args:
        func: 要执行的异步函数
        max_retries: 最大重试次数（默认3次）
        base_delay: 基础延迟时间（秒，指数增长）
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
                    # 指数退避：1秒, 2秒, 4秒
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"{error_context}失败（数据库锁定），"
                        f"第{attempt + 1}/{max_retries}次重试，"
                        f"等待{delay:.1f}秒后重试..."
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"{error_context}失败：已达最大重试次数（{max_retries}次）"
                    )
                # 不是锁定错误，直接抛出
                raise
        except Exception as e:
            # 其他类型的错误，直接抛出
            raise

    # 所有重试都失败，抛出最后一次的错误
    if last_error:
        raise last_error


# ==============================================================================
# 基础 CRUD 异步函数
# ==============================================================================

async def get_torrent_by_hash_async(
    db: AsyncSession,
    hash_value: str,
    downloader_id: Optional[str] = None
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
    filters = [
        TorrentInfo.hash == hash_value,
        TorrentInfo.dr == 0  # 只查询未删除的记录
    ]

    # 如果提供了 downloader_id，则限定查询范围
    if downloader_id is not None:
        filters.append(TorrentInfo.downloader_id == downloader_id)

    result = await db.execute(select(TorrentInfo).filter(*filters))

    # 使用 first() 代替 scalar_one_or_none()，避免多行异常
    # 如果存在多条重复记录（历史遗留问题），返回第一条
    return result.scalars().first()


async def update_torrent_async(db: AsyncSession, torrent_id: str, torrent_data: Dict[str, Any], commit: bool = True) -> Optional[TorrentInfo]:
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
    result = await db.execute(
        select(TorrentInfo).filter(TorrentInfo.info_id == torrent_id)
    )
    db_torrent = result.scalar_one_or_none()

    if not db_torrent:
        return None

    try:
        # 更新对象属性
        for key, value in torrent_data.items():
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
    db: AsyncSession,
    tracker_id: str,
    update_data: Dict[str, Any],
    max_retries: int = MAX_OPTIMISTIC_LOCK_RETRIES
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
                select(trackerInfoModel).filter(
                    trackerInfoModel.tracker_id == tracker_id,
                    trackerInfoModel.dr == 0
                )
            )
            tracker = result.scalar_one_or_none()

            if tracker is None:
                logger.warning(f"乐观锁更新失败: tracker {tracker_id} 不存在或已删除")
                return False

            old_version = tracker.version

            # 创建新的数据字典副本，避免污染传入的参数
            final_update_data = update_data.copy()
            final_update_data['version'] = old_version + 1

            # 执行更新（带版本检查）
            from sqlalchemy import update
            update_stmt = (
                update(trackerInfoModel)
                .where(
                    trackerInfoModel.tracker_id == tracker_id,
                    trackerInfoModel.version == old_version,
                    trackerInfoModel.dr == 0
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
    max_retries: int = MAX_OPTIMISTIC_LOCK_RETRIES
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
                    trackerInfoModel.dr == 1
                )
            )
            deleted_tracker = result.scalar_one_or_none()

            if deleted_tracker is None:
                return False

            # 恢复记录（保留 create_time/create_by，更新其他字段）
            # 使用 get() 并提供默认值，防止 None 写入数据库
            update_data = {
                'dr': 0,
                'tracker_name': tracker_data.get('tracker_name', deleted_tracker.tracker_name),
                'last_announce_succeeded': tracker_data.get('last_announce_succeeded', 0),
                'last_announce_msg': tracker_data.get('last_announce_msg', ''),
                'last_scrape_succeeded': tracker_data.get('last_scrape_succeeded', 0),
                'last_scrape_msg': tracker_data.get('last_scrape_msg', ''),
                'update_time': current_time,
                'update_by': 'admin',
                'version': deleted_tracker.version + 1
            }

            from sqlalchemy import update
            update_stmt = (
                update(trackerInfoModel)
                .where(
                    trackerInfoModel.tracker_id == deleted_tracker.tracker_id,
                    trackerInfoModel.version == deleted_tracker.version,
                    trackerInfoModel.dr == 1
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
    db: AsyncSession,
    torrent_info_id: str,
    current_tracker_urls: set,
    current_time: datetime
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
            logger.warning(
                "current_tracker_urls is empty, skip mark-removed trackers"
            )
            return

        result = await db.execute(
            update(trackerInfoModel)
            .where(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.dr == 0,
                ~trackerInfoModel.tracker_url.in_(current_tracker_urls)
            )
            .values(dr=1, update_time=current_time, update_by='system')
        )

        removed_count = result.rowcount or 0
        if removed_count > 0:
            logger.info(f"Marked {removed_count} removed trackers")

    except Exception as e:
        logger.error(f"Mark removed trackers failed: {e}")
        await db.rollback()

async def mark_removed_trackers_async(
    db: AsyncSession,
    torrent_info_id: str,
    current_tracker_urls: set,
    current_time: datetime
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
            logger.warning(f"current_tracker_urls 为空集合，跳过标记已移除 tracker 的操作")
            return

        # 查询所有活跃的 tracker
        result = await db.execute(
            select(trackerInfoModel).filter(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.dr == 0
            )
        )
        existing_trackers = result.scalars().all()

        removed_count = 0
        from sqlalchemy import update

        for existing_tracker in existing_trackers:
            if existing_tracker.tracker_url not in current_tracker_urls:
                # 使用乐观锁标记为删除
                update_data = {
                    'dr': 1,
                    'update_time': current_time,
                    'update_by': 'system',
                    'version': existing_tracker.version + 1
                }

                update_stmt = (
                    update(trackerInfoModel)
                    .where(
                        trackerInfoModel.tracker_id == existing_tracker.tracker_id,
                        trackerInfoModel.version == existing_tracker.version,
                        trackerInfoModel.dr == 0
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
    db: AsyncSession,
    torrent_info_id: str,
    tracker_url: str,
    tracker_data: Dict[str, Any],
    current_time: datetime
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
                trackerInfoModel.dr == 0
            )
        )
        # 修复：使用 first() 代替 scalar_one_or_none()
        # 如果存在多条重复记录（历史遗留问题），取第一条
        active_tracker = result.scalars().first()

        if active_tracker is not None:
            # 准备更新数据（保留 create_time/create_by）
            # 修复P3-2: 明确区分"字段不存在"和"字段值为None"
            update_data = {
                'tracker_name': tracker_data.get('tracker_name') if tracker_data.get('tracker_name') is not None else active_tracker.tracker_name,
                'last_announce_succeeded': tracker_data.get('last_announce_succeeded') if tracker_data.get('last_announce_succeeded') is not None else active_tracker.last_announce_succeeded,
                'last_announce_msg': tracker_data.get('last_announce_msg') if tracker_data.get('last_announce_msg') is not None else active_tracker.last_announce_msg,
                'last_scrape_succeeded': tracker_data.get('last_scrape_succeeded') if tracker_data.get('last_scrape_succeeded') is not None else active_tracker.last_scrape_succeeded,
                'last_scrape_msg': tracker_data.get('last_scrape_msg') if tracker_data.get('last_scrape_msg') is not None else active_tracker.last_scrape_msg,
                'update_time': current_time,
                'update_by': 'admin'
            }

            # 使用乐观锁更新
            success = await update_tracker_with_optimistic_lock_async(
                db, active_tracker.tracker_id, update_data
            )

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
                trackerInfoModel.dr == 1
            )
        )
        # 修复：使用 first() 代替 scalar_one_or_none()
        deleted_tracker = result.scalars().first()

        if deleted_tracker is not None:
            # 恢复已删除的记录
            success = await restore_deleted_tracker_async(
                db, torrent_info_id, tracker_url, tracker_data, current_time
            )

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


async def sync_add_tracker_async(
    db: AsyncSession,
    downloader_type: str,
    mode: str,
    torrent_info: Any,
    torrent_info_id: str
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
            trackers_data = getattr(torrent_info, 'trackers', None)
            if callable(trackers_data):
                trackers_data = trackers_data()
            trackers_data = trackers_data or []
        except Exception as e:
            logger.error(f"Failed to get qbittorrent trackers: {str(e)}")
            trackers_data = []

        for tracker in trackers_data:
            try:
                url = tracker.get('url')
                if not url:
                    continue
                url = str(url)
                if 'DHT' in url or 'PeX' in url or 'LSD' in url:
                    continue
                current_tracker_urls.add(url)
                tracker_rows.append({
                    'tracker_id': str(uuid.uuid4()),
                    'torrent_info_id': torrent_info_id,
                    'tracker_name': url,
                    'tracker_url': url,
                    'last_announce_succeeded': tracker.get('status'),
                    'last_announce_msg': tracker.get('msg'),
                    'last_scrape_succeeded': tracker.get('status'),
                    'last_scrape_msg': tracker.get('msg'),
                    'create_time': current_time,
                    'create_by': 'admin',
                    'update_time': current_time,
                    'update_by': 'admin',
                    'dr': 0
                })
            except Exception as tracker_err:
                logger.error(f"Failed to process tracker [{tracker}]: {str(tracker_err)}")
                continue

    elif downloader_type == "transmission":
        tracker_stats = getattr(torrent_info, 'tracker_stats', None) or []
        for tracker_status in tracker_stats:
            tracker_url = None
            try:
                tracker_url = tracker_status.fields.get('announce')
            except Exception:
                tracker_url = None
            if not tracker_url:
                continue
            current_tracker_urls.add(tracker_url)
            tracker_rows.append({
                'tracker_id': str(uuid.uuid4()),
                'torrent_info_id': torrent_info_id,
                'tracker_name': tracker_status.site_name,
                'tracker_url': tracker_url,
                'last_announce_succeeded': tracker_status.last_announce_succeeded,
                'last_announce_msg': tracker_status.last_announce_result,
                'last_scrape_succeeded': tracker_status.last_scrape_succeeded,
                'last_scrape_msg': tracker_status.last_scrape_result,
                'create_time': current_time,
                'create_by': 'admin',
                'update_time': current_time,
                'update_by': 'admin',
                'dr': 0
            })

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
                    active_tracker.dr == 0
                )
            )
            .values(dr=0, update_time=current_time, update_by='admin')
        )

    if tracker_rows:
        # Avoid resurrecting soft-deleted rows during upsert.
        from sqlalchemy import delete, tuple_

        # ✅ P1修复：添加row的None检查，避免AttributeError
        soft_deleted_pairs = {
            (row.get('torrent_info_id'), row.get('tracker_url'))
            for row in tracker_rows
            if row and isinstance(row, dict) and row.get('torrent_info_id') and row.get('tracker_url')
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
                    delete(trackerInfoModel)
                    .where(
                        trackerInfoModel.dr == 1,
                        tuple_(
                            trackerInfoModel.torrent_info_id,
                            trackerInfoModel.tracker_url
                        ).in_(list(soft_deleted_pairs))
                    )
                )

            # 插入新记录或更新现有记录
            stmt = sqlite_insert(trackerInfoModel).values(tracker_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=['torrent_info_id', 'tracker_url'],
                set_={
                    'tracker_name': stmt.excluded.tracker_name,
                    'last_announce_succeeded': stmt.excluded.last_announce_succeeded,
                    'last_announce_msg': stmt.excluded.last_announce_msg,
                    'last_scrape_succeeded': stmt.excluded.last_scrape_succeeded,
                    'last_scrape_msg': stmt.excluded.last_scrape_msg,
                    'update_time': current_time,
                    'update_by': 'admin',
                    'dr': 0
                }
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
    to_insert: List[Dict[str, Any]],
    to_update: List[Dict[str, Any]]
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
        key = (item.get('downloader_id'), item.get('hash'))
        if key not in seen_insert:
            seen_insert[key] = 'insert'
            deduped_insert.append(item)
        else:
            logger.warning(
                f"[去重保护] 发现重复插入: {item.get('name')} "
                f"(hash={item.get('hash')}, downloader_id={item.get('downloader_id')})"
            )

    # 去重待更新列表
    for item in to_update:
        key = (item.get('downloader_id'), item.get('hash'))
        if key not in seen_update:
            seen_update[key] = 'update'
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
            item for item in deduped_insert
            if (item.get('downloader_id'), item.get('hash')) not in conflicts
        ]
        logger.info("[去重保护] 已保留更新操作，移除冲突的插入操作")

    if len(to_insert) != len(deduped_insert) or len(to_update) != len(deduped_update):
        logger.info(
            f"[去重保护] 去重完成: 插入 {len(to_insert)}→{len(deduped_insert)}, "
            f"更新 {len(to_update)}→{len(deduped_update)}"
        )

    return deduped_insert, deduped_update


async def tr_add_torrents_async(db: AsyncSession, downloaders: List[Any]) -> None:
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

    Raises:
        ValueError: 当下载器列表为空时
    """
    # 添加空列表检查，防止IndexError
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    tr_client = trClient(
        host=bt_downloader.host,
        username=bt_downloader.username,
        password=bt_downloader.password,
        port=bt_downloader.port,
        protocol="http",
        timeout=TR_API_TIMEOUT
    )
    # 分批获取 Transmission 种子，避免超大响应导致超时
    # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
    base_torrents = await asyncio.to_thread(
        tr_client.get_torrents,
        arguments=TR_BASE_FIELDS
    )
    torrent_info_list = []
    total = len(base_torrents)

    # 非首次同步时，仅同步最近活跃的种子（降低数据量）
    downloader_id = str(bt_downloader.downloader_id)
    now_ts = datetime.now().timestamp()
    last_full_ts = _TR_LAST_FULL_SYNC.get(downloader_id, 0)
    force_full_sync = (now_ts - last_full_ts) >= TR_FULL_SYNC_INTERVAL_SECONDS

    if _TR_FULL_SYNC_DONE.get(downloader_id) and not force_full_sync:
        now_ts = datetime.now().timestamp()
        recent_threshold = now_ts - TR_ACTIVE_WINDOW_SECONDS
        active_torrents = []
        for t in base_torrents:
            activity_date = getattr(t, 'activity_date', None)
            if activity_date is None and hasattr(t, 'activityDate'):
                activity_date = getattr(t, 'activityDate', None)
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
            batch = base_torrents[i:i + TR_BATCH_SIZE]
            batch_ids = [t.id for t in batch if hasattr(t, 'id')]
            if not batch_ids:
                continue
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            detailed_batch = await asyncio.to_thread(
                tr_client.get_torrents,
                ids=batch_ids,
                arguments=TR_DETAIL_FIELDS
            )
            torrent_info_list.extend(detailed_batch)

    # 标记已完成首次全量同步
    _TR_FULL_SYNC_DONE[downloader_id] = True
    if force_full_sync:
        _TR_LAST_FULL_SYNC[downloader_id] = now_ts
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
            TorrentInfo.backup_file_path
        ).filter(
            TorrentInfo.downloader_id == bt_downloader.downloader_id
        ).filter(
            TorrentInfo.dr == 0
        )
    )
    existing_torrents_rows = result.all()

    # 构建内存字典：{hash: (info_id, create_time, progress, backup_file_path)}
    existing_torrents_cache = {
        row.hash: (row.info_id, row.create_time, row.progress, row.backup_file_path)
        for row in existing_torrents_rows
    }

    batch_query_duration = (datetime.now() - batch_query_start).total_seconds()
    logger.debug(
        f"[PERF] 批量查询完成：查询 {len(existing_torrents_cache)} 个种子，"
        f"耗时 {batch_query_duration:.3f} 秒"
    )

    # ⚡ 性能优化2：收集所有变更数据（不立即执行数据库操作）
    to_insert = []
    to_update = []
    torrent_info_map = {}

    stats = {
        'insert_count': 0,
        'update_count': 0,
        'skip_count': 0,
        'error_count': 0
    }

    # 第一阶段：收集数据
    tracker_source = "tr_detailed"
    for torrent_info in torrent_info_list:
        try:
            setattr(torrent_info, "_tracker_source", tracker_source)
        except Exception:
            pass
        cached_data = existing_torrents_cache.get(torrent_info.hashString)

        # 计算进度值
        raw_percent_done = getattr(torrent_info, 'percent_done', None) if hasattr(torrent_info, 'percent_done') else None
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
            stats['insert_count'] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            update_time = current_time
            progress_value = new_progress
            backup_file_path = None
        else:
            mode = "update"
            stats['update_count'] += 1
            torrent_info_id, create_time, old_progress_cached, backup_file_path = cached_data

            if create_time is None:
                create_time = current_time
            update_time = current_time

            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats['skip_count'] += 1
                logger.debug(f"进度未变化: {torrent_info.name}, 保留旧值 {old_progress:.2f}%")
            else:
                progress_value = new_progress
                logger.debug(f"进度更新: {torrent_info.name}, {old_progress:.2f}% → {new_progress:.2f}%")

        # 构建种子数据字典
        torrent_data = {
            'info_id': torrent_info_id,
            'downloader_id': bt_downloader.downloader_id,
            'downloader_name': bt_downloader.nickname,
            'torrent_id': torrent_info.id,
            'hash': torrent_info.hashString,
            'name': torrent_info.name,
            'status': convert_transmission_status(torrent_info.status),
            'save_path': torrent_info.download_dir,
            'size': torrent_info.total_size,
            'progress': progress_value,
            'torrent_file': torrent_info.torrent_file,
            'added_date': torrent_info.added_date,
            'completed_date': torrent_info.done_date if torrent_info.done_date else None,
            'ratio': torrent_info.ratio,
            'ratio_limit': torrent_info.seed_ratio_limit,
            'tags': ",".join(torrent_info.labels) if hasattr(torrent_info, 'labels') and torrent_info.labels else "",
            'category': "",
            'super_seeding': "",
            'enabled': 1,
            'create_time': create_time,
            'create_by': "admin",
            'update_time': update_time,
            'update_by': "admin",
            'backup_file_path': backup_file_path,
            'dr': 0
        }

        # 收集数据
        if mode == "insert":
            to_insert.append(torrent_data)
        else:
            to_update.append(torrent_data)

        # 保存映射关系
        torrent_info_map[torrent_info_id] = {
            'mode': mode,
            'torrent_info': torrent_info,
            'backup_file_path': backup_file_path,
            'torrent_data': torrent_data
        }

    # ✅ 第二阶段预处理：去重保护（双重保护机制）
    logger.debug(f"[PERF] 开始去重检查：插入 {len(to_insert)} 个，更新 {len(to_update)} 个...")
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    # 第三阶段：批量执行数据库操作（快速提交，释放锁）
    logger.debug(f"[PERF] 开始批量写入：插入 {len(to_insert)} 个，更新 {len(to_update)} 个...")
    bulk_write_start = datetime.now()

    try:
        # ✅ 使用重试机制执行批量写入
        async def _bulk_write_with_retry():
            # 批量插入
            if to_insert:
                await db.run_sync(lambda session: session.bulk_insert_mappings(TorrentInfo, to_insert))
                logger.debug(f"[PERF] 批量插入 {len(to_insert)} 个种子完成")

            # 批量更新
            if to_update:
                await db.run_sync(lambda session: session.bulk_update_mappings(TorrentInfo, to_update))
                logger.debug(f"[PERF] 批量更新 {len(to_update)} 个种子完成")

            # ✅ 修复：移除提前提交，统一在最后提交（包括 tracker 数据）
            # 原因：
            # 1. commit() 后事务结束，后续 tracker 操作会在无事务状态执行
            # 2. tracker 数据写入但未提交，最终丢失
            # 3. 应该在所有操作（包括 tracker 同步）完成后统一提交
            # await db.commit()  # ❌ 移除此行

            bulk_write_duration = (datetime.now() - bulk_write_start).total_seconds()
            logger.debug(f"[PERF] 批量写入完成（待提交），耗时 {bulk_write_duration:.3f} 秒")

        # 执行批量写入（带重试机制）
        await _retry_on_db_lock(
            _bulk_write_with_retry,
            max_retries=3,
            base_delay=1.0,
            rollback=db.rollback,
            error_context=f"[{bt_downloader.nickname}] 批量写入种子数据"
        )

        logger.info(f"[{bt_downloader.nickname}] 批量写入成功：插入 {len(to_insert)} 个，更新 {len(to_update)} 个")

    except Exception as e:
        await db.rollback()
        stats['error_count'] = len(to_insert) + len(to_update)
        error_msg = f"[{bt_downloader.nickname}] 批量写入失败: {str(e)}"
        logger.error(error_msg)

        # ✅ 关键修复：抛出异常，让调用方知道失败
        raise Exception(error_msg) from e

    # ✅ 关键优化：批量写入完成后立即释放事务，后续操作使用独立事务

    # 第三阶段：处理 tracker 同步和备份（独立事务，避免长时间持有锁）
    logger.debug(f"[PERF] 开始处理 tracker 同步和备份...")
    tracker_backup_start = datetime.now()

    # 收集需要更新的 backup_file_path，最后批量更新
    backup_updates = []

    for torrent_info_id, info in torrent_info_map.items():
        mode = info['mode']
        torrent_info = info['torrent_info']
        backup_file_path = info['backup_file_path']

        try:
            # 🔧 统一类型转换，支持整数和字符串两种格式
            # 数据库存储：0=qBittorrent, 1=Transmission
            # API 字符串：'qbittorrent', 'transmission'
            original_type = bt_downloader.downloader_type
            downloader_type_str = None

            if original_type == 'qbittorrent' or original_type == 0 or original_type == '0':
                downloader_type_str = 'qbittorrent'
            elif original_type == 'transmission' or original_type == 1 or original_type == '1':
                downloader_type_str = 'transmission'

            if not downloader_type_str:
                logger.error(f"不支持的下载器类型: {original_type}")
                continue

            # Tracker 同步（使用独立事务）
            await sync_add_tracker_async(db, downloader_type_str, mode, torrent_info, torrent_info_id)

            if not backup_file_path:
                legacy_path = _resolve_legacy_backup_file_path(torrent_info_id, torrent_info.name)
                if legacy_path:
                    backup_file_path = legacy_path
                    backup_updates.append({
                        'info_id': torrent_info_id,
                        'backup_file_path': legacy_path,
                        'name': torrent_info.name
                    })

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
                    backup_result = await asyncio.to_thread(
                        backup_service.backup_torrent_file,
                        info_id=torrent_info_id,
                        torrent_hash=torrent_info.hashString,
                        torrent_name=torrent_info.name,
                        downloader_type='transmission',
                        save_path=torrent_info.download_dir,
                        downloader_config={
                            'host': bt_downloader.host,
                            'port': bt_downloader.port,
                            'username': bt_downloader.username,
                            'password': bt_downloader.password,
                            'torrent_file_path': torrent_info.torrent_file,
                            'torrent_save_path': bt_downloader.torrent_save_path
                        }
                    )

                    if backup_result['success']:
                        # ✅ 收集更新，稍后批量处理，避免循环内提交
                        backup_updates.append({
                            'info_id': torrent_info_id,
                            'backup_file_path': backup_result['backup_file_path'],
                            'name': torrent_info.name
                        })

                        # ✅ 集成：同时记录到 torrent_file_backup 表
                        try:
                            # 检查是否已存在相同 info_hash + downloader_id 的记录
                            existing_backup = await db.execute(
                                select(TorrentFileBackup).filter(
                                    TorrentFileBackup.info_hash == torrent_info.hashString,
                                    TorrentFileBackup.downloader_id == bt_downloader.downloader_id,
                                    TorrentFileBackup.is_deleted == False
                                )
                            )
                            existing_record = existing_backup.scalar_one_or_none()

                            if not existing_record:
                                # 不存在则插入新记录
                                backup_manager = TorrentFileBackupManagerService(db=db)
                                await backup_manager.repository.create(
                                    info_hash=torrent_info.hashString,
                                    file_path=backup_result['backup_file_path'],
                                    file_size=None,  # 可选：如果需要文件大小可以获取
                                    task_name=torrent_info.name,
                                    uploader_id=1,  # 默认管理员ID
                                    downloader_id=bt_downloader.downloader_id,
                                    upload_time=datetime.now()
                                )
                                await db.commit()
                                logger.info(f"记录种子备份到数据库: {torrent_info.name} (hash: {torrent_info.hashString[:8]}...)")
                            else:
                                logger.debug(f"种子备份记录已存在，跳过: {torrent_info.name} (hash: {torrent_info.hashString[:8]}...)")
                        except Exception as record_err:
                            # 只记录警告，不影响同步流程
                            logger.warning(f"记录种子备份到数据库失败（不影响同步）: {torrent_info.name}, 错误: {record_err}")

                except Exception as backup_err:
                    logger.warning(f"种子文件备份异常: {torrent_info.name}, 错误: {backup_err}")


            # ✅ 新增：自动补录历史种子备份记录（无论是否刚刚备份过）
            try:
                # 检查是否已存在相同 info_hash + downloader_id 的记录
                existing_backup = await db.execute(
                    select(TorrentFileBackup).filter(
                        TorrentFileBackup.info_hash == torrent_info.hashString,
                        TorrentFileBackup.downloader_id == bt_downloader.downloader_id,
                        TorrentFileBackup.is_deleted == False
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
                            upload_time=info['torrent_data']['create_time']  # 使用种子创建时间
                        )
                        await db.commit()
                        logger.info(
                            f"✅ 补录历史种子备份记录: {torrent_info.name} "
                            f"(hash: {torrent_info.hashString[:8]}..., 大小: {file_size / 1024:.2f}KB)"
                        )
                elif existing_record:
                    logger.debug(f"种子备份记录已存在，无需补录: {torrent_info.name} (hash: {torrent_info.hashString[:8]}...)")

            except Exception as backfill_err:
                # 只记录警告，不影响同步流程
                logger.warning(f"补录历史种子备份失败（不影响同步）: {torrent_info.name}, 错误: {backfill_err}")

        except Exception as e:
            stats['error_count'] += 1
            logger.error(f"处理种子 {torrent_info.name} 时出错: {str(e)}")

    # 批量更新 backup_file_path（一次性提交）
    if backup_updates:
        try:
            for update_data in backup_updates:
                await update_torrent_async(
                    db,
                    update_data['info_id'],
                    {'backup_file_path': update_data['backup_file_path']},
                    commit=False
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


# ==============================================================================
# qBittorrent 种子同步（优化版本）
# ==============================================================================

async def qb_add_torrents_async(db: AsyncSession, downloaders: List[Any]) -> None:
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

    Raises:
        ValueError: 当下载器列表为空时
    """
    # 添加空列表检查，防止IndexError
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    client = qbClient(
        host=bt_downloader.host,
        port=bt_downloader.port,
        username=bt_downloader.username,
        password=bt_downloader.password,
        VERIFY_WEBUI_CERTIFICATE=False,
        REQUESTS_ARGS={'timeout': QB_API_TIMEOUT})

    downloader_id = str(bt_downloader.downloader_id)
    torrent_info_list = []
    incremental_failed = False
    force_full_sync = False
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
                # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                sync_data = await asyncio.to_thread(client.sync_maindata, rid=0)
                new_rid = int(sync_data.get("rid", 0))
                with _QB_RID_LOCK:
                    _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                    _save_qb_rid_cache(_QB_SYNC_RID_CACHE)
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                used_sync_maindata = True
                if torrent_info_list:
                    await _enrich_qb_torrents_with_trackers(client, torrent_info_list)
                logger.info(
                    f"[QB_SYNC] first full sync: downloader_id={downloader_id}, "
                    f"rid={new_rid}, torrents={len(torrent_info_list)}"
                )
            else:
                # 增量同步：只获取变化的种子
                # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                sync_data = await asyncio.to_thread(client.sync_maindata, rid=last_rid)
                new_rid = int(sync_data.get("rid", last_rid))
                with _QB_RID_LOCK:
                    _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                    _save_qb_rid_cache(_QB_SYNC_RID_CACHE)

                # 处理删除的种子
                removed = sync_data.get("torrents_removed", []) or []
                if removed:
                    await _mark_qb_removed_torrents(db, bt_downloader.downloader_id, removed)

                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                used_sync_maindata = True
                if torrent_info_list:
                    await _enrich_qb_torrents_with_trackers(client, torrent_info_list)
                logger.info(
                    f"[QB_SYNC] incremental: downloader_id={downloader_id}, "
                    f"rid={last_rid}->{new_rid}, changed={len(torrent_info_list)}, "
                    f"removed={len(removed)}"
                )
        except APIConnectionError as e:
            # 连接异常：重试后失败再降级
            retry_success = False
            for attempt in range(1, 4):
                await asyncio.sleep(2 ** (attempt - 1))
                try:
                    # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                    sync_data = await asyncio.to_thread(client.sync_maindata, rid=last_rid or 0)
                    new_rid = int(sync_data.get("rid", last_rid or 0))
                    with _QB_RID_LOCK:
                        _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                        _save_qb_rid_cache(_QB_SYNC_RID_CACHE)
                    removed = sync_data.get("torrents_removed", []) or []
                    if removed:
                        await _mark_qb_removed_torrents(db, bt_downloader.downloader_id, removed)
                    torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                    used_sync_maindata = True
                    if torrent_info_list:
                        await _enrich_qb_torrents_with_trackers(client, torrent_info_list)
                    retry_success = True
                    logger.info(
                        f"[QB_SYNC] retry success: downloader_id={downloader_id}, "
                        f"rid={last_rid}->{new_rid}, changed={len(torrent_info_list)}, "
                        f"removed={len(removed)}"
                    )
                    break
                except APIConnectionError:
                    continue
            if not retry_success:
                incremental_failed = True
                logger.error(f"[QB_SYNC] connection failed, fallback to batch full sync: {e}")
        except LoginFailed as e:
            logger.error(f"[QB_SYNC] auth failed, abort: {e}")
            raise
        except APIError as e:
            incremental_failed = True
            logger.warning(f"[QB_SYNC] api error, fallback to batch full sync: {e}")
        except Exception as e:
            incremental_failed = True
            logger.warning(f"[QB_SYNC] incremental failed, fallback to batch full sync: {e}")

    # 兜底：分批全量同步，避免单次超大响应
    if force_full_sync or (not QB_USE_INCREMENTAL_SYNC) or incremental_failed:
        offset = 0
        while True:
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            batch = await asyncio.to_thread(client.torrents_info, limit=QB_BATCH_SIZE, offset=offset, include_trackers=True)
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
            TorrentInfo.backup_file_path
        ).filter(
            TorrentInfo.downloader_id == bt_downloader.downloader_id
        ).filter(
            TorrentInfo.dr == 0
        )
    )
    existing_torrents_rows = result.all()

    # 构建内存字典：{hash: (info_id, create_time, progress, backup_file_path)}
    existing_torrents_cache = {
        row.hash: (row.info_id, row.create_time, row.progress, row.backup_file_path)
        for row in existing_torrents_rows
    }

    batch_query_duration = (datetime.now() - batch_query_start).total_seconds()
    logger.debug(
        f"[PERF] 批量查询完成：查询 {len(existing_torrents_cache)} 个种子，"
        f"耗时 {batch_query_duration:.3f} 秒"
    )

    # ⚡ 性能优化2：收集所有变更数据（不立即执行数据库操作）
    to_insert = []  # 待插入的种子数据列表
    to_update = []  # 待更新的种子数据列表
    torrent_info_map = {}  # {info_id: torrent_info} 用于后续处理

    stats = {
        'insert_count': 0,
        'update_count': 0,
        'skip_count': 0,
        'error_count': 0
    }

    # 第一阶段：收集数据
    tracker_source = "qb_sync_maindata" if used_sync_maindata else "qb_torrents_info"
    for torrent_info in torrent_info_list:
        try:
            setattr(torrent_info, "_tracker_source", tracker_source)
        except Exception:
            pass
        # 使用内存字典查找
        torrent_hash = _qb_get_attr(torrent_info, 'hash')
        if not torrent_hash:
            stats['error_count'] += 1
            logger.warning("跳过无hash的qBittorrent种子记录")
            continue
        cached_data = existing_torrents_cache.get(torrent_hash)

        # 计算进度值
        raw_progress = _qb_get_attr(torrent_info, 'progress', None)
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
            stats['insert_count'] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            update_time = current_time
            progress_value = new_progress
            backup_file_path = None
        else:
            # 已存在种子：更新
            mode = "update"
            stats['update_count'] += 1
            torrent_info_id, create_time, old_progress_cached, backup_file_path = cached_data

            if create_time is None:
                create_time = current_time
            update_time = current_time

            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats['skip_count'] += 1
                logger.debug(f"进度未变化: {torrent_info.name}, 保留旧值 {old_progress:.2f}%")
            else:
                progress_value = new_progress
                logger.debug(f"进度更新: {torrent_info.name}, {old_progress:.2f}% → {new_progress:.2f}%")

        # 构建种子数据字典
        torrent_data = {
            'info_id': torrent_info_id,
            'downloader_id': bt_downloader.downloader_id,
            'downloader_name': bt_downloader.nickname,
            'torrent_id': torrent_hash,
            'hash': torrent_hash,
            'name': _qb_get_attr(torrent_info, 'name', ''),
            'status': TorrentStatusMapper.convert_qbittorrent_status(
                _qb_get_attr(torrent_info, 'state', '')
            ),
            'save_path': _qb_get_attr(torrent_info, 'save_path', ''),
            'size': _qb_get_attr(torrent_info, 'total_size', None) or _qb_get_attr(torrent_info, 'size', 0),
            'progress': progress_value,
            'torrent_file': "/config/qbittorrent/BT_backup/" + torrent_hash + ".torrent",
            'added_date': (
                datetime.fromtimestamp(_qb_get_attr(torrent_info, 'added_on', 0))
                if _qb_get_attr(torrent_info, 'added_on', 0) > 0 else None
            ),
            'completed_date': (
                datetime.fromtimestamp(_qb_get_attr(torrent_info, 'completion_on', 0))
                if _qb_get_attr(torrent_info, 'completion_on', 0) > 0 else None
            ),
            'ratio': _qb_get_attr(torrent_info, 'ratio', 0),
            'ratio_limit': _qb_get_attr(torrent_info, 'ratio_limit', 0),
            'tags': _qb_get_attr(torrent_info, 'tags', ''),
            'category': _qb_get_attr(torrent_info, 'category', ''),
            'super_seeding': _qb_get_attr(torrent_info, 'super_seeding', False),
            'enabled': 1,
            'create_time': create_time,
            'create_by': "admin",
            'update_time': update_time,
            'update_by': "admin",
            'backup_file_path': backup_file_path,
            'dr': 0
        }

        # 收集数据
        if mode == "insert":
            to_insert.append(torrent_data)
        else:  # mode == "update"
            to_update.append(torrent_data)

        # 保存映射关系，用于后续处理
        torrent_info_map[torrent_info_id] = {
            'mode': mode,
            'torrent_info': torrent_info,
            'backup_file_path': backup_file_path,
            'torrent_data': torrent_data
        }

    # ✅ 第二阶段预处理：去重保护（双重保护机制）
    logger.debug(f"[PERF] 开始去重检查：插入 {len(to_insert)} 个，更新 {len(to_update)} 个...")
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    # 第三阶段：批量执行数据库操作（快速提交，释放锁）
    logger.debug(f"[PERF] 开始批量写入：插入 {len(to_insert)} 个，更新 {len(to_update)} 个...")
    bulk_write_start = datetime.now()

    try:
        # ✅ 使用重试机制执行批量写入
        async def _bulk_write_with_retry():
            # 批量插入
            if to_insert:
                await db.run_sync(lambda session: session.bulk_insert_mappings(TorrentInfo, to_insert))
                logger.debug(f"[PERF] 批量插入 {len(to_insert)} 个种子完成")

            # 批量更新
            if to_update:
                await db.run_sync(lambda session: session.bulk_update_mappings(TorrentInfo, to_update))
                logger.debug(f"[PERF] 批量更新 {len(to_update)} 个种子完成")

            # ✅ 修复：移除提前提交，统一在最后提交（包括 tracker 数据）
            # 原因：
            # 1. commit() 后事务结束，后续 tracker 操作会在无事务状态执行
            # 2. tracker 数据写入但未提交，最终丢失
            # 3. 应该在所有操作（包括 tracker 同步）完成后统一提交
            # await db.commit()  # ❌ 移除此行

            bulk_write_duration = (datetime.now() - bulk_write_start).total_seconds()
            logger.debug(f"[PERF] 批量写入完成（待提交），耗时 {bulk_write_duration:.3f} 秒")

        # 执行批量写入（带重试机制）
        await _retry_on_db_lock(
            _bulk_write_with_retry,
            max_retries=3,
            base_delay=1.0,
            rollback=db.rollback,
            error_context=f"[{bt_downloader.nickname}] 批量写入种子数据"
        )

        logger.info(f"[{bt_downloader.nickname}] 批量写入成功：插入 {len(to_insert)} 个，更新 {len(to_update)} 个")

    except Exception as e:
        await db.rollback()
        stats['error_count'] = len(to_insert) + len(to_update)
        error_msg = f"[{bt_downloader.nickname}] 批量写入失败: {str(e)}"
        logger.error(error_msg)

        # ✅ 关键修复：抛出异常，让调用方知道失败
        raise Exception(error_msg) from e

    # ✅ 关键优化：批量写入完成后立即释放事务，后续操作使用独立事务

    # 第三阶段：处理 tracker 同步和备份（独立事务，避免长时间持有锁）
    logger.debug(f"[PERF] 开始处理 tracker 同步和备份...")
    tracker_backup_start = datetime.now()

    # 收集需要更新的 backup_file_path，最后批量更新
    backup_updates = []

    for torrent_info_id, info in torrent_info_map.items():
        mode = info['mode']
        torrent_info = info['torrent_info']
        backup_file_path = info['backup_file_path']

        try:
            # 🔧 统一类型转换，支持整数和字符串两种格式
            # 数据库存储：0=qBittorrent, 1=Transmission
            # API 字符串：'qbittorrent', 'transmission'
            original_type = bt_downloader.downloader_type
            downloader_type_str = None

            if original_type == 'qbittorrent' or original_type == 0 or original_type == '0':
                downloader_type_str = 'qbittorrent'
            elif original_type == 'transmission' or original_type == 1 or original_type == '1':
                downloader_type_str = 'transmission'

            if not downloader_type_str:
                logger.error(f"不支持的下载器类型: {original_type}")
                continue

            # Tracker 同步（使用独立事务）
            await sync_add_tracker_async(db, downloader_type_str, mode, torrent_info, torrent_info_id)

            if not backup_file_path:
                legacy_path = _resolve_legacy_backup_file_path(torrent_info_id, torrent_info.name)
                if legacy_path:
                    backup_file_path = legacy_path
                    backup_updates.append({
                        'info_id': torrent_info_id,
                        'backup_file_path': legacy_path,
                        'name': torrent_info.name
                    })

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
                    backup_result = await asyncio.to_thread(
                        backup_service.backup_torrent_file,
                        info_id=torrent_info_id,
                        torrent_hash=torrent_info.hash,
                        torrent_name=torrent_info.name,
                        downloader_type='qbittorrent',
                        save_path=torrent_info.save_path,
                        downloader_config={
                            'host': bt_downloader.host,
                            'port': bt_downloader.port,
                            'username': bt_downloader.username,
                            'password': bt_downloader.password,
                            'torrent_save_path': bt_downloader.torrent_save_path
                        }
                    )

                    if backup_result['success']:
                        # ✅ 收集更新，稍后批量处理，避免循环内提交
                        backup_updates.append({
                            'info_id': torrent_info_id,
                            'backup_file_path': backup_result['backup_file_path'],
                            'name': torrent_info.name
                        })

                        # ✅ 集成：同时记录到 torrent_file_backup 表
                        try:
                            # 检查是否已存在相同 info_hash + downloader_id 的记录
                            existing_backup = await db.execute(
                                select(TorrentFileBackup).filter(
                                    TorrentFileBackup.info_hash == torrent_info.hash,
                                    TorrentFileBackup.downloader_id == bt_downloader.downloader_id,
                                    TorrentFileBackup.is_deleted == False
                                )
                            )
                            existing_record = existing_backup.scalar_one_or_none()

                            if not existing_record:
                                # 不存在则插入新记录
                                backup_manager = TorrentFileBackupManagerService(db=db)
                                await backup_manager.repository.create(
                                    info_hash=torrent_info.hash,
                                    file_path=backup_result['backup_file_path'],
                                    file_size=None,  # 可选：如果需要文件大小可以获取
                                    task_name=torrent_info.name,
                                    uploader_id=1,  # 默认管理员ID
                                    downloader_id=bt_downloader.downloader_id,
                                    upload_time=datetime.now()
                                )
                                await db.commit()
                                logger.info(f"记录种子备份到数据库: {torrent_info.name} (hash: {torrent_info.hash[:8]}...)")
                            else:
                                logger.debug(f"种子备份记录已存在，跳过: {torrent_info.name} (hash: {torrent_info.hash[:8]}...)")
                        except Exception as record_err:
                            # 只记录警告，不影响同步流程
                            logger.warning(f"记录种子备份到数据库失败（不影响同步）: {torrent_info.name}, 错误: {record_err}")

                except Exception as backup_err:
                    logger.warning(f"种子文件备份异常: {torrent_info.name}, 错误: {backup_err}")

            # ✅ 新增：自动补录历史种子备份记录（无论是否刚刚备份过）
            try:
                # 检查是否已存在相同 info_hash + downloader_id 的记录
                existing_backup = await db.execute(
                    select(TorrentFileBackup).filter(
                        TorrentFileBackup.info_hash == torrent_info.hash,
                        TorrentFileBackup.downloader_id == bt_downloader.downloader_id,
                        TorrentFileBackup.is_deleted == False
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
                            upload_time=info['torrent_data']['create_time']  # 使用种子创建时间
                        )
                        await db.commit()
                        logger.info(
                            f"✅ 补录历史种子备份记录: {torrent_info.name} "
                            f"(hash: {torrent_info.hash[:8]}..., 大小: {file_size / 1024:.2f}KB)"
                        )
                elif existing_record:
                    logger.debug(f"种子备份记录已存在，无需补录: {torrent_info.name} (hash: {torrent_info.hash[:8]}...)")

            except Exception as backfill_err:
                # 只记录警告，不影响同步流程
                logger.warning(f"补录历史种子备份失败（不影响同步）: {torrent_info.name}, 错误: {backfill_err}")

        except Exception as e:
            stats['error_count'] += 1
            logger.error(f"处理种子 {torrent_info.name} 时出错: {str(e)}")

    # 批量更新 backup_file_path（一次性提交）
    if backup_updates:
        try:
            for update_data in backup_updates:
                await update_torrent_async(
                    db,
                    update_data['info_id'],
                    {'backup_file_path': update_data['backup_file_path']},
                    commit=False
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
        logger.info(f"[{bt_downloader.nickname}] ✅ Tracker数据批量提交成功（包括 {len(torrent_info_map)} 个种子的tracker信息）")
        logger.debug(f"[TRACKER_FIX] Tracker数据批量提交成功")
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
QB_BATCH_SIZE = int(os.getenv('QB_BATCH_SIZE', '500'))
TR_BATCH_SIZE = int(os.getenv('TR_BATCH_SIZE', '1000'))
QB_USE_INCREMENTAL_SYNC = os.getenv('QB_USE_INCREMENTAL_SYNC', 'true').lower() == 'true'
QB_API_TIMEOUT = int(os.getenv('QB_API_TIMEOUT', '60'))
TR_API_TIMEOUT = int(os.getenv('TR_API_TIMEOUT', '60'))
TR_ACTIVE_WINDOW_SECONDS = int(os.getenv('TR_ACTIVE_WINDOW_SECONDS', '300'))
QB_FULL_SYNC_INTERVAL_SECONDS = int(os.getenv('QB_FULL_SYNC_INTERVAL_SECONDS', '43200'))
TR_FULL_SYNC_INTERVAL_SECONDS = int(os.getenv('TR_FULL_SYNC_INTERVAL_SECONDS', '43200'))
TR_BASE_FIELDS = [
    "id",
    "hashString",
    "name",
    "status",
    "activityDate",
    "trackerStats"
]
TR_DETAIL_FIELDS = [
    "id",
    "hashString",
    "name",
    "status",
    "activityDate",
    "trackerStats",
    "percentDone",
    "downloadDir",
    "totalSize",
    "torrentFile",
    "addedDate",
    "doneDate",
    "uploadRatio",
    "seedRatioLimit",
    "labels"
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
        data = json.loads(cache_file.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}


def _save_qb_rid_cache(cache: Dict[str, int]) -> None:
    cache_file = _get_qb_rid_cache_file()
    try:
        cache_file.write_text(json.dumps(cache), encoding='utf-8')
    except Exception:
        # 持久化失败不影响主流程
        pass


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


async def _enrich_qb_torrents_with_trackers(
    client: qbClient,
    torrent_info_list: List[Any],
    batch_size: int = 100
) -> None:
    """
    Enrich qBittorrent torrents with tracker info after sync/maindata.
    """
    if not torrent_info_list:
        return

    info_by_hash = {}
    torrent_hashes = []
    for torrent_info in torrent_info_list:
        torrent_hash = _qb_get_attr(torrent_info, "hash")
        if torrent_hash:
            info_by_hash[torrent_hash] = torrent_info
            torrent_hashes.append(torrent_hash)

    if not torrent_hashes:
        logger.warning("[QB_TRACKER_ENRICH] No valid hashes found")
        return

    enrich_start = datetime.now()
    logger.info(
        f"[QB_TRACKER_ENRICH] Enriching {len(torrent_hashes)} torrents with tracker info"
    )

    for i in range(0, len(torrent_hashes), batch_size):
        batch_hashes = torrent_hashes[i:i + batch_size]
        try:
            trackers_map = await asyncio.to_thread(
                client.torrents_trackers,
                hashes=batch_hashes
            )
            if isinstance(trackers_map, dict) and trackers_map:
                for torrent_hash, trackers in trackers_map.items():
                    torrent_info = info_by_hash.get(torrent_hash)
                    if torrent_info:
                        torrent_info.trackers = trackers
                logger.debug(
                    f"[QB_TRACKER_ENRICH] Batch {i // batch_size + 1} completed: "
                    f"{len(batch_hashes)} torrents"
                )
                continue
        except Exception as e:
            logger.warning(
                f"[QB_TRACKER_ENRICH] Batch fetch failed, fallback to single calls: {e}"
            )

        for torrent_hash in batch_hashes:
            try:
                trackers = await asyncio.to_thread(client.torrents_trackers, torrent_hash)
                torrent_info = info_by_hash.get(torrent_hash)
                if torrent_info:
                    torrent_info.trackers = trackers
            except Exception as e:
                logger.error(
                    f"[QB_TRACKER_ENRICH] Failed to fetch trackers for {torrent_hash}: {e}"
                )
                continue

    enrich_duration = (datetime.now() - enrich_start).total_seconds()
    logger.info(
        f"[QB_TRACKER_ENRICH] Completed enrichment for {len(torrent_hashes)} torrents "
        f"in {enrich_duration:.3f}s"
    )


async def _mark_qb_removed_torrents(
    db: AsyncSession,
    downloader_id: str,
    removed_hashes: List[str]
) -> None:
    """标记 qBittorrent 增量同步中被删除的种子"""
    if not removed_hashes:
        return
    try:
        from sqlalchemy import update
        current_time = datetime.now()
        await db.execute(
            update(TorrentInfo)
            .where(
                TorrentInfo.downloader_id == downloader_id,
                TorrentInfo.hash.in_(removed_hashes),
                TorrentInfo.dr == 0
            )
            .values(dr=1, update_time=current_time, update_by="system")
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"[QB_SYNC] mark removed torrents failed: {e}")
        await db.rollback()

# ==============================================================================
# 种子信息同步（不含 tracker，用于高频种子信息同步）
# ==============================================================================

async def qb_add_torrents_info_only_async(db: AsyncSession, downloaders: List[Any]) -> None:
    """qBittorrent 种子信息同步（仅同步种子基础信息，不同步 tracker）"""
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    client = qbClient(
        host=bt_downloader.host,
        port=bt_downloader.port,
        username=bt_downloader.username,
        password=bt_downloader.password,
        VERIFY_WEBUI_CERTIFICATE=False,
        REQUESTS_ARGS={"timeout": QB_API_TIMEOUT}
    )

    downloader_id = str(bt_downloader.downloader_id)
    torrent_info_list = []
    incremental_failed = False
    force_full_sync = False

    now_ts = datetime.now().timestamp()
    last_full_ts = _QB_LAST_FULL_SYNC.get(downloader_id, 0)
    if now_ts - last_full_ts >= QB_FULL_SYNC_INTERVAL_SECONDS:
        force_full_sync = True

    if QB_USE_INCREMENTAL_SYNC and not force_full_sync:
        last_rid = _QB_SYNC_RID_CACHE.get(downloader_id)
        try:
            if last_rid is None:
                # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                sync_data = await asyncio.to_thread(client.sync_maindata, rid=0)
                new_rid = int(sync_data.get("rid", 0))
                with _QB_RID_LOCK:
                    _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                    _save_qb_rid_cache(_QB_SYNC_RID_CACHE)
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                if torrent_info_list:
                    await _enrich_qb_torrents_with_trackers(client, torrent_info_list)
                logger.info(f"[QB_INFO_SYNC] first full sync: downloader_id={downloader_id}, rid={new_rid}, torrents={len(torrent_info_list)}")
            else:
                # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                sync_data = await asyncio.to_thread(client.sync_maindata, rid=last_rid)
                new_rid = int(sync_data.get("rid", last_rid))
                with _QB_RID_LOCK:
                    _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                    _save_qb_rid_cache(_QB_SYNC_RID_CACHE)
                removed = sync_data.get("torrents_removed", []) or []
                if removed:
                    await _mark_qb_removed_torrents(db, bt_downloader.downloader_id, removed)
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                if torrent_info_list:
                    await _enrich_qb_torrents_with_trackers(client, torrent_info_list)
                logger.info(f"[QB_INFO_SYNC] incremental: downloader_id={downloader_id}, changed={len(torrent_info_list)}, removed={len(removed)}")
        except (APIConnectionError, Exception) as e:
            incremental_failed = True
            logger.warning(f"[QB_INFO_SYNC] incremental failed, fallback to batch: {e}")

    if force_full_sync or (not QB_USE_INCREMENTAL_SYNC) or incremental_failed:
        offset = 0
        while True:
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            batch = await asyncio.to_thread(client.torrents_info, limit=QB_BATCH_SIZE, offset=offset)
            if not batch:
                break
            torrent_info_list.extend(batch)
            if len(batch) < QB_BATCH_SIZE:
                break
            offset += QB_BATCH_SIZE
        _QB_LAST_FULL_SYNC[downloader_id] = now_ts

    current_time = datetime.now()

    result = await db.execute(
        select(TorrentInfo.hash, TorrentInfo.info_id, TorrentInfo.create_time, TorrentInfo.progress)
        .filter(TorrentInfo.downloader_id == bt_downloader.downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    existing_torrents_cache = {row.hash: (row.info_id, row.create_time, row.progress) for row in result.all()}

    to_insert, to_update = [], []
    stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}

    for torrent_info in torrent_info_list:
        torrent_hash = _qb_get_attr(torrent_info, "hash")
        if not torrent_hash:
            stats["error"] += 1
            continue

        cached_data = existing_torrents_cache.get(torrent_hash)
        raw_progress = _qb_get_attr(torrent_info, "progress", None)
        new_progress = _normalize_progress_value(
            float(raw_progress) * 100.0 if raw_progress and raw_progress <= 1.0 else
            float(raw_progress) / 100.0 if raw_progress and raw_progress > 100.0 else
            float(raw_progress) if raw_progress else 0.0
        ) if raw_progress else 0.0

        if cached_data is None:
            stats["insert"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            progress_value = new_progress
            mode = "insert"
        else:
            stats["update"] += 1
            torrent_info_id, create_time, old_progress_cached = cached_data
            if create_time is None:
                create_time = current_time
            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats["skip"] += 1
            else:
                progress_value = new_progress
            mode = "update"

        torrent_data = {
            "info_id": torrent_info_id, "downloader_id": bt_downloader.downloader_id,
            "downloader_name": bt_downloader.nickname, "torrent_id": torrent_hash, "hash": torrent_hash,
            "name": _qb_get_attr(torrent_info, "name", ""), "save_path": _qb_get_attr(torrent_info, "save_path", ""),
            "size": _qb_get_attr(torrent_info, "total_size", None) or _qb_get_attr(torrent_info, "size", 0),
            "progress": progress_value, "torrent_file": f"/config/qbittorrent/BT_backup/{torrent_hash}.torrent",
            "status": TorrentStatusMapper.convert_qbittorrent_status(_qb_get_attr(torrent_info, "state", "")),
            "added_date": datetime.fromtimestamp(_qb_get_attr(torrent_info, "added_on", 0)) if _qb_get_attr(torrent_info, "added_on", 0) > 0 else None,
            "completed_date": datetime.fromtimestamp(_qb_get_attr(torrent_info, "completion_on", 0)) if _qb_get_attr(torrent_info, "completion_on", 0) > 0 else None,
            "ratio": _qb_get_attr(torrent_info, "ratio", 0), "ratio_limit": _qb_get_attr(torrent_info, "ratio_limit", 0),
            "tags": _qb_get_attr(torrent_info, "tags", ""), "category": _qb_get_attr(torrent_info, "category", ""),
            "super_seeding": _qb_get_attr(torrent_info, "super_seeding", False), "enabled": 1,
            "create_time": create_time, "create_by": "admin", "update_time": current_time, "update_by": "admin", "dr": 0
        }

        (to_insert if mode == "insert" else to_update).append(torrent_data)

    # ✅ 去重保护（双重保护机制）
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    try:
        async def _bulk_write():
            if to_insert:
                await db.run_sync(lambda s: s.bulk_insert_mappings(TorrentInfo, to_insert))
            if to_update:
                await db.run_sync(lambda s: s.bulk_update_mappings(TorrentInfo, to_update))
            await db.commit()
        await _retry_on_db_lock(_bulk_write, max_retries=3, base_delay=1.0, rollback=db.rollback, error_context=f"[QB_INFO] {bt_downloader.nickname}")
        logger.info(f"[QB_INFO_SYNC] {bt_downloader.nickname} 成功: 插入 {len(to_insert)}, 更新 {len(to_update)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"[QB_INFO_SYNC] {bt_downloader.nickname} 失败: {e}")
        raise


async def tr_add_torrents_info_only_async(db: AsyncSession, downloaders: List[Any]) -> None:
    """Transmission 种子信息同步（仅同步种子基础信息，不同步 tracker）"""
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    tr_client = trClient(host=bt_downloader.host, username=bt_downloader.username, password=bt_downloader.password, port=bt_downloader.port, protocol="http", timeout=TR_API_TIMEOUT)

    # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
    base_torrents = await asyncio.to_thread(tr_client.get_torrents, arguments=TR_BASE_FIELDS)
    torrent_info_list = []
    downloader_id = str(bt_downloader.downloader_id)
    now_ts = datetime.now().timestamp()
    last_full_ts = _TR_LAST_FULL_SYNC.get(downloader_id, 0)
    force_full_sync = (now_ts - last_full_ts) >= TR_FULL_SYNC_INTERVAL_SECONDS

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
        batch = base_torrents[i:i + TR_BATCH_SIZE]
        batch_ids = [t.id for t in batch if hasattr(t, "id")]
        if batch_ids:
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            torrent_info_list.extend(
                await asyncio.to_thread(
                    tr_client.get_torrents,
                    ids=batch_ids,
                    arguments=TR_DETAIL_FIELDS
                )
            )

    _TR_FULL_SYNC_DONE[downloader_id] = True
    if force_full_sync:
        _TR_LAST_FULL_SYNC[downloader_id] = now_ts

    current_time = datetime.now()
    result = await db.execute(
        select(TorrentInfo.hash, TorrentInfo.info_id, TorrentInfo.create_time, TorrentInfo.progress)
        .filter(TorrentInfo.downloader_id == bt_downloader.downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    existing_torrents_cache = {row.hash: (row.info_id, row.create_time, row.progress) for row in result.all()}

    to_insert, to_update = [], []
    stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}

    for torrent_info in torrent_info_list:
        cached_data = existing_torrents_cache.get(torrent_info.hashString)
        raw_percent = getattr(torrent_info, "percent_done", None)
        new_progress = _normalize_progress_value(float(raw_percent) * 100.0 if raw_percent else 0.0)

        if cached_data is None:
            stats["insert"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            progress_value = new_progress
            mode = "insert"
        else:
            stats["update"] += 1
            torrent_info_id, create_time, old_progress_cached = cached_data
            if create_time is None:
                create_time = current_time
            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats["skip"] += 1
            else:
                progress_value = new_progress
            mode = "update"

        torrent_data = {
            "info_id": torrent_info_id, "downloader_id": bt_downloader.downloader_id, "downloader_name": bt_downloader.nickname,
            "torrent_id": torrent_info.id, "hash": torrent_info.hashString, "name": torrent_info.name,
            "status": convert_transmission_status(torrent_info.status), "save_path": torrent_info.download_dir,
            "size": torrent_info.total_size, "progress": progress_value, "torrent_file": torrent_info.torrent_file,
            "added_date": torrent_info.added_date, "completed_date": torrent_info.done_date if torrent_info.done_date else None,
            "ratio": torrent_info.ratio, "ratio_limit": torrent_info.seed_ratio_limit,
            "tags": ",".join(torrent_info.labels) if hasattr(torrent_info, "labels") and torrent_info.labels else "",
            "enabled": 1, "create_time": create_time, "create_by": "admin", "update_time": current_time, "update_by": "admin", "dr": 0
        }

        (to_insert if mode == "insert" else to_update).append(torrent_data)

    # ✅ 去重保护（双重保护机制）
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    try:
        async def _bulk_write():
            if to_insert:
                await db.run_sync(lambda s: s.bulk_insert_mappings(TorrentInfo, to_insert))
            if to_update:
                await db.run_sync(lambda s: s.bulk_update_mappings(TorrentInfo, to_update))
            await db.commit()
        await _retry_on_db_lock(_bulk_write, max_retries=3, base_delay=1.0, rollback=db.rollback, error_context=f"[TR_INFO] {bt_downloader.nickname}")
        logger.info(f"[TR_INFO_SYNC] {bt_downloader.nickname} 成功: 插入 {len(to_insert)}, 更新 {len(to_update)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"[TR_INFO_SYNC] {bt_downloader.nickname} 失败: {e}")
        raise

# ==============================================================================
# 种子信息同步（不含 tracker，用于高频种子信息同步）
# ==============================================================================

async def qb_add_torrents_info_only_async(db: AsyncSession, downloaders: List[Any]) -> None:
    """qBittorrent 种子信息同步（仅同步种子基础信息，不同步 tracker）"""
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    client = qbClient(
        host=bt_downloader.host,
        port=bt_downloader.port,
        username=bt_downloader.username,
        password=bt_downloader.password,
        VERIFY_WEBUI_CERTIFICATE=False,
        REQUESTS_ARGS={"timeout": QB_API_TIMEOUT}
    )

    downloader_id = str(bt_downloader.downloader_id)
    torrent_info_list = []
    incremental_failed = False
    force_full_sync = False

    now_ts = datetime.now().timestamp()
    last_full_ts = _QB_LAST_FULL_SYNC.get(downloader_id, 0)
    if now_ts - last_full_ts >= QB_FULL_SYNC_INTERVAL_SECONDS:
        force_full_sync = True

    if QB_USE_INCREMENTAL_SYNC and not force_full_sync:
        last_rid = _QB_SYNC_RID_CACHE.get(downloader_id)
        try:
            if last_rid is None:
                # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                sync_data = await asyncio.to_thread(client.sync_maindata, rid=0)
                new_rid = int(sync_data.get("rid", 0))
                with _QB_RID_LOCK:
                    _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                    _save_qb_rid_cache(_QB_SYNC_RID_CACHE)
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                if torrent_info_list:
                    await _enrich_qb_torrents_with_trackers(client, torrent_info_list)
                logger.info(f"[QB_INFO_SYNC] first full sync: downloader_id={downloader_id}, rid={new_rid}, torrents={len(torrent_info_list)}")
            else:
                # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                sync_data = await asyncio.to_thread(client.sync_maindata, rid=last_rid)
                new_rid = int(sync_data.get("rid", last_rid))
                with _QB_RID_LOCK:
                    _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                    _save_qb_rid_cache(_QB_SYNC_RID_CACHE)
                removed = sync_data.get("torrents_removed", []) or []
                if removed:
                    await _mark_qb_removed_torrents(db, bt_downloader.downloader_id, removed)
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                if torrent_info_list:
                    await _enrich_qb_torrents_with_trackers(client, torrent_info_list)
                logger.info(f"[QB_INFO_SYNC] incremental: downloader_id={downloader_id}, changed={len(torrent_info_list)}, removed={len(removed)}")
        except (APIConnectionError, Exception) as e:
            incremental_failed = True
            logger.warning(f"[QB_INFO_SYNC] incremental failed, fallback to batch: {e}")

    if force_full_sync or (not QB_USE_INCREMENTAL_SYNC) or incremental_failed:
        offset = 0
        while True:
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            batch = await asyncio.to_thread(client.torrents_info, limit=QB_BATCH_SIZE, offset=offset)
            if not batch:
                break
            torrent_info_list.extend(batch)
            if len(batch) < QB_BATCH_SIZE:
                break
            offset += QB_BATCH_SIZE
        _QB_LAST_FULL_SYNC[downloader_id] = now_ts

    current_time = datetime.now()

    result = await db.execute(
        select(TorrentInfo.hash, TorrentInfo.info_id, TorrentInfo.create_time, TorrentInfo.progress)
        .filter(TorrentInfo.downloader_id == bt_downloader.downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    existing_torrents_cache = {row.hash: (row.info_id, row.create_time, row.progress) for row in result.all()}

    to_insert, to_update = [], []
    stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}

    for torrent_info in torrent_info_list:
        torrent_hash = _qb_get_attr(torrent_info, "hash")
        if not torrent_hash:
            stats["error"] += 1
            continue

        cached_data = existing_torrents_cache.get(torrent_hash)
        raw_progress = _qb_get_attr(torrent_info, "progress", None)
        new_progress = _normalize_progress_value(
            float(raw_progress) * 100.0 if raw_progress and raw_progress <= 1.0 else
            float(raw_progress) / 100.0 if raw_progress and raw_progress > 100.0 else
            float(raw_progress) if raw_progress else 0.0
        ) if raw_progress else 0.0

        if cached_data is None:
            stats["insert"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            progress_value = new_progress
            mode = "insert"
        else:
            stats["update"] += 1
            torrent_info_id, create_time, old_progress_cached = cached_data
            if create_time is None:
                create_time = current_time
            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats["skip"] += 1
            else:
                progress_value = new_progress
            mode = "update"

        torrent_data = {
            "info_id": torrent_info_id, "downloader_id": bt_downloader.downloader_id,
            "downloader_name": bt_downloader.nickname, "torrent_id": torrent_hash, "hash": torrent_hash,
            "name": _qb_get_attr(torrent_info, "name", ""), "save_path": _qb_get_attr(torrent_info, "save_path", ""),
            "size": _qb_get_attr(torrent_info, "total_size", None) or _qb_get_attr(torrent_info, "size", 0),
            "progress": progress_value, "torrent_file": f"/config/qbittorrent/BT_backup/{torrent_hash}.torrent",
            "status": TorrentStatusMapper.convert_qbittorrent_status(_qb_get_attr(torrent_info, "state", "")),
            "added_date": datetime.fromtimestamp(_qb_get_attr(torrent_info, "added_on", 0)) if _qb_get_attr(torrent_info, "added_on", 0) > 0 else None,
            "completed_date": datetime.fromtimestamp(_qb_get_attr(torrent_info, "completion_on", 0)) if _qb_get_attr(torrent_info, "completion_on", 0) > 0 else None,
            "ratio": _qb_get_attr(torrent_info, "ratio", 0), "ratio_limit": _qb_get_attr(torrent_info, "ratio_limit", 0),
            "tags": _qb_get_attr(torrent_info, "tags", ""), "category": _qb_get_attr(torrent_info, "category", ""),
            "super_seeding": _qb_get_attr(torrent_info, "super_seeding", False), "enabled": 1,
            "create_time": create_time, "create_by": "admin", "update_time": current_time, "update_by": "admin", "dr": 0
        }

        (to_insert if mode == "insert" else to_update).append(torrent_data)

    # ✅ 去重保护（双重保护机制）
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    try:
        async def _bulk_write():
            if to_insert:
                await db.run_sync(lambda s: s.bulk_insert_mappings(TorrentInfo, to_insert))
            if to_update:
                await db.run_sync(lambda s: s.bulk_update_mappings(TorrentInfo, to_update))
            await db.commit()
        await _retry_on_db_lock(_bulk_write, max_retries=3, base_delay=1.0, rollback=db.rollback, error_context=f"[QB_INFO] {bt_downloader.nickname}")
        logger.info(f"[QB_INFO_SYNC] {bt_downloader.nickname} 成功: 插入 {len(to_insert)}, 更新 {len(to_update)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"[QB_INFO_SYNC] {bt_downloader.nickname} 失败: {e}")
        raise


async def tr_add_torrents_info_only_async(db: AsyncSession, downloaders: List[Any]) -> None:
    """Transmission 种子信息同步（仅同步种子基础信息，不同步 tracker）"""
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    tr_client = trClient(host=bt_downloader.host, username=bt_downloader.username, password=bt_downloader.password, port=bt_downloader.port, protocol="http", timeout=TR_API_TIMEOUT)

    # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
    base_torrents = await asyncio.to_thread(tr_client.get_torrents, arguments=TR_BASE_FIELDS)
    torrent_info_list = []
    downloader_id = str(bt_downloader.downloader_id)
    now_ts = datetime.now().timestamp()
    last_full_ts = _TR_LAST_FULL_SYNC.get(downloader_id, 0)
    force_full_sync = (now_ts - last_full_ts) >= TR_FULL_SYNC_INTERVAL_SECONDS

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
        batch = base_torrents[i:i + TR_BATCH_SIZE]
        batch_ids = [t.id for t in batch if hasattr(t, "id")]
        if batch_ids:
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            torrent_info_list.extend(
                await asyncio.to_thread(
                    tr_client.get_torrents,
                    ids=batch_ids,
                    arguments=TR_DETAIL_FIELDS
                )
            )

    _TR_FULL_SYNC_DONE[downloader_id] = True
    if force_full_sync:
        _TR_LAST_FULL_SYNC[downloader_id] = now_ts

    current_time = datetime.now()
    result = await db.execute(
        select(TorrentInfo.hash, TorrentInfo.info_id, TorrentInfo.create_time, TorrentInfo.progress)
        .filter(TorrentInfo.downloader_id == bt_downloader.downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    existing_torrents_cache = {row.hash: (row.info_id, row.create_time, row.progress) for row in result.all()}

    to_insert, to_update = [], []
    stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}

    for torrent_info in torrent_info_list:
        cached_data = existing_torrents_cache.get(torrent_info.hashString)
        raw_percent = getattr(torrent_info, "percent_done", None)
        new_progress = _normalize_progress_value(float(raw_percent) * 100.0 if raw_percent else 0.0)

        if cached_data is None:
            stats["insert"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            progress_value = new_progress
            mode = "insert"
        else:
            stats["update"] += 1
            torrent_info_id, create_time, old_progress_cached = cached_data
            if create_time is None:
                create_time = current_time
            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats["skip"] += 1
            else:
                progress_value = new_progress
            mode = "update"

        torrent_data = {
            "info_id": torrent_info_id, "downloader_id": bt_downloader.downloader_id, "downloader_name": bt_downloader.nickname,
            "torrent_id": torrent_info.id, "hash": torrent_info.hashString, "name": torrent_info.name,
            "status": convert_transmission_status(torrent_info.status), "save_path": torrent_info.download_dir,
            "size": torrent_info.total_size, "progress": progress_value, "torrent_file": torrent_info.torrent_file,
            "added_date": torrent_info.added_date, "completed_date": torrent_info.done_date if torrent_info.done_date else None,
            "ratio": torrent_info.ratio, "ratio_limit": torrent_info.seed_ratio_limit,
            "tags": ",".join(torrent_info.labels) if hasattr(torrent_info, "labels") and torrent_info.labels else "",
            "enabled": 1, "create_time": create_time, "create_by": "admin", "update_time": current_time, "update_by": "admin", "dr": 0
        }

        (to_insert if mode == "insert" else to_update).append(torrent_data)

    # ✅ 去重保护（双重保护机制）
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    try:
        async def _bulk_write():
            if to_insert:
                await db.run_sync(lambda s: s.bulk_insert_mappings(TorrentInfo, to_insert))
            if to_update:
                await db.run_sync(lambda s: s.bulk_update_mappings(TorrentInfo, to_update))
            await db.commit()
        await _retry_on_db_lock(_bulk_write, max_retries=3, base_delay=1.0, rollback=db.rollback, error_context=f"[TR_INFO] {bt_downloader.nickname}")
        logger.info(f"[TR_INFO_SYNC] {bt_downloader.nickname} 成功: 插入 {len(to_insert)}, 更新 {len(to_update)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"[TR_INFO_SYNC] {bt_downloader.nickname} 失败: {e}")
        raise

# ==============================================================================
# 种子信息同步（不含 tracker，用于高频种子信息同步）
# ==============================================================================

async def qb_add_torrents_info_only_async(db: AsyncSession, downloaders: List[Any]) -> None:
    """qBittorrent 种子信息同步（仅同步种子基础信息，不同步 tracker）"""
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    client = qbClient(
        host=bt_downloader.host,
        port=bt_downloader.port,
        username=bt_downloader.username,
        password=bt_downloader.password,
        VERIFY_WEBUI_CERTIFICATE=False,
        REQUESTS_ARGS={"timeout": QB_API_TIMEOUT}
    )

    downloader_id = str(bt_downloader.downloader_id)
    torrent_info_list = []
    incremental_failed = False
    force_full_sync = False

    now_ts = datetime.now().timestamp()
    last_full_ts = _QB_LAST_FULL_SYNC.get(downloader_id, 0)
    if now_ts - last_full_ts >= QB_FULL_SYNC_INTERVAL_SECONDS:
        force_full_sync = True

    if QB_USE_INCREMENTAL_SYNC and not force_full_sync:
        last_rid = _QB_SYNC_RID_CACHE.get(downloader_id)
        try:
            if last_rid is None:
                # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                sync_data = await asyncio.to_thread(client.sync_maindata, rid=0)
                new_rid = int(sync_data.get("rid", 0))
                with _QB_RID_LOCK:
                    _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                    _save_qb_rid_cache(_QB_SYNC_RID_CACHE)
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                logger.info(f"[QB_INFO_SYNC] first full sync: downloader_id={downloader_id}, rid={new_rid}, torrents={len(torrent_info_list)}")
            else:
                # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
                sync_data = await asyncio.to_thread(client.sync_maindata, rid=last_rid)
                new_rid = int(sync_data.get("rid", last_rid))
                with _QB_RID_LOCK:
                    _QB_SYNC_RID_CACHE[downloader_id] = new_rid
                    _save_qb_rid_cache(_QB_SYNC_RID_CACHE)
                removed = sync_data.get("torrents_removed", []) or []
                if removed:
                    await _mark_qb_removed_torrents(db, bt_downloader.downloader_id, removed)
                torrent_info_list = _qb_dict_to_objects(sync_data.get("torrents", {}))
                logger.info(f"[QB_INFO_SYNC] incremental: downloader_id={downloader_id}, changed={len(torrent_info_list)}, removed={len(removed)}")
        except (APIConnectionError, Exception) as e:
            incremental_failed = True
            logger.warning(f"[QB_INFO_SYNC] incremental failed, fallback to batch: {e}")

    if force_full_sync or (not QB_USE_INCREMENTAL_SYNC) or incremental_failed:
        offset = 0
        while True:
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            batch = await asyncio.to_thread(client.torrents_info, limit=QB_BATCH_SIZE, offset=offset)
            if not batch:
                break
            torrent_info_list.extend(batch)
            if len(batch) < QB_BATCH_SIZE:
                break
            offset += QB_BATCH_SIZE
        _QB_LAST_FULL_SYNC[downloader_id] = now_ts

    current_time = datetime.now()

    result = await db.execute(
        select(TorrentInfo.hash, TorrentInfo.info_id, TorrentInfo.create_time, TorrentInfo.progress)
        .filter(TorrentInfo.downloader_id == bt_downloader.downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    existing_torrents_cache = {row.hash: (row.info_id, row.create_time, row.progress) for row in result.all()}

    to_insert, to_update = [], []
    stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}

    for torrent_info in torrent_info_list:
        torrent_hash = _qb_get_attr(torrent_info, "hash")
        if not torrent_hash:
            stats["error"] += 1
            continue

        cached_data = existing_torrents_cache.get(torrent_hash)
        raw_progress = _qb_get_attr(torrent_info, "progress", None)
        new_progress = _normalize_progress_value(
            float(raw_progress) * 100.0 if raw_progress and raw_progress <= 1.0 else
            float(raw_progress) / 100.0 if raw_progress and raw_progress > 100.0 else
            float(raw_progress) if raw_progress else 0.0
        ) if raw_progress else 0.0

        if cached_data is None:
            stats["insert"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            progress_value = new_progress
            mode = "insert"
        else:
            stats["update"] += 1
            torrent_info_id, create_time, old_progress_cached = cached_data
            if create_time is None:
                create_time = current_time
            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats["skip"] += 1
            else:
                progress_value = new_progress
            mode = "update"

        torrent_data = {
            "info_id": torrent_info_id, "downloader_id": bt_downloader.downloader_id,
            "downloader_name": bt_downloader.nickname, "torrent_id": torrent_hash, "hash": torrent_hash,
            "name": _qb_get_attr(torrent_info, "name", ""), "save_path": _qb_get_attr(torrent_info, "save_path", ""),
            "size": _qb_get_attr(torrent_info, "total_size", None) or _qb_get_attr(torrent_info, "size", 0),
            "progress": progress_value, "torrent_file": f"/config/qbittorrent/BT_backup/{torrent_hash}.torrent",
            "status": TorrentStatusMapper.convert_qbittorrent_status(_qb_get_attr(torrent_info, "state", "")),
            "added_date": datetime.fromtimestamp(_qb_get_attr(torrent_info, "added_on", 0)) if _qb_get_attr(torrent_info, "added_on", 0) > 0 else None,
            "completed_date": datetime.fromtimestamp(_qb_get_attr(torrent_info, "completion_on", 0)) if _qb_get_attr(torrent_info, "completion_on", 0) > 0 else None,
            "ratio": _qb_get_attr(torrent_info, "ratio", 0), "ratio_limit": _qb_get_attr(torrent_info, "ratio_limit", 0),
            "tags": _qb_get_attr(torrent_info, "tags", ""), "category": _qb_get_attr(torrent_info, "category", ""),
            "super_seeding": _qb_get_attr(torrent_info, "super_seeding", False), "enabled": 1,
            "create_time": create_time, "create_by": "admin", "update_time": current_time, "update_by": "admin", "dr": 0
        }

        (to_insert if mode == "insert" else to_update).append(torrent_data)

    # ✅ 去重保护（双重保护机制）
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    try:
        async def _bulk_write():
            if to_insert:
                await db.run_sync(lambda s: s.bulk_insert_mappings(TorrentInfo, to_insert))
            if to_update:
                await db.run_sync(lambda s: s.bulk_update_mappings(TorrentInfo, to_update))
            await db.commit()
        await _retry_on_db_lock(_bulk_write, max_retries=3, base_delay=1.0, rollback=db.rollback, error_context=f"[QB_INFO] {bt_downloader.nickname}")
        logger.info(f"[QB_INFO_SYNC] {bt_downloader.nickname} 成功: 插入 {len(to_insert)}, 更新 {len(to_update)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"[QB_INFO_SYNC] {bt_downloader.nickname} 失败: {e}")
        raise


async def tr_add_torrents_info_only_async(db: AsyncSession, downloaders: List[Any]) -> None:
    """Transmission 种子信息同步（仅同步种子基础信息，不同步 tracker）"""
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
    tr_client = trClient(host=bt_downloader.host, username=bt_downloader.username, password=bt_downloader.password, port=bt_downloader.port, protocol="http", timeout=TR_API_TIMEOUT)

    # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
    base_torrents = await asyncio.to_thread(tr_client.get_torrents, arguments=TR_BASE_FIELDS)
    torrent_info_list = []
    downloader_id = str(bt_downloader.downloader_id)
    now_ts = datetime.now().timestamp()
    last_full_ts = _TR_LAST_FULL_SYNC.get(downloader_id, 0)
    force_full_sync = (now_ts - last_full_ts) >= TR_FULL_SYNC_INTERVAL_SECONDS

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
        batch = base_torrents[i:i + TR_BATCH_SIZE]
        batch_ids = [t.id for t in batch if hasattr(t, "id")]
        if batch_ids:
            # ✅ 修复：在线程池中执行同步HTTP调用，避免阻塞事件循环
            torrent_info_list.extend(
                await asyncio.to_thread(
                    tr_client.get_torrents,
                    ids=batch_ids,
                    arguments=TR_DETAIL_FIELDS
                )
            )

    _TR_FULL_SYNC_DONE[downloader_id] = True
    if force_full_sync:
        _TR_LAST_FULL_SYNC[downloader_id] = now_ts

    current_time = datetime.now()
    result = await db.execute(
        select(TorrentInfo.hash, TorrentInfo.info_id, TorrentInfo.create_time, TorrentInfo.progress)
        .filter(TorrentInfo.downloader_id == bt_downloader.downloader_id)
        .filter(TorrentInfo.dr == 0)
    )
    existing_torrents_cache = {row.hash: (row.info_id, row.create_time, row.progress) for row in result.all()}

    to_insert, to_update = [], []
    stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}

    for torrent_info in torrent_info_list:
        cached_data = existing_torrents_cache.get(torrent_info.hashString)
        raw_percent = getattr(torrent_info, "percent_done", None)
        new_progress = _normalize_progress_value(float(raw_percent) * 100.0 if raw_percent else 0.0)

        if cached_data is None:
            stats["insert"] += 1
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            progress_value = new_progress
            mode = "insert"
        else:
            stats["update"] += 1
            torrent_info_id, create_time, old_progress_cached = cached_data
            if create_time is None:
                create_time = current_time
            old_progress = _normalize_progress_value(old_progress_cached)
            if abs(new_progress - old_progress) < 0.5:
                progress_value = old_progress
                stats["skip"] += 1
            else:
                progress_value = new_progress
            mode = "update"

        torrent_data = {
            "info_id": torrent_info_id, "downloader_id": bt_downloader.downloader_id, "downloader_name": bt_downloader.nickname,
            "torrent_id": torrent_info.id, "hash": torrent_info.hashString, "name": torrent_info.name,
            "status": convert_transmission_status(torrent_info.status), "save_path": torrent_info.download_dir,
            "size": torrent_info.total_size, "progress": progress_value, "torrent_file": torrent_info.torrent_file,
            "added_date": torrent_info.added_date, "completed_date": torrent_info.done_date if torrent_info.done_date else None,
            "ratio": torrent_info.ratio, "ratio_limit": torrent_info.seed_ratio_limit,
            "tags": ",".join(torrent_info.labels) if hasattr(torrent_info, "labels") and torrent_info.labels else "",
            "enabled": 1, "create_time": create_time, "create_by": "admin", "update_time": current_time, "update_by": "admin", "dr": 0
        }

        (to_insert if mode == "insert" else to_update).append(torrent_data)

    # ✅ 去重保护（双重保护机制）
    to_insert, to_update = _deduplicate_torrent_lists(to_insert, to_update)

    try:
        async def _bulk_write():
            if to_insert:
                await db.run_sync(lambda s: s.bulk_insert_mappings(TorrentInfo, to_insert))
            if to_update:
                await db.run_sync(lambda s: s.bulk_update_mappings(TorrentInfo, to_update))
            await db.commit()
        await _retry_on_db_lock(_bulk_write, max_retries=3, base_delay=1.0, rollback=db.rollback, error_context=f"[TR_INFO] {bt_downloader.nickname}")
        logger.info(f"[TR_INFO_SYNC] {bt_downloader.nickname} 成功: 插入 {len(to_insert)}, 更新 {len(to_update)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"[TR_INFO_SYNC] {bt_downloader.nickname} 失败: {e}")
        raise
