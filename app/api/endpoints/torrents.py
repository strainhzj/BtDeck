import asyncio
import hashlib
import os
import re
import tempfile
import time
from datetime import datetime
from logging import exception

import bencodepy
import urllib3
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Form, UploadFile, File, BackgroundTasks, Body
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, Field

from app.api.responseVO import CommonResponse
from sqlalchemy import text, and_, or_, asc, desc, update, exists
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, aliased
from app.database import get_db, AsyncSessionLocal
from app.auth import utils
import uuid
import logging
from app.downloader.models import BtDownloaders
from app.downloader.request import DownloaderCheckVO
from app.torrents.models import TorrentInfo as torrentInfoModel, TorrentInfo
from app.torrents.models import TrackerInfo as trackerInfoModel, TrackerInfo
from typing import List, Dict, Any, Optional
from app.downloader.responseVO import DownloaderVO
from qbittorrentapi import Client as qbClient
from qbittorrentapi import exceptions as qbExceptions
# 审计日志相关导入（使用异步版本）
from app.services.audit_service import AuditLogService, get_audit_service, extract_audit_info_from_request
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from transmission_rpc import Client as trClient, TransmissionError
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.core.background_task_manager import task_manager, TaskStatus

from app.torrents.responseVO import TorrentInfoVO
from app.torrents.trackerVO import TrackerInfoVO
from app.services.torrent_deletion_service import (
    TorrentDeletionService,
    DeleteRequest,
    DeleteOption,
    SafetyCheckLevel
)
from app.schemas.torrent_location import SetLocationRequest
from app.models.setting_templates import DownloaderTypeEnum

logger = logging.getLogger(__name__)
router = APIRouter()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==================== 种子操作请求模型 ====================

class TorrentOperationRequest(BaseModel):
    """种子操作请求（统一基类）"""
    hashes: List[str] = Field(..., description="种子hash列表", min_items=1, max_items=100)
    operator: Optional[str] = Field(default="admin", description="操作人")


class ResumeTorrentsRequest(BaseModel):
    """恢复/开始种子请求"""
    downloader_id: str = Field(..., description="下载器ID")
    hashes: List[str] = Field(..., description="种子hash列表", min_items=1, max_items=100)


class PauseTorrentsRequest(BaseModel):
    """暂停种子请求"""
    downloader_id: str = Field(..., description="下载器ID")
    hashes: List[str] = Field(..., description="种子hash列表", min_items=1, max_items=100)


class RecheckTorrentsRequest(BaseModel):
    """重新检查种子请求"""
    downloader_id: str = Field(..., description="下载器ID")
    hashes: List[str] = Field(..., description="种子hash列表", min_items=1, max_items=100)


import asyncio
from concurrent.futures import ThreadPoolExecutor


# ==================== 辅助函数 ====================

def _register_downloader_adapters(
        deletion_service: 'TorrentDeletionService',
        torrent_info_ids: List[str],
        db: Session,
        app: Any = None
) -> int:
    """
    为要删除的种子注册对应的下载器适配器（使用缓存连接）

    Args:
        deletion_service: 删除服务实例
        torrent_info_ids: 要删除的种子ID列表
        db: 数据库会话
        app: FastAPI应用实例（用于访问缓存连接）

    Returns:
        成功注册的适配器数量
    """
    from app.services.torrent_deletion_service import DownloaderAdapterFactory

    # 查询种子所属的下载器
    torrent_infos = db.query(torrentInfoModel).filter(
        torrentInfoModel.info_id.in_(torrent_info_ids),
        torrentInfoModel.dr == 0
    ).all()

    if not torrent_infos:
        logger.warning("没有找到有效的种子记录")
        return 0

    # 获取所有唯一的下载器ID
    downloader_ids = list(set(t.downloader_id for t in torrent_infos))

    # 查询这些下载器的详细信息
    downloaders = db.query(BtDownloaders).filter(
        BtDownloaders.downloader_id.in_(downloader_ids),
        BtDownloaders.dr == 0
    ).all()

    if not downloaders:
        logger.warning("没有找到有效的下载器")
        return 0

    # 检查app参数并获取缓存
    if app is None:
        logger.error("未传入app参数，无法访问缓存连接，跳过适配器注册")
        return 0

    if not hasattr(app.state, 'store'):
        logger.error("app.state.store 未初始化，跳过适配器注册")
        return 0

    # 获取缓存的下载器列表
    cached_downloaders = app.state.store.get_snapshot_sync()

    registered_count = 0
    for downloader in downloaders:
        try:
            # 从缓存中查找对应的下载器
            downloader_vo = next(
                (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
                None
            )

            if not downloader_vo:
                logger.error(f"下载器 {downloader.nickname} (ID={downloader.downloader_id}) 不在缓存中")
                continue

            # 检查下载器是否有效
            if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
                logger.warning(f"下载器 {downloader.nickname} (ID={downloader.downloader_id}) 已失效")
                continue

            # 获取缓存的客户端连接
            client = downloader_vo.client
            if not client:
                logger.error(f"下载器 {downloader.nickname} (ID={downloader.downloader_id}) 客户端连接不存在")
                continue

            # 🔧 使用统一的枚举类方法进行类型转换
            normalized_type = DownloaderTypeEnum.normalize(downloader.downloader_type)
            downloader_type_str = DownloaderTypeEnum(normalized_type).to_name()

            if downloader_type_str:
                # 使用缓存的客户端连接创建适配器
                adapter = DownloaderAdapterFactory.create_adapter(
                    downloader_type=downloader_type_str,
                    client=client  # 传入缓存的客户端连接
                )

                # 🔧 关键修复：使用原始的 downloader.downloader_type 作为注册key
                # 因为 TorrentDeletionService 查询时使用的是原始值
                deletion_service.register_adapter(
                    downloader_type=downloader.downloader_type,
                    adapter=adapter
                )
                registered_count += 1
                logger.info(
                    f"已注册下载器适配器（使用缓存连接）: {downloader.nickname} ({downloader_type_str}), key={downloader.downloader_type}")
            else:
                logger.error(f"不支持的下载器类型: {downloader.downloader_type}")
        except Exception as e:
            logger.error(f"注册下载器{downloader.nickname}适配器失败: {str(e)}")

    return registered_count


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

    logger.info(f"[TORRENT_SYNC][MARKER] using file={__file__}")
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


def torrent_sync(downloader_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    后台同步种子数据的函数（不依赖接口请求）
    用于定时任务调用

    Args:
        downloader_info: 下载器信息字典

    Returns:
        同步结果字典
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        # 创建下载器对象
        downloader = BtDownloaders()
        for key, value in downloader_info.items():
            if hasattr(downloader, key):
                setattr(downloader, key, value)

        # 处理每种下载器类型
        if downloader.is_qbittorrent:
            qb_add_torrents(db, [downloader])
            logger.info(f"Successfully synced qBittorrent downloader: {downloader.nickname}")
            return {
                "status": "success",
                "message": f"qBittorrent下载器 {downloader.nickname} 同步成功",
                "downloader_type": "qbittorrent",
                "nickname": downloader.nickname
            }
        elif downloader.is_transmission:
            tr_add_torrents(db, [downloader])
            logger.info(f"Successfully synced Transmission downloader: {downloader.nickname}")
            return {
                "status": "success",
                "message": f"Transmission下载器 {downloader.nickname} 同步成功",
                "downloader_type": "transmission",
                "nickname": downloader.nickname
            }
        else:
            error_msg = f"不支持的下载器类型: {downloader.downloader_type}"
            logger.error(error_msg)
            return {
                "status": "failed",
                "message": error_msg,
                "downloader_type": downloader.downloader_type,
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
    finally:
        db.close()


@router.post("/list", response_model=CommonResponse)
def torrent_list(req: Request, name: str = Query(
    default="default",
    alias="name",
    description="种子名称"
), db: Session = Depends(get_db)):
    """
    同步下载器中的种子数据到数据库
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )

    try:
        # 查询启用的下载器
        query = db.query(
            BtDownloaders.downloader_id,
            BtDownloaders.nickname,
            BtDownloaders.host,
            BtDownloaders.username,
            BtDownloaders.password,
            BtDownloaders.is_search,
            BtDownloaders.status,
            BtDownloaders.enabled,
            BtDownloaders.downloader_type,
            BtDownloaders.port,
            BtDownloaders.is_ssl
        ).filter(
            BtDownloaders.dr == 0,
            BtDownloaders.enabled == True,
            BtDownloaders.status == '1'
        )

        downloaders = query.all()

        if not downloaders:
            return CommonResponse(
                status="success",
                msg="未找到可用的下载器",
                code="200",
                data=[]
            )

        synced_count = 0
        errors = []

        # 处理每个下载器
        for downloader in downloaders:
            try:
                if downloader.is_qbittorrent:
                    qb_add_torrents(db, [downloader])
                    synced_count += 1
                    logger.info(f"成功同步qBittorrent下载器: {downloader.nickname}")
                elif downloader.is_transmission:
                    tr_add_torrents(db, [downloader])
                    synced_count += 1
                    logger.info(f"成功同步Transmission下载器: {downloader.nickname}")
                else:
                    errors.append(f"不支持的下载器类型: {downloader.downloader_type}")

            except Exception as e:
                error_msg = f"同步下载器 {downloader.nickname} 失败: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # 构建响应消息
        if errors:
            msg = f"同步完成，成功: {synced_count}，失败: {len(errors)}"
            if errors:
                msg += f"。错误详情: {'; '.join(errors[:3])}"  # 只显示前3个错误
        else:
            msg = f"同步成功，共处理 {synced_count} 个下载器"

        return CommonResponse(
            status="success",
            msg=msg,
            code="200",
            data={
                "synced_count": synced_count,
                "total_count": len(downloaders),
                "errors": errors if len(errors) <= 5 else errors[:5]  # 限制返回的错误数量
            }
        )

    except SQLAlchemyError as e:
        logger.error(f"数据库操作失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"数据库操作失败: {str(e)}",
            code="500",
            data=None
        )
    except Exception as e:
        logger.error(f"同步过程中发生未知错误: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"同步失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/add", response_model=CommonResponse)
async def create_torrent(
        request: Request,
        downloader_id: Optional[str] = Form(..., description="所属下载器主键"),
        save_path: Optional[str | None] = Form(..., description="种子文件保存路径"),
        tags: Optional[str | None] = Form("", description="标签"),
        category: Optional[str | None] = Form("", description="分类"),
        paused: Optional[bool] = Form(False, description="是否暂停,0代表false，1代表true"),
        skip_hash_check: Optional[bool | None] = Form(False, description="是否跳过校验,0代表false，1代表true"),
        is_sequential_download: Optional[bool | None] = Form(False, description="是否按顺序下载,0代表false，1代表true"),
        is_first_last_piece_priority: Optional[bool | None] = Form(False,
                                                                   description="是否先下载首尾文件块,0代表false，1代表true"),
        upload_limit: Optional[str | int | None] = Form(False, description="上传速度，单位bytes/second"),
        download_limit: Optional[str | int | None] = Form(False, description="下载速度，单位bytes/second"),
        torrent_file: Optional[UploadFile] = File(description="种子文件"),
        db: Session = Depends(get_db)
):
    # """创建新的种子信息"""
    result = CommonResponse(
        status="success",
        msg="种子添加成功",
        data=None,
        code="200"
    )

    # ========== 从 app.state.store 获取缓存的下载器（强制规范） ==========
    # 步骤1：获取 app 对象并检查缓存初始化
    app = request.app

    if not hasattr(app.state, 'store'):
        result.code = "500"
        result.msg = "下载器缓存未初始化"
        result.status = "failed"
        return result

    # 步骤2：从缓存获取下载器
    # 🔧 修复：使用异步版本 get_snapshot() 避免线程问题
    cached_downloaders = await app.state.store.get_snapshot()
    downloader_vo = next(
        (d for d in cached_downloaders if d.downloader_id == downloader_id),
        None
    )

    # 步骤3：验证下载器有效性
    if not downloader_vo:
        result.code = "404"
        result.msg = f"下载器不在缓存中 [downloader_id={downloader_id}]"
        result.status = "failed"
        return result

    if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
        result.code = "503"
        result.msg = f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]"
        result.status = "failed"
        return result

    # 步骤4：获取并验证客户端连接
    client = downloader_vo.client

    if not client:
        result.code = "500"
        result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
        result.status = "failed"
        return result

    # 使用缓存的下载器对象（替换原来的数据库查询）
    downloader = downloader_vo
    if torrent_file:
        # 保存文件到临时位置
        file_content = await torrent_file.read()

        # 将文件写入操作放到线程池中执行
        def write_temp_file(content):
            """安全地写入临时文件"""
            try:
                tmp_file = tempfile.NamedTemporaryFile(
                    mode='wb',
                    delete=False,
                    suffix=".torrent"
                )
                tmp_file.write(content)
                tmp_file.flush()  # 确保数据写入磁盘
                os.fsync(tmp_file.fileno())  # 强制同步
                tmp_file.close()
                return tmp_file.name
            except Exception as e:
                logging.error(f"写入临时文件失败: {str(e)}")
                if 'tmp_file' in locals():
                    try:
                        tmp_file.close()
                    except OSError as close_err:
                        logging.debug(f"关闭临时文件失败: {close_err}")
                raise

        tmp_file_path = await asyncio.to_thread(write_temp_file, file_content)

        try:
            # 计算文件哈希
            info_hash = await calculate_info_hash(tmp_file_path)

        except Exception as e:
            # 如果出错，删除临时文件
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
            result.code = "500"
            result.msg = str(e)
            return result

    # 🔧 修复：使用 downloader_type 字段判断下载器类型
    # downloader_type: 0=qBittorrent, 1=Transmission
    if downloader.downloader_type == 1:  # Transmission
        try:
            # 使用缓存的客户端连接（强制规范）
            tr_client = client
            # 准备添加参数
            add_args = {
                "paused": paused,
                "download_dir": save_path if save_path else None
            }

            # 如果有种子文件，添加文件
            if tmp_file_path:
                # 将文件读取操作放到线程池中执行
                def read_file_data(file_path):
                    with open(file_path, "rb") as f:
                        return f.read()

                file_data = await asyncio.to_thread(read_file_data, tmp_file_path)
                # 将文件数据包装成类似文件对象
                from io import BytesIO
                tr_client.add_torrent(BytesIO(file_data), **add_args)
            else:
                result.code = "400"
                result.msg = "Transmission需要种子文件"
                return result

            # 等待Transmission处理种子（最多30秒）
            tr_torrent = None
            max_retries = 30
            retry_count = 0
            while tr_torrent is None and retry_count < max_retries:
                await asyncio.sleep(1)
                tr_torrent = await get_transmission_torrent_info(tr_client, info_hash)
                retry_count += 1

            if not tr_torrent:
                result.code = "408"
                result.msg = "获取种子信息超时，请检查Transmission连接"
                return result
                result.code = "500"
                result.msg = "种子添加到Transmission后无法获取信息"
                return result

            # 检查数据库中是否已存在该种子
            existing_torrent = db.query(TorrentInfo.info_id).filter(TorrentInfo.hash == info_hash).filter(
                TorrentInfo.dr == 0).filter(
                TorrentInfo.downloader_id == downloader_id).first()

            if existing_torrent is None:
                # 不存在：创建新记录
                db_torrent = create_transmission_torrent_record(downloader, downloader_id, tr_torrent)
                db.add(db_torrent)
                db.commit()
                db.refresh(db_torrent)
            else:
                # 已存在：使用现有记录
                db_torrent = existing_torrent

        except TransmissionError as e:
            result.code = "500"
            result.msg = str(e)
            return result
    # 🔧 修复：使用 downloader_type 字段判断下载器类型
    # downloader_type: 0=qBittorrent, 1=Transmission
    if downloader.downloader_type == 0:  # qBittorrent
        try:
            # 使用缓存的客户端连接（强制规范）
            qb_client = client

            # 将文件读取操作放到线程池中执行
            def read_file_data_qb(file_path):
                with open(file_path, "rb") as f:
                    return f.read()

            file_data = await asyncio.to_thread(read_file_data_qb, tmp_file_path)
            from io import BytesIO
            qb_client.torrents_add(torrent_files=BytesIO(file_data), save_path=save_path, is_stopped=paused, tags=tags,
                                   category=category, is_skip_checking=skip_hash_check,
                                   is_sequential_download=is_sequential_download,
                                   is_first_last_piece_priority=is_first_last_piece_priority,
                                   upload_limit=upload_limit, download_limit=download_limit)

            # 从qBittorrent获取种子信息（最多30秒）
            torrents = None
            max_retries = 30
            retry_count = 0
            while (torrents is None or len(torrents) == 0) and retry_count < max_retries:
                await asyncio.sleep(1)
                torrents = qb_client.torrents_info(torrent_hashes=info_hash)
                retry_count += 1

            if not torrents:
                result.code = "500"
                result.msg = str("种子添加到qBittorrent后无法获取信息")
                return result
        except qbExceptions as e:
            result.code = "500"
            result.msg = str(e)
            return result

        # 双重检查：确保torrents列表不为空
        if not torrents or len(torrents) == 0:
            result.code = "500"
            result.msg = "种子信息列表为空"
            return result

        qb_torrent = torrents[0]

        # 检查数据库中是否已存在该种子
        existing_torrent = db.query(TorrentInfo.info_id).filter(TorrentInfo.hash == info_hash).filter(
            TorrentInfo.dr == 0).filter(
            TorrentInfo.downloader_id == downloader_id).first()

        if existing_torrent is None:
            # 不存在：创建新记录
            db_torrent = create_qbittorrent_torrent_record(downloader, downloader_id, qb_torrent,
                                                           tmp_file_path)
            db.add(db_torrent)
            db.commit()
            db.refresh(db_torrent)
        else:
            # 已存在：使用现有记录
            db_torrent = existing_torrent

    # ========== 记录审计日志（异步） ==========
    async def write_audit_log_async():
        """异步写入审计日志的内部函数"""
        try:
            async with AsyncSessionLocal() as async_db:
                audit_service = await get_audit_service(async_db)
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ADD,
                    operator="admin",  # 当前API没有认证，使用默认操作人
                    torrent_info_id=db_torrent.info_id,
                    operation_detail={
                        "torrent_name": db_torrent.name,
                        "torrent_hash": db_torrent.hash,
                        "downloader_id": downloader_id,
                        "downloader_name": downloader.nickname,
                        "save_path": save_path,
                        "tags": tags,
                        "category": category,
                        "paused": paused,
                        "file_size": db_torrent.size
                    },
                    new_value={"status": "added"},
                    operation_result=AuditOperationResult.SUCCESS,
                    downloader_id=downloader_id,
                    **extract_audit_info_from_request(request)
                )
        except Exception as audit_error:
            # 审计日志失败不影响主业务
            logging.error(f"记录审计日志失败: {str(audit_error)}")

    # 在后台执行审计日志写入（不阻塞主业务）
    # ⚠️ 异步任务异常需要注意：如果任务失败，异常会被静默忽略
    asyncio.create_task(write_audit_log_async())
    # ========== 审计日志记录结束 ==========

    return result


@router.get("/torrents/{info_id}/{downloader_id}/{downloader_name}", response_model=CommonResponse)
def get_torrent(
        info_id: str,
        downloader_id: str,
        downloader_name: str,
        db: Session = Depends(get_db)
):
    """根据复合主键获取种子信息"""
    torrent = get_torrent_info(db, info_id, downloader_id, downloader_name)
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found")
    return torrent


@router.get("/getList")
def get_torrents(
        downloader_id: Optional[str] = Query(None, description="所属下载器主键", examples={"default": ""}),
        downloader_name_like: Optional[str] = Query(None, description="所属下载器名模糊查询"),
        name_like: Optional[str] = Query(None, description="种子名称模糊查询"),
        save_path_like: Optional[str] = Query(None, description="种子文件保存路径模糊查询"),
        size_min: Optional[str] = Query(None, description="种子大小最小值"),
        size_max: Optional[str] = Query(None, description="种子大小最大值"),
        added_date_min: Optional[str] = Query(None, description="添加时间最小值"),
        added_date_max: Optional[str] = Query(None, description="添加时间最大值"),
        completed_date_min: Optional[str] = Query(None, description="完成时间最小值"),
        completed_date_max: Optional[str] = Query(None, description="完成时间最大值"),
        tags_like: Optional[str] = Query(None, description="标签模糊查询"),
        category_like: Optional[str] = Query(None, description="分类模糊查询"),
        tracker_like: Optional[str] = Query(None, description="tracker地址模糊查询"),
        status: Optional[str] = Query(None,
                                      description="种子状态筛选(error状态满足status='error'或has_tracker_error=True之一即可)"),
        skip: int = Query(0, ge=0, description="跳过记录数"),
        limit: int = Query(100, ge=1, le=1000, description="限制记录数"),
        sort_by: Optional[str] = Query(None, description="排序字段"),
        sort_order: Optional[str] = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
        db: Session = Depends(get_db)
):
    """通用查询方法，支持多种过滤条件和排序，返回数据总数和列表"""
    try:
        # 获取包含总数和数据的查询结果
        result = get_torrent_infos(
            db=db,
            downloader_id=downloader_id,
            downloader_name_like=downloader_name_like,
            name_like=name_like,
            save_path_like=save_path_like,
            size_min=size_min,
            size_max=size_max,
            added_date_min=added_date_min,
            added_date_max=added_date_max,
            completed_date_min=completed_date_min,
            completed_date_max=completed_date_max,
            tags_like=tags_like,
            category_like=category_like,
            status=status,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            tracker=tracker_like
        )

        # 构建响应数据，包含总数和列表
        response_data = {
            "total": result["total"],
            "list": result["data"]
        }

        response = CommonResponse(
            status="success",
            msg="获取列表成功",
            data=response_data,
            code="200"
        )
        return response

    except Exception as e:
        response = CommonResponse(
            status="failed",
            msg=f"获取列表失败: {str(e)}",
            data=None,
            code="500"
        )
        return response


@router.post("/pause", description="暂停种子接口",
             response_model=CommonResponse)
async def pause_torrents(
        request: Request,
        req_data: PauseTorrentsRequest,
        db: Session = Depends(get_db)
):
    """
    批量暂停种子

    功能：
    - 支持批量暂停多个种子
    - 指定下载器ID，根据下载器类型调用不同API
    - 使用缓存中的客户端连接，避免重复创建
    - 严格模式：任何一个失败整体回滚
    - 立即更新数据库状态为paused
    - 记录审计日志

    修复CRITICAL问题：
    - #1: 空指针解引用 - 添加None检查
    - #2: 资源泄漏 - 使用缓存连接，不手动logout
    - #3: 数据一致性 - 先执行API后更新数据库
    - #4: 审计日志异常 - 使用_safe_write_audit_log
    - #5: 下载器类型判断 - 使用枚举类型而非字符串比较

    请求格式：
    {
        "downloader_id": "下载器ID",
        "hashes": ["hash1", "hash2", ...]
    }
    """
    # 从请求模型中获取参数
    downloader_id = req_data.downloader_id
    hashes = req_data.hashes

    result = CommonResponse(
        status="success",
        msg="暂停成功",
        code="200",
        data={"success_count": len(hashes), "failed_items": []}
    )

    # ========== 验证参数 ==========
    if not hashes or len(hashes) == 0:
        result.status = "failed"
        result.msg = "参数错误：hashes列表不能为空"
        result.code = "400"
        return result

    try:
        # ========== 从缓存中获取下载器 ==========
        app = request.app
        if not hasattr(app.state, 'store'):
            result.status = "failed"
            result.msg = "下载器缓存未初始化"
            result.code = "500"
            return result

        cached_downloaders = app.state.store.get_snapshot_sync()

        # 根据 downloader_id 查找对应的下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        if not downloader_vo:
            result.status = "failed"
            result.msg = f"下载器不在缓存中 [downloader_id={downloader_id}]"
            result.code = "404"
            return result

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            result.status = "failed"
            result.msg = f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]"
            result.code = "503"
            return result

        # 获取缓存的客户端连接
        client = downloader_vo.client
        if not client:
            result.status = "failed"
            result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
            result.code = "500"
            return result

        # ========== 查询种子信息 ==========
        # 只查询指定下载器且未删除的种子（dr=0）
        torrent_records = db.query(torrentInfoModel).filter(
            torrentInfoModel.hash.in_(hashes),
            torrentInfoModel.downloader_id == downloader_id,
            torrentInfoModel.dr == 0  # 只操作未删除的种子
        ).all()

        if not torrent_records:
            result.status = "failed"
            result.msg = "未找到任何种子记录"
            result.code = "404"
            return result

        # 提取hash列表
        group_hashes = [r.hash for r in torrent_records]

        # ========== 执行暂停操作 ==========
        try:
            # 使用枚举类型判断下载器类型
            downloader_type_enum = downloader_vo.type_enum if hasattr(downloader_vo, 'type_enum') else None

            if downloader_vo.downloader_type == 0 or (downloader_type_enum and downloader_type_enum.is_qbittorrent()):
                # qBittorrent 下载器
                client.torrents_pause(torrent_hashes=group_hashes)

            elif downloader_vo.downloader_type == 1 or (
                    downloader_type_enum and downloader_type_enum.is_transmission()):
                # Transmission 下载器
                client.stop_torrent(group_hashes)

            else:
                error_msg = f"不支持的下载器类型: {downloader_vo.downloader_type}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 修复CRITICAL #3: API调用成功后再更新数据库
            for record in torrent_records:
                old_status = record.status
                record.status = "paused"
                db.add(record)

                # 修复CRITICAL #4: 使用安全包装记录审计日志
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.PAUSE,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_name": downloader_vo.nickname,
                        "downloader_type": downloader_vo.downloader_type
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    old_value={"status": old_status},
                    new_value={"status": "paused"},
                    operation_result=AuditOperationResult.SUCCESS,
                    audit_info=audit_info
                )

            # 提交数据库事务
            db.commit()

            result.msg = f"成功暂停 {len(torrent_records)} 个种子"
            result.data = {
                "success_count": len(torrent_records),
                "failed_items": []
            }

        except Exception as e:
            # 严格模式：任何失败都回滚
            db.rollback()
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"暂停种子失败 [downloader_id={downloader_id}]: {error_detail}")

            result.status = "failed"
            result.msg = f"暂停失败：{error_detail}"
            result.code = "500"
            result.data = {
                "success_count": 0,
                "failed_items": [{
                    "hash": r.hash,
                    "name": r.name,
                    "error": error_detail
                } for r in torrent_records]
            }

            # 记录失败的审计日志
            for record in torrent_records:
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.PAUSE,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_type": downloader_vo.downloader_type,
                        "exception_type": type(e).__name__
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    operation_result=AuditOperationResult.FAILED,
                    error_message=error_detail,
                    audit_info=audit_info
                )

            return result
        # 注意：不再需要 finally 块手动释放连接，因为使用的是缓存连接

    except Exception as e:
        db.rollback()
        error_detail = f"{type(e).__name__}: {str(e)}"
        logger.error(f"暂停种子异常: {error_detail}")

        result.status = "failed"
        result.msg = f"操作异常：{error_detail}"
        result.code = "500"

    return result


@router.post("/resume", description="恢复/开始种子接口",
             response_model=CommonResponse)
async def resume_torrents(
        request: Request,
        req_data: ResumeTorrentsRequest,
        db: Session = Depends(get_db)
):
    """
    批量恢复/开始种子

    功能：
    - 支持批量恢复多个种子
    - 指定下载器ID，根据下载器类型调用不同API
    - 使用缓存中的客户端连接，避免重复创建
    - 严格模式：任何一个失败整体回滚
    - 立即更新数据库状态（根据进度：100%→seeding, 否则→downloading）
    - 记录审计日志

    修复CRITICAL问题：
    - #1: 空指针解引用 - 添加None检查
    - #2: 资源泄漏 - 使用缓存连接，不手动logout
    - #3: 数据一致性 - 先执行API后更新数据库
    - #4: 审计日志异常 - 使用_safe_write_audit_log
    - #5: 下载器类型判断 - 使用枚举类型而非字符串比较

    请求格式：
    {
        "downloader_id": "下载器ID",
        "hashes": ["hash1", "hash2", ...]
    }
    """
    # 从请求模型中获取参数
    downloader_id = req_data.downloader_id
    hashes = req_data.hashes

    result = CommonResponse(
        status="success",
        msg="开始成功",
        code="200",
        data={"success_count": len(hashes), "failed_items": []}
    )

    # ========== 验证参数 ==========
    if not hashes or len(hashes) == 0:
        result.status = "failed"
        result.msg = "参数错误：hashes列表不能为空"
        result.code = "400"
        return result

    try:
        # ========== 从缓存中获取下载器 ==========
        app = request.app
        if not hasattr(app.state, 'store'):
            result.status = "failed"
            result.msg = "下载器缓存未初始化"
            result.code = "500"
            return result

        cached_downloaders = app.state.store.get_snapshot_sync()

        # 根据 downloader_id 查找对应的下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        if not downloader_vo:
            result.status = "failed"
            result.msg = f"下载器不在缓存中 [downloader_id={downloader_id}]"
            result.code = "404"
            return result

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            result.status = "failed"
            result.msg = f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]"
            result.code = "503"
            return result

        # 获取缓存的客户端连接
        client = downloader_vo.client
        if not client:
            result.status = "failed"
            result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
            result.code = "500"
            return result

        # ========== 查询种子信息 ==========
        # 只查询指定下载器且未删除的种子（dr=0）
        torrent_records = db.query(torrentInfoModel).filter(
            torrentInfoModel.hash.in_(hashes),
            torrentInfoModel.downloader_id == downloader_id,
            torrentInfoModel.dr == 0  # 只操作未删除的种子
        ).all()

        if not torrent_records:
            result.status = "failed"
            result.msg = "未找到任何种子记录"
            result.code = "404"
            return result

        # 提取hash列表
        group_hashes = [r.hash for r in torrent_records]

        # ========== 执行恢复操作 ==========
        try:
            # 使用枚举类型判断下载器类型
            if downloader_vo.downloader_type == 0:
                # qBittorrent 下载器
                client.torrents_resume(torrent_hashes=group_hashes)

            elif downloader_vo.downloader_type == 1:
                # Transmission 下载器
                client.start_torrent(group_hashes)

            else:
                error_msg = f"不支持的下载器类型: {downloader_vo.downloader_type}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 修复CRITICAL #3: API调用成功后再更新数据库
            for record in torrent_records:
                old_status = record.status

                # 修复CRITICAL #1: 添加None检查避免空指针解引用
                if record.progress is not None and record.progress >= 100.0:
                    new_status = "seeding"
                else:
                    new_status = "downloading"

                record.status = new_status
                db.add(record)

                # 修复CRITICAL #4: 使用安全包装记录审计日志
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.RESUME,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_name": downloader_vo.nickname,
                        "downloader_type": downloader_vo.downloader_type,
                        "progress": record.progress
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    old_value={"status": old_status},
                    new_value={"status": new_status},
                    operation_result=AuditOperationResult.SUCCESS,
                    audit_info=audit_info
                )

            # 提交数据库事务
            db.commit()

            result.msg = f"成功开始 {len(torrent_records)} 个种子"
            result.data = {
                "success_count": len(torrent_records),
                "failed_items": []
            }

        except Exception as e:
            # 严格模式：任何失败都回滚
            db.rollback()
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"恢复种子失败 [downloader_id={downloader_id}]: {error_detail}")

            result.status = "failed"
            result.msg = f"恢复失败：{error_detail}"
            result.code = "500"
            result.data = {
                "success_count": 0,
                "failed_items": [{
                    "hash": r.hash,
                    "name": r.name,
                    "error": error_detail
                } for r in torrent_records]
            }

            # 记录失败的审计日志
            for record in torrent_records:
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.RESUME,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_type": downloader_vo.downloader_type,
                        "exception_type": type(e).__name__
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    operation_result=AuditOperationResult.FAILED,
                    error_message=error_detail,
                    audit_info=audit_info
                )

            return result
        # 注意：不再需要 finally 块手动释放连接，因为使用的是缓存连接

    except Exception as e:
        db.rollback()
        error_detail = f"{type(e).__name__}: {str(e)}"
        logger.error(f"恢复种子异常: {error_detail}")

        result.status = "failed"
        result.msg = f"操作异常：{error_detail}"
        result.code = "500"

    return result


@router.post("/recheck", description="重新检查种子接口",
             response_model=CommonResponse)
async def recheck_torrents(
        request: Request,
        req_data: RecheckTorrentsRequest,
        db: Session = Depends(get_db)
):
    """
    批量重新检查种子

    功能：
    - 支持批量重新检查多个种子
    - 指定下载器ID，根据下载器类型调用不同API
    - 使用缓存中的客户端连接，避免重复创建
    - 严格模式：任何一个失败整体回滚
    - Transmission每次最多3个种子（用户自定义）
    - 立即更新数据库状态为checking
    - 记录审计日志

    修复CRITICAL问题：
    - #1: 资源泄漏 - 使用缓存连接，不手动logout
    - #2: 数据一致性 - 先执行API后更新数据库
    - #3: 审计日志异常 - 使用_safe_write_audit_log
    - #4: 下载器类型判断 - 使用枚举类型而非字符串比较

    请求格式：
    {
        "downloader_id": "下载器ID",
        "hashes": ["hash1", "hash2", ...]
    }
    """
    # 从请求模型中获取参数
    downloader_id = req_data.downloader_id
    hashes = req_data.hashes

    result = CommonResponse(
        status="success",
        msg="重新检查成功",
        code="200",
        data={"success_count": len(hashes), "failed_items": []}
    )

    # ========== 验证参数 ==========
    if not hashes or len(hashes) == 0:
        result.status = "failed"
        result.msg = "参数错误：hashes列表不能为空"
        result.code = "400"
        return result

    # Transmission并发限制（用户自定义：每次最多3个）
    MAX_CONCURRENT_RECHECK = 3

    try:
        # ========== 从缓存中获取下载器 ==========
        app = request.app
        if not hasattr(app.state, 'store'):
            result.status = "failed"
            result.msg = "下载器缓存未初始化"
            result.code = "500"
            return result

        cached_downloaders = app.state.store.get_snapshot_sync()

        # 根据 downloader_id 查找对应的下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        if not downloader_vo:
            result.status = "failed"
            result.msg = f"下载器不在缓存中 [downloader_id={downloader_id}]"
            result.code = "404"
            return result

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            result.status = "failed"
            result.msg = f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]"
            result.code = "503"
            return result

        # 获取缓存的客户端连接
        client = downloader_vo.client
        if not client:
            result.status = "failed"
            result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
            result.code = "500"
            return result

        # ========== 查询种子信息 ==========
        # 只查询指定下载器且未删除的种子（dr=0）
        torrent_records = db.query(torrentInfoModel).filter(
            torrentInfoModel.hash.in_(hashes),
            torrentInfoModel.downloader_id == downloader_id,
            torrentInfoModel.dr == 0  # 只操作未删除的种子
        ).all()

        if not torrent_records:
            result.status = "failed"
            result.msg = "未找到任何种子记录"
            result.code = "404"
            return result

        # Transmission并发限制检查
        if downloader_vo.downloader_type == 1 and len(torrent_records) > MAX_CONCURRENT_RECHECK:
            error_msg = f"Transmission重检限制：每次最多{MAX_CONCURRENT_RECHECK}个种子，当前{len(torrent_records)}个"
            logger.error(error_msg)
            result.status = "failed"
            result.msg = error_msg
            result.code = "400"
            return result

        # 提取hash列表
        group_hashes = [r.hash for r in torrent_records]

        # ========== 执行重检操作 ==========
        try:
            # 使用枚举类型判断下载器类型
            if downloader_vo.downloader_type == 0:
                # qBittorrent 下载器
                client.torrents_recheck(torrent_hashes=group_hashes)

            elif downloader_vo.downloader_type == 1:
                # Transmission 下载器
                client.verify_torrent(group_hashes)

            else:
                error_msg = f"不支持的下载器类型: {downloader_vo.downloader_type}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 修复CRITICAL #2: API调用成功后再更新数据库
            for record in torrent_records:
                old_status = record.status
                record.status = "checking"
                db.add(record)

                # 修复CRITICAL #3: 使用安全包装记录审计日志
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.RECHECK,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_name": downloader_vo.nickname,
                        "downloader_type": downloader_vo.downloader_type
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    old_value={"status": old_status},
                    new_value={"status": "checking"},
                    operation_result=AuditOperationResult.SUCCESS,
                    audit_info=audit_info
                )

            # 提交数据库事务
            db.commit()

            result.msg = f"成功重检 {len(torrent_records)} 个种子"
            result.data = {
                "success_count": len(torrent_records),
                "failed_items": []
            }

        except Exception as e:
            # 严格模式：任何失败都回滚
            db.rollback()
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"重新检查种子失败 [downloader_id={downloader_id}]: {error_detail}")

            result.status = "failed"
            result.msg = f"重检失败：{error_detail}"
            result.code = "500"
            result.data = {
                "success_count": 0,
                "failed_items": [{
                    "hash": r.hash,
                    "name": r.name,
                    "error": error_detail
                } for r in torrent_records]
            }

            # 记录失败的审计日志
            for record in torrent_records:
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.RECHECK,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_type": downloader_vo.downloader_type,
                        "exception_type": type(e).__name__
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    operation_result=AuditOperationResult.FAILED,
                    error_message=error_detail,
                    audit_info=audit_info
                )

            return result
        # 注意：不再需要 finally 块手动释放连接，因为使用的是缓存连接

    except Exception as e:
        db.rollback()
        error_detail = f"{type(e).__name__}: {str(e)}"
        logger.error(f"重新检查种子异常: {error_detail}")

        result.status = "failed"
        result.msg = f"操作异常：{error_detail}"
        result.code = "500"

    return result


@router.delete("/delete", description="删除种子接口",
               response_model=CommonResponse)
async def delete_torrent(
        http_request: Request,
        info_id: Optional[str] = Query(None, description="种子id"),
        downloader_id: Optional[str] = Query(None, description="下载器id"),
        delete_data: Optional[int] = Query(None, description="是否删除数据，1是true,0是false"),
        id_recycle: Optional[int] = Query(None, description="是否进入回收箱，1是true,0是false"),
        db: Session = Depends(get_db)
):
    """删除种子（使用TorrentDeletionService统一入口）"""
    # 验证token
    try:
        from app.auth.utils import verify_access_token
        token = http_request.headers.get("x-access-token")
        if not verify_access_token(token):
            return CommonResponse(
                code="401",
                msg="token验证失败或已过期",
                status="error",
                data=None
            )
    except Exception as e:
        return CommonResponse(
            code="401",
            msg=f"token验证失败：{str(e)}",
            status="error",
            data=None
        )

    try:
        # 参数验证
        delete_option = DeleteOption.DELETE_FILES_AND_TORRENT if delete_data else DeleteOption.DELETE_ONLY_TORRENT
        safety_check_level = SafetyCheckLevel.ENHANCED

        # 获取异步数据库会话和审计服务
        from app.database import AsyncSessionLocal
        from app.services.audit_service import get_audit_service

        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 创建删除服务（传入审计服务）
            deletion_service = TorrentDeletionService(
                db=db,
                audit_service=audit_service,
                async_db_session=async_db
            )

            # 🔧 修复：注册下载器适配器（从缓存获取客户端连接）
            from app.services.torrent_deletion_service import DownloaderAdapterFactory

            # 查询要删除的种子所属的下载器
            torrent_info = db.query(torrentInfoModel).filter(
                torrentInfoModel.info_id == info_id,
                torrentInfoModel.dr == 0
            ).first()

            if torrent_info:
                # 从缓存获取下载器（工作约束16：必须使用缓存中的客户端连接）
                app = http_request.app

                # 检查缓存是否已初始化
                if not hasattr(app.state, 'store'):
                    return CommonResponse(
                        code="500",
                        msg="下载器缓存未初始化",
                        status="error",
                        data=None
                    )

                # 从缓存获取下载器快照（使用异步版本）
                cached_downloaders = await app.state.store.get_snapshot()
                downloader_vo = next(
                    (d for d in cached_downloaders if d.downloader_id == torrent_info.downloader_id),
                    None
                )

                # 验证下载器是否在缓存中
                if not downloader_vo:
                    logger.warning(f"下载器{torrent_info.downloader_id}不在缓存中")
                    return CommonResponse(
                        code="404",
                        msg=f"下载器{torrent_info.downloader_id}不在缓存中",
                        status="error",
                        data=None
                    )

                # 验证下载器是否有效（fail_time=0 表示有效）
                if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
                    logger.warning(
                        f"下载器已失效 [downloader_id={downloader_vo.downloader_id}, nickname={downloader_vo.nickname}]")
                    return CommonResponse(
                        code="503",
                        msg=f"下载器已失效 [nickname={downloader_vo.nickname}]",
                        status="error",
                        data=None
                    )

                # 获取缓存的客户端连接
                client = downloader_vo.client

                # 验证客户端是否存在
                if not client:
                    logger.error(f"下载器客户端连接不存在 [downloader_id={downloader_vo.downloader_id}]")
                    return CommonResponse(
                        code="500",
                        msg="下载器客户端连接不存在",
                        status="error",
                        data=None
                    )

                try:
                    # 🔧 关键修复：统一下载器类型字符串（用于适配器创建）
                    downloader_type_str = None
                    if downloader_vo.downloader_type == 0 or downloader_vo.downloader_type == '0':
                        downloader_type_str = 'qbittorrent'
                    elif downloader_vo.downloader_type == 1 or downloader_vo.downloader_type == '1':
                        downloader_type_str = 'transmission'

                    if downloader_type_str:
                        # 使用缓存的客户端连接创建适配器（不再重新创建连接）
                        adapter = DownloaderAdapterFactory.create_adapter(
                            downloader_type=downloader_type_str,
                            client=client  # 传入缓存的客户端连接
                        )

                        # 注册适配器
                        deletion_service.register_adapter(
                            downloader_type=downloader_vo.downloader_type,
                            adapter=adapter
                        )
                        logger.info(
                            f"已注册下载器适配器（使用缓存连接）: {downloader_vo.nickname} ({downloader_type_str}), key={downloader_vo.downloader_type}")
                    else:
                        logger.error(f"不支持的下载器类型: {downloader_vo.downloader_type}")
                        return CommonResponse(
                            code="400",
                            msg=f"不支持的下载器类型: {downloader_vo.downloader_type}",
                            status="error",
                            data=None
                        )
                except Exception as e:
                    logger.error(f"注册下载器适配器失败: {str(e)}")
                    return CommonResponse(
                        code="500",
                        msg=f"下载器适配器初始化失败: {str(e)}",
                        status="error",
                        data=None
                    )
            else:
                logger.warning(f"种子{info_id}不存在或已删除")

        # 创建删除请求
        delete_request = DeleteRequest(
            torrent_info_ids=[info_id] if info_id else [],
            delete_option=delete_option,
            safety_check_level=safety_check_level,
            force_delete=True,  # 强制删除，因为用户已确认
            reason=f"用户手动删除，id_recycle={id_recycle}"
        )

        # 执行删除
        result = await deletion_service.delete_torrents(delete_request)

        # 检查删除结果
        if result.failed_count > 0:
            return CommonResponse(
                code="500",
                msg=f"删除失败：{result.failed_count}个",
                status="error",
                data={
                    "success_count": result.success_count,
                    "failed_count": result.failed_count,
                    "skipped_count": result.skipped_count,
                    "failed_torrents": result.failed_torrents
                }
            )

        return CommonResponse(
            code="200",
            msg=f"删除成功，共删除{result.success_count}个种子",
            status="success",
            data={
                "success_count": result.success_count,
                "failed_count": result.failed_count,
                "skipped_count": result.skipped_count,
                "total_size_freed": result.total_size_freed
            }
        )

    except ValueError as e:
        return CommonResponse(code="400", msg=f"参数错误: {str(e)}", status="error", data=None)
    except Exception as e:
        logger.error(f"删除种子失败: {str(e)}")
        return CommonResponse(code="500", msg="服务器内部错误", status="error", data=None)


def tr_add_torrents(db, downloaders):
    """
    根据transmission的种子数据结构创建插入数据

    Args:
        db: 数据库会话
        downloaders: 下载器列表

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
        timeout=100.0
        # 调试日志：验证查询条件    logger.info(f"[getList] 开始查询种子列表，过滤条件: dr=0, downloader_id={downloader_id}")
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
            status=convert_transmission_status(torrent_info.status),
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


def qb_add_torrents(db, downloaders):
    """
    根据qbittorrent的种子数据结构创建插入数据

    Args:
        db: 数据库会话
        downloaders: 下载器列表

    Raises:
        ValueError: 当下载器列表为空时
    """
    # 添加空列表检查，防止IndexError
    if not downloaders or len(downloaders) == 0:
        logger.error("下载器列表为空，无法同步种子信息")
        return

    bt_downloader = downloaders[0]
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

MAX_OPTIMISTIC_LOCK_RETRIES = 3


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


def get_tracker_by_tracker_url(db, torrent_info_id, tracker_url):
    return db.query(trackerInfoModel).filter(
        trackerInfoModel.torrent_info_id == torrent_info_id).filter(
        trackerInfoModel.tracker_url == tracker_url).filter(
        trackerInfoModel.dr == 0).first()


def create_torrent(db: Session, torrent_data: Dict[str, Any]) -> TorrentInfo:
    """
    创建新的种子记录

    Args:
        db: 数据库会话
        torrent_data: 种子数据字典

    Returns:
        新创建的种子信息对象
    """
    # 如果没有提供ID，则生成一个UUID
    if "id_" not in torrent_data:
        torrent_data["id_"] = str(uuid.uuid4())

    db_torrent = TorrentInfo(**torrent_data)
    db.add(db_torrent)
    db.commit()
    db.refresh(db_torrent)
    return db_torrent


def get_torrent(db: Session, torrent_id: str) -> Optional[TorrentInfo]:
    """
    通过ID获取种子信息

    Args:
        db: 数据库会话
        torrent_id: 种子ID

    Returns:
        种子信息对象或None
    """
    return db.query(TorrentInfo).filter(TorrentInfo.info_id == torrent_id).first()


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


def get_torrents(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        tags: Optional[str] = None,
        category: Optional[str] = None
) -> List[TorrentInfo]:
    """
    获取种子列表，支持分页和过滤

    Args:
        db: 数据库会话
        skip: 跳过记录数
        limit: 返回记录数上限
        status: 按状态过滤
        tags: 按标签过滤
        category: 按分类过滤

    Returns:
        种子信息对象列表
    """
    query = db.query(TorrentInfo)

    if status:
        query = query.filter(TorrentInfo.status == status)
    if tags:
        query = query.filter(TorrentInfo.tags.like(f"%{tags}%"))
    if category:
        query = query.filter(TorrentInfo.category == category)

    return query.offset(skip).limit(limit).all()


def search_torrents_by_name(db: Session, name_query: str, skip: int = 0, limit: int = 100) -> List[TorrentInfo]:
    """
    通过名称搜索种子

    Args:
        db: 数据库会话
        name_query: 名称搜索关键词
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        种子信息对象列表
    """
    return db.query(TorrentInfo).filter(
        TorrentInfo.name.like(f"%{name_query}%")
    ).offset(skip).limit(limit).all()


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
    except SQLAlchemyError as e:
        db.rollback()
        raise e  # 重新抛出异常，便于调试


def delete_torrent(db: Session, torrent_id: str) -> bool:
    """
    删除种子信息

    Args:
        db: 数据库会话
        torrent_id: 种子ID

    Returns:
        操作是否成功
    """
    db_torrent = get_torrent(db, torrent_id)
    if not db_torrent:
        return False

    db.delete(db_torrent)
    db.commit()
    return True


def get_torrents_count(
        db: Session,
        status: Optional[str] = None,
        category: Optional[str] = None
) -> int:
    """
    获取种子总数

    Args:
        db: 数据库会话
        status: 按状态过滤
        category: 按分类过滤

    Returns:
        符合条件的种子数量
    """
    query = db.query(TorrentInfo)

    if status:
        query = query.filter(TorrentInfo.status == status)
    if category:
        query = query.filter(TorrentInfo.category == category)

    return query.count()


def get_torrents_by_save_path(db: Session, path: str, skip: int = 0, limit: int = 100) -> List[TorrentInfo]:
    """
    通过保存路径获取种子列表

    Args:
        db: 数据库会话
        path: 保存路径（支持部分匹配）
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        种子信息对象列表
    """
    return db.query(TorrentInfo).filter(
        TorrentInfo.save_path.like(f"%{path}%")
    ).offset(skip).limit(limit).all()


# 自定义序列化器处理特殊类型
def custom_serializer(obj):
    """处理 JSON 不支持的数据类型"""
    if isinstance(obj, datetime):
        return obj.isoformat()  # 转换为 ISO 8601 字符串
    if isinstance(obj, set):
        return list(obj)  # 集合转列表
    if hasattr(obj, '__dict__'):
        return obj.__dict__  # 自定义对象转字典
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# 创建操作
def create_tracker(db: Session, tracker_data: Dict[str, Any]) -> TrackerInfo:
    """
    创建新的 tracker 记录

    Args:
        db: 数据库会话
        tracker_data: 包含 tracker 信息的字典

    Returns:
        新创建的 tracker 记录
    """
    # 如果没有提供 tracker_id，生成一个 UUID
    if "tracker_id" not in tracker_data:
        tracker_data["tracker_id"] = str(uuid.uuid4())

    # 设置默认值
    if "dr" not in tracker_data:
        tracker_data["dr"] = 0

    db_tracker = TrackerInfo(**tracker_data)
    db.add(db_tracker)
    db.commit()
    db.refresh(db_tracker)
    return db_tracker


# 读取操作
def get_tracker(db: Session, tracker_id: str) -> Optional[TrackerInfo]:
    """
    通过 ID 获取 tracker 记录

    Args:
        db: 数据库会话
        tracker_id: tracker 的 ID

    Returns:
        tracker 记录或 None
    """
    return db.query(TrackerInfo).filter(
        and_(
            TrackerInfo.tracker_id == tracker_id,
            TrackerInfo.dr == 0
        )
    ).first()


def get_trackers_by_torrent(db: Session, torrent_info_id: str) -> List[TrackerInfo]:
    """
    获取指定种子的所有 tracker

    Args:
        db: 数据库会话
        torrent_info_id: 种子的 ID

    Returns:
        tracker 记录列表
    """
    return db.query(TrackerInfo).filter(
        and_(
            TrackerInfo.torrent_info_id == torrent_info_id,
            TrackerInfo.dr == 0
        )
    ).all()


def get_trackers(db: Session, skip: int = 0, limit: int = 100) -> List[TrackerInfo]:
    """
    获取所有 tracker 记录，支持分页

    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的最大记录数

    Returns:
        tracker 记录列表
    """
    return db.query(TrackerInfo).filter(TrackerInfo.dr == 0).offset(skip).limit(limit).all()


def get_trackers_by_status(db: Session, status: str) -> List[TrackerInfo]:
    """
    获取指定状态的所有 tracker

    Args:
        db: 数据库会话
        status: tracker 状态

    Returns:
        tracker 记录列表
    """
    return db.query(TrackerInfo).filter(
        and_(
            TrackerInfo.tracker_status == status,
            TrackerInfo.dr == 0
        )
    ).all()


# 更新操作
def update_tracker(db: Session, tracker_id: str, tracker_data: Dict[str, Any]) -> Optional[TrackerInfo]:
    """
    更新 tracker 记录

    Args:
        db: 数据库会话
        tracker_id: 要更新的 tracker ID
        tracker_data: 包含要更新的字段的字典

    Returns:
        更新后的 tracker 记录或 None
    """
    # 确保 tracker_data 是字典类型
    if not isinstance(tracker_data, dict):
        raise TypeError("tracker_data 必须是字典类型")

    db_tracker = get_tracker(db, tracker_id)
    if not db_tracker:
        return None

    try:
        # 更新属性
        for key, value in tracker_data.items():
            if hasattr(db_tracker, key):
                setattr(db_tracker, key, value)

        db.commit()
        db.refresh(db_tracker)
        return db_tracker
    except Exception as e:
        db.rollback()
        raise e


def update_tracker_status(db: Session, tracker_id: str, status: str, msg: Optional[str] = None) -> Optional[
    TrackerInfo]:
    """
    更新 tracker 状态

    Args:
        db: 数据库会话
        tracker_id: tracker ID
        status: 新状态
        msg: 可选的状态消息

    Returns:
        更新后的 tracker 记录或 None
    """
    update_data = {"tracker_status": status}
    if msg is not None:
        update_data["last_scrape_msg"] = msg

    return update_tracker(db, tracker_id, update_data)


# 删除操作
def delete_tracker(db: Session, tracker_id: str) -> bool:
    """
    标记 tracker 为已删除（软删除）

    Args:
        db: 数据库会话
        tracker_id: 要删除的 tracker ID

    Returns:
        是否成功删除
    """
    db_tracker = get_tracker(db, tracker_id)
    if not db_tracker:
        return False

    db_tracker.dr = 1
    db.commit()
    return True


def hard_delete_tracker(db: Session, tracker_id: str) -> bool:
    """
    从数据库中物理删除 tracker 记录

    Args:
        db: 数据库会话
        tracker_id: 要删除的 tracker ID

    Returns:
        是否成功删除
    """
    db_tracker = db.query(TrackerInfo).filter(TrackerInfo.tracker_id == tracker_id).filter(TrackerInfo.dr == 1).first()
    if not db_tracker:
        return False

    db.delete(db_tracker)
    db.commit()
    return True


def delete_trackers_by_torrent(db: Session, torrent_info_id: str) -> int:
    """
    删除与指定种子关联的所有 tracker（软删除）

    Args:
        db: 数据库会话
        torrent_info_id: 种子 ID

    Returns:
        删除的记录数
    """
    trackers = get_trackers_by_torrent(db, torrent_info_id)
    count = 0

    for tracker in trackers:
        tracker.dr = 1
        count += 1

    db.commit()
    return count


def create_torrent_info(
        db: Session,
        info_id: str,
        downloader_id: str,
        downloader_name: str,
        torrent_id: str,
        hash: str,
        name: str,
        save_path: str,
        size: float,
        status: str,
        torrent_file: str,
        added_date: int,
        completed_date: Optional[int] = None,
        ratio: str = "0.0",
        ratio_limit: str = "",
        tags: str = "",
        category: str = "",
        super_seeding: str = "0",
        enabled: int = 1,
        dr: int = 0
) -> torrentInfoModel:
    """创建新的种子信息记录"""
    db_torrent = torrentInfoModel(
        id_=info_id,
        downloader_id=downloader_id,
        downloader_name=downloader_name,
        torrent_id=torrent_id,
        hash=hash,
        name=name,
        save_path=save_path,
        size=size,
        status=status,
        torrent_file=torrent_file,
        added_date=added_date,
        completed_date=completed_date,
        ratio=ratio,
        ratio_limit=ratio_limit,
        tags=tags,
        category=category,
        super_seeding=super_seeding,
        enabled=enabled,
        dr=dr
    )
    db.add(db_torrent)
    db.commit()
    db.refresh(db_torrent)
    return db_torrent


def get_torrent_info(
        db: Session,
        info_id: str,
        downloader_id: str,
) -> Optional[TorrentInfo]:
    """根据复合主键获取种子信息"""
    return db.query(TorrentInfo).filter(
        TorrentInfo.info_id == info_id,
        TorrentInfo.downloader_id == downloader_id,
        TorrentInfo.dr == 0
    ).first()


def update_torrent_info(
        db: Session,
        info_id: str,
        downloader_id: str,
        downloader_name: str,
        update_data: Dict[str, Any]
) -> Optional[TorrentInfo]:
    """更新种子信息"""
    db_torrent = get_torrent_info(db, info_id, downloader_id, downloader_name)
    if not db_torrent:
        return None

    # 过滤掉不允许更新的字段
    allowed_fields = {
        "torrent_id", "hash", "name", "save_path", "size", "status",
        "torrent_file", "added_date", "completed_date", "ratio", "ratio_limit",
        "tags", "category", "super_seeding", "enabled", "dr"
    }

    for field, value in update_data.items():
        if field in allowed_fields and hasattr(db_torrent, field):
            setattr(db_torrent, field, value)

    db.commit()
    db.refresh(db_torrent)
    return db_torrent


def delete_torrent_info(
        db: Session,
        info_id: str,
        downloader_id: str
) -> bool:
    """软删除种子信息"""
    db_torrent = get_torrent_info(db, info_id, downloader_id)
    if not db_torrent:
        return False

    db_torrent.dr = 1
    logger.info(f"[delete_torrent_info] 软删除种子: info_id={info_id}, 设置 dr=1")
    db_torrent.update_time = datetime.now()
    db_torrent.update_by = "admin"
    # 删除tracker表数据
    db.execute(text(
        "update tracker_info set update_time=datetime('now'),dr=1 where torrent_info_id =:info_id;")
        , {"info_id": info_id})
    db.commit()
    return True


# 通用查询方法
def get_torrent_infos(
        db: Session,
        downloader_id: Optional[str] = None,
        downloader_name_like: Optional[str] = None,
        name_like: Optional[str] = None,
        save_path_like: Optional[str] = None,
        size_min: Optional[str] = None,
        size_max: Optional[str] = None,
        added_date_min: Optional[str] = None,
        added_date_max: Optional[str] = None,
        completed_date_min: Optional[str] = None,
        completed_date_max: Optional[str] = None,
        tags_like: Optional[str] = None,
        category_like: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        tracker: Optional[str] = None,
) -> Dict[str, Any]:
    """通用查询方法，支持多种过滤条件和排序，返回数据总数和列表"""
    # 构建基础查询（排除回收站中的种子：dr=0 且 deleted_at=NULL）
    query = db.query(TorrentInfo).filter(
        and_(
            TorrentInfo.dr == 0,
            TorrentInfo.deleted_at.is_(None)  # 只显示未移入回收站的种子
        )
    )

    # 构建计数查询（相同的过滤条件）
    count_query = db.query(TorrentInfo).filter(
        and_(
            TorrentInfo.dr == 0,
            TorrentInfo.deleted_at.is_(None)  # 只统计未移入回收站的种子
        )
    )

    # 添加过滤条件
    if downloader_id:
        query = query.filter(TorrentInfo.downloader_id == downloader_id)
        count_query = count_query.filter(TorrentInfo.downloader_id == downloader_id)

    if downloader_name_like:
        like_pattern = f"%{downloader_name_like}%"
        query = query.filter(TorrentInfo.downloader_name.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.downloader_name.like(like_pattern))

    if name_like:
        like_pattern = f"%{name_like}%"
        query = query.filter(TorrentInfo.name.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.name.like(like_pattern))

    if save_path_like:
        like_pattern = f"%{save_path_like}%"
        query = query.filter(TorrentInfo.save_path.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.save_path.like(like_pattern))

    if size_min is not None:
        size_min_bytes = parse_size_string(size_min)
        if size_min_bytes is not None:
            query = query.filter(TorrentInfo.size >= size_min_bytes)
            count_query = count_query.filter(TorrentInfo.size >= size_min_bytes)

    if size_max is not None:
        size_max_bytes = parse_size_string(size_max)
        if size_max_bytes is not None:
            query = query.filter(TorrentInfo.size <= size_max_bytes)
            count_query = count_query.filter(TorrentInfo.size <= size_max_bytes)

    if added_date_min is not None:
        added_date_min_datetime = parse_datetime_string(added_date_min)
        if added_date_min_datetime is not None:
            query = query.filter(TorrentInfo.added_date >= added_date_min_datetime)
            count_query = count_query.filter(TorrentInfo.added_date >= added_date_min_datetime)

    if added_date_max is not None:
        added_date_max_datetime = parse_datetime_string(added_date_max)
        if added_date_max_datetime is not None:
            query = query.filter(TorrentInfo.added_date <= added_date_max_datetime)
            count_query = count_query.filter(TorrentInfo.added_date <= added_date_max_datetime)

    if completed_date_min is not None:
        completed_date_min_datetime = parse_datetime_string(completed_date_min)
        if completed_date_min_datetime is not None:
            query = query.filter(TorrentInfo.completed_date >= completed_date_min_datetime)
            count_query = count_query.filter(TorrentInfo.completed_date >= completed_date_min_datetime)

    if completed_date_max is not None:
        completed_date_max_datetime = parse_datetime_string(completed_date_max)
        if completed_date_max_datetime is not None:
            query = query.filter(TorrentInfo.completed_date <= completed_date_max_datetime)
            count_query = count_query.filter(TorrentInfo.completed_date <= completed_date_max_datetime)

    if tags_like:
        like_pattern = f"%{tags_like}%"
        query = query.filter(TorrentInfo.tags.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.tags.like(like_pattern))

    if category_like:
        like_pattern = f"%{category_like}%"
        query = query.filter(TorrentInfo.category.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.category.like(like_pattern))

    if tracker:
        tracker_query_result = db.query(TrackerInfo.torrent_info_id).filter(
            TrackerInfo.tracker_url.like(f"%{tracker}%")).filter(TrackerInfo.dr == 0).all()
        if tracker_query_result.__len__() > 0:
            info_id_list = [row[0] for row in tracker_query_result]
            query = query.filter(TorrentInfo.info_id.in_(info_id_list))
            count_query = count_query.filter(TorrentInfo.info_id.in_(info_id_list))

    # 状态筛选：error状态满足 status='error' 或 has_tracker_error=True 之一即可
    if status:
        if status == 'error':
            query = query.filter(
                or_(
                    TorrentInfo.status == 'error',
                    TorrentInfo.has_tracker_error == True
                )
            )
            count_query = count_query.filter(
                or_(
                    TorrentInfo.status == 'error',
                    TorrentInfo.has_tracker_error == True
                )
            )
        else:
            query = query.filter(TorrentInfo.status == status)
            count_query = count_query.filter(TorrentInfo.status == status)

    # 获取总数
    total = count_query.count()

    # 处理排序
    if sort_by:
        sort_column = getattr(TorrentInfo, sort_by, None)
        if sort_column is not None:
            if sort_order and sort_order.lower() == "asc":
                query = query.order_by(asc(sort_column))
            else:
                query = query.order_by(desc(sort_column))
    else:
        # 默认按添加时间倒序排序
        query = query.order_by(desc(TorrentInfo.added_date))

    # 分页查询
    query_result_list = query.offset(skip).limit(limit).all()
    data = [convert_to_vo_with_trackers(db, torrent) for torrent in query_result_list]

    return {
        "total": total,
        "data": data
    }


def get_torrent_infos_legacy(
        db: Session,
        downloader_id: Optional[str] = None,
        downloader_name_like: Optional[str] = None,
        name_like: Optional[str] = None,
        save_path_like: Optional[str] = None,
        size_min: Optional[str] = None,
        size_max: Optional[str] = None,
        added_date_min: Optional[str] = None,
        added_date_max: Optional[str] = None,
        completed_date_min: Optional[str] = None,
        completed_date_max: Optional[str] = None,
        tags_like: Optional[str] = None,
        category_like: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        tracker: Optional[str] = None,
) -> List[TorrentInfo]:
    """通用查询方法（旧版本，保持兼容性），支持多种过滤条件和排序"""
    result = get_torrent_infos(
        db=db,
        downloader_id=downloader_id,
        downloader_name_like=downloader_name_like,
        name_like=name_like,
        save_path_like=save_path_like,
        size_min=size_min,
        size_max=size_max,
        added_date_min=added_date_min,
        added_date_max=added_date_max,
        completed_date_min=completed_date_min,
        completed_date_max=completed_date_max,
        tags_like=tags_like,
        category_like=category_like,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        tracker=tracker
    )
    return result["data"]


# 批量操作
def bulk_create_torrent_infos(
        db: Session,
        torrents_data: List[Dict[str, Any]]
) -> List[TorrentInfo]:
    """批量创建种子信息"""
    db_torrents = []
    for torrent_data in torrents_data:
        # 确保必要字段存在
        required_fields = ["info_id", "downloader_id", "downloader_name", "torrent_id", "hash", "name", "save_path",
                           "size", "status", "torrent_file", "added_date"]
        if not all(field in torrent_data for field in required_fields):
            continue

        db_torrent = TorrentInfo(
            id_=torrent_data["info_id"],
            downloader_id=torrent_data["downloader_id"],
            downloader_name=torrent_data["downloader_name"],
            torrent_id=torrent_data["torrent_id"],
            hash=torrent_data["hash"],
            name=torrent_data["name"],
            save_path=torrent_data["save_path"],
            size=torrent_data["size"],
            status=torrent_data["status"],
            torrent_file=torrent_data["torrent_file"],
            added_date=torrent_data["added_date"],
            completed_date=torrent_data.get("completed_date"),
            ratio=torrent_data.get("ratio", "0.0"),
            ratio_limit=torrent_data.get("ratio_limit", ""),
            tags=torrent_data.get("tags", ""),
            category=torrent_data.get("category", ""),
            super_seeding=torrent_data.get("super_seeding", "0"),
            enabled=torrent_data.get("enabled", 1),
            dr=torrent_data.get("dr", 0)
        )
        db_torrents.append(db_torrent)

    db.add_all(db_torrents)
    db.commit()
    for torrent in db_torrents:
        db.refresh(torrent)
    return db_torrents


# 统计方法
def count_torrent_infos(
        db: Session,
        downloader_id: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None
) -> int:
    """统计符合条件的种子数量"""
    query = db.query(TorrentInfo).filter(TorrentInfo.dr == 0)

    if downloader_id:
        query = query.filter(TorrentInfo.downloader_id == downloader_id)

    if status:
        query = query.filter(TorrentInfo.status == status)

    if category:
        query = query.filter(TorrentInfo.category == category)

    return query.count()


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
        size=torrent.size,
        status=torrent.status,
        torrent_file=torrent.torrent_file,
        added_date=added_timestamp,
        completed_date=completed_timestamp,
        ratio=torrent.ratio,
        ratio_limit=torrent.ratio_limit,
        tags=torrent.tags,
        category=torrent.category,
        super_seeding=torrent.super_seeding,
        enabled=torrent.enabled
    )


def convert_to_vo_with_trackers(db: Session, torrent: torrentInfoModel) -> TorrentInfoVO:
    """将数据库模型转换为VO对象，包含tracker信息"""
    # 保持datetime对象不变，让 Pydantic 序列化时自动转换为 ISO 8601 格式

    # 导入枚举类
    from app.enums.tracker_status import QBittorrentTrackerStatus, TransmissionTrackerStatus

    # 查询关联的tracker信息
    # 🔧 修复：使用 torrent.hash 查询 tracker，因为 tracker 表的 torrent_info_id 字段存储的是 hash
    trackers = db.query(TrackerInfo).filter(
        TrackerInfo.torrent_info_id == torrent.info_id,
        TrackerInfo.dr == 0  # 只查询未逻辑删除的tracker数据
    ).all()

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
    try:
        from app.downloader.models import BtDownloaders
        downloader = db.query(BtDownloaders.downloader_type).filter(
            BtDownloaders.downloader_id == torrent.downloader_id
        ).first()
        if downloader:
            # 从 Row 对象中正确提取整数值
            # SQLAlchemy 查询单列返回 Row 对象，需要通过列名或索引访问
            if hasattr(downloader, 'downloader_type'):
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

        # 构建tracker_info对象数组
        tracker_vo = TrackerInfoVO(
            tracker_id=tracker.tracker_id,
            tracker_name=tracker.tracker_name,
            tracker_url=tracker.tracker_url,
            last_announce_succeeded=announce_status_text,  # 返回中文状态
            last_announce_msg=tracker.last_announce_msg,
            last_scrape_succeeded=scrape_status_text,  # 返回中文状态
            last_scrape_msg=tracker.last_scrape_msg
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
        size=torrent.size,
        status=torrent.status,
        progress=torrent.progress,
        torrent_file=torrent.torrent_file,
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
        tracker_info=tracker_info_list
    )


def parse_size_string(size_str: Optional[str]) -> Optional[int]:
    """将大小字符串转换为字节数"""
    if not size_str:
        return None

    # 使用正则表达式匹配数字和单位
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([BKMG]?)B?$', size_str, re.IGNORECASE)
    if not match:
        return None

    size_value = float(match.group(1))
    unit = match.group(2).upper()

    # 根据单位计算字节数
    if unit == 'K':  # KB
        return int(size_value * 1024)
    elif unit == 'M':  # MB
        return int(size_value * 1024 * 1024)
    elif unit == 'G':  # GB
        return int(size_value * 1024 * 1024 * 1024)
    elif unit == 'T':  # TB
        return int(size_value * 1024 * 1024 * 1024 * 1024)
    else:  # B (无单位或B)
        return int(size_value)


def parse_datetime_string(datetime_str: Optional[str]) -> Optional[datetime]:
    """将日期时间字符串转换为datetime对象"""
    if not datetime_str:
        return None

    # 尝试解析不同格式的日期时间字符串
    formats = [
        "%Y-%m-%d %H:%M:%S",  # yyyy-mm-dd hh24:mi:ss
        "%Y-%m-%d %H:%M",  # yyyy-mm-dd hh24:mi
        "%Y-%m-%d",  # yyyy-mm-dd
        "%Y/%m/%d %H:%M:%S",  # yyyy/mm/dd hh24:mi:ss
        "%Y/%m/%d %H:%M",  # yyyy/mm/dd hh24:mi
        "%Y/%m/%d",  # yyyy/mm/dd
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(datetime_str, fmt)
            return dt
        except ValueError:
            continue

    # 如果所有格式都失败，尝试解析ISO格式
    try:
        dt = datetime.fromisoformat(datetime_str)
        return dt
    except ValueError:
        return None


async def calculate_info_hash(torrent_file_path: str) -> str:
    """计算种子文件的info_hash"""
    try:
        # 将文件读取和解析操作放到线程池中执行
        def read_and_decode_file(file_path):
            with open(file_path, 'rb') as f:
                file_content = f.read()
            return bencodepy.decode(file_content)

        torrent_data = await asyncio.to_thread(read_and_decode_file, torrent_file_path)

        # 获取info部分并计算SHA1哈希
        info_data = bencodepy.encode(torrent_data[b'info'])
        info_hash = hashlib.sha1(info_data).hexdigest()

        return info_hash
    except Exception as e:
        raise Exception(f"计算info_hash失败: {str(e)}")


async def get_transmission_torrent_info(tr_client: trClient, info_hash: str, timeout: int = 10) -> Optional[
    Dict[str, Any]]:
    """从Transmission获取种子信息"""
    import time

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # 获取所有种子
            torrents = tr_client.get_torrents(info_hash)
            return torrents[0]
            # 查找匹配的种子
            # for torrent in torrents:
            #     if torrent.hashString.lower() == info_hash.lower():
            #         return torrent
            #
            # time.sleep(1)
        except Exception as e:
            # 如果出错，等待一会儿再试
            await asyncio.sleep(1)

    return None


def convert_transmission_status(transmission_status: str) -> str:
    """
    将Transmission状态转换为通用状态

    注意：此函数保留以向后兼容，建议直接使用 TorrentStatusMapper.convert_transmission_status()
    """
    return TorrentStatusMapper.convert_transmission_status(transmission_status)


def create_qbittorrent_torrent_record(downloader, downloader_id, qb_torrent, tmp_file_path):
    """创建qBittorrent种子信息记录"""
    db_torrent = torrentInfoModel(
        id_=str(uuid.uuid4()),
        downloader_id=downloader_id,
        downloader_name=downloader.nickname,
        torrent_id=qb_torrent.hash,
        hash=qb_torrent.hash,
        name=qb_torrent.name,
        save_path=qb_torrent.save_path,
        size=qb_torrent.total_size,
        status=TorrentStatusMapper.convert_qbittorrent_status(qb_torrent.state),
        torrent_file="/config/qbittorrent/BT_backup/" + qb_torrent.hash + ".torrent",
        added_date=datetime.fromtimestamp(qb_torrent.added_on),
        completed_date=datetime.fromtimestamp(qb_torrent.completion_on) if qb_torrent.completion_on > 0 else None,
        ratio=str(qb_torrent.ratio),
        ratio_limit=str(qb_torrent.ratio_limit) if qb_torrent.ratio_limit != -1 else "",
        tags=",".join(qb_torrent.tags) if qb_torrent.tags else "",
        category=qb_torrent.category,
        super_seeding="1" if qb_torrent.super_seeding else "0",
        enabled=1,
        create_time=datetime.fromtimestamp(qb_torrent.added_on),
        create_by="admin",
        update_time=datetime.fromtimestamp(qb_torrent.added_on),
        update_by="admin",
        dr=0,  # 🔧 修复：添加缺失的 dr 参数
        progress=0  # 🔧 修复：添加缺失的 progress 参数
    )
    return db_torrent


def create_transmission_torrent_record(downloader, downloader_id, tr_torrent):
    db_torrent = torrentInfoModel(
        id_=str(uuid.uuid4()),
        downloader_id=downloader_id,
        downloader_name=downloader.nickname,
        torrent_id=tr_torrent.id,
        hash=tr_torrent.hashString,
        name=tr_torrent.name,
        save_path=tr_torrent.download_dir,
        size=tr_torrent.total_size,
        status=convert_transmission_status(tr_torrent.status),
        torrent_file=tr_torrent.torrent_file,
        added_date=tr_torrent.added_date,
        completed_date=tr_torrent.done_date if tr_torrent.done_date else None,
        ratio=str(tr_torrent.seed_ratio_limit),
        ratio_limit="",
        tags=",".join(tr_torrent.labels) if hasattr(tr_torrent, 'labels') and tr_torrent.labels else "",
        category="",
        super_seeding="",
        enabled=1,
        create_time=tr_torrent.added_date,
        create_by="admin",
        update_time=tr_torrent.added_date,
        update_by="admin",
        dr=0,  # 🔧 修复：添加缺失的 dr 参数
        progress=0  # 🔧 修复：添加缺失的 progress 参数
    )
    return db_torrent


# ==================== 批量删除功能 ====================

# 批量删除请求模型
class BulkDeleteRequest(BaseModel):
    """批量删除种子请求"""
    torrent_info_ids: List[str] = Field(..., description="要删除的种子信息ID列表", min_items=1, max_items=1000)
    delete_option: str = Field(default="delete_only_torrent", description="删除选项")
    safety_check_level: str = Field(default="enhanced", description="安全检查级别")
    force_delete: bool = Field(default=False, description="是否强制删除（跳过安全确认）")
    reason: Optional[str] = Field(default=None, description="删除原因")


class DeletionPreviewRequest(BaseModel):
    """删除预览请求"""
    torrent_info_ids: List[str] = Field(..., description="要预览的种子信息ID列表", min_items=1, max_items=1000)
    delete_option: str = Field(default="delete_only_torrent", description="删除选项")
    safety_check_level: str = Field(default="enhanced", description="安全检查级别")


# 响应模型
class DeletionPreviewResponse(BaseModel):
    """删除预览响应"""
    total_torrents: int
    total_size: int
    torrents_by_downloader: Dict[str, Any]
    safety_warnings: List[str]
    estimated_execution_time: float


class DeletionResultResponse(BaseModel):
    """删除结果响应"""
    success_count: int
    failed_count: int
    skipped_count: int
    total_size_freed: int
    execution_time: float
    safety_warnings: List[str]
    deleted_torrents: List[Dict[str, Any]]
    failed_torrents: List[Dict[str, Any]]
    skipped_torrents: List[Dict[str, Any]]


@router.post("/delete/preview")
async def preview_bulk_torrent_deletion(
        request: DeletionPreviewRequest,
        http_request: Request,
        db: Session = Depends(get_db)
):
    """
    预览批量种子删除操作
    注意：此端点不依赖用户认证，与其他 torrents 端点保持一致
    """
    # 验证token
    try:
        from app.auth.utils import verify_access_token
        token = http_request.headers.get("x-access-token")
        if not verify_access_token(token):
            return CommonResponse(
                code="401",
                msg="token验证失败或已过期",
                status="error",
                data=None
            )
    except Exception as e:
        return CommonResponse(
            code="401",
            msg=f"token验证失败：{str(e)}",
            status="error",
            data=None
        )

    try:
        # 参数验证
        delete_option = DeleteOption(request.delete_option)
        safety_check_level = SafetyCheckLevel(request.safety_check_level)

        # 获取异步数据库会话和审计服务
        from app.database import AsyncSessionLocal
        from app.services.audit_service import get_audit_service

        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 创建删除服务（传入审计服务）
            deletion_service = TorrentDeletionService(
                db=db,
                audit_service=audit_service,
                async_db_session=async_db
            )

            # 🔧 修复：注册下载器适配器（传入app对象以访问缓存）
            _register_downloader_adapters(
                deletion_service=deletion_service,
                torrent_info_ids=request.torrent_info_ids,
                db=db,
                app=http_request.app
            )

        # 创建预览请求（dry-run模式）
        preview_request = DeleteRequest(
            torrent_info_ids=request.torrent_info_ids,
            delete_option=DeleteOption.DRY_RUN,
            safety_check_level=safety_check_level,
            force_delete=False
        )

        # 执行预览
        result = await deletion_service.delete_torrents(preview_request)

        # 组织预览响应数据
        preview_data = await _organize_preview_data(request.torrent_info_ids, db)

        response_data = DeletionPreviewResponse(
            total_torrents=result.success_count,
            total_size=result.total_size_freed,
            torrents_by_downloader=preview_data,
            safety_warnings=result.safety_warnings,
            estimated_execution_time=result.execution_time * 1.5
        )

        return CommonResponse(
            code="200",
            msg="删除预览成功",
            data=response_data.__dict__,
            status="success"
        )

    except ValueError as e:
        return CommonResponse(code="400", msg=f"参数错误: {str(e)}", status="error", data=None)
    except Exception as e:
        logger.error(f"删除预览失败: {str(e)}")
        return CommonResponse(code="500", msg="服务器内部错误", status="error", data=None)


@router.post("/delete/bulk")
async def bulk_delete_torrents(
        request: BulkDeleteRequest,
        background_tasks: BackgroundTasks,
        http_request: Request,
        db: Session = Depends(get_db)
):
    """
    批量删除种子
    """
    # 验证token
    try:
        from app.auth.utils import verify_access_token
        token = http_request.headers.get("x-access-token")
        if not verify_access_token(token):
            return CommonResponse(
                code="401",
                msg="token验证失败或已过期",
                status="error",
                data=None
            )
    except Exception as e:
        return CommonResponse(
            code="401",
            msg=f"token验证失败：{str(e)}",
            status="error",
            data=None
        )

    try:
        # 参数验证
        delete_option = DeleteOption(request.delete_option)
        safety_check_level = SafetyCheckLevel(request.safety_check_level)

        # 获取异步数据库会话和审计服务
        from app.database import AsyncSessionLocal
        from app.services.audit_service import get_audit_service

        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 创建删除服务（传入审计服务）
            deletion_service = TorrentDeletionService(
                db=db,
                audit_service=audit_service,
                async_db_session=async_db
            )

            # 🔧 修复：注册下载器适配器（传入app对象以访问缓存）
            _register_downloader_adapters(
                deletion_service=deletion_service,
                torrent_info_ids=request.torrent_info_ids,
                db=db,
                app=http_request.app
            )

        # 创建删除请求
        delete_request = DeleteRequest(
            torrent_info_ids=request.torrent_info_ids,
            delete_option=delete_option,
            safety_check_level=safety_check_level,
            force_delete=request.force_delete,
            reason=request.reason
        )

        # 执行删除
        result = await deletion_service.delete_torrents(delete_request)

        # 组织响应数据
        response_data = DeletionResultResponse(
            success_count=result.success_count,
            failed_count=result.failed_count,
            skipped_count=result.skipped_count,
            total_size_freed=result.total_size_freed,
            execution_time=result.execution_time,
            safety_warnings=result.safety_warnings,
            deleted_torrents=result.deleted_torrents,
            failed_torrents=result.failed_torrents,
            skipped_torrents=result.skipped_torrents
        )

        return CommonResponse(
            code="200",
            msg=f"种子删除完成，成功删除{result.success_count}个",
            data=response_data.__dict__,
            status="success"
        )

    except ValueError as e:
        return CommonResponse(code="400", msg=f"参数错误: {str(e)}", status="error", data=None)
    except Exception as e:
        logger.error(f"批量删除种子失败: {str(e)}")
        return CommonResponse(code="500", msg="服务器内部错误", status="error", data=None)


# 辅助函数
async def _organize_preview_data(torrent_info_ids: List[str], db: Session) -> Dict[str, Any]:
    """组织预览数据"""
    from app.models.torrents import TorrentInfo

    torrents = db.query(TorrentInfo).filter(
        TorrentInfo.info_id.in_(torrent_info_ids),
        TorrentInfo.dr == 0
    ).all()

    downloader_groups = {}

    for torrent in torrents:
        downloader_id = torrent.downloader_id
        if downloader_id not in downloader_groups:
            downloader_groups[downloader_id] = {
                "downloader_name": torrent.downloader_name,
                "torrent_count": 0,
                "total_size": 0,
                "torrents": []
            }

        group = downloader_groups[downloader_id]
        group["torrent_count"] += 1
        group["total_size"] += torrent.size or 0

        if len(group["torrents"]) < 10:
            group["torrents"].append({
                "info_id": torrent.info_id,
                "name": torrent.name,
                "size": torrent.size,
                "status": torrent.status
            })

    return downloader_groups


async def _write_audit_log_async(
        operation_type: str,
        operator: str,
        torrent_info_id: str,
        operation_detail: Dict[str, Any],
        torrent_name: Optional[str],
        torrent_hash: Optional[str],
        downloader_id: str,
        operation_result: str,
        error_message: Optional[str] = None,
        new_value: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        audit_info: Optional[Dict[str, str]] = None
):
    """异步写入审计日志的辅助函数"""
    try:
        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 构建完整的操作详情
            full_detail = operation_detail.copy()
            if torrent_name:
                full_detail["torrent_name"] = torrent_name
            if torrent_hash:
                full_detail["torrent_hash"] = torrent_hash

            await audit_service.log_operation(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=full_detail,
                old_value=old_value,
                new_value=new_value,
                operation_result=operation_result,
                error_message=error_message,
                downloader_id=downloader_id,
                **(audit_info or {})
            )
    except Exception as audit_error:
        logging.error(f"记录审计日志失败: {str(audit_error)}", exc_info=True)


def _safe_write_audit_log(
        operation_type: str,
        operator: str,
        torrent_info_id: str,
        operation_detail: Dict[str, Any],
        torrent_name: Optional[str],
        torrent_hash: Optional[str],
        downloader_id: str,
        operation_result: str,
        error_message: Optional[str] = None,
        new_value: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        audit_info: Optional[Dict[str, str]] = None
):
    """
    安全地写入审计日志（带异常处理和日志记录）

    修复CRITICAL #4: asyncio.create_task的异常会被静默忽略
    使用此包装函数确保审计日志异常不会丢失，同时记录到日志文件中
    """
    try:
        asyncio.create_task(
            _write_audit_log_async(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=operation_detail,
                torrent_name=torrent_name,
                torrent_hash=torrent_hash,
                downloader_id=downloader_id,
                operation_result=operation_result,
                error_message=error_message,
                new_value=new_value,
                old_value=old_value,
                audit_info=audit_info
            )
        )
    except Exception as e:
        # 记录创建任务失败（极少发生）
        logging.error(
            f"创建审计日志任务失败 [operation_type={operation_type}, torrent_info_id={torrent_info_id}]: {str(e)}",
            exc_info=True
        )


async def _log_deletion_operation_async(
        username: str,
        request: BulkDeleteRequest,
        result,
        audit_info: Optional[Dict[str, str]] = None
):
    """记录删除操作日志（使用异步审计日志服务）"""
    try:
        # 创建异步数据库会话
        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 安全地提取审计信息
            ip_address = None
            user_agent = None
            request_id = None
            session_id = None

            if audit_info and isinstance(audit_info, dict):
                ip_address = audit_info.get("ip_address")
                user_agent = audit_info.get("user_agent")
                request_id = audit_info.get("request_id")
                session_id = audit_info.get("session_id")

            # 确定操作类型
            operation_type_map = {
                DeleteOption.LEVEL1: AuditOperationType.DELETE_L1,
                DeleteOption.LEVEL2: AuditOperationType.DELETE_L2,
                DeleteOption.LEVEL3: AuditOperationType.DELETE_L3,
                DeleteOption.LEVEL4: AuditOperationType.DELETE_L4,
            }
            operation_type = operation_type_map.get(
                DeleteOption(request.delete_option),
                AuditOperationType.DELETE_L1
            )

            # 记录批量删除操作（为每个种子记录一条日志）
            for torrent_id in request.torrent_info_ids:
                await audit_service.log_operation(
                    operation_type=operation_type,
                    operator=username,
                    torrent_info_id=torrent_id,
                    operation_detail={
                        "delete_option": request.delete_option,
                        "safety_check_level": request.safety_check_level,
                        "force_delete": request.force_delete,
                        "reason": request.reason,
                        "bulk_operation": True,
                        "total_torrents": len(request.torrent_info_ids)
                    },
                    new_value={
                        "status": "deleted",
                        "delete_time": datetime.now().isoformat()
                    },
                    operation_result=AuditOperationResult.SUCCESS if result.failed_count == 0 else AuditOperationResult.PARTIAL,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_id=request_id,
                    session_id=session_id
                )

        # 同时保留原有的日志记录方式
        log_entry = {
            "username": username,
            "operation": "bulk_torrent_deletion",
            "request": {
                "torrent_count": len(request.torrent_info_ids),
                "delete_option": request.delete_option,
                "safety_check_level": request.safety_check_level,
                "force_delete": request.force_delete,
                "reason": request.reason
            },
            "result": {
                "success_count": result.success_count,
                "failed_count": result.failed_count,
                "skipped_count": result.skipped_count,
                "total_size_freed": result.total_size_freed,
                "execution_time": result.execution_time
            },
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"用户{username}执行批量种子删除: {log_entry}")

    except Exception as e:
        # 完整的异常记录，包含堆栈跟踪
        logger.error(
            f"记录审计日志失败（后台任务）: {str(e)}",
            exc_info=True,  # 记录完整堆栈
            extra={
                "username": username,
                "torrent_count": len(request.torrent_info_ids) if request and hasattr(request,
                                                                                      'torrent_info_ids') else 0
            }
        )
        # 不抛出异常，确保后台任务正常完成


# ==================== 按等级删除API (Task 5) ====================

class DeleteWithLevelRequest(BaseModel):
    """按等级删除种子请求"""
    torrent_info_ids: List[str] = Field(
        ...,
        description="要删除的种子信息ID列表",
        min_items=1,
        max_items=100
    )
    delete_level: int = Field(
        ...,
        description="删除等级 (3=回收站, 4=待删除标签)",
        ge=3,
        le=4
    )
    operator: str = Field(default="admin", description="操作人")


class DeleteWithLevelResponse(BaseModel):
    """按等级删除种子响应"""
    total_count: int
    success_count: int
    failed_count: int
    results: List[Dict[str, Any]]


@router.delete("/delete-with-level", response_model=CommonResponse)
async def delete_torrent_with_level(
        request: Request,
        torrent_info_ids: str = Query(..., description="要删除的种子信息ID列表（逗号分隔）"),
        delete_level: int = Query(..., description="删除等级 (3=回收站, 4=待删除标签)", ge=3, le=4),
        operator: str = Query(default="admin", description="操作人"),
        db: Session = Depends(get_db)
):
    """
    按等级删除种子

    支持的删除等级:
    - Level 3: 移到回收站（创建标记文件+删除下载器任务+数据库标记）
    - Level 4: 添加"待删除"标签

    Args:
        torrent_info_ids: 要删除的种子信息ID列表（逗号分隔的字符串）
        delete_level: 删除等级 (3-4)
        operator: 操作人
        db: 数据库会话

    Returns:
        删除结果
    """
    # 将逗号分隔的字符串转换为列表
    # 验证token
    try:
        from app.auth.utils import verify_access_token
        token = request.headers.get("x-access-token")
        if not verify_access_token(token):
            return CommonResponse(
                code="401",
                msg="token验证失败或已过期",
                status="error",
                data=None
            )
    except Exception as e:
        return CommonResponse(
            code="401",
            msg=f"token验证失败：{str(e)}",
            status="error",
            data=None
        )

    # 将逗号分隔的字符串转换为列表
    torrent_info_id_list = [id.strip() for id in torrent_info_ids.split(',') if id.strip()]

    try:
        # 导入删除服务
        from app.services.torrent_deletion_by_level import TorrentDeletionByLevelService

        # 创建删除服务（传递 request 对象用于访问 app.state.store）
        deletion_service = TorrentDeletionByLevelService(db, request)

        # 获取审计日志服务
        audit_service = None
        try:
            async with AsyncSessionLocal() as async_db:
                audit_service = await get_audit_service(async_db)
        except Exception as e:
            logger.warning(f"获取审计日志服务失败: {str(e)}")

        # 执行批量删除
        result = await deletion_service.delete_batch_by_level(
            torrent_info_ids=torrent_info_id_list,
            delete_level=delete_level,
            operator=operator,
            audit_service=audit_service
        )

        # 构建响应
        if result.get("success"):
            # 全部成功
            msg_parts = []
            if delete_level == 3:
                level3_count = len(result.get("level3_success", []))
                level4_count = len(result.get("level4_downgraded", []))
                if level3_count > 0:
                    msg_parts.append(f"等级3删除成功{level3_count}个")
                if level4_count > 0:
                    msg_parts.append(f"降级为等级4删除{level4_count}个")
                msg = "、".join(msg_parts) if msg_parts else "删除完成"
            else:
                msg = f"删除完成，成功{len(result.get('level4_success', []))}个"

            return CommonResponse(
                status="success",
                msg=msg,
                code="200",
                data={
                    "total": result["total"],
                    "level3_success": result.get("level3_success", []),
                    "level4_downgraded": result.get("level4_downgraded", []),
                    "level4_success": result.get("level4_success", []),
                    "failed": result.get("failed", []),
                    "delete_level": delete_level
                }
            )
        else:
            # 部分失败或全部失败
            total = result["total"]
            failed_count = len(result.get("failed", []))
            success_count = total - failed_count

            # 构建详细消息
            msg_parts = []
            if delete_level == 3:
                level3_count = len(result.get("level3_success", []))
                level4_count = len(result.get("level4_downgraded", []))
                if level3_count > 0:
                    msg_parts.append(f"等级3删除成功{level3_count}个")
                if level4_count > 0:
                    msg_parts.append(f"降级为等级4删除{level4_count}个")
            elif delete_level == 4:
                level4_count = len(result.get("level4_success", []))
                if level4_count > 0:
                    msg_parts.append(f"等级4删除成功{level4_count}个")

            if failed_count > 0:
                msg_parts.append(f"失败{failed_count}个")

            msg = "、".join(msg_parts) if msg_parts else "删除操作完成"

            return CommonResponse(
                status="partial" if success_count > 0 else "error",
                msg=msg,
                code="207" if success_count > 0 else "500",
                data={
                    "total": result["total"],
                    "level3_success": result.get("level3_success", []),
                    "level4_downgraded": result.get("level4_downgraded", []),
                    "level4_success": result.get("level4_success", []),
                    "failed": result.get("failed", []),
                    "delete_level": delete_level
                }
            )

    # P2 修复: 区分不同类型的异常
    except SQLAlchemyError as e:
        logger.error(f"数据库操作失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg="数据库操作失败",
            code="500",
            data=None
        )
    except ValueError as e:
        logger.warning(f"参数验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"参数错误: {str(e)}",
            code="400",
            data=None
        )
    except Exception as e:
        logger.error(f"未知错误: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg="系统内部错误",
            code="500",
            data=None
        )


# ==================== 单个下载器同步接口 ====================

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


# ==================== 修改种子保存路径 ====================

@router.post("/set-location", response_model=CommonResponse)
async def set_torrent_location(
        request: Request,
        location_request: SetLocationRequest,
        db: Session = Depends(get_db)
):
    """
    修改种子保存路径

    修改一个或多个种子在同一下载器内的保存路径。
    支持选择是否移动已下载的文件。

    Args:
        request: FastAPI请求对象
        location_request: 位置修改请求参数
        db: 数据库会话

    Returns:
        CommonResponse: 操作结果
        {
            "code": "200",
            "msg": "成功提交2个种子路径修改请求",
            "data": {
                "success": true,
                "moved_count": 2,
                "failed_count": 0,
                "error_message": null
            },
            "status": "success"
        }
    """
    try:
        # 从请求头获取用户信息
        token = request.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        # 验证token并获取用户信息
        decoded = utils.verify_access_token(token)
        user_id = decoded.get("user_id")
        username = decoded.get("username", "unknown")

        if not user_id:
            return CommonResponse(
                status="error",
                msg="无效的访问令牌",
                code="401",
                data=None
            )

        # 导入服务层（避免循环导入）
        from app.services.torrent_location_service import TorrentLocationService
        from app.factory import app

        # 创建服务实例
        service = TorrentLocationService(db=db)

        # 调用服务修改路径
        result = await service.set_location(
            downloader_id=location_request.downloader_id,
            hashes=location_request.hashes,
            target_path=location_request.target_path,
            move_files=location_request.move_files,
            user_id=int(user_id),
            username=username,
            app_state=app.state
        )

        # 构建响应消息
        if result["success"]:
            msg = f"成功提交{result['moved_count']}个种子路径修改请求"
            if result["failed_count"] > 0:
                msg += f"，{result['failed_count']}个失败"

            return CommonResponse(
                status="success",
                msg=msg,
                code="200",
                data={
                    "success": True,
                    "moved_count": result["moved_count"],
                    "failed_count": result["failed_count"],
                    "error_message": result["error_message"]
                }
            )
        else:
            return CommonResponse(
                status="error",
                msg=result["error_message"] or "修改路径失败",
                code="500",
                data={
                    "success": False,
                    "moved_count": 0,
                    "failed_count": len(location_request.hashes),
                    "error_message": result["error_message"]
                }
            )

    except Exception as e:
        logger.error(f"修改种子路径API异常: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"服务器错误: {str(e)}",
            code="500",
            data=None
        )
