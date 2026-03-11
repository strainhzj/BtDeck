from fastapi import APIRouter, Query, Depends
from typing import Optional
from app.api.responseVO import CommonResponse
from app.auth import utils
from fastapi import Request

from app.tasks.logger import get_task_logs, get_task_statistics

router = APIRouter()


@router.get("/logs", response_model=CommonResponse)
async def get_task_logs_endpoint(
    req: Request,
    task_name: Optional[str] = Query(None, description="任务名称"),
    success: Optional[bool] = Query(None, description="执行结果"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数"),
    offset: int = Query(0, ge=0, description="跳过记录数")
):
    """获取任务执行日志"""
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)

        # 获取任务日志
        result = await get_task_logs(
            task_name=task_name,
            success=success,
            limit=limit,
            offset=offset
        )

        return CommonResponse(
            status="success",
            msg="获取任务日志成功",
            code="200",
            data=result
        )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"获取任务日志失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/statistics", response_model=CommonResponse)
async def get_task_statistics_endpoint(req: Request):
    """获取任务统计信息"""
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)

        # 获取统计信息
        stats = await get_task_statistics()

        return CommonResponse(
            status="success",
            msg="获取任务统计成功",
            code="200",
            data=stats
        )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"获取任务统计失败: {str(e)}",
            code="500",
            data=None
        )