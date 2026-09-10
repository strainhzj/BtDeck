# -*- coding: utf-8 -*-
"""MoviePilot 集成 API（feature moviepilot-integration-20260908）。

端点分组：

- **集成面（插件调用）**：``POST /handshake``、``POST /sync/transfer-history``
  —— 认证复用现有用户令牌体系（专用集成账号 /login + /refresh，与
  ``require_mcp_control_plane_user`` 同一 principal 内核链路：token 缺失/
  无效 401，禁用/强制改密 403）；全局开关关闭或实例禁用时 403。
- **管理面（设置页）**：``GET/PUT /settings``（revision CAS）、
  ``GET /instances``、``PUT/DELETE /instances/{instance_id}``。
- **查询面（种子详情/反查）**：``GET /associations``、
  ``GET /associations/reverse``——轻量 token 校验（require_authenticated_user）。

同步是纯只读镜像写入，不存在任何触发删除/暂停/修改生产任务的路径；
审计 best-effort（失败仅告警不阻断响应）。
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth.dependencies import _extract_access_token, require_authenticated_user
from app.auth.principal import (
    REASON_PASSWORD_CHANGE_REQUIRED,
    REASON_USER_INACTIVE,
    AuthenticatedPrincipal,
    PrincipalAuthenticationError,
    authenticate_access_token,
)
from app.database import get_async_db, get_db
from app.services.audit_context import AuditContext
from app.services.audit_service import AuditLogService
from app.services.moviepilot_integration_service import (
    MAX_SYNC_BATCH_ITEMS,
    MOVIEPILOT_PROTOCOL_VERSION,
    MoviePilotIntegrationDisabledError,
    MoviePilotIntegrationService,
    MoviePilotInstanceBindingError,
    MoviePilotInstanceDisabledError,
    MoviePilotInstanceNotFoundError,
    MoviePilotMappingError,
    MoviePilotSyncPayloadError,
)
from app.services.moviepilot_settings_service import (
    MoviePilotSettingsRevisionConflict,
    MoviePilotSettingsService,
    MoviePilotSettingsStateError,
)
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType

logger = logging.getLogger(__name__)
router = APIRouter()

_FORBIDDEN_REASONS = {REASON_USER_INACTIVE, REASON_PASSWORD_CHANGE_REQUIRED}


def require_moviepilot_integration_user(request: Request, db: Session = Depends(get_db)) -> AuthenticatedPrincipal:
    """集成/管理面认证门禁：principal 内核全链校验（对齐 mcp_settings 先例）。"""
    token = _extract_access_token(request)
    try:
        return authenticate_access_token(token, db)
    except PrincipalAuthenticationError as exc:
        http_status = status.HTTP_403_FORBIDDEN if exc.reason in _FORBIDDEN_REASONS else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(
            status_code=http_status,
            detail=CommonResponse(status="error", msg=exc.message, code=str(http_status), data=None).model_dump(),
        )


def _http_error(http_status: int, message: str, data: Any = None) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail=CommonResponse(status="error", msg=message, code=str(http_status), data=data).model_dump(),
    )


# ==============================================================================
# 请求模型
# ==============================================================================


class HandshakeRequest(BaseModel):
    """握手载荷：插件持久化的实例身份 + 版本信息。"""

    instanceId: str = Field(min_length=8, max_length=64)
    instanceName: Optional[str] = Field(default=None, max_length=128)
    protocolVersion: int = Field(ge=1)
    pluginVersion: Optional[str] = Field(default=None, max_length=32)
    moviepilotVersion: Optional[str] = Field(default=None, max_length=64)


class SyncItemRequest(BaseModel):
    """单条整理历史（协议 v1；字段名与 MoviePilot TransferHistory 对齐）。"""

    historyId: int = Field(ge=0)
    srcStorage: Optional[str] = Field(default=None, max_length=32)
    srcPath: Optional[str] = Field(default=None, max_length=1024)
    srcFileitem: Optional[Dict[str, Any]] = None
    destStorage: Optional[str] = Field(default=None, max_length=32)
    destPath: Optional[str] = Field(default=None, max_length=1024)
    destFileitem: Optional[Dict[str, Any]] = None
    transferMode: Optional[str] = Field(default=None, max_length=32)
    mediaType: Optional[str] = Field(default=None, max_length=16)
    title: Optional[str] = Field(default=None, max_length=255)
    year: Optional[str] = Field(default=None, max_length=8)
    seasons: Optional[str] = Field(default=None, max_length=32)
    episodes: Optional[str] = Field(default=None, max_length=255)
    tmdbId: Optional[int] = None
    doubanId: Optional[str] = Field(default=None, max_length=32)
    mediaSource: Optional[str] = Field(default=None, max_length=32)
    mediaId: Optional[str] = Field(default=None, max_length=64)
    mpDownloader: Optional[str] = Field(default=None, max_length=128)
    downloadHash: Optional[str] = Field(default=None, max_length=64)
    status: Optional[bool] = None
    errmsg: Optional[str] = Field(default=None, max_length=2048)
    recordedAt: Optional[str] = Field(default=None, max_length=32)
    files: Optional[List[Dict[str, Any]]] = None


class SyncRequest(BaseModel):
    """同步载荷：一批整理历史 + 批次定位信息。"""

    instanceId: str = Field(min_length=8, max_length=64)
    protocolVersion: int = Field(ge=1)
    syncMode: str = Field(pattern="^(full|incremental)$")
    pageNumber: int = Field(default=1, ge=1)
    pageSize: int = Field(default=100, ge=1, le=MAX_SYNC_BATCH_ITEMS)
    isLastBatch: bool = False
    items: List[SyncItemRequest] = Field(max_length=MAX_SYNC_BATCH_ITEMS)


class SettingsUpdateRequest(BaseModel):
    """全局开关 PUT 载荷（revision CAS）。"""

    enabled: bool
    expectedRevision: int = Field(ge=0)


class InstanceUpdateRequest(BaseModel):
    """实例更新载荷：三字段均可选，未提供的保持不变。"""

    name: Optional[str] = Field(default=None, max_length=128)
    enabled: Optional[bool] = None
    downloaderMapping: Optional[Dict[str, str]] = None


# ==============================================================================
# 审计
# ==============================================================================


async def _log_audit(
    adb: Optional[AsyncSession],
    principal: AuthenticatedPrincipal,
    audit_context: AuditContext,
    operation_type: AuditOperationType,
    operation_detail: Dict[str, Any],
    result: str,
) -> None:
    """best-effort 审计写入（失败仅告警，不阻断响应）。"""
    if adb is None:
        return
    try:
        audit_service = AuditLogService(adb)
        await audit_service.log_operation(
            operation_type=operation_type,
            operator=principal.username,
            operation_detail=operation_detail,
            operation_result=result,
            ip_address=audit_context.ip_address,
            user_agent=audit_context.user_agent,
            request_id=audit_context.request_id,
            session_id=audit_context.session_id,
        )
    except Exception as exc:  # noqa: BLE001 - 审计缺失不影响主流程
        logger.warning("MoviePilot 集成审计写入失败（不阻断响应）: %s", exc)


def _map_service_error(exc: Exception) -> HTTPException:
    """服务层异常 → HTTP 错误（信封语义与 mcp_settings 一致）。"""
    if isinstance(
        exc, (MoviePilotIntegrationDisabledError, MoviePilotInstanceDisabledError, MoviePilotInstanceBindingError)
    ):
        return _http_error(status.HTTP_403_FORBIDDEN, str(exc))
    if isinstance(exc, MoviePilotInstanceNotFoundError):
        return _http_error(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (MoviePilotSyncPayloadError, MoviePilotMappingError)):
        return _http_error(status.HTTP_400_BAD_REQUEST, str(exc))
    return _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, f"服务端内部错误: {exc}")


# ==============================================================================
# 集成面（插件调用）
# ==============================================================================


@router.post("/handshake", summary="MoviePilot 插件握手（注册/刷新实例）", response_model=CommonResponse)
def moviepilot_handshake(
    payload: HandshakeRequest,
    _principal: AuthenticatedPrincipal = Depends(require_moviepilot_integration_user),
    db: Session = Depends(get_db),
) -> CommonResponse:
    service = MoviePilotIntegrationService(db)
    try:
        result = service.handshake(_principal.username, payload.model_dump())
    except (MoviePilotSyncPayloadError,) as exc:
        raise _http_error(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        raise _map_service_error(exc) from exc
    return CommonResponse(status="success", msg="握手成功", code="200", data=result)


@router.post("/sync/transfer-history", summary="批量同步整理历史（幂等 upsert）", response_model=CommonResponse)
async def moviepilot_sync_transfer_history(
    payload: SyncRequest,
    request: Request,
    _principal: AuthenticatedPrincipal = Depends(require_moviepilot_integration_user),
    db: Session = Depends(get_db),
    adb: AsyncSession = Depends(get_async_db),
) -> CommonResponse:
    service = MoviePilotIntegrationService(db)
    try:
        result = service.sync_transfer_history(_principal.username, payload.model_dump())
    except Exception as exc:
        raise _map_service_error(exc) from exc

    await _log_audit(
        adb=adb,
        principal=_principal,
        audit_context=AuditContext.from_request(request),
        operation_type=AuditOperationType.MOVIEPILOT_SYNC,
        operation_detail={
            "instanceId": payload.instanceId,
            "syncMode": payload.syncMode,
            "batch": {"pageNumber": payload.pageNumber, "pageSize": payload.pageSize, "isLast": payload.isLastBatch},
            "counts": {key: result[key] for key in ("inserted", "updated", "skipped", "failed")},
        },
        result=AuditOperationResult.PARTIAL if result["failed"] else AuditOperationResult.SUCCESS,
    )
    return CommonResponse(status="success", msg="同步成功", code="200", data=result)


# ==============================================================================
# 管理面（设置页）
# ==============================================================================


@router.get("/settings", summary="获取 MoviePilot 集成全局开关", response_model=CommonResponse)
def get_moviepilot_settings(
    _principal: AuthenticatedPrincipal = Depends(require_moviepilot_integration_user),
    db: Session = Depends(get_db),
) -> CommonResponse:
    snapshot = MoviePilotSettingsService(db).get_settings()
    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data={"settings": snapshot.to_payload(), "protocolVersion": MOVIEPILOT_PROTOCOL_VERSION},
    )


@router.put("/settings", summary="更新 MoviePilot 集成全局开关（revision CAS）", response_model=CommonResponse)
async def update_moviepilot_settings(
    payload: SettingsUpdateRequest,
    request: Request,
    _principal: AuthenticatedPrincipal = Depends(require_moviepilot_integration_user),
    db: Session = Depends(get_db),
    adb: AsyncSession = Depends(get_async_db),
) -> CommonResponse:
    service = MoviePilotSettingsService(db)
    try:
        snapshot = service.update_settings(
            enabled=payload.enabled,
            expected_revision=payload.expectedRevision,
            updated_by=_principal.username,
        )
    except MoviePilotSettingsRevisionConflict as exc:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            f"配置已被其他会话修改，请刷新后重试（当前 revision={exc.current_revision}）",
            data={"currentRevision": exc.current_revision},
        ) from exc
    except MoviePilotSettingsStateError as exc:
        raise _http_error(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await _log_audit(
        adb=adb,
        principal=_principal,
        audit_context=AuditContext.from_request(request),
        operation_type=AuditOperationType.MOVIEPILOT_SETTINGS_UPDATE,
        operation_detail={"enabled": snapshot.enabled, "revision": snapshot.revision},
        result=AuditOperationResult.SUCCESS,
    )
    return CommonResponse(status="success", msg="更新成功", code="200", data={"settings": snapshot.to_payload()})


@router.get("/instances", summary="已注册 MoviePilot 实例列表（分页）", response_model=CommonResponse)
def list_moviepilot_instances(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    _principal: AuthenticatedPrincipal = Depends(require_moviepilot_integration_user),
    db: Session = Depends(get_db),
) -> CommonResponse:
    instances = MoviePilotIntegrationService(db).list_instances()
    total = len(instances)
    start = (page - 1) * pageSize
    window = instances[start : start + pageSize]
    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data={"total": total, "page": page, "pageSize": pageSize, "list": window},
    )


@router.put("/instances/{instance_id}", summary="更新实例（名称/启用/下载器映射）", response_model=CommonResponse)
async def update_moviepilot_instance(
    instance_id: str,
    payload: InstanceUpdateRequest,
    request: Request,
    _principal: AuthenticatedPrincipal = Depends(require_moviepilot_integration_user),
    db: Session = Depends(get_db),
    adb: AsyncSession = Depends(get_async_db),
) -> CommonResponse:
    service = MoviePilotIntegrationService(db)
    try:
        result = service.update_instance(instance_id, payload.model_dump(exclude_none=True))
    except Exception as exc:
        raise _map_service_error(exc) from exc

    await _log_audit(
        adb=adb,
        principal=_principal,
        audit_context=AuditContext.from_request(request),
        operation_type=AuditOperationType.MOVIEPILOT_INSTANCE_UPDATE,
        operation_detail={"instanceId": instance_id, "changes": payload.model_dump(exclude_none=True)},
        result=AuditOperationResult.SUCCESS,
    )
    return CommonResponse(status="success", msg="更新成功", code="200", data=result)


@router.delete("/instances/{instance_id}", summary="删除实例及其历史镜像", response_model=CommonResponse)
async def delete_moviepilot_instance(
    instance_id: str,
    request: Request,
    _principal: AuthenticatedPrincipal = Depends(require_moviepilot_integration_user),
    db: Session = Depends(get_db),
    adb: AsyncSession = Depends(get_async_db),
) -> CommonResponse:
    service = MoviePilotIntegrationService(db)
    try:
        result = service.delete_instance(instance_id)
    except Exception as exc:
        raise _map_service_error(exc) from exc

    await _log_audit(
        adb=adb,
        principal=_principal,
        audit_context=AuditContext.from_request(request),
        operation_type=AuditOperationType.MOVIEPILOT_INSTANCE_UPDATE,
        operation_detail={
            "instanceId": instance_id,
            "action": "delete",
            "deletedHistories": result["deletedHistories"],
        },
        result=AuditOperationResult.SUCCESS,
    )
    return CommonResponse(status="success", msg="删除成功", code="200", data=result)


# ==============================================================================
# 查询面（种子详情「媒体库」页签 / 路径反查）
# ==============================================================================


@router.get("/associations", summary="种子任务 → MoviePilot 整理历史（媒体库/源文件）", response_model=CommonResponse)
def get_torrent_associations(
    downloaderId: str = Query(min_length=1, max_length=64),
    hash: str = Query(min_length=1, max_length=64),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    _user: Any = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> CommonResponse:
    service = MoviePilotIntegrationService(db)
    items, total = service.get_associations_for_torrent(downloaderId, hash, page, pageSize)
    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data={"total": total, "page": page, "pageSize": pageSize, "list": items},
    )


@router.get("/associations/reverse", summary="媒体/源路径 → 关联历史与任务（反查）", response_model=CommonResponse)
def reverse_lookup_associations(
    path: str = Query(max_length=1024),
    mode: str = Query(default="both", pattern="^(src|dest|both)$"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    _user: Any = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> CommonResponse:
    service = MoviePilotIntegrationService(db)
    try:
        items, total = service.reverse_lookup(path, mode, page, pageSize)
    except MoviePilotSyncPayloadError as exc:
        raise _http_error(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data={"total": total, "page": page, "pageSize": pageSize, "list": items},
    )
