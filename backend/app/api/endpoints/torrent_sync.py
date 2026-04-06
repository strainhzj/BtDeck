import asyncio
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import update, exists
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import SQLAlchemyError

from app.api.responseVO import CommonResponse
from app.database import get_db, AsyncSessionLocal
from app.auth import utils
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo as torrentInfoModel, TorrentInfo
from app.torrents.models import TrackerInfo as trackerInfoModel, TrackerInfo
from qbittorrentapi import Client as qbClient
from transmission_rpc import Client as trClient
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.core.background_task_manager import task_manager, TaskStatus
from app.models.setting_templates import DownloaderTypeEnum
# 审计日志相关导入（使用异步版本）
from app.services.audit_service import AuditLogService, get_audit_service, extract_audit_info_from_request
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
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

def get_torrent_by_hash(
        db: Session,
        hash_value: str,
        downloader_id: Optional[str] = None
) -> Optional[TorrentInfo]:
    """
    通过哈希值获取种子信息

    Args:
        db: 数据库会话
        hash_value: 种子哈希值
        downloader_id: 下载器ID（可选，用于限定查询范围）

    Returns:
        种子信息对象或None
    """
    query = db.query(TorrentInfo).filter(
        TorrentInfo.hash == hash_value,
        TorrentInfo.dr == 0  # 只查询未删除的记录
    )

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

async def torrent_sync_db_async(downloader_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    异步版本的种子同步数据库函数

    使用 AsyncSessionLocal 进行异步数据库操作，
    替代同步版本的 torrent_sync 函数。

    Args:
        downloader_info: 下载器信息字典

    Returns:
        同步结果字典
    """
    from app.database import AsyncSessionLocal
    from app.api.endpoints.torrents_async import qb_add_torrents_async, tr_add_torrents_async

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
            if original_type == 'qbittorrent' or original_type == 0 or original_type == '0':
                downloader_type_str = 'qbittorrent'
            elif original_type == 'transmission' or original_type == 1 or original_type == '1':
                downloader_type_str = 'transmission'
            else:
                # 未知类型
                error_msg = f"不支持的下载器类型: {original_type} (类型: {type(original_type).__name__})"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "message": error_msg,
                    "downloader_type": str(original_type),
                    "nickname": downloader.nickname
                }

            # 使用转换后的类型进行判断
            if downloader_type_str == 'qbittorrent':
                try:
                    await qb_add_torrents_async(db, [downloader])
                    logger.info(f"Successfully synced qBittorrent downloader: {downloader.nickname}")
                    return {
                        "status": "success",
                        "message": f"qBittorrent下载器 {downloader.nickname} 同步成功",
                        "downloader_type": "qbittorrent",
                        "nickname": downloader.nickname
                    }
                except Exception as sync_error:
                    # ✅ 关键修复：捕获同步异常，正确标记任务失败
                    logger.error(f"qBittorrent下载器 {downloader.nickname} 同步失败: {str(sync_error)}")
                    return {
                        "status": "failed",
                        "message": f"同步失败: {str(sync_error)}",
                        "downloader_type": "qbittorrent",
                        "nickname": downloader.nickname
                    }

            elif downloader_type_str == 'transmission':
                try:
                    await tr_add_torrents_async(db, [downloader])
                    logger.info(f"Successfully synced Transmission downloader: {downloader.nickname}")
                    return {
                        "status": "success",
                        "message": f"Transmission下载器 {downloader.nickname} 同步成功",
                        "downloader_type": "transmission",
                        "nickname": downloader.nickname
                    }
                except Exception as sync_error:
                    # ✅ 关键修复：捕获同步异常，正确标记任务失败
                    logger.error(f"Transmission下载器 {downloader.nickname} 同步失败: {str(sync_error)}")
                    return {
                        "status": "failed",
                        "message": f"同步失败: {str(sync_error)}",
                        "downloader_type": "transmission",
                        "nickname": downloader.nickname
                    }

        except Exception as e:
            error_msg = f"同步下载器 {downloader_info.get('nickname', 'Unknown')} 失败: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "failed",
                "message": error_msg,
                "downloader_type": downloader_info.get('downloader_type', 'unknown'),
                "nickname": downloader_info.get('nickname', 'unknown')
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
        logger.info(f"[TORRENT_SYNC] 开始种子同步任务")
        logger.info(f"[TORRENT_SYNC] 使用的 app 实例 id: {id(downloader_app)}")
        logger.info(f"[TORRENT_SYNC] app 类型: {type(downloader_app)}")

        # 检查 app.state.store 是否存在
        if not hasattr(downloader_app, 'state') or not hasattr(downloader_app.state, 'store'):
            logger.error(f"[TORRENT_SYNC] app.state.store 不存在！app 类型: {type(downloader_app)}")
            logger.error(f"[TORRENT_SYNC] app.state 属性: {hasattr(downloader_app, 'state')}")
            if hasattr(downloader_app, 'state'):
                logger.error(f"[TORRENT_SYNC] app.state 的属性: {dir(downloader_app.state)}")
            return {
                "status": "failed",
                "message": "下载器缓存未初始化 (app.state.store 不存在)",
                "successful_syncs": 0,
                "failed_syncs": 0,
                "total_downloaders": 0
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
                "total_downloaders": 0
            }

        # 只对有效的下载器（fail_time=0）进行种子同步
        valid_downloaders = [
            d for d in cached_downloaders
            if hasattr(d, 'fail_time') and d.fail_time == 0
        ]

        # 记录失效下载器信息
        failed_downloaders = [
            d for d in cached_downloaders
            if hasattr(d, 'fail_time') and d.fail_time > 0
        ]

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
                "failed_count": len(failed_downloaders)
            }

        # 记录将要同步的下载器列表
        for downloader in valid_downloaders:
            logger.info(
                f"[TORRENT_SYNC] 准备同步: {downloader.nickname} (type={getattr(downloader, 'downloader_type', 'unknown')})")

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
                        'downloader_id': getattr(downloader_check_vo, 'downloader_id', None),
                        'nickname': downloader_check_vo.nickname,
                        'host': getattr(downloader_check_vo, 'host', None),
                        'port': getattr(downloader_check_vo, 'port', None),
                        'username': getattr(downloader_check_vo, 'username', None),
                        'password': getattr(downloader_check_vo, 'password', None),
                        'downloader_type': getattr(downloader_check_vo, 'downloader_type', None),
                        'torrent_save_path': getattr(downloader_check_vo, 'torrent_save_path', None),  # 🔧 添加种子保存目录
                        'enabled': '1',
                        'status': '1'
                    }

                    # 调用异步种子同步函数
                    result = await torrent_sync_db_async(downloader_info)

                    return result

                except Exception as e:
                    error_result = {
                        "status": "failed",
                        "message": f"Torrent sync error for {downloader_check_vo.nickname}: {str(e)}",
                        "nickname": downloader_check_vo.nickname
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
                    "nickname": "unknown"
                }
                errors.append(error_result)
                logger.error(f"[TORRENT_SYNC] 同步异常: {str(result)}")
            elif result.get('status') == 'success':
                successful_syncs += 1
                logger.info(f"[TORRENT_SYNC] 同步成功: {result.get('nickname', 'unknown')}")
            else:
                failed_syncs += 1
                logger.warning(
                    f"[TORRENT_SYNC] 同步失败: {result.get('nickname', 'unknown')} - {result.get('message', 'Unknown error')}")

        # 种子同步完成后，根据关键词看板更新tracker状态
        logger.info(f"[TORRENT_SYNC] 种子同步完成，成功: {successful_syncs}, 失败: {failed_syncs}")
        logger.info(f"[TORRENT_SYNC] 开始更新 Tracker 状态")
        tracker_status_result = await update_tracker_status_from_keywords()

        logger.info(f"[TORRENT_SYNC] Tracker状态更新完成: {tracker_status_result.get('message', 'N/A')}")
        logger.info(f"[TORRENT_SYNC] ✅ 种子同步任务全部完成")

        return {
            "status": "success" if failed_syncs == 0 else "partial",
            "message": f"Sync completed: {successful_syncs} successful, {failed_syncs} failed",
            "successful_syncs": successful_syncs,
            "failed_syncs": failed_syncs,
            "total_downloaders": len(valid_downloaders),
            "tracker_status_update": tracker_status_result
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": f"Torrent sync task failed: {str(e)}",
            "successful_syncs": 0,
            "failed_syncs": 0,
            "total_downloaders": 0
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

    # 优先使用缓存连接（约束16）
    tr_client = None
    if app and hasattr(app.state, 'store'):
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == bt_downloader.downloader_id),
            None
        )
        if downloader_vo and hasattr(downloader_vo, 'client') and downloader_vo.client:
            tr_client = downloader_vo.client

    if tr_client is None:
        tr_client = trClient(
            host=bt_downloader.host,
            username=bt_downloader.username,
            password=bt_downloader.password,
            port=bt_downloader.port,
            protocol="http",
            timeout=100.0
        )
    torrent_info_list = tr_client.get_torrents()
    current_time = datetime.now()
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
        torrent = torrentInfoModel(
            id_=torrent_info_id,
            downloader_id=bt_downloader.downloader_id,
            downloader_name=bt_downloader.nickname,
            torrent_id=torrent_info.id,
            hash=torrent_info.hashString,
            name=torrent_info.name,
            status=TorrentStatusMapper.convert_transmission_status(torrent_info.status),
            save_path=torrent_info.download_dir,
            size=torrent_info.total_size,
            torrent_file=torrent_info.torrent_file,
            added_date=torrent_info.added_date,
            completed_date=torrent_info.done_date if torrent_info.done_date else None,
            ratio=torrent_info.ratio,
            ratio_limit=torrent_info.seed_ratio_limit,
            tags=",".join(torrent_info.labels) if hasattr(torrent_info, 'labels') and torrent_info.labels else "",
            category="",
            super_seeding="",
            enabled=1,
            create_time=current_time,
            create_by="admin",
            update_time=current_time,
            update_by="admin",
            dr=0
        )
        try:
            if mode == "insert":
                db.add(torrent)
            if mode == "update":
                torrent_dict = torrent.to_dict()
                update_torrent(db, result_info.info_id, torrent_dict)
                # db.query(torrent_info_model).filter(torrent_info_model.info_id == torrent_info_id).update
            sync_add_tracker(db, bt_downloader.downloader_type, mode, torrent_info, torrent_info_id)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating database: {str(e)}")


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
        trackers_data = getattr(torrent_info, 'trackers', None)
        if callable(trackers_data):
            trackers_data = trackers_data()
        trackers_data = trackers_data or []

        for tracker in trackers_data:
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

    elif type_name == "transmission":
        tracker_stats = getattr(torrent_info, 'tracker_stats', None) or []
        for tracker_status in tracker_stats:
            tracker_url = tracker_status.fields.get('announce')
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

        # ✅ P0修复：使用事务保护，确保删除和插入的原子性
        if soft_deleted_pairs or tracker_rows:
            with db.begin():
                # 删除软删除记录，避免upsert时恢复
                if soft_deleted_pairs:
                    db.execute(
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

    # 优先使用缓存连接（约束16）
    client = None
    if app and hasattr(app.state, 'store'):
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == bt_downloader.downloader_id),
            None
        )
        if downloader_vo and hasattr(downloader_vo, 'client') and downloader_vo.client:
            client = downloader_vo.client

    if client is None:
        # P0-1 修复: 添加30秒超时，避免无限阻塞
        client = qbClient(
            host=bt_downloader.host,
            port=bt_downloader.port,
            username=bt_downloader.username,
            password=bt_downloader.password,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS={'timeout': 30}  # 30秒超时
        )
    torrent_info_list = client.torrents_info()
    current_time = datetime.now()
    for torrent_info in torrent_info_list:
        torrent_query_result = \
            db.query(torrentInfoModel.info_id, torrentInfoModel.create_time).filter(
                torrentInfoModel.hash == torrent_info.hash).filter(
                torrentInfoModel.downloader_id == bt_downloader.downloader_id).filter(
                torrentInfoModel.dr == 0).all()
        if torrent_query_result.__len__() == 0:
            mode = "insert"
            torrent_info_id = str(uuid.uuid4())
            create_time = current_time
            update_time = current_time
        else:
            mode = "update"
            torrent_info_id = torrent_query_result[0][0]
            create_time = torrent_query_result[0][1]
            if create_time == None:
                create_time = current_time
            update_time = current_time
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
            added_date=datetime.fromtimestamp(torrent_info.added_on),
            completed_date=datetime.fromtimestamp(torrent_info.completion_on),
            ratio=torrent_info.ratio,
            ratio_limit=torrent_info.ratio_limit,
            tags=torrent_info.tags,
            category=torrent_info.category,
            super_seeding=torrent_info.super_seeding,
            enabled=1,
            create_time=create_time,
            create_by="admin",
            update_time=update_time,
            update_by="admin",
            dr=0
        )

        try:
            result_info = get_torrent_by_hash(db, torrent_info.hash, bt_downloader.downloader_id)
            if result_info:
                torrent_dict = torrent.to_dict()
                update_torrent(db, result_info.info_id, torrent_dict)
            else:
                db.add(torrent)
            sync_add_tracker(db, bt_downloader.downloader_type, mode, torrent_info, torrent_info_id)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating database: {str(e)}")


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
            tracker = db.query(trackerInfoModel).filter(
                trackerInfoModel.tracker_id == tracker_id,
                trackerInfoModel.dr == 0
            ).first()

            if tracker is None:
                logger.warning(f"乐观锁更新失败: tracker {tracker_id} 不存在或已删除")
                return False

            old_version = tracker.version

            # 创建新的数据字典副本，避免污染传入的参数
            final_update_data = update_data.copy()
            final_update_data['version'] = old_version + 1

            # 执行更新（带版本检查）
            affected_rows = db.query(trackerInfoModel).filter(
                trackerInfoModel.tracker_id == tracker_id,
                trackerInfoModel.version == old_version,
                trackerInfoModel.dr == 0
            ).update(final_update_data)

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


def restore_deleted_tracker(db, torrent_info_id, tracker_url, tracker_data, current_time,
                            max_retries=MAX_OPTIMISTIC_LOCK_RETRIES):
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
            deleted_tracker = db.query(trackerInfoModel).filter(
                trackerInfoModel.torrent_info_id == torrent_info_id,
                trackerInfoModel.tracker_url == tracker_url,
                trackerInfoModel.dr == 1
            ).first()

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

            affected_rows = db.query(trackerInfoModel).filter(
                trackerInfoModel.tracker_id == deleted_tracker.tracker_id,
                trackerInfoModel.version == deleted_tracker.version,
                trackerInfoModel.dr == 1
            ).update(update_data)

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
            logger.warning("current_tracker_urls is empty, skip mark-removed trackers"
                           )
            return

        result = db.execute(
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
            logger.warning(f"current_tracker_urls 为空集合，跳过标记已移除 tracker 的操作")
            return

        # 查询所有活跃的 tracker
        existing_trackers = db.query(trackerInfoModel).filter(
            trackerInfoModel.torrent_info_id == torrent_info_id,
            trackerInfoModel.dr == 0
        ).all()

        removed_count = 0
        for existing_tracker in existing_trackers:
            if existing_tracker.tracker_url not in current_tracker_urls:
                # 使用乐观锁标记为删除
                update_data = {
                    'dr': 1,
                    'update_time': current_time,
                    'update_by': 'system',
                    'version': existing_tracker.version + 1
                }

                affected_rows = db.query(trackerInfoModel).filter(
                    trackerInfoModel.tracker_id == existing_tracker.tracker_id,
                    trackerInfoModel.version == existing_tracker.version,
                    trackerInfoModel.dr == 0
                ).update(update_data)

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
        active_tracker = db.query(trackerInfoModel).filter(
            trackerInfoModel.torrent_info_id == torrent_info_id,
            trackerInfoModel.tracker_url == tracker_url,
            trackerInfoModel.dr == 0
        ).first()

        if active_tracker is not None:
            # 准备更新数据（保留 create_time/create_by）
            # 使用 get() 并提供默认值，防止 None 写入数据库
            update_data = {
                'tracker_name': tracker_data.get('tracker_name', active_tracker.tracker_name),
                'last_announce_succeeded': tracker_data.get('last_announce_succeeded', 0),
                'last_announce_msg': tracker_data.get('last_announce_msg', ''),
                'last_scrape_succeeded': tracker_data.get('last_scrape_succeeded', 0),
                'last_scrape_msg': tracker_data.get('last_scrape_msg', ''),
                'update_time': current_time,
                'update_by': 'admin'
            }

            # 使用乐观锁更新
            success = update_tracker_with_optimistic_lock(
                db, active_tracker.tracker_id, update_data
            )

            if success:
                logger.debug(f"更新 tracker 成功: {tracker_url}")
            else:
                logger.warning(f"更新 tracker 失败（重试耗尽）: {tracker_url}")

            return True  # 已处理

        # 步骤2：查询已删除记录（dr=1）
        deleted_tracker = db.query(trackerInfoModel).filter(
            trackerInfoModel.torrent_info_id == torrent_info_id,
            trackerInfoModel.tracker_url == tracker_url,
            trackerInfoModel.dr == 1
        ).first()

        if deleted_tracker is not None:
            # 恢复已删除的记录
            success = restore_deleted_tracker(
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
        logger.error(f"update_or_restore_tracker 异常: {e}, tracker_url={tracker_url}")
        return False


# ==================== 同步接口 ====================

@router.post("/sync-single", response_model=CommonResponse)
async def sync_single_downloader(
        request: Request,
        sync_request: SyncSingleRequest,
        db: Session = Depends(get_db)
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
        # 验证token
        token = request.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )

    try:
        downloader_id = sync_request.downloader_id

        # 从数据库查询下载器信息
        downloader = db.query(BtDownloaders).filter(
            BtDownloaders.downloader_id == downloader_id,
            BtDownloaders.dr == 0
        ).first()

        if not downloader:
            return CommonResponse(
                status="error",
                msg=f"下载器不存在: {downloader_id}",
                code="404",
                data=None
            )

        # 检查下载器是否启用
        if downloader.enabled != True or downloader.status != '1':
            return CommonResponse(
                status="error",
                msg=f"下载器未启用或已停用: {downloader.nickname}",
                code="400",
                data=None
            )

        # 检查是否已有正在运行的同步任务
        existing_task = task_manager.get_downloader_task(downloader_id)
        if existing_task and existing_task.status == TaskStatus.RUNNING:
            return CommonResponse(
                status="error",
                msg=f"该下载器正在同步中，请等待当前任务完成",
                code="409",
                data={
                    "task_id": existing_task.task_id,
                    "status": existing_task.status.value
                }
            )

        # 构建下载器信息字典（用于同步）
        downloader_info = {
            'downloader_id': downloader.downloader_id,
            'nickname': downloader.nickname,
            'host': downloader.host,
            'port': downloader.port,
            'username': downloader.username,
            'password': downloader.password,
            'downloader_type': downloader.downloader_type,
            'torrent_save_path': downloader.torrent_save_path,
            'enabled': '1',
            'status': '1'
        }

        # 创建后台任务
        task = await task_manager.create_task(
            task_type="sync",
            downloader_id=downloader.downloader_id,
            downloader_nickname=downloader.nickname
        )

        # 定义后台执行函数
        async def execute_sync_task():
            """执行同步任务并更新状态"""
            try:
                # 执行同步（使用任务管理器的并发控制）
                await task_manager.execute_task(
                    task.task_id,
                    torrent_sync_db_async(downloader_info)
                )

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
                                "task_id": task.task_id
                            },
                            new_value={"last_sync_time": datetime.now().isoformat()},
                            operation_result=AuditOperationResult.SUCCESS if sync_result.get(
                                "status") == "success" else AuditOperationResult.FAILED,
                            downloader_id=downloader.downloader_id,
                            **extract_audit_info_from_request(request)
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
                                "task_id": task.task_id
                            },
                            operation_result=AuditOperationResult.FAILED,
                            error_message=str(e),
                            downloader_id=downloader.downloader_id,
                            **extract_audit_info_from_request(request)
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
                "message": "任务正在后台执行，请使用 task_id 查询进度"
            }
        )

    except SQLAlchemyError as e:
        logger.error(f"数据库操作失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"数据库操作失败: {str(e)}",
            code="500",
            data=None
        )
    except Exception as e:
        logger.error(f"启动同步任务失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"启动同步任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/sync-status/{task_id}", response_model=CommonResponse)
async def get_sync_task_status(
        request: Request,
        task_id: str
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
        # 验证token
        token = request.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )

    try:
        # 从任务管理器获取任务
        task = task_manager.get_task(task_id)

        if not task:
            return CommonResponse(
                status="error",
                msg=f"任务不存在: {task_id}",
                code="404",
                data=None
            )

        # 返回任务信息
        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data=task.to_dict()
        )

    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"查询任务状态失败: {str(e)}",
            code="500",
            data=None
        )


# ==================== Tracker状态更新 ====================

async def update_tracker_status_from_keywords() -> Dict[str, Any]:
    """
    根据关键词看板更新tracker状态

    在种子同步完成后调用此函数，按tracker_host分组，
    根据关键词池判断每个tracker的状态，并批量更新到数据库。

    判断规则：
    - 全部失败 → status = 'error'
    - 有成功/忽略 → status = 'normal'
    - 其他情况 → status = 'unknown'

    Returns:
        更新结果字典
    """
    from app.database import AsyncSessionLocal
    from app.torrents.models import TrackerInfo, TrackerKeywordConfig
    from sqlalchemy import select, func
    from urllib.parse import urlparse
    from datetime import datetime

    try:
        async with AsyncSessionLocal() as db:
            # Step 1: 加载所有启用的关键词到内存
            result = await db.execute(
                select(TrackerKeywordConfig).filter(
                    TrackerKeywordConfig.enabled == True,
                    TrackerKeywordConfig.dr == 0
                )
            )
            keywords = result.scalars().all()

            # 构建关键词字典 {keyword: keyword_type}
            keyword_map = {}
            for kw in keywords:
                if kw.keyword not in keyword_map:
                    keyword_map[kw.keyword] = kw.keyword_type
                # 如果重复，保留后读取的（通常priority更高）

            logger.debug(f"加载关键词: {len(keyword_map)}条")

            if not keyword_map:
                return {
                    "status": "success",
                    "message": "未加载到任何关键词",
                    "updated_count": 0
                }

            # Step 2: 查询所有tracker信息（只查询需要的字段）
            result = await db.execute(
                select(
                    TrackerInfo.tracker_id,
                    TrackerInfo.tracker_url,
                    TrackerInfo.last_announce_msg,
                    TrackerInfo.last_scrape_msg,
                    TrackerInfo.tracker_host
                ).filter(
                    TrackerInfo.dr == 0
                )
            )
            trackers = result.all()

            if not trackers:
                return {
                    "status": "success",
                    "message": "未发现任何tracker",
                    "updated_count": 0
                }

            logger.debug(f"发现tracker记录: {len(trackers)}条")

            # Step 3: 按tracker_host分组，提取消息
            tracker_host_msgs = {}  # {tracker_host: [(tracker_id, msg), ...]}

            for tracker in trackers:
                tracker_id = tracker.tracker_id
                tracker_url = tracker.tracker_url
                announce_msg = tracker.last_announce_msg
                scrape_msg = tracker.last_scrape_msg
                tracker_host = tracker.tracker_host

                # 如果tracker_host为空，尝试从URL提取
                if not tracker_host and tracker_url:
                    try:
                        parsed = urlparse(tracker_url)
                        if parsed and parsed.hostname:
                            tracker_host = parsed.hostname
                            logger.debug(f"从URL提取tracker_host: {tracker_host}")
                    except Exception as e:
                        logger.debug(f"解析tracker URL失败: {tracker_url}, 错误: {e}")

                if not tracker_host:
                    logger.debug(f"跳过无tracker_host的记录: tracker_id={tracker_id}")
                    continue

                # 优先使用announce消息，为空则使用scrape消息
                msg = announce_msg or scrape_msg or ""

                # 过滤空消息
                if not msg or not msg.strip():
                    continue

                if tracker_host not in tracker_host_msgs:
                    tracker_host_msgs[tracker_host] = []

                tracker_host_msgs[tracker_host].append({
                    "tracker_id": tracker_id,
                    "msg": msg.strip()
                })

            logger.debug(f"按tracker_host分组后: {len(tracker_host_msgs)}个host")

            # Step 4: 判断每个tracker_host的状态
            tracker_status_map = {}  # {tracker_id: (status, msg)}

            for tracker_host, msg_list in tracker_host_msgs.items():
                # 判断每条消息的类型
                msg_types = []
                for item in msg_list:
                    msg = item["msg"]

                    # 精确匹配关键词（优先级高）
                    exact_match = None
                    if msg in keyword_map:
                        exact_match = keyword_map[msg]
                    elif msg.strip() in keyword_map:  # 去除前后空格后再匹配
                        exact_match = keyword_map[msg.strip()]

                    if exact_match:
                        msg_types.append(exact_match)
                    else:
                        # 尝试部分匹配（关键词包含在消息中）
                        partial_match = None
                        for keyword, keyword_type in keyword_map.items():
                            if keyword.lower() in msg.lower():
                                partial_match = keyword_type
                                break

                        if partial_match:
                            msg_types.append(partial_match)
                            logger.debug(f"部分匹配成功: msg='{msg[:50]}...' keyword='{partial_match}'")
                        else:
                            msg_types.append("unknown")

                # 判断规则
                if all(t == "failed" for t in msg_types):
                    # 全部失败 → error
                    status = "error"
                    status_msg = "失败"
                elif any(t in ["success", "ignored"] for t in msg_types):
                    # 有成功或忽略 → normal
                    status = "normal"
                    status_msg = "正常"
                else:
                    # 其他情况 → unknown
                    status = "unknown"
                    status_msg = "未知"

                # 将状态应用到该host下的所有tracker
                for item in msg_list:
                    tracker_status_map[item["tracker_id"]] = (status, status_msg)

                logger.debug(f"Tracker Host: {tracker_host} | 状态: {status} | 消息类型: {msg_types}")

            # Step 5: 批量更新数据库（使用UPDATE语句，保留乐观锁）
            from sqlalchemy import update

            updated_count = 0
            failed_tracker_ids = []

            for tracker_id, (status, status_msg) in tracker_status_map.items():
                try:
                    # 使用UPDATE语句批量更新（带乐观锁）
                    result = await db.execute(
                        update(TrackerInfo)
                        .where(TrackerInfo.tracker_id == tracker_id)
                        .values(
                            status=status,
                            msg=status_msg,
                            update_time=datetime.now(),
                            version=TrackerInfo.version + 1  # 子查询方式更新version
                        )
                        .execution_options(synchronize_session=False)
                    )

                    # 检查是否真正更新了数据（乐观锁可能失败）
                    if result.rowcount > 0:
                        updated_count += 1
                    else:
                        # rowcount=0 表示记录不存在或乐观锁冲突
                        failed_tracker_ids.append(tracker_id)
                        logger.debug(f"Tracker更新失败(未找到或乐观锁冲突): tracker_id={tracker_id}")

                except Exception as e:
                    failed_tracker_ids.append(tracker_id)
                    logger.debug(f"Tracker更新异常: tracker_id={tracker_id}, 错误={str(e)}")

            await db.commit()

            logger.debug(f"Tracker状态批量更新完成: 成功{updated_count}条, 失败{len(failed_tracker_ids)}条")
            if failed_tracker_ids:
                logger.debug(f"失败的tracker_ids: {failed_tracker_ids}")

            return {
                "status": "success",
                "message": f"更新完成: {updated_count}条成功, {len(failed_tracker_ids)}条失败",
                "updated_count": updated_count,
                "failed_count": len(failed_tracker_ids),
                "failed_tracker_ids": failed_tracker_ids,
                "total_hosts": len(tracker_host_msgs)
            }

    except Exception as e:
        logger.error(f"更新tracker状态失败: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"更新失败: {str(e)}",
            "updated_count": 0
        }
