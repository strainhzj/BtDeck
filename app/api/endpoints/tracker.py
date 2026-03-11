from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Request, Query, BackgroundTasks
import json
from pathlib import Path

from app.api.responseVO import CommonResponse
from sqlalchemy import text, distinct, select, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_db, AsyncSessionLocal
from app.auth import utils
import uuid
import logging
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo as torrentInfoModel
from app.torrents.models import TrackerInfo as trackerInfoModel
from transmission_rpc import Client as trClient
from qbittorrentapi import Client as qbClient
# 审计日志相关导入
from app.services.audit_service import get_audit_service, AuditLogService, extract_audit_info_from_request
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult

logger = logging.getLogger(__name__)
router = APIRouter()

# 审计日志配置常量
MAX_AUDIT_LOG_ENTRIES = 10  # 批量操作时最多详细记录的条目数


@router.post("/addTracker", summary="添加种子tracker地址", response_model=CommonResponse)
async def add_tracker(req: Request, background_tasks: BackgroundTasks, torrent_info_ids: str = Query(
    default="default",
    alias="torrentInfoIds",
    description="torrent_info_id列表",
    examples={"default": "91a92a76-9640-4c50-bb03-381a4d37158c"}
), trackers: str = Query(
    default="default",
    alias="trackers",
    description="多个tracker以;分隔",
    examples={"default": "https://ptskit.kqbhek.com1/announce.php?passkey=6fa2d880b3666a460f7ed063f7b9818b"}
), db: AsyncSession = Depends(get_async_db)):
    """
       添加tracker

       Args:
           req: 请求头
           db: 数据库会话
           torrent_info_ids: 种子数据列表
           trackers: tracker地址

       """
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )
        return response

    torrent_info_id_list = torrent_info_ids.split(',')
    tracker_list = trackers.split(';')
    success_count = 0
    failed_count = 0

    for torrent_info_id in torrent_info_id_list:
        try:
            result = await db.execute(
                select(torrentInfoModel).where(torrentInfoModel.info_id == torrent_info_id)
            )
            torrent = result.scalar_one_or_none()
            # P1-1 修复: 删除重复的种子存在性检查
            if not torrent:
                logging.error(f"种子不存在: torrent_info_id={torrent_info_id}")
                failed_count += 1
                continue
            # 修复异步查询: 查询下载器
            result = await db.execute(
                select(BtDownloaders).where(
                    BtDownloaders.dr == 0,
                    BtDownloaders.downloader_id == torrent.downloader_id
                )
            )
            downloaders = result.scalars().all()

            if not downloaders:
                logging.error(f"下载器不存在: downloader_id={torrent.downloader_id}")
                failed_count += 1
                continue

            if not downloaders:
                logging.error(f"下载器不存在: downloader_id={torrent.downloader_id}")
                failed_count += 1
                continue

            # 使用变量避免重复访问downloaders[0]
            downloader = downloaders[0]
            if downloader.is_qbittorrent:
                qb_add_torrents_tracker(db, downloaders, tracker_list, torrent.torrent_id, torrent_info_id)
            if downloader.is_transmission:
                tr_add_torrents_tracker(db, downloaders, tracker_list, int(torrent.torrent_id), torrent_info_id)

            success_count += 1

            # ========== 记录审计日志（后台任务） ==========
            # P2修复: 添加防御性检查
            audit_info = extract_audit_info_from_request(req) or {}
            background_tasks.add_task(
                _write_tracker_audit_log_async,
                operation_type=AuditOperationType.ADD_TRACKER,
                operator="admin",
                torrent_info_id=torrent_info_id,
                operation_detail={
                    "torrent_name": torrent.name,
                    "trackers": tracker_list,
                    "tracker_count": len(tracker_list)
                },
                new_value={"trackers_added": tracker_list},
                operation_result=AuditOperationResult.SUCCESS,
                downloader_id=torrent.downloader_id,
                audit_info=audit_info
            )
            # ========== 审计日志记录结束 ==========

        except Exception as e:
            failed_count += 1
            logging.error(f"添加tracker失败: {str(e)}")

            # ========== 记录失败的审计日志（后台任务） ==========
            # P2修复: 添加防御性检查
            audit_info = extract_audit_info_from_request(req) or {}
            background_tasks.add_task(
                _write_tracker_audit_log_async,
                operation_type=AuditOperationType.ADD_TRACKER,
                operator="admin",
                torrent_info_id=torrent_info_id,
                operation_detail={
                    "trackers": tracker_list,
                    "tracker_count": len(tracker_list)
                },
                error_message=str(e),
                operation_result=AuditOperationResult.FAILED,
                downloader_id=None,
                audit_info=audit_info
            )
            # ========== 审计日志记录结束 ==========

    return CommonResponse(
        status="success",
        msg=f"添加Tracker成功，成功: {success_count}，失败: {failed_count}",
        code="200",
        data={"success_count": success_count, "failed_count": failed_count}
    )


@router.post("/replaceTracker", summary="替换种子tracker地址", response_model=CommonResponse)
async def replace_tracker(req: Request, background_tasks: BackgroundTasks, replace_tracker_url: str = Query(
    default="default",
    alias="torrentInfoIds",
    description="被替换的tracker地址",
    examples={"default": "https://tracker.pterclub.com/announce?passkey=e0bde7f14f78cea7d704eb157815bbdc"}
), target_tracker_url: str = Query(
    default="default",
    alias="trackers",
    description="替换成的tracker地址",
    examples={"default": "https://tracker.pterclub.net/announce?passkey=e0bde7f14f78cea7d704eb157815bbdc"}
), db: AsyncSession = Depends(get_async_db)):
    """
       根据tracker链接地址替换tracker

       Args:
           req: 请求头
           db: 数据库会话
           replace_tracker_url: 要被替换的tracker
           target_tracker_url: 要替换的tracker

       """
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )
        return response

    # ========== 记录替换前的信息用于审计日志 ==========
    # 根据被替换的tracker查询相应tracker数据
    # 修复异步查询: 使用select()替代db.query()
    result = await db.execute(
        select(trackerInfoModel).where(
            trackerInfoModel.tracker_url == replace_tracker_url,
            trackerInfoModel.dr == 0
        )
    )
    tracker_info_list = result.scalars().all()

    if not tracker_info_list:
        return CommonResponse(
            status="error",
            msg="未找到要替换的tracker",
            code="404",
            data=None
        )

    affected_torrents = []
    for tracker_info in tracker_info_list:
        # 修复异步查询: 查询种子信息
        result = await db.execute(
            select(torrentInfoModel).where(torrentInfoModel.info_id == tracker_info.torrent_info_id)
        )
        torrent = result.scalar_one_or_none()
        if torrent:
            affected_torrents.append({
                "torrent_info_id": torrent.info_id,
                "torrent_name": torrent.name,
                "downloader_id": torrent.downloader_id
            })
    # ========== 审计日志信息获取结束 ==========

    # 作废所有旧数据
    await db.execute(
        text("update tracker_info set update_time=datetime('now'),dr=1 where tracker_url = :tracker_url and dr = 0"),
        {"tracker_url": replace_tracker_url})
    torrent_info_id_list = []
    for row in tracker_info_list:
        torrent_info_id_list.append(row.torrent_info_id)
        # 根据旧数据生成新数据
        row.tracker_id = str(uuid.uuid4())
        row.tracker_url = target_tracker_url
        db.add(row)
    # 查询相应的下载器id
    # 查询相应的下载器id
    # 修复异步查询: 使用select(distinct())替代db.query(distinct())
    result = await db.execute(
        select(distinct(torrentInfoModel.downloader_id)).where(
            torrentInfoModel.info_id.in_(torrent_info_id_list),
            torrentInfoModel.dr == 0
        )
    )
    downloader_id_list = result.all()
    # 根据下载器id循环修改
    for row in downloader_id_list:
        downloader_id = row[0]
        torrent_id_list = []
        # 修复异步查询: 查询下载器
        result = await db.execute(
            select(BtDownloaders).where(BtDownloaders.downloader_id == downloader_id)
        )
        downloader = result.scalar_one_or_none()

        if not downloader:
            logging.error(f"下载器不存在: downloader_id={downloader_id}")
            continue
        # 修复异步查询: 查询torrent_id列表
        result = await db.execute(
            select(torrentInfoModel.torrent_id).where(
                torrentInfoModel.info_id.in_(torrent_info_id_list),
                torrentInfoModel.dr == 0,
                torrentInfoModel.downloader_id == downloader_id
            )
        )
        torrent_ids = result.all()

        for torrent_id in torrent_ids:
            if downloader.is_qbittorrent:
                torrent_id_list.append(torrent_id[0])
            if downloader.is_transmission:
                torrent_id_list.append(int(torrent_id[0]))
        if downloader.is_qbittorrent:
            qb_replace_tracker(downloader, replace_tracker_url, target_tracker_url, torrent_id_list)
        if downloader.is_transmission:
            tr_replace_tracker(downloader, replace_tracker_url, target_tracker_url, torrent_id_list)
    await db.commit()

    # ========== 记录审计日志（后台任务） ==========
    # P0修复: 确保数据完整性检查
    if affected_torrents:
        audit_info = extract_audit_info_from_request(req) or {}

        # 创建数据副本，避免引用问题
        affected_torrents_copy = [
            {
                "torrent_info_id": t["torrent_info_id"],
                "torrent_name": t["torrent_name"],
                "downloader_id": t["downloader_id"]
            }
            for t in affected_torrents
        ]

        # 使用BackgroundTasks在后台执行审计日志写入
        background_tasks.add_task(
            _write_replace_tracker_audit_log_batch,
            affected_torrents=affected_torrents_copy,
            replace_tracker_url=replace_tracker_url,
            target_tracker_url=target_tracker_url,
            audit_info=audit_info
        )
    # ========== 审计日志记录结束 ==========

    return CommonResponse(
        status="success",
        msg=f"替换Tracker成功，影响了{len(affected_torrents)}个种子",
        code="200",
        data={"affected_count": len(affected_torrents)}
    )


@router.post("/modifyTracker", summary="更改种子tracker地址", response_model=CommonResponse)
async def modify_tracker(req: Request, background_tasks: BackgroundTasks, torrent_info_ids: str = Query(
    default="default",
    alias="torrentInfoIds",
    description="torrent_info_id列表",
    examples={"default": "91a92a76-9640-4c50-bb03-381a4d37158c"}
), trackers: str = Query(
    default="default",
    alias="trackers",
    description="多个tracker以;分隔",
    examples={"default": "https://ptskit.kqbhek.com/announce.php?passkey=6fa2d880b3666a460f7ed063f7b9818b"}
), db: AsyncSession = Depends(get_async_db)):
    """
       修改tracker

       Args:
           req: 请求头
           db: 数据库会话
           torrent_info_ids: 种子数据列表
           trackers: tracker地址

       """
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None

        )
        return response

    torrent_info_id_list = torrent_info_ids.split(',')
    tracker_list = trackers.split(';')
    success_count = 0
    failed_count = 0

    for torrent_info_id in torrent_info_id_list:
        try:
            # 获取修改前的tracker信息
            # 修复异步查询: 使用select()替代db.query()
            result = await db.execute(
                select(trackerInfoModel).where(
                    trackerInfoModel.torrent_info_id == torrent_info_id,
                    trackerInfoModel.dr == 0
                )
            )
            old_trackers = result.scalars().all()

            old_tracker_urls = [t.tracker_url for t in old_trackers]

            # 修复异步查询: 查询种子信息
            result = await db.execute(
                select(torrentInfoModel).where(torrentInfoModel.info_id == torrent_info_id)
            )
            torrent = result.scalar_one_or_none()

            if not torrent:
                logging.error(f"种子不存在: torrent_info_id={torrent_info_id}")
                failed_count += 1
                continue
            # 修复异步查询: 查询下载器
            result = await db.execute(
                select(BtDownloaders).where(
                    BtDownloaders.dr == 0,
                    BtDownloaders.downloader_id == torrent.downloader_id
                )
            )
            downloaders = result.scalars().all()

            if not downloaders:
                logging.error(f"下载器不存在: downloader_id={torrent.downloader_id}")
                failed_count += 1
                continue

            if downloaders[0].is_qbittorrent:
                qb_change_torrents_tracker(db, downloaders, tracker_list, torrent.torrent_id)
            if downloaders[0].is_transmission:
                tr_change_torrents_tracker(db, downloaders, tracker_list, int(torrent.torrent_id))

            success_count += 1

            # ========== 记录审计日志（后台任务） ==========
            # P2修复: 添加防御性检查
            audit_info = extract_audit_info_from_request(req) or {}
            background_tasks.add_task(
                _write_tracker_audit_log_async,
                operation_type=AuditOperationType.UPDATE_TRACKER,
                operator="admin",
                torrent_info_id=torrent_info_id,
                operation_detail={
                    "torrent_name": torrent.name,
                    "operation": "modify",
                    "old_trackers": old_tracker_urls,
                    "new_trackers": tracker_list,
                    "tracker_count": len(tracker_list)
                },
                old_value={"trackers": old_tracker_urls},
                new_value={"trackers": tracker_list},
                operation_result=AuditOperationResult.SUCCESS,
                downloader_id=torrent.downloader_id,
                audit_info=audit_info
            )
            # ========== 审计日志记录结束 ==========

        except Exception as e:
            failed_count += 1
            logging.error(f"修改tracker失败: {str(e)}")

            # ========== 记录失败的审计日志（后台任务） ==========
            # P2修复: 添加防御性检查
            audit_info = extract_audit_info_from_request(req) or {}
            background_tasks.add_task(
                _write_tracker_audit_log_async,
                operation_type=AuditOperationType.UPDATE_TRACKER,
                operator="admin",
                torrent_info_id=torrent_info_id,
                operation_detail={
                    "operation": "modify",
                    "new_trackers": tracker_list,
                    "tracker_count": len(tracker_list)
                },
                error_message=str(e),
                operation_result=AuditOperationResult.FAILED,
                downloader_id=None,
                audit_info=audit_info
            )
            # ========== 审计日志记录结束 ==========

    return CommonResponse(
        status="success",
        msg=f"修改Tracker成功，成功: {success_count}，失败: {failed_count}",
        code="200",
        data={"success_count": success_count, "failed_count": failed_count}
    )


def qb_add_torrents_tracker(db, downloaders, todo_tracker_list, torrent_id, torrent_info_id):
    # P0-1 修复: 添加30秒超时，避免无限阻塞
    qb_client = qbClient(downloaders[0].host, port=downloaders[0].port, username=downloaders[0].username,
                         password=downloaders[0].password,
                         VERIFY_WEBUI_CERTIFICATE=False,
                         REQUESTS_ARGS={'timeout': 30})  # 30秒超时
    torrent = qb_client.torrents_info(torrent_hashes=torrent_id)[0]
    torrent.add_trackers(todo_tracker_list)
    current_time = datetime.now()
    for tracker in torrent.trackers:
        if todo_tracker_list.__contains__(tracker['url']):
            tracker_info = trackerInfoModel(
                tracker_id=str(uuid.uuid4()),
                torrent_info_id=torrent_info_id,
                tracker_name=tracker['url'],
                tracker_url=tracker['url'],
                last_announce_succeeded=tracker['status'],
                last_announce_msg=tracker['msg'],
                last_scrape_succeeded=tracker['status'],
                last_scrape_msg=tracker['msg'],
                create_time=current_time,
                create_by="admin",
                update_time=current_time,
                update_by="admin",
                dr=0
            )
            db.add(tracker_info)
    db.commit()


async def tr_add_torrents_tracker(db, downloaders, todo_tracker_list, torrent_id, torrent_info_id):
    """
        根据transmission的种子数据结添加tracker

        Args:
            db: 数据库会话
            downloaders: 种子数据列表
            todo_tracker_list: 目标trackerList
            torrent_id: 需要添加的种子id
            torrent_info_id: 种子主键
    """
    tr_client = trClient(host=downloaders[0].host, username=downloaders[0].username, password=downloaders[0].password,
                         port=downloaders[0].port, protocol="http", timeout=100.0)
    new_tracker_list = []
    # 修复异步查询: 查询现有tracker
    result = await db.execute(
        select(trackerInfoModel.tracker_url).where(
            trackerInfoModel.torrent_info_id == torrent_info_id,
            trackerInfoModel.dr == 0
        )
    )
    exit_tracker_list = result.all()
    new_count = todo_tracker_list.__len__()
    for row in exit_tracker_list:
        if todo_tracker_list.count(row[0]) == 0:
            todo_tracker_list.append(row[0])
        else:
            new_count -= 1
    if new_count == 0:
        return
    sub_tracker_list = []
    for row in todo_tracker_list:
        sub_tracker_list.extend(row.split(';'))
    new_tracker_list.append(sub_tracker_list)

    # 该语句效果是直接已list替换tracker
    tr_client.change_torrent(torrent_id, tracker_list=new_tracker_list)
    # 同步修改tracker记录状态
    torrent_info = tr_client.get_torrent(torrent_id)
    # 添加新tracker数据
    current_time = datetime.now()
    for tracker_status in torrent_info.tracker_stats:
        if exit_tracker_list.count(tracker_status.fields.get('announce')) == 0:
            # 修复异步查询: 先查询torrent_info_id
            result = await db.execute(
                select(torrentInfoModel.info_id).where(
                    torrentInfoModel.torrent_id == torrent_info.id,
                    torrentInfoModel.downloader_id == downloaders[0].downloader_id
                )
            )
            info_id_result = result.first()

            if not info_id_result:
                continue

            tracker_info = trackerInfoModel(
                tracker_id=str(uuid.uuid4()),
                torrent_info_id=info_id_result[0],
                tracker_name=tracker_status.site_name,
                tracker_url=tracker_status.fields.get('announce'),
                last_announce_succeeded=tracker_status.last_announce_succeeded,
                last_announce_msg=tracker_status.last_announce_result,
                last_scrape_succeeded=tracker_status.last_scrape_succeeded,
                last_scrape_msg=tracker_status.last_scrape_result,
                create_time=current_time,
                create_by="admin",
                update_time=current_time,
                update_by="admin",
                dr=0
            )
            db.add(tracker_info)
    await db.commit()


async def qb_change_torrents_tracker(db, downloaders, todo_tracker_list, torrent_id):
    """
        根据qbittorrent的种子数据结修改tracker

        Args:
            db: 数据库会话
            downloaders: 种子数据列表
            todo_tracker_list: 目标trackerList
            torrent_id: 需要修改的种子id
    """
    # P0-1 修复: 添加30秒超时，避免无限阻塞
    qb_client = qbClient(downloaders[0].host, port=downloaders[0].port, username=downloaders[0].username,
                         password=downloaders[0].password,
                         VERIFY_WEBUI_CERTIFICATE=False,
                         REQUESTS_ARGS={'timeout': 30})  # 30秒超时
    torrent = qb_client.torrents_info(torrent_hashes=torrent_id)[0]
    # 移除旧的tracker
    for tracker in torrent.trackers:
        url = str(tracker['url'])
        if url.__contains__('DHT') or url.__contains__('PeX') or url.__contains__('LSD'):
            continue
        torrent.remove_trackers(url)

    # 逻辑删除旧tracker数据
    await db.execute(text(
        "update tracker_info set update_time=datetime('now'),dr=1 where torrent_info_id in (select info_id from torrent_info where torrent_id=:torrent_id and downloader_id=:downloader_id);")
        , {"torrent_id": torrent.hash, "downloader_id": downloaders[0].downloader_id})
    # 添加新tracker
    torrent.add_trackers(todo_tracker_list)
    current_time = datetime.now()
    
    # 添加新tracker前先查询torrent_info_id(只需查询一次)
    result = await db.execute(
        select(torrentInfoModel.info_id).where(
            torrentInfoModel.torrent_id == torrent.hash,
            torrentInfoModel.downloader_id == downloaders[0].downloader_id
        )
    )
    info_id_result = result.first()

    if not info_id_result:
        logging.error(f"找不到种子信息: torrent_id={torrent.hash}")
        return

    torrent_info_id_value = info_id_result[0]

    for tracker in torrent.trackers:
        url = str(tracker['url'])
        if url.__contains__('DHT') or url.__contains__('PeX') or url.__contains__('LSD'):
            continue

        tracker_info = trackerInfoModel(
            tracker_id=str(uuid.uuid4()),
            torrent_info_id=torrent_info_id_value,
            tracker_name=tracker['url'],
            tracker_url=tracker['url'],
            last_announce_succeeded=tracker['status'],
            last_announce_msg=tracker['msg'],
            last_scrape_succeeded=tracker['status'],
            last_scrape_msg=tracker['msg'],
            create_time=current_time,
            create_by="admin",
            update_time=current_time,
            update_by="admin",
            dr=0
        )
        db.add(tracker_info)
    await db.commit()

    return


async def tr_change_torrents_tracker(db, downloaders, todo_tracker_list, torrent_id):
    """
        根据transmission的种子数据结修改tracker

        Args:
            db: 数据库会话
            downloaders: 种子数据列表
            todo_tracker_list: 目标trackerList
            torrent_id: 需要修改的种子id
    """
    tr_client = trClient(host=downloaders[0].host, username=downloaders[0].username, password=downloaders[0].password,
                         port=downloaders[0].port, protocol="http", timeout=100.0)
    new_tracker_list = []
    for row in todo_tracker_list:
        sub_tracker_list = row.split(';')
        new_tracker_list.append(sub_tracker_list)

    # 该语句效果是直接已list替换tracker
    tr_client.change_torrent(torrent_id, tracker_list=new_tracker_list)
    # 同步修改tracker记录状态
    torrent_info = tr_client.get_torrent(torrent_id)
    # 逻辑删除旧tracker数据
    await db.execute(text(
        "update tracker_info set update_time=datetime('now'),dr=1 where torrent_info_id in (select info_id from torrent_info where torrent_id=:torrent_id and downloader_id=:downloader_id);")
        , {"torrent_id": torrent_info.id, "downloader_id": downloaders[0].downloader_id})
    # 添加新tracker数据
    current_time = datetime.now()

    # 先查询torrent_info_id(只需查询一次)
    result = await db.execute(
        select(torrentInfoModel.info_id).where(
            torrentInfoModel.torrent_id == torrent_info.id,
            torrentInfoModel.downloader_id == downloaders[0].downloader_id
        )
    )
    info_id_result = result.first()

    if not info_id_result:
        logging.error(f"找不到种子信息: torrent_id={torrent_info.id}")
        return

    torrent_info_id_value = info_id_result[0]

    for tracker_status in torrent_info.tracker_stats:
        tracker_info = trackerInfoModel(
            tracker_id=str(uuid.uuid4()),
            torrent_info_id=torrent_info_id_value,
            tracker_name=tracker_status.site_name,
            tracker_url=tracker_status.fields.get('announce'),
            last_announce_succeeded=tracker_status.last_announce_succeeded,
            last_announce_msg=tracker_status.last_announce_result,
            last_scrape_succeeded=tracker_status.last_scrape_succeeded,
            last_scrape_msg=tracker_status.last_scrape_result,
            create_time=current_time,
            create_by="admin",
            update_time=current_time,
            update_by="admin",
            dr=0
        )
        db.add(tracker_info)
    await db.commit()


def qb_replace_tracker(downloader, replace_tracker_url, target_tracker_url, torrent_id_list):
    # P0-1 修复: 添加30秒超时，避免无限阻塞
    qb_client = qbClient(downloader.host, port=downloader.port, username=downloader.username,
                         password=downloader.password,
                         VERIFY_WEBUI_CERTIFICATE=False,
                         REQUESTS_ARGS={'timeout': 30})  # 30秒超时
    for torrent_id in torrent_id_list:
        torrent = qb_client.torrents_info(torrent_hashes=torrent_id)[0]
        # 移除要替换的tracker
        torrent.remove_trackers(replace_tracker_url)
        torrent.add_trackers(target_tracker_url)


def tr_replace_tracker(downloader, replace_tracker_url, target_tracker_url, torrent_id_list):
    tr_client = trClient(host=downloader.host, username=downloader.username,
                         password=downloader.password,
                         port=downloader.port, protocol="http", timeout=100.0)

    for torrent_id in torrent_id_list:
        # 获取当前种子的所有tracker
        tr_torrent_info = tr_client.get_torrent(torrent_id)
        
        # 构建新的tracker列表
        # 策略：将每个tracker作为一个独立的tier，保持原有顺序
        # 如果遇到要替换的tracker，使用新URL
        new_tracker_list = []
        
        for tracker_status in tr_torrent_info.tracker_stats:
            tracker_url = tracker_status.fields.get('announce')
            
            if tracker_url == replace_tracker_url:
                # 替换为新的tracker URL（作为单独的tier）
                new_tracker_list.append([target_tracker_url])
            else:
                # 保留原有tracker（作为单独的tier）
                new_tracker_list.append([tracker_url])
        
        # 防御性检查
        if not new_tracker_list:
            logging.warning(f"警告: 种子 {torrent_id} 的tracker列表为空，跳过替换操作")
            continue
        
        # 调用Transmission API替换tracker
        tr_client.change_torrent(torrent_id, tracker_list=new_tracker_list)


# ========== 审计日志辅助函数 ==========

async def _write_replace_tracker_audit_log_batch(
    affected_torrents: List[Dict[str, Any]],
    replace_tracker_url: str,
    target_tracker_url: str,
    audit_info: Optional[Dict[str, Any]] = None
):
    """批量记录替换tracker操作的审计日志"""
    try:
        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 为每个受影响的种子记录审计日志（最多MAX_AUDIT_LOG_ENTRIES个）
            for torrent_info in affected_torrents[:MAX_AUDIT_LOG_ENTRIES]:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.UPDATE_TRACKER,
                    operator="admin",
                    torrent_info_id=torrent_info["torrent_info_id"],
                    operation_detail={
                        "torrent_name": torrent_info["torrent_name"],
                        "operation": "replace",
                        "old_tracker_url": replace_tracker_url,
                        "new_tracker_url": target_tracker_url,
                        "affected_torrents_count": len(affected_torrents)
                    },
                    old_value={"tracker_url": replace_tracker_url},
                    new_value={"tracker_url": target_tracker_url},
                    operation_result=AuditOperationResult.SUCCESS,
                    downloader_id=torrent_info["downloader_id"],
                    **(audit_info or {})
                )

            # 如果影响的种子超过MAX_AUDIT_LOG_ENTRIES个，记录一条汇总日志
            if len(affected_torrents) > MAX_AUDIT_LOG_ENTRIES:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.BATCH_OPERATION,
                    operator="admin",
                    operation_detail={
                        "operation": "batch_replace_tracker",
                        "old_tracker_url": replace_tracker_url,
                        "new_tracker_url": target_tracker_url,
                        "total_affected_torrents": len(affected_torrents),
                        "logged_torrents": MAX_AUDIT_LOG_ENTRIES,
                        "note": f"仅详细记录前{MAX_AUDIT_LOG_ENTRIES}条，共{len(affected_torrents)}条"
                    },
                    operation_result=AuditOperationResult.SUCCESS,
                    **(audit_info or {})
                )
    except Exception as audit_error:
        logging.error(f"记录审计日志失败: {str(audit_error)}")

        # P1修复: 添加审计日志备份机制
        try:
            # 创建备份目录
            backup_dir = Path("logs/audit_backup")
            backup_dir.mkdir(parents=True, exist_ok=True)

            # 写入备份文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # 毫秒精度
            backup_file = backup_dir / f"audit_replace_tracker_{timestamp}.json"

            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "operation": "replace_tracker",
                "error": str(audit_error),
                "affected_torrents_count": len(affected_torrents),
                "replace_tracker_url": replace_tracker_url,
                "target_tracker_url": target_tracker_url,
                "audit_info": audit_info,
                "torrents_sample": affected_torrents[:5]  # 保存前5条作为样本
            }

            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)

            logging.info(f"审计日志已备份到: {backup_file}")
        except Exception as backup_error:
            logging.critical(f"审计日志备份失败: {str(backup_error)}")


async def _write_tracker_audit_log_async(
    operation_type: str,
    operator: str,
    torrent_info_id: Optional[str],
    operation_detail: Dict[str, Any],
    downloader_id: Optional[str],
    operation_result: str,
    error_message: Optional[str] = None,
    new_value: Optional[Dict[str, Any]] = None,
    old_value: Optional[Dict[str, Any]] = None,
    audit_info: Optional[Dict[str, Any]] = None
):
    """异步写入tracker审计日志的辅助函数"""
    try:
        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)
            await audit_service.log_operation(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=operation_detail,
                old_value=old_value,
                new_value=new_value,
                operation_result=operation_result,
                error_message=error_message,
                downloader_id=downloader_id,
                **(audit_info or {})
            )
    except Exception as audit_error:
        logging.error(f"记录审计日志失败: {str(audit_error)}")

        # P1修复: 添加审计日志备份机制
        try:
            # 创建备份目录
            backup_dir = Path("logs/audit_backup")
            backup_dir.mkdir(parents=True, exist_ok=True)

            # 写入备份文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # 毫秒精度
            backup_file = backup_dir / f"audit_tracker_op_{timestamp}.json"

            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "operation_type": operation_type,
                "operator": operator,
                "torrent_info_id": torrent_info_id,
                "operation_detail": operation_detail,
                "downloader_id": downloader_id,
                "operation_result": operation_result,
                "error_message": error_message,
                "old_value": old_value,
                "new_value": new_value,
                "audit_info": audit_info,
                "original_error": str(audit_error)
            }

            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)

            logging.info(f"审计日志已备份到: {backup_file}")
        except Exception as backup_error:
            logging.critical(f"审计日志备份失败: {str(backup_error)}")

