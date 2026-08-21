# -*- coding: utf-8 -*-
"""
种子转移API端点

提供种子转移的REST API接口。
所有端点使用 x-access-token 进行身份验证。

@author: btpManager Team
@file: seed_transfer.py
@time: 2026-02-15
"""

import logging
from typing import Optional

import urllib3
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request

from app.database import AsyncSessionLocal
from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user
from app.services.seed_transfer_service import SeedTransferService
from app.schemas.seed_transfer import (
    SeedTransferRequest,
    SeedTransferBatchRequest,
)
from app.services.audit_service import AuditLogService, extract_audit_info_from_request
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult

# 注意：禁止在此处顶层 `from app.factory import app`。
# seed_transfer 由 app.api.api 在路由装配时导入；顶层 factory import 会形成
# 循环依赖：app.api.api(半成品，无 api_router) → app.factory →
# configure_routes_and_static 命中早退 → 全局 app 无业务路由。
# 历史 bug：tests/api/test_tag_aggregation_api.py 全量运行时 16 个用例全 404。
# 改为函数内 lazy import，与 downloader.py / torrent_location.py 的既有模式一致。

# 禁用 urllib3 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _log_transfer_audit(
    db,
    username: str,
    info_hash: str,
    source_downloader_id: str,
    target_downloader_id: str,
    target_path: str,
    transfer_status: str,
    error_message: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    torrent_name: Optional[str] = None,
    source_downloader_name: Optional[str] = None,
):
    """转移操作写入 torrent_audit_log（操作日志页面可见）。

    best-effort：审计失败仅记 warning，不阻断转移响应。
    torrent_name/downloader_name 放入 operation_detail 后由
    AuditLogService 自动提取到冗余列（列表页展示 + 种子名称搜索）；
    下载器口径取来源下载器（downloader_id/downloader_name 同源，
    目标下载器信息保留在 detail 中）。
    """
    try:
        audit_service = AuditLogService(db)
        await audit_service.log_operation(
            operation_type=AuditOperationType.TRANSFER,
            operator=username,
            operation_detail={
                "info_hash": info_hash,
                "source_downloader_id": source_downloader_id,
                "target_downloader_id": target_downloader_id,
                "target_path": target_path,
                "torrent_name": torrent_name or "",
                "downloader_name": source_downloader_name or "",
            },
            operation_result=(
                AuditOperationResult.SUCCESS
                if transfer_status in ("success", "partial")
                else AuditOperationResult.FAILED
            ),
            error_message=error_message,
            downloader_id=str(source_downloader_id),
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception as e:  # noqa: BLE001 - 审计失败不影响主流程
        logger.warning(f"记录转移审计日志失败: {e}")


# ==================== API端点 ====================


@router.post("/transfer", response_model=CommonResponse)
async def transfer_seed(
    transfer_request: SeedTransferRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    _user=Depends(require_authenticated_user),
):
    """
    单个种子转移

    将单个种子从源下载器转移到目标下载器。

    Args:
        request: FastAPI请求对象
        transfer_request: 转移请求参数
        background_tasks: 后台任务

    Returns:
        CommonResponse: 转移结果
        {
            "status": "success",
            "msg": "种子转移成功",
            "code": "200",
            "data": {
                "success": true,
                "transfer_status": "success",
                "torrent_name": "Example Movie",
                "source_downloader_id": 1,
                "source_downloader_name": "Primary Downloader",
                "target_downloader_id": 2,
                "target_downloader_name": "Backup Downloader",
                "info_hash": "abc123...",
                "source_path": "/downloads/temp",
                "target_path": "/downloads/movies",
                "delete_source": false,
                "transfer_duration": 2500,
                "error_message": null
            }
        }
    """
    try:
        # ✅ 修复: 使用全局 app 实例(从 app.factory 导入)
        from app.factory import app  # lazy import，避免顶层循环依赖（见模块顶部注释）

        if not hasattr(app.state, "store") or app.state.store is None:
            return CommonResponse(status="error", msg="下载器缓存未初始化", code="500")

        # 使用真实登录用户（修复硬编码 admin；旧 token 可能无 user_id，兜底 1）
        user_id = getattr(_user, "user_id", None) or 1
        username = getattr(_user, "username", None) or "admin"
        audit_info = extract_audit_info_from_request(request) if request else {}

        # 执行种子转移
        async with AsyncSessionLocal() as db:
            service = SeedTransferService(db=db)
            try:
                result = await service.transfer_seed(
                    source_downloader_id=transfer_request.source_downloader_id,
                    target_downloader_id=transfer_request.target_downloader_id,
                    info_hash=transfer_request.info_hash,
                    target_path=transfer_request.target_path,
                    delete_source=transfer_request.delete_source,
                    user_id=user_id,
                    username=username,
                    app_state=app.state,
                )

                # 构建响应数据
                response_data = {
                    "success": result["success"],
                    "transfer_status": result["transfer_status"],
                    "torrent_name": result.get("torrent_name"),
                    "source_downloader_id": transfer_request.source_downloader_id,
                    "source_downloader_name": result.get("source_downloader_name"),
                    "target_downloader_id": transfer_request.target_downloader_id,
                    "target_downloader_name": result.get("target_downloader_name"),
                    "info_hash": transfer_request.info_hash,
                    "source_path": result.get("source_path"),
                    "target_path": result["target_path"],
                    "delete_source": result["delete_source"],
                    "transfer_duration": result.get("transfer_duration"),
                    "error_message": result.get("error_message"),
                }

                # 转移操作写入 torrent_audit_log（操作日志页面可见；best-effort）
                await _log_transfer_audit(
                    db=db,
                    username=username,
                    info_hash=transfer_request.info_hash,
                    source_downloader_id=transfer_request.source_downloader_id,
                    target_downloader_id=transfer_request.target_downloader_id,
                    target_path=transfer_request.target_path,
                    transfer_status=result["transfer_status"],
                    error_message=result.get("error_message"),
                    ip_address=audit_info.get("ip_address"),
                    user_agent=audit_info.get("user_agent"),
                    torrent_name=result.get("torrent_name"),
                    source_downloader_name=result.get("source_downloader_name"),
                )

                if result["success"]:
                    return CommonResponse(status="success", msg="种子转移成功", code="200", data=response_data)
                else:
                    return CommonResponse(
                        status="error", msg=result.get("error_message", "种子转移失败"), code="400", data=response_data
                    )
            finally:
                # 确保 backup_manager 自建的异步会话被归还，避免连接泄漏触发 SAWarning
                await service.aclose()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"种子转移异常: {e}")
        import traceback

        traceback.print_exc()
        return CommonResponse(status="error", msg=f"种子转移失败: {str(e)}", code="500")


@router.post("/batch-transfer", response_model=CommonResponse)
async def batch_transfer_seeds(
    batch_request: SeedTransferBatchRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    _user=Depends(require_authenticated_user),
):
    """
    批量种子转移

    将多个种子从源下载器批量转移到目标下载器。

    Args:
        request: FastAPI请求对象
        batch_request: 批量转移请求参数
        background_tasks: 后台任务

    Returns:
        CommonResponse: 批量转移结果
        {
            "status": "success",
            "msg": "批量转移完成",
            "code": "200",
            "data": {
                "total_count": 3,
                "success_count": 2,
                "failed_count": 1,
                "results": [
                    {
                        "success": true,
                        "transfer_status": "success",
                        "torrent_name": "Example 1",
                        ...
                    },
                    {
                        "success": false,
                        "transfer_status": "failed",
                        "error_message": "种子文件备份中未找到该种子",
                        ...
                    }
                ]
            }
        }
    """
    try:
        # ✅ 修复: 使用全局 app 实例(从 app.factory 导入)
        from app.factory import app  # lazy import，避免顶层循环依赖（见模块顶部注释）

        if not hasattr(app.state, "store") or app.state.store is None:
            return CommonResponse(status="error", msg="下载器缓存未初始化", code="500")

        # 使用真实登录用户（修复硬编码 admin；旧 token 可能无 user_id，兜底 1）
        user_id = getattr(_user, "user_id", None) or 1
        username = getattr(_user, "username", None) or "admin"
        audit_info = extract_audit_info_from_request(request) if request else {}

        results = []
        success_count = 0
        failed_count = 0

        # 批量执行种子转移
        async with AsyncSessionLocal() as db:
            service = SeedTransferService(db=db)
            try:
                for info_hash in batch_request.info_hashes:
                    result = await service.transfer_seed(
                        source_downloader_id=batch_request.source_downloader_id,
                        target_downloader_id=batch_request.target_downloader_id,
                        info_hash=info_hash,
                        target_path=batch_request.target_path,
                        delete_source=batch_request.delete_source,
                        user_id=user_id,
                        username=username,
                        app_state=app.state,
                    )

                    # 构建单个转移结果
                    transfer_result = {
                        "success": result["success"],
                        "transfer_status": result["transfer_status"],
                        "torrent_name": result.get("torrent_name"),
                        "source_downloader_id": batch_request.source_downloader_id,
                        "source_downloader_name": result.get("source_downloader_name"),
                        "target_downloader_id": batch_request.target_downloader_id,
                        "target_downloader_name": result.get("target_downloader_name"),
                        "info_hash": info_hash,
                        "source_path": result.get("source_path"),
                        "target_path": result["target_path"],
                        "delete_source": result["delete_source"],
                        "transfer_duration": result.get("transfer_duration"),
                        "error_message": result.get("error_message"),
                    }

                    results.append(transfer_result)

                    if result["success"]:
                        success_count += 1
                    else:
                        failed_count += 1

                    # 单条转移审计（best-effort）
                    await _log_transfer_audit(
                        db=db,
                        username=username,
                        info_hash=info_hash,
                        source_downloader_id=batch_request.source_downloader_id,
                        target_downloader_id=batch_request.target_downloader_id,
                        target_path=batch_request.target_path,
                        transfer_status=result["transfer_status"],
                        error_message=result.get("error_message"),
                        ip_address=audit_info.get("ip_address"),
                        user_agent=audit_info.get("user_agent"),
                        torrent_name=result.get("torrent_name"),
                        source_downloader_name=result.get("source_downloader_name"),
                    )

                # 构建响应数据
                response_data = {
                    "total_count": len(batch_request.info_hashes),
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "results": results,
                }

                # 部分/全部失败时返回 code=400（results 仍在 data），
                # 前端据此展示失败明细而非"转移完成"
                if failed_count > 0:
                    return CommonResponse(
                        status="error",
                        msg=f"批量转移完成：成功{success_count}个，失败{failed_count}个",
                        code="400",
                        data=response_data,
                    )
                return CommonResponse(
                    status="success",
                    msg=f"批量转移完成：成功{success_count}个，失败{failed_count}个",
                    code="200",
                    data=response_data,
                )
            finally:
                # 确保 backup_manager 自建的异步会话被归还，避免连接泄漏触发 SAWarning
                await service.aclose()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量种子转移异常: {e}")
        import traceback

        traceback.print_exc()
        return CommonResponse(status="error", msg=f"批量种子转移失败: {str(e)}", code="500")
