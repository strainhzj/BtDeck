"""
审计日志API端点（异步版本）

提供审计日志的查询、导出、归档、统计等功能。
"""
import os
import logging
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responseVO import CommonResponse
from app.database import get_async_db
from app.services.audit_service import AuditLogService, get_audit_service, extract_audit_info_from_request
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit-logs"])


# ========== 请求模型 ==========

class AuditLogQueryRequest(BaseModel):
    """审计日志查询请求"""
    torrent_info_id: Optional[str] = Field(None, description="种子信息ID")
    torrent_name: Optional[str] = Field(None, description="种子名称（支持模糊搜索）")
    operation_type: Optional[str] = Field(None, description="操作类型")
    operator: Optional[str] = Field(None, description="操作人")
    downloader_id: Optional[str] = Field(None, description="下载器ID")
    start_time: Optional[str] = Field(None, description="开始时间(ISO 8601格式)")
    end_time: Optional[str] = Field(None, description="结束时间(ISO 8601格式)")
    operation_result: Optional[str] = Field(None, description="操作结果")
    ip_address: Optional[str] = Field(None, description="IP地址")
    request_id: Optional[str] = Field(None, description="请求ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class ArchiveLogsRequest(BaseModel):
    """归档审计日志请求"""
    end_time: str = Field(..., description="归档截止时间(ISO 8601格式)")
    archive_path: Optional[str] = Field(None, description="归档文件路径（可选，默认自动生成）")


class ExportLogsRequest(BaseModel):
    """导出审计日志请求"""
    torrent_info_id: Optional[str] = Field(None, description="种子信息ID")
    torrent_name: Optional[str] = Field(None, description="种子名称（支持模糊搜索）")
    operation_type: Optional[str] = Field(None, description="操作类型")
    operator: Optional[str] = Field(None, description="操作人")
    downloader_id: Optional[str] = Field(None, description="下载器ID")
    start_time: Optional[str] = Field(None, description="开始时间(ISO 8601格式)")
    end_time: Optional[str] = Field(None, description="结束时间(ISO 8601格式)")
    operation_result: Optional[str] = Field(None, description="操作结果")
    export_format: str = Field("csv", description="导出格式: csv/excel")
    max_rows: int = Field(10000, ge=1, le=100000, description="最大导出行数")


# ========== API端点 ==========

@router.post("/query", response_model=CommonResponse)
async def query_audit_logs(
    request: AuditLogQueryRequest,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询审计日志

    权限: 需要登录（无特殊权限限制）
    """
    try:
        # 创建审计日志服务
        audit_service = await get_audit_service(db)

        # 解析时间参数
        start_dt = datetime.fromisoformat(request.start_time) if request.start_time else None
        end_dt = datetime.fromisoformat(request.end_time) if request.end_time else None

        # 查询日志
        result = await audit_service.query_logs(
            torrent_info_id=request.torrent_info_id,
            torrent_name=request.torrent_name,  # 🔥 支持种子名称模糊搜索
            operation_type=request.operation_type,
            operator=request.operator,
            downloader_id=request.downloader_id,
            start_time=start_dt,
            end_time=end_dt,
            operation_result=request.operation_result,
            ip_address=request.ip_address,
            request_id=request.request_id,
            session_id=request.session_id,
            page=request.page,
            page_size=request.page_size
        )

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data=result
        )

    except ValueError as e:
        logger.error(f"查询审计日志失败: 参数解析错误 - {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"参数错误: {str(e)}",
            code="400",
            data=None
        )
    except Exception as e:
        logger.error(f"查询审计日志失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/statistics", response_model=CommonResponse)
async def get_audit_log_statistics(
    start_time: Optional[str] = Query(None, description="开始时间(ISO 8601格式)"),
    end_time: Optional[str] = Query(None, description="结束时间(ISO 8601格式)"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取审计日志统计信息

    权限: 需要登录（无特殊权限限制）
    """
    try:
        # 创建审计日志服务
        audit_service = await get_audit_service(db)

        # 解析时间参数
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None

        # 获取统计信息
        stats = await audit_service.get_statistics(
            start_time=start_dt,
            end_time=end_dt
        )

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data=stats
        )

    except ValueError as e:
        logger.error(f"获取审计日志统计失败: 参数解析错误 - {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"参数错误: {str(e)}",
            code="400",
            data=None
        )
    except Exception as e:
        logger.error(f"获取审计日志统计失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/archive", response_model=CommonResponse)
async def archive_audit_logs(
    request_data: ArchiveLogsRequest,
    http_request: Request,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    归档审计日志

    将指定时间之前的审计日志导出到归档文件，并从主数据库中删除。

    权限: 需要登录（无特殊权限限制）
    """
    try:
        # 创建审计日志服务
        audit_service = await get_audit_service(db)

        # 解析时间参数
        end_dt = datetime.fromisoformat(request_data.end_time)

        # 提取审计信息
        audit_info = extract_audit_info_from_request(http_request)

        # 执行归档
        result = await audit_service.archive_logs(
            end_time=end_dt,
            archive_path=request_data.archive_path
        )

        if result["success"]:
            return CommonResponse(
                status="success",
                msg=result["message"],
                code="200",
                data=result
            )
        else:
            return CommonResponse(
                status="error",
                msg=result["message"],
                code="500",
                data=result
            )

    except ValueError as e:
        logger.error(f"归档审计日志失败: 参数解析错误 - {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"参数错误: {str(e)}",
            code="400",
            data=None
        )
    except Exception as e:
        logger.error(f"归档审计日志失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"归档失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/export", response_model=CommonResponse)
async def export_audit_logs(
    request_data: ExportLogsRequest,
    http_request: Request,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    导出审计日志

    支持导出为CSV或Excel格式。

    权限: 需要登录（无特殊权限限制）
    """
    try:
        # 创建审计日志服务
        audit_service = await get_audit_service(db)

        # 解析时间参数
        start_dt = datetime.fromisoformat(request_data.start_time) if request_data.start_time else None
        end_dt = datetime.fromisoformat(request_data.end_time) if request_data.end_time else None

        # 查询日志
        result = await audit_service.query_logs(
            torrent_info_id=request_data.torrent_info_id,
            torrent_name=request_data.torrent_name,  # 🔥 支持种子名称模糊搜索
            operation_type=request_data.operation_type,
            operator=request_data.operator,
            downloader_id=request_data.downloader_id,
            start_time=start_dt,
            end_time=end_dt,
            operation_result=request_data.operation_result,
            page=1,
            page_size=request_data.max_rows
        )

        if not result["list"]:
            return CommonResponse(
                status="error",
                msg="没有符合条件的数据可导出",
                code="400",
                data=None
            )

        # 导出目录
        export_dir = Path("data/audit_logs_export")
        export_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if request_data.export_format == "excel":
            output_path = export_dir / f"audit_logs_{timestamp}.xlsx"
        else:
            output_path = export_dir / f"audit_logs_{timestamp}.csv"

        # 导出：直接传递字典列表，不重建模型对象
        if request_data.export_format == "excel":
            success = await audit_service.export_logs_to_excel(result["list"], str(output_path))
        else:
            success = await audit_service.export_logs_to_csv(result["list"], str(output_path))

        if success:
            return CommonResponse(
                status="success",
                msg=f"成功导出 {len(result['list'])} 条记录",
                code="200",
                data={
                    "file_path": str(output_path),
                    "file_name": output_path.name,
                    "record_count": len(result["list"]),
                    "file_format": request_data.export_format
                }
            )
        else:
            return CommonResponse(
                status="error",
                msg="导出失败",
                code="500",
                data=None
            )

    except ValueError as e:
        logger.error(f"导出审计日志失败: 参数解析错误 - {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"参数错误: {str(e)}",
            code="400",
            data=None
        )
    except Exception as e:
        logger.error(f"导出审计日志失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"导出失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/operation-types", response_model=CommonResponse)
async def get_operation_types(
    current_user = Depends(get_current_user)
):
    """
    获取所有操作类型列表

    权限: 需要登录（无特殊权限限制）
    """
    try:
        # 获取所有操作类型
        operation_types = []
        for op_type in AuditOperationType:
            operation_types.append({
                "value": op_type.value,
                "display_name": op_type.get_display_name(op_type.value),
                "category": op_type.get_category(op_type.value)
            })

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "operation_types": operation_types,
                "total": len(operation_types)
            }
        )

    except Exception as e:
        logger.error(f"获取操作类型失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/download-export/{file_name}", response_model=None)
async def download_export_file(
    file_name: str,
    current_user = Depends(get_current_user)
):
    """
    下载导出的审计日志文件

    权限: 需要登录（无特殊权限限制）
    """
    from fastapi.responses import FileResponse

    try:
        # 构建文件路径
        file_path = Path("data/audit_logs_export") / file_name

        # 检查文件是否存在
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        # 返回文件
        return FileResponse(
            path=str(file_path),
            filename=file_name,
            media_type='application/octet-stream'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载导出文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")
