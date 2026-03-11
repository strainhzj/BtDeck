import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responseVO import CommonResponse
from app.auth.dependencies import get_current_user
from app.database import get_async_db
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


@router.get("", summary="获取仪表盘数据", response_model=CommonResponse)
async def get_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """获取仪表盘完整数据."""
    try:
        service = DashboardService(db, request.app)
        data = await service.get_dashboard_data()

        return CommonResponse(
            status="success",
            msg="获取成功",
            code="200",
            data=data,
        )
    except Exception as exc:
        logger.error(f"获取仪表盘数据失败: {exc}")
        return CommonResponse(
            status="error",
            msg=f"获取失败: {str(exc)}",
            code="500",
            data=None,
        )
