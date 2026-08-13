"""同名同大小种子只读排查接口。"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth.dependencies import AuthenticatedUserInfo, require_authenticated_user
from app.database import get_db
from app.services.same_content_inspection_service import inspect_same_content_torrents

logger = logging.getLogger(__name__)
router = APIRouter()


class SameContentInspectionRequest(BaseModel):
    """同名同大小种子排查请求。"""

    mode: Literal["all", "errors"] = Field("all", description="all=完整结果，errors=仅错误种子")
    page: int = Field(1, ge=1, description="页码（从1开始，按候选组分页）")
    pageSize: int = Field(20, ge=1, le=50, description="每页候选组数")


@router.post("/same-content-inspection", response_model=CommonResponse)
def same_content_inspection(
    payload: SameContentInspectionRequest,
    current_user: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """发现名称、大小相同且 InfoHash 不同的种子，并返回只读错误诊断。"""
    try:
        data = inspect_same_content_torrents(
            db,
            mode=payload.mode,
            page=payload.page,
            page_size=payload.pageSize,
        )
        logger.info(
            "同内容异常排查成功: 用户=%s, 模式=%s, 候选组=%s, 错误组=%s, 当前页=%s",
            current_user.username,
            payload.mode,
            data["summary"]["candidate_group_count"],
            data["summary"]["error_group_count"],
            payload.page,
        )
        return CommonResponse(status="success", msg="查询成功", code="200", data=data)
    except Exception as exc:
        logger.error("同内容异常排查失败: %s", exc, exc_info=True)
        return CommonResponse(status="error", msg="查询失败，请稍后重试", code="500", data=None)
