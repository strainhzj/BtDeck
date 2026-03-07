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
import urllib3
from typing import List
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.api.responseVO import CommonResponse
from app.auth.utils import verify_access_token
from app.services.seed_transfer_service import SeedTransferService
from app.schemas.seed_transfer import (
    SeedTransferRequest,
    SeedTransferResponse,
    SeedTransferBatchRequest,
    SeedTransferBatchResponse
)
from app.factory import app  # ✅ 修复: 直接导入全局app实例

# 禁用 urllib3 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 辅助函数 ====================

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


# ==================== API端点 ====================

@router.post("/transfer", response_model=CommonResponse)
async def transfer_seed(
    request: Request,
    transfer_request: SeedTransferRequest,
    background_tasks: BackgroundTasks
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
    # 验证token
    verify_token(request)

    try:
        # ✅ 修复: 使用全局 app 实例(从 app.factory 导入)
        if not hasattr(app.state, 'store') or app.state.store is None:
            return CommonResponse(
                status="error",
                msg="下载器缓存未初始化",
                code="500"
            )

        # 使用固定用户信息（admin和管理员）
        user_id = 1
        username = "admin"

        # 执行种子转移
        async with AsyncSessionLocal() as db:
            service = SeedTransferService(db=db)

            result = await service.transfer_seed(
                source_downloader_id=transfer_request.source_downloader_id,
                target_downloader_id=transfer_request.target_downloader_id,
                info_hash=transfer_request.info_hash,
                target_path=transfer_request.target_path,
                delete_source=transfer_request.delete_source,
                user_id=user_id,
                username=username,
                app_state=app.state
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
                "error_message": result.get("error_message")
            }

            if result["success"]:
                return CommonResponse(
                    status="success",
                    msg="种子转移成功",
                    code="200",
                    data=response_data
                )
            else:
                return CommonResponse(
                    status="error",
                    msg=result.get("error_message", "种子转移失败"),
                    code="400",
                    data=response_data
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"种子转移异常: {e}")
        import traceback
        traceback.print_exc()
        return CommonResponse(
            status="error",
            msg=f"种子转移失败: {str(e)}",
            code="500"
        )


@router.post("/batch-transfer", response_model=CommonResponse)
async def batch_transfer_seeds(
    request: Request,
    batch_request: SeedTransferBatchRequest,
    background_tasks: BackgroundTasks
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
    # 验证token
    verify_token(request)

    try:
        # ✅ 修复: 使用全局 app 实例(从 app.factory 导入)
        if not hasattr(app.state, 'store') or app.state.store is None:
            return CommonResponse(
                status="error",
                msg="下载器缓存未初始化",
                code="500"
            )

        # 使用固定用户信息（admin和管理员）
        user_id = 1
        username = "admin"

        results = []
        success_count = 0
        failed_count = 0

        # 批量执行种子转移
        async with AsyncSessionLocal() as db:
            service = SeedTransferService(db=db)

            for info_hash in batch_request.info_hashes:
                result = await service.transfer_seed(
                    source_downloader_id=batch_request.source_downloader_id,
                    target_downloader_id=batch_request.target_downloader_id,
                    info_hash=info_hash,
                    target_path=batch_request.target_path,
                    delete_source=batch_request.delete_source,
                    user_id=user_id,
                    username=username,
                    app_state=app.state
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
                    "error_message": result.get("error_message")
                }

                results.append(transfer_result)

                if result["success"]:
                    success_count += 1
                else:
                    failed_count += 1

            # 构建响应数据
            response_data = {
                "total_count": len(batch_request.info_hashes),
                "success_count": success_count,
                "failed_count": failed_count,
                "results": results
            }

            return CommonResponse(
                status="success",
                msg=f"批量转移完成：成功{success_count}个，失败{failed_count}个",
                code="200",
                data=response_data
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量种子转移异常: {e}")
        import traceback
        traceback.print_exc()
        return CommonResponse(
            status="error",
            msg=f"批量种子转移失败: {str(e)}",
            code="500"
        )
