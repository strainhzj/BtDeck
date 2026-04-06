import asyncio
import hashlib
import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

import bencodepy
import urllib3
from fastapi import APIRouter, Depends, Request, Query, UploadFile, File, BackgroundTasks
from fastapi import Form, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.database import get_db, AsyncSessionLocal
from app.auth import utils
from app.auth.models import User
from app.downloader.models import BtDownloaders
from app.downloader.request import DownloaderCheckVO
from app.downloader.responseVO import DownloaderVO
from app.torrents.models import TorrentInfo as torrentInfoModel, TorrentInfo
from app.torrents.models import TrackerInfo as trackerInfoModel, TrackerInfo
from app.torrents.responseVO import TorrentInfoVO
from qbittorrentapi import Client as qbClient
from qbittorrentapi import exceptions as qbExceptions
from transmission_rpc import Client as trClient, TransmissionError
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.core.background_task_manager import task_manager, TaskStatus
from app.models.setting_templates import DownloaderTypeEnum
from app.services.audit_service import extract_audit_info_from_request, get_audit_service

# Import from new split modules
from app.api.endpoints.torrent_helpers import (
    convert_to_vo,
    convert_to_vo_with_trackers,
    calculate_info_hash,
    get_transmission_torrent_info,
    create_qbittorrent_torrent_record,
    create_transmission_torrent_record,
    get_torrent_infos,
    get_torrent_infos_legacy,
    parse_size_string,
    parse_datetime_string,
    custom_serializer,
    _safe_write_audit_log
)
from app.api.endpoints.torrent_sync import (
    qb_add_torrents,
    tr_add_torrents
)
from app.services.torrent_crud_service import get_torrent_info
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult

logger = logging.getLogger(__name__)
router = APIRouter()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==================== 种子操作请求模型 ====================

class TorrentOperationRequest(BaseModel):
    """种子操作请求（统一基类）"""
    hashes: List[str] = Field(..., description="种子hash列表", min_items=1, max_items=100)
    operator: Optional[str] = Field(default="admin", description="操作人")


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
                    qb_add_torrents(db, [downloader], app=req.app)
                    synced_count += 1
                    logger.info(f"成功同步qBittorrent下载器: {downloader.nickname}")
                elif downloader.is_transmission:
                    tr_add_torrents(db, [downloader], app=req.app)
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

    # 清理临时文件
    if tmp_file_path and os.path.exists(tmp_file_path):
        try:
            os.unlink(tmp_file_path)
        except OSError:
            pass

    return result


@router.post("/add-batch", response_model=CommonResponse)
async def create_torrents_batch(
        request: Request,
        torrent_files: List[UploadFile] = File(..., description="种子文件列表（最多10个）"),
        downloader_id: Optional[str] = Form(..., description="所属下载器主键"),
        save_path: Optional[str | None] = Form(..., description="种子文件保存路径"),
        tags: Optional[str | None] = Form("", description="标签"),
        category: Optional[str | None] = Form("", description="分类"),
        paused: Optional[bool] = Form(False, description="是否暂停,0代表false，1代表true"),
        skip_hash_check: Optional[bool | None] = Form(False, description="是否跳过校验,0代表false，1代表true"),
        is_sequential_download: Optional[bool | None] = Form(False, description="是否按顺序下载,0代表false，1代表true"),
        is_first_last_piece_priority: Optional[bool | None] = Form(False, description="是否先下载首尾文件块,0代表false，1代表true"),
        upload_limit: Optional[str | int | None] = Form(False, description="上传速度，单位bytes/second"),
        download_limit: Optional[str | int | None] = Form(False, description="下载速度，单位bytes/second"),
        db: Session = Depends(get_db)
):
    """
    批量创建种子信息（支持多个种子文件）

    优化说明：
    - 一次性接收多个种子文件，减少HTTP请求次数
    - 批量处理，提升性能（10个文件从2秒降低到300ms）
    - 返回详细的批量处理结果
    """
    # 验证文件数量限制
    if len(torrent_files) > 10:
        return CommonResponse(
            status="error",
            msg="最多只能上传10个种子文件",
            code="400",
            data=None
        )

    # ========== 从 app.state.store 获取缓存的下载器（强制规范） ==========
    app = request.app

    if not hasattr(app.state, 'store'):
        return CommonResponse(
            status="error",
            msg="下载器缓存未初始化",
            code="500",
            data=None
        )

    # 从缓存获取下载器
    cached_downloaders = await app.state.store.get_snapshot()
    downloader_vo = next(
        (d for d in cached_downloaders if d.downloader_id == downloader_id),
        None
    )

    if not downloader_vo:
        return CommonResponse(
            status="error",
            msg=f"下载器不在缓存中 [downloader_id={downloader_id}]",
            code="404",
            data=None
        )

    if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
        return CommonResponse(
            status="error",
            msg=f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]",
            code="503",
            data=None
        )

    client = downloader_vo.client
    if not client:
        return CommonResponse(
            status="error",
            msg=f"下载器客户端连接不存在 [downloader_id={downloader_id}]",
            code="500",
            data=None
        )

    downloader = downloader_vo

    # ========== 批量处理种子文件 ==========
    results = []
    success_count = 0
    failed_count = 0

    for torrent_file in torrent_files:
        file_name = torrent_file.filename
        result_item = {
            "file_name": file_name,
            "success": False,
            "info_id": None,
            "error": None
        }

        try:
            # 保存文件到临时位置
            file_content = await torrent_file.read()

            def write_temp_file(content):
                """安全地写入临时文件"""
                try:
                    tmp_file = tempfile.NamedTemporaryFile(
                        mode='wb',
                        delete=False,
                        suffix=".torrent"
                    )
                    tmp_file.write(content)
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())
                    tmp_file.close()
                    return tmp_file.name
                except Exception as e:
                    logging.error(f"写入临时文件失败: {str(e)}")
                    if 'tmp_file' in locals():
                        try:
                            tmp_file.close()
                        except OSError:
                            pass
                    raise

            tmp_file_path = await asyncio.to_thread(write_temp_file, file_content)

            try:
                # 计算文件哈希
                info_hash = await calculate_info_hash(tmp_file_path)

                # 根据下载器类型添加种子
                if downloader.downloader_type == 1:  # Transmission
                    tr_client = client
                    add_args = {
                        "paused": paused,
                        "download_dir": save_path if save_path else None
                    }

                    def read_file_data(file_path):
                        with open(file_path, "rb") as f:
                            return f.read()

                    file_data = await asyncio.to_thread(read_file_data, tmp_file_path)
                    from io import BytesIO
                    tr_client.add_torrent(BytesIO(file_data), **add_args)

                    # 等待Transmission处理种子（最多30秒）
                    tr_torrent = None
                    max_retries = 30
                    retry_count = 0
                    while tr_torrent is None and retry_count < max_retries:
                        await asyncio.sleep(1)
                        tr_torrent = await get_transmission_torrent_info(tr_client, info_hash)
                        retry_count += 1

                    if not tr_torrent:
                        raise Exception("获取种子信息超时")

                    # 检查数据库中是否已存在该种子
                    existing_torrent = db.query(TorrentInfo.info_id).filter(
                        TorrentInfo.hash == info_hash
                    ).filter(
                        TorrentInfo.dr == 0
                    ).filter(
                        TorrentInfo.downloader_id == downloader_id
                    ).first()

                    if existing_torrent is None:
                        db_torrent = create_transmission_torrent_record(downloader, downloader_id, tr_torrent)
                        db.add(db_torrent)
                        db.commit()
                        db.refresh(db_torrent)
                    else:
                        db_torrent = existing_torrent

                elif downloader.downloader_type == 0:  # qBittorrent
                    qb_client = client

                    def read_file_data_qb(file_path):
                        with open(file_path, "rb") as f:
                            return f.read()

                    file_data = await asyncio.to_thread(read_file_data_qb, tmp_file_path)
                    from io import BytesIO
                    qb_client.torrents_add(
                        torrent_files=BytesIO(file_data),
                        save_path=save_path,
                        is_stopped=paused,
                        tags=tags,
                        category=category,
                        is_skip_checking=skip_hash_check,
                        is_sequential_download=is_sequential_download,
                        is_first_last_piece_priority=is_first_last_piece_priority,
                        upload_limit=upload_limit,
                        download_limit=download_limit
                    )

                    # 从qBittorrent获取种子信息（最多30秒）
                    torrents = None
                    max_retries = 30
                    retry_count = 0
                    while (torrents is None or len(torrents) == 0) and retry_count < max_retries:
                        await asyncio.sleep(1)
                        torrents = qb_client.torrents_info(torrent_hashes=info_hash)
                        retry_count += 1

                    if not torrents or len(torrents) == 0:
                        raise Exception("种子添加到qBittorrent后无法获取信息")

                    qb_torrent = torrents[0]

                    # 检查数据库中是否已存在该种子
                    existing_torrent = db.query(TorrentInfo.info_id).filter(
                        TorrentInfo.hash == info_hash
                    ).filter(
                        TorrentInfo.dr == 0
                    ).filter(
                        TorrentInfo.downloader_id == downloader_id
                    ).first()

                    if existing_torrent is None:
                        db_torrent = create_qbittorrent_torrent_record(downloader, downloader_id, qb_torrent, tmp_file_path)
                        db.add(db_torrent)
                        db.commit()
                        db.refresh(db_torrent)
                    else:
                        db_torrent = existing_torrent

                # 成功添加
                result_item["success"] = True
                result_item["info_id"] = db_torrent.info_id
                success_count += 1

                # 异步记录审计日志
                async def write_audit_log():
                    try:
                        async with AsyncSessionLocal() as async_db:
                            audit_service = await get_audit_service(async_db)
                            await audit_service.log_operation(
                                operation_type=AuditOperationType.ADD,
                                operator="admin",
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
                        logging.error(f"记录审计日志失败: {str(audit_error)}")

                asyncio.create_task(write_audit_log())

            except Exception as e:
                # 处理失败
                result_item["error"] = str(e)
                failed_count += 1

            finally:
                # 清理临时文件
                if os.path.exists(tmp_file_path):
                    try:
                        os.unlink(tmp_file_path)
                    except Exception as cleanup_error:
                        logging.debug(f"清理临时文件失败: {cleanup_error}")

        except Exception as e:
            # 文件读取或处理失败
            result_item["error"] = str(e)
            failed_count += 1

        results.append(result_item)

    # ========== 返回批量处理结果 ==========
    total_count = len(torrent_files)
    if success_count == total_count:
        msg = f"成功添加 {success_count} 个种子"
        status = "success"
        code = "200"
    elif success_count == 0:
        msg = "种子添加失败"
        status = "error"
        code = "500"
    else:
        msg = f"部分成功：成功 {success_count} 个，失败 {failed_count} 个"
        status = "partial_success"
        code = "207"  # Multi-Status

    return CommonResponse(
        status=status,
        msg=msg,
        code=code,
        data={
            "total": total_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }
    )


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
        downloader_id: Optional[str] = Query(None, description="所属下载器主键（支持多选，逗号分隔）", examples={"default": ""}),
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
                                      description="种子状态筛选(支持多选，逗号分隔；error状态满足status='error'或has_tracker_error=True之一即可)"),
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
