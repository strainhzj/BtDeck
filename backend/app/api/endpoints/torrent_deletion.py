import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, Request, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth.models import User
from app.auth.dependencies import get_current_user
from app.database import get_db, AsyncSessionLocal
from app.downloader.models import BtDownloaders
from app.models.setting_templates import DownloaderTypeEnum
from app.services.audit_service import get_audit_service, extract_audit_info_from_request
from app.services.torrent_deletion_service import (
    TorrentDeletionService,
    DeleteRequest,
    DeleteOption,
    SafetyCheckLevel
)
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.torrents.models import TorrentInfo as torrentInfoModel, TorrentInfo
from app.api.endpoints.torrent_helpers import _safe_write_audit_log, _write_audit_log_async

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 辅助函数 ====================

async def _register_downloader_adapters(
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

    # 获取缓存的下载器列表（使用异步方法，避免在异步上下文中调用同步方法）
    cached_downloaders = await app.state.store.get_snapshot()

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


# ==================== 单个种子删除接口 ====================

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

            # 创建删除请求（在 async with 块内，确保 async_db_session 有效）
            delete_request = DeleteRequest(
                torrent_info_ids=[info_id] if info_id else [],
                delete_option=delete_option,
                safety_check_level=safety_check_level,
                force_delete=True,  # 强制删除，因为用户已确认
                reason=f"用户手动删除，id_recycle={id_recycle}"
            )

            # 执行删除（在 async with 块内，确保 async_db_session 有效）
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

            # 修复：注册下载器适配器（传入app对象以访问缓存）
            await _register_downloader_adapters(
                deletion_service=deletion_service,
                torrent_info_ids=request.torrent_info_ids,
                db=db,
                app=http_request.app
            )

            # 创建预览请求（dry-run模式，在 async with 块内确保 async_db_session 有效）
            preview_request = DeleteRequest(
                torrent_info_ids=request.torrent_info_ids,
                delete_option=DeleteOption.DRY_RUN,
                safety_check_level=safety_check_level,
                force_delete=False
            )

            # 执行预览（在 async with 块内确保 async_db_session 有效）
            result = await deletion_service.delete_torrents(preview_request)

            # 组织预览响应数据（在 async with 块内，确保 async_db_session 有效）
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

            # 修复：注册下载器适配器（传入app对象以访问缓存）
            await _register_downloader_adapters(
                deletion_service=deletion_service,
                torrent_info_ids=request.torrent_info_ids,
                db=db,
                app=http_request.app
            )

            # 创建删除请求（在 async with 块内，确保 async_db_session 有效）
            delete_request = DeleteRequest(
                torrent_info_ids=request.torrent_info_ids,
                delete_option=delete_option,
                safety_check_level=safety_check_level,
                force_delete=request.force_delete,
                reason=request.reason
            )

            # 执行删除（在 async with 块内，确保 async_db_session 有效）
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
    from app.torrents.models import TorrentInfo

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


# ==================== 删除操作审计日志 ====================

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
        delete_level: int = Query(..., description="删除等级 (1=完全删除, 2=删除任务保留数据, 3=回收站, 4=待删除标签)",
                                  ge=1, le=4),
        operator: str = Query(default="admin", description="操作人"),
        db: Session = Depends(get_db)
):
    """
    按等级删除种子（同步接口，主要用于单个种子删除）

    支持的删除等级:
    - Level 1: 删除任务和数据（原有功能）
    - Level 2: 删除任务保留数据（原有功能）
    - Level 3: 移到回收站（创建标记文件+删除下载器任务+数据库标记）
    - Level 4: 添加"待删除"标签

    Args:
        torrent_info_ids: 要删除的种子信息ID列表（逗号分隔的字符串）
        delete_level: 删除等级 (1-4)
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
            if delete_level == 1:
                msg = f"等级1删除完成，成功{len(result.get('level1_success', []))}个"
            elif delete_level == 2:
                msg = f"等级2删除完成，成功{len(result.get('level2_success', []))}个"
            elif delete_level == 3:
                level3_count = len(result.get("level3_success", []))
                level4_count = len(result.get("level4_downgraded", []))
                if level3_count > 0:
                    msg_parts.append(f"等级3删除成功{level3_count}个")
                if level4_count > 0:
                    msg_parts.append(f"降级为等级4删除{level4_count}个")
                msg = "、".join(msg_parts) if msg_parts else "删除完成"
            else:  # delete_level == 4
                msg = f"等级4删除完成，成功{len(result.get('level4_success', []))}个"

            return CommonResponse(
                status="success",
                msg=msg,
                code="200",
                data={
                    "total": result["total"],
                    "level1_success": result.get("level1_success", []),
                    "level2_success": result.get("level2_success", []),
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


# ==================== 异步批量删除接口 ====================

class BatchDeleteRequest(BaseModel):
    """批量删除请求"""
    torrent_info_ids: List[str] = Field(..., description="要删除的种子ID列表")
    delete_level: int = Field(..., ge=1, le=4, description="删除等级 (1-4)")
    operator: str = Field(default="admin", description="操作人")


@router.post("/delete-batch-async", response_model=CommonResponse)
async def delete_batch_async(
        request: Request,
        delete_request: BatchDeleteRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    异步批量删除种子（提交任务）

    支持的删除等级:
    - Level 1: 删除任务和数据
    - Level 2: 删除任务保留数据
    - Level 3: 移到回收站
    - Level 4: 添加"待删除"标签

    Args:
        delete_request: 删除请求参数
        current_user: 当前登录用户
        db: 数据库会话

    Returns:
        任务ID
    """
    try:
        from app.database import SessionLocal
        from app.services.deletion_task_manager import get_deletion_task_manager, TaskStatus
        from app.services.async_deletion_executor import AsyncDeletionExecutor

        # 获取任务管理器
        task_manager = get_deletion_task_manager()

        # 创建任务
        task_id = await task_manager.create_task(
            torrent_info_ids=delete_request.torrent_info_ids,
            delete_level=delete_request.delete_level,
            operator=delete_request.operator
        )

        # 创建执行器并启动异步任务
        executor = AsyncDeletionExecutor(db_session_factory=SessionLocal, request=request)

        # 在后台执行删除任务（不等待完成）
        asyncio.create_task(
            executor.execute_deletion_task(
                task_id=task_id,
                torrent_info_ids=delete_request.torrent_info_ids,
                delete_level=delete_request.delete_level,
                operator=delete_request.operator,
                request=request
            )
        )

        logger.info(
            f"提交批量删除任务成功: task_id={task_id}, "
            f"用户={current_user.username}, "
            f"种子数量={len(delete_request.torrent_info_ids)}, "
            f"删除等级={delete_request.delete_level}"
        )

        return CommonResponse(
            status="success",
            msg="批量删除任务已提交，正在后台执行",
            code="200",
            data={
                "task_id": task_id,
                "total_count": len(delete_request.torrent_info_ids),
                "delete_level": delete_request.delete_level
            }
        )

    except Exception as e:
        logger.error(f"提交批量删除任务失败: {e}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"提交任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/delete-batch-status/{task_id}", response_model=CommonResponse)
async def get_batch_delete_status(
        task_id: str,
        current_user: User = Depends(get_current_user)
):
    """
    查询批量删除任务状态

    Args:
        task_id: 任务ID
        current_user: 当前登录用户

    Returns:
        任务状态信息
    """
    try:
        from app.services.deletion_task_manager import get_deletion_task_manager, TaskStatus

        # 获取任务管理器
        task_manager = get_deletion_task_manager()

        # 查询任务状态
        task = await task_manager.get_task(task_id)

        if not task:
            return CommonResponse(
                status="error",
                msg=f"任务不存在: {task_id}",
                code="404",
                data=None
            )

        # 构建响应数据
        data = {
            "task_id": task.task_id,
            "status": task.status.value,
            "total_count": task.total_count,
            "success_count": task.success_count,
            "failed_count": task.failed_count,
            "error_message": task.error_message,
            "created_time": task.created_at.isoformat() if task.created_at else None,
            "started_time": task.started_at.isoformat() if task.started_at else None,
            "completed_time": task.completed_at.isoformat() if task.completed_at else None,
            "results": task.results,
            "failed_items": task.failed_items
        }

        # 根据状态返回不同消息
        if task.status == TaskStatus.PENDING:
            msg = "任务待处理"
        elif task.status == TaskStatus.RUNNING:
            progress = task.success_count + task.failed_count
            msg = f"任务执行中... ({progress}/{task.total_count})"
        elif task.status == TaskStatus.COMPLETED:
            msg = f"任务完成，成功{task.success_count}个"
        elif task.status == TaskStatus.PARTIAL:
            msg = f"任务部分完成，成功{task.success_count}个，失败{task.failed_count}个"
        elif task.status == TaskStatus.FAILED:
            msg = f"任务失败：{task.error_message}"
        else:
            msg = "未知状态"

        return CommonResponse(
            status="success",
            msg=msg,
            code="200",
            data=data
        )

    except Exception as e:
        logger.error(f"查询任务状态失败: {e}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )
