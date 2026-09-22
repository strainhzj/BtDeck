# -*- coding: utf-8 -*-
"""MCP 服务配置控制面 API（feature mcp-service-capabilities-2026-08-28 W1）。

- ``GET /api/v1/mcp/settings``：读取生效配置（含 kill switch 覆盖态）与能力目录元数据；
- ``PUT /api/v1/mcp/settings``：revision CAS 更新（409 冲突），写审计日志（best-effort）。

W5 新增服务密钥控制面（外部 agent 对接 MCP 的长期专用密钥）：

- ``GET /api/v1/mcp/apikey``：查看密钥（active 返回明文；absent/unreadable
  返回引导态，不带明文）；仅 active（真实明文披露）写审计（best-effort）；
- ``POST /api/v1/mcp/apikey/rotate``：生成/刷新密钥（revision CAS，409
  冲突），旧密钥立即失效；写审计（含 previousOwner/rotatedBy）。

认证（计划 §4.2）：控制面仅允许数据库中存在、``is_active=True`` 且
``must_change_password=False`` 的认证用户操作——直接消费协议无关认证内核
``app/auth/principal.py``（禁用/强制改密分别映射 403，token 问题映射 401）。
token 提取复用 ``app.auth.dependencies._extract_access_token``（X-Access-Token
与 Bearer 双兼容，不在本文件手写解析——BTD201）；W2 MCP transport 侧接线
将收敛同一 principal 内核。
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth.dependencies import _extract_access_token
from app.auth.principal import (
    REASON_PASSWORD_CHANGE_REQUIRED,
    REASON_USER_INACTIVE,
    AuthenticatedPrincipal,
    PrincipalAuthenticationError,
    authenticate_access_token,
)
from app.database import get_async_db, get_db
from app.mcp.contracts import CAPABILITY_CATALOG
from app.services.audit_context import AuditContext
from app.services.audit_service import AuditLogService
from app.services.mcp_apikey_service import (
    McpApiKeyRevisionConflict,
    McpApiKeyService,
    McpApiKeyStateError,
)
from app.services.mcp_settings_service import (
    McpSettingsRevisionConflict,
    McpSettingsService,
    McpSettingsStateError,
)
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType

logger = logging.getLogger(__name__)
router = APIRouter()

_FORBIDDEN_REASONS = {REASON_USER_INACTIVE, REASON_PASSWORD_CHANGE_REQUIRED}


class McpSettingsUpdateRequest(BaseModel):
    """PUT 载荷：完整期望状态 + CAS 前提 revision。"""

    enabled: bool
    capabilities: Dict[str, bool]
    expectedRevision: int = Field(ge=0)


class McpApiKeyRotateRequest(BaseModel):
    """服务密钥生成/刷新载荷：CAS 前提 revision（无密钥行时为 0）。"""

    expectedRevision: int = Field(ge=0)


def require_mcp_control_plane_user(request: Request, db: Session = Depends(get_db)) -> AuthenticatedPrincipal:
    """控制面认证门禁：principal 内核全链校验（存在/启用/非强制改密）。"""
    token = _extract_access_token(request)
    try:
        return authenticate_access_token(token, db)
    except PrincipalAuthenticationError as exc:
        # 禁用/强制改密是"主体状态不允许"（403）；token 缺失/无效/用户不存在（401）
        http_status = status.HTTP_403_FORBIDDEN if exc.reason in _FORBIDDEN_REASONS else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(
            status_code=http_status,
            detail=CommonResponse(status="error", msg=exc.message, code=str(http_status), data=None).model_dump(),
        )


def _catalog_meta() -> list[Dict[str, Any]]:
    """能力目录元数据（单一事实源 contracts.CAPABILITY_CATALOG，UI 免维护文案）。

    W5 双语化：``description``/``descriptionEn`` 成对下发，前端按 locale 选取
    （与 HTTP 高级搜索契约 labelEn 同模式）；MCP 协议面工具描述（catalog.py
    的 Tool.description）维持中文不动（协议消费者按稳定工具名对接）。
    """
    return [
        {
            "code": spec.code,
            "tool": spec.tool_name,
            "risk": spec.risk,
            "description": spec.description,
            "descriptionEn": spec.description_en,
            "defaultEnabled": False,
            "requiresConfirm": spec.requires_confirm,
            "requiresIdempotencyKey": spec.requires_idempotency_key,
        }
        for spec in CAPABILITY_CATALOG
    ]


async def _log_settings_audit(
    adb: Optional[AsyncSession],
    principal: AuthenticatedPrincipal,
    audit_context: AuditContext,
    new_payload: Dict[str, Any],
    result: str,
) -> None:
    """配置变更审计（G11）：best-effort，失败不阻断响应。"""
    if adb is None:
        return
    try:
        audit_service = AuditLogService(adb)
        await audit_service.log_operation(
            operation_type=AuditOperationType.MCP_SETTINGS_UPDATE,
            operator=principal.username,
            operation_detail={
                "enabled": new_payload["enabled"],
                "capabilities": new_payload["capabilities"],
                "revision": new_payload["revision"],
                "forceDisabled": new_payload["forceDisabled"],
            },
            operation_result=result,
            ip_address=audit_context.ip_address,
            user_agent=audit_context.user_agent,
            request_id=audit_context.request_id,
            session_id=audit_context.session_id,
        )
    except Exception as exc:  # noqa: BLE001 - 审计缺失不影响配置主流程
        logger.warning("MCP 配置变更审计写入失败（不阻断响应）: %s", exc)


async def _log_apikey_audit(
    adb: Optional[AsyncSession],
    principal: AuthenticatedPrincipal,
    audit_context: AuditContext,
    operation_type: AuditOperationType,
    detail: Dict[str, Any],
) -> None:
    """服务密钥查看/刷新审计（W5）：best-effort；detail 禁记密钥本体与哈希。"""
    if adb is None:
        return
    try:
        audit_service = AuditLogService(adb)
        await audit_service.log_operation(
            operation_type=operation_type,
            operator=principal.username,
            operation_detail=detail,
            operation_result=AuditOperationResult.SUCCESS,
            ip_address=audit_context.ip_address,
            user_agent=audit_context.user_agent,
            request_id=audit_context.request_id,
            session_id=audit_context.session_id,
        )
    except Exception as exc:  # noqa: BLE001 - 审计缺失不影响密钥主流程
        logger.warning("MCP 服务密钥审计写入失败（不阻断响应）: %s", exc)


@router.get(
    "/settings",
    summary="获取 MCP 服务配置（生效态 + 能力目录）",
    response_model=CommonResponse,
)
def get_mcp_settings(
    _principal: AuthenticatedPrincipal = Depends(require_mcp_control_plane_user),
    db: Session = Depends(get_db),
) -> CommonResponse:
    service = McpSettingsService(db)
    snapshot = service.get_settings()
    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data={"settings": snapshot.to_payload(), "catalog": _catalog_meta()},
    )


@router.put(
    "/settings",
    summary="更新 MCP 服务配置（revision CAS，冲突 409）",
    response_model=CommonResponse,
)
async def update_mcp_settings(
    payload: McpSettingsUpdateRequest,
    request: Request,
    _principal: AuthenticatedPrincipal = Depends(require_mcp_control_plane_user),
    db: Session = Depends(get_db),
    adb: AsyncSession = Depends(get_async_db),
) -> CommonResponse:
    service = McpSettingsService(db)
    try:
        snapshot = service.update_settings(
            enabled=payload.enabled,
            capabilities=payload.capabilities,
            expected_revision=payload.expectedRevision,
            updated_by=_principal.username,
        )
    except McpSettingsRevisionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CommonResponse(
                status="error",
                msg="配置已被其他会话修改，请刷新后重试",
                code="409",
                data={
                    "currentRevision": exc.current_revision,
                    # 双语错误契约：前端按 reasonCode 本地化（revision 移出 msg，只进 data）
                    "reasonCode": "MCP_SETTINGS_CONFLICT",
                },
            ).model_dump(),
        )
    except McpSettingsStateError as exc:
        # 动态 str(exc)（未知/缺失能力码等）只进日志不进 msg（防泄露/可本地化）
        logger.warning("MCP 配置载荷校验失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CommonResponse(
                status="error",
                msg="MCP 配置载荷无效，请检查能力码与取值",
                code="400",
                data={"reasonCode": "MCP_SETTINGS_INVALID"},
            ).model_dump(),
        )
    await _log_settings_audit(
        adb=adb,
        principal=_principal,
        audit_context=AuditContext.from_request(request),
        new_payload=snapshot.to_payload(),
        result=AuditOperationResult.SUCCESS,
    )
    return CommonResponse(
        status="success",
        msg="更新成功",
        code="200",
        data={"settings": snapshot.to_payload(), "catalog": _catalog_meta()},
    )


@router.get(
    "/apikey",
    summary="查看 MCP 服务密钥（未生成返回 absent 引导态）",
    response_model=CommonResponse,
)
async def get_mcp_apikey(
    request: Request,
    _principal: AuthenticatedPrincipal = Depends(require_mcp_control_plane_user),
    db: Session = Depends(get_db),
    adb: AsyncSession = Depends(get_async_db),
) -> CommonResponse:
    """查看服务密钥：active 返回明文（写查看审计），absent/unreadable 引导生成/刷新。

    响应 data 形态（信封四字段不变，仅 data）：
    - active：{status, exists:true, revision, key, createdAt, createdBy, updatedAt, updatedBy, keyPrefix}
    - absent/unreadable：同款元数据但不含 key（前端按 status 分流引导）
    """
    view = McpApiKeyService(db).get_view()
    if view.get("status") == "active":
        # 仅真实明文披露入审计（面板挂载的 absent/unreadable 读取不刷审计噪音）
        await _log_apikey_audit(
            adb=adb,
            principal=_principal,
            audit_context=AuditContext.from_request(request),
            operation_type=AuditOperationType.MCP_APIKEY_VIEW,
            detail={"revision": view.get("revision")},
        )
    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data=view,
    )


@router.post(
    "/apikey/rotate",
    summary="生成/刷新 MCP 服务密钥（revision CAS，冲突 409；旧密钥立即失效）",
    response_model=CommonResponse,
)
async def rotate_mcp_apikey(
    payload: McpApiKeyRotateRequest,
    request: Request,
    _principal: AuthenticatedPrincipal = Depends(require_mcp_control_plane_user),
    db: Session = Depends(get_db),
    adb: AsyncSession = Depends(get_async_db),
) -> CommonResponse:
    """生成/刷新服务密钥并返回新明文（全链路唯一返回明文的写出口）。

    CAS：expectedRevision 必须等于当前 revision（无密钥行时为 0）；并发
    rotate 后者收 409 + currentRevision，避免 last-write-wins 静默覆盖
    （被覆盖方 agent 会无提示失联）。
    """
    service = McpApiKeyService(db)
    previous = service.get_view()
    previous_owner = previous.get("updatedBy") or previous.get("createdBy")
    try:
        reveal = service.rotate(
            rotated_by=_principal.username,
            expected_revision=payload.expectedRevision,
        )
    except McpApiKeyRevisionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CommonResponse(
                status="error",
                msg="服务密钥已被其他会话变更，请刷新后重试",
                code="409",
                data={
                    "currentRevision": exc.current_revision,
                    # 双语错误契约：前端按 reasonCode 本地化（revision 移出 msg，只进 data）
                    "reasonCode": "MCP_APIKEY_CONFLICT",
                },
            ).model_dump(),
        )
    except McpApiKeyStateError as exc:
        # 动态 str(exc)（载荷非法/加密组件不可用）只进日志不进 msg（防泄露/可本地化）
        logger.warning("MCP 服务密钥生成/刷新失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CommonResponse(
                status="error",
                msg="服务密钥生成失败，请检查请求或服务器加密组件配置",
                code="400",
                data={"reasonCode": "MCP_APIKEY_INVALID"},
            ).model_dump(),
        )
    await _log_apikey_audit(
        adb=adb,
        principal=_principal,
        audit_context=AuditContext.from_request(request),
        operation_type=AuditOperationType.MCP_APIKEY_ROTATE,
        detail={
            "revision": reveal.state.revision,
            "previousOwner": previous_owner,
            "rotatedBy": _principal.username,
        },
    )
    return CommonResponse(
        status="success",
        msg="服务密钥已生成",
        code="200",
        data=reveal.to_payload(),
    )
