# -*- coding: utf-8 -*-
"""统计报表端点（统计报表 W3，PLANS/statistics-reports.md §3.5）。

全部 GET + ``Depends(get_current_user)`` + CommonResponse；聚合端点不分页。
空数据语义：聚合返回空数组/零值；速度历史无样本 ``series=[]`` +
``samplingActive=true, firstSampleAt=null``。
"""

import logging
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responseVO import CommonResponse
from app.auth.dependencies import get_current_user
from app.core.runtime_context import RuntimeContext
from app.database import get_async_db
from app.services import report_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


def _year_param(year: int) -> int:
    """年度参数收敛到合理区间（前端选择器 2024–当前年，后端宽松校验）。"""
    current = datetime.now().year
    if year < 2000 or year > current + 1:
        raise ValueError(f"year 需在 2000-{current + 1} 之间，实际 {year}")
    return year


@router.get("/overview", summary="报表·总览", response_model=CommonResponse)
async def get_reports_overview(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """A1-A5：库存总览 / 五桶状态分布 / 分类标签 / 目录占用 / 下载器对比 + 实时速度。"""
    try:
        data = await report_service.get_overview(db, RuntimeContext.from_app(request.app))
        return CommonResponse(status="success", msg="获取成功", code="200", data=data)
    except Exception as exc:
        logger.error(f"[REPORTS] overview failed: {exc}")
        return CommonResponse(status="error", msg=f"获取失败: {str(exc)}", code="500", data=None)


@router.get("/trends", summary="报表·趋势", response_model=CommonResponse)
async def get_reports_trends(
    period: Literal["month", "week"] = Query("month", description="分桶周期：month/week"),
    limit: int = Query(12, ge=1, le=48, description="保留桶数"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """B6/B7 新增与完成趋势 + B8 库龄结构 + B9 速度历史（默认 24h）。"""
    try:
        data = await report_service.get_trends(db, period=period, limit=limit)
        return CommonResponse(status="success", msg="获取成功", code="200", data=data)
    except Exception as exc:
        logger.error(f"[REPORTS] trends failed: {exc}")
        return CommonResponse(status="error", msg=f"获取失败: {str(exc)}", code="500", data=None)


@router.get("/seeding", summary="报表·做种", response_model=CommonResponse)
async def get_reports_seeding(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """C10 分享率分布 / C11 摸鱼象限 / C12 辅种网络。"""
    try:
        data = await report_service.get_seeding(db)
        return CommonResponse(status="success", msg="获取成功", code="200", data=data)
    except Exception as exc:
        logger.error(f"[REPORTS] seeding failed: {exc}")
        return CommonResponse(status="error", msg=f"获取失败: {str(exc)}", code="500", data=None)


@router.get("/trackers", summary="报表·Tracker", response_model=CommonResponse)
async def get_reports_trackers(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """D14 站点构成 / D15 站点健康榜 / D16 站点冷热。"""
    try:
        data = await report_service.get_tracker_stats(db)
        return CommonResponse(status="success", msg="获取成功", code="200", data=data)
    except Exception as exc:
        logger.error(f"[REPORTS] trackers failed: {exc}")
        return CommonResponse(status="error", msg=f"获取失败: {str(exc)}", code="500", data=None)


@router.get("/fun/summary", summary="趣味报表·战报", response_model=CommonResponse)
async def get_reports_fun_summary(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """趣味 24 火种守护者 / 25 上传量勋章 / 27 白嫖 vs 慈善榜。"""
    try:
        data = await report_service.get_fun_summary(db)
        return CommonResponse(status="success", msg="获取成功", code="200", data=data)
    except Exception as exc:
        logger.error(f"[REPORTS] fun/summary failed: {exc}")
        return CommonResponse(status="error", msg=f"获取失败: {str(exc)}", code="500", data=None)


@router.get("/fun/yearly", summary="趣味报表·年度报告", response_model=CommonResponse)
async def get_reports_fun_yearly(
    year: Optional[int] = Query(None, description="年份，缺省今年"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """趣味 26 种库年度报告（Spotify Wrapped 式翻页流数据源）。"""
    try:
        target_year = year if year is not None else datetime.now().year
        data = await report_service.get_fun_yearly(db, _year_param(target_year))
        return CommonResponse(status="success", msg="获取成功", code="200", data=data)
    except ValueError as exc:
        return CommonResponse(status="error", msg=str(exc), code="400", data=None)
    except Exception as exc:
        logger.error(f"[REPORTS] fun/yearly failed: {exc}")
        return CommonResponse(status="error", msg=f"获取失败: {str(exc)}", code="500", data=None)


@router.get("/speed/history", summary="报表·速度历史", response_model=CommonResponse)
async def get_reports_speed_history(
    range: Literal["24h", "7d", "30d"] = Query("24h", description="时间窗口"),
    downloaderId: Optional[str] = Query(None, description="可选：限定下载器"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """B9 速度历史曲线（同 trends.speedHistory，可独立带筛选查询）。"""
    try:
        data = await report_service.get_speed_history(db, range_key=range, downloader_id=downloaderId)
        return CommonResponse(status="success", msg="获取成功", code="200", data=data)
    except Exception as exc:
        logger.error(f"[REPORTS] speed/history failed: {exc}")
        return CommonResponse(status="error", msg=f"获取失败: {str(exc)}", code="500", data=None)
