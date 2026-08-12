import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import update, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import SQLAlchemyError

from app.api.responseVO import CommonResponse
from app.database import get_async_db, AsyncSessionLocal
from app.auth.dependencies import require_authenticated_user
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo as torrentInfoModel, TorrentInfo
from app.torrents.models import TrackerInfo as trackerInfoModel
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.core.tracker_mapper import extract_tracker_host, resolve_transmission_tracker_status_code
from app.core.background_task_manager import task_manager, TaskStatus
from app.models.setting_templates import DownloaderTypeEnum
from app.core.config import settings

# 审计日志相关导入（使用异步版本）
from app.services.audit_service import get_audit_service, extract_audit_info_from_request
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.services.torrent_ratio_values import (
    MISSING_RATIO_VALUE,
    RatioNormalizationStats,
    apply_normalized_ratio_fields,
)
import urllib3

logger = logging.getLogger(__name__)
router = APIRouter()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_OPTIMISTIC_LOCK_RETRIES = 3


# ==================== 同步请求模型 ====================


class SyncSingleRequest(BaseModel):
    """单个下载器同步请求"""

    downloader_id: str = Field(..., description="下载器ID", min_length=1)


class SyncSingleResponse(BaseModel):
    """单个下载器同步响应"""

    downloader_id: str
    nickname: str
    downloader_type: str
    synced_count: int
    execution_time: float


# ==================== 辅助函数 ====================


def get_torrent_by_hash(db: Session, hash_value: str, downloader_id: Optional[str] = None) -> Optional[TorrentInfo]:
    """
    通过哈希值获取种子信息

    Args:
        db: 数据库会话
        hash_value: 种子哈希值
        downloader_id: 下载器ID（可选，用于限定查询范围）

    Returns:
        种子信息对象或None
    """
    query = db.query(TorrentInfo).filter(TorrentInfo.hash == hash_value, TorrentInfo.dr == 0)  # 只查询未删除的记录

    # 如果提供了 downloader_id，则限定查询范围
    if downloader_id is not None:
        query = query.filter(TorrentInfo.downloader_id == downloader_id)

    return query.first()


def update_torrent(db: Session, torrent_id: str, torrent_data: Dict[str, Any]) -> Optional[TorrentInfo]:
    """
    更新种子信息

    Args:
        db: 数据库会话
        torrent_id: 种子ID
        torrent_data: 更新的种子数据

    Returns:
        更新后的种子信息对象或None（如果未找到）
    """
    # 确保使用正确的ID字段名
    db_torrent = db.query(TorrentInfo).filter(TorrentInfo.info_id == torrent_id).first()
    if not db_torrent:
        return None

    try:
        # 更新对象属性
        for key, value in torrent_data.items():
            if hasattr(db_torrent, key):
                setattr(db_torrent, key, value)

        db.commit()
        db.refresh(db_torrent)
        return db_torrent
    except Exception as e:
        db.rollback()
        logger.error(f"更新种子信息失败: {str(e)}")
        return None


# ==================== 同步核心函数 ====================


async def torrent_sync_db_async(
    downloader_info: Dict[str, Any],
    trigger: str = "api",
) -> Dict[str, Any]:
    """
    异步版本的种子同步数据库函数（legacy adapter，W2-1）

    签名与旧版本完全兼容（两个调用方 torrent_sync_async / sync_single_downloader
    零改动）。SYNC_CANONICAL_COORDINATOR_ENABLED=True 时内部转发到
    SyncCoordinator::run_sync（sync_type="full"，统一资源准入/写治理/观测）；
    False 时回退旧直接调用 qb/tr_add_torrents_async 全量同步的路径（应急回滚）。
    ⚠️ legacy 只能作为应急回退，禁止与新路径同时执行，两个稳定版本后删除。

    Args:
        downloader_info: 下载器信息字典
        trigger: 触发来源（"manual"/"cron"/"api"），仅影响结构化日志与观测

    Returns:
        同步结果字典（status/message/downloader_type/nickname，契约不变）
    """
    if not settings.SYNC_CANONICAL_COORDINATOR_ENABLED:
        return await _legacy_full_sync_impl(downloader_info)

    from app.services.sync_coordinator import (
        SyncRequest,
        map_sync_result_to_legacy_dict,
        run_sync,
    )

    downloader_id = downloader_info.get("downloader_id")
    result = await run_sync(
        SyncRequest(
            sync_type="full",
            downloader_ids=[str(downloader_id)] if downloader_id else None,
            trigger=trigger,
        )
    )
    return map_sync_result_to_legacy_dict(result, downloader_info)


async def _execute_manual_sync_via_coordinator(downloader_info: Dict[str, Any]) -> Dict[str, Any]:
    """手动 sync-single 后台执行体（W2-1 新路径）。

    经 SyncCoordinator::run_sync 执行（sync_type="full", trigger="manual"），
    返回旧 dict 结构（status/message/downloader_type/nickname）保持 TaskLog
    与前端 sync-status 契约不变。资源准入在后台执行体内完成，不阻塞 HTTP 线程。
    """
    from app.services.sync_coordinator import (
        SyncRequest,
        map_sync_result_to_legacy_dict,
        run_sync,
    )

    downloader_id = downloader_info.get("downloader_id")
    result = await run_sync(
        SyncRequest(
            sync_type="full",
            downloader_ids=[str(downloader_id)] if downloader_id else None,
            trigger="manual",
        )
    )
    return map_sync_result_to_legacy_dict(result, downloader_info)


async def _legacy_full_sync_impl(downloader_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    旧全量同步实现（仅 SYNC_CANONICAL_COORDINATOR_ENABLED=False 应急回滚时使用）

    使用 AsyncSessionLocal 进行异步数据库操作，
    替代同步版本的 torrent_sync 函数。

    Args:
        downloader_info: 下载器信息字典

    Returns:
        同步结果字典
    """
    from app.database import AsyncSessionLocal
    from app.api.endpoints.torrents_async import qb_add_torrents_async, tr_add_torrents_async
    from app.main import app as downloader_app
    from app.services.sync_coordinator import _get_cached_client

    async with AsyncSessionLocal() as db:
        try:
            # 创建下载器对象
            downloader = BtDownloaders()
            for key, value in downloader_info.items():
                if hasattr(downloader, key):
                    setattr(downloader, key, value)

            # 🔧 修复：统一类型转换，支持整数和字符串两种格式
            # 数据库存储：0=qBittorrent, 1=Transmission
            # API 字符串：'qbittorrent', 'transmission'
            original_type = downloader.downloader_type
            downloader_type_str = None

            # 类型转换逻辑
            if original_type == "qbittorrent" or original_type == 0 or original_type == "0":
                downloader_type_str = "qbittorrent"
            elif original_type == "transmission" or original_type == 1 or original_type == "1":
                downloader_type_str = "transmission"
            else:
                # 未知类型
                error_msg = f"不支持的下载器类型: {original_type} (类型: {type(original_type).__name__})"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "message": error_msg,
                    "downloader_type": str(original_type),
                    "nickname": downloader.nickname,
                }

            cached_client = await _get_cached_client(downloader_app, str(downloader.downloader_id))
            if cached_client is None:
                return {
                    "status": "failed",
                    "message": f"下载器 {downloader.nickname} 缺少 store 缓存客户端连接",
                    "downloader_type": downloader_type_str,
                    "nickname": downloader.nickname,
                }

            # 使用转换后的类型进行判断
            if downloader_type_str == "qbittorrent":
                try:
                    await qb_add_torrents_async(db, [downloader], client=cached_client)
                    logger.info(f"Successfully synced qBittorrent downloader: {downloader.nickname}")
                    return {
                        "status": "success",
                        "message": f"qBittorrent下载器 {downloader.nickname} 同步成功",
                        "downloader_type": "qbittorrent",
                        "nickname": downloader.nickname,
                    }
                except Exception as sync_error:
                    # ✅ 关键修复：捕获同步异常，正确标记任务失败
                    logger.error(f"qBittorrent下载器 {downloader.nickname} 同步失败: {str(sync_error)}")
                    return {
                        "status": "failed",
                        "message": f"同步失败: {str(sync_error)}",
                        "downloader_type": "qbittorrent",
                        "nickname": downloader.nickname,
                    }

            elif downloader_type_str == "transmission":
                try:
                    await tr_add_torrents_async(db, [downloader], client=cached_client)
                    logger.info(f"Successfully synced Transmission downloader: {downloader.nickname}")
                    return {
                        "status": "success",
                        "message": f"Transmission下载器 {downloader.nickname} 同步成功",
                        "downloader_type": "transmission",
                        "nickname": downloader.nickname,
                    }
                except Exception as sync_error:
                    # ✅ 关键修复：捕获同步异常，正确标记任务失败
                    logger.error(f"Transmission下载器 {downloader.nickname} 同步失败: {str(sync_error)}")
                    return {
                        "status": "failed",
                        "message": f"同步失败: {str(sync_error)}",
                        "downloader_type": "transmission",
                        "nickname": downloader.nickname,
                    }

        except Exception as e:
            error_msg = f"同步下载器 {downloader_info.get('nickname', 'Unknown')} 失败: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "failed",
                "message": error_msg,
                "downloader_type": downloader_info.get("downloader_type", "unknown"),
                "nickname": downloader_info.get("nickname", "unknown"),
            }


async def torrent_sync_async() -> Dict[str, Any]:
    """
    异步后台同步种子数据的函数（不依赖接口请求）
    用于定时任务调用，从缓存获取下载器列表并同步种子信息

    Returns:
        同步结果汇总字典
        - status: "success" (全部成功), "partial" (部分成功), "failed" (全部失败), "no_action" (无下载器可同步)
    """
    # 🔧 修复：从 app.main 导入正确的 FastAPI 实例
    from app.main import app as downloader_app

    try:
        # 🔍 添加调试日志：记录 app 实例信息
        logger.info("[TORRENT_SYNC] 开始种子同步任务")
        logger.info(f"[TORRENT_SYNC] 使用的 app 实例 id: {id(downloader_app)}")
        logger.info(f"[TORRENT_SYNC] app 类型: {type(downloader_app)}")

        # 检查 app.state.store 是否存在
        if not hasattr(downloader_app, "state") or not hasattr(downloader_app.state, "store"):
            logger.error(f"[TORRENT_SYNC] app.state.store 不存在！app 类型: {type(downloader_app)}")
            logger.error(f"[TORRENT_SYNC] app.state 属性: {hasattr(downloader_app, 'state')}")
            if hasattr(downloader_app, "state"):
                logger.error(f"[TORRENT_SYNC] app.state 的属性: {dir(downloader_app.state)}")
            return {
                "status": "failed",
                "message": "下载器缓存未初始化 (app.state.store 不存在)",
                "successful_syncs": 0,
                "failed_syncs": 0,
                "total_downloaders": 0,
            }

        # 获取缓存的下载器列表
        cached_downloaders = await downloader_app.state.store.get_snapshot()
        logger.info(f"[TORRENT_SYNC] 缓存中的下载器数量: {len(cached_downloaders) if cached_downloaders else 0}")

        if not cached_downloaders:
            # 🔧 修复：返回 "no_action" 而不是 "success"
            logger.warning("[TORRENT_SYNC] 下载器缓存为空，无法执行同步")
            return {
                "status": "no_action",
                "message": "下载器缓存为空，无下载器可同步",
                "successful_syncs": 0,
                "failed_syncs": 0,
                "total_downloaders": 0,
            }

        # 只对有效的下载器（fail_time=0）进行种子同步
        valid_downloaders = [d for d in cached_downloaders if hasattr(d, "fail_time") and d.fail_time == 0]

        # 记录失效下载器信息
        failed_downloaders = [d for d in cached_downloaders if hasattr(d, "fail_time") and d.fail_time > 0]

        logger.info(f"[TORRENT_SYNC] 有效下载器数量: {len(valid_downloaders)}")
        if failed_downloaders:
            logger.warning(f"[TORRENT_SYNC] 失效下载器数量: {len(failed_downloaders)} (fail_time > 0)")

        if not valid_downloaders:
            # 🔧 修复：返回 "no_action" 而不是 "success"
            logger.warning("[TORRENT_SYNC] 没有有效的下载器可同步（所有下载器均失效）")
            return {
                "status": "no_action",
                "message": f"没有有效的下载器可同步（共 {len(cached_downloaders)} 个下载器，其中 {len(failed_downloaders)} 个失效）",
                "successful_syncs": 0,
                "failed_syncs": 0,
                "total_downloaders": len(cached_downloaders),
                "failed_count": len(failed_downloaders),
            }

        # 记录将要同步的下载器列表
        for downloader in valid_downloaders:
            logger.info(
                f"[TORRENT_SYNC] 准备同步: {downloader.nickname} (type={getattr(downloader, 'downloader_type', 'unknown')})"
            )

        # 并发执行同步任务，不设置超时限制
        sync_results = []
        successful_syncs = 0
        failed_syncs = 0
        max_concurrent_syncs = 3  # 限制同时进行的同步任务数量

        # 创建信号量来控制并发
        semaphore = asyncio.Semaphore(max_concurrent_syncs)

        async def sync_single_downloader(downloader_check_vo):
            """同步单个下载器的异步函数"""
            async with semaphore:  # 获取信号量
                try:
                    # 从缓存中获取下载器信息
                    downloader_info = {
                        "downloader_id": getattr(downloader_check_vo, "downloader_id", None),
                        "nickname": downloader_check_vo.nickname,
                        "host": getattr(downloader_check_vo, "host", None),
                        "port": getattr(downloader_check_vo, "port", None),
                        "username": getattr(downloader_check_vo, "username", None),
                        "password": getattr(downloader_check_vo, "password", None),
                        "downloader_type": getattr(downloader_check_vo, "downloader_type", None),
                        "torrent_save_path": getattr(
                            downloader_check_vo, "torrent_save_path", None
                        ),  # 🔧 添加种子保存目录
                        "enabled": "1",
                        "status": "1",
                    }

                    # 调用异步种子同步函数
                    result = await torrent_sync_db_async(downloader_info)

                    return result

                except Exception as e:
                    error_result = {
                        "status": "failed",
                        "message": f"Torrent sync error for {downloader_check_vo.nickname}: {str(e)}",
                        "nickname": downloader_check_vo.nickname,
                    }
                    return error_result

        # 并发执行同步任务
        logger.info(f"[TORRENT_SYNC] 开始并发同步 {len(valid_downloaders)} 个下载器（最大并发数: {3}）")
        tasks = [sync_single_downloader(d) for d in valid_downloaders]
        sync_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        errors = []
        for result in sync_results:
            if isinstance(result, Exception):
                failed_syncs += 1
                error_result = {
                    "status": "failed",
                    "message": f"Unexpected error: {str(result)}",
                    "nickname": "unknown",
                }
                errors.append(error_result)
                logger.error(f"[TORRENT_SYNC] 同步异常: {str(result)}")
            elif result.get("status") == "success":
                successful_syncs += 1
                logger.info(f"[TORRENT_SYNC] 同步成功: {result.get('nickname', 'unknown')}")
            else:
                failed_syncs += 1
                logger.warning(
                    f"[TORRENT_SYNC] 同步失败: {result.get('nickname', 'unknown')} - {result.get('message', 'Unknown error')}"
                )

        # 种子同步完成后，根据关键词看板更新tracker状态
        logger.info(f"[TORRENT_SYNC] 种子同步完成，成功: {successful_syncs}, 失败: {failed_syncs}")
        logger.info("[TORRENT_SYNC] 开始更新 Tracker 状态")
        tracker_status_result = await update_tracker_status_from_keywords()

        logger.info(f"[TORRENT_SYNC] Tracker状态更新完成: {tracker_status_result.get('message', 'N/A')}")
        logger.info("[TORRENT_SYNC] ✅ 种子同步任务全部完成")

        return {
            "status": "success" if failed_syncs == 0 else "partial",
            "message": f"Sync completed: {successful_syncs} successful, {failed_syncs} failed",
            "successful_syncs": successful_syncs,
            "failed_syncs": failed_syncs,
            "total_downloaders": len(valid_downloaders),
            "tracker_status_update": tracker_status_result,
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": f"Torrent sync task failed: {str(e)}",
            "successful_syncs": 0,
            "failed_syncs": 0,
            "total_downloaders": 0,
        }


# ==================== 下载器种子同步函数 ====================


def tr_add_torrents(db, downloaders, app=None):
    """
    根据transmission的种子数据结构创建插入数据

    Args:
        db: 数据库会话
        downloaders: 下载器列表
        app: FastAPI应用实例（可选，传入时使用缓存连接）

    Raises:
        ValueError: 当下载器列表为空时
    """
    # 添加空列表检查，防止IndexError
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]

    # 优先使用缓存连接（约束16）+ 健康检查
    tr_client = None
    if app and hasattr(app.state, "store"):
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next((d for d in cached_downloaders if d.downloader_id == bt_downloader.downloader_id), None)
        if downloader_vo and hasattr(downloader_vo, "client") and downloader_vo.client:
            tr_client = downloader_vo.client
            # 添加连接健康检查
            try:
                # 测试连接是否有效
                tr_client.get_torrents()
            except Exception as e:
                logger.warning(f"缓存连接已失效，重新创建: {e}")
                tr_client = None  # 触发重新创建逻辑

    if tr_client is None:
        logger.error(
            "下载器 %s 缺少有效缓存 Transmission 客户端，拒绝在业务接口中自建连接",
            bt_downloader.downloader_id,
        )
        return {
            "status": "error",
            "message": "下载器缓存客户端不可用",
            "downloader_id": bt_downloader.downloader_id,
        }
    try:
        torrent_info_list = tr_client.get_torrents()
    except Exception as e:
        logger.error(f"获取Transmission种子列表失败: {str(e)}")
        return {
            "status": "error",
            "message": f"获取种子列表失败: {str(e)}",
            "downloader_id": bt_downloader.downloader_id,
        }
    current_time = datetime.now()
    ratio_stats = RatioNormalizationStats()
    for torrent_info in torrent_info_list:
        # torrent_query_result = \
        #     db.query(torrent_info_model.info_id).filter(torrent_info_model.hash == torrent_info.hashString).filter(
        #         torrent_info_model.downloader_id == downloaders[0].downloader_id).filter(
        #         torrent_info_model.dr == 1).all()
        result_info = get_torrent_by_hash(db, torrent_info.hashString, bt_downloader.downloader_id)
        if result_info is None:
            mode = "insert"
            torrent_info_id = str(uuid.uuid4())
        else:
            mode = "update"
            torrent_info_id = result_info.info_id
        ratio_fields: Dict[str, Any] = {}
        ratio_stats.observe(
            apply_normalized_ratio_fields(
                ratio_fields,
                raw_ratio=getattr(torrent_info, "ratio", MISSING_RATIO_VALUE),
                raw_ratio_limit=getattr(torrent_info, "seed_ratio_limit", MISSING_RATIO_VALUE),
                is_insert=mode == "insert",
            )
        )
        torrent = torrentInfoModel(
            id_=torrent_info_id,
            downloader_id=bt_downloader.downloader_id,
            downloader_name=bt_downloader.nickname,
            torrent_id=torrent_info.id,
            hash=torrent_info.hashString,
            name=torrent_info.name,
            status=TorrentStatusMapper.resolve_transmission_status(torrent_info.status, torrent_info.error),
            error_reason=TorrentStatusMapper.extract_transmission_error_reason(torrent_info),
            save_path=torrent_info.download_dir,
            size=torrent_info.total_size,
            torrent_file=torrent_info.torrent_file,
            added_date=torrent_info.added_date,
            completed_date=torrent_info.done_date if torrent_info.done_date else None,
            ratio=ratio_fields.get("ratio"),
            ratio_limit=ratio_fields.get("ratio_limit"),
            tags=",".join(torrent_info.labels) if hasattr(torrent_info, "labels") and torrent_info.labels else "",
            category="",
            super_seeding="",
            enabled=1,
            create_time=current_time,
            create_by="admin",
            update_time=current_time,
            update_by="admin",
            dr=0,
        )
        try:
            if mode == "insert":
                db.add(torrent)
            if mode == "update":
                torrent_dict = torrent.to_dict()
                for ratio_field in ("ratio", "ratio_limit"):
                    if ratio_field not in ratio_fields:
                        torrent_dict.pop(ratio_field, None)
                update_torrent(db, result_info.info_id, torrent_dict)
                # db.query(torrent_info_model).filter(torrent_info_model.info_id == torrent_info_id).update
            sync_add_tracker(db, bt_downloader.downloader_type, mode, torrent_info, torrent_info_id)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating database: {str(e)}")
    ratio_stats.log_summary(
        logger,
        context=f"transmission-legacy:{bt_downloader.downloader_id}",
    )


def sync_add_tracker(db, downloader_type, mode, torrent_info, torrent_info_id):
    """
    Sync tracker info with batch upsert and batch updates.
    """
    current_time = datetime.now()
    current_tracker_urls = set()
    tracker_rows = []

    # 使用统一的枚举类方法进行类型判断
    type_name = DownloaderTypeEnum(downloader_type).to_name()
    if type_name == "qbittorrent":
        trackers_data = getattr(torrent_info, "trackers", None)
        if callable(trackers_data):
            trackers_data = trackers_data()
        trackers_data = trackers_data or []

        for tracker in trackers_data:
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

    elif type_name == "transmission":
        tracker_stats = getattr(torrent_info, "tracker_stats", None) or []
        for tracker_status in tracker_stats:
            tracker_url = tracker_status.fields.get("announce")
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
                    "last_announce_succeeded": resolve_transmission_tracker_status_code(
                        tracker_status, "announce"
                    ),
                    "last_announce_msg": tracker_status.last_announce_result,
                    "last_scrape_succeeded": resolve_transmission_tracker_status_code(
                        tracker_status, "scrape"
                    ),
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

    if mode == "update" and current_tracker_urls:
        active_tracker = aliased(trackerInfoModel)
        db.execute(
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

        # P1修复：添加row的None检查，避免AttributeError
        soft_deleted_pairs = {
            (row.get("torrent_info_id"), row.get("tracker_url"))
            for row in tracker_rows
            if row and isinstance(row, dict) and row.get("torrent_info_id") and row.get("tracker_url")
        }

        # 删除软删除记录，避免upsert时恢复（不使用嵌套事务，由外层commit统一管理）
        if soft_deleted_pairs:
            db.execute(
                delete(trackerInfoModel).where(
                    trackerInfoModel.dr == 1,
                    tuple_(trackerInfoModel.torrent_info_id, trackerInfoModel.tracker_url).in_(
                        list(soft_deleted_pairs)
                    ),
                )
            )

        # 插入新记录或更新现有记录
        stmt = sqlite_insert(trackerInfoModel).values(tracker_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["torrent_info_id", "tracker_url"],
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
        db.execute(stmt)

    if mode == "update":
        mark_removed_trackers_batch(db, torrent_info_id, current_tracker_urls, current_time)


def qb_add_torrents(db, downloaders, app=None):
    """
    根据qbittorrent的种子数据结构创建插入数据

    Args:
        db: 数据库会话
        downloaders: 下载器列表
        app: FastAPI应用实例（可选，传入时使用缓存连接）

    Raises:
        ValueError: 当下载器列表为空时
    """
    # 添加空列表检查，防止IndexError
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]

    # 优先使用缓存连接（约束16）+ 健康检查
    client = None
    if app and hasattr(app.state, "store"):
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next((d for d in cached_downloaders if d.downloader_id == bt_downloader.downloader_id), None)
        if downloader_vo and hasattr(downloader_vo, "client") and downloader_vo.client:
            client = downloader_vo.client
            # 添加连接健康检查
            try:
                # 测试连接是否有效
                client.torrents_info()
            except Exception as e:
                logger.warning(f"缓存连接已失效，重新创建: {e}")
                client = None  # 触发重新创建逻辑

    if client is None:
        logger.error(
            "下载器 %s 缺少有效缓存 qBittorrent 客户端，拒绝在业务接口中自建连接",
            bt_downloader.downloader_id,
        )
        return {
            "status": "error",
            "message": "下载器缓存客户端不可用",
            "downloader_id": bt_downloader.downloader_id,
        }
    try:
        torrent_info_list = client.torrents_info()
    except Exception as e:
        logger.error(f"获取qBittorrent种子列表失败: {str(e)}")
        return {
            "status": "error",
            "message": f"获取种子列表失败: {str(e)}",
            "downloader_id": bt_downloader.downloader_id,
        }
    current_time = datetime.now()
    ratio_stats = RatioNormalizationStats()
    for torrent_info in torrent_info_list:
        torrent_query_result = (
            db.query(torrentInfoModel.info_id, torrentInfoModel.create_time)
            .filter(torrentInfoModel.hash == torrent_info.hash)
            .filter(torrentInfoModel.downloader_id == bt_downloader.downloader_id)
            .filter(torrentInfoModel.dr == 0)
            .all()
        )
        if torrent_query_result.__len__() == 0:
            mode = "insert"
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            update_time = current_time
        else:
            mode = "update"
            torrent_info_id = torrent_query_result[0][0]
            create_time = torrent_query_result[0][1]
            if create_time is None:
                create_time = current_time
            update_time = current_time
        ratio_fields: Dict[str, Any] = {}
        ratio_stats.observe(
            apply_normalized_ratio_fields(
                ratio_fields,
                raw_ratio=getattr(torrent_info, "ratio", MISSING_RATIO_VALUE),
                raw_ratio_limit=getattr(torrent_info, "ratio_limit", MISSING_RATIO_VALUE),
                is_insert=mode == "insert",
            )
        )
        torrent = torrentInfoModel(
            id_=torrent_info_id,
            downloader_id=bt_downloader.downloader_id,
            downloader_name=bt_downloader.nickname,
            torrent_id=torrent_info.hash,
            hash=torrent_info.hash,
            name=torrent_info.name,
            status=TorrentStatusMapper.convert_qbittorrent_status(torrent_info.state),
            save_path=torrent_info.save_path,
            size=torrent_info.total_size,
            torrent_file="/config/qbittorrent/BT_backup/" + torrent_info.hash + ".torrent",
            # 防御性：添加时间戳范围检查，防止负数和溢出
            added_date=datetime.fromtimestamp(torrent_info.added_on) if torrent_info.added_on > 0 else None,
            completed_date=(
                datetime.fromtimestamp(torrent_info.completion_on)
                if torrent_info.completion_on
                and torrent_info.completion_on > 0
                and torrent_info.completion_on <= 2147483647  # 防止Year 2038问题
                else None
            ),
            ratio=ratio_fields.get("ratio"),
            # NULL 表示“无显式单种数值限制”，不能用于向下载器回写设置。
            ratio_limit=ratio_fields.get("ratio_limit"),
            tags=torrent_info.tags,
            category=torrent_info.category,
            super_seeding=torrent_info.super_seeding,
            enabled=1,
            create_time=create_time,
            create_by="admin",
            update_time=update_time,
            update_by="admin",
            dr=0,
        )

        try:
            result_info = get_torrent_by_hash(db, torrent_info.hash, bt_downloader.downloader_id)
            if result_info:
                torrent_dict = torrent.to_dict()
                for ratio_field in ("ratio", "ratio_limit"):
                    if ratio_field not in ratio_fields:
                        torrent_dict.pop(ratio_field, None)
                update_torrent(db, result_info.info_id, torrent_dict)
            else:
                db.add(torrent)
            sync_add_tracker(db, bt_downloader.downloader_type, mode, torrent_info, torrent_info_id)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating database: {str(e)}")
    ratio_stats.log_summary(
        logger,
        context=f"qbittorrent-legacy:{bt_downloader.downloader_id}",
    )


# ==============================================================================
# Tracker 同步辅助函数（乐观锁版本）
# ==============================================================================


def validate_tracker_params(torrent_info_id, tracker_url, current_time):
    """
    验证 tracker 相关参数的有效性

    Args:
        torrent_info_id: 种子主键
        tracker_url: tracker URL
        current_time: 当前时间

    Returns:
        bool: 参数是否有效
    """
    if not torrent_info_id or not isinstance(torrent_info_id, str):
        logger.warning(f"无效的 torrent_info_id: {torrent_info_id}")
        return False

    if not tracker_url or not isinstance(tracker_url, str):
        logger.warning(f"无效的 tracker_url: {tracker_url}")
        return False

    if not isinstance(current_time, datetime):
        logger.warning(f"无效的 current_time 类型: {type(current_time)}")
        return False

    return True


def update_tracker_with_optimistic_lock(db, tracker_id, update_data, max_retries=MAX_OPTIMISTIC_LOCK_RETRIES):
    """
    使用乐观锁更新 tracker 记录

    Args:
        db: 数据库会话
        tracker_id: tracker 主键
        update_data: 更新数据字典
        max_retries: 最大重试次数（默认3次）

    Returns:
        bool: 更新是否成功
    """
    for attempt in range(max_retries):
        try:
            # 读取当前记录
            tracker = (
                db.query(trackerInfoModel)
                .filter(trackerInfoModel.tracker_id == tracker_id, trackerInfoModel.dr == 0)
                .first()
            )

            if tracker is None:
                logger.warning(f"乐观锁更新失败: tracker {tracker_id} 不存在或已删除")
                return False

            old_version = tracker.version

            # 创建新的数据字典副本，避免污染传入的参数
            final_update_data = update_data.copy()
            final_update_data["version"] = old_version + 1

            # 执行更新（带版本检查）
            affected_rows = (
                db.query(trackerInfoModel)
                .filter(
                    trackerInfoModel.tracker_id == tracker_id,
                    trackerInfoModel.version == old_version,
                    trackerInfoModel.dr == 0,
                )
                .update(final_update_data)
            )

            if affected_rows > 0:
                return True  # 更新成功
            elif attempt < max_retries - 1:
                logger.info(f"乐观锁冲突，第 {attempt + 1} 次重试: tracker_id={tracker_id}")
                continue  # 重试
            else:
                logger.warning(f"乐观锁重试失败，已达到最大重试次数: tracker_id={tracker_id}")
                return False

        except Exception as e:
            logger.error(f"乐观锁更新异常: {e}, tracker_id={tracker_id}")
            if attempt < max_retries - 1:
                continue
            else:
                return False

    return False


def restore_deleted_tracker(
    db, torrent_info_id, tracker_url, tracker_data, current_time, max_retries=MAX_OPTIMISTIC_LOCK_RETRIES
):
    """
    恢复已删除的 tracker 记录（dr: 1 -> 0）

    Args:
        db: 数据库会话
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
            deleted_tracker = (
                db.query(trackerInfoModel)
                .filter(
                    trackerInfoModel.torrent_info_id == torrent_info_id,
                    trackerInfoModel.tracker_url == tracker_url,
                    trackerInfoModel.dr == 1,
                )
                .first()
            )

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

            affected_rows = (
                db.query(trackerInfoModel)
                .filter(
                    trackerInfoModel.tracker_id == deleted_tracker.tracker_id,
                    trackerInfoModel.version == deleted_tracker.version,
                    trackerInfoModel.dr == 1,
                )
                .update(update_data)
            )

            if affected_rows > 0:
                logger.info(f"恢复已删除的 tracker: {tracker_url}")
                return True
            elif attempt < max_retries - 1:
                logger.info(f"恢复 tracker 乐观锁冲突，第 {attempt + 1} 次重试: {tracker_url}")
                continue  # 重试
            else:
                logger.warning(f"恢复 tracker 失败（乐观锁重试耗尽）: {tracker_url}")
                return False

        except Exception as e:
            logger.error(f"恢复 tracker 异常: {e}, tracker_url={tracker_url}")
            if attempt < max_retries - 1:
                continue
            else:
                return False

    return False


def mark_removed_trackers_batch(db, torrent_info_id, current_tracker_urls, current_time):
    """
    Batch mark removed trackers using a single UPDATE.
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

        result = db.execute(
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


def mark_removed_trackers(db, torrent_info_id, current_tracker_urls, current_time):
    """
    标记已移除的 tracker 为逻辑删除（保留用于向后兼容）

    注意：此函数使用乐观锁，已废弃。请使用 mark_removed_trackers_batch 替代。

    Args:
        db: 数据库会话
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
        existing_trackers = (
            db.query(trackerInfoModel)
            .filter(trackerInfoModel.torrent_info_id == torrent_info_id, trackerInfoModel.dr == 0)
            .all()
        )

        removed_count = 0
        for existing_tracker in existing_trackers:
            if existing_tracker.tracker_url not in current_tracker_urls:
                # 使用乐观锁标记为删除
                update_data = {
                    "dr": 1,
                    "update_time": current_time,
                    "update_by": "system",
                    "version": existing_tracker.version + 1,
                }

                affected_rows = (
                    db.query(trackerInfoModel)
                    .filter(
                        trackerInfoModel.tracker_id == existing_tracker.tracker_id,
                        trackerInfoModel.version == existing_tracker.version,
                        trackerInfoModel.dr == 0,
                    )
                    .update(update_data)
                )

                if affected_rows > 0:
                    removed_count += 1
                    logger.info(f"标记已移除的 tracker: {existing_tracker.tracker_url}")
                else:
                    logger.warning(f"标记删除失败（乐观锁冲突）: {existing_tracker.tracker_url}")

        if removed_count > 0:
            logger.info(f"共标记 {removed_count} 个已移除的 tracker")

    except Exception as e:
        logger.error(f"标记已移除 tracker 异常: {e}")


def update_or_restore_tracker_with_retry(db, torrent_info_id, tracker_url, tracker_data, current_time):
    """
    更新或恢复 tracker 记录（带重试机制）

    逻辑：
    1. 查询是否存在 dr=0 的活跃记录
    2. 如果存在，使用乐观锁更新
    3. 如果不存在，查询是否存在 dr=1 的已删除记录
    4. 如果存在已删除记录，恢复它
    5. 如果都不存在，返回 False（需要添加新记录）

    Args:
        db: 数据库会话
        torrent_info_id: 种子主键
        tracker_url: tracker URL
        tracker_data: tracker 数据字典
        current_time: 当前时间

    Returns:
        bool: True 表示已处理（更新或恢复），False 表示需要添加新记录
    """
    try:
        # 参数验证
        if not validate_tracker_params(torrent_info_id, tracker_url, current_time):
            logger.error(f"参数验证失败: torrent_info_id={torrent_info_id}, tracker_url={tracker_url}")
            return False

        if not isinstance(tracker_data, dict):
            logger.error(f"tracker_data 必须是字典类型: {type(tracker_data)}")
            return False

        # 步骤1：查询活跃记录（dr=0）
        active_tracker = (
            db.query(trackerInfoModel)
            .filter(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.tracker_url == tracker_url,
                trackerInfoModel.dr == 0,
            )
            .first()
        )

        if active_tracker is not None:
            # 准备更新数据（保留 create_time/create_by）
            # 使用 get() 并提供默认值，防止 None 写入数据库
            update_data = {
                "tracker_name": tracker_data.get("tracker_name", active_tracker.tracker_name),
                "last_announce_succeeded": tracker_data.get("last_announce_succeeded", 0),
                "last_announce_msg": tracker_data.get("last_announce_msg", ""),
                "last_scrape_succeeded": tracker_data.get("last_scrape_succeeded", 0),
                "last_scrape_msg": tracker_data.get("last_scrape_msg", ""),
                "update_time": current_time,
                "update_by": "admin",
            }

            # 使用乐观锁更新
            success = update_tracker_with_optimistic_lock(db, active_tracker.tracker_id, update_data)

            if success:
                logger.debug(f"更新 tracker 成功: {tracker_url}")
            else:
                logger.warning(f"更新 tracker 失败（重试耗尽）: {tracker_url}")

            return True  # 已处理

        # 步骤2：查询已删除记录（dr=1）
        deleted_tracker = (
            db.query(trackerInfoModel)
            .filter(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.tracker_url == tracker_url,
                trackerInfoModel.dr == 1,
            )
            .first()
        )

        if deleted_tracker is not None:
            # 恢复已删除的记录
            success = restore_deleted_tracker(db, torrent_info_id, tracker_url, tracker_data, current_time)

            if success:
                logger.info(f"恢复 tracker 成功: {tracker_url}")
            else:
                logger.warning(f"恢复 tracker 失败: {tracker_url}")

            return True  # 已处理

        # 步骤3：都不存在，需要添加新记录
        return False

    except Exception as e:
        logger.error(f"update_or_restore_tracker 异常: {e}, tracker_url={tracker_url}")
        return False


# ==================== 同步接口 ====================


@router.post("/sync-single", response_model=CommonResponse)
async def sync_single_downloader(
    request: Request,
    sync_request: SyncSingleRequest,
    _user=Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    单个下载器种子同步接口（异步后台执行）

    启动指定下载器的种子同步任务，立即返回任务ID，不等待同步完成。
    同步任务在后台异步执行，支持并发控制。

    Args:
        request: 请求对象
        sync_request: 同步请求参数
        db: 数据库会话

    Returns:
        任务信息（包含任务ID和查询接口）
    """
    try:
        downloader_id = sync_request.downloader_id

        # 使用 AsyncSession 查询，避免在 async handler 内执行同步 SQLAlchemy 查询。
        result = await db.execute(
            select(BtDownloaders).where(
                BtDownloaders.downloader_id == downloader_id,
                BtDownloaders.dr == 0,
            )
        )
        downloader = result.scalar_one_or_none()

        if not downloader:
            return CommonResponse(status="error", msg=f"下载器不存在: {downloader_id}", code="404", data=None)

        # 检查下载器是否启用
        if not downloader.enabled or downloader.status != "1":
            return CommonResponse(
                status="error", msg=f"下载器未启用或已停用: {downloader.nickname}", code="400", data=None
            )

        # 检查是否已有正在运行的同步任务
        existing_task = task_manager.get_downloader_task(downloader_id)
        if existing_task and existing_task.status == TaskStatus.RUNNING:
            return CommonResponse(
                status="error",
                msg="该下载器正在同步中，请等待当前任务完成",
                code="409",
                data={"task_id": existing_task.task_id, "status": existing_task.status.value},
            )

        # 构建下载器信息字典（用于同步）
        downloader_info = {
            "downloader_id": downloader.downloader_id,
            "nickname": downloader.nickname,
            "host": downloader.host,
            "port": downloader.port,
            "username": downloader.username,
            "password": downloader.password,
            "downloader_type": downloader.downloader_type,
            "torrent_save_path": downloader.torrent_save_path,
            "enabled": "1",
            "status": "1",
        }

        # 创建后台任务
        task = await task_manager.create_task(
            task_type="sync", downloader_id=downloader.downloader_id, downloader_nickname=downloader.nickname
        )

        # 定义后台执行函数
        async def execute_sync_task():
            """执行同步任务并更新状态"""
            try:
                if settings.SYNC_CANONICAL_COORDINATOR_ENABLED:
                    # W2-1 新路径：经 SyncCoordinator 统一准入/写治理/观测。
                    # 准入在后台执行体内完成（不阻塞 HTTP 请求线程）。
                    sync_coro = _execute_manual_sync_via_coordinator(downloader_info)
                else:
                    # 应急回滚：旧直接调用 torrent_sync_db_async 全量同步路径。
                    # ⚠️ legacy 只能作为应急回退，禁止与新路径同时执行。
                    sync_coro = torrent_sync_db_async(downloader_info)
                # 执行同步（使用任务管理器的并发控制）
                await task_manager.execute_task(task.task_id, sync_coro)

                # 获取任务结果
                completed_task = task_manager.get_task(task.task_id)
                sync_result = completed_task.result if completed_task else {}

                # 记录审计日志（异步）
                async with AsyncSessionLocal() as async_db:
                    try:
                        audit_service = await get_audit_service(async_db)
                        await audit_service.log_operation(
                            operation_type=AuditOperationType.SYNC,
                            operator="admin",
                            torrent_info_id=None,
                            operation_detail={
                                "downloader_id": downloader.downloader_id,
                                "downloader_name": downloader.nickname,
                                "downloader_type": downloader.downloader_type,
                                "sync_result": sync_result.get("status", "unknown"),
                                "task_id": task.task_id,
                            },
                            new_value={"last_sync_time": datetime.now().isoformat()},
                            operation_result=(
                                AuditOperationResult.SUCCESS
                                if sync_result.get("status") == "success"
                                else AuditOperationResult.FAILED
                            ),
                            downloader_id=downloader.downloader_id,
                            **extract_audit_info_from_request(request),
                        )
                    except Exception as audit_error:
                        logger.error(f"记录审计日志失败: {str(audit_error)}")

            except Exception as e:
                logger.error(f"同步任务执行异常: {task.task_id} - {str(e)}", exc_info=True)
                # 记录失败的审计日志
                try:
                    async with AsyncSessionLocal() as async_db:
                        audit_service = await get_audit_service(async_db)
                        await audit_service.log_operation(
                            operation_type=AuditOperationType.SYNC,
                            operator="admin",
                            torrent_info_id=None,
                            operation_detail={
                                "downloader_id": downloader.downloader_id,
                                "error_message": str(e),
                                "task_id": task.task_id,
                            },
                            operation_result=AuditOperationResult.FAILED,
                            error_message=str(e),
                            downloader_id=downloader.downloader_id,
                            **extract_audit_info_from_request(request),
                        )
                except Exception:
                    pass

        # 在后台启动任务（不阻塞响应）
        asyncio.create_task(execute_sync_task())

        logger.info(f"同步任务已启动: {task.task_id} - {downloader.nickname}")

        # 立即返回任务信息
        return CommonResponse(
            status="success",
            msg=f"同步任务已启动: {downloader.nickname}",
            code="200",
            data={
                "task_id": task.task_id,
                "downloader_id": downloader.downloader_id,
                "nickname": downloader.nickname,
                "status": task.status.value,
                "query_url": f"/torrents/sync-status/{task.task_id}",
                "message": "任务正在后台执行，请使用 task_id 查询进度",
            },
        )

    except SQLAlchemyError as e:
        logger.error(f"数据库操作失败: {str(e)}", exc_info=True)
        return CommonResponse(status="error", msg=f"数据库操作失败: {str(e)}", code="500", data=None)
    except Exception as e:
        logger.error(f"启动同步任务失败: {str(e)}", exc_info=True)
        return CommonResponse(status="error", msg=f"启动同步任务失败: {str(e)}", code="500", data=None)


@router.get("/sync-status/{task_id}", response_model=CommonResponse)
async def get_sync_task_status(
    request: Request,
    task_id: str,
    _user=Depends(require_authenticated_user),
):
    """
    查询同步任务状态接口

    根据任务ID查询同步任务的执行状态和结果。

    Args:
        request: 请求对象
        task_id: 任务ID

    Returns:
        任务状态和结果信息
    """
    try:
        # 从任务管理器获取任务
        task = task_manager.get_task(task_id)

        if not task:
            return CommonResponse(status="error", msg=f"任务不存在: {task_id}", code="404", data=None)

        # 返回任务信息
        return CommonResponse(status="success", msg="查询成功", code="200", data=task.to_dict())

    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询任务状态失败: {str(e)}", code="500", data=None)


# ==================== Tracker状态更新 ====================


async def update_tracker_status_from_keywords() -> Dict[str, Any]:
    """
    根据关键词看板更新tracker状态（W1-2 兼容包装）

    在种子同步完成后调用此函数，按tracker_host分组，
    根据关键词池判断每个tracker的状态，并更新到数据库。

    判断规则（由服务层承担，语义不变）：
    - 全部失败 → status = 'error'
    - 有成功/忽略 → status = 'normal'
    - 其他情况 → status = 'unknown'

    W1-2 起 Tracker 全表更新业务逻辑搬迁至
    app/services/tracker_status_sync.py::sync_tracker_status_from_keywords
    （增量写：只写判定结果有变化的行，零变化零 DML；统一分批写入
    bulk_upsert_with_retry）。本函数仅负责：
    1. 自建 AsyncSessionLocal 会话；
    2. 调用服务层；
    3. 将 TrackerStatusStats 映射回历史返回结构，并追加
       scanned/changed/unchanged/batches/duration_ms 新字段。

    两个调用方（torrent_sync_async / tracker_sync_task）因此零改动。

    Returns:
        更新结果字典
    """
    from app.database import AsyncSessionLocal
    from app.services.tracker_status_sync import sync_tracker_status_from_keywords

    try:
        async with AsyncSessionLocal() as db:
            stats = await sync_tracker_status_from_keywords(db)

        # 无关键词 / 无 tracker 提前返回，保持原消息语义
        if stats.reason == "no_keywords":
            return {
                "status": "success",
                "message": "未加载到任何关键词",
                "updated_count": 0,
                "scanned": stats.scanned,
                "changed": stats.changed,
                "unchanged": stats.unchanged,
                "batches": stats.batches,
                "duration_ms": stats.duration_ms,
            }
        if stats.reason == "no_trackers":
            return {
                "status": "success",
                "message": "未发现任何tracker",
                "updated_count": 0,
                "scanned": stats.scanned,
                "changed": stats.changed,
                "unchanged": stats.unchanged,
                "batches": stats.batches,
                "duration_ms": stats.duration_ms,
            }

        # 统一写入器成功返回即代表变化集全部提交成功（失败会抛异常），故 failed_count=0
        updated_count = stats.changed
        failed_count = 0

        return {
            "status": "success",
            "message": f"更新完成: {updated_count}条成功, {failed_count}条失败",
            "updated_count": updated_count,
            "failed_count": failed_count,
            "total_hosts": stats.total_hosts,
            "scanned": stats.scanned,
            "changed": stats.changed,
            "unchanged": stats.unchanged,
            "batches": stats.batches,
            "duration_ms": stats.duration_ms,
        }

    except Exception as e:
        logger.error(f"更新tracker状态失败: {str(e)}", exc_info=True)
        return {"status": "error", "message": f"更新失败: {str(e)}", "updated_count": 0}
