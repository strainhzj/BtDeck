# -*- coding: utf-8 -*-
"""
种子文件备份API端点

提供种子文件备份的REST API接口。
所有端点使用 x-access-token 进行身份验证。

@author: btpManager Team
@file: torrent_backup.py
@time: 2026-02-15
"""

import logging
import shutil
import urllib3
import zipfile
from typing import Optional, List
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import io

from app.database import AsyncSessionLocal
from app.api.responseVO import CommonResponse
from app.auth.utils import verify_access_token
from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService
from app.core.path_mapping import PathMappingService
from app.schemas.torrent_backup import (
    TorrentFileBackupCreate,
    TorrentFileBackupResponse,
    TorrentFileBackupListResponse,
    TorrentFileBackupDelete,
    TorrentFileBackupBatchCreate,
    TorrentFileBackupBatchResponse
)
from app.models.torrent_file_backup import TorrentFileBackup
from app.models.setting_templates import DownloaderTypeEnum

# 禁用 urllib3 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 辅助函数 ====================

def get_downloader_from_store(downloader_id: int):
    """
    从应用状态存储中获取下载器配置

    Args:
        downloader_id: 下载器ID

    Returns:
        DownloaderVO: 下载器值对象，如果未找到则返回 None
    """
    from fastapi import FastAPI
    import inspect

    # 获取当前调用栈中的 FastAPI app 实例
    for frame in inspect.stack():
        if frame.frame.f_locals.get('app') and isinstance(frame.frame.f_locals.get('app'), FastAPI):
            app = frame.frame.f_locals['app']
            break
    else:
        # 如果找不到 app，尝试从请求上下文获取
        try:
            from fastapi import Request
            from app.api.endpoints.torrents import router as torrents_router
            # 使用路由器的 app 属性
            if hasattr(torrents_router, 'app'):
                app = torrents_router.app
            else:
                logger.error("无法获取 FastAPI app 实例")
                return None
        except Exception as e:
            logger.error(f"获取 app 实例失败: {e}")
            return None

    # 从 store 获取下载器
    if not hasattr(app.state, 'store'):
        logger.error("app.state 未初始化 store")
        return None

    try:
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )
        return downloader
    except Exception as e:
        logger.error(f"从 store 获取下载器失败: {e}")
        return None


def verify_token(request: Request) -> None:
    """
    验证访问令牌

    Args:
        request: FastAPI请求对象

    Raises:
        HTTPException: 认证失败
    """
    try:
        token = request.headers.get("x-access-token")
        if not verify_access_token(token):
            raise HTTPException(status_code=401, detail="Invalid access token")
    except Exception as e:
        logger.error(f"Token验证失败: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


def backup_to_dict(backup: TorrentFileBackup) -> dict:
    """将TorrentFileBackup对象转换为字典"""
    return backup.to_dict()


# ==================== API端点 ====================

@router.post("/backup", response_model=CommonResponse)
async def create_backup(
    request: Request,
    backup_request: TorrentFileBackupCreate,
    background_tasks: BackgroundTasks
):
    """
    手动触发种子文件备份

    从下载器备份种子文件到项目备份目录。

    Args:
        request: FastAPI请求对象
        backup_request: 备份请求参数
        background_tasks: 后台任务

    Returns:
        CommonResponse: 操作结果
    """
    # 验证token
    verify_token(request)

    result = {
        "success": False,
        "backup": None,
        "message": ""
    }

    try:
        # 获取下载器配置
        downloader = get_downloader_from_store(backup_request.downloader_id)
        if not downloader or downloader.fail_time > 0:
            return CommonResponse(
                status="error",
                msg="下载器不可用",
                code="400"
            )

        # 准备下载器配置
        downloader_config = {
            "host": downloader.host,
            "port": downloader.port,
            "username": downloader.username,
            "password": downloader.password,
            "torrent_save_path": downloader.torrent_save_path
        }

        # 准备路径映射服务
        path_mapping_service = None
        if downloader.path_mapping:
            try:
                path_mapping_service = PathMappingService(downloader.path_mapping)
            except Exception as e:
                logger.warning(f"加载路径映射服务失败: {e}")

        # 初始化管理服务
        async with AsyncSessionLocal() as db:
            manager = TorrentFileBackupManagerService(
                db=db,
                path_mapping_service=path_mapping_service
            )

            # 判断备份方式
            if backup_request.source_file_path:
                # 从路径备份
                result_data = await manager.backup_torrent_from_path(
                    info_hash=backup_request.info_hash,
                    torrent_name=backup_request.torrent_name,
                    source_file_path=backup_request.source_file_path,
                    downloader_id=backup_request.downloader_id,
                    task_name=backup_request.task_name,
                    uploader_id=backup_request.uploader_id
                )
            else:
                # 从下载器备份
                result_data = await manager.backup_torrent_from_downloader(
                    info_hash=backup_request.info_hash,
                    torrent_name=backup_request.torrent_name,
                    downloader_type=downloader.downloader_type,  # 0或1
                    downloader_id=backup_request.downloader_id,
                    save_path=downloader.save_path,
                    downloader_config=downloader_config,
                    task_name=backup_request.task_name,
                    uploader_id=backup_request.uploader_id
                )

            if result_data["success"]:
                result["success"] = True
                result["backup"] = result_data["backup"]
                result["message"] = "备份成功"

                return CommonResponse(
                    status="success",
                    msg="种子文件备份成功",
                    code="200",
                    data={
                        "backup": backup_to_dict(result_data["backup"]),
                        "backup_file_path": result_data["backup_file_path"]
                    }
                )
            else:
                result["message"] = result_data.get("error_message", "备份失败")
                return CommonResponse(
                    status="error",
                    msg=result["message"],
                    code="400"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建备份异常: {e}")
        return CommonResponse(
            status="error",
            msg=f"备份失败: {str(e)}",
            code="500"
        )


@router.get("/backup", response_model=CommonResponse)
async def list_backups(
    request: Request,
    downloader_id: Optional[int] = Query(None, description="下载器ID（可选）"),
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页大小")
):
    """
    获取种子文件备份列表

    支持按下载器筛选和分页查询。

    Args:
        request: FastAPI请求对象
        downloader_id: 下载器ID（可选）
        page: 页码（默认1）
        pageSize: 每页大小（默认20，最大100）

    Returns:
        CommonResponse: 备份列表（分页格式）
    """
    # 验证token
    verify_token(request)

    try:
        async with AsyncSessionLocal() as db:
            manager = TorrentFileBackupManagerService(db=db)

            result_data = await manager.list_backups(
                downloader_id=downloader_id,
                page=page,
                page_size=pageSize
            )

            if result_data["success"]:
                # 转换为响应模型
                backup_list = [
                    backup_to_dict(backup)
                    for backup in result_data["list"]
                ]

                return CommonResponse(
                    status="success",
                    msg="查询成功",
                    code="200",
                    data={
                        "total": result_data["total"],
                        "page": result_data["page"],
                        "pageSize": result_data["pageSize"],
                        "list": backup_list
                    }
                )
            else:
                return CommonResponse(
                    status="error",
                    msg=result_data.get("error_message", "查询失败"),
                    code="400"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"列出备份异常: {e}")
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500"
        )


@router.get("/backup/{info_hash}", response_model=CommonResponse)
async def get_backup(
    request: Request,
    info_hash: str
):
    """
    查询单个种子文件备份

    根据info_hash查询种子文件备份的详细信息。

    Args:
        request: FastAPI请求对象
        info_hash: 种子的info_hash（40位十六进制）

    Returns:
        CommonResponse: 备份详细信息
    """
    # 验证token
    verify_token(request)

    # 验证info_hash格式
    if len(info_hash) != 40:
        return CommonResponse(
            status="error",
            msg="info_hash格式错误（必须为40位字符）",
            code="400"
        )

    try:
        async with AsyncSessionLocal() as db:
            manager = TorrentFileBackupManagerService(db=db)

            result_data = await manager.get_backup_info(info_hash)

            if result_data["success"]:
                return CommonResponse(
                    status="success",
                    msg="查询成功",
                    code="200",
                    data={"backup": backup_to_dict(result_data["backup"])}
                )
            else:
                return CommonResponse(
                    status="error",
                    msg=result_data.get("error_message", "查询失败"),
                    code="404"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取备份信息异常: {e}")
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500"
        )


@router.delete("/backup/{info_hash}", response_model=CommonResponse)
async def delete_backup(
    request: Request,
    info_hash: str,
    deletePhysicalFile: bool = Query(False, description="是否删除物理文件")
):
    """
    删除种子文件备份

    支持逻辑删除和物理删除。

    Args:
        request: FastAPI请求对象
        info_hash: 种子的info_hash（40位十六进制）
        deletePhysicalFile: 是否同时删除物理文件

    Returns:
        CommonResponse: 操作结果
    """
    # 验证token
    verify_token(request)

    # 验证info_hash格式
    if len(info_hash) != 40:
        return CommonResponse(
            status="error",
            msg="info_hash格式错误（必须为40位字符）",
            code="400"
        )

    try:
        async with AsyncSessionLocal() as db:
            manager = TorrentFileBackupManagerService(db=db)

            result_data = await manager.delete_backup(
                info_hash=info_hash,
                delete_physical_file=deletePhysicalFile
            )

            if result_data["success"]:
                message = "删除成功"
                if result_data["deleted_file"]:
                    message += "（已删除物理文件）"

                return CommonResponse(
                    status="success",
                    msg=message,
                    code="200"
                )
            else:
                return CommonResponse(
                    status="error",
                    msg=result_data.get("error_message", "删除失败"),
                    code="400"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除备份异常: {e}")
        return CommonResponse(
            status="error",
            msg=f"删除失败: {str(e)}",
            code="500"
        )


@router.post("/backup/batch", response_model=CommonResponse)
async def batch_create_backups(
    request: Request,
    batch_request: TorrentFileBackupBatchCreate,
    background_tasks: BackgroundTasks
):
    """
    批量备份种子文件

    支持批量操作多个种子文件。

    Args:
        request: FastAPI请求对象
        batch_request: 批量备份请求
        background_tasks: 后台任务

    Returns:
        CommonResponse: 批量操作结果
    """
    # 验证token
    verify_token(request)

    try:
        # 准备备份数据
        backup_requests = []
        for req in batch_request.backup_requests:
            backup_requests.append({
                "info_hash": req.info_hash,
                "torrent_name": req.torrent_name,
                "downloader_id": req.downloader_id,
                "source_file_path": req.source_file_path,
                "task_name": req.task_name,
                "uploader_id": req.uploader_id
            })

        async with AsyncSessionLocal() as db:
            manager = TorrentFileBackupManagerService(db=db)

            result_data = await manager.batch_backup(backup_requests)

            # 准备响应数据
            success_items = [
                backup_to_dict(backup)
                for backup in result_data["success_items"]
            ]

            return CommonResponse(
                status="success",
                msg=f"批量备份完成：成功{result_data['success_count']}个，失败{result_data['failed_count']}个",
                code="200",
                data={
                    "total": result_data["total"],
                    "success_count": result_data["success_count"],
                    "failed_count": result_data["failed_count"],
                    "success_items": success_items,
                    "failed_items": result_data["failed_items"]
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量备份异常: {e}")
        return CommonResponse(
            status="error",
            msg=f"批量备份失败: {str(e)}",
            code="500"
        )


@router.get("/backup/{info_hash}/validate", response_model=CommonResponse)
async def validate_backup(
    request: Request,
    info_hash: str
):
    """
    验证种子文件备份完整性

    检查种子文件是否存在、大小是否正常、文件是否可读。

    Args:
        request: FastAPI请求对象
        info_hash: 种子的info_hash（40位十六进制）

    Returns:
        CommonResponse: 验证结果
    """
    # 验证token
    verify_token(request)

    # 验证info_hash格式
    if len(info_hash) != 40:
        return CommonResponse(
            status="error",
            msg="info_hash格式错误（必须为40位字符）",
            code="400"
        )

    try:
        async with AsyncSessionLocal() as db:
            manager = TorrentFileBackupManagerService(db=db)

            result_data = await manager.validate_backup_file(info_hash)

            if result_data["success"]:
                message = "文件验证通过"
                if not result_data["is_valid"]:
                    message = result_data.get("error_message", "文件验证失败")

                return CommonResponse(
                    status="success" if result_data["is_valid"] else "error",
                    msg=message,
                    code="200",
                    data={
                        "is_valid": result_data["is_valid"],
                        "file_exists": result_data["file_exists"],
                        "file_size": result_data["file_size"]
                    }
                )
            else:
                return CommonResponse(
                    status="error",
                    msg=result_data.get("error_message", "验证失败"),
                    code="400"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证备份文件异常: {e}")
        return CommonResponse(
            status="error",
            msg=f"验证失败: {str(e)}",
            code="500"
        )


@router.post("/backup/deduplicate", response_model=CommonResponse)
async def deduplicate_backups(request: Request):
    """
    去重种子文件备份

    按照info_hash去重，保留最新的备份记录（基于created_at字段）。
    旧备份记录将被逻辑删除（is_deleted=1）。

    Args:
        request: FastAPI请求对象

    Returns:
        CommonResponse: 去重结果
    """
    # 验证token
    verify_token(request)

    try:
        async with AsyncSessionLocal() as db:
            # 查找重复的备份记录（按info_hash分组）
            from sqlalchemy import select, and_
            from app.models.torrent_file_backup import TorrentFileBackup

            # 查询所有未删除的备份
            stmt = select(TorrentFileBackup).where(
                TorrentFileBackup.is_deleted == 0
            ).order_by(TorrentFileBackup.created_at.desc())

            result = await db.execute(stmt)
            all_backups = result.scalars().all()

            # 按info_hash分组
            from collections import defaultdict
            backup_groups = defaultdict(list)
            for backup in all_backups:
                backup_groups[backup.info_hash].append(backup)

            # 找出重复的并保留最新的
            deleted_count = 0
            duplicates_count = 0

            for info_hash, backups in backup_groups.items():
                if len(backups) > 1:
                    duplicates_count += 1
                    # 保留第一个（最新的），删除其余的
                    for backup in backups[1:]:
                        backup.is_deleted = 1
                        backup.deleted_at = datetime.now()
                        deleted_count += 1

            await db.commit()

            message = f"去重完成：发现{duplicates_count}个重复项，删除{deleted_count}条旧记录"
            return CommonResponse(
                status="success",
                msg=message,
                code="200",
                data={
                    "duplicates_count": duplicates_count,
                    "deleted_count": deleted_count
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"去重异常: {e}")
        return CommonResponse(
            status="error",
            msg=f"去重失败: {str(e)}",
            code="500"
        )


@router.get("/backup/export")
async def export_backups(
    request: Request,
    info_hashes: str = Query(..., description="要导出的info_hash列表，逗号分隔")
):
    """
    批量导出种子文件

    将选中的种子文件打包成ZIP文件下载，文件名按任务名称重命名。

    Args:
        request: FastAPI请求对象
        info_hashes: 要导出的info_hash列表（逗号分隔）

    Returns:
        StreamingResponse: ZIP文件流
    """
    # 验证token
    verify_token(request)

    try:
        # 解析info_hash列表
        hash_list = [h.strip() for h in info_hashes.split(',') if h.strip()]

        if not hash_list:
            raise HTTPException(status_code=400, detail="未指定要导出的种子文件")

        async with AsyncSessionLocal() as db:
            manager = TorrentFileBackupManagerService(db=db)

            # 查询备份记录
            from sqlalchemy import select, and_
            from app.models.torrent_file_backup import TorrentFileBackup

            stmt = select(TorrentFileBackup).where(
                and_(
                    TorrentFileBackup.info_hash.in_(hash_list),
                    TorrentFileBackup.is_deleted == 0
                )
            )
            result = await db.execute(stmt)
            backups = result.scalars().all()

            if not backups:
                raise HTTPException(status_code=404, detail="未找到备份记录")

            # 创建内存中的ZIP文件
            zip_buffer = io.BytesIO()
            failed_items = []

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for backup in backups:
                    try:
                        # 获取种子文件路径
                        file_path = Path(backup.file_path)

                        if not file_path.exists():
                            logger.warning(f"种子文件不存在: {file_path}")
                            failed_items.append({
                                "info_hash": backup.info_hash,
                                "reason": "文件不存在"
                            })
                            continue

                        # 确定文件名：优先使用任务名称，否则使用info_hash
                        if backup.task_name:
                            # 使用任务名称，替换特殊字符
                            safe_name = backup.task_name.replace('/', '_').replace('\\', '_')
                            filename = f"{safe_name}.torrent"
                        else:
                            filename = f"{backup.info_hash}.torrent"

                        # 添加到ZIP
                        zip_file.write(file_path, filename)

                    except Exception as e:
                        logger.error(f"添加文件到ZIP失败: {backup.info_hash}, {e}")
                        failed_items.append({
                            "info_hash": backup.info_hash,
                            "reason": str(e)
                        })

            # 准备ZIP文件
            zip_buffer.seek(0)
            zip_bytes = zip_buffer.getvalue()

            # 生成ZIP文件名（带时间戳）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"torrent_backup_{timestamp}.zip"

            # 返回ZIP文件（添加Content-Disposition响应头，确保浏览器下载）
            # 使用 RFC 5987 标准编码文件名，支持中文等非ASCII字符
            encoded_zip_filename = quote(zip_filename.encode('utf-8'))

            return StreamingResponse(
                io.BytesIO(zip_bytes),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_zip_filename}"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出异常: {e}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/backup/import")
async def import_backups(
    request: Request,
    downloader_id: int = Query(..., description="目标下载器ID"),
    files: List[UploadFile] = File(..., description="种子文件列表")
):
    """
    批量导入种子文件

    上传多个种子文件，并添加到指定下载器。
    添加种子的逻辑交给SDK处理。

    Args:
        request: FastAPI请求对象
        downloader_id: 目标下载器ID
        files: 种子文件列表

    Returns:
        CommonResponse: 导入结果
    """
    # 验证token
    verify_token(request)

    # 获取下载器配置
    downloader = get_downloader_from_store(downloader_id)
    if not downloader or downloader.fail_time > 0:
        return CommonResponse(
            status="error",
            msg="下载器不可用",
            code="400"
        )

    # 准备下载器配置
    downloader_config = {
        "host": downloader.host,
        "port": downloader.port,
        "username": downloader.username,
        "password": downloader.password,
        "torrent_save_path": downloader.torrent_save_path
    }

    success_count = 0
    failed_count = 0
    failed_items = []

    try:
        async with AsyncSessionLocal() as db:
            manager = TorrentFileBackupManagerService(db=db)

            # 临时保存目录
            temp_dir = Path("data/temp_imports")
            temp_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                try:
                    # 保存临时文件
                    temp_file_path = temp_dir / file.filename
                    with open(temp_file_path, "wb") as buffer:
                        shutil.copyfileobj(file.file, buffer)

                    # 读取种子文件内容
                    with open(temp_file_path, "rb") as f:
                        torrent_content = f.read()

                    # 提取info_hash和torrent_name
                    import bencodepy
                    torrent_data = bencodepy.decode(torrent_content)
                    info_hash = torrent_data[b'info'].get(b'infohash', b'').hex()

                    if not info_hash:
                        # 计算info_hash
                        import hashlib
                        info_bytes = bencodepy.encode(torrent_data[b'info'])
                        info_hash = hashlib.sha1(info_bytes).hexdigest()

                    # 获取种子名称
                    torrent_name = torrent_data[b'info'].get(b'name', b'').decode('utf-8', errors='ignore')

                    # 添加到下载器（使用SDK）
                    normalized_type = DownloaderTypeEnum.normalize(downloader.downloader_type)
                    if normalized_type == DownloaderTypeEnum.QBITTORRENT:  # qBittorrent
                        from app.services.downloader_adapters.qbittorrent_adapter import QBittorrentAdapter
                        adapter = QBittorrentAdapter(downloader_config)
                        adapter.add_torrent_file(
                            torrent_file=torrent_content,
                            save_path=downloader.save_path
                        )
                    elif normalized_type == DownloaderTypeEnum.TRANSMISSION:  # Transmission
                        from app.services.downloader_adapters.transmission_adapter import TransmissionAdapter
                        adapter = TransmissionAdapter(downloader_config)
                        adapter.add_torrent_file(
                            torrent_file=torrent_content,
                            save_path=downloader.save_path
                        )

                    # 备份种子文件
                    result_data = await manager.backup_torrent_from_path(
                        info_hash=info_hash,
                        torrent_name=torrent_name,
                        source_file_path=str(temp_file_path),
                        downloader_id=downloader_id,
                        task_name=torrent_name,
                        uploader_id=None
                    )

                    if result_data["success"]:
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_items.append({
                            "filename": file.filename,
                            "reason": result_data.get("error_message", "未知错误")
                        })

                    # 清理临时文件
                    temp_file_path.unlink(missing_ok=True)

                except Exception as e:
                    logger.error(f"导入文件失败: {file.filename}, {e}")
                    failed_count += 1
                    failed_items.append({
                        "filename": file.filename,
                        "reason": str(e)
                    })

            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)

            message = f"导入完成：成功{success_count}个，失败{failed_count}个"
            return CommonResponse(
                status="success",
                msg=message,
                code="200",
                data={
                    "total": len(files),
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_items": failed_items
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量导入异常: {e}")
        return CommonResponse(
            status="error",
            msg=f"导入失败: {str(e)}",
            code="500"
        )


@router.get("/backup/download/{info_hash}")
async def download_backup(
    request: Request,
    info_hash: str
):
    """
    下载单个种子文件

    下载指定info_hash的种子文件。

    Args:
        request: FastAPI请求对象
        info_hash: 种子的info_hash（40位十六进制）

    Returns:
        FileResponse: 种子文件
    """
    # 验证token
    verify_token(request)

    # 验证info_hash格式
    if len(info_hash) != 40:
        raise HTTPException(status_code=400, detail="info_hash格式错误（必须为40位字符）")

    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from app.models.torrent_file_backup import TorrentFileBackup

            # 查询备份记录
            stmt = select(TorrentFileBackup).where(
                TorrentFileBackup.info_hash == info_hash
            )
            result = await db.execute(stmt)
            backup = result.scalar_one_or_none()

            if not backup:
                raise HTTPException(status_code=404, detail="备份记录不存在")

            # 获取文件路径
            file_path = Path(backup.file_path)

            if not file_path.exists():
                raise HTTPException(status_code=404, detail="种子文件不存在")

            # 确定下载文件名
            if backup.task_name:
                safe_name = backup.task_name.replace('/', '_').replace('\\', '_')
                filename = f"{safe_name}.torrent"
            else:
                filename = f"{info_hash}.torrent"

            # 返回文件（添加Content-Disposition响应头，确保浏览器下载而非预览）
            # 使用 RFC 5987 标准编码文件名，支持中文等非ASCII字符
            encoded_filename = quote(filename.encode('utf-8'))

            return FileResponse(
                path=str(file_path),
                filename=filename,
                media_type="application/x-bittorrent",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载种子文件异常: {e}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")
