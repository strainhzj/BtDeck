# -*- coding: utf-8 -*-
"""主机能力矩阵 API（dual-mode-client Phase 4）。

GET /api/v1/platform/capabilities：按服务端主机形态下发 capability 集合，
设置页/任务列表/创建表单三处消费同一来源（一致降级，见
docs/android/host-capability-matrix.md 第 3 节设计冻结）。
"""

import logging

from fastapi import APIRouter, Depends

from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user
from app.core.platform_capabilities import capability_payload

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/capabilities",
    summary="获取主机能力矩阵（平台形态与功能支持级别）",
    response_model=CommonResponse,
)
def get_platform_capabilities(
    _user=Depends(require_authenticated_user),
) -> CommonResponse:
    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data=capability_payload(),
    )
