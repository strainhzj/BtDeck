# -*- coding: utf-8 -*-
"""
Tracker Reannounce 配置管理 API

提供站点汇报配置的 CRUD 接口和自动检测域名功能。
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import utils as auth_utils
from app.database import get_db
from app.core import reannounce_config_operations as ops

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 请求模型 ====================

class CreateConfigRequest(BaseModel):
    domain_pattern: str = Field(..., description="域名匹配模式")
    domain_display_name: str = Field("", description="域名显示名称")
    interval_minutes: int = Field(30, description="汇报间隔（分钟）")
    enabled: bool = Field(True, description="是否启用")


class UpdateConfigRequest(BaseModel):
    domain_pattern: str | None = None
    domain_display_name: str | None = None
    interval_minutes: int | None = None
    enabled: bool | None = None


# ==================== 认证辅助 ====================

def _verify_token(request: Request) -> CommonResponse | None:
    """验证token，失败时返回错误响应"""
    token = request.headers.get("x-access-token")
    if not token:
        return CommonResponse(status="error", msg="Token缺失", code="401")
    try:
        user_info = auth_utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(status="error", msg="token验证失败", code="401")
    except Exception:
        return CommonResponse(status="error", msg="token验证失败", code="401")
    return None


# ==================== API 接口 ====================

@router.get("/configs", description="获取所有站点配置")
async def list_configs(request: Request, db: Session = Depends(get_db)):
    """获取所有站点汇报配置"""
    if err := _verify_token(request):
        return err

    result = ops.get_configs(db)
    if not result.success:
        return CommonResponse(status="error", msg=result.message, code="500")

    configs = [c.to_dict() for c in result.data]
    return CommonResponse(
        status="success", msg="查询成功", code="200",
        data={"total": result.total_count, "list": configs},
    )


@router.post("/configs", description="新增站点配置")
async def create_config(
        request: Request,
        req_data: CreateConfigRequest,
        db: Session = Depends(get_db),
):
    """新增站点汇报配置"""
    if err := _verify_token(request):
        return err

    config_data = req_data.dict()
    if not config_data.get("domain_display_name"):
        config_data["domain_display_name"] = config_data["domain_pattern"]

    result = ops.create_config(db, config_data)
    if not result.success:
        return CommonResponse(status="error", msg=result.message, code="400")

    return CommonResponse(
        status="success", msg="创建成功", code="200",
        data=result.data.to_dict(),
    )


@router.put("/configs/{config_id}", description="更新站点配置")
async def update_config(
        config_id: str,
        request: Request,
        req_data: UpdateConfigRequest,
        db: Session = Depends(get_db),
):
    """更新站点汇报配置"""
    if err := _verify_token(request):
        return err

    update_data = {k: v for k, v in req_data.dict().items() if v is not None}
    if not update_data:
        return CommonResponse(status="error", msg="没有需要更新的字段", code="400")

    result = ops.update_config(db, config_id, update_data)
    if not result.success:
        code = "404" if "不存在" in result.message else "400"
        return CommonResponse(status="error", msg=result.message, code=code)

    return CommonResponse(
        status="success", msg="更新成功", code="200",
        data=result.data.to_dict(),
    )


@router.delete("/configs/{config_id}", description="删除站点配置")
async def delete_config(
        config_id: str,
        request: Request,
        db: Session = Depends(get_db),
):
    """删除站点汇报配置"""
    if err := _verify_token(request):
        return err

    result = ops.delete_config(db, config_id)
    if not result.success:
        return CommonResponse(status="error", msg=result.message, code="404")

    return CommonResponse(status="success", msg="删除成功", code="200")


@router.post("/configs/auto-detect", description="自动检测tracker域名并生成配置")
async def auto_detect_domains(request: Request, db: Session = Depends(get_db)):
    """从现有tracker数据中提取域名，生成默认配置"""
    if err := _verify_token(request):
        return err

    from app.torrents.models import TrackerInfo

    # 查询所有未删除的 tracker URL
    trackers = db.query(TrackerInfo.tracker_url).filter(
        TrackerInfo.dr == 0,
        TrackerInfo.tracker_url.isnot(None),
    ).all()

    tracker_urls = [t[0] for t in trackers if t[0]]
    domains = ops.extract_domains_from_trackers(tracker_urls)

    # 查询已存在的配置域名
    existing = ops.get_configs(db)
    existing_patterns = {c.domain_pattern for c in existing.data} if existing.success else set()

    # 过滤掉已有配置的域名
    new_domains = [d for d in domains if d not in existing_patterns]

    # 为新域名创建默认配置
    created = []
    for domain in new_domains:
        result = ops.create_config(db, {
            "domain_pattern": domain,
            "domain_display_name": domain,
            "interval_minutes": 30,
            "enabled": True,
        })
        if result.success:
            created.append(result.data.to_dict())

    return CommonResponse(
        status="success",
        msg=f"检测到 {len(domains)} 个域名，新增 {len(created)} 个配置",
        code="200",
        data={"detected": len(domains), "created": len(created), "configs": created},
    )
